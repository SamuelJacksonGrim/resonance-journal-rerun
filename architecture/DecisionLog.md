---
artifact: DecisionLog
status: complete
order: 99
fills: "architectural memory — consequential decisions, not every change"
depends_on: []
filled_by: both
last_decision: D-010
---

# DecisionLog — Resonance Journal

> Append-only. Supersede, never rewrite. Titles are the question.
> Status values: `active` · `superseded by D-NNN` · `reversed by D-NNN`.

### D-001 — Build order: Flows before Contracts?
- **Date:** 2026-09-26
- **Decided by:** both (inherited from the methodology's PIPELINE)
- **Status:** active
- **Decision:** Architecture → Flows → Contracts → Types → … → implementation → verification → README.
- **Alternatives:** Contracts before Flows (rejected).
- **Reason:** A contract constrains a behavior; a guarantee cannot be written for a flow not yet described.
- **Affects:** all artifacts, build path.

### D-002 — Which stack, given the human named none?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** Python ≥ 3.11, standard library only: `sqlite3` storage, `argparse` CLI, `unittest` tests. Installable via `pyproject.toml`, runnable as `python -m resonance` without installing.
- **Alternatives:** Node + a web UI (adds a listener → `networked` exposure, CSRF/CSP/token controls, and a second moving part; not "small"); plain JSON/Markdown files as the store (no atomic multi-record writes, so edit-with-history and import could half-apply); a TUI (more code, harder to smoke-test).
- **Reason:** Smallest stack that can smoke-test every verb, zero dependencies to install ("self-contained"), and SQLite gives transactions and cascades for free. The service layer is UI-independent, so a web or TUI front end can be added later without a rewrite.
- **Affects:** everything; INTENT stack line; README install steps.

### D-003 — Which class, depth, and exposure; ask the human anything?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** `class: cli`, `depth: thin`, `exposure: local-single`. No questions asked.
- **Alternatives:** `standard` depth "because it stores personal writing" — rejected: the SELECTOR defines the operator's own writing on their own machine as not private data, and persistent local state alone is not a trigger. Asking about users/sync — rejected: "local-first", "a user", "self-contained" already fill every consequential field.
- **Reason:** No SELECTOR Step C trigger holds. The escalation conditions are recorded in INTENT `escalate_if`.
- **Affects:** INTENT, which artifacts must be complete.

### D-004 — Which component may touch the database?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** Only `resonance/journal.py` imports `sqlite3` or contains SQL. Exchange and CLI go through the `Journal` API; import's bulk write is `Journal.merge`.
- **Alternatives:** Let `exchange.py` write rows directly for speed.
- **Reason:** Parameterized-only SQL (G9), `foreign_keys = ON` (cascade correctness), and one-transaction-per-command (G2) are enforceable only with a single owner. This is ordinary layering, not a depth trigger.
- **Affects:** Architecture, Contracts guardrails, Dependencies.

### D-005 — What bounds storage growth?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** Per-entry hard caps in `model.py`: 20 revisions (oldest dropped), 20 tags, 100 outgoing links, 200-char titles, 1,000,000-char bodies; imports ≤ 64 MiB; result lists ≤ 1000. The number of entries is not capped.
- **Alternatives:** Unbounded full-copy history (grows with every keystroke-save; rejected); diff-based history (bounded differently, but more code and a corrupt diff loses every later version); capping entry count (would refuse the operator's own writing — the product itself).
- **Reason:** Edits must be recoverable (implied counterpart) without unbounded growth. Worst case per entry ≈ 21 × 1 MB. Entries grow only by explicit operator action; export is the archive/backup path.
- **Affects:** Contracts G6 bounds table, Flows (edit), model.py.

### D-006 — How are entries identified across journals?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** Every entry has a random UUID (v4) used for export, import, and links in files. Small integer ids are local, for typing at the CLI only.
- **Alternatives:** Integer ids everywhere (merging two journals collides and silently mislinks); UUIDs at the CLI (unpleasant to type).
- **Reason:** Round-trip and merge must keep links pointing at the same entries (G3, G4).
- **Affects:** Types, Schemas (DB), exchange format.

### D-007 — What does import do when an entry already exists?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** Merge by UUID. Unknown UUID → insert with its tags and revisions. Known UUID → skip; local copy wins. Links are unioned wherever both ends exist after the import. The whole file is validated before the first write; the merge is one transaction.
- **Alternatives:** Overwrite existing entries (silently destroys local edits — an irreversible action); refuse any non-empty target (blocks merging two journals); newest-`updated_at` wins (clock-dependent, surprising).
- **Reason:** Import must never destroy local text, and re-importing must be safe (idempotent). To take the incoming version, the operator deletes the local entry and re-imports.
- **Affects:** Contracts G3/G4, exchange.py, Journal.merge.

### D-008 — How is permanent delete guarded?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** `delete` is a separate verb from the reversible `archive`. It needs `--yes`, or, on a terminal, typing the entry id back. Without a terminal and without `--yes` it refuses. Delete cascades to tags, links (both directions), and revisions.
- **Alternatives:** Soft delete / trash (a second archive with a retention rule — duplicates archive); no delete at all (fails the create↔delete counterpart).
- **Reason:** Delete of the operator's own record behind a guard is an ordinary feature (SELECTOR), and the guard makes accidents from scripts or history recall unlikely.
- **Affects:** Flows, Contracts G7, cli.py.

### D-009 — What is the export format, and which part is importable?
- **Date:** 2026-09-26
- **Decided by:** AI
- **Status:** active
- **Decision:** `export DIR` writes `journal.json` (versioned `resonance-journal` v1, lossless: entries, tags, links by UUID, revisions) plus a Markdown tree (`index.md`, `entries/<date>-<slug>-<uuid8>.md`) with relative links and backlinks. Only `journal.json` is imported. The target directory must be new or empty.
- **Alternatives:** Markdown-only export parsed back on import (fragile to hand edits, loses revisions); JSON only (not readable or navigable without the app); overwrite the target (could clobber the operator's files).
- **Reason:** One lossless machine format for round-trip, one human format that works in any Markdown viewer with clickable links (G5). Links to entries left out by `--active-only` become plain text so no link is ever broken.
- **Affects:** Contracts G3/G5, exchange.py, README.

### D-010 — Under what terms is this released?
- **Date:** 2026-09-27
- **Decided by:** human (the AI applied it)
- **Status:** active
- **Decision:** Dual license, AGPL-3.0-only OR commercial, mirroring
  resonance-memory: LICENSE, LICENSING.md, COMMERCIAL-LICENSE.md, NOTICE,
  CONTRIBUTING.md, legal/, SPDX headers on source files, README badges, and
  license metadata in pyproject.toml. legal/AUTHORSHIP.md records the one-shot
  process as it actually happened, together with the author's position that
  the work is protected through the methodology and the templates it was
  instantiated from.
- **Alternatives:** Copy resonance-memory's authorship record word for word
  (rejected: its multi-model account is false for this project).
- **Affects:** repository root, legal/, source file headers.
