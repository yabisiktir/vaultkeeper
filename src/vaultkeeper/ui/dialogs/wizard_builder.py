"""WizardBuilder — author a mod's Installer Wizard (VB ``WizardBuilder``).

Interactive editor for the wizard NIT presents at install time. The mod's eligible
installer files are listed in a **source list**; the user transfers them (Add ▸▸ /
Add All ▸▸ / ◂◂ Remove) into three target lists — mutually-exclusive **Choices**
(SelectOne), optional **Preferences** (SelectMany, checkable) and files **excluded**
from the installer — edits each entry's **Display Name**, sets the Wizard Title and
the instruction texts, and **Save**s. Built on ``ProfileController.wizard_report`` /
``wizard_source_files`` / ``save_wizard_authoring``, plus the earlier Validate/Delete
actions. Captions come from ``WizardBuilder.Designer.vb``.

Bounded (see the handoff): the source list is the loose-file view (VB
``ExtractType.Files``); the archive-extraction Folders/FolderFiles views and the
download-rules wizard source are deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.wizard import default_display
from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R

#: Data role storing a target/source item's file key (relative path).
_KEY_ROLE = Qt.ItemDataRole.UserRole


class WizardBuilder(QDialog):
    """An editor for a mod's installer-wizard definition."""

    def __init__(self, controller, mod_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mod_name = mod_name
        self.setWindowTitle("Wizard Builder")
        self.setWindowIcon(R.get_icon("witchcraft"))
        geometry.remember(self, "WizardBuilder", 820, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Generate Mod Installer Wizard"))

        form = QFormLayout()
        self.title_edit = QLineEdit()
        form.addRow("Wizard Title", self.title_edit)
        self.select_one_text_edit = QLineEdit()
        form.addRow("Choices prompt", self.select_one_text_edit)
        self.select_many_text_edit = QLineEdit()
        form.addRow("Preferences prompt", self.select_many_text_edit)
        layout.addLayout(form)

        # Main split: source list on the left, the three target lists on the right.
        body = QHBoxLayout()
        layout.addLayout(body, 1)

        source_box = QVBoxLayout()
        source_box.addWidget(QLabel("Items Processed by Installer"))
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        source_box.addWidget(self.source_list, 1)
        body.addLayout(source_box, 1)

        targets = QVBoxLayout()
        body.addLayout(targets, 1)

        # Choices (SelectOne)
        self.choices = self._target_group(
            targets, "Choices (Only one item can be selected)", "one"
        )
        # Preferences (SelectMany) — checkable
        self.preferences = self._target_group(
            targets, "Preferences (Optional items)", "many", checkable=True
        )
        # Exclude from Installer
        self.excludes = self._target_group(
            targets, "Exclude from Installer", "exclude", editable=False
        )

        # Display-name editor for the selected Choices/Preferences item.
        dn = QHBoxLayout()
        dn.addWidget(QLabel("Display Name"))
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setEnabled(False)
        self.display_name_edit.editingFinished.connect(self._on_display_name_edited)
        dn.addWidget(self.display_name_edit, 1)
        layout.addLayout(dn)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhWizardBuilder", self))
        buttons.addStretch(1)
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self._on_validate)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        for btn in (self.validate_button, self.save_button, self.delete_button, close_button):
            buttons.addWidget(btn)
        layout.addLayout(buttons)

        self._selected_target: QListWidget | None = None
        self.refresh()

    # -- Construction helpers --------------------------------------------- #
    def _target_group(
        self,
        parent_layout: QVBoxLayout,
        heading: str,
        kind: str,
        *,
        checkable: bool = False,
        editable: bool = True,
    ) -> QListWidget:
        box = QGroupBox(heading)
        row = QHBoxLayout(box)
        buttons = QVBoxLayout()
        add = QPushButton("Add ▸▸")
        add_all = QPushButton("Add All ▸▸")
        remove = QPushButton("◂◂ Remove")
        buttons.addStretch(1)
        buttons.addWidget(add)
        buttons.addWidget(add_all)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        row.addLayout(buttons)
        target = QListWidget()
        target.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        target._checkable = checkable  # type: ignore[attr-defined]
        target._editable = editable  # type: ignore[attr-defined]
        if editable:
            target.itemSelectionChanged.connect(
                lambda t=target: self._on_target_selected(t)
            )
        row.addWidget(target, 1)
        add.clicked.connect(lambda _=False, t=target: self._add_selected(t))
        add_all.clicked.connect(lambda _=False, t=target: self._add_all(t))
        remove.clicked.connect(lambda _=False, t=target: self._remove_selected(t))
        parent_layout.addWidget(box, 1)
        return target

    # -- Population ------------------------------------------------------- #
    def refresh(self) -> None:
        """(Re)load the wizard + eligible source files for the mod."""
        report = self._controller.wizard_report(self._mod_name)
        self.title_edit.setText(report["title"])
        self.select_one_text_edit.setText(report["select_one_text"])
        self.select_many_text_edit.setText(report["select_many_text"])
        self._extract_archives = report["extract_archives"]
        self.summary.setText(report["summary"])

        self.choices.clear()
        for row in report["choices"]:
            self._add_target_item(self.choices, row["key"], row["display"])
        self.preferences.clear()
        for row in report["preferences"]:
            self._add_target_item(
                self.preferences, row["key"], row["display"], checked=row["checked"]
            )
        self.excludes.clear()
        for name in report["excludes"]:
            self._add_target_item(self.excludes, name, name)

        # Source list = eligible files minus those already in a target list.
        assigned = self._all_target_keys()
        self.source_list.clear()
        for key in self._controller.wizard_source_files(self._mod_name):
            if key.lower() not in assigned:
                self._add_source_item(key)

        has_wizard = report["has_wizard"]
        self.validate_button.setEnabled(has_wizard)
        self.delete_button.setEnabled(has_wizard)
        self.display_name_edit.setEnabled(False)
        self.display_name_edit.clear()

    def _add_source_item(self, key: str) -> None:
        item = QListWidgetItem(key)
        item.setData(_KEY_ROLE, key)
        self.source_list.addItem(item)

    def _add_target_item(
        self, target: QListWidget, key: str, display: str, *, checked: bool = True
    ) -> None:
        item = QListWidgetItem(display)
        item.setData(_KEY_ROLE, key)
        item.setToolTip(key)
        if getattr(target, "_checkable", False):
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
        target.addItem(item)

    # -- Key bookkeeping -------------------------------------------------- #
    def _target_keys(self, target: QListWidget) -> list[str]:
        return [
            target.item(i).data(_KEY_ROLE) for i in range(target.count())
        ]

    def _all_target_keys(self) -> set[str]:
        keys: set[str] = set()
        for target in (self.choices, self.preferences, self.excludes):
            keys.update(k.lower() for k in self._target_keys(target))
        return keys

    # -- Transfer actions (VB MoveItems) ---------------------------------- #
    def _add_selected(self, target: QListWidget) -> None:
        rows = sorted((i.row() for i in self.source_list.selectedIndexes()), reverse=True)
        for row in rows:
            item = self.source_list.takeItem(row)
            key = item.data(_KEY_ROLE)
            display = default_display(key) if getattr(target, "_editable", True) else key
            self._add_target_item(target, key, display)

    def _add_all(self, target: QListWidget) -> None:
        self.source_list.selectAll()
        self._add_selected(target)

    def _remove_selected(self, target: QListWidget) -> None:
        rows = sorted((i.row() for i in target.selectedIndexes()), reverse=True)
        for row in rows:
            item = target.takeItem(row)
            self._add_source_item(item.data(_KEY_ROLE))
        self.source_list.sortItems()
        self.display_name_edit.setEnabled(False)
        self.display_name_edit.clear()

    # -- Display-name editing --------------------------------------------- #
    def _on_target_selected(self, target: QListWidget) -> None:
        self._selected_target = target
        items = target.selectedItems()
        if len(items) == 1:
            self.display_name_edit.setEnabled(True)
            self.display_name_edit.setText(items[0].text())
        else:
            self.display_name_edit.setEnabled(False)
            self.display_name_edit.clear()

    def _on_display_name_edited(self) -> None:
        if self._selected_target is None:
            return
        items = self._selected_target.selectedItems()
        if len(items) == 1:
            text = self.display_name_edit.text().strip()
            if text:
                items[0].setText(text)

    # -- Save / Validate / Delete ----------------------------------------- #
    def _collect(self) -> dict:
        choices = [
            {"key": self.choices.item(i).data(_KEY_ROLE), "display": self.choices.item(i).text()}
            for i in range(self.choices.count())
        ]
        preferences = [
            {
                "key": self.preferences.item(i).data(_KEY_ROLE),
                "display": self.preferences.item(i).text(),
                "checked": self.preferences.item(i).checkState() == Qt.CheckState.Checked,
            }
            for i in range(self.preferences.count())
        ]
        excludes = [self.excludes.item(i).data(_KEY_ROLE) for i in range(self.excludes.count())]
        return {"choices": choices, "preferences": preferences, "excludes": excludes}

    def _on_save(self) -> None:
        """Build + save the wizard from the current lists (VB BtSave)."""
        data = self._collect()
        result = self._controller.save_wizard_authoring(
            self._mod_name,
            title=self.title_edit.text(),
            select_one_text=self.select_one_text_edit.text(),
            select_many_text=self.select_many_text_edit.text(),
            extract_archives=self._extract_archives,
            **data,
        )
        self.summary.setText(result["message"])
        self.refresh()

    def _on_validate(self) -> None:
        """Report how many wizard entries no longer match a real file (VB Validate)."""
        result = self._controller.validate_wizard(self._mod_name)
        self.summary.setText(result["message"])

    def _on_delete(self) -> None:
        """Delete the wizard file after confirmation (VB Delete)."""
        confirm = QMessageBox.question(
            self,
            "Delete Installer Wizard",
            f"Delete the installer wizard for {self._mod_name}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.delete_wizard(self._mod_name)
        self.refresh()
        self.summary.setText(result["message"])

    @classmethod
    def show_for(
        cls, controller, mod_name: str, parent: QWidget | None = None
    ) -> WizardBuilder:
        """Build and show the wizard editor for a mod."""
        dlg = cls(controller, mod_name, parent)
        dlg.show()
        return dlg
