import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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

    def notes(self):
        return [e.note for e in journal.read_entries(self.dir / "spend.journal")]

    def test_rm_last_and_numbers(self):
        self.run_cli("100 a, 200 b, 300 c, 400 d")
        code, out = self.run_cli("rm", "-y", "last")
        self.assertEqual((code, self.notes()), (0, ["a", "b", "c"]))
        self.assertIn("removed 400 AMD", out)
        code, _ = self.run_cli("-y", "rm", "3", "1", "1")  # numbers as in `spend list`; repeats are fine
        self.assertEqual((code, self.notes()), (0, ["b"]))
        self.run_cli("500 e")  # the file still appends cleanly
        self.assertEqual(self.notes(), ["b", "e"])

    def test_rm_asks_first(self):
        self.run_cli("100 a, 200 b")
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="n"):
            code, out = self.run_cli("rm", "last")
        self.assertEqual((code, self.notes()), (1, ["a", "b"]))
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="y"):
            code, _ = self.run_cli("rm", "last")
        self.assertEqual((code, self.notes()), (0, ["a"]))

    def test_rm_without_terminal_needs_yes(self):
        self.run_cli("100 a")
        with mock.patch("sys.stdin.isatty", return_value=False), redirect_stderr(io.StringIO()) as err:
            code, _ = self.run_cli("rm", "last")
        self.assertEqual((code, self.notes()), (2, ["a"]))
        self.assertIn("add -y", err.getvalue())

    def test_rm_dry_run_and_bad_targets(self):
        self.run_cli("100 a")
        code, out = self.run_cli("-n", "rm", "1")
        self.assertEqual((code, self.notes()), (0, ["a"]))
        self.assertIn("would remove 100 AMD", out)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_cli("rm", "-y", "5")[0], 1)
            self.assertEqual(self.run_cli("rm", "-y", "x")[0], 2)
            self.assertEqual(self.run_cli("rm")[0], 2)
        self.assertEqual(self.notes(), ["a"])


if __name__ == "__main__":
    unittest.main()
