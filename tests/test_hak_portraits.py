"""Tests for extracting portraits from hak files (VB ExtractHakPortraits).

Builds synthetic haks containing portrait TGA resources (via the ERF fixture) and
checks the complete-set filtering, the L→H fixup, and the controller ops.
"""

from __future__ import annotations

import struct
from pathlib import Path

from nwnfile.character import extract_hak_portraits
from nwnfile.formats.erf_reader import ErfReader

from vaultkeeper.ui.controller import ProfileController

_TGA = 3
_TXT = 10


def _build_hak(resources: list[tuple[str, int, bytes]]) -> bytes:
    """A minimal ERF (HAK) holding (resref, res_type, data) resources."""
    n = len(resources)
    keys_off, res_off = 32, 32 + n * 24
    data_off = res_off + n * 8
    out = b"HAK V1.0" + struct.pack("<6i", 0, 0, n, keys_off, keys_off, res_off)
    keys = reslist = blob = b""
    cursor = data_off
    for rid, (ref, rtype, data) in enumerate(resources):
        keys += ref.encode().ljust(16, b"\x00") + struct.pack("<iH", rid, rtype) + b"\x00\x00"
        reslist += struct.pack("<Ii", cursor, len(data))
        blob += data
        cursor += len(data)
    return out + keys + reslist + blob


def _portrait_set(base: str, sizes: str = "tsmlh") -> list[tuple[str, int, bytes]]:
    return [(f"{base}{s}", _TGA, f"{base}{s}-data".encode()) for s in sizes]


def test_extract_complete_portrait(tmp_path: Path) -> None:
    hak = tmp_path / "port.hak"
    hak.write_bytes(_build_hak(_portrait_set("po_hero")))
    count = extract_hak_portraits(hak, tmp_path / "out", erf_reader=ErfReader())
    assert count == 1
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} == {
        "po_heroh.tga", "po_herol.tga", "po_herom.tga", "po_heros.tga", "po_herot.tga"
    }


def test_incomplete_set_discarded(tmp_path: Path) -> None:
    hak = tmp_path / "port.hak"
    # Only 3 sizes (t/s/m) → not a complete portrait → all discarded.
    hak.write_bytes(_build_hak(_portrait_set("po_partial", "tsm")))
    count = extract_hak_portraits(hak, tmp_path / "out", erf_reader=ErfReader())
    assert count == 0
    assert list((tmp_path / "out").iterdir()) == []


def test_missing_huge_created_from_large(tmp_path: Path) -> None:
    hak = tmp_path / "port.hak"
    # t/s/m/l present but no h → h is copied from l (VB missingH fixup).
    hak.write_bytes(_build_hak(_portrait_set("po_king", "tsml")))
    count = extract_hak_portraits(hak, tmp_path / "out", erf_reader=ErfReader())
    assert count == 1
    huge = tmp_path / "out" / "po_kingh.tga"
    assert huge.is_file()
    assert huge.read_bytes() == (tmp_path / "out" / "po_kingl.tga").read_bytes()


def test_non_portrait_tgas_removed(tmp_path: Path) -> None:
    hak = tmp_path / "mix.hak"
    resources = _portrait_set("po_hero") + [
        ("gui_button", _TGA, b"guidata"),  # not a portrait suffix
        ("readme", _TXT, b"text"),  # not even a tga
    ]
    hak.write_bytes(_build_hak(resources))
    count = extract_hak_portraits(hak, tmp_path / "out", erf_reader=ErfReader())
    assert count == 1
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert "gui_button.tga" not in names
    assert "readme.txt" not in names  # non-tga never extracted


# -- Controller ------------------------------------------------------------- #


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Data-root" / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data-root" / "Data" / "P.json",
    )


def test_controller_extract_and_clear(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    hak_dir = controller.ctx.profile_mods_dir / "Mod" / ".Mod Installer" / "hak"
    hak_dir.mkdir(parents=True)
    (hak_dir / "port.hak").write_bytes(_build_hak(_portrait_set("po_npc")))

    result = controller.extract_mod_hak_portraits("Mod")
    assert result["count"] == 1
    root = controller.hak_portraits_root()
    assert (root / "port.hak" / "po_npch.tga").is_file()
    # Extracted portraits are now in the search path.
    assert any("Portraits Extracted" in str(d) for d in controller.portrait_search_dirs())

    cleared = controller.clear_hak_portraits()
    assert cleared["cleared"] is True
    assert not root.exists()


def test_controller_no_portraits_leaves_no_folder(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    hak = tmp_path / "empty.hak"
    hak.write_bytes(_build_hak([("readme", _TXT, b"x")]))
    result = controller.extract_hak_portraits(hak)
    assert result["count"] == 0
    assert not (controller.hak_portraits_root() / "empty.hak").exists()
