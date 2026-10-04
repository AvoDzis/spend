"""Keyword rules that map a note to a category, and learn from fixes. Built in T-009.2."""


def categorize(note: str) -> str:
    """Category for a note like "supermarket" → "groceries". Unknown → "other"."""
    return "other"


def fix(target: str, category: str) -> int:
    """`spend fix last|N <category>`: re-tag an entry (N = Nth from the end) and save a rule."""
    print("spend fix: not built yet (T-009.2)")
    return 1


def show() -> int:
    """`spend cats`: list categories and their keywords."""
    print("spend cats: not built yet (T-009.2)")
    return 1
