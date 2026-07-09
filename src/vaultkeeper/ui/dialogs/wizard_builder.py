"""WizardBuilder — view a mod's Installer Wizard (VB ``WizardBuilder``).

Shows the wizard defined for a mod: its title, whether archives are extracted, the
mutually-exclusive **Choices** (SelectOne), the optional **Preferences** (SelectMany,
with default checked state) and the files **excluded** from the installer. Built on
``ProfileController.wizard_report``.

Shows the wizard and exposes two of the VB authoring actions: **Validate** (VB
``Validate`` — report how many entries no longer point at a real mod file) and
**Delete** (VB ``Delete`` — remove the wizard file). The add/remove-between-lists
editing surface and Save-from-edits are still deferred — see the handoff. Window
title, heading and column captions come from ``WizardBuilder.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class WizardBuilder(QDialog):
    """A read-only view of a mod's installer-wizard definition."""

    def __init__(self, controller, mod_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mod_name = mod_name
        self.setWindowTitle("Wizard Builder")
        self.setWindowIcon(R.get_icon("witchcraft"))
        self.resize(680, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Generate Mod Installer Wizard"))

        form = QFormLayout()
        self.title_label = QLabel()
        self.extract_label = QLabel()
        form.addRow("Wizard Title", self.title_label)
        form.addRow("Extract Archives", self.extract_label)
        layout.addLayout(form)

        self.choices = self._make_list("Choices (Only one item can be selected)")
        self.preferences = self._make_list("Preferences (Optional items)")
        self.excludes = self._make_list("Exclude from Installer")
        layout.addWidget(self.choices, 1)
        layout.addWidget(self.preferences, 1)
        layout.addWidget(self.excludes, 1)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self._on_validate)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()

    @staticmethod
    def _make_list(heading: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels([heading, "File"])
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return tree

    def refresh(self) -> None:
        """(Re)load the wizard for the mod."""
        report = self._controller.wizard_report(self._mod_name)
        self.title_label.setText(report["title"])
        self.extract_label.setText("Yes" if report["extract_archives"] else "No")
        self.summary.setText(report["summary"])

        self.choices.clear()
        for row in report["choices"]:
            self.choices.addTopLevelItem(
                QTreeWidgetItem([row["display"], row["key"]])
            )
        self.preferences.clear()
        for row in report["preferences"]:
            state = "on" if row["checked"] else "off"
            self.preferences.addTopLevelItem(
                QTreeWidgetItem([f"{row['display']} ({state})", row["key"]])
            )
        self.excludes.clear()
        for name in report["excludes"]:
            self.excludes.addTopLevelItem(QTreeWidgetItem([name, name]))

        has_wizard = report["has_wizard"]
        self.validate_button.setEnabled(has_wizard)
        self.delete_button.setEnabled(has_wizard)

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
        """Build and show the wizard view for a mod."""
        dlg = cls(controller, mod_name, parent)
        dlg.show()
        return dlg
