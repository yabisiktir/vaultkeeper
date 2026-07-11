"""Tests for the controller vault ops + DownloadProject dialog (offline)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
from vaultkeeper.vault.scraper_info import VaultScraperInfo

_PROJECT_HTML = (
    "<h1>My Project</h1>\n"
    '<span class="file-icon"></span><a href="http://cdn/a.zip" length=100>a.zip</a>\n'
    '<span class="file-icon"></span><a href="http://cdn/b.hak" length=200>b.hak</a>\n'
)


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    installer = profile_mods / "My Mod" / C.MOD_INSTALLER_DIR / "hak"
    installer.mkdir(parents=True)
    (installer / "x.hak").write_bytes(b"x")
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_controller_scrape_project(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://vault/project/my-project": HttpResponse(
            "http://vault/project/my-project", 200, text=_PROJECT_HTML
        )}
    )
    files = controller.scrape_project("http://vault/project/my-project")
    assert [f.description for f in files] == ["a.zip", "b.hak"]


def test_controller_download_project(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {
            "http://cdn/a.zip": HttpResponse("http://cdn/a.zip", 200, content=b"AAAA"),
            "http://cdn/b.hak": HttpResponse("http://cdn/b.hak", 200, content=b"BB"),
        }
    )
    files = [
        VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip"),
        VaultScraperInfo(direct_url="http://cdn/b.hak", filename="b.hak"),
    ]
    results = controller.download_project(files, "My Mod")
    assert all(r.ok for r in results)
    downloads = tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR
    assert (downloads / "a.zip").read_bytes() == b"AAAA"
    assert (downloads / "b.hak").read_bytes() == b"BB"


def test_dialog_fetch_and_populate(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://vault/p": HttpResponse("http://vault/p", 200, text=_PROJECT_HTML)}
    )
    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("http://vault/p")
    dlg._on_fetch()
    assert dlg.file_tree.topLevelItemCount() == 2
    # All rows checked by default.
    assert len(dlg.checked_files()) == 2


def test_dialog_unchecking_excludes_file(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.populate_files(
        [VaultScraperInfo(description="a.zip"), VaultScraperInfo(description="b.hak")]
    )
    dlg.file_tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)
    checked = dlg.checked_files()
    assert len(checked) == 1
    assert checked[0].description == "a.zip"


def test_dialog_download_writes_files(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://cdn/a.zip": HttpResponse("http://cdn/a.zip", 200, content=b"DATA")}
    )
    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")])
    dlg._on_download()
    downloads = tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR
    assert (downloads / "a.zip").read_bytes() == b"DATA"
    assert "Downloaded 1 of 1" in dlg.status.text()


_REQUIRED_PAGE = (
    "<h1>My Project</h1>\n"
    '<span class="file-icon"></span><a href="http://cdn/a.zip" length=100>a.zip</a>\n'
    '<div class="field field-name-field-required-projects">'
    '<div class="field-items"><div class="field-item">'
    '<a href="http://vault/cep">CEP 2.6 <br></a></div></div></div>'
    '<div class="field field-name-field-related-projects"></div>'
)


def test_dialog_shows_required_projects(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://vault/project/needs-cep": HttpResponse(
            "http://vault/project/needs-cep", 200, text=_REQUIRED_PAGE
        )}
    )
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("http://vault/project/needs-cep")
    dlg._on_fetch()
    assert not dlg.required_list.isHidden()  # made visible on fetch
    assert dlg.required_list.topLevelItemCount() == 1
    assert dlg.required_list.topLevelItem(0).text(0) == "CEP 2.6"
    # Double-clicking loads the required project's URL into the fetch box.
    dlg._on_required_double_clicked(dlg.required_list.topLevelItem(0))
    assert dlg.url_edit.text() == "http://vault/cep"
