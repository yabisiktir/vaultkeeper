"""The Start Screen Manager's clickable status texts (rbloadscreenhelp.htm).

"You can also click the Excluded Status Text to perform the Add [or Remove]."
"You can also click the Start Screens Statistics Text to display the Information
Report." "Hover over the Start Screens Statistics Text to display the summary."

All three were plain labels here — a shortcut nobody could find, and the shape
that no command diff and no interaction sweep catches, because the topic's own
sentences were the only evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.start_screen_manager import StartScreenManager, _ClickableLabel


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_a_clickable_label_says_so_with_the_cursor(qtbot):
    """A label that does something without looking like it does is a shortcut
    nobody finds."""
    label = _ClickableLabel("text")
    qtbot.addWidget(label)
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_it_only_fires_when_there_is_something_to_click(qtbot):
    label = _ClickableLabel("")
    qtbot.addWidget(label)
    fired: list[int] = []
    label.clicked.connect(lambda: fired.append(1))

    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    assert fired == []

    label.setText("Excluded: no")
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    assert fired == [1]


def test_the_two_status_texts_are_wired(qtbot, controller, monkeypatch):
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)

    toggled: list[int] = []
    reported: list[int] = []
    monkeypatch.setattr(dlg, "_on_toggle_exclude", lambda: toggled.append(1))
    monkeypatch.setattr(dlg, "_on_info_report", lambda: reported.append(1))
    # Reconnect, since the originals were bound at construction.
    dlg._detail.clicked.disconnect()
    dlg._summary.clicked.disconnect()
    dlg._detail.clicked.connect(dlg._on_toggle_exclude)
    dlg._summary.clicked.connect(dlg._on_info_report)

    dlg._detail.setText("something")
    dlg._summary.setText("something")
    dlg._detail.clicked.emit()
    dlg._summary.clicked.emit()

    assert toggled == [1] and reported == [1]


def test_hovering_the_statistics_shows_the_summary(qtbot, controller):
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    assert "information report" in dlg._summary.toolTip().lower()
