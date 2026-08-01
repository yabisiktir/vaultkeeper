"""NWN client/engine log parsing — faithful port of ``PlayDataManager.ClientLog``.

Parses ``nwclientlog1.txt`` (Diamond) or ``nwenginelog.txt`` (EE) for "Loading
Module:" / "Server Shutting Down" events between a launch's start and end, and
attributes the elapsed time between successive module loads to each module. Module
names in the log are resolved to NIT mod names via GameMapper (injected here as two
callables). Missing-hak-file lines are collected for reporting.

Log entry layout::

    [Thu Nov 02 17:23:10] Loading Module: +Pretty Good Char Creator v43
    [Thu Nov 02 18:34:37] Server Shutting Down
    Couldn't load the Hak Pak File "file.hak"

The EE engine log prefixes timestamps with ``I `` (``I [...]``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from nwnfile.log import get_logger
from vaultkeeper.core.ci_dict import CIStrDict

log = get_logger(__name__)

_TIME_ENTRY_START = "["
_TIME_ENTRY_END = "]"
_LOAD_ENTRY = "Loading Module:"
_CLOSE_ENTRY = "Server Shutting Down"
_COULD_NOT_LOAD_HAK = 'Couldn\'t load the Hak Pak File "'
#: Sessions shorter than this record no execution time (VB: < 5 minutes -> zero).
MIN_EXECUTION_MINUTES = 5
#: The date formats NWN uses inside the brackets (``LogDateFormats``).
_LOG_DATE_FORMATS = ("%a %b %d %H:%M:%S", "%H:%M:%S")
_TIME_ONLY_FORMAT = "%H:%M:%S"


@dataclass
class ClientLogResult:
    """Outcome of parsing one play session's worth of log lines."""

    #: Mod name -> time attributed this session.
    mods_loaded: CIStrDict[timedelta] = field(default_factory=CIStrDict)
    #: Whole-session execution time (zero if under :data:`MIN_EXECUTION_MINUTES`).
    execution_time: timedelta = timedelta(0)
    #: Distinct missing hak-pak file names seen in the log(s).
    missing_hak_files: list[str] = field(default_factory=list)
    #: True if a timestamp failed to parse (VB clears everything and bails).
    date_error: bool = False
    #: Log module names that could not be resolved to a NIT mod name.
    unresolved: list[str] = field(default_factory=list)


def _log_date(entry: str, reference: datetime) -> datetime | None:
    """Parse the timestamp inside the last ``[...]`` of a log line.

    Missing components are backfilled from ``reference`` to mirror .NET's
    ``ParseExact`` (which fills the year — and, for time-only, the whole date —
    from the current date). Returns ``None`` if no format matches.
    """
    start = entry.rfind(_TIME_ENTRY_START)
    end = entry.rfind(_TIME_ENTRY_END)
    if start == -1 or end == -1 or end <= start:
        return None
    date_string = re.sub(r"\s+", " ", entry[start + 1 : end].strip())
    for fmt in _LOG_DATE_FORMATS:
        if fmt == _TIME_ONLY_FORMAT:
            try:
                parsed = datetime.strptime(date_string, fmt)
            except ValueError:
                continue
            return parsed.replace(
                year=reference.year, month=reference.month, day=reference.day
            )
        # NWN logs omit the year; supply the reference year explicitly (.NET fills
        # the current year, and this avoids the day-without-year parsing pitfall).
        try:
            return datetime.strptime(f"{date_string} {reference.year}", f"{fmt} %Y")
        except ValueError:
            continue
    return None


def _extract_hak_name(entry: str) -> str:
    """Pull the hak filename out of a "Couldn't load the Hak Pak File" line."""
    q = entry.rfind('"', 0, len(entry) - 1)
    return entry[q + 1 :].rstrip('"')


def parse_client_log(
    lines: list[str],
    started: datetime,
    stopped: datetime,
    *,
    is_engine_log: bool,
    mods_started: dict[str, datetime],
    save_name_to_mod_name: Callable[[str], str] = lambda s: s,
    log_name_to_mod_name: Callable[[str], str] = lambda s: s,
    process_hak_inline: bool = True,
    engine_lines: list[str] | None = None,
) -> ClientLogResult:
    """Attribute a session's play time to mods (``ClientLog.GetTimes``).

    ``mods_started`` is updated in place with first-seen start dates for modules
    identified by their logged (non-path) name, matching the VB ByRef semantics.
    """
    result = ClientLogResult()
    result.execution_time = stopped - started
    if result.execution_time.total_seconds() < MIN_EXECUTION_MINUTES * 60:
        result.execution_time = timedelta(0)

    # Log timestamps have no sub-second precision.
    close_date = stopped.replace(microsecond=0)

    time_entry = f"I {_TIME_ENTRY_START}" if is_engine_log else _TIME_ENTRY_START

    current_mod = ""
    current_start = datetime.min
    shut_down = False
    for entry in lines:
        # Missing hak files (Diamond keeps them in the same log).
        if process_hak_inline and _COULD_NOT_LOAD_HAK.lower() in entry.lower():
            result.missing_hak_files.append(_extract_hak_name(entry))
            continue
        if not entry.startswith(time_entry):
            continue

        # Server shutting down: close out the current module.
        if entry.rstrip().endswith(_CLOSE_ENTRY):
            shut_down = True
            log_time = _log_date(entry, started)
            if log_time is None:
                result.mods_loaded = CIStrDict()
                result.date_error = True
                return result
            if current_mod in result.mods_loaded:
                result.mods_loaded[current_mod] += log_time - current_start
            else:
                log.debug("Current mod not in mods_loaded: %r", current_mod)
            current_mod = ""
            continue

        load_index = entry.find(_LOAD_ENTRY)
        if load_index == -1:
            continue
        shut_down = False

        entry_date = _log_date(entry, started)
        if entry_date is None:
            result.mods_loaded = CIStrDict()
            result.date_error = True
            return result

        loaded_text = entry[load_index + len(_LOAD_ENTRY) + 1 :].split("\\")
        if len(loaded_text) > 1:
            # A backslash means the log recorded a mod *file* path -> save name.
            module_name = save_name_to_mod_name(loaded_text[-1])
        else:
            module_name = log_name_to_mod_name(loaded_text[-1])
            if module_name not in mods_started:
                mods_started[module_name] = entry_date

        if module_name == "":
            result.unresolved.append(loaded_text[-1])
            log.info("Can't find module name from %s", loaded_text[-1])
            continue

        # Accumulate the previous module's elapsed span onto the right key.
        if module_name not in result.mods_loaded:
            result.mods_loaded[module_name] = timedelta(0)
            if current_mod != "" and current_mod != module_name:
                result.mods_loaded[current_mod] += entry_date - current_start
        elif module_name == current_mod:
            result.mods_loaded[module_name] += entry_date - current_start
        elif current_mod != "" and current_mod in result.mods_loaded:
            result.mods_loaded[current_mod] += entry_date - current_start

        current_mod = module_name
        current_start = entry_date

    # Abnormal termination (no shutdown line): close the last module at stop time.
    if not shut_down and result.mods_loaded and current_mod in result.mods_loaded:
        result.mods_loaded[current_mod] += close_date - current_start

    # EE reads missing-hak entries from the separate engine log.
    if not process_hak_inline and engine_lines is not None:
        for entry in engine_lines:
            if _COULD_NOT_LOAD_HAK.lower() in entry.lower():
                result.missing_hak_files.append(_extract_hak_name(entry))

    result.missing_hak_files = list(dict.fromkeys(result.missing_hak_files))
    return result
