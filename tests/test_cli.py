"""End-to-end smoke: the real CLI in a subprocess, the main path a user takes."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CliSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "home" / "journal.db"

    def run_cli(self, *args, db=None, stdin=None, ok=True):
        env = {**os.environ, "RESONANCE_DB": str(db or self.db), "PYTHONPATH": str(ROOT)}
        p = subprocess.run([sys.executable, "-m", "resonance", *args], input=stdin,
                           capture_output=True, text=True, env=env, cwd=self.tmp.name)
        if ok:
            self.assertEqual(p.returncode, 0, f"{args}: {p.stderr}")
        return p

    def test_main_path(self):
        r = self.run_cli
        self.assertIn("created #1", r("new", "Tide", "-b", "Low tide at dawn", "-d", "2026-05-01",
                                      "-t", "sea").stdout)
        r("new", "Harbor", "--body-file", "-", "-d", "2026-05-03", stdin="Boats\nand gulls\n")
        r("new", "Lighthouse", "-d", "2026-05-09")
        r("edit", "1", "--body", "Low tide before dawn")
        r("tag", "2", "sea", "#Birds")
        r("link", "1", "2")
        r("link", "2", "3")

        show = r("show", "2").stdout
        self.assertIn("Boats\nand gulls", show)
        self.assertIn("links to:", show)
        self.assertIn("linked from:", show)
        self.assertIn("#birds #sea", show)

        self.assertIn("revision 1", r("history", "1", "--rev", "1").stdout)
        self.assertIn("Low tide at dawn", r("history", "1", "--rev", "1").stdout)

        found = r("search", "tide", "--from", "2026-04-30", "--to", "2026-05-02").stdout
        self.assertIn("Tide", found)
        self.assertNotIn("Harbor", found)
        self.assertIn("Harbor", r("list", "-t", "birds").stdout)

        graph = r("graph", "1", "--depth", "2").stdout
        self.assertIn("Lighthouse", graph)
        self.assertIn("2 hops", graph)
        self.assertIn("Lighthouse", r("path", "1", "3").stdout)

        r("archive", "3")
        self.assertNotIn("Lighthouse", r("list").stdout)
        self.assertIn("Lighthouse", r("list", "--archived").stdout)

        out = Path(self.tmp.name) / "export"
        self.assertIn("exported 3 entries", r("export", str(out)).stdout)
        self.assertTrue((out / "index.md").is_file())
        self.assertEqual(len(list((out / "entries").glob("*.md"))), 3)

        other = Path(self.tmp.name) / "other" / "journal.db"
        self.assertIn("imported 3 entries", r("import", str(out), db=other).stdout)
        self.assertEqual(r("list", "--all", db=other).stdout, r("list", "--all").stdout)
        self.assertIn("linked from:", r("show", "2", db=other).stdout)

        # Delete is guarded: refused without --yes when stdin is not a terminal.
        refused = r("delete", "1", ok=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("not confirmed", refused.stderr)
        self.assertIn("Tide", r("show", "1").stdout)
        r("delete", "1", "--yes")
        self.assertEqual(r("show", "1", ok=False).returncode, 1)
        self.assertNotIn("linked from:", r("show", "2").stdout)

    def test_errors_exit_nonzero_without_traceback(self):
        for args, code in [(("show", "42"), 1), (("new", "x", "-d", "2026-02-30"), 1),
                           (("link", "1", "1"), 1), (("show", "abc"), 2), (("bogus",), 2)]:
            p = self.run_cli(*args, ok=False)
            self.assertEqual(p.returncode, code, args)
            self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
