"""Locations of the files the application works with."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running as a PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder that holds conf.ini and the database.

    Next to the executable, or the project root when running from source. The
    OKUMA_IGF_VIEWER_HOME environment variable overrides both.
    """
    override = os.environ.get("OKUMA_IGF_VIEWER_HOME")
    if override:
        return Path(override)
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parent


def assets_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", PACKAGE_DIR)) / "okuma_igf_viewer" / "assets"
    return PACKAGE_DIR / "assets"


def config_file() -> Path:
    return app_dir() / "conf.ini"


def database_file() -> Path:
    return app_dir() / "sqlite.db"


def metadata_file() -> Path:
    """Titles, tags and descriptions; kept apart so a database update never removes them."""
    return app_dir() / "metadata.db"
