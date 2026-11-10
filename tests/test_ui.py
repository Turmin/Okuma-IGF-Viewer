"""Smoke tests for the windows, run without a display."""

import pytest
from PyQt6.QtCore import QEventLoop, QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from okuma_igf_viewer import indexer, theme
from okuma_igf_viewer.settings import Preferences
from okuma_igf_viewer.ui.thumbnail_grid import card_size


def wait_until(condition, timeout_ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: loop.quit() if condition() else None)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    assert condition()


@pytest.fixture(scope="session")
def app():
    app = QApplication.instance() or QApplication([])
    theme.apply(app, "dark")
    return app


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OKUMA_IGF_VIEWER_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def preferences(tmp_path):
    return Preferences(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat))


def test_main_window_without_database_offers_update(app, home, preferences):
    from okuma_igf_viewer.ui.main_window import MainWindow

    window = MainWindow(preferences)

    assert window._stack.currentIndex() == 1
    assert window._empty_title.text() == "No database yet"
    assert not window._viewer_action.isEnabled()
    window.close()


def test_main_window_lists_categories_searches_and_scales(app, home, preferences, source_folders):
    from okuma_igf_viewer.ui.main_window import MainWindow

    igf, pdf, thumbnails = source_folders
    indexer.rebuild(home / "sqlite.db", str(igf), str(pdf), str(thumbnails))

    window = MainWindow(preferences)
    window.resize(1200, 800)
    window.show()
    assert [window._categories.item(row).text() for row in range(2)] == ["AS-30   (2)", "AS-40   (1)"]
    wait_until(lambda: window._model.rowCount() == 2)

    window._search.setText("0003650")
    wait_until(lambda: [item.name for item in window._model.items()] == ["D0003650-OAL"])

    window._set_thumbnail_size(320)
    assert preferences.thumbnail_size == 320
    assert window._grid.gridSize().width() >= card_size(320).width()
    window.close()


def test_database_viewer_filters_rows(app, home, source_folders):
    from okuma_igf_viewer.ui.database_viewer import DatabaseViewer

    igf, pdf, thumbnails = source_folders
    indexer.rebuild(home / "sqlite.db", str(igf), str(pdf), str(thumbnails))

    viewer = DatabaseViewer(home / "sqlite.db")
    assert viewer._model.total() == 3
    viewer._filter.setText("AS-40")
    viewer._reload()
    assert viewer._model.total() == 1
    viewer.close()


def test_update_window_rebuilds_database_and_reports(app, home, source_folders):
    from okuma_igf_viewer.ui.update_window import UpdateWindow

    igf, pdf, thumbnails = source_folders
    window = UpdateWindow()
    updated = []
    window.databaseUpdated.connect(lambda: updated.append(True))

    window._edits["igf"].setText(str(igf / "missing"))
    window._start_or_cancel()
    assert not window.is_running()
    assert "does not exist" in window._log.toPlainText()

    for field, folder in (("igf", igf), ("pdf", pdf), ("thumbnail", thumbnails)):
        window._edits[field].setText(str(folder))
    window._start_or_cancel()
    wait_until(lambda: bool(updated) and not window.is_running())

    assert (home / "sqlite.db").is_file()
    assert "Done: 3 IGF programs, 1 PDF files and 2 thumbnails." in window._log.toPlainText()
    assert "Backup 2026-01-01" in (home / "conf.ini").read_text()
    window.close()
