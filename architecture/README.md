---
artifact: README
status: complete
order: 10
fills: "front door — what/why/problem/components for the instantiated system"
depends_on: [Architecture, Flows, Contracts]
filled_by: both
last_decision: D-009
---

# Resonance Journal — design

## What is this?
A small local-first command-line journal: entries you can create, edit (with
recoverable history), tag, link, search, view, archive, delete, export, and
import back, all stored in one SQLite file on your machine.

## Why does it exist?
To keep a personal journal whose entries relate to each other ("resonate")
through tags and links, without an account, a server, or a dependency to
install.

## What problem does it solve?
Plain-text journals lose structure (no reliable tags, links, or history);
hosted apps take the writing off your machine. This keeps it local, linked,
searchable by text/tag/date, and exportable to readable, clickable Markdown
plus a lossless JSON you can import again.

## Major components
From [Architecture](Architecture.md) (and [Modules](Modules.md)):
- **CLI** (`cli.py`) — the terminal front end.
- **Model** (`model.py`) — all bounds and validators.
- **Journal service** (`journal.py`) — the only owner of the SQLite file.
- **Exchange** (`exchange.py`) — export to JSON + Markdown, import from JSON.

Reading order: [Intent](../INTENT.md) → [Architecture](Architecture.md) →
[Flows](Flows.md) → [Contracts](Contracts.md) → [DecisionLog](DecisionLog.md).

## Slices
One slice covers the whole intent; every included counterpart is built. Nothing
is left unbuilt.

## Artifact status
Depth `thin`: Architecture, Flows, Contracts, DecisionLog, README must be complete.

| Artifact | Status |
|----------|--------|
| Architecture | complete |
| Flows | complete |
| Contracts | complete |
| Types | partial |
| Schemas | partial |
| Interfaces | partial |
| Modules | partial |
| Dependencies | partial |
| DecisionLog | complete |
| README | complete |
