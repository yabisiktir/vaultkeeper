"""NWN:EE crash reports (VB ``CheckSelectedFiles.AddCrashDumpFiles`` + ``CrashDumpManager``).

When the game crashes, EE writes ``nwmain-crash-<date>...`` files into the user
folder's ``crashreport`` directory. NIT remembers which ones it has seen
(``CrashReportFiles``) and, after a session that produced new ones, says so and
offers a manager to look at or delete them (``FileShowCrashFileManager``, on by
default). Pre-89.8193 builds wrote them to the user folder root; this reads the
``crashreport`` folder only (every EE the tool supports writes there).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: Crash files start with this (VB ``Co.CrashFile``).
CRASH_PREFIX = "nwmain-crash-"
#: The user-folder subfolder EE writes them to (VB ``Paths.C.CrashReport``).
CRASH_FOLDER = "crashreport"
#: The per-profile list of crash files already reported (VB ``CrashReportFiles``).
KNOWN_FILE = "CrashReportFiles.txt"


@dataclass(frozen=True)
class CrashFile:
    path: Path
    size: int
    modified: datetime


def crash_files(user_dir: Path | None) -> list[CrashFile]:
    """Every crash file in the user folder's ``crashreport`` directory, newest first."""
    folder = (user_dir / CRASH_FOLDER) if user_dir is not None else None
    if folder is None or not folder.is_dir():
        return []
    found = []
    for entry in folder.iterdir():
        if entry.is_file() and entry.name.lower().startswith(CRASH_PREFIX):
            st = entry.stat()
            found.append(CrashFile(entry, st.st_size, datetime.fromtimestamp(st.st_mtime)))
    return sorted(found, key=lambda c: c.modified, reverse=True)


def read_known(data_dir: Path) -> list[str]:
    try:
        return [n for n in (data_dir / KNOWN_FILE).read_text(encoding="utf-8").splitlines() if n]
    except OSError:
        return []


def save_known(data_dir: Path, names: list[str]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / KNOWN_FILE).write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")


def new_crash_files(user_dir: Path | None, data_dir: Path) -> list[CrashFile]:
    """Crash files not reported before; remembers them (VB ``AddCrashDumpFiles``).

    The known list is also pruned of files that no longer exist (VB, when the
    manager closes), so it does not grow for ever.
    """
    files = crash_files(user_dir)
    known = {n.lower() for n in read_known(data_dir)}
    fresh = [c for c in files if c.path.name.lower() not in known]
    save_known(data_dir, sorted(c.path.name for c in files))
    return fresh
