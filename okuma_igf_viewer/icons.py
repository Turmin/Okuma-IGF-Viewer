"""SVG icons, tinted to match the active theme."""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from . import theme
from .paths import assets_dir


@lru_cache(maxsize=None)
def _source(name: str) -> str:
    return (assets_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8")


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int) -> QPixmap:
    """Render an icon in the given colour at size x size device pixels."""
    renderer = QSvgRenderer(QByteArray(_source(name).replace("currentColor", color).encode("utf-8")))
    image = QPixmap(size, size)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def icon(name: str, color: str | None = None) -> QIcon:
    """An icon in the theme's text colour (or the given colour), with a muted disabled state."""
    colors = theme.current()
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        result.addPixmap(pixmap(name, color or colors.text, size), QIcon.Mode.Normal)
        result.addPixmap(pixmap(name, colors.text_muted, size), QIcon.Mode.Disabled)
    return result


def app_icon() -> QIcon:
    result = QIcon()
    renderer = QSvgRenderer(str(assets_dir() / "app.svg"))
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QPixmap(QSize(size, size))
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(image)
    return result
