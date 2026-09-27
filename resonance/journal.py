# Resonance Journal (resonance-journal-rerun)
# Copyright (C) 2026 Samuel Jackson Grim
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# A commercial license is also available: see LICENSING.md.
"""The journal service: the only module that imports sqlite3 (Contracts guardrails).

Every public mutating method runs in exactly one transaction (Contracts G2).
Every query binds values with `?` (Contracts G9).
"""

from __future__ import annotations

import os
import sqlite3
import uuid as uuidlib
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import model
from .model import Conflict, Entry, EntryRef, NotFound, Query, Revision, ValidationError

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE entries (
    id          INTEGER PRIMARY KEY,
    uuid        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    entry_date  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived_at TEXT
);
CREATE INDEX entries_date ON entries(entry_date);
CREATE TABLE tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);
CREATE INDEX tags_tag ON tags(tag);
CREATE TABLE links (
    src_id     INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    dst_id     INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (src_id, dst_id),
    CHECK (src_id <> dst_id)
);
CREATE INDEX links_dst ON links(dst_id);
CREATE TABLE revisions (
    entry_id   INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    rev        INTEGER NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    saved_at   TEXT NOT NULL,
    PRIMARY KEY (entry_id, rev)
);
"""

ENTRY_COLUMNS = "id, uuid, title, body, entry_date, created_at, updated_at, archived_at"


def default_db_path() -> Path:
    env = os.environ.get("RESONANCE_DB")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".resonance-journal" / "journal.db"


def _contains(haystack: str | None, needle: str) -> bool:
    """Unicode case-insensitive substring test; SQLite's LIKE folds ASCII only."""
    return haystack is not None and needle in haystack.casefold()


class Journal:
    def __init__(self, conn: sqlite3.Connection, path: Path):
        self._conn = conn
        self.db_path = path

    # --- lifecycle --------------------------------------------------------

    @classmethod
    def open(cls, path: Path | str | None = None) -> "Journal":
        path = Path(path).expanduser() if path else default_db_path()
        if str(path) != ":memory:":
            if not path.parent.exists():
                path.parent.mkdir(parents=True, mode=0o700)
            if not path.exists():
                # Create owner-only before SQLite touches it (Contracts G8).
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        conn = sqlite3.connect(str(path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.create_function("rj_contains", 2, _contains, deterministic=True)
        try:
            # Off by default per connection; without it deletes orphan links (Contracts).
            conn.execute("PRAGMA foreign_keys = ON")
            journal = cls(conn, path)
            journal._migrate()
        except sqlite3.DatabaseError as err:
            conn.close()
            raise model.JournalError(f"cannot open {path} as a journal ({err})") from None
        except BaseException:
            conn.close()
            raise
        return journal

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise model.JournalError(
                f"database schema v{version} is newer than this program (v{SCHEMA_VERSION})")
        if version == 0:
            with self._tx():
                # executescript() would COMMIT implicitly; run statements inside our tx.
                for stmt in SCHEMA.split(";"):
                    if stmt.strip():
                        self._conn.execute(stmt)
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # --- reads ------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> Entry:
        tags = [r[0] for r in self._conn.execute(
            "SELECT tag FROM tags WHERE entry_id = ? ORDER BY tag", (row["id"],))]
        return Entry(id=row["id"], uuid=row["uuid"], title=row["title"], body=row["body"],
                     entry_date=row["entry_date"], created_at=row["created_at"],
                     updated_at=row["updated_at"], archived_at=row["archived_at"], tags=tags)

    def get(self, entry_id: int) -> Entry:
        row = self._conn.execute(
            f"SELECT {ENTRY_COLUMNS} FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise NotFound(f"entry {entry_id} not found")
        return self._row_to_entry(row)

    def _require(self, entry_id: int) -> None:
        if self._conn.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone() is None:
            raise NotFound(f"entry {entry_id} not found")

    def _refs(self, sql: str, params: tuple) -> list[EntryRef]:
        return [EntryRef(id=r["id"], uuid=r["uuid"], title=r["title"], entry_date=r["entry_date"],
                         archived=r["archived_at"] is not None)
                for r in self._conn.execute(sql, params)]

    def links_out(self, entry_id: int) -> list[EntryRef]:
        return self._refs(
            "SELECT e.id, e.uuid, e.title, e.entry_date, e.archived_at FROM links l "
            "JOIN entries e ON e.id = l.dst_id WHERE l.src_id = ? ORDER BY e.entry_date, e.id",
            (entry_id,))

    def links_in(self, entry_id: int) -> list[EntryRef]:
        return self._refs(
            "SELECT e.id, e.uuid, e.title, e.entry_date, e.archived_at FROM links l "
            "JOIN entries e ON e.id = l.src_id WHERE l.dst_id = ? ORDER BY e.entry_date, e.id",
            (entry_id,))

    def ref(self, entry_id: int) -> EntryRef:
        refs = self._refs("SELECT id, uuid, title, entry_date, archived_at FROM entries "
                          "WHERE id = ?", (entry_id,))
        if not refs:
            raise NotFound(f"entry {entry_id} not found")
        return refs[0]

    def search(self, q: Query) -> list[Entry]:
        # Clause text is fixed in code; only values are bound (Contracts G9).
        clauses: list[str] = []
        params: list[object] = []
        for word in q.words:
            # Plain substring match: user text is never SQL and never a wildcard.
            clauses.append("(rj_contains(e.title, ?) OR rj_contains(e.body, ?))")
            params += [word.casefold(), word.casefold()]
        for tag in q.tags:
            clauses.append("EXISTS (SELECT 1 FROM tags t WHERE t.entry_id = e.id AND t.tag = ?)")
            params.append(tag)
        if q.date_from:
            clauses.append("e.entry_date >= ?")
            params.append(q.date_from)
        if q.date_to:
            clauses.append("e.entry_date <= ?")
            params.append(q.date_to)
        if q.scope == "active":
            clauses.append("e.archived_at IS NULL")
        elif q.scope == "archived":
            clauses.append("e.archived_at IS NOT NULL")
        where = " AND ".join(clauses) or "1"
        rows = self._conn.execute(
            f"SELECT {ENTRY_COLUMNS} FROM entries e WHERE {where} "
            "ORDER BY e.entry_date DESC, e.id DESC LIMIT ?", (*params, q.limit)).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def tag_counts(self) -> list[tuple[str, int]]:
        return [(r[0], r[1]) for r in self._conn.execute(
            "SELECT tag, COUNT(*) FROM tags GROUP BY tag ORDER BY COUNT(*) DESC, tag")]

    def revisions(self, entry_id: int) -> list[Revision]:
        self._require(entry_id)
        return [Revision(rev=r["rev"], title=r["title"], body=r["body"],
                         entry_date=r["entry_date"], saved_at=r["saved_at"])
                for r in self._conn.execute(
                    "SELECT rev, title, body, entry_date, saved_at FROM revisions "
                    "WHERE entry_id = ? ORDER BY rev DESC", (entry_id,))]

    def revision(self, entry_id: int, rev: int) -> Revision:
        for r in self.revisions(entry_id):
            if r.rev == rev:
                return r
        raise NotFound(f"entry {entry_id} has no revision {rev}")

    def _neighbors(self, entry_id: int) -> list[int]:
        return [r[0] for r in self._conn.execute(
            "SELECT dst_id FROM links WHERE src_id = ? UNION "
            "SELECT src_id FROM links WHERE dst_id = ? ORDER BY 1", (entry_id, entry_id))]

    def neighborhood(self, entry_id: int, depth: int) -> list[tuple[EntryRef, int, int | None]]:
        """Entries within `depth` undirected hops: (entry, distance, reached_from)."""
        depth = model.validate_depth(depth)
        self._require(entry_id)
        seen: dict[int, tuple[int, int | None]] = {entry_id: (0, None)}
        queue = deque([entry_id])
        while queue:
            current = queue.popleft()
            dist = seen[current][0]
            if dist == depth:
                continue
            for nxt in self._neighbors(current):
                if nxt not in seen:
                    seen[nxt] = (dist + 1, current)
                    queue.append(nxt)
        return [(self.ref(eid), d, parent) for eid, (d, parent) in seen.items()]

    def path(self, src: int, dst: int) -> list[EntryRef] | None:
        """Shortest undirected link path src..dst, or None. Bounded by entry count."""
        self._require(src)
        self._require(dst)
        parent: dict[int, int | None] = {src: None}
        queue = deque([src])
        while queue:
            current = queue.popleft()
            if current == dst:
                chain = []
                node: int | None = dst
                while node is not None:
                    chain.append(node)
                    node = parent[node]
                return [self.ref(n) for n in reversed(chain)]
            for nxt in self._neighbors(current):
                if nxt not in parent:
                    parent[nxt] = current
                    queue.append(nxt)
        return None

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

    # --- writes -----------------------------------------------------------

    def create(self, title: str, body: str = "", entry_date: str | None = None,
               tags: list[str] | None = None) -> int:
        title = model.validate_title(title)
        body = model.validate_body(body)
        entry_date = model.validate_date(entry_date or model.today())
        tag_list = model.normalize_tags(list(tags or []))
        ts = model.now_utc()
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO entries (uuid, title, body, entry_date, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuidlib.uuid4()), title, body, entry_date, ts, ts))
            entry_id = cur.lastrowid
            c.executemany("INSERT INTO tags (entry_id, tag) VALUES (?, ?)",
                          [(entry_id, t) for t in tag_list])
        return entry_id

    def _snapshot_and_update(self, c: sqlite3.Connection, current: Entry, title: str,
                             body: str, entry_date: str) -> None:
        # Snapshot BEFORE the update, same transaction (Contracts G1).
        next_rev = c.execute("SELECT COALESCE(MAX(rev), 0) + 1 FROM revisions WHERE entry_id = ?",
                             (current.id,)).fetchone()[0]
        ts = model.now_utc()
        c.execute("INSERT INTO revisions (entry_id, rev, title, body, entry_date, saved_at) "
                  "VALUES (?, ?, ?, ?, ?, ?)",
                  (current.id, next_rev, current.title, current.body, current.entry_date, ts))
        c.execute("DELETE FROM revisions WHERE entry_id = ? AND rev <= ?",
                  (current.id, next_rev - model.MAX_REVISIONS))
        c.execute("UPDATE entries SET title = ?, body = ?, entry_date = ?, updated_at = ? "
                  "WHERE id = ?", (title, body, entry_date, ts, current.id))

    def update(self, entry_id: int, title: str | None = None, body: str | None = None,
               entry_date: str | None = None) -> bool:
        """Apply changes; returns False (and writes nothing) when nothing changed."""
        new_title = model.validate_title(title) if title is not None else None
        new_body = model.validate_body(body) if body is not None else None
        new_date = model.validate_date(entry_date) if entry_date is not None else None
        with self._tx() as c:
            cur = self.get(entry_id)
            t = new_title if new_title is not None else cur.title
            b = new_body if new_body is not None else cur.body
            d = new_date if new_date is not None else cur.entry_date
            if (t, b, d) == (cur.title, cur.body, cur.entry_date):
                return False
            self._snapshot_and_update(c, cur, t, b, d)
        return True

    def revert(self, entry_id: int, rev: int) -> bool:
        with self._tx() as c:
            cur = self.get(entry_id)
            r = self.revision(entry_id, rev)
            if (r.title, r.body, r.entry_date) == (cur.title, cur.body, cur.entry_date):
                return False
            self._snapshot_and_update(c, cur, r.title, r.body, r.entry_date)
        return True

    def add_tags(self, entry_id: int, tags: list[str]) -> list[str]:
        new = model.normalize_tags(list(tags))
        with self._tx() as c:
            existing = self.get(entry_id).tags
            merged = existing + [t for t in new if t not in existing]
            if len(merged) > model.MAX_TAGS_PER_ENTRY:
                raise ValidationError(f"tags: more than {model.MAX_TAGS_PER_ENTRY} on one entry")
            c.executemany("INSERT OR IGNORE INTO tags (entry_id, tag) VALUES (?, ?)",
                          [(entry_id, t) for t in new])
        return sorted(merged)

    def remove_tags(self, entry_id: int, tags: list[str]) -> list[str]:
        gone = [model.normalize_tag(t) for t in tags]
        with self._tx() as c:
            self._require(entry_id)
            c.executemany("DELETE FROM tags WHERE entry_id = ? AND tag = ?",
                          [(entry_id, t) for t in gone])
        return self.get(entry_id).tags

    def add_link(self, src: int, dst: int) -> None:
        if src == dst:
            raise Conflict("link: an entry cannot link to itself")
        with self._tx() as c:
            self._require(src)
            self._require(dst)
            if c.execute("SELECT 1 FROM links WHERE src_id = ? AND dst_id = ?",
                         (src, dst)).fetchone():
                raise Conflict(f"link: {src} already links to {dst}")
            n = c.execute("SELECT COUNT(*) FROM links WHERE src_id = ?", (src,)).fetchone()[0]
            if n >= model.MAX_LINKS_PER_ENTRY:
                raise Conflict(f"link: entry {src} already has {model.MAX_LINKS_PER_ENTRY} links")
            c.execute("INSERT INTO links (src_id, dst_id, created_at) VALUES (?, ?, ?)",
                      (src, dst, model.now_utc()))

    def remove_link(self, src: int, dst: int) -> None:
        with self._tx() as c:
            cur = c.execute("DELETE FROM links WHERE src_id = ? AND dst_id = ?", (src, dst))
            if cur.rowcount == 0:
                raise NotFound(f"link: {src} does not link to {dst}")

    def set_archived(self, entry_id: int, archived: bool) -> bool:
        """Returns False when the entry was already in the requested state."""
        with self._tx() as c:
            cur = self.get(entry_id)
            if cur.archived == archived:
                return False
            c.execute("UPDATE entries SET archived_at = ? WHERE id = ?",
                      (model.now_utc() if archived else None, entry_id))
        return True

    def delete(self, entry_id: int) -> None:
        """Permanent. The caller owns confirmation (Contracts authority table)."""
        with self._tx() as c:
            self._require(entry_id)
            c.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    # --- bulk (used by exchange) ------------------------------------------

    def dump(self) -> list[dict]:
        """Every entry with tags, outgoing link UUIDs, and revisions, oldest first."""
        out = []
        rows = self._conn.execute(
            f"SELECT {ENTRY_COLUMNS} FROM entries ORDER BY entry_date, id").fetchall()
        for row in rows:
            e = self._row_to_entry(row)
            out.append({
                "id": e.id, "uuid": e.uuid, "title": e.title, "body": e.body,
                "date": e.entry_date, "created_at": e.created_at, "updated_at": e.updated_at,
                "archived_at": e.archived_at, "tags": e.tags,
                "links": [r.uuid for r in self.links_out(e.id)],
                "revisions": [{"rev": r.rev, "title": r.title, "body": r.body,
                               "date": r.entry_date, "saved_at": r.saved_at}
                              for r in reversed(self.revisions(e.id))],
            })
        return out

    def merge(self, records: list[dict]) -> dict[str, int]:
        """Insert records with unknown UUIDs, skip known ones, union links. One transaction.

        Records must already be validated (exchange.validate_document).
        """
        stats = {"added": 0, "skipped": 0, "links_added": 0, "links_skipped": 0}
        with self._tx() as c:
            for rec in records:
                if c.execute("SELECT 1 FROM entries WHERE uuid = ?", (rec["uuid"],)).fetchone():
                    stats["skipped"] += 1
                    continue
                cur = c.execute(
                    "INSERT INTO entries (uuid, title, body, entry_date, created_at, updated_at, "
                    "archived_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rec["uuid"], rec["title"], rec["body"], rec["date"], rec["created_at"],
                     rec["updated_at"], rec["archived_at"]))
                eid = cur.lastrowid
                c.executemany("INSERT INTO tags (entry_id, tag) VALUES (?, ?)",
                              [(eid, t) for t in rec["tags"]])
                c.executemany(
                    "INSERT INTO revisions (entry_id, rev, title, body, entry_date, saved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [(eid, r["rev"], r["title"], r["body"], r["date"], r["saved_at"])
                     for r in rec["revisions"]])
                stats["added"] += 1
            ids = {r[0]: r[1] for r in c.execute("SELECT uuid, id FROM entries")}
            ts = model.now_utc()
            for rec in records:
                src = ids[rec["uuid"]]
                for dst_uuid in rec["links"]:
                    dst = ids.get(dst_uuid)
                    if dst is None or dst == src:
                        stats["links_skipped"] += 1
                        continue
                    if c.execute("SELECT 1 FROM links WHERE src_id = ? AND dst_id = ?",
                                 (src, dst)).fetchone():
                        continue
                    n = c.execute("SELECT COUNT(*) FROM links WHERE src_id = ?",
                                  (src,)).fetchone()[0]
                    if n >= model.MAX_LINKS_PER_ENTRY:
                        stats["links_skipped"] += 1
                        continue
                    c.execute("INSERT INTO links (src_id, dst_id, created_at) VALUES (?, ?, ?)",
                              (src, dst, ts))
                    stats["links_added"] += 1
        return stats
