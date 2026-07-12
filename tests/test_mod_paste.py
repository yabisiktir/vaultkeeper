"""Tests for the mods-pane clipboard paste (VB NIT.Paste.vb ModPaste)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _external_mod(root: Path, name: str) -> Path:
    """A mod-shaped folder outside the profile (payload under .Mod Installer)."""
    src = root / "external" / name
    payload = src / C.MOD_INSTALLER_DIR / "hak" / "x.hak"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"HAK")
    return src


def test_paste_directory_creates_mod(tmp_path):
    controller = _controller(tmp_path)
    src = _external_mod(tmp_path, "Imported Mod")

    result = controller.paste_mod_sources([src], group="100. Packs")
    assert result["created"] == ["Imported Mod"]
    md = controller.pd.mod_item("Imported Mod")
    assert md is not None and md.group == "100. Packs"
    # The folder was copied into the profile and its files scanned.
    assert (controller.ctx.profile_mods_dir / "Imported Mod" / C.MOD_INSTALLER_DIR
            / "hak" / "x.hak").is_file()
    assert any(fk.filename == "x.hak" for fk in md.files)


def test_paste_existing_name_is_ignored(tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("Imported Mod")
    src = _external_mod(tmp_path, "Imported Mod")

    result = controller.paste_mod_sources([src])
    # VB ModPaste skips a source whose mod name already exists (no-op).
    assert result["ignored"] == ["Imported Mod"]
    assert not result["created"]


def test_paste_archive_delegates_to_add_mods(tmp_path):
    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(
        contents={"cool.zip": {"override/o.2da": b"O"}}
    )
    archive = tmp_path / "cool.zip"
    archive.write_bytes(b"")  # must exist on disk to be seen as a file source

    result = controller.paste_mod_sources([archive], group="100. Packs")
    assert result["created"] == ["cool"]
    assert (controller.ctx.profile_mods_dir / "cool" / "override" / "o.2da").is_file()


def test_paste_non_extractable_file_errors(tmp_path):
    controller = _controller(tmp_path)
    junk = tmp_path / "notes.txt"
    junk.write_text("hi")
    result = controller.paste_mod_sources([junk])
    assert result["errors"] == ["notes.txt"]
    assert not result["created"]


def test_paste_mixed_dir_and_archive(tmp_path):
    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(
        contents={"pack.7z": {"hak/p.hak": b"P"}}
    )
    src_dir = _external_mod(tmp_path, "Folder Mod")
    archive = tmp_path / "pack.7z"
    archive.write_bytes(b"")

    result = controller.paste_mod_sources([src_dir, archive])
    assert set(result["created"]) == {"Folder Mod", "pack"}


# -- UI: copy selected mods to the system clipboard ------------------------- #
def test_copy_puts_mod_folders_on_clipboard(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    controller.create_mod("Alpha")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._on_mods_copy()

    mime = QApplication.clipboard().mimeData()
    assert mime.hasUrls()
    local = [u.toLocalFile() for u in mime.urls()]
    assert str(controller.ctx.profile_mods_dir / "Alpha") in local
