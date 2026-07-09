"""Tests for Validate Movie Files (VB ``MsValidateMovieFiles``).

EE uses ``.wbm`` movies, so an installer's ``.bik`` files are the wrong format
(and vice-versa for classic NWN). The report lists them grouped by mod.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *, is_ee: bool = True) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=is_ee,
    )
    return controller


def _add_movie(controller: ProfileController, mod: str, name: str) -> None:
    controller.create_mod(mod)
    inst = controller.ctx.profile_mods_dir / mod / C.MOD_INSTALLER_DIR / "movies"
    inst.mkdir(parents=True, exist_ok=True)
    (inst / name).write_bytes(b"MOV")
    controller.pd.scan_mod_files(controller.pd.mod_item(mod), controller.ctx.profile_mods_dir)


def test_no_invalid_movies(tmp_path: Path) -> None:
    controller = _controller(tmp_path, is_ee=True)
    _add_movie(controller, "Mod", "intro.wbm")  # correct for EE
    report = controller.movie_files_report()
    assert report["count"] == 0
    assert report["summary"] == "Invalid movie files: None."


def test_ee_flags_bik_files(tmp_path: Path) -> None:
    controller = _controller(tmp_path, is_ee=True)
    _add_movie(controller, "Beta", "b.bik")
    _add_movie(controller, "Alpha", "a.bik")
    _add_movie(controller, "Alpha", "intro.wbm")  # valid, ignored
    report = controller.movie_files_report()
    assert report["count"] == 2
    assert report["mods"] == ["Alpha", "Beta"]  # win-sorted
    assert report["summary"] == "Invalid movie files: 2. Mods affected: 2."
    assert "a.bik" in report["text"] and "b.bik" in report["text"]
    assert "intro.wbm" not in report["text"]


def test_classic_nwn_flags_wbm_files(tmp_path: Path) -> None:
    controller = _controller(tmp_path, is_ee=False)
    _add_movie(controller, "Mod", "clip.wbm")
    _add_movie(controller, "Mod", "old.bik")  # valid for classic, ignored
    report = controller.movie_files_report()
    assert report["count"] == 1
    assert "clip.wbm" in report["text"]
    assert "old.bik" not in report["text"]


def test_dialog_renders_report(tmp_path: Path, qtbot) -> None:
    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    controller = _controller(tmp_path, is_ee=True)
    _add_movie(controller, "Mod", "bad.bik")
    report = controller.movie_files_report()
    dialog = TextViewer.show_text(report["text"], "Invalid Movie Files")
    qtbot.addWidget(dialog)
    assert "bad.bik" in dialog.editor.toPlainText()
    assert dialog.windowTitle() == "Invalid Movie Files"
