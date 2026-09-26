---
artifact: Dependencies
status: partial
order: 9
fills: "allowed/forbidden dependency directions, hierarchy, import rules"
depends_on: [Modules, Interfaces]
filled_by: both
last_decision: D-004
---

# Dependencies — Resonance Journal

Optional at `thin` depth.

## Module Hierarchy
1. `model` (depends on nothing but the standard library)
2. `journal` → model
3. `exchange` → journal, model
4. `cli` → exchange, journal, model

## Allowed Directions
Downward only, as listed. Third-party packages: none (D-002).

## Forbidden Directions
- Anything except `journal` importing `sqlite3` (D-004).
- `model` importing any project module (it must stay pure so every layer can use it).
- `journal` or `exchange` importing `cli` (the service must work without a terminal).

## Import Rules
No cycles. Check: `grep -rn "sqlite3" resonance/` lists only `journal.py`.
