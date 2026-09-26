---
artifact: Types
status: partial
order: 5
fills: "core domain types, primitives, enums, identifiers, structural schemas"
depends_on: [Contracts]
filled_by: both
last_decision: D-006
---

# Types — Resonance Journal

Optional at `thin` depth; filled because it is small. Source of truth:
`resonance/model.py`.

## Core Domain Types
- **Entry** — `id, uuid, title, body, entry_date, created_at, updated_at, archived_at, tags[]`.
  `archived` is derived: `archived_at is not None`.
- **Revision** — `rev, title, body, entry_date, saved_at`: the entry's state
  *before* edit number `rev`.
- **EntryRef** — `id, uuid, title, entry_date, archived`: a pointer used for
  links, backlinks, graph nodes, and paths.
- **Query** — `words[], tags[], date_from?, date_to?, scope, limit`.

## Primitives & Identifiers
| Name | Form | Notes |
|---|---|---|
| entry id | positive integer | Local to one database (D-006). |
| entry uuid | lowercase UUID v4 | Stable across export/import. |
| date | `YYYY-MM-DD`, a real calendar date | The day the entry is *about*. |
| timestamp | `YYYY-MM-DDTHH:MM:SSZ` (UTC) | `created_at`, `updated_at`, `archived_at`, `saved_at`. |
| tag | `[a-z0-9][a-z0-9_/-]{0,39}` | Input `#Work` normalizes to `work`. |

## Enums
- **scope**: `active` (default) · `archived` · `all`.

## Errors
`JournalError` → `ValidationError` (bad input), `NotFound` (unknown id/revision/link),
`Conflict` (duplicate link, self-link, link cap, non-empty export dir). The CLI
maps every `JournalError` to exit code 1.

## Structural Schemas
- **Export document** (`journal.json`): `{format: "resonance-journal", version: 1,
  exported_at, entries: [{uuid, title, body, date, created_at, updated_at,
  archived_at, tags[], links[uuid], revisions[{rev, title, body, date, saved_at}]}]}`.
- **Import stats**: `{added, skipped, links_added, links_skipped}`.
