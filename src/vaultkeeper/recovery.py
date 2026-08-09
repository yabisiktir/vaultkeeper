"""Restoring a profile store from a backup, without loading it first.

Kept out of the controller on purpose. The whole point of this path is that it
runs when the store cannot be loaded, so nothing here may depend on a loaded
profile — it works on file names and bytes only.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def profile_name_for(backup: Path) -> str:
    """The profile a backup belongs to.

    Backups are written as ``<profile> (<tag> <stamp>).json``
    (``ProfileController._backup_profile_store``), so the name is everything
    before the bracket. A file with no bracket restores to its own stem, which
    is what a hand-copied one looks like.
    """
    stem = backup.stem
    head, sep, _rest = stem.partition(" (")
    return (head if sep else stem).strip()


def data_backups(store_root: Path) -> list[Path]:
    """Every profile-store backup, newest first."""
    backups = store_root / "Backups"
    if not backups.is_dir():
        return []
    return sorted(
        (p for p in backups.glob("*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def restore_backup(backup: Path, store_root: Path) -> str:
    """Copy ``backup`` over the profile store it came from.

    The file being replaced is moved aside first, with a stamp, so restoring the
    wrong backup costs one more restore rather than the data. Returns a sentence
    for the caller to show.
    """
    profile = profile_name_for(backup)
    target = store_root / "Data" / f"{profile}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    replaced = None
    if target.is_file():
        stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        replaced = target.with_name(f"{profile} (replaced {stamp}).json")
        shutil.move(str(target), replaced)
    shutil.copy2(backup, target)

    message = f"Restored {profile} from {backup.name}."
    if replaced is not None:
        message += f" The file it replaced was kept as {replaced.name}."
    return message
