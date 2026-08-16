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


def default_run_links() -> list[dict[str, str]]:
    """The default Run-menu programs (VB ``Defs.DefaultRunMenu`` / ``My.Settings.MenuRun``).

    Empty by default: VB pre-fills two Windows-only companion tools (a console-command
    helper and *NWVault Metadata Viewer*) whose paths it auto-detects on disk. Neither
    is bundled cross-platform, so the port starts with no user programs and the user
    adds their own (label + executable path) — the faithful, non-inventing default.
    """
    return []


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
    #: Override for the game user-data folder (Documents/Neverwinter Nights); ``None``
    #: = auto-resolve from the platform.
    game_user_path: str | None = None
    #: Stop auto-resolving the Enhanced Edition user-files folder at start-up (VB
    #: ``PrivateExtendedDisabled``, the ExtendedEditionDialogue's "Disable Enhanced
    #: Edition detection at start-up"). When set, first-run config leaves
    #: ``game_user_path`` for the user to set, rather than guessing the standard
    #: folder — the escape hatch for a non-standard or not-yet-created layout.
    disable_ee_detection: bool = False
    #: Name of the active profile.
    active_profile: str | None = None
    #: Send user-initiated deletes to the OS trash rather than deleting permanently.
    recycle_on_delete: bool = True
    #: Game saves get their own answer (VB "Recycle Bin for Game Saves"): they
    #: are large and routinely discarded, so someone can reasonably want these
    #: gone for good while keeping the safety net everywhere else.
    recycle_game_saves: bool = True
    #: Lock the live game-saves folder: when on, the tool refuses every action that
    #: removes saves from it — Finished, Reduce and Deactivate (and the automatic
    #: move-aside when the Game Saves Manager opens). Off by default; a user who
    #: never wants the tool touching their saves turns it on.
    protect_game_saves: bool = False
    #: On startup, check whether the game config diverged and prompt before syncing
    #: (config-isolation principle — never sync silently).
    validate_game_config_on_startup: bool = True
    #: Convert ``.bik`` movies to ``.wbm`` when building an installer (VB
    #: ``ProfileInfo.ConvertBikFiles``; NWN:EE plays WebM, not Bink).
    convert_bik_files: bool = False
    #: Automatically install a mod right after building its installer (VB
    #: install-after-create behaviour).
    install_after_create: bool = False
    #: Remember and restore the main window's size/position across runs (VB
    #: FormsManager window-position preference).
    remember_window_position: bool = True
    #: Saved main-window geometry (Qt ``saveGeometry`` bytes, base64); internal.
    window_geometry: str = ""
    #: Saved per-dialog geometry, keyed by screen name (same encoding); internal.
    #: Cleared by Reset Window Layout, because a remembered size can itself be
    #: the problem — a window dragged onto a monitor that is no longer there.
    dialog_geometry: dict[str, str] = field(default_factory=dict)
    #: Play a sound when the application starts (VB ``BehaviourPlayStartup``).
    startup_sound: bool = False
    #: The file to play; empty means the game's own autorun fanfare, found at
    #: start-up (VB ``PathStartupSound``, which VB likewise fills in by default).
    startup_sound_path: str = ""
    #: When auto-installing after creating an installer, only (re)install mods that
    #: were already installed rather than every mod (VB ``BehaviourInstallerRestore``;
    #: coupled with ``install_after_create`` — installing implies this is on).
    installer_restore: bool = False
    #: Select the mod being played in the list when you press Play Neverwinter Nights
    #: (VB ``BehaviourSelectGameMod``).
    select_game_mod: bool = False
    #: Copy the mod name to the clipboard when starting a new Neverwinter Nights game
    #: (VB ``ConfigCopyOnPlay``).
    copy_mod_name_on_play: bool = False
    #: Create Character Restorers automatically when you close Neverwinter Nights
    #: (VB ``BehaviourAutoCharacter``).
    auto_character: bool = False
    #: Name prefix for a generated Character Restorer (VB
    #: ``ConfigCharacterRestorerPrefix``). The hyphen is the original's own
    #: convention: it makes the name unique and sorts them together.
    character_restorer_prefix: str = "-"
    #: DebugMode console command copied to the clipboard when playing an existing game
    #: (VB ``ConfigCopyDebugModeOnPlay``; empty = off, e.g. ``"DebugMode 1"`` when on).
    #: BOUNDED: the VB per-command picker is fixed to ``"DebugMode 1"`` here.
    copy_debug_mode_on_play: str = ""
    #: Thickness (1-4) of the drag handles between the main window's panels (VB
    #: ``ConfigSplitterWidth``: Default/Medium/Large/Extra large).
    splitter_width: int = 1
    #: Maximum number of mods shown in the Recent Mods menu (VB
    #: ``ConfigMaxRecentMods``; range 5-50, default 15).
    max_recent_mods: int = 15
    #: Number the Recent Mods entries instead of showing a status icon (VB
    #: ``BehaviourNumberRecentMods``).
    number_recent_mods: bool = False
    #: Default group for newly created / added mods; empty = ungrouped (VB
    #: ``ConfigDefaultGroup``).
    default_group: str = ""
    #: Prompt to confirm destructive actions (remove/uninstall/delete). When off,
    #: actions proceed without a confirmation dialog (VB ``BehaviourConfirmActions``
    #: / NitUserInterface.ConfirmActions).
    confirm_actions: bool = True
    #: When uninstalling a mod, also uninstall its dependency mods that are no
    #: longer required by any other installed mod (VB ``BehaviourUninstallDependencies``).
    uninstall_dependencies: bool = False
    #: Per-extension filename-prefix exceptions that send a file to its
    #: secondary folder (VB's Exceptions panel, ``defineextension.htm``).
    map_exception_prefixes: dict[str, list] = field(default_factory=dict)
    #: Include the Enhanced Edition ``development`` folder as a legal install
    #: target (VB ``ConfigDevelopmentFolder``; toggled from the Debug Options
    #: menu's *Enable Development Folder*). Off by default — the game warns player
    #: use of it "can break things in many subtle ways" (``newtopic55.htm``).
    enable_development_folder: bool = False
    #: Show the Debug Options menu (VB ``DebugOptionsMenu``; ``newtopic68.htm``).
    #: Off by default; it hosts *Enable Development Folder* and *Move to Development*.
    debug_options_menu: bool = False
    #: Whether the one-time Player/Builder question has been put (VB
    #: ``PrivateCheckPlayerExcludes``). Asked once; the Map Excludes page is
    #: where it is revisited.
    asked_player_excludes: bool = False
    #: Per-profile game folders, profile name → path. "Each profile operates
    #: with a specific Neverwinter Nights Installation or Enhanced Edition User
    #: Files folder […] to use development or test installations that do not
    #: interfere with your live gaming environment"
    #: (``specifyaneverwinternightsfolder.htm``).
    profile_game_paths: dict[str, str] = field(default_factory=dict)
    profile_game_user_paths: dict[str, str] = field(default_factory=dict)
    #: Per-profile edition, profile name → ``True`` for Enhanced Edition. Fixed
    #: when the profile is made (``definenewprofiles.htm``: "You cannot change
    #: the Profile Type after the Profile has been created"), because the folder
    #: layout it selects is the one every recorded file key was built against.
    profile_editions: dict[str, bool] = field(default_factory=dict)
    #: Which file a mod's Contents pane opens on (VB Selection Preferences):
    #: "history" | "play_time" | "text_file".
    selection_preference: str = "text_file"
    #: Per-mod memory of what was selected in Contents, "mod" → "folder/filename".
    #: Cleared by *Clear Selection History* (``newtopic63.htm``).
    contents_selection: dict[str, str] = field(default_factory=dict)
    #: Mods pinned in the Recent Mods list — they stay however long ago they
    #: were last used (VB's Pin/Unpin, ``newtopic47``).
    pinned_recent_mods: list[str] = field(default_factory=list)
    #: The quick toolbar's contents, as ``{"action", "image", "caption"}`` rows
    #: (VB's Toolbar Editor). Empty means the default strip.
    quick_toolbar_items: list[dict] = field(default_factory=list)
    #: Show the caption under each toolbar icon (VB ``MsShowText``).
    toolbar_show_text: bool = True
    #: Where each mod's notes were last scrolled to, mod name → caret position
    #: (VB ``ScrollPositions.RtModNotes``). Cleared by *Clear Text Position
    #: Information*; internal.
    notes_positions: dict[str, int] = field(default_factory=dict)
    #: Remember where the notes were left, per mod (VB ``BehaviourTextPosition``).
    remember_text_positions: bool = True
    #: Size the Properties panel to what it is showing (VB ``MsPropertiesHeight``,
    #: also toggled by clicking the Properties heading).
    auto_properties_height: bool = False
    #: Move mods added from files/paste into the default group instead of leaving
    #: them ungrouped (VB ``BehaviourMoveAddedMods``).
    move_added_mods: bool = False
    #: When adding downloaded files to a mod, move them (removing the source) rather
    #: than copying (VB ``BehaviourUseMove`` / adddownloadedfilestoamod.htm). VB's
    #: default is Move — "the selected files are moved to your Mod's folder".
    use_move_on_add: bool = True
    #: Let the Tool manage Steam Workshop subscription content (VB
    #: ``ConfigManageSteamWorkshop`` / newtopic19.htm). Off by default — "the
    #: Installer Tool does not manage Steam's Workshop Subscription content".
    manage_steam_workshop: bool = False
    #: Manual Steam Workshop content folder, for when it is not auto-detected
    #: (VB Locations ``Steam Workshop Content``). Blank = derive it from the game
    #: install, which is the usual case.
    workshop_content_dir: str = ""
    #: Show image files (tga/png/…) as a preview in Display Info; when off they open
    #: as text (VB ``BehaviourDisplayImageFiles`` / ``ConfigDisplayTgaImages``).
    display_image_files: bool = True
    #: Automatically move Leto log files (``LoadITPLog.leto.txt``) to the recycle bin
    #: when the app starts (VB ``ConfigDeleteLetoLogs`` → ``DeleteLetoLogs``, default
    #: on). When off, the manual **Remove Leto Log Files** command is shown instead
    #: (VB ``MsRemoveLetoLogFiles.Visible = Not ConfigDeleteLetoLogs``).
    delete_leto_logs: bool = True
    #: Prompt before saving edited Mod Notes when navigating away; when off, notes are
    #: saved silently (VB ``BehaviourConfirmSaves`` → ``RttDetails.SaveChangesPrompt``,
    #: default on).
    confirm_saves: bool = True
    #: Size the Character Explorer portrait preview: ``"Huge"`` | ``"Large"`` |
    #: ``"Medium"`` (VB ``ConfigPortraitDisplaySize`` → ``Defs.PicSizes`` H/L/M,
    #: default ``"Huge"``).
    portrait_display_size: str = "Huge"
    #: Mod Explorer name-prefix filters (VB ``FilterPrefixList``). Each entry is
    #: ``{"prefix": str, "included": bool}``; an *unchecked* prefix hides every
    #: mod whose name starts with it. A prefix is only matched text — there is no
    #: prefix field on a mod, in VB either.
    mod_prefix_filters: list[dict] = field(default_factory=list)
    #: Mod Explorer attribute filters (VB ``FilterModFiles`` / ``FilterInstallers``
    #: / ``FilterRestorers``), all on by default as in the original: the list
    #: starts restricted to mods that have an installer, can be played, and
    #: includes Restorers.
    filter_mod_files: bool = True
    filter_installers: bool = True
    filter_restorers: bool = True
    #: Character Explorer: show only skills the character has ranks in (VB
    #: ``FilterSkillsByRank`` / the *Only show Ranked Skills* tick). A PRC
    #: character has around forty skills and ranks in a handful, so the unranked
    #: ones are mostly noise.
    filter_skills_by_rank: bool = False
    #: Portrait Manager: also list the portraits held in ``override`` (and ``ovr``
    #: on EE) rather than only the ``portraits`` folder (VB
    #: ``PrivateOverridePortraits``).
    portrait_include_override: bool = False
    #: Portrait Manager: after excluding a portrait, select the next (or previous)
    #: entry, following whichever direction you last moved in (VB
    #: ``PrivateAlwaysNextPortrait``).
    portrait_always_select_next: bool = True
    #: An external TGA editor to open portrait images in. Empty = the Portrait
    #: Manager's Edit action stays hidden, as in VB, where the button appears only
    #: once a TGA File Editor is configured (VB ``TgaEditor.Path``).
    tga_editor_path: str = ""
    #: A web page to open from the Portrait Manager — for people who build
    #: portraits from a favourite image site (VB ``PathImageWebPage``). Empty =
    #: the link is hidden.
    portrait_image_web_page: str = ""
    #: Install the next start-screen image each time the game closes, so a
    #: different one greets you next launch (VB ``ConfigAutoLoadscreen``).
    auto_loadscreen: bool = False
    #: Seconds each image is held in the start-screen slide show (VB
    #: ``ConfigSlideShowInterval``).
    slideshow_interval: int = 5
    #: Restart the slide show from the first image after the last, rather than
    #: closing it (VB ``ConfigSlideShowContinuous``).
    slideshow_continuous: bool = False
    #: Character Explorer inventory shows the NWN-style item icon grid (vs the list).
    inventory_nwn_style: bool = False
    #: Look up custom item icons from installed haks (CEP/PRC) as well as the base
    #: game — richer icons for custom items, at the cost of a one-time hak scan
    #: (~0.5s) the first time an inventory is shown. Off by default (opt-in).
    hak_item_icons: bool = False
    #: Work out each item's *own* inventory icon from the game files, the way
    #: the game does — an armour's torso model, a potion's three stacked parts,
    #: a cloak's variant. Off means every item of a type shows that type's one
    #: default picture: uniform, and nothing to look up.
    exact_item_icons: bool = True
    #: Save Game Editor colour theme: ``"dark"`` | ``"light"`` (see
    #: ``nwnsaveeditor.ui.editor.tokens.THEMES``). The editor is self-themed
    #: rather than following ``theme`` above, so it carries its own preference.
    save_editor_theme: str = "dark"
    #: Save Game Editor: allow editing class levels (opt-in, off by default). The
    #: editor defines this setting type; carrying it here lets the editor's own
    #: Settings screen show the toggle when it runs embedded in Vaultkeeper, with
    #: the value stored per host (the standalone editor keeps its own).
    enable_class_level_editing: bool = False
    #: Save Game Editor: extra saves folders to scan besides ``<user dir>/saves``
    #: (each holds NWN save sub-folders). The editor defines the protocol; carrying
    #: the list here lets its "Additional save folders" panel manage them when it
    #: runs embedded, exactly as the standalone editor does with its own file.
    extra_save_dirs: list[str] = field(default_factory=list)
    #: How a Vault project's file list is obtained: ``"api"`` asks the Vault's own
    #: API (what NIT v8.0 moved to, and what survives the site's redesign),
    #: ``"scrape"`` reads the project page's HTML as before. The API is the
    #: default because it is the one the Vault intends to keep answering; the
    #: scraper stays as the fallback for as long as the pages exist.
    vault_download_method: str = "api"
    #: Fetch the published Vault download rules rather than using only a local
    #: copy. The rules carry the API addresses and per-project fixes, so keeping
    #: them current is how a Vault change is absorbed without a new release.
    #: Off means the cached, then the bundled, copy is used.
    vault_rules_online: bool = True
    #: Apply the published rules' per-project entries: the mod folder and group a
    #: project belongs in, which of its files are wanted, and which are superseded
    #: and should not be offered. Off means a project is taken exactly as the
    #: Vault presents it (VB's Download Project rule preferences).
    vault_apply_project_rules: bool = True
    #: Expand a project's required projects into their files and pre-tick them, so
    #: one download fetches the module and its prerequisites together (VB's
    #: DownloadProject requirements list). Off leaves them shown but unticked — you
    #: opt each one in — so a missing dependency is never silent either way.
    vault_include_prerequisites: bool = True
    #: User's Web-menu links (``[{"text", "url"}, ...]``); defaults to Vault + Nexus.
    web_links: list[dict[str, str]] = field(default_factory=default_web_links)
    #: User's Run-menu external programs (``[{"text", "path"}, ...]``) shown after the
    #: fixed Play / Toolset entries (VB ``My.Settings.MenuRun`` / ``SetRunMenu``); empty
    #: by default (see :func:`default_run_links`).
    run_links: list[dict[str, str]] = field(default_factory=default_run_links)
    #: User map overrides ``{table: {key: folder}}`` merged onto the Mapper's default
    #: tables (VB My.Settings map customisations); empty = pure v21 defaults.
    map_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    #: User exclude additions ``{"files": [...], "folders": [...]}`` the installer
    #: scan skips (VB Settings "Excluded Items"); empty = default excludes only.
    map_exclude_overrides: dict[str, list[str]] = field(default_factory=dict)
    #: Global application font point size; ``0`` = platform default (VB
    #: ``My.Settings.Fonts`` via the BasicFontAndColourEditor's Font page). BOUNDED
    #: PORT: the VB editor sets a font per-element/control; here it is a single
    #: app-wide override, which is the high-value accessibility subset.
    font_point_size: int = 0
    #: UI font family, "" for the platform default (VB Fonts page). VB carries a
    #: font per element; the port has one, because it has one to apply.
    font_family: str = ""
    #: Overrides for the mod-list status colours, name → "#rrggbb" (VB Colour
    #: page). Only the colours this application actually paints with are
    #: offered: a picker for a colour nothing reads is a preference that lies.
    status_colours: dict[str, str] = field(default_factory=dict)
    #: UI colour theme: ``"system"`` | ``"light"`` | ``"dark"`` (VB
    #: BasicFontAndColourEditor's Colour page / colour settings, applied via
    #: ``SaveColourSettings``/``ApplyThemeToRichTextFiles``). BOUNDED PORT: the VB
    #: editor lets the user recolour individual UI elements; here it is a single
    #: light/dark/system palette choice.
    theme: str = "system"

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
