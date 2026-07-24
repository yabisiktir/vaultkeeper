"""Bulk find-and-rename over mod names (VB ``ModFindAndRename``).

Faithful headless port of the ``ModFindAndRename.ModNames`` / ``ModNameInfo``
find-and-replace engine.  The VB dialog lets the user type a *find* string and a
*replace* string, choose *Match start* / *Match case*, and rewrite the matching
mod names in bulk before applying them all at once.

Semantics preserved from the VB source:

* **Match start** couples two behaviours (VB ``MatchStart`` ⇔ ``ReplaceCount``):
  when on, find uses ``StartsWith`` and replace rewrites only the *first*
  occurrence (``Strings.Replace`` ``Count:=1``); when off, find uses ``Contains``
  and replace rewrites *all* occurrences (``Count:=-1``).
* **Match case** selects case-sensitive vs case-insensitive find and replace.
* Find and replace both operate on the working ``new_name`` (not the original),
  so successive replaces compound (VB operates on ``.NewName``).
* Duplicate detection mirrors VB ``IsDuplicate``: a candidate name that collides
  with another entry's current-or-new name (first match in list order wins) is
  flagged; flagged entries are excluded from the applied renames.
* Names are Windows-natural sorted (VB ``WindowsSorter``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key

from vaultkeeper.core.win_sort import win_compare


def vb_replace(text: str, find: str, repl: str, *, count: int, case_sensitive: bool) -> str:
    """Port of VB ``Strings.Replace(text, find, repl, Start:=1, Count, Compare)``.

    ``count`` of ``1`` rewrites only the first occurrence; ``-1`` rewrites all.
    Matching honours ``case_sensitive``; the replacement text is inserted verbatim.
    """
    if not find:
        return text
    hay = text if case_sensitive else text.lower()
    needle = find if case_sensitive else find.lower()
    n = len(needle)
    out: list[str] = []
    i = 0
    done = 0
    while i < len(text):
        if (count < 0 or done < count) and hay[i : i + n] == needle:
            out.append(repl)
            i += n
            done += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


@dataclass
class ModNameEntry:
    """One mod name's current/working state (VB ``ModNameInfo``)."""

    current_name: str
    new_name: str
    selected: bool = False
    duplicated: bool = False

    @property
    def changed(self) -> bool:
        return self.current_name != self.new_name


@dataclass
class ModRenameSet:
    """Working set of mod names for bulk find/replace (VB ``ModNames``)."""

    entries: list[ModNameEntry] = field(default_factory=list)
    match_start: bool = True
    match_case: bool = False
    _found: list[int] = field(default_factory=list)
    _search: str = ""
    _next_pos: int = -1

    @classmethod
    def from_names(
        cls, names: list[str], *, match_start: bool = True, match_case: bool = False
    ) -> ModRenameSet:
        entries = [ModNameEntry(n, n) for n in names]
        s = cls(entries=entries, match_start=match_start, match_case=match_case)
        s._sort()
        return s

    # -- ordering --------------------------------------------------------- #
    def _sort(self) -> None:
        self.entries.sort(key=lambda e: cmp_to_key(win_compare)(e.new_name))

    # -- find ------------------------------------------------------------- #
    def find(self, search: str) -> list[int]:
        """Populate the found set for ``search`` and return the matching indices.

        A blank search matches nothing (VB ``FindMods``).  Uses ``StartsWith``
        when *match start* is on, otherwise ``Contains``.
        """
        self._search = search
        self._next_pos = -1
        if not search:
            self._found = []
            return []
        needle = search if self.match_case else search.lower()
        found: list[int] = []
        for i, e in enumerate(self.entries):
            hay = e.new_name if self.match_case else e.new_name.lower()
            hit = hay.startswith(needle) if self.match_start else (needle in hay)
            if hit:
                found.append(i)
        self._found = found
        return list(found)

    @property
    def found_count(self) -> int:
        return len(self._found)

    def find_next(self) -> int | None:
        """Advance to the next found entry index, cycling (VB ``NextIndex``).

        Returns the entry index to select, or ``None`` when nothing is found.
        """
        if not self._found:
            return None
        self._next_pos = (self._next_pos + 1) % len(self._found)
        return self._found[self._next_pos]

    def select_found(self) -> None:
        """Select exactly the found entries (VB ``SelectFoundIndices``)."""
        for e in self.entries:
            e.selected = False
        for i in self._found:
            self.entries[i].selected = True

    # -- duplicate detection (VB IsDuplicate) ----------------------------- #
    def _is_duplicate(self, value: str, index: int) -> bool:
        for i, e in enumerate(self.entries):
            if value == e.current_name or value == e.new_name:
                return i != index
        return False

    # -- replace ---------------------------------------------------------- #
    @property
    def _replace_count(self) -> int:
        return 1 if self.match_start else -1

    def _replace_at(self, index: int, repl: str) -> None:
        e = self.entries[index]
        new = vb_replace(
            e.new_name,
            self._search,
            repl,
            count=self._replace_count,
            case_sensitive=self.match_case,
        ).strip()
        e.duplicated = self._is_duplicate(new, index)
        e.new_name = new

    def replace_all(self, repl: str, indices: list[int] | None = None) -> None:
        """Apply the replacement to the found entries (VB ``ReplaceAll``).

        ``indices`` restricts which found entries are rewritten; ``None`` means
        all found.  The found set is cleared afterwards, matching VB.
        """
        allowed = set(self._found if indices is None else indices)
        for i in list(self._found):
            if i in allowed:
                self._replace_at(i, repl)
        self._found = []

    def replace_one(self, index: int, repl: str) -> None:
        """Rewrite a single found entry and drop it from the found set (VB ``Replace``)."""
        self._replace_at(index, repl)
        if index in self._found:
            self._found.remove(index)

    def undo_one(self, index: int) -> None:
        """Revert a single entry's working name to its original (VB single Undo)."""
        e = self.entries[index]
        e.new_name = e.current_name
        e.duplicated = False

    def reset(self) -> None:
        """Revert every working name to its original (VB Undo All)."""
        for e in self.entries:
            e.new_name = e.current_name
            e.duplicated = False
            e.selected = False
        self._found = []
        self._search = ""
        self._next_pos = -1

    # -- results ---------------------------------------------------------- #
    @property
    def change_count(self) -> int:
        return sum(1 for e in self.entries if e.changed)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for e in self.entries if e.duplicated)

    @property
    def renames(self) -> dict[str, str]:
        """current → new for changed entries that do not collide (VB ``Renames``)."""
        return {
            e.current_name: e.new_name
            for e in self.entries
            if e.changed and not e.duplicated
        }
