"""Tests for user map overrides + persistence (VB Settings map editors, Phase 8).

Covers the Mapper override merge/remove/reset/export and the controller edit
methods that persist them to the settings file and re-apply them on load.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.ui.controller import ProfileController

# -- Mapper level ----------------------------------------------------------- #


def test_override_changes_resolution() -> None:
    mapper = Mapper()
    # .txt is not in the default extension map → unsupported.
    assert mapper.get_mapped_folder("readme.txt") == ""
    mapper.set_override("ext_mapping", ".txt", "override")
    assert mapper.get_mapped_folder("readme.txt") == "override"
    assert mapper.is_nwn_extension(".txt")


def test_exception_file_override() -> None:
    mapper = Mapper()
    mapper.set_override("exception_files", "special.hak", "patch")
    assert mapper.get_mapped_folder("special.hak") == "patch"
    assert mapper.is_override("exception_files", "SPECIAL.HAK")  # case-insensitive


def test_remove_override_restores_default() -> None:
    mapper = Mapper()
    assert mapper.exception_files.get("dialog.tlk") == "nwn"  # a default
    mapper.set_override("exception_files", "dialog.tlk", "hak")  # shadow the default
    assert mapper.exception_files["dialog.tlk"] == "hak"
    assert mapper.remove_override("exception_files", "dialog.tlk") is True
    assert mapper.exception_files["dialog.tlk"] == "nwn"  # default restored


def test_remove_non_override_is_noop() -> None:
    mapper = Mapper()
    assert mapper.remove_override("exception_files", "dialog.tlk") is False


def test_export_and_reapply_roundtrip() -> None:
    mapper = Mapper()
    mapper.set_override("ext_mapping", ".txt", "override")
    mapper.set_override("dir_mapping", "myfolder", "hak")
    exported = mapper.export_overrides()
    assert exported == {"ext_mapping": {".txt": "override"}, "dir_mapping": {"myfolder": "hak"}}

    fresh = Mapper(overrides=exported)
    assert fresh.get_mapped_folder("readme.txt") == "override"
    assert fresh.dir_mapping["myfolder"] == "hak"


def test_reset_overrides() -> None:
    mapper = Mapper()
    mapper.set_override("ext_mapping", ".txt", "override")
    mapper.reset_overrides()
    assert mapper.get_mapped_folder("readme.txt") == ""
    assert mapper.export_overrides() == {}


# -- Settings persistence --------------------------------------------------- #


def test_settings_map_overrides_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings()
    settings.map_overrides = {"ext_mapping": {".txt": "override"}}
    save_settings(settings, path)
    assert load_settings(path).map_overrides == {"ext_mapping": {".txt": "override"}}


# -- Controller edit + persist --------------------------------------------- #


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        settings_path=tmp_path / "settings.json",
    )


def test_controller_set_and_persist(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.set_map_file_exception("special.hak", "patch")
    # Live mapper updated.
    assert controller.ctx.mapper.get_mapped_folder("special.hak") == "patch"
    # Persisted to settings.
    saved = load_settings(tmp_path / "settings.json").map_overrides
    assert saved == {"exception_files": {"special.hak": "patch"}}
    # And re-applied on a fresh load.
    reloaded = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        map_overrides=saved,
    )
    assert reloaded.ctx.mapper.get_mapped_folder("special.hak") == "patch"


def test_controller_report_flags_overrides(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.set_map_folder("myfolder", "hak")
    folders = {f["source"]: f for f in controller.folder_mapping_report()["folders"]}
    assert folders["myfolder"]["override"] is True
    assert folders["override"]["override"] is False  # a default entry


def test_controller_remove_and_reset(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.set_map_extension("xyz", "override")  # no leading dot → normalised
    assert controller.ctx.mapper.get_mapped_folder("a.xyz") == "override"
    assert controller.remove_map_override("ext_mapping", ".xyz") is True
    assert controller.ctx.mapper.get_mapped_folder("a.xyz") == ""
    controller.set_map_extension(".abc", "hak")
    controller.reset_map_overrides()
    assert load_settings(tmp_path / "settings.json").map_overrides == {}


# -- Exclude overrides (VB "Excluded Items") ------------------------------- #


def test_exclude_file_override_skips_in_mapper() -> None:
    mapper = Mapper()
    assert mapper.is_excluded_file("mymod_broken.hak") is False
    mapper.add_exclude("files", "mymod_broken.hak")
    assert mapper.is_excluded_file("mymod_broken.hak") is True
    assert mapper.is_exclude_override("files", "MYMOD_BROKEN.HAK")


def test_exclude_folder_override() -> None:
    mapper = Mapper()
    mapper.add_exclude("folders", "junkstuff")
    assert mapper.is_excluded_folder("junkstuff") is True
    assert mapper.remove_exclude("folders", "junkstuff") is True
    assert mapper.is_excluded_folder("junkstuff") is False


def test_exclude_default_not_removable() -> None:
    mapper = Mapper()
    # __macosx is a default excluded folder, not a user override.
    assert mapper.is_excluded_folder("__macosx") is True
    assert mapper.remove_exclude("folders", "__macosx") is False


def test_reset_clears_excludes_and_maps_together() -> None:
    mapper = Mapper()
    mapper.set_override("ext_mapping", ".txt", "override")
    mapper.add_exclude("files", "bad.hak")
    mapper.reset_overrides()
    assert mapper.get_mapped_folder("a.txt") == ""
    assert mapper.is_excluded_file("bad.hak") is False
    assert mapper.export_exclude_overrides() == {}


def test_map_and_exclude_overrides_survive_each_others_removal() -> None:
    mapper = Mapper()
    mapper.set_override("ext_mapping", ".txt", "override")
    mapper.add_exclude("files", "bad.hak")
    # Removing the map override must not wipe the exclude (shared _reapply).
    mapper.remove_override("ext_mapping", ".txt")
    assert mapper.is_excluded_file("bad.hak") is True


def test_controller_exclude_persist_and_reload(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.add_map_exclude("files", "mymod_broken.hak")
    assert controller.ctx.mapper.is_excluded_file("mymod_broken.hak")
    saved = load_settings(tmp_path / "settings.json").map_exclude_overrides
    assert saved == {"files": ["mymod_broken.hak"]}
    reloaded = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        map_exclude_overrides=saved,
    )
    assert reloaded.ctx.mapper.is_excluded_file("mymod_broken.hak")


def test_controller_excludes_report_flags_override(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.add_map_exclude("folders", "junk")
    report = controller.map_excludes_report()
    folders = {f["name"]: f for f in report["folders"]}
    assert folders["junk"]["override"] is True
    assert folders["__macosx"]["override"] is False
