"""Hak Patch Editor keeps NIT's move keys and icons (screen parity, VB MsMoveUp/MsMoveDown)."""

from __future__ import annotations

from PySide6.QtCore import Qt

from vaultkeeper.ui.dialogs.hak_patch_editor import HakPatchEditor


class _Controller:
    def __init__(self) -> None:
        self.saved: list[str] | None = None

    def patch_hak_sequence(self) -> list[str]:
        return ["cep2_patch", "prc8_patch", "zz_patch"]

    def save_patch_hak_sequence(self, order: list[str]) -> None:
        self.saved = order


def test_ctrl_down_moves_the_selected_hak_to_a_higher_priority(qtbot) -> None:
    dlg = HakPatchEditor(_Controller())
    qtbot.addWidget(dlg)
    dlg.list.setCurrentRow(0)
    down = next(a for a in dlg.list.actions() if a.shortcut().toString() == "Ctrl+Down")
    down.trigger()
    assert [dlg.list.item(i).text() for i in range(3)] == ["prc8_patch", "cep2_patch", "zz_patch"]
    assert dlg.list.currentRow() == 1


def test_the_move_actions_carry_nits_arrows_and_sit_on_the_context_menu(qtbot) -> None:
    dlg = HakPatchEditor(_Controller())
    qtbot.addWidget(dlg)
    assert dlg.list.contextMenuPolicy() == Qt.ContextMenuPolicy.ActionsContextMenu
    assert [a.text() for a in dlg.list.actions()] == [
        "Move Up (Lower priority)", "Move Down (Higher priority)",
    ]
    assert not dlg.up_button.icon().isNull() and not dlg.down_button.icon().isNull()
