import io
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from spend import cli, export, journal
from spend.parse import Expense


class Export(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.phone = self.dir / "Scriptable"
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir), "SPEND_PHONE_DIR": str(self.phone)})
        self.env.start()
        journal.append(self.dir / "spend.journal", [
            Expense(date(2026, 10, 1), D("1200"), "AMD", "yandex. go", "transport:taxi"),
            Expense(date(2025, 1, 1), D("5"), "AMD", "too old", "other")])

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_payload(self):
        p = export.payload(journal.read_entries(self.dir / "spend.journal"), today=date(2026, 10, 5))
        self.assertEqual(p["today"], "2026-10-05")
        self.assertEqual(p["entries"], [["2026-10-01", 1200.0, "AMD", "transport/taxi", "Yandex. Go", "cli"]])

    def test_waits_for_scriptable(self):
        code, out = self.run_cli("export")
        self.assertIn("install Scriptable", out)
        self.assertFalse(self.phone.exists())

    def test_writes_code_and_data_once(self):
        self.phone.mkdir()
        code, out = self.run_cli("export")
        self.assertIn("updated Spend.js, spend-app.html, spend-data.json", out)
        data = json.loads((self.phone / "spend-data.json").read_text())
        self.assertEqual(data["entries"][0][3], "transport/taxi")
        self.assertEqual((self.phone / "Spend.js").read_bytes(), (export.PHONE / "Spend.js").read_bytes())
        self.assertIn("phone view already up to date", self.run_cli("export")[1])

    def test_other_commands_refresh_it(self):
        self.phone.mkdir()
        self.run_cli("export")
        time.sleep(0.01)
        self.run_cli("300 coffee")
        notes = [r[4] for r in json.loads((self.phone / "spend-data.json").read_text())["entries"]]
        self.assertIn("Coffee", notes)
        self.run_cli("-n", "500 tea")  # dry runs change nothing
        notes = [r[4] for r in json.loads((self.phone / "spend-data.json").read_text())["entries"]]
        self.assertNotIn("Tea", notes)

    def test_page_has_the_data_placeholder(self):
        self.assertEqual((export.PHONE / "spend-app.html").read_text().count("__SPEND_DATA__"), 1)
        self.assertIn('"__SPEND_DATA__"', (export.PHONE / "Spend.js").read_text())


if __name__ == "__main__":
    unittest.main()
