"""Tests for the Inventory tab (equipment doll + carried tree + detail pane)."""

from __future__ import annotations

from nwnfile.formats.bic_reader import (
    CharacterInfo,
    EquippedItem,
    Gender,
    InventoryItem,
    ItemProperty,
    Race,
)

from vaultkeeper.ui.dialogs.inventory_view import InventoryView, _count_items, _item_detail


def _item(name: str, **kw) -> InventoryItem:
    base = dict(
        base_item=0, tag="", resref="", stack_size=1, identified=True,
        stolen=False, description="", properties=[], contents=[],
    )
    base.update(kw)
    return InventoryItem(name=name, **base)


def _info(equipped, inventory) -> CharacterInfo:
    return CharacterInfo(
        name="T", gender=Gender.MALE, race_id=Race.HUMAN.value, classes=[], level=1,
        experience=0, alignment_good_evil=50, alignment_lawful_chaotic=50,
        hit_points=10, equipped_items=equipped, inventory_items=inventory,
    )


def test_count_items_recurses_into_containers():
    bag = _item("Bag", contents=[_item("A"), _item("B", contents=[_item("C")])])
    assert _count_items([bag]) == 4  # bag + A + B + C


def test_item_detail_text():
    item = _item(
        "Amulet", tag="amul", resref="amul001",
        properties=[ItemProperty(0, 4, 1, 8, 255, 0)],  # Ability Bonus: Wisdom +8
        description="Glows faintly.", identified=False,
    )
    text = _item_detail(item)
    assert text.startswith("Amulet")
    assert "Magical properties (1):" in text
    assert "Ability Bonus: Wisdom +8" in text
    assert "unidentified" in text
    assert "Tag: amul" in text
    assert "Glows faintly." in text


def test_inventory_view_populates_doll_and_tree(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    helm = _item("Helm of X", description="A fine helm.")
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
    helm = _item(
        "Helm", description="Shiny.",
        properties=[ItemProperty(6, 0, 1, 5, 255, 0), ItemProperty(43, 0, 0, 0, 255, 0)],
    )
    view.set_character(_info([EquippedItem(1, "Head", helm)], []))
    view._show_item(helm)  # what a card click does
    text = view._detail.toPlainText()
    assert "Helm" in text and "Magical properties (2):" in text and "Shiny." in text
    assert "Enhancement Bonus +5" in text and "Keen" in text


def test_inventory_view_clear(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    view.set_character(_info([EquippedItem(1, "Head", _item("Helm"))], [_item("Ring")]))
    view.clear()
    assert view._tree.topLevelItemCount() == 0
    assert view._cards["Head"]._item is None
    assert view._detail.toPlainText() == ""


class _FakeIcons:
    available = True

    def __init__(self):
        self.asked = []

    def icon_bytes(self, base_item, model_part, **variant):
        return None  # exercise the icon path without needing the game install

    def icon_image(self, base_item, model_part, **variant):
        # ``variant`` carries what tells one suit of armour from another; the real
        # source needs it, so a fake that refused it would hide a wiring mistake.
        self.asked.append((base_item, model_part, variant))
        return None


def test_nwn_style_toggle_switches_view_and_persists(qtbot):
    changes: list[bool] = []
    view = InventoryView(icon_source=_FakeIcons(), on_style_changed=changes.append)
    qtbot.addWidget(view)
    view.set_character(_info([], [_item("Bag", contents=[_item("Sword")]), _item("Ring")]))
    assert view._nwn_checkbox.isEnabled()
    assert view._carried_stack.currentIndex() == 0  # list design by default
    assert view._grid_view.count() == 3  # flattened: bag + sword + ring
    view._nwn_checkbox.setChecked(True)
    assert view._carried_stack.currentIndex() == 1  # NWN icon grid
    assert changes == [True]
    view._grid_view.setCurrentRow(0)  # selecting a grid tile shows its detail
    assert "Bag" in view._detail.toPlainText()


def test_nwn_checkbox_disabled_without_icon_source(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    assert not view._nwn_checkbox.isEnabled()


def test_ammunition_cell_shows_any_ammo(qtbot):
    view = InventoryView()
    qtbot.addWidget(view)
    bolts = _item("+3 Bolts", stack_size=99)
    view.set_character(_info([EquippedItem(8192, "Bolts", bolts)], []))
    # slot 8192 (Bolts) is one of the Ammunition cell's candidate bits.
    assert view._cards["Ammunition"]._item is bolts


def test_each_suit_of_armour_gets_its_own_icon_not_the_first_one(qtbot):
    """Armour carries no ModelPart1 — every suit is ``(16, 0)``.

    Keyed on that alone, the view's own cache handed the first suit's picture to
    all of them, however well the layer underneath resolved them.
    """
    icons = _FakeIcons()
    view = InventoryView(icon_source=icons)
    qtbot.addWidget(view)
    view.set_character(_info([], [
        _item("Plate", base_item=16, armor_torso=28),
        _item("Scale", base_item=16, armor_torso=33),
    ]))
    torsos = [v.get("armor_torso") for _b, _m, v in icons.asked if _b == 16]
    assert sorted(set(torsos)) == [28, 33]  # both asked for, not one cached for both


def test_a_womans_armour_is_asked_for_as_hers(qtbot):
    """The same suit is a different picture on each body."""
    icons = _FakeIcons()
    view = InventoryView(icon_source=icons)
    qtbot.addWidget(view)
    info = _info([], [_item("Plate", base_item=16, armor_torso=28)])
    info.gender = Gender.FEMALE
    view.set_character(info)
    assert any(v.get("female") for _b, _m, v in icons.asked)
