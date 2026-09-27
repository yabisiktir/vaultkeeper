"""Download selection for prerequisites, as NIT's Download Project does it.

Logic audit 1c follow-up: both apps were given the same Vault projects (23,
covering every rule feature) and their offered files compared. Three gaps:

* the rules' Redirects were not applied to prerequisite (or project) URLs, so
  the Aielund Saga offered the superseded Abyss Tileset, not Abyss Tileset Redux;
* a prerequisite the rules add was named from its URL ("Sands Fate 2 Gem
  Tower") even after it had been fetched, which is also its folder name;
* prerequisites a prerequisite's own rule adds were not followed (VB
  ``ProcessRulesAddAndExcludes`` recurses), so Sinister Inc. 2 lacked the Fixed
  CTP Loadscreens that the Community Tileset Project rule adds.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.scraper_info import VaultScraperInfo

V = "https://neverwintervault.org/project/nwn1/"

RULES = f"""
Redirects
\tFrom {V}hakpak/tileset/abyss-tileset
\tTo {V}hakpak/tileset/abyss-tileset-redux
End Redirects

Project = Saga
\tRequiredProjects
\t\t{V}module/saga-two
\tEnd RequiredProjects
End Project

Project = Saga Two
\tRequiredProjects
\t\t{V}module/saga-one
\t\t{V}hakpak/extra-bits
\tEnd RequiredProjects
End Project
"""

PAGES = {
    f"{V}module/saga-two": ("Saga Two", ["two.7z"]),
    f"{V}module/saga-one": ("Saga", ["one.7z"]),
    f"{V}hakpak/extra-bits": ("Extra Bits", ["bits.7z"]),
    f"{V}hakpak/tileset/abyss-tileset-redux": ("Abyss Tileset Redux", ["abyss_v21.7z"]),
    f"{V}hakpak/tileset/abyss-tileset": ("Abyss Tileset", ["abyss.rar"]),
}


def _controller(tmp_path: Path, monkeypatch) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=True,
    )
    c._download_rules = DownloadRules.from_text(RULES)
    fetched = []

    def fetch(url, *, only_files=None):
        fetched.append(url)
        title, names = PAGES[url]
        files = [VaultScraperInfo(filename=n, description=n, counter_url=f"http://cdn/{n}")
                 for n in names]
        return c._apply_project_rules(title, files, [], only_files=only_files)

    monkeypatch.setattr(c, "fetch_vault_project", fetch)
    c.fetched = fetched
    return c


def test_a_redirected_prerequisite_is_fetched_from_its_new_page(tmp_path, monkeypatch) -> None:
    c = _controller(tmp_path, monkeypatch)
    required = [{"title": "Abyss Tileset", "url": f"{V}hakpak/tileset/abyss-tileset"}]

    result = c._apply_project_rules("Some Module", [], required)
    bundles = c.expand_prerequisites(result["required"])

    assert [b["title"] for b in bundles] == ["Abyss Tileset Redux"]
    assert [f.filename for f in bundles[0]["files"]] == ["abyss_v21.7z"]


def test_a_rule_added_prerequisite_gets_its_real_title(tmp_path, monkeypatch) -> None:
    c = _controller(tmp_path, monkeypatch)
    result = c._apply_project_rules("Saga", [], [])
    assert result["required"][0]["title"] == "Saga Two"  # from the address, for now

    bundles = c.expand_prerequisites(result["required"], project_title="Saga")

    assert bundles[0]["title"] == "Saga Two" and bundles[0]["mod_folder"] == "Saga Two"


def test_rule_prerequisites_of_prerequisites_are_followed(tmp_path, monkeypatch) -> None:
    """Saga needs Saga Two, whose rule adds Extra Bits (and Saga, the project itself)."""
    c = _controller(tmp_path, monkeypatch)
    result = c._apply_project_rules("Saga", [], [])

    bundles = c.expand_prerequisites(
        result["required"], project_url=f"{V}module/saga-one", project_title="Saga"
    )

    assert [b["title"] for b in bundles] == ["Saga Two", "Extra Bits"]
    assert f"{V}module/saga-one" not in c.fetched  # never its own prerequisite
