---
artifact: Flows
status: complete
order: 3
fills: "behavioral blueprint — request, event, execution, error, state-update flows"
depends_on: [Architecture]
filled_by: both
last_decision: D-005
---

# Flows — Resonance Journal

## Request Flow
Every command is one request: `resonance [--db PATH] <command> [args]`.

1. `cli.main` parses argv. Bad syntax → argparse message, exit 2.
2. Body text is resolved: `--body TEXT`, or `--body-file PATH` (`-` = stdin).
3. `Journal.open(path)` creates the parent directory (0700) and the file
   (0600) if missing, enables foreign keys, and creates/migrates the schema
   (`PRAGMA user_version`).
4. The command's service call validates its input through `model`, then runs
   in one transaction.
5. The CLI formats the returned value and exits 0.

Per-command behavior:

| Command | Behavior |
|---|---|
| `new` | Validate title/body/date/tags → insert entry with a fresh UUID → print id. |
| `edit ID` | Load entry → if nothing changed, no-op → else snapshot current title/body/date as the next revision, drop revisions beyond 20, update, bump `updated_at`. |
| `history ID` / `history ID --rev N` | List revisions (newest first) / print one revision in full. |
| `revert ID N` | Same path as `edit`, with revision N's values; the pre-revert text becomes a revision, so a revert is itself undoable. |
| `show ID` | Entry, tags, outgoing links, backlinks (incoming), archive state, revision count. |
| `list` / `search [TEXT]` | Filters: every word of TEXT appears in title or body (case-insensitive), `--tag` (all must match), `--from`/`--to` inclusive date range, scope active (default) / `--archived` / `--all`, `--limit` (default 50, max 1000). Ordered by entry date, newest first. |
| `tag ID T…` / `untag ID T…` / `tags` | Add / remove tags (normalized lowercase, leading `#` stripped) / tag counts. |
| `link A B` / `unlink A B` | Directed link A→B. Self-links and duplicates are refused / removed. |
| `graph ID [--depth N]` | Breadth-first walk over links in both directions, depth 1–5 (default 2); prints each reached entry with its hop distance and the entry it was reached from. |
| `path A B` | Shortest undirected link path A…B, or "no path". Bounded by the entry count. |
| `archive ID` / `unarchive ID` | Set / clear `archived_at`. Archived entries leave default lists and searches but keep tags, links, history. |
| `delete ID` | Refuse unless `--yes`, or stdin is a terminal and the operator types the id back. Then remove the entry, its tags, its links in both directions, and its revisions. |
| `export DIR` | Refuse if DIR exists and is non-empty. Write `journal.json` (lossless), `index.md`, `entries/<date>-<slug>-<uuid8>.md` with relative links and backlinks. `--active-only` omits archived entries. |
| `import PATH` | PATH is `journal.json` or an export directory. Validate the whole file, then in one transaction insert entries whose UUID is unknown, skip known UUIDs, union links whose two ends now exist. Report counts. |

## Event Flow
None. There are no events, subscribers, or background work. Each command is
synchronous and complete when the process exits.

## Execution Flow
There is no long-running loop. The core work unit is: open → validate →
transaction → format → exit. The only iterative algorithms are bounded walks:
`graph` (BFS to depth ≤ 5) and `path` (BFS until found or all reachable
entries visited).

## Error Flow
| Failure | Where caught | Result |
|---|---|---|
| Bad arguments | argparse | usage text, exit 2 |
| Invalid value (title too long, bad date, bad tag, oversize body) | `model` validators | `error: <field>: <reason>`, exit 1, nothing written |
| Unknown id | Journal | `error: entry N not found`, exit 1 |
| Conflict (duplicate link, self-link, link cap, non-empty export dir) | Journal / Exchange | `error: …`, exit 1, nothing written |
| Delete not confirmed | CLI | `error: delete not confirmed`, exit 1, nothing written |
| Bad import file (too big, not JSON, wrong format/version, invalid record) | Exchange, before any write | `error: import: …` naming the record index, exit 1, nothing written |
| SQLite error mid-transaction | Journal context manager | rollback, error re-raised, exit 1 |
| Database newer than this program (`user_version` > supported) | `Journal.open` | refuse to open, exit 1 — never downgrade-write |

Error messages name fields and ids, never entry bodies.

## State-Update Flow
All persistent state is the SQLite file.

- **Entry**: created by `new`/`import`; mutated by `edit`/`revert`
  (`updated_at` bumped); `archived_at` set/cleared by `archive`/`unarchive`;
  removed by `delete` (cascades).
- **Revision**: appended only by `edit`/`revert`/import; numbered per entry,
  monotonically; the oldest are dropped so at most 20 remain per entry.
- **Tag / Link**: added and removed only by their verbs, `import`, or the
  entry's deletion (cascade).
- Every mutation is one transaction; a crash mid-command leaves the previous
  state.
