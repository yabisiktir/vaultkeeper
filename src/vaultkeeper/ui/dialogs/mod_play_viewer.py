"""ModPlayViewer — mods sorted by date completed (VB ``ModPlayViewer``).

A tabular view of every mod that has a module file, ordered from the oldest last
date completed. Selecting a mod reveals its group, best weapon, web link, notes
and per-user play-time history. Built on ``ProfileController.mod_play_report``.

Carries the VB *filter options* toolbar: a **Filters…** button opens the shared
Group + Rating include/exclude dialog (VB ``CommonFiltersDialogue``), plus an
Only-completed toggle, a Min-end-level box and its companion "include mods with
no end level" (VB ``TsShowNoEndLevel``), without which a minimum empties the list
for everything that never recorded one. Select, Add to Recent and Copy Name drive
the main window through callbacks, from the buttons or the row menu (VB
``BtSelect`` / ``BtRecent`` / ``CmCopyName``).
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.state import State
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button
from vaultkeeper.ui.file_view import icon_name_for_state

_ROW_ROLE = Qt.ItemDataRole.UserRole


def _end_level(row: dict) -> int:
    """Leading integer of a row's End column ("40", "Lvl 40", ""); 0 if none."""
    m = re.match(r"\s*(\d+)", str(row.get("end", "")))
    return int(m.group(1)) if m else 0


class ModPlayViewer(QDialog):
    """A read-only table of mods ordered by last date completed."""

    def __init__(
        self,
        report: dict,
        parent: QWidget | None = None,
        *,
        on_select=None,
        on_add_recent=None,
    ) -> None:
        super().__init__(parent)
        self._on_select = on_select
        self._on_add_recent = on_add_recent
        self.setWindowTitle("Mods Sorted by Date Completed")
        self.setWindowIcon(R.get_icon("Time_Green_16x"))
        self.resize(760, 560)

        self._rows = report.get("rows", [])
        # Include/exclude filter state (VB CommonFiltersDialogue); all included by default.
        self._groups = sorted({r["group"] for r in self._rows if r.get("group")})
        self._ratings = sorted(
            {r["rating"] for r in self._rows if str(r.get("rating", "")).strip()}
        )
        self._group_filters: dict[str, bool] = {g: True for g in self._groups}
        self._rating_filters: dict[str, bool] = {r: True for r in self._ratings}

        layout = QVBoxLayout(self)
        # VB heading (ModPlayViewer.Designer LbHeading).
        heading = QLabel(
            "List of Mods sorted by the last date the Mod was completed and ordered "
            "from the oldest to the most recent. You may find this list useful when "
            "choosing which Mod you want to replay."
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        # -- Filter options (VB filter toolbar) ----------------------------- #
        filters = QHBoxLayout()
        self.filters_button = QPushButton("Filters…")
        self.filters_button.clicked.connect(self._open_filters)
        filters.addWidget(self.filters_button)
        self._filter_summary = QLabel("")
        filters.addWidget(self._filter_summary)
        self.only_completed = QCheckBox("Only completed")
        self.only_completed.stateChanged.connect(self._populate_mods)
        filters.addWidget(self.only_completed)
        filters.addWidget(QLabel("Min end level:"))
        self.min_end = QLineEdit()
        self.min_end.setValidator(QIntValidator(0, 60, self))
        self.min_end.setFixedWidth(48)
        self.min_end.setClearButtonEnabled(True)
        self.min_end.textChanged.connect(self._populate_mods)
        filters.addWidget(self.min_end)
        # VB TsShowNoEndLevel: a minimum level otherwise hides every mod that
        # never recorded one, which is most of them until you have played a few.
        self.show_no_end = QCheckBox("Include mods with no end level")
        self.show_no_end.setChecked(True)
        self.show_no_end.stateChanged.connect(self._populate_mods)
        filters.addWidget(self.show_no_end)
        filters.addStretch(1)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # -- Mod list (top) ------------------------------------------------- #
        self.mods = QTreeWidget()
        self.mods.setHeaderLabels(
            ["Mod Name", "Completed", "Time Played", "Rating", "Start", "End"]
        )
        self.mods.setRootIsDecorated(False)
        self.mods.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.mods.currentItemChanged.connect(self._on_selection)
        self.mods.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mods.customContextMenuRequested.connect(self._on_context_menu)
        splitter.addWidget(self.mods)

        # -- Detail (bottom) ------------------------------------------------ #
        detail = QWidget()
        dlayout = QVBoxLayout(detail)
        dlayout.setContentsMargins(0, 0, 0, 0)
        self.group_label = QLabel()
        self.weapon_label = QLabel()
        self.link_label = QLabel()
        self.link_label.setOpenExternalLinks(True)
        self.played_label = QLabel()
        self.played_label.setWordWrap(True)
        for w in (self.group_label, self.weapon_label, self.link_label, self.played_label):
            dlayout.addWidget(w)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        dlayout.addWidget(self.notes, 1)

        self.times = QTreeWidget()
        self.times.setHeaderLabels(["Completed", "Time Played", "User"])
        self.times.setRootIsDecorated(False)
        dlayout.addWidget(self.times, 1)
        splitter.addWidget(detail)
        splitter.setSizes([340, 220])

        # -- Summary -------------------------------------------------------- #
        self._summary_prefix = report.get("summary", "0/0")
        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhModsPlayed", self))
        buttons.addStretch(1)
        self.select_button = QPushButton("Select")
        self.select_button.setIcon(R.get_icon("SelectAll"))
        self.select_button.setToolTip("Select this mod in the main window")
        self.select_button.clicked.connect(self._on_select_mod)
        buttons.addWidget(self.select_button)
        self.recent_button = QPushButton("Add to Recent")
        self.recent_button.setIcon(R.get_icon("History_16x"))
        self.recent_button.setToolTip("Add this mod to the Recent Mods list")
        self.recent_button.clicked.connect(self._on_add_to_recent)
        buttons.addWidget(self.recent_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate_mods()

    def _open_filters(self) -> None:
        """Open the shared Group + Rating include/exclude dialog (VB CommonFiltersDialogue)."""
        from vaultkeeper.ui.dialogs.common_filters import CommonFiltersDialog

        dlg = CommonFiltersDialog(
            self._groups,
            self._ratings,
            self._group_filters,
            self._rating_filters,
            self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._group_filters = dlg.group_filters()
            self._rating_filters = dlg.rating_filters()
            self._populate_mods()

    def _update_filter_summary(self) -> None:
        gsel = sum(1 for v in self._group_filters.values() if v)
        rsel = sum(1 for v in self._rating_filters.values() if v)
        parts = []
        if self._groups and gsel < len(self._groups):
            parts.append(f"Groups: {gsel}/{len(self._groups)}")
        if self._ratings and rsel < len(self._ratings):
            parts.append(f"Ratings: {rsel}/{len(self._ratings)}")
        self._filter_summary.setText("  ".join(parts))

    def _populate_mods(self, *_args) -> None:
        """Fill the mod list, applying the group / rating / only-completed filters."""
        only_completed = self.only_completed.isChecked()
        min_end = int(self.min_end.text()) if self.min_end.text().strip() else 0
        self.mods.clear()
        shown = 0
        for row in self._rows:
            group = row.get("group")
            if group and not self._group_filters.get(group, True):
                continue
            rating = str(row.get("rating", "")).strip()
            if rating and not self._rating_filters.get(rating, True):
                continue
            if only_completed and not row.get("completed"):
                continue
            if min_end:
                level = _end_level(row)
                if level == 0 and not self.show_no_end.isChecked():
                    continue
                if level and level < min_end:
                    continue
            item = QTreeWidgetItem(
                [
                    row["mod"],
                    row["completed"],
                    row["play_time"],
                    row["rating"],
                    row["start"],
                    row["end"],
                ]
            )
            item.setIcon(0, R.get_icon(icon_name_for_state(State(row["state"]))))
            item.setToolTip(0, row["played_info"])
            item.setData(0, _ROW_ROLE, row)
            self.mods.addTopLevelItem(item)
            shown += 1
        self.summary.setText(
            f"Shown: {shown:,}    Mods (installed/total): {self._summary_prefix}"
        )
        self._update_filter_summary()
        if shown:
            self.mods.setCurrentItem(self.mods.topLevelItem(0))

    def _on_selection(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        self._update_row_actions()
        if current is None:
            return
        row = current.data(0, _ROW_ROLE)
        if row is None:
            return
        self.group_label.setText(f"Group: {row['group']}")
        self.weapon_label.setText(f"Best Weapon: {row['best_weapon']}")
        if row["web_link"]:
            self.link_label.setText(
                f'<a href="{row["web_link"]}">{row["web_link"]}</a>'
            )
        else:
            self.link_label.setText("")
        self.played_label.setText(row["played_info"] or "No Play Time history recorded.")
        self.notes.setText(row["notes"])

        self.times.clear()
        for pt in row.get("play_times", []):
            self.times.addTopLevelItem(
                QTreeWidgetItem([pt["completed"], pt["play_time"], pt["user"]])
            )

    # -- Row actions (VB BtSelect / BtRecent / CmCopyName) ----------------- #
    def _current_mod(self) -> str:
        item = self.mods.currentItem()
        return item.text(0) if item is not None else ""

    def _on_select_mod(self) -> None:
        name = self._current_mod()
        if name and self._on_select is not None:
            self._on_select(name)
            self.accept()

    def _on_add_to_recent(self) -> None:
        name = self._current_mod()
        if name and self._on_add_recent is not None:
            self._on_add_recent(name)

    def _on_copy_name(self) -> None:
        from PySide6.QtWidgets import QApplication

        name = self._current_mod()
        if name:
            QApplication.clipboard().setText(name)

    def _on_context_menu(self, point) -> None:
        """The row actions, as VB offers them from CmModsPlayed."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        has_row = bool(self._current_mod())
        menu = QMenu(self)
        select = menu.addAction(R.get_icon("SelectAll"), "Select in the main window")
        select.setEnabled(has_row and self._on_select is not None)
        select.triggered.connect(self._on_select_mod)
        recent = menu.addAction(R.get_icon("History_16x"), "Add to Recent Mods")
        recent.setEnabled(has_row and self._on_add_recent is not None)
        recent.triggered.connect(self._on_add_to_recent)
        copy = menu.addAction(R.get_icon("CopyName"), "Copy Name")
        copy.setEnabled(has_row)
        copy.triggered.connect(self._on_copy_name)
        menu.exec(self.mods.viewport().mapToGlobal(point) if point else QCursor.pos())

    def _update_row_actions(self) -> None:
        has_row = bool(self._current_mod())
        self.select_button.setEnabled(has_row and self._on_select is not None)
        self.recent_button.setEnabled(has_row and self._on_add_recent is not None)

    @classmethod
    def show_for(
        cls,
        controller,
        parent: QWidget | None = None,
        *,
        on_select=None,
        on_add_recent=None,
    ) -> ModPlayViewer:
        """Build and show the viewer for a controller's mod-play report."""
        dlg = cls(
            controller.mod_play_report(),
            parent,
            on_select=on_select,
            on_add_recent=on_add_recent,
        )
        dlg.show()
        return dlg
