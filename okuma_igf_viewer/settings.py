"""Shared folder settings (conf.ini) and per-user interface preferences (QSettings)."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings

from . import APP_NAME, ORGANIZATION

DEFAULT_PDF_PATH = "//srv-w2012-cad/ME10_data$/data/pdf/code"
DEFAULT_THUMBNAIL_PATH = "//srv-w2012-cad/ME10_data$/data/Thumbnail_3D/code"

_KEYS = {
    "igf": "IGFBackupPath",
    "pdf": "PDFPath",
    "thumbnail": "ThumbnailPath",
}


@dataclass
class SourceFolders:
    """The three folders the database is built from."""

    igf: str = ""
    pdf: str = DEFAULT_PDF_PATH
    thumbnail: str = DEFAULT_THUMBNAIL_PATH

    @classmethod
    def load(cls, file: Path) -> "SourceFolders":
        folders = cls()
        parser = configparser.ConfigParser()
        try:
            parser.read(file, encoding="utf-8")
        except (OSError, configparser.Error):
            return folders
        for field, key in _KEYS.items():
            value = parser["DEFAULT"].get(key, "").strip()
            if value:
                setattr(folders, field, value)
        return folders

    def save(self, file: Path) -> None:
        """Write the folders to conf.ini, keeping anything else that is in the file."""
        parser = configparser.ConfigParser()
        try:
            parser.read(file, encoding="utf-8")
        except (OSError, configparser.Error):
            parser = configparser.ConfigParser()
        for field, key in _KEYS.items():
            parser["DEFAULT"][key] = getattr(self, field)
        with open(file, "w", encoding="utf-8") as handle:
            parser.write(handle)


class Preferences:
    """Per-user interface state: window layout, thumbnail size and theme."""

    THUMBNAIL_MIN = 96
    THUMBNAIL_MAX = 384
    THUMBNAIL_DEFAULT = 176
    THEMES = ("system", "dark", "light")

    def __init__(self, store: QSettings | None = None) -> None:
        self._store = store or QSettings(ORGANIZATION, APP_NAME)

    @property
    def thumbnail_size(self) -> int:
        try:
            size = int(self._store.value("view/thumbnail_size", self.THUMBNAIL_DEFAULT))
        except (TypeError, ValueError):
            size = self.THUMBNAIL_DEFAULT
        return max(self.THUMBNAIL_MIN, min(self.THUMBNAIL_MAX, size))

    @thumbnail_size.setter
    def thumbnail_size(self, size: int) -> None:
        self._store.setValue("view/thumbnail_size", int(size))

    @property
    def theme(self) -> str:
        theme = str(self._store.value("view/theme", "dark"))
        return theme if theme in self.THEMES else "dark"

    @theme.setter
    def theme(self, theme: str) -> None:
        self._store.setValue("view/theme", theme)

    @property
    def last_category(self) -> str:
        return str(self._store.value("view/last_category", ""))

    @last_category.setter
    def last_category(self, category: str) -> None:
        self._store.setValue("view/last_category", category)

    def value(self, key: str):
        return self._store.value(key)

    def set_value(self, key: str, value) -> None:
        self._store.setValue(key, value)
