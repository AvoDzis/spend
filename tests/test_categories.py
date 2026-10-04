import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from spend import categories, cli, journal
from spend.categories import categorize
from spend.parse import parse_one


class Isolated(unittest.TestCase):
    """Temp data dir, so learned rules and the journal never touch real data."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()
        self.journal = self.dir / "spend.journal"
        self.rules = self.dir / "spend-rules.txt"

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue() + err.getvalue()

    def cats(self):
        return [e.category for e in journal.read_entries(self.journal)]


class Defaults(Isolated):
    def test_common_notes(self):
        for note, cat in [("supermarket", "groceries"), ("taxi", "transport"), ("jeans", "clothes"),
                          ("coffee", "eating-out"), ("rent", "home"), ("gym", "sport"),
                          ("netflix", "subscriptions"), ("dentist", "health"), ("gas", "utilities")]:
            self.assertEqual(categorize(note), cat, note)

    def test_unknown_is_other(self):
        self.assertEqual(categorize("test"), "other")
        self.assertEqual(categorize("zzz qqq"), "other")
        self.assertEqual(categorize(""), "other")

    def test_case_plurals_and_punctuation(self):
        self.assertEqual(categorize("Taxis"), "transport")
        self.assertEqual(categorize("SAS, milk"), "groceries")
        self.assertEqual(categorize("buses"), "transport")
        self.assertEqual(categorize("2 t-shirts"), "clothes")
        self.assertEqual(categorize("menu.am order"), "eating-out")
        self.assertEqual(categorize("McDonald's"), "eating-out")

    def test_prefix_keyword(self):
        self.assertEqual(categorize("pharmacy"), "health")

    def test_whole_words_only(self):
        self.assertEqual(categorize("barbecue sauce"), "other")  # not "bar"

    def test_longest_phrase_then_earliest_word(self):
        self.assertEqual(categorize("yandex eats"), "eating-out")
        self.assertEqual(categorize("yandex go"), "transport")
        self.assertEqual(categorize("taxi to supermarket"), "transport")
        self.assertEqual(categorize("supermarket by taxi"), "groceries")
        self.assertEqual(categorize("cat food"), "pets")

    def test_default_rules_are_clean(self):
        seen = {}
        for line in categories.DEFAULT_RULES.read_text(encoding="utf-8").splitlines():
            cat, sep, kws = line.split("#", 1)[0].partition(":")
            if not sep:
                continue
            self.assertEqual(journal.account_name(cat), cat.strip(), "category must be an account name")
            for kw in kws.split(","):
                ws = tuple(categories.words(kw, keep_star=True))
                self.assertTrue(ws, f"empty keyword in {cat}")
                self.assertNotIn(ws, seen, f"{kw.strip()!r} in both {seen.get(ws)} and {cat}")
                seen[ws] = cat


class Learned(Isolated):
    def test_learned_rule_beats_default_of_same_length(self):
        self.rules.write_text("groceries: coffee\n")
        self.assertEqual(categorize("coffee"), "groceries")
        self.assertEqual(categorize("coffee shop"), "eating-out")  # longer default still wins

    def test_later_line_wins_and_bad_lines_ignored(self):
        self.rules.write_text("# comment\nnonsense line\nshopping: aragil\ntransport: aragil\n: orphan\n")
        self.assertEqual(categorize("aragil airport"), "transport")

    def test_stopwords_dropped(self):
        self.rules.write_text("eating-out: lunch team\n")
        self.assertEqual(categorize("lunch with the team"), "eating-out")


class Fix(Isolated):
    def test_fix_last_retags_and_learns_the_note(self):
        self.run_cli("1200", "aragil")
        self.assertEqual(self.cats(), ["other"])
        code, out = self.run_cli("fix", "last", "transport")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cats(), ["transport"])
        self.assertIn("other → transport", out)
        self.assertIn('learned "aragil" → transport', out)
        self.assertIn("transport: aragil", self.rules.read_text())
        self.run_cli("900", "aragil", "airport")
        self.assertEqual(self.cats(), ["transport", "transport"])

    def test_fix_n_counts_from_the_end(self):
        self.run_cli("100 aaa, 200 bbb, 300 ccc")
        self.assertEqual(self.run_cli("fix", "3", "gifts")[0], 0)
        self.assertEqual(self.run_cli("fix", "1", "home")[0], 0)
        self.assertEqual(self.cats(), ["gifts", "other", "home"])
        self.assertEqual(categorize("aaa"), "gifts")
        self.assertEqual(categorize("ccc"), "home")

    def test_fixing_a_wrong_default_learns_the_phrase_not_the_word(self):
        self.run_cli("5000", "coffee", "beans")
        self.assertEqual(self.cats(), ["eating-out"])
        self.run_cli("fix", "last", "groceries")
        self.assertEqual(self.cats(), ["groceries"])
        self.assertEqual(categorize("coffee beans 1kg"), "groceries")
        self.assertEqual(categorize("coffee"), "eating-out")

    def test_fix_with_word_learns_just_that_word(self):
        self.run_cli("3000", "zov", "milk", "and", "bread")
        code, out = self.run_cli("fix", "last", "groceries", "--word", "zov")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cats(), ["groceries"])
        self.assertIn('learned "zov" → groceries', out)
        self.assertEqual(categorize("zov eggs"), "groceries")

    def test_fix_with_multi_word_keyword(self):
        self.run_cli("3000", "dalma", "mall", "socks")
        self.run_cli("fix", "last", "shopping", "--word", "dalma", "mall")
        self.assertEqual(self.cats(), ["shopping"])
        self.assertEqual(categorize("dalma mall"), "shopping")
        self.assertEqual(categorize("dalma"), "other")

    def test_no_rule_saved_when_rules_already_agree(self):
        journal.append(self.journal, [parse_one("1200 aragil")])  # logged before the rule existed
        self.rules.write_text("transport: aragil\n")
        self.assertEqual(self.cats(), ["other"])
        code, out = self.run_cli("fix", "last", "transport")
        self.assertEqual((code, self.cats()), (0, ["transport"]))
        self.assertIn("already", out)
        self.assertEqual(self.rules.read_text(), "transport: aragil\n")

    def test_new_category_is_flagged(self):
        self.run_cli("2000", "zzz")
        code, out = self.run_cli("fix", "last", "Car Stuff")
        self.assertEqual(code, 0)
        self.assertEqual(self.cats(), ["car-stuff"])
        self.assertIn("(new category)", out)

    def test_hledger_still_reads_fixed_journal(self):
        if not shutil.which("hledger"):
            self.skipTest("hledger not installed")
        self.run_cli("1200", "aragil")
        self.run_cli("fix", "last", "transport")
        self.assertIn("expenses:transport", journal.hledger(self.journal, "bal", "expenses"))

    def test_errors(self):
        self.assertEqual(self.run_cli("fix", "last", "transport")[0], 1)  # empty journal
        self.run_cli("1200", "aragil")
        self.assertEqual(self.run_cli("fix", "5", "transport")[0], 1)
        self.assertEqual(self.run_cli("fix", "first", "transport")[0], 2)
        self.assertEqual(self.run_cli("fix", "0", "transport")[0], 2)
        self.assertEqual(self.run_cli("fix", "last")[0], 2)
        self.assertEqual(self.run_cli("fix", "last", "transport", "--word")[0], 2)
        self.assertEqual(self.cats(), ["other"])
        self.assertFalse(self.rules.exists())


class Learn(Isolated):
    def test_learn_adds_a_rule_without_entries(self):
        code, out = self.run_cli("learn", "sas", "shopping")
        self.assertEqual(code, 0, out)
        self.assertEqual(categorize("sas"), "shopping")
        self.assertFalse(self.journal.exists())

    def test_learn_multi_word_and_prefix(self):
        self.run_cli("learn", "dalma", "mall", "shopping")
        self.run_cli("learn", "zoo*", "pets")
        self.assertEqual(categorize("dalma mall"), "shopping")
        self.assertEqual(categorize("zoomarket"), "pets")

    def test_learn_keeps_a_hand_edited_file_intact(self):
        self.rules.write_text("# mine\ntransport: aragil")  # no trailing newline
        self.run_cli("learn", "bolt", "transport")  # default already says transport
        self.run_cli("learn", "lavash", "groceries")
        self.assertEqual(self.rules.read_text(), "# mine\ntransport: aragil\ngroceries: lavash\n")

    def test_learn_usage(self):
        self.assertEqual(self.run_cli("learn", "sas")[0], 2)
        self.assertEqual(self.run_cli("learn", "!!", "groceries")[0], 2)


class Cats(Isolated):
    def test_lists_defaults_and_learned(self):
        self.run_cli("learn", "aragil", "transport")
        self.run_cli("learn", "dalma", "mall", "mall-stuff")
        code, out = self.run_cli("cats")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"groceries\s+supermarket")
        self.assertIn("learned: aragil", out)
        self.assertRegex(out, r"mall-stuff\s+learned: dalma mall")
        self.assertIn("other", out)


if __name__ == "__main__":
    unittest.main()
