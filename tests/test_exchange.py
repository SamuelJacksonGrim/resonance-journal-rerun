import json
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path

from resonance import exchange, model
from resonance.journal import Journal
from resonance.model import Conflict, ValidationError

MD_LINK = re.compile(r"\]\(([^)]+\.md)\)")


def snapshot(j: Journal) -> list[dict]:
    """Everything G3 promises to preserve, keyed by UUID (local ids may differ)."""
    return [{k: v for k, v in r.items() if k != "id"} for r in j.dump()]


class ExchangeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = Journal.open(self.root / "src.db")
        j = self.src
        self.a = j.create("Alpha [draft]", "first body", "2026-01-01", ["one", "shared"])
        self.b = j.create("Beta", "second", "2026-01-02", ["shared"])
        self.c = j.create("Gamma", "third", "2026-01-03")
        j.update(self.a, body="first body, edited")
        j.update(self.a, title="Alpha")
        j.add_link(self.a, self.b)
        j.add_link(self.b, self.c)
        j.add_link(self.c, self.a)
        j.set_archived(self.c, True)

    def tearDown(self):
        self.src.close()
        self.tmp.cleanup()

    def fresh(self, name="dst.db") -> Journal:
        j = Journal.open(self.root / name)
        self.addCleanup(j.close)
        return j


class RoundTrip(ExchangeTestCase):
    def test_lossless_round_trip(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        dst = self.fresh()
        stats = exchange.import_journal(dst, out)  # directory form
        self.assertEqual(stats["added"], 3)
        self.assertEqual(stats["links_added"], 3)
        self.assertEqual(snapshot(dst), snapshot(self.src))
        # Imported history still works: revert to the original text.
        alpha = next(e for e in dst.search(model.validate_query([], [], None, None, "all", 50))
                     if e.title == "Alpha")
        dst.revert(alpha.id, 1)
        self.assertEqual(dst.get(alpha.id).body, "first body")

    def test_reimport_is_idempotent(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        dst = self.fresh()
        exchange.import_journal(dst, out / exchange.JSON_NAME)
        before = snapshot(dst)
        stats = exchange.import_journal(dst, out / exchange.JSON_NAME)
        self.assertEqual((stats["added"], stats["skipped"], stats["links_added"]), (0, 3, 0))
        self.assertEqual(snapshot(dst), before)

    def test_merge_into_nonempty_keeps_local_and_links_by_uuid(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        dst = self.fresh()
        local = dst.create("Local only")  # takes id 1, which is Alpha's id in src
        exchange.import_journal(dst, out)
        self.assertEqual(dst.count(), 4)
        self.assertEqual(dst.get(local).title, "Local only")
        self.assertEqual(dst.links_out(local), [])
        alpha = [r for r in snapshot(dst) if r["title"] == "Alpha"][0]
        beta_uuid = [r for r in snapshot(dst) if r["title"] == "Beta"][0]["uuid"]
        self.assertEqual(alpha["links"], [beta_uuid])

    def test_import_into_same_journal_skips_everything(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        before = snapshot(self.src)
        stats = exchange.import_journal(self.src, out)
        self.assertEqual(stats["skipped"], 3)
        self.assertEqual(snapshot(self.src), before)


class MarkdownExport(ExchangeTestCase):
    def md_links(self, out: Path) -> list[tuple[Path, Path]]:
        pairs = []
        for md in [out / exchange.INDEX_NAME, *(out / exchange.ENTRIES_DIR).glob("*.md")]:
            for target in MD_LINK.findall(md.read_text(encoding="utf-8")):
                pairs.append((md, (md.parent / target).resolve()))
        return pairs

    def test_every_link_resolves(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        pairs = self.md_links(out)
        # index -> 3 entries, 3 links, 3 backlinks, 3 back-to-index
        self.assertEqual(len(pairs), 12)
        for md, target in pairs:
            self.assertTrue(target.is_file(), f"{md.name} -> {target}")

    def test_links_and_backlinks_present(self):
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        beta = next((out / exchange.ENTRIES_DIR).glob("*-beta-*.md")).read_text()
        self.assertIn("## Links", beta)
        self.assertIn("## Backlinks", beta)
        self.assertIn("-gamma-", beta.split("## Backlinks")[0])
        self.assertIn("-alpha-", beta.split("## Backlinks")[1])

    def test_active_only_has_no_broken_links(self):
        out = self.root / "export"
        res = exchange.export_journal(self.src, out, active_only=True)
        self.assertEqual(res["entries"], 2)
        for md, target in self.md_links(out):
            self.assertTrue(target.is_file(), f"{md.name} -> {target}")
        beta = next((out / exchange.ENTRIES_DIR).glob("*-beta-*.md")).read_text()
        self.assertIn("not in this export", beta)
        doc = json.loads((out / exchange.JSON_NAME).read_text())
        uuids = {e["uuid"] for e in doc["entries"]}
        self.assertTrue(all(u in uuids for e in doc["entries"] for u in e["links"]))

    def test_label_brackets_escaped(self):
        self.src.update(self.b, title="Beta [x]")
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        index = (out / exchange.INDEX_NAME).read_text()
        self.assertIn("[Beta \\[x\\]]", index)

    def test_refuses_nonempty_target_and_files_are_private(self):
        out = self.root / "busy"
        out.mkdir()
        (out / "keep.txt").write_text("mine")
        with self.assertRaises(Conflict):
            exchange.export_journal(self.src, out)
        self.assertEqual(os.listdir(out), ["keep.txt"])
        out2 = self.root / "export"
        exchange.export_journal(self.src, out2)
        self.assertEqual(stat.S_IMODE(os.stat(out2).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(out2 / exchange.JSON_NAME).st_mode), 0o600)


class ImportValidation(ExchangeTestCase):
    def write(self, doc) -> Path:
        p = self.root / "in.json"
        p.write_text(doc if isinstance(doc, str) else json.dumps(doc))
        return p

    def valid_doc(self) -> dict:
        out = self.root / "export"
        exchange.export_journal(self.src, out)
        return json.loads((out / exchange.JSON_NAME).read_text())

    def test_bad_documents_write_nothing(self):
        dst = self.fresh()
        good = self.valid_doc()
        cases = {
            "not json": "{nope",
            "wrong format": {"format": "other", "version": 1, "entries": []},
            "wrong version": {**good, "version": 2},
            "bad date in last record": {**good, "entries": good["entries"][:-1] + [
                {**good["entries"][-1], "date": "2026-02-31"}]},
            "duplicate uuid": {**good, "entries": good["entries"] + good["entries"][:1]},
            "too many revisions": {**good, "entries": [{**good["entries"][0], "revisions": [
                {"rev": i, "title": "t", "body": "", "date": "2026-01-01",
                 "saved_at": "2026-01-01T00:00:00Z"} for i in range(1, 22)]}]},
            "bad tag": {**good, "entries": [{**good["entries"][0], "tags": ["no spaces"]}]},
        }
        for name, doc in cases.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                exchange.import_journal(dst, self.write(doc))
            self.assertEqual(dst.count(), 0)

    def test_error_names_record_not_text(self):
        good = self.valid_doc()
        good["entries"][1]["title"] = "secret words " * 30
        with self.assertRaises(ValidationError) as ctx:
            exchange.import_journal(self.fresh(), self.write(good))
        self.assertIn("entry #1", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))

    def test_size_cap(self):
        orig = model.MAX_IMPORT_BYTES
        model.MAX_IMPORT_BYTES = 10
        self.addCleanup(setattr, model, "MAX_IMPORT_BYTES", orig)
        with self.assertRaises(ValidationError):
            exchange.import_journal(self.fresh(), self.write(self.valid_doc()))

    def test_dangling_link_skipped(self):
        good = self.valid_doc()
        good["entries"][0]["links"].append("00000000-0000-4000-8000-000000000000")
        stats = exchange.import_journal(self.fresh(), self.write(good))
        self.assertEqual(stats["links_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
