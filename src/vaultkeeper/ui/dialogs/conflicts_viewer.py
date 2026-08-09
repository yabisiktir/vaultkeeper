"""ConflictsViewer — the mod-file conflicts dialog (VB ``FileConflictsViewer``).

Every game file that more than one mod's **installer** maps onto, the mod that
would own it (the highest priority, which is the last in Mod List order) and the
full set of claimants, from ``ProfileController.conflicts_report``.

``msconflicts.htm`` gives the dialog three scope buttons — **Selected**,
**Installed**, **All** — because the useful question changes: what the mods I am
about to install will do to each other, what is clashing on disk right now, and
what the whole collection would do if it were all installed at once.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
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

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button


class ConflictsViewer(QDialog):
    """A read-only table of file conflicts and their winning mod."""

    def __init__(
        self,
        report: dict,
        controller=None,
        selected: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._selected = list(selected or [])

        self.setWindowTitle("Mod File Conflicts")
        self.setWindowIcon(R.get_icon("Overridden"))
        geometry.remember(self, "ConflictsViewer", 640, 440)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Files that more than one mod's installer lays down. The winning "
            "mod is the highest priority — the last one in the Mod List — and "
            "the others are overridden by it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["File", "Winner", "Conflicting Mods"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.summary = QLabel("")
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("ManageModFileConflicts", self))
        # The three scopes the topic names, in its order.
        from vaultkeeper.ui.controller import ProfileController as _PC

        self.scope_buttons = {}
        for label, scope in (
            ("Selected", _PC.CONFLICTS_SELECTED),
            ("Installed", _PC.CONFLICTS_INSTALLED),
            ("All", _PC.CONFLICTS_ALL),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, s=scope: self.show_scope(s))
            button.setEnabled(controller is not None)
            self.scope_buttons[scope] = button
            buttons.addWidget(button)
        # Nothing selected means the Selected scope has nothing to say.
        self.scope_buttons[_PC.CONFLICTS_SELECTED].setEnabled(
            controller is not None and bool(self._selected)
        )
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate(report)

    # -- Rendering --------------------------------------------------------- #
    def _populate(self, report: dict) -> None:
        self.table.clear()
        for row in report.get("rows", []):
            others = ", ".join(m for m in row["mods"] if m != row["winner"])
            self.table.addTopLevelItem(
                QTreeWidgetItem([row["file"], row["winner"], others])
            )

        scope = report.get("scope", "")
        for name, button in self.scope_buttons.items():
            button.setChecked(name == scope)

        count = report.get("count", 0)
        across = f" across {report.get('mods', 0):,} mod(s)" if scope else ""
        self.summary.setText(
            f"{count:,} file(s) with conflicts{across}."
            if count
            else f"No file conflicts{across}."
        )

    def show_scope(self, scope: str) -> None:
        """Re-run the analysis for one of the three scopes."""
        if self._controller is None:
            return
        self._populate(self._controller.conflicts_report(scope, self._selected))

    @classmethod
    def show_for(
        cls,
        controller,
        selected: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> ConflictsViewer:
        """Build and show the viewer.

        Opens on **Selected** when mods are selected — "typically, you would
        select one mod to view its file conflicts" — and on All otherwise.
        """
        scope = (
            controller.CONFLICTS_SELECTED if selected else controller.CONFLICTS_ALL
        )
        report = controller.conflicts_report(scope, selected)
        dlg = cls(report, controller, selected, parent)
        dlg.show()
        return dlg
