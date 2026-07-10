"""Filesystem helpers — a small, safe wrapper around copy/move/delete.

Replaces the VB app's ``LazWorks IOSystem.FS`` and (partially) ``FileOperations``:
validated primitives with an optional **recycle-bin** delete (cross-platform via
``send2trash``) versus permanent delete — a distinction the original preserves
(e.g. uninstall deletes are permanent, user deletes are recycle-aware).

This module is deliberately UI-free and synchronous; the progress-driven batch
copy/CRC worker (the ``FileOperations`` analogue) is built on top of it in a
later phase. Nothing here touches game config files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class FsError(OSError):
    """Raised for filesystem operations that fail in a way worth surfacing."""


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if absent; return it. Idempotent."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def copy_file(src: str | Path, dst: str | Path, *, overwrite: bool = True) -> Path:
    """Copy a file, creating the destination directory. Preserves mtime.

    With ``overwrite=False`` an existing destination raises :class:`FsError`.
    """
    src_p, dst_p = Path(src), Path(dst)
    if dst_p.exists() and not overwrite:
        raise FsError(f"destination exists: {dst_p}")
    ensure_dir(dst_p.parent)
    shutil.copy2(src_p, dst_p)
    return dst_p


def move_file(src: str | Path, dst: str | Path, *, overwrite: bool = True) -> Path:
    """Move/rename a file, creating the destination directory."""
    src_p, dst_p = Path(src), Path(dst)
    ensure_dir(dst_p.parent)
    if dst_p.exists():
        if not overwrite:
            raise FsError(f"destination exists: {dst_p}")
        dst_p.unlink()
    shutil.move(os.fspath(src_p), os.fspath(dst_p))
    return dst_p


def move_dir(src: str | Path, dst: str | Path, *, overwrite: bool = False) -> Path:
    """Move a directory tree (VB ``FS.MoveDir``).

    ``overwrite=False`` (VB ``IOAction.Fail``) raises :class:`FsError` if ``dst``
    already exists; ``overwrite=True`` (VB ``IOAction.Overwrite``) merges ``src`` into
    an existing ``dst``, replacing matching files, and removes the emptied ``src``.
    """
    src_p, dst_p = Path(src), Path(dst)
    if dst_p.exists():
        if not overwrite:
            raise FsError(f"destination exists: {dst_p}")
        for child in src_p.iterdir():
            target = dst_p / child.name
            if child.is_dir() and not child.is_symlink():
                move_dir(child, target, overwrite=True)
            else:
                move_file(child, target, overwrite=True)
        src_p.rmdir()
        return dst_p
    ensure_dir(dst_p.parent)
    shutil.move(os.fspath(src_p), os.fspath(dst_p))
    return dst_p


def delete(path: str | Path, *, to_trash: bool = False, missing_ok: bool = True) -> None:
    """Delete a file or directory tree.

    ``to_trash=True`` sends it to the OS recycle bin/trash (``send2trash``);
    otherwise it is removed permanently. ``missing_ok`` swallows a missing path.
    """
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        if missing_ok:
            return
        raise FsError(f"path not found: {p}")

    if to_trash:
        try:
            from send2trash import send2trash  # imported lazily; optional at import time
        except ImportError as exc:  # pragma: no cover - dependency guaranteed in prod
            raise FsError("send2trash is required for recycle-bin deletes") from exc
        send2trash(os.fspath(p))
        return

    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        p.unlink()
