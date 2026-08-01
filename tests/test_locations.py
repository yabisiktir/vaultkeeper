"""Tests for cross-platform NWN discovery and path handling.

These run headless and never touch a real game install — they build fake install
trees under tmp_path and drive the discovery/resolution helpers directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nwnfile.editions import Edition
from nwnfile.locations import (
    GameInstall,
    HostOS,
    InstallKind,
    discover_installs,
    is_network_path,
    looks_like_nwn_root,
    resolve_wine_path,
    user_documents_dir,
)


def _make_nwn_root(base: Path) -> Path:
    root = base / "Neverwinter Nights"
    (root / "data").mkdir(parents=True)
    (root / "bin").mkdir()
    return root


def test_looks_like_nwn_root_detects_data_marker(tmp_path: Path) -> None:
    root = _make_nwn_root(tmp_path)
    assert looks_like_nwn_root(root)


def test_looks_like_nwn_root_detects_executable(tmp_path: Path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    (root / "nwmain").write_bytes(b"\x00")
    assert looks_like_nwn_root(root)


def test_looks_like_nwn_root_rejects_empty(tmp_path: Path) -> None:
    empty = tmp_path / "nope"
    empty.mkdir()
    assert not looks_like_nwn_root(empty)


def test_looks_like_nwn_root_rejects_missing(tmp_path: Path) -> None:
    assert not looks_like_nwn_root(tmp_path / "does-not-exist")


@pytest.mark.parametrize(
    "path,expected",
    [
        (r"\\nas\games\nwn", True),
        ("//nas/games/nwn", True),
        ("/Volumes/Games/NWN", True),
        ("/mnt/share/nwn", True),
        ("/media/user/usb/nwn", True),
        ("/net/host/nwn", True),
        ("/home/user/nwn", False),
        ("/Users/me/Games/NWN", False),
        ("C:/Program Files/NWN", False),
    ],
)
def test_is_network_path(path: str, expected: bool) -> None:
    assert is_network_path(path) is expected


def test_resolve_wine_path_default_drive_c(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    resolved = resolve_wine_path(r"C:\Program Files\Neverwinter Nights", prefix)
    assert resolved == prefix / "drive_c/Program Files/Neverwinter Nights"


def test_resolve_wine_path_honours_dosdevices(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    dosdev = prefix / "dosdevices/d:"
    target = tmp_path / "external_drive"
    target.mkdir()
    dosdev.parent.mkdir(parents=True)
    dosdev.symlink_to(target, target_is_directory=True)
    resolved = resolve_wine_path(r"D:\Games\NWN", prefix)
    assert resolved == (dosdev / "Games/NWN").resolve()


def test_discover_installs_finds_extra_network_root(tmp_path: Path) -> None:
    # Simulate a mounted network game folder supplied explicitly.
    net_base = tmp_path / "Volumes/Games"
    root = _make_nwn_root(net_base)
    installs = discover_installs(host=HostOS.LINUX, include_wine=False, extra_roots=[root])
    assert any(i.root == root and i.kind is InstallKind.MANUAL for i in installs)


def test_discover_installs_dedupes(tmp_path: Path) -> None:
    root = _make_nwn_root(tmp_path)
    installs = discover_installs(
        host=HostOS.LINUX, include_wine=False, extra_roots=[root, root]
    )
    matching = [i for i in installs if i.root == root]
    assert len(matching) == 1


def test_user_documents_dir_wine_uses_prefix(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    (prefix / "drive_c/users/gamer/Documents").mkdir(parents=True)
    docs = user_documents_dir(HostOS.LINUX, wine_prefix=prefix)
    assert docs == prefix / "drive_c/users/gamer/Documents/Neverwinter Nights"


def test_game_install_edition_defaults_to_enhanced() -> None:
    install = GameInstall(root=Path("/tmp/nwn"))
    assert install.edition is Edition.ENHANCED
    assert install.edition.steam_app_id == "704450"
