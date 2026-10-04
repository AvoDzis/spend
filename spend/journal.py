"""Read and write the hledger journal. Each expense is one 3-line entry:

2026-10-04 supermarket  ; src:cli
    expenses:groceries    800 AMD
    assets:wallet
"""
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .parse import Expense

HEADER = """; spend journal, written by ~/Desktop/projects/spend (one entry per expense)
decimal-mark .
commodity 1,000. AMD
commodity 1,000.00 USD
commodity 1,000.00 EUR
commodity 1,000.00 RUB
commodity 1,000.00 GBP

"""
FUNDING = "assets:wallet"
ENTRY_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<note>.*?)(?:  ; (?P<tags>.*))?\n"
    r"    expenses:(?P<category>\S+)\s+(?P<amount>[\d.]+) (?P<currency>[A-Z]{3})\n"
    r"    " + re.escape(FUNDING) + r"\n",
    re.M,
)


@dataclass
class Entry:
    date: str
    note: str
    category: str
    amount: Decimal
    currency: str
    tags: str
    start: int  # character offsets in the file, used by set_category
    end: int


def account_name(category: str) -> str:
    return re.sub(r"[^\w-]+", "-", category.strip().lower()).strip("-") or "other"


def fmt_amount(amount: Decimal) -> str:
    s = f"{amount:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def format_entry(e: Expense, source: str = "cli") -> str:
    note = e.note.replace(";", ",").replace("\n", " ")
    cat = account_name(e.category or "other")
    return (f"{e.date.isoformat()} {note}  ; src:{source}\n"
            f"    expenses:{cat}    {fmt_amount(e.amount)} {e.currency}\n"
            f"    {FUNDING}\n\n")


def append(path: Path, expenses: list[Expense], source: str = "cli") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(format_entry(e, source) for e in expenses)
    with open(path, "a", encoding="utf-8") as fh:
        if fh.tell() == 0:
            fh.write(HEADER)
        fh.write(text)
    return text


def read_entries(path: Path) -> list[Entry]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [Entry(m["date"], m["note"], m["category"], Decimal(m["amount"]), m["currency"],
                  m["tags"] or "", m.start(), m.end())
            for m in ENTRY_RE.finditer(text)]


def set_category(path: Path, entry: Entry, category: str) -> None:
    """Rewrite one entry's expenses:<category> account in place."""
    text = path.read_text(encoding="utf-8")
    old = text[entry.start:entry.end]
    new = old.replace(f"    expenses:{entry.category} ", f"    expenses:{account_name(category)} ", 1)
    path.write_text(text[:entry.start] + new + text[entry.end:], encoding="utf-8")


def hledger(path: Path, *args: str) -> str:
    """Run hledger on the journal and return its stdout."""
    r = subprocess.run(["hledger", "-f", str(path), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout
