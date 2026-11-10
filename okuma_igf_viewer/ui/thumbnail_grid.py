"""The grid of program cards: model, background thumbnail loading, painting and view."""

from __future__ import annotations

import dataclasses
from collections import OrderedDict
from enum import Enum
from html import escape

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFontMetrics, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from .. import icons, metadata, theme, thumbnails
from ..database import Item

ITEM_ROLE = Qt.ItemDataRole.UserRole
THUMBNAIL_ROLE = Qt.ItemDataRole.UserRole + 1

# Thumbnails are read at up to READ_EDGE, cleaned up and cropped, and kept at up to DECODE_EDGE.
# They are scaled down further while painting.
READ_EDGE = 1024
DECODE_EDGE = 512
CACHE_LIMIT = 600

CARD_PADDING = 8
FOOTER_HEIGHT = 30
FOOTER_GAP = 8
CARD_GAP = 12
CARD_RADIUS = 10


class Region(Enum):
    NONE = 0
    IMAGE = 1
    FOOTER = 2


class _LoaderSignals(QObject):
    loaded = pyqtSignal(str, QImage)


class _LoadTask(QRunnable):
    def __init__(self, path: str, signals: _LoaderSignals) -> None:
        super().__init__()
        self._path = path
        self._signals = signals

    def run(self) -> None:
        reader = QImageReader(self._path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > READ_EDGE:
            reader.setScaledSize(size.scaled(READ_EDGE, READ_EDGE, Qt.AspectRatioMode.KeepAspectRatio))
        image = thumbnails.tidy(reader.read())
        if max(image.width(), image.height()) > DECODE_EDGE:
            image = image.scaled(
                DECODE_EDGE,
                DECODE_EDGE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        try:
            self._signals.loaded.emit(self._path, image)
        except RuntimeError:
            pass  # the model was destroyed while the image was loading


class ItemModel(QAbstractListModel):
    """The programs shown in the grid. Thumbnails are loaded in the background on demand."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[Item] = []
        self._rows_by_thumbnail: dict[str, list[int]] = {}
        self._cache: OrderedDict[str, QPixmap | None] = OrderedDict()
        self._pending: set[str] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(6)
        self._signals = _LoaderSignals(self)
        self._signals.loaded.connect(self._on_loaded)

    def set_items(self, items: list[Item]) -> None:
        self.beginResetModel()
        self._pool.clear()
        self._pending.clear()
        self._items = list(items)
        self._rows_by_thumbnail = {}
        for row, item in enumerate(self._items):
            if item.thumbnail:
                self._rows_by_thumbnail.setdefault(item.thumbnail, []).append(row)
        self.endResetModel()

    def items(self) -> list[Item]:
        return self._items

    def set_details(self, drawing_number: str, details: metadata.Details) -> None:
        """Show new details on every card with this drawing number."""
        for row, item in enumerate(self._items):
            if item.drawing_number == drawing_number:
                self._items[row] = dataclasses.replace(
                    item, title=details.title, description=details.description, tags=details.tags
                )
                index = self.index(row)
                self.dataChanged.emit(index, index)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == ITEM_ROLE:
            return item
        if role == THUMBNAIL_ROLE:
            return self._thumbnail(item)
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip(item)
        return None

    def thumbnail_state(self, item: Item) -> str:
        """'none' (no thumbnail known), 'loading', 'missing' (could not be read) or 'ready'."""
        if not item.thumbnail:
            return "none"
        if item.thumbnail not in self._cache:
            return "loading"
        return "ready" if self._cache[item.thumbnail] is not None else "missing"

    def _thumbnail(self, item: Item) -> QPixmap | None:
        path = item.thumbnail
        if not path:
            return None
        if path in self._cache:
            self._cache.move_to_end(path)
            return self._cache[path]
        if path not in self._pending:
            self._pending.add(path)
            self._pool.start(_LoadTask(path, self._signals))
        return None

    def _on_loaded(self, path: str, image: QImage) -> None:
        self._pending.discard(path)
        self._cache[path] = None if image.isNull() else QPixmap.fromImage(image)
        self._cache.move_to_end(path)
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)
        for row in self._rows_by_thumbnail.get(path, []):
            index = self.index(row)
            self.dataChanged.emit(index, index, [THUMBNAIL_ROLE])

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(2000)


DESCRIPTION_LIMIT = 400


def tooltip(item: Item) -> str:
    """Rich text shown when hovering a card: title, tags, description and the file details."""
    colors = theme.current()
    muted = f"color:{colors.text_muted}"
    parts = [f"<b style='font-size:11pt'>{escape(item.label)}</b>"]
    if item.title:
        parts.append(f"<span style='{muted}'>{escape(item.name)}</span>")
    if item.tags:
        chips = "&nbsp; ".join(
            f"<span style='color:{colors.accent}'>#{escape(tag)}</span>" for tag in item.tags
        )
        parts.append(chips)
    if item.description:
        text = item.description
        if len(text) > DESCRIPTION_LIMIT:
            text = text[:DESCRIPTION_LIMIT].rstrip() + "…"
        parts.append(escape(text).replace("\n", "<br>"))
    facts = [f"Drawing {escape(item.drawing_number)}", escape(item.category)]
    if item.modified:
        facts.append(f"modified {escape(item.modified[:10])}")
    facts.append("PDF available" if item.pdf else "no PDF")
    parts.append(f"<span style='{muted}'>{' · '.join(facts)}</span>")
    if not item.has_details:
        parts.append(f"<span style='{muted}'>Press F2 to add a title, tags or a description.</span>")
    return f"<div style='max-width:340px'>{'<br>'.join(parts)}</div>"


def card_size(thumbnail_size: int) -> QSize:
    return QSize(
        thumbnail_size + 2 * CARD_PADDING,
        thumbnail_size + 2 * CARD_PADDING + FOOTER_GAP + FOOTER_HEIGHT,
    )


def card_rect(cell: QRect, thumbnail_size: int) -> QRect:
    size = card_size(thumbnail_size)
    return QRect(
        cell.x() + (cell.width() - size.width()) // 2,
        cell.y() + (cell.height() - size.height()) // 2,
        size.width(),
        size.height(),
    )


def image_rect(card: QRect, thumbnail_size: int) -> QRect:
    return QRect(card.x() + CARD_PADDING, card.y() + CARD_PADDING, thumbnail_size, thumbnail_size)


def footer_rect(card: QRect) -> QRect:
    return QRect(
        card.x() + CARD_PADDING,
        card.bottom() + 1 - CARD_PADDING - FOOTER_HEIGHT,
        card.width() - 2 * CARD_PADDING,
        FOOTER_HEIGHT,
    )


class CardDelegate(QStyledItemDelegate):
    """Paints one program as a card: thumbnail on top, name (and PDF button) below."""

    def __init__(self, view: "ThumbnailGrid") -> None:
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index) -> QSize:
        return self._view.gridSize()

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        item: Item | None = index.data(ITEM_ROLE)
        if item is None:
            return
        colors = theme.current()
        size = self._view.thumbnail_size()
        card = card_rect(option.rect, size)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        border = colors.accent if selected else (colors.text_muted if hovered else colors.border)
        painter.setPen(QPen(QColor(border), 2 if selected else 1))
        painter.setBrush(QColor(colors.surface_hover if hovered else colors.surface))
        painter.drawRoundedRect(card.adjusted(1, 1, -1, -1), CARD_RADIUS, CARD_RADIUS)

        area = image_rect(card, size)
        self._paint_image(painter, index, item, area, colors)
        if item.has_details:
            self._paint_badge(painter, area)
        self._paint_footer(painter, option, item, footer_rect(card), colors)
        painter.restore()

    def _paint_image(self, painter, index, item, area: QRect, colors) -> None:
        pixmap: QPixmap | None = index.data(THUMBNAIL_ROLE)
        clip = QPainterPath()
        clip.addRoundedRect(area.x(), area.y(), area.width(), area.height(), 6, 6)
        if pixmap is not None:
            scaled = pixmap.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(
                area.x() + (area.width() - scaled.width()) // 2,
                area.y() + (area.height() - scaled.height()) // 2,
                scaled.width(),
                scaled.height(),
            )
            painter.save()
            painter.setClipPath(clip)
            painter.fillRect(area, QColor("#ffffff"))
            painter.drawPixmap(target, pixmap)
            painter.restore()
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.window))
        painter.drawPath(clip)
        state = index.model().thumbnail_state(item)
        name = "image" if state == "loading" else "image-off"
        edge = max(24, min(56, area.width() // 4))
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        placeholder = icons.pixmap(name, colors.border, int(edge * ratio))
        painter.drawPixmap(
            QRect(area.center().x() - edge // 2, area.center().y() - edge // 2, edge, edge), placeholder
        )

    def _paint_badge(self, painter, area: QRect) -> None:
        """A small marker for cards that have a title, tags or a description."""
        edge = 20
        badge = QRect(area.right() - edge - 4, area.y() + 4, edge, edge)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawEllipse(badge)
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        glyph = icons.pixmap("info", "#ffffff", int(12 * ratio))
        painter.drawPixmap(QRect(badge.x() + 4, badge.y() + 4, 12, 12), glyph)
        painter.restore()

    def _paint_footer(self, painter, option, item, area: QRect, colors) -> None:
        has_pdf = bool(item.pdf)
        text_rect = area.adjusted(10, 0, -10, 0)
        if has_pdf:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors.accent))
            painter.drawRoundedRect(area, 6, 6)
            ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
            glyph = icons.pixmap("file-text", colors.accent_text, int(16 * ratio))
            painter.drawPixmap(QRect(area.x() + 8, area.center().y() - 7, 16, 16), glyph)
            text_rect = area.adjusted(30, 0, -8, 0)
            painter.setPen(QColor(colors.accent_text))
        else:
            painter.setPen(QColor(colors.text_muted))
        metrics = QFontMetrics(option.font)
        text = metrics.elidedText(item.label, Qt.TextElideMode.ElideMiddle, text_rect.width())
        alignment = Qt.AlignmentFlag.AlignVCenter | (
            Qt.AlignmentFlag.AlignLeft if has_pdf else Qt.AlignmentFlag.AlignHCenter
        )
        painter.setFont(option.font)
        painter.drawText(text_rect, int(alignment), text)


class ThumbnailGrid(QListView):
    """Wrapping grid of cards. The number of columns follows the window width."""

    pdfRequested = pyqtSignal(object)
    editRequested = pyqtSignal(object)
    imageRequested = pyqtSignal(object)
    zoomRequested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("grid")
        self._thumbnail_size = 176
        self._pressed: tuple[int, Region] | None = None

        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalScrollBar().setSingleStep(32)
        self.setItemDelegate(CardDelegate(self))
        self._update_grid()

    def thumbnail_size(self) -> int:
        return self._thumbnail_size

    def set_thumbnail_size(self, size: int) -> None:
        if size != self._thumbnail_size:
            self._thumbnail_size = size
            self._update_grid()

    def _update_grid(self, viewport_width: int | None = None) -> None:
        size = card_size(self._thumbnail_size)
        if viewport_width is None:
            viewport_width = self.viewport().width()
        width = max(viewport_width - 1, size.width() + CARD_GAP)
        columns = max(1, width // (size.width() + CARD_GAP))
        # Spread the columns over the full width so the grid always fills the window.
        grid = QSize(width // columns, size.height() + CARD_GAP)
        if grid != self.gridSize():
            self.setGridSize(grid)

    def resizeEvent(self, event) -> None:
        # Set the grid for the new width first, so the layout below already uses it.
        self._update_grid(event.size().width())
        super().resizeEvent(event)

    def item_at(self, position: QPoint) -> tuple[Item | None, Region]:
        index = self.indexAt(position)
        if not index.isValid():
            return None, Region.NONE
        item: Item = index.data(ITEM_ROLE)
        card = card_rect(self.visualRect(index), self._thumbnail_size)
        if footer_rect(card).contains(position):
            return item, Region.FOOTER
        if image_rect(card, self._thumbnail_size).contains(position):
            return item, Region.IMAGE
        return item, Region.NONE

    def _clickable(self, item: Item | None, region: Region) -> bool:
        if item is None:
            return False
        return (region is Region.FOOTER and bool(item.pdf)) or (
            region is Region.IMAGE and bool(item.thumbnail)
        )

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        item, region = self.item_at(event.position().toPoint())
        if self._clickable(item, region):
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._pressed = None
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            index = self.indexAt(position)
            if index.isValid():
                self._pressed = (index.row(), self.item_at(position)[1])

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        pressed, self._pressed = self._pressed, None
        if event.button() != Qt.MouseButton.LeftButton or pressed is None:
            return
        position = event.position().toPoint()
        index = self.indexAt(position)
        item, region = self.item_at(position)
        if not index.isValid() or (index.row(), region) != pressed or not self._clickable(item, region):
            return
        if region is Region.FOOTER:
            self.pdfRequested.emit(item)
        else:
            self.imageRequested.emit(item)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F2:
            item = self.current_item()
            if item is not None:
                self.editRequested.emit(item)
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.current_item()
            if item is not None:
                if item.pdf:
                    self.pdfRequested.emit(item)
                elif item.thumbnail:
                    self.imageRequested.emit(item)
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomRequested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def current_item(self) -> Item | None:
        index = self.currentIndex()
        return index.data(ITEM_ROLE) if index.isValid() else None
