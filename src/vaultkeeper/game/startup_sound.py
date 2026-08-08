"""The start-up sound (VB ``NIT.Common.PlayStartupSound``).

NIT plays the game's own autorun fanfare when it opens, if you ask it to. The
preference was ported, shown in two settings screens, saved and reloaded — and
read by nothing, so ticking it did precisely nothing.

Resolving the file is the whole of the interesting part. VB looks in
``<game>\\music\\mus_autorun.wav`` for the classic game and
``<extended data>\\mus\\mus_autorun.wav`` for the Enhanced Edition; on a real EE
install that second path is ``<game>/data/mus/mus_autorun.wav``. Both are tried,
because a machine can have either.
"""

from __future__ import annotations

from pathlib import Path

#: Where the game keeps its autorun fanfare, EE layout first (VB
#: ``PathStartupSound`` defaults: ``ExtendedDataPath\mus`` / ``Nwn\music``).
_CANDIDATES = (
    ("data", "mus", "mus_autorun.wav"),
    ("music", "mus_autorun.wav"),
    ("mus", "mus_autorun.wav"),
)


def default_sound(game_root: Path | str | None) -> Path | None:
    """The game's autorun sound, or ``None`` when it cannot be found.

    Returning ``None`` rather than a made-up path matters: the caller shows the
    resolved file in Settings, and a path to something that does not exist is
    worse than an empty box, which at least says "nothing found".
    """
    if not game_root:
        return None
    root = Path(game_root)
    for parts in _CANDIDATES:
        candidate = root.joinpath(*parts)
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def resolve_sound(configured: str | None, game_root: Path | str | None) -> Path | None:
    """The sound to play: what was configured, else the game's own.

    A configured path that has gone missing falls back to the game's rather than
    silently playing nothing — an uninstalled sound pack should not turn the
    preference off.
    """
    if configured:
        chosen = Path(configured)
        try:
            if chosen.is_file():
                return chosen
        except OSError:
            pass
    return default_sound(game_root)
