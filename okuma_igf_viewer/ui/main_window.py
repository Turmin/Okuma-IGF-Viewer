"""Main window: categories on the left, the program grid on the right."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, database, icons, metadata, theme
from ..database import Item
from ..paths import database_file, metadata_file
from ..settings import Preferences
from .thumbnail_grid import ItemModel, ThumbnailGrid

ZOOM_STEP = 16


class _QuerySignals(QObject):
    finished = pyqtSignal(int, object, str)


class _QueryTask(QRunnable):
    """Runs one item query off the UI thread."""

    def __init__(self, token: int, file: Path, category: str | None, search: str, signals: _QuerySignals):
        super().__init__()
        self._token = token
        self._file = file
        self._category = category
        self._search = search
        self._signals = signals

    def run(self) -> None:
        items: list[Item] = []
        error = ""
        try:
            with closing(database.connect(self._file, readonly=True, metadata_file=metadata_file())) as connection:
                if self._search:
                    items = database.search_items(connection, self._search)
                elif self._category is not None:
                    items = database.items_in_category(connection, self._category)
        except (sqlite3.Error, OSError) as exception:
            error = str(exception) or type(exception).__name__
        try:
            self._signals.finished.emit(self._token, items, error)
        except RuntimeError:
            pass  # the window was closed while the query was running


class MainWindow(QMainWindow):
    def __init__(self, preferences: Preferences | None = None) -> None:
        super().__init__()
        self._preferences = preferences or Preferences()
        self._pool = QThreadPool(self)
        self._query_signals = _QuerySignals(self)
        self._query_signals.finished.connect(self._on_items)
        self._query_token = 0
        self._update_window = None
        self._viewer = None
        self._themed_actions: list[tuple[QAction, str]] = []

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(900, 560)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._load_items)

        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._apply_icons()
        self._restore_state()
        self.reload_database()

    # ----- construction -------------------------------------------------

    def _action(self, text: str, icon_name: str | None, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        if icon_name:
            self._themed_actions.append((action, icon_name))
        return action

    def _build_actions(self) -> None:
        self._update_action = self._action("Update database…", "refresh-cw", self.open_update_window, "Ctrl+U")
        self._viewer_action = self._action("Database viewer…", "database", self.open_database_viewer, "Ctrl+D")
        self._exit_action = self._action("Exit", "log-out", self.close, QKeySequence.StandardKey.Quit)
        self._zoom_in_action = self._action("Larger thumbnails", "zoom-in", lambda: self._zoom(1), "Ctrl++")
        self._zoom_out_action = self._action("Smaller thumbnails", "zoom-out", lambda: self._zoom(-1), "Ctrl+-")
        self._zoom_reset_action = self._action(
            "Default size", None, lambda: self._set_thumbnail_size(Preferences.THUMBNAIL_DEFAULT), "Ctrl+0"
        )
        self._find_action = self._action("Search", "search", self._focus_search, QKeySequence.StandardKey.Find)
        self._about_action = self._action("About", "info", self.about)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self._update_action)
        file_menu.addAction(self._viewer_action)
        file_menu.addSeparator()
        file_menu.addAction(self._exit_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self._find_action)
        view_menu.addSeparator()
        view_menu.addAction(self._zoom_in_action)
        view_menu.addAction(self._zoom_out_action)
        view_menu.addAction(self._zoom_reset_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Theme")
        group = QActionGroup(self)
        for key, label, icon_name in (
            ("system", "Follow Windows", "monitor"),
            ("dark", "Dark", "moon"),
            ("light", "Light", "sun"),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(self._preferences.theme == key)
            action.triggered.connect(lambda _checked=False, name=key: self._set_theme(name))
            group.addAction(action)
            theme_menu.addAction(action)
            self._themed_actions.append((action, icon_name))

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self._about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main toolbar", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(toolbar)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search name, number, title, tag or description")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(260)
        self._search.setMaximumWidth(460)
        self._search_icon = self._search.addAction(icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self._search.textChanged.connect(lambda _text: self._search_timer.start())
        self._search.returnPressed.connect(self._load_items)
        toolbar.addWidget(self._search)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        toolbar.addAction(self._zoom_out_action)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(Preferences.THUMBNAIL_MIN, Preferences.THUMBNAIL_MAX)
        self._zoom_slider.setSingleStep(ZOOM_STEP)
        self._zoom_slider.setPageStep(ZOOM_STEP * 2)
        self._zoom_slider.setFixedWidth(150)
        self._zoom_slider.setToolTip("Thumbnail size (Ctrl + mouse wheel)")
        self._zoom_slider.valueChanged.connect(self._set_thumbnail_size)
        toolbar.addWidget(self._zoom_slider)
        toolbar.addAction(self._zoom_in_action)
        toolbar.addSeparator()
        toolbar.addAction(self._update_action)
        toolbar.widgetForAction(self._update_action).setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

    def _build_central(self) -> None:
        sidebar_panel = QWidget()
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_title = QLabel("CATEGORIES")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_layout.addWidget(sidebar_title)
        self._categories = QListWidget()
        self._categories.setObjectName("sidebar")
        self._categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._categories.currentItemChanged.connect(self._on_category_changed)
        sidebar_layout.addWidget(self._categories, 1)

        self._model = ItemModel(self)
        self._grid = ThumbnailGrid()
        self._grid.setModel(self._model)
        self._grid.pdfRequested.connect(self._open_pdf)
        self._grid.imageRequested.connect(self._open_thumbnail)
        self._grid.editRequested.connect(self.edit_details)
        self._grid.zoomRequested.connect(self._zoom)
        self._grid.customContextMenuRequested.connect(self._show_context_menu)

        self._empty_title = QLabel()
        self._empty_title.setObjectName("emptyTitle")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text = QLabel()
        self._empty_text.setObjectName("emptyText")
        self._empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_text.setWordWrap(True)
        self._empty_button = QPushButton("Update database…")
        self._empty_button.setObjectName("primary")
        self._empty_button.clicked.connect(self.open_update_window)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setSpacing(10)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self._empty_title)
        empty_layout.addWidget(self._empty_text)
        empty_layout.addWidget(self._empty_button, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch(1)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._grid)
        self._stack.addWidget(empty)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(sidebar_panel)
        self._splitter.addWidget(self._stack)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([230, 1000])
        sidebar_panel.setMinimumWidth(160)
        self.setCentralWidget(self._splitter)

    def _build_statusbar(self) -> None:
        self._status_info = QLabel()
        self.statusBar().addPermanentWidget(self._status_info)

    def _apply_icons(self) -> None:
        for action, name in self._themed_actions:
            action.setIcon(icons.icon(name))
        self._search_icon.setIcon(icons.icon("search", theme.current().text_muted))

    # ----- state --------------------------------------------------------

    def _restore_state(self) -> None:
        geometry = self._preferences.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter = self._preferences.value("window/splitter")
        if splitter is not None:
            self._splitter.restoreState(splitter)
        size = self._preferences.thumbnail_size
        self._zoom_slider.setValue(size)
        self._grid.set_thumbnail_size(size)

    def has_saved_geometry(self) -> bool:
        return self._preferences.value("window/geometry") is not None

    def closeEvent(self, event) -> None:
        if self._update_window is not None and self._update_window.is_running():
            QMessageBox.information(
                self, APP_NAME, "A database update is still running. Stop it or wait until it has finished."
            )
            event.ignore()
            return
        self._preferences.set_value("window/geometry", self.saveGeometry())
        self._preferences.set_value("window/splitter", self._splitter.saveState())
        self._model.shutdown()
        for window in (self._update_window, self._viewer):
            if window is not None:
                window.close()
        event.accept()

    # ----- data ---------------------------------------------------------

    def reload_database(self) -> None:
        """Read the categories again, for example after the database was rebuilt."""
        file = database_file()
        previous = self._current_category() or self._preferences.last_category
        self._categories.blockSignals(True)
        self._categories.clear()
        self._categories.blockSignals(False)
        self._model.set_items([])
        self._status_info.clear()

        if not file.is_file():
            self._show_empty(
                "No database yet",
                "Build the database from the IGF backup, PDF and thumbnail folders to get started.",
                with_button=True,
            )
            self._set_database_available(False)
            return

        database.ensure_indexes(file)
        try:
            with closing(database.connect(file, readonly=True, metadata_file=metadata_file())) as connection:
                categories = database.categories(connection)
                info = database.info(connection)
        except (sqlite3.Error, OSError) as error:
            self._show_empty("The database could not be opened", str(error), with_button=True)
            self._set_database_available(False)
            return

        self._set_database_available(True)
        if info is not None:
            parts = []
            if info.last_updated is not None:
                parts.append(f"Last updated {info.last_updated.strftime('%d-%m-%Y')}")
            if info.folder:
                parts.append(info.folder)
            self._status_info.setText("  ·  ".join(parts))

        if not categories:
            self._show_empty(
                "The database is empty",
                "No IGF programs were found during the last update. Check the folders and update again.",
                with_button=True,
            )
            return

        selected_row = 0
        for row, (category, count) in enumerate(categories):
            entry = QListWidgetItem(f"{category}   ({count})")
            entry.setData(Qt.ItemDataRole.UserRole, category)
            self._categories.addItem(entry)
            if category == previous:
                selected_row = row
        self._categories.setCurrentRow(selected_row)

    def _set_database_available(self, available: bool) -> None:
        self._viewer_action.setEnabled(available)
        self._search.setEnabled(available)

    def _current_category(self) -> str | None:
        entry = self._categories.currentItem()
        return entry.data(Qt.ItemDataRole.UserRole) if entry is not None else None

    def _on_category_changed(self, current, _previous) -> None:
        if current is None:
            return
        self._preferences.last_category = current.data(Qt.ItemDataRole.UserRole)
        if self._search.text().strip():
            # Picking a category leaves the search and shows that category.
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self._load_items()

    def _load_items(self) -> None:
        self._search_timer.stop()
        search = self._search.text().strip()
        category = self._current_category()
        if not search and category is None:
            return
        self._query_token += 1
        self.statusBar().showMessage("Loading…")
        self._pool.start(_QueryTask(self._query_token, database_file(), category, search, self._query_signals))

    def _on_items(self, token: int, items: list[Item], error: str) -> None:
        if token != self._query_token:
            return  # a newer query is already on its way
        if error:
            self._model.set_items([])
            self._show_empty("The programs could not be loaded", error)
            self.statusBar().clearMessage()
            return

        self._model.set_items(items)
        self._grid.scrollToTop()
        search = self._search.text().strip()
        if not items:
            if search:
                self._show_empty("No results", f"Nothing matches '{search}'.")
            else:
                self._show_empty("No programs", "This category is empty.")
        else:
            self._stack.setCurrentIndex(0)

        with_pdf = sum(1 for item in items if item.pdf)
        scope = f"Search '{search}'" if search else str(self._current_category())
        noun = "program" if len(items) == 1 else "programs"
        self.statusBar().showMessage(f"{scope}  ·  {len(items)} {noun}  ·  {with_pdf} with PDF")

    def _show_empty(self, title: str, text: str, *, with_button: bool = False) -> None:
        self._empty_title.setText(title)
        self._empty_text.setText(text)
        self._empty_button.setVisible(with_button)
        self._stack.setCurrentIndex(1)

    # ----- view ---------------------------------------------------------

    def _focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def _zoom(self, direction: int) -> None:
        self._set_thumbnail_size(self._grid.thumbnail_size() + direction * ZOOM_STEP)

    def _set_thumbnail_size(self, size: int) -> None:
        size = max(Preferences.THUMBNAIL_MIN, min(Preferences.THUMBNAIL_MAX, int(size)))
        self._grid.set_thumbnail_size(size)
        if self._zoom_slider.value() != size:
            self._zoom_slider.blockSignals(True)
            self._zoom_slider.setValue(size)
            self._zoom_slider.blockSignals(False)
        self._preferences.thumbnail_size = size

    def _set_theme(self, name: str) -> None:
        self._preferences.theme = name
        theme.apply(QApplication.instance(), name)
        self._apply_icons()
        self._grid.viewport().update()

    # ----- actions on a program -----------------------------------------

    def _open_file(self, file: str | None, description: str) -> None:
        if not file:
            return
        if not os.path.exists(file):
            self.statusBar().showMessage(f"{description} not found: {file}", 8000)
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(file)  # noqa: S606 - opens the file with its default Windows application
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(file))
        except OSError as error:
            self.statusBar().showMessage(f"{description} could not be opened: {error}", 8000)

    def _open_pdf(self, item: Item) -> None:
        self._open_file(item.pdf, "PDF")

    def _open_thumbnail(self, item: Item) -> None:
        self._open_file(item.thumbnail, "Thumbnail")

    def _show_in_folder(self, file: str) -> None:
        if not os.path.exists(file):
            self.statusBar().showMessage(f"File not found: {file}", 8000)
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(file)])  # noqa: S603, S607
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file)))

    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"Copied {text}", 3000)

    def _show_context_menu(self, position) -> None:
        item, _region = self._grid.item_at(position)
        if item is None:
            return
        menu = QMenu(self)
        open_pdf = menu.addAction(icons.icon("file-text"), "Open PDF")
        open_pdf.setEnabled(bool(item.pdf))
        open_pdf.triggered.connect(lambda: self._open_pdf(item))
        open_image = menu.addAction(icons.icon("image"), "Open thumbnail")
        open_image.setEnabled(bool(item.thumbnail))
        open_image.triggered.connect(lambda: self._open_thumbnail(item))
        menu.addSeparator()
        menu.addAction(icons.icon("pencil"), "Edit details…\tF2").triggered.connect(
            lambda: self.edit_details(item)
        )
        menu.addSeparator()
        show_igf = menu.addAction(icons.icon("folder-open"), "Show IGF program in folder")
        show_igf.setEnabled(bool(item.igf_file))
        show_igf.triggered.connect(lambda: self._show_in_folder(item.igf_file))
        menu.addSeparator()
        menu.addAction(icons.icon("copy"), "Copy drawing number").triggered.connect(
            lambda: self._copy(item.drawing_number)
        )
        menu.addAction(icons.icon("copy"), "Copy program name").triggered.connect(lambda: self._copy(item.name))
        menu.exec(self._grid.viewport().mapToGlobal(position))

    def edit_details(self, item: Item) -> None:
        from .details_dialog import DetailsDialog

        file = metadata_file()
        current = metadata.Details(item.title, item.description, item.tags)
        dialog = DetailsDialog(item, current, self)
        if dialog.exec() != DetailsDialog.DialogCode.Accepted:
            return
        try:
            saved = metadata.save(file, item.drawing_number, dialog.details())
        except (sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, APP_NAME, f"The details could not be saved.\n\n{error}")
            return
        self._model.set_details(item.drawing_number, saved)
        self.statusBar().showMessage(f"Saved details for {item.drawing_number}", 3000)

    # ----- windows ------------------------------------------------------

    def open_update_window(self) -> None:
        from .update_window import UpdateWindow

        if self._update_window is None:
            self._update_window = UpdateWindow(self)
            self._update_window.databaseUpdated.connect(self.reload_database)
        self._update_window.show()
        self._update_window.raise_()
        self._update_window.activateWindow()

    def open_database_viewer(self) -> None:
        from .database_viewer import DatabaseViewer

        if self._viewer is not None:
            self._viewer.close()
        try:
            self._viewer = DatabaseViewer(database_file(), self)
        except (sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, APP_NAME, f"The database could not be opened.\n\n{error}")
            return
        self._viewer.show()

    def about(self) -> None:
        colors = theme.current()
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"""
            <h3>{APP_NAME}</h3>
            <p>Version {__version__}</p>
            <p>Shows the Okuma IGF programs with the thumbnail and PDF of their drawing.</p>
            <p>© Michael van Druten<br>
            <a style='color:{colors.accent}' href='mailto:info@turmin.com?Subject=Okuma%20IGF%20Viewer'>info@turmin.com</a></p>
            <p style='color:{colors.text_muted}'>Icons: Lucide (ISC License)</p>
            """,
        )
