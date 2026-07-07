"""Qt implementation of :class:`GameMapperPrompter`.

The play loop's name-resolution ladder falls back to the user when a logged/save
name is ambiguous (multiple candidate mods, an unknown name, or several profiles).
Headless code uses ``DefaultPrompter`` (picks the first / uses the name as-is); the
running app injects this Qt-backed prompter so those rungs show the real dialogs
(the VB ``MsgOptions`` chooser and ``NameTextEditor``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QWidget


class QtGameMapperPrompter:
    """Resolves GameMapper ambiguity via Qt input dialogs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        self._parent = parent

    def choose_mod(self, mod_list: list[str]) -> str:
        """Pick one mod from several that share the played file (VB AskUser)."""
        if not mod_list:
            return ""
        item, ok = QInputDialog.getItem(
            self._parent,
            "Select Mod",
            "You have more than one Mod containing the same file.\n"
            "Please select which Mod you last played or saved.",
            mod_list,
            0,
            False,
        )
        return item if ok else mod_list[0]

    def specify_mod_name(self, identifier: str, message: str) -> tuple[bool, str]:
        """Ask the user to type a mod name (VB NameTextEditor)."""
        text, ok = QInputDialog.getText(
            self._parent, "Mod Name", f"{message}\n\n({identifier})"
        )
        text = text.strip()
        return (ok and bool(text), text)

    def choose_profile(self, message: str, options: list[str]) -> int:
        """Pick which profile the session belonged to (VB MsgOptions)."""
        if not options:
            return 0
        item, ok = QInputDialog.getItem(
            self._parent, "Select Profile", message, options, 0, False
        )
        return options.index(item) if ok and item in options else 0
