"""HakPatchManager — regenerates the game's ``nwnpatch.ini`` from installed haks.

Ported from ``HakPatchManager.vb`` (CreateNwnPatchIniFile). Neverwinter Nights
loads hak "patches" listed in ``nwnpatch.ini`` under a ``[Patch]`` section; NIT
rebuilds that file after every install/uninstall so the installed patch-haks are
loaded in the right order. This is wired into the install engine as the
``hak_patch`` hook.

Installed patch-haks are the ``.hak`` files present in the game's ``patch`` folder
(``.hak`` files map there via the folder-move rule). Their order comes from an
optional maintained sequence; installed haks not in the sequence are appended.
The original ``nwnpatch.ini`` is preserved as a ``.bak`` on first write.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.crc import crc32_file
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.profile_data import ProfileData

SECTION_NAME = "[Patch]"
PATCH_KEY = "PatchFile"
PATCH_FOLDER = "patch"
HAK_EXT = ".hak"

#: Persistent patch-hak ordering file in a profile's data folder (VB
#: ``HakPatchManager.PatchFileSequence``).
PATCH_SEQUENCE_FILE = "PatchFileSequence.txt"


def read_patch_sequence(profile_data_dir: Path) -> list[str]:
    """Read the persisted patch-hak ordering (VB ``PatchSequence`` load)."""
    path = profile_data_dir / PATCH_SEQUENCE_FILE
    if not path.is_file():
        return []
    try:
        return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return []


def save_patch_sequence(profile_data_dir: Path, sequence: list[str]) -> None:
    """Persist the patch-hak ordering (VB ``SaveSequenceFile``)."""
    profile_data_dir.mkdir(parents=True, exist_ok=True)
    (profile_data_dir / PATCH_SEQUENCE_FILE).write_text(
        "\n".join(sequence) + ("\n" if sequence else ""), encoding="utf-8"
    )


def update_patch_sequence(profile_data_dir: Path, hak_stems: list[str]) -> list[str]:
    """Append new patch-hak stems to the sequence, preserving order (VB ``UpdateSequenceFile``).

    Each stem (a ``.hak`` name without its extension) not already present
    (case-insensitive) is appended, then the file is saved. Returns the new sequence.
    """
    sequence = read_patch_sequence(profile_data_dir)
    lower = {s.lower() for s in sequence}
    for stem in hak_stems:
        if stem.lower() not in lower:
            sequence.append(stem)
            lower.add(stem.lower())
    save_patch_sequence(profile_data_dir, sequence)
    return sequence


def patch_ini_haks(ini_path: Path) -> list[str]:
    """Hak names (no extension) listed in a patch INI, in file order (VB ``GetPatchHaks``)."""
    try:
        text = ini_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    haks: list[str] = []
    for line in text.splitlines():
        _key, sep, value = line.partition("=")
        value = value.strip()
        if sep and value:
            haks.append(value[: -len(HAK_EXT)] if value.lower().endswith(HAK_EXT) else value)
    return haks


class HakPatchManager:
    """Rebuilds ``nwnpatch.ini`` / ``userpatch.ini`` from the installed patch-haks.

    With ``sequence_dir`` the manager owns the saved load order
    (``PatchFileSequence.txt``): it is read before every rebuild, seeded from the
    current patch INI when it does not exist yet, and extended with newly
    installed haks (VB ``HakPatchManager.New`` / ``UpdateSequenceFile``). With
    ``patch_dir`` the installed haks are the ``.hak`` files in the game's patch
    folder on disk (VB ``GetInstalledPatchHaks``); a hak whose record outlived
    its file must not be listed, as a missing patch hak stops modules loading.
    """

    def __init__(
        self,
        pd: ProfileData,
        patch_ini_path: Path,
        *,
        sequence: list[str] | None = None,
        sequence_dir: Path | None = None,
        patch_dir: Path | None = None,
    ) -> None:
        self.pd = pd
        self.patch_ini_path = patch_ini_path
        self.sequence_dir = sequence_dir
        self.patch_dir = patch_dir
        #: Ordered hak names (without extension); maintained across ops.
        self.sequence = list(sequence) if sequence else []

    def load_sequence(self) -> list[str]:
        """The saved order, seeded from the current patch INI the first time."""
        if self.sequence_dir is None:
            return self.sequence
        path = self.sequence_dir / PATCH_SEQUENCE_FILE
        if path.is_file():
            raw = read_patch_sequence(self.sequence_dir)
        else:
            raw = patch_ini_haks(self.patch_ini_path)
        seen: set[str] = set()
        sequence: list[str] = []
        for name in raw:
            stem = name[: -len(HAK_EXT)] if name.lower().endswith(HAK_EXT) else name
            if stem.lower() not in seen:
                seen.add(stem.lower())
                sequence.append(stem)
        self.sequence = sequence
        return sequence

    def installed_patch_haks(self) -> list[str]:
        """Names (without ``.hak``) of haks installed in the game's patch folder."""
        if self.patch_dir is not None:
            try:
                return sorted(
                    p.stem
                    for p in self.patch_dir.iterdir()
                    if p.is_file() and p.suffix.lower() == HAK_EXT
                )
            except OSError:
                return []
        haks: list[str] = []
        for ifk in self.pd.installed_list:
            if ifk.folder.lower() == PATCH_FOLDER and ifk.extension.lower() == HAK_EXT:
                haks.append(Path(ifk.filename).stem)
        return haks

    def new_patch_haks(self) -> list[str]:
        """Installed patch haks the saved order does not list yet."""
        known = {h.lower() for h in self.load_sequence()}
        return [h for h in self.installed_patch_haks() if h.lower() not in known]

    def ordered_haks(self) -> list[str]:
        """Public alias of :meth:`_ordered_haks` (the effective patch-hak order)."""
        return self._ordered_haks()

    def _ordered_haks(self) -> list[str]:
        self.load_sequence()
        installed = self.installed_patch_haks()
        lowered = {h.lower() for h in installed}
        ordered = [h for h in self.sequence if h.lower() in lowered]
        present = {h.lower() for h in self.sequence}
        added = False
        for hak in installed:
            if hak.lower() not in present:
                ordered.append(hak)
                self.sequence.append(hak)
                present.add(hak.lower())
                added = True
        if self.sequence_dir is not None and (
            added or not (self.sequence_dir / PATCH_SEQUENCE_FILE).is_file()
        ):
            save_patch_sequence(self.sequence_dir, self.sequence)
        return ordered

    def refresh_on_load(self) -> bool:
        """Rebuild the patch INI when new patch haks appeared (VB ``HakPatchManager.New``)."""
        if self.patch_dir is None or not self.patch_dir.is_dir() or not self.new_patch_haks():
            return False
        return self.create_nwn_patch_ini_file()

    def create_nwn_patch_ini_file(self) -> bool:
        """Regenerate ``nwnpatch.ini``; update the installed patch-ini record."""
        ordered = self._ordered_haks()
        lines = [SECTION_NAME]
        if ordered:
            for i, hak in enumerate(ordered):
                lines.append(f"{PATCH_KEY}{i:03d}={hak}")
        else:
            lines.append(f"{PATCH_KEY}000=")
        text = "\n".join(lines) + "\n"

        # Preserve the pre-existing patch ini once.
        self.patch_ini_path.parent.mkdir(parents=True, exist_ok=True)
        backup = self.patch_ini_path.with_name(self.patch_ini_path.name + ".bak")
        if self.patch_ini_path.exists() and not backup.exists():
            self.patch_ini_path.replace(backup)

        self.patch_ini_path.write_text(text, encoding="utf-8")

        # Keep the installed patch-ini record's checksum/size/mtime current.
        ifk = FileKeyInfo.installed(C.MOD_ROOT_FOLDER, self.patch_ini_path.name)
        ifd = self.pd.installed_item(ifk)
        if ifd is not None:
            stat = self.patch_ini_path.stat()
            ifd.file_crc = crc32_file(self.patch_ini_path)
            ifd.byte_size = stat.st_size
            from datetime import datetime

            ifd.modified = datetime.fromtimestamp(stat.st_mtime)
        return True
