"""Tests for Move Compressed Files to Mod's Downloads Folder (VB UpdateDownloads)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_mod("My Mod")
    return controller


def test_moves_archives_and_exe_leaves_other_files(tmp_path):
    controller = _controller(tmp_path)
    mod_folder = tmp_path / "Profiles" / "P" / "My Mod"
    # Loose files dropped in the mod folder root.
    (mod_folder / "pack.zip").write_bytes(b"ZIP")
    (mod_folder / "extra.7z").write_bytes(b"7Z")
    (mod_folder / "setup.exe").write_bytes(b"EXE")  # recognised, movable
    (mod_folder / "readme.txt").write_bytes(b"hello")  # not an archive -> stays

    result = controller.update_downloads(["My Mod"])
    assert result == {"mods": 1, "files": 3, "errors": 0}

    downloads = mod_folder / C.DOWNLOADS_DIR
    assert (downloads / "pack.zip").is_file()
    assert (downloads / "extra.7z").is_file()
    assert (downloads / "setup.exe").is_file()
    # Non-archive stays put; archives no longer at the root.
    assert (mod_folder / "readme.txt").is_file()
    assert not (mod_folder / "pack.zip").exists()


def test_creates_downloads_folder_even_with_no_archives(tmp_path):
    controller = _controller(tmp_path)
    mod_folder = tmp_path / "Profiles" / "P" / "My Mod"
    (mod_folder / "notes.txt").write_bytes(b"x")

    result = controller.update_downloads(["My Mod"])
    assert result == {"mods": 1, "files": 0, "errors": 0}
    assert (mod_folder / C.DOWNLOADS_DIR).is_dir()


def test_does_not_touch_installer_subfolder(tmp_path):
    controller = _controller(tmp_path)
    mod_folder = tmp_path / "Profiles" / "P" / "My Mod"
    # An archive nested inside .Mod Installer must NOT be moved (non-recursive).
    nested = mod_folder / C.MOD_INSTALLER_DIR / "hak"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "buried.zip").write_bytes(b"ZIP")

    result = controller.update_downloads(["My Mod"])
    assert result["files"] == 0
    assert (nested / "buried.zip").is_file()  # untouched


def test_group_and_unknown_mods_skipped(tmp_path):
    controller = _controller(tmp_path)
    result = controller.update_downloads(["Ghost Mod"])
    assert result == {"mods": 0, "files": 0, "errors": 0}


def test_database_is_untouched(tmp_path):
    controller = _controller(tmp_path)
    mod_folder = tmp_path / "Profiles" / "P" / "My Mod"
    (mod_folder / "pack.zip").write_bytes(b"ZIP")
    before = list(controller.pd.mod_item("My Mod").files)
    controller.update_downloads(["My Mod"])
    # Loose downloads are not tracked installer files.
    assert list(controller.pd.mod_item("My Mod").files) == before


def test_compress_mod_folder_reports_unavailable_off_windows(tmp_path):
    """On macOS/Linux, NTFS folder compression is honestly reported unavailable."""
    import sys

    controller = _controller(tmp_path)
    result = controller.compress_mod_folders(["My Mod"])
    if sys.platform.startswith("win"):
        assert result["available"] is True
    else:
        assert result["available"] is False
        assert result["applied"] == 0
        assert "windows" in result["message"].lower()


def test_publish_mod_uses_archive_seam_with_excludes(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor()
    dest = tmp_path / "out"
    result = controller.publish_mod("My Mod", dest)

    assert result["ok"]
    assert result["path"].endswith("My Mod.7z")
    # The private folders/files are excluded (VB PublishMod -x! list).
    assert controller._extractor.last_exclude == [
        ".Game Play Time.rtf",
        "_Downloads",
        "_History",
        "_Published",
    ]
    assert controller._extractor.create_calls[0][0] == dest / "My Mod.7z"


def test_publish_unknown_mod(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor()
    result = controller.publish_mod("Ghost", tmp_path / "out")
    assert not result["ok"]


def test_publish_reports_when_backend_unavailable(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(available=False)
    result = controller.publish_mod("My Mod", tmp_path / "out")
    assert not result["ok"]
    assert "not available" in result["message"].lower()
