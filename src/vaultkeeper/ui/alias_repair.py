"""Ask before re-pointing ``nwn.ini`` aliases into the profile's user folder.

VB ``NwnFolderInfo.PopulateLocations`` does it silently on every profile load and
then says so; Vaultkeeper writes game config only when the user agrees.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_alias_repair(
    user_dir: Path, updates: dict[str, str], parent: QWidget | None = None
) -> bool:
    """True when the user agrees to point the listed aliases into ``user_dir``."""
    lines = "\n".join(f"{key} → {value}" for key, value in sorted(updates.items()))
    answer = QMessageBox.question(
        parent,
        "Alias Section",
        "Some folders in the Alias Section of your NWN.ini point outside this "
        f"profile's user folder:\n{user_dir}\n\nThe game, and every install, would "
        "use those other folders. Point them at this folder instead?\n\n"
        f"{lines}\n\nNWN.ini.bak keeps a copy of the file as it is now.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return answer == QMessageBox.StandardButton.Yes
