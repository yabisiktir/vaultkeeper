"""Tests for the case-insensitive string dict."""

from __future__ import annotations

from vaultkeeper.core.ci_dict import CIStrDict


def test_case_insensitive_get_set() -> None:
    d: CIStrDict[int] = CIStrDict()
    d["Mod A"] = 1
    assert d["mod a"] == 1
    assert "MOD A" in d
    d["MOD A"] = 2  # overwrites same key
    assert len(d) == 1
    assert d["Mod A"] == 2


def test_preserves_original_casing_on_iter() -> None:
    d: CIStrDict[int] = CIStrDict()
    d["Cool Mod"] = 1
    d["cool mod"] = 2  # update keeps first-seen casing
    assert list(d) == ["Cool Mod"]
    assert list(d.keys()) == ["Cool Mod"]


def test_delete_and_pop() -> None:
    d: CIStrDict[int] = CIStrDict()
    d["X"] = 1
    del d["x"]
    assert "X" not in d
    d["Y"] = 5
    assert d.pop("y") == 5
    assert len(d) == 0


def test_items_and_values() -> None:
    d: CIStrDict[str] = CIStrDict()
    d["A"] = "a"
    d["B"] = "b"
    assert dict(d.items()) == {"A": "a", "B": "b"}
    assert sorted(d.values()) == ["a", "b"]
