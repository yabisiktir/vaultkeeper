"""Case-insensitive string-keyed dictionary.

The VB app builds ``ModList``, ``OriginalFiles`` etc. with
``StringComparer.CurrentCultureIgnoreCase``, so mod-name and file-key lookups are
case-insensitive. Python dicts are case-sensitive, and on case-sensitive
filesystems (APFS) we cannot rely on consistent casing, so we need an explicit
case-insensitive map. The first-seen key casing is preserved for iteration.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import TypeVar

_V = TypeVar("_V")


class CIStrDict(MutableMapping[str, _V]):
    """A dict with case-insensitive string keys (preserving original casing)."""

    def __init__(self, data: MutableMapping[str, _V] | None = None) -> None:
        # lower-cased key -> (original key, value)
        self._store: dict[str, tuple[str, _V]] = {}
        if data:
            for k, v in data.items():
                self[k] = v

    def __getitem__(self, key: str) -> _V:
        return self._store[key.lower()][1]

    def __setitem__(self, key: str, value: _V) -> None:
        low = key.lower()
        # Preserve the original casing already stored, if any (matches dict update).
        orig = self._store[low][0] if low in self._store else key
        self._store[low] = (orig, value)

    def __delitem__(self, key: str) -> None:
        del self._store[key.lower()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._store

    def __iter__(self) -> Iterator[str]:
        return (orig for orig, _ in self._store.values())

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"CIStrDict({dict(self.items())!r})"
