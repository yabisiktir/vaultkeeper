"""DependencyManager — the mod dependency dialog (VB ``DependencyManager``).

Lists each mod's declared dependencies and the mods that require it, from
``ProfileController.dependencies_report`` (the ProfileData dependency graph),
and carries **Auto** (VB ``BtAuto``), which works the whole list out from the
mods' Vault project pages. Without Auto this table starts empty and stays that
way, because nothing else in the tool ever writes a dependency by itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
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

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button


class DependencyManager(QDialog):
    """A table of mod dependencies, with Auto to work them out."""

    def __init__(self, report: dict, controller=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Dependency Manager")
        self.setWindowIcon(R.get_icon("DependencyGraph_16x"))
        geometry.remember(self, "DependencyManager", 640, 440)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Mod dependencies: which mods each mod depends on, and which mods require "
            "it. Installing a mod also installs what it depends on."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Mod", "Depends On", "Required By"])
        self.table.setRootIsDecorated(False)
        header = self.table.header()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._populate(report)
        layout.addWidget(self.table)

        count = report.get("count", 0)
        self.summary = QLabel(
            f"{count:,} mod(s) with dependencies."
            if count
            else "No dependencies recorded yet — run Auto to work them out."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhDependencyManager", self))
        self.auto_button = QPushButton("Auto")
        self.auto_button.setToolTip(
            "Work out dependencies from each mod's Neverwinter Vault project page"
        )
        self.auto_button.clicked.connect(self._on_auto)
        buttons.addWidget(self.auto_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _populate(self, report: dict) -> None:
        self.table.clear()
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        row["mod"],
                        ", ".join(row["depends_on"]),
                        ", ".join(row["required_by"]),
                    ]
                )
            )

    def _on_auto(self) -> None:
        if self._controller is None:
            return
        result = run_auto_dependencies(self._controller, self)
        if result is None:
            return
        self._populate(self._controller.dependencies_report())
        self.summary.setText(result["message"])

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> DependencyManager:
        dlg = cls(controller.dependencies_report(), controller, parent)
        dlg.show()
        return dlg


#: VB explains what Auto does before running it rather than just doing it: it is
#: a page fetch per mod, and it *replaces* what is recorded. Both are worth
#: knowing in advance.
_AUTO_EXPLANATION = (
    "Dependencies name the other mods a mod needs to play (CEP, for example).\n\n"
    "Every mod that has a Neverwinter Vault project link will have its page — and "
    "its required-projects list — read, which takes a moment per mod.\n\n"
    "What this finds replaces the dependencies already recorded for those mods."
    "\n\nDo you want to proceed?"
)


def run_auto_dependencies(controller, parent) -> dict | None:
    """Confirm, run Auto Mod Dependencies, and report. ``None`` if declined.

    Shared so the report and the per-mod editor put the same question and give
    the same account of the answer.
    """
    if (
        QMessageBox.question(
            parent,
            "Auto Mod Dependencies",
            _AUTO_EXPLANATION,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        != QMessageBox.StandardButton.Yes
    ):
        return None

    from PySide6.QtWidgets import QApplication

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        result = controller.auto_mod_dependencies()
    finally:
        QApplication.restoreOverrideCursor()

    # What could not be matched is the useful part of the answer: a requirement
    # naming a mod you do not have is a mod you are missing, not a failure.
    if result["unmatched"] or result["errors"]:
        from vaultkeeper.ui.dialogs.text_viewer import TextViewer

        lines = ["Requirements naming a mod that is not in this profile:", ""]
        lines += result["unmatched"] or ["  (none)"]
        if result["errors"]:
            lines += ["", "Pages that could not be read:", *result["errors"]]
        parent._auto_report = TextViewer.show_text(
            "\n".join(lines), "Auto Mod Dependencies", parent
        )
    return result
