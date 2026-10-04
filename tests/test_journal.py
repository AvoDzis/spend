import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from spend import journal
from spend.parse import Expense


class Journal(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "t.journal"

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_append_read_and_set_category(self):
        journal.append(self.path, [
            Expense(date(2026, 10, 4), Decimal("800"), "AMD", "supermarket", "groceries"),
            Expense(date(2026, 10, 4), Decimal("12.50"), "USD", "lunch; with team"),
        ])
        es = journal.read_entries(self.path)
        self.assertEqual([(e.note, e.category, e.amount, e.currency) for e in es],
                         [("supermarket", "groceries", Decimal("800"), "AMD"),
                          ("lunch, with team", "other", Decimal("12.5"), "USD")])
        journal.set_category(self.path, es[1], "Eating Out")
        self.assertEqual(journal.read_entries(self.path)[1].category, "eating-out")
        self.assertEqual(journal.read_entries(self.path)[1].tags, "src:cli")

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_hledger_reads_it(self):
        journal.append(self.path, [Expense(date(2026, 10, 4), Decimal("250000"), "AMD", "rent", "home")])
        journal.append(self.path, [Expense(date(2026, 10, 4), Decimal("50"), "USD", "jeans", "clothes")])
        out = journal.hledger(self.path, "bal", "expenses")
        self.assertIn("250,000 AMD  expenses:home", out)
        self.assertIn("50.00 USD  expenses:clothes", out)


if __name__ == "__main__":
    unittest.main()
