"""Coming back to the window (VB ``NIT.Monitor.ActivatedEventProcessing``).

NIT takes in what other programs changed while it was in the background: mod
folders added or removed (its file-system watcher), notes edited elsewhere, new
patch haks, and the Auto restorers. Vaultkeeper did none of it until restarted.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_a_mod_folder_added_elsewhere_is_taken_in(tmp_path: Path) -> None:
    c = _open(tmp_path)
    assert c.on_window_activated() == ""

    payload = c.ctx.profile_mods_dir / "From Finder" / C.MOD_INSTALLER_DIR / "override"
    payload.mkdir(parents=True)
    (payload / "a.2da").write_bytes(b"x")

    note = c.on_window_activated()

    assert c.pd.mod_item("From Finder") is not None
    assert "mods added 1" in note
    assert c.on_window_activated() == ""  # nothing new the second time


def test_an_installer_file_deleted_elsewhere_is_forgotten(tmp_path: Path) -> None:
    c = _open(tmp_path)
    c.create_mod("Mod One")
    payload = c.ctx.profile_mods_dir / "Mod One" / C.MOD_INSTALLER_DIR / "override"
    payload.mkdir(parents=True)
    (payload / "a.2da").write_bytes(b"x")
    (payload / "b.2da").write_bytes(b"y")
    c.create_installer("Mod One")
    c.on_window_activated()

    (payload / "b.2da").unlink()
    c.on_window_activated()

    assert [fk.filename for fk in c.pd.mod_item("Mod One").files if fk.folder == "override"] == [
        "a.2da"
    ]


def test_the_window_reloads_notes_edited_elsewhere(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.main_window import MainWindow

    c = _open(tmp_path)
    c.create_mod("Noted")
    c.save_notes("Noted", "first")
    win = MainWindow(c)
    qtbot.addWidget(win)
    win._select_mod_by_name("Noted")
    assert win._details.toPlainText() == "first"

    import os

    path = c.mod_notes_path("Noted")
    c.save_notes("Noted", "edited elsewhere")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    win._on_reactivated()

    assert win._details.toPlainText() == "edited elsewhere"


def test_the_health_icon_follows_the_game_error_logs(qtbot, tmp_path: Path) -> None:
    # VB HealthCheck: AR_ERROR.LOG / logs/nwclienterror1.txt with content.
    from vaultkeeper.ui.main_window import MainWindow

    c = _open(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    win.show()
    assert not win.nit_status.bt_health.isVisible()

    root = c.ctx.game_folders[C.MOD_ROOT_FOLDER]
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "nwclienterror1.txt").write_text("Error: something broke")
    win._health_check()
    assert win.nit_status.bt_health.isVisible()
    assert "something broke" in c.game_error_logs()[0]["text"]

    assert c.clear_game_error_logs() == 1
    win._health_check()
    assert not win.nit_status.bt_health.isVisible()


def _mod(c: ProfileController, name: str, data: bytes) -> None:
    c.create_mod(name)
    payload = c.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR / "override"
    payload.mkdir(parents=True)
    (payload / "x.2da").write_bytes(data)
    c.create_installer(name)


def test_every_mod_is_annealed_when_the_profile_opens(tmp_path: Path) -> None:
    # VB LoadProfile anneals all mods: a record naming the wrong owner is put right.
    from vaultkeeper.core.file_key import FileKeyInfo

    c = _open(tmp_path)
    _mod(c, "Alpha", b"alpha")
    _mod(c, "Beta", b"beta")
    c.install(["Alpha", "Beta"])
    ifk = FileKeyInfo.installed("override", "x.2da")
    winner = c.pd.installed_item(ifk).installer
    loser = "Alpha" if winner == "Beta" else "Beta"
    c.pd.installed_item(ifk).installer = loser
    c.save()

    c = _open(tmp_path)

    assert c.pd.installed_item(ifk).installer == winner
    assert (c.ctx.game_folders["override"] / "x.2da").read_bytes() == winner.lower().encode()


def test_the_credits_movie_fix_is_copied_on_ee(tmp_path: Path) -> None:
    (tmp_path / "NWN" / "data" / "mov").mkdir(parents=True)
    (tmp_path / "NWN" / "data" / "mov" / "credits.wbm").write_bytes(b"movie")

    c = _open(tmp_path)

    movies = c.ctx.game_folders[c.ctx.mapper.ext_mapping[".wbm"]]
    assert (movies / C.CREDITS_MOVIE_FIX).read_bytes() == b"movie"


def test_a_mod_folder_renamed_elsewhere_keeps_its_group(tmp_path: Path) -> None:
    # VB RenamedChange: the mod is renamed, not re-added as a new ungrouped mod.
    c = _open(tmp_path)
    c.create_group("300.  Adventures")
    c.create_mod("Old Name", "300.  Adventures")
    payload = c.ctx.profile_mods_dir / "Old Name" / C.MOD_INSTALLER_DIR / "override"
    payload.mkdir(parents=True)
    (payload / "a.2da").write_bytes(b"x")
    c.create_installer("Old Name")
    c.on_window_activated()

    (c.ctx.profile_mods_dir / "Old Name").rename(c.ctx.profile_mods_dir / "New Name")
    note = c.on_window_activated()

    assert c.pd.mod_item("Old Name") is None
    md = c.pd.mod_item("New Name")
    assert md is not None and md.group == "300.  Adventures"
    assert "renamed" in note
    ident = c.ctx.profile_mods_dir / "New Name" / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
    assert (ident / "New Name.nitins").is_file()
