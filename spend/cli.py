"""spend — log expenses as one short line.

  spend 800dram supermarket, 50usd jeans   log one or more expenses (no currency = AMD)
  spend yesterday 1200 taxi                 dates: today, yesterday, YYYY-MM-DD
  spend inbox                              import lines from the iPhone inbox
  spend month [YYYY-MM]                    totals by category, per currency
  spend list [N]                           last N entries
  spend fix last|N <category>              change a category (and learn the rule)
  spend cats                               categories and their keywords

Options: -n / --dry-run (show, don't write), --src <name> (tag where it came from; default cli).
"""
import sys

from . import categories, config, inbox, journal, report
from .parse import ParseError, parse_many

COMMANDS = {"add", "inbox", "month", "list", "fix", "cats", "help"}


def add(text: str, dry_run: bool = False, source: str = "cli") -> int:
    try:
        expenses = parse_many(text)
    except ParseError as e:
        print(f"spend: {e}", file=sys.stderr)
        return 2
    for e in expenses:
        e.category = categories.categorize(e.note)
    if not dry_run:
        journal.append(config.journal(), expenses, source)
    verb = "would log" if dry_run else "logged"
    for e in expenses:
        print(f"{verb} {journal.fmt_amount(e.amount)} {e.currency} · {e.category} · {e.note} ({e.date})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run, source = False, "cli"
    for flag in ("-n", "--dry-run"):
        if flag in args:
            args.remove(flag)
            dry_run = True
    if "--src" in args:
        i = args.index("--src")
        source = args[i + 1] if i + 1 < len(args) else source
        del args[i:i + 2]
    if not args or args[0] in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0
    cmd, rest = args[0], args[1:]
    if cmd not in COMMANDS:
        return add(" ".join(args), dry_run, source)
    if cmd == "add":
        return add(" ".join(rest), dry_run, source)
    if cmd == "inbox":
        return inbox.run(dry_run)
    if cmd == "month":
        return report.month(rest[0] if rest else None)
    if cmd == "list":
        return report.recent(int(rest[0]) if rest else 10)
    if cmd == "fix":
        if len(rest) < 2:
            print("usage: spend fix last|N <category>", file=sys.stderr)
            return 2
        return categories.fix(rest[0], " ".join(rest[1:]))
    if cmd == "cats":
        return categories.show()
    return 2
