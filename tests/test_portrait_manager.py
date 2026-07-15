"""Portrait Manager Prev/Next navigation (VB RbPrevious / RbNext)."""

from __future__ import annotations

from types import SimpleNamespace

from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager


def _viewer(qtbot, n: int) -> PortraitManager:
    entries = [SimpleNamespace(resref=f"p{i}", sizes={}) for i in range(n)]
    dlg = PortraitManager(SimpleNamespace(portrait_entries=lambda: entries))
    qtbot.addWidget(dlg)
    return dlg


def test_prev_next_steps_and_clamps(qtbot):
    dlg = _viewer(qtbot, 3)
    assert dlg._list.currentRow() == 0
    dlg._step(1)
    assert dlg._list.currentRow() == 1
    dlg._step(1)
    dlg._step(1)  # clamp at the last row
    assert dlg._list.currentRow() == 2
    dlg._step(-10)  # clamp at the first row
    assert dlg._list.currentRow() == 0


def test_step_on_empty_is_noop(qtbot):
    dlg = _viewer(qtbot, 0)
    dlg._step(1)  # must not raise
    assert dlg._list.currentRow() == -1
