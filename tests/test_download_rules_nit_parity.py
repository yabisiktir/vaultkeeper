"""The Vault download rules, read and applied as NIT does (logic audit R2, R1c, R4, R5).

Vaultkeeper parsed only a project's folder, group, Excludes, Downloads and
RequiredProjects, and applied none of the file-wide exclusions. Measured against
NIT's own parse of the same rules file (docs/logic_audit/stage1_findings.md 1c):

- R2  ``If EE Downloads`` / ``If NWN Downloads`` were dropped, so both Community
  Patch projects lost their mod folder and archive;
- R1c ``ExcludeFiles From <project>`` was ignored (a test module, a trailer…);
- R4  ``RequiredFiles From <project>`` (only these files of a prerequisite);
- R5  ``IgnoreExcludes``, ``IncludeExtensions``, ``ExcludeDirectLinks``,
  ``ExcludeRequiredProjects``, ``ExternalFile``;
- and the description / file-type exclusions ("outdated", "(Mac)", ``.txt``)
  were parsed by nobody.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.scraper_info import VaultScraperInfo

RULES = """
ExcludeRules
\tContains
\t\toutdated
\t\t"Do not use"
\tEnd Contains
\tStartsWith
\t\t"Mac "
\tEnd StartsWith
\tEndsWith
\t\t" old"
\tEnd EndsWith
\tExtensions
\t\t.txt
\tEnd Extensions
\tExcludeFiles From Arena Tileset
\t\tarena.mod
\tEnd ExcludeFiles
End ExcludeRules

Project = Community Patch 1.72
\tGroup = 100.  Community Packs
\tIf NWN Downloads
\t\tModFolder = CPP Community Patch
\t\tpatch_169.7z
\tEnd If
\tIf EE Downloads
\t\tModFolder = CPP Community Patch (EE)
\t\tpatch_ee.7z
\tEnd If
End Project

Project = D20 Modern
\tIf ERF Downloads
\t\td20_update_erf.rar
\tEnd If
End Project

Project = Old Files
\tIgnoreExcludes
\tDownloads
\t\tkept.txt
\t\tancient.7z
\tEnd Downloads
End Project

Project = Walkthroughs
\tIncludeExtensions
\t\t.txt
\tEnd IncludeExtensions
End Project

Project = Sanctum
\tDownloads
\t\tsanctum_hak.7z
\tEnd Downloads
\tIf EE Downloads
\t\tModFolder = Sanctum (EE)
\t\tExternalFile = http://example.org/dl/sanctum_ee_mod.7z
\tEnd If
\tRequiredProjects
\t\thttps://neverwintervault.org/project/nwn1/hakpak/tileset/community-tileset-project
\tEnd RequiredProjects
\tRequiredFiles From Community Tileset Project
\t\tctp_common.7z
\tEnd RequiredFiles
\tExcludeRequiredProjects
\t\tUnwanted Thing
\tEnd ExcludeRequiredProjects
\tExcludeDirectLinks
\t\thttps://neverwintervault.org/sites/files/dup.zip
\tEnd ExcludeDirectLinks
End Project
"""


def _rules() -> DownloadRules:
    return DownloadRules.from_text(RULES)


# -- parsing ------------------------------------------------------------------ #
def test_edition_blocks_choose_the_folder_and_the_archive() -> None:
    rules = _rules()
    ee = rules.rule_for_game("Community Patch 1.72", is_ee=True)
    classic = rules.rule_for_game("Community Patch 1.72", is_ee=False)
    assert (ee.mod_folder, ee.downloads) == ("CPP Community Patch (EE)", ["patch_ee.7z"])
    assert (classic.mod_folder, classic.downloads) == ("CPP Community Patch", ["patch_169.7z"])
    # The stored rule is untouched: each profile asks for its own.
    assert rules.project_rule("Community Patch 1.72").downloads == []


def test_erf_files_are_held_back_by_default() -> None:
    rule = _rules().rule_for_game("D20 Modern", is_ee=True)
    assert rule.excludes == ["d20_update_erf.rar"]
    included = _rules().rule_for_game("D20 Modern", is_ee=True, exclude_erf=False)
    # NIT adds ERF files to the wanted list only when there is one already.
    assert included.excludes == [] and included.downloads == []


def test_an_external_file_is_fetched_and_wanted() -> None:
    rule = _rules().rule_for_game("Sanctum", is_ee=True)
    assert rule.mod_folder == "Sanctum (EE)"
    assert rule.external_files == ["http://example.org/dl/sanctum_ee_mod.7z"]
    assert rule.wanted("sanctum_ee_mod.7z") and rule.wanted("sanctum_hak.7z")


def test_ignore_excludes_does_not_swallow_the_next_block() -> None:
    """A bare ``IgnoreExcludes`` used to open a swallowed block, eating Downloads."""
    rule = _rules().project_rule("Old Files")
    assert rule.apply_excludes is False
    assert rule.downloads == ["kept.txt", "ancient.7z"]


def test_prerequisite_rules_are_read() -> None:
    rule = _rules().project_rule("Sanctum")
    assert rule.required_files == {"community tileset project": ["ctp_common.7z"]}
    assert rule.exclude_required_projects == ["Unwanted Thing"]
    assert rule.exclude_direct_links == ["https://neverwintervault.org/sites/files/dup.zip"]


def test_file_wide_exclusions() -> None:
    rules = _rules()
    assert rules.is_excluded("Arena Tileset", "ARENA.MOD")  # no Project block needed
    assert rules.is_excluded("Anything", "readme.txt")
    assert not rules.is_excluded("Walkthroughs", "guide.txt")  # IncludeExtensions
    assert rules.is_excluded("Anything", "a.7z", "Outdated build")
    assert rules.is_excluded("Anything", "a.7z", "Mac version")
    assert rules.is_excluded("Anything", "a.7z", "Version 1 old")
    assert not rules.is_excluded("Anything", "a.7z", "The module")


# -- the published file -------------------------------------------------------- #
def _published() -> DownloadRules:
    from vaultkeeper.vault import rules_source

    return DownloadRules.from_text(rules_source.bundled_rules_text())


def test_published_community_patch_has_a_folder_on_each_edition() -> None:
    rules = _published()
    for title in ("Community Patch 1.72", "Community Patch Project"):
        assert rules.rule_for_game(title, is_ee=True).mod_folder
        assert rules.rule_for_game(title, is_ee=False).mod_folder
        assert (
            rules.rule_for_game(title, is_ee=True).downloads
            != rules.rule_for_game(title, is_ee=False).downloads
        )


def test_published_file_wide_rules_are_read() -> None:
    rules = _published()
    assert "outdated" in rules.exclude_contains
    assert ".txt" in rules.exclude_extensions
    assert rules.is_excluded("Arena Tileset", "arena.mod")
    assert rules.project_rule("Project Q Archive").downloads  # not eaten by IgnoreExcludes


# -- applied to a fetched project --------------------------------------------- #
def _controller(tmp_path: Path, *, is_ee: bool = True) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=is_ee,
    )
    c._download_rules = _rules()
    return c


def _files(*names: str, description: dict | None = None) -> list[VaultScraperInfo]:
    description = description or {}
    return [
        VaultScraperInfo(filename=n, description=description.get(n, n), counter_url=f"http://cdn/{n}")
        for n in names
    ]


def test_a_project_is_listed_for_the_profiles_edition(tmp_path: Path) -> None:
    files = _files("patch_169.7z", "patch_ee.7z")
    ee = _controller(tmp_path / "ee")._apply_project_rules("Community Patch 1.72", files, [])
    classic = _controller(tmp_path / "nwn", is_ee=False)._apply_project_rules(
        "Community Patch 1.72", files, []
    )
    assert ee["mod_folder"] == "CPP Community Patch (EE)"
    assert [f.filename for f in ee["files"]] == ["patch_ee.7z"]
    assert classic["mod_folder"] == "CPP Community Patch"
    assert [f.filename for f in classic["files"]] == ["patch_169.7z"]


def test_file_wide_exclusions_apply_to_a_project_with_no_rule(tmp_path: Path) -> None:
    files = _files("mod.7z", "readme.txt", "mac.7z", description={"mac.7z": "Mac build"})
    result = _controller(tmp_path)._apply_project_rules("Some Module", files, [])
    assert [f.filename for f in result["files"]] == ["mod.7z"]
    assert result["excluded"] == 2


def test_ignore_excludes_keeps_what_would_be_excluded(tmp_path: Path) -> None:
    files = _files("kept.txt", "ancient.7z", "other.7z", description={"ancient.7z": "outdated"})
    result = _controller(tmp_path)._apply_project_rules("Old Files", files, [])
    assert [f.filename for f in result["files"]] == ["kept.txt", "ancient.7z"]


def test_external_file_and_prerequisite_rules(tmp_path: Path) -> None:
    required = [
        {"title": "Unwanted Thing", "url": "https://neverwintervault.org/project/nwn1/x/unwanted"},
        {"title": "dup.zip", "url": "https://neverwintervault.org/sites/files/dup.zip"},
    ]
    result = _controller(tmp_path)._apply_project_rules(
        "Sanctum", _files("sanctum_hak.7z", "other.7z"), required
    )
    names = [f.filename for f in result["files"]]
    assert names == ["sanctum_ee_mod.7z", "sanctum_hak.7z"]
    assert result["files"][0].direct_url == "http://example.org/dl/sanctum_ee_mod.7z"
    assert [r["title"] for r in result["required"]] == ["Community Tileset Project"]
    assert result["required"][0]["only_files"] == ["ctp_common.7z"]


def test_a_per_file_prerequisite_overrides_its_own_rules(tmp_path: Path, monkeypatch) -> None:
    c = _controller(tmp_path)
    files = _files("ctp_common.7z", "ctp_other.7z", "notes.txt")

    def fetch(url, *, only_files=None):
        return c._apply_project_rules("Community Tileset Project", files, [], only_files=only_files)

    monkeypatch.setattr(c, "fetch_vault_project", fetch)
    bundles = c.expand_prerequisites(
        [{"title": "Community Tileset Project", "type": "project",
          "url": "https://neverwintervault.org/project/nwn1/hakpak/tileset/ctp",
          "only_files": ["ctp_common.7z"]}]
    )
    assert [f.filename for f in bundles[0]["files"]] == ["ctp_common.7z"]
