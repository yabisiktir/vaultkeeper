"""Start-up options: the way back in when the app will not start (VB NIT.Menu).

These are not conveniences. Every one of them exists to get past a start-up
that crashes — a corrupted store, settings pointing at a folder that is gone —
by doing something *before* the thing that crashes runs. The help says so
plainly: "designed to help you overcome problems that prevent the Tool from
starting normally".

Two ways in, exactly as in the original:

* on the command line — ``-Settings``, or its first letter, ``-S``;
* by holding a modifier key while the app starts, for when there is no command
  line to type on: **Ctrl** for the menu, **Alt** to restore profile data,
  **Shift** to silence the start-up sound.

A modifier and a flag do not conflict; either turns the option on (VB ORs them
together).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

#: Option name → the attribute it sets. Order is the order the menu offers them.
#: The names are VB's own enum members, which is what the help documents; each
#: may be abbreviated to its first letter, so the initials must stay unique.
OPTIONS: dict[str, str] = {
    "CommandMenu": "command_menu",
    "Settings": "show_settings",
    "ProfileValidate": "validate_profile",
    "RestoreProfileData": "restore_profile_data",
    "MusicOff": "music_off",
}

#: What each option does, for the menu and for ``--help``. VB's help wording.
DESCRIPTIONS: dict[str, str] = {
    "CommandMenu": "Display this menu of start-up options.",
    "Settings": "Show Settings before any profile data is loaded.",
    "ProfileValidate": "Validate profile information after it has been loaded.",
    "RestoreProfileData": (
        "List your data backups before loading profile information, so you can "
        "restore from one."
    ),
    "MusicOff": "Do not play the start-up sound.",
}


@dataclass
class StartupOptions:
    """What was asked for at start-up, however it was asked."""

    command_menu: bool = False
    show_settings: bool = False
    validate_profile: bool = False
    restore_profile_data: bool = False
    music_off: bool = False
    #: Arguments that looked like options and are not, reported rather than
    #: ignored (VB shows them in a message box) — a silently dropped ``-Setings``
    #: is how someone ends up believing the option does not work.
    invalid: list[str] = field(default_factory=list)

    def any_requested(self) -> bool:
        return bool(
            self.command_menu
            or self.show_settings
            or self.validate_profile
            or self.restore_profile_data
            or self.music_off
        )

    def merged_with(self, other: StartupOptions) -> StartupOptions:
        """Either source turning an option on turns it on."""
        return StartupOptions(
            command_menu=self.command_menu or other.command_menu,
            show_settings=self.show_settings or other.show_settings,
            validate_profile=self.validate_profile or other.validate_profile,
            restore_profile_data=(
                self.restore_profile_data or other.restore_profile_data
            ),
            music_off=self.music_off or other.music_off,
            invalid=self.invalid + other.invalid,
        )

    def with_option(self, name: str) -> StartupOptions:
        """A copy with the named option (a key of :data:`OPTIONS`) turned on."""
        return replace(self, **{OPTIONS[name]: True})


def _lookup() -> dict[str, str]:
    """Full names and single-letter abbreviations, lower-cased."""
    table = {name.lower(): name for name in OPTIONS}
    table.update({name[0].lower(): name for name in OPTIONS})
    return table


def parse_args(argv: list[str]) -> StartupOptions:
    """Read the options out of a command line (VB ``ProcessCommandLine``).

    Case-insensitive, each option abbreviable to its first letter. Anything else
    beginning with ``-`` is collected as invalid rather than dropped. Arguments
    that do not begin with ``-`` are left alone: they belong to someone else
    (``--scan`` is handled before this, and Qt reads its own).
    """
    table = _lookup()
    options = StartupOptions()
    for arg in argv:
        if not arg.startswith("-"):
            continue
        name = table.get(arg.lstrip("-").lower())
        if name is None:
            options.invalid.append(arg)
            continue
        options = options.with_option(name)
    return options


def from_modifiers(modifiers) -> StartupOptions:
    """The options a held key asks for (VB reads the keyboard at start-up).

    Ctrl opens the menu, Alt restores profile data, Shift silences the sound —
    the point being that they need no command line, which is what you have when
    the app crashes from an icon someone double-clicked.
    """
    from PySide6.QtCore import Qt

    return StartupOptions(
        command_menu=bool(modifiers & Qt.KeyboardModifier.ControlModifier),
        restore_profile_data=bool(modifiers & Qt.KeyboardModifier.AltModifier),
        music_off=bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
    )


def menu_options() -> list[tuple[str, str]]:
    """``(name, description)`` for the menu — everything but the menu itself."""
    return [(name, DESCRIPTIONS[name]) for name in OPTIONS if name != "CommandMenu"]


def usage_text() -> str:
    """The options, for ``--help`` and for the invalid-argument message."""
    lines = ["Start-up options (case-insensitive, abbreviable to the first letter):"]
    width = max(len(name) for name in OPTIONS)
    for name in OPTIONS:
        lines.append(f"  -{name:<{width}}  -{name[0]}  {DESCRIPTIONS[name]}")
    return "\n".join(lines)
