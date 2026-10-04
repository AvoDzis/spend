"""spend — log expenses as one short line.

  spend 800dram supermarket, 50usd jeans   log one or more expenses (no currency = AMD)
  spend yesterday 1200 taxi                 dates: today, yesterday, YYYY-MM-DD
  spend inbox                              import lines from the iPhone inbox (month/list do it too)
  spend import <bank.csv> [--month YYYY-MM]  one-time backfill from a bank export (card payments)
  spend month [YYYY-MM]                    totals by category, per currency
  spend list [N]                           last N entries
  spend chart [--trend|--days|--cat C|--top]  text charts (spend chart -h for options)
  spend report [YYYY-MM] [--email]         month-end report (default: last month), printed or emailed
  spend fix last|N <category> [--word kw]  change a category and learn the note (or just kw); --once: no rule
  spend learn <keyword> <category>         add a keyword rule
  spend rm last|N [N …]                    delete entries (asks first; -y skips the question)
  spend cats                               categories and their keywords

Options: -n / --dry-run (show, don't write), -y / --yes (don't ask), --src <name> (tag where it came from; default cli).
"""
import sys

from . import bankcsv, categories, chart, config, inbox, journal, monthly, report
from .parse import ParseError, parse_many

COMMANDS = {"add", "inbox", "month", "list", "chart", "report", "import", "fix", "learn", "rm", "cats", "help"}


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


def rm(targets: list[str], yes: bool = False, dry_run: bool = False) -> int:
    """`spend rm last|N [N …]`: delete entries, numbered like `spend list` (1 = newest)."""
    path = config.journal()
    entries = journal.read_entries(path)
    picked = []
    for t in targets:
        n = 1 if t == "last" else int(t) if t.isdigit() else 0
        if n < 1:
            print(f"spend rm: which entry? 'last' or a number from `spend list` (1 = newest), not {t!r}",
                  file=sys.stderr)
            return 2
        if n > len(entries):
            print(f"spend rm: there are only {len(entries)} entries in {path}", file=sys.stderr)
            return 1
        if entries[-n] not in picked:
            picked.append(entries[-n])
    lines = [f"{journal.fmt_amount(e.amount)} {e.currency} · {e.category} · {e.note} ({e.date})" for e in picked]
    if dry_run:
        print("".join(f"would remove {line}\n" for line in lines), end="")
        return 0
    if not yes:
        if not sys.stdin.isatty():
            print("".join(f"spend rm: would remove {line}\n" for line in lines) + "add -y to confirm",
                  file=sys.stderr)
            return 2
        print("".join(f"  {line}\n" for line in lines), end="")
        if input(f"remove {'these' if len(lines) > 1 else 'this'}? [y/N] ").strip().lower() not in ("y", "yes"):
            print("kept")
            return 1
    journal.remove(path, picked)
    print("".join(f"removed {line}\n" for line in lines), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run, yes, source = False, False, "cli"
    for flag in ("-n", "--dry-run"):
        if flag in args:
            args.remove(flag)
            dry_run = True
    for flag in ("-y", "--yes"):
        if flag in args:
            args.remove(flag)
            yes = True
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
    if cmd in ("month", "list", "chart") and not dry_run:
        inbox.sync()  # phone entries show up without running `spend inbox` first
    if cmd == "month":
        return report.month(rest[0] if rest else None)
    if cmd == "list":
        return report.recent(int(rest[0]) if rest else 10)
    if cmd == "chart":
        return chart.run(rest)
    if cmd == "report":
        return monthly.run(rest, dry_run)
    if cmd == "import":
        return bankcsv.run(rest, dry_run)
    if cmd == "fix":
        word, once = None, "--once" in rest
        rest = [a for a in rest if a != "--once"]
        if "--word" in rest:
            i = rest.index("--word")
            rest, word = rest[:i], " ".join(rest[i + 1:])
        if len(rest) < 2 or word == "":
            print("usage: spend fix last|N <category> [--word <keyword>]", file=sys.stderr)
            return 2
        return categories.fix(rest[0], " ".join(rest[1:]), word, learn=not once)
    if cmd == "learn":
        if len(rest) < 2:
            print("usage: spend learn <keyword> <category>", file=sys.stderr)
            return 2
        return categories.learn(" ".join(rest[:-1]), rest[-1])
    if cmd == "rm":
        if not rest:
            print("usage: spend rm last|N [N …]  (numbers from `spend list`)", file=sys.stderr)
            return 2
        return rm(rest, yes, dry_run)
    if cmd == "cats":
        return categories.show()
    return 2
