"""Atomic JSON read/write — the substrate for Vaultkeeper's native store.

Replaces the VB app's BinaryFormatter persistence with a plain, inspectable JSON
format (per the hybrid data strategy: native format going forward; a read-only
importer for legacy stores lands later). Writes are atomic (temp file + rename)
so an interrupted save never corrupts an existing file — the VB app went to some
length to survive sharing violations mid-save; atomic replace gives us the same
safety more simply.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StoreError(OSError):
    """Raised when a store file exists but cannot be read/parsed."""


def read_json(path: str | Path, *, default: Any = None) -> Any:
    """Read and parse a JSON file. Returns ``default`` if the file is absent.

    Raises :class:`StoreError` if the file exists but is unreadable/invalid — a
    corrupt store must be surfaced (and, for profile data, triggers a
    rebuild-from-disk), never silently treated as empty.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except OSError as exc:
        raise StoreError(f"cannot read {p}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise StoreError(f"invalid JSON in {p}: {exc}") from exc


def write_json(path: str | Path, data: Any, *, indent: int = 2) -> Path:
    """Atomically write ``data`` as JSON to ``path`` (creating parent dirs).

    The write goes to a temp file in the same directory and is then renamed over
    the target, so readers never observe a half-written file. ``os.replace`` is
    atomic on the same filesystem across Windows/macOS/Linux.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=True)

    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, p)
    except BaseException:
        # Clean up the temp file on any failure (including interrupts).
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return p
