"""UserResponseEditor — view/forget the GameMapper's remembered answers (VB UserResponseEditor).

When NIT can't map a save/log name to a mod on its own it asks the user and
remembers the answer. This dialog lists those remembered responses in the four
VB groups (Mod Choices / Log to Mod Names / Save Name to Mod Names / Save Name to
Profile Mod Names) and lets the user delete one so the mapper asks again.
Data + mutation come from ``ProfileController.user_responses_report`` /
``delete_user_response``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R

_KEY_ROLE = 0x0100  # Qt.UserRole


class UserResponseEditor(QDialog):
    """List remembered GameMapper responses and delete individual ones."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("User Response Editor")
        self.setWindowIcon(R.get_icon("user"))
        geometry.remember(self, "UserResponseEditor", 560, 440)
        self._controller = controller

        layout = QVBoxLayout(self)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Identifier", "Mod Name"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._tree)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhGameMapper", self))
        buttons.addStretch(1)
        self._delete = QPushButton("Delete")
        self._delete.setEnabled(False)
        self._delete.clicked.connect(self._on_delete)
        buttons.addWidget(self._delete)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        self._tree.clear()
        report = self._controller.user_responses_report()
        for group in report["groups"]:
            parent = QTreeWidgetItem([group["title"], ""])
            parent.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(parent)
            for row in group["rows"]:
                child = QTreeWidgetItem([row["identifier"], row["mod_name"]])
                # Stash (category, delete-key) so the button knows what to remove.
                child.setData(0, _KEY_ROLE, (group["key"], row["key"]))
                parent.addChild(child)
            if not group["rows"]:
                empty = QTreeWidgetItem(["None", ""])
                parent.addChild(empty)
            parent.setExpanded(True)
        self._delete.setEnabled(False)

    def _on_selection(self, current: QTreeWidgetItem | None) -> None:
        self._delete.setEnabled(
            current is not None and current.data(0, _KEY_ROLE) is not None
        )

    def _on_delete(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        payload = item.data(0, _KEY_ROLE)
        if payload is None:
            return
        category, key = payload
        if self._controller.delete_user_response(category, key):
            self._reload()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> UserResponseEditor:
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
