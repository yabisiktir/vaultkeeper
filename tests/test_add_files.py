"""Add Files to Mod, and adding files to a mod's installer (logic audit, stage 3f).

adddownloadedfilestoamod.htm: "The selected files are moved to your Mod's
folder" — where Create Installer finds them. Vaultkeeper put them straight into
the ``.Mod Installer``, which the next rebuild recycles and rebuilds from the mod
folder, so they were lost; an archive landed there still packed.

NIT's other way in is pasting into a mod's Installer folder (``InstallerPaste`` →
``UpdateInstaller``): the items go through Create Installer's scan — archives
extracted, files mapped — and are added without clearing the installer.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_mod("My Mod")
    controller._extractor = FakeArchiveExtractor(
        contents={"patch.7z": {"override/fixed.2da": b"FIX", "extra.hak": b"HAK"}}
    )
    return controller


def _source(tmp_path: Path, name: str, data: bytes = b"x") -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    path = src / name
    path.write_bytes(data)
    return path


def _mod(tmp_path: Path) -> Path:
    return tmp_path / "Profiles" / "P" / "My Mod"


# -- Add Files: into the mod folder ---------------------------------------------- #
def test_add_files_go_to_the_mod_folder(tmp_path):
    controller = _controller(tmp_path)
    hak = _source(tmp_path, "content.hak")
    archive = _source(tmp_path, "patch.7z")

    assert controller.add_files_to_mod("My Mod", [hak, archive]) == 2

    assert (_mod(tmp_path) / "content.hak").is_file()
    assert (_mod(tmp_path) / "patch.7z").is_file()
    installer = _mod(tmp_path) / C.MOD_INSTALLER_DIR
    assert not [p for p in installer.rglob("*") if p.is_file()]


def test_added_files_survive_the_next_rebuild(tmp_path):
    """The bug: the rebuild recycled the installer the files had been put in."""
    controller = _controller(tmp_path)
    controller.add_files_to_mod("My Mod", [_source(tmp_path, "content.hak")])
    controller.add_files_to_mod("My Mod", [_source(tmp_path, "patch.7z")])

    assert controller.build_installer_payload("My Mod")["ok"]
    assert controller.build_installer_payload("My Mod")["ok"]  # and again

    files = {fk.filename for fk in controller.pd.mod_item("My Mod").files}
    assert {"content.hak", "fixed.2da", "extra.hak"} <= files
    assert "patch.7z" not in files  # extracted, not installed packed


def test_add_files_moves_by_default(tmp_path):
    controller = _controller(tmp_path)
    hak = _source(tmp_path, "content.hak")
    assert controller.add_files_to_mod("My Mod", [hak]) == 1
    assert not hak.exists()
    assert (_mod(tmp_path) / "content.hak").is_file()


def test_add_files_copies_when_use_move_is_off(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    controller = _controller(tmp_path)
    settings = load_settings()
    settings.use_move_on_add = False
    save_settings(settings)
    hak = _source(tmp_path, "content.hak")

    assert controller.add_files_to_mod("My Mod", [hak]) == 1
    assert hak.is_file()
    assert (_mod(tmp_path) / "content.hak").is_file()


def test_an_existing_file_is_replaced_only_with_overwrite(tmp_path):
    controller = _controller(tmp_path)
    (_mod(tmp_path) / "content.hak").write_bytes(b"OLD")

    assert controller.add_files_to_mod(
        "My Mod", [_source(tmp_path, "content.hak", b"NEW")], overwrite=False
    ) == 0
    assert (_mod(tmp_path) / "content.hak").read_bytes() == b"OLD"

    assert controller.add_files_to_mod(
        "My Mod", [_source(tmp_path, "content.hak", b"NEW")], overwrite=True
    ) == 1
    assert (_mod(tmp_path) / "content.hak").read_bytes() == b"NEW"


def test_add_files_ignores_missing(tmp_path):
    controller = _controller(tmp_path)
    assert controller.add_files_to_mod("My Mod", [tmp_path / "nope.hak"]) == 0


def test_add_files_unknown_mod(tmp_path):
    controller = _controller(tmp_path)
    assert controller.add_files_to_mod("Ghost", [_source(tmp_path, "a.hak")]) == 0


# -- Update Installer: into the installer, mapped ----------------------------------- #
def test_update_installer_maps_extracts_and_keeps_what_is_there(tmp_path):
    controller = _controller(tmp_path)
    controller.add_files_to_mod("My Mod", [_source(tmp_path, "base.hak")])
    controller.build_installer_payload("My Mod")

    result = controller.update_installer(
        "My Mod", [_source(tmp_path, "rules.2da"), _source(tmp_path, "patch.7z")]
    )

    assert result["ok"] and result["copied"] == 3 and result["archives"] == 1
    installer = _mod(tmp_path) / C.MOD_INSTALLER_DIR
    mapped = controller.ctx.mapper.get_mapped_folder
    for name in ("base.hak", "rules.2da", "fixed.2da", "extra.hak"):
        assert (installer / mapped(name) / name).is_file(), name
    files = {fk.filename for fk in controller.pd.mod_item("My Mod").files}
    assert {"base.hak", "rules.2da", "fixed.2da", "extra.hak"} <= files


def test_update_installer_scans_a_folder(tmp_path):
    controller = _controller(tmp_path)
    folder = tmp_path / "loose"
    (folder / "deep").mkdir(parents=True)
    (folder / "deep" / "one.2da").write_bytes(b"1")
    (folder / "two.hak").write_bytes(b"2")

    result = controller.update_installer("My Mod", [folder])

    assert result["copied"] == 2
    assert controller.pd.mod_item("My Mod").is_installer()


def test_update_installer_respects_overwrite(tmp_path):
    controller = _controller(tmp_path)
    controller.update_installer("My Mod", [_source(tmp_path, "rules.2da", b"OLD")])
    target = (
        _mod(tmp_path) / C.MOD_INSTALLER_DIR
        / controller.ctx.mapper.get_mapped_folder("rules.2da") / "rules.2da"
    )

    kept = controller.update_installer(
        "My Mod", [_source(tmp_path, "rules.2da", b"NEW")], overwrite=False
    )
    assert kept["skipped"] == 1 and target.read_bytes() == b"OLD"

    controller.update_installer("My Mod", [_source(tmp_path, "rules.2da", b"NEW")])
    assert target.read_bytes() == b"NEW"


def test_update_installer_move_leaves_the_archive(tmp_path):
    controller = _controller(tmp_path)
    loose = _source(tmp_path, "rules.2da")
    archive = _source(tmp_path, "patch.7z")

    controller.update_installer("My Mod", [loose, archive], move=True)

    assert not loose.exists()
    assert archive.exists()


def test_update_installer_needs_something_to_add(tmp_path):
    controller = _controller(tmp_path)
    assert not controller.update_installer("My Mod", [tmp_path / "nope"])["ok"]
    assert not controller.update_installer("Ghost", [_source(tmp_path, "a.2da")])["ok"]


def test_contents_menu_offers_the_installer_actions(qtbot, tmp_path, monkeypatch):
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._contents_mod = "My Mod"
    monkeypatch.setattr(win._contents, "selected_file", lambda: None)
    monkeypatch.setattr(win._contents, "selected_related_path", lambda: None)

    menu = win._build_contents_menu()

    labels = [a.text() for a in menu.actions()]
    assert "Paste into Installer" in labels and "Add Files to Installer…" in labels

    sent = []
    monkeypatch.setattr(win.controller, "update_installer",
                        lambda mod, paths, **kw: sent.append((mod, paths, kw))
                        or {"message": "done"})
    win._update_installer([tmp_path / "x.2da"])
    assert sent[0][0] == "My Mod" and "overwrite" in sent[0][2]
