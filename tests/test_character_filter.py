"""Tests for the character level/class filter (game/character_filter.py)."""

from __future__ import annotations

import pytest

from vaultkeeper.game.character import NON_PC_CLASS_REF, pc_class_names
from vaultkeeper.game.character_filter import (
    FILTER_NAME,
    SHOW_ALL_TEXT,
    CharacterLevelFilter,
    validate_level_filter,
)

# --- validate_level_filter (VB IsValidLevelFilter) ------------------------- #


@pytest.mark.parametrize("text", ["1", "20", "=20", "<15", ">30", "15-20", "40", "20-20"])
def test_validate_accepts_valid(text: str) -> None:
    assert validate_level_filter(text) is None


def test_validate_blank_is_rejected() -> None:
    msg = validate_level_filter("   ")
    assert msg == f"You have not specified a {FILTER_NAME} value"


def test_validate_lone_comparer_is_rejected() -> None:
    assert validate_level_filter("<") == f"You have not specified a {FILTER_NAME} value"
    # ">"-only collapses to empty after the strip; treated as blank, not a crash.
    assert validate_level_filter(">") == f"You have not specified a {FILTER_NAME} value"


def test_validate_too_many_range_parts() -> None:
    assert validate_level_filter("1-2-3") == f"You specified an invalid {FILTER_NAME} format"


def test_validate_non_numeric_char() -> None:
    assert validate_level_filter("2x") == '"x" is not a number'


def test_validate_out_of_range() -> None:
    assert validate_level_filter("41") == "You must specify a number between 1 and 40"
    assert validate_level_filter("0") == "You must specify a number between 1 and 40"


def test_validate_descending_range() -> None:
    assert (
        validate_level_filter("20-15")
        == "The second Character Level must be higher than the first"
    )


def test_validate_strips_gt_symbol() -> None:
    # ">30" is valid: '>' is stripped, leaving the number 30.
    assert validate_level_filter(">30") is None


# --- CharacterLevelFilter.parse (VB LbcFilter_Click) ----------------------- #


def test_parse_bare_number_is_and_higher() -> None:
    f = CharacterLevelFilter.parse("20")
    assert (f.comparer, f.level, f.level_upper) == (">", 20, 0)


def test_parse_gt_symbol_stripped() -> None:
    f = CharacterLevelFilter.parse(">20")
    assert (f.comparer, f.level, f.level_upper) == (">", 20, 0)


def test_parse_equals() -> None:
    f = CharacterLevelFilter.parse("=20")
    assert (f.comparer, f.level) == ("=", 20)


def test_parse_less_than() -> None:
    f = CharacterLevelFilter.parse("<15")
    assert (f.comparer, f.level) == ("<", 15)


def test_parse_less_than_one_becomes_equals() -> None:
    # There are no levels below 1, so "<1" is treated as "=1".
    assert CharacterLevelFilter.parse("<1").comparer == "="


def test_parse_range() -> None:
    f = CharacterLevelFilter.parse("15-20")
    assert (f.comparer, f.level, f.level_upper) == ("", 15, 20)


# --- matches (VB level comparison + ApplyClassFilter) ---------------------- #


def test_matches_and_higher() -> None:
    f = CharacterLevelFilter.parse("20")
    assert f.matches(20, "") and f.matches(40, "")
    assert not f.matches(19, "")


def test_matches_equals() -> None:
    f = CharacterLevelFilter.parse("=20")
    assert f.matches(20, "") and not f.matches(21, "")


def test_matches_less_than() -> None:
    f = CharacterLevelFilter.parse("<20")
    assert f.matches(20, "") and f.matches(1, "") and not f.matches(21, "")


def test_matches_range() -> None:
    f = CharacterLevelFilter.parse("15-20")
    assert f.matches(15, "") and f.matches(20, "") and not f.matches(14, "")
    assert not f.matches(21, "")


def test_matches_class_filter_requires_all_classes() -> None:
    f = CharacterLevelFilter.parse("1", ["Bard", "Red Dragon Disciple"])
    desc = "Foo the Rebel (40)\nBard (8)\nRed Dragon Disciple (10)"
    assert f.matches(40, desc)
    # Missing one of the required classes -> excluded.
    assert not f.matches(40, "Foo the Rebel (40)\nBard (8)")


def test_matches_class_filter_case_insensitive() -> None:
    f = CharacterLevelFilter.parse("1", ["bard"])
    assert f.matches(8, "Some Bard (8)")


# --- label (VB CheckedText + ClassFilterInfo) ------------------------------ #


def test_label_default_is_show_all() -> None:
    assert CharacterLevelFilter().label() == SHOW_ALL_TEXT
    assert CharacterLevelFilter().is_default


def test_label_branches() -> None:
    assert CharacterLevelFilter.parse("=20").label() == "Only Show Level 20"
    assert CharacterLevelFilter.parse("20").label() == "Show Level 20 and higher"
    assert CharacterLevelFilter.parse("<20").label() == "Show Level 20 and lower"
    assert CharacterLevelFilter.parse("15-20").label() == "Show Levels between 15 and 20"


def test_label_class_suffix() -> None:
    f = CharacterLevelFilter.parse("1", ["Bard", "Cleric"])
    assert f.label() == f"{SHOW_ALL_TEXT} for Bard, Cleric"
    assert not f.is_default


# --- pc_class_names (VB ClassInfo.Values Where Ref <> NonPc) --------------- #


def test_pc_class_names_sorted_and_excludes_non_pc() -> None:
    names = pc_class_names()
    assert names == sorted(names)
    # Base + prestige PC classes are present.
    for expected in ("Bard", "Wizard", "Red Dragon Disciple", "Purple Dragon Knight"):
        assert expected in names
    # Non-PC creature classes (ref 8154) are excluded.
    for creature in ("Aberration", "Animal", "Undead", "Ooze"):
        assert creature not in names
    # Commoner has ref 8155 (not the NonPc sentinel), so it is included.
    assert "Commoner" in names
    assert NON_PC_CLASS_REF == 8154
