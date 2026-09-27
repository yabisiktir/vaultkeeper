"""A download that replaces old files updates the mod's wizard (VB ``UpdateWizard``).

When Download Project removes or retires files the new download replaces, NIT
rewrites the wizard's entries that name them, so the wizard keeps offering the
choice for the new file. A rules-defined wizard is saved as the mod's own only
after the user agrees. Vaultkeeper had no equivalent (logic audit, R3 follow-up).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.download_rules import DownloadRules

RULES = """
Project = Menus
\tSelectOne = Pick one.
\t\tmenus_v1_2.7z\\old > Old
\t\tmenus_v1_2.7z\\new > New
\tEnd SelectOne
End Project
"""


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c._download_rules = DownloadRules.from_text(RULES)
    return c


def _old(c: ProfileController, mod: str, name: str) -> Path:
    path = c.ctx.profile_mods_dir / mod / C.DOWNLOADS_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"old")
    return path


def test_the_mods_own_wizard_follows_a_new_version(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Alpha")
    wizard = c.ctx.profile_mods_dir / "Alpha" / C.WIZARD_FILE
    wizard.write_text(
        "SelectMany\n\talpha_v1_1.7z > Alpha\n\textras.zip > Extras\nEnd SelectMany\n"
    )
    old = _old(c, "Alpha", "alpha_v1_1.7z")

    update = c.wizard_update_for_download("Alpha", ["alpha_v1_2.7z"], [old])

    assert update["source"] == "file"
    assert "alpha_v1_2.7z > Alpha" in update["text"] and "alpha_v1_1" not in update["text"]
    assert "extras.zip" in update["text"]


def test_a_dated_release_is_matched_by_its_date(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Beta")
    (c.ctx.profile_mods_dir / "Beta" / C.WIZARD_FILE).write_text(
        "InstallerExcludes\n\tbeta_20250104.zip\nEnd InstallerExcludes\n"
    )
    old = _old(c, "Beta", "beta_20250104.zip")

    update = c.wizard_update_for_download("Beta", ["beta_20260214.zip"], [old])

    assert "beta_20260214.zip" in update["text"]


def test_a_rules_wizard_is_offered_as_the_mods_own(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Menus")
    old = _old(c, "Menus", "menus_v1_2.7z")

    update = c.wizard_update_for_download("Menus", ["menus_v1_3.7z"], [old])

    assert update["source"] == "rules"
    assert "menus_v1_3.7z\\new > New" in update["text"]
    assert c.save_wizard_text("Menus", update["text"])
    assert c.wizard_install_prompt("Menus")["choices"][1]["key"] == "menus_v1_3.7z\\new"


def test_nothing_to_change(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Alpha")
    (c.ctx.profile_mods_dir / "Alpha" / C.WIZARD_FILE).write_text(
        "InstallerExcludes\n\tother.zip\nEnd InstallerExcludes\n"
    )
    old = _old(c, "Alpha", "alpha_v1_1.7z")
    assert c.wizard_update_for_download("Alpha", ["alpha_v1_2.7z"], [old]) is None


def test_the_dialog_saves_a_rules_wizard_only_when_asked(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

    c = _controller(tmp_path)
    c.create_mod("Menus")
    old = _old(c, "Menus", "menus_v1_2.7z")
    dlg = DownloadProjectDialog(c)
    qtbot.addWidget(dlg)
    wizard = c.ctx.profile_mods_dir / "Menus" / C.WIZARD_FILE

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._update_wizard("Menus", ["menus_v1_3.7z"], [old])
    assert not wizard.exists()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg._update_wizard("Menus", ["menus_v1_3.7z"], [old])
    assert "menus_v1_3.7z" in wizard.read_text()
