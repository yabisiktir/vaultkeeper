"""Tests for play-time records and LazWorks formatting helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from vaultkeeper.core.formatting import (
    parse_date_string,
    to_date_string,
    to_int,
    to_plural,
)
from vaultkeeper.core.play_time import (
    PlayData,
    PlayTimeInfo,
    distinct_play_times,
    sort_play_times,
)


class TestFormatting:
    def test_to_int_numeric(self):
        assert to_int("150") == 150
        assert to_int("  16 ") == 16

    def test_to_int_non_numeric_is_minus_one(self):
        # LazWorks ToInteger returns -1, not 0, for non-numeric input.
        assert to_int("abc") == -1
        assert to_int("") == -1

    def test_to_date_string_round_trip(self):
        dt = datetime(2017, 2, 23)
        assert to_date_string(dt) == "23 Feb 2017"
        assert parse_date_string("23 Feb 2017") == dt

    def test_parse_date_string_invalid(self):
        assert parse_date_string("not a date") is None

    def test_to_plural_singular_and_plural(self):
        assert to_plural(1, "hour") == "1 hour"
        assert to_plural(2, "hour") == "2 hours"

    def test_to_plural_day_is_special_cased(self):
        # "day" must NOT become "daies" despite ending in y.
        assert to_plural(3, "day") == "3 days"

    def test_to_plural_y_becomes_ies(self):
        assert to_plural(2, "century") == "2 centuries"

    def test_to_plural_thousands_separator(self):
        assert to_plural(1500, "hour") == "1,500 hours"


class TestPlayTimeInfo:
    def test_parses_hours_and_minutes(self):
        pti = PlayTimeInfo("23 Feb 2017", "150 hours 16 mins", "Louis")
        assert pti.play_time_span == timedelta(hours=150, minutes=16)

    def test_parses_hours_only(self):
        pti = PlayTimeInfo("23 Feb 2017", "2 hours", "Louis")
        assert pti.play_time_span == timedelta(hours=2)

    def test_parses_minutes_only(self):
        pti = PlayTimeInfo("23 Feb 2017", "16 mins", "Louis")
        assert pti.play_time_span == timedelta(minutes=16)

    def test_explicit_span_not_overwritten(self):
        span = timedelta(hours=5)
        pti = PlayTimeInfo("23 Feb 2017", "150 hours 16 mins", "Louis", span)
        assert pti.play_time_span == span

    def test_str_is_csv(self):
        pti = PlayTimeInfo("23 Feb 2017", "2 hours", "Louis")
        assert str(pti) == "23 Feb 2017,2 hours,Louis"

    def test_equality_case_insensitive(self):
        a = PlayTimeInfo("23 Feb 2017", "2 hours", "louis")
        b = PlayTimeInfo("23 Feb 2017", "2 hours", "Louis")
        assert a == b
        assert hash(a) == hash(b)

    def test_clone_is_independent(self):
        a = PlayTimeInfo("23 Feb 2017", "2 hours", "Louis")
        b = a.clone()
        b.user_name = "Vivienne"
        assert a.user_name == "Louis"


class TestSorting:
    def test_sort_descending_by_date(self):
        items = [
            PlayTimeInfo("01 Jan 2017", "1 hour", "Louis"),
            PlayTimeInfo("05 Mar 2019", "2 hours", "Louis"),
            PlayTimeInfo("10 Feb 2018", "3 hours", "Louis"),
        ]
        sort_play_times(items)
        assert [p.completed for p in items] == [
            "05 Mar 2019",
            "10 Feb 2018",
            "01 Jan 2017",
        ]

    def test_distinct_preserves_order(self):
        items = [
            PlayTimeInfo("01 Jan 2017", "1 hour", "Louis"),
            PlayTimeInfo("01 Jan 2017", "1 hour", "louis"),  # dup (case-insensitive)
            PlayTimeInfo("02 Jan 2017", "1 hour", "Louis"),
        ]
        result = distinct_play_times(items)
        assert len(result) == 2
        assert result[0].completed == "01 Jan 2017"
        assert result[1].completed == "02 Jan 2017"


class TestPlayData:
    def test_defaults(self):
        pd = PlayData()
        assert pd.total_played == timedelta(0)
        assert pd.total_today == timedelta(0)
        assert pd.most_in_one_day == timedelta(0)
        assert pd.last_played == to_date_string(datetime.now())
        assert len(pd.play_times) == 0

    def test_play_times_case_insensitive(self):
        pd = PlayData()
        pd.play_times["My Mod"] = timedelta(hours=3)
        assert pd.play_times["my mod"] == timedelta(hours=3)
