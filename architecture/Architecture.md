---
artifact: Architecture
status: complete
order: 2
fills: "structural blueprint — subsystems, boundaries, data & control flow"
depends_on: []
filled_by: both
last_decision: D-004
---

# Architecture — Resonance Journal

## Purpose
A single-process command-line journal. Each invocation opens one SQLite file
owned by the operator, performs one operation inside one transaction, prints a
result, and exits. There is no daemon, no listener, and no network. Structurally
it is four layers: a CLI shell, a pure validation/model layer, one journal
service that is the only owner of the database, and an exchange layer that
moves the journal in and out of files.

## Major Subsystems
- **CLI** (`resonance/cli.py`) — parses arguments, reads body text from flags,
  files, or stdin, asks the delete confirmation, formats output, maps errors to
  exit codes. Holds no state and no SQL.
- **Model** (`resonance/model.py`) — constants (all bounds live here), value
  types, and the validators every input passes before any write. Pure: no I/O.
- **Journal service** (`resonance/journal.py`) — the only module that imports
  `sqlite3`. Owns the schema, every query, revision capping, archive state,
  tags, links, search, and graph traversal.
- **Exchange** (`resonance/exchange.py`) — export (JSON + navigable Markdown
  tree) and import (JSON, merged by UUID). Talks to storage only through the
  Journal service API.

## Boundaries
- **Trust boundary:** everything from the command line, stdin, body files, and
  import files is untrusted until `model` validates it. The import file is
  validated in full before the first write.
- **Storage boundary:** the SQLite file (default
  `~/.resonance-journal/journal.db`, overridable by `--db` or `RESONANCE_DB`).
  Only the Journal service crosses it.
- **Filesystem boundary (exchange):** export writes only into a directory that
  is new or empty; import only reads.
- **Outside the system:** the operator's shell, their editor, whatever they do
  with exported files. Nothing leaves the machine.

## Data Flow
```
argv / stdin / body file ──► CLI ──► model.validate_* ──► Journal ──► SQLite file
                                                            │
                     import file ──► Exchange (validate all) ┘
                     Journal ──► Exchange ──► export dir (journal.json, index.md, entries/*.md)
Journal ──► CLI formatter ──► stdout        errors ──► stderr (never entry bodies)
```

## Control Flow
Control always originates in `cli.main(argv)`. It opens a `Journal` (which
creates or migrates the schema), calls exactly one service or exchange
operation, prints, closes, and returns an exit code: `0` success, `1` domain
error (not found, invalid input, conflict), `2` usage error (argparse).
Every mutating service call runs in a single SQLite transaction, so a failure
leaves the file as it was.

## High-Level Diagram
See [`diagrams/architecture_graph.md`](diagrams/architecture_graph.md) and
[`diagrams/system_flow.md`](diagrams/system_flow.md).
