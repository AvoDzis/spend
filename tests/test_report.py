import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from spend import cli, journal, report
from spend.parse import Expense


class Helpers(unittest.TestCase):
    def test_months(self):
        self.assertEqual(report.prev_month("2026-10"), "2026-09")
        self.assertEqual(report.prev_month("2026-01"), "2025-12")
        self.assertEqual(report.next_month("2026-12"), "2027-01")

    def test_fmt_money(self):
        self.assertEqual(report.fmt_money(D("250000"), "AMD"), "250,000")
        self.assertEqual(report.fmt_money(D("1500.0"), "AMD"), "1,500")
        self.assertEqual(report.fmt_money(D("229941.75"), "AMD"), "229,942")
        self.assertEqual(report.fmt_money(D("50"), "USD"), "50.00")


class RenderMonth(unittest.TestCase):
    def test_table(self):
        this = {"transport": {"AMD": D("4200")}, "groceries": {"AMD": D("12300")},
                "clothes": {"USD": D("50")}, "fun": {"EUR": D("20"), "AMD": D("1000")}}
        last = {"home": {"AMD": D("250000"), "USD": D("30")}}
        lines = report.render_month("2026-10", this, last).splitlines()
        self.assertEqual(lines[0], "October 2026 · spent per category")
        self.assertEqual(lines[1].split(), ["category", "AMD", "USD", "EUR"])
        # categories sorted by AMD, then USD, then EUR, biggest first
        self.assertEqual([ln.split()[0] for ln in lines[2:6]], ["groceries", "transport", "fun", "clothes"])
        self.assertEqual(lines[2].split(), ["groceries", "12,300", "-", "-"])
        self.assertEqual(lines[5].split(), ["clothes", "-", "50.00", "-"])
        self.assertTrue(lines[6].strip().startswith("─"))
        self.assertEqual(lines[7].split(), ["total", "17,500", "50.00", "20.00"])
        self.assertEqual(lines[8].split(), ["last", "month", "(Sep)", "250,000", "30.00", "-"])
        # columns line up
        self.assertEqual(len({len(ln) for ln in lines[1:6] + lines[7:]}), 1)

    def test_only_currencies_in_use(self):
        out = report.render_month("2026-10", {"groceries": {"AMD": D("800")}}, {})
        self.assertEqual(out.splitlines()[1].split(), ["category", "AMD"])
        self.assertIn("last month (Sep)", out)

    def test_empty_this_month(self):
        out = report.render_month("2026-11", {}, {"groceries": {"AMD": D("800")}})
        self.assertIn("nothing logged yet", out)
        self.assertEqual(out.splitlines()[-1].split(), ["last", "month", "(Oct)", "800"])

    def test_nothing_at_all(self):
        self.assertEqual(report.render_month("2026-01", {}, {}),
                         "January 2026: nothing logged (nothing in December 2025 either)\n")


class RenderRecent(unittest.TestCase):
    def test_numbered_from_the_end(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        path = self.dir / "t.journal"
        journal.append(path, [Expense(date(2026, 10, 3), D("3000"), "AMD", "taxi", "transport")])
        journal.append(path, [Expense(date(2026, 10, 4), D("50"), "USD", "jeans", "clothes")], "phone")
        lines = report.render_recent(journal.read_entries(path)).splitlines()
        self.assertEqual(lines[0].split(), ["2", "2026-10-03", "3,000", "AMD", "transport", "taxi"])
        self.assertEqual(lines[1].split(), ["1", "2026-10-04", "50.00", "USD", "clothes", "jeans", "(phone)"])


class Commands(unittest.TestCase):
    """`spend month` / `spend list` end to end through the CLI, on a temp journal."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()
        self.path = self.dir / "spend.journal"

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue() + err.getvalue()

    def log(self, when, amount, currency, note, category):
        journal.append(self.path, [Expense(when, D(amount), currency, note, category)])

    def test_no_journal_yet(self):
        self.assertEqual(self.run_cli("month")[0], 0)
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("no entries yet", out)

    def test_bad_month(self):
        code, out = self.run_cli("month", "October")
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM", out)

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_month(self):
        self.log(date(2026, 9, 1), "250000", "AMD", "rent", "home")
        self.log(date(2026, 9, 30), "30", "USD", "book", "fun")
        self.log(date(2026, 10, 1), "800", "AMD", "supermarket", "groceries")
        self.log(date(2026, 10, 2), "4500", "AMD", "supermarket", "groceries")
        self.log(date(2026, 10, 4), "50", "USD", "jeans", "clothes")
        self.log(date(2026, 11, 1), "999", "AMD", "next month", "groceries")
        with open(self.path, "a") as fh:  # hand-written entry in a sub-account rolls up to its category
            fh.write("2026-10-03 dinner\n    expenses:food:restaurants    7,000 AMD\n    assets:wallet\n")
        code, out = self.run_cli("month", "2026-10")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "October 2026 · spent per category")
        self.assertEqual(lines[1].split(), ["category", "AMD", "USD"])
        self.assertEqual(lines[2].split(), ["food", "7,000", "-"])
        self.assertEqual(lines[3].split(), ["groceries", "5,300", "-"])
        self.assertEqual(lines[4].split(), ["clothes", "-", "50.00"])
        self.assertEqual(lines[6].split(), ["total", "12,300", "50.00"])
        self.assertEqual(lines[7].split(), ["last", "month", "(Sep)", "250,000", "30.00"])

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_month_defaults_to_this_month(self):
        self.run_cli("1200", "taxi")
        code, out = self.run_cli("month")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.splitlines()[0].startswith(date.today().strftime("%B %Y")))
        self.assertIn("1,200", out)

    def test_list(self):
        for i in range(1, 13):
            self.log(date(2026, 10, 1), str(i * 100), "AMD", f"thing {i}", "other")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 10)  # default: last 10
        self.assertEqual(lines[0].split()[:3], ["10", "2026-10-01", "300"])
        self.assertEqual(lines[-1].split(), ["1", "2026-10-01", "1,200", "AMD", "other", "thing", "12"])
        self.assertEqual(len(self.run_cli("list", "3")[1].splitlines()), 3)
        self.assertEqual(len(self.run_cli("list", "50")[1].splitlines()), 12)


if __name__ == "__main__":
    unittest.main()
