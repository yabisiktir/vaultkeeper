"""Tests for the Steam Workshop contents diff (VB SteamWorkshop.ValidateSteamContent)."""

from __future__ import annotations

import time
from pathlib import Path

_REAL_WS = Path(
    "/Users/example/Library/Application Support/Steam/steamapps/workshop/content/704450"
)


def _item(content: Path, id_: str, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = content / id_ / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def test_diff_first_run_all_added(tmp_path):
    from vaultkeeper.game.workshop import diff_workshop

    content = tmp_path / "704450"
    _item(content, "111", {"override/a.tga": b"x", "override/b.mdl": b"yy"})
    _item(content, "222", {"override/c.tga": b"z"})

    diff = diff_workshop(content, {})
    assert sorted(diff.added) == ["111", "222"]
    assert diff.added_files == 3
    assert not diff.updated and not diff.unsubscribed
    assert set(diff.contents) == {"111", "222"}
    assert "Added: 2" in diff.summary


def test_diff_detects_update_remove_unsubscribe(tmp_path):
    from vaultkeeper.game.workshop import contents_from_json, contents_to_json, diff_workshop

    content = tmp_path / "704450"
    _item(content, "111", {"override/a.tga": b"x", "override/b.mdl": b"yy"})
    _item(content, "222", {"override/c.tga": b"z"})
    stored = contents_from_json(contents_to_json(diff_workshop(content, {}).contents))

    # Change 111's a.tga (size differs), delete 222's whole folder.
    time.sleep(0.01)
    (content / "111" / "override" / "a.tga").write_bytes(b"xxxxx")
    import shutil

    shutil.rmtree(content / "222")

    diff = diff_workshop(content, stored)
    assert diff.updated == ["111"]  # 111 changed
    assert diff.unsubscribed == ["222"]
    assert diff.updated_files == 1
    assert "222" not in diff.contents


def test_resolve_mod_name_from_module(tmp_path):
    from vaultkeeper.game.workshop import resolve_mod_name

    folder = tmp_path / "333"
    (folder / "modules").mkdir(parents=True)
    (folder / "modules" / "Cool Adventure.mod").write_bytes(b"m")
    assert resolve_mod_name(folder, "333") == "Cool Adventure"
    # No module → "Mod <id>".
    assert resolve_mod_name(tmp_path / "444", "444") == "Mod 444"


import pytest  # noqa: E402


@pytest.mark.skipif(not _REAL_WS.is_dir(), reason="No real Steam Workshop content")
def test_diff_real_workshop_folder_stable():
    from vaultkeeper.game.workshop import contents_from_json, contents_to_json, diff_workshop

    first = diff_workshop(_REAL_WS, {})
    assert len(first.added) >= 10  # the real folder has ~15 subscriptions
    assert first.added_files > 1000
    # Persisting then re-diffing yields no changes (stable).
    stored = contents_from_json(contents_to_json(first.contents))
    second = diff_workshop(_REAL_WS, stored)
    assert not second.added and not second.updated and not second.unsubscribed
