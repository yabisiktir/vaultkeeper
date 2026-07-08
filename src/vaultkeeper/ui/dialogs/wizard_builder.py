"""WizardBuilder — view a mod's Installer Wizard (VB ``WizardBuilder``).

Shows the wizard defined for a mod: its title, whether archives are extracted, the
mutually-exclusive **Choices** (SelectOne), the optional **Preferences** (SelectMany,
with default checked state) and the files **excluded** from the installer. Built on
``ProfileController.wizard_report``.

Read-only. The VB form is a full authoring tool (add/remove files between the mod's
contents and each list, edit display names, Save/Delete the wizard, validate against
the real files/archives); that editing surface is deferred — see the handoff. Window
title, heading and column captions come from ``WizardBuilder.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
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

    @classmethod
    def show_for(
        cls, controller, mod_name: str, parent: QWidget | None = None
    ) -> WizardBuilder:
        """Build and show the wizard view for a mod."""
        dlg = cls(controller, mod_name, parent)
        dlg.show()
        return dlg
