"""Tests for the controller vault ops + DownloadProject dialog (offline)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
from vaultkeeper.vault.scraper_info import VaultScraperInfo


def _finish(qtbot, dlg, timeout: int = 10000) -> None:
    """Wait for the dialog's background job to run its course.

    Transfers happen on a worker thread now, so a click returns long before the
    work does; every test that used to read the outcome straight after the click
    has to wait for it.
    """
    qtbot.waitUntil(lambda: not dlg._busy, timeout=timeout)

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


_PROJECT_JSON = (
    '{"project_id": 7, "title": "My Project", "attachments": ['
    '{"description": "a.zip", "filename": "a.zip", "link": "http://cdn/a.zip",'
    ' "size_bytes": 100},'
    '{"description": "b.hak", "filename": "b.hak", "link": "http://cdn/b.hak",'
    ' "size_bytes": 200}]}'
)


def _set_download_method(method: str) -> None:
    """Choose how the controller reads a Vault project (the Downloads setting)."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings(None)
    settings.vault_download_method = method
    settings.vault_rules_online = False  # never reach for the published rules here
    save_settings(settings, None)


def test_controller_scrape_project(qtbot, tmp_path):
    _set_download_method("scrape")
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://vault/project/my-project": HttpResponse(
            "http://vault/project/my-project", 200, text=_PROJECT_HTML
        )}
    )
    files = controller.scrape_project("http://vault/project/my-project")
    assert [f.description for f in files] == ["a.zip", "b.hak"]


def test_controller_reads_the_project_through_the_api_by_default(qtbot, tmp_path):
    """The default source is the Vault's API, as in NIT v8.0."""
    _set_download_method("api")
    controller = _controller(tmp_path)
    url = "http://vault/project/nwn1/module/my-project"
    query = (
        "https://neverwintervault.org/api/v1/projects/by-url?url="
        "http%3A%2F%2Fvault%2Fproject%2Fnwn1%2Fmodule%2Fmy-project"
    )
    controller._http = FakeHttpClient({query: HttpResponse(query, 200, text=_PROJECT_JSON)})
    files = controller.scrape_project(url)
    # Sizes come with the listing — the scraper had to ask per file.
    assert [(f.filename, f.byte_size) for f in files] == [("a.zip", 100), ("b.hak", 200)]


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
    _set_download_method("scrape")  # this fixture is a project *page*
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
    _finish(qtbot, dlg)
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
    _set_download_method("scrape")  # this fixture is a project *page*
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
    _finish(qtbot, dlg)
    md = controller.pd.mod_item("Installed Project")
    assert md is not None and md.is_installer()
    assert "Installed 'Installed Project'" in dlg.status.text()


def test_download_shows_byte_progress(qtbot, tmp_path):
    """"Downloading part 1 of 2" says nothing over the twenty minutes it takes."""
    controller = _controller(tmp_path)
    url = "http://cdn/big.zip"
    controller._http = FakeHttpClient(
        {url: HttpResponse(url, 200, {"Content-Length": "9"}, content=b"BIGGISH!!")}
    )
    dlg = DownloadProjectDialog(controller, default_mod="My Mod")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url=url, filename="big.zip")])
    seen: list[str] = []
    real = dlg._on_bytes
    dlg._on_bytes = lambda done, total: (real(done, total), seen.append(dlg.status.text()))
    dlg._on_download()
    _finish(qtbot, dlg)
    assert seen and "9 B of 9 B" in seen[0]
    assert controller._http.streamed == [
        (url, tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR / "big.zip")
    ]


# -- off the UI thread -------------------------------------------------------- #
class _GatedHttpClient(FakeHttpClient):
    """Holds a transfer open until the test lets go, so the UI can be watched."""

    def __init__(self, responses):
        super().__init__(responses)
        self.gate = threading.Event()
        self.started = threading.Event()

    def download(self, url, dest, *, on_chunk=None, timeout=300):
        self.started.set()
        for index in range(1, 500):  # dribble progress while we wait
            if on_chunk is not None:
                on_chunk(index, 500)
            if self.gate.wait(0.005):
                break
        return super().download(url, dest, on_chunk=on_chunk, timeout=timeout)


def _gated(tmp_path):
    controller = _controller(tmp_path)
    url = "http://cdn/big.zip"
    controller._http = _GatedHttpClient(
        {url: HttpResponse(url, 200, {"Content-Length": "9"}, content=b"BIGGISH!!")}
    )
    dlg = DownloadProjectDialog(controller, default_mod="My Mod")
    dlg.populate_files([VaultScraperInfo(direct_url=url, filename="big.zip")])
    return controller, dlg


def test_the_download_does_not_block_the_ui_thread(qtbot, tmp_path):
    """The whole point: clicking Download returns at once and the window lives.

    A gigabyte on the UI thread leaves the window unpainted for minutes, which
    reads as a crash. Here the click returns while the transfer is still open,
    and the event loop is free enough to deliver progress signals meanwhile.
    """
    controller, dlg = _gated(tmp_path)
    qtbot.addWidget(dlg)
    dlg._on_download()
    assert dlg._busy  # returned with the transfer still running
    assert controller._http.started.wait(5)
    assert not dlg.download_button.isEnabled()
    assert not dlg.cancel_button.isHidden()
    # The loop is turning: progress arrives while the transfer is still held open.
    qtbot.waitUntil(lambda: "of 500 B" in dlg.status.text(), timeout=5000)
    controller._http.gate.set()
    _finish(qtbot, dlg)
    assert dlg.download_button.isEnabled()
    assert dlg.cancel_button.isHidden()


def test_cancelling_stops_the_transfer_and_keeps_no_part_file(qtbot, tmp_path):
    controller, dlg = _gated(tmp_path)
    qtbot.addWidget(dlg)
    dlg._on_download()
    assert controller._http.started.wait(5)
    dlg._on_cancel()
    _finish(qtbot, dlg)
    assert "Cancelled" in dlg.status.text()
    assert not (
        tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR / "big.zip"
    ).exists()


def test_the_dialog_will_not_close_while_a_transfer_is_running(qtbot, tmp_path):
    """Closing would leave the worker emitting into a deleted dialog."""
    controller, dlg = _gated(tmp_path)
    qtbot.addWidget(dlg)
    dlg._on_download()
    assert controller._http.started.wait(5)
    dlg.reject()
    assert dlg.result() != QDialog.DialogCode.Rejected or dlg._busy
    assert "Cancel the download first" in dlg.status.text()
    controller._http.gate.set()
    _finish(qtbot, dlg)
    dlg.reject()  # and now it closes


def test_a_failing_job_reports_instead_of_taking_the_app_down(qtbot, tmp_path):
    """A worker thread that raises into Qt is a crash; it has to come back as text."""
    controller = _controller(tmp_path)
    dlg = DownloadProjectDialog(controller, default_mod="My Mod")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")])

    def boom(*_a, **_k):
        raise RuntimeError("the disk fell off")

    controller.download_project = boom
    dlg._on_download()
    _finish(qtbot, dlg)
    assert "the disk fell off" in dlg.status.text()
    assert dlg.download_button.isEnabled()


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
    '<a href="http://vault/project/nwn1/hakpak/cep">CEP 2.6 <br></a></div>'
    # Not every prerequisite is a Vault project: 7-Zip links to its own site.
    '<div class="field-item"><a href="https://www.7-zip.org">7-Zip</a></div>'
    "</div></div>"
    '<div class="field field-name-field-related-projects"></div>'
)


def test_dialog_shows_required_projects(qtbot, tmp_path):
    _set_download_method("scrape")  # this fixture is a project *page*
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
    assert dlg.required_list.topLevelItemCount() == 2
    assert dlg.required_list.topLevelItem(0).text(0) == "CEP 2.6"
    # Double-clicking loads the required project's URL into the fetch box.
    dlg._on_required_double_clicked(dlg.required_list.topLevelItem(0))
    assert dlg.url_edit.text() == "http://vault/project/nwn1/hakpak/cep"


def test_an_external_prerequisite_is_marked_and_not_fetched(qtbot, tmp_path, monkeypatch):
    """7-Zip is required by name; loading its home page here would find nothing."""
    _set_download_method("scrape")
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
    external = dlg.required_list.topLevelItem(1)
    assert external.text(0) == "7-Zip (external page)"

    opened = []
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    dlg._on_required_double_clicked(external)
    assert opened == ["https://www.7-zip.org"]
    # The retrieve box is left alone — there is nothing here to download.
    assert dlg.url_edit.text() == "http://vault/project/needs-cep"


# -- the silent half: extracting and installing -------------------------------- #
def test_the_build_and_install_phases_report_progress(qtbot, tmp_path):
    """After the download, extracting and installing took as long and said nothing.

    The last "1.2 GB of 1.2 GB" stayed on screen under a full bar for minutes,
    which is indistinguishable from being stuck.
    """
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._http = FakeHttpClient(
        {"http://cdn/a.zip": HttpResponse("http://cdn/a.zip", 200, content=b"Z")}
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"a.zip": {"hak/x.hak": b"X", "override/o.2da": b"O"}}
    )
    dlg = DownloadProjectDialog(controller, default_mod="Phased")
    qtbot.addWidget(dlg)
    dlg.populate_files([VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")])

    said: list[tuple[str, int, int]] = []
    real = dlg._on_phase
    dlg._on_phase = lambda label, done, total: (
        real(label, done, total), said.append((label, done, total))
    )
    dlg._on_install()
    _finish(qtbot, dlg)

    labels = [label for label, _, _ in said]
    assert any(label == "Extracting a.zip" for label in labels)
    assert any(label == "Building the installer" for label in labels)
    assert any(label == "Installing files" for label in labels)
    # A phase with a count drives a real bar; one without asks for a busy indicator.
    counted = [(d, t) for _, d, t in said if t > 0]
    assert counted and all(0 < d <= t for d, t in counted)
    assert "Installed 'Phased'" in dlg.status.text()


def test_a_phase_without_a_count_shows_a_busy_bar_not_a_full_one(qtbot, tmp_path):
    """Extracting a 2 GB archive is one opaque step; a bar for it would have to lie."""
    dlg = DownloadProjectDialog(_controller(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_phase("Extracting cep_3.1.4.7z", 0, 0)
    assert (dlg.progress.minimum(), dlg.progress.maximum()) == (0, 0)  # indeterminate
    assert dlg.status.text() == "Extracting cep_3.1.4.7z…"
    dlg._on_phase("Installing files", 40, 200)
    assert (dlg.progress.maximum(), dlg.progress.value()) == (200, 40)
    assert dlg.status.text() == "Installing files — 40 of 200"


def test_the_api_marks_an_external_prerequisite_outright(qtbot, tmp_path):
    """The API states the kind; the scraper had to infer it from the URL."""
    from vaultkeeper.ui.dialogs.download_project import _is_external

    assert _is_external({"type": "external", "url": "https://neverwintervault.org/x"})
    assert not _is_external({"type": "project", "url": "https://elsewhere.example/p"})


def test_files_and_prerequisites_come_from_one_request(qtbot, tmp_path):
    """Asking twice meant two API calls to the same place for the same answer."""
    _set_download_method("api")
    controller = _controller(tmp_path)
    query = "https://neverwintervault.org/api/v1/projects/9"
    payload = (
        '{"project_id": 9, "title": "P", "attachments": ['
        '{"filename": "a.zip", "link": "http://cdn/a.zip", "size_bytes": 5}],'
        ' "required_projects": [{"type": "external", "title": "7-Zip",'
        ' "link": "https://www.7-zip.org"}]}'
    )
    controller._http = FakeHttpClient({query: HttpResponse(query, 200, text=payload)})
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("https://neverwintervault.org/project/9")
    dlg._on_fetch()
    assert dlg.file_tree.topLevelItemCount() == 1
    assert dlg.required_list.topLevelItem(0).text(0) == "7-Zip (external page)"
    assert controller._http.calls == [("GET", query)]  # one, not two


# -- remembering where a mod came from ------------------------------------------ #
def _api_controller(tmp_path, url, payload):
    _set_download_method("api")
    controller = _controller(tmp_path)
    from urllib.parse import quote

    query = (
        "https://neverwintervault.org/api/v1/projects/by-url?url=" + quote(url, safe="")
    )
    controller._http = FakeHttpClient({query: HttpResponse(query, 200, text=payload)})
    return controller


def test_a_new_mod_downloaded_from_a_page_remembers_it(qtbot, tmp_path):
    """Without this, Check for Mod Updates has nothing to check."""
    url = "http://vault/project/nwn1/module/mine"
    controller = _api_controller(tmp_path, url, _PROJECT_JSON)
    controller._http.responses["http://cdn/a.zip"] = HttpResponse(
        "http://cdn/a.zip", 200, content=b"A"
    )
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    dlg.mod_name_edit.setText("Brand New")
    dlg._on_download()
    _finish(qtbot, dlg)
    assert controller.mod_web_link("Brand New") == url


def test_an_existing_mods_link_is_not_replaced_without_asking(qtbot, tmp_path, monkeypatch):
    url = "http://vault/project/nwn1/module/mine"
    controller = _api_controller(tmp_path, url, _PROJECT_JSON)
    controller.create_mod("My Mod")
    controller.set_mod_web_link("My Mod", "http://vault/project/nwn1/module/old")
    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)

    from PySide6.QtWidgets import QMessageBox

    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.No)[1],
    )
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert asked, "an existing, different link must be a question"
    assert controller.mod_web_link("My Mod").endswith("/old")


def test_saying_yes_replaces_the_link_and_is_only_asked_once(qtbot, tmp_path, monkeypatch):
    url = "http://vault/project/nwn1/module/mine"
    controller = _api_controller(tmp_path, url, _PROJECT_JSON)
    controller.create_mod("My Mod")
    controller.set_mod_web_link("My Mod", "http://vault/project/nwn1/module/old")
    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)

    from PySide6.QtWidgets import QMessageBox

    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: (asked.append(1), QMessageBox.StandardButton.Yes)[1],
    )
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    dlg._on_fetch()  # retrieving twice must not ask twice
    assert len(asked) == 1
    assert controller.mod_web_link("My Mod") == url


def test_an_empty_link_is_filled_in_without_a_question(qtbot, tmp_path, monkeypatch):
    url = "http://vault/project/nwn1/module/mine"
    controller = _api_controller(tmp_path, url, _PROJECT_JSON)
    controller.create_mod("My Mod")
    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: pytest.fail("nothing to ask about")
    )
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert controller.mod_web_link("My Mod") == url


def test_the_title_names_the_download_rules_in_force(qtbot, tmp_path):
    """Which rules answered matters when a download behaves oddly."""
    url = "http://vault/project/nwn1/module/mine"
    controller = _api_controller(tmp_path, url, _PROJECT_JSON)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Download Project"  # nothing loaded yet
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert "Rules revision" in dlg.windowTitle()


def test_a_download_offers_to_clear_the_version_it_replaced(qtbot, tmp_path, monkeypatch):
    """The folder otherwise keeps every version of a 400 MB module for ever."""
    url = "http://vault/project/nwn1/module/mine"
    payload = (
        '{"project_id": 3, "title": "Mine", "attachments": ['
        '{"filename": "mymodule_1_2.7z", "link": "http://cdn/new.7z", "size_bytes": 4}]}'
    )
    controller = _api_controller(tmp_path, url, payload)
    controller._http.responses["http://cdn/new.7z"] = HttpResponse(
        "http://cdn/new.7z", 200, content=b"NEW!"
    )
    controller.create_mod("My Mod")
    downloads = tmp_path / "Profiles" / "P" / "My Mod" / C.DOWNLOADS_DIR
    downloads.mkdir(parents=True, exist_ok=True)
    (downloads / "mymodule_1_1.7z").write_bytes(b"OLD")

    dlg = DownloadProjectDialog(controller, ["My Mod"], "My Mod")
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()

    from vaultkeeper.ui.dialogs.old_downloads import OldDownloadsDialog

    seen = {}

    def fake_exec(self):
        seen["names"] = [p.name for p in self.checked_paths()]
        self.action = "history"
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(OldDownloadsDialog, "exec", fake_exec)
    dlg._on_download()
    _finish(qtbot, dlg)

    assert seen["names"] == ["mymodule_1_1.7z"]
    assert not (downloads / "mymodule_1_1.7z").exists()
    assert (tmp_path / "Profiles" / "P" / "My Mod" / "_History" / "mymodule_1_1.7z").is_file()
    assert (downloads / "mymodule_1_2.7z").read_bytes() == b"NEW!"


def test_a_first_download_asks_nothing(qtbot, tmp_path, monkeypatch):
    url = "http://vault/project/nwn1/module/mine"
    payload = (
        '{"project_id": 3, "title": "Mine", "attachments": ['
        '{"filename": "mymodule_1_2.7z", "link": "http://cdn/new.7z", "size_bytes": 4}]}'
    )
    controller = _api_controller(tmp_path, url, payload)
    controller._http.responses["http://cdn/new.7z"] = HttpResponse(
        "http://cdn/new.7z", 200, content=b"NEW!"
    )
    from vaultkeeper.ui.dialogs.old_downloads import OldDownloadsDialog

    monkeypatch.setattr(
        OldDownloadsDialog, "exec", lambda self: pytest.fail("nothing was replaced")
    )
    dlg = DownloadProjectDialog(controller, ["My Mod"], "Fresh")
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    dlg._on_download()
    _finish(qtbot, dlg)


# -- saying why nothing came back ----------------------------------------------- #
def _empty_controller(tmp_path):
    _set_download_method("api")
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient({})  # every request 404s
    return controller


def test_a_nexus_url_says_nexus_refuses_rather_than_no_files(qtbot, tmp_path):
    """Nexus answers 403 to programs by policy. "No files found" blames us."""
    controller = _empty_controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("https://www.nexusmods.com/neverwinter/mods/824")
    dlg._on_fetch()
    text = dlg.status.text()
    assert "Nexus Mods does not allow" in text
    assert "Add Files to Mod" in text  # and what to do instead


def test_a_non_vault_url_says_so(qtbot, tmp_path):
    controller = _empty_controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("https://example.com/some/page")
    dlg._on_fetch()
    assert "not a Neverwinter Vault project address" in dlg.status.text()


def test_a_real_vault_url_with_nothing_on_it_blames_the_page(qtbot, tmp_path):
    controller = _empty_controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)
    dlg.url_edit.setText("https://neverwintervault.org/project/nwn1/module/empty")
    dlg._on_fetch()
    assert dlg.status.text() == "No downloadable files found on that project page."


# -- the published per-project rules, applied ----------------------------------- #
_RULED_JSON = (
    '{"project_id": 8, "title": "CEP 3 The Community Expansion Pack", "attachments": ['
    '{"filename": "cep_3.1.4_-_part_1.7z", "link": "http://cdn/n1.7z", "size_bytes": 9},'
    '{"filename": "cep_3.1.3_-_part_1.7z", "link": "http://cdn/o1.7z", "size_bytes": 9},'
    '{"filename": "extra_optional.7z", "link": "http://cdn/x.7z", "size_bytes": 9}]}'
)

_RULES_TEXT = (
    "Project = CEP 3 The Community Expansion Pack\n"
    "\tModFolder = CEP v3.x\n"
    "\tGroup = 100.  Community Packs\n"
    "\tExcludes\n\t\tcep_3.1.3_-_part_1.7z\n\tEnd Excludes\n"
    "\tDownloads\n\t\tcep_3.1.4_-_part_1.7z\n\tEnd Downloads\n"
    "End Project\n"
)


def _ruled_controller(tmp_path, *, apply_rules=True):
    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.vault.download_rules import DownloadRules

    settings = load_settings(None)
    settings.vault_download_method = "api"
    settings.vault_rules_online = False
    settings.vault_apply_project_rules = apply_rules
    save_settings(settings, None)

    controller = _controller(tmp_path)
    url = "https://neverwintervault.org/project/nwnee/hakpak/combined/cep-3"
    from urllib.parse import quote

    query = (
        "https://neverwintervault.org/api/v1/projects/by-url?url=" + quote(url, safe="")
    )
    controller._http = FakeHttpClient({query: HttpResponse(query, 200, text=_RULED_JSON)})
    controller._download_rules = DownloadRules.from_text(_RULES_TEXT)
    return controller, url


def test_the_rules_choose_the_mod_folder_and_group(qtbot, tmp_path):
    controller, url = _ruled_controller(tmp_path)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert dlg.mod_name_edit.text() == "CEP v3.x"
    assert dlg.group_combo.currentText() == "100.  Community Packs"


def test_a_superseded_file_is_not_offered_and_the_holding_back_is_stated(qtbot, tmp_path):
    controller, url = _ruled_controller(tmp_path)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    listed = [
        dlg.file_tree.topLevelItem(i).text(0)
        for i in range(dlg.file_tree.topLevelItemCount())
    ]
    assert "cep_3.1.3_-_part_1.7z" not in listed
    assert "2 files the download rules hold back" in dlg.status.text()


def test_a_downloads_block_is_a_whitelist_not_a_set_of_ticks(qtbot, tmp_path):
    """VB holds back everything a Downloads block does not name, exactly as an
    Excludes entry would (DownloadProject.Methods.vb:735). Community Music Pack
    publishes thirty-odd files and names three; the rest are not choices."""
    controller, url = _ruled_controller(tmp_path)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    listed = [
        dlg.file_tree.topLevelItem(i).text(0)
        for i in range(dlg.file_tree.topLevelItemCount())
    ]
    assert listed == ["cep_3.1.4_-_part_1.7z"]        # the one named
    assert [f.filename for f in dlg.checked_files()] == ["cep_3.1.4_-_part_1.7z"]


def test_a_typed_mod_name_is_never_overwritten_by_a_rule(qtbot, tmp_path):
    controller, url = _ruled_controller(tmp_path)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.mod_name_edit.setText("My Own Name")
    dlg._on_name_edited("My Own Name")
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert dlg.mod_name_edit.text() == "My Own Name"


def test_turning_the_rules_off_takes_the_project_as_the_vault_presents_it(qtbot, tmp_path):
    controller, url = _ruled_controller(tmp_path, apply_rules=False)
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    assert dlg.file_tree.topLevelItemCount() == 3     # nothing held back
    assert len(dlg.checked_files()) == 3              # nothing unticked
    assert dlg.mod_name_edit.text() != "CEP v3.x"     # the page title, not the rule


def test_the_rules_can_add_a_prerequisite_the_page_omits(qtbot, tmp_path):
    from vaultkeeper.vault.download_rules import DownloadRules

    controller, url = _ruled_controller(tmp_path)
    controller._download_rules = DownloadRules.from_text(
        "Project = CEP 3 The Community Expansion Pack\n"
        "\tRequiredProjects\n"
        "\t\thttps://neverwintervault.org/project/nwn1/hakpak/needed-anyway\n"
        "\tEnd RequiredProjects\n"
        "End Project\n"
    )
    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    dlg.url_edit.setText(url)
    dlg._on_fetch()
    urls = [
        dlg.required_list.topLevelItem(i).text(1)
        for i in range(dlg.required_list.topLevelItemCount())
    ]
    assert "https://neverwintervault.org/project/nwn1/hakpak/needed-anyway" in urls


# -- Download rules toggle (newtopic5.htm) ---------------------------------- #


def test_rules_toggle_reflects_and_saves_the_preference(qtbot, tmp_path):
    """"Disable Apply Project Download File rules to show all available files."

    The preference was honoured but lived three dialogs away, in Advanced
    Settings — not where you read "3 files the download rules hold back".
    """
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings(None)
    settings.vault_apply_project_rules = True
    save_settings(settings, None)

    controller = _controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)

    assert dlg.rules_button.isChecked()
    dlg.rules_button.setChecked(False)
    assert load_settings(None).vault_apply_project_rules is False
    assert "every file" in dlg.status.text()

    dlg.rules_button.setChecked(True)
    assert load_settings(None).vault_apply_project_rules is True


def test_turning_rules_off_refetches_what_they_held_back(qtbot, tmp_path, monkeypatch):
    """The held-back files were dropped before the list was built.

    Without the re-fetch the setting would appear to do nothing at all.
    """
    controller = _controller(tmp_path)
    dlg = DownloadProjectDialog(controller, ["My Mod"])
    qtbot.addWidget(dlg)

    fetches: list[str] = []
    monkeypatch.setattr(dlg, "_on_fetch", lambda: fetches.append("fetched"))

    # Nothing retrieved yet: there is nothing to re-fetch.
    dlg.rules_button.setChecked(False)
    assert fetches == []

    dlg._fetched_url = "http://vault/project/my-project"
    dlg.rules_button.setChecked(True)
    assert fetches == ["fetched"]
