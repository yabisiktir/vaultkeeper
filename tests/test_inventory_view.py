"""Tests for the Inventory tab (equipment doll + carried tree + detail pane)."""

from __future__ import annotations

from vaultkeeper.core.formats.bic_reader import (
    CharacterInfo,
    EquippedItem,
    Gender,
    InventoryItem,
    Race,
)
from vaultkeeper.ui.dialogs.inventory_view import InventoryView, _count_items, _item_detail


def _item(name: str, **kw) -> InventoryItem:
    base = dict(
        base_item=0, tag="", resref="", stack_size=1, identified=True,
        stolen=False, description="", property_count=0, contents=[],
    )
    base.update(kw)
    return InventoryItem(name=name, **base)


def _info(equipped, inventory) -> CharacterInfo:
    return CharacterInfo(
        name="T", gender=Gender.MALE, race=Race.HUMAN, classes=[], level=1,
        experience=0, alignment_good_evil=50, alignment_lawful_chaotic=50,
        hit_points=10, equipped_items=equipped, inventory_items=inventory,
    )


def test_count_items_recurses_into_containers():
    bag = _item("Bag", contents=[_item("A"), _item("B", contents=[_item("C")])])
    assert _count_items([bag]) == 4  # bag + A + B + C


def test_item_detail_text():
    item = _item(
        "Amulet", tag="amul", resref="amul001", property_count=1,
        description="Glows faintly.", identified=False,
    )
    text = _item_detail(item)
    assert text.startswith("Amulet")
    assert "1 magical property" in text  # singular
    assert "unidentified" in text
    assert "Tag: amul" in text
    assert "Glows faintly." in text


def test_inventory_view_populates_doll_and_tree(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    helm = _item("Helm of X", property_count=3, description="A fine helm.")
    bag = _item("Bag", contents=[_item("Sword"), _item("Shield")])
    ring = _item("Ring")
    view.set_character(_info([EquippedItem(1, "Head", helm)], [bag, ring]))

    assert view._cards["Head"]._item is helm
    assert view._cards["Chest"]._item is None  # empty slot stays greyed
    # tree: two top-level rows; the bag expands to its two contents.
    assert view._tree.topLevelItemCount() == 2
    bag_node = view._tree.topLevelItem(0)
    assert bag_node.text(0) == "Bag" and bag_node.childCount() == 2
    # carried count includes nested items (bag + 2 + ring = 4).
    assert "4 items" in view._carried_label.text()
    assert "1 container" in view._carried_label.text()


def test_slot_card_click_shows_detail(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    helm = _item("Helm", property_count=2, description="Shiny.")
    view.set_character(_info([EquippedItem(1, "Head", helm)], []))
    view._show_item(helm)  # what a card click does
    text = view._detail.toPlainText()
    assert "Helm" in text and "2 magical properties" in text and "Shiny." in text


def test_inventory_view_clear(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    view.set_character(_info([EquippedItem(1, "Head", _item("Helm"))], [_item("Ring")]))
    view.clear()
    assert view._tree.topLevelItemCount() == 0
    assert view._cards["Head"]._item is None
    assert view._detail.toPlainText() == ""


def test_ammunition_cell_shows_any_ammo(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    bolts = _item("+3 Bolts", stack_size=99)
    view.set_character(_info([EquippedItem(8192, "Bolts", bolts)], []))
    # slot 8192 (Bolts) is one of the Ammunition cell's candidate bits.
    assert view._cards["Ammunition"]._item is bolts
