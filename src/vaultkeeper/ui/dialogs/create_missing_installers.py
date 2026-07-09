"""Create Missing Installers (VB ``CreateMissingInstallers``).

Lists the mods that do not yet have a ``.Mod Installer`` folder, each checkable
with an **Action** column (Create Installer / Exclude). Checked mods have their
installer payload built when **Create** is pressed; unchecked mods are remembered
in a persisted exclude list so they are hidden next time (VB
``Exclude from missing Installers.txt``). A **Include Mods previously excluded**
checkbox reveals the excluded mods again.

Built on ``ProfileController.missing_installer_report`` /
``create_missing_installers`` / ``save_missing_installer_excludes``. Captions,
columns and window title come from ``CreateMissingInstallers.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: VB ``LbInstructions.Text``.
_INSTRUCTIONS = (
    "Set or clear the tick (check or uncheck) to specify the action to take for "
    "each Mod in the list."
)
_CREATE_ACTION = "Create Installer"
_EXCLUDE_ACTION = "Exclude"


class CreateMissingInstallers(QDialog):
    """Checkable list of installer-less mods with a Create action."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Create Missing Installers")
        self.resize(560, 460)

        report = controller.missing_installer_report()
        self._missing: list[str] = report["mods"]
        self._excluded_lower = {e.lower() for e in report["excluded"]}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_INSTRUCTIONS))

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(
            ["Mods that do not have an Installer", "Action"]
        )
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tree)
        self._tree.itemChanged.connect(self._on_item_changed)

        self._include_excluded = QCheckBox("Include Mods previously excluded")
        self._include_excluded.toggled.connect(lambda _=False: self._populate())
        layout.addWidget(self._include_excluded)

        self._summary = QLabel()
        layout.addWidget(self._summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._create_btn = QPushButton("Create")
        self._create_btn.clicked.connect(self._on_create)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self._create_btn)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self._populate()

    # -- Population -------------------------------------------------------- #
    def _populate(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        show_excluded = self._include_excluded.isChecked()
        for name in self._missing:
            excluded = name.lower() in self._excluded_lower
            if excluded and not show_excluded:
                continue
            checked = not excluded
            item = QTreeWidgetItem(
                [name, _CREATE_ACTION if checked else _EXCLUDE_ACTION]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)
        self._update_summary()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        checked = item.checkState(0) == Qt.CheckState.Checked
        item.setText(1, _CREATE_ACTION if checked else _EXCLUDE_ACTION)
        self._update_summary()

    def _checked_names(self) -> list[str]:
        names: list[str] = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                names.append(item.text(0))
        return names

    def _update_summary(self) -> None:
        # Excluded = every missing mod not marked for creation (unchecked shown +
        # hidden excluded). VB DisplayCounts tracks the same ExcludeCount.
        excluded = len(self._missing) - len(self._checked_names())
        self._summary.setText(
            f"Mods detected: {len(self._missing):,}. "
            f"Excluded: {excluded if excluded else 'None'}."
        )
        self._create_btn.setText(
            "Save" if len(self._missing) == excluded else "Create"
        )

    # -- Actions ----------------------------------------------------------- #
    def _new_exclude_list(self, created: set[str]) -> list[str]:
        """Missing mods not built this round remain/added to the persisted excludes."""
        built = {c.lower() for c in created}
        return [m for m in self._missing if m.lower() not in built]

    def _on_create(self) -> None:
        selected = self._checked_names()
        # Persist exclusions: every still-missing mod that was not selected.
        self._controller.save_missing_installer_excludes(
            self._new_exclude_list(set(selected))
        )
        if selected:
            self._controller.create_missing_installers(selected)
        self.accept()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> CreateMissingInstallers:
        dialog = cls(controller, parent)
        dialog.show()
        return dialog
