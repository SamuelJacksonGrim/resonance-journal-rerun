---
artifact: Modules
status: partial
order: 8
fills: "module list, ownership, responsibilities, boundaries"
depends_on: [Interfaces]
filled_by: both
last_decision: D-004
---

# Modules — Resonance Journal

Optional at `thin` depth; filled because it is four rows.

| Module | Responsibility | Owns (boundary) | Implements interface |
|--------|----------------|-----------------|----------------------|
| `resonance/model.py` | Bounds, value types, validators, error types | Every numeric bound; tag normalization | — (pure library) |
| `resonance/journal.py` | Storage, schema, all SQL, revisions, links, search, graph | The SQLite file | Journal |
| `resonance/exchange.py` | Export JSON + Markdown; validate and import JSON | Export format (`resonance-journal` v1) | Exchange |
| `resonance/cli.py` | Argument parsing, body input, delete confirmation, output, exit codes | The terminal | — (consumer) |
| `tests/` | Unit tests per module + subprocess end-to-end smoke | — | — |
