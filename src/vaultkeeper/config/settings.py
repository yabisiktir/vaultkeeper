"""Vaultkeeper application settings — one typed, versioned, isolated store.

This replaces (a) the VB app's ~180 ``My.Settings`` entries and (b) the earlier
Python port's *two* competing settings systems that wrote two different files.
There is exactly one settings file, in the OS config dir (see
:func:`vaultkeeper.app_paths.VaultStore.settings_file`), and it is Vaultkeeper's
own — the game's ``nwn.ini``/``settings.tml`` are never written here.

Only the handful of settings the foundation needs are modelled now; the field
set grows per phase. Unknown keys in an on-disk file are preserved on save
(forward-compatibility) and a ``version`` field allows future migrations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from vaultkeeper.app_paths import VaultStore
from vaultkeeper.persistence.json_store import read_json, write_json

SETTINGS_VERSION = 1


def default_web_links() -> list[dict[str, str]]:
    """The default Web-menu links (VB ``Defs.DefaultWebMenu``).

    Text/URL pairs from the app's ``Application Definitions.txt``; ``&`` mnemonics
    are preserved so Qt renders the same accelerators as the VB menu.
    """
    return [
        {"text": "The Neverwinter &Vault", "url": "https://neverwintervault.org"},
        {
            "text": "&Nexus Neverwinter Nights",
            "url": "https://www.nexusmods.com/neverwinter",
        },
    ]


@dataclass
class Settings:
    """The application settings model.

    Paths are stored as strings (JSON-friendly); ``None`` means "not yet set".
    """

    version: int = SETTINGS_VERSION
    #: Where Vaultkeeper keeps its own store; ``None`` = use the platform default.
    store_root: str | None = None
    #: Last used / active NWN install root.
    nwn_path: str | None = None
    #: Name of the active profile.
    active_profile: str | None = None
    #: Send user-initiated deletes to the OS trash rather than deleting permanently.
    recycle_on_delete: bool = True
    #: On startup, check whether the game config diverged and prompt before syncing
    #: (config-isolation principle — never sync silently).
    validate_game_config_on_startup: bool = True
    #: Convert ``.bik`` movies to ``.wbm`` when building an installer (VB
    #: ``ProfileInfo.ConvertBikFiles``; NWN:EE plays WebM, not Bink).
    convert_bik_files: bool = False
    #: User's Web-menu links (``[{"text", "url"}, ...]``); defaults to Vault + Nexus.
    web_links: list[dict[str, str]] = field(default_factory=default_web_links)
    #: User map overrides ``{table: {key: folder}}`` merged onto the Mapper's default
    #: tables (VB My.Settings map customisations); empty = pure v21 defaults.
    map_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    #: User exclude additions ``{"files": [...], "folders": [...]}`` the installer
    #: scan skips (VB Settings "Excluded Items"); empty = default excludes only.
    map_exclude_overrides: dict[str, list[str]] = field(default_factory=dict)

    #: Keys present in the file that this version doesn't model, kept for round-trip.
    _extra: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- (de)serialisation -------------------------------------------------- #
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        known = {f.name for f in fields(cls) if not f.name.startswith("_")}
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        obj = cls(**kwargs)
        obj._extra = extra
        return obj

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        out.update(self._extra)
        return out

    # -- convenience -------------------------------------------------------- #
    def resolved_store(self) -> VaultStore:
        """The store this configuration points at (custom root or default)."""
        if self.store_root:
            return VaultStore(root=Path(self.store_root))
        return VaultStore.default()


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an on-disk settings dict to the current version in place.

    No historical versions exist yet; this is the seam future migrations use.
    """
    version = int(data.get("version", SETTINGS_VERSION))
    # future: while version < SETTINGS_VERSION: ...
    data["version"] = max(version, SETTINGS_VERSION) if version else SETTINGS_VERSION
    return data


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from ``path`` (default: the platform settings file).

    A missing file yields defaults; a corrupt file raises (surfaced to the user
    rather than silently reset).
    """
    settings_path = Path(path) if path is not None else VaultStore.default().settings_file
    data = read_json(settings_path, default=None)
    if data is None:
        return Settings()
    if not isinstance(data, dict):
        from vaultkeeper.persistence.json_store import StoreError

        raise StoreError(f"settings file is not an object: {settings_path}")
    return Settings.from_dict(_migrate(dict(data)))


def save_settings(settings: Settings, path: str | Path | None = None) -> Path:
    """Persist settings atomically to ``path`` (default: platform settings file)."""
    settings_path = Path(path) if path is not None else settings.resolved_store().settings_file
    return write_json(settings_path, settings.to_dict())
