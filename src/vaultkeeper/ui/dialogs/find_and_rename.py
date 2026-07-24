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

_DUPLICATE_COLOUR = QColor(200, 0, 0)


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

        profile_name = getattr(getattr(controller, "store_path", None), "stem", "") or ""
        self._profile = QLabel(profile_name)
        font = self._profile.font()
        font.setBold(True)
        self._profile.setFont(font)
        layout.addWidget(self._profile)

        # Find row
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Fin&d:"))
        self._find = QLineEdit()
        self._find.textChanged.connect(self._on_find_changed)
        find_row.addWidget(self._find, 1)
        clear_find = QPushButton("✕")
        clear_find.setFixedWidth(28)
        clear_find.setToolTip("Clear")
        clear_find.clicked.connect(self._find.clear)
        find_row.addWidget(clear_find)
        layout.addLayout(find_row)

        # Replace row
        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel("Replac&e:"))
        self._replace = QLineEdit()
        repl_row.addWidget(self._replace, 1)
        clear_repl = QPushButton("✕")
        clear_repl.setFixedWidth(28)
        clear_repl.setToolTip("Clear")
        clear_repl.clicked.connect(self._replace.clear)
        repl_row.addWidget(clear_repl)
        layout.addLayout(repl_row)

        # Options
        opts = QHBoxLayout()
        self._match_start = QCheckBox("Match &start")
        self._match_start.setChecked(True)
        self._match_start.toggled.connect(self._on_options_changed)
        self._match_case = QCheckBox("&Match case")
        self._match_case.setChecked(False)
        self._match_case.toggled.connect(self._on_options_changed)
        opts.addWidget(self._match_start)
        opts.addWidget(self._match_case)
        opts.addStretch(1)
        layout.addLayout(opts)

        # Replace actions
        actions = QHBoxLayout()
        self._replace_btn = QPushButton("&Replace")
        self._replace_btn.clicked.connect(self._replace_selected)
        self._replace_all_btn = QPushButton("Repla&ce All")
        self._replace_all_btn.clicked.connect(self._replace_all)
        self._undo_all_btn = QPushButton("U&ndo All")
        self._undo_all_btn.clicked.connect(self._undo_all)
        actions.addWidget(self._replace_btn)
        actions.addWidget(self._replace_all_btn)
        actions.addWidget(self._undo_all_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list, 1)

        self._status = QLabel("")
        layout.addWidget(self._status)

        # Bottom bar
        bar = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        bar.addWidget(help_button("TsHelpFindAndRename", self))
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
                item.setForeground(QBrush(_DUPLICATE_COLOUR))
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

    def _on_options_changed(self, *_a: object) -> None:
        self._sync_options()
        self._on_find_changed()

    def _on_find_changed(self, *_a: object) -> None:
        self._sync_options()
        self._model.find(self._find.text())
        self._model.select_found()
        self._refresh_list()

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
