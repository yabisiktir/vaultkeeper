"""Update the Installer Tool (VB MsUpdateNow / bhnitdownload.htm).

VB downloads a 7-Zip from the Vault and unpacks it over itself. This asks the
project's releases what the newest version is and offers the download page:
replacing a running application's own files is the part of a self-updater that
goes wrong, and it goes wrong on the machine of whoever least wanted it to.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from vaultkeeper.vault import app_update as au


class _Http:
    def __init__(self, payload=None, status=200, boom: Exception | None = None) -> None:
        self.payload, self.status, self.boom = payload or {}, status, boom
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if self.boom is not None:
            raise self.boom
        return SimpleNamespace(status_code=self.status, json=lambda: self.payload)


# -- Comparing versions ---------------------------------------------------------- #
@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("1.2.3", "1.2.2", True),
        ("v1.2.3", "1.2.3", False),
        ("1.3", "1.2.9", True),
        ("1.2", "1.2.0", False),      # padded, not compared by length
        ("2.0.0-beta", "1.9.9", True),
        ("0.0.1", "0.0.1", False),
        ("", "1.0.0", False),          # nothing to compare is not "newer"
        ("not a version", "1.0.0", False),
    ],
)
def test_version_comparison(latest, current, expected):
    assert au.is_newer(latest, current) is expected


def test_a_tag_is_written_by_a_person(name="v1.2.3-rc1"):
    """Refusing to parse a hand-written tag would fail exactly when it matters."""
    assert au.parse_version(name) == (1, 2, 3, 1)


# -- Asking ----------------------------------------------------------------------- #
def test_a_newer_release_is_offered():
    http = _Http({"tag_name": "v9.9.9", "html_url": "https://example/rel", "body": "Notes"})
    check = au.check_for_update(http, "1.0.0")

    assert check.available and check.latest == "v9.9.9"
    assert check.url == "https://example/rel"
    assert "9.9.9" in check.message and "1.0.0" in check.message


def test_being_up_to_date_is_said_plainly():
    check = au.check_for_update(_Http({"tag_name": "1.0.0"}), "1.0.0")
    assert not check.available
    assert "latest version" in check.message


def test_no_releases_yet_is_not_a_failure():
    check = au.check_for_update(_Http(status=404), "1.0.0")
    assert not check.available and not check.error
    assert "No releases" in check.message


def test_a_network_failure_is_reported_not_raised():
    check = au.check_for_update(_Http(boom=TimeoutError("no answer")), "1.0.0")
    assert not check.available
    assert check.error and "Could not check" in check.message


def test_a_release_with_no_tag_falls_back_to_the_releases_page():
    check = au.check_for_update(_Http({"html_url": ""}), "1.0.0")
    assert check.url == au.RELEASES_PAGE
    assert "no version number" in check.message


def test_nothing_is_sent_about_the_machine():
    """It reads a public list. It does not report who asked or what they run."""
    http = _Http({"tag_name": "1.0.0"})
    au.check_for_update(http, "1.0.0")
    assert http.calls == [au.RELEASES_URL]


def test_the_command_is_live(qtbot, tmp_path):
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(c)
    qtbot.addWidget(win)
    assert "MsUpdateNow" in win.implemented_commands()
    assert "MsResetWebMenu" in win.implemented_commands()


# -- Web menu links (VB MsResetWebMenu) ------------------------------------------ #
@pytest.fixture()
def controller(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.controller import ProfileController

    settings = load_settings()
    settings.web_links = [
        {"text": "Vault", "url": "https://neverwintervault.org"},
        {"text": "Gone", "url": "https://example.invalid/missing"},
        {"text": "Blank", "url": ""},
    ]
    save_settings(settings)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        settings_path=None,
    )


def _answers(controller, statuses: dict[str, int]) -> None:
    class _Client:
        def head(self, url, **kwargs):
            if url not in statuses:
                raise ConnectionError("no such host")
            return SimpleNamespace(status_code=statuses[url])

    controller._http = _Client()


def test_a_link_with_no_address_is_a_finding(controller):
    _answers(controller, {"https://neverwintervault.org": 200,
                          "https://example.invalid/missing": 200})
    result = controller.check_web_menu_links()
    assert [b["text"] for b in result["bad"]] == ["Blank"]


def test_a_dead_link_is_a_finding(controller):
    _answers(controller, {"https://neverwintervault.org": 200,
                          "https://example.invalid/missing": 404})
    result = controller.check_web_menu_links()
    assert {b["text"] for b in result["bad"]} == {"Gone", "Blank"}
    assert "HTTP 404" in next(b["problem"] for b in result["bad"] if b["text"] == "Gone")


@pytest.mark.parametrize("status", [403, 405, 429])
def test_a_site_that_dislikes_head_is_not_called_dead(controller, status):
    """Plenty of sites refuse HEAD and answer GET perfectly well; calling those
    links broken would send someone off to fix what is not wrong."""
    _answers(controller, {"https://neverwintervault.org": status,
                          "https://example.invalid/missing": 200})
    result = controller.check_web_menu_links()
    assert "Vault" not in {b["text"] for b in result["bad"]}


def test_all_well_says_so(controller):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.web_links = [{"text": "Vault", "url": "https://neverwintervault.org"}]
    save_settings(settings)
    _answers(controller, {"https://neverwintervault.org": 200})

    result = controller.check_web_menu_links()
    assert result["ok"] and "all answered" in result["message"]
