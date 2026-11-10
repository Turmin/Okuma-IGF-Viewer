from contextlib import closing

import pytest

from okuma_igf_viewer import database, indexer, metadata


@pytest.fixture
def files(tmp_path, source_folders):
    igf, pdf, thumbnails = source_folders
    target = tmp_path / "sqlite.db"
    indexer.rebuild(target, str(igf), str(pdf), str(thumbnails))
    return target, tmp_path / "metadata.db"


def search(files, text):
    database_file, metadata_file = files
    with closing(database.connect(database_file, readonly=True, metadata_file=metadata_file)) as connection:
        return [item.name for item in database.search_items(connection, text)]


def test_parse_tags_trims_splits_and_drops_duplicates():
    assert metadata.parse_tags(" Shaft, steel;M12\nshaft ,, ") == ("Shaft", "steel", "M12")
    assert metadata.parse_tags("") == ()


def test_save_and_load_round_trip_and_empty_details_remove_the_entry(tmp_path):
    file = tmp_path / "metadata.db"
    details = metadata.Details("  Drive  shaft ", "Turn first.\n", ("steel", "Steel", "M12"))

    saved = metadata.save(file, "10227615", details)

    assert saved == metadata.Details("Drive shaft", "Turn first.", ("steel", "M12"))
    assert metadata.load(file, "10227615") == saved
    assert metadata.load(file, "99999999") == metadata.Details()

    metadata.save(file, "10227615", metadata.Details())
    assert metadata.load(file, "10227615").is_empty()


def test_items_carry_their_details(files):
    database_file, metadata_file = files
    metadata.save(metadata_file, "10227615", metadata.Details("Drive shaft", "Steel, 40 mm", ("shaft", "steel")))

    with closing(database.connect(database_file, readonly=True, metadata_file=metadata_file)) as connection:
        with_details, without = database.items_in_category(connection, "AS-30")

    assert (with_details.title, with_details.description, with_details.tags) == (
        "Drive shaft",
        "Steel, 40 mm",
        ("shaft", "steel"),
    )
    assert with_details.label == "Drive shaft" and with_details.has_details
    assert without.label == without.name and not without.has_details


def test_search_finds_title_tags_and_description_and_needs_every_word(files):
    _, metadata_file = files
    metadata.save(metadata_file, "10227615", metadata.Details("Drive shaft", "Hardened steel", ("long", "M12")))
    metadata.save(metadata_file, "10230001", metadata.Details("Bushing", "", ("steel",)))

    assert search(files, "shaft") == ["A16-10227615-OAL"]
    assert search(files, "m12") == ["A16-10227615-OAL"]
    assert search(files, "hardened") == ["A16-10227615-OAL"]
    assert search(files, "steel") == ["A16-10227615-OAL", "B20-10230001-OAL"]
    assert search(files, "steel drive") == ["A16-10227615-OAL"]
    assert search(files, "steel nothing") == []
    assert search(files, "10230001") == ["B20-10230001-OAL"]
    assert search(files, "   ") == []
    assert search(files, "%") == []


def test_details_survive_a_database_update(files, source_folders):
    database_file, metadata_file = files
    metadata.save(metadata_file, "10227615", metadata.Details("Drive shaft"))
    igf, pdf, thumbnails = source_folders

    indexer.rebuild(database_file, str(igf), str(pdf), str(thumbnails))

    assert search(files, "drive") == ["A16-10227615-OAL"]


def test_search_works_without_a_metadata_file(files):
    assert search(files, "10227615") == ["A16-10227615-OAL"]
