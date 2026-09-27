"""Install wizards defined by the download rules (logic audit R3).

38 published projects carry an installer wizard in the rules file — Custom
Menus' choice of menu screen, Project Q's version picker, Facelift's optional
tilesets. NIT falls back to it wherever a mod has no wizard file of its own
(``WizardInfo.Load`` → ``GetWizardInfo``: Create Installer, the install worker,
Wizard Builder…); Vaultkeeper read only wizard files, so these mods installed
every variant at once.

Many of those wizards point *inside* an archive
(``aribeth_4.7z\\override_1.79.8191+``). NIT extracts each archive into a folder
named after it, so such an entry names a real folder; Vaultkeeper extracted into
``x0000`` folders, where no wizard entry could ever match.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.download_rules import DownloadRules

RULES = """
Project = Custom Menus
\tWizardTitle = Custom Menus Installer Wizard
\tExtractArchives
\tSelectOne = Choose which custom menu screen you want to use.
\t\tmenus.7z\\old_menu > Old Menu
\t\tmenus.7z\\new_menu > New Menu
\t\tplain.zip > Plain Menu
\tEnd SelectOne
\tInstallerExcludes
\t\textras.zip
\tEnd InstallerExcludes
End Project

Project = Facelift On The Vault
\tModFolder = Facelift
\tSelectMany = Pick the optional parts.
\t\tpart_a.zip > Part A = Checked
\t\tpart_b.zip > Part B = Unchecked
\tEnd SelectMany
End Project

Project = Lonely
\tSelectOne = Only one here.
\t\tonly.zip > Only
\tEnd SelectOne
End Project
"""

EXTRACTOR = FakeArchiveExtractor(
    contents={
        "menus.7z": {
            "old_menu/menu_old.2da": b"OLD",
            "new_menu/menu_new.2da": b"NEW",
        },
        "plain.zip": {"menu_plain.2da": b"PLAIN"},
        "extras.zip": {"extra.2da": b"EXTRA"},
    }
)


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c._download_rules = DownloadRules.from_text(RULES)
    c._extractor = EXTRACTOR
    return c


def _menus_mod(c: ProfileController, tmp_path: Path) -> Path:
    c.create_mod("Custom Menus")
    downloads = tmp_path / "Profiles" / "P" / "Custom Menus" / C.DOWNLOADS_DIR
    downloads.mkdir(parents=True, exist_ok=True)
    for name in ("menus.7z", "plain.zip", "extras.zip"):
        (downloads / name).write_bytes(b"archive")
    return downloads


def _installed_payload(c: ProfileController, mod: str) -> set[str]:
    installer = c.ctx.profile_mods_dir / mod / C.MOD_INSTALLER_DIR
    return {p.name for p in installer.rglob("*") if p.is_file() and p.suffix != ".nitins"}


def test_the_rules_wizard_is_offered_when_the_mod_has_none(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)

    prompt = c.wizard_install_prompt("Custom Menus")

    assert prompt["run_wizard"]
    assert prompt["title"] == "Custom Menus Installer Wizard"
    assert [x["display"] for x in prompt["choices"]] == ["Old Menu", "New Menu", "Plain Menu"]
    assert c.wizard_report("Custom Menus")["source"] == "rules"


def test_a_choice_inside_an_archive_installs_only_that_folder(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)

    result = c.build_installer_payload("Custom Menus", wizard_choice="menus.7z\\new_menu")

    assert result["ok"]
    # The chosen folder only: not the other folder of the same archive, not the
    # other choice's archive, and never the InstallerExcludes archive.
    assert _installed_payload(c, "Custom Menus") == {"menu_new.2da"}


def test_a_plain_archive_choice(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)

    c.build_installer_payload("Custom Menus", wizard_choice="plain.zip")

    assert _installed_payload(c, "Custom Menus") == {"menu_plain.2da"}


def test_found_by_mod_folder_and_select_many_defaults(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Facelift")

    prompt = c.wizard_install_prompt("Facelift")

    assert [(p["key"], p["checked"]) for p in prompt["preferences"]] == [
        ("part_a.zip", True),
        ("part_b.zip", False),
    ]


def test_a_lone_choice_is_no_wizard(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Lonely")
    assert c.wizard_install_prompt("Lonely") == {"run_wizard": False}


def test_the_mods_own_wizard_file_wins(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)
    (c.ctx.profile_mods_dir / "Custom Menus" / C.WIZARD_FILE).write_text(
        "WizardTitle = Mine\nInstallerExcludes\n\tplain.zip\nEnd InstallerExcludes\n"
    )

    prompt = c.wizard_install_prompt("Custom Menus")

    assert prompt["title"] == "Mine" and prompt["choices"] == []
    assert c.wizard_report("Custom Menus")["source"] == "file"


def test_no_rules_wizard_when_the_rules_are_off(tmp_path: Path) -> None:
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings(None)
    settings.vault_apply_project_rules = False
    save_settings(settings, None)
    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)

    assert c.wizard_install_prompt("Custom Menus") == {"run_wizard": False}


def test_the_bundled_rules_define_34_wizards(tmp_path: Path) -> None:
    """34 in the bundled file; the live file (2,602 lines) has 38, as NIT parses it."""
    from vaultkeeper.vault import rules_source

    c = _controller(tmp_path)
    c._download_rules = DownloadRules.from_text(rules_source.bundled_rules_text())
    running = [t for t, r in c._download_rules.projects.items() if c.rule_wizard(r.title)]
    assert len(running) == 34
    menus = c.rule_wizard("Custom Menus")
    assert menus.extract_archives and len(menus.select_one) > 1


def test_wizard_builder_opens_on_the_rules_wizard(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder

    c = _controller(tmp_path)
    _menus_mod(c, tmp_path)
    dlg = WizardBuilder(c, "Custom Menus")
    qtbot.addWidget(dlg)

    assert dlg.title_edit.text() == "Custom Menus Installer Wizard"
    assert dlg.choices.count() == 3
    assert "download rules" in dlg.summary.text()
    assert not dlg.delete_button.isEnabled()  # nothing on disk to delete
