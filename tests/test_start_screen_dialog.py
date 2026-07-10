"""Dialog test for the Start Screen Manager gallery (VB StartScreenManager)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.ui.dialogs.start_screen_manager import StartScreenManager  # noqa: E402


def _report() -> dict:
    return {
        "exists": True,
        "mod_name": "NWN Loadscreens (NIT Managed)",
        "installed": True,
        "active": "sunset.tga",
        "image_folder": "/mods/NWN Loadscreens (NIT Managed)/Loadscreen Images",
        "images": [
            {
                "name": "castle.tga",
                "path": "/x/castle.tga",
                "size": 100,
                "size_text": "100 B",
                "excluded": True,
                "active": False,
            },
            {
                "name": "sunset.tga",
                "path": "/x/sunset.tga",
                "size": 200,
                "size_text": "200 B",
                "excluded": False,
                "active": True,
            },
        ],
        "count": 2,
        "excluded_count": 1,
        "summary": "2 loadscreen images · 'sunset.tga' installed · 1 auto-excluded.",
    }


def test_dialog_population(qtbot) -> None:
    dlg = StartScreenManager(_report())
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 2
    # Active image gets the ★ marker.
    labels = [dlg._list.item(i).text() for i in range(dlg._list.count())]
    assert any("★" in label and "sunset.tga" in label for label in labels)
    assert "auto-excluded" in dlg._summary.text().lower()


def test_dialog_empty_report(qtbot) -> None:
    report = {
        "exists": False,
        "mod_name": "NWN Loadscreens (NIT Managed)",
        "installed": False,
        "active": "",
        "image_folder": "",
        "images": [],
        "count": 0,
        "excluded_count": 0,
        "summary": "NIT does not yet manage your NWN Start Screen.",
    }
    dlg = StartScreenManager(report)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 0
    assert "no loadscreen images" in dlg._preview.text().lower()
