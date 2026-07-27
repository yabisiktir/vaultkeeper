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

import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.bic_reader import InventoryItem
from vaultkeeper.game.item_properties import describe_property, editable_magnitude, is_cast_spell
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
        #: the selected editable target, discriminated by its first element:
        #: ("store", area, index, Store) or ("property", item_path, prop_index, prop, item_name).
        self._edit_target: tuple | None = None
        #: edit session (SaveEditor) — batches changes; None until an edit is made.
        self._session = None
        self._editing = False
        self._syncing_selection = False  # guard against re-entrant save switching

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
        self._areas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._areas.customContextMenuRequested.connect(self._show_context_menu)
        contents.addWidget(self._areas)
        self._content_detail = QTextEdit()
        self._content_detail.setReadOnly(True)
        contents.addWidget(self._content_detail)
        contents.setSizes([440, 400])
        right_layout.addWidget(contents, 1)
        right_layout.addWidget(self._build_pending_panel())
        split.addWidget(right)
        split.setSizes([230, 690])

        bar = QHBoxLayout()
        bar.addWidget(help_button("BhGameManager", self))
        bar.addStretch(1)
        self._edit_toggle = QPushButton("Edit")
        self._edit_toggle.setCheckable(True)
        self._edit_toggle.setToolTip("Turn on editing to change stores (saved as a new save)")
        self._edit_toggle.toggled.connect(self._set_edit_mode)
        bar.addWidget(self._edit_toggle)
        self._edit_btn = QPushButton("Edit…")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._edit_selected)
        bar.addWidget(self._edit_btn)
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
        if self._syncing_selection:
            return
        item = self._list.item(row) if row >= 0 else None
        save = item.data(_SAVE_ROLE) if item is not None else None
        # Guard unsaved edits when leaving the current save.
        if save is not self._current and self._session is not None and self._session.has_edits:
            if not self._confirm_discard():
                self._reselect_current()
                return
            self._clear_session()
        self._current = save
        self._char_btn.setEnabled(save is not None and save.player_bic is not None)
        self._content_detail.clear()
        self._shot.clear()
        if save is None:
            self._detail.clear()
            self._areas.clear()
            return
        self._show_screenshot(save)
        self._detail.setPlainText(_module_detail(save, self._module_for(save)))
        self._reload_areas()

    def _reload_areas(self) -> None:
        """(Re)build the top-level area/faction nodes for the current save."""
        self._areas.clear()
        self._edit_target = None
        self._update_edit_btn()
        if self._current is not None:
            self._populate_areas(self._current, self._module_for(self._current))

    def _reselect_current(self) -> None:
        self._syncing_selection = True
        for i in range(self._list.count()):
            if self._list.item(i).data(_SAVE_ROLE) is self._current:
                self._list.setCurrentRow(i)
                break
        self._syncing_selection = False

    def _module_for(self, save: SaveGame):
        if save.name not in self._module_cache:
            self._module_cache[save.name] = save.module_info()
        return self._module_cache[save.name]

    def _populate_areas(self, save: SaveGame, info) -> None:
        """Top-level Character + area nodes (lazy) + a factions node."""
        if self._controller is not None and save.sav_path is not None:
            char = QTreeWidgetItem(["Player character"])
            char.setData(0, _NODE_ROLE, ("character", None))
            char.addChild(QTreeWidgetItem(["…"]))  # dummy -> shows an expand arrow
            self._areas.addTopLevelItem(char)
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
        if role and role[0] == "character":
            node.takeChildren()
            node.setData(0, _NODE_ROLE, ("character-loaded", None))
            self._populate_character(node)
            return
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
            pending = self._pending_store_keys()
            group = _group("Stores", len(area.stores))
            for index, store in enumerate(area.stores):
                marker = "● " if (area.resref.lower(), index) in pending else ""
                sn = _payload_node(
                    f"{marker}{store.name}  ({len(store.items)} items)",
                    ("store", store, area.resref, index),
                )
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

    def _populate_character(self, node: QTreeWidgetItem) -> None:
        """The player's equipped + carried items, each with editable properties."""
        from vaultkeeper.game.save_editor import SaveEditError

        try:
            items = self._ensure_session().player_items()
        except SaveEditError:
            node.addChild(QTreeWidgetItem(["(character unavailable)"]))
            return
        resolver = self._resolver()
        equipped = [it for it in items if it.slot is not None]
        carried = [it for it in items if it.slot is None]
        pending = self._pending_prop_keys()
        for label, group_items in (("Equipped", equipped), ("Carried", carried)):
            if not group_items:
                continue
            group = _group(label, len(group_items))
            for item in group_items:
                group.addChild(self._char_item_node(item, resolver, pending))
            node.addChild(group)

    def _char_item_node(self, item, resolver, pending) -> QTreeWidgetItem:
        name = item.name
        if item.name_strref >= 0:
            name = resolver.name_for(item.name_strref) or name
        node = _payload_node(name, ("edit-item", item))
        icon = self._icon_for(item)  # EditableItem duck-types base_item/model_part
        if icon is not None:
            node.setIcon(0, icon)
        for prop in item.properties:
            editable = editable_magnitude(prop.prop) or is_cast_spell(prop.prop)
            marker = "● " if (tuple(item.path), prop.index) in pending else ""
            desc = describe_property(prop.prop, None)
            pnode = _payload_node(
                f"{marker}{desc}",
                ("property", item.path, prop.index, prop, name, editable),
            )
            node.addChild(pnode)
        return node

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
        self._edit_target = None
        if not role:
            self._update_edit_btn()
            return
        kind, payload = role[0], role[1] if len(role) > 1 else None
        text = ""
        if kind == "item" and isinstance(payload, InventoryItem):
            text = _item_detail(payload)
        elif kind == "store":
            text = _store_detail(payload)
            if self._controller is not None and len(role) >= 4:
                self._edit_target = ("store", role[2], role[3], payload)
        elif kind == "edit-item":
            text = _edit_item_detail(payload)
        elif kind == "property":
            # role = ("property", item_path, prop_index, EditableProperty, item_name, editable)
            _, item_path, prop_index, prop, item_name, editable = role
            text = describe_property(prop.prop, None)
            if editable:
                self._edit_target = ("property", item_path, prop_index, prop, item_name)
            else:
                text += "\n\n(This property's value isn't a simple magnitude, so it's" \
                        " read-only here — editing it could corrupt the item.)"
        elif kind == "creature":
            text = _creature_detail(payload)
        elif kind == "container":
            text = _container_detail(payload)
        elif kind == "area-loaded":
            text = _area_detail(payload) if payload is not None else "(contents unavailable)"
        elif kind in ("area", "character"):
            text = "Expand to load this."
        elif kind == "factions":
            text = _factions_detail(payload)
        self._content_detail.setPlainText(text)
        self._update_edit_btn()

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

    # -- edit session ----------------------------------------------------- #
    def _build_pending_panel(self) -> QWidget:
        """The 'pending changes' strip: a summary list + Discard / Save buttons."""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 4)
        self._pending_label = QLabel("No pending changes")
        layout.addWidget(self._pending_label)
        self._pending_list = QListWidget()
        self._pending_list.setMaximumHeight(84)
        layout.addWidget(self._pending_list)
        row = QHBoxLayout()
        row.addStretch(1)
        self._discard_btn = QPushButton("Discard All")
        self._discard_btn.clicked.connect(self._discard_all)
        row.addWidget(self._discard_btn)
        self._save_btn = QPushButton("Save as New Save…")
        self._save_btn.clicked.connect(self._save_as_new)
        row.addWidget(self._save_btn)
        layout.addLayout(row)
        panel.setVisible(False)
        self._pending_panel = panel
        return panel

    def _set_edit_mode(self, on: bool) -> None:
        if not on and self._session is not None and self._session.has_edits:
            if not self._confirm_discard():
                self._edit_toggle.setChecked(True)  # stay in edit mode
                return
            self._clear_session()
            self._reload_areas()
        self._editing = on
        self._pending_panel.setVisible(on)
        self._update_edit_btn()

    def _update_edit_btn(self) -> None:
        self._edit_btn.setEnabled(self._editing and self._edit_target is not None)

    def _ensure_session(self):
        from vaultkeeper.game.save_editor import SaveEditor

        if self._session is None and self._current is not None:
            self._session = SaveEditor(self._current)
        return self._session

    def _pending_store_keys(self) -> set[tuple[str, int]]:
        if self._session is None:
            return set()
        return {
            (change.key[0].lower(), change.key[1])
            for change in self._session.pending_changes()
            if change.kind == "store"
        }

    def _pending_prop_keys(self) -> set[tuple[tuple, int]]:
        if self._session is None:
            return set()
        return {
            (tuple(change.key[0]), change.key[1])
            for change in self._session.pending_changes()
            if change.kind == "property"
        }

    def _clear_session(self) -> None:
        if self._session is not None:
            self._session.discard()
        self._session = None
        self._refresh_pending()

    def _confirm_discard(self) -> bool:
        count = len(self._session.pending_changes()) if self._session else 0
        return (
            QMessageBox.question(
                self, "Discard changes",
                f"Discard {count} unsaved change(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _refresh_pending(self) -> None:
        changes = self._session.pending_changes() if self._session else []
        self._pending_list.clear()
        for change in changes:
            self._pending_list.addItem(f"{change.where}: {change.summary}")
        count = len(changes)
        self._pending_label.setText(
            f"<b>● {count} pending change{'' if count == 1 else 's'}</b>"
            if count else "No pending changes"
        )
        self._save_btn.setEnabled(count > 0)
        self._discard_btn.setEnabled(count > 0)

    def _edit_selected(self) -> None:
        """Stage an edit to whatever editable node is selected (store or property)."""
        if not self._editing or self._current is None or self._edit_target is None:
            return
        if self._edit_target[0] == "store":
            self._edit_store(*self._edit_target[1:])
        elif self._edit_target[0] == "property":
            self._edit_property(*self._edit_target[1:])

    def _edit_store(self, area_resref: str, store_index: int, store: Store) -> None:
        from vaultkeeper.game.save_editor import SaveEditError
        from vaultkeeper.ui.dialogs.store_edit_dialog import StoreEditDialog

        dialog = StoreEditDialog(store, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._ensure_session().set_store_fields(
                area_resref, store_index,
                where=f"{store.name} ({area_resref})", **dialog.values(),
            )
        except SaveEditError as exc:
            QMessageBox.critical(self, "Edit failed", str(exc))
            return
        self._mark_current_node()
        self._refresh_pending()

    def _edit_property(self, item_path, prop_index, prop, item_name) -> None:
        from vaultkeeper.game.item_properties import describe_property, is_cast_spell
        from vaultkeeper.game.save_editor import SaveEditError
        from vaultkeeper.ui.dialogs.property_edit_dialog import PropertyEditDialog

        label = describe_property(prop.prop, None)
        cast = is_cast_spell(prop.prop)
        if cast:
            dialog = PropertyEditDialog(
                label, "Uses per day:", prop.uses_per_day,
                minimum=0, maximum=255, special_text="", parent=self,
            )
        else:
            dialog = PropertyEditDialog(
                label, "Magnitude (+N):", prop.prop.cost_value,
                minimum=0, maximum=255, parent=self,
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kwargs = {"uses_per_day": dialog.value()} if cast else {"cost_value": dialog.value()}
        try:
            self._ensure_session().set_property_cost(
                item_path, prop_index, where=item_name, prop_label=label, **kwargs
            )
        except SaveEditError as exc:
            QMessageBox.critical(self, "Edit failed", str(exc))
            return
        self._mark_current_node()
        self._refresh_pending()

    def _show_context_menu(self, pos) -> None:
        """Right-click a player item (in edit mode) to add a copy to inventory."""
        if not self._editing:
            return
        node = self._areas.itemAt(pos)
        role = node.data(0, _NODE_ROLE) if node is not None else None
        if not role or role[0] != "edit-item":
            return
        menu = QMenu(self)
        action = menu.addAction("Add a copy to my inventory")
        if menu.exec(self._areas.viewport().mapToGlobal(pos)) is action:
            self._add_item_copy(role[1])

    def _add_item_copy(self, item) -> None:
        from vaultkeeper.game.save_editor import SaveEditError

        try:
            self._ensure_session().add_item_copy(item.path, where=item.name)
        except SaveEditError as exc:
            QMessageBox.critical(self, "Add failed", str(exc))
            return
        self._refresh_character_node()
        self._refresh_pending()

    def _refresh_character_node(self) -> None:
        """Rebuild the Character node's children so a newly-added item shows."""
        for i in range(self._areas.topLevelItemCount()):
            node = self._areas.topLevelItem(i)
            role = node.data(0, _NODE_ROLE)
            if role and role[0] == "character-loaded":
                node.takeChildren()
                self._populate_character(node)
                node.setExpanded(True)
                return

    def _mark_current_node(self) -> None:
        """Add/remove the ● dirty marker on the selected editable node."""
        node = self._areas.currentItem()
        if node is None or self._edit_target is None:
            return
        if self._edit_target[0] == "store":
            _, area_resref, store_index, _store = self._edit_target
            pending = (area_resref.lower(), store_index) in self._pending_store_keys()
        else:  # property
            _, item_path, prop_index, _prop, _name = self._edit_target
            pending = (tuple(item_path), prop_index) in self._pending_prop_keys()
        base = node.text(0).removeprefix("● ")
        node.setText(0, ("● " + base) if pending else base)

    def _discard_all(self) -> None:
        if self._session is None or not self._session.has_edits:
            return
        if not self._confirm_discard():
            return
        self._clear_session()
        self._reload_areas()

    def _save_as_new(self) -> None:
        if self._session is None or not self._session.has_edits or self._current is None:
            return
        from vaultkeeper.game.save_editor import SaveEditError

        name, ok = QInputDialog.getText(
            self, "Save as New Save", "New save name:",
            text=f"{_base_name(self._current.name)} (edited)",
        )
        if not ok or not name.strip():
            return
        try:
            new_save = self._session.save_as(
                _next_save_folder(self._current.folder.parent, name.strip())
            )
        except (SaveEditError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(
            self, "Saved",
            f"Saved as “{new_save.name}”.\nYour original save is unchanged.",
        )
        self._session = None
        self._refresh_pending()
        self._add_save(new_save)  # selecting it rebuilds the tree (markers cleared)

    def _add_save(self, save: SaveGame) -> None:
        """Insert a freshly-written save at the top of the list and select it."""
        self._saves.insert(0, save)
        label = f"{save.name}\n{save.location}" if save.location else save.name
        item = QListWidgetItem(label)
        item.setData(_SAVE_ROLE, save)
        self._list.insertItem(0, item)
        self._list.setCurrentRow(0)

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
def _base_name(folder_name: str) -> str:
    """A save folder's display name without the ``NNNNNN - `` numeric prefix."""
    return re.sub(r"^\d{6}\s*-\s*", "", folder_name).strip() or folder_name


def _next_save_folder(saves_dir, name: str):
    """The path for a new save folder ``<next-number> - <name>`` under ``saves_dir``."""
    numbers = [
        int(match.group(1))
        for p in saves_dir.iterdir()
        if p.is_dir() and (match := re.match(r"(\d{6})", p.name))
    ]
    number = (max(numbers) + 1) if numbers else 1
    return saves_dir / f"{number:06d} - {_base_name(name)}"


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


def _edit_item_detail(item) -> str:
    """Summary for a player item node (an EditableItem) in the character tree."""
    lines = [item.name]
    if item.resref:
        lines.append(f"ResRef: {item.resref}")
    count = len(item.properties)
    lines.append(f"{count} magical propert{'y' if count == 1 else 'ies'}")
    if count:
        lines.append("")
        lines.extend(f"  • {describe_property(p.prop, None)}" for p in item.properties)
    lines.append("")
    lines.append("Select a property, then Edit… to change its value.")
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
