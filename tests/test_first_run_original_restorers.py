"""First run offers to back up the files NWN installed (VB first-run question).

NIT asks "Do you want to create Restorers for files installed by Neverwinter
Nights?" (with the disk space needed) when a profile is created or migrated.
Vaultkeeper had the command in a menu but never asked (logic audit 3a, F1).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from vaultkeeper.ui.controller import ProfileController


def _window(qtbot, tmp_path: Path, monkeypatch, count: int):
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(
        c, "original_restorers_offer", lambda: {"count": count, "bytes": 2048, "size": "2.0 KB"}
    )
    created = []
    monkeypatch.setattr(
        c, "create_original_restorers", lambda: created.append(1) or {"message": "done"}
    )
    return win, created


def test_yes_creates_the_restorers(qtbot, tmp_path, monkeypatch) -> None:
    win, created = _window(qtbot, tmp_path, monkeypatch, count=3)
    asked = []

    def question(_parent, _title, text, *a, **k):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    win.offer_original_restorers()

    assert created == [1]
    assert "files installed by Neverwinter Nights" in asked[0] and "2.0 KB" in asked[0]


def test_no_leaves_them(qtbot, tmp_path, monkeypatch) -> None:
    win, created = _window(qtbot, tmp_path, monkeypatch, count=3)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    win.offer_original_restorers()
    assert created == []


def test_nothing_to_back_up_asks_nothing(qtbot, tmp_path, monkeypatch) -> None:
    win, created = _window(qtbot, tmp_path, monkeypatch, count=0)

    def fail(*a, **k):
        raise AssertionError("asked")

    monkeypatch.setattr(QMessageBox, "question", fail)
    win.offer_original_restorers()
    assert created == []


def test_the_offer_counts_pristine_originals(tmp_path: Path, monkeypatch) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    assert c.original_restorers_offer()["count"] == 0
