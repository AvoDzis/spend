"""`spend chart`: spending as text charts — bars per category, a monthly trend, a calendar of days,
one category over time, the biggest expenses. One currency at a time (default AMD), no conversion."""
import argparse
import calendar
import math
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal

from . import config, journal
from .parse import ALIAS, DEFAULT_CURRENCY
from .report import YM_RE, fmt_money, month_name, prev_month

EIGHTHS = "▏▎▍▌▋▊▉█"
SPARK = "▁▂▃▄▅▆▇█"
SHADES = "░▒▓█"
WIDTH = 24
ZERO = Decimal(0)


def bar(value: Decimal, top: Decimal, width: int = WIDTH) -> str:
    """A horizontal bar `width` cells long for `top`, drawn in eighths of a cell."""
    if top <= 0 or value <= 0:
        return ""
    full, rest = divmod(max(1, round(float(value) / float(top) * width * 8)), 8)
    return "█" * full + (EIGHTHS[rest - 1] if rest else "")


def spark(values: list[Decimal]) -> str:
    """One character per value, scaled to the largest; a gap for zero."""
    top = float(max(values, default=ZERO))
    return "".join(SPARK[max(0, math.ceil(float(v) / top * 8) - 1)] if v > 0 else " " for v in values)


def shade(value: Decimal, top: Decimal) -> str:
    return SHADES[min(3, int(float(value) / float(top) * 4))] if value > 0 else "·"


def months_back(end: str, n: int) -> list[str]:
    months = [end]
    while len(months) < n:
        months.insert(0, prev_month(months[0]))
    return months


def pct(part: Decimal, whole: Decimal) -> str:
    return f"{round(float(part) / float(whole) * 100)}%" if whole else ""


def render_bars(ym: str, cur: str, entries: list[journal.Entry]) -> str:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for e in entries:
        if e.date.startswith(ym):
            totals[e.category] += e.amount
    if not totals:
        return f"{month_name(ym)}: nothing in {cur}\n"
    rows = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    total, top = sum(totals.values()), rows[0][1]
    w = max(len("total"), *(len(c) for c, _ in rows))
    aw = len(fmt_money(total, cur))
    out = [f"{month_name(ym)} · {cur} per category"]
    out += [f"  {c:<{w}}  {bar(v, top):<{WIDTH}}  {fmt_money(v, cur):>{aw}}  {pct(v, total):>4}" for c, v in rows]
    out.append(f"  {'total':<{w}}  {'':<{WIDTH}}  {fmt_money(total, cur):>{aw}}")
    return "\n".join(out) + "\n"


def render_trend(end: str, n: int, cur: str, entries: list[journal.Entry], title: str | None = None,
                 by_category: bool = True) -> str:
    months = months_back(end, n)
    per_month = {m: ZERO for m in months}
    per_cat: dict[str, dict[str, Decimal]] = defaultdict(lambda: {m: ZERO for m in months})
    for e in entries:
        m = e.date[:7]
        if m in per_month:
            per_month[m] += e.amount
            per_cat[e.category][m] += e.amount
    title = title or f"Last {n} months · {cur}"
    top = max(per_month.values())
    if not top:
        return f"{title}: nothing logged\n"
    aw = max(len(fmt_money(v, cur)) for v in per_month.values())
    out = [title]
    out += [f"  {month_name(m, '%b %Y')}  {bar(per_month[m], top):<{WIDTH}}  {fmt_money(per_month[m], cur):>{aw}}"
            for m in months]
    if by_category and per_cat:
        cats = sorted(per_cat, key=lambda c: (-sum(per_cat[c].values()), c))
        w = max(len(c) for c in cats)
        out += ["", f"  by category, {month_name(months[0], '%b')} → {month_name(months[-1], '%b')}:"]
        out += [f"  {c:<{w}}  {spark([per_cat[c][m] for m in months])}  "
                f"{fmt_money(per_cat[c][months[-1]], cur)} in {month_name(months[-1], '%b')}" for c in cats]
    return "\n".join(out) + "\n"


def render_days(ym: str, cur: str, entries: list[journal.Entry]) -> str:
    """A calendar of the month; each day shaded by how much was spent (· = nothing)."""
    y, mo = map(int, ym.split("-"))
    daily: dict[int, Decimal] = defaultdict(Decimal)
    for e in entries:
        if e.date.startswith(ym):
            daily[int(e.date[8:10])] += e.amount
    if not daily:
        return f"{month_name(ym)}: nothing in {cur}\n"
    top = max(daily.values())
    big = max(daily, key=lambda d: daily[d])
    out = [f"{month_name(ym)} · {cur} per day", "   " + " ".join(f"{d:>3}" for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))]
    for week in calendar.Calendar().monthdayscalendar(y, mo):
        out.append("   " + " ".join(f"{d:>2}{shade(daily.get(d, ZERO), top)}" if d else "   " for d in week))
    total = sum(daily.values())
    out += ["", f"  · nothing  {''.join(SHADES)} more   biggest day: {date(y, mo, big):%b %-d} "
                f"({fmt_money(top, cur)})   total {fmt_money(total, cur)} over {len(daily)} days"]
    return "\n".join(out) + "\n"


def render_top(ym: str, n: int, cur: str, entries: list[journal.Entry]) -> str:
    picked = sorted((e for e in entries if e.date.startswith(ym)), key=lambda e: -e.amount)[:n]
    if not picked:
        return f"{month_name(ym)}: nothing in {cur}\n"
    aw = max(len(fmt_money(e.amount, cur)) for e in picked)
    cw = max(len(e.category) for e in picked)
    out = [f"{month_name(ym)} · biggest {len(picked)} in {cur}"]
    out += [f"  {e.date}  {fmt_money(e.amount, cur):>{aw}}  {e.category:<{cw}}  {e.note}" for e in picked]
    return "\n".join(out) + "\n"


def run(args: list[str]) -> int:
    """`spend chart [--trend [N]] [--days] [--cat C] [--top [N]] [--month YYYY-MM] [--currency CUR]`"""
    p = argparse.ArgumentParser(prog="spend chart", description="Spending as text charts. "
                                "No view option = bars per category for the month.")
    p.add_argument("--month", metavar="YYYY-MM", help="month to show (default: this month)")
    p.add_argument("--currency", metavar="CUR", default=DEFAULT_CURRENCY, help="AMD (default), USD, EUR…")
    p.add_argument("--trend", nargs="?", const=6, type=int, metavar="N", help="last N months (default 6)")
    p.add_argument("--days", action="store_true", help="calendar of the month, shaded by spending")
    p.add_argument("--cat", metavar="CATEGORY", help="one category over the last 6 months (or --trend N)")
    p.add_argument("--top", nargs="?", const=10, type=int, metavar="N", help="biggest N expenses (default 10)")
    try:
        a = p.parse_args(args)
    except SystemExit as e:
        return int(e.code or 0)
    ym = a.month or date.today().strftime("%Y-%m")
    if not YM_RE.match(ym):
        p.print_usage()
        print(f"spend chart: {ym!r} isn't a month, use YYYY-MM", file=sys.stderr)
        return 2
    cur = ALIAS.get(a.currency.lower(), a.currency.upper())
    every = journal.read_entries(config.journal())
    entries = [e for e in every if e.currency == cur]

    views = []
    if a.cat:
        cat = journal.account_name(a.cat)
        views.append(render_trend(ym, a.trend or 6, cur, [e for e in entries if e.category == cat],
                                  title=f"{cat} · last {a.trend or 6} months · {cur}", by_category=False))
    elif a.trend:
        views.append(render_trend(ym, a.trend, cur, entries))
    if a.days:
        views.append(render_days(ym, cur, entries))
    if a.top:
        views.append(render_top(ym, a.top, cur, entries))
    if not views:
        views.append(render_bars(ym, cur, entries))
    print("\n".join(views), end="")

    others = sorted({e.currency for e in every if e.date.startswith(ym)} - {cur})
    if others:
        print(f"\n  also spent in {', '.join(others)}: add --currency {others[0]}")
    return 0
