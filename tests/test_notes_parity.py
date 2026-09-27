"""Mod notes, as NIT keeps them (logic audit stage 3i).

NIT renames a mod's notes file with the mod (``ModData.Rename``) and sends
orphaned notes to the recycle bin (``ValidateNotes``). Vaultkeeper did neither:
a renamed mod lost its notes, and Validate Mods then deleted them for good.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Old Name")
    c.save_notes("Old Name", "Remember the password is swordfish.")
    return c


def test_notes_follow_a_renamed_mod(tmp_path: Path) -> None:
    c = _controller(tmp_path)

    assert c.rename_mod("Old Name", "New Name")

    assert c.read_notes("New Name") == "Remember the password is swordfish."
    assert not c.mod_notes_path("Old Name").exists()
    assert c.validate_notes() == 0


def test_bulk_rename_keeps_notes(tmp_path: Path) -> None:
    c = _controller(tmp_path)

    c.apply_mod_renames({"Old Name": "Bulk Name"})

    assert c.read_notes("Bulk Name") == "Remember the password is swordfish."


def test_orphaned_notes_go_to_the_recycle_bin(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)
    c.pd.remove_mod("Old Name")
    (c.ctx.profile_mods_dir / "Old Name").rename(c.ctx.profile_mods_dir / "Gone")

    assert c.validate_notes() == 1

    assert [p.name for p in recycle_bin.rglob("*.rtf")] == ["Old Name.rtf"]


def test_edited_open_notes_follow_a_rename(qtbot, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.ui.main_window import MainWindow

    c = _controller(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    win._tree.select_mod("Old Name")
    win._on_selection_changed()
    win._details.setPlainText("Edited just now.")
    win._details.document().setModified(True)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Name", True))
    monkeypatch.setattr(win, "_confirm_save_notes", lambda mod: True)

    win._on_rename()
    win._save_current_notes()

    assert c.read_notes("New Name") == "Edited just now."
    assert not c.mod_notes_path("Old Name").exists()


def test_deleting_a_mod_recycles_its_notes(tmp_path: Path, recycle_bin: Path) -> None:
    """VB ModData.Remove sends the notes to the recycle bin with the mod."""
    c = _controller(tmp_path)

    c.delete_mods(["Old Name"])

    assert not c.mod_notes_path("Old Name").exists()
    assert [p.name for p in recycle_bin.rglob("Old Name.rtf")] == ["Old Name.rtf"]


def test_orphaned_notes_are_recycled_when_the_profile_opens(tmp_path: Path, recycle_bin) -> None:
    """VB ProfileData.Load runs ValidateNotes on every load."""
    c = _controller(tmp_path)
    orphan = c.mod_notes_path("Long Gone")
    orphan.write_text("{\\rtf1 x}", encoding="utf-8")

    ProfileController.open_profile(
        profile_mods_dir=c.ctx.profile_mods_dir,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )

    assert not orphan.exists()
    assert c.mod_notes_path("Old Name").exists()  # a real mod's notes stay
