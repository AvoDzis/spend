"""`spend report [YYYY-MM] [--email]`: the month-end report (totals, charts, biggest expenses, trend),
printed or emailed through Gmail. The Gmail app password is read from the macOS Keychain, never a file:

  security add-generic-password -s spend-gmail -a you@gmail.com -w     # asks for the password

`make schedule EMAIL=you@gmail.com` runs `spend report --email` on the 1st of every month at 10:00.
"""
import argparse
import os
import smtplib
import ssl
import subprocess
import sys
from collections import Counter
from datetime import date
from email.message import EmailMessage
from html import escape

from . import chart, config, inbox, journal, report
from .report import YM_RE, fmt_money, month_name, prev_month

KEYCHAIN_SERVICE = "spend-gmail"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
CURRENCY_ORDER = report.CURRENCY_ORDER


def last_month(today: date | None = None) -> str:
    return prev_month((today or date.today()).strftime("%Y-%m"))


def build(ym: str, problem: str | None = None) -> tuple[str, str]:
    """(subject, plain-text body) for one month."""
    path = config.journal()
    every = journal.read_entries(path)
    this = [e for e in every if e.date.startswith(ym)]
    totals: dict[str, object] = {}
    for e in this:
        totals[e.currency] = totals.get(e.currency, 0) + e.amount
    curs = [c for c in CURRENCY_ORDER if c in totals] + sorted(set(totals) - set(CURRENCY_ORDER))
    spent = " + ".join(f"{fmt_money(totals[c], c)} {c}" for c in curs) or "nothing logged"
    subject = f"Spending · {month_name(ym)}: {spent}"

    parts = []
    if problem:
        parts.append(f"⚠ {problem}; entries logged on the phone since your last `spend month` may be missing.\n")
    if path.exists():
        t = report.month_totals(path, [prev_month(ym), ym])
        parts.append(report.render_month(ym, t[ym], t[prev_month(ym)]))
    for cur in curs:
        of_cur = [e for e in every if e.currency == cur]
        parts.append(chart.render_bars(ym, cur, of_cur))
        parts.append(chart.render_top(ym, 5, cur, of_cur))
    if "AMD" in totals:
        amd = [e for e in every if e.currency == "AMD"]
        parts.append(chart.render_days(ym, "AMD", amd))
        parts.append(chart.render_trend(ym, 6, "AMD", amd))
    sources = Counter(e.tags.partition("src:")[2].split(",")[0].strip() or "cli" for e in this)
    names = {"cli": "terminal", "phone": "phone", "claude": "Claude", "bank": "bank import"}
    parts.append(f"{len(this)} entries ({', '.join(f'{n} {names.get(s, s)}' for s, n in sources.most_common())}). "
                 f"Sent by `spend report` on {date.today():%Y-%m-%d}.\n" if this else
                 f"Sent by `spend report` on {date.today():%Y-%m-%d}.\n")
    return subject, "\n".join(parts)


def password(address: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", address, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def send(subject: str, body: str, address: str, secret: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"spend <{address}>", address
    msg.set_content(body)
    msg.add_alternative('<pre style="font-family: Menlo, Consolas, monospace; font-size: 13px; line-height: 1.35">'
                        f"{escape(body)}</pre>", subtype="html")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as s:
        s.login(address, secret)
        s.send_message(msg)


def run(args: list[str], dry_run: bool = False) -> int:
    p = argparse.ArgumentParser(prog="spend report", description="Month-end report: printed, or emailed.")
    p.add_argument("month", nargs="?", metavar="YYYY-MM", help="default: last month")
    p.add_argument("--email", action="store_true", help="send it by Gmail instead of printing")
    p.add_argument("--to", metavar="ADDRESS", help="default: $SPEND_EMAIL")
    try:
        a = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 0)
    ym = a.month or last_month()
    if not YM_RE.match(ym):
        print(f"spend report: {ym!r} isn't a month, use YYYY-MM", file=sys.stderr)
        return 2

    problem = inbox.sync()
    try:
        subject, body = build(ym, problem)
    except (FileNotFoundError, RuntimeError) as e:  # hledger missing or failing
        print(f"spend report: {e}", file=sys.stderr)
        return 1
    if not a.email or dry_run:
        print(("(would email) " if a.email else "") + subject + "\n\n" + body, end="")
        return 0

    address = a.to or os.environ.get("SPEND_EMAIL")
    if not address:
        print("spend report: who to? set SPEND_EMAIL or pass --to you@gmail.com", file=sys.stderr)
        return 2
    secret = password(address)
    if not secret:
        print(f"spend report: no Gmail app password in the Keychain for {address}. Create one at "
              "https://myaccount.google.com/apppasswords, then run:\n"
              f"  security add-generic-password -s {KEYCHAIN_SERVICE} -a {address} -w", file=sys.stderr)
        return 1
    try:
        send(subject, body, address, secret)
    except (OSError, smtplib.SMTPException) as e:
        print(f"spend report: sending failed: {e}", file=sys.stderr)
        return 1
    print(f"sent \"{subject}\" to {address}")
    return 0
