"""Character level/class filter — ported from VB ``CharacterFilter`` + ``CharacterViewer``.

The Character Explorer's "Show all Levels" control opens a small dialog to enter a
level filter (e.g. ``20``, ``=20``, ``<15``, ``18-24``) and tick up to three class
names. This module is the headless core, faithful to the VB:

* :func:`validate_level_filter` = ``CharacterFilter.IsValidLevelFilter`` — returns the
  error message for an invalid entry (or ``None`` when valid).
* :class:`CharacterLevelFilter` = ``CharacterViewer.LbcFilter_Click``'s parse of the
  (validated) text into a comparer + level bounds, plus:
  * :meth:`matches` — ``CharacterInfo.Level`` comparison + ``ApplyClassFilter``,
  * :meth:`label` — the ``LcbFilter.CheckedText`` shown on the filter control,
  * :attr:`is_default` — whether the filter shows every character (VB ``TitleText``).

The class list itself comes from :func:`nwnfile.character.pc_class_names`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vaultkeeper.core.formatting import to_int

#: Filter control's default caption (VB ``LcbFilter.CheckedText`` in the designer).
SHOW_ALL_TEXT = "Show all Levels"

#: Name used in validation messages (VB ``CharacterFilter.FilterName``).
FILTER_NAME = "Character Level Filter"

#: Raised when a fourth class name is ticked (VB ``CharacterFilter.ClassNameError``).
CLASS_NAME_ERROR = "You can only specify 3 class names."

#: Maximum number of class names a filter may specify (VB rule in ``ItemCheck``).
MAX_CLASSES = 3

MIN_LEVEL = 1
MAX_LEVEL = 40

#: Valid comparer symbols (VB ``FilterComparers``).
_COMPARERS = ("<", "=", ">")


def validate_level_filter(text: str) -> str | None:
    """VB ``CharacterFilter.IsValidLevelFilter`` — ``None`` if valid, else the error.

    Mirrors the VB validation exactly: a blank entry or a lone comparer is rejected,
    spaces and redundant ``>`` symbols are stripped, a leading ``<``/``=`` is removed,
    a ``start-end`` range may have at most two parts, every character must be a digit,
    every value must be 1–40, and a range's second value must exceed the first
    (an equal range like ``20-20`` is accepted, as in VB).
    """
    level_filter = (text or "").strip()
    if not level_filter or level_filter in _COMPARERS:
        return f"You have not specified a {FILTER_NAME} value"

    # Remove spaces and unused '>' comparer symbols (VB Replace chain).
    level_filter = level_filter.replace(" ", "").replace(">", "")
    if not level_filter:
        # ">"-only inputs collapse to empty; VB would crash on the next Substring, so
        # treat as the blank case instead.
        return f"You have not specified a {FILTER_NAME} value"

    # Validate and remove a leading '<' or '=' comparer symbol.
    if level_filter[0] in _COMPARERS:
        level_filter = level_filter[1:]

    # Validate range formatting.
    parts = level_filter.split("-")
    if len(parts) > 2:
        return f"You specified an invalid {FILTER_NAME} format"

    # Check that only numeric characters have been entered.
    for value in parts:
        for ch in value:
            if not ("0" <= ch <= "9"):
                return f'"{ch}" is not a number'

    # Validate values (ToInteger returns -1 on empty, so "-20" fails the range here).
    values = [to_int(part) for part in parts]
    for value in values:
        if value > MAX_LEVEL or value < MIN_LEVEL:
            return "You must specify a number between 1 and 40"

    # Validate level range values (equal values are accepted, VB falls through).
    if len(values) > 1 and values[0] != values[1] and values[0] >= values[1]:
        return "The second Character Level must be higher than the first"

    return None


@dataclass(frozen=True)
class CharacterLevelFilter:
    """A parsed level/class filter (VB ``CharacterViewer`` FilterComparer/LevelFilter)."""

    comparer: str = ">"  # one of "<", "=", ">", or "" for a range
    level: int = MIN_LEVEL
    level_upper: int = 0
    class_names: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def parse(
        cls, level_text: str, class_names: tuple[str, ...] | list[str] = ()
    ) -> CharacterLevelFilter:
        """Parse a (validated) level-filter string, per VB ``LbcFilter_Click``.

        The text has spaces and ``>`` symbols removed; a leading ``<``/``=`` selects
        that comparer; a bare number means "level and higher" (``>``); a ``start-end``
        string is a range (empty comparer). Level 1 with ``<`` becomes ``=`` (there are
        no levels below 1). ``ToInteger`` yields ``-1`` for anything non-numeric.
        """
        text = (level_text or "").replace(" ", "").replace(">", "")
        level_upper = 0
        first = text[:1]
        if first in _COMPARERS:
            comparer = first
            level = to_int(text[1:])
        elif "-" not in text:
            level = to_int(text)
            comparer = ">"
        else:
            start, _, end = text.partition("-")
            level = to_int(start)
            level_upper = to_int(end)
            comparer = ""

        # There are no levels less than 1, so treat "<1" as an equality filter.
        if level == 1 and comparer == "<":
            comparer = "="

        return cls(
            comparer=comparer,
            level=level,
            level_upper=level_upper,
            class_names=tuple(class_names),
        )

    @property
    def is_default(self) -> bool:
        """True when the filter shows every character (VB ``TitleText`` test)."""
        return self.level == MIN_LEVEL and self.level_upper == 0 and not self.class_names

    def matches(self, level: int, description: str) -> bool:
        """True if a character at ``level`` with ``description`` passes the filter.

        ``description`` is the character's summary text; the class filter requires
        every selected class name to appear in it (VB ``ApplyClassFilter``).
        """
        return self._matches_level(level) and self._matches_classes(description)

    def _matches_level(self, level: int) -> bool:
        if self.comparer == "=":
            return level == self.level
        if self.comparer == "<":
            return level <= self.level
        if self.comparer == ">":
            return level >= self.level
        return self.level <= level <= self.level_upper  # range

    def _matches_classes(self, description: str) -> bool:
        if not self.class_names:
            return True
        haystack = description.casefold()
        return all(name.casefold() in haystack for name in self.class_names)

    def label(self) -> str:
        """The filter control's caption (VB ``LcbFilter.CheckedText`` per branch)."""
        suffix = self._class_suffix()
        if self.comparer == "=":
            return f"Only Show Level {self.level}{suffix}"
        if self.comparer == "<":
            return f"Show Level {self.level} and lower{suffix}"
        if self.comparer == ">":
            if self.level == MIN_LEVEL:
                return f"{SHOW_ALL_TEXT}{suffix}"
            return f"Show Level {self.level} and higher{suffix}"
        return f"Show Levels between {self.level} and {self.level_upper}{suffix}"

    def _class_suffix(self) -> str:
        """VB ``ClassFilterInfo`` — ``" for A, B"`` (or "" with no class filter)."""
        if not self.class_names:
            return ""
        info = " for "
        for name in self.class_names:
            info += f"{name}, "
        return info.rstrip().rstrip(",")
