---
artifact: Intent
status: complete
order: 0
fills: "human intent plus the inspectable class/depth decision"
depends_on: []
filled_by: both
last_decision: D-002
---

# Intent Card — Resonance Journal

> Rules for filling it: SELECTOR Step A of Architecture-Blueprints-Frameworks.
> Guesses are marked *(guess)*. Anything unmarked was stated or implied.

- **Want:** A small, self-contained, local-first journal. One person creates,
  edits, tags, links, searches, views, archives, and exports journal entries.
- **Must not:** Need a server, an account, or the network. Lose the writer's
  text silently. Grow storage without a stated bound.
- **Roles** (who uses it, and what each may do): one operator, the journal's
  writer, who may do everything. There are no other roles.
- **Runs where / exposed to:** the operator's own machine, as a command-line
  program under their OS user. No listener, no network.
- **Money:** none.
- **Private data / secrets:** none by the SELECTOR definition. The entries are
  the operator's own writing on their own machine. Files are still created
  owner-only (SECURITY `always` row). No secrets exist.
- **Irreversible actions:** none by the SELECTOR definition. Hard delete of the
  operator's own entry is guarded (a separate verb from archive plus an
  explicit confirmation).
- **Done when:** each named verb works from the CLI (create, edit, tag, link,
  search, view, archive, export) plus the included counterparts below; the
  export can be imported back with its links intact; tests and an end-to-end
  smoke run pass.
- **Stack** (chosen: the smallest that can smoke-test): Python 3.11+ standard
  library only, `sqlite3` for storage, `argparse` CLI, `unittest` tests.
  No third-party dependencies. See D-002.

## Implied counterparts

| Named | Expected but unstated | Decision | Why |
|---|---|---|---|
| create | delete (permanent) | include | create↔delete. Guarded: separate verb from archive, needs `--yes` or typing the id at a prompt. Only touches the operator's own store. |
| edit | recover the previous text | include | edit↔recover. Every edit saves the prior version as a revision; `history` and `revert`. Bounded at 20 revisions per entry (oldest dropped). |
| archive | unarchive | include | archive↔unarchive; archiving must be reversible or it is just delete. |
| tag | untag, list tags with counts | include | add↔remove; seeing your tag vocabulary is a category norm. |
| link | unlink; backlinks; traverse more than one step | include | connect↔disconnect/traverse. `show` lists outgoing and incoming links; `graph` walks the neighborhood to depth 1–5; `path` finds the shortest link path between two entries. |
| search | filter by date / date range; filter by tag; include archived on request | include | Dated records → filter by date is a category norm. |
| export | import (round-trip) | include | export↔import: data out must come back in, links still working. JSON export is the lossless format; import merges by entry UUID and is idempotent. |
| export | links navigable in the exported files | include | Markdown export writes one file per entry with relative links (and backlinks) that click through in any Markdown viewer, plus an `index.md`. |
| view | list recent entries | include | Viewing needs a way to find what to view. `list` is `search` with no query. |
| local-first | owner-only file permissions | include | SECURITY `always` row: the journal is personal writing. |
| local-first | sync across devices | exclude | Adds a second process or network boundary (a depth trigger). The JSON export/import is the manual path; sync is new intent. |
| local-first | encryption at rest | exclude | Not requested and no law or contract requires it. Listed for the human: SECURITY's encryption row says a forgotten passphrase would mean lost data, which is a real trade-off for them to choose. |
| view | web or TUI interface | exclude | "Small and self-contained": a CLI is the smallest interface that exercises every verb. The service layer is UI-independent, so a UI can be added without a rewrite. |
| export | other formats (PDF, HTML) | exclude | Markdown renders to both with standard tools. |
| search | full-text ranking / stemming (FTS5) | exclude | Substring AND-matching is predictable and enough at journal scale; FTS5 availability varies across Python builds. |
| entries | attachments / images | exclude | Would add the SECURITY `uploads` row (type detection, metadata stripping). New intent. |
| — | backups | exclude | Export is the backup. Scheduled backups would be a second process. Listed for the human. |
| — | privacy policy, licensing, terms | exclude | Norms outside software are never decided here. Listed for the human: no license file was added. |

## Selector decision

Axes, triggers, and profiles live only in SELECTOR.md of the methodology repo.

```yaml
class: cli
depth: thin
exposure: local-single
asked: none — every consequential field (roles, exposure, money, private data,
  irreversible actions) is stated or implied by the request: one local user,
  no network, no money, the operator's own writing.
reasons:
  - No Step C trigger holds: one process, no network, no secrets, no money, no
    private data (operator's own writing on their own machine), no
    irreversible actions (guarded delete of own records is an ordinary feature),
    no module-isolation contract, no reuse as a skeleton. Persistent local
    state alone is not a trigger.
  - Types, Interfaces, Modules, Dependencies, Schemas are filled anyway (as
    partial) because they are cheap and aid inspection; they do not raise the
    depth.
escalate_if:
  - sync, a web UI, or any listener is added (network boundary / networked exposure)
  - several OS users share one journal file (local-shared)
  - encryption at rest is requested (secrets: a passphrase-derived key)
  - attachments are added (SECURITY uploads row)
  - entries start holding other people's records (private data)
```
