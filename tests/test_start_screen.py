"""Tests for the headless Start Screen (loadscreen) model."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game import start_screen as ss


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# -- Constants ------------------------------------------------------------- #


def test_constants_match_vb() -> None:
    assert ss.LOADSCREEN_MOD == "NWN Loadscreens (NIT Managed)"
    assert ss.AUTO_GROUP == "ZZZ.  NIT Managed Restorers (Auto)"
    assert ss.SCREEN_FOLDER == "Loadscreen Images"
    assert ss.NWN_START_SCREEN_NAME == "gui_pre_bknd3.tga"
    assert ss.OVERRIDE_FOLDER == "override"


# -- StartScreenInfo parse ------------------------------------------------- #


def test_read_info_missing_returns_none(tmp_path: Path) -> None:
    assert ss.read_start_screen_info(tmp_path) is None


def test_read_info_standard_active(tmp_path: Path) -> None:
    _write(
        tmp_path / ss.INFO_FILENAME,
        "1\nsunset.tga\ncastle.tga\n/some/browse/folder\n",
    )
    info = ss.read_start_screen_info(tmp_path)
    assert info is not None
    assert info.standard_active is True
    assert info.prefix_active is False
    assert info.standard == "sunset.tga"
    assert info.prefixed == "castle.tga"
    assert info.browse_folder == "/some/browse/folder"
    assert info.active_screen == "sunset.tga"


def test_read_info_prefixed_active(tmp_path: Path) -> None:
    _write(tmp_path / ss.INFO_FILENAME, "2\nsunset.tga\ncastle.tga\n/browse\n")
    info = ss.read_start_screen_info(tmp_path)
    assert info is not None
    assert info.prefix_active is True
    assert info.active_screen == "castle.tga"


def test_read_info_truncated_pads(tmp_path: Path) -> None:
    # A short file must not raise; missing slots default to "".
    _write(tmp_path / ss.INFO_FILENAME, "1\nonly.tga\n")
    info = ss.read_start_screen_info(tmp_path)
    assert info is not None
    assert info.standard == "only.tga"
    assert info.prefixed == ""
    assert info.browse_folder == ""
    assert info.active_screen == "only.tga"


def test_read_info_blank_type_defaults_standard(tmp_path: Path) -> None:
    _write(tmp_path / ss.INFO_FILENAME, "\na.tga\nb.tga\n/x\n")
    info = ss.read_start_screen_info(tmp_path)
    assert info is not None
    assert info.standard_active is True
    assert info.active_screen == "a.tga"


# -- Auto excludes --------------------------------------------------------- #


def test_read_auto_excludes(tmp_path: Path) -> None:
    _write(tmp_path / ss.AUTO_EXCLUDES_FILENAME, "skip1.tga\n\nskip2.tga\n")
    assert ss.read_auto_excludes(tmp_path) == ["skip1.tga", "skip2.tga"]


def test_read_auto_excludes_missing(tmp_path: Path) -> None:
    assert ss.read_auto_excludes(tmp_path) == []


def test_save_auto_excludes_sorts_and_dedups(tmp_path: Path) -> None:
    ss.save_auto_excludes(tmp_path, ["screen10.tga", "screen2.tga", "screen2.tga"])
    # Windows natural sort + dedup.
    assert ss.read_auto_excludes(tmp_path) == ["screen2.tga", "screen10.tga"]


def test_save_auto_excludes_empty_writes_empty(tmp_path: Path) -> None:
    ss.save_auto_excludes(tmp_path, ["x.tga"])
    ss.save_auto_excludes(tmp_path, [])
    assert ss.read_auto_excludes(tmp_path) == []


def test_save_auto_excludes_creates_dir(tmp_path: Path) -> None:
    target = tmp_path / "Data" / "P"  # does not exist yet
    ss.save_auto_excludes(target, ["a.tga"])
    assert ss.read_auto_excludes(target) == ["a.tga"]


# -- Scanning -------------------------------------------------------------- #


def test_scan_missing_folder(tmp_path: Path) -> None:
    assert ss.scan_loadscreens(tmp_path / "nope") == []


def test_scan_filters_and_sorts(tmp_path: Path) -> None:
    folder = tmp_path / "Loadscreen Images"
    folder.mkdir()
    (folder / "b_screen.tga").write_bytes(b"x" * 10)
    (folder / "a_screen.tga").write_bytes(b"x" * 20)
    (folder / "notes.txt").write_text("ignore me")  # non-tga skipped
    (folder / "sub").mkdir()  # directory skipped

    images = ss.scan_loadscreens(folder)
    names = [im.name for im in images]
    assert names == ["a_screen.tga", "b_screen.tga"]  # win_compare order
    assert images[0].size == 20
    assert all(not im.excluded and not im.active for im in images)


def test_scan_windows_numeric_sort(tmp_path: Path) -> None:
    folder = tmp_path / "imgs"
    folder.mkdir()
    for name in ("screen10.tga", "screen2.tga", "screen1.tga"):
        (folder / name).write_bytes(b"x")
    names = [im.name for im in ss.scan_loadscreens(folder)]
    # Natural (StrCmpLogicalW) order: 1, 2, 10 — not lexical 1, 10, 2.
    assert names == ["screen1.tga", "screen2.tga", "screen10.tga"]


# -- Prefix subsystem ------------------------------------------------------ #


def test_read_prefixes_missing(tmp_path: Path) -> None:
    assert ss.read_prefixes(tmp_path) == {}


def test_read_prefixes_enabled_and_disabled(tmp_path: Path) -> None:
    _write(tmp_path / ss.PREFIX_FILENAME, "Winter\n!Summer\n\nSpring\n")
    prefixes = ss.read_prefixes(tmp_path)
    assert prefixes == {"winter": True, "summer": False, "spring": True}


def test_file_prefix() -> None:
    assert ss.file_prefix("Winter castle.tga") == "Winter"
    assert ss.file_prefix("noSpace.tga") == "noSpace.tga"


def test_is_prefixed_and_filter_prefixed() -> None:
    prefixes = {"winter": True, "summer": False}
    assert ss.is_prefixed("Winter scene.tga", prefixes) is True
    assert ss.is_prefixed("Summer scene.tga", prefixes) is True  # defined but disabled
    assert ss.is_prefixed("Autumn scene.tga", prefixes) is False
    # Filter-prefixed requires the prefix to be enabled.
    assert ss.is_filter_prefixed("Winter scene.tga", prefixes) is True
    assert ss.is_filter_prefixed("Summer scene.tga", prefixes) is False
    assert ss.is_filter_prefixed("Autumn scene.tga", prefixes) is False


def test_scan_marks_prefixed(tmp_path: Path) -> None:
    folder = tmp_path / "imgs"
    folder.mkdir()
    for name in ("Winter a.tga", "Summer b.tga", "plain.tga"):
        (folder / name).write_bytes(b"x")
    prefixes = {"winter": True, "summer": False}
    images = {im.name: im for im in ss.scan_loadscreens(folder, prefixes=prefixes)}
    assert images["Winter a.tga"].prefixed is True
    assert images["Winter a.tga"].filter_prefixed is True
    assert images["Summer b.tga"].prefixed is True
    assert images["Summer b.tga"].filter_prefixed is False
    assert images["plain.tga"].prefixed is False


def test_scan_marks_active_and_excluded_case_insensitive(tmp_path: Path) -> None:
    folder = tmp_path / "imgs"
    folder.mkdir()
    for name in ("Active.tga", "Excluded.tga", "Plain.tga"):
        (folder / name).write_bytes(b"x")

    images = {
        im.name: im
        for im in ss.scan_loadscreens(
            folder, active="active.tga", excludes=["EXCLUDED.TGA"]
        )
    }
    assert images["Active.tga"].active is True
    assert images["Excluded.tga"].excluded is True
    assert images["Plain.tga"].active is False
    assert images["Plain.tga"].excluded is False


# -- save_start_screen_info (VB SaveInfo) ---------------------------------- #


def test_save_start_screen_info_round_trip(tmp_path: Path) -> None:
    info = ss.StartScreenInfo(
        active_type="2", standard="Std.tga", prefixed="Pfx image.tga", browse_folder="C:/x"
    )
    ss.save_start_screen_info(tmp_path, info)
    back = ss.read_start_screen_info(tmp_path)
    assert back == info
    assert back.active_screen == "Pfx image.tga"


# -- add_image_target_name (VB ProcessFiles rename @2161) ------------------ #


def test_add_image_target_keeps_normal_name(tmp_path: Path) -> None:
    assert ss.add_image_target_name("Winter.tga", tmp_path / "src") == "Winter.tga"


def test_add_image_target_renames_reserved_from_folder(tmp_path: Path) -> None:
    src = tmp_path / "My Cool Screen" / "override"
    assert ss.add_image_target_name("gui_pre_bknd3.tga", src) == "My Cool Screen.tga"


def test_add_image_target_renames_reserved_direct_parent(tmp_path: Path) -> None:
    src = tmp_path / "My Cool Screen"
    assert ss.add_image_target_name("gui_pre_bknd3.tga", src) == "My Cool Screen.tga"


# -- validate_loadscreen_name (VB ValidateName @2257) --------------------- #


def test_validate_name_blank() -> None:
    # Trailing dots are trimmed, so a dots-only name becomes blank (VB TrimEnd(".")).
    ok, msg = ss.validate_loadscreen_name("...", initial="x.tga", existing=[])
    assert not ok and "not specified" in msg


def test_validate_name_appends_extension() -> None:
    ok, value = ss.validate_loadscreen_name("Winter", initial="x.tga", existing=[])
    assert ok and value == "Winter.tga"


def test_validate_name_rejects_reserved_startscreen() -> None:
    ok, msg = ss.validate_loadscreen_name("gui_pre_bknd3.tga", initial="x.tga", existing=[])
    assert not ok and "reserved" in msg


def test_validate_name_rejects_wrong_extension() -> None:
    ok, msg = ss.validate_loadscreen_name("Winter.png", initial="x.tga", existing=[])
    assert not ok and ".tga" in msg


def test_validate_name_rejects_unchanged() -> None:
    ok, msg = ss.validate_loadscreen_name("Same.tga", initial="Same.tga", existing=[])
    assert not ok and "not been changed" in msg


def test_validate_name_rejects_existing() -> None:
    ok, msg = ss.validate_loadscreen_name(
        "New.tga", initial="Old.tga", existing=["New.tga"]
    )
    assert not ok and "already exists" in msg


def test_validate_name_case_change_allowed() -> None:
    ok, value = ss.validate_loadscreen_name("same.tga", initial="Same.tga", existing=[])
    assert ok and value == "same.tga"


# -- collect_tga_from_folders (VB ProcessFolders) -------------------------- #


def test_collect_tga_loose_and_archive(tmp_path: Path) -> None:
    root = tmp_path / "folder"
    (root / "sub").mkdir(parents=True)
    (root / "a.tga").write_bytes(b"x")
    (root / "sub" / "b.tga").write_bytes(b"x")
    (root / "readme.txt").write_bytes(b"x")
    archive = root / "pack.zip"
    archive.write_bytes(b"PK")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    (extracted_dir / "c.tga").write_bytes(b"x")
    (extracted_dir / "excluded.tga").write_bytes(b"x")

    def fake_extract(a: Path) -> Path:
        assert a == archive
        return extracted_dir

    found = ss.collect_tga_from_folders(
        [root], extract=fake_extract, exclusions={"excluded.tga"}
    )
    names = sorted(p.name for p in found)
    assert names == ["a.tga", "b.tga", "c.tga"]
