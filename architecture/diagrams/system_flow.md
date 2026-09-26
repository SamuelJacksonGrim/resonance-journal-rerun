# System Flow — Resonance Journal

Primary path: one invocation, one transaction.

```
argv ─► parse ─► validate (model) ─► open journal (create/migrate schema)
                     │                        │
                     │ invalid                ▼
                     ▼                 BEGIN ─► operation ─► COMMIT ─► format ─► stdout, exit 0
               stderr, exit 1/2                  │
                                                 └─ (error) ─► ROLLBACK ─► stderr, exit 1

edit:    load current ─► unchanged? no-op : save current as revision ─► cap to 20 ─► update
export:  target new/empty? ─► read all ─► write journal.json + entries/*.md + index.md
import:  size ≤ 64 MiB ─► parse ─► validate every record ─► BEGIN ─► insert new UUIDs,
         skip known ─► union links by UUID ─► COMMIT ─► report counts
```
