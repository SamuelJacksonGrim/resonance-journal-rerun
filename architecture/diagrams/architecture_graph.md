# Architecture Graph — Resonance Journal

```mermaid
graph TD
  U[Operator shell] --> CLI[cli.py<br/>argparse, formatting, confirm]
  CLI --> M[model.py<br/>bounds + validators, pure]
  CLI --> J[journal.py<br/>only sqlite3 importer]
  CLI --> X[exchange.py<br/>export / import]
  X --> M
  X --> J
  J --> M
  J --> DB[(journal.db<br/>0600, dir 0700)]
  X --> FS[(export dir<br/>journal.json, index.md, entries/*.md)]
  FS -. import reads journal.json .-> X
```
