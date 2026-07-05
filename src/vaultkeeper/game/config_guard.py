"""Config-isolation guard — detect game-config changes, never write silently.

A deliberate divergence from the original tool (which rewrote ``nwn.ini`` behind
the user's back): Vaultkeeper keeps its own config and only ever changes game
files through an explicit, user-confirmed sync. This module provides the startup
check that powers that promise.

It fingerprints the game's user-side config files (``nwn.ini``, ``settings.tml``)
and compares the current state to the last snapshot Vaultkeeper recorded. If they
diverge, :meth:`ConfigGuard.check` reports *what* changed so the UI can ask the
user how to proceed. Nothing here modifies any game file; it only reads and
records fingerprints in Vaultkeeper's own config area.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vaultkeeper.app_paths import config_root
from vaultkeeper.persistence.json_store import read_json, write_json

#: Game user-config files Vaultkeeper watches (relative to the NWN user dir).
WATCHED_CONFIG_FILES = ("nwn.ini", "settings.tml")


class ChangeKind(StrEnum):
    ADDED = "added"      # file now present, wasn't in the snapshot
    REMOVED = "removed"  # file was in the snapshot, now gone
    MODIFIED = "modified"  # content hash differs


@dataclass(frozen=True)
class ConfigChange:
    path: Path
    kind: ChangeKind


@dataclass
class Fingerprint:
    """Content fingerprint of a single file."""

    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"sha256": self.sha256, "size": self.size}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Fingerprint:
        return cls(sha256=str(data["sha256"]), size=int(data["size"]))  # type: ignore[call-overload]


def fingerprint_file(path: Path) -> Fingerprint | None:
    """SHA-256 + size of ``path``; ``None`` if it does not exist."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return Fingerprint(sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def snapshot(
    nwn_user_dir: Path, files: tuple[str, ...] = WATCHED_CONFIG_FILES
) -> dict[str, Fingerprint]:
    """Fingerprint the watched config files under ``nwn_user_dir``.

    Only existing files appear in the result (a missing file simply isn't a key).
    """
    result: dict[str, Fingerprint] = {}
    for name in files:
        fp = fingerprint_file(nwn_user_dir / name)
        if fp is not None:
            result[name] = fp
    return result


def diff_snapshots(
    previous: dict[str, Fingerprint],
    current: dict[str, Fingerprint],
    nwn_user_dir: Path,
) -> list[ConfigChange]:
    """Compute what changed between two snapshots."""
    changes: list[ConfigChange] = []
    for name in sorted(set(previous) | set(current)):
        old, new = previous.get(name), current.get(name)
        path = nwn_user_dir / name
        if old is None and new is not None:
            changes.append(ConfigChange(path, ChangeKind.ADDED))
        elif old is not None and new is None:
            changes.append(ConfigChange(path, ChangeKind.REMOVED))
        elif old is not None and new is not None and old.sha256 != new.sha256:
            changes.append(ConfigChange(path, ChangeKind.MODIFIED))
    return changes


class ConfigGuard:
    """Persists the last-seen game-config snapshot and detects divergence.

    The snapshot lives in Vaultkeeper's config area (never in the game folder).
    Call :meth:`check` at startup; if it returns changes, prompt the user. Only
    after the user decides do you call :meth:`accept` to record the new baseline.
    """

    def __init__(self, nwn_user_dir: Path, snapshot_path: Path | None = None) -> None:
        self.nwn_user_dir = nwn_user_dir
        self._path = snapshot_path or (config_root() / "game_config_snapshot.json")

    def _load(self) -> dict[str, Fingerprint]:
        raw = read_json(self._path, default={}) or {}
        out: dict[str, Fingerprint] = {}
        for name, data in raw.items():
            if isinstance(data, dict) and "sha256" in data and "size" in data:
                out[str(name)] = Fingerprint.from_dict(data)
        return out

    def check(self) -> list[ConfigChange]:
        """Return game-config changes since the recorded baseline (read-only).

        An empty list means "in sync" (or no baseline yet + no config present).
        On first run with a config present, every file reports as ADDED, letting
        the UI establish an initial baseline with the user's blessing.
        """
        return diff_snapshots(self._load(), snapshot(self.nwn_user_dir), self.nwn_user_dir)

    def accept(self) -> dict[str, Fingerprint]:
        """Record the current game config as the new baseline (writes only VK's snapshot)."""
        current = snapshot(self.nwn_user_dir)
        write_json(self._path, {name: fp.to_dict() for name, fp in current.items()})
        return current

    def has_baseline(self) -> bool:
        return self._path.exists()
