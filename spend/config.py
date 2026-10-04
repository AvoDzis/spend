"""Where the data lives. Everything can be overridden with env vars (tests use a temp dir)."""
import os
from pathlib import Path

ICLOUD = Path("~/Library/Mobile Documents/com~apple~CloudDocs").expanduser()


def _env(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser() if v else default


def data_dir() -> Path:
    return _env("SPEND_DIR", Path("~/Desktop/personal/budgeting").expanduser())


def journal() -> Path:
    return _env("SPEND_JOURNAL", data_dir() / "spend.journal")


def rules() -> Path:
    """Learned keyword → category rules (T-009.2)."""
    return _env("SPEND_RULES", data_dir() / "spend-rules.txt")


def inbox() -> Path:
    """Text file the iPhone Shortcut appends to (T-009.3)."""
    return _env("SPEND_INBOX", ICLOUD / "Spend" / "inbox.txt")


def inbox_state() -> Path:
    """What `spend inbox` already imported (T-009.3)."""
    return _env("SPEND_INBOX_STATE", data_dir() / ".spend-inbox-state")


def import_state() -> Path:
    """Which bank-CSV rows `spend import` already imported."""
    return _env("SPEND_IMPORT_STATE", data_dir() / ".spend-import-state")
