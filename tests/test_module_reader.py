"""Tests for the ERF/module.ifo module reader."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from vaultkeeper.game.game_mapper import UNKNOWN_SAVE_NAME
from vaultkeeper.game.module_reader import NO_DESCRIPTION, ErfModuleReader


def _gff(save_name: str) -> bytes:
    """A minimal module.ifo GFF with one CExoLocString field ``Mod_Name``."""
    contents = save_name.encode("ascii")
    substr = struct.pack("<II", 0, len(contents)) + contents  # stringId 0 (English)
    locstr = struct.pack("<III", 8 + len(substr), 0, 1) + substr
    struct_arr = struct.pack("<iII", -1, 0, 1)  # root struct, 1 field
    field_arr = struct.pack("<iII", 12, 0, 0)  # CExoLocString, label 0, data offset 0
    label_arr = b"Mod_Name".ljust(16, b"\x00")
    field_data = locstr
    field_indices = struct.pack("<I", 0)

    struct_off = 56
    field_off = struct_off + len(struct_arr)
    label_off = field_off + len(field_arr)
    field_data_off = label_off + len(label_arr)
    field_indices_off = field_data_off + len(field_data)
    list_indices_off = field_indices_off + len(field_indices)
    header = b"IFO V3.2" + struct.pack(
        "<12I",
        struct_off, 1, field_off, 1, label_off, 1,
        field_data_off, len(field_data), field_indices_off, len(field_indices),
        list_indices_off, 0,
    )
    return header + struct_arr + field_arr + label_arr + field_data + field_indices


def _erf(save_name: str, description: str, *, loc_count: int = 1) -> bytes:
    gff = _gff(save_name)
    if loc_count:
        desc_b = description.encode("ascii")
        loc = struct.pack("<ii", 0, len(desc_b)) + desc_b
        loc_size = len(desc_b)
    else:
        loc = b""
        loc_size = 0
    key = (
        b"module".ljust(16, b"\x00")
        + struct.pack("<i", 0)
        + struct.pack("<h", 2014)
        + b"\x00\x00"
    )
    loc_off = 32
    keys_off = loc_off + len(loc)
    res_off = keys_off + len(key)
    gff_off = res_off + 8
    res_entry = struct.pack("<Ii", gff_off, len(gff))
    header = b"MOD V1.0" + struct.pack(
        "<6i", loc_count, loc_size, 1, loc_off, keys_off, res_off
    )
    return header + loc + key + res_entry + gff


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


class TestSyntheticModule:
    def test_reads_save_name_and_description(self, tmp_path):
        p = _write(tmp_path, "adv.mod", _erf("Beorunna", "An epic tale"))
        info = ErfModuleReader().read(p)
        assert info is not None
        assert info.save_name == "Beorunna"
        assert info.description == "An epic tale"
        assert info.mod_filename == "adv.mod"

    def test_save_name_leading_space_trimmed(self, tmp_path):
        p = _write(tmp_path, "adv.mod", _erf("   Spaced Name", "d"))
        assert ErfModuleReader().read(p).save_name == "Spaced Name"

    def test_illegal_folder_chars_removed(self, tmp_path):
        p = _write(tmp_path, "adv.mod", _erf('My:Save/Name?"', "d"))
        assert ErfModuleReader().read(p).save_name == "MySaveName"

    def test_no_localized_description(self, tmp_path):
        p = _write(tmp_path, "adv.mod", _erf("Name", "", loc_count=0))
        assert ErfModuleReader().read(p).description == NO_DESCRIPTION

    def test_not_an_erf_returns_none(self, tmp_path):
        p = _write(tmp_path, "junk.mod", b"NOPE" + b"\x00" * 40)
        assert ErfModuleReader().read(p) is None

    def test_missing_module_ifo_yields_unknown_save(self, tmp_path):
        # An ERF whose key list has no "module"/2014 entry.
        gff = _gff("x")
        key = b"other".ljust(16, b"\x00") + struct.pack("<ih", 0, 9999) + b"\x00\x00"
        loc_off, keys_off = 32, 32
        res_off = keys_off + len(key)
        gff_off = res_off + 8
        data = (
            b"MOD V1.0"
            + struct.pack("<6i", 0, 0, 1, loc_off, keys_off, res_off)
            + key
            + struct.pack("<Ii", gff_off, len(gff))
            + gff
        )
        p = _write(tmp_path, "adv.mod", data)
        assert ErfModuleReader().read(p).save_name == UNKNOWN_SAVE_NAME

    def test_missing_file_returns_none(self, tmp_path):
        assert ErfModuleReader().read(tmp_path / "nope.mod") is None


_REAL_DIRS = [
    Path.home() / "Documents" / "Neverwinter Nights" / "modules",
    (
        Path.home()
        / "Library/Application Support/Steam/steamapps/common"
        / "Neverwinter Nights/data/nwm"
    ),
]


def _first_real_module() -> Path | None:
    """A real module to read, or ``None`` — probing must never abort collection.

    This runs at import time, inside a ``skipif``. ``iterdir`` can raise as well
    as return nothing: macOS guards Documents behind a privacy grant, and
    without it the probe raises ``PermissionError`` and takes the whole test
    session down at collection. "Cannot look" and "nothing there" mean the same
    thing to a skip, so both answer ``None``.
    """
    for d in _REAL_DIRS:
        try:
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in (".mod", ".nwm"):
                    return p
        except OSError:
            continue
    return None


@pytest.mark.skipif(
    _first_real_module() is None, reason="No real NWN modules on this machine"
)
class TestRealModules:
    def test_reads_real_module_save_names(self):
        reader = ErfModuleReader()
        read_ok = 0
        for d in _REAL_DIRS:
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir())[:10]:
                if p.suffix.lower() not in (".mod", ".nwm"):
                    continue
                info = reader.read(p)
                assert info is not None, f"failed to read {p.name}"
                # Real modules resolve to a real save name, not the failure sentinel.
                assert info.save_name and info.save_name != UNKNOWN_SAVE_NAME
                read_ok += 1
        assert read_ok > 0
