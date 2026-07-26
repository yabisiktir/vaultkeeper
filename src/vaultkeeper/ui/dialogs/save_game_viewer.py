"""Save Game Viewer — browse NWN save games and their module state (read-only).

A new view (no VB equivalent): lists the player's saves and, for the selected one,
shows its screenshot, the module state decoded from the ``.sav``'s ``module.ifo``
(name, description, in-game date/time, XP scale) and a browsable tree of each
area's *contents* — stores (with pricing + stock), creatures (with their gear),
placeable containers (loot) and the module's factions — plus a button to open the
save's character in the Character Explorer. Areas are parsed lazily on expand.
Data comes from :mod:`vaultkeeper.game.save_game` + :mod:`vaultkeeper.game.save_area`.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.bic_reader import InventoryItem
from vaultkeeper.game.save_area import (
    AreaContents,
    Container,
    CreatureRef,
    Faction,
    Store,
    read_area_contents,
    read_factions,
)
from vaultkeeper.game.save_game import SaveGame, scan_save_games
from vaultkeeper.ui.dialogs.character_viewer import item_icon_source, tga_to_pixmap
from vaultkeeper.ui.dialogs.help_viewer import help_button
from vaultkeeper.ui.dialogs.inventory_view import _item_detail, _load_icon

_SAVE_ROLE = Qt.ItemDataRole.UserRole
_NODE_ROLE = Qt.ItemDataRole.UserRole + 1  # (kind, payload) for a contents-tree node
_ICON_PX = 32


class SaveGameViewer(QDialog):
    """Lists save games; shows the selected save's module, area contents + character."""

    def __init__(
        self, saves: list[SaveGame], controller=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Game Viewer")
        self.resize(920, 620)
        self._controller = controller
        self._saves = saves
        self._current: SaveGame | None = None
        self._module_cache: dict[str, object] = {}
        self._child_viewer = None  # keep a ref so it isn't garbage-collected
        self._icons = item_icon_source(controller) if controller is not None else None
        self._icon_cache: dict[tuple[int, int], QIcon | None] = {}

        outer = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        # -- Left: the list of saves ---------------------------------------- #
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(f"<b>Save games ({len(saves)})</b>"))
        self._list = QListWidget()
        self._list.setMinimumWidth(210)
        self._list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self._list, 1)
        split.addWidget(left)

        # -- Right: screenshot + module detail, then contents tree + detail -- #
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
        self._detail.setMaximumHeight(150)
        header.addWidget(self._detail, 1)
        right_layout.addLayout(header)

        right_layout.addWidget(QLabel("<b>Area contents</b>"))
        contents = QSplitter(Qt.Orientation.Horizontal)
        self._areas = QTreeWidget()
        self._areas.setHeaderHidden(True)
        self._areas.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self._areas.itemExpanded.connect(self._on_expand)
        self._areas.currentItemChanged.connect(self._on_content_selection)
        contents.addWidget(self._areas)
        self._content_detail = QTextEdit()
        self._content_detail.setReadOnly(True)
        contents.addWidget(self._content_detail)
        contents.setSizes([440, 400])
        right_layout.addWidget(contents, 1)
        split.addWidget(right)
        split.setSizes([230, 690])

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

    # -- save selection --------------------------------------------------- #
    def _on_select(self, row: int) -> None:
        item = self._list.item(row) if row >= 0 else None
        save = item.data(_SAVE_ROLE) if item is not None else None
        self._current = save
        self._char_btn.setEnabled(save is not None and save.player_bic is not None)
        self._areas.clear()
        self._content_detail.clear()
        self._shot.clear()
        if save is None:
            self._detail.clear()
            return
        self._show_screenshot(save)
        info = self._module_for(save)
        self._detail.setPlainText(_module_detail(save, info))
        self._populate_areas(save, info)

    def _module_for(self, save: SaveGame):
        if save.name not in self._module_cache:
            self._module_cache[save.name] = save.module_info()
        return self._module_cache[save.name]

    def _populate_areas(self, save: SaveGame, info) -> None:
        """Top-level area nodes (lazy) + a factions node — no .git parsed yet."""
        if info is not None:
            for resref, name in info.areas:
                label = f"{name}  ({resref})" if name != resref else resref
                node = QTreeWidgetItem([label])
                node.setData(0, _NODE_ROLE, ("area", resref))
                node.addChild(QTreeWidgetItem(["…"]))  # dummy -> shows an expand arrow
                self._areas.addTopLevelItem(node)
        if save.sav_path is not None:
            factions = read_factions(save.sav_path)
            if factions:
                node = QTreeWidgetItem([f"Factions ({len(factions)})"])
                node.setData(0, _NODE_ROLE, ("factions", factions))
                self._areas.addTopLevelItem(node)

    # -- lazy area expansion ---------------------------------------------- #
    def _on_expand(self, node: QTreeWidgetItem) -> None:
        role = node.data(0, _NODE_ROLE)
        if not role or role[0] != "area":
            return  # already loaded, or not an area node
        resref = role[1]
        node.takeChildren()  # drop the dummy placeholder
        save = self._current
        area = (
            read_area_contents(
                save.sav_path, resref, resolver=self._resolver()
            )
            if save is not None and save.sav_path is not None
            else None
        )
        node.setData(0, _NODE_ROLE, ("area-loaded", area))
        # The area's real name is a dialog.tlk StrRef only reachable from its .are;
        # now that it's parsed, upgrade the resref label to the resolved name.
        if area is not None and area.name and area.name != resref:
            node.setText(0, f"{area.name}  ({resref})")
        self._populate_area(node, area)

    def _populate_area(self, node: QTreeWidgetItem, area: AreaContents | None) -> None:
        if area is None:
            node.addChild(QTreeWidgetItem(["(contents unavailable)"]))
            return
        if area.stores:
            group = _group("Stores", len(area.stores))
            for store in area.stores:
                sn = _payload_node(f"{store.name}  ({len(store.items)} items)", ("store", store))
                for it in store.items:
                    sn.addChild(self._item_node(it))
                group.addChild(sn)
            node.addChild(group)
        if area.creatures:
            group = _group("Creatures", len(area.creatures))
            for cre in area.creatures:
                cn = _payload_node(f"{cre.name}  ({cre.item_count} items)", ("creature", cre))
                for entry in cre.equipped:
                    cn.addChild(self._item_node(entry.item, prefix=f"[{entry.slot_name}] "))
                for it in cre.carried:
                    cn.addChild(self._item_node(it))
                group.addChild(cn)
            node.addChild(group)
        if area.containers:
            group = _group("Containers", len(area.containers))
            for cont in area.containers:
                kn = _payload_node(f"{cont.name}  ({len(cont.items)} items)", ("container", cont))
                for it in cont.items:
                    kn.addChild(self._item_node(it))
                group.addChild(kn)
            node.addChild(group)
        if not (area.stores or area.creatures or area.containers):
            node.addChild(QTreeWidgetItem(["(no stores, creatures or containers)"]))

    def _item_node(self, item: InventoryItem, *, prefix: str = "") -> QTreeWidgetItem:
        node = QTreeWidgetItem([prefix + item.name])
        node.setData(0, _NODE_ROLE, ("item", item))
        icon = self._icon_for(item)
        if icon is not None:
            node.setIcon(0, icon)
        for child in item.contents:  # a container item's own contents
            node.addChild(self._item_node(child))
        return node

    def _icon_for(self, item: InventoryItem) -> QIcon | None:
        if self._icons is None:
            return None
        key = (item.base_item, item.model_part)
        if key not in self._icon_cache:
            self._icon_cache[key] = _load_icon(self._icons, item)
        return self._icon_cache[key]

    def _resolver(self):
        from vaultkeeper.game.item_names import resolver_for

        game_root = getattr(getattr(self._controller, "ctx", None), "game_root", None)
        return resolver_for(game_root)

    # -- selection -> detail ---------------------------------------------- #
    def _on_content_selection(self, current: QTreeWidgetItem | None, _prev=None) -> None:
        role = current.data(0, _NODE_ROLE) if current is not None else None
        if not role:
            return
        kind, payload = role
        text = ""
        if kind == "item" and isinstance(payload, InventoryItem):
            text = _item_detail(payload)
        elif kind == "store":
            text = _store_detail(payload)
        elif kind == "creature":
            text = _creature_detail(payload)
        elif kind == "container":
            text = _container_detail(payload)
        elif kind == "area-loaded":
            text = _area_detail(payload) if payload is not None else "(contents unavailable)"
        elif kind == "area":
            text = "Expand to load this area's contents."
        elif kind == "factions":
            text = _factions_detail(payload)
        self._content_detail.setPlainText(text)

    # -- screenshot + character ------------------------------------------- #
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
        from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

        info = BicFileReader().read_file(save.player_bic)
        if info is None:
            return
        self._resolver().resolve_character(info)
        character = CharacterFile(path=save.player_bic, info=info)
        nwn_style = getattr(self._controller._settings(), "inventory_nwn_style", False) \
            if self._controller else False
        self._child_viewer = CharacterViewer(
            [character], parent=self,
            icon_source=self._icons, inventory_nwn_style=nwn_style,
            on_inventory_style_changed=(
                self._controller.set_inventory_nwn_style if self._controller else None
            ),
        )
        self._child_viewer.show()


# --------------------------------------------------------------------------- #
# tree-node helpers + detail text
# --------------------------------------------------------------------------- #
def _group(label: str, count: int) -> QTreeWidgetItem:
    """A non-selectable grouping node, e.g. ``Stores (2)``."""
    return QTreeWidgetItem([f"{label} ({count})"])


def _payload_node(label: str, role: tuple) -> QTreeWidgetItem:
    node = QTreeWidgetItem([label])
    node.setData(0, _NODE_ROLE, role)
    return node


def _gold(value: int) -> str:
    return "unlimited" if value < 0 else str(value)


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


def _area_detail(area: AreaContents) -> str:
    lines = [f"{area.name}  ({area.resref})"]
    meta = []
    if area.tileset:
        meta.append(f"Tileset: {area.tileset}")
    if area.dimensions:
        meta.append(f"Size: {area.dimensions}")
    meta.append(f"Terrain: {area.terrain}")
    lines.append("    ".join(meta))
    hidden = f" (+{area.hidden_creatures} hidden)" if area.hidden_creatures else ""
    lines.append(
        f"Stores: {len(area.stores)}    "
        f"Creatures: {len(area.creatures)}{hidden}    "
        f"Containers: {len(area.containers)}"
    )
    counts = area.counts
    if counts:
        lines.append(
            "    ".join(f"{label.capitalize()}: {counts[label]}" for label in counts)
        )
    return "\n".join(lines)


def _store_detail(store: Store) -> str:
    lines = [store.name]
    if store.tag:
        lines.append(f"Tag: {store.tag}")
    lines.append(f"Sells {len(store.items)} items")
    lines.append(f"Buy markup: {store.markup}%    Sell-back markdown: {store.markdown}%")
    extra = [f"Store gold: {_gold(store.store_gold)}"]
    if store.identify_price >= 0:
        extra.append(f"Identify price: {store.identify_price}")
    if store.max_buy_price >= 0:
        extra.append(f"Max buy price: {store.max_buy_price}")
    if store.black_market:
        extra.append("Black market")
    lines.append("    ".join(extra))
    return "\n".join(lines)


def _creature_detail(cre: CreatureRef) -> str:
    lines = [cre.name]
    if cre.tag:
        lines.append(f"Tag: {cre.tag}")
    lines.append(f"Gold: {cre.gold}")
    lines.append(f"Equipped: {len(cre.equipped)}    Carried: {len(cre.carried)}")
    return "\n".join(lines)


def _container_detail(cont: Container) -> str:
    lines = [cont.name]
    if cont.tag:
        lines.append(f"Tag: {cont.tag}")
    lines.append(f"{len(cont.items)} items")
    return "\n".join(lines)


def _reputation_band(rep: int) -> str:
    if rep >= 90:
        return "friendly"
    if rep <= 10:
        return "hostile"
    return "neutral"


def _factions_detail(factions: list[Faction]) -> str:
    lines = [f"Factions ({len(factions)})", ""]
    for faction in factions:
        if faction.reputation_to_pc is None:
            standing = ""
        else:
            band = _reputation_band(faction.reputation_to_pc)
            standing = f"  —  {band} ({faction.reputation_to_pc})"
        lines.append(f"{faction.name}{standing}")
    return "\n".join(lines)
