"""Mapper — decides which game folder every mod file belongs in.

Faithful port of the engine in ``Mapper.vb`` (the piece the previous port faked).
Given a source file, :meth:`Mapper.get_mapped_folder` returns the NWN subfolder
name the file should be installed into (or ``""`` for unsupported/excluded
files), following the exact VB dispatch ladder:

1. unsupported extension (not in the extension map) -> excluded
2. directory mapping (``grandparent\\parent`` then ``parent`` then ``grandparent``)
3. exception files (by exact filename)
4. optional ERF exclusion
5. extension map, honouring a folder-move if the file already sits in it
6. filename-prefix exceptions (fonts / voice sets) -> secondary folder

The maps are initialised from the default v21 tables (verified against source).
The user-editable persistence, ListView editors, import/export and the historical
version migrations belong to the Settings dialog and are out of scope here; the
tables are exposed as plain dicts so a settings layer can later override them.

Runtime path resolution (folder-name -> absolute path, ``NwnFolders``) needs the
Paths layer and is deferred; this module works purely at the folder-name level.

All name/extension lookups are case-insensitive (VB ``Option Compare Text`` /
``StringComparer.CurrentCultureIgnoreCase``): table keys are stored lower-cased
and lookups lower-case their argument.
"""

from __future__ import annotations

from pathlib import PurePath

from vaultkeeper.core import constants as C

# --- Folder-name constants (Mapper.C) ------------------------------------- #
FOLDER_ROOT = C.MOD_ROOT_FOLDER          # "nwn"
FOLDER_OVERRIDE = "override"
FOLDER_OVR = "ovr"                        # EE override
FOLDER_DATABASE = "database"
FOLDER_DMVAULT = "dmvault"
FOLDER_LOCALVAULT = "localvault"
FOLDER_PORTRAITS = "portraits"
FOLDER_TEXTUREPACKS = "texturepacks"
FOLDER_EE_TEXTUREPACKS = "txpk"
FOLDER_AMBIENT = "ambient"
FOLDER_MUSIC = "music"
FOLDER_MOVIES = "movies"
FOLDER_HAK = "hak"
FOLDER_ERF = "erf"
FOLDER_TLK = "tlk"
FOLDER_DATA = "data"
FOLDER_PREMIUM = "premium"
FOLDER_PATCH = "patch"
FOLDER_MODULES = C.MOD_FOLDER             # "modules"
FOLDER_NWM = C.MOD_NWM_FOLDER             # "nwm"
FOLDER_MOD_EE = "mod"                     # EE .mod folder
FOLDER_EE_MUS = "mus"
FOLDER_VANILLA_ICONS = "restore vanilla icons"

# --- Extension constants (Mapper.C) --------------------------------------- #
EXT_ERF = ".erf"
EXT_BACKUPMOD = ".backupmod"
EXT_EE_DATABASE = ".sqlite3"

#: Extensions that map to the database folder (Mapper.DatabaseExtensions).
DATABASE_EXTENSIONS = frozenset({".cdx", ".dbf", ".fpt", EXT_EE_DATABASE})

#: Extensions that can never be removed from the map (Mapper.MandatoryExtensions).
MANDATORY_EXTENSIONS = frozenset(
    {
        EXT_ERF, ".hak", C.EXT_MOD, ".bik", ".wbm", ".bmu", ".ttf", ".mtr",
        C.EXT_NWM, ".ncs", ".2da", ".tlk", ".bif", ".dlg", ".ini", ".tml",
        ".cdx", ".dbf", ".fpt", EXT_EE_DATABASE, C.EXT_INSTALLER, C.EXT_RESTORER,
    }
)

#: Directory names that are never valid install targets (Mapper.NwnIllegalFolders).
NWN_ILLEGAL_FOLDERS = frozenset(
    {"docs", "ereg", "logs", "override_bak", "saves"}
)


def _ci(pairs: dict[str, str]) -> dict[str, str]:
    """Return a dict with lower-cased keys (values unchanged) for CI lookup."""
    return {k.lower(): v for k, v in pairs.items()}


def default_ext_mapping() -> dict[str, str]:
    """Default extension -> primary folder map (DefaultExtMapping, v21)."""
    return _ci(
        {
            ".wav": FOLDER_AMBIENT,
            EXT_ERF: FOLDER_ERF,
            ".hak": FOLDER_HAK,
            ".dat": FOLDER_PREMIUM,
            ".bic": FOLDER_LOCALVAULT,
            C.EXT_MOD: FOLDER_MODULES,
            EXT_BACKUPMOD: FOLDER_MODULES,
            ".bik": FOLDER_MOVIES,
            ".wbm": FOLDER_MOVIES,
            ".bmu": FOLDER_MUSIC,
            C.EXT_NWM: FOLDER_NWM,
            ".bif": FOLDER_DATA,
            ".bmp": FOLDER_OVERRIDE,
            ".mdl": FOLDER_OVERRIDE,
            ".dds": FOLDER_OVERRIDE,
            ".tga": FOLDER_PORTRAITS,
            ".2da": FOLDER_OVERRIDE,
            ".tlk": FOLDER_TLK,
            ".key": FOLDER_ROOT,
            ".ini": FOLDER_ROOT,
            ".tml": FOLDER_ROOT,
            ".dll": FOLDER_ROOT,
            ".txi": FOLDER_OVERRIDE,
            ".ncs": FOLDER_OVERRIDE,
            ".nss": FOLDER_OVERRIDE,
            ".utc": FOLDER_OVERRIDE,
            ".dlg": FOLDER_OVERRIDE,
            ".itp": FOLDER_OVERRIDE,
            ".pwk": FOLDER_OVERRIDE,
            ".ssf": FOLDER_OVERRIDE,
            ".shd": FOLDER_OVERRIDE,
            ".ttf": FOLDER_OVERRIDE,
            ".uti": FOLDER_OVERRIDE,
            ".plt": FOLDER_OVERRIDE,
            ".png": FOLDER_OVERRIDE,
            ".gif": FOLDER_OVERRIDE,
            ".mtr": FOLDER_OVERRIDE,
            ".gui": FOLDER_OVERRIDE,
            ".cdx": FOLDER_DATABASE,
            ".dbf": FOLDER_DATABASE,
            ".fpt": FOLDER_DATABASE,
            EXT_EE_DATABASE: FOLDER_DATABASE,
            C.EXT_INSTALLER: C.MOD_NIT_DIR,
            C.EXT_RESTORER: C.MOD_NIT_DIR,
        }
    )


def default_dir_mapping() -> dict[str, str]:
    """Default directory-name -> folder map (DefaultDirMapping, v21)."""
    return _ci(
        {
            FOLDER_OVERRIDE: FOLDER_OVERRIDE,
            FOLDER_DMVAULT: FOLDER_DMVAULT,
            FOLDER_MUSIC: FOLDER_MUSIC,
            FOLDER_TEXTUREPACKS: FOLDER_TEXTUREPACKS,
            FOLDER_ERF: FOLDER_ERF,
            "nwncq_override_basic_by_chico400": FOLDER_OVERRIDE,
            "nwncq_override_extended_by_chico400": FOLDER_OVERRIDE,
            "nwncq_plus_version_addon": FOLDER_OVERRIDE,
            "sh_miscmed_override": FOLDER_OVERRIDE,
            "bd hd textures modular": FOLDER_OVR,
        }
    )


def default_exception_files() -> dict[str, str]:
    """Default filename -> folder exceptions (DefaultExceptionFiles, v21)."""
    return _ci({"dungeonmaster.bic": FOLDER_DMVAULT, "dialog.tlk": FOLDER_ROOT})


def default_exception_prefixes() -> dict[str, list[str]]:
    """Default extension -> filename prefixes (DefaultExceptionPrefixes, v21)."""
    prefixes = {
        ".tga": [
            "__ref.", "__ref01.", "chrome", "fnt_", "fxpa_rain", "fog_genm",
            "gui_", "id_", "ife_", "iit_picks", "ir_", "is_", "isk_", "iss_",
            "ls_load", "ls_save", "pal_", "potm_", "zdc03_", "anvil", "crate",
        ],
        ".wav": ["vs_f", "vs_n", "c_"],
    }
    for lst in prefixes.values():
        lst.sort()
    return {k.lower(): v for k, v in prefixes.items()}


def default_folder_moves() -> dict[str, str]:
    """Default extension -> secondary (move) folder (DefaultFolderMoves, v21)."""
    return _ci(
        {
            ".bic": FOLDER_DMVAULT,
            EXT_ERF: FOLDER_TEXTUREPACKS,
            ".hak": FOLDER_PATCH,
            EXT_BACKUPMOD: FOLDER_NWM,
            ".tga": FOLDER_OVERRIDE,
            ".wav": FOLDER_OVERRIDE,
        }
    )


def default_exclude_folders() -> dict[str, bool]:
    """Default excluded folder names -> player-editable flag (DefaultExcludeFolders)."""
    return {
        k.lower(): v
        for k, v in {
            "$pluginsdir": False,
            "__macosx": False,
            C.MOD_INSTALLER_DIR: False,
            C.HISTORY_DIR: False,
            C.PUBLISHED_DIR: False,
            C.REMOVED_ITEMS_DIR: False,
            FOLDER_VANILLA_ICONS: True,
            "optional override files": True,
        }.items()
    }


def default_exclude_mods() -> dict[str, bool]:
    """Default demo-mod exclusion substrings (DefaultExcludeMods)."""
    return {"demo": True, "test": True}


def default_exclude_files() -> dict[str, bool]:
    """Default excluded filenames (DefaultExcludeFiles)."""
    return {
        k.lower(): v
        for k, v in {
            "dc_genericdoors.ini": True,
            "gxpa_shld.tga": True,
            "nwnenglish1.69origupdate.exe": False,
            "nwnenglish1.69souupdate.exe": False,
            "nwnenglish1.69hotuupdate.exe": False,
        }.items()
    }


class Mapper:
    """The file-to-folder mapping engine, initialised from the default v21 tables."""

    def __init__(self, *, is_ee: bool = True, exclude_erf: bool = True) -> None:
        self.is_ee = is_ee
        #: My.Settings.MapExcludeErf — whether stray ERFs are excluded on create.
        self.exclude_erf = exclude_erf

        self.ext_mapping = default_ext_mapping()
        self.folder_moves = default_folder_moves()
        self.dir_mapping = default_dir_mapping()
        self.exception_files = default_exception_files()
        self.exception_prefixes = default_exception_prefixes()
        self.exclude_folders = default_exclude_folders()
        self.exclude_mods = default_exclude_mods()
        self.exclude_files = default_exclude_files()

        # NwnExtensions = a copy of ExtMapping plus .txt/.dll roots (Mapper.New).
        self.nwn_extensions = dict(self.ext_mapping)
        self.nwn_extensions.setdefault(".txt", FOLDER_LOCALVAULT)
        self.nwn_extensions.setdefault(".dll", FOLDER_ROOT)

        # Files listed without an extension act as filename prefixes.
        self.exclude_file_prefixes = [
            k for k in self.exclude_files if PurePath(k).suffix == ""
        ]
        #: Names that are never excluded (overrides); populated from app defs in VB.
        self.map_exclude_exceptions: list[str] = []

        if is_ee:
            self._apply_ee()

    def _apply_ee(self) -> None:
        """EE reclassifies .gui/.shd as ovr for NwnExtensions (DefineEeFolders)."""
        for ext in (".gui", ".shd"):
            self.nwn_extensions[ext] = FOLDER_OVR

    # -- Core dispatch ----------------------------------------------------- #
    def get_mapped_folder(self, source: str | PurePath, *, erf_check: bool = False) -> str:
        """Return the target folder name for ``source`` (``""`` if unsupported/excluded)."""
        p = PurePath(source)
        name = p.name
        ext = PurePath(name).suffix
        ext_key = ext.lower()

        # 1. Unsupported extension.
        if ext_key not in self.ext_mapping:
            return ""

        parent_name = p.parent.name
        grandparent_name = p.parent.parent.name

        # 2. Directory mapping takes precedence over extension mapping.
        combo = f"{grandparent_name}\\{parent_name}".lower()
        if combo in self.dir_mapping:
            return self.dir_mapping[combo]
        if parent_name and parent_name.lower() in self.dir_mapping:
            return self.dir_mapping[parent_name.lower()]
        if grandparent_name and grandparent_name.lower() in self.dir_mapping:
            return self.dir_mapping[grandparent_name.lower()]

        # 3. Exception files (exact filename).
        if name.lower() in self.exception_files:
            return self.exception_files[name.lower()]

        # 4. Optional ERF exclusion (only requested during installer creation).
        if erf_check and self.is_excluded_erf(p):
            return ""

        # 5. Extension map; keep the file in its secondary folder if already there.
        folder = self.ext_mapping[ext_key]
        source_folder = parent_name
        if (
            folder != source_folder
            and ext_key in self.folder_moves
            and source_folder.lower() == self.folder_moves[ext_key].lower()
        ):
            folder = self.folder_moves[ext_key]

        # 6. Filename-prefix exceptions (fonts / voice sets) -> secondary folder.
        ext_only = ext_key[1:] if ext_key.startswith(".") else ext_key
        if ext_key in self.exception_prefixes:
            lower_name = name.lower()
            for prefix in self.exception_prefixes[ext_key]:
                if lower_name.startswith(prefix.lower()) or lower_name.endswith(
                    (prefix + ext_only).lower()
                ):
                    return self.folder_moves[ext_key]

        return folder

    # -- Folder / move helpers -------------------------------------------- #
    def get_primary_folder(self, extension: str) -> str:
        return self.ext_mapping[extension.lower()]

    def get_secondary_folder(self, extension: str) -> str:
        return self.folder_moves.get(extension.lower(), "")

    def get_move_target(self, current_folder: str, extension: str) -> str:
        """Toggle target between the primary folder and the secondary (move) folder."""
        default_folder = self.ext_mapping[extension.lower()]
        if current_folder != default_folder:
            return default_folder
        return self.folder_moves[extension.lower()]

    # -- Extension / folder predicates ------------------------------------ #
    def mapped_extension(self, extension: str) -> bool:
        return extension.lower() in self.ext_mapping

    def extension_folder(self, extension: str) -> str:
        return self.ext_mapping.get(extension.lower(), "")

    def root_mapped_extension(self, extension: str) -> bool:
        return self.nwn_extensions.get(extension.lower()) == FOLDER_ROOT

    def allow_moves(self, extension: str) -> bool:
        return extension.lower() in self.folder_moves

    def is_exception_file(self, filename: str) -> bool:
        return filename.lower() in self.exception_files

    def is_optional_extension(self, extension: str) -> bool:
        return extension.lower() not in MANDATORY_EXTENSIONS

    def is_database_extension(self, extension: str) -> bool:
        return extension.lower() in DATABASE_EXTENSIONS

    def is_nwn_extension(self, extension: str) -> bool:
        ext = extension.lower()
        return ext in self.ext_mapping or ext in self.nwn_extensions

    def can_rename_extension(self, extension: str) -> bool:
        return extension.lower() not in self.nwn_extensions

    def is_identifier_file(self, extension: str) -> bool:
        return extension.lower() in (C.EXT_INSTALLER, C.EXT_RESTORER)

    def is_texture_pack_folder(self, folder: str) -> bool:
        return folder.lower() in (
            self.get_secondary_folder(EXT_ERF).lower(),
            FOLDER_EE_TEXTUREPACKS,
        )

    # -- Exclusion predicates --------------------------------------------- #
    def is_excluded_folder(self, folder_name: str) -> bool:
        return folder_name.lower() in self.exclude_folders

    def is_excluded_file(self, filename: str) -> bool:
        low = filename.lower()
        if any(low == e.lower() for e in self.map_exclude_exceptions):
            return False
        if low in self.exclude_files:
            return True
        return any(low.startswith(prefix.lower()) for prefix in self.exclude_file_prefixes)

    def is_excluded_erf(self, source: str | PurePath) -> bool:
        p = PurePath(source)
        if p.suffix.lower() != EXT_ERF or not self.exclude_erf:
            return False
        parent_name = p.parent.name
        # Faithful to VB: not the ERF secondary folder, and (buggy) full dir path
        # not literally "txpk" — the latter is virtually always true.
        return (
            parent_name.lower() != self.get_secondary_folder(EXT_ERF).lower()
            and str(p.parent) != FOLDER_EE_TEXTUREPACKS
        )

    def is_demo_mod(self, filename: str) -> bool:
        """Demo/test module detection (Mapper.IsDemoMod), with the 'demo' special case."""
        name = PurePath(filename).name
        low = name.lower()
        if any(low == e.lower() for e in self.map_exclude_exceptions):
            return False
        if not self.exclude_mods or PurePath(name).suffix.lower() != C.EXT_MOD:
            return False
        for demo_string in self.exclude_mods:
            if demo_string.lower() in low:
                if demo_string.lower() != "demo":
                    return True
                # Extra tests for the ambiguous word "demo".
                if low == "demo.mod":
                    return True
                if low.startswith("demo "):
                    return True
                if " demo " in low:
                    return True
                if " demo." in low:
                    return True
        return False

    # -- Legal-folder set (name level) ------------------------------------ #
    def legal_folder_names(self) -> set[str]:
        """Set of valid target folder names (name-level; path resolution deferred)."""
        names: set[str] = {FOLDER_ROOT, FOLDER_TEXTUREPACKS, FOLDER_DATABASE}
        names.update(v.lower() for v in self.ext_mapping.values())
        names.update(v.lower() for v in self.folder_moves.values())
        if self.is_ee:
            names.update({FOLDER_OVR, FOLDER_EE_TEXTUREPACKS, FOLDER_EE_MUS, FOLDER_MOD_EE})
        return names

    def is_legal_folder(self, folder: str) -> bool:
        return folder.lower() in self.legal_folder_names()
