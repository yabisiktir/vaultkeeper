"""Tests for the ProfileData dependency graph."""

from __future__ import annotations

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State


def _pd() -> ProfileData:
    pd = ProfileData()
    for name in ("Base Mod", "Mod 2", "Mod 10"):
        pd.add_mod(ModData(group="G", mod_name=name))
    return pd


def test_has_dependants() -> None:
    pd = _pd()
    pd.mod_item("Mod 2").dependencies.append("Base Mod")
    assert pd.has_dependants("Base Mod")
    assert pd.has_dependants("base mod")  # case-insensitive
    assert not pd.has_dependants("Mod 10")


def test_validate_removes_invalid() -> None:
    pd = _pd()
    md = pd.mod_item("Mod 2")
    md.dependencies.extend(["Base Mod", "Ghost Mod"])  # Ghost Mod doesn't exist
    removed = pd.validate_dependencies()
    assert removed == 1
    assert md.dependencies == ["Base Mod"]


def test_get_dependants_sorted() -> None:
    pd = _pd()
    pd.mod_item("Mod 10").dependencies.append("Base Mod")
    pd.mod_item("Mod 2").dependencies.append("Base Mod")
    dependants = pd.get_dependants()
    # Values sorted by natural order: "Mod 2" before "Mod 10".
    assert dependants["Base Mod"] == ["Mod 2", "Mod 10"]


def test_get_installed_dependants() -> None:
    pd = _pd()
    pd.mod_item("Base Mod").mod_state = State.INSTALLED
    pd.mod_item("Mod 2").mod_state = State.INSTALLED
    pd.mod_item("Mod 2").dependencies.append("Base Mod")
    # Mod 10 depends on Base Mod but is NOT installed -> excluded.
    pd.mod_item("Mod 10").dependencies.append("Base Mod")
    installed = pd.get_installed_dependants()
    assert installed == {"Base Mod": ["Mod 2"]}
