"""Monthly summary (via hledger) and recent entries (via journal.read_entries)."""
import csv
import io
import re
import sys
from datetime import date
from decimal import Decimal

from . import config, journal
from .parse import DEFAULT_CURRENCY

CURRENCY_ORDER = ["AMD", "USD", "EUR"]  # first columns; any other currency follows alphabetically
YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SRC_RE = re.compile(r"\bsrc:([^,\s]+)")
NONE = "-"

Totals = dict[str, dict[str, Decimal]]  # category -> currency -> amount


def prev_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def next_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def month_name(ym: str, fmt: str = "%B %Y") -> str:
    y, m = map(int, ym.split("-"))
    return date(y, m, 1).strftime(fmt)


def fmt_money(amount: Decimal, currency: str) -> str:
    """12300 AMD → "12,300", 50 USD → "50.00". AMD keeps decimals only when it has them."""
    whole = currency == "AMD" and amount == amount.to_integral_value()
    return f"{amount:,.{0 if whole else 2}f}"


def month_totals(path, months: list[str]) -> dict[str, Totals]:
    """{"2026-10": {"groceries": {"AMD": Decimal("800")}}, ...} for each month, from hledger.
    Sub-accounts roll up to their category (expenses:food:restaurants → food)."""
    out = journal.hledger(path, "bal", "expenses", "--depth", "2", "-M",
                          "-b", f"{min(months)}-01", "-e", f"{next_month(max(months))}-01",
                          "-O", "csv", "--layout", "tidy")
    result: dict[str, Totals] = {m: {} for m in months}
    for row in csv.DictReader(io.StringIO(out)):
        value = Decimal(row["value"].replace(",", ""))
        ym = row["start_date"][:7]
        if not value or ym not in result:
            continue
        category = row["account"].partition(":")[2] or "other"
        currency = row["commodity"] or DEFAULT_CURRENCY
        cell = result[ym].setdefault(category, {})
        cell[currency] = cell.get(currency, Decimal(0)) + value
    return result


def column_total(totals: Totals) -> dict[str, Decimal]:
    sums: dict[str, Decimal] = {}
    for by_cur in totals.values():
        for cur, v in by_cur.items():
            sums[cur] = sums.get(cur, Decimal(0)) + v
    return sums


def currencies(*sums: dict[str, Decimal]) -> list[str]:
    seen = {c for s in sums for c, v in s.items() if v}
    return [c for c in CURRENCY_ORDER if c in seen] + sorted(seen - set(CURRENCY_ORDER))


def render_month(ym: str, this: Totals, last: Totals) -> str:
    """Table: one row per category, one column per currency, then this month's and last month's totals."""
    total, last_total = column_total(this), column_total(last)
    curs = currencies(total, last_total)
    title = month_name(ym)
    if not curs:
        return f"{title}: nothing logged (nothing in {month_name(prev_month(ym))} either)\n"

    def cells(by_cur: dict[str, Decimal]) -> list[str]:
        return [fmt_money(by_cur[c], c) if by_cur.get(c) else NONE for c in curs]

    cats = sorted(this, key=lambda cat: ([-this[cat].get(c, 0) for c in curs], cat))
    rows = [(cat, cells(this[cat])) for cat in cats]
    foot = [("total", cells(total)), (f"last month ({month_name(prev_month(ym), '%b')})", cells(last_total))]
    label_w = max(len(r[0]) for r in rows + foot)
    col_w = [max(len(c), *(len(r[1][i]) for r in rows + foot)) for i, c in enumerate(curs)]

    def line(label: str, values: list[str]) -> str:
        return f"  {label:<{label_w}}" + "".join(f"  {v:>{w}}" for v, w in zip(values, col_w))

    out = [title, line("", curs)]
    out += [line(label, vals) for label, vals in rows] or ["  nothing logged yet"]
    out.append("  " + "─" * (label_w + sum(w + 2 for w in col_w)))
    out += [line(label, vals) for label, vals in foot]
    return "\n".join(out) + "\n"


def month(ym: str | None = None) -> int:
    """`spend month [YYYY-MM]`: totals by category, one column per currency, plus last month's totals."""
    ym = ym or date.today().strftime("%Y-%m")
    if not YM_RE.match(ym):
        print(f"spend month: {ym!r} isn't a month, use YYYY-MM (e.g. 2026-10)", file=sys.stderr)
        return 2
    path = config.journal()
    if not path.exists():
        print(f"no entries yet ({path})")
        return 0
    try:
        t = month_totals(path, [prev_month(ym), ym])
    except FileNotFoundError:
        print("spend month: hledger not found (brew install hledger)", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"spend month: hledger failed: {e}", file=sys.stderr)
        return 1
    print(render_month(ym, t[ym], t[prev_month(ym)]), end="")
    return 0


def render_recent(entries: list[journal.Entry]) -> str:
    """Numbered from the end: the newest entry is 1 (shown last), so `spend fix 1` == `spend fix last`."""
    rows = []
    for i, e in enumerate(entries):
        src = SRC_RE.search(e.tags)
        note = e.note + (f" ({src[1]})" if src and src[1] != "cli" else "")
        rows.append((str(len(entries) - i), e.date, fmt_money(e.amount, e.currency), e.currency, e.category, note))
    w = [max(len(r[k]) for r in rows) for k in range(5)]
    return "".join(f"{n:>{w[0]}}  {d}  {a:>{w[2]}} {c:<{w[3]}}  {cat:<{w[4]}}  {note}\n"
                   for n, d, a, c, cat, note in rows)


def recent(n: int = 10) -> int:
    """`spend list [N]`: the last N entries, newest last, numbered so `spend fix N` can use them."""
    path = config.journal()
    entries = journal.read_entries(path)
    if not entries:
        print(f"no entries yet ({path})")
        return 0
    print(render_recent(entries[-n:] if n > 0 else entries), end="")
    return 0
