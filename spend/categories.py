"""Keyword rules that map a note to a category, and learn from fixes.

Rules files have one category per line:  `groceries: supermarket, sas, yerevan city`
Defaults ship in default_rules.txt; `spend fix` / `spend learn` append to config.rules().
A rule matches whole words of the note in order (plurals too; `pharm*` matches any word
starting with "pharm"). The longest phrase wins, then learned over default, then the
earliest in the note. No match → "other".
"""
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

from . import config, journal

DEFAULT_RULES = Path(__file__).with_name("default_rules.txt")
OTHER = "other"
# dropped from notes and rules before matching, so "lunch with team" matches "lunch team"
STOPWORDS = {"a", "an", "the", "and", "or", "for", "with", "at", "to", "from", "of", "in", "on",
             "my", "our", "some"}
WORD_RE = re.compile(r"\w+\*?")
LEARNED_HEADER = ("# Rules learned by `spend fix` / `spend learn` (category: keyword, keyword).\n"
                  "# Later lines win; edit freely.\n")


@dataclass
class Rule:
    category: str
    words: tuple[str, ...]
    learned: bool


def words(text: str, keep_star: bool = False) -> list[str]:
    """Lowercase words of a note or keyword, without filler words and bare numbers."""
    out = []
    for w in WORD_RE.findall(re.sub(r"['’]", "", text.lower())):
        if not keep_star:
            w = w.rstrip("*")
        if w and w not in STOPWORDS and not w.isdigit():
            out.append(w)
    return out


def _load(path: Path, learned: bool) -> dict[tuple[str, ...], Rule]:
    rules: dict[tuple[str, ...], Rule] = {}
    if not path.exists():
        return rules
    for line in path.read_text(encoding="utf-8").splitlines():
        cat, sep, keywords = line.split("#", 1)[0].partition(":")
        if not sep or not cat.strip():
            continue
        cat = journal.account_name(cat)
        for kw in keywords.split(","):
            ws = tuple(words(kw, keep_star=True))
            if ws:
                rules.pop(ws, None)  # re-insert so a later line wins and lists last
                rules[ws] = Rule(cat, ws, learned)
    return rules


def load_rules() -> list[Rule]:
    """Default rules, then learned ones (which replace a default with the same keyword)."""
    merged = _load(DEFAULT_RULES, learned=False)
    for ws, rule in _load(config.rules(), learned=True).items():
        merged.pop(ws, None)
        merged[ws] = rule
    return list(merged.values())


def _word_matches(kw: str, w: str) -> bool:
    if kw.endswith("*"):
        return w.startswith(kw[:-1])
    return w in (kw, kw + "s", kw + "es") or (kw.endswith("y") and w == kw[:-1] + "ies")


def _position(rule: Rule, ws: list[str]) -> int | None:
    n = len(rule.words)
    for i in range(len(ws) - n + 1):
        if all(_word_matches(k, w) for k, w in zip(rule.words, ws[i:i + n])):
            return i
    return None


def match(note: str, rules: list[Rule] | None = None) -> Rule | None:
    """The rule that decides a note's category, or None."""
    ws = words(note)
    best, best_key = None, None
    for rule in load_rules() if rules is None else rules:
        pos = _position(rule, ws)
        if pos is None:
            continue
        key = (len(rule.words), rule.learned, -pos)
        if best_key is None or key > best_key:
            best, best_key = rule, key
    return best


def categorize(note: str, rules: list[Rule] | None = None) -> str:
    """Category for a note like "supermarket" → "groceries". Unknown → "other"."""
    rule = match(note, rules)
    return rule.category if rule else OTHER


def _save(keyword: list[str], category: str) -> None:
    path = config.rules()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    with open(path, "a", encoding="utf-8") as fh:
        if not text.strip():
            fh.write(LEARNED_HEADER)
        elif not text.endswith("\n"):
            fh.write("\n")
        fh.write(f"{category}: {' '.join(keyword)}\n")


def _known(rules: list[Rule]) -> set[str]:
    return {r.category for r in rules} | {e.category for e in journal.read_entries(config.journal())} | {OTHER}


def _learn(keyword: list[str], category: str, rules: list[Rule], known: set[str]) -> None:
    """Save keyword → category unless the rules already give that category for it."""
    phrase = " ".join(keyword)
    if categorize(phrase, rules) == category:
        print(f'rules already file "{phrase}" under {category}')
        return
    _save(keyword, category)
    new = "" if category in known else " (new category)"
    print(f'learned "{phrase}" → {category}{new}')


def fix(target: str, category: str, word: str | None = None) -> int:
    """`spend fix last|N <category> [--word <keyword>]`: re-tag an entry (N = Nth from the end)
    and save a rule: the whole note, or just <keyword> when given."""
    path = config.journal()
    n = 1 if target == "last" else int(target) if target.isdigit() else 0
    if n < 1:
        print(f"spend fix: which entry? 'last' or a number (1 = newest), not {target!r}", file=sys.stderr)
        return 2
    entries = journal.read_entries(path)
    if n > len(entries):
        print(f"spend fix: there are only {len(entries)} entries in {path}", file=sys.stderr)
        return 1
    keyword = words(word if word is not None else entries[-n].note)
    if word is not None and not keyword:
        print(f"spend fix: {word!r} has no keyword to learn", file=sys.stderr)
        return 2
    e, cat, rules = entries[-n], journal.account_name(category), load_rules()
    known = _known(rules)  # before re-tagging, so a brand-new category is flagged
    change = f"already {cat}" if cat == e.category else f"{e.category} → {cat}"
    if cat != e.category:
        journal.set_category(path, e, cat)
    print(f"fixed {journal.fmt_amount(e.amount)} {e.currency} · {change} · {e.note} ({e.date})")
    if keyword:
        _learn(keyword, cat, rules, known)
    else:
        print(f"nothing to learn from {e.note!r}")
    return 0


def learn(keyword: str, category: str) -> int:
    """`spend learn <keyword> <category>`: add a rule without touching any entry."""
    ws = words(keyword, keep_star=True)
    if not ws:
        print(f"spend learn: {keyword!r} has no keyword to learn", file=sys.stderr)
        return 2
    rules = load_rules()
    _learn(ws, journal.account_name(category), rules, _known(rules))
    return 0


def show() -> int:
    """`spend cats`: list categories and their keywords."""
    by_cat: dict[str, dict[bool, list[str]]] = {}
    for r in load_rules():
        by_cat.setdefault(r.category, {False: [], True: []})[r.learned].append(" ".join(r.words))
    width = max(60, min(shutil.get_terminal_size((100, 20)).columns, 120))
    pad = max(len(c) for c in [*by_cat, OTHER]) + 2
    for cat in sorted(by_cat):
        for learned, kws in ((False, by_cat[cat][False]), (True, by_cat[cat][True])):
            if not kws:
                continue
            head = cat if learned is False or not by_cat[cat][False] else ""
            text = ("learned: " if learned else "") + ", ".join(kws)
            print(textwrap.fill(text, width, initial_indent=head.ljust(pad), subsequent_indent=" " * pad))
    print(f"{OTHER.ljust(pad)}anything no rule matches")
    print(f"\nrules: {DEFAULT_RULES} + learned {config.rules()}")
    return 0
