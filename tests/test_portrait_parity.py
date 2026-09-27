"""Portrait Manager, as NIT does it (logic audit stage 3g).

NIT's Apply Excludes adds each marked portrait's five files to the mod's wizard
``InstallerExcludes`` and runs Create Installer with installer-restore forced on
(``RbApplyExcludes_Click``), so the portrait leaves the installer *and* the game.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController

_SIZES = ("h", "l", "m", "s", "t")


def _files(*resrefs: str) -> dict[str, bytes]:
    return {
        f"portraits/{r}{s}.tga": f"{r}{s}".encode() for r in resrefs for s in _SIZES
    }


def _controller(tmp_path: Path, *, in_archive: bool) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Heroes")
    mod = profile_mods / "Heroes"
    if in_archive:
        c._extractor = FakeArchiveExtractor(contents={"heroes.7z": _files("po_a", "po_b")})
        (mod / C.DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
        (mod / C.DOWNLOADS_DIR / "heroes.7z").write_bytes(b"7z")
    else:
        for name, data in _files("po_a", "po_b").items():
            (mod / name).parent.mkdir(parents=True, exist_ok=True)
            (mod / name).write_bytes(data)
    assert c.build_installer_payload("Heroes")["ok"]
    c.install(["Heroes"])
    return c


def _installed(c: ProfileController) -> set[str]:
    return {p["resref"] for p in c.installed_portraits_report()["portraits"]}


def test_apply_excludes_removes_the_portrait_from_the_game(tmp_path: Path) -> None:
    c = _controller(tmp_path, in_archive=False)
    assert _installed(c) == {"po_a", "po_b"}

    result = c.exclude_portraits_from_installer("Heroes", ["po_a"])

    assert result["ok"] and result["excluded"] == 5
    assert _installed(c) == {"po_b"}
    files = {fk.filename for fk in c.pd.mod_item("Heroes").files}
    assert "po_ah.tga" not in files and "po_bh.tga" in files
    assert not (c.ctx.game_folders["portraits"] / "po_ah.tga").exists()


def test_apply_excludes_reaches_portraits_inside_an_archive(tmp_path: Path) -> None:
    """NIT builds the exclude list with archives extracted (``ExtractArchives``)."""
    c = _controller(tmp_path, in_archive=True)
    assert _installed(c) == {"po_a", "po_b"}

    result = c.exclude_portraits_from_installer("Heroes", ["po_a"])

    assert result["ok"] and result["excluded"] == 5
    assert _installed(c) == {"po_b"}


def test_create_installer_button_rebuilds_with_restore(qtbot, monkeypatch) -> None:
    """VB ``RbCreateInstaller`` runs PerformCreateInstaller with restore forced on."""
    from PySide6.QtWidgets import QMessageBox

    from tests.test_portrait_manager import _controller as fake
    from tests.test_portrait_manager import _portraits
    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    controller = fake(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dlg._on_create_installer()

    assert controller.calls["installer"] and controller.calls["installer"][0][1] is True


def test_an_override_texture_ending_in_h_is_not_a_portrait(tmp_path: Path) -> None:
    """VB ``IsPortraitFile``: outside ``portraits`` the m and t sizes must be there."""
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Loose")
    override = profile_mods / "Loose" / C.MOD_INSTALLER_DIR / "override"
    override.mkdir(parents=True)
    (override / "tno_brickh.tga").write_bytes(b"x")
    for size in _SIZES:
        (override / f"po_ovr{size}.tga").write_bytes(b"x")
    c.create_installer("Loose")
    c.install(["Loose"])

    listed = {p["resref"] for p in c.installed_portraits_report(include_override=True)["portraits"]}

    assert listed == {"po_ovr"}


def test_edit_opens_the_mods_source_files(tmp_path: Path) -> None:
    """VB ``RbEditPortrait`` edits the ``_Downloads`` source, not the game's copy."""
    c = _controller(tmp_path, in_archive=False)
    downloads = tmp_path / "Profiles" / "P" / "Heroes" / C.DOWNLOADS_DIR / "art"
    downloads.mkdir(parents=True)
    for size in _SIZES:
        (downloads / f"po_a{size}.tga").write_bytes(b"src")
    entry = next(p for p in c.installed_portraits_report()["portraits"] if p["resref"] == "po_a")

    assert c.portrait_edit_files(entry) == [downloads / f"po_a{s}.tga" for s in "hlmst"]

    other = next(p for p in c.installed_portraits_report()["portraits"] if p["resref"] == "po_b")
    assert all(p.parent == c.ctx.game_folders["portraits"] for p in c.portrait_edit_files(other))
