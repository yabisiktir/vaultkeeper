"""Find the henchmen a save is carrying.

A save has no companion roster: henchmen are ordinary creatures sitting in an
area's ``.git`` alongside everything else. They are identified here by NWN's own
convention — the stock companions all carry a ``NW_HEN_*`` tag — and by a
``MasterID`` that points at something rather than at ``OBJECT_INVALID``.

That is a convention, not a guarantee: a module is free to use its own tags for
its own henchmen, and those will not be recognised. The screen says so rather
than implying the list is exhaustive.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core.formats.erf_reader import ErfReader
from vaultkeeper.core.formats.gff import read_gff

_GIT_RESTYPE = 2023
#: OBJECT_INVALID — a creature that is not currently anyone's associate.
OBJECT_INVALID = 0x7F000000
#: The tag prefix NWN's stock henchmen use.
HENCHMAN_TAG_PREFIX = "NW_HEN_"


@dataclass
class Companion:
    """A henchman found in one of the save's areas."""

    area: str
    tag: str
    name: str
    current_hp: int
    max_hp: int
    experience: int
    faction: int
    master_id: int

    @property
    def is_associated(self) -> bool:
        """Whether the creature is currently following a master."""
        return self.master_id not in (0, OBJECT_INVALID)

    @property
    def display_name(self) -> str:
        return self.name or self.tag


def _text(value) -> str:
    text = getattr(value, "text", None)
    if callable(text):
        return text() or ""
    return str(value or "")


def find_companions(sav_path: Path, area_resrefs: list[str]) -> list[Companion]:
    """Every recognisable henchman across ``area_resrefs``."""
    reader = ErfReader()
    found: list[Companion] = []
    for resref in area_resrefs:
        res = reader.find_resource(sav_path, resref, res_type=_GIT_RESTYPE)
        if res is None:
            continue
        try:
            git = read_gff(reader.read_resource_bytes(sav_path, res))
        except Exception:
            continue
        entry = git.root.fields.get("Creature List")
        creatures = getattr(entry.value, "structs", []) if entry is not None else []
        for struct in creatures:
            companion = _companion(resref, struct)
            if companion is not None:
                found.append(companion)
    return found


def _companion(area: str, struct) -> Companion | None:
    fields = struct.fields

    def value(label, default=0):
        entry = fields.get(label)
        return entry.value if entry is not None else default

    tag = str(value("Tag", ""))
    master = int(value("MasterID", OBJECT_INVALID))
    looks_like_henchman = tag.upper().startswith(HENCHMAN_TAG_PREFIX)
    if not looks_like_henchman and master in (0, OBJECT_INVALID):
        return None
    if int(value("IsPC", 0)):
        return None  # the player is not their own companion

    return Companion(
        area=area,
        tag=tag,
        name=_text(value("FirstName", "")).strip(),
        current_hp=int(value("CurrentHitPoints", 0)),
        max_hp=int(value("MaxHitPoints", 0)),
        experience=int(value("Experience", 0)),
        faction=int(value("FactionID", 0)),
        master_id=master,
    )
