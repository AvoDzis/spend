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

from spend import cli, digest, journal, monthly
from spend.parse import Expense


class Report(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()
        os.environ.pop("SPEND_EMAIL", None)
        journal.append(self.dir / "spend.journal", [
            Expense(date(2026, 9, 2), D("250000"), "AMD", "rent", "home"),
            Expense(date(2026, 9, 21), D("40"), "USD", "jeans", "clothes")])
        journal.append(self.dir / "spend.journal", [Expense(date(2026, 9, 5), D("4500"), "AMD", "sas", "groceries")],
                       source="phone")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_last_month(self):
        self.assertEqual(monthly.last_month(date(2026, 1, 1)), "2025-12")

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_build(self):
        d = monthly.build("2026-09", problem="phone entries not imported: test")
        self.assertEqual(d.subject, "Spending · September 2026: 254,500 AMD + 40.00 USD")
        text = digest.render_text(d)
        self.assertIn("⚠ phone entries not imported: test", text)
        for part in ("• Most went to home: 250,000 AMD, 98% of everything in AMD.", "AMD per category",
                     "USD per category", "biggest payments", "AMD per day",
                     "3 payments (2 from terminal, 1 from phone)"):
            self.assertIn(part, text)
        self.assertNotIn("Last 6 months", text)  # only one month of data

    def test_empty_month(self):
        d = monthly.build("2026-03")
        self.assertEqual(d.subject, "Spending · March 2026: nothing logged")
        self.assertIn("Nothing was logged in March.", digest.render_text(d))
        self.assertIn("<html>", digest.render_html(d))

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_print_and_dry_run(self):
        code, out, _ = self.run_cli("report", "2026-09")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Spending · September 2026"))
        code, out, _ = self.run_cli("-n", "report", "2026-09", "--email")
        self.assertTrue(out.startswith("(would email) Spending"))

    @unittest.skipUnless(shutil.which("hledger"), "hledger not installed")
    def test_email(self):
        self.assertEqual(self.run_cli("report", "2026-09", "--email")[0], 2)  # no address
        with mock.patch.object(monthly, "password", return_value=None):
            code, _, err = self.run_cli("report", "2026-09", "--email", "--to", "me@example.com")
        self.assertEqual(code, 1)
        self.assertIn("security add-generic-password -s spend-gmail -a me@example.com -w", err)
        with mock.patch.object(monthly, "password", return_value="app-pass"), \
                mock.patch("smtplib.SMTP_SSL") as smtp, mock.patch.dict(os.environ, {"SPEND_EMAIL": "me@example.com"}):
            code, out, _ = self.run_cli("report", "2026-09", "--email")
        self.assertEqual(code, 0)
        server = smtp.return_value.__enter__.return_value
        server.login.assert_called_once_with("me@example.com", "app-pass")
        msg = server.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "me@example.com")
        self.assertEqual([p.get_content_type() for p in msg.iter_parts()], ["text/plain", "text/html"])
        self.assertIn("Where it went", msg.get_body(("html",)).get_content())
        self.assertIn("September 2026", msg["Subject"])
        self.assertIn('sent "Spending', out)

    def test_bad_month(self):
        self.assertEqual(self.run_cli("report", "Sept")[0], 2)


if __name__ == "__main__":
    unittest.main()
