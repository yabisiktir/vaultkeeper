"""FindAndRenameDialog — bulk find/replace over mod names (VB ``ModFindAndRename``).

Lists every mod name; type a *find* string to select matching names, a *replace*
string, then **Replace** / **Replace All** to rewrite the working names in bulk
(bold = changed, red = would-duplicate).  **Apply** renames every changed,
non-colliding mod through ``ProfileController.apply_mod_renames``.

Faithful to the VB dialog's control set and Match-start / Match-case coupling
(see ``vaultkeeper.game.find_rename``).  Divergence: the VB virtual ListView with
per-item found-index navigation (Find Next) is rendered as a plain selectable
list — Find selects all matches at once instead of stepping through them.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
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

from vaultkeeper.game.find_rename import ModRenameSet
from vaultkeeper.ui.theme import status_colour


def _duplicate_colour() -> QColor:
    return status_colour("duplicate")


class FindAndRenameDialog(QDialog):
    """Find-and-replace mod names in bulk (VB ModFindAndRename)."""

    def __init__(
        self,
        controller,
        on_applied: Callable[[dict], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_applied = on_applied
        self._model: ModRenameSet = controller.mod_rename_set()
        self.setWindowTitle("Find and Rename Mods")
        self.resize(480, 520)

        layout = QVBoxLayout(self)

        # Find row + Match start (VB: checkboxes sit to the right of the fields).
        find_row = QHBoxLayout()
        self._find = QLineEdit()
        find_label = QLabel("Fin&d:")
        find_label.setBuddy(self._find)
        find_row.addWidget(find_label)
        self._find.textChanged.connect(self._on_find_changed)
        find_row.addWidget(self._find, 1)
        clear_find = QPushButton("✕")
        clear_find.setFixedWidth(28)
        clear_find.setToolTip("Clear")
        clear_find.clicked.connect(self._find.clear)
        find_row.addWidget(clear_find)
        self._match_start = QCheckBox("Match &start")
        self._match_start.setChecked(True)
        self._match_start.toggled.connect(self._on_options_changed)
        find_row.addWidget(self._match_start)
        layout.addLayout(find_row)

        # Replace row + Match case.
        repl_row = QHBoxLayout()
        self._replace = QLineEdit()
        repl_label = QLabel("Replac&e:")
        repl_label.setBuddy(self._replace)
        repl_row.addWidget(repl_label)
        repl_row.addWidget(self._replace, 1)
        clear_repl = QPushButton("✕")
        clear_repl.setFixedWidth(28)
        clear_repl.setToolTip("Clear")
        clear_repl.clicked.connect(self._replace.clear)
        repl_row.addWidget(clear_repl)
        self._match_case = QCheckBox("&Match case")
        self._match_case.setChecked(False)
        self._match_case.toggled.connect(self._on_options_changed)
        repl_row.addWidget(self._match_case)
        layout.addLayout(repl_row)

        # Action toolbar row: Find Next | Replace | Replace All | Undo | Undo All … [?]
        actions = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        self._find_next_btn = QPushButton("&Find Next")
        self._find_next_btn.clicked.connect(self._find_next)
        self._replace_btn = QPushButton("&Replace")
        self._replace_btn.clicked.connect(self._replace_selected)
        self._replace_all_btn = QPushButton("Repla&ce All")
        self._replace_all_btn.clicked.connect(self._replace_all)
        self._undo_btn = QPushButton("&Undo")
        self._undo_btn.clicked.connect(self._undo_selected)
        self._undo_all_btn = QPushButton("U&ndo All")
        self._undo_all_btn.clicked.connect(self._undo_all)
        for btn in (
            self._find_next_btn,
            self._replace_btn,
            self._replace_all_btn,
            self._undo_btn,
            self._undo_all_btn,
        ):
            actions.addWidget(btn)
        actions.addStretch(1)
        actions.addWidget(help_button("TsHelpFindAndRename", self))
        layout.addLayout(actions)

        # Profile name (VB: bold label above the list).
        profile_name = getattr(getattr(controller, "store_path", None), "stem", "") or ""
        self._profile = QLabel(profile_name)
        pfont = self._profile.font()
        pfont.setBold(True)
        self._profile.setFont(pfont)
        layout.addWidget(self._profile)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # Double-click a mod to load its name into both boxes (VB
        # LvMods_MouseDoubleClick): the quickest way to rename one thing, which
        # is what a find-and-replace over names is usually being used for.
        self._list.itemDoubleClicked.connect(self._on_mod_double_clicked)
        layout.addWidget(self._list, 1)

        self._status = QLabel("")
        layout.addWidget(self._status)

        # Bottom bar: Apply / Cancel (right-aligned).
        bar = QHBoxLayout()
        bar.addStretch(1)
        self._apply_btn = QPushButton("&Apply")
        self._apply_btn.clicked.connect(self._apply)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(self._apply_btn)
        bar.addWidget(cancel)
        layout.addLayout(bar)

        self._refresh_list()

    # -- rendering -------------------------------------------------------- #
    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for entry in self._model.entries:
            item = QListWidgetItem(entry.new_name)
            if entry.changed:
                f = item.font()
                f.setWeight(QFont.Weight.Bold)
                item.setFont(f)
            if entry.duplicated:
                item.setForeground(QBrush(_duplicate_colour()))
            self._list.addItem(item)
            item.setSelected(entry.selected)
        self._list.blockSignals(False)
        self._update_status()

    def _update_status(self) -> None:
        total = len(self._model.entries)
        found = self._model.found_count
        dups = self._model.duplicate_count
        parts = [f"Mods: {total}", f"Found: {found or 'None'}"]
        if dups:
            parts.append(f"Duplicate Mod names generated: {dups}.")
        self._status.setText("   ".join(parts))
        self._apply_btn.setEnabled(bool(self._model.renames))

    # -- events ----------------------------------------------------------- #
    def _sync_options(self) -> None:
        self._model.match_start = self._match_start.isChecked()
        self._model.match_case = self._match_case.isChecked()

    def _on_mod_double_clicked(self, item) -> None:
        """Put the double-clicked mod's name into Find and Replace (VB ``LvMods``)."""
        name = (item.text() or "").strip()
        if not name:
            return
        self._find.setText(name)
        self._replace.setText(name)

    def _on_options_changed(self, *_a: object) -> None:
        self._sync_options()
        self._on_find_changed()

    def _on_find_changed(self, *_a: object) -> None:
        self._sync_options()
        self._model.find(self._find.text())
        self._model.select_found()
        self._refresh_list()

    def _find_next(self) -> None:
        """Step the selection to the next matching mod name (VB Find Next)."""
        self._sync_options()
        self._model.find(self._find.text())
        index = self._model.find_next()
        if index is None:
            return
        self._list.clearSelection()
        item = self._list.item(index)
        if item is not None:
            item.setSelected(True)
            self._list.setCurrentItem(item)
            self._list.scrollToItem(item)
        self._update_status()

    def _selected_indices(self) -> list[int]:
        return [self._list.row(i) for i in self._list.selectedItems()]

    def _replace_selected(self) -> None:
        self._sync_options()
        # Re-run the find so the found set matches the current find box, then
        # restrict the replacement to the user's current selection.
        self._model.find(self._find.text())
        self._model.replace_all(self._replace.text(), self._selected_indices())
        self._refresh_list()

    def _replace_all(self) -> None:
        self._sync_options()
        self._model.find(self._find.text())
        self._model.replace_all(self._replace.text())
        self._refresh_list()

    def _undo_selected(self) -> None:
        """Revert the selected mods' working names to their originals (VB Undo)."""
        for i in self._selected_indices():
            self._model.undo_one(i)
        self._refresh_list()

    def _undo_all(self) -> None:
        self._model.reset()
        self._refresh_list()

    def _apply(self) -> None:
        renames = self._model.renames
        if not renames:
            self.reject()
            return
        report = self._controller.apply_mod_renames(renames)
        if self._on_applied is not None:
            self._on_applied(report)
        renamed = len(report.get("renamed", []))
        failed = len(report.get("failed", []))
        msg = f"Renamed {renamed} mod(s)."
        if failed:
            msg += f" Failures: {failed}."
        QMessageBox.information(self, "Find and Rename Mods", msg)
        self.accept()

    @classmethod
    def show_for(cls, controller, on_applied=None, parent=None) -> FindAndRenameDialog:
        dlg = cls(controller, on_applied, parent)
        dlg.show()
        return dlg
