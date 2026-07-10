"""Tests for the HelpViewer dialog (bundled CHM topics + TOC)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.ui import help_model as H  # noqa: E402
from vaultkeeper.ui.dialogs.help_viewer import HelpViewer  # noqa: E402


def test_viewer_populates_toc_and_topic(qtbot):
    dlg = HelpViewer.show_for_control("ManageMenu")
    qtbot.addWidget(dlg)
    # TOC tree is populated from toc.hhc.
    assert dlg.contents.topLevelItemCount() == len(H.load_toc())
    # The requested topic is shown.
    assert "managemenu.htm" in dlg.browser.source().toString().lower()


def test_viewer_contents_root_defaults_to_default_topic(qtbot):
    dlg = HelpViewer.show_contents()
    qtbot.addWidget(dlg)
    assert H.DEFAULT_TOPIC.lower() in dlg.browser.source().toString().lower()


def test_viewer_unknown_control_falls_back_to_contents(qtbot):
    # An unknown control has no topic; the viewer opens at the contents root
    # rather than erroring (help IS bundled).
    dlg = HelpViewer.show_for_control("NoSuchControl98765")
    qtbot.addWidget(dlg)
    assert H.DEFAULT_TOPIC.lower() in dlg.browser.source().toString().lower()


def test_viewer_shows_message_when_topic_missing(qtbot):
    # Passing a missing path directly yields the friendly unavailable message.
    from pathlib import Path

    dlg = HelpViewer(Path("/no/such/topic.htm"))
    qtbot.addWidget(dlg)
    assert "unavailable" in dlg.browser.toPlainText().lower()


def test_viewer_toc_selection_loads_topic(qtbot):
    from PySide6.QtCore import Qt

    dlg = HelpViewer.show_contents()
    qtbot.addWidget(dlg)
    # Select the first child of the first section and confirm it loads.
    root = dlg.contents.topLevelItem(0)
    child = root.child(0)
    local = child.data(0, Qt.ItemDataRole.UserRole)
    dlg.contents.setCurrentItem(child)
    assert local.lower() in dlg.browser.source().toString().lower()
