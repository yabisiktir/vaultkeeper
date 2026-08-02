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


def test_download_creates_new_mod(qtbot, tmp_path):
    # The key UX: Download a Vault project to CREATE a mod (VB "create or update").
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://cdn/a.zip": HttpResponse("http://cdn/a.zip", 200, content=b"NEW")}
    )
    assert controller.pd.mod_item("Fresh Project") is None
    files = [VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")]
    results = controller.download_project(
        files, "Fresh Project", group="100. Packs"
    )
    assert all(r.ok for r in results)
    # A new managed mod was created under the chosen group.
    md = controller.pd.mod_item("Fresh Project")
    assert md is not None and md.group == "100. Packs"
    dl = tmp_path / "Profiles" / "P" / "Fresh Project" / C.DOWNLOADS_DIR / "a.zip"
    assert dl.read_bytes() == b"NEW"


def test_suggested_mod_name_sanitises_title(tmp_path):
    controller = _controller(tmp_path)
    assert controller.suggested_mod_name("Aribeth's Redemption: Ch. 3?") == (
        "Aribeth's Redemption Ch. 3"
    )


def test_dialog_prefills_mod_name_from_project_title(qtbot, tmp_path):
    controller = _controller(tmp_path)
    url = "http://vault/project/my-project"
    controller._http = FakeHttpClient(
        {url: HttpResponse(url, 200, text=_PROJECT_HTML)}
    )
    dlg = DownloadProjectDialog(controller)  # no default mod
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    # The mod folder name is derived from the project (URL slug -> "My Project").
    assert dlg.mod_name_edit.text() == "My Project"
    assert dlg.project_label.text() == "My Project"
    assert not dlg.config_box.isHidden()  # revealed on retrieve
    assert dlg.download_button.isEnabled()


def test_install_downloaded_project(qtbot, tmp_path):
    # Install = download the project + build the installer + install (VB Install).
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://cdn/pack.zip": HttpResponse("http://cdn/pack.zip", 200, content=b"Z")}
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"pack.zip": {"override/o.2da": b"O"}}
    )
    files = [VaultScraperInfo(direct_url="http://cdn/pack.zip", filename="pack.zip")]
    result = controller.install_downloaded_project(files, "New Project", group="100. Packs")
    assert result["downloaded"] == 1
    assert result["built"] is True
    md = controller.pd.mod_item("New Project")
    assert md is not None and md.is_installer()
    payload = (
        tmp_path / "Profiles" / "P" / "New Project" / C.MOD_INSTALLER_DIR
        / "override" / "o.2da"
    )
    assert payload.is_file()


def test_dialog_marks_already_downloaded(qtbot, tmp_path):
    controller = _controller(tmp_path)
    downloads = tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR
    downloads.mkdir(parents=True, exist_ok=True)
    (downloads / "a.zip").write_bytes(b"old")

    dlg = DownloadProjectDialog(controller, default_mod="My Mod")
    qtbot.addWidget(dlg)
    dlg.populate_files(
        [
            VaultScraperInfo(description="a.zip", filename="a.zip"),
            VaultScraperInfo(description="b.hak", filename="b.hak"),
        ]
    )
    # a.zip already present -> "Already downloaded" + unticked; b.hak -> ticked.
    assert dlg.file_tree.topLevelItem(0).text(2) == "Already downloaded"
    assert dlg.file_tree.topLevelItem(0).checkState(0) == Qt.CheckState.Unchecked
    assert dlg.file_tree.topLevelItem(1).text(2) == ""
    assert dlg.file_tree.topLevelItem(1).checkState(0) == Qt.CheckState.Checked
    # Only the not-yet-downloaded file is queued.
    assert [f.filename for f in dlg.checked_files()] == ["b.hak"]


def test_dialog_install_button_runs_install_flow(qtbot, tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://cdn/a.zip": HttpResponse("http://cdn/a.zip", 200, content=b"Z")}
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"a.zip": {"hak/x.hak": b"X"}}
    )
    dlg = DownloadProjectDialog(controller, default_mod="Installed Project")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")])
    dlg._on_install()
    md = controller.pd.mod_item("Installed Project")
    assert md is not None and md.is_installer()
    assert "Installed 'Installed Project'" in dlg.status.text()


def test_download_shows_byte_progress_and_locks_the_buttons(qtbot, tmp_path):
    """A 1.2 GB file downloads on the UI thread — "part 1 of 2" is not enough.

    Without per-byte progress the window simply stops repainting for many
    minutes, which reads as a crash; and because the event loop keeps turning to
    prevent that, a second click would land inside the first download.
    """
    controller = _controller(tmp_path)
    url = "http://cdn/big.zip"
    controller._http = FakeHttpClient(
        {url: HttpResponse(url, 200, {"Content-Length": "9"}, content=b"BIGGISH!!")}
    )
    dlg = DownloadProjectDialog(controller, default_mod="My Mod")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url=url, filename="big.zip")])

    seen: list[str] = []
    real_on_bytes = dlg._on_bytes

    def spy(vsi, done, total):
        real_on_bytes(vsi, done, total)
        seen.append(dlg.status.text())
        # Mid-transfer the buttons are locked, so a stray click does nothing.
        assert dlg._busy
        assert not dlg.download_button.isEnabled()
        assert not dlg.install_button.isEnabled()
        dlg._on_download()  # a second click during the first download

    dlg._on_bytes = spy
    dlg._on_download()
    assert seen and "9 B of 9 B" in seen[0]
    assert not dlg._busy  # released afterwards
    assert dlg.download_button.isEnabled()
    # Only one transfer happened despite the re-entrant click.
    assert controller._http.streamed == [
        (url, tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR / "big.zip")
    ]


def test_dialog_download_needs_a_mod_name(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(description="a.zip")])
    dlg.mod_name_edit.clear()
    dlg._on_download()
    assert "mod folder name" in dlg.status.text().lower()


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
