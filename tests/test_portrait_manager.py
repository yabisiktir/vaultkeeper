"""Portrait Manager — installed-portrait source + Select + Remove (VB PortraitManager)."""

from __future__ import annotations

from types import SimpleNamespace

from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager


def _controller(portraits, on_remove=None):
    report = {"portraits": list(portraits), "count": len(portraits)}
    default_remove = lambda resref: {"removed": 5, "mod": "M", "message": "ok"}  # noqa: E731
    return SimpleNamespace(
        installed_portraits_report=lambda: report,
        remove_installed_portrait=on_remove or default_remove,
    )


def _portraits():
    return [
        {"resref": "po_hero", "mod": "Heroes Pack", "group": "Community", "sizes": {}},
        {"resref": "po_villain", "mod": "Heroes Pack", "group": "Community", "sizes": {}},
        {"resref": "po_king", "mod": "Royal Set", "group": "Community", "sizes": {}},
    ]


def test_lists_installed_portraits_with_mod(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 3
    # Each row shows the portrait and its installing mod.
    row0 = dlg._tree.topLevelItem(0)
    assert "po_hero" in row0.text(0)
    assert row0.text(1) == "Heroes Pack"


def test_select_invokes_callback_with_mod(qtbot):
    selected = []
    dlg = PortraitManager(_controller(_portraits()), on_select=selected.append)
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(2))  # po_king / Royal Set
    dlg._on_select_mod()
    assert selected == ["Royal Set"]
    assert not dlg.isVisible()  # dialog closes after select


def test_remove_calls_controller_and_refreshes(qtbot, monkeypatch):
    calls = []

    def fake_remove(resref):
        calls.append(resref)
        return {"removed": 5, "mod": "Heroes Pack", "message": "Removed."}

    from vaultkeeper.ui.dialogs import portrait_manager as pm

    yes = pm.QMessageBox.StandardButton.Yes
    monkeypatch.setattr(pm.QMessageBox, "question", lambda *a, **k: yes)
    monkeypatch.setattr(pm.QMessageBox, "information", lambda *a, **k: None)

    dlg = PortraitManager(_controller(_portraits(), on_remove=fake_remove))
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))  # po_hero
    dlg._on_remove()
    assert calls == ["po_hero"]


def test_empty_source_is_safe(qtbot):
    dlg = PortraitManager(_controller([]))
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 0
    assert not dlg._select_button.isEnabled()
    assert not dlg._remove_button.isEnabled()
