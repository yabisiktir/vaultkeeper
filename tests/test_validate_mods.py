"""Tests for Validate Mods (VB ``MsValidateMods`` / ``ValidateMods``).

Covers the orphaned-notes cleanup (``ValidateNotes``), the per-mod
``nwnpatch.ini`` create/delete from patch-folder haks (``HakPatchManager.
ValidateMod``), and the composite ``validate_mods`` pass.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    return controller


def _add_hak(controller: ProfileController, mod: str, folder: str, name: str) -> None:
    inst = controller.ctx.profile_mods_dir / mod / C.MOD_INSTALLER_DIR / folder
    inst.mkdir(parents=True, exist_ok=True)
    (inst / name).write_bytes(b"HAK")
    controller.pd.scan_mod_files(controller.pd.mod_item(mod), controller.ctx.profile_mods_dir)


# -- ValidateNotes ---------------------------------------------------------- #


def test_validate_notes_removes_orphans(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Real")
    notes_dir = controller.mod_notes_path("_").parent
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "Real.rtf").write_text("{}", encoding="utf-8")  # kept — mod exists
    (notes_dir / "Ghost.rtf").write_text("{}", encoding="utf-8")  # orphan
    assert controller.validate_notes() == 1
    assert (notes_dir / "Real.rtf").is_file()
    assert not (notes_dir / "Ghost.rtf").exists()


def test_validate_notes_keeps_note_when_folder_exists(tmp_path: Path) -> None:
    """A notes file whose mod folder exists (row not yet added) is kept."""
    controller = _controller(tmp_path)
    (controller.ctx.profile_mods_dir / "Pending").mkdir()
    notes_dir = controller.mod_notes_path("_").parent
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "Pending.rtf").write_text("{}", encoding="utf-8")
    assert controller.validate_notes() == 0
    assert (notes_dir / "Pending.rtf").is_file()


# -- Per-mod patch ini ------------------------------------------------------ #


def test_patch_ini_created_from_patch_haks(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _add_hak(controller, "Mod", "patch", "cep1patch.hak")
    _add_hak(controller, "Mod", "patch", "cep2patch.hak")

    result = controller._validate_mod_patch_ini(controller.pd.mod_item("Mod"))
    assert result == "created"
    ini = (
        controller.ctx.profile_mods_dir
        / "Mod"
        / C.MOD_INSTALLER_DIR
        / C.MOD_ROOT_FOLDER
        / C.PATCH_INI_FILE
    )
    assert ini.is_file()
    text = ini.read_text(encoding="utf-8")
    assert "[Patch]" in text
    assert "PatchFile000=cep1patch" in text
    assert "PatchFile001=cep2patch" in text
    # The ini is now a tracked file of the mod.
    assert any(fk.filename == C.PATCH_INI_FILE for fk in controller.pd.mod_item("Mod").files)


def test_patch_ini_deleted_when_no_patch_haks(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _add_hak(controller, "Mod", "hak", "content.hak")  # a hak, but not in patch folder
    # Pre-create a stale mod ini and register it.
    ini = (
        controller.ctx.profile_mods_dir
        / "Mod"
        / C.MOD_INSTALLER_DIR
        / C.MOD_ROOT_FOLDER
        / C.PATCH_INI_FILE
    )
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("[Patch]\n", encoding="utf-8")
    controller.pd.scan_mod_files(controller.pd.mod_item("Mod"), controller.ctx.profile_mods_dir)

    result = controller._validate_mod_patch_ini(controller.pd.mod_item("Mod"))
    assert result == "deleted"
    assert not ini.exists()
    assert not any(fk.filename == C.PATCH_INI_FILE for fk in controller.pd.mod_item("Mod").files)


def test_patch_ini_skips_ini_only_installer(tmp_path: Path) -> None:
    """A mod with no hak files is left alone (INI-only installer guard)."""
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _add_hak(controller, "Mod", "tlk", "world.tlk")  # not a hak
    assert controller._validate_mod_patch_ini(controller.pd.mod_item("Mod")) == "none"


# -- Composite -------------------------------------------------------------- #


def test_validate_mods_composite(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _add_hak(controller, "Mod", "patch", "p.hak")
    message = controller.validate_mods()
    assert "Patch INI created: 1" in message
    assert "Validated mods" in message
