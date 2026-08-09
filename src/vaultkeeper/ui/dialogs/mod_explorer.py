"""ModExplorer — the all-mods table dialog (VB ``ModExplorer``).

A sortable table of every mod with its group, state, rating, file count, play time
and completed count, from ``ProfileController.mod_explorer_report``.

The filter bar carries the VB subsystem: a name/group search, a state combo, an
only-completed toggle, a rating **comparison** (=, worse than, better than —
VB ``CmEqual``/``CmGreater``/``CmLess``), Clear Text Filters, and a Filters…
dialog for the group and rating include/exclude sets. The row menu offers Select,
Copy Names, Add to Recent Mods and Show the mod's folder (VB ``CmExplorer``).

Two parts of the VB subsystem are **not** ported, and neither is a UI omission:
the *notes* filter has nothing to filter, since ``ModData`` carries no notes
field, and the *prefix* filters belong to a mod-name prefix feature this port
does not have. Both need a domain change first, not a widget.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button

#: The three attribute filters, in the original's toolbar order, keyed by the
#: setting each persists to (VB My.Settings.FilterModFiles / …Installers /
#: …Restorers). Captions and tooltips are the VB button's own.
_ATTRIBUTE_FILTERS = [
    (
        "filter_mod_files",
        "Mod Files",
        "Check to only include Mods that have\n.mod or .nwm files",
    ),
    (
        "filter_installers",
        "Installers",
        "Check to include Mods that have Installers\n(ie has a Mod Installer folder)",
    ),
    ("filter_restorers", "Restorers", "Check to include Mod Restorers"),
]

_HEADERS = [
    "Mod", "Group", "State", "Rating", "Files", "Time Played", "Completed",
    # VB ChWeapon / ChStart / ChEnd / ChHench.
    "Weapon", "Start", "End", "Hench",
]


def _passes_number(value, filter_text: str) -> bool:
    """VB ``FilterNumber``, stated positively.

    The text is a number optionally prefixed with ``>``, ``=`` or ``<``; a bare
    number means "greater than", and a bare operand means "-1", the value shown
    as a hyphen for *not recorded*. VB writes the test as an exclusion; this is
    the same rule the other way round, which is how the tooltip describes it.
    """
    text = (filter_text or "").strip()
    if not text or value is None:
        return True
    operand, rest = (text[0], text[1:]) if text[0] in "><=" else (">", text)
    try:
        wanted = int(rest) if rest.strip() else -1
    except ValueError:
        return True  # not a number yet: do not filter mid-typing
    if operand == "=":
        return value == wanted
    if operand == "<":
        return value < wanted
    return value > wanted


class ModExplorer(QDialog):
    """A sortable, read-only table of all mods with a filter bar."""

    def __init__(
        self,
        report: dict,
        on_select=None,
        parent: QWidget | None = None,
        *,
        on_add_recent=None,
        mods_dir=None,
        controller=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Mod Explorer")
        self.setWindowIcon(R.get_icon("Mod Explorer 1"))
        self.resize(760, 500)
        self._rows = list(report.get("rows", []))
        self._on_select = on_select
        self._on_add_recent = on_add_recent
        self._mods_dir = mods_dir
        # Group + Rating include/exclude filter state (VB CommonFiltersDialogue);
        # all included by default.
        self._groups = sorted({r["group"] for r in self._rows if r.get("group")})
        self._ratings = sorted(
            {r["rating"] for r in self._rows if str(r.get("rating", "")).strip()}
        )
        # VB persists the *excluded* groups to GroupNameFilters.txt and re-reads
        # them each time the Explorer opens, so a filter you set survives the
        # session — which is what makes "Undo Group Changes" mean anything.
        hidden = set(controller.group_filter_excludes()) if controller else set()
        # Name-prefix filters (VB LvPrefixFilters / FilterPrefixList), persisted
        # in settings. An *unticked* prefix hides mods whose name starts with it.
        self._prefix_filters: list[dict] = list(
            controller._settings().mod_prefix_filters if controller else []
        )
        self._group_filters: dict[str, bool] = {g: g not in hidden for g in self._groups}
        self._rating_filters: dict[str, bool] = {r: True for r in self._ratings}

        layout = QVBoxLayout(self)

        # Filter bar (VB filter toolbar): name search + state + only-completed inline,
        # plus a Filters… button for the shared Group + Rating include/exclude dialog.
        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by mod or group name…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._populate)
        bar.addWidget(self._search, 1)
        # State, with the comparison VB offers (TsStateLess / TsStateEqual /
        # TsStateGreater). The State enum runs from "no installer" up through
        # partly-installed to overridden, so "more files installed" really is a
        # greater ordinal — which is the only way to ask "what is half-installed?"
        bar.addWidget(QLabel("State:"))
        self._state_op = QComboBox()
        for label, op in (
            ("matching", "="),
            ("more files installed than", ">"),
            ("less files installed than", "<"),
        ):
            self._state_op.addItem(label, op)
        self._state_op.currentIndexChanged.connect(self._populate)
        bar.addWidget(self._state_op)
        self._state = QComboBox()
        self._state.addItem("All states", "")
        known = {r["state"]: r.get("state_value", 0) for r in self._rows if r["state"]}
        for state, _value in sorted(known.items(), key=lambda kv: kv[1]):
            self._state.addItem(state, state)
        self._state.currentIndexChanged.connect(self._populate)
        bar.addWidget(self._state)
        self._only_completed = QCheckBox("Completed only")
        self._only_completed.stateChanged.connect(self._populate)
        bar.addWidget(self._only_completed)

        # Rating comparison (VB CmEqual / CmGreater / CmLess). The ratings are an
        # ordinal enum whose numbers run best-to-worst — Excellent is 1 and
        # Abandoned is 7 — so ">" reads as "worse than", which is why the labels
        # say so rather than leaving a bare symbol to be guessed at.
        bar.addWidget(QLabel("Rating:"))
        self._rating_op = QComboBox()
        for label, op in (("any", ""), ("is", "="), ("worse than", ">"), ("better than", "<")):
            self._rating_op.addItem(label, op)
        self._rating_op.currentIndexChanged.connect(self._populate)
        bar.addWidget(self._rating_op)
        self._rating_value = QComboBox()
        for rating in self._ratings:
            self._rating_value.addItem(rating, rating)
        self._rating_value.currentIndexChanged.connect(self._populate)
        bar.addWidget(self._rating_value)

        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(R.get_icon("CancelGrey"))
        self._clear_btn.setToolTip("Clear the text filters (VB Clear Text Filters)")
        self._clear_btn.clicked.connect(self._on_clear_filters)
        bar.addWidget(self._clear_btn)

        # The numeric filters VB puts beside the name box (TxStart / TxEnd /
        # TxHench) and the weapon text filter (TxWeapon). Each accepts a bare
        # number, or one prefixed with > = < — see _passes_number.
        for attr, label, width in (
            ("_start_filter", "Start", 52),
            ("_end_filter", "End", 52),
            ("_hench_filter", "Hench", 52),
        ):
            bar.addWidget(QLabel(f"{label}:"))
            box = QLineEdit()
            box.setFixedWidth(width)
            box.setPlaceholderText(">0")
            box.setToolTip(
                f"{label} level filter: a number, optionally prefixed with "
                f"> = or < (a bare number means 'greater than')."
            )
            box.textChanged.connect(self._populate)
            setattr(self, attr, box)
            bar.addWidget(box)

        self._weapon_filter = QLineEdit()
        self._weapon_filter.setPlaceholderText("Weapon")
        self._weapon_filter.setFixedWidth(90)
        self._weapon_filter.textChanged.connect(self._populate)
        bar.addWidget(self._weapon_filter)

        self._filters_btn = QPushButton("Filters…")
        self._filters_btn.setIcon(R.get_icon("Filter_16x"))
        self._filters_btn.setToolTip("Include/exclude by group and rating")
        self._filters_btn.clicked.connect(self._open_filters)
        bar.addWidget(self._filters_btn)

        self._undo_groups_btn = QPushButton()
        self._undo_groups_btn.setIcon(R.get_icon("Undo_16x"))
        self._undo_groups_btn.setToolTip("Undo Group Changes — revert to the saved group filter")
        self._undo_groups_btn.clicked.connect(self._on_undo_group_filters)
        bar.addWidget(self._undo_groups_btn)

        self._undo_prefix_btn = QPushButton()
        self._undo_prefix_btn.setIcon(R.get_icon("Undo_16x"))
        self._undo_prefix_btn.setToolTip(
            "Undo Prefix Changes — revert to the saved name-prefix filters"
        )
        self._undo_prefix_btn.clicked.connect(self._on_undo_prefix_filters)
        bar.addWidget(self._undo_prefix_btn)

        # The attribute filters (VB TsModFiles / TsInstallers / TsRestorers),
        # carrying the original's own Checked/Unchecked images rather than a Qt
        # check box, because that is what the button looks like in the tool.
        settings = controller._settings() if controller else None
        self._attributes: dict[str, QPushButton] = {}
        for key, caption, tip in _ATTRIBUTE_FILTERS:
            on = getattr(settings, key, True) if settings is not None else True
            btn = QPushButton(caption)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setChecked(bool(on))
            btn.toggled.connect(lambda checked, b=None, k=key: self._on_attribute_toggled(k))
            self._attributes[key] = btn
            bar.addWidget(btn)
            self._show_attribute(key)

        # Filters On/Off (VB TsIgnoreFilters) — one switch that suspends every
        # filter at once, so you can see the whole list without unpicking them.
        self._ignore_filters = False
        self._ignore_btn = QPushButton()
        self._ignore_btn.setToolTip(
            "Filters Off: All current filters are ignored.\n"
            "Filters On: All current filters are applied."
        )
        self._ignore_btn.clicked.connect(self._on_toggle_ignore_filters)
        bar.addWidget(self._ignore_btn)
        self._show_ignore_filters()
        layout.addLayout(bar)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(_HEADERS)
        self.table.setRootIsDecorated(False)
        self.table.setSortingEnabled(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

        self._count_label = QLabel()
        layout.addWidget(self._count_label)

        # Bottom bar: help (VB TsHelpExplorer) + Copy Names + Select + Close.
        buttons = QHBoxLayout()
        buttons.addWidget(help_button("TsHelpExplorer", self))
        buttons.addStretch(1)
        copy_names = QPushButton("Copy Names")
        copy_names.clicked.connect(self._on_copy_names)
        buttons.addWidget(copy_names)
        select = QPushButton("Select")
        select.clicked.connect(self._on_select_mod)
        buttons.addWidget(select)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate()

    def _open_filters(self) -> None:
        """Open the shared Group + Rating include/exclude dialog (VB CommonFiltersDialogue)."""
        from vaultkeeper.ui.dialogs.common_filters import CommonFiltersDialog

        dlg = CommonFiltersDialog(
            self._groups,
            self._ratings,
            self._group_filters,
            self._rating_filters,
            self,
            prefixes=self._prefix_filters,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._group_filters = dlg.group_filters()
            self._rating_filters = dlg.rating_filters()
            self._prefix_filters = dlg.prefix_filters()
            self._save_prefix_filters()
            self._populate()

    def _on_attribute_toggled(self, key: str) -> None:
        self._show_attribute(key)
        self._save_attribute_filters()
        self._populate()

    def _show_attribute(self, key: str) -> None:
        """Ticked/unticked, drawn with the original's own two images."""
        btn = self._attributes[key]
        btn.setIcon(R.get_icon("Checked" if btn.isChecked() else "Unchecked"))

    def _on_toggle_ignore_filters(self) -> None:
        self._ignore_filters = not self._ignore_filters
        self._show_ignore_filters()
        self._populate()

    def _show_ignore_filters(self) -> None:
        """VB shows the *state* on the button: "Filters On" when they apply."""
        on = not self._ignore_filters
        self._ignore_btn.setText(f"Filters {'On' if on else 'Off'}")
        self._ignore_btn.setIcon(R.get_icon("Checked" if on else "Unchecked"))

    def _save_attribute_filters(self) -> None:
        """Persist the three toggles (VB writes them to My.Settings on close)."""
        if self._controller is None:
            return
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings(self._controller._settings_path)
        for key, btn in self._attributes.items():
            setattr(settings, key, btn.isChecked())
        save_settings(settings, self._controller._settings_path)

    def _passes_attributes(self, row: dict) -> bool:
        """The three attribute filters, with VB's exact asymmetries.

        Ticking Installers narrows the list to mods that *have* an installer;
        unticking it hides the ones that *are* an installer — two different
        tests on the same switch, which is what the original does (NotFiltered).
        """
        # A row that does not record an attribute is not hidden by it: these
        # filters exclude on evidence, and absent evidence is not evidence.
        if self._attributes["filter_mod_files"].isChecked() and not row.get(
            "playable", True
        ):
            return False
        installers = self._attributes["filter_installers"].isChecked()
        if installers and not row.get("has_installer", True):
            return False
        if not installers and row.get("is_installer"):
            return False
        restorers = self._attributes["filter_restorers"].isChecked()
        return not (not restorers and row.get("is_restorer"))

    def _passes(self, row: dict) -> bool:
        # Filters Off shows everything, filters intact (VB NotFiltered's first test).
        if self._ignore_filters:
            return True
        if not self._passes_attributes(row):
            return False
        query = self._search.text().strip().lower()
        if query and query not in row["mod"].lower() and query not in row["group"].lower():
            return False
        if not self._passes_state(row):
            return False
        weapon = self._weapon_filter.text().strip().lower()
        if weapon and weapon not in str(row.get("weapon", "")).lower():
            return False
        for box, key in (
            (self._start_filter, "start_value"),
            (self._end_filter, "end_value"),
            (self._hench_filter, "hench_value"),
        ):
            if not _passes_number(row.get(key), box.text()):
                return False
        group = row.get("group")
        if group and not self._group_filters.get(group, True):
            return False
        rating = str(row.get("rating", "")).strip()
        if rating and not self._rating_filters.get(rating, True):
            return False
        name = row["mod"].lower()
        for entry in self._prefix_filters:
            prefix = str(entry.get("prefix", "")).lower()
            if prefix and not entry.get("included", True) and name.startswith(prefix):
                return False
        if not self._passes_rating_comparison(rating):
            return False
        return not (self._only_completed.isChecked() and not row["completed"])

    def _passes_state(self, row: dict) -> bool:
        """Compare the row's state with the chosen one (VB ``FilterState``).

        VB writes this as an *exclusion*: with ``<`` it drops anything whose
        state is greater than or equal to the chosen one, and so on. Stated
        positively it is the plain comparison, which is what the labels say.
        """
        want = self._state.currentData()
        if not want:
            return True
        chosen = self._state_values().get(want)
        value = row.get("state_value")
        if chosen is None or value is None:
            return row["state"] == want  # no ordinal available: exact match
        operand = self._state_op.currentData()
        if operand == "=":
            return value == chosen
        if operand == ">":
            return value > chosen
        return value < chosen

    def _state_values(self) -> dict[str, int]:
        return {r["state"]: r.get("state_value", 0) for r in self._rows if r["state"]}

    def _passes_rating_comparison(self, rating: str) -> bool:
        """Compare against the chosen rating with =, > or < (VB CmOperand_Click).

        VB stores the filter as operand-plus-rating ("&gt;Good") and compares the
        ``Ratings`` ordinals. Those run best to worst — ``EXCELLENT`` is 1 and
        ``ABANDONED`` is 7 — so a *greater* ordinal is a *worse* rating, which is
        what the combo's wording says out loud.
        """
        operand = self._rating_op.currentData()
        wanted = self._rating_value.currentData()
        if not operand or not wanted:
            return True
        order = self._rating_order()
        if rating not in order or wanted not in order:
            return False  # unrated rows drop out once a comparison is asked for
        left, right = order[rating], order[wanted]
        if operand == "=":
            return left == right
        if operand == ">":
            return left > right
        return left < right

    @staticmethod
    def _rating_order() -> dict[str, int]:
        """Rating label → ordinal, from the domain enum rather than the display list."""
        from vaultkeeper.core.state import Ratings

        return {name.title(): member.value for name, member in Ratings.__members__.items()}

    def _populate(self, *_args) -> None:
        self.table.setSortingEnabled(False)
        self.table.clear()
        shown = 0
        for row in self._rows:
            if not self._passes(row):
                continue
            shown += 1
            item = QTreeWidgetItem(
                [
                    row["mod"],
                    row["group"],
                    row["state"],
                    row["rating"],
                    f"{row['files']:,}",
                    row["played"],
                    f"{row['completed']:,}" if row["completed"] else "",
                    row.get("weapon", ""),
                    row.get("start", ""),
                    row.get("end", ""),
                    row.get("hench", ""),
                ]
            )
            item.setData(4, Qt.ItemDataRole.UserRole, row["files"])
            item.setData(6, Qt.ItemDataRole.UserRole, row["completed"])
            self.table.addTopLevelItem(item)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        total = len(self._rows)
        self._count_label.setText(
            f"{shown:,} of {total:,} mod(s)." if shown != total else f"{total:,} mod(s)."
        )

    def _save_group_filters(self) -> None:
        """Persist the hidden groups (VB writes these on the form closing)."""
        if self._controller is None:
            return
        self._controller.save_group_filter_excludes(
            sorted(g for g, shown in self._group_filters.items() if not shown)
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._save_group_filters()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        # Qt dialogs usually finish through done(), not closeEvent, so the save
        # hangs off both — otherwise clicking Close silently loses the filter.
        self._save_group_filters()
        super().done(result)

    def _save_prefix_filters(self) -> None:
        """Persist the prefix list (VB ``SavePrefixFilters``, into My.Settings)."""
        if self._controller is None:
            return
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings(self._controller._settings_path)
        settings.mod_prefix_filters = list(self._prefix_filters)
        save_settings(settings, self._controller._settings_path)

    def _on_undo_prefix_filters(self) -> None:
        """Revert the prefix list to the saved one (VB ``TsUndoPrefix``)."""
        if self._controller is None:
            return
        self._prefix_filters = list(self._controller._settings().mod_prefix_filters)
        self._populate()

    def _on_undo_group_filters(self) -> None:
        """Revert the group filter to the saved set (VB ``TsUndoGroups``)."""
        if self._controller is None:
            return
        hidden = set(self._controller.group_filter_excludes())
        self._group_filters = {g: g not in hidden for g in self._groups}
        self._populate()

    def _on_clear_filters(self) -> None:
        """Reset the text filters, leaving the include/exclude sets (VB TsClearTextFilters)."""
        self._search.clear()
        self._state.setCurrentIndex(0)
        self._state_op.setCurrentIndex(0)
        for box in (self._start_filter, self._end_filter, self._hench_filter):
            box.clear()
        self._weapon_filter.clear()
        self._rating_op.setCurrentIndex(0)
        self._only_completed.setChecked(False)
        self._populate()

    def _on_context_menu(self, point) -> None:
        """The row actions, as VB offers them from CmExplorer."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        current = self.table.currentItem()
        menu = QMenu(self)
        select = menu.addAction(R.get_icon("SelectAll"), "Select in the main window")
        select.setEnabled(current is not None and self._on_select is not None)
        select.triggered.connect(self._on_select_mod)

        copy = menu.addAction(R.get_icon("CopyName"), "Copy Names")
        copy.setEnabled(bool(self.table.selectedItems()))
        copy.triggered.connect(self._on_copy_names)

        recent = menu.addAction(R.get_icon("History_16x"), "Add to Recent Mods")
        recent.setEnabled(current is not None and self._on_add_recent is not None)
        recent.triggered.connect(self._on_add_to_recent)

        menu.addSeparator()
        reveal = menu.addAction(R.get_icon("Mod Explorer 1"), "Show the mod's folder")
        reveal.setEnabled(current is not None and self._mods_dir is not None)
        reveal.triggered.connect(self._on_reveal_folder)

        menu.addSeparator()
        clear = menu.addAction(R.get_icon("CancelGrey"), "Clear Text Filters")
        clear.triggered.connect(self._on_clear_filters)
        menu.exec(self.table.viewport().mapToGlobal(point) if point else QCursor.pos())

    def _on_add_to_recent(self) -> None:
        current = self.table.currentItem()
        if current is not None and self._on_add_recent is not None:
            self._on_add_recent(current.text(0))

    def _on_reveal_folder(self) -> None:
        """Open the selected mod's folder in the file manager (VB CmExplorer)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        current = self.table.currentItem()
        if current is None or self._mods_dir is None:
            return
        folder = self._mods_dir / current.text(0)
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_copy_names(self) -> None:
        """Copy selected mod names to clipboard, one per line."""
        names = []
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            if item and item.isSelected():
                names.append(item.text(0))
        if names:
            QApplication.clipboard().setText("\n".join(names))

    def _on_select_mod(self) -> None:
        """Jump to the selected mod in the main window and close."""
        if not self._on_select:
            return
        current = self.table.currentItem()
        if current:
            self._on_select(current.text(0))
            self.accept()

    @classmethod
    def show_for(
        cls,
        controller,
        on_select=None,
        parent: QWidget | None = None,
        *,
        on_add_recent=None,
    ) -> ModExplorer:
        dlg = cls(
            controller.mod_explorer_report(),
            on_select,
            parent,
            on_add_recent=on_add_recent,
            mods_dir=controller.ctx.profile_mods_dir,
            controller=controller,
        )
        dlg.show()
        return dlg
