"""SQLite access: schema, queries for the viewer and helpers for the indexer."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS igf (
        id INTEGER PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        basename VARCHAR(255) NOT NULL,
        mm VARCHAR(255) NOT NULL,
        path VARCHAR(255) NOT NULL,
        cat VARCHAR(255) NOT NULL,
        modified DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS pdf (
        id INTEGER PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        basename VARCHAR(255) NOT NULL,
        mm VARCHAR(255) NOT NULL,
        path VARCHAR(255) NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS thumbs (
        id INTEGER PRIMARY KEY,
        filename VARCHAR(255) NOT NULL,
        basename VARCHAR(255) NOT NULL,
        mm VARCHAR(255) NOT NULL,
        path VARCHAR(255) NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS info (
        id INTEGER PRIMARY KEY,
        last_updated DATETIME NOT NULL,
        folder VARCHAR(255) NOT NULL
    )""",
)

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_igf_cat ON igf (cat)",
    "CREATE INDEX IF NOT EXISTS idx_igf_mm ON igf (mm)",
    "CREATE INDEX IF NOT EXISTS idx_pdf_mm ON pdf (mm)",
    "CREATE INDEX IF NOT EXISTS idx_thumbs_mm ON thumbs (mm)",
)

_ITEM_QUERY = """
    SELECT
        igf.basename, igf.filename, igf.path, igf.mm, igf.cat, igf.modified,
        pdf.path, pdf.filename, thumbs.path, thumbs.filename
    FROM igf
    LEFT JOIN pdf ON igf.mm = pdf.mm
    LEFT JOIN thumbs ON igf.mm = thumbs.mm
    WHERE {where}
    GROUP BY igf.cat, igf.mm
    ORDER BY igf.basename COLLATE NOCASE
"""


@dataclass(frozen=True)
class Item:
    """One IGF program (drawing number) with the PDF and thumbnail that belong to it."""

    name: str
    igf_file: str
    drawing_number: str
    category: str
    modified: str | None
    pdf: str | None
    thumbnail: str | None


@dataclass(frozen=True)
class DatabaseInfo:
    last_updated: datetime | None
    folder: str


def _join(path: str | None, filename: str | None) -> str | None:
    if not path or not filename:
        return None
    return os.path.join(path, filename)


def connect(file: Path, *, readonly: bool = False) -> sqlite3.Connection:
    """Open the database. Raises FileNotFoundError when a read-only database is missing."""
    if readonly:
        if not Path(file).is_file():
            raise FileNotFoundError(file)
        return sqlite3.connect(f"{Path(file).as_uri()}?mode=ro", uri=True)
    return sqlite3.connect(file)


def create_schema(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        connection.execute(statement)


def create_indexes(connection: sqlite3.Connection) -> None:
    for statement in INDEXES:
        connection.execute(statement)
    connection.commit()


def ensure_indexes(file: Path) -> bool:
    """Add the lookup indexes to a database made by an older version. False when not possible."""
    try:
        with closing(connect(file)) as connection:
            existing = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
            }
            if all(statement.split()[5] in existing for statement in INDEXES):
                return True
            create_indexes(connection)
        return True
    except sqlite3.Error:
        return False


def categories(connection: sqlite3.Connection) -> list[tuple[str, int]]:
    """Every category with its number of drawing numbers."""
    rows = connection.execute(
        "SELECT cat, COUNT(DISTINCT mm) FROM igf GROUP BY cat ORDER BY cat COLLATE NOCASE"
    )
    return [(str(category), int(count)) for category, count in rows]


def _items(connection: sqlite3.Connection, where: str, parameters: tuple) -> list[Item]:
    rows = connection.execute(_ITEM_QUERY.format(where=where), parameters)
    return [
        Item(
            name=name,
            igf_file=_join(igf_path, igf_filename) or "",
            drawing_number=mm,
            category=category,
            modified=modified,
            pdf=_join(pdf_path, pdf_filename),
            thumbnail=_join(thumb_path, thumb_filename),
        )
        for (name, igf_filename, igf_path, mm, category, modified,
             pdf_path, pdf_filename, thumb_path, thumb_filename) in rows
    ]


def items_in_category(connection: sqlite3.Connection, category: str) -> list[Item]:
    return _items(connection, "igf.cat = ?", (category,))


def search_items(connection: sqlite3.Connection, text: str) -> list[Item]:
    """Programs in any category whose name or drawing number contains the text."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return _items(
        connection,
        "(igf.basename LIKE ? ESCAPE '\\' OR igf.mm LIKE ? ESCAPE '\\')",
        (pattern, pattern),
    )


def info(connection: sqlite3.Connection) -> DatabaseInfo | None:
    try:
        row = connection.execute(
            "SELECT last_updated, folder FROM info ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        last_updated = datetime.fromisoformat(row[0])
    except (TypeError, ValueError):
        last_updated = None
    return DatabaseInfo(last_updated=last_updated, folder=str(row[1] or ""))


def table_names(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in rows]
