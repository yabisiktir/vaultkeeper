"""CharacterFilter — the "Filter Characters" dialog (VB ``CharacterFilter``).

A small modal dialog to enter a character *level* filter (e.g. ``20``, ``=20``,
``<15``, ``18-24``) and tick up to three *class* names. The parsing, validation and
matching live in :mod:`vaultkeeper.game.character_filter`; this is the thin Qt shell
that gathers the input, validates the level text on Apply (VB ``BtApply_Click`` ->
``IsValidLevelFilter``) and caps the class selection at three (VB ``ItemCheck``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.character_filter import (
    CLASS_NAME_ERROR,
    MAX_CLASSES,
    validate_level_filter,
)

#: Level-help text shown under the entry box (VB ``CharacterFilter`` Load).
_LEVEL_HELP = "\n".join(
    (
        "Enter a value between 1 and 40 to show all characters with the "
        "specified level and higher.",
        "Specify 1 to show all characters regardless of Level.",
        "Use equals to show characters with a specific level "
        "(eg =20 shows all level 20 characters).",
        "Use less than to show characters with the specified level and lower "
        "(eg <20 shows character levels 20 and lower).",
        "Use a hyphen to separate a start and end level "
        "(eg 15-20 shows characters with levels between 15 and 20).",
    )
)


class CharacterFilter(QDialog):
    """Enter a character level filter and pick up to three class names."""

    def __init__(
        self,
        class_names: list[str],
        *,
        level_text: str = "1",
        checked_classes: tuple[str, ...] | list[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filter Characters")
        self._checked_order: list[str] = list(checked_classes)

        layout = QVBoxLayout(self)

        # -- Level filter --------------------------------------------------- #
        layout.addWidget(QLabel("Character Level Filter"))
        self._level = QLineEdit(level_text or "1")
        layout.addWidget(self._level)
        help_label = QLabel(_LEVEL_HELP)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # -- Class filter --------------------------------------------------- #
        layout.addWidget(QLabel("Character Class Filter"))
        self._classes = QListWidget()
        for name in class_names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = name in self._checked_order
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self._classes.addItem(item)
        self._classes.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._classes, 1)

        # -- Status + buttons ---------------------------------------------- #
        self._status = QLabel("")
        layout.addWidget(self._status)

        bar = QHBoxLayout()
        bar.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._on_reset)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        for btn in (apply_btn, reset_btn, cancel_btn):
            bar.addWidget(btn)
        layout.addLayout(bar)

    # -- Results ------------------------------------------------------------ #
    @property
    def level_text(self) -> str:
        """The trimmed level-filter text (VB ``LevelFilterText`` = ``TxLevel.Text``)."""
        return self._level.text().strip()

    @property
    def class_names(self) -> tuple[str, ...]:
        """The checked class names, in the order they were ticked (VB order)."""
        return tuple(self._checked_order)

    # -- Handlers ----------------------------------------------------------- #
    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Maintain the checked-class list, capping the selection at three."""
        name = item.text()
        if item.checkState() == Qt.CheckState.Checked:
            if name in self._checked_order:
                return
            if len(self._checked_order) >= MAX_CLASSES:
                # Refuse the fourth class (VB rejects it in ItemCheck).
                self._status.setText(CLASS_NAME_ERROR)
                QApplication.beep()
                self._classes.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._classes.blockSignals(False)
                return
            self._checked_order.append(name)
        else:
            if name in self._checked_order:
                self._checked_order.remove(name)
            if self._status.text() == CLASS_NAME_ERROR:
                self._status.setText("")

    def _on_apply(self) -> None:
        """Validate the level text; close with Accepted only if it is valid."""
        error = validate_level_filter(self.level_text)
        if error is not None:
            self._status.setText(error)
            return
        self.accept()

    def _on_reset(self) -> None:
        """Reset the level to 1 and clear every ticked class (VB ``BtReset``)."""
        self._level.setText("1")
        self._status.setText("")
        self._checked_order.clear()
        self._classes.blockSignals(True)
        for row in range(self._classes.count()):
            self._classes.item(row).setCheckState(Qt.CheckState.Unchecked)
        self._classes.blockSignals(False)
