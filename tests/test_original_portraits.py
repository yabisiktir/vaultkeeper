"""Show BioWare's Portrait Images (VB MsOriginalPortraits / newtopic73.htm).

CAPABILITY_STATUS recorded this as ported. The menu item was there; nothing was
wired to it — the third time that mistake was made, and the reason
test_capability_status_claims.py now exists.

The game keeps its built-in portraits inside its own data files, where nothing
here can read them, so a character rolled with one shows no picture at all. The
Vault publishes them as a reference archive.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_nothing_is_downloaded_until_it_is_asked_for(controller):
    """~150MB down, ~350MB unpacked: nobody should meet that by accident."""
    assert controller.has_original_portraits() is False
    assert controller.original_portraits_root().exists() is False


def test_the_portraits_become_a_search_folder(controller):
    """Otherwise it is a download nothing reads."""
    root = controller.original_portraits_root()
    assert root not in controller.portrait_search_dirs()

    root.mkdir(parents=True)
    (root / "po_hu_m_01_.tga").write_bytes(b"x")

    dirs = controller.portrait_search_dirs()
    assert root in dirs
    assert dirs[-1] == root, "a mod's replacement for a built-in portrait wins"


def test_a_second_run_does_not_download_again(controller):
    root = controller.original_portraits_root()
    root.mkdir(parents=True)
    (root / "po_hu_m_01_.tga").write_bytes(b"x")

    result = controller.download_original_portraits()
    assert result["ok"] and result["downloaded"] is False
    assert "already here" in result["message"]


def test_a_project_with_no_files_is_reported_not_crashed(controller, monkeypatch):
    monkeypatch.setattr(controller, "scrape_project", lambda url: [])
    result = controller.download_original_portraits()
    assert result["ok"] is False
    assert "no downloadable files" in result["message"]


def test_the_portraits_folder_is_lifted_out_of_the_archive(controller, monkeypatch):
    """The archive wraps them in a `portraits` folder; a repack might not, so
    both shapes have to land in the same place."""
    monkeypatch.setattr(
        controller, "scrape_project", lambda url: [SimpleNamespace(filename="p.zip")]
    )

    def fake_download(self, vsi, dest_dir):
        path = Path(dest_dir) / "p.zip"
        path.write_bytes(b"archive")
        return SimpleNamespace(ok=True, path=path, error="")

    monkeypatch.setattr(
        "vaultkeeper.vault.downloader.Downloader.download_file", fake_download
    )

    def fake_extract(archive, dest):
        inner = Path(dest) / "NWN Portraits" / "portraits"
        inner.mkdir(parents=True)
        (inner / "po_hu_m_01_.tga").write_bytes(b"x")
        (inner / "po_hu_f_01_.tga").write_bytes(b"x")
        return SimpleNamespace(ok=True, dest=dest, error="")

    monkeypatch.setattr(
        controller, "_archive_backend", lambda: SimpleNamespace(extract=fake_extract)
    )

    result = controller.download_original_portraits()

    assert result["ok"] and result["downloaded"] is True
    root = controller.original_portraits_root()
    assert sorted(p.name for p in root.iterdir()) == ["po_hu_f_01_.tga", "po_hu_m_01_.tga"]
    assert "2 portrait image(s)" in result["message"]


def test_a_failed_extract_leaves_nothing_behind(controller, monkeypatch):
    monkeypatch.setattr(
        controller, "scrape_project", lambda url: [SimpleNamespace(filename="p.zip")]
    )
    monkeypatch.setattr(
        "vaultkeeper.vault.downloader.Downloader.download_file",
        lambda self, vsi, dest: SimpleNamespace(
            ok=True, path=Path(dest) / "p.zip", error=""
        ),
    )
    monkeypatch.setattr(
        controller,
        "_archive_backend",
        lambda: SimpleNamespace(
            extract=lambda a, d: SimpleNamespace(ok=False, dest=d, error="corrupt")
        ),
    )
    (controller.data_dir()).mkdir(parents=True, exist_ok=True)

    result = controller.download_original_portraits()
    assert result["ok"] is False and "corrupt" in result["message"]
    assert controller.has_original_portraits() is False


def test_turning_it_off_removes_them(controller):
    root = controller.original_portraits_root()
    root.mkdir(parents=True)
    (root / "po_hu_m_01_.tga").write_bytes(b"x")

    assert controller.remove_original_portraits()["ok"]
    assert controller.has_original_portraits() is False


def test_the_menu_item_is_live(qtbot, controller):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    action = win.nit_menu.action("MsOriginalPortraits")
    assert action.isEnabled(), "it had a menu item and no handler for a long time"
    assert "MsOriginalPortraits" in win.implemented_commands()


def test_declining_the_download_unticks_it(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    called: list[int] = []
    monkeypatch.setattr(
        controller, "download_original_portraits", lambda **k: called.append(1)
    )

    win.nit_menu.action("MsOriginalPortraits").setChecked(True)

    assert called == []
    assert win.nit_menu.action("MsOriginalPortraits").isChecked() is False
