"""Turn free text like "800dram supermarket, 50usd jeans" into Expense records."""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

DEFAULT_CURRENCY = "AMD"
CURRENCIES = {
    "AMD": ["amd", "dram", "drams", "dr", "֏", "դր", "դրամ"],
    "USD": ["usd", "$", "dollar", "dollars"],
    "EUR": ["eur", "€", "euro", "euros"],
    "RUB": ["rub", "₽", "ruble", "rubles"],
    "GBP": ["gbp", "£", "pound", "pounds"],
}
ALIAS = {a: code for code, names in CURRENCIES.items() for a in names}

# "800", "1,500", "12.5", "1.5k", "$50", "50$", "800dram", "12k֏"
AMOUNT_RE = re.compile(r"^(?P<pre>[$€£₽֏])?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<k>[kK])?(?P<suf>\D*)$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_NAMES = ["jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july",
               "aug august", "sep sept september", "oct october", "nov november", "dec december"]
MONTHS = {n: i for i, names in enumerate(MONTH_NAMES, 1) for n in names.split()}
DAY_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?[.,:]?$")
GLUED_RE = re.compile(r"^(?:(\d{1,2})([a-z]{3,9})|([a-z]{3,9})(\d{1,2}))$")  # "1oct", "oct1"
# split "a, b; c" into separate expenses, but never "1,500"
SPLIT_RE = re.compile(r"[;\n]|,\s+")


class ParseError(ValueError):
    pass


@dataclass
class Expense:
    date: date
    amount: Decimal
    currency: str
    note: str
    category: str | None = None


def _number(num: str) -> Decimal:
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        num = num.replace(",", "")
    elif "," in num and "." not in num:
        num = num.replace(",", ".")  # decimal comma: "2,5"
    try:
        return Decimal(num)
    except InvalidOperation:
        raise ParseError(f"can't read the amount {num!r}")


def _amount(token: str):
    """(Decimal, currency or None) if the token is an amount, else None."""
    m = AMOUNT_RE.match(token)
    if not m:
        return None
    suf = m["suf"].lower()
    if suf and suf not in ALIAS:
        return None  # "3pm", "2x" are words, not amounts
    value = _number(m["num"]) * (1000 if m["k"] else 1)
    currency = ALIAS.get(m["pre"]) if m["pre"] else ALIAS.get(suf)
    return value, currency


def _date(token: str, today: date):
    t = token.lower()
    if t in ("today",):
        return today
    if t in ("yesterday", "yday"):
        return today - timedelta(days=1)
    if ISO_DATE_RE.match(t):
        return date.fromisoformat(t)
    return None


def _month_day(month: int, day: int, today: date) -> date | None:
    """Oct 1 → the most recent Oct 1 (typed in January, "dec 30" means last December)."""
    try:
        d = date(today.year, month, day)
        return d.replace(year=d.year - 1) if d > today + timedelta(days=1) else d
    except ValueError:
        return None


def _find_date(tokens: list[str], today: date) -> tuple[date | None, set[int]]:
    """The first date in a line ("yesterday", "2026-10-01", "oct 1", "1 oct", "oct1") and the tokens it used."""
    for i, tok in enumerate(tokens):
        t = tok.lower().rstrip(".,:")
        d = _date(t, today)
        if d:
            return d, {i}
        m = GLUED_RE.match(t)
        if m:
            day, mon = (m[1], m[2]) if m[1] else (m[4], m[3])
            if mon in MONTHS and (d := _month_day(MONTHS[mon], int(day), today)):
                return d, {i}
        if t in MONTHS:
            for j in (i + 1, i - 1):
                dm = DAY_RE.match(tokens[j].lower()) if 0 <= j < len(tokens) else None
                if dm and (d := _month_day(MONTHS[t], int(dm[1]), today)):
                    return d, {i, j}
    return None, set()


def parse_one(text: str, today: date | None = None) -> Expense:
    """One expense: an amount (with or without currency) anywhere, the rest is the note."""
    today = today or date.today()
    return _parse(text, today, today)[0]


def _parse(text: str, today: date, default: date) -> tuple[Expense, bool]:
    """(expense, whether the line named its own date); lines without a date get `default`."""
    tokens = text.split()
    found, used = _find_date(tokens, today)
    when, amount, currency = found or default, None, None
    for i, tok in enumerate(tokens):
        if i in used:
            continue
        hit = _amount(tok)
        if hit:
            amount, currency = hit
            used.add(i)
            if not currency:  # "800 dram" / "usd 50"
                for j in (i + 1, i - 1):
                    if 0 <= j < len(tokens) and j not in used and tokens[j].lower() in ALIAS:
                        currency = ALIAS[tokens[j].lower()]
                        used.add(j)
                        break
            break
    if amount is None:
        raise ParseError(f"no amount in {text.strip()!r}")
    note = " ".join(t for i, t in enumerate(tokens) if i not in used).strip(" ,.-")
    if not note:
        raise ParseError(f"what was {text.strip()!r} for? add a word, e.g. '{text.strip()} taxi'")
    return Expense(when, amount, currency or DEFAULT_CURRENCY, note), found is not None


def parse_many(text: str, today: date | None = None) -> list[Expense]:
    """Several expenses separated by ", " / ";" / newlines. A chunk without an amount joins the previous note.
    A date carries on to the expenses after it: "oct 1 1200 taxi, 4500 sas, oct 2 300 coffee"."""
    today = today or date.today()
    chunks = [c.strip() for c in SPLIT_RE.split(text) if c.strip()]
    merged: list[str] = []
    for c in chunks:
        if merged and not any(_amount(t) for t in c.split()):
            merged[-1] += ", " + c
        else:
            merged.append(c)
    out, current = [], today
    for c in merged:
        e, dated = _parse(c, today, current)
        if dated:
            current = e.date
        out.append(e)
    return out
