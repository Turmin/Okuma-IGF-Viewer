"""Builds the database by scanning the IGF backup, PDF and thumbnail folders."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from . import database

# A drawing number is the first run of at least seven digits in a file name.
DRAWING_NUMBER = re.compile(r"\d{7,}")

IGF_SUFFIX = ".pda"
PDF_SUFFIX = ".pdf"
THUMBNAIL_SUFFIX = ".jpg"

ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


class Cancelled(Exception):
    """Raised when the user stops a running update."""


@dataclass(frozen=True)
class Summary:
    igf: int
    pdf: int
    thumbnails: int


def find_files(root: str | Path, suffix: str, cancelled: CancelCheck | None = None) -> Iterator[Path]:
    """Yield every file below root with the given suffix (case-insensitive)."""
    suffix = suffix.casefold()
    for folder, _, filenames in os.walk(root):
        if cancelled is not None and cancelled():
            raise Cancelled
        for filename in filenames:
            if filename.casefold().endswith(suffix):
                yield Path(folder) / filename


def drawing_number(filename: str) -> str | None:
    match = DRAWING_NUMBER.search(filename)
    return match.group() if match else None


def _document_rows(root, suffix, cancelled) -> Iterator[tuple[str, str, str, str]]:
    for file in find_files(root, suffix, cancelled):
        number = drawing_number(file.name)
        if number is not None:
            yield file.name, file.stem, number, str(file.parent)


def _igf_rows(root, cancelled) -> Iterator[tuple[str, str, str, str, str, str | None]]:
    for file in find_files(root, IGF_SUFFIX, cancelled):
        number = drawing_number(file.name)
        if number is None:
            continue
        try:
            modified = datetime.fromtimestamp(file.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            modified = None
        # The category is the folder the program is stored in.
        yield file.name, file.stem, number, str(file.parent), file.parent.name, modified


def _insert(connection: sqlite3.Connection, statement: str, rows: Iterator[tuple]) -> int:
    count = 0
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= 5000:
            connection.executemany(statement, batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.executemany(statement, batch)
        count += len(batch)
    return count


def rebuild(
    database_file: Path,
    igf_folder: str,
    pdf_folder: str,
    thumbnail_folder: str,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> Summary:
    """Scan the three folders into a new database and swap it in when it is complete.

    The current database stays in use until the new one is finished. The previous
    database is kept as '<name>.backup<suffix>'.
    """
    database_file = Path(database_file)
    report = progress or (lambda message: None)
    new_file = database_file.with_name(database_file.name + ".new")
    new_file.unlink(missing_ok=True)

    try:
        with closing(database.connect(new_file)) as connection:
            database.create_schema(connection)

            report("Scanning IGF programs…")
            igf = _insert(
                connection,
                "INSERT INTO igf (filename, basename, mm, path, cat, modified) VALUES (?, ?, ?, ?, ?, ?)",
                _igf_rows(igf_folder, cancelled),
            )
            report(f"{igf} IGF programs found.")

            report("Scanning PDF files…")
            pdf = _insert(
                connection,
                "INSERT INTO pdf (filename, basename, mm, path) VALUES (?, ?, ?, ?)",
                _document_rows(pdf_folder, PDF_SUFFIX, cancelled),
            )
            report(f"{pdf} PDF files found.")

            report("Scanning thumbnails…")
            thumbnails = _insert(
                connection,
                "INSERT INTO thumbs (filename, basename, mm, path) VALUES (?, ?, ?, ?)",
                _document_rows(thumbnail_folder, THUMBNAIL_SUFFIX, cancelled),
            )
            report(f"{thumbnails} thumbnails found.")

            connection.execute(
                "INSERT INTO info (last_updated, folder) VALUES (?, ?)",
                (datetime.now().isoformat(), Path(igf_folder).name),
            )
            report("Building search indexes…")
            database.create_indexes(connection)
            connection.commit()
    except BaseException:
        new_file.unlink(missing_ok=True)
        raise

    if database_file.exists():
        backup = database_file.with_name(f"{database_file.stem}.backup{database_file.suffix}")
        os.replace(database_file, backup)
    os.replace(new_file, database_file)
    return Summary(igf=igf, pdf=pdf, thumbnails=thumbnails)
