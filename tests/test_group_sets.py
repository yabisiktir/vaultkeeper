"""The starting group sets offered for a new profile (VB GroupSets).

The choice is not cosmetic: groups sort by name, that order is the order mod
files are copied, and that order decides which mod wins a file conflict
(``faqgroupnumbers.htm``). Picking a set is picking a conflict policy.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core import group_sets


def test_the_four_sets_are_offered_default_first():
    names = group_sets.set_names()
    assert len(names) == 4
    assert names[0] == group_sets.DEFAULT_SET_NAME
    assert "category and usage" in names[0]
    assert any(n.startswith("None") for n in names)


def test_none_is_a_real_answer():
    """Not a way out of the question — some people want to organise their own."""
    none = next(n for n in group_sets.set_names() if n.startswith("None"))
    assert group_sets.group_names(none) == []


def test_every_set_sorts_the_way_it_is_written():
    """The numeric prefixes exist to force an order, so the listed order and the
    sorted order must agree — a set that does not sort as written would install
    mods in an order nobody chose."""
    for name in group_sets.set_names():
        groups = group_sets.group_names(name)
        assert groups == sorted(groups), name


def test_the_restorer_groups_come_first_where_they_appear():
    for name in group_sets.set_names():
        groups = group_sets.group_names(name)
        if C.RESTORER_GROUP in groups:
            assert groups[0] == C.RESTORER_GROUP, name


def test_an_unknown_set_name_falls_back_to_the_default():
    assert group_sets.group_names("something else") == group_sets.group_names(
        group_sets.DEFAULT_SET_NAME
    )


# -- Seeding a profile --------------------------------------------------------- #
def _configure(tmp_path: Path, group_set: str | None):
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.session import configure_profile

    settings = Settings()
    settings.store_root = str(tmp_path / "Store")
    settings.game_user_path = str(tmp_path / "user")
    return configure_profile(
        str(tmp_path / "NWN"),
        "Test Profile",
        group_set=group_set,
        settings=settings,
        settings_path=tmp_path / "settings.json",
    )


def _visible_groups(controller) -> list[str]:
    return [g for g in controller.group_names() if not g.startswith(C.GROUP_HIDDEN_PREFIX)]


def test_a_new_profile_starts_with_the_chosen_set(qtbot, tmp_path):
    controller = _configure(tmp_path, "Groups are based on Nexus Mods categories")
    groups = _visible_groups(controller)
    assert "020.  Armour and Clothing" in groups
    assert "700.  Borderline Worth Playing" not in groups, "that is the other set"


def test_no_choice_means_the_default_set(qtbot, tmp_path):
    controller = _configure(tmp_path, None)
    assert "700.  Borderline Worth Playing" in _visible_groups(controller)


def test_choosing_none_leaves_the_profile_bare(qtbot, tmp_path):
    controller = _configure(tmp_path, "None (no pre-defined Groups)")
    assert _visible_groups(controller) == []


def test_a_profile_that_already_has_groups_is_left_alone(qtbot, tmp_path):
    """Re-seeding would put back every group the user had deleted."""
    controller = _configure(tmp_path, "None (no pre-defined Groups)")
    controller.create_group("500.  Mine")

    again = _configure(tmp_path, None)
    assert _visible_groups(again) == ["500.  Mine"]
