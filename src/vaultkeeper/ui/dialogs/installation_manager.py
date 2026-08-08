"""InstallationManager editor — named installation sets (VB ``InstallationManager*``).

Manage snapshots of which mods are installed: the live **Current** set (read-only),
static **Checkpoint** snapshots, and editable **User** sets. Select a set to see its
groups → mods with their desired install state (a checkbox, editable for user sets) and
each mod's *live* install state. **Apply** installs/uninstalls to reach the selected
set's desired states (VB ``InstallationManagerEditor.BtApply``).

Built on the headless :mod:`vaultkeeper.game.installation_sets` + the controller's
``load_installation_sets`` / ``save_installation_sets`` / ``create_*`` / ``apply_*``.

BOUNDED PORT (noted): the VB editor also lets you add/remove whole groups within a set,
drag to reorder, sort by created/updated date, and import sets; here a set is built from
a checkpoint of installed mods and refined by toggling desired states. Group/mod rename
propagation into saved sets is handled by load-time pruning rather than rewrites.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.installation_sets import (
    SET_CURRENT,
    STATE_INSTALLED,
    STATE_SOME,
    STATE_UNINSTALLED,
)
from vaultkeeper.ui import resources as R

_SET_ROLE = Qt.ItemDataRole.UserRole
_MOD_ROLE = Qt.ItemDataRole.UserRole

_STATE_LABEL = {
    STATE_UNINSTALLED: "Not installed",
    STATE_SOME: "Some installed",
    STATE_INSTALLED: "Installed",
}
_TYPE_LABEL = {"current": "Current", "checkpoint": "Checkpoint", "user": "User set"}


class InstallationManager(QDialog):
    """Create, apply, and manage installation sets."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Installation Manager")
        self.setWindowIcon(R.get_icon("Installed"))
        self.resize(760, 500)

        self._sets: list = []
        self._installed: set[str] = set()
        self._current_set = None  # the selected InstallationSet

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel("Installation sets — snapshots of which mods are installed:")
        )

        body = QHBoxLayout()
        outer.addLayout(body, 1)

        # Left: the set list + create/rename/delete buttons.
        left = QVBoxLayout()
        # VB sorts the set list by Created / Updated / Set Name, ascending or
        # descending (TsCreated / TsUpdated / TsSetName + TsAscending /
        # TsDescending). Sets accumulate, and the one you want is usually the
        # newest — which is exactly the order you cannot get without this.
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort:"))
        self.sort_key = QComboBox()
        for label, key in (("Name", "name"), ("Created", "created"), ("Updated", "updated")):
            self.sort_key.addItem(label, key)
        self.sort_key.currentIndexChanged.connect(lambda *_: self._reload(self._selected_name()))
        sort_row.addWidget(self.sort_key)
        self.sort_desc = QToolButton()
        self.sort_desc.setCheckable(True)
        self.sort_desc.setText("▼")
        self.sort_desc.setToolTip("Descending (newest or last, first)")
        self.sort_desc.toggled.connect(
            lambda checked: (
                self.sort_desc.setText("▲" if checked else "▼"),
                self._reload(self._selected_name()),
            )
        )
        sort_row.addWidget(self.sort_desc)
        sort_row.addStretch(1)
        left.addLayout(sort_row)
        self.set_list = QListWidget()
        self.set_list.currentRowChanged.connect(self._on_set_selected)
        left.addWidget(self.set_list, 1)
        for label, slot in (
            ("New Checkpoint", self._on_new_checkpoint),
            ("New Set", self._on_new_set),
            ("Rename", self._on_rename),
            ("Delete", self._on_delete),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            left.addWidget(btn)
        body.addLayout(left, 2)

        # Right: the selected set's groups -> mods with desired + current states.
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Mod", "Current State"])
        self.tree.itemChanged.connect(self._on_item_changed)
        body.addWidget(self.tree, 3)

        # Reconciliation summary (VB ChangesInfo) — shown when a load pruned sets.
        self._status = QLabel()
        outer.addWidget(self._status)

        # Bottom: apply / save / close.
        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhInstallationManager", self))
        buttons.addStretch(1)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Install/uninstall mods to match this set.")
        self.apply_button.clicked.connect(self._on_apply)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

        self._reload()

    # -- Data / population ------------------------------------------------- #
    def _reload(self, select_name: str | None = None) -> None:
        """Reload the sets from the controller and repopulate the list."""
        self._sets = self._controller.load_installation_sets()
        self._status.setText(self._controller.installation_sets_changes_info())
        self._installed = {
            m for mods in self._controller.installed_by_group().values() for m in mods
        }
        self._sets = self._sorted_sets(self._sets)
        self.set_list.blockSignals(True)
        self.set_list.clear()
        target_row = 0
        for i, iset in enumerate(self._sets):
            state = _STATE_LABEL.get(iset.state(), "")
            item = QListWidgetItem(
                f"{iset.name}  ·  {_TYPE_LABEL.get(iset.set_type, iset.set_type)}  ·  {state}"
            )
            item.setData(_SET_ROLE, iset)
            self.set_list.addItem(item)
            if select_name is not None and iset.name == select_name:
                target_row = i
        self.set_list.blockSignals(False)
        if self.set_list.count():
            self.set_list.setCurrentRow(target_row)

    def _selected_name(self) -> str | None:
        """The selected set's name, so a re-sort can keep it selected."""
        return self._current_set.name if self._current_set is not None else None

    def _sorted_sets(self, sets: list) -> list:
        """Order the sets by the chosen key and direction (VB SortSets).

        The *Current* set stays pinned at the top whatever the sort: it is the
        live state rather than a saved snapshot, and burying it under a date
        order would make the list read as if it were missing.
        """
        key = self.sort_key.currentData() or "name"
        rest = [s for s in sets if s.set_type != SET_CURRENT]
        pinned = [s for s in sets if s.set_type == SET_CURRENT]
        rest.sort(key=lambda s: (getattr(s, key, "") or "", s.name.lower()),
                  reverse=self.sort_desc.isChecked())
        return pinned + rest

    def _on_set_selected(self, row: int) -> None:
        item = self.set_list.item(row) if row >= 0 else None
        iset = item.data(_SET_ROLE) if item is not None else None
        self._current_set = iset
        self._populate_tree(iset)
        # Apply works on any real selection (Rename/Delete guard against the Current set).
        self.apply_button.setEnabled(iset is not None)

    def _populate_tree(self, iset) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        if iset is not None:
            editable = iset.editable
            for group in iset.groups:
                parent = QTreeWidgetItem([group.name, ""])
                parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                self.tree.addTopLevelItem(parent)
                for mod in group.mods:
                    child = QTreeWidgetItem(
                        [mod.name, "Installed" if mod.name in self._installed else "—"]
                    )
                    child.setData(0, _MOD_ROLE, mod)
                    flags = child.flags() | Qt.ItemFlag.ItemIsUserCheckable
                    if not editable:
                        flags &= ~Qt.ItemFlag.ItemIsEnabled
                    child.setFlags(flags)
                    child.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if mod.desired_installed
                        else Qt.CheckState.Unchecked,
                    )
                    parent.addChild(child)
            self.tree.expandAll()
        self.tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        mod = item.data(0, _MOD_ROLE)
        if mod is None:
            return
        checked = item.checkState(0) == Qt.CheckState.Checked
        if self._current_set is not None and self._current_set.editable:
            mod.desired_installed = checked
        elif checked != mod.desired_installed:
            # Read-only set: revert any stray change back to the stored desired state.
            self.tree.blockSignals(True)
            item.setCheckState(
                0, Qt.CheckState.Checked if mod.desired_installed else Qt.CheckState.Unchecked
            )
            self.tree.blockSignals(False)

    # -- Actions ----------------------------------------------------------- #
    def _selected_set(self):
        item = self.set_list.currentItem()
        return item.data(_SET_ROLE) if item is not None else None

    def _on_new_checkpoint(self) -> None:
        name = self._controller.create_installation_checkpoint()
        self._reload(select_name=name)

    def _on_new_set(self) -> None:
        name, ok = QInputDialog.getText(self, "New Installation Set", "Set name:")
        name = name.strip()
        if not ok or not name:
            return
        if any(s.name == name for s in self._sets):
            QMessageBox.warning(self, "New Installation Set", "That name is already used.")
            return
        self._controller.create_installation_set(name)
        self._reload(select_name=name)

    def _on_rename(self) -> None:
        iset = self._selected_set()
        if iset is None or iset.set_type == "current":
            return
        name, ok = QInputDialog.getText(
            self, "Rename Installation Set", "New name:", text=iset.name
        )
        name = name.strip()
        if not ok or not name or name == iset.name:
            return
        self._controller.rename_installation_set(iset.name, name)
        self._reload(select_name=name)

    def _on_delete(self) -> None:
        iset = self._selected_set()
        if iset is None or iset.set_type == "current":
            return
        if (
            QMessageBox.question(self, "Delete Installation Set", f"Delete '{iset.name}'?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._controller.delete_installation_set(iset.name)
        self._reload()

    def _on_save(self) -> None:
        self._controller.save_installation_sets(self._sets)
        QMessageBox.information(self, "Installation Manager", "Installation sets saved.")

    def _on_apply(self) -> None:
        iset = self._selected_set()
        if iset is None:
            return
        # Persist any desired-state edits first (VB BtApply calls SaveSets), then apply.
        self._controller.save_installation_sets(self._sets)
        message = self._controller.apply_installation_set(iset)
        QMessageBox.information(self, "Installation Manager", message)
        self._reload(select_name=iset.name)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> InstallationManager:
        """Build and show the Installation Manager for a controller's profile."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
