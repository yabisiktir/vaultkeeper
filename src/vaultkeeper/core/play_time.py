"""Play-time records — faithful ports of ``PlayTimeInfo`` and ``PlayData``.

``PlayTimeInfo`` is one line of a per-mod ``.Game Play Time.rtf`` file (a completed
date, a formatted duration, and the OS user who played). ``PlayData`` is the whole
play-time database: totals plus a per-mod duration map. Both are pure data; the
recording/parsing logic lives in :mod:`vaultkeeper.game.play_data_manager`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import cmp_to_key

from vaultkeeper.core.ci_dict import CIStrDict
from vaultkeeper.core.formatting import parse_date_string, to_date_string, to_int


class PlayTimeInfo:
    """A single Game Play Time record: ``completed, play_time, user_name``.

    Sorts in *descending* completed-date order (newest first), matching the VB
    ``IComparable`` implementation. Equality is case-insensitive on the CSV string.
    """

    __slots__ = ("completed", "play_time", "user_name", "play_time_span")

    def __init__(
        self,
        completed: str = "",
        play_time: str = "",
        user_name: str = "",
        play_time_span: timedelta = timedelta(0),
    ) -> None:
        # Derive the TimeSpan from the formatted string when one wasn't supplied.
        if play_time_span == timedelta(0) and play_time != "":
            fields = play_time.split(" ")
            if len(fields) > 3:
                play_time_span = timedelta(
                    hours=to_int(fields[0]), minutes=to_int(fields[2])
                )
            elif "hour" in play_time.lower():
                play_time_span = timedelta(hours=to_int(fields[0]))
            else:
                play_time_span = timedelta(minutes=to_int(fields[0]))

        self.completed = completed
        self.play_time = play_time
        self.user_name = user_name
        self.play_time_span = play_time_span

    def __str__(self) -> str:
        return f"{self.completed},{self.play_time},{self.user_name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlayTimeInfo):
            return NotImplemented
        return str(self).lower() == str(other).lower()

    def __hash__(self) -> int:
        return hash(str(self).lower())

    def clone(self) -> PlayTimeInfo:
        return PlayTimeInfo(
            self.completed, self.play_time, self.user_name, self.play_time_span
        )

    def compare_to(self, other: PlayTimeInfo) -> int:
        """Descending by completed date (``DateTime.Compare`` negated)."""
        a = parse_date_string(self.completed) or datetime.min
        b = parse_date_string(other.completed) or datetime.min
        # Descending: newest first.
        return (b > a) - (b < a)


def sort_play_times(items: list[PlayTimeInfo]) -> None:
    """In-place sort into descending completed-date order (VB ``List.Sort``)."""
    items.sort(key=cmp_to_key(PlayTimeInfo.compare_to))


def distinct_play_times(items: list[PlayTimeInfo]) -> list[PlayTimeInfo]:
    """De-duplicate preserving order (VB ``Distinct`` with the equality comparer)."""
    seen: set[str] = set()
    result: list[PlayTimeInfo] = []
    for item in items:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class PlayData:
    """All game play time information (``PlayDataManager.PlayData``).

    ``last_played`` is a ``"dd MMM yyyy"`` string; ``play_times`` maps mod name →
    duration and is case-insensitive on the mod name.
    """

    __slots__ = ("total_played", "total_today", "most_in_one_day", "last_played", "play_times")

    def __init__(self) -> None:
        self.total_played: timedelta = timedelta(0)
        self.total_today: timedelta = timedelta(0)
        self.most_in_one_day: timedelta = timedelta(0)
        self.last_played: str = to_date_string(datetime.now())
        self.play_times: CIStrDict[timedelta] = CIStrDict()
