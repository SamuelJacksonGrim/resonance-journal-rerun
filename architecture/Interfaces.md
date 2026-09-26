---
artifact: Interfaces
status: partial
order: 7
fills: "plug points — the contracts between modules that make them swappable"
depends_on: [Types, Contracts]
filled_by: both
last_decision: D-004
---

# Interfaces — Resonance Journal

Optional at `thin` depth. One real plug point: the `Journal` service API. A
future web or TUI front end replaces `cli.py` and calls the same API.

### Journal (service API)
- **Purpose:** every read and write of journal data.
- **Inputs → outputs:**
  - `open(path) → Journal`; `close()`
  - `create(title, body, date?, tags?) → id`
  - `update(id, title?, body?, date?) → changed: bool`; `revert(id, rev) → bool`
  - `get(id) → Entry`; `search(Query) → [Entry]`; `revisions(id)`; `revision(id, rev)`
  - `add_tags / remove_tags(id, tags) → [tag]`; `tag_counts() → [(tag, n)]`
  - `add_link / remove_link(src, dst)`; `links_out / links_in(id) → [EntryRef]`
  - `neighborhood(id, depth) → [(EntryRef, distance, parent)]`; `path(a, b) → [EntryRef] | None`
  - `set_archived(id, bool) → changed`; `delete(id)`
  - `dump() → [record]`; `merge([record]) → stats`
- **Upholds contract:** G1, G2, G6, G9, I1–I5.
- **Implemented by:** `journal.py`
- **Consumed by:** `cli.py`, `exchange.py`

### Exchange
- **Purpose:** move a journal to and from files.
- **Inputs → outputs:** `export_journal(journal, dir, active_only) → {entries, path}`;
  `import_journal(journal, path) → stats`; `validate_document(obj) → [record]`.
- **Upholds contract:** G3, G4, G5, G8, G10.
- **Implemented by:** `exchange.py`
- **Consumed by:** `cli.py`
