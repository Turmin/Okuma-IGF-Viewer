"""Dialog that rebuilds the database from the IGF backup, PDF and thumbnail folders."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .. import APP_NAME, icons, indexer
from ..paths import config_file, database_file
from ..settings import SourceFolders


class _RebuildThread(QThread):
    message = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, folders: SourceFolders, target: Path, parent=None) -> None:
        super().__init__(parent)
        self._folders = folders
        self._target = target

    def run(self) -> None:
        try:
            summary = indexer.rebuild(
                self._target,
                self._folders.igf,
                self._folders.pdf,
                self._folders.thumbnail,
                progress=self.message.emit,
                cancelled=self.isInterruptionRequested,
            )
        except indexer.Cancelled:
            self.cancelled.emit()
        except Exception as error:  # noqa: BLE001 - shown to the user
            self.failed.emit(str(error) or type(error).__name__)
        else:
            self.succeeded.emit(summary)


class UpdateWindow(QDialog):
    """Lets the user pick the three source folders and start a rebuild."""

    databaseUpdated = pyqtSignal()

    _ROWS = (
        ("igf", "IGF backup", "Folder with the Okuma backup (contains AD0)"),
        ("pdf", "PDF folder", "Folder with the drawing PDFs (pdf/code)"),
        ("thumbnail", "Thumbnail folder", "Folder with the 3D thumbnails (Thumbnail_3D/code)"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Update database - {APP_NAME}")
        self.setMinimumSize(720, 520)
        self._thread: _RebuildThread | None = None
        self._folders = SourceFolders.load(config_file())
        self._edits: dict[str, QLineEdit] = {}
        self._browse_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Update database")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        intro = QLabel(
            "Scans the folders below and rebuilds the database. The viewer keeps using the "
            "current database until the new one is complete."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for row, (field, label, hint) in enumerate(self._ROWS):
            edit = QLineEdit(getattr(self._folders, field))
            edit.setPlaceholderText(hint)
            edit.setClearButtonEnabled(True)
            button = QPushButton("Browse…")
            button.setIcon(icons.icon("folder-open"))
            button.clicked.connect(lambda _checked=False, name=field: self._browse(name))
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(button, row, 2)
            self._edits[field] = edit
            self._browse_buttons.append(button)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Progress appears here.")
        layout.addWidget(self._log, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._close_button = QPushButton("Close")
        self._close_button.clicked.connect(self.close)
        self._start_button = QPushButton("Start update")
        self._start_button.setObjectName("primary")
        self._start_button.setDefault(True)
        self._start_button.clicked.connect(self._start_or_cancel)
        buttons.addWidget(self._close_button)
        buttons.addWidget(self._start_button)
        layout.addLayout(buttons)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _browse(self, field: str) -> None:
        edit = self._edits[field]
        selected = QFileDialog.getExistingDirectory(self, "Select folder", edit.text() or "C:/")
        if selected:
            edit.setText(selected)

    def _collect(self) -> SourceFolders | None:
        folders = SourceFolders(*(self._edits[field].text().strip() for field, _, _ in self._ROWS))
        for field, label, _ in self._ROWS:
            value = getattr(folders, field)
            if not value:
                self._log.appendPlainText(f"{label}: no folder selected.")
                return None
            if not Path(value).is_dir():
                self._log.appendPlainText(f"{label}: '{value}' does not exist or is not reachable.")
                return None
        return folders

    def _start_or_cancel(self) -> None:
        if self.is_running():
            self._start_button.setEnabled(False)
            self._log.appendPlainText("Stopping…")
            self._thread.requestInterruption()
            return

        folders = self._collect()
        if folders is None:
            return
        try:
            folders.save(config_file())
        except OSError as error:
            self._log.appendPlainText(f"Could not save the folders to conf.ini: {error}")

        self._log.clear()
        self._set_running(True)
        self._thread = _RebuildThread(folders, database_file(), self)
        self._thread.message.connect(self._log.appendPlainText)
        self._thread.succeeded.connect(self._on_succeeded)
        self._thread.failed.connect(self._on_failed)
        self._thread.cancelled.connect(self._on_cancelled)
        self._thread.finished.connect(lambda: self._set_running(False))
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        self._progress.setRange(0, 0 if running else 1)
        self._progress.setValue(0)
        self._start_button.setText("Stop" if running else "Start update")
        self._start_button.setEnabled(True)
        self._close_button.setEnabled(not running)
        for widget in (*self._edits.values(), *self._browse_buttons):
            widget.setEnabled(not running)

    def _on_succeeded(self, summary: indexer.Summary) -> None:
        self._log.appendPlainText(
            f"Done: {summary.igf} IGF programs, {summary.pdf} PDF files and "
            f"{summary.thumbnails} thumbnails."
        )
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self.databaseUpdated.emit()

    def _on_failed(self, message: str) -> None:
        self._log.appendPlainText(f"The update failed: {message}")
        self._log.appendPlainText("The existing database was not changed.")

    def _on_cancelled(self) -> None:
        self._log.appendPlainText("Update stopped. The existing database was not changed.")

    def closeEvent(self, event) -> None:
        if self.is_running():
            QMessageBox.information(
                self,
                APP_NAME,
                "An update is still running. Stop it or wait until it has finished.",
            )
            event.ignore()
            return
        event.accept()

    def keyPressEvent(self, event) -> None:
        # Escape must not close the dialog while an update is running.
        if event.key() == Qt.Key.Key_Escape and self.is_running():
            event.ignore()
            return
        super().keyPressEvent(event)
