"""Finding and validating a mod's Vault page.

The rule these tests exist to hold: a page is identified by the *files* a mod
already holds, never by how much its name resembles a title — and where the
evidence is ambiguous, nothing is chosen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.api import ApiProject, FoundProject
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.mod_links import (
    LinkFinding,
    ModLinkInput,
    Verdict,
    check_link,
    find_candidates,
    report_text,
    search_name,
    summary_line,
    validate_links,
)
from vaultkeeper.vault.scraper_info import VaultScraperInfo


def _rules() -> DownloadRules:
    return DownloadRules.from_text(
        "VaultDomain = //neverwintervault.org/project\n"
        "OldVaultDomain = //neverwintervault.net/project\n"
        "RoloVaultDomain = //neverwintervault.org/rolovault\n"
        "FindLinkIgnorePrefixes = cmp,ctp,cpp\n"
        "VaultProjectTypes\nnwn1\nnwnee\nEnd VaultProjectTypes\n"
        "ExceptionUrls\nhttps://neverwintervault.org/cep\nEnd ExceptionUrls\n"
    )


def _project(project_id, title, link, files=(), canonical=None) -> ApiProject:
    return ApiProject(
        project_id=project_id,
        title=title,
        link=canonical or link,
        files=[VaultScraperInfo(filename=name) for name in files],
    )


class FakeApi:
    """The two questions the link finder asks, and nothing else."""

    def __init__(self, hits=(), projects=()):
        self._hits = list(hits)
        self._by_id = {p.project_id: p for p in projects}
        self._by_url = {p.link: p for p in projects}
        self.searched: list[str] = []
        self.fetched: list[int] = []

    def search_by_title(self, title):
        self.searched.append(title)
        return list(self._hits)

    def project_by_id(self, project_id, *, description=False):
        self.fetched.append(project_id)
        return self._by_id.get(project_id)

    def project_by_url(self, url, *, description=False):
        return self._by_url.get(url)


# -- reducing a folder name to a searchable title ------------------------------ #
class TestSearchName:
    def test_a_packager_prefix_is_dropped(self):
        assert search_name("CTP Almraiven", _rules()) == "Almraiven"

    def test_an_enhanced_edition_suffix_is_dropped(self):
        assert search_name("Almraiven (EE)", _rules()) == "Almraiven"

    def test_cep_version_marks_are_removed(self):
        assert search_name("CEP v3.x", _rules()) == "CEP 3"

    def test_project_q_is_named_for_its_archive_page(self):
        assert search_name("Project Q v1.3", _rules()) == "Project Q Archive"

    def test_an_ordinary_name_is_left_alone(self):
        assert search_name("Aielund Saga Act I", _rules()) == "Aielund Saga Act I"

    def test_a_prefix_that_is_only_a_word_start_is_not_stripped(self):
        """"CTPManor" is not the CTP prefix — the prefix is a whole word."""
        assert search_name("CTPManor", _rules()) == "CTPManor"


# -- identifying the page by the files the mod holds --------------------------- #
class TestFindCandidates:
    def test_a_shared_filename_identifies_the_page(self):
        api = FakeApi(
            hits=[FoundProject(1, "Almraiven", "https://v/project/nwn1/module/almraiven")],
            projects=[
                _project(1, "Almraiven", "https://v/project/nwn1/module/almraiven",
                         files=["almraiven.rar", "almraivenhak.rar"])
            ],
        )
        mod = ModLinkInput("Almraiven", filenames=("almraivenhak.rar",), is_module=True)
        found = find_candidates(mod, api, _rules())
        assert [c.url for c in found] == ["https://v/project/nwn1/module/almraiven"]

    def test_a_matching_title_with_no_matching_file_is_only_a_suggestion(self):
        """Repackaged archives rename the files, so the page can be right anyway.

        It is offered — and marked, so nothing writes it without being asked.
        """
        api = FakeApi(
            hits=[FoundProject(1, "Almraiven", "https://v/project/nwn1/module/almraiven")],
            projects=[_project(1, "Almraiven", "https://v/project/nwn1/module/almraiven",
                               files=["something-else.rar"])],
        )
        mod = ModLinkInput("Almraiven", filenames=("almraiven.rar",), is_module=True)
        found = find_candidates(mod, api, _rules())
        assert [(c.title, c.matched) for c in found] == [("Almraiven", "title")]
        assert not found[0].is_evidence

    def test_a_title_that_only_resembles_the_mod_is_not_offered_at_all(self):
        """Resemblance is not evidence, and near-enough is not a name."""
        api = FakeApi(
            hits=[FoundProject(1, "Almraiven II", "https://v/project/nwn1/module/almraiven-2")],
            projects=[_project(1, "Almraiven II", "https://v/project/nwn1/module/almraiven-2",
                               files=["other.rar"])],
        )
        mod = ModLinkInput("Almraiven", filenames=("almraiven.rar",), is_module=True)
        assert find_candidates(mod, api, _rules()) == []

    def test_evidence_wins_over_a_name(self):
        """A page holding the mod's own file beats one that merely shares its name."""
        hits = [
            FoundProject(1, "Almraiven", "https://v/project/nwn1/module/almraiven"),
            FoundProject(2, "Almraiven Redux", "https://v/project/nwn1/module/redux"),
        ]
        projects = [
            _project(1, "Almraiven", hits[0].link, files=["other.rar"]),
            _project(2, "Almraiven Redux", hits[1].link, files=["almraiven.rar"]),
        ]
        mod = ModLinkInput("Almraiven", filenames=("almraiven.rar",), is_module=True)
        found = find_candidates(mod, FakeApi(hits, projects), _rules())
        assert [(c.title, c.matched) for c in found] == [("Almraiven Redux", "files")]

    def test_a_hakpak_page_is_not_offered_for_a_module(self):
        api = FakeApi(
            hits=[FoundProject(2, "Almraiven Hakpack", "https://v/project/nwn1/hakpak/alm")],
            projects=[_project(2, "Almraiven Hakpack", "https://v/project/nwn1/hakpak/alm",
                               files=["shared.rar"])],
        )
        mod = ModLinkInput("Almraiven", filenames=("shared.rar",), is_module=True)
        assert find_candidates(mod, api, _rules()) == []
        assert api.fetched == []  # rejected before a request was spent on it

    def test_a_module_page_is_not_offered_for_a_hakpak(self):
        api = FakeApi(
            hits=[FoundProject(1, "Almraiven", "https://v/project/nwn1/module/almraiven")],
            projects=[_project(1, "Almraiven", "https://v/project/nwn1/module/almraiven",
                               files=["shared.rar"])],
        )
        mod = ModLinkInput("Almraiven Hak", filenames=("shared.rar",), is_module=False)
        assert find_candidates(mod, api, _rules()) == []

    def test_filenames_match_regardless_of_case(self):
        api = FakeApi(
            hits=[FoundProject(1, "X", "https://v/project/nwn1/module/x")],
            projects=[_project(1, "X", "https://v/project/nwn1/module/x", files=["Mod.RAR"])],
        )
        mod = ModLinkInput("X", filenames=("mod.rar",), is_module=True)
        assert len(find_candidates(mod, api, _rules())) == 1

    def test_several_pages_are_all_returned_with_the_prelude_first(self):
        """Three Selendi chapters share files; no ranking can settle which."""
        hits = [
            FoundProject(2, "Selendi 2", "https://v/project/nwn1/module/selendi-2"),
            FoundProject(1, "Selendi Prelude", "https://v/project/nwn1/module/selendi-1"),
        ]
        projects = [
            _project(2, "Selendi 2", "https://v/project/nwn1/module/selendi-2",
                     files=["selendi.hak"]),
            _project(1, "Selendi Prelude", "https://v/project/nwn1/module/selendi-1",
                     files=["selendi.hak"]),
        ]
        mod = ModLinkInput("Selendi", filenames=("selendi.hak",), is_module=True)
        found = find_candidates(mod, FakeApi(hits, projects), _rules())
        assert [c.title for c in found] == ["Selendi Prelude", "Selendi 2"]

    def test_a_mod_holding_nothing_can_still_be_named(self):
        api = FakeApi(
            hits=[FoundProject(1, "X", "https://v/project/nwn1/module/x")],
            projects=[_project(1, "X", "https://v/project/nwn1/module/x", files=["a.rar"])],
        )
        found = find_candidates(ModLinkInput("X", is_module=True), api, _rules())
        assert [c.matched for c in found] == ["title"]

    def test_an_unreadable_project_is_skipped_rather_than_fatal(self):
        api = FakeApi(hits=[FoundProject(9, "Gone", "https://v/project/nwn1/module/gone")])
        mod = ModLinkInput("Gone", filenames=("a.rar",), is_module=True)
        assert find_candidates(mod, api, _rules()) == []


# -- validating a link that is already recorded -------------------------------- #
class TestCheckLink:
    def test_a_link_the_vault_confirms_needs_no_attention(self):
        url = "https://neverwintervault.org/project/nwn1/module/almraiven"
        api = FakeApi(projects=[_project(1, "Almraiven", url)])
        finding = check_link(ModLinkInput("Almraiven", web_link=url), api, _rules())
        assert finding.verdict is Verdict.OK

    def test_a_migrated_link_is_reported_with_its_new_address(self):
        """The .net to .org migration, which is most of what this pass finds."""
        old = "https://neverwintervault.net/project/nwn1/module/almraiven"
        new = "https://neverwintervault.org/project/nwn1/module/almraiven"
        # Asked about the old address, the Vault answers with the new one.
        api = FakeApi(projects=[_project(1, "Almraiven", old, canonical=new)])
        api._by_url = {old: api._by_id[1]}
        finding = check_link(ModLinkInput("Almraiven", web_link=old), api, _rules())
        assert finding.verdict is Verdict.REVISED
        assert (finding.current, finding.suggested) == (old, new)
        assert finding.actionable

    def test_a_vault_link_the_vault_does_not_know_is_invalid(self):
        url = "https://neverwintervault.org/project/nwn1/module/gone"
        finding = check_link(ModLinkInput("Gone", web_link=url), FakeApi(), _rules())
        assert finding.verdict is Verdict.INVALID
        assert not finding.actionable

    def test_an_invalid_link_with_one_match_is_offered_a_replacement(self):
        url = "https://neverwintervault.org/project/nwn1/module/gone"
        good = "https://neverwintervault.org/project/nwn1/module/moved"
        api = FakeApi(
            hits=[FoundProject(1, "Moved", good)],
            projects=[_project(1, "Moved", good, files=["a.rar"])],
        )
        mod = ModLinkInput("Moved", web_link=url, filenames=("a.rar",), is_module=True)
        finding = check_link(mod, api, _rules())
        assert (finding.verdict, finding.suggested) == (Verdict.REVISED, good)

    def test_a_rolovault_link_is_reported_as_never_migrated(self):
        url = "https://neverwintervault.org/rolovault/projects/nwn1/modules/x.zip"
        finding = check_link(ModLinkInput("X", web_link=url), FakeApi(), _rules())
        assert finding.verdict is Verdict.ROLOVAULT

    def test_a_link_somewhere_else_entirely_is_left_alone(self):
        url = "https://www.nexusmods.com/neverwinter/mods/824"
        finding = check_link(ModLinkInput("X", web_link=url), FakeApi(), _rules())
        assert finding.verdict is Verdict.NON_VAULT
        assert not finding.actionable

    def test_a_mod_with_no_link_is_reported_when_it_could_have_one(self):
        finding = check_link(ModLinkInput("X", eligible=True), FakeApi(), _rules())
        assert finding.verdict is Verdict.NO_LINK

    def test_a_restorer_with_no_link_is_not_a_problem(self):
        """A restorer holds the game's own files; there is no page to find."""
        finding = check_link(ModLinkInput("Restorer", eligible=False), FakeApi(), _rules())
        assert finding.verdict is Verdict.OK

    def test_several_matches_are_recorded_but_never_chosen(self):
        hits = [
            FoundProject(1, "Selendi 1", "https://neverwintervault.org/project/nwn1/module/s1"),
            FoundProject(2, "Selendi 2", "https://neverwintervault.org/project/nwn1/module/s2"),
        ]
        projects = [
            _project(1, "Selendi 1", hits[0].link, files=["s.hak"]),
            _project(2, "Selendi 2", hits[1].link, files=["s.hak"]),
        ]
        mod = ModLinkInput("Selendi", filenames=("s.hak",), is_module=True)
        finding = check_link(mod, FakeApi(hits, projects), _rules())
        assert finding.verdict is Verdict.NO_LINK  # not resolved
        assert len(finding.candidates) == 2
        assert not finding.actionable


# -- the pass over every mod --------------------------------------------------- #
class TestValidateLinks:
    def test_only_mods_needing_attention_are_reported(self):
        url = "https://neverwintervault.org/project/nwn1/module/ok"
        api = FakeApi(projects=[_project(1, "Ok", url)])
        mods = [
            ModLinkInput("Fine", web_link=url),
            ModLinkInput("Elsewhere", web_link="https://example.com/x"),
        ]
        findings = validate_links(mods, api, _rules())
        assert [(f.mod, f.verdict) for f in findings] == [
            ("Elsewhere", Verdict.NON_VAULT)
        ]

    def test_progress_is_reported_per_mod(self):
        seen = []
        mods = [ModLinkInput(f"M{i}", eligible=False) for i in range(3)]
        validate_links(mods, FakeApi(), _rules(), on_progress=lambda d, t: seen.append((d, t)))
        assert seen == [(1, 3), (2, 3), (3, 3)]


class TestReport:
    def test_every_section_appears_even_when_empty(self):
        text = report_text([], 10)
        for heading in (
            "Revised Vault Web Links",
            "Non-Migrated Rolovault Web Links",
            "Invalid Vault Web Links",
            "Mods with no Web Link",
            "Non-Vault Web Links",
        ):
            assert heading in text
        assert text.count("None.") == 5

    def test_a_revision_shows_both_addresses(self):
        finding = LinkFinding("Almraiven", Verdict.REVISED, current="http://old", suggested="http://new")
        text = report_text([finding], 1)
        assert "Almraiven: http://old" in text
        assert "Correct link: http://new" in text

    def test_the_summary_counts_each_kind(self):
        findings = [
            LinkFinding("a", Verdict.REVISED, suggested="x"),
            LinkFinding("b", Verdict.NON_VAULT),
            LinkFinding("c", Verdict.NON_VAULT),
        ]
        line = summary_line(findings, 10)
        assert "processed: 10" in line
        assert "Revised: 1" in line
        assert "Non-Vault: 2" in line


# -- the controller ------------------------------------------------------------ #
def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _use_api() -> None:
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings(None)
    settings.vault_download_method = "api"
    settings.vault_rules_online = False
    save_settings(settings, None)


def test_the_evidence_excludes_the_installer_payload(tmp_path):
    """The installer is our own copy of the mod — matching it matches nothing."""
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    mod_dir = tmp_path / "Profiles" / "P" / "My Mod"
    (mod_dir / C.DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    (mod_dir / C.DOWNLOADS_DIR / "almraiven.rar").write_bytes(b"x")
    payload = mod_dir / C.MOD_INSTALLER_DIR / "hak"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "installed.hak").write_bytes(b"y")

    md = ctrl.pd.mod_item("My Mod")
    names = ctrl._mod_link_input(md).filenames
    assert "almraiven.rar" in names
    assert "installed.hak" not in names


def test_finding_a_link_needs_the_api(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings(None)
    settings.vault_download_method = "scrape"
    save_settings(settings, None)
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    result = ctrl.find_mod_web_link("My Mod")
    assert not result["ok"]
    assert "API" in result["message"]


def test_applying_revisions_writes_only_the_actionable_ones(tmp_path):
    _use_api()
    ctrl = _controller(tmp_path)
    ctrl.create_mod("Moved")
    ctrl.create_mod("Fine")
    ctrl.set_mod_web_link("Fine", "https://neverwintervault.org/project/nwn1/module/fine")
    findings = [
        LinkFinding("Moved", Verdict.REVISED, current="http://old", suggested="http://new"),
        LinkFinding("Fine", Verdict.NON_VAULT, current="http://elsewhere"),
    ]
    result = ctrl.apply_mod_link_revisions(findings)
    assert result["applied"] == 1
    assert ctrl.mod_web_link("Moved") == "http://new"
    assert ctrl.mod_web_link("Fine").endswith("/module/fine")  # untouched


def test_an_unknown_mod_is_reported_not_raised(tmp_path):
    _use_api()
    ctrl = _controller(tmp_path)
    assert not ctrl.find_mod_web_link("Nope")["ok"]


@pytest.mark.parametrize(
    "url,is_project,is_rolo",
    [
        ("https://neverwintervault.org/project/nwn1/module/x", True, False),
        ("https://neverwintervault.org/project/nwnee/module/x", True, False),
        ("https://neverwintervault.net/project/nwn1/hakpak/cep", True, False),
        ("https://neverwintervault.org/rolovault/projects/nwn1/x.zip", False, True),
        ("https://neverwintervault.org/cep", True, False),  # a listed exception
        ("https://www.nexusmods.com/neverwinter/mods/824", False, False),
        ("", False, False),
    ],
)
def test_url_classification(url, is_project, is_rolo):
    rules = _rules()
    assert rules.is_vault_project_url(url) is is_project
    assert rules.is_rolovault_url(url) is is_rolo


# -- the screens ---------------------------------------------------------------- #
def test_the_three_commands_are_on_the_menus_with_the_original_captions(qtbot):
    """The VB captions, mnemonics and icons — a text button is not a port."""
    from vaultkeeper.ui import resources as R
    from vaultkeeper.ui.menu_bar import NitMenuBar

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    assert bar.action("MsFindWebLink").text() == "Find Mod's Web Page Lin&k"
    assert bar.action("MsCheckForUpdates").text() == "Check for Mod &Updates"
    assert bar.action("MsValidateModWebLinks").text() == "Validate Mod Web &Links"
    assert R.icon_exists("DynamicWebSite_16x")


def _window(tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    return MainWindow(ctrl), ctrl


def test_check_for_updates_needs_a_link(qtbot, tmp_path):
    _use_api()
    win, ctrl = _window(tmp_path)
    qtbot.addWidget(win)
    win.selected_mod_names = lambda: ["My Mod"]
    win._on_check_for_mod_updates()
    assert "no web page link" in win.nit_status.mg_info.text()


def test_check_for_updates_opens_the_project_on_the_mods_own_link(qtbot, tmp_path):
    from vaultkeeper.vault.http import FakeHttpClient, HttpResponse

    _use_api()
    win, ctrl = _window(tmp_path)
    qtbot.addWidget(win)
    link = "https://neverwintervault.org/project/nwn1/module/mine"
    ctrl.set_mod_web_link("My Mod", link)
    query = (
        "https://neverwintervault.org/api/v1/projects/by-url?url="
        "https%3A%2F%2Fneverwintervault.org%2Fproject%2Fnwn1%2Fmodule%2Fmine"
    )
    payload = (
        '{"project_id": 4, "title": "Mine", "attachments": ['
        '{"filename": "mine.7z", "link": "http://cdn/mine.7z", "size_bytes": 9}]}'
    )
    ctrl._http = FakeHttpClient({query: HttpResponse(query, 200, text=payload)})
    win.selected_mod_names = lambda: ["My Mod"]
    win._on_check_for_mod_updates()
    dlg = win._download_dialog
    qtbot.addWidget(dlg)
    assert dlg.url_edit.text() == link
    assert dlg.file_tree.topLevelItemCount() == 1  # already fetched, not just filled in


def test_the_report_dialog_offers_an_update_only_for_definite_revisions(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.mod_links_report import ModLinksReportDialog

    _use_api()
    ctrl = _controller(tmp_path)
    ctrl.create_mod("Moved")
    dlg = ModLinksReportDialog(ctrl)
    qtbot.addWidget(dlg)
    dlg._on_done(
        {
            "ok": True,
            "summary": "Mod links processed: 2.",
            "report": "the report",
            "findings": [
                LinkFinding("Moved", Verdict.REVISED, current="http://old", suggested="http://new"),
                LinkFinding("Odd", Verdict.NO_LINK),
            ],
        }
    )
    assert dlg.update_button.isEnabled()
    assert dlg.update_button.text() == "Update 1 Link"

    dlg._on_update = lambda: None  # the message box would block
    result = ctrl.apply_mod_link_revisions(dlg._findings)
    assert result["applied"] == 1
    assert ctrl.mod_web_link("Moved") == "http://new"


def test_the_report_dialog_says_so_when_the_api_is_not_in_use(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.mod_links_report import ModLinksReportDialog

    ctrl = _controller(tmp_path)
    dlg = ModLinksReportDialog(ctrl)
    qtbot.addWidget(dlg)
    dlg._on_done({"ok": False, "message": "needs the Vault's API"})
    assert not dlg.update_button.isEnabled()
    assert "API" in dlg.report.toPlainText()


def test_a_name_only_match_is_never_written_by_the_batch_pass():
    """The pass writes links to every mod at once; a guess would go to all of them."""
    hit = FoundProject(1, "Cormyrean Nights", "https://neverwintervault.org/project/nwn1/module/cn")
    api = FakeApi(
        hits=[hit],
        projects=[_project(1, "Cormyrean Nights", hit.link, files=["cormyrean_nights.zip"])],
    )
    # A PRC-ified repack: the Vault's own filename is nowhere in the mod folder.
    mod = ModLinkInput(
        "Cormyrean Nights",
        filenames=("Cormyrean Nights [PRC8-CEP3].7z",),
        is_module=True,
    )
    finding = check_link(mod, api, _rules())
    assert finding.verdict is Verdict.NO_LINK
    assert not finding.actionable  # offered, not applied
    assert [c.matched for c in finding.candidates] == ["title"]
    assert "matched by name only" in report_text([finding], 1)
