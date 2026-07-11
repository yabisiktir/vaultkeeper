"""Steam Workshop discovery — a bounded slice of VB ``SteamWorkshop``.

The full VB subsystem persists a ``WorkshopContents`` database, diffs it against
Steam's item folders (added/updated/removed/unsubscribed), fetches titles over the
network and edits unknown names. This module ports just what the read-only
``WorkshopViewer`` needs: enumerate the subscription id folders under Steam's
Workshop content path and map each id to a mod. A workshop id is *managed* when it
maps to a known mod (VB ``ModInfo.Managed`` / ``ModData.IsSteamManaged``).

Filesystem-only and injectable, so the whole thing is testable with a temp dir.
The persistent database, network title fetch and name editor are deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core.win_sort import win_compare

#: Steam depot id for Neverwinter Nights: Enhanced Edition.
STEAM_EE_APPID = "704450"
#: The ``modules`` sub-folder + ``.mod`` extension used to name a workshop item.
_MODULES_FOLDER = "modules"
_MOD_EXT = ".mod"

#: The mod group NIT files newly-created workshop mods under (VB ``Pdc.WorkshopGroup``).
WORKSHOP_GROUP = "820.  Steam Workshop"


def workshop_url(id_: str) -> str:
    """A Steam Workshop item's web page URL (VB ``Defs.SteamWorkshopUrl``)."""
    return f"https://steamcommunity.com/sharedfiles/filedetails/?id={id_}"


@dataclass
class WorkshopItem:
    """One Steam Workshop subscription (VB ``SteamWorkshop.ModInfo``)."""

    id: str
    folder: Path
    managed: bool
    mod_name: str


# -- WorkshopContents diff (VB SteamWorkshop.ValidateSteamContent) --------- #


@dataclass
class WorkshopFile:
    """A tracked file inside a workshop subscription (VB ``IdFileInfo``)."""

    size: int
    mtime: int  # last-modified time (ns), for change detection


@dataclass
class WorkshopIdInfo:
    """A workshop subscription's tracked state (VB ``IdInfo``)."""

    id: str
    mod_name: str
    files: dict[str, WorkshopFile] = field(default_factory=dict)

    @property
    def unknown_name(self) -> bool:
        return self.mod_name == unknown_mod_name(self.id)

    @property
    def display_name(self) -> str:
        """``<mod> (<id>)`` when named, else just ``Mod <id>`` (VB ``DisplayName``)."""
        return self.mod_name if self.unknown_name else f"{self.mod_name} ({self.id})"


@dataclass
class WorkshopDiff:
    """The result of diffing Steam's content against the stored contents."""

    contents: dict[str, WorkshopIdInfo]
    added: list[str] = field(default_factory=list)  # newly-seen subscriptions
    updated: list[str] = field(default_factory=list)  # existing subs whose files changed
    unsubscribed: list[str] = field(default_factory=list)  # subscriptions gone from Steam
    added_files: int = 0
    updated_files: int = 0
    removed_files: int = 0

    @property
    def summary(self) -> str:
        parts = [f"Workshop Subscriptions: {len(self.contents) or 'None'}."]
        if self.added:
            parts.append(f"Added: {len(self.added)}.")
        if self.updated:
            parts.append(f"Updated: {len(self.updated)}.")
        if self.unsubscribed:
            parts.append(f"Removed: {len(self.unsubscribed)}.")
        return " ".join(parts)


def unknown_mod_name(id_: str) -> str:
    """The default name for an unidentifiable subscription (VB ``UnknownModName``)."""
    return f"Mod {id_}"


def resolve_mod_name(id_folder: Path, id_: str, *, web_title: str = "") -> str:
    """Name a workshop subscription (VB ``IdInfo.GetModFolderName``).

    A web title (injected — network fetch is out of scope) wins; otherwise the first
    ``.mod`` file's stem in the item's ``modules`` folder; otherwise ``Mod <id>``.
    """
    if web_title:
        return web_title
    modules = id_folder / _MODULES_FOLDER
    if modules.is_dir():
        mods = sorted(p for p in modules.iterdir() if p.suffix.lower() == _MOD_EXT)
        if mods:
            return mods[0].stem
    return unknown_mod_name(id_)


def scan_id_files(id_folder: Path) -> dict[str, WorkshopFile]:
    """Every file under a subscription, keyed by its relative path (VB RefreshSteamFiles)."""
    files: dict[str, WorkshopFile] = {}
    if not id_folder.is_dir():
        return files
    for entry in id_folder.rglob("*"):
        if not entry.is_file():
            continue
        key = entry.relative_to(id_folder).as_posix()
        try:
            st = entry.stat()
            files[key] = WorkshopFile(size=st.st_size, mtime=st.st_mtime_ns)
        except OSError:
            continue
    return files


def diff_workshop(
    content_path: Path,
    stored: dict[str, WorkshopIdInfo],
    *,
    resolve_name=None,
) -> WorkshopDiff:
    """Diff Steam's content folders against the stored contents (VB ``ValidateSteamContent``).

    Produces the new contents plus the added (new subscriptions), updated (existing
    subscriptions whose files changed) and unsubscribed (folders gone from Steam)
    lists, with file-level add/update/remove counts. ``resolve_name(folder, id)``
    names a new subscription (defaults to :func:`resolve_mod_name`).
    """
    resolver = resolve_name or (lambda folder, id_: resolve_mod_name(folder, id_))
    diff = WorkshopDiff(contents={})

    if not content_path.is_dir():
        # Everything stored is now unsubscribed.
        diff.unsubscribed = list(stored)
        return diff

    present = {
        entry.name
        for entry in content_path.iterdir()
        if entry.is_dir() and entry.name.isdigit()
    }
    diff.unsubscribed = sorted(id_ for id_ in stored if id_ not in present)

    for id_ in sorted(present):
        folder = content_path / id_
        current = scan_id_files(folder)
        prev = stored.get(id_)
        if prev is None:
            diff.added.append(id_)
            mod_name = resolver(folder, id_)
            diff.added_files += len(current)
        else:
            mod_name = prev.mod_name
            changed = False
            for key, f in current.items():
                old = prev.files.get(key)
                if old is None:
                    diff.added_files += 1
                    changed = True
                elif old.size != f.size or old.mtime != f.mtime:
                    diff.updated_files += 1
                    changed = True
            gone = [k for k in prev.files if k not in current]
            diff.removed_files += len(gone)
            if gone:
                changed = True
            if changed:
                diff.updated.append(id_)
        diff.contents[id_] = WorkshopIdInfo(id_, mod_name, current)

    return diff


def contents_to_json(contents: dict[str, WorkshopIdInfo]) -> dict:
    """Serialise WorkshopContents to a JSON-safe dict."""
    return {
        id_: {
            "mod_name": info.mod_name,
            "files": {k: {"size": f.size, "mtime": f.mtime} for k, f in info.files.items()},
        }
        for id_, info in contents.items()
    }


def contents_from_json(data: dict) -> dict[str, WorkshopIdInfo]:
    """Rebuild WorkshopContents from a JSON dict."""
    contents: dict[str, WorkshopIdInfo] = {}
    for id_, entry in (data or {}).items():
        files = {
            k: WorkshopFile(size=int(v.get("size", 0)), mtime=int(v.get("mtime", 0)))
            for k, v in (entry.get("files") or {}).items()
        }
        contents[id_] = WorkshopIdInfo(id_, entry.get("mod_name", unknown_mod_name(id_)), files)
    return contents


def workshop_content_path(game_root: Path) -> Path | None:
    """The Steam Workshop content folder for NWN:EE, or None for a non-Steam install.

    A Steam install lives at ``…/steamapps/common/Neverwinter Nights``; its Workshop
    content sits at ``…/steamapps/workshop/content/704450`` (VB
    ``Paths.GetWorkshopContentPath``).
    """
    steamapps = game_root.parent.parent
    if steamapps.name.lower() != "steamapps":
        return None
    return steamapps / "workshop" / "content" / STEAM_EE_APPID


def scan_workshop(content_path: Path, id_to_mod: dict[str, str]) -> list[WorkshopItem]:
    """Enumerate subscription id folders and map them to mods (VB ``WorkshopMods``).

    ``id_to_mod`` maps a workshop id to the managing mod name (case-insensitive);
    ids absent from it are *unmanaged*. Results are natural-sorted by mod name, as
    the VB viewer sorts ``LvWorkshop`` on its Mod Name column.
    """
    if not content_path.is_dir():
        return []
    lookup = {key.lower(): value for key, value in id_to_mod.items()}
    items = [
        WorkshopItem(
            entry.name,
            entry,
            lookup.get(entry.name.lower(), "") != "",
            lookup.get(entry.name.lower(), ""),
        )
        for entry in content_path.iterdir()
        if entry.is_dir() and entry.name.isdigit()
    ]
    items.sort(key=cmp_to_key(lambda a, b: win_compare(a.mod_name, b.mod_name)))
    return items
