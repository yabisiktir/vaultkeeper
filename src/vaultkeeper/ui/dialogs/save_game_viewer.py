"""Save Game Viewer — browse NWN save games and their module state (read-only).

A new view (no VB equivalent): lists the player's saves and, for the selected one,
shows its screenshot, the module state decoded from the ``.sav``'s ``module.ifo``
(name, description, in-game date/time, XP scale, area list) and a button to open
the save's character in the Character Explorer. Data comes from
:mod:`vaultkeeper.game.save_game`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.save_game import SaveGame, scan_save_games
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap
from vaultkeeper.ui.dialogs.help_viewer import help_button

_SAVE_ROLE = Qt.ItemDataRole.UserRole


class SaveGameViewer(QDialog):
    """Lists save games; shows the selected save's module + character."""

    def __init__(
        self, saves: list[SaveGame], controller=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Game Viewer")
        self.resize(820, 560)
        self._controller = controller
        self._saves = saves
        self._current: SaveGame | None = None
        self._module_cache: dict[str, object] = {}
        self._child_viewer = None  # keep a ref so it isn't garbage-collected

        outer = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        # -- Left: the list of saves ---------------------------------------- #
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(f"<b>Save games ({len(saves)})</b>"))
        self._list = QListWidget()
        self._list.setMinimumWidth(230)
        self._list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self._list, 1)
        split.addWidget(left)

        # -- Right: screenshot + module detail + area list ------------------ #
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self._shot = QLabel()
        self._shot.setFixedSize(180, 135)
        self._shot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._shot.setFrameShape(QFrame.Shape.StyledPanel)
        header.addWidget(self._shot)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        header.addWidget(self._detail, 1)
        right_layout.addLayout(header)
        right_layout.addWidget(QLabel("<b>Areas</b>"))
        self._areas = QListWidget()
        right_layout.addWidget(self._areas, 1)
        split.addWidget(right)
        split.setSizes([250, 570])

        bar = QHBoxLayout()
        bar.addWidget(help_button("BhGameManager", self))
        bar.addStretch(1)
        self._char_btn = QPushButton("View Character…")
        self._char_btn.setEnabled(False)
        self._char_btn.clicked.connect(self._view_character)
        bar.addWidget(self._char_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bar.addWidget(close)
        outer.addLayout(bar)

        for save in saves:
            item = QListWidgetItem(f"{save.name}\n{save.location}" if save.location else save.name)
            item.setData(_SAVE_ROLE, save)
            self._list.addItem(item)
        if saves:
            self._list.setCurrentRow(0)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> SaveGameViewer:
        """Open the viewer over the install's ``saves`` folder."""
        user = getattr(controller.ctx, "game_user_dir", None)
        saves = scan_save_games(user / "saves" if user is not None else None)
        dialog = cls(saves, controller, parent)
        dialog.show()
        return dialog

    def _on_select(self, row: int) -> None:
        item = self._list.item(row) if row >= 0 else None
        save = item.data(_SAVE_ROLE) if item is not None else None
        self._current = save
        self._char_btn.setEnabled(save is not None and save.player_bic is not None)
        self._areas.clear()
        self._shot.clear()
        if save is None:
            self._detail.clear()
            return
        self._show_screenshot(save)
        info = self._module_for(save)
        self._detail.setPlainText(_module_detail(save, info))
        if info is not None:
            for resref, name in info.areas:
                label = f"{name}  ({resref})" if name != resref else resref
                self._areas.addItem(label)

    def _module_for(self, save: SaveGame):
        if save.name not in self._module_cache:
            self._module_cache[save.name] = save.module_info()
        return self._module_cache[save.name]

    def _show_screenshot(self, save: SaveGame) -> None:
        if save.screenshot is None:
            self._shot.setText("(no screenshot)")
            return
        pixmap = tga_to_pixmap(save.screenshot, box=180)
        if pixmap is None:
            self._shot.setText("(no screenshot)")
        else:
            self._shot.setPixmap(pixmap)

    def _view_character(self) -> None:
        save = self._current
        if save is None or save.player_bic is None:
            return
        from vaultkeeper.core.formats.bic_reader import BicFileReader
        from vaultkeeper.game.character import CharacterFile
        from vaultkeeper.game.item_names import resolver_for
        from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer, item_icon_source

        info = BicFileReader().read_file(save.player_bic)
        if info is None:
            return
        game_root = getattr(getattr(self._controller, "ctx", None), "game_root", None)
        resolver_for(game_root).resolve_character(info)
        character = CharacterFile(path=save.player_bic, info=info)
        icon_source = item_icon_source(self._controller) if self._controller else None
        nwn_style = getattr(self._controller._settings(), "inventory_nwn_style", False) \
            if self._controller else False
        self._child_viewer = CharacterViewer(
            [character], parent=self,
            icon_source=icon_source, inventory_nwn_style=nwn_style,
            on_inventory_style_changed=(
                self._controller.set_inventory_nwn_style if self._controller else None
            ),
        )
        self._child_viewer.show()


def _module_detail(save: SaveGame, info) -> str:
    lines = [save.name]
    if save.location:
        lines.append(f"Location: {save.location}")
    if save.saved is not None:
        lines.append(f"Saved: {save.saved:%d %b %Y %H:%M}")
    if info is None:
        lines.append("")
        lines.append("(module state could not be read)")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"Module: {info.name}" + (f"  [{info.tag}]" if info.tag else ""))
    if info.game_time:
        lines.append(f"In-game date: {info.game_time}")
    lines.append(
        f"XP scale: {info.xp_scale}x    "
        f"Time: {info.minutes_per_hour} min/hour, dawn {info.dawn_hour}, dusk {info.dusk_hour}"
    )
    if info.entry_area:
        lines.append(f"Entry area: {info.entry_area}    Min game version: {info.min_game_version}")
    lines.append(f"Players: {info.player_count}    Areas: {len(info.areas)}")
    if info.description:
        lines.append("")
        lines.append(info.description)
    return "\n".join(lines)
