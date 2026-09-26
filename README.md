# Resonance Journal

A small, local-first journal for the terminal. Create, edit, tag, link,
search, view, archive, delete, export, and import journal entries. Everything
lives in one SQLite file on your machine. No account, no network, no
dependencies beyond Python 3.11+.

Design and decisions: [`INTENT.md`](INTENT.md) and [`architecture/`](architecture/README.md),
built with the [Architecture-Blueprints-Frameworks](https://github.com/SamuelJacksonGrim/Architecture-Blueprints-Frameworks) methodology.

## Run it

```sh
python3 -m resonance --help          # from this folder, no install needed
pip install .                        # optional: adds a `resonance` command
```

The journal is stored at `~/.resonance-journal/journal.db` (folder `0700`,
file `0600`). Use another file with `--db PATH` or `RESONANCE_DB=PATH`.

## A quick tour

```sh
resonance new "Low tide" -b "Walked out past the rocks." -t sea -t morning
resonance new "Harbor" --body-file notes.txt --date 2026-05-03      # or --body-file - for stdin
resonance edit 1 --body "Walked out past the rocks before dawn."    # old text kept in history
resonance history 1            # earlier versions (last 20 per entry)
resonance history 1 --rev 1    # print one in full
resonance revert 1 1           # restore it (the current text goes to history too)

resonance tag 2 sea birds      # untag 2 birds · tags (all tags with counts)
resonance link 1 2             # 1 -> 2; unlink 1 2
resonance show 2               # the entry, its links, and what links to it
resonance graph 1 --depth 3    # everything within 3 link hops (max 5)
resonance path 1 7             # shortest chain of links between two entries

resonance list                                     # newest first, active entries
resonance search tide rocks                        # entries containing every word
resonance search -t sea --from 2026-05-01 --to 2026-05-31
resonance list --archived        # or --all; --limit N (default 50, max 1000)

resonance archive 2            # hide from lists; unarchive 2 brings it back
resonance delete 2             # permanent: asks you to type the id (or pass --yes)

resonance export ~/journal-export          # new or empty folder only
resonance import ~/journal-export          # merge into this (or another) journal
```

## Export and import

`export DIR` writes:

- `journal.json` — the complete journal (entries, tags, links, and history),
  the file `import` reads;
- `index.md` and `entries/*.md` — one Markdown file per entry, with clickable
  links and backlinks to other entries. Open the folder in any Markdown viewer.

`--active-only` leaves out archived entries. Links to them become plain text,
so no link in the export is broken.

`import` merges by each entry's permanent ID: new entries are added, entries
you already have are skipped (your local copy wins), and links are restored.
Importing the same file twice changes nothing.

## Limits

These limits keep storage from growing without bound. All are set in `resonance/model.py`.

| What | Limit |
|---|---|
| Earlier versions kept per entry | 20 (oldest dropped first) |
| Title / body | 200 characters / 1,000,000 characters |
| Tags per entry | 20 (letters, digits, `_ / -`, up to 40 chars) |
| Outgoing links per entry | 100 |
| Graph depth | 5 hops |
| Search results | 50 by default, 1000 max |
| Import file | 64 MiB |

The number of entries is not limited.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```

The suite has 38 tests, covering the service, export and import round trips,
Markdown link integrity, and an end-to-end run of the real CLI in a
subprocess.

## Not included (on purpose)

- **Sync between devices:** would need a server or a network. Use export/import instead.
- **Encryption at rest:** not built. If you want it, the trade-off is that a
  forgotten passphrase means the journal is lost.
- **Web or TUI interface, attachments, PDF/HTML export, scheduled backups:**
  these weren't requested. The service layer is independent of the CLI, so
  any of them can be added later.
- **License file:** not chosen here. That decision is yours.
