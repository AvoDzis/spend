"""The phone view: a copy of the data plus the widget's code in Scriptable's iCloud folder.

`spend export` writes them; every other spend command refreshes them when the journal changed,
and `spend sync` (run every 30 min by `make schedule`) imports phone lines first. Nothing happens
until the Scriptable app is installed and its iCloud folder exists.
"""
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from . import config, inbox, journal
from .digest import pretty
from .report import prev_month

DATA = "spend-data.json"
PHONE = Path(__file__).resolve().parent.parent / "phone"
CODE = ["Spend.js", "spend-app.html"]  # copied as they are; the script loads the page and the data
MONTHS = 13


def payload(entries: list[journal.Entry], today: date | None = None) -> dict:
    today = today or date.today()
    oldest = today.strftime("%Y-%m")
    for _ in range(MONTHS - 1):
        oldest = prev_month(oldest)
    rows = [[e.date, float(e.amount), e.currency, journal.display(e.category), pretty(e.note, 40),
             (e.tags.partition("src:")[2].split(",")[0].strip() or "cli")]
            for e in entries if e.date[:7] >= oldest]
    return {"generated": datetime.now().isoformat(timespec="minutes"), "today": today.isoformat(),
            "entries": sorted(rows, key=lambda r: r[0])}


def _write(path: Path, data: bytes) -> bool:
    """Write only when the content changed (iCloud re-syncs every write); atomically."""
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def write() -> str:
    """Refresh the phone copy. Returns what happened, for `spend export` to print."""
    target = config.phone_dir()
    try:
        if not target.is_dir():
            return f"no Scriptable folder yet ({target}): install Scriptable on the iPhone and open it once"
        changed = [name for name in CODE if _write(target / name, (PHONE / name).read_bytes())]
        data = json.dumps(payload(journal.read_entries(config.journal())), ensure_ascii=False, separators=(",", ":"))
        if _write(target / DATA, data.encode("utf-8")):
            changed.append(DATA)
    except PermissionError:
        return f"can't write to {target} (permission denied): run spend from your own terminal"
    return f"updated {', '.join(changed)} in {target}" if changed else "phone view already up to date"


def refresh() -> None:
    """After a command: refresh quietly when the journal is newer than the phone copy."""
    target, journal_path = config.phone_dir(), config.journal()
    try:
        data = target / DATA
        if target.is_dir() and journal_path.exists() and (
                not data.exists() or journal_path.stat().st_mtime > data.stat().st_mtime):
            write()
    except OSError:
        pass  # the phone view is a convenience; never let it break a command


def run(args: list[str]) -> int:
    """`spend export`: refresh the phone view now."""
    print(write())
    return 0


def sync(args: list[str]) -> int:
    """`spend sync`: import new phone lines, then refresh the phone view (the 30-minute job)."""
    problem = inbox.sync()
    print(f"{datetime.now():%Y-%m-%d %H:%M} {write()}" + (f" ({problem})" if problem else ""))
    return 0
