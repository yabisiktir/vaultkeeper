"""Tests for the Web menu (default links, settings round-trip, menu population).

Covers the bounded VB Web-menu slice: the default Vault + Nexus links, persisting a
user's link list, and populating the menu so each item opens its URL.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.config.settings import (  # noqa: E402
    Settings,
    default_web_links,
    load_settings,
    save_settings,
)
from vaultkeeper.ui.menu_bar import NitMenuBar  # noqa: E402


def test_default_web_links_are_vault_and_nexus():
    links = default_web_links()
    urls = [link["url"] for link in links]
    assert urls == [
        "https://neverwintervault.org",
        "https://www.nexusmods.com/neverwinter",
    ]


def test_web_links_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(web_links=[{"text": "My Site", "url": "https://example.org"}])
    save_settings(settings, path)
    assert load_settings(path).web_links == [
        {"text": "My Site", "url": "https://example.org"}
    ]


def test_default_settings_include_web_links():
    assert Settings().web_links == default_web_links()


def test_populate_web_menu_adds_items(qtbot):
    menu_bar = NitMenuBar()
    qtbot.addWidget(menu_bar)
    opened: list[str] = []
    menu_bar.populate_web_menu(default_web_links(), opened.append)

    web = menu_bar.menus["MsWeb"]
    actions = web.actions()
    assert [a.text() for a in actions] == [
        "The Neverwinter &Vault",
        "&Nexus Neverwinter Nights",
    ]
    actions[0].trigger()
    assert opened == ["https://neverwintervault.org"]


def test_empty_web_menu_is_disabled(qtbot):
    menu_bar = NitMenuBar()
    qtbot.addWidget(menu_bar)
    menu_bar.populate_web_menu([], lambda url: None)
    assert menu_bar.menus["MsWeb"].isEnabled() is False


def test_main_window_opens_web_link(qtbot, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    from vaultkeeper.ui.main_window import MainWindow

    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    win = MainWindow(controller=None)
    qtbot.addWidget(win)
    win._open_url("https://example.org")
    assert opened == ["https://example.org"]
