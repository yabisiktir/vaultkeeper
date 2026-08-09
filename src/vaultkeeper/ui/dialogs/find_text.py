"""Find within a text pane or a list (VB's Find, for the non-profile scopes).

The original's Find is one command with three meanings, chosen by what has
focus: the mod list searches the whole profile, a contents/details list steps
through its rows, and a text pane steps through occurrences in the text. This
module is the last two; the profile search is
:mod:`vaultkeeper.ui.dialogs.find_files`.

Both directions are supported, and running off the end says so rather than
silently doing nothing — "The dialogue indicates when there are no more
occurrences" is the documented behaviour, and it is the only way to tell
"not found" from "nothing happened".
"""

from __future__ import annotations

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)


class FindTextDialog(QDialog):
    """Step through occurrences in a text editor or rows in a list.

    ``target`` is either a ``QTextEdit``/``QPlainTextEdit`` or a ``QTreeWidget``;
    the dialog works out which and searches accordingly.
    """

    def __init__(self, target: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target = target
        self._is_list = isinstance(target, QTreeWidget)

        self.setWindowTitle("Find")
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Find what:"))
        self.text = QLineEdit()
        self.text.returnPressed.connect(self.find_next)
        row.addWidget(self.text, 1)
        layout.addLayout(row)

        self.match_case = QCheckBox("Match case")
        layout.addWidget(self.match_case)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        buttons = QDialogButtonBox()
        self._next = QPushButton("Find Next")
        self._next.setDefault(True)
        self._next.clicked.connect(self.find_next)
        buttons.addButton(self._next, QDialogButtonBox.ButtonRole.ActionRole)
        self._previous = QPushButton("Previous")
        self._previous.clicked.connect(self.find_previous)
        buttons.addButton(self._previous, QDialogButtonBox.ButtonRole.ActionRole)
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close.clicked.connect(self.reject)
        layout.addWidget(buttons)

    # -- Searching --------------------------------------------------------- #
    def find_next(self) -> bool:
        return self._find(forwards=True)

    def find_previous(self) -> bool:
        return self._find(forwards=False)

    def _find(self, *, forwards: bool) -> bool:
        needle = self.text.text()
        if not needle:
            self.message.setText("")
            return False
        found = (
            self._find_in_list(needle, forwards=forwards)
            if self._is_list
            else self._find_in_text(needle, forwards=forwards)
        )
        self.message.setText(
            "" if found else f"There are no more occurrences of '{needle}'."
        )
        return found

    def _find_in_text(self, needle: str, *, forwards: bool) -> bool:
        flags = QTextDocument.FindFlag(0)
        if not forwards:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.match_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self._target.find(needle, flags):
            return True
        # Wrapping is not "no more occurrences": say nothing found only when a
        # search from the very start (or end) also fails.
        cursor = self._target.textCursor()
        restart = QTextCursor(cursor)
        restart.movePosition(
            QTextCursor.MoveOperation.End if not forwards else QTextCursor.MoveOperation.Start
        )
        self._target.setTextCursor(restart)
        if self._target.find(needle, flags):
            return True
        self._target.setTextCursor(cursor)
        return False

    def _find_in_list(self, needle: str, *, forwards: bool) -> bool:
        rows = []
        iterator = QTreeWidgetItemIterator(self._target)
        while iterator.value():
            rows.append(iterator.value())
            iterator += 1
        if not rows:
            return False

        current = self._target.currentItem()
        start = rows.index(current) if current in rows else -1
        order = range(start + 1, len(rows)) if forwards else range(start - 1, -1, -1)
        # Wrap, so Find Next from the last match returns to the first rather
        # than reporting nothing when there plainly is something.
        wrapped = range(0, start + 1) if forwards else range(len(rows) - 1, start, -1)

        haystack = (lambda s: s) if self.match_case.isChecked() else str.lower
        target = haystack(needle)
        for index in list(order) + list(wrapped):
            item = rows[index]
            columns = self._target.columnCount()
            if any(target in haystack(item.text(c)) for c in range(columns)):
                self._target.setCurrentItem(item)
                self._target.scrollToItem(item)
                return True
        return False
