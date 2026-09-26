"""Bounds, value types, and input validators. Pure: no I/O.

Every bound in the system is defined here (Contracts G6). Callers validate
through these functions and never re-implement a check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

MAX_TITLE_LEN = 200
MAX_BODY_LEN = 1_000_000
MAX_TAGS_PER_ENTRY = 20
MAX_LINKS_PER_ENTRY = 100
MAX_REVISIONS = 20
MAX_GRAPH_DEPTH = 5
DEFAULT_GRAPH_DEPTH = 2
DEFAULT_LIMIT = 50
MAX_LIMIT = 1000
MAX_IMPORT_BYTES = 64 * 1024 * 1024

TAG_PATTERN = re.compile(r"[a-z0-9][a-z0-9_/-]{0,39}")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class JournalError(Exception):
    """Base for errors the CLI reports as `error: ...` with exit code 1."""


class ValidationError(JournalError):
    pass


class NotFound(JournalError):
    pass


class Conflict(JournalError):
    pass


@dataclass
class Entry:
    id: int
    uuid: str
    title: str
    body: str
    entry_date: str
    created_at: str
    updated_at: str
    archived_at: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


@dataclass
class Revision:
    rev: int
    title: str
    body: str
    entry_date: str
    saved_at: str


@dataclass
class EntryRef:
    """A lightweight pointer to an entry, used for links and graph results."""
    id: int
    uuid: str
    title: str
    entry_date: str
    archived: bool


@dataclass
class Query:
    words: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    scope: str = "active"  # active | archived | all
    limit: int = DEFAULT_LIMIT


SCOPES = ("active", "archived", "all")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return date.today().isoformat()


def validate_title(title: object) -> str:
    if not isinstance(title, str):
        raise ValidationError("title: must be text")
    title = title.strip()
    if not title:
        raise ValidationError("title: must not be empty")
    if len(title) > MAX_TITLE_LEN:
        raise ValidationError(f"title: longer than {MAX_TITLE_LEN} characters")
    if "\n" in title or "\r" in title:
        raise ValidationError("title: must be a single line")
    return title


def validate_body(body: object) -> str:
    if not isinstance(body, str):
        raise ValidationError("body: must be text")
    if len(body) > MAX_BODY_LEN:
        raise ValidationError(f"body: longer than {MAX_BODY_LEN} characters")
    if "\x00" in body:
        raise ValidationError("body: contains a NUL character")
    return body


def validate_date(value: object, what: str = "date") -> str:
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        raise ValidationError(f"{what}: expected YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{what}: not a real calendar date") from None
    return value


def validate_timestamp(value: object, what: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise ValidationError(f"{what}: expected YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValidationError(f"{what}: not a real timestamp") from None
    return value


def validate_uuid(value: object) -> str:
    if not isinstance(value, str) or not UUID_PATTERN.fullmatch(value):
        raise ValidationError("uuid: expected a lowercase UUID")
    return value


def normalize_tag(raw: object) -> str:
    """The one place tags are normalized (Contracts: optional-looking invariants)."""
    if not isinstance(raw, str):
        raise ValidationError("tag: must be text")
    tag = raw.strip().lstrip("#").lower()
    if not TAG_PATTERN.fullmatch(tag):
        raise ValidationError(
            f"tag {raw!r}: use 1-40 of a-z 0-9 _ / -, starting with a letter or digit")
    return tag


def normalize_tags(raw: list[object]) -> list[str]:
    out: list[str] = []
    for r in raw:
        t = normalize_tag(r)
        if t not in out:
            out.append(t)
    if len(out) > MAX_TAGS_PER_ENTRY:
        raise ValidationError(f"tags: more than {MAX_TAGS_PER_ENTRY} on one entry")
    return out


def validate_depth(depth: object) -> int:
    if not isinstance(depth, int) or not 1 <= depth <= MAX_GRAPH_DEPTH:
        raise ValidationError(f"depth: must be 1-{MAX_GRAPH_DEPTH}")
    return depth


def validate_query(words: list[str], tags: list[str], date_from: str | None,
                   date_to: str | None, scope: str, limit: int) -> Query:
    if scope not in SCOPES:
        raise ValidationError(f"scope: must be one of {', '.join(SCOPES)}")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValidationError(f"limit: must be 1-{MAX_LIMIT}")
    if date_from is not None:
        validate_date(date_from, "from")
    if date_to is not None:
        validate_date(date_to, "to")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("from: is after to")
    clean_words = [w for w in (w.strip() for w in words) if w]
    return Query(words=clean_words, tags=normalize_tags(list(tags)), date_from=date_from,
                 date_to=date_to, scope=scope, limit=limit)
