"""Inventory tab for the Character Explorer — a new view with no VB equivalent.

The original tool never surfaced a character's items. This shows both halves of a
``.bic``'s inventory:

* **Equipped** — a paper-doll grid of slot cards (Head, Chest, weapons, rings …),
  each showing the worn item; empty slots are greyed. Clicking a card details it.
* **Carried** — the backpack as a tree: loose items plus containers (bags) that
  expand to their contents. Selecting an item details it.

A shared detail pane shows the selected item's name, flags, magical-property count
and its in-game description. All data comes from :mod:`bic_reader`
(``CharacterInfo.equipped_items`` / ``inventory_items``); this module is display
only.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.bic_reader import CharacterInfo, EquippedItem, InventoryItem
from vaultkeeper.game.item_names import base_item_type
from vaultkeeper.game.item_properties import describe_properties

_ITEM_ROLE = Qt.ItemDataRole.UserRole

#: Paper-doll layout: (card label, candidate slot bits) laid out 3 per row. A cell
#: with several bits (ammunition, creature weapon) shows whichever one is worn.
_DOLL: list[tuple[str, tuple[int, ...]]] = [
    ("Head", (1,)), ("Neck", (512,)), ("Cloak", (64,)),
    ("Chest", (2,)), ("Arms", (8,)), ("Belt", (1024,)),
    ("Right Hand", (16,)), ("Boots", (4,)), ("Left Hand", (32,)),
    ("Right Ring", (256,)), ("Ammunition", (2048, 4096, 8192)), ("Left Ring", (128,)),
    ("Skin", (131072,)), ("Creature Weapon", (16384, 32768, 65536)),
]
_COLUMNS = 3


class _SlotCard(QFrame):
    """A clickable equipment-slot card: slot label above the worn item's name."""

    def __init__(self, label: str, on_click: Callable[[InventoryItem], None]) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._on_click = on_click
        self._item: InventoryItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)
        self._slot = QLabel(label)
        slot_font = self._slot.font()
        slot_font.setPointSize(max(slot_font.pointSize() - 2, 7))
        self._slot.setFont(slot_font)
        self._slot.setStyleSheet("color: palette(mid);")
        self._name = QLabel("— empty —")
        name_font = self._name.font()
        name_font.setBold(True)
        self._name.setFont(name_font)
        self._name.setWordWrap(True)
        layout.addWidget(self._slot)
        layout.addWidget(self._name)

    def set_item(self, item: InventoryItem | None) -> None:
        self._item = item
        if item is None:
            self._name.setText("— empty —")
            self._name.setStyleSheet("color: palette(mid); font-style: italic;")
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self._name.setText(item.name)
            self._name.setStyleSheet("")
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._item is not None:
            self._on_click(self._item)


class InventoryView(QWidget):
    """The Inventory tab: equipment doll + carried tree + item detail pane."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        # -- Left: equipped paper-doll -------------------------------------- #
        equipped = QWidget()
        eq_layout = QVBoxLayout(equipped)
        eq_layout.setContentsMargins(0, 0, 0, 0)
        eq_layout.addWidget(QLabel("<b>Equipped</b>"))
        doll = QWidget()
        self._grid = QGridLayout(doll)
        self._grid.setSpacing(4)
        self._cards: dict[str, _SlotCard] = {}
        for index, (label, _bits) in enumerate(_DOLL):
            card = _SlotCard(label, self._show_item)
            self._cards[label] = card
            self._grid.addWidget(card, index // _COLUMNS, index % _COLUMNS)
        eq_layout.addWidget(doll)
        eq_layout.addStretch(1)
        split.addWidget(equipped)

        # -- Right: carried tree over the detail pane ----------------------- #
        right = QSplitter(Qt.Orientation.Vertical)
        carried = QWidget()
        c_layout = QVBoxLayout(carried)
        c_layout.setContentsMargins(0, 0, 0, 0)
        self._carried_label = QLabel("<b>Carried</b>")
        c_layout.addWidget(self._carried_label)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Item", "Qty"])
        self._tree.setColumnCount(2)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.currentItemChanged.connect(self._on_tree_selection)
        c_layout.addWidget(self._tree, 1)
        right.addWidget(carried)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        right.addWidget(self._detail)
        right.setSizes([300, 160])
        split.addWidget(right)
        split.setSizes([360, 420])

    def clear(self) -> None:
        for card in self._cards.values():
            card.set_item(None)
        self._tree.clear()
        self._detail.clear()
        self._carried_label.setText("<b>Carried</b>")

    def set_character(self, info: CharacterInfo | None) -> None:
        self.clear()
        if info is None or not info.is_valid:
            return
        self._fill_equipped(info.equipped_items)
        self._fill_carried(info.inventory_items)

    # -- population ------------------------------------------------------- #
    def _fill_equipped(self, equipped: list[EquippedItem]) -> None:
        by_slot = {entry.slot: entry.item for entry in equipped}
        for label, bits in _DOLL:
            item = next((by_slot[bit] for bit in bits if bit in by_slot), None)
            self._cards[label].set_item(item)

    def _fill_carried(self, items: list[InventoryItem]) -> None:
        item_count = _count_items(items)
        containers = sum(1 for it in items if it.is_container)
        parts = [_plural(item_count, "item")]
        if containers:
            parts.append(_plural(containers, "container"))
        self._carried_label.setText(f"<b>Carried</b> ({', '.join(parts)})")
        for item in items:
            self._tree.addTopLevelItem(self._tree_item(item))

    def _tree_item(self, item: InventoryItem) -> QTreeWidgetItem:
        qty = str(item.stack_size) if item.stack_size > 1 else ""
        if item.is_container:
            qty = f"[{_count_items(item.contents)}]"
        node = QTreeWidgetItem([item.name, qty])
        node.setData(0, _ITEM_ROLE, item)
        for child in item.contents:
            node.addChild(self._tree_item(child))
        return node

    # -- selection -> detail --------------------------------------------- #
    def _on_tree_selection(self, current: QTreeWidgetItem | None, _prev=None) -> None:
        item = current.data(0, _ITEM_ROLE) if current is not None else None
        if isinstance(item, InventoryItem):
            self._show_item(item)

    def _show_item(self, item: InventoryItem) -> None:
        self._detail.setPlainText(_item_detail(item))


def _count_items(items: list[InventoryItem]) -> int:
    """Total items including container contents (containers themselves count)."""
    return sum(1 + _count_items(it.contents) for it in items)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _item_detail(item: InventoryItem) -> str:
    lines = [item.name]
    tags = []
    if item.is_container:
        tags.append("Container")
    if item.stack_size > 1:
        tags.append(f"Stack of {item.stack_size}")
    if not item.identified:
        tags.append("unidentified")
    if item.stolen:
        tags.append("stolen")
    if tags:
        lines.append(" · ".join(tags))
    item_type = base_item_type(item.base_item)
    if item_type:
        lines.append(f"Type: {item_type}")
    if item.tag or item.resref:
        lines.append(f"Tag: {item.tag or '—'}    ResRef: {item.resref or '—'}")
    if item.properties:
        lines.append("")
        lines.append(f"Magical properties ({len(item.properties)}):")
        lines.extend(f"  • {text}" for text in describe_properties(item.properties))
    if item.description:
        lines.append("")
        lines.append(item.description)
    return "\n".join(lines)
