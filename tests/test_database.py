import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from okuma_igf_viewer import database, indexer


@pytest.fixture
def connection(tmp_path, source_folders):
    igf, pdf, thumbnails = source_folders
    target = tmp_path / "sqlite.db"
    indexer.rebuild(target, str(igf), str(pdf), str(thumbnails))
    with closing(database.connect(target, readonly=True)) as connection:
        yield connection


def test_items_in_category_link_pdf_and_thumbnail(connection):
    items = database.items_in_category(connection, "AS-30")

    assert [item.name for item in items] == ["A16-10227615-OAL", "B20-10230001-OAL"]
    with_files, without_files = items
    assert Path(with_files.pdf).name == "10227615.pdf"
    assert Path(with_files.thumbnail).name == "10227615.JPG"
    assert Path(with_files.igf_file).name == "A16-10227615-OAL.PDA"
    assert without_files.pdf is None and without_files.thumbnail is None


def test_search_covers_all_categories_and_treats_wildcards_literally(connection):
    assert [item.category for item in database.search_items(connection, "oal")] == ["AS-30", "AS-30", "AS-40"]
    assert [item.name for item in database.search_items(connection, "0003650")] == ["D0003650-OAL"]
    assert database.search_items(connection, "%") == []
    assert database.search_items(connection, "_") == []


def test_readonly_connection_requires_existing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        database.connect(tmp_path / "missing.db", readonly=True)


def test_ensure_indexes_upgrades_database_from_older_version(tmp_path):
    file = tmp_path / "old.db"
    with closing(sqlite3.connect(file)) as old:
        database.create_schema(old)
        old.commit()

    assert database.ensure_indexes(file) is True

    with closing(sqlite3.connect(file)) as upgraded:
        names = {row[0] for row in upgraded.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_thumbs_mm" in names


def test_info_is_none_without_info_table(tmp_path):
    with closing(sqlite3.connect(tmp_path / "empty.db")) as empty:
        assert database.info(empty) is None
