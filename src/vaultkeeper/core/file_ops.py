"""Headless batch copy/delete worker — the LazWorks FileOperations analogue.

The VB install engine drives file copies/deletes through ``FileOperations`` (a
progress dialog wrapping a background worker) and reads per-item results back. In
Vaultkeeper the *engine* logic is UI-free, so this provides the same per-item
result surface without any dialog. A Qt progress adapter is layered on top in the
UI phase; the engine only sees this interface, so it stays testable against real
temp files (or a fake).

Copies stamp the target with a caller-provided CRC (the source file's known CRC),
matching how the VB engine records installed-file checksums without recomputing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core import fs
from vaultkeeper.core.file_key import FileKeyInfo


@dataclass(frozen=True)
class CopyItem:
    """One planned copy: source -> target, tagged with its file key and CRC."""

    source: Path
    target: Path
    key: FileKeyInfo
    crc: int


@dataclass(frozen=True)
class DeleteItem:
    """One planned delete, tagged with its file key."""

    path: Path
    key: FileKeyInfo


@dataclass(frozen=True)
class OpResult:
    """Outcome of a single copy or delete."""

    key: FileKeyInfo
    success: bool
    message: str = ""
    crc: int = 0


class FileOps:
    """Performs batch copies/deletes against the real filesystem, headlessly."""

    def copy(self, items: list[CopyItem]) -> list[OpResult]:
        results: list[OpResult] = []
        for item in items:
            try:
                fs.copy_file(item.source, item.target, overwrite=True)
                results.append(OpResult(item.key, True, crc=item.crc))
            except OSError as exc:
                results.append(OpResult(item.key, False, message=str(exc)))
        return results

    def delete(self, items: list[DeleteItem], *, to_trash: bool = False) -> list[OpResult]:
        results: list[OpResult] = []
        for item in items:
            try:
                fs.delete(item.path, to_trash=to_trash, missing_ok=True)
                results.append(OpResult(item.key, True))
            except OSError as exc:
                results.append(OpResult(item.key, False, message=str(exc)))
        return results
