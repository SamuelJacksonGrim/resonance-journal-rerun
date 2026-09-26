---
artifact: Contracts
status: complete
order: 4
fills: "guarantees, assumptions, invariants, pre/post-conditions"
depends_on: [Architecture, Flows]
filled_by: both
last_decision: D-005
---

# Contracts — Resonance Journal

## Guarantees
- **G1 — No silent text loss.** An `edit` or `revert` that changes an entry
  first stores the previous title/body/date as a revision, in the same
  transaction as the change. The only paths that discard text are the
  revision cap (G6) and an explicit, confirmed `delete`.
- **G2 — Atomic commands.** Each command's writes happen in one SQLite
  transaction. A failed command leaves the journal's contents unchanged
  (no partial import, no half-applied edit).
- **G3 — Lossless round-trip.** `import` of a `journal.json` produced by
  `export` into an empty journal reproduces every entry's UUID, title, body,
  date, timestamps, archive state, tags, links, and revisions.
- **G4 — Idempotent import.** Importing the same file twice changes nothing
  the second time. Entries are keyed by UUID; a known UUID is skipped (local
  copy wins); links are a set union.
- **G5 — Navigable export.** Every link in the Markdown export is a relative
  path to a file that exists in the same export, in both directions
  (outgoing links and backlinks). Links to entries omitted by
  `--active-only` are written as plain text, never as broken links.
- **G6 — Bounded growth.** Every per-entry collection has a hard cap
  (table below). Nothing else grows without an operator action.
- **G7 — Guarded delete.** `delete` never runs without `--yes` or an
  interactive confirmation where the operator types the id. Archive is a
  separate, reversible verb.
- **G8 — Owner-only files** (SECURITY `always`). The journal directory is
  created 0700 and the database file 0600; export directories 0700 and export
  files 0600.
- **G9 — Parameterized SQL only** (SECURITY `always`). Every query binds
  values with `?`. Search words are bound as values to `rj_contains(column, ?)`,
  a Python function registered on the connection that does a Unicode
  case-folded substring test, so user text is never SQL and never a wildcard.
- **G10 — Input validated at the boundary** (SECURITY `always`). CLI values
  and every import record pass `model` validators before any write.
- **G11 — No entry text in errors.** Error messages name fields, ids, and
  record indexes, never titles or bodies. The program writes no log files.

### Bounds (G6) — all defined once in `resonance/model.py`

| Constant | Value | Provenance |
|---|---|---|
| `MAX_TITLE_LEN` | 200 chars | A title is a line, not a paragraph. |
| `MAX_BODY_LEN` | 1,000,000 chars | ~500 printed pages; far above any single journal entry, small enough that 20 revisions stay ≤ ~20 MB worst case. |
| `MAX_TAGS_PER_ENTRY` | 20 | Tags are for filtering; more than 20 stops filtering. |
| `TAG_PATTERN` | `[a-z0-9][a-z0-9_/-]{0,39}` | Lowercase so `#Work` and `#work` are one tag; `/` allows `project/x`. |
| `MAX_LINKS_PER_ENTRY` | 100 outgoing | Keeps `show` and exports readable; graph walks stay small. |
| `MAX_REVISIONS` | 20 per entry | Recover several recent edits without unbounded full-copy history. Oldest dropped first. |
| `MAX_GRAPH_DEPTH` | 5 | Beyond ~5 hops the neighborhood is most of the journal; use `path` instead. |
| `DEFAULT_LIMIT` / `MAX_LIMIT` | 50 / 1000 results | One screen by default; a hard ceiling on output size. |
| `MAX_IMPORT_BYTES` | 64 MiB | Well above a realistic journal export; stops a wrong file from exhausting memory. |

The entry count itself is bounded only by the operator's writing and disk:
this is the product, grows only by explicit operator action, and is recorded
as a decision (D-005).

## Assumptions
- **A1** — One operator, one process at a time. SQLite's file lock serializes
  accidental concurrent runs; there is no multi-writer design.
- **A2** — The filesystem honors POSIX permission bits. On filesystems that do
  not (e.g. some Windows mounts), G8 is best-effort.
- **A3** — Python 3.11+ with the standard `sqlite3` module (SQLite ≥ 3.24).
- **A4** — Dates are calendar days (`YYYY-MM-DD`) in the operator's local
  sense; timestamps are UTC.

## Invariants
- **I1** — Every entry has a UUID (unique), a non-empty title ≤ 200 chars, a
  valid `YYYY-MM-DD` date, a body ≤ 1,000,000 chars.
- **I2** — Revisions per entry ≤ 20; revision numbers per entry strictly
  increase and are never reused while the entry exists.
- **I3** — No link has `src = dst`; no duplicate (src, dst) pair; ≤ 100
  outgoing links per entry.
- **I4** — Tags, links, and revisions never outlive their entry
  (`ON DELETE CASCADE` with `PRAGMA foreign_keys = ON`).
- **I5** — `archived_at` is either NULL (active) or a UTC timestamp.

## Invariants that look optional but aren't
- **`PRAGMA foreign_keys = ON` on every connection.** SQLite defaults it off
  per connection. Without it, `delete` leaves orphan links and revisions that
  later show up as ghost backlinks and inflate the graph — no error, just
  wrong answers. It is set inside `Journal.open`, never elsewhere.
- **Revision snapshot happens before the update, in the same transaction.**
  Taking it after, or in a separate transaction, records the *new* text as
  "previous" (or nothing, on a crash) and G1 silently fails.
- **Revision numbers come from `MAX(rev) + 1`, not `COUNT + 1`.** After the cap
  drops old revisions, `COUNT + 1` reuses a number and `history --rev N`
  returns the wrong text.
- **Import keys entries by UUID, never by integer id.** Integer ids are local
  to one database; matching on them merges unrelated entries between journals.
- **Links are exported by UUID, not id.** Same reason; otherwise a re-import
  into a non-empty journal links the wrong entries.
- **Tags are normalized (lowercase, `#` stripped) in exactly one place,
  `model.normalize_tag`.** A second normalizer that disagrees splits one tag
  into two that never match in search.
- **Search must not use SQLite `LIKE`.** `LIKE` folds ASCII case only, so
  `über` would silently miss "Über"; and unescaped `%`/`_` would match
  unrelated entries. Both are wrong results with no error. `rj_contains` is
  registered in `Journal.open` and used for every word.

## Guardrails — do NOT
- Don't import `sqlite3` or write SQL outside `journal.py`. Add a method to
  `Journal` instead.
- Don't build SQL with f-strings or `%` from values. Bind with `?`; if a
  column or order clause must vary, choose from a fixed whitelist in code.
- Don't raise a bound by editing a literal at the call site. Change the
  constant in `model.py` and its provenance row above.
- Don't add a "force" path to delete that skips confirmation in interactive
  use. Scripts pass `--yes` explicitly.
- Don't overwrite a non-empty directory on export. Choose a new directory.
- Don't make import "update" existing entries by UUID. Local copy wins; to take
  the incoming version, delete the local entry and import again.
- Don't print entry bodies in error messages or exceptions.

## Authority hierarchy (single source of truth)
| Decision | Authority | Others |
|---|---|---|
| Whether an input value is valid | `model` validators | CLI and Exchange call them; never re-implement. |
| What is stored; revision capping; archive state; link rules | `Journal` | CLI and Exchange request, never write directly. |
| Whether a delete is confirmed | CLI (it owns the terminal) | `Journal.delete` assumes confirmation happened. |
| File format of exports and imports | `exchange` (`FORMAT_NAME`, `FORMAT_VERSION`) | Journal is format-agnostic. |
| All numeric bounds | `model.py` constants | Everyone reads them. |

## Pre/Post-Conditions
| Operation | Pre | Post |
|---|---|---|
| `Journal.create` | validated fields | new entry with fresh UUID; returns id |
| `Journal.update` | entry exists; validated fields | unchanged → no write; changed → one new revision holding prior values, ≤ 20 revisions, entry updated |
| `Journal.revert(id, rev)` | entry and revision exist | as `update` with the revision's values |
| `Journal.add_link(a, b)` | both exist; a ≠ b; not already linked; a has < 100 links | link a→b exists |
| `Journal.delete(id)` | entry exists; confirmation done by caller | entry, its tags, links (both directions), revisions gone |
| `Journal.search(q)` | validated query | ≤ `limit` entries matching every filter, newest date first |
| `Journal.neighborhood(id, d)` | entry exists; 1 ≤ d ≤ 5 | every entry within d undirected hops, each with distance and parent |
| `exchange.export_journal(dir)` | dir missing or empty | journal.json + index.md + entries/*.md; every md link resolves (G5) |
| `exchange.import_journal(path)` | file ≤ 64 MiB; format/version match; every record valid | new UUIDs inserted, known skipped, links unioned; one transaction |
