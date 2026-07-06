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


class HakPatchManager:
    """Rebuilds ``nwnpatch.ini`` from the installed patch-haks."""

    def __init__(
        self,
        pd: ProfileData,
        patch_ini_path: Path,
        *,
        sequence: list[str] | None = None,
    ) -> None:
        self.pd = pd
        self.patch_ini_path = patch_ini_path
        #: Ordered hak names (without extension); maintained across ops.
        self.sequence = list(sequence) if sequence else []

    def installed_patch_haks(self) -> list[str]:
        """Names (without ``.hak``) of haks installed in the game's patch folder."""
        haks: list[str] = []
        for ifk in self.pd.installed_list:
            if ifk.folder.lower() == PATCH_FOLDER and ifk.extension.lower() == HAK_EXT:
                haks.append(Path(ifk.filename).stem)
        return haks

    def _ordered_haks(self) -> list[str]:
        installed = self.installed_patch_haks()
        lowered = {h.lower() for h in installed}
        ordered = [h for h in self.sequence if h.lower() in lowered]
        present = {h.lower() for h in ordered}
        for hak in sorted(installed):
            if hak.lower() not in present:
                ordered.append(hak)
                present.add(hak.lower())
        return ordered

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
