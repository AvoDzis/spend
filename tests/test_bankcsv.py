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

from spend import bankcsv, cli, journal

HEADER = ('"Transaction date","Settlement date","Transaction type","Transaction details",'
          '"Transaction amount","Transaction amount in account currency"\n')
CARD, TRANSFER = "Քարտային գործարք", "Փոխանցում հաշվին"
ROWS = [  # made-up rows in the bank's format
    ("12/09/26, 18:40", CARD, "POS: SAS SUPERMARKET\\YEREVAN AM 123456", "-4,500.00 AMD"),
    ("13/09/26, 09:15", CARD, "Purchase: YANDEX. GO YEREVAN AM 654321", "-1,200.00 AMD"),
    ("14/09/26, 20:00", CARD, "MCDONALDS\\VISA SALES WIEN 0", "-9.80 EUR"),
    ("15/09/26, 10:00", CARD, "SAS SUPERMARKET\\YEREVAN AM 123456", "+4,500.00 AMD"),
    ("16/09/26, 11:00", TRANSFER, "Personal transfer", "-50,000.00 AMD"),
    ("02/10/26, 12:00", CARD, "ZORIK LLC PURCHASE POS YEREVAN AM 1", "-2,000.00 AMD"),
]


def csv_text(rows):
    return HEADER + "".join(f'"{d}","{d}","{t}","{det}","{amt}","{amt}"\n' for d, t, det, amt in rows)


class Pieces(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(bankcsv.clean("POS: SAS SUPERMARKET\\YEREVAN AM 123456"), "sas supermarket")
        self.assertEqual(bankcsv.clean("MCDONALDS\\VISA SALES WIEN 0"), "mcdonalds")
        self.assertEqual(bankcsv.clean("TINY CAFE PURCHASE POS YEREVAN AM 1"), "tiny cafe")
        self.assertEqual(bankcsv.clean("BUY .AM EPOS PURCHASE YEREVAN A"), "buy .am")
        self.assertEqual(bankcsv.clean("YERITSYAN SUPERMARKET YEREVAN A"), "yeritsyan supermarket")

    def test_date_and_amount(self):
        self.assertEqual(bankcsv.parse_date("12/09/26, 18:40"), date(2026, 9, 12))
        self.assertEqual(bankcsv.parse_amount("-4,500.00 AMD"), (D("-4500.00"), "AMD"))
        self.assertEqual(bankcsv.parse_amount("+9.80 EUR"), (D("9.80"), "EUR"))
        with self.assertRaises(ValueError):
            bankcsv.parse_amount("abc")


class Import(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()
        self.csv = self.dir / "export.csv"
        self.csv.write_text(csv_text(ROWS), encoding="utf-8-sig")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def entries(self):
        return journal.read_entries(self.dir / "spend.journal")

    def test_card_payments_only_once(self):
        code, out, _ = self.run_cli("import", str(self.csv))
        self.assertEqual(code, 0)
        self.assertEqual([(e.date, e.amount, e.currency, e.category, e.note, e.tags) for e in self.entries()], [
            ("2026-09-12", D("4500"), "AMD", "groceries", "sas supermarket", "src:bank"),
            ("2026-09-13", D("1200"), "AMD", "transport", "yandex. go", "src:bank"),
            ("2026-09-14", D("9.8"), "EUR", "eating-out", "mcdonalds", "src:bank"),
            ("2026-10-02", D("2000"), "AMD", "other", "zorik llc", "src:bank")])
        self.assertIn("refund or incoming", out)
        self.assertIn("transfer: 16/09/26", out)
        self.assertIn("imported 4, already there 0, skipped 2; 1 in 'other'", out)
        code, out, _ = self.run_cli("import", str(self.csv))  # again: nothing new
        self.assertIn("imported 0, already there 4", out)
        self.assertEqual(len(self.entries()), 4)

    def test_month_filter_and_overlapping_export(self):
        self.run_cli("import", str(self.csv), "--month", "2026-09")
        self.assertEqual({e.date[:7] for e in self.entries()}, {"2026-09"})
        self.csv.write_text(csv_text(ROWS + [("03/10/26, 08:00", CARD, "TAXI\\YEREVAN AM 2", "-800.00 AMD")]),
                            encoding="utf-8-sig")
        self.run_cli("import", str(self.csv))
        self.assertEqual(len(self.entries()), 5)  # 3 September + 2 new October rows

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.run_cli("-n", "import", str(self.csv))
        self.assertIn("would import 4", out)
        self.assertEqual(self.entries(), [])
        self.assertFalse((self.dir / ".spend-import-state").exists() and
                         (self.dir / ".spend-import-state").read_text().strip())

    def test_bad_input(self):
        (self.dir / "other.csv").write_text("a,b\n1,2\n")
        self.assertEqual(self.run_cli("import", str(self.dir / "other.csv"))[0], 1)
        self.assertEqual(self.run_cli("import", str(self.dir / "missing.csv"))[0], 1)
        self.assertEqual(self.run_cli("import")[0], 2)
        self.assertEqual(self.run_cli("import", str(self.csv), "--month", "Sept")[0], 2)


if __name__ == "__main__":
    unittest.main()
