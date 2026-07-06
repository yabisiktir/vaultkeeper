"""Tests for NWN client/engine log parsing (time attribution)."""

from __future__ import annotations

from datetime import datetime, timedelta

from vaultkeeper.game.client_log import parse_client_log


def _dt(h, m, s=0):
    return datetime(2020, 11, 2, h, m, s)


class TestBasicAttribution:
    def test_two_mods_with_shutdown(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: Mod A",
            "[Mon Nov 02 17:30:00] Loading Module: Mod B",
            "[Mon Nov 02 18:00:00] Server Shutting Down",
        ]
        mods_started: dict[str, datetime] = {}
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 1),
            is_engine_log=False, mods_started=mods_started,
        )
        assert not res.date_error
        assert res.mods_loaded["Mod A"] == timedelta(minutes=30)
        assert res.mods_loaded["Mod B"] == timedelta(minutes=30)

    def test_abnormal_termination_uses_stop_time(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: Mod A",
            "[Mon Nov 02 17:30:00] Loading Module: Mod B",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
        )
        # No shutdown line: Mod B is closed at the stop time (18:00).
        assert res.mods_loaded["Mod A"] == timedelta(minutes=30)
        assert res.mods_loaded["Mod B"] == timedelta(minutes=30)

    def test_records_start_date_for_logged_names(self):
        lines = ["[Mon Nov 02 17:00:00] Loading Module: Mod A"]
        mods_started: dict[str, datetime] = {}
        parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started=mods_started,
        )
        assert mods_started["Mod A"] == _dt(17, 0)


class TestResolution:
    def test_backslash_path_uses_save_name_resolver(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: SomeProfile\\folder\\adv.mod",
            "[Mon Nov 02 17:20:00] Server Shutting Down",
        ]
        mods_started: dict[str, datetime] = {}
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started=mods_started,
            save_name_to_mod_name=lambda s: {"adv.mod": "My Adventure"}.get(s, ""),
        )
        assert "My Adventure" in res.mods_loaded
        # Path-style entries do NOT record a start date.
        assert mods_started == {}

    def test_logged_name_uses_log_resolver(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: rawname",
            "[Mon Nov 02 17:20:00] Server Shutting Down",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
            log_name_to_mod_name=lambda s: "Resolved Mod",
        )
        assert "Resolved Mod" in res.mods_loaded

    def test_unresolved_name_is_skipped(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: mystery",
            "[Mon Nov 02 17:20:00] Server Shutting Down",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
            log_name_to_mod_name=lambda s: "",
        )
        assert res.unresolved == ["mystery"]
        assert len(res.mods_loaded) == 0


class TestExecutionTime:
    def test_short_session_zero_execution(self):
        res = parse_client_log(
            [], _dt(17, 0), _dt(17, 3), is_engine_log=False, mods_started={}
        )
        assert res.execution_time == timedelta(0)

    def test_long_session_records_execution(self):
        res = parse_client_log(
            [], _dt(17, 0), _dt(18, 0), is_engine_log=False, mods_started={}
        )
        assert res.execution_time == timedelta(hours=1)


class TestEngineLogAndHaks:
    def test_engine_log_prefix(self):
        lines = [
            "I [Mon Nov 02 17:00:00] Loading Module: Mod A",
            "I [Mon Nov 02 17:20:00] Server Shutting Down",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=True, mods_started={},
        )
        assert "Mod A" in res.mods_loaded

    def test_missing_hak_inline(self):
        lines = [
            'Couldn\'t load the Hak Pak File "cep2_add_ci.hak"',
            'Couldn\'t load the Hak Pak File "cep2_add_ci.hak"',  # dup
            "[Mon Nov 02 17:00:00] Loading Module: Mod A",
            "[Mon Nov 02 17:20:00] Server Shutting Down",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
        )
        assert res.missing_hak_files == ["cep2_add_ci.hak"]

    def test_missing_hak_from_engine_lines(self):
        res = parse_client_log(
            ["[Mon Nov 02 17:00:00] Loading Module: Mod A",
             "[Mon Nov 02 17:20:00] Server Shutting Down"],
            _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
            process_hak_inline=False,
            engine_lines=['Couldn\'t load the Hak Pak File "extra.hak"'],
        )
        assert res.missing_hak_files == ["extra.hak"]


class TestDateFailure:
    def test_unparseable_timestamp_clears(self):
        lines = [
            "[Mon Nov 02 17:00:00] Loading Module: Mod A",
            "[garbled timestamp] Server Shutting Down",
        ]
        res = parse_client_log(
            lines, _dt(16, 59), _dt(18, 0),
            is_engine_log=False, mods_started={},
        )
        assert res.date_error
        assert len(res.mods_loaded) == 0
