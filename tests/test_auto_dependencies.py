"""Auto Mod Dependencies (VB BtAuto / RunAutoModDependencies).

Owner-reported: the Dependency Manager showed nothing although mods plainly
depend on CEP2 and CEP3. Nothing was lost — checked against both the original
NIT store and the live one, neither had a single recorded dependency. Nothing
in the tool ever *writes* one by itself, and the one thing that would was
deferred. This is that thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.pd.add_mod(ModData(group="Adv", mod_name="Swordflight"))
    c.pd.add_mod(ModData(group="Packs", mod_name="CEP 2.6"))
    c.pd.add_mod(ModData(group="Packs", mod_name="CEP 3"))
    c.set_mod_web_link("Swordflight", "https://neverwintervault.org/project/1")
    c.set_mod_web_link("CEP 2.6", "https://neverwintervault.org/project/cep2")
    return c


def _required(controller, mapping: dict[str, list[dict]]):
    """Stand in for the Vault: url -> its required-projects list."""
    controller.project_required_projects = lambda url: mapping.get(url, [])


def test_a_requirement_is_matched_by_its_project_link(controller):
    """A link is the identity the Vault itself uses — a name is a guess."""
    _required(
        controller,
        {
            "https://neverwintervault.org/project/1": [
                {"title": "Something Else Entirely", "url": "https://neverwintervault.org/project/cep2"}
            ]
        },
    )
    result = controller.auto_mod_dependencies()

    assert result["updated"] == 1
    assert controller.pd.mod_item("Swordflight").dependencies == ["CEP 2.6"]


def test_a_requirement_is_matched_by_name_when_the_link_is_unknown(controller):
    """"CEP 3" and "CEP v3" are the same mod to a person and not to ==."""
    _required(
        controller,
        {
            "https://neverwintervault.org/project/1": [
                {"title": "CEP 3", "url": "https://neverwintervault.org/project/cep3"}
            ]
        },
    )
    controller.auto_mod_dependencies()
    assert controller.pd.mod_item("Swordflight").dependencies == ["CEP 3"]


def test_a_requirement_you_do_not_have_is_reported_not_invented(controller):
    """It means a mod is missing, which is worth saying — but it must not become
    a dependency on a mod that is not there."""
    _required(
        controller,
        {
            "https://neverwintervault.org/project/1": [
                {"title": "Project Q", "url": "https://neverwintervault.org/project/q"}
            ]
        },
    )
    result = controller.auto_mod_dependencies()

    assert controller.pd.mod_item("Swordflight").dependencies == []
    assert result["unmatched"] == ["Swordflight requires Project Q"]
    assert "do not have" in result["message"]


def test_a_mod_never_depends_on_itself(controller):
    _required(
        controller,
        {
            "https://neverwintervault.org/project/1": [
                {"title": "Swordflight", "url": "https://neverwintervault.org/project/1"}
            ]
        },
    )
    controller.auto_mod_dependencies()
    assert controller.pd.mod_item("Swordflight").dependencies == []


def test_only_mods_with_a_project_link_are_looked_up(controller):
    asked: list[str] = []
    controller.project_required_projects = lambda url: asked.append(url) or []

    result = controller.auto_mod_dependencies()

    assert sorted(asked) == [
        "https://neverwintervault.org/project/1",
        "https://neverwintervault.org/project/cep2",
    ]
    assert result["checked"] == 2


def test_no_links_at_all_says_what_to_do_about_it(tmp_path):
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.pd.add_mod(ModData(group="Adv", mod_name="Lonely"))

    result = c.auto_mod_dependencies()
    assert result["checked"] == 0
    assert "Find Mod's Web Page Link" in result["message"]


def test_a_page_that_cannot_be_read_does_not_stop_the_rest(controller):
    def flaky(url: str):
        if url.endswith("/1"):
            raise TimeoutError("the vault did not answer")
        return [{"title": "CEP 3", "url": "https://neverwintervault.org/project/cep3"}]

    controller.project_required_projects = flaky
    result = controller.auto_mod_dependencies()

    assert result["ok"] is False
    assert result["errors"] and "Swordflight" in result["errors"][0]
    assert controller.pd.mod_item("CEP 2.6").dependencies == ["CEP 3"]


def test_nothing_is_written_when_nothing_changed(controller):
    _required(
        controller,
        {
            "https://neverwintervault.org/project/1": [
                {"title": "CEP 3", "url": "https://neverwintervault.org/project/cep3"}
            ]
        },
    )
    controller.auto_mod_dependencies()
    again = controller.auto_mod_dependencies()

    assert again["updated"] == 0
    assert "Nothing needed changing." in again["message"]


# -- The dialogs --------------------------------------------------------------- #
def test_the_manager_offers_auto_and_says_so_when_empty(qtbot, controller):
    from vaultkeeper.ui.dialogs.dependency_manager import DependencyManager

    dlg = DependencyManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg.auto_button.isEnabled()
    assert "run Auto" in dlg.summary.text(), "an empty table should say what to do"


def test_declining_the_confirmation_changes_nothing(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs import dependency_manager as dm

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    called: list[int] = []
    monkeypatch.setattr(
        controller, "auto_mod_dependencies", lambda **k: called.append(1) or {}
    )

    assert dm.run_auto_dependencies(controller, None) is None
    assert called == []
