import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from spend import categories, cli, inbox, journal


class Inbox(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.inbox = self.dir / "icloud" / "inbox.txt"
        self.inbox.parent.mkdir()
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir), "SPEND_INBOX": str(self.inbox)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def phone(self, *lines):
        """Append lines the way the Shortcut does ("Make New Line" on: newline before, none after)."""
        with open(self.inbox, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(("\n" if fh.tell() else "") + line)

    def run_inbox(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([*flags, "inbox"])
        return code, out.getvalue(), err.getvalue()

    def entries(self):
        return journal.read_entries(self.dir / "spend.journal")

    def test_imports_with_timestamp_date_and_phone_tag(self):
        self.phone("2026-10-03 21:05:44 800dram supermarket", "2026-10-04 09:12:01 50usd jeans")
        code, out, _ = self.run_inbox()
        self.assertEqual(code, 0)
        self.assertIn("logged 800 AMD", out)
        es = self.entries()
        self.assertEqual([(e.date, e.note, e.amount, e.currency, e.tags) for e in es],
                         [("2026-10-03", "supermarket", Decimal("800"), "AMD", "src:phone"),
                          ("2026-10-04", "jeans", Decimal("50"), "USD", "src:phone")])
        self.assertEqual(es[0].category, journal.account_name(categories.categorize("supermarket")))

    def test_each_line_exactly_once(self):
        self.phone("2026-10-04 09:00:00 1200 taxi")
        self.run_inbox()
        code, out, _ = self.run_inbox()
        self.assertEqual(code, 0)
        self.assertIn("nothing new (1 line(s) already imported)", out)
        self.phone("2026-10-04 13:30:10 300 coffee")
        _, out, _ = self.run_inbox()
        self.assertNotIn("taxi", out)
        self.assertEqual([e.note for e in self.entries()], ["taxi", "coffee"])

    def test_same_text_at_different_times_is_two_expenses(self):
        self.phone("2026-10-04 09:00:00 300 coffee", "2026-10-04 15:00:00 300 coffee")
        self.run_inbox()
        self.assertEqual(len(self.entries()), 2)

    def test_duplicated_line_and_cleared_inbox(self):
        line = "2026-10-04 09:00:00 1200 taxi"
        self.phone(line, line)  # e.g. an iCloud sync glitch
        self.run_inbox()
        self.assertEqual(len(self.entries()), 1)
        self.inbox.write_text("")  # Avo clears the file; an old line coming back is still skipped
        self.phone("2026-10-05 08:00:00 2000 lunch", line)
        self.run_inbox()
        self.assertEqual([e.note for e in self.entries()], ["taxi", "lunch"])

    def test_formats(self):
        self.inbox.write_text("﻿2026-10-04T14:32:05+04:00 20eur museum\r\n"
                              "\r\n"
                              "2026-10-04 14:33 | 1.5k bus, 900 bread\r\n"
                              "2026-10-04 08:00:00 yesterday 5000 gym\r\n"
                              "2026-10-04 08:01:00   \n", encoding="utf-8")
        code, _, _ = self.run_inbox()
        self.assertEqual(code, 0)
        self.assertEqual([(e.date, e.note, e.amount, e.currency) for e in self.entries()],
                         [("2026-10-04", "museum", Decimal("20"), "EUR"),
                          ("2026-10-04", "bus", Decimal("1500"), "AMD"),
                          ("2026-10-04", "bread", Decimal("900"), "AMD"),
                          ("2026-10-03", "gym", Decimal("5000"), "AMD")])

    def test_bad_lines_reported_once_good_ones_imported(self):
        self.phone("800 supermarket", "2026-10-04 10:00:00 coffee", "2026-10-04 10:01:00 300 tea")
        code, out, err = self.run_inbox()
        self.assertEqual(code, 1)
        self.assertIn("couldn't read 2 line(s)", err)
        self.assertIn("no timestamp", err)
        self.assertIn("no amount in 'coffee'", err)
        self.assertEqual([e.note for e in self.entries()], ["tea"])
        code, _, err = self.run_inbox()
        self.assertEqual((code, err), (0, ""))

    def test_dry_run_writes_nothing(self):
        self.phone("2026-10-04 09:00:00 1200 taxi")
        code, out, _ = self.run_inbox("-n")
        self.assertEqual(code, 0)
        self.assertIn("would log 1200 AMD", out)
        self.assertFalse((self.dir / "spend.journal").exists())
        self.assertFalse((self.dir / ".spend-inbox-state").exists())
        self.run_inbox()
        self.assertEqual(len(self.entries()), 1)

    def test_no_inbox_yet(self):
        code, out, _ = self.run_inbox()
        self.assertEqual(code, 0)
        self.assertIn("no inbox at", out)
        self.assertFalse((self.dir / ".spend-inbox-state").exists())

    def test_icloud_placeholder_is_downloaded(self):
        (self.inbox.parent / ".inbox.txt.icloud").write_text("")

        def brctl(cmd, **kw):
            self.assertEqual(cmd, ["brctl", "download", str(self.inbox)])
            self.inbox.write_text("2026-10-04 09:00:00 1200 taxi\n")

        with mock.patch.object(inbox.subprocess, "run", side_effect=brctl):
            code, _, _ = self.run_inbox()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.entries()), 1)

    def test_icloud_placeholder_not_arriving(self):
        (self.inbox.parent / ".inbox.txt.icloud").write_text("")
        with mock.patch.object(inbox.subprocess, "run"), mock.patch.object(inbox.time, "sleep"):
            code, _, err = self.run_inbox()
        self.assertEqual(code, 1)
        self.assertIn("still downloading from iCloud", err)


class ParseLine(unittest.TestCase):
    def test_parse_line(self):
        [e] = inbox.parse_line("2026-09-30 23:59:59 50usd jeans")
        self.assertEqual((e.date, e.amount, e.currency, e.note), (date(2026, 9, 30), Decimal("50"), "USD", "jeans"))
        self.assertEqual(inbox.parse_line("2026-09-30 23:59:59"), [])

    def test_key_ignores_spacing(self):
        self.assertEqual(inbox.key("2026-10-04 09:00:00  1200 taxi "), inbox.key("2026-10-04 09:00:00 1200 taxi"))


if __name__ == "__main__":
    unittest.main()
