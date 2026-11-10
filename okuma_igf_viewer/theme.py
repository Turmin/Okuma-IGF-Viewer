"""Light and dark appearance for the whole application."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class Colors:
    name: str
    window: str
    surface: str
    surface_hover: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    selection: str
    danger: str
    success: str


DARK = Colors(
    name="dark",
    window="#15181d",
    surface="#1e2229",
    surface_hover="#272c35",
    border="#323844",
    text="#e6e9ee",
    text_muted="#98a1b0",
    accent="#2f8fdd",
    accent_hover="#4aa3ea",
    accent_text="#ffffff",
    selection="#1d4f7c",
    danger="#e5646b",
    success="#4cb782",
)

LIGHT = Colors(
    name="light",
    window="#f3f5f8",
    surface="#ffffff",
    surface_hover="#edf1f6",
    border="#d5dbe4",
    text="#1b2028",
    text_muted="#5e6878",
    accent="#0b6cbd",
    accent_hover="#0a5ea6",
    accent_text="#ffffff",
    selection="#cfe5f8",
    danger="#c8323a",
    success="#1f8a57",
)

_current = DARK


def current() -> Colors:
    return _current


def resolve(theme: str) -> Colors:
    """Translate 'system', 'dark' or 'light' into a colour set."""
    if theme == "light":
        return LIGHT
    if theme == "system":
        scheme = QGuiApplication.styleHints().colorScheme()
        return LIGHT if scheme == Qt.ColorScheme.Light else DARK
    return DARK


def apply(app: QApplication, theme: str) -> Colors:
    global _current
    colors = resolve(theme)
    _current = colors

    app.setStyle("Fusion")
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: colors.window,
        QPalette.ColorRole.WindowText: colors.text,
        QPalette.ColorRole.Base: colors.surface,
        QPalette.ColorRole.AlternateBase: colors.surface_hover,
        QPalette.ColorRole.Text: colors.text,
        QPalette.ColorRole.Button: colors.surface,
        QPalette.ColorRole.ButtonText: colors.text,
        QPalette.ColorRole.ToolTipBase: colors.surface,
        QPalette.ColorRole.ToolTipText: colors.text,
        QPalette.ColorRole.PlaceholderText: colors.text_muted,
        QPalette.ColorRole.Highlight: colors.accent,
        QPalette.ColorRole.HighlightedText: colors.accent_text,
        QPalette.ColorRole.Link: colors.accent,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors.text_muted))
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet(colors))
    return colors


def _stylesheet(c: Colors) -> str:
    return f"""
    QWidget {{ font-size: 10pt; }}
    QMainWindow, QDialog {{ background: {c.window}; }}
    QToolTip {{ background: {c.surface}; color: {c.text}; border: 1px solid {c.border}; padding: 4px 6px; }}

    QMenuBar {{ background: {c.window}; border-bottom: 1px solid {c.border}; }}
    QMenuBar::item {{ padding: 6px 10px; background: transparent; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {c.surface_hover}; }}
    QMenu {{ background: {c.surface}; border: 1px solid {c.border}; padding: 4px; }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c.selection}; color: {c.text}; }}
    QMenu::item:disabled {{ color: {c.text_muted}; }}
    QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 6px; }}
    QMenu::icon {{ padding-left: 8px; }}

    QToolBar {{ background: {c.window}; border: none; border-bottom: 1px solid {c.border}; padding: 8px 10px; spacing: 8px; }}
    QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 6px; }}
    QToolButton:hover {{ background: {c.surface_hover}; }}
    QToolButton:pressed {{ background: {c.selection}; }}

    QLineEdit {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 6px; padding: 6px 10px; selection-background-color: {c.accent}; }}
    QLineEdit:focus {{ border-color: {c.accent}; }}
    QLineEdit:disabled {{ color: {c.text_muted}; }}

    QPushButton {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 6px; padding: 7px 16px; }}
    QPushButton:hover {{ background: {c.surface_hover}; }}
    QPushButton:disabled {{ color: {c.text_muted}; }}
    QPushButton#primary {{ background: {c.accent}; border-color: {c.accent}; color: {c.accent_text}; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
    QPushButton#primary:disabled {{ background: {c.surface_hover}; border-color: {c.border}; color: {c.text_muted}; }}

    QComboBox {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 6px; padding: 6px 10px; }}
    QComboBox QAbstractItemView {{ background: {c.surface}; border: 1px solid {c.border}; selection-background-color: {c.selection}; selection-color: {c.text}; }}

    QListWidget#sidebar {{ background: {c.window}; border: none; outline: none; padding: 6px; }}
    QListWidget#sidebar::item {{ padding: 8px 10px; border-radius: 6px; margin: 1px 0; }}
    QListWidget#sidebar::item:hover {{ background: {c.surface_hover}; }}
    QListWidget#sidebar::item:selected {{ background: {c.selection}; color: {c.text}; }}
    QLabel#sidebarTitle {{ color: {c.text_muted}; font-size: 8pt; font-weight: 600; padding: 14px 16px 4px 16px; }}
    QWidget#sidebarPanel {{ background: {c.window}; border-right: 1px solid {c.border}; }}

    QListView#grid {{ background: {c.window}; border: none; outline: none; }}

    QLabel#emptyTitle {{ font-size: 15pt; font-weight: 600; }}
    QLabel#emptyText, QLabel#muted {{ color: {c.text_muted}; }}
    QLabel#dialogTitle {{ font-size: 13pt; font-weight: 600; }}

    QPlainTextEdit {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 6px; padding: 6px; }}
    QProgressBar {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {c.accent}; border-radius: 3px; }}

    QTableView {{ background: {c.surface}; border: 1px solid {c.border}; gridline-color: {c.border}; selection-background-color: {c.selection}; selection-color: {c.text}; }}
    QHeaderView::section {{ background: {c.window}; border: none; border-bottom: 1px solid {c.border}; border-right: 1px solid {c.border}; padding: 6px 8px; font-weight: 600; }}

    QStatusBar {{ background: {c.window}; border-top: 1px solid {c.border}; color: {c.text_muted}; }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ color: {c.text_muted}; padding: 0 8px; }}

    QSlider::groove:horizontal {{ height: 4px; background: {c.border}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {c.accent}; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c.border}; border-radius: 4px; min-height: 32px; margin: 2px; }}
    QScrollBar::handle:vertical:hover {{ background: {c.text_muted}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c.border}; border-radius: 4px; min-width: 32px; margin: 2px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

    QSplitter::handle {{ background: {c.border}; width: 1px; }}
    """
