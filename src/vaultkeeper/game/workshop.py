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

from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core.win_sort import win_compare

#: Steam depot id for Neverwinter Nights: Enhanced Edition.
STEAM_EE_APPID = "704450"


@dataclass
class WorkshopItem:
    """One Steam Workshop subscription (VB ``SteamWorkshop.ModInfo``)."""

    id: str
    folder: Path
    managed: bool
    mod_name: str


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
