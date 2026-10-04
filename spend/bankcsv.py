"""`spend import <bank.csv>`: a one-time backfill from the bank's CSV export (card payments only).

The export has one row per transaction:
  "Transaction date","Settlement date","Transaction type","Transaction details",
  "Transaction amount","Transaction amount in account currency"
  "12/09/26, 18:40", …, "Քարտային գործարք", "POS: SAS SUPERMARKET\\YEREVAN AM 123456", "-4,500.00 AMD", …

Card payments and bill payments (outgoing transfers like "Ucom Payment: …" or city parking) become
expenses in the paid currency, tagged src:bank. Personal transfers out and card refunds are skipped
and listed, since only you know what they were; incoming money is ignored. Every imported row is
remembered (config.import_state()), so importing the same or an overlapping export twice is safe.
"""
import csv
import fcntl
import hashlib
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import categories, config, journal
from .parse import Expense

SOURCE = "bank"
COLUMNS = ["Transaction date", "Transaction type", "Transaction details", "Transaction amount"]
CARD = "Քարտային գործարք"  # card transaction; the other type seen is "Փոխանցում հաշվին" (transfer)
PERSONAL = re.compile(r"personal transfer|transfer of own funds|անձնական փոխանցում", re.I)
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})")
AMOUNT_RE = re.compile(r"^\s*([+-]?)\s*([\d,]+(?:\.\d+)?)\s*([A-Z]{3})\s*$")
STATE_HEADER = "# spend import: sha256 of every bank-CSV row already imported (one per line)\n"


def clean(details: str) -> str:
    """"POS: SAS SUPERMARKET\\YEREVAN AM 123456" → "sas supermarket",
    "MCDONALDS VISA SALES WIEN 0" → "mcdonalds"."""
    s = re.sub(r"^[^:]{1,15}:\s*", "", details)          # "POS: " style prefix
    s = re.sub(r"^[\w.]{2,12}\s?\*\s?", "", s)            # payment processor: "POLAR* HIRIFY" → "HIRIFY"
    s = s.replace("\\", " ").replace("*", " ")
    s = re.split(r"\s+(?:e?pos\s+purchase|purchase\s+po\w*|visa\s+sales)\b", s, flags=re.I)[0]  # the bank's own words
    s = re.sub(r"\s+վիրտ\S*\s*$", "", s)                  # "virtual card" marker (often cut short)
    s = re.sub(r"^visa\s+", "", s, flags=re.I)
    s = re.sub(r"\s+(?:AM|[A-Z]{2}\s+\d+)\s*$", "", s)     # trailing country code + terminal id
    s = re.sub(r"\s\d{3,}\b", " ", s)                     # stray long numbers
    s = re.sub(r"\s+yerevan(?:\s+\w{1,2})?\s*$", "", s, flags=re.I)  # the city adds nothing
    ws = re.sub(r"\s+", " ", s).strip(" .,-/").lower().split()
    ws = [w for i, w in enumerate(ws) if w not in ws[:i]]   # "backyard backyard" → "backyard"
    return " ".join(ws) or details.strip().lower()


def clean_transfer(details: str) -> str:
    """"Ucom Payment: 123 / ab1c" → "ucom payment"; "|ONLINE| 12BX345, Zone A, 2 hours, …" → "parking zone a"."""
    d = details.strip()
    if d.upper().startswith("|ONLINE|") and re.search(r"\bzone\b", d, re.I):
        zone = re.search(r"\bzone\s+(\w)", d, re.I)
        return f"parking zone {zone[1].lower()}" if zone else "parking"
    m = re.match(r"^(.{2,40}?)\s*payment\s*:", d, re.I)
    return f"{m[1].strip().lower()} payment" if m else clean(d)


def parse_date(text: str) -> date:
    m = DATE_RE.match(text.strip())
    if not m:
        raise ValueError(f"bad date {text!r}")
    d, mo, y = (int(g) for g in m.groups())
    return date(y + 2000 if y < 100 else y, mo, d)


def parse_amount(text: str) -> tuple[Decimal, str]:
    """"-4,500.00 AMD" → (Decimal("-4500.00"), "AMD")."""
    m = AMOUNT_RE.match(text)
    if not m:
        raise ValueError(f"bad amount {text!r}")
    try:
        value = Decimal(m[2].replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"bad amount {text!r}")
    return (-value if m[1] == "-" else value), m[3]


def key(row: dict) -> str:
    raw = "\x1f".join(row.get(c, "").strip() for c in COLUMNS)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read(path: Path, month: str | None = None):
    """(expenses with their row keys, skipped rows as (reason, row), # incoming) from one export."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"not a bank export this importer knows (missing columns: {', '.join(missing)})")
        found, skipped, incoming = [], [], 0
        for row in reader:
            try:
                when = parse_date(row["Transaction date"])
                amount, currency = parse_amount(row["Transaction amount"])
            except ValueError as e:
                skipped.append((str(e), row))
                continue
            if month and when.strftime("%Y-%m") != month:
                continue
            card = row["Transaction type"].strip() == CARD
            details = row["Transaction details"]
            if amount >= 0:
                if card:
                    skipped.append(("refund", row))
                else:
                    incoming += 1
            elif not card and PERSONAL.search(details):
                skipped.append(("personal transfer", row))
            else:
                note = clean(details) if card else clean_transfer(details)
                found.append((Expense(when, -amount, currency, note, categories.categorize(note)), key(row)))
    return found, skipped, incoming


def run(args: list[str], dry_run: bool = False) -> int:
    """`spend import <bank.csv> [--month YYYY-MM]`"""
    month = None
    if "--month" in args:
        i = args.index("--month")
        month = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            print("spend import: --month needs YYYY-MM", file=sys.stderr)
            return 2
    if len(args) != 1:
        print("usage: spend import <bank.csv> [--month YYYY-MM]   (-n to preview)", file=sys.stderr)
        return 2
    path = Path(args[0]).expanduser()
    try:
        found, skipped, incoming = read(path, month)
    except (OSError, ValueError) as e:
        print(f"spend import: {e}", file=sys.stderr)
        return 1

    state = config.import_state()
    state.parent.mkdir(parents=True, exist_ok=True)
    with open(state, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        seen = fh.read()
        done = {ln.strip() for ln in seen.splitlines() if ln.strip() and not ln.startswith("#")}
        new = [(e, k) for e, k in found if k not in done]
        if new and not dry_run:
            journal.append(config.journal(), [e for e, _ in new], SOURCE)
            fh.write(("" if seen else STATE_HEADER) + "".join(k + "\n" for _, k in new))

    verb = "would import" if dry_run else "imported"
    for e, _ in new:
        print(f"{verb} {journal.fmt_amount(e.amount)} {e.currency} · {e.category} · {e.note} ({e.date})")
    if skipped:
        print(f"\nskipped {len(skipped)} (add any real spending by hand with `spend <date> <amount> <what>`):")
        for reason, row in skipped:
            print(f"  {reason}: {row.get('Transaction date', '')}  {row.get('Transaction amount', '')}  "
                  f"{row.get('Transaction details', '').strip()}")
    others = sum(1 for e, _ in new if e.category == "other")
    print(f"\n{verb} {len(new)}, already there {len(found) - len(new)}, skipped {len(skipped)}"
          + (f", ignored {incoming} incoming" if incoming else "")
          + (f"; {others} in 'other': see `spend list`, then `spend fix N <cat> --word <shop>`" if others else ""))
    return 0
