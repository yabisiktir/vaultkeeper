"""FileData / InstalledFileData — per-file records in the profile database.

Ported from ``FileData.vb`` and ``InstalledFileData.vb``.

* ``FileData`` describes one file inside a mod's ``.Mod Installer`` payload
  (values in ``ProfileData.FileList``).
* ``InstalledFileData`` describes one file present in the game folder (values in
  ``ProfileData.InstalledList``) and additionally tracks which mod "owns" it
  (``installer``) plus the mod files that map onto it (``mod_files`` /
  ``mod_file_conflicts``).

Scope note (faithful layering): the records here carry the fields and the *pure*
derived properties. The state-transition behaviour on ``InstalledFileData``
(the ``Installer`` resolver, ``reset_mod_files``, ``installer_conflicts``,
``remove_mod_file``, ``remove_file``, ``rename``) reaches into the whole
``ProfileData`` graph (FileList/ModList/Changes/OriginalFiles) and is implemented
alongside ``ProfileData`` in this phase, not baked into the record. VB references
are kept in comments so that work is mechanical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import State


@dataclass
class FileData:
    """A file inside a mod installer (FileList value)."""

    key: FileKeyInfo
    file_state: State = State.NOT_INSTALLED
    extension: str = ""
    modified: datetime | None = None
    byte_size: int = 0
    file_crc: int = 0  # CRC-32; 0 means "not calculated" (unless byte_size == 0)

    # -- Derived ----------------------------------------------------------- #
    @property
    def installed(self) -> bool:
        """True if the file has been installed (FileData.Installed)."""
        return self.file_state > State.NOT_INSTALLED

    @property
    def crc_calculated(self) -> bool:
        """True once a CRC is known. Empty files (size 0) count as calculated."""
        return self.file_crc != 0 or self.byte_size == 0

    def clone(self) -> FileData:
        """Copy of the data fields (VB Clone leaves the key for the caller to set)."""
        return FileData(
            key=self.key,
            file_state=self.file_state,
            extension=self.extension,
            modified=self.modified,
            byte_size=self.byte_size,
            file_crc=self.file_crc,
        )


@dataclass
class InstalledFileData(FileData):
    """A file present in the game folder (InstalledList value)."""

    #: The mod name that currently owns this installed file (Installer property).
    installer: str = C.INSTALLER_UNKNOWN
    #: All mod files whose file_key maps onto this installed file, sorted by
    #: FileKeyInfo.comparer (ModFileConflicts).
    mod_file_conflicts: list[FileKeyInfo] = field(default_factory=list)
    #: The subset of mod_file_conflicts whose CRC matches this file (ModFiles).
    mod_files: list[FileKeyInfo] = field(default_factory=list)

    # -- Pure derived properties ------------------------------------------ #
    @property
    def is_default_installer(self) -> bool:
        """True if the installer is one of the non-user-mod default names."""
        return self.installer in C.DEFAULT_INSTALLERS

    @property
    def is_unknown_installer(self) -> bool:
        """True if the source is unknown (ModUnknown or ModCharacter)."""
        return self.installer in (C.INSTALLER_UNKNOWN, C.INSTALLER_CHARACTER)

    def clone(self) -> InstalledFileData:
        """Deep-ish copy (mirrors VB Clone: copies fields + mod_files, not the key)."""
        ifd = InstalledFileData(
            key=self.key,
            file_state=self.file_state,
            extension=self.extension,
            modified=self.modified,
            byte_size=self.byte_size,
            file_crc=self.file_crc,
            installer=self.installer,
        )
        ifd.mod_files.extend(self.mod_files)
        return ifd
