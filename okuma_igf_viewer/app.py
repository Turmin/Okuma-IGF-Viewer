"""Application start-up."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from . import APP_NAME, ORGANIZATION, __version__, icons, theme
from .settings import Preferences
from .ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(ORGANIZATION)

    preferences = Preferences()
    theme.apply(app, preferences.theme)
    app.setWindowIcon(icons.app_icon())

    window = MainWindow(preferences)
    if "--smoke-test" in app.arguments():
        # Used by the build workflow: start, show the window briefly and exit.
        window.show()
        QTimer.singleShot(500, app.quit)
        return app.exec()
    if window.has_saved_geometry():
        window.show()
    else:
        window.showMaximized()
    return app.exec()
