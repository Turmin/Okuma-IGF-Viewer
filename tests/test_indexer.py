from contextlib import closing

import pytest

from okuma_igf_viewer import database, indexer


def rebuild(target, folders, **kwargs):
    igf, pdf, thumbnails = folders
    return indexer.rebuild(target, str(igf), str(pdf), str(thumbnails), **kwargs)


def test_drawing_number_is_first_run_of_seven_digits():
    assert indexer.drawing_number("A16-10227615-OAL.PDA") == "10227615"
    assert indexer.drawing_number("D0003650-OAL.PDA") == "0003650"
    assert indexer.drawing_number("SHORT-123.PDA") is None


def test_rebuild_indexes_all_three_folders(tmp_path, source_folders):
    target = tmp_path / "sqlite.db"
    messages = []

    summary = rebuild(target, source_folders, progress=messages.append)

    assert summary == indexer.Summary(igf=3, pdf=1, thumbnails=2)
    assert messages[0] == "Scanning IGF programs…"
    with closing(database.connect(target, readonly=True)) as connection:
        assert database.categories(connection) == [("AS-30", 2), ("AS-40", 1)]
        assert database.info(connection).folder == "Backup 2026-01-01"
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_igf_cat", "idx_igf_mm", "idx_pdf_mm", "idx_thumbs_mm"} <= indexes


def test_rebuild_keeps_previous_database_as_backup(tmp_path, source_folders):
    target = tmp_path / "sqlite.db"
    target.write_text("old database")

    rebuild(target, source_folders)

    assert (tmp_path / "sqlite.backup.db").read_text() == "old database"
    assert not (tmp_path / "sqlite.db.new").exists()


def test_cancelled_rebuild_leaves_existing_database_untouched(tmp_path, source_folders):
    target = tmp_path / "sqlite.db"
    target.write_text("old database")

    with pytest.raises(indexer.Cancelled):
        rebuild(target, source_folders, cancelled=lambda: True)

    assert target.read_text() == "old database"
    assert not (tmp_path / "sqlite.db.new").exists()
    assert not (tmp_path / "sqlite.backup.db").exists()
