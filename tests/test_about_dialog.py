"""Tests for the About dialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDialogButtonBox  # noqa: E402

from vaultkeeper.ui.dialogs.about import AboutDialog  # noqa: E402


def test_about_dialog_constructs(qtbot) -> None:
    """AboutDialog constructs without error."""
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None


def test_about_dialog_window_title(qtbot) -> None:
    """AboutDialog has correct window title."""
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "About Vaultkeeper"


def test_about_dialog_has_ok_button(qtbot) -> None:
    """AboutDialog has an OK button."""
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    # Find the QDialogButtonBox and verify it has an Ok button
    button_boxes = dlg.findChildren(QDialogButtonBox)
    assert len(button_boxes) > 0, "No QDialogButtonBox found in dialog"
    button_box = button_boxes[0]
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None, "OK button not found"


def test_about_dialog_contains_credits(qtbot) -> None:
    """AboutDialog contains all required credit entries."""
    dlg = AboutDialog()
    qtbot.addWidget(dlg)

    # Get all text from the dialog
    all_text = ""
    for widget in dlg.findChildren(object):
        if hasattr(widget, "text"):
            all_text += widget.text()
        if hasattr(widget, "toPlainText"):
            all_text += widget.toPlainText()
        if hasattr(widget, "toHtml"):
            all_text += widget.toHtml()

    # Verify key library names are present
    assert "BicFileReader" in all_text, "BicFileReader not found in credits"
    assert "TargaImage" in all_text, "TargaImage not found in credits"
    assert "UDE" in all_text, "UDE not found in credits"


def test_about_dialog_show_dialog_classmethod(qtbot) -> None:
    """AboutDialog.show_dialog(parent) creates and executes the dialog."""
    # This test just verifies that show_dialog exists and is callable
    # We don't actually exec() it in the test to avoid blocking
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    # Verify the classmethod exists
    assert hasattr(AboutDialog, "show_dialog")
    assert callable(AboutDialog.show_dialog)
