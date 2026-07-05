"""Vaultkeeper's own on-disk layout — deliberately isolated from the game.

Design principle (a deliberate divergence from the original NIT, per the rehaul
decisions): Vaultkeeper keeps **its own** configuration and data store and does
**not** silently overwrite the game's ``nwn.ini`` / ``settings.tml`` under
``Documents/Neverwinter Nights``. Game files are only ever touched through an
explicit, user-confirmed sync (see :mod:`vaultkeeper.game` sync, added later).

This module resolves platform-appropriate config/data/cache roots (XDG on Linux,
``Application Support`` on macOS, ``%APPDATA%``/``%LOCALAPPDATA%`` on Windows)
and defines the "Vault Store" tree that replaces NIT's "NIT Store".
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_APP_NAME = "Vaultkeeper"
_APP_DIRNAME = "vaultkeeper"  # lower-case for XDG/dotfile style


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def config_root() -> Path:
    """Base directory for Vaultkeeper's configuration files."""
    if sys.platform == "darwin":
        return _home() / "Library/Application Support" / _APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(_home() / "AppData/Roaming")
        return Path(base) / _APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(_home() / ".config")
    return Path(base) / _APP_DIRNAME


def data_root() -> Path:
    """Base directory for Vaultkeeper's data store (profiles, backups, notes)."""
    if sys.platform == "darwin":
        return _home() / "Library/Application Support" / _APP_NAME / "Store"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData/Local")
        return Path(base) / _APP_NAME / "Store"
    base = os.environ.get("XDG_DATA_HOME") or str(_home() / ".local/share")
    return Path(base) / _APP_DIRNAME / "Store"


def cache_root() -> Path:
    """Base directory for disposable caches (extracted archives, thumbnails)."""
    if sys.platform == "darwin":
        return _home() / "Library/Caches" / _APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData/Local")
        return Path(base) / _APP_NAME / "Cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(_home() / ".cache")
    return Path(base) / _APP_DIRNAME


@dataclass(frozen=True)
class VaultStore:
    """The Vaultkeeper data-store tree (analogue of NIT's ``NIT Store``).

    A single ``root`` (default :func:`data_root`, but relocatable — including to a
    network path) with a fixed sub-layout. Paths are computed, not created;
    :meth:`ensure` makes the directories on demand.
    """

    root: Path

    @classmethod
    def default(cls) -> VaultStore:
        return cls(root=data_root())

    # -- Top-level sub-trees (mirror NIT's store concepts) ------------------- #
    @property
    def profiles(self) -> Path:
        """Per-profile mod libraries (one directory per profile)."""
        return self.root / "Profiles"

    @property
    def data(self) -> Path:
        """Per-profile database files (native Vaultkeeper JSON store)."""
        return self.root / "Data"

    @property
    def backups(self) -> Path:
        return self.root / "Backups"

    @property
    def archived_saves(self) -> Path:
        return self.root / "Archived Saves"

    @property
    def exported_settings(self) -> Path:
        return self.root / "Exported Settings"

    @property
    def temp(self) -> Path:
        return self.root / "Temp"

    # -- Config file (kept in config_root, not the store) ------------------- #
    @property
    def settings_file(self) -> Path:
        return config_root() / "settings.json"

    def profile_dir(self, profile_name: str) -> Path:
        return self.profiles / profile_name

    def profile_data_dir(self, profile_name: str) -> Path:
        return self.data / profile_name

    def is_network(self) -> bool:
        from vaultkeeper.game.locations import is_network_path

        return is_network_path(self.root)

    def ensure(self) -> None:
        """Create the store's directory tree (idempotent)."""
        for path in (
            self.root,
            self.profiles,
            self.data,
            self.backups,
            self.archived_saves,
            self.exported_settings,
            self.temp,
            config_root(),
        ):
            path.mkdir(parents=True, exist_ok=True)
