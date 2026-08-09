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
    # The published rules also contribute requirements (see the tests at the
    # end). Silence them here so these tests are about the project pages only —
    # "Swordflight" is a real project in the bundled rules.
    from vaultkeeper.vault.download_rules import DownloadRules

    c.download_rules = lambda: DownloadRules()
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

    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
    called: list[int] = []
    monkeypatch.setattr(
        controller, "auto_mod_dependencies", lambda **k: called.append(1) or {}
    )

    assert dm.run_auto_dependencies(controller, None) is None
    assert called == []


def test_the_confirmation_offers_to_find_missing_links(qtbot, controller, monkeypatch):
    """A mod with no Vault link is one Auto can say nothing about, and a store
    that never used Download Project has none — which is how it comes to report
    "no dependencies" for a shelf full of mods that plainly have some."""
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs import dependency_manager as dm

    seen: dict = {}

    def fake_exec(self) -> int:
        # Read the text now: the box (and its check box) is destroyed with the
        # dialog as soon as run_auto_dependencies returns.
        seen["label"] = self.checkBox().text()
        self.checkBox().setChecked(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    def fake_auto(**kwargs):
        seen["kwargs"] = kwargs
        return {"message": "done", "unmatched": [], "errors": [], "skipped": 0}

    monkeypatch.setattr(controller, "auto_mod_dependencies", fake_auto)

    dm.run_auto_dependencies(controller, None)
    assert "Find missing Vault links" in seen["label"]
    assert seen["kwargs"]["find_links"] is True


# -- What the published rules already know ------------------------------------- #
def _rules(text: str):
    from vaultkeeper.vault.download_rules import DownloadRules

    return DownloadRules.from_text(text)


def test_the_rules_supply_requirements_with_no_network_at_all(controller):
    """41 of the 222 published projects name their prerequisites, and the rules
    already say which mod folder a project belongs in. A mod that came from
    anywhere but Download Project has no Vault link, so this is often the only
    thing that knows anything about it."""
    controller.download_rules = lambda: _rules(
        "Project = Swordflight Chapter 1\n"
        "\tModFolder = Swordflight\n"
        "\tRequiredProjects\n"
        "\t\thttps://neverwintervault.org/project/cep2\n"
        "\tEnd RequiredProjects\n"
        "End Project\n"
        "Project = CEP 2.6\n"
        "\tModFolder = CEP 2.6\n"
        "End Project\n"
    )
    controller.project_required_projects = lambda url: []

    controller.auto_mod_dependencies()
    assert controller.pd.mod_item("Swordflight").dependencies == ["CEP 2.6"]


def test_a_rule_naming_its_own_folder_is_not_a_dependency(controller):
    """Several projects share one mod folder — chapters of the same module. A
    requirement that resolves to the mod itself is neither a dependency nor a
    missing mod, and reporting it as either is noise."""
    controller.download_rules = lambda: _rules(
        "Project = Swordflight Chapter 1\n"
        "\tModFolder = Swordflight\n"
        "\tRequiredProjects\n"
        "\t\thttps://neverwintervault.org/project/nwn1/module/swordflight\n"
        "\tEnd RequiredProjects\n"
        "End Project\n"
        "Project = Swordflight\n"
        "\tModFolder = Swordflight\n"
        "End Project\n"
    )
    controller.project_required_projects = lambda url: []

    result = controller.auto_mod_dependencies()
    assert controller.pd.mod_item("Swordflight").dependencies == []
    assert result["unmatched"] == []


# -- Saying what was *not* looked at ------------------------------------------- #
def test_the_answer_says_how_many_mods_it_knew_nothing_about(controller):
    """"Nothing needed changing" after looking at 2 of 4 mods reads as "you have
    no dependencies", which is a different and wrong answer — and is what the
    owner was told about a store where only 3 of 48 mods had a link."""
    controller.project_required_projects = lambda url: []

    result = controller.auto_mod_dependencies()

    assert result["checked"] == 2
    assert result["skipped"] == 1, "CEP 3 has no link"
    assert "have no Vault link" in result["message"]
    assert "Find Mod's Web Page Link" in result["message"]


def test_finding_missing_links_saves_only_an_unambiguous_match(controller):
    """Several candidates is a question for the user, not something to guess at
    behind their back."""
    from vaultkeeper.vault.mod_links import LinkCandidate

    def fake_find(mod_name: str) -> dict:
        if mod_name == "CEP 3":
            return {
                "ok": True,
                "candidates": [LinkCandidate(title="CEP 3", url="https://v/cep3")],
                "message": "",
            }
        return {
            "ok": True,
            "candidates": [
                LinkCandidate(title="A", url="https://v/a"),
                LinkCandidate(title="B", url="https://v/b"),
            ],
            "message": "",
        }

    controller.find_mod_web_link = fake_find
    controller.project_required_projects = lambda url: []

    result = controller.auto_mod_dependencies(find_links=True)

    assert controller.pd.mod_item("CEP 3").web_link == "https://v/cep3"
    assert result["skipped"] == 0, "the one that could be identified now counts"


# -- Progress, cancelling, and making the answer count (newtopic18) ------------- #
def test_cancelling_stops_the_run_and_says_so(controller):
    """VB warns that Cancel may take a moment because the current page finishes.
    Ours stops at the next mod, and the count reported is what was looked at —
    a run that was stopped must not read like a run that found nothing."""
    seen: list[str] = []

    def stop_after_one(done: int, total: int, label: str) -> bool:
        seen.append(label)
        return done >= 1

    controller.project_required_projects = lambda url: []
    result = controller.auto_mod_dependencies(on_progress=stop_after_one)

    assert result["cancelled"] is True
    assert result["checked"] == 1
    assert result["message"].startswith("Stopped.")
    assert len(seen) == 2, "asked before each mod, and stopped at the second"


def test_progress_reports_each_mod(controller):
    calls: list[tuple] = []
    controller.project_required_projects = lambda url: []
    controller.auto_mod_dependencies(
        on_progress=lambda done, total, label: calls.append((done, total, label)) or False
    )
    assert [c[1] for c in calls] == [2, 2]
    assert {c[2] for c in calls} == {"Swordflight", "CEP 2.6"}


def test_it_offers_to_turn_on_uninstall_dependencies(qtbot, controller, monkeypatch):
    """Knowing a mod needs CEP does nothing on its own — the preference that
    uses it is off by default, so VB asks about it once it has become useful."""
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.dialogs import dependency_manager as dm

    settings = load_settings()
    settings.uninstall_dependencies = False
    save_settings(settings)

    asked: list[str] = []

    def fake_question(parent, title, text, *a, **k):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    dm._offer_dependency_uninstall(controller, None, {"updated": 1, "cancelled": False})

    assert asked and "Uninstall Mod Dependencies" in asked[0]
    assert load_settings().uninstall_dependencies is True


def test_it_does_not_ask_when_nothing_was_found(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs import dependency_manager as dm

    asked: list[int] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.Yes,
    )
    dm._offer_dependency_uninstall(controller, None, {"updated": 0, "cancelled": False})
    dm._offer_dependency_uninstall(controller, None, {"updated": 3, "cancelled": True})
    assert asked == []


# -- The PRC hop: chosen at install time, followed by Auto afterwards ----------- #
def test_installing_a_prc_module_records_what_it_needed(qtbot, tmp_path, monkeypatch):
    """The dependencies were *settled by the user* a few clicks earlier, so this
    is the one moment they are known for certain rather than inferred. Throwing
    that away and asking the Vault for it later is doing work twice, badly.
    """
    from types import SimpleNamespace

    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.pd.add_mod(ModData(group="Adv", mod_name="Swordflight (PRC)"))

    monkeypatch.setattr(c, "scrape_project", lambda url: [SimpleNamespace(project_title="CEP 2.6")])
    monkeypatch.setattr(c, "suggested_mod_name", lambda title: title)
    monkeypatch.setattr(
        c,
        "install_downloaded_project",
        lambda files, mod, **kw: (c.pd.add_mod(ModData(group="Adv", mod_name=mod)), {
            "built": True, "install_message": "ok", "downloaded": 1, "total": 1
        })[1],
    )
    monkeypatch.setattr(
        c, "download_drive_module", lambda *a, **k: SimpleNamespace(ok=True, error="")
    )
    monkeypatch.setattr(c, "build_installer_payload", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(c, "install", lambda *a, **k: "installed")

    c.install_prc_module(
        "file-id",
        "Swordflight (PRC)",
        [SimpleNamespace(name="CEP 2.6", url="https://neverwintervault.org/cep2")],
        page_url="https://neverwintervault.org/project/swordflight",
    )

    md = c.pd.mod_item("Swordflight (PRC)")
    assert md.dependencies == ["CEP 2.6"], "settled at install time, not guessed later"
    # And the hop the owner pointed out: the module carries the Vault page it was
    # matched to, so Auto can follow that page to *its* prerequisites afterwards.
    assert md.web_link == "https://neverwintervault.org/project/swordflight"


def test_a_requirement_that_failed_to_install_is_not_recorded(qtbot, tmp_path, monkeypatch):
    """A dependency on a mod that is not there would make every later uninstall
    reason about something that does not exist."""
    from types import SimpleNamespace

    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.pd.add_mod(ModData(group="Adv", mod_name="Module"))

    monkeypatch.setattr(c, "scrape_project", lambda url: [SimpleNamespace(project_title="CEP")])
    monkeypatch.setattr(c, "suggested_mod_name", lambda title: title)
    monkeypatch.setattr(
        c,
        "install_downloaded_project",
        lambda files, mod, **kw: {
            "built": False, "install_message": "", "downloaded": 0, "total": 1
        },
    )
    monkeypatch.setattr(
        c, "download_drive_module", lambda *a, **k: SimpleNamespace(ok=True, error="")
    )
    monkeypatch.setattr(c, "build_installer_payload", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(c, "install", lambda *a, **k: "installed")

    c.install_prc_module(
        "id", "Module", [SimpleNamespace(name="CEP", url="https://v/cep")]
    )
    assert c.pd.mod_item("Module").dependencies == []
