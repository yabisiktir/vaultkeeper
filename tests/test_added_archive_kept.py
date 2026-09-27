"""An archive made into a mod is kept in the mod's ``_Downloads`` (logic audit A1).

NIT's ``ModPaste`` extracts the archive into the new mod and then copies — or,
with "Use Move (rather than Copy) when adding files", moves — the archive itself
into ``<mod>\\_Downloads`` (``SetModPasteTarget``). Vaultkeeper extracted it and
kept nothing, so once the user tidied their download folder the mod had no
original left to rebuild from.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c._extractor = FakeArchiveExtractor(contents={"cool_mod.7z": {"hak/c.hak": b"C"}})
    return c


def _download(tmp_path: Path) -> Path:
    source = tmp_path / "Downloads" / "cool_mod.7z"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"ARCHIVE")
    return source


def _kept(c: ProfileController) -> Path:
    return c.ctx.profile_mods_dir / "cool_mod" / C.DOWNLOADS_DIR / "cool_mod.7z"


def test_add_mods_from_files_moves_the_archive_by_default(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    source = _download(tmp_path)

    c.add_mods_from_files([source])

    assert _kept(c).read_bytes() == b"ARCHIVE"
    assert not source.exists()  # NIT's default: Move rather than Copy


def test_add_mods_from_files_copies_when_move_is_off(tmp_path: Path) -> None:
    settings = load_settings(None)
    settings.use_move_on_add = False
    save_settings(settings, None)
    c = _controller(tmp_path)
    source = _download(tmp_path)

    c.add_mods_from_files([source])

    assert _kept(c).read_bytes() == b"ARCHIVE"
    assert source.exists()


def test_a_pasted_archive_is_copied_into_downloads(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    source = _download(tmp_path)

    result = c.paste_mod_sources([source])

    assert result["created"] == ["cool_mod"]
    assert _kept(c).read_bytes() == b"ARCHIVE"
    assert source.exists()  # a paste leaves the clipboard's original alone
    assert (c.ctx.profile_mods_dir / "cool_mod" / "hak" / "c.hak").is_file()


def test_the_installer_builds_once_from_both_copies(tmp_path: Path) -> None:
    """The extracted files and the kept archive hold the same file; NIT scans
    ``_Downloads`` too, and the installer carries it once."""
    c = _controller(tmp_path)
    c.add_mods_from_files([_download(tmp_path)])

    result = c.build_installer_payload("cool_mod")

    assert result["ok"]
    installer = c.ctx.profile_mods_dir / "cool_mod" / C.MOD_INSTALLER_DIR
    payload = sorted(
        p.relative_to(installer).as_posix()
        for p in installer.rglob("*")
        if p.is_file() and p.suffix != ".nitins"
    )
    assert payload == ["hak/c.hak"]
