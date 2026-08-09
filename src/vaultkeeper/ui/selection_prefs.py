"""Which file a mod's Contents pane opens on (VB Selection Preferences).

The status bar's Selection Preferences icon chooses between three answers, and
``newtopic34.htm`` describes all three: the item that was selected when the mod
was last looked at, the mod's play-time record, or its first document.

Kept apart from the widgets so the choosing is testable without a status bar,
and so *Clear Selection History* has something real to clear — VB's command
empties "Mod selection information for the Contents Panel and Details Panel"
(``newtopic63.htm``), which is exactly the history this keeps.
"""

from __future__ import annotations

from vaultkeeper.core import constants as C

#: The three answers, in the order the icon cycles them.
HISTORY = "history"
PLAY_TIME = "play_time"
TEXT_FILE = "text_file"

PREFERENCES = (HISTORY, PLAY_TIME, TEXT_FILE)

LABELS: dict[str, str] = {
    HISTORY: "Whatever was selected last time",
    PLAY_TIME: "The mod's play-time record",
    TEXT_FILE: "The mod's first document",
}

#: Document extensions, in the order VB prefers them.
_DOCUMENT_ORDER = (".rtf", ".txt", ".htm", ".html", ".pdf")


def choose(
    preference: str,
    files: list[tuple[str, str]],
    *,
    remembered: tuple[str, str] | None = None,
) -> tuple[str, str] | None:
    """The file to select, or ``None`` when nothing fits.

    Falls through rather than giving up: a mod with no play-time record and a
    preference for one should still open somewhere sensible, and "somewhere
    sensible" is the first document.
    """
    if not files:
        return None
    if preference == HISTORY and remembered in files:
        return remembered
    if preference == PLAY_TIME:
        for key in files:
            if key[1].lower() == C.PLAY_TIME_FILE.lower():
                return key
    return _first_document(files)


def _first_document(files: list[tuple[str, str]]) -> tuple[str, str] | None:
    """The first document by VB's extension preference, else nothing.

    Nothing, not "the first file": selecting a .hak because there is no readme
    puts the pane on something nobody asked to look at.
    """
    for extension in _DOCUMENT_ORDER:
        for key in files:
            if key[1].lower().endswith(extension):
                return key
    return None
