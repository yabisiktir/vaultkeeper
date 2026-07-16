"""Installation sets — named snapshots of which mods are installed (VB ``InstallationManager``).

A *set* records, per group, the desired install state of each member mod. **Applying**
a set installs the mods it marks installed and uninstalls those it marks uninstalled,
reaching that snapshot (VB ``InstallationManagerEditor.BtApply``). Three types
(VB ``SetTypes``):

- ``current`` — the live install state, rebuilt on load, never persisted, read-only.
- ``checkpoint`` — a static point-in-time snapshot; not editable by the user.
- ``user`` — a user-defined set the user can edit.

This is the headless core (data model + apply-diff + load-time validation + JSON). The
VB app serialises the sets with ``BinaryFormatter``; the port keeps its native-JSON data
strategy, so sets round-trip through :func:`sets_to_json` / :func:`sets_from_json`.

BOUNDED PORT (noted, not silently dropped): load-time validation drops groups/mods that
no longer exist (VB ``ValidateSets`` housekeeping) but does not auto-add newly-installed
mods to user sets, nor propagate group/mod *renames* into saved sets (VB
``RenameGroup``/``RenameMod``); a rename simply drops the now-missing name on next load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: Set types (VB ``InstallationManager.SetTypes``).
SET_CURRENT = "current"
SET_CHECKPOINT = "checkpoint"
SET_USER = "user"

#: Display name for the live "Current" set (VB ``InstallationManager.CurrentSetName``).
CURRENT_SET_NAME = "Current"

#: Install-state labels for a set/group (VB ``InstallationManager.State``).
STATE_UNINSTALLED = "uninstalled"
STATE_SOME = "some"
STATE_INSTALLED = "installed"


@dataclass
class ModEntry:
    """A mod within a set and its desired install state (VB ``ModInfo``)."""

    name: str
    desired_installed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "desired_installed": self.desired_installed}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModEntry:
        return cls(
            name=str(data.get("name", "")),
            desired_installed=bool(data.get("desired_installed", True)),
        )


@dataclass
class GroupEntry:
    """A group within a set and its member mods (VB ``GroupInfo``)."""

    name: str
    mods: list[ModEntry] = field(default_factory=list)

    def state(self) -> str:
        """The group's desired install state (VB ``GroupInfo.GroupState``)."""
        if not self.mods:
            return STATE_UNINSTALLED
        installed = sum(1 for m in self.mods if m.desired_installed)
        if installed == 0:
            return STATE_UNINSTALLED
        if installed == len(self.mods):
            return STATE_INSTALLED
        return STATE_SOME

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "mods": [m.to_dict() for m in self.mods]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupEntry:
        return cls(
            name=str(data.get("name", "")),
            mods=[ModEntry.from_dict(m) for m in data.get("mods", [])],
        )


@dataclass
class InstallationSet:
    """A named installation set (VB ``SetInfo``)."""

    name: str
    set_type: str = SET_USER
    created: str = ""
    updated: str = ""
    groups: list[GroupEntry] = field(default_factory=list)

    @property
    def editable(self) -> bool:
        """User sets are editable; current + checkpoint sets are read-only (VB)."""
        return self.set_type == SET_USER

    def state(self) -> str:
        """The set's overall install state (VB ``SetInfo.SetState``)."""
        if not self.groups:
            return STATE_UNINSTALLED
        installed = sum(1 for g in self.groups if g.state() == STATE_INSTALLED)
        if installed == len(self.groups):
            return STATE_INSTALLED
        if installed > 0 or any(g.state() == STATE_SOME for g in self.groups):
            return STATE_SOME
        return STATE_UNINSTALLED

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "set_type": self.set_type,
            "created": self.created,
            "updated": self.updated,
            "groups": [g.to_dict() for g in self.groups],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallationSet:
        return cls(
            name=str(data.get("name", "")),
            set_type=str(data.get("set_type", SET_USER)),
            created=str(data.get("created", "")),
            updated=str(data.get("updated", "")),
            groups=[GroupEntry.from_dict(g) for g in data.get("groups", [])],
        )


def now_iso() -> str:
    """A timestamp for created/updated fields (seconds precision)."""
    return datetime.now().isoformat(timespec="seconds")


def checkpoint_name(when: datetime | None = None) -> str:
    """The auto name for a checkpoint set (VB ``"Checkpoint " & Now``)."""
    when = when or datetime.now()
    return f"Checkpoint {when.strftime('%Y-%m-%d %H.%M.%S')}"


def build_set(
    name: str,
    set_type: str,
    installed_by_group: dict[str, list[str]],
) -> InstallationSet:
    """Build a set from the currently-installed mods (VB ``Checkpoint`` / ``SetInfo`` ctor).

    ``installed_by_group`` maps each group name to its installed mod names (already in
    display order). Every mod is recorded ``desired_installed=True`` — a snapshot of what
    is installed now.
    """
    groups = [
        GroupEntry(name=group, mods=[ModEntry(m, True) for m in mods])
        for group, mods in installed_by_group.items()
    ]
    stamp = now_iso()
    return InstallationSet(
        name=name, set_type=set_type, created=stamp, updated=stamp, groups=groups
    )


def apply_diff(iset: InstallationSet, current_installed: set[str]) -> tuple[list[str], list[str]]:
    """Return ``(installs, uninstalls)`` to reach the set's desired states.

    Only mods *in the set* whose desired state differs from their current state are
    acted on (VB ``BtApply`` ``ApplyList`` — mods not in the set are left untouched).
    Duplicate names across groups are de-duplicated, first occurrence wins.
    """
    installs: list[str] = []
    uninstalls: list[str] = []
    seen: set[str] = set()
    for group in iset.groups:
        for mod in group.mods:
            if mod.name in seen:
                continue
            seen.add(mod.name)
            currently = mod.name in current_installed
            if mod.desired_installed and not currently:
                installs.append(mod.name)
            elif not mod.desired_installed and currently:
                uninstalls.append(mod.name)
    return installs, uninstalls


def validate_sets(
    sets: list[InstallationSet],
    existing_mods: dict[str, str],
    existing_groups: set[str],
) -> int:
    """Drop groups/mods that no longer exist (VB ``ValidateSets`` housekeeping, bounded).

    ``existing_mods`` maps a live mod name to its current group; ``existing_groups`` is
    the set of live group names. The current set is skipped (rebuilt fresh each load).
    Returns the number of removed groups + mods.
    """
    removed = 0
    for iset in sets:
        if iset.set_type == SET_CURRENT:
            continue
        kept_groups: list[GroupEntry] = []
        for group in iset.groups:
            if group.name not in existing_groups:
                removed += 1
                continue
            kept_mods = [m for m in group.mods if m.name in existing_mods]
            removed += len(group.mods) - len(kept_mods)
            group.mods = kept_mods
            kept_groups.append(group)
        iset.groups = kept_groups
    return removed


def sets_to_json(sets: list[InstallationSet]) -> list[dict[str, Any]]:
    """Serialise the persistable sets (the current set is never written)."""
    return [s.to_dict() for s in sets if s.set_type != SET_CURRENT]


def sets_from_json(data: Any) -> list[InstallationSet]:
    """Deserialise persisted sets; tolerates a missing/blank file (returns ``[]``)."""
    if not isinstance(data, list):
        return []
    return [InstallationSet.from_dict(d) for d in data if isinstance(d, dict)]
