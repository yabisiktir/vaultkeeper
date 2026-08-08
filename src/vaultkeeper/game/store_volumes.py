"""Where the store could live, and which volume has room for it.

The store holds every mod's downloaded archives and its built installer payload,
so it grows to the size of someone's whole mod collection — tens of gigabytes is
ordinary. The platform default puts it beside the application's own data, which
on the common setup (small system SSD, large data drive) is the wrong drive, and
nothing about the default says so.

NIT asks at first run and recommends the volume with the most free space. This
works out the same answer. It only *offers*: a volume with room is not
automatically the right one — an external disk that is not always plugged in has
plenty of room and is a poor home for a store — so the recommendation is a
default in a list, never a decision.
"""

from __future__ import annotations

import os
import shutil
import string
from dataclasses import dataclass
from pathlib import Path

#: The folder name a store gets when it is placed on a volume by hand.
STORE_DIR_NAME = "Vaultkeeper"


@dataclass(frozen=True)
class StoreVolume:
    """One place the store could go, and how much room is there."""

    #: Where the store would be created.
    path: Path
    #: Free bytes on the volume holding it; 0 when it could not be read.
    free: int
    #: The platform's own default location.
    is_default: bool = False
    #: Reached over the network. Offered, never recommended — see :func:`recommended`.
    is_network: bool = False

    @property
    def label(self) -> str:
        where = " (network)" if self.is_network else ""
        return f"{self.path}{where}  —  {_human(self.free)} free"


def _human(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "bytes" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


def _free(path: Path) -> int:
    """Free bytes on the volume holding ``path`` — its nearest existing parent."""
    probe = path
    while True:
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            if probe.parent == probe:
                return 0
            probe = probe.parent


def _mount_points() -> list[Path]:
    """Volumes worth offering, per platform.

    Deliberately shallow: the roots a person recognises, not every mount the
    kernel knows about. A list including ``/System/Volumes/VM`` helps nobody.
    """
    if os.name == "nt":
        return [
            Path(f"{letter}:\\")
            for letter in string.ascii_uppercase
            if Path(f"{letter}:\\").is_dir()
        ]
    roots = [Path("/")]
    for parent in (Path("/Volumes"), Path("/media"), Path("/mnt")):
        try:
            entries = sorted(parent.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir() and not entry.is_symlink():
                    roots.append(entry)
            except OSError:
                continue
    return roots


def candidates(default_root: Path) -> list[StoreVolume]:
    """Store locations to offer, most free space first.

    ``default_root`` — the platform default — is always present and always
    marked, even when it is the smallest: someone who wants the ordinary place
    should not have to hunt for it.
    """
    default_root = Path(default_root)
    found = [StoreVolume(default_root, _free(default_root), is_default=True)]
    seen = {_volume_key(default_root)}

    for mount in _mount_points():
        key = _volume_key(mount)
        if key in seen:
            continue
        seen.add(key)
        free = _free(mount)
        if free <= 0 or not os.access(mount, os.W_OK):
            continue  # unreadable, full, or not ours to write to
        found.append(StoreVolume(mount / STORE_DIR_NAME, free, is_network=_is_network(mount)))

    return sorted(found, key=lambda v: (-v.free, str(v.path)))


def _is_network(path: Path) -> bool:
    """Whether a volume is reached over the network."""
    from nwnfile.locations import is_network_path

    try:
        return bool(is_network_path(path))
    except Exception:
        return False


def _volume_key(path: Path) -> object:
    """Identifies the volume a path sits on, so one volume is offered once."""
    probe = path
    while True:
        try:
            info = probe.stat()
            return (info.st_dev,)
        except OSError:
            if probe.parent == probe:
                return (str(path).lower(),)
            probe = probe.parent


def recommended(
    default_root: Path, *, options: list[StoreVolume] | None = None, margin: float = 2.0
) -> StoreVolume:
    """The volume to preselect.

    The default wins unless a **local** volume has ``margin`` times its free
    space — a little more room is not worth sending someone's store to a second
    disk, and a lot more room is exactly the case NIT's question exists for.

    Network volumes are never recommended, however roomy. A NAS share has
    hundreds of spare gigabytes and is the wrong home for a store that must be
    readable every time the application opens; this machine offers three such
    shares, each reporting 493 GB, and picking one of them automatically would
    put the whole profile behind a mount that is not always there. They stay in
    the list for anyone who means it.

    Pass ``options`` to weigh a list you already have. Free space moves while a
    machine is running, so scanning twice returns two sets of values equal in
    meaning and unequal as data — worth avoiding both for the wasted scan and
    for anyone comparing the result against their own list.
    """
    options = list(options) if options is not None else candidates(default_root)
    default = next((v for v in options if v.is_default), options[0])
    local = [v for v in options if not v.is_network]
    best = local[0] if local else default
    if best is default or best.free < default.free * margin:
        return default
    return best
