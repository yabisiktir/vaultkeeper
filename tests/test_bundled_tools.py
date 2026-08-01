"""The 7-Zip we ship, and finding it.

Vaultkeeper has no pure-Python fallback for reading a mod's archive, so a build
that cannot find 7-Zip cannot install anything. These pin that the bundled binary
is present, is preferred over PATH, and actually runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from vaultkeeper.core.archive import (
    SevenZipExtractor,
    bundled_dir,
    bundled_sevenzip,
    platform_slug,
)

_ROOT = Path(__file__).resolve().parents[1]


def test_a_binary_is_committed_for_every_platform_we_build_for():
    """Fetched by scripts/fetch_tools.py; committed so builds need no network."""
    for slug, name in (
        ("macos", "7zz"), ("linux-x64", "7zz"),
        ("linux-arm64", "7zz"), ("windows-x64", "7za.exe"),
    ):
        assert (_ROOT / "external" / "bin" / slug / name).is_file(), f"{slug} missing"


def test_each_one_ships_its_licence():
    """7-Zip's terms: "Redistributions in binary form must reproduce related
    license information from this file"."""
    for slug in ("macos", "linux-x64", "linux-arm64", "windows-x64"):
        licence = _ROOT / "external" / "bin" / slug / "License.txt"
        assert licence.is_file(), f"{slug} has no License.txt"
        assert "GNU LGPL" in licence.read_text(encoding="utf-8", errors="replace")


def test_this_machine_resolves_to_its_own_binary():
    assert platform_slug() in {"macos", "linux-x64", "linux-arm64", "windows-x64"}
    assert bundled_sevenzip() is not None
    assert platform_slug() in str(bundled_sevenzip())


def test_the_bundled_one_wins_over_anything_on_path():
    """A user's own 7-Zip may be any version; ours is the one we tested against."""
    assert SevenZipExtractor().exe == str(bundled_sevenzip())


def test_it_is_found_with_nothing_on_path(monkeypatch):
    """The case that matters on an installed machine."""
    monkeypatch.setenv("PATH", "")
    assert SevenZipExtractor().available


def test_path_is_still_used_when_nothing_is_bundled(monkeypatch):
    """A source checkout without the binaries must keep working."""
    monkeypatch.setattr("vaultkeeper.core.archive.bundled_sevenzip", lambda: None)
    found = SevenZipExtractor()._discover()
    assert found is None or Path(found).name.startswith("7z")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="posix permission bit")
def test_the_binary_is_executable():
    """git and some installers drop the bit; without it the app cannot run it."""
    assert os.access(bundled_sevenzip(), os.X_OK)


@pytest.mark.integration
def test_it_actually_runs_and_round_trips_an_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    source = tmp_path / "src"
    source.mkdir()
    (source / "mod.hak").write_bytes(b"HAK" * 500)

    extractor = SevenZipExtractor()
    assert extractor.create(tmp_path / "m.7z", [source]).ok
    result = extractor.extract(tmp_path / "m.7z", tmp_path / "out")
    assert result.ok
    assert [p.name for p in (tmp_path / "out").rglob("*") if p.is_file()] == ["mod.hak"]


def test_the_version_it_reports_is_the_one_we_pinned():
    """If a refresh silently fetched something else, this is where it shows."""
    import tomllib

    pinned = tomllib.loads((_ROOT / "external" / "tools.toml").read_text())
    version = pinned["sevenzip"]["version"]
    out = subprocess.run(
        [str(bundled_sevenzip())], capture_output=True, text=True, timeout=30
    ).stdout
    assert version in out, f"expected {version} in {out.splitlines()[:2]}"


def test_the_manifest_records_a_checksum_for_every_platform():
    import tomllib

    pinned = tomllib.loads((_ROOT / "external" / "tools.toml").read_text())
    for slug, entry in pinned["sevenzip"]["platforms"].items():
        assert len(entry["sha256"]) == 64, f"{slug} has no pinned checksum"
        assert entry["url"].startswith("https://"), f"{slug} url is not https"


def test_ffmpeg_is_deliberately_not_bundled():
    """It is optional, large, and commonly built GPL — the feature degrades."""
    import tomllib

    pinned = tomllib.loads((_ROOT / "external" / "tools.toml").read_text())
    assert pinned["ffmpeg"]["bundled"] is False
    assert pinned["ffmpeg"]["optional"] is True


def test_bundled_dir_is_found_from_the_installed_layout(monkeypatch, tmp_path):
    """PyInstaller unpacks data beside the executable, not next to the source."""
    frozen = tmp_path / "external" / "bin" / platform_slug()
    frozen.mkdir(parents=True)
    (frozen / "7zz").write_bytes(b"")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert bundled_dir() == tmp_path / "external" / "bin"
