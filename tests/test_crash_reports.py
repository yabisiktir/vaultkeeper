"""Crash files after play (VB ``AddCrashDumpFiles`` + ``CrashDumpManager``).

NIT tells the player when a session produced crash files and shows them in the
Crash Dump File Manager (``FileShowCrashFileManager``, on by default). Vaultkeeper
had no equivalent (ledger: Deferred; logic audit stage 4).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *, is_ee: bool = True) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=is_ee,
    )
    c.ctx.ee_user_files_dir = tmp_path / "user"
    return c


def _crash(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / "user" / "crashreport"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"dump")
    return path


def test_new_crash_files_are_reported_once(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _crash(tmp_path, "nwmain-crash-1.dmp")
    _crash(tmp_path, "unrelated.txt")

    assert [f.path.name for f in c.new_crash_reports()] == ["nwmain-crash-1.dmp"]
    assert c.new_crash_reports() == []  # remembered

    _crash(tmp_path, "nwmain-crash-2.log")
    assert [f.path.name for f in c.new_crash_reports()] == ["nwmain-crash-2.log"]


def test_classic_profiles_have_no_crash_reports(tmp_path: Path) -> None:
    c = _controller(tmp_path, is_ee=False)
    _crash(tmp_path, "nwmain-crash-1.dmp")
    assert c.new_crash_reports() == []


def test_delete_goes_to_the_recycle_bin(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)
    path = _crash(tmp_path, "nwmain-crash-1.dmp")

    assert c.delete_crash_reports([path]) == 1

    assert not path.exists()
    assert [p.name for p in recycle_bin.rglob("nwmain-crash-*")] == ["nwmain-crash-1.dmp"]


def test_the_manager_is_shown_after_a_crashing_session(qtbot, tmp_path, monkeypatch) -> None:
    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.dialogs import crash_reports
    from vaultkeeper.ui.main_window import MainWindow

    c = _controller(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    shown = []
    monkeypatch.setattr(crash_reports.CrashReportsDialog, "exec", lambda self: shown.append(
        (self.info.text(), self.files.count())
    ))
    _crash(tmp_path, "nwmain-crash-1.dmp")

    win._report_new_crash_files()

    assert shown == [("A crash information file was created during your last Neverwinter "
                      "Nights session.", 1)]

    settings = load_settings()
    settings.show_crash_file_manager = False
    save_settings(settings)
    _crash(tmp_path, "nwmain-crash-2.dmp")
    win._report_new_crash_files()
    assert len(shown) == 1


def test_submit_shows_the_crash_file_and_opens_beamdogs_crash_page(
    qtbot, tmp_path, monkeypatch
) -> None:
    """VB CrashDumpManager.BtSubmit: Explorer on the file, then BeamdogSupportPage."""
    from PySide6.QtGui import QDesktopServices

    from vaultkeeper.ui.dialogs.crash_reports import BEAMDOG_CRASH_PAGE, CrashReportsDialog

    controller = _controller(tmp_path)
    crash = _crash(tmp_path, "nwmain-crash-1728375984.nwcrash")
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    dlg = CrashReportsDialog(controller)
    qtbot.addWidget(dlg)

    dlg.submit_button.click()

    folder, page = opened
    assert Path(folder.toLocalFile()) == crash.parent  # separators differ on Windows
    assert page.toString() == BEAMDOG_CRASH_PAGE
