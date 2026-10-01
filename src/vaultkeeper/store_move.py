"""Move the store to another folder (VB ``MoveNitStore``, Settings › Locations).

NIT records the new location (``PathNewStore``) and moves the store the next
time it starts, before anything reads it. Vaultkeeper does the same, but more
carefully, because this is every mod, database and archived save the user has:

1. copy the store into ``<chosen folder>/Vaultkeeper Store`` under a temporary
   name, and check every file arrived with its size;
2. rewrite the absolute paths that point into the old store (settings, and the
   store's own JSON files such as ``GameMapData.json``), as NIT rewrites its
   selection files;
3. give the copy its real name; the caller then saves ``store_root`` pointing
   at it (:func:`move_store` returns here);
4. only once that is saved, send the old store to the recycle bin
   (:func:`recycle_old_store`).

Any failure before step 3 leaves the old store in use and untouched; the
partial copy goes to the recycle bin.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

#: The folder created inside the chosen location (NIT appends ``Paths.C.Tool``).
STORE_FOLDER = "Vaultkeeper Store"


@dataclass
class MoveResult:
    ok: bool
    message: str
    #: The store in use afterwards.
    store: Path | None = None


def target_for(chosen: str | Path) -> Path:
    """Where the store goes for a chosen folder."""
    chosen = Path(chosen)
    return chosen if chosen.name == STORE_FOLDER else chosen / STORE_FOLDER


def check_target(source: Path, chosen: str | Path) -> str:
    """Why the store cannot move to ``chosen``, or ``""`` if it can."""
    target = target_for(chosen).resolve()
    source = Path(source).resolve()
    if target == source:
        return "That is where the store already is."
    if source in target.parents or target in source.parents:
        return "The new location cannot be inside the store, or the store inside it."
    if target.exists() and any(target.iterdir()):
        return f"{target} already exists and is not empty."
    return ""


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]


def _rewrite_text(text: str, old: PurePath, new: PurePath) -> str:
    """Replace JSON-encoded paths that start with ``old`` by the same under ``new``.

    Both spellings are matched: Windows paths are saved with backslashes by
    Python but with forward slashes by Qt's file dialogs.
    """
    spellings = {(str(old), str(new)), (old.as_posix(), new.as_posix())}
    for old_text, new_text in spellings:
        old_enc = json.dumps(old_text)[1:-1]
        new_enc = json.dumps(new_text)[1:-1]
        # Only whole path prefixes: at the start of a JSON string, and followed
        # by a separator or the end of the string.
        pattern = r'(?<=")' + re.escape(old_enc) + r'(?=["/]|\\\\)'
        text = re.sub(pattern, lambda _m, enc=new_enc: enc, text)
    return text


def rewrite_paths(root: Path, old: PurePath, new: PurePath) -> int:
    """Rewrite paths into the old store in every JSON file under ``root``."""
    changed = 0
    for path in root.rglob("*.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = _rewrite_text(text, old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def rewrite_settings_paths(data: dict, old: PurePath, new: PurePath) -> dict:
    """``data`` (settings as a dict) with paths into the old store moved to ``new``."""
    return json.loads(_rewrite_text(json.dumps(data), old, new))


def move_store(
    source: Path,
    chosen: str | Path,
    *,
    recycle: Callable[[str], None],
    on_progress: Callable[[int, int], bool] = lambda _done, _total: True,
) -> MoveResult:
    """Copy and verify the store into its new place; the old one is untouched.

    ``on_progress(done, total)`` is called per file; returning False cancels.
    When ``ok``, the caller saves ``store_root`` (rewriting settings paths with
    :func:`rewrite_settings_paths`) and then calls :func:`recycle_old_store`.
    """
    source = Path(source)
    reason = check_target(source, chosen)
    if reason:
        return MoveResult(False, reason, store=source)
    if not source.is_dir():
        return MoveResult(False, f"The store {source} was not found.", store=source)
    target = target_for(chosen)
    staging = target.with_name(target.name + ".moving")
    files = _files(source)
    total = len(files)
    try:
        if staging.exists():
            recycle(str(staging))  # left by an earlier attempt that did not finish
        staging.mkdir(parents=True)
        for done, path in enumerate(files, 1):
            dest = staging / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            if not on_progress(done, total):
                raise InterruptedError("cancelled")
        # Empty folders count too: an empty Profiles folder is still a profile.
        for folder in (p for p in source.rglob("*") if p.is_dir()):
            (staging / folder.relative_to(source)).mkdir(parents=True, exist_ok=True)
        missing = [
            p for p in files
            if not (staging / p.relative_to(source)).is_file()
            or (staging / p.relative_to(source)).stat().st_size != p.stat().st_size
        ]
        if missing:
            raise OSError(f"{len(missing)} file(s) did not copy correctly")
        rewrite_paths(staging, source, target)
        if target.exists():
            target.rmdir()  # checked empty above
        os.replace(staging, target)
    except InterruptedError:
        _discard(staging, recycle)
        return MoveResult(False, "Moving the store was cancelled; nothing changed.", store=source)
    except OSError as exc:
        _discard(staging, recycle)
        return MoveResult(
            False, f"The store could not be moved ({exc}); it stays where it was.", store=source
        )

    return MoveResult(True, f"Moved the store to {target}.", store=target)


def recycle_old_store(source: Path, recycle: Callable[[str], None]) -> str:
    """Send the old store to the recycle bin; a sentence saying what happened."""
    try:
        recycle(str(source))
    except Exception:  # noqa: BLE001 - the move succeeded; report, do not fail it
        return f"The old store could not be sent to the recycle bin; it is still at {source}."
    return "The old store is in the recycle bin."


def _discard(staging: Path, recycle: Callable[[str], None]) -> None:
    if staging.exists():
        # The copy is ours and the old store is intact: a failed clean-up is not fatal.
        with contextlib.suppress(Exception):
            recycle(str(staging))
