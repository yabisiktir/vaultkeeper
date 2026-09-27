"""NIT settings whose default or meaning Vaultkeeper got wrong (logic audit 3b).

Found by mapping every NIT ``My.Settings`` value to the Vaultkeeper setting and
the code that reads it (``docs/logic_audit/stage3/map_settings.py``):

* ``BehaviourConvertBik`` (True) and ``BehaviourSelectGameMod`` (True) were
  ported as False — migrated once (settings version 3);
* ``ConfigMinPlayTime`` is 10 minutes in NIT, 1 here;
* ``BehaviourUninstallDeletes``: NIT's Delete uninstalls installed mods first,
  deletes their folders and anneals; Vaultkeeper only forgot the record;
* ``BehaviourRetainProperties``: importing a mod you have keeps your group and
  properties, replaces the old folder, and reinstalls it if it was installed.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.state import Ratings
from vaultkeeper.persistence.json_store import write_json
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, name: str = "P") -> ProfileController:
    profile_mods = tmp_path / "Profiles" / name
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / f"{name}.json",
    )


def _built(c: ProfileController, name: str, files: dict[str, str]) -> Path:
    c.create_mod(name)
    folder = c.ctx.profile_mods_dir / name
    for rel, text in files.items():
        (folder / rel).write_text(text)
    assert c.build_installer_payload(name)["ok"]
    return folder


# -- defaults ------------------------------------------------------------------ #
def test_defaults_match_nit() -> None:
    s = Settings()
    assert s.convert_bik_files and s.select_game_mod
    assert s.uninstall_before_delete and s.retain_properties_on_import
    from vaultkeeper.game.play_data_manager import PlayDataSettings

    assert PlayDataSettings().config_min_play_time == 10


def test_version_2_settings_are_migrated_once(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    write_json(path, {"version": 2, "convert_bik_files": False, "select_game_mod": False})
    loaded = load_settings(path)
    assert loaded.convert_bik_files and loaded.select_game_mod
    write_json(path, {"version": 3, "convert_bik_files": False})
    assert load_settings(path).convert_bik_files is False  # a deliberate off stays


def test_bik_movies_are_kept_when_they_cannot_be_converted(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    folder = _built(c, "Movies", {"intro.bik": "BINK"})
    payload = {p.name for p in (folder / C.MOD_INSTALLER_DIR).rglob("*") if p.is_file()}
    # Converted, or — when it cannot be — kept as it is; never left out.
    assert "intro.bik" in payload or "intro.wbm" in payload


# -- delete ----------------------------------------------------------------------- #
def test_delete_uninstalls_removes_folder_and_anneals(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)
    _built(c, "Alpha", {"shared.2da": "ALPHA", "alpha.hak": "A"})
    _built(c, "Beta", {"shared.2da": "BETA-SHARED"})
    c.install(["Beta"])
    c.install(["Alpha"])  # Alpha's shared.2da wins (later)
    override = c.ctx.game_folders["override"]

    result = c.delete_mods(["Alpha"])

    assert result["deleted"] == ["Alpha"]
    assert c.pd.mod_item("Alpha") is None
    assert not (c.ctx.profile_mods_dir / "Alpha").exists()
    assert any(recycle_bin.iterdir())
    assert not (c.ctx.game_folders["hak"] / "alpha.hak").exists()
    assert (override / "shared.2da").read_text() == "BETA-SHARED"  # annealed back


def test_delete_can_leave_files_installed(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)
    _built(c, "Alpha", {"alpha.hak": "A"})
    c.install(["Alpha"])

    c.delete_mods(["Alpha"], uninstall=False)

    assert (c.ctx.game_folders["hak"] / "alpha.hak").exists()


def test_delete_drops_the_mod_from_dependency_lists(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)
    _built(c, "Base", {"base.hak": "B"})
    _built(c, "Addon", {"addon.hak": "D"})
    c.pd.mod_item("Addon").dependencies.append("Base")

    c.delete_mods(["Base"])

    assert c.pd.mod_item("Addon").dependencies == []


# -- import ------------------------------------------------------------------------ #
def test_import_keeps_local_group_properties_and_install(tmp_path: Path, recycle_bin: Path) -> None:
    other = _controller(tmp_path / "other")
    _built(other, "Alpha", {"alpha.hak": "NEW VERSION"})
    other.pd.mod_item("Alpha").rating = Ratings(1)
    export = other.export_mods(["Alpha"], tmp_path / "out")["exported"][0]

    c = _controller(tmp_path / "mine")
    folder = _built(c, "Alpha", {"alpha.hak": "OLD", "stale.2da": "OLD"})
    c.move_to_group(["Alpha"], "200.  My Group")
    md = c.pd.mod_item("Alpha")
    md.rating = Ratings(3)
    md.web_link = "https://example.org/mine"
    c.install(["Alpha"])

    result = c.import_mods([Path(getattr(export, "path", export))])

    assert result["imported"] == ["Alpha"]
    md = c.pd.mod_item("Alpha")
    assert md.group == "200.  My Group"
    assert md.rating == Ratings(3) and md.web_link == "https://example.org/mine"
    assert not (folder / "stale.2da").exists()  # old folder replaced, not merged
    assert md.installed
    assert (c.ctx.game_folders["hak"] / "alpha.hak").read_text() == "NEW VERSION"
    assert not (c.ctx.game_folders["override"] / "stale.2da").exists()


# -- default group for downloads --------------------------------------------------- #
def test_download_group_order(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.pd.move_mods_to_group([], "000.  Restorers")
    assert c.download_group("New Mod") == C.DEFAULT_GROUP  # "810.  Evaluating"
    assert c.download_group("New Mod", "100.  Community Packs") == "100.  Community Packs"
    c.create_mod("Have It", "300.  Mine")
    assert c.download_group("Have It", "100.  Community Packs") == "300.  Mine"


def test_the_dialog_does_not_default_to_the_first_group(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

    c = _controller(tmp_path)
    for g in ("000.  Restorers", "100.  Community Packs"):
        c.pd.move_mods_to_group([], g)
    dlg = DownloadProjectDialog(c)
    qtbot.addWidget(dlg)
    dlg._apply_project_rule({"mod_folder": "", "group": "", "excluded": 0})
    assert dlg.group_combo.currentText() == C.DEFAULT_GROUP
