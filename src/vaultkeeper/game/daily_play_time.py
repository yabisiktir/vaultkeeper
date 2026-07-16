"""Daily play-time averages (VB ``DailyPlayTimeInfo``).

Tracks how long the game was played each day so NIT can show an average hours-per-day
figure (the VB "Auto" day-conversion factor, ``ConfigAutoDayConversionFactor``). The
original keys its dictionary by *day-of-month* (1-31), which silently collides across
months; the port keys by full ISO date instead — strictly a bug-fix divergence — and
otherwise mirrors ``DailyAverage`` / ``GetDailyPlayInfo``. Persisted as native JSON
(``DailyPlayTime.json``); VB used a BinaryFormatter blob.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


def _today_iso() -> str:
    return date.today().isoformat()


@dataclass
class DailyPlayTime:
    """Minutes played per calendar day (VB ``DailyPlayTimeInfo.PlayTimes``)."""

    minutes_by_date: dict[str, int] = field(default_factory=dict)

    def add(self, minutes: int, *, day: str | None = None) -> None:
        """Add ``minutes`` to a day's total (VB ``TodaysTime``; today by default)."""
        if minutes <= 0:
            return
        day = day or _today_iso()
        self.minutes_by_date[day] = self.minutes_by_date.get(day, 0) + int(minutes)

    def daily_average_hours(self, *, today: str | None = None) -> int:
        """Average whole hours per day over past non-zero days (VB ``DailyAverage``).

        Today is excluded; the result is at least 1. With a single recorded day, that
        day's hours are used.
        """
        today = today or _today_iso()
        past = [m for d, m in self.minutes_by_date.items() if d != today and m > 0]
        if not past:
            # Only today recorded -> use today's hours (VB single-entry branch).
            only = [m for m in self.minutes_by_date.values() if m > 0]
            if len(only) == 1:
                return max(1, only[0] // 60)
            return 1
        return max(1, round((sum(past) / len(past)) / 60))

    def daily_play_info(self) -> list[dict[str, Any]]:
        """Per-day play rows, most-recent first (VB ``GetDailyPlayInfo`` display list)."""
        rows = []
        for day in sorted(self.minutes_by_date, reverse=True):
            minutes = self.minutes_by_date[day]
            rows.append({"date": day, "minutes": minutes, "label": _format_minutes(minutes)})
        return rows

    def to_json(self) -> dict[str, Any]:
        return {"minutes_by_date": self.minutes_by_date}

    @classmethod
    def from_json(cls, data: Any) -> DailyPlayTime:
        if not isinstance(data, dict):
            return cls()
        raw = data.get("minutes_by_date", {})
        if not isinstance(raw, dict):
            return cls()
        return cls(minutes_by_date={str(k): int(v) for k, v in raw.items()})


def _format_minutes(minutes: int) -> str:
    """A "N hours M mins" label (VB ``GetDailyPlayInfo`` per-day formatting)."""
    if minutes < 1:
        return "None recorded yet"
    hours, mins = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if mins:
        parts.append(f"{mins} min" + ("s" if mins != 1 else ""))
    return " ".join(parts) or "None recorded yet"


def session_minutes(started: datetime, stopped: datetime) -> int:
    """Whole minutes between two timestamps (a finished play session)."""
    return max(0, int((stopped - started).total_seconds() // 60))
