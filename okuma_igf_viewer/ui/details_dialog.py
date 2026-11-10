"""Dialog to give a drawing number a title, tags and a description."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import metadata
from ..database import Item


class DetailsDialog(QDialog):
    def __init__(self, item: Item, details: metadata.Details, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit details")
        self.setMinimumWidth(460)

        heading = QLabel(item.name)
        heading.setObjectName("dialogTitle")
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        note = QLabel(
            f"Drawing number {item.drawing_number}. The details are shared by every program with this number "
            "and are used by the search."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)

        self._title = QLineEdit(details.title)
        self._title.setPlaceholderText("Short name that is shown on the card")
        self._tags = QLineEdit(metadata.format_tags(details.tags))
        self._tags.setPlaceholderText("Separate tags with commas, for example: shaft, steel, M12")
        self._description = QPlainTextEdit(details.description)
        self._description.setPlaceholderText("Material, machine setup, remarks…")
        self._description.setMinimumHeight(110)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("Title", self._title)
        form.addRow("Tags", self._tags)
        form.addRow("Description", self._description)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._title.setFocus()

    def details(self) -> metadata.Details:
        return metadata.clean(
            metadata.Details(
                title=self._title.text(),
                description=self._description.toPlainText(),
                tags=metadata.parse_tags(self._tags.text()),
            )
        )
