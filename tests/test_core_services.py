"""Tests for the Phase 0 infrastructure services: constants, crc, fs, json store."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from vaultkeeper.core import constants as C
from vaultkeeper.core.crc import crc32_bytes, crc32_file
from vaultkeeper.core.fs import FsError, copy_file, delete, ensure_dir, move_file
from vaultkeeper.persistence.json_store import StoreError, read_json, write_json


# --- constants (data-contract values verified against VB source) ---------- #
def test_group_sentinels_match_vb() -> None:
    assert C.GROUP_INSTALLED == "......000"
    assert C.GROUP_NONE == "......001"
    assert C.INSTALLED_MOD_KEY == "......000/Installed Files"
    assert C.MANDATORY_GROUPS == (C.GROUP_NONE, C.GROUP_INSTALLED)


def test_small_file_crc_guard_value() -> None:
    assert C.NO_CRC_CHECK_MAX_BYTES == 1024 * 5 + 1  # VB: NoCrcCheckRequired


def test_legacy_versions() -> None:
    assert C.LEGACY_DATA_FORMAT_VERSION == 2
    assert C.LEGACY_MAP_VERSION == 21


def test_reserved_mod_names() -> None:
    assert "_Downloads" in C.RESERVED_MOD_NAMES
    assert C.MOD_INSTALLER_DIR == ".Mod Installer"


# --- crc ------------------------------------------------------------------ #
def test_crc32_bytes_matches_zlib() -> None:
    data = b"neverwinter"
    assert crc32_bytes(data) == (zlib.crc32(data) & 0xFFFFFFFF)


def test_crc32_file_streaming_equals_whole(tmp_path: Path) -> None:
    payload = b"x" * (3 * (1 << 20) + 17)  # spans multiple 1 MiB chunks
    f = tmp_path / "blob.bin"
    f.write_bytes(payload)
    assert crc32_file(f) == crc32_bytes(payload)


def test_crc32_file_empty(tmp_path: Path) -> None:
    f = tmp_path / "empty"
    f.write_bytes(b"")
    assert crc32_file(f) == 0


# --- fs ------------------------------------------------------------------- #
def test_copy_file_creates_dirs(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hi")
    dst = tmp_path / "sub/dir/b.txt"
    copy_file(src, dst)
    assert dst.read_text() == "hi"


def test_copy_no_overwrite_raises(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hi")
    dst = tmp_path / "b.txt"
    dst.write_text("old")
    with pytest.raises(FsError):
        copy_file(src, dst, overwrite=False)


def test_move_file(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hi")
    dst = tmp_path / "moved/a.txt"
    move_file(src, dst)
    assert dst.read_text() == "hi"
    assert not src.exists()


def test_delete_permanent(tmp_path: Path) -> None:
    d = ensure_dir(tmp_path / "tree")
    (d / "f.txt").write_text("x")
    delete(d)
    assert not d.exists()


def test_delete_missing_ok(tmp_path: Path) -> None:
    delete(tmp_path / "nope", missing_ok=True)  # no raise
    with pytest.raises(FsError):
        delete(tmp_path / "nope", missing_ok=False)


# --- json store ----------------------------------------------------------- #
def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "x/data.json"
    payload = {"b": 2, "a": [1, 2, 3], "u": "nëver"}
    write_json(p, payload)
    assert read_json(p) == payload


def test_read_missing_returns_default(tmp_path: Path) -> None:
    assert read_json(tmp_path / "absent.json", default={"k": 1}) == {"k": 1}


def test_read_invalid_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{ not json")
    with pytest.raises(StoreError):
        read_json(p)


def test_write_is_atomic_no_temp_left(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    write_json(p, {"ok": True})
    leftovers = [x for x in tmp_path.iterdir() if x.name != "data.json"]
    assert leftovers == []
