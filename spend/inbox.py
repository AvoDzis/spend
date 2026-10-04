"""Import lines the iPhone Shortcut appended to the iCloud inbox file (docs/phone-shortcut.md).

Each inbox line is a timestamp and an expense line, as the Shortcut writes it:

2026-10-04 14:32:05 800dram supermarket

The timestamp's date is the expense date ("yesterday" in the line counts back from it).
Every line is handled exactly once: `spend inbox` keeps a hash of each line it has handled in
config.inbox_state(), so re-running, iCloud duplicating a line or clearing the inbox never logs
anything twice. The inbox itself is only read, never written (the phone may be appending to it).
"""
import fcntl
import hashlib
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from . import categories, config, journal
from .parse import Expense, ParseError, parse_many

SOURCE = "phone"
# "2026-10-04 14:32:05", "2026-10-04 14:32", ISO 8601 "2026-10-04T14:32:05+04:00"; then " ", "|" or "\t"
LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"(?:\s*\|\s*|\s+|$)(?P<text>.*)$"
)
# the iPhone's own short date style (day first): "04.10.26, 18:18", "04.10.2026 18:18:05"
DOT_RE = re.compile(
    r"^(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4}|\d{2}),?\s+\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*\|\s*|\s+|$)(?P<text>.*)$"
)
STATE_HEADER = "# spend inbox: sha256 of every inbox line already handled (one per line)\n"


def key(line: str) -> str:
    return hashlib.sha256(" ".join(line.split()).encode("utf-8")).hexdigest()


def parse_line(line: str) -> list[Expense]:
    """Expenses in one inbox line ([] for a timestamp with nothing after it)."""
    m = LINE_RE.match(line) or DOT_RE.match(line)
    if not m:
        raise ParseError("no timestamp at the start (the Shortcut writes 'YYYY-MM-DD HH:MM:SS <expense>')")
    try:
        if "date" in m.groupdict():
            day = date.fromisoformat(m["date"])
        else:
            y = int(m["y"])
            day = date(y + 2000 if y < 100 else y, int(m["m"]), int(m["d"]))
    except ValueError:
        raise ParseError(f"bad date at the start of {line!r}")
    text = m["text"].strip()
    return parse_many(text, day) if text else []


def read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    return [line.strip() for line in text.splitlines() if line.strip()]


def scan(lines: list[str], done: set[str]):
    """Split inbox lines into (expenses to log, keys of newly handled lines, unreadable lines, # already done)."""
    logged, handled, bad, old = [], [], [], 0
    for line in lines:
        k = key(line)
        if k in done:
            old += 1
            continue
        done.add(k)  # an identical line later in the file is a duplicate
        handled.append(k)
        try:
            expenses = parse_line(line)
        except ParseError as e:
            bad.append((line, str(e)))
            continue
        for e in expenses:
            e.category = categories.categorize(e.note)
        logged += expenses
    return logged, handled, bad, old


def _keys(text: str) -> set[str]:
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def _download(path: Path) -> bool:
    """With "Optimize Mac Storage", iCloud may leave only a placeholder (.inbox.txt.icloud).
    Ask iCloud for the real file and wait a little. False if it's still not here."""
    stub = path.with_name(f".{path.name}.icloud")
    if path.exists() or not stub.exists():
        return True
    try:
        subprocess.run(["brctl", "download", str(path)], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass
    for _ in range(20):
        if path.exists():
            return True
        time.sleep(0.5)
    return False


def _blocked(path: Path) -> Path | None:
    """The nearest existing folder above the inbox that can't be read (macOS privacy, Claude's sandbox).
    Without this check a blocked iCloud folder looks the same as "no inbox yet"."""
    for d in path.parents:
        if d.is_dir():
            try:
                os.listdir(d)
            except PermissionError:
                return d
            return None
    return None


def _import(path: Path, dry_run: bool) -> tuple[list[Expense], list[tuple[str, str]], int]:
    """(logged, unreadable, # already done): import new inbox lines, or only scan them when dry_run."""
    state = config.inbox_state()
    if dry_run:
        done = _keys(state.read_text(encoding="utf-8")) if state.exists() else set()
        logged, _, bad, old = scan(read_lines(path), done)
        return logged, bad, old
    state.parent.mkdir(parents=True, exist_ok=True)
    with open(state, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # two runs at once take turns instead of both importing
        fh.seek(0)
        seen = fh.read()
        logged, handled, bad, old = scan(read_lines(path), _keys(seen))
        if logged:  # journal first: a crash between the two writes re-imports, never loses
            journal.append(config.journal(), logged, SOURCE)
        if handled:
            fh.write(("" if seen else STATE_HEADER) + "".join(k + "\n" for k in handled))
    return logged, bad, old


def _report_bad(bad: list[tuple[str, str]]) -> None:
    print(f"spend inbox: couldn't read {len(bad)} line(s), log them by hand "
          "(each inbox line is only tried once):", file=sys.stderr)
    for line, err in bad:
        print(f"  {line}\n    {err}", file=sys.stderr)


def run(dry_run: bool = False) -> int:
    """`spend inbox`: import new lines exactly once, tagged src:phone."""
    path = config.inbox()
    blocked = _blocked(path)
    if blocked:
        print(f"spend inbox: can't read {blocked} (permission denied). Run `spend inbox` in your own "
              "terminal; from Claude, type `! spend inbox`", file=sys.stderr)
        return 1
    if not _download(path):
        print(f"spend inbox: {path} is still downloading from iCloud, try again in a moment", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"spend inbox: no inbox at {path} yet (set up the iPhone Shortcut: docs/phone-shortcut.md)")
        return 0
    logged, bad, old = _import(path, dry_run)
    verb = "would log" if dry_run else "logged"
    for e in logged:
        print(f"{verb} {journal.fmt_amount(e.amount)} {e.currency} · {e.category} · {e.note} ({e.date}, phone)")
    if bad:
        _report_bad(bad)
    if not logged and not bad:
        print(f"spend inbox: nothing new ({old} line(s) already imported)")
    return 1 if bad else 0


def sync() -> str | None:
    """Pull new phone lines before `spend month` / `spend list`, so nobody has to run `spend inbox`.
    Prints only what it imported or what went wrong; a problem here never stops the report.
    Returns the problem, if any, so a report can mention it."""
    path = config.inbox()
    blocked = _blocked(path)
    problem = None
    if blocked:
        problem = f"phone entries not imported: no permission to read {blocked}"
        print(f"({problem}. Run this in your own terminal; from Claude, type `! spend inbox`)", file=sys.stderr)
        return problem
    if not _download(path):
        problem = "phone entries not imported: the inbox is still downloading from iCloud"
        print(f"({problem})", file=sys.stderr)
        return problem
    if not path.exists():
        return None
    logged, bad, _ = _import(path, dry_run=False)
    for e in logged:
        print(f"+ from phone: {journal.fmt_amount(e.amount)} {e.currency} · {e.category} · {e.note} ({e.date})")
    if bad:
        _report_bad(bad)
        problem = f"{len(bad)} phone line(s) couldn't be read; see `spend inbox`"
    if logged or bad:
        print()
    return problem
