"""The Enhanced Edition user-files prompt (VB ExtendedEditionDialogue).

Shown at first run when EE is installed but its user-files folder cannot be
found (firsttimeexecution.htm / newtopic... the 5th first-run question).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox  # noqa: E402

from vaultkeeper.ui.dialogs.extended_edition import ExtendedEditionDialog  # noqa: E402


def _save(dlg):
    return dlg.buttons.button(QDialogButtonBox.StandardButton.Save)


def test_save_is_disabled_until_a_real_folder_or_disable(qtbot, tmp_path):
    dlg = ExtendedEditionDialog()
    qtbot.addWidget(dlg)
    assert not _save(dlg).isEnabled()

    dlg.user_folder_edit.setText(str(tmp_path))  # an existing directory
    assert _save(dlg).isEnabled()
    assert dlg.user_folder == str(tmp_path)
    assert dlg.detection_disabled is False


def test_a_non_existent_folder_keeps_save_disabled(qtbot, tmp_path):
    dlg = ExtendedEditionDialog()
    qtbot.addWidget(dlg)
    dlg.user_folder_edit.setText(str(tmp_path / "does-not-exist"))
    assert not _save(dlg).isEnabled()


def test_disabling_detection_enables_save_and_ignores_the_folder(qtbot, tmp_path):
    dlg = ExtendedEditionDialog()
    qtbot.addWidget(dlg)
    dlg.user_folder_edit.setText(str(tmp_path))
    dlg.disable_check.setChecked(True)
    assert _save(dlg).isEnabled()
    assert dlg.detection_disabled is True
    # Detection off -> the folder is not reported, so nothing is guessed from it.
    assert dlg.user_folder == ""
