import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from resonance import model
from resonance.journal import Journal
from resonance.model import Conflict, NotFound, ValidationError


def q(words=(), tags=(), date_from=None, date_to=None, scope="active", limit=50):
    return model.validate_query(list(words), list(tags), date_from, date_to, scope, limit)


class JournalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nested" / "journal.db"
        self.j = Journal.open(self.path)

    def tearDown(self):
        self.j.close()
        self.tmp.cleanup()


class CreateAndValidate(JournalTestCase):
    def test_create_and_get(self):
        eid = self.j.create("  Hello  ", "body", "2026-01-02", ["Work", "#work", "a/b"])
        e = self.j.get(eid)
        self.assertEqual(e.title, "Hello")
        self.assertEqual(e.entry_date, "2026-01-02")
        self.assertEqual(e.tags, ["a/b", "work"])  # normalized + deduplicated
        self.assertRegex(e.uuid, model.UUID_PATTERN)
        self.assertFalse(e.archived)

    def test_rejects_bad_input_without_writing(self):
        bad = [dict(title=""), dict(title="x" * 201), dict(title="a\nb"),
               dict(title="t", entry_date="2026-13-01"), dict(title="t", entry_date="26-1-1"),
               dict(title="t", tags=["bad tag"]), dict(title="t", tags=[f"t{i}" for i in range(21)]),
               dict(title="t", body="x" * (model.MAX_BODY_LEN + 1))]
        for kwargs in bad:
            with self.subTest(kwargs=str(kwargs)[:60]), self.assertRaises(ValidationError):
                self.j.create(**kwargs)
        self.assertEqual(self.j.count(), 0)

    def test_not_found(self):
        with self.assertRaises(NotFound):
            self.j.get(99)


class EditHistory(JournalTestCase):
    def test_edit_keeps_previous_text(self):
        eid = self.j.create("T", "v1", "2026-01-01")
        self.assertTrue(self.j.update(eid, body="v2"))
        self.assertEqual(self.j.get(eid).body, "v2")
        revs = self.j.revisions(eid)
        self.assertEqual([(r.rev, r.body) for r in revs], [(1, "v1")])

    def test_unchanged_edit_writes_nothing(self):
        eid = self.j.create("T", "v1", "2026-01-01")
        before = self.j.get(eid).updated_at
        self.assertFalse(self.j.update(eid, title="T", body="v1"))
        self.assertEqual(self.j.revisions(eid), [])
        self.assertEqual(self.j.get(eid).updated_at, before)

    def test_revisions_bounded_and_numbers_never_reused(self):
        eid = self.j.create("T", "v0", "2026-01-01")
        for i in range(1, 31):
            self.j.update(eid, body=f"v{i}")
        revs = self.j.revisions(eid)
        self.assertEqual(len(revs), model.MAX_REVISIONS)
        self.assertEqual([r.rev for r in revs], list(range(30, 10, -1)))
        # rev N holds the text as it was before edit N.
        self.assertEqual(self.j.revision(eid, 30).body, "v29")
        self.assertEqual(self.j.revision(eid, 11).body, "v10")
        with self.assertRaises(NotFound):
            self.j.revision(eid, 10)

    def test_revert_is_itself_undoable(self):
        eid = self.j.create("T", "original", "2026-01-01")
        self.j.update(eid, title="T2", body="changed", entry_date="2026-02-02")
        self.assertTrue(self.j.revert(eid, 1))
        e = self.j.get(eid)
        self.assertEqual((e.title, e.body, e.entry_date), ("T", "original", "2026-01-01"))
        self.assertEqual(self.j.revision(eid, 2).body, "changed")
        self.assertFalse(self.j.revert(eid, 1))  # already at that text


class TagsLinksGraph(JournalTestCase):
    def test_tags_add_remove_counts(self):
        a = self.j.create("A")
        b = self.j.create("B")
        self.j.add_tags(a, ["x", "Y"])
        self.j.add_tags(b, ["x"])
        self.assertEqual(self.j.tag_counts(), [("x", 2), ("y", 1)])
        self.assertEqual(self.j.remove_tags(a, ["#X"]), ["y"])

    def test_tag_cap_is_atomic(self):
        a = self.j.create("A", tags=[f"t{i}" for i in range(19)])
        with self.assertRaises(ValidationError):
            self.j.add_tags(a, ["n1", "n2"])
        self.assertEqual(len(self.j.get(a).tags), 19)

    def test_link_rules(self):
        a, b = self.j.create("A"), self.j.create("B")
        self.j.add_link(a, b)
        with self.assertRaises(Conflict):
            self.j.add_link(a, b)
        with self.assertRaises(Conflict):
            self.j.add_link(a, a)
        with self.assertRaises(NotFound):
            self.j.add_link(a, 999)
        self.assertEqual([r.id for r in self.j.links_out(a)], [b])
        self.assertEqual([r.id for r in self.j.links_in(b)], [a])
        self.j.remove_link(a, b)
        with self.assertRaises(NotFound):
            self.j.remove_link(a, b)

    def test_link_cap(self):
        hub = self.j.create("hub")
        for i in range(model.MAX_LINKS_PER_ENTRY):
            self.j.add_link(hub, self.j.create(f"n{i}"))
        with self.assertRaises(Conflict):
            self.j.add_link(hub, self.j.create("one too many"))

    def test_neighborhood_multi_hop_both_directions(self):
        a, b, c, d, e = (self.j.create(n) for n in "ABCDE")
        self.j.add_link(a, b)
        self.j.add_link(c, b)  # incoming to b: still traversed
        self.j.add_link(c, d)
        got = {ref.id: (dist, parent) for ref, dist, parent in self.j.neighborhood(a, 2)}
        self.assertEqual(got, {a: (0, None), b: (1, a), c: (2, b)})
        got3 = {ref.id: dist for ref, dist, _ in self.j.neighborhood(a, 3)}
        self.assertEqual(got3[d], 3)
        self.assertNotIn(e, got3)
        with self.assertRaises(ValidationError):
            self.j.neighborhood(a, model.MAX_GRAPH_DEPTH + 1)

    def test_path(self):
        a, b, c, d = (self.j.create(n) for n in "ABCD")
        self.j.add_link(a, b)
        self.j.add_link(c, b)
        self.assertEqual([r.id for r in self.j.path(a, c)], [a, b, c])
        self.assertIsNone(self.j.path(a, d))


class ArchiveDelete(JournalTestCase):
    def test_archive_scope(self):
        a, b = self.j.create("A"), self.j.create("B")
        self.assertTrue(self.j.set_archived(a, True))
        self.assertFalse(self.j.set_archived(a, True))
        self.assertEqual([e.id for e in self.j.search(q())], [b])
        self.assertEqual([e.id for e in self.j.search(q(scope="archived"))], [a])
        self.assertEqual({e.id for e in self.j.search(q(scope="all"))}, {a, b})
        self.j.set_archived(a, False)
        self.assertEqual({e.id for e in self.j.search(q())}, {a, b})

    def test_delete_cascades_no_ghost_backlinks(self):
        a, b = self.j.create("A"), self.j.create("B")
        self.j.add_link(a, b)
        self.j.add_link(b, a)
        self.j.add_tags(a, ["t"])
        self.j.update(a, body="new")
        self.j.delete(a)
        self.assertEqual(self.j.links_in(b), [])
        self.assertEqual(self.j.links_out(b), [])
        self.assertEqual(self.j.tag_counts(), [])
        conn = sqlite3.connect(self.path)
        for table in ("tags", "links", "revisions"):
            self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        conn.close()


class Search(JournalTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.j.create("Morning walk", "Quiet river, 100% calm", "2026-03-01", ["walk"])
        self.b = self.j.create("Evening", "river again", "2026-03-15", ["walk", "evening"])
        self.c = self.j.create("Work notes", "a_b token", "2026-04-01", ["work"])

    def ids(self, **kw):
        return [e.id for e in self.j.search(q(**kw))]

    def test_words_are_anded_case_insensitive(self):
        self.assertEqual(self.ids(words=["RIVER"]), [self.b, self.a])
        self.assertEqual(self.ids(words=["river", "quiet"]), [self.a])

    def test_unicode_case_insensitive(self):
        eid = self.j.create("Über den Fluß", "ÉTÉ à Paris")
        self.assertEqual(self.ids(words=["über"]), [eid])
        self.assertEqual(self.ids(words=["été"]), [eid])
        self.assertEqual(self.ids(words=["FLUSS"]), [eid])  # casefold: ß == ss

    def test_wildcards_are_literal(self):
        self.assertEqual(self.ids(words=["100%"]), [self.a])
        self.assertEqual(self.ids(words=["%"]), [self.a])
        self.assertEqual(self.ids(words=["a_b"]), [self.c])
        self.assertEqual(self.ids(words=["_"]), [self.c])

    def test_date_range_inclusive(self):
        self.assertEqual(self.ids(date_from="2026-03-01", date_to="2026-03-15"), [self.b, self.a])
        self.assertEqual(self.ids(date_from="2026-03-02"), [self.c, self.b])
        self.assertEqual(self.ids(date_to="2026-03-01"), [self.a])
        with self.assertRaises(ValidationError):
            q(date_from="2026-04-01", date_to="2026-03-01")

    def test_tags_all_must_match_and_limit(self):
        self.assertEqual(self.ids(tags=["walk", "evening"]), [self.b])
        self.assertEqual(self.ids(limit=1), [self.c])
        with self.assertRaises(ValidationError):
            q(limit=model.MAX_LIMIT + 1)


class Storage(unittest.TestCase):
    def test_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dir" / "j.db"
            Journal.open(path).close()
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(path.parent).st_mode), 0o700)

    def test_refuses_newer_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "j.db"
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA user_version = 99")
            conn.close()
            with self.assertRaises(model.JournalError):
                Journal.open(path)

    def test_reopen_keeps_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "j.db"
            with Journal.open(path) as j:
                eid = j.create("Persisted")
            with Journal.open(path) as j:
                self.assertEqual(j.get(eid).title, "Persisted")


if __name__ == "__main__":
    unittest.main()
