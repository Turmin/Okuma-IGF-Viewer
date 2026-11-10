"""Titles, tags and descriptions that people add to a drawing number.

They live in their own file (metadata.db) next to the database, so updating the database
from the IGF backup never touches them. They belong to the drawing number, so a program
that is stored in several categories shows the same details everywhere.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """CREATE TABLE IF NOT EXISTS metadata (
    mm VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    updated DATETIME
)"""

ALIAS = "meta"
_TAG_SEPARATOR = re.compile(r"[,;\n]")


@dataclass(frozen=True)
class Details:
    title: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.title or self.description or self.tags)


def parse_tags(text: str) -> tuple[str, ...]:
    """Split on commas, semicolons or new lines; trim, and drop duplicates regardless of case."""
    seen: dict[str, str] = {}
    for part in _TAG_SEPARATOR.split(text or ""):
        tag = " ".join(part.split())
        if tag:
            seen.setdefault(tag.casefold(), tag)
    return tuple(seen.values())


def format_tags(tags: tuple[str, ...] | list[str]) -> str:
    return ", ".join(tags)


def clean(details: Details) -> Details:
    return Details(
        title=" ".join(details.title.split()),
        description=details.description.strip(),
        tags=parse_tags(format_tags(details.tags)),
    )


def attach(connection: sqlite3.Connection, file: Path | None) -> None:
    """Make the metadata available to queries on `connection` as meta.metadata.

    Without a metadata file an empty in-memory table is used, so queries work the same.
    """
    if file is not None and Path(file).is_file():
        connection.execute(f"ATTACH DATABASE ? AS {ALIAS}", (f"{Path(file).as_uri()}?mode=ro",))
    else:
        connection.execute(f"ATTACH DATABASE ':memory:' AS {ALIAS}")
        connection.execute(SCHEMA.replace("metadata", f"{ALIAS}.metadata", 1))


def load(file: Path, drawing_number: str) -> Details:
    if not Path(file).is_file():
        return Details()
    with closing(sqlite3.connect(file)) as connection:
        row = connection.execute(
            "SELECT title, description, tags FROM metadata WHERE mm = ?", (drawing_number,)
        ).fetchone()
    if row is None:
        return Details()
    return Details(title=row[0], description=row[1], tags=parse_tags(row[2]))


def save(file: Path, drawing_number: str, details: Details) -> Details:
    """Store the details; empty details remove the entry. Returns what was stored."""
    details = clean(details)
    with closing(sqlite3.connect(file, timeout=10)) as connection:
        connection.execute(SCHEMA)
        if details.is_empty():
            connection.execute("DELETE FROM metadata WHERE mm = ?", (drawing_number,))
        else:
            connection.execute(
                "INSERT INTO metadata (mm, title, description, tags, updated) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(mm) DO UPDATE SET title = excluded.title, description = excluded.description, "
                "tags = excluded.tags, updated = excluded.updated",
                (
                    drawing_number,
                    details.title,
                    details.description,
                    format_tags(details.tags),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        connection.commit()
    return details
