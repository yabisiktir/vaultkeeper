"""CharacterViewer — the Character Explorer / Character Summary dialog (VB CharacterViewer).

Lists the player's characters (local vault + one per game save) on the left and
shows the selected character's multi-line summary plus portrait on the right.
Read-only. Data comes from ``ProfileController.character_files`` /
``portrait_path``; the summary text is produced by ``game.character``.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.character import level_summary

# The Qt conversions live with the save editor: nwnfile decodes images but
# stays free of Qt, and Vaultkeeper depends on the editor, not the reverse.
from nwnsaveeditor.ui.icons import (  # noqa: F401 - re-exported for callers
    item_icon_source,
    tga_to_pixmap,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.character_filter import CharacterLevelFilter
from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button
from vaultkeeper.ui.dialogs.inventory_view import InventoryView

_CHAR_ROLE = Qt.ItemDataRole.UserRole
_PORTRAIT_BOX = 128  # px — default fallback box for the portrait preview.

#: Portrait preview box size (px) per VB ``ConfigPortraitDisplaySize`` — the VB
#: ``Defs.PicSizes`` widths H=256 / L=128 / M=64 (portraits are taller than wide, so
#: the image scales to fit within a box of this size keeping its aspect ratio).
PORTRAIT_SIZES = {"Huge": 256, "Large": 128, "Medium": 64}
DEFAULT_PORTRAIT_SIZE = "Huge"


def portrait_box(name: str) -> int:
    """The preview box size (px) for a ``ConfigPortraitDisplaySize`` value."""
    return PORTRAIT_SIZES.get(name, PORTRAIT_SIZES[DEFAULT_PORTRAIT_SIZE])


class CharacterViewer(QDialog):
    """Browse characters with their summary and portrait."""

    def __init__(
        self,
        characters: list,
        portrait_resolver=None,
        parent: QWidget | None = None,
        *,
        portrait_size: str = DEFAULT_PORTRAIT_SIZE,
        icon_source=None,
        inventory_nwn_style: bool = False,
        on_inventory_style_changed=None,
        filter_skills_by_rank: bool = False,
        on_skills_filter_changed=None,
        on_open_portrait_manager=None,
    ) -> None:
        super().__init__(parent)
        self._filter_skills_by_rank = filter_skills_by_rank
        self._on_skills_filter_changed = on_skills_filter_changed
        self._on_open_portrait_manager = on_open_portrait_manager
        self._icon_source = icon_source
        self._inventory_nwn_style = inventory_nwn_style
        self._on_inventory_style_changed = on_inventory_style_changed
        self.setWindowIcon(R.get_icon("LookupUser_16x"))
        geometry.remember(self, "CharacterViewer", 680, 460)
        self._characters = characters
        self._resolve_portrait = portrait_resolver
        #: Portrait preview box (px) from Settings.portrait_display_size (VB PicSizes).
        self._portrait_box = portrait_box(portrait_size)
        # Level/class filter (VB LcbFilter -> CharacterFilter); default shows all.
        self._filter = CharacterLevelFilter()
        self._filter_text = "1"
        self._descriptions: dict[int, str] = {}

        outer = QVBoxLayout(self)
        layout = QHBoxLayout()
        outer.addLayout(layout, 1)

        # Left column: the level/class filter button (VB "Show all Levels") + a
        # name-search box (VB "Search Names") above the character list.
        left = QVBoxLayout()
        self._filter_btn = QPushButton(self._filter.label())
        self._filter_btn.setToolTip("Filter characters by level and/or class.")
        self._filter_btn.clicked.connect(self._on_filter)
        left.addWidget(self._filter_btn)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search Names")  # VB InactiveSearchText
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _=None: self._populate_list())
        # VB: "Press the Escape key to close the search box."
        self._search.installEventFilter(self)
        left.addWidget(self._search)
        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_row)
        left.addWidget(self._list, 1)
        layout.addLayout(left)

        right = QVBoxLayout()
        self._portrait = QLabel()
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait.setFixedHeight(self._portrait_box)
        # VB PicPortrait_Click / CmOpenPortraitManager: clicking the portrait
        # opens the Portrait Manager, and the cursor says so. Only offered when
        # the host supplied a way to open it.
        if on_open_portrait_manager is not None:
            self._portrait.setCursor(Qt.CursorShape.PointingHandCursor)
            self._portrait.setToolTip("Open in Portrait Manager")
            self._portrait.mouseReleaseEvent = self._on_portrait_clicked
        right.addWidget(self._portrait)

        self._tabs = QTabWidget()
        self._summary = QTextEdit()
        self._summary.setReadOnly(True)
        self._tabs.addTab(self._summary, "Summary")
        self._tabs.addTab(self._build_skills_tab(), "Skills")
        self._tabs.addTab(self._build_feats_tab(), "Feats")
        self._tabs.addTab(self._build_spells_tab(), "Spells")
        self._inventory = InventoryView(
            icon_source=self._icon_source,
            nwn_style=self._inventory_nwn_style,
            on_style_changed=self._on_inventory_style_changed,
        )
        self._tabs.addTab(self._inventory, "Inventory")
        right.addWidget(self._tabs, 1)
        layout.addLayout(right, 1)

        # Bottom bar: help + match count + copy actions + Close.
        bar = QHBoxLayout()
        # VB CharacterViewer help button → HelpFile.Open("MsCharacterViewer").
        bar.addWidget(help_button("MsCharacterViewer", self))
        self._count_label = QLabel()
        bar.addWidget(self._count_label)
        bar.addStretch(1)
        # One image-only clipboard button with the two copies under it, as the
        # original has them (VB TsClipboard → TsCopyDetails / TsCopyLevel, with
        # the CopyOffice2016 icon). Two labelled push buttons were not a port.
        self._clipboard_btn = QToolButton()
        self._clipboard_btn.setIcon(R.get_icon("CopyOffice2016"))
        self._clipboard_btn.setToolTip("Copy to the Clipboard")
        self._clipboard_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._clipboard_btn)
        self._copy_details_action = menu.addAction(
            R.get_icon("CopyPagesArrow_16x"),
            "Copy Summary Details to the Clipboard",
            self._on_copy_details,
        )
        self._copy_level_action = menu.addAction(
            R.get_icon("CopyPageArrow_16x"),
            "Copy Level Summary to the Clipboard",
            self._on_copy_level,
        )
        self._clipboard_btn.setMenu(menu)
        bar.addWidget(self._clipboard_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        outer.addLayout(bar)
        self._current_cf = None

        self._populate_list()
        if not characters:
            self._summary.setPlainText("No character files detected.")

    def _populate_list(self) -> None:
        """(Re)fill the list, applying the name search and level/class filter."""
        needle = self._search.text().strip().lower()
        self._list.blockSignals(True)
        self._list.clear()
        shown = 0
        for cf in self._characters:
            # The .bic file name, as VB lists it (its column is titled "Files" and
            # each row is FileInfo.Name). Showing the *character* name instead made
            # the list unusable on a real profile: one of the owner's holds 36
            # files under 3 distinct names, so it read as a screen of identical
            # rows — and a filter that cut it to 16 looked like it had done
            # nothing at all.
            if needle and needle not in self._searchable(cf):
                continue
            if not self._passes_filter(cf):
                continue
            item = QListWidgetItem(cf.path.name)
            item.setToolTip(self._row_tooltip(cf))
            item.setData(_CHAR_ROLE, cf)
            self._list.addItem(item)
            shown += 1
        self._list.blockSignals(False)
        total = len(self._characters)
        filtered = bool(needle) or not self._filter.is_default
        self._count_label.setText(
            f"{shown:,} of {total:,} shown" if filtered else f"{total:,} character(s)"
        )
        self._update_title(shown, total, filtered)
        if shown:
            self._list.setCurrentRow(0)
        else:
            self._on_row(-1)

    def _update_title(self, shown: int, total: int, filtered: bool) -> None:
        """Window title with the (filtered) file count (VB ``TitleText``)."""
        files = "file" if total == 1 else "files"
        if not total:
            self.setWindowTitle("Character Explorer")
        elif filtered:
            self.setWindowTitle(f"Character Explorer — {shown:,} of {total:,} {files} shown")
        else:
            self.setWindowTitle(f"Character Explorer — {total:,} {files} shown")

    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        """Escape clears the name search (VB ``LsbCharacters.EscapeSearch``)."""
        from PySide6.QtCore import QEvent

        if (
            watched is self._search
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
            and self._search.text()
        ):
            self._search.clear()
            return True  # swallowed: Escape must not also close the dialog
        return super().eventFilter(watched, event)

    @staticmethod
    def _searchable(cf) -> str:
        """What the name search looks in: the file name *and* the character name.

        VB's search box drives the list view, so it matches what the list shows —
        the file name. Ours also accepts the character name, because a file is
        usually named after its character but not always, and somebody typing
        "Morcan" expects to find it either way. A superset cannot hide a row the
        original would have shown.
        """
        return f"{cf.path.name}\n{cf.display_name}".lower()

    @staticmethod
    def _row_tooltip(cf) -> str:
        """VB shows the owning mod on hover; the name and level cost nothing more."""
        level = cf.info.level if cf.info.is_valid else "?"
        parts = [f"{cf.display_name} (level {level})"]
        mod = getattr(cf, "mod_name", "")
        if mod:
            parts.append(mod)
        parts.append(str(cf.path))
        return "\n".join(parts)

    def _passes_filter(self, cf) -> bool:
        """True if ``cf`` satisfies the current level/class filter (VB ApplyClassFilter)."""
        if self._filter.is_default:
            return True
        level = cf.info.level if cf.info.is_valid else 1
        # The class filter needs the summary text; only build it when classes are set.
        description = self._description(cf) if self._filter.class_names else ""
        return self._filter.matches(level, description)

    def _description(self, cf) -> str:
        """Cached character summary text used for class-name matching."""
        key = id(cf)
        if key not in self._descriptions:
            self._descriptions[key] = cf.summary() if cf.info.is_valid else ""
        return self._descriptions[key]

    def _on_filter(self) -> None:
        """Open the level/class filter dialog and apply the result (VB LbcFilter_Click)."""
        from nwnfile.character import pc_class_names

        from vaultkeeper.ui.dialogs.character_filter import CharacterFilter

        dlg = CharacterFilter(
            pc_class_names(),
            level_text=self._filter_text,
            checked_classes=self._filter.class_names,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # VB persists the stripped filter text and re-seeds the dialog with it.
        self._filter_text = dlg.level_text.replace(" ", "").replace(">", "")
        self._filter = CharacterLevelFilter.parse(dlg.level_text, dlg.class_names)
        self._filter_btn.setText(self._filter.label())
        self._populate_list()

    def _build_skills_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        # VB CbRanked, remembered in FilterSkillsByRank. A PRC character carries
        # around forty skills and has ranks in a handful, so the unranked ones
        # are mostly noise.
        self._ranked_only = QCheckBox("Only show Ranked Skills")
        self._ranked_only.setChecked(self._filter_skills_by_rank)
        self._ranked_only.toggled.connect(self._on_ranked_only)
        top_layout.addWidget(self._ranked_only)
        self._skills = QTreeWidget()
        self._skills.setHeaderLabels(["Skill", "Rank"])
        self._skills.setRootIsDecorated(False)
        self._skills.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._skills.currentItemChanged.connect(self._on_skill)
        top_layout.addWidget(self._skills, 1)
        splitter.addWidget(top)
        self._skill_desc = QTextEdit()
        self._skill_desc.setReadOnly(True)
        splitter.addWidget(self._skill_desc)
        splitter.setSizes([260, 120])
        return splitter

    def _on_portrait_clicked(self, _event) -> None:
        """Hand off to the Portrait Manager (VB closes this window and opens it)."""
        if self._on_open_portrait_manager is None:
            return
        cf = self._current_cf
        resref = cf.info.portrait_resref if cf is not None and cf.info.is_valid else ""
        self._on_open_portrait_manager(resref)
        self.accept()

    def _on_ranked_only(self, checked: bool) -> None:
        """Re-fill the skills list and remember the choice (VB CbRanked)."""
        self._filter_skills_by_rank = checked
        if self._on_skills_filter_changed is not None:
            self._on_skills_filter_changed(checked)
        if self._current_cf is not None:
            self._fill_skills(self._current_cf)

    def _fill_skills(self, cf) -> None:
        """Skill rows for ``cf``, hiding rank-0 entries when asked (VB GetFilteredSkills)."""
        self._skills.clear()
        self._skill_desc.clear()
        rows = cf.skills() if cf.info.is_valid else []
        if self._filter_skills_by_rank:
            rows = [row for row in rows if row[1]]
        self._skill_rows = rows
        for name, rank, _desc in rows:
            self._skills.addTopLevelItem(QTreeWidgetItem([name, str(rank)]))

    def _build_feats_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._feats = QListWidget()
        self._feats.currentRowChanged.connect(self._on_feat)
        splitter.addWidget(self._feats)
        self._feat_desc = QTextEdit()
        self._feat_desc.setReadOnly(True)
        splitter.addWidget(self._feat_desc)
        splitter.setSizes([260, 120])
        return splitter

    def _build_spells_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._spells = QListWidget()
        self._spells.currentRowChanged.connect(self._on_spell)
        splitter.addWidget(self._spells)
        self._spell_desc = QTextEdit()
        self._spell_desc.setReadOnly(True)
        splitter.addWidget(self._spell_desc)
        splitter.setSizes([260, 120])
        return splitter

    def _on_row(self, row: int) -> None:
        item = self._list.item(row) if row >= 0 else None
        cf = item.data(_CHAR_ROLE) if item is not None else None
        self._current_cf = cf
        has = cf is not None
        self._clipboard_btn.setEnabled(has)
        if cf is None:
            self._summary.clear()
            self._portrait.clear()
            self._skills.clear()
            self._feats.clear()
            self._spells.clear()
            self._skill_desc.clear()
            self._feat_desc.clear()
            self._spell_desc.clear()
            self._inventory.clear()
            return
        self._summary.setPlainText(cf.summary(show_stats=True))
        self._show_portrait(cf)
        self._populate_skills_and_feats(cf)
        self._inventory.set_character(cf.info)

    def _on_copy_details(self) -> None:
        """Copy the selected character's full summary to the clipboard (VB TsCopyDetails)."""
        if self._current_cf is not None:
            QApplication.clipboard().setText(self._current_cf.summary(show_stats=True))

    def _on_copy_level(self) -> None:
        """Copy the selected character's class/level line (VB TsCopyLevel).

        The bare summary — "Level 12 (Fighter 8, Rogue 4)" — because that is what
        VB puts on the clipboard (``LbInfo.Tag``, set from ``BicFileInfo``'s
        ``LevelSummary``). This used to prepend the character's name, which
        nothing in the original does and which is one more thing to delete after
        pasting.
        """
        cf = self._current_cf
        if cf is not None:
            QApplication.clipboard().setText(level_summary(cf.info))

    def _populate_skills_and_feats(self, cf) -> None:
        self._skills.clear()
        self._skill_desc.clear()
        self._feats.clear()
        self._feat_desc.clear()
        self._spells.clear()
        self._spell_desc.clear()
        self._fill_skills(cf)
        self._feat_rows = cf.feats() if cf.info.is_valid else []
        for name, _desc in self._feat_rows:
            self._feats.addItem(name)
        self._spell_rows = cf.spells() if cf.info.is_valid else []
        for name, _desc, level in self._spell_rows:
            self._spells.addItem(f"{name}  (Level {level})" if level is not None else name)
        if self._skill_rows:
            self._skills.setCurrentItem(self._skills.topLevelItem(0))
        if self._feat_rows:
            self._feats.setCurrentRow(0)
        if self._spell_rows:
            self._spells.setCurrentRow(0)

    def _on_skill(self, current, _previous=None) -> None:
        row = self._skills.indexOfTopLevelItem(current) if current is not None else -1
        if 0 <= row < len(getattr(self, "_skill_rows", [])):
            self._skill_desc.setPlainText(self._skill_rows[row][2])
        else:
            self._skill_desc.clear()

    def _on_feat(self, row: int) -> None:
        if 0 <= row < len(getattr(self, "_feat_rows", [])):
            self._feat_desc.setPlainText(self._feat_rows[row][1])
        else:
            self._feat_desc.clear()

    def _on_spell(self, row: int) -> None:
        if 0 <= row < len(getattr(self, "_spell_rows", [])):
            self._spell_desc.setPlainText(self._spell_rows[row][1])
        else:
            self._spell_desc.clear()

    def _show_portrait(self, cf) -> None:
        self._portrait.clear()
        resref = cf.info.portrait_resref if cf.info.is_valid else ""
        if not resref or self._resolve_portrait is None:
            return
        path = self._resolve_portrait(resref, cf.path.parent)
        if path is not None:
            pixmap = tga_to_pixmap(path, box=self._portrait_box)
            if pixmap is not None:
                self._portrait.setPixmap(pixmap)

    @classmethod
    def show_for(
        cls,
        controller,
        parent: QWidget | None = None,
        *,
        on_open_portrait_manager=None,
    ) -> CharacterViewer:
        """Build and show the viewer from a controller's character files."""

        def resolver(resref: str, own_folder: Path):
            return controller.portrait_path(resref, extra_dirs=[own_folder])

        settings = controller._settings()
        dlg = cls(
            controller.character_files(),
            resolver,
            parent,
            portrait_size=settings.portrait_display_size,
            icon_source=item_icon_source(controller),
            inventory_nwn_style=settings.inventory_nwn_style,
            on_inventory_style_changed=controller.set_inventory_nwn_style,
            filter_skills_by_rank=settings.filter_skills_by_rank,
            on_skills_filter_changed=controller.set_filter_skills_by_rank,
            on_open_portrait_manager=on_open_portrait_manager,
        )
        dlg.show()
        return dlg


