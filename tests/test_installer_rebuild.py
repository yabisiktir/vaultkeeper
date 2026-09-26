"""Rebuilding a mod's installer after its source changed (VB ``CreateInstaller``).

NIT uninstalls an installed mod (without its dependencies), removes the old
installer and its file records, then builds a fresh one — so a file that has
left the mod's source leaves the installer and the game. Vaultkeeper only copied
the new files over the old installer: a deleted source file stayed in the
installer and in the game (logic audit, docs/logic_audit/stage2_findings.md U3).

NIT never rebuilds a restorer, and treats a mod with no source files as one, so
neither may lose its payload here.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _mod_folder(tmp_path: Path, mod: str) -> Path:
    return tmp_path / "Profiles" / "P" / mod


def _write(folder: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _alpha(c: ProfileController, tmp_path: Path) -> Path:
    c.create_mod("Alpha Pack")
    folder = _mod_folder(tmp_path, "Alpha Pack")
    _write(folder, {"alpha.hak": "v1", "music/mus_alpha.bmu": "tune"})
    assert c.build_installer_payload("Alpha Pack")["ok"]
    return folder


def test_file_removed_from_source_leaves_installer_and_game(
    tmp_path: Path, recycle_bin: Path
) -> None:
    c = _controller(tmp_path)
    folder = _alpha(c, tmp_path)
    c.install(["Alpha Pack"])
    music = c.ctx.game_folders["music"] / "mus_alpha.bmu"
    assert music.exists()

    (folder / "music" / "mus_alpha.bmu").unlink()
    _write(folder, {"alpha.hak": "v2", "alpha_new.hak": "new"})
    result = c.build_installer_payload("Alpha Pack")

    assert result["ok"]
    installer = folder / C.MOD_INSTALLER_DIR
    assert not (installer / "music" / "mus_alpha.bmu").exists()
    assert (installer / "hak" / "alpha_new.hak").read_text() == "new"
    # The installed mod was taken out first: its old files are gone from the game…
    assert not music.exists()
    assert not c.pd.mod_item("Alpha Pack").installed
    # …and nothing in the database still points at the deleted file.
    assert all(fk.filename != "mus_alpha.bmu" for fk in c.pd.mod_item("Alpha Pack").files)
    # The old installer went to the recycle bin, not straight to oblivion.
    assert any(recycle_bin.iterdir())

    c.install(["Alpha Pack"])
    hak = c.ctx.game_folders["hak"]
    assert (hak / "alpha.hak").read_text() == "v2"
    assert (hak / "alpha_new.hak").read_text() == "new"
    assert not music.exists()


def test_mod_without_source_files_keeps_its_installer(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.create_mod("Installer Only")
    installer = _mod_folder(tmp_path, "Installer Only") / C.MOD_INSTALLER_DIR
    _write(installer, {"hak/kept.hak": "only copy"})

    result = c.build_installer_payload("Installer Only")

    assert not result["ok"]
    assert (installer / "hak" / "kept.hak").read_text() == "only copy"


def test_restorer_is_not_rebuilt(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    folder = _alpha(c, tmp_path)
    installer = folder / C.MOD_INSTALLER_DIR
    assert c.create_restorer("Alpha Pack")

    result = c.build_installer_payload("Alpha Pack")

    assert not result["ok"]
    assert (installer / "hak" / "alpha.hak").read_text() == "v1"
