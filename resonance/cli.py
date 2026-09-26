"""Command-line shell: parse, read input, confirm, format. No SQL, no state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, exchange, model
from .journal import Journal, default_db_path
from .model import Entry, EntryRef, JournalError


def _read_body(args: argparse.Namespace) -> str | None:
    if getattr(args, "body", None) is not None:
        return args.body
    path = getattr(args, "body_file", None)
    if path is None:
        return None
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise model.ValidationError(f"body-file: cannot read {path} ({type(err).__name__})")


def _tags(tags: list[str]) -> str:
    return " ".join("#" + t for t in tags)


def _ref_line(r: EntryRef) -> str:
    return f"#{r.id:<4} {r.entry_date}  {r.title}" + ("  [archived]" if r.archived else "")


def _entry_line(e: Entry) -> str:
    parts = [f"#{e.id:<4} {e.entry_date}  {e.title}"]
    if e.tags:
        parts.append(_tags(e.tags))
    if e.archived:
        parts.append("[archived]")
    return "  ".join(parts)


def _print_entries(entries: list[Entry], limit: int) -> None:
    if not entries:
        print("no entries")
        return
    for e in entries:
        print(_entry_line(e))
    if len(entries) == limit:
        print(f"(showing the first {limit}; use --limit to see more)")


# --- commands -----------------------------------------------------------------

def cmd_new(j: Journal, a: argparse.Namespace) -> None:
    eid = j.create(a.title, _read_body(a) or "", a.date, a.tag)
    print(f"created #{eid}")


def cmd_edit(j: Journal, a: argparse.Namespace) -> None:
    body = _read_body(a)
    if a.title is None and body is None and a.date is None:
        raise model.ValidationError("edit: give --title, --body, --body-file, or --date")
    print(f"updated #{a.id}" if j.update(a.id, a.title, body, a.date) else "no changes")


def cmd_show(j: Journal, a: argparse.Namespace) -> None:
    e = j.get(a.id)
    status = f"archived {e.archived_at}" if e.archived else "active"
    print(f"#{e.id}  {e.title}")
    print(f"date: {e.entry_date}   status: {status}   tags: {_tags(e.tags) or '-'}")
    print(f"uuid: {e.uuid}   created: {e.created_at}   updated: {e.updated_at}   "
          f"revisions: {len(j.revisions(e.id))}")
    print()
    print(e.body.rstrip("\n") if e.body.strip() else "(empty)")
    out, inc = j.links_out(e.id), j.links_in(e.id)
    if out:
        print("\nlinks to:")
        for r in out:
            print("  " + _ref_line(r))
    if inc:
        print("\nlinked from:")
        for r in inc:
            print("  " + _ref_line(r))


def _query(a: argparse.Namespace, words: list[str]) -> model.Query:
    scope = "all" if a.all else "archived" if a.archived else "active"
    return model.validate_query(words, a.tag, a.date_from, a.date_to, scope, a.limit)


def cmd_list(j: Journal, a: argparse.Namespace) -> None:
    q = _query(a, [])
    _print_entries(j.search(q), q.limit)


def cmd_search(j: Journal, a: argparse.Namespace) -> None:
    q = _query(a, a.text.split() if a.text else [])
    _print_entries(j.search(q), q.limit)


def cmd_tag(j: Journal, a: argparse.Namespace) -> None:
    print(f"#{a.id} tags: {_tags(j.add_tags(a.id, a.tags)) or '-'}")


def cmd_untag(j: Journal, a: argparse.Namespace) -> None:
    print(f"#{a.id} tags: {_tags(j.remove_tags(a.id, a.tags)) or '-'}")


def cmd_tags(j: Journal, a: argparse.Namespace) -> None:
    counts = j.tag_counts()
    if not counts:
        print("no tags")
    for tag, n in counts:
        print(f"#{tag}  {n}")


def cmd_link(j: Journal, a: argparse.Namespace) -> None:
    j.add_link(a.src, a.dst)
    print(f"linked #{a.src} -> #{a.dst}")


def cmd_unlink(j: Journal, a: argparse.Namespace) -> None:
    j.remove_link(a.src, a.dst)
    print(f"unlinked #{a.src} -> #{a.dst}")


def cmd_graph(j: Journal, a: argparse.Namespace) -> None:
    nodes = j.neighborhood(a.id, a.depth)
    children: dict[int | None, list[tuple[EntryRef, int]]] = {}
    for ref, dist, parent in nodes:
        children.setdefault(parent, []).append((ref, dist))

    def walk(parent: int | None, indent: int) -> None:
        for ref, dist in sorted(children.get(parent, []), key=lambda x: x[0].id):
            prefix = "  " * indent + ("└─ " if indent else "")
            print(f"{prefix}{_ref_line(ref)}" + (f"   ({dist} hop{'s' * (dist > 1)})" if dist else ""))
            walk(ref.id, indent + 1)

    walk(None, 0)
    print(f"{len(nodes) - 1} linked entr{'y' if len(nodes) == 2 else 'ies'} within {a.depth} hops")


def cmd_path(j: Journal, a: argparse.Namespace) -> None:
    chain = j.path(a.src, a.dst)
    if chain is None:
        raise model.NotFound(f"path: no link path between #{a.src} and #{a.dst}")
    for i, r in enumerate(chain):
        print(("  " * i + "└─ " if i else "") + _ref_line(r))


def cmd_history(j: Journal, a: argparse.Namespace) -> None:
    if a.rev is not None:
        r = j.revision(a.id, a.rev)
        print(f"#{a.id} revision {r.rev} (saved {r.saved_at})")
        print(f"title: {r.title}\ndate: {r.entry_date}\n")
        print(r.body.rstrip("\n") if r.body.strip() else "(empty)")
        return
    revs = j.revisions(a.id)
    if not revs:
        print(f"#{a.id} has no earlier versions")
    for r in revs:
        print(f"rev {r.rev:<3} saved {r.saved_at}  {r.entry_date}  {r.title}  "
              f"({len(r.body)} chars)")


def cmd_revert(j: Journal, a: argparse.Namespace) -> None:
    changed = j.revert(a.id, a.rev)
    print(f"#{a.id} reverted to revision {a.rev} (previous text kept in history)"
          if changed else "no changes")


def cmd_archive(j: Journal, a: argparse.Namespace) -> None:
    print(f"archived #{a.id}" if j.set_archived(a.id, True) else f"#{a.id} already archived")


def cmd_unarchive(j: Journal, a: argparse.Namespace) -> None:
    print(f"unarchived #{a.id}" if j.set_archived(a.id, False) else f"#{a.id} is not archived")


def cmd_delete(j: Journal, a: argparse.Namespace) -> None:
    e = j.get(a.id)
    if not a.yes:
        if not sys.stdin.isatty():
            raise JournalError("delete not confirmed: pass --yes (or run in a terminal)")
        print(f"Permanently delete #{e.id} \"{e.title}\" with its tags, links, and history?")
        print("Consider `archive` instead — it is reversible.")
        answer = input(f"Type {e.id} to confirm: ").strip()
        if answer != str(e.id):
            raise JournalError("delete not confirmed")
    j.delete(e.id)
    print(f"deleted #{e.id}")


def cmd_export(j: Journal, a: argparse.Namespace) -> None:
    res = exchange.export_journal(j, a.dir, active_only=a.active_only)
    print(f"exported {res['entries']} entries to {res['path']} "
          f"({exchange.JSON_NAME}, {exchange.INDEX_NAME}, {exchange.ENTRIES_DIR}/)")


def cmd_import(j: Journal, a: argparse.Namespace) -> None:
    s = exchange.import_journal(j, a.path)
    print(f"imported {s['added']} entries, skipped {s['skipped']} already present; "
          f"links added {s['links_added']}, skipped {s['links_skipped']}")


# --- parser -------------------------------------------------------------------

def _add_body(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--body", "-b", help="entry text")
    g.add_argument("--body-file", "-f", metavar="PATH", help="read entry text from a file (- = stdin)")


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tag", "-t", action="append", default=[], help="require tag (repeatable)")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="on or after date")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="on or before date")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--archived", action="store_true", help="only archived entries")
    scope.add_argument("--all", action="store_true", help="active and archived entries")
    p.add_argument("--limit", "-n", type=int, default=model.DEFAULT_LIMIT,
                   help=f"max results (default {model.DEFAULT_LIMIT}, max {model.MAX_LIMIT})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="resonance", description="Resonance Journal — a local-first journal.")
    p.add_argument("--db", help=f"journal file (default: $RESONANCE_DB or {default_db_path()})")
    p.add_argument("--version", action="version", version=f"resonance {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(fn=fn)
        return sp

    sp = add("new", cmd_new, "create an entry")
    sp.add_argument("title")
    _add_body(sp)
    sp.add_argument("--date", "-d", metavar="YYYY-MM-DD", help="entry date (default today)")
    sp.add_argument("--tag", "-t", action="append", default=[], help="tag (repeatable)")

    sp = add("edit", cmd_edit, "change an entry; the previous version is kept in history")
    sp.add_argument("id", type=int)
    sp.add_argument("--title")
    _add_body(sp)
    sp.add_argument("--date", "-d", metavar="YYYY-MM-DD")

    add("show", cmd_show, "view one entry with its links and backlinks").add_argument("id", type=int)

    sp = add("list", cmd_list, "list entries, newest first")
    _add_filters(sp)
    sp = add("search", cmd_search, "find entries containing every word of TEXT")
    sp.add_argument("text", nargs="?", default="")
    _add_filters(sp)

    sp = add("tag", cmd_tag, "add tags to an entry")
    sp.add_argument("id", type=int)
    sp.add_argument("tags", nargs="+")
    sp = add("untag", cmd_untag, "remove tags from an entry")
    sp.add_argument("id", type=int)
    sp.add_argument("tags", nargs="+")
    add("tags", cmd_tags, "list all tags with counts")

    for name, fn, h in (("link", cmd_link, "link entry SRC to entry DST"),
                        ("unlink", cmd_unlink, "remove the link SRC -> DST")):
        sp = add(name, fn, h)
        sp.add_argument("src", type=int)
        sp.add_argument("dst", type=int)
    sp = add("graph", cmd_graph, "show entries reachable through links")
    sp.add_argument("id", type=int)
    sp.add_argument("--depth", type=int, default=model.DEFAULT_GRAPH_DEPTH,
                    help=f"hops, 1-{model.MAX_GRAPH_DEPTH} (default {model.DEFAULT_GRAPH_DEPTH})")
    sp = add("path", cmd_path, "shortest chain of links between two entries")
    sp.add_argument("src", type=int)
    sp.add_argument("dst", type=int)

    sp = add("history", cmd_history, f"earlier versions of an entry (last {model.MAX_REVISIONS} kept)")
    sp.add_argument("id", type=int)
    sp.add_argument("--rev", type=int, help="print one revision in full")
    sp = add("revert", cmd_revert, "restore an earlier version (current text goes to history)")
    sp.add_argument("id", type=int)
    sp.add_argument("rev", type=int)

    add("archive", cmd_archive, "hide an entry from default lists (reversible)").add_argument("id", type=int)
    add("unarchive", cmd_unarchive, "bring an archived entry back").add_argument("id", type=int)
    sp = add("delete", cmd_delete, "permanently delete an entry (asks for confirmation)")
    sp.add_argument("id", type=int)
    sp.add_argument("--yes", action="store_true", help="skip the confirmation prompt")

    sp = add("export", cmd_export, "write journal.json + Markdown files to a new or empty directory")
    sp.add_argument("dir")
    sp.add_argument("--active-only", action="store_true", help="leave out archived entries")
    sp = add("import", cmd_import, "merge a journal.json (or an export directory) into this journal")
    sp.add_argument("path")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with Journal.open(args.db) as journal:
            args.fn(journal, args)
    except JournalError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except OSError as err:
        print(f"error: {err.strerror or err}: {err.filename or ''}".rstrip(": "), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\ncancelled", file=sys.stderr)
        return 1
    return 0
