"""Read-only viewer for the raw database tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QTableView, QVBoxLayout

from .. import APP_NAME, database

BATCH = 500


class _TableModel(QAbstractTableModel):
    """Shows one table and fetches its rows in batches while scrolling."""

    def __init__(self, connection: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._connection = connection
        self._table = ""
        self._filter = ""
        self._columns: list[str] = []
        self._rows: list[tuple] = []
        self._total = 0

    def total(self) -> int:
        return self._total

    def set_source(self, table: str, text: str = "") -> None:
        self.beginResetModel()
        self._table = table
        self._filter = text.strip()
        self._rows = []
        self._columns = [row[1] for row in self._connection.execute(f'PRAGMA table_info("{table}")')]
        where, parameters = self._where()
        self._total = self._connection.execute(
            f'SELECT COUNT(*) FROM "{table}"{where}', parameters
        ).fetchone()[0]
        self.endResetModel()

    def _where(self) -> tuple[str, tuple]:
        if not self._filter or not self._columns:
            return "", ()
        pattern = f"%{self._filter}%"
        clause = " OR ".join(f'CAST("{column}" AS TEXT) LIKE ?' for column in self._columns)
        return f" WHERE {clause}", tuple(pattern for _ in self._columns)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            value = self._rows[index.row()][index.column()]
            return "" if value is None else str(value)
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section]
        return str(section + 1)

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and len(self._rows) < self._total

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        where, parameters = self._where()
        rows = self._connection.execute(
            f'SELECT * FROM "{self._table}"{where} LIMIT ? OFFSET ?',
            (*parameters, BATCH, len(self._rows)),
        ).fetchall()
        if not rows:
            self._total = len(self._rows)
            return
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows) + len(rows) - 1)
        self._rows.extend(rows)
        self.endInsertRows()


class DatabaseViewer(QDialog):
    def __init__(self, file: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Database viewer - {APP_NAME}")
        self.resize(1000, 640)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self._connection = database.connect(file, readonly=True)
        self._model = _TableModel(self._connection, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        self._tables = QComboBox()
        self._tables.setMinimumWidth(160)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter rows…")
        self._filter.setClearButtonEnabled(True)
        bar.addWidget(QLabel("Table"))
        bar.addWidget(self._tables)
        bar.addWidget(self._filter, 1)
        layout.addLayout(bar)

        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._view.setAlternatingRowColors(True)
        self._view.verticalHeader().setDefaultSectionSize(26)
        self._view.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._view, 1)

        self._count = QLabel()
        self._count.setObjectName("muted")
        layout.addWidget(self._count)

        names = database.table_names(self._connection)
        self._tables.addItems(names)
        if "igf" in names:
            self._tables.setCurrentText("igf")
        self._tables.currentTextChanged.connect(lambda _name: self._reload())
        self._filter.returnPressed.connect(self._reload)
        self._filter.textChanged.connect(lambda text: self._reload() if not text else None)
        self._reload()

    def _reload(self) -> None:
        table = self._tables.currentText()
        if not table:
            return
        self._model.set_source(table, self._filter.text())
        if self._model.canFetchMore():
            self._model.fetchMore()  # so the column widths fit real content
        self._view.resizeColumnsToContents()
        self._count.setText(f"{self._model.total():,} rows".replace(",", "."))

    def closeEvent(self, event) -> None:
        self._connection.close()
        super().closeEvent(event)
