"""DependencyEditor — edit one mod's dependencies (VB ``DependencyManager``).

Three-column editor mirroring the original: **Groups** (left) → the selected group's
**Mods** (middle, checkable — ticked = a dependency of the edited mod) → the edited
mod's current **Dependencies** (right). Ticking a mod adds it as a dependency; **Save**
persists the set and (for an installed mod) reconciles dependency installs/uninstalls.
Built on ``ProfileController.dependency_editor_data`` / ``set_mod_dependencies``.

**Auto** (VB ``BtAuto``) works the dependencies out from the mods' Neverwinter
Vault project pages, for the whole profile at once — which is what VB's button
does too. It matters more than it looks: nothing else in the tool ever writes a
dependency by itself, so without it the list stays empty however many mods
depend on CEP in fact.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R

_KEY_ROLE = Qt.ItemDataRole.UserRole


class DependencyEditor(QDialog):
    """Edit the dependency list of a single mod."""

    def __init__(self, controller, mod_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mod_name = mod_name
        self.setWindowTitle("Dependency Manager")
        self.setWindowIcon(R.get_icon("DependencyGraph_16x"))
        geometry.remember(self, "DependencyEditor", 720, 460)

        data = controller.dependency_editor_data(mod_name)
        self._groups = data["groups"]
        self._deps: set[str] = set(data["dependencies"])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Dependencies for: {mod_name}"))

        lists = QHBoxLayout()
        layout.addLayout(lists, 1)

        self.group_list = QListWidget()
        for group in self._groups:
            item = QListWidgetItem(group["name"])
            self.group_list.addItem(item)
        self.group_list.currentRowChanged.connect(self._on_group)
        lists.addWidget(self._titled("Groups", self.group_list), 1)

        self.mod_list = QListWidget()
        self.mod_list.itemChanged.connect(self._on_mod_checked)
        lists.addWidget(self._titled("Mods", self.mod_list), 1)

        self.dep_list = QListWidget()
        lists.addWidget(self._titled("Dependencies", self.dep_list), 1)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhDependencyManager", self))
        self.auto_button = QPushButton("Auto")
        self.auto_button.setToolTip(
            "Work out dependencies from each mod's Neverwinter Vault project page"
        )
        self.auto_button.clicked.connect(self._on_auto)
        buttons.addWidget(self.auto_button)
        buttons.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._refresh_deps()
        if self._groups:
            self.group_list.setCurrentRow(0)

    @staticmethod
    def _titled(title: str, widget: QWidget) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(QLabel(title))
        v.addWidget(widget)
        return box

    # -- Population ------------------------------------------------------- #
    def _on_group(self, row: int) -> None:
        self.mod_list.blockSignals(True)
        self.mod_list.clear()
        if 0 <= row < len(self._groups):
            for name in self._groups[row]["mods"]:
                item = QListWidgetItem(name)
                item.setData(_KEY_ROLE, name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if name in self._deps
                    else Qt.CheckState.Unchecked
                )
                self.mod_list.addItem(item)
        self.mod_list.blockSignals(False)

    def _on_mod_checked(self, item: QListWidgetItem) -> None:
        name = item.data(_KEY_ROLE)
        if item.checkState() == Qt.CheckState.Checked:
            self._deps.add(name)
        else:
            self._deps.discard(name)
        self._refresh_deps()

    def _refresh_deps(self) -> None:
        self.dep_list.clear()
        for name in sorted(self._deps, key=str.lower):
            self.dep_list.addItem(QListWidgetItem(name))

    def _on_auto(self) -> None:
        """Run Auto Mod Dependencies and reload this mod's set from the result."""
        from vaultkeeper.ui.dialogs.dependency_manager import run_auto_dependencies

        if run_auto_dependencies(self._controller, self) is None:
            return
        md = self._controller.pd.mod_item(self._mod_name)
        self._deps = set(md.dependencies) if md is not None else set()
        self._refresh_deps()
        self._sync_checks()

    def _sync_checks(self) -> None:
        """Re-tick the middle list against the dependency set."""
        for row in range(self.mod_list.count()):
            item = self.mod_list.item(row)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.data(_KEY_ROLE) in self._deps
                else Qt.CheckState.Unchecked
            )

    # -- Save ------------------------------------------------------------- #
    def _on_save(self) -> None:
        result = self._controller.set_mod_dependencies(
            self._mod_name, sorted(self._deps, key=str.lower)
        )
        QMessageBox.information(self, "Dependency Manager", result["message"])
        self.accept()

    @classmethod
    def show_for(
        cls, controller, mod_name: str, parent: QWidget | None = None
    ) -> DependencyEditor:
        """Build and show the dependency editor for a mod."""
        dlg = cls(controller, mod_name, parent)
        dlg.show()
        return dlg
