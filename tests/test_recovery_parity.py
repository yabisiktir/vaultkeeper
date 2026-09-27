"""Backups and recovery tools as NIT runs them (logic audit 3c).

* Validate Profile Data is NIT's Validate Installed Data + Validate Mods; VK's
  only pruned dependencies.
* Validate Installed Data runs ``ValidateInstalledFileData`` too: records that
  point at deleted mods / mod files are repaired and the owner re-resolved.
* Restore Data: NIT restarts, so the restored database is checked against the
  game on load; VK trusted the backup's picture of the game.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _built(c: ProfileController, name: str, files: dict[str, str]) -> None:
    c.create_mod(name)
    for rel, text in files.items():
        (c.ctx.profile_mods_dir / name / rel).write_text(text)
    assert c.build_installer_payload(name)["ok"]


def test_restore_is_checked_against_the_game(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _built(c, "Alpha", {"alpha.hak": "A"})
    backup = tmp_path / "backup.zip"
    c.backup_data(backup)  # Alpha not installed in the backup
    c.install(["Alpha"])

    c.restore_data(backup)

    assert c.pd.mod_item("Alpha").mod_state == State.INSTALLED


def test_validate_installed_data_repairs_records_of_a_forgotten_mod(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _built(c, "Alpha", {"alpha.hak": "A"})
    c.install(["Alpha"])
    # Damage: the mod definition goes, its installed record still names it.
    del c.pd.mod_list["Alpha"]

    c.validate_installed_data()

    ifd = next(i for k, i in c.pd.installed_list.items() if k.filename == "alpha.hak")
    assert ifd.installer != "Alpha"
    assert ifd.mod_files == []


def test_validate_profile_data_runs_both_validations(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    message = c.validate_profile_data()
    assert "Installed File Data" in message and "Validated mods" in message
