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
from datetime import date
from email.message import EmailMessage

from . import config, digest, inbox, journal
from .report import YM_RE, prev_month

KEYCHAIN_SERVICE = "spend-gmail"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def last_month(today: date | None = None) -> str:
    return prev_month((today or date.today()).strftime("%Y-%m"))


def build(ym: str, problem: str | None = None) -> digest.Digest:
    return digest.Digest.build(ym, journal.read_entries(config.journal()), problem)


def password(address: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", address, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def send(d: digest.Digest, address: str, secret: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = d.subject, f"spend <{address}>", address
    msg.set_content(digest.render_text(d))
    msg.add_alternative(digest.render_html(d), subtype="html")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as s:
        s.login(address, secret)
        s.send_message(msg)


def run(args: list[str], dry_run: bool = False) -> int:
    p = argparse.ArgumentParser(prog="spend report", description="Month-end report: printed, or emailed.")
    p.add_argument("month", nargs="?", metavar="YYYY-MM", help="default: last month")
    p.add_argument("--email", action="store_true", help="send it by Gmail instead of printing")
    p.add_argument("--to", metavar="ADDRESS", help="default: $SPEND_EMAIL")
    p.add_argument("--html", metavar="FILE", help="also write the email's HTML to FILE (to preview it)")
    try:
        a = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 0)
    ym = a.month or last_month()
    if not YM_RE.match(ym):
        print(f"spend report: {ym!r} isn't a month, use YYYY-MM", file=sys.stderr)
        return 2

    d = build(ym, inbox.sync())
    if a.html:
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(digest.render_html(d))
        print(f"wrote {a.html}")
    if not a.email or dry_run:
        print(("(would email) " if a.email else "") + digest.render_text(d), end="")
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
        send(d, address, secret)
    except (OSError, smtplib.SMTPException) as e:
        print(f"spend report: sending failed: {e}", file=sys.stderr)
        return 1
    print(f"sent \"{d.subject}\" to {address}")
    return 0
