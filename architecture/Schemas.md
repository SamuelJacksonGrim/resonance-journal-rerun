---
artifact: Schemas
status: partial
order: 6
fills: "conceptual ontology — Entity→State→Event→Evaluation→Decision→Action"
depends_on: [Types]
filled_by: both
last_decision: D-006
---

# Schemas — Resonance Journal

Optional at `thin` depth. Kept short: this is a CRUD journal, not a cognitive system.

## Core Transformation Chain
- **Entity:** Entry (with Tags, Links, Revisions).
- **State:** active | archived; current text + ≤ 20 prior versions.
- **Event:** an operator command (new, edit, tag, link, archive, delete, import …).
- **Evaluation:** `model` validators; Journal rules (caps, self-link, duplicate).
- **Decision:** accept → one transaction; reject → error, nothing written.
- **Action:** SQLite write, or export files written.

## Cognitive Schemas
Not applicable.

## Information Schemas
Storage (SQLite, `PRAGMA user_version = 1`):

| Table | Key | Columns | Cascade |
|---|---|---|---|
| `entries` | `id`; `uuid` unique | title, body, entry_date (indexed), created_at, updated_at, archived_at | — |
| `tags` | (entry_id, tag) | tag indexed | on entry delete |
| `links` | (src_id, dst_id); `CHECK src ≠ dst` | created_at; dst indexed | on either end's delete |
| `revisions` | (entry_id, rev) | title, body, entry_date, saved_at | on entry delete |

## Transformation Schemas
- DB row → `Entry` (Journal) → CLI text or export record.
- Export record: local `id` dropped, links become UUIDs.
- Import record → validated record → DB rows with fresh local ids; links resolved UUID → id.
