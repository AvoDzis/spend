import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from spend import cli, journal


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SPEND_DIR": str(self.dir)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_add_line(self):
        code, out = self.run_cli("800dram", "supermarket,", "50usd", "jeans")
        self.assertEqual(code, 0)
        self.assertIn("logged 800 AMD", out)
        notes = [e.note for e in journal.read_entries(self.dir / "spend.journal")]
        self.assertEqual(notes, ["supermarket", "jeans"])

    def test_dry_run_and_src(self):
        code, out = self.run_cli("-n", "--src", "claude", "300", "coffee")
        self.assertEqual(code, 0)
        self.assertIn("would log 300 AMD", out)
        self.assertFalse((self.dir / "spend.journal").exists())
        self.run_cli("--src", "claude", "300", "coffee")
        self.assertEqual(journal.read_entries(self.dir / "spend.journal")[0].tags, "src:claude")

    def test_bad_line(self):
        code, _ = self.run_cli("supermarket")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
