"""Persistent "how many times have we shown this" tracker.

Ports the VB app's ``MessageHistory``/``MessageId`` display-count mechanism used
for "don't show again" dialogs and throttled diagnostics (e.g. the anneal
null-conflict diagnostic is shown only a couple of times). Keys are stable string
ids; the counts persist as a small JSON file so the throttling survives restarts.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.app_paths import config_root
from vaultkeeper.persistence.json_store import read_json, write_json


def _default_path() -> Path:
    return config_root() / "message_history.json"


class MessageHistory:
    """Tracks per-message display counts with optional persistence.

    Typical use::

        if history.should_display("anneal.null_conflict", max_times=2):
            show_warning(...)
            history.record("anneal.null_conflict")
    """

    def __init__(self, path: Path | None = None, *, autosave: bool = True) -> None:
        self._path = path or _default_path()
        self._autosave = autosave
        raw = read_json(self._path, default={}) or {}
        # Coerce to a clean dict[str, int].
        self._counts: dict[str, int] = {
            str(k): int(v) for k, v in raw.items() if isinstance(v, (int, float))
        }

    def count(self, key: str) -> int:
        return self._counts.get(key, 0)

    def should_display(self, key: str, max_times: int = 1) -> bool:
        """True if ``key`` has been shown fewer than ``max_times`` times."""
        return self.count(key) < max_times

    def record(self, key: str) -> int:
        """Increment and (optionally) persist the count for ``key``; return it."""
        new = self.count(key) + 1
        self._counts[key] = new
        if self._autosave:
            self.save()
        return new

    def reset(self, key: str | None = None) -> None:
        """Reset one key (or all, when ``key`` is None) — e.g. "show these again"."""
        if key is None:
            self._counts.clear()
        else:
            self._counts.pop(key, None)
        if self._autosave:
            self.save()

    def save(self) -> None:
        write_json(self._path, self._counts)
