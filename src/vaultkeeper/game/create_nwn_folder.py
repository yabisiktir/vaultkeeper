"""Create an isolated NWN installation folder for a profile (VB ``CreateNwnFolder``).

Clones an existing NWN install's *contents* (its top-level files + sub-folders,
not the source root itself) into a new target folder, so a profile can have its
own game directory that other profiles' installs never touch.  For classic NWN it
also copies ``nwn.ini`` from a config source when the target lacks one (VB skips
this for Enhanced Edition).

Headless + testable: :func:`create_nwn_folder` does the copy and returns a
:class:`CreateFolderResult`; the dialog (``ui/dialogs/create_nwn_folder.py``)
drives it.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

#: Config ini copied for classic NWN (VB ``NwnFolderInfo.ConfigIniFile``).
CONFIG_INI_FILE = "nwn.ini"


@dataclass
class CreateFolderResult:
    """Outcome of a create-folder request (VB DialogResult OK/Cancel/Abort)."""

    status: str  # "ok" | "abort" | "cancel"
    copied: int = 0
    failed: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def create_nwn_folder(
    target: Path,
    source: Path,
    *,
    is_ee: bool = True,
    config_ini_source: Path | None = None,
) -> CreateFolderResult:
    """Populate ``target`` by copying the *contents* of ``source`` (VB CreateFolder).

    ``target`` is created if missing.  Every top-level file and sub-folder of
    ``source`` is copied in (the source root itself is not nested).  An empty
    source aborts and removes a freshly-created target.  For classic NWN
    (``is_ee=False``), ``nwn.ini`` is copied from ``config_ini_source`` when the
    target has none.  Returns a :class:`CreateFolderResult`.
    """
    target = Path(target)
    source = Path(source)

    if not source.is_dir():
        return CreateFolderResult("abort", message=f"Source folder not found: {source}")

    # Guard: never create the copy inside the source (would recurse) or onto it.
    if target == source or _is_within(target, source):
        return CreateFolderResult(
            "abort", message="Target folder must be outside the source folder."
        )

    freshly_created = not target.exists()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CreateFolderResult("abort", message=f"Could not create target: {exc}")

    entries = sorted(source.iterdir(), key=lambda p: p.name.lower())
    if not entries:
        if freshly_created:
            shutil.rmtree(target, ignore_errors=True)
        return CreateFolderResult("abort", message="The source folder is empty.")

    copied = 0
    failed: list[str] = []
    for entry in entries:
        dest = target / entry.name
        try:
            if entry.is_dir():
                shutil.copytree(entry, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, dest)
            copied += 1
        except OSError as exc:  # noqa: PERF203
            failed.append(f"{entry.name}: {exc}")

    # Classic NWN: bring over nwn.ini from the config source if the target lacks one.
    if not is_ee and config_ini_source is not None:
        target_ini = target / CONFIG_INI_FILE
        source_ini = Path(config_ini_source) / CONFIG_INI_FILE
        if not target_ini.exists() and source_ini.is_file():
            with contextlib.suppress(OSError):
                shutil.copy2(source_ini, target_ini)

    if failed and copied == 0:
        if freshly_created:
            shutil.rmtree(target, ignore_errors=True)
        return CreateFolderResult(
            "abort", copied=copied, failed=failed, message="Copy failed."
        )
    msg = f"Created the game folder ({copied} item(s) copied)."
    if failed:
        msg += f" {len(failed)} item(s) failed."
    return CreateFolderResult("ok", copied=copied, failed=failed, message=msg)


def default_target(parent: Path, profile_name: str, *, is_ee: bool = True) -> Path:
    """Suggested target under ``parent`` named for the edition + profile (VB DefaultTarget)."""
    edition_folder = "NeverwinterNights EE" if is_ee else "NeverwinterNights"
    return Path(parent) / edition_folder / profile_name


def _is_within(child: Path, parent: Path) -> bool:
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False
