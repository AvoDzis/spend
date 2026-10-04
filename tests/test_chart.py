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

from spend import chart, cli, journal
from spend.parse import Expense


def entry(day, amount, category, note="x", currency="AMD"):
    return journal.Entry(day, note, category, D(amount), currency, "src:cli", 0, 0)


OCT = [entry("2026-10-01", "4500", "groceries"), entry("2026-10-03", "45000", "groceries"),
       entry("2026-10-02", "3000", "eating-out"), entry("2026-10-02", "1200", "transport")]


class Pieces(unittest.TestCase):
    def test_bar(self):
        self.assertEqual(chart.bar(D(100), D(100), 4), "████")
        self.assertEqual(chart.bar(D(50), D(100), 4), "██")
        self.assertEqual(chart.bar(D(1), D(100), 4), "▏")  # tiny but visible
        self.assertEqual(chart.bar(D(0), D(100), 4), "")

    def test_spark_and_shade(self):
        self.assertEqual(chart.spark([D(0), D(50), D(100)]), " ▄█")
        self.assertEqual([chart.shade(D(v), D(100)) for v in (0, 10, 30, 60, 100)], ["·", "░", "▒", "▓", "█"])

    def test_months_back(self):
        self.assertEqual(chart.months_back("2026-02", 3), ["2025-12", "2026-01", "2026-02"])


class Views(unittest.TestCase):
    def test_bars(self):
        lines = chart.render_bars("2026-10", "AMD", OCT).splitlines()
        self.assertEqual(lines[0], "October 2026 · AMD per category")
        self.assertEqual(lines[1].split()[0], "groceries")
        self.assertTrue(lines[1].split()[-2:] == ["49,500", "92%"])
        self.assertEqual(lines[-1].split(), ["total", "53,700"])
        self.assertEqual(chart.render_bars("2026-09", "AMD", OCT), "September 2026: nothing in AMD\n")

    def test_trend(self):
        out = chart.render_trend("2026-10", 2, "AMD", OCT + [entry("2026-09-10", "8000", "transport")])
        self.assertIn("Sep 2026", out)
        self.assertIn("53,700", out)
        self.assertIn("transport   █▂  1,200 in Oct", out)

    def test_days(self):
        lines = chart.render_days("2026-10", "AMD", OCT).splitlines()
        self.assertEqual(lines[1].split(), ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"])
        self.assertEqual(lines[2].split(), ["1░", "2░", "3█", "4·"])  # Oct 1 2026 is a Thursday
        self.assertIn("biggest day: Oct 3 (45,000)", lines[-1])
        self.assertIn("over 3 days", lines[-1])

    def test_top(self):
        lines = chart.render_top("2026-10", 2, "AMD", OCT).splitlines()
        self.assertEqual([ln.split()[1] for ln in lines[1:]], ["45,000", "4,500"])


class Command(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()
        journal.append(self.dir / "spend.journal", [
            Expense(date(2026, 10, 3), D("45000"), "AMD", "supermarket", "groceries"),
            Expense(date(2026, 10, 4), D("50"), "USD", "jeans", "clothes"),
            Expense(date(2026, 9, 2), D("250000"), "AMD", "rent", "home")])

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_default_is_bars_with_other_currency_hint(self):
        code, out, _ = self.run_cli("chart", "--month", "2026-10")
        self.assertEqual(code, 0)
        self.assertIn("October 2026 · AMD per category", out)
        self.assertIn("also spent in USD: add --currency USD", out)

    def test_options_combine(self):
        code, out, _ = self.run_cli("chart", "--month", "2026-10", "--trend", "2", "--days", "--top", "1")
        self.assertEqual(code, 0)
        self.assertIn("Last 2 months · AMD", out)
        self.assertIn("per day", out)
        self.assertIn("biggest 1 in AMD", out)

    def test_currency_alias_and_cat(self):
        code, out, _ = self.run_cli("chart", "--month", "2026-10", "--currency", "dollars", "--top")
        self.assertIn("biggest 1 in USD", out)
        code, out, _ = self.run_cli("chart", "--month", "2026-10", "--cat", "Groceries")
        self.assertIn("groceries · last 6 months · AMD", out)

    def test_bad_input(self):
        self.assertEqual(self.run_cli("chart", "--month", "13")[0], 2)
        self.assertEqual(self.run_cli("chart", "--trend", "x")[0], 2)


if __name__ == "__main__":
    unittest.main()
