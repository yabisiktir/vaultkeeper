"""Export a mod to a single file, and import it back (VB ``ModExport`` + import).

The original moves mods between two PCs through a **shared NIT Store**: a network
folder holding the other machine's Profiles tree, with a metadata marker per mod
in ``Data/<profile>/ExportedMods``. Importing copies the whole mod folder across,
merges the play-time files and keeps the local completion history.

This ports the *outcome* without the network. A mod exports to one self-contained
``.vkmod`` archive — its record, its notes, its play time and its files — which
can be copied by any means: a USB stick, a sync folder, an email to yourself. The
shared-store half is not reproduced, because a live share needs a background sync
queue whose payload in VB is only two file types, and because a file you can move
yourself does not go stale when the other machine is switched off.

**``_Downloads`` is excluded unless asked for.** It holds the original archives a
mod was built from, which are routinely larger than everything else combined —
CEP alone is over a gigabyte. The installer payload is what another machine needs
in order to install; the downloads are only needed to *rebuild* the installer.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData

#: The archive's own name for the metadata member.
RECORD_NAME = "vaultkeeper-mod.json"
#: Format marker, so a future change can be recognised rather than guessed at.
FORMAT_VERSION = 1
#: What an exported mod is called.
SUFFIX = ".vkmod"


@dataclass(frozen=True)
class ExportedMod:
    """What an archive says about itself, without unpacking it."""

    path: Path
    mod_name: str
    group: str
    file_count: int
    has_downloads: bool
    version: int = FORMAT_VERSION


def _payload_dirs(include_downloads: bool) -> tuple[str, ...]:
    dirs = (C.MOD_INSTALLER_DIR, C.HISTORY_DIR, C.PUBLISHED_DIR, C.WORKSHOP_DIR)
    return (*dirs, C.DOWNLOADS_DIR) if include_downloads else dirs


def export_mod(
    md: ModData,
    mod_folder: Path,
    dest: Path,
    *,
    notes: str = "",
    include_downloads: bool = False,
    record: dict | None = None,
) -> ExportedMod:
    """Write ``mod_folder`` and its record to ``dest`` as one archive.

    ``record`` is the mod's serialised :class:`ModData` (the caller passes the
    profile store's own ``_mod_to_dict`` output, so the export and the profile
    never drift into two descriptions of the same thing).
    """
    from vaultkeeper.persistence.profile_store import _mod_to_dict

    wanted = _payload_dirs(include_downloads)
    files: list[tuple[Path, str]] = []
    if mod_folder.is_dir():
        for sub in wanted:
            root = mod_folder / sub
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    files.append((path, str(path.relative_to(mod_folder))))
        # Loose files in the mod root (documentation the Doc Organiser copied up).
        for path in sorted(mod_folder.glob("*")):
            if path.is_file():
                files.append((path, path.name))

    dest.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "version": FORMAT_VERSION,
        "mod": record if record is not None else _mod_to_dict(md),
        "notes": notes,
        "has_downloads": include_downloads,
    }
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(RECORD_NAME, json.dumps(header, indent=1))
        for path, arcname in files:
            archive.write(path, f"files/{arcname}")
    return ExportedMod(
        path=dest,
        mod_name=md.mod_name,
        group=md.group,
        file_count=len(files),
        has_downloads=include_downloads,
    )


def describe(path: Path) -> ExportedMod | None:
    """Read an archive's header without extracting it, or ``None`` if unreadable."""
    try:
        with zipfile.ZipFile(path) as archive:
            header = json.loads(archive.read(RECORD_NAME))
            count = sum(1 for n in archive.namelist() if n.startswith("files/"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    mod = header.get("mod", {})
    return ExportedMod(
        path=path,
        mod_name=mod.get("mod_name", path.stem),
        group=mod.get("group", ""),
        file_count=count,
        has_downloads=bool(header.get("has_downloads")),
        version=int(header.get("version", 0)),
    )


def extract(path: Path, mod_folder: Path) -> tuple[dict, str]:
    """Unpack an archive into ``mod_folder``; returns ``(record, notes)``.

    Members are checked to stay inside the target. A zip can name ``../`` or an
    absolute path, and this one may have arrived from another machine, so it is
    not ours to trust.
    """
    with zipfile.ZipFile(path) as archive:
        header = json.loads(archive.read(RECORD_NAME))
        mod_folder.mkdir(parents=True, exist_ok=True)
        root = mod_folder.resolve()
        for name in archive.namelist():
            if not name.startswith("files/") or name.endswith("/"):
                continue
            target = (mod_folder / name[len("files/") :]).resolve()
            if not target.is_relative_to(root):
                continue  # escapes the mod folder: skip it
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as src, target.open("wb") as out:
                out.write(src.read())
    return header.get("mod", {}), header.get("notes", "")
