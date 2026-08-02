"""Installing a PRC-ified Vault module: the controller ops + the dialog (offline).

The two rules the flow exists to keep are asserted here directly: the Vault page
is never chosen for the user, and a dependency the archive and the page disagree
about is never resolved without an answer.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.prc_module import PrcModuleDialog
from vaultkeeper.vault.drive_folder import PRC_MODULES_FOLDER, download_url, listing_url
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
from vaultkeeper.vault.vault_search import search_url

FOLDER_HTML = """
<div class="flip-entry" id="entry-1zxFolderAA">
 <a href="https://drive.google.com/drive/folders/1zxFolderAA">
  <div class="flip-entry-title">Base Modules</div></a>
</div>
<div class="flip-entry" id="entry-1hWArchiveAA">
 <a href="https://drive.google.com/file/d/1hWArchiveAA/view">
  <div class="flip-entry-title">A Call for Heroes [PRC8-CEP3].7z</div></a>
</div>
"""

SUBFOLDER_HTML = """
<div class="flip-entry" id="entry-1hWArchiveBB">
 <a href="https://drive.google.com/file/d/1hWArchiveBB/view">
  <div class="flip-entry-title">Almraiven [PRC8].7z</div></a>
</div>
"""

#: Three near-identical pages — the case no ranking can settle.
SEARCH_HTML = """
<a href="/project/nwn1/module/selendi-call-heroes-1">Selendi: A Call For Heroes 1</a>
<a href="/project/nwn1/module/selendi-call-heroes-2">Selendi: A Call For Heroes 2</a>
<a href="/project/nwn1/hakpak/heroes-music">Heroes Music Pack</a>
"""

#: The module's page: needs CEP 2.65, where the archive was built for CEP3.
PAGE_HTML = (
    "<h1>Selendi</h1>"
    '<span class="file-icon"></span><a href="http://cdn/mod.zip" length=10>mod.zip</a>'
    '<div class="field field-name-field-required-projects"><div class="field-items">'
    '<div class="field-item"><a href="https://neverwintervault.org/project/nwn1/hakpak/cep">'
    "CEP 2.65</a></div>"
    '<div class="field-item"><a href="https://neverwintervault.org/project/nwn1/hakpak/tileset">'
    "Sigil Tileset</a></div>"
    "</div></div>"
)

PAGE_URL = "https://neverwintervault.org/project/nwn1/module/selendi-call-heroes-1"


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _responses() -> dict:
    return {
        listing_url(PRC_MODULES_FOLDER): HttpResponse(
            listing_url(PRC_MODULES_FOLDER), 200, text=FOLDER_HTML
        ),
        listing_url("1zxFolderAA"): HttpResponse(
            listing_url("1zxFolderAA"), 200, text=SUBFOLDER_HTML
        ),
        search_url("A Call for Heroes"): HttpResponse(
            search_url("A Call for Heroes"), 200, text=SEARCH_HTML
        ),
        PAGE_URL: HttpResponse(PAGE_URL, 200, text=PAGE_HTML),
    }


def _wired(tmp_path: Path, extra: dict | None = None) -> ProfileController:
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient({**_responses(), **(extra or {})})
    return controller


def _at_the_plan(qtbot, controller) -> PrcModuleDialog:
    """A dialog driven as far as the merged dependency plan."""
    dlg = PrcModuleDialog(controller)
    qtbot.addWidget(dlg)
    dlg._on_browse()
    dlg.entry_tree.setCurrentItem(dlg.entry_tree.topLevelItem(1))  # the archive
    dlg._on_search()
    dlg.candidate_tree.setCurrentItem(dlg.candidate_tree.topLevelItem(0))
    dlg._on_use_page()
    return dlg


# -- controller ops ----------------------------------------------------------- #
def test_the_default_folder_is_the_published_collection(qtbot, tmp_path):
    controller = _wired(tmp_path)
    entries = controller.drive_entries()
    assert [e.name for e in entries] == [
        "Base Modules",
        "A Call for Heroes [PRC8-CEP3].7z",
    ]  # subfolders first
    assert entries[1].tags == ("PRC8", "CEP3")


def test_an_unreadable_folder_lists_as_empty_rather_than_partly(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller._http = FakeHttpClient({})  # every request 404s
    assert controller.drive_entries() == []


def test_the_plan_merges_the_build_tag_with_the_pages_requirements(qtbot, tmp_path):
    controller = _wired(tmp_path)
    plan = controller.module_dependency_plan(("PRC8", "CEP3"), PAGE_URL)
    # The tileset is only the page's, so it is settled; CEP is disputed.
    assert [r.name for r in plan.agreed] == ["PRC8", "Sigil Tileset"]
    assert [c.family for c in plan.choices] == ["CEP"]
    assert plan.choices[0].recommended.name == "CEP3"


def test_an_installed_mod_satisfies_a_requirement_of_the_same_family(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("CEP 2.65")
    md = controller.pd.mod_item("CEP 2.65")
    md.mod_state = 99  # installed
    # A requirement written "CEP3" is answered by the CEP that is actually here.
    assert controller.satisfied_by("CEP3") == "CEP 2.65"
    assert controller.satisfied_by("Sigil Tileset") == ""


def test_a_drive_archive_downloads_into_the_mods_downloads_folder(qtbot, tmp_path):
    archive = b"7z\xbc\xaf\x27\x1c" + b"payload"
    controller = _wired(
        tmp_path,
        {
            download_url("1hWArchiveAA"): HttpResponse(
                download_url("1hWArchiveAA"), 200,
                {"Content-Type": "application/octet-stream",
                 "Content-Disposition": 'attachment; filename="A Call for Heroes.7z"'},
                content=archive,
            )
        },
    )
    result = controller.download_drive_module("1hWArchiveAA", "Call for Heroes")
    assert result.ok
    written = (
        tmp_path / "Profiles" / "P" / "Call for Heroes" / C.DOWNLOADS_DIR
        / "A Call for Heroes.7z"
    )
    assert written.read_bytes() == archive
    assert controller.pd.mod_item("Call for Heroes") is not None  # created on the way


def test_a_quota_page_is_reported_rather_than_written_out_as_an_archive(qtbot, tmp_path):
    from vaultkeeper.vault.drive_download import DriveDownloadError

    quota = "<html>Too many users have viewed or downloaded this file recently.</html>"
    controller = _wired(
        tmp_path,
        {
            download_url("1hWArchiveAA"): HttpResponse(
                download_url("1hWArchiveAA"), 200, {"Content-Type": "text/html"}, quota
            )
        },
    )
    with pytest.raises(DriveDownloadError):
        controller.download_drive_module("1hWArchiveAA", "Call for Heroes")


def test_a_requirement_with_no_vault_page_is_reported_not_dropped(qtbot, tmp_path):
    """``PRC8`` is a build tag; it names no page, so nothing can fetch it."""
    from vaultkeeper.vault.prc_dependencies import Requirement

    archive = b"7z\xbc\xaf\x27\x1c"
    controller = _wired(
        tmp_path,
        {
            download_url("1hWArchiveAA"): HttpResponse(
                download_url("1hWArchiveAA"), 200,
                {"Content-Type": "application/octet-stream"}, content=archive,
            )
        },
    )
    steps = controller.install_prc_module(
        "1hWArchiveAA", "Heroes", [Requirement("PRC8", "archive")]
    )
    assert steps[0]["name"] == "PRC8" and not steps[0]["ok"]
    assert "install it yourself" in steps[0]["message"]
    assert steps[1]["kind"] == "module"  # the module still went in, after it


def test_dependencies_are_installed_before_the_module_and_as_their_own_mods(
    qtbot, tmp_path
):
    """CEP is shared between modules, so it must stay separately uninstallable."""
    from vaultkeeper.core.archive import FakeArchiveExtractor
    from vaultkeeper.vault.prc_dependencies import Requirement

    cep_page = (
        "<h1>CEP</h1>"
        '<span class="file-icon"></span><a href="http://cdn/cep.zip" length=9>cep.zip</a>'
    )
    controller = _wired(
        tmp_path,
        {
            "http://vault/cep": HttpResponse("http://vault/cep", 200, text=cep_page),
            "http://cdn/cep.zip": HttpResponse(
                "http://cdn/cep.zip", 200, content=b"CEPDATA"
            ),
            download_url("1hWArchiveAA"): HttpResponse(
                download_url("1hWArchiveAA"), 200,
                {"Content-Type": "application/octet-stream"},
                content=b"7z\xbc\xaf\x27\x1cmod",
            ),
        },
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"cep.zip": {"hak/cep.hak": b"C"}, "1hWArchiveAA.7z": {"modules/m.mod": b"M"}}
    )
    steps = controller.install_prc_module(
        "1hWArchiveAA",
        "Call for Heroes",
        [Requirement("CEP 2.65", "vault", "http://vault/cep")],
    )
    assert [s["kind"] for s in steps] == ["dependency", "module"]  # deps first
    assert all(s["ok"] for s in steps)
    # The dependency became its own mod, not part of the module's installer.
    assert controller.pd.mod_item("CEP") is not None
    assert controller.pd.mod_item("Call for Heroes") is not None


# -- the way in ---------------------------------------------------------------- #
def test_the_ribbon_button_opens_the_dialog(qtbot, tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller=_wired(tmp_path))
    qtbot.addWidget(win)
    assert "RbnPrcModule" in win.implemented_commands()
    assert win.ribbon.button("RbnPrcModule").isEnabled()
    win._on_command("RbnPrcModule")
    assert isinstance(win._prc_dialog, PrcModuleDialog)
    assert win._prc_dialog.isVisible()


# -- the dialog --------------------------------------------------------------- #
def test_browsing_lists_folders_and_modules(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_browse()
    assert dlg.entry_tree.topLevelItemCount() == 2
    assert dlg.entry_tree.topLevelItem(0).text(0) == "Base Modules"
    # The archive shows its title without the tag, and the tag in its own column.
    assert dlg.entry_tree.topLevelItem(1).text(0) == "A Call for Heroes"
    assert dlg.entry_tree.topLevelItem(1).text(1) == "PRC8, CEP3"


def test_double_clicking_a_folder_opens_it_and_up_comes_back(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_browse()
    dlg.entry_tree.setCurrentItem(dlg.entry_tree.topLevelItem(0))
    dlg._on_entry_activated(dlg.entry_tree.topLevelItem(0))
    assert [dlg.entry_tree.topLevelItem(0).text(0)] == ["Almraiven"]
    assert dlg.up_button.isEnabled()
    dlg._on_up()
    assert dlg.entry_tree.topLevelItemCount() == 2
    assert not dlg.up_button.isEnabled()


def test_choosing_a_module_seeds_the_search_and_the_mod_name(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_browse()
    dlg.entry_tree.setCurrentItem(dlg.entry_tree.topLevelItem(1))
    assert dlg.search_edit.text() == "A Call for Heroes"
    assert dlg.mod_name_edit.text() == "A Call For Heroes"
    assert not dlg.page_box.isHidden()


def test_the_vault_page_is_ranked_but_never_chosen(qtbot, tmp_path):
    """Three Selendi pages tie; picking one for the user would be a guess."""
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_browse()
    dlg.entry_tree.setCurrentItem(dlg.entry_tree.topLevelItem(1))
    dlg._on_search()
    assert dlg.candidate_tree.topLevelItemCount() == 3
    assert dlg.candidate_tree.currentItem() is None  # nothing preselected
    assert dlg.selected_candidate is None
    # Pressing on without a choice refuses rather than taking the top row.
    dlg._on_use_page()
    assert "Select the Vault page" in dlg.status.text()
    assert dlg.plan_box.isHidden()


def test_modules_are_ranked_above_an_equally_similar_hakpak(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg.search_edit.setText("A Call for Heroes")
    dlg._on_search()
    kinds = [
        dlg.candidate_tree.topLevelItem(i).text(1)
        for i in range(dlg.candidate_tree.topLevelItemCount())
    ]
    assert kinds[-1] == "hakpak"


def test_a_disagreement_blocks_install_until_it_is_answered(qtbot, tmp_path):
    """The page says CEP 2.65, the file name says CEP3 — only the user can settle it."""
    controller = _wired(tmp_path)
    dlg = _at_the_plan(qtbot, controller)
    assert dlg.unanswered == ["CEP"]
    assert not dlg.install_button.isEnabled()
    # The disputed family is not listed as though it were decided.
    listed = [
        dlg.plan_tree.topLevelItem(i).text(0)
        for i in range(dlg.plan_tree.topLevelItemCount())
    ]
    assert "CEP3" not in listed and "CEP 2.65" not in listed
    assert listed == ["PRC8", "Sigil Tileset"]


def test_the_archives_answer_is_recommended_but_not_preselected(qtbot, tmp_path):
    dlg = _at_the_plan(qtbot, _wired(tmp_path))
    group = dlg._choice_groups["CEP"]
    assert group.checkedButton() is None
    labels = [b.text() for b in group.buttons()]
    assert any(label.startswith("CEP3") and "recommended" in label for label in labels)
    assert any(label == "CEP 2.65" for label in labels)


def test_answering_the_question_lists_the_choice_and_enables_install(qtbot, tmp_path):
    dlg = _at_the_plan(qtbot, _wired(tmp_path))
    chosen = next(
        b for b in dlg._choice_groups["CEP"].buttons()
        if b.property("requirement_name") == "CEP 2.65"
    )
    chosen.setChecked(True)
    assert dlg.picks() == {"CEP": "CEP 2.65"}
    listed = [
        dlg.plan_tree.topLevelItem(i).text(0)
        for i in range(dlg.plan_tree.topLevelItemCount())
    ]
    assert "CEP 2.65" in listed and "CEP3" not in listed
    assert dlg.install_button.isEnabled()


def test_an_already_installed_dependency_shows_as_satisfied_and_unticked(qtbot, tmp_path):
    controller = _wired(tmp_path)
    controller.create_mod("Sigil Tileset")
    controller.pd.mod_item("Sigil Tileset").mod_state = 99
    dlg = _at_the_plan(qtbot, controller)
    rows = {
        dlg.plan_tree.topLevelItem(i).text(0): dlg.plan_tree.topLevelItem(i)
        for i in range(dlg.plan_tree.topLevelItemCount())
    }
    tileset = rows["Sigil Tileset"]
    assert tileset.text(2) == "Already installed as 'Sigil Tileset'"
    assert tileset.checkState(0) == Qt.CheckState.Unchecked
    assert tileset not in dlg.checked_requirements()
    # It is listed, not hidden — and can be re-ticked to reinstall.
    tileset.setCheckState(0, Qt.CheckState.Checked)
    assert [r.name for r in dlg.checked_requirements()] == ["Sigil Tileset"]


def test_a_requirement_with_no_page_says_so_and_offers_no_tick_box(qtbot, tmp_path):
    """``PRC8`` is a build tag, not a page — a box here could never do anything."""
    dlg = _at_the_plan(qtbot, _wired(tmp_path))
    rows = {
        dlg.plan_tree.topLevelItem(i).text(0): dlg.plan_tree.topLevelItem(i)
        for i in range(dlg.plan_tree.topLevelItemCount())
    }
    assert "install this one yourself" in rows["PRC8"].text(2)
    assert rows["PRC8"].checkState(0) == Qt.CheckState.Unchecked
    # No check state means Qt draws no box. The flag is no use as a test: every
    # QTreeWidgetItem carries ItemIsUserCheckable whether a box is shown or not.
    assert rows["PRC8"].data(0, Qt.ItemDataRole.CheckStateRole) is None
    assert rows["Sigil Tileset"].data(0, Qt.ItemDataRole.CheckStateRole) is not None


def test_a_match_score_is_never_shown_above_a_hundred_percent(qtbot, tmp_path):
    """Ranking adds a bonus for being a module; "105%" reads as a broken gauge."""
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg.search_edit.setText("A Call for Heroes")
    dlg._on_search()
    shown = [
        dlg.candidate_tree.topLevelItem(i).text(2)
        for i in range(dlg.candidate_tree.topLevelItemCount())
    ]
    assert shown[0] == "100%"
    assert all(int(s.rstrip("%")) <= 100 for s in shown)


def test_a_module_with_no_vault_page_still_gets_its_build_tag(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg._on_browse()
    dlg.entry_tree.setCurrentItem(dlg.entry_tree.topLevelItem(1))
    dlg._on_no_page()
    listed = [
        dlg.plan_tree.topLevelItem(i).text(0)
        for i in range(dlg.plan_tree.topLevelItemCount())
    ]
    assert listed == ["PRC8", "CEP3"]
    assert dlg.install_button.isEnabled()  # nothing to disagree about


def test_a_pasted_file_link_skips_the_folder_and_asks_for_a_title(qtbot, tmp_path):
    dlg = PrcModuleDialog(_wired(tmp_path))
    qtbot.addWidget(dlg)
    dlg.folder_edit.setText("https://drive.google.com/file/d/1hWArchiveZZ/view?usp=sharing")
    dlg._on_browse()
    assert dlg._file_ident == "1hWArchiveZZ"
    assert dlg._tags == ()  # a link carries no build tag
    assert dlg.search_edit.text() == ""
    assert not dlg.page_box.isHidden()


def test_install_needs_a_mod_folder_name(qtbot, tmp_path):
    dlg = _at_the_plan(qtbot, _wired(tmp_path))
    next(iter(dlg._choice_groups["CEP"].buttons())).setChecked(True)
    dlg.mod_name_edit.clear()
    dlg._on_install()
    assert "mod folder name" in dlg.status.text().lower()


def test_installing_reports_each_step(qtbot, tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _wired(
        tmp_path,
        {
            download_url("1hWArchiveAA"): HttpResponse(
                download_url("1hWArchiveAA"), 200,
                {"Content-Type": "application/octet-stream",
                 "Content-Disposition": 'attachment; filename="heroes.7z"'},
                content=b"7z\xbc\xaf\x27\x1cmod",
            ),
        },
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"heroes.7z": {"modules/m.mod": b"M"}}
    )
    dlg = _at_the_plan(qtbot, controller)
    # Answer the CEP question with the archive's recommendation.
    next(
        b for b in dlg._choice_groups["CEP"].buttons()
        if b.property("requirement_name") == "CEP3"
    ).setChecked(True)
    # CEP3 has no Vault URL, so untick it and install the module alone.
    for index in range(dlg.plan_tree.topLevelItemCount()):
        dlg.plan_tree.topLevelItem(index).setCheckState(0, Qt.CheckState.Unchecked)
    dlg._on_install()
    qtbot.waitUntil(lambda: not dlg._busy, timeout=10000)
    assert dlg.result_tree.topLevelItemCount() == 1
    assert dlg.result_tree.topLevelItem(0).text(0) == "A Call For Heroes"
    assert "is installed" in dlg.status.text()
    assert controller.pd.mod_item("A Call For Heroes").is_installer()


# -- off the UI thread -------------------------------------------------------- #
class _GatedHttpClient(FakeHttpClient):
    """Holds a transfer open until the test lets go, so the UI can be watched."""

    def __init__(self, responses):
        super().__init__(responses)
        self.gate = threading.Event()
        self.started = threading.Event()

    def download(self, url, dest, *, on_chunk=None, timeout=300):
        self.started.set()
        for index in range(1, 500):
            if on_chunk is not None:
                on_chunk(index, 500)
            if self.gate.wait(0.005):
                break
        return super().download(url, dest, on_chunk=on_chunk, timeout=timeout)


def _ready_to_install(qtbot, tmp_path):
    """A dialog with everything answered, whose archive download can be held open."""
    controller = _controller(tmp_path)
    controller._http = _GatedHttpClient({
        **_responses(),
        download_url("1hWArchiveAA"): HttpResponse(
            download_url("1hWArchiveAA"), 200,
            {"Content-Type": "application/octet-stream",
             "Content-Disposition": 'attachment; filename="heroes.7z"'},
            content=b"7z\xbc\xaf\x27\x1cmod",
        ),
    })
    dlg = _at_the_plan(qtbot, controller)
    next(
        b for b in dlg._choice_groups["CEP"].buttons()
        if b.property("requirement_name") == "CEP3"
    ).setChecked(True)
    for index in range(dlg.plan_tree.topLevelItemCount()):
        dlg.plan_tree.topLevelItem(index).setCheckState(0, Qt.CheckState.Unchecked)
    return controller, dlg


def test_installing_does_not_block_the_ui_thread(qtbot, tmp_path):
    """These archives run to 83 MB; the window has to stay alive while one lands."""
    controller, dlg = _ready_to_install(qtbot, tmp_path)
    dlg._on_install()
    assert dlg._busy  # returned with the transfer still running
    assert controller._http.started.wait(5)
    assert not dlg.install_button.isEnabled()
    assert not dlg.cancel_button.isHidden()
    qtbot.waitUntil(lambda: "of 500 B" in dlg.status.text(), timeout=5000)
    controller._http.gate.set()
    qtbot.waitUntil(lambda: not dlg._busy, timeout=10000)
    assert dlg.cancel_button.isHidden()
    assert "is installed" in dlg.status.text()


def test_cancelling_an_install_keeps_no_part_file(qtbot, tmp_path):
    controller, dlg = _ready_to_install(qtbot, tmp_path)
    dlg._on_install()
    assert controller._http.started.wait(5)
    dlg._on_cancel()
    qtbot.waitUntil(lambda: not dlg._busy, timeout=10000)
    assert "Cancelled" in dlg.status.text()
    downloads = (
        tmp_path / "Profiles" / "P" / "A Call For Heroes" / C.DOWNLOADS_DIR
    )
    assert not list(downloads.glob("*")) if downloads.is_dir() else True


def test_the_dialog_will_not_close_mid_install(qtbot, tmp_path):
    controller, dlg = _ready_to_install(qtbot, tmp_path)
    dlg._on_install()
    assert controller._http.started.wait(5)
    dlg.reject()
    assert "Cancel the install first" in dlg.status.text()
    controller._http.gate.set()
    qtbot.waitUntil(lambda: not dlg._busy, timeout=10000)


def test_the_install_phases_report_after_the_download(qtbot, tmp_path):
    """The archive lands, then extracting and installing it must keep talking."""
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path)
    controller._http = FakeHttpClient({
        **_responses(),
        download_url("1hWArchiveAA"): HttpResponse(
            download_url("1hWArchiveAA"), 200,
            {"Content-Type": "application/octet-stream",
             "Content-Disposition": 'attachment; filename="heroes.7z"'},
            content=b"7z\xbc\xaf\x27\x1cmod",
        ),
    })
    controller._extractor = FakeArchiveExtractor(
        contents={"heroes.7z": {"modules/m.mod": b"M"}}
    )
    dlg = _at_the_plan(qtbot, controller)
    next(
        b for b in dlg._choice_groups["CEP"].buttons()
        if b.property("requirement_name") == "CEP3"
    ).setChecked(True)
    for index in range(dlg.plan_tree.topLevelItemCount()):
        dlg.plan_tree.topLevelItem(index).setCheckState(0, Qt.CheckState.Unchecked)

    said: list[str] = []
    real = dlg._on_phase
    dlg._on_phase = lambda label, done, total: (
        real(label, done, total), said.append(label)
    )
    dlg._on_install()
    qtbot.waitUntil(lambda: not dlg._busy, timeout=10000)
    assert "Extracting heroes.7z" in said
    assert "Building the installer" in said
    assert "Installing files" in said
    # The phase line names the step it belongs to, not just the phase.
    assert "A Call For Heroes" in dlg._step_label
