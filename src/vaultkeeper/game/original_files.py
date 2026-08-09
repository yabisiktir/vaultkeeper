"""Original NWN installation files — CRC tables + restorer detection.

Ported from ``ProfileData`` (``OriginalFiles`` / ``OriginalSourceFiles`` /
``ValidateOriginals``) and the ``AutoOriginalRestorer`` subsystem. The original tool
ships a table of every file the NWN / NWN:EE setup program lays down, keyed by
``folder\\filename`` with its CRC-32. A currently-installed file whose CRC matches its
table entry is a *pristine original* — one that no mod has changed — which the
**Create Original Restorers** command can back up into restorer mods so the base game
can be reinstalled later.

The CRC tables are the VB ``My.Resources.OriginalFiles`` / ``OriginalEeFiles``
BinaryFormatter blobs, extracted to bundled JSON (``game/data/original_files.json`` /
``original_ee_files.json``). VB CRCs are signed 32-bit; they are normalised to unsigned
here to match :func:`vaultkeeper.core.crc.crc32_file`.

BOUNDED PORT (noted): the classic-vs-EE table merge is the classic table plus the EE
overrides (VB ``UseNwOriginal`` additionally swaps in per-file *OriginalNwnCrcValues*,
a table not bundled here); the pristine-original test uses the CRC + mapped-extension +
installer checks but not the finer restorer-membership CRC comparison (VB
``OriginalSourceFile`` last line).
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo

_MASK = 0xFFFFFFFF


def _normalise_key(file_key: str) -> str:
    """A comparable form of a ``folder\\filename`` key (lower, forward slashes)."""
    return file_key.lower().replace("\\", "/")


@cache
def _load_table(name: str) -> dict[str, int]:
    raw = json.loads((files("vaultkeeper.game.data") / name).read_text(encoding="utf-8"))
    return {_normalise_key(k): (int(v) & _MASK) for k, v in raw.items()}


def original_crc_table(*, is_ee: bool, overrides: dict[str, int] | None = None) -> dict[str, int]:
    """The known-original ``folder/filename`` → CRC table for the edition.

    Classic base (VB ``OriginalFiles``); when ``is_ee`` the Enhanced Edition entries
    are added/overridden (VB ``UseEeOriginal``).

    ``overrides`` is the profile's own table (``ProfileData.original_ee_files``),
    built by *Update Enhanced Edition Files* after Beamdog or Steam has patched
    the game. The bundled table is a snapshot of one version, so without this
    every file an update touched looks like a file some mod changed.
    """
    table = dict(_load_table("original_files.json"))
    if is_ee:
        table.update(_load_table("original_ee_files.json"))
    if overrides:
        table.update({_normalise_key(k): (int(v) & _MASK) for k, v in overrides.items()})
    return table


#: The EE library folders whose contents ship with the game (VB ``DefineEeFolders``
#: — mod, mus, nwm, txpk — plus the EE override, ``ovr``).
EE_ORIGINAL_FOLDERS = ("mod", "mus", "nwm", "txpk", "ovr")


def scan_ee_originals(game_folders: dict, *, on_progress=None) -> dict[str, int]:
    """CRC every file the Enhanced Edition ships (VB ``UpdateEeFiles``' scan).

    Keyed the same way as the bundled table, so the two can simply be compared.
    """
    from vaultkeeper.core.crc import crc32_file

    found: dict[str, int] = {}
    for name in EE_ORIGINAL_FOLDERS:
        folder = game_folders.get(name)
        if folder is None or not folder.is_dir():
            continue
        if on_progress is not None:
            on_progress(name)
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            try:
                found[_normalise_key(f"{name}/{path.name}")] = crc32_file(path) & _MASK
            except OSError:
                continue
    return found


def ee_original_changes(
    scanned: dict[str, int], *, known: dict[str, int]
) -> dict[str, dict[str, int]]:
    """Split a scan into what is new and what has changed since the bundled table.

    Files the table knows and the scan does not are *not* reported as removed: a
    folder that was not scanned (a Steam install with no ``ovr``, say) would
    otherwise look like the game had lost half its files.
    """
    added = {k: v for k, v in scanned.items() if k not in known}
    changed = {k: v for k, v in scanned.items() if k in known and known[k] != v}
    return {"added": added, "changed": changed}


def original_source_files(pd, mapper, *, is_ee: bool) -> list[FileKeyInfo]:
    """Installed files that are pristine game originals (VB ``OriginalSourceFiles``)."""
    table = original_crc_table(is_ee=is_ee, overrides=dict(pd.original_ee_files))
    mod_names = set(pd.mod_keys)
    result: list[FileKeyInfo] = []
    for fk, ifd in pd.installed_list.items():
        key = _normalise_key(fk.file_key)
        crc = table.get(key)
        if crc is None or not mapper.mapped_extension(fk.extension):
            continue
        if (int(ifd.file_crc) & _MASK) != crc:
            continue
        if ifd.installer == C.INSTALLER_ORIGINAL or ifd.installer not in mod_names:
            result.append(fk)
    return result


def validate_originals(pd, mapper, *, is_ee: bool) -> int:
    """Relabel installed files as game originals when their CRC matches (VB ``ValidateOriginals``).

    An installed file whose CRC matches its known-original entry and that is currently
    tagged *unknown* / *character* is retagged ``INSTALLER_ORIGINAL``. Returns the number
    of installer labels changed. (Bounded: the reverse relabelling of a stale original to
    ``FindInstaller``/``Unknown`` is left to the normal installer-resolution pass.)
    """
    table = original_crc_table(is_ee=is_ee)
    changes = 0
    for fk, ifd in pd.installed_list.items():
        crc = table.get(_normalise_key(fk.file_key))
        if crc is None or not mapper.mapped_extension(fk.extension):
            continue
        if (int(ifd.file_crc) & _MASK) == crc and ifd.installer in (
            C.INSTALLER_UNKNOWN,
            C.INSTALLER_CHARACTER,
        ):
            ifd.installer = C.INSTALLER_ORIGINAL
            changes += 1
    return changes


def restorer_buckets(originals: list[FileKeyInfo]) -> dict[tuple[str, str], list[FileKeyInfo]]:
    """Group original files into ``(group, restorer_name) -> files`` (VB ``AutoOriginalRestorer``).

    The three fixed restorers — Core / INI / Character — under the Restorers group, plus a
    per-module restorer under "Mods Installed by NWN" for each base-game module
    (``.mod`` / ``.nwm``). Empty buckets are omitted by the caller.
    """
    buckets: dict[tuple[str, str], list[FileKeyInfo]] = {}
    for fk in originals:
        ext = fk.extension.lower()
        if ext in (C.EXT_MOD, C.EXT_NWM):
            # A base-game module -> its own restorer named after the module file.
            name = fk.filename.rsplit(".", 1)[0]
            key = (C.ORIGINAL_MODS_GROUP, name)
        elif ext == ".ini":
            key = (C.RESTORER_GROUP, C.INI_FILES_RESTORER)
        elif ext == ".bic":
            key = (C.RESTORER_GROUP, C.CHARACTER_FILES_RESTORER)
        else:
            key = (C.RESTORER_GROUP, C.CORE_FILES_RESTORER)
        buckets.setdefault(key, []).append(fk)
    return buckets
