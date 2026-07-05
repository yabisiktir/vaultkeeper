"""Tests for Vaultkeeper's isolated store/config layout."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.app_paths import VaultStore


def test_store_layout_is_under_root(tmp_path: Path) -> None:
    store = VaultStore(root=tmp_path / "Store")
    assert store.profiles == tmp_path / "Store/Profiles"
    assert store.data == tmp_path / "Store/Data"
    assert store.backups == tmp_path / "Store/Backups"
    assert store.archived_saves == tmp_path / "Store/Archived Saves"


def test_profile_dirs(tmp_path: Path) -> None:
    store = VaultStore(root=tmp_path / "Store")
    assert store.profile_dir("My Mods") == tmp_path / "Store/Profiles/My Mods"
    assert store.profile_data_dir("My Mods") == tmp_path / "Store/Data/My Mods"


def test_ensure_creates_tree(tmp_path: Path) -> None:
    store = VaultStore(root=tmp_path / "Store")
    store.ensure()
    for path in (
        store.root,
        store.profiles,
        store.data,
        store.backups,
        store.archived_saves,
        store.exported_settings,
        store.temp,
    ):
        assert path.is_dir()


def test_ensure_is_idempotent(tmp_path: Path) -> None:
    store = VaultStore(root=tmp_path / "Store")
    store.ensure()
    store.ensure()  # must not raise
    assert store.root.is_dir()


def test_network_store_detected(tmp_path: Path) -> None:
    # A store rooted on a network-looking path reports itself as network.
    store = VaultStore(root=Path("/Volumes/NAS/Vaultkeeper/Store"))
    assert store.is_network() is True
    local = VaultStore(root=tmp_path / "Store")
    assert local.is_network() is False
