# Resonance Journal (resonance-journal-rerun)
# Copyright (C) 2026 Samuel Jackson Grim
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# A commercial license is also available: see LICENSING.md.
"""Export to JSON + navigable Markdown, and import JSON back (Contracts G3, G4, G5).

The only storage access is through the Journal API; this module has no SQL.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import model
from .journal import Journal
from .model import Conflict, ValidationError

FORMAT_NAME = "resonance-journal"
FORMAT_VERSION = 1
JSON_NAME = "journal.json"
INDEX_NAME = "index.md"
ENTRIES_DIR = "entries"


# --- export -----------------------------------------------------------------

def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return s or "entry"


def entry_filename(rec: dict) -> str:
    return f"{rec['date']}-{_slug(rec['title'])}-{rec['uuid'][:8]}.md"


def _md_text(text: str) -> str:
    """Escape characters that would break a Markdown link label."""
    return re.sub(r"([\\\[\]])", r"\\\1", text)


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _entry_markdown(rec: dict, by_uuid: dict[str, dict], exported: set[str],
                    backlinks: list[str]) -> str:
    def link_line(target_uuid: str) -> str:
        t = by_uuid[target_uuid]
        label = f"{_md_text(t['title'])} ({t['date']})"
        if target_uuid in exported:
            return f"- [{label}]({entry_filename(t)})"
        return f"- {label} — not in this export (archived)"

    lines = [
        "---",
        f"uuid: {rec['uuid']}",
        f"title: {json.dumps(rec['title'], ensure_ascii=False)}",
        f"date: {rec['date']}",
        f"created: {rec['created_at']}",
        f"updated: {rec['updated_at']}",
        f"archived: {rec['archived_at'] or 'false'}",
        f"tags: [{', '.join(rec['tags'])}]",
        "---",
        "",
        f"# {rec['title']}",
        "",
        f"*{rec['date']}*" + ("  ·  **archived**" if rec["archived_at"] else "")
        + (f"  ·  {' '.join('#' + t for t in rec['tags'])}" if rec["tags"] else ""),
        "",
        rec["body"].rstrip("\n"),
        "",
    ]
    if rec["links"]:
        lines += ["## Links", ""] + [link_line(u) for u in rec["links"]] + [""]
    if backlinks:
        lines += ["## Backlinks", ""] + [link_line(u) for u in backlinks] + [""]
    lines += [f"[← Index](../{INDEX_NAME})", ""]
    return "\n".join(lines)


def _index_markdown(records: list[dict], exported_at: str) -> str:
    lines = ["# Resonance Journal", "", f"Exported {exported_at} · {len(records)} entries", ""]
    for rec in sorted(records, key=lambda r: (r["date"], r["uuid"]), reverse=True):
        tags = f" — {' '.join('#' + t for t in rec['tags'])}" if rec["tags"] else ""
        arch = " *(archived)*" if rec["archived_at"] else ""
        lines.append(f"- {rec['date']} · [{_md_text(rec['title'])}]"
                     f"({ENTRIES_DIR}/{entry_filename(rec)}){arch}{tags}")
    tag_count: dict[str, int] = {}
    for rec in records:
        for t in rec["tags"]:
            tag_count[t] = tag_count.get(t, 0) + 1
    if tag_count:
        lines += ["", "## Tags", ""]
        lines += [f"- #{t} ({n})" for t, n in sorted(tag_count.items())]
    lines.append("")
    return "\n".join(lines)


def export_journal(journal: Journal, target: Path | str, active_only: bool = False) -> dict:
    target = Path(target).expanduser()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise Conflict(f"export: {target} exists and is not an empty directory")
    records = journal.dump()
    by_uuid = {r["uuid"]: r for r in records}
    chosen = [r for r in records if not (active_only and r["archived_at"])]
    exported = {r["uuid"] for r in chosen}

    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target, 0o700)
    (target / ENTRIES_DIR).mkdir(mode=0o700)

    exported_at = model.now_utc()
    doc = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": exported_at,
        "entries": [
            {k: v for k, v in r.items() if k != "id"} | {"links": [u for u in r["links"]
                                                                  if u in exported]}
            for r in chosen
        ],
    }
    _write_private(target / JSON_NAME, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    backlinks: dict[str, list[str]] = {u: [] for u in by_uuid}
    for r in records:
        for dst in r["links"]:
            backlinks[dst].append(r["uuid"])
    for r in chosen:
        _write_private(target / ENTRIES_DIR / entry_filename(r),
                       _entry_markdown(r, by_uuid, exported, backlinks[r["uuid"]]))
    _write_private(target / INDEX_NAME, _index_markdown(chosen, exported_at))
    return {"entries": len(chosen), "path": str(target)}


# --- import -----------------------------------------------------------------

def _fail(where: str, err: Exception) -> ValidationError:
    return ValidationError(f"import: {where}: {err}")


def _validate_revisions(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        raise ValidationError("revisions: must be a list")
    if len(raw) > model.MAX_REVISIONS:
        raise ValidationError(f"revisions: more than {model.MAX_REVISIONS}")
    out, seen = [], set()
    for r in raw:
        if not isinstance(r, dict):
            raise ValidationError("revisions: each must be an object")
        rev = r.get("rev")
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1 or rev in seen:
            raise ValidationError("revisions: rev must be a unique positive integer")
        seen.add(rev)
        out.append({"rev": rev, "title": model.validate_title(r.get("title")),
                     "body": model.validate_body(r.get("body")),
                     "date": model.validate_date(r.get("date")),
                     "saved_at": model.validate_timestamp(r.get("saved_at"), "saved_at")})
    return out


def validate_document(doc: object) -> list[dict]:
    """Validate a whole import document before any write (Contracts G10)."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT_NAME:
        raise ValidationError(f"import: not a {FORMAT_NAME} export")
    if doc.get("version") != FORMAT_VERSION:
        raise ValidationError(f"import: unsupported format version {doc.get('version')!r}")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise ValidationError("import: entries must be a list")
    records, uuids = [], set()
    for i, e in enumerate(entries):
        where = f"entry #{i}"
        try:
            if not isinstance(e, dict):
                raise ValidationError("must be an object")
            uid = model.validate_uuid(e.get("uuid"))
            if uid in uuids:
                raise ValidationError("uuid: duplicated in file")
            uuids.add(uid)
            links = e.get("links", [])
            if not isinstance(links, list) or len(links) > model.MAX_LINKS_PER_ENTRY:
                raise ValidationError(f"links: must be a list of at most "
                                      f"{model.MAX_LINKS_PER_ENTRY} UUIDs")
            archived_at = e.get("archived_at")
            records.append({
                "uuid": uid,
                "title": model.validate_title(e.get("title")),
                "body": model.validate_body(e.get("body")),
                "date": model.validate_date(e.get("date")),
                "created_at": model.validate_timestamp(e.get("created_at"), "created_at"),
                "updated_at": model.validate_timestamp(e.get("updated_at"), "updated_at"),
                "archived_at": None if archived_at is None
                else model.validate_timestamp(archived_at, "archived_at"),
                "tags": model.normalize_tags(e.get("tags", []) if isinstance(e.get("tags", []), list)
                                             else [None]),
                "links": list(dict.fromkeys(model.validate_uuid(u) for u in links)),
                "revisions": _validate_revisions(e.get("revisions", [])),
            })
        except ValidationError as err:
            raise _fail(where, err) from None
    return records


def import_journal(journal: Journal, source: Path | str) -> dict[str, int]:
    source = Path(source).expanduser()
    if source.is_dir():
        source = source / JSON_NAME
    if not source.is_file():
        raise ValidationError(f"import: {source} is not a file")
    if source.stat().st_size > model.MAX_IMPORT_BYTES:
        raise ValidationError(f"import: file larger than {model.MAX_IMPORT_BYTES} bytes")
    try:
        doc = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValidationError(f"import: not valid UTF-8 JSON ({type(err).__name__})") from None
    return journal.merge(validate_document(doc))
