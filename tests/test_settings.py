import configparser

from PyQt6.QtCore import QSettings

from okuma_igf_viewer.settings import DEFAULT_PDF_PATH, Preferences, SourceFolders


def test_missing_config_gives_defaults(tmp_path):
    folders = SourceFolders.load(tmp_path / "conf.ini")

    assert folders.igf == ""
    assert folders.pdf == DEFAULT_PDF_PATH


def test_save_keeps_other_sections_and_round_trips(tmp_path):
    file = tmp_path / "conf.ini"
    file.write_text("[DEFAULT]\nigfbackuppath = C:/Old\n\n[SETTINGS]\nnumberofcolumns = 10\n")

    folders = SourceFolders.load(file)
    assert folders.igf == "C:/Old"
    folders.igf = "C:/Backup 2026-01-01"
    folders.save(file)

    assert SourceFolders.load(file).igf == "C:/Backup 2026-01-01"
    parser = configparser.ConfigParser()
    parser.read(file)
    assert parser["SETTINGS"]["numberofcolumns"] == "10"


def test_preferences_clamp_thumbnail_size_and_reject_unknown_theme(tmp_path):
    store = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    preferences = Preferences(store)

    preferences.thumbnail_size = 5000
    assert preferences.thumbnail_size == Preferences.THUMBNAIL_MAX
    store.setValue("view/theme", "neon")
    assert preferences.theme == "dark"
