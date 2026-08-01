"""FileKeyInfo — the dictionary key / identity for every tracked file.

Faithful port of ``FileKeyInfo.vb``. A file key has four parts:

* ``group``    — the mod's group (or the ``GROUP_INSTALLED`` sentinel for game files)
* ``mod_name`` — the owning mod (or ``INSTALLED_FILES_LABEL`` for game files)
* ``folder``   — the file's parent folder name
* ``filename`` — the file name

From these it derives:

* ``file_key``  = ``folder\\filename``
* ``qualifier`` = ``group\\mod_name``
* ``full_key``  = ``group\\mod_name\\folder\\filename``  (the identity)

Identity semantics (correctness-critical):

* **Equality and hashing are case-insensitive** on ``full_key``. The VB
  ``Object.Equals`` compared ordinally while ``GetHashCode`` was
  case-insensitive — a latent inconsistency that never bit on case-insensitive
  Windows filesystems. The dictionaries that actually matter used the
  case-insensitive ``EqualityComparer`` (`FileKeyInfo.vb:363`), and on
  case-sensitive APFS we *must* compare case-insensitively in code. So we make
  both consistent and case-insensitive.
* **Ordering** (`comparer`) sorts by ``qualifier`` then ``file_key`` using
  Windows natural sort (:func:`win_compare`). Install-conflict resolution depends
  on this: the greatest key wins (install "last in sorted list wins";
  uninstall sorts reversed and takes index 0).

The separator is always a backslash on disk regardless of host OS
(:data:`constants.FILEKEY_SEPARATOR`); we normalise at the filesystem boundary
elsewhere.
"""

from __future__ import annotations

from nwnfile.win_sort import win_compare
from vaultkeeper.core import constants as C

_SEP = C.FILEKEY_SEPARATOR  # "\\"


def _split_file_key(filekey: str) -> tuple[str, str]:
    """Split a ``folder\\filename`` (or ``folder/filename``) into (folder, filename)."""
    normalised = filekey.replace("/", _SEP)
    if _SEP in normalised:
        folder, _, filename = normalised.rpartition(_SEP)
        return folder, filename
    return "", normalised


class FileKeyInfo:
    """Immutable-by-convention identity for a mod-installer file or an installed file."""

    __slots__ = ("group", "mod_name", "folder", "filename", "_full_key", "_hash")

    def __init__(
        self,
        group: str,
        mod_name: str,
        folder: str,
        filename: str,
        *,
        root_folder_name: str | None = None,
    ) -> None:
        # A file that sits directly in the game root records its folder as the
        # normalised "nwn" root marker (VB: folder == Mapper.NwnRootFolder ->
        # Mapper.C.ModRoot). The caller supplies the actual root folder name once
        # the path/mapper layer knows it.
        if root_folder_name is not None and folder == root_folder_name:
            folder = C.MOD_ROOT_FOLDER

        self.group = group
        self.mod_name = mod_name
        self.folder = folder
        self.filename = filename
        self._full_key = f"{group}{_SEP}{mod_name}{_SEP}{folder}{_SEP}{filename}"
        self._hash = hash(self._full_key.lower())

    # -- Alternate constructors ------------------------------------------- #
    @classmethod
    def installed(
        cls, folder: str, filename: str, *, root_folder_name: str | None = None
    ) -> FileKeyInfo:
        """Key for an installed (game-folder) file."""
        return cls(
            C.GROUP_INSTALLED,
            C.INSTALLED_FILES_LABEL,
            folder,
            filename,
            root_folder_name=root_folder_name,
        )

    @classmethod
    def installed_from_key(
        cls, filekey: str, *, root_folder_name: str | None = None
    ) -> FileKeyInfo:
        """Installed-file key from a ``folder\\filename`` string."""
        folder, filename = _split_file_key(filekey)
        return cls.installed(folder, filename, root_folder_name=root_folder_name)

    @classmethod
    def mod_file(
        cls,
        group: str,
        mod_name: str,
        filekey: str,
        *,
        root_folder_name: str | None = None,
    ) -> FileKeyInfo:
        """Mod-installer file key from a group, mod and ``folder\\filename`` string."""
        folder, filename = _split_file_key(filekey)
        return cls(group, mod_name, folder, filename, root_folder_name=root_folder_name)

    @classmethod
    def from_full_key(cls, full_key: str) -> FileKeyInfo:
        """Reconstruct from a persisted ``full_key`` (group\\mod\\folder\\filename)."""
        parts = full_key.split(_SEP)
        if len(parts) != 4:
            raise ValueError(f"malformed full key (expected 4 parts): {full_key!r}")
        group, mod_name, folder, filename = parts
        return cls(group, mod_name, folder, filename)

    # -- Derived keys ------------------------------------------------------ #
    @property
    def file_key(self) -> str:
        return f"{self.folder}{_SEP}{self.filename}"

    @property
    def qualifier(self) -> str:
        return f"{self.group}{_SEP}{self.mod_name}"

    @property
    def full_key(self) -> str:
        return self._full_key

    @property
    def installed_key(self) -> FileKeyInfo:
        """The corresponding InstalledList key (strips group/mod identity)."""
        return FileKeyInfo.installed(self.folder, self.filename)

    # -- Predicates -------------------------------------------------------- #
    @property
    def extension(self) -> str:
        """File extension including the dot (e.g. ``.mod``), or ``""``."""
        idx = self.filename.rfind(".")
        return self.filename[idx:] if idx != -1 else ""

    @property
    def is_mod_file(self) -> bool:
        """True for a mod-installer file (in FileList); False for a game file."""
        return self.group != C.GROUP_INSTALLED

    @property
    def is_not_mod_file(self) -> bool:
        return self.group == C.GROUP_INSTALLED

    @property
    def is_mod_extension(self) -> bool:
        """True if the file is a module (.mod or .nwm)."""
        return self.extension.lower() in (C.EXT_MOD, C.EXT_NWM)

    @property
    def is_installer_key(self) -> bool:
        return self.folder == C.MOD_NIT_DIR and self.extension.lower() == C.EXT_INSTALLER

    @property
    def is_restorer_key(self) -> bool:
        return self.folder == C.MOD_NIT_DIR and self.extension.lower() == C.EXT_RESTORER

    @property
    def is_identifier_key(self) -> bool:
        return self.folder == C.MOD_NIT_DIR and self.extension.lower() in (
            C.EXT_INSTALLER,
            C.EXT_RESTORER,
        )

    # -- Identity ---------------------------------------------------------- #
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileKeyInfo):
            return NotImplemented
        return self._full_key.lower() == other._full_key.lower()

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"FileKeyInfo({self._full_key!r})"

    def __str__(self) -> str:
        return self._full_key

    # -- Ordering ---------------------------------------------------------- #
    def compare_to(self, other: FileKeyInfo) -> int:
        """IComparable: order by full_key (Windows natural sort)."""
        return win_compare(self._full_key, other._full_key)

    @staticmethod
    def comparer(x: FileKeyInfo, y: FileKeyInfo) -> int:
        """Sort comparer: by qualifier then file_key (drives winner selection)."""
        result = win_compare(x.qualifier, y.qualifier)
        if result != 0:
            return result
        return win_compare(x.file_key, y.file_key)
