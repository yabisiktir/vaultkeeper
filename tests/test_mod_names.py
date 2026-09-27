"""Mod names from raw archive names (logic audit N1, N2).

NIT tidies ``angel_falls_prelude_v24.7z`` into "Angel Falls Prelude v24"
(``ModNameFromFile``); Vaultkeeper kept the raw stem. NIT's CamelCase splitter
also damages clean names ("Tales of Arterra ( EE)"), which this port does not do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.core.mod_names import mod_name_from_file
from vaultkeeper.ui.controller import ProfileController


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        # NIT's own results (harness query ``modname``, 2026-09-27).
        ("angel_falls_prelude_v24", "Angel Falls Prelude v24"),
        ("8191_overrides", "8191 Overrides"),
        ("q22", "Project Q v22"),
        ("cep_2.65_haks", "CEP 2.65 Haks"),
        ("tortured_hearts_ii", "Tortured Hearts II"),
        ("the_obsidian_legend", "The Obsidian Legend"),
        # Where this port deliberately differs from NIT.
        ("Tales of Arterra (EE)", "Tales of Arterra (EE)"),  # NIT: "( EE)"
        ("The Aielund Saga", "The Aielund Saga"),  # NIT: double spaces
        ("CEP_v2.x", "CEP v2.x"),  # NIT: "V2.x"
        ("mix_of_things", "Mix of Things"),  # NIT: "MIX" (any I/V/X/L/C/D/M word)
        ("single", "Single"),
        ("q2.2_full", "Q2.2 Full"),
        ("cmp_hak_169", "CMP Hak 169"),
        ("rl_gothic_int_1_5", "Rl Gothic Int 1 5"),
        ("the_lord_of_the_rings_vi", "The Lord of the Rings VI"),
        ("against_the_cult_of_the_reptile_god_2", "Against the Cult of the Reptile God 2"),
    ],
)
def test_mod_name_from_file(stem: str, expected: str) -> None:
    assert mod_name_from_file(stem) == expected


def test_add_mods_from_files_uses_the_tidied_name(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c._extractor = FakeArchiveExtractor(
        contents={"angel_falls_prelude_v24.7z": {"hak/a.hak": b"A"}}
    )
    source = tmp_path / "angel_falls_prelude_v24.7z"
    source.write_bytes(b"7z")

    result = c.add_mods_from_files([source])

    assert result["created"] == ["Angel Falls Prelude v24"]
    assert (profile_mods / "Angel Falls Prelude v24" / "hak" / "a.hak").is_file()
