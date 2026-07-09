"""Tests for the Create-Installer payload builder (VB ``CreateInstaller``).

Two layers, matching the port's discipline:

* **Analyse rules** — pure, off-disk: secondary-folder resolution, the
  ``LastWriteTime`` duplicate tie-break, the placeholder-``.mod``-size guard, and
  the excluded-file / demo-mod skips (``Analyse`` @1347).
* **Scan + extract + golden** — walk a real/synthetic mod folder, extract loose
  archives via the seam, and check the ``CopyList``/plan folders; the golden case
  is grounded on a real NIT Store mod's existing ``.Mod Installer`` layout.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.game.installer_build import (
    PLACEHOLDER_MOD_SIZE,
    CopyInfo,
    SourceFile,
    _Analyser,
    build_copy_plan,
    parse_patch_haks,
    process_patch_files,
)

NIT_STORE = Path("/Users/example/Documents/NIT Store")


def sf(path: str, *, size: int = 100, mtime: float = 1000.0) -> SourceFile:
    """A SourceFile with a synthetic (need-not-exist) path for Analyse tests."""
    return SourceFile(path=Path(path), size=size, mtime=mtime)


# --------------------------------------------------------------------------- #
# Analyse rules (pure)
# --------------------------------------------------------------------------- #


def test_simple_extension_mapping() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/cep.tlk"))
    a.analyse("Mod", sf("/mod/patch.hak"))
    assert set(a.copy_list["Mod"]) == {"tlk", "hak"}
    assert "cep.tlk" in a.copy_list["Mod"]["tlk"]
    assert "patch.hak" in a.copy_list["Mod"]["hak"]


def test_unsupported_extension_skipped() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/readme.xyz"))
    assert not a.copy_list


def test_excluded_file_recorded_and_skipped() -> None:
    a = _Analyser(Mapper())
    # gxpa_shld.tga is a default MapExcludes entry.
    a.analyse("Mod", sf("/mod/gxpa_shld.tga"))
    assert not a.copy_list
    assert a.excluded == ["gxpa_shld.tga"]


def test_demo_mod_skipped() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/demo.mod", size=PLACEHOLDER_MOD_SIZE + 1))
    assert not a.copy_list
    assert a.excluded == ["demo.mod"]


def test_last_write_time_tie_break_keeps_newer() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/a.hak", size=10, mtime=1000.0))
    a.analyse("Mod", sf("/mod/a.hak", size=20, mtime=2000.0))  # newer wins
    winner = a.copy_list["Mod"]["hak"]["a.hak"]
    assert winner.source.mtime == 2000.0 and winner.source.size == 20


def test_last_write_time_tie_break_keeps_existing_when_older() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/a.hak", size=10, mtime=2000.0))
    a.analyse("Mod", sf("/mod/a.hak", size=20, mtime=1000.0))  # older loses
    assert a.copy_list["Mod"]["hak"]["a.hak"].source.mtime == 2000.0


def test_placeholder_mod_guard_retains_larger_older_mod() -> None:
    """A newer but tiny (placeholder) .mod must not displace a larger older one."""
    a = _Analyser(Mapper())
    big_old = sf("/mod/quest.mod", size=PLACEHOLDER_MOD_SIZE + 5000, mtime=1000.0)
    tiny_new = sf("/mod/quest.mod", size=1024, mtime=2000.0)
    a.analyse("Mod", big_old)
    a.analyse("Mod", tiny_new)
    kept = a.copy_list["Mod"]["modules"]["quest.mod"]
    assert kept.source is big_old and kept.source.size > PLACEHOLDER_MOD_SIZE
    assert kept.source.mtime == 1000.0  # older large file retained


def test_placeholder_guard_allows_newer_large_mod() -> None:
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/quest.mod", size=1024, mtime=1000.0))
    big_new = sf("/mod/quest.mod", size=PLACEHOLDER_MOD_SIZE + 1, mtime=2000.0)
    a.analyse("Mod", big_new)
    assert a.copy_list["Mod"]["modules"]["quest.mod"].source is big_new


def test_secondary_folder_override_kept_in_source_dir() -> None:
    """A .tga already sitting in its secondary (override) folder stays in override."""
    mapper = Mapper()
    assert mapper.get_secondary_folder(".tga") == "override"
    a = _Analyser(mapper)
    # Parent dir == the secondary folder → GetMappedFolder returns 'override'.
    a.analyse("Mod", sf("/mod/override/skin.tga"))
    assert "override" in a.copy_list["Mod"]
    assert "skin.tga" in a.copy_list["Mod"]["override"]


def test_primary_and_secondary_reconcile_removes_primary() -> None:
    """When a file lands in both primary (portraits) and secondary (override), the
    primary entry is folded into the secondary (VB target==secondary branch)."""
    mapper = Mapper()
    a = _Analyser(mapper)
    # portraits is the primary for .tga; override the secondary.
    a.analyse("Mod", sf("/mod/po_hero.tga", size=10, mtime=1000.0))  # → portraits
    assert "portraits" in a.copy_list["Mod"]
    a.analyse("Mod", sf("/mod/override/po_hero.tga", size=10, mtime=1000.0))  # → override
    # Now a third copy whose parent == override, forcing the reconcile branch.
    a.analyse("Mod", sf("/mod/override/po_hero.tga", size=10, mtime=3000.0))
    assert "po_hero.tga" not in a.copy_list["Mod"].get("portraits", {})
    assert "po_hero.tga" in a.copy_list["Mod"]["override"]


def test_copy_list_is_case_insensitive() -> None:
    """A file differing only in case is the same CopyList slot (VB CI dedup)."""
    a = _Analyser(Mapper())
    a.analyse("Mod", sf("/mod/A.hak", mtime=1000.0))
    a.analyse("Mod", sf("/mod/a.hak", mtime=2000.0))  # newer, same slot
    assert len(a.copy_list["mod"]["HAK"]) == 1  # folder + mod keys also CI
    assert a.copy_list["Mod"]["hak"]["a.HAK"].source.mtime == 2000.0


# --------------------------------------------------------------------------- #
# ProcessPatchFiles (patch-hak reassignment)
# --------------------------------------------------------------------------- #


def test_parse_patch_haks() -> None:
    text = "[Patch]\nPatchFile000=cep1patch\nPatchFile001=cep2patch\nEmpty=\nnoequals\n"
    assert parse_patch_haks(text) == ["cep1patch.hak", "cep2patch.hak"]


def test_process_patch_files_moves_haks_to_patch_folder(tmp_path: Path) -> None:
    mapper = Mapper()
    # A real nwnpatch.ini source referencing one of two haks.
    ini = tmp_path / "nwnpatch.ini"
    ini.write_text("[Patch]\nPatchFile000=cep1patch\n", encoding="utf-8")

    a = _Analyser(mapper)
    a.analyse("Mod", SourceFile(ini, size=10, mtime=1.0))  # → nwn/nwnpatch.ini
    a.analyse("Mod", sf("/m/cep1patch.hak"))  # → hak, should move to patch
    a.analyse("Mod", sf("/m/other.hak"))  # → hak, stays
    process_patch_files(a.copy_list, mapper)

    folders = a.copy_list["Mod"]
    assert "cep1patch.hak" in folders["patch"]
    assert "cep1patch.hak" not in folders["hak"]
    assert "other.hak" in folders["hak"]


def test_process_patch_files_drops_emptied_hak_folder(tmp_path: Path) -> None:
    mapper = Mapper()
    ini = tmp_path / "nwnpatch.ini"
    ini.write_text("PatchFile000=only\n", encoding="utf-8")
    a = _Analyser(mapper)
    a.analyse("Mod", SourceFile(ini, size=10, mtime=1.0))
    a.analyse("Mod", sf("/m/only.hak"))
    process_patch_files(a.copy_list, mapper)
    assert "hak" not in a.copy_list["Mod"]
    assert "only.hak" in a.copy_list["Mod"]["patch"]


def test_process_patch_files_noop_without_ini(tmp_path: Path) -> None:
    mapper = Mapper()
    a = _Analyser(mapper)
    a.analyse("Mod", sf("/m/plain.hak"))
    process_patch_files(a.copy_list, mapper)
    assert "plain.hak" in a.copy_list["Mod"]["hak"]
    assert "patch" not in a.copy_list["Mod"]


# --------------------------------------------------------------------------- #
# Scan + extract
# --------------------------------------------------------------------------- #


def test_scan_loose_files(tmp_path: Path) -> None:
    mod = tmp_path / "Mod"
    mod.mkdir()
    (mod / "cep.tlk").write_bytes(b"x")
    (mod / "big.hak").write_bytes(b"y")
    (mod / "notes.txt").write_bytes(b"z")  # unsupported → skipped
    plan = build_copy_plan("Mod", mod, mapper=Mapper(), extractor=None)
    folders = {item.folder for item in plan.items}
    assert folders == {"tlk", "hak"}
    assert plan.files_scanned == 3  # txt scanned but not mapped


def test_scan_extracts_downloads_archive(tmp_path: Path) -> None:
    mod = tmp_path / "Mod"
    (mod / C.DOWNLOADS_DIR).mkdir(parents=True)
    (mod / C.DOWNLOADS_DIR / "pack.zip").write_bytes(b"archive")
    extractor = FakeArchiveExtractor(
        contents={"pack.zip": {"stuff.hak": b"h", "world.tlk": b"t", "read.me": b"r"}}
    )
    plan = build_copy_plan(
        "Mod", mod, mapper=Mapper(), extractor=extractor, extract_root=tmp_path / "ex"
    )
    assert plan.archives_extracted == 1
    by_name = {item.filename: item.folder for item in plan.items}
    assert by_name == {"stuff.hak": "hak", "world.tlk": "tlk"}


def test_mod_installer_folder_not_rescanned(tmp_path: Path) -> None:
    """The .Mod Installer target must never be scanned as a source."""
    mod = tmp_path / "Mod"
    (mod / C.MOD_INSTALLER_DIR / "hak").mkdir(parents=True)
    (mod / C.MOD_INSTALLER_DIR / "hak" / "old.hak").write_bytes(b"x")
    (mod / "new.hak").write_bytes(b"y")
    plan = build_copy_plan("Mod", mod, mapper=Mapper(), extractor=None)
    sources = {item.filename for item in plan.items}
    assert sources == {"new.hak"}


# --------------------------------------------------------------------------- #
# Golden test — real NIT Store mod layout
# --------------------------------------------------------------------------- #


def test_golden_cep_mod_installer_layout(tmp_path: Path) -> None:
    """Recreate a real mod's ``.Mod Installer`` files loose and confirm the builder
    maps each back to its original game folder (ground truth = the real layout)."""
    installer = NIT_STORE / "Profiles/Enhanced Edition Mods/CEP v2.x/.Mod Installer"
    if not installer.is_dir():
        import pytest

        pytest.skip("NIT Store CEP mod not present")

    # Collect (filename -> expected folder) from the real installer, ignoring the
    # nitconfig identifier folder (created separately, not a scanned source).
    expected: dict[str, str] = {}
    for folder_dir in installer.iterdir():
        if not folder_dir.is_dir() or folder_dir.name == C.MOD_NIT_DIR:
            continue
        for f in folder_dir.iterdir():
            if f.is_file():
                expected[f.name] = folder_dir.name

    assert expected, "expected some real files to validate against"

    # Recreate them loose (empty placeholders — mapping only needs the name).
    mod = tmp_path / "CEP v2.x"
    mod.mkdir()
    for filename in expected:
        (mod / filename).write_bytes(b"")

    plan = build_copy_plan("CEP v2.x", mod, mapper=Mapper(), extractor=None)
    got = {item.filename: item.folder for item in plan.items}
    assert got == expected


def test_copy_info_dataclass() -> None:
    """CopyInfo is a thin winner record."""
    s = sf("/x/a.hak")
    assert CopyInfo(source=s).source is s


# --------------------------------------------------------------------------- #
# Controller op — build_installer_payload
# --------------------------------------------------------------------------- #


def _controller(tmp_path: Path):
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_mod("My Mod")
    return controller


def test_build_installer_payload_copies_and_tracks(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(
        contents={"pack.zip": {"world.tlk": b"t"}}
    )
    mod_folder = tmp_path / "Profiles" / "P" / "My Mod"
    (mod_folder / "content.hak").write_bytes(b"HAK")
    (mod_folder / C.DOWNLOADS_DIR).mkdir(parents=True, exist_ok=True)
    (mod_folder / C.DOWNLOADS_DIR / "pack.zip").write_bytes(b"zip")

    result = controller.build_installer_payload("My Mod")
    assert result["ok"] and result["archives"] == 1
    assert result["copied"] == 2  # hak + extracted tlk

    installer = mod_folder / C.MOD_INSTALLER_DIR
    assert (installer / "hak" / "content.hak").is_file()
    assert (installer / "tlk" / "world.tlk").is_file()

    md = controller.pd.mod_item("My Mod")
    assert md.is_installer()
    filenames = {fk.filename for fk in md.files}
    assert {"content.hak", "world.tlk"} <= filenames


def test_build_installer_payload_unknown_mod(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    result = controller.build_installer_payload("Ghost")
    assert result["ok"] is False and result["copied"] == 0
