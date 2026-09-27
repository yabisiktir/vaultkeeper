"""Managed Steam Workshop mods follow Steam (logic audit stage 3h).

With "Use NIT to manage Steam's Workshop Content" on, NIT's ``LoadMods`` runs
when a profile loads: a new subscription becomes a mod (packed, built,
installed), a changed one is repacked and rebuilt, and for one that is gone it
asks whether to keep this tool's copy. Vaultkeeper only reported a summary;
new items needed a manual Add, and changes never reached the game.
"""

from __future__ import annotations

import os
from pathlib import Path

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse


def _setup(tmp_path: Path, *, managed: bool = True):
    settings = load_settings()
    settings.manage_steam_workshop = managed
    save_settings(settings)
    steamapps = tmp_path / "steamapps"
    game_root = steamapps / "common" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    content = steamapps / "workshop" / "content" / "704450"
    item = content / "123" / "modules"
    item.mkdir(parents=True)
    (item / "Cool Module.mod").write_bytes(b"MOD v1")
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
        is_ee=True,
    )
    c._http = FakeHttpClient()  # never reach Steam from a test
    c._extractor = FakeArchiveExtractor(
        contents={"Cool Module (123).7z": {"modules/Cool Module.mod": b"MOD v1"}}
    )
    return c, content


def test_a_new_subscription_becomes_an_installed_mod(tmp_path: Path) -> None:
    c, _content = _setup(tmp_path)

    result = c.sync_workshop_mods()

    assert result["created"] == ["Cool Module"]
    md = c.pd.mod_item("Cool Module")
    assert md.workshop_id == "123" and md.is_installer()
    assert c._mod_installed("Cool Module")
    assert c.sync_workshop_mods()["created"] == []  # nothing new the second time


def test_nothing_happens_when_management_is_off(tmp_path: Path) -> None:
    c, _content = _setup(tmp_path, managed=False)
    assert c.sync_workshop_mods()["created"] == []
    assert c.pd.mod_item("Cool Module") is None


def test_a_changed_subscription_is_repacked_and_rebuilt(tmp_path: Path) -> None:
    c, content = _setup(tmp_path)
    c.sync_workshop_mods()
    mod_file = content / "123" / "modules" / "Cool Module.mod"
    mod_file.write_bytes(b"MOD v2, longer")
    os.utime(mod_file, ns=(1, 1))
    c._extractor._contents["Cool Module (123).7z"] = {"modules/Cool Module.mod": b"MOD v2"}
    creates = len(c._extractor.create_calls)

    result = c.sync_workshop_mods()

    assert result["updated"] == ["Cool Module"]
    assert len(c._extractor.create_calls) == creates + 1
    game_mod = c.ctx.game_folders["modules"] / "Cool Module.mod"
    assert game_mod.read_bytes() == b"MOD v2"
    assert c.sync_workshop_mods()["updated"] == []


def test_a_change_seen_while_unmanaged_is_not_lost(tmp_path: Path) -> None:
    """The startup summary refreshes the database whether or not management is on."""
    c, content = _setup(tmp_path)
    c.sync_workshop_mods()
    mod_file = content / "123" / "modules" / "Cool Module.mod"
    mod_file.write_bytes(b"MOD v2, longer")
    c.workshop_refresh()  # e.g. the profile-load summary

    assert c.sync_workshop_mods()["updated"] == ["Cool Module"]


def test_an_unsubscribed_mod_is_kept_or_deleted_as_answered(tmp_path: Path) -> None:
    c, content = _setup(tmp_path)
    c.sync_workshop_mods()
    (content / "123" / "modules" / "Cool Module.mod").unlink()
    (content / "123" / "modules").rmdir()
    (content / "123").rmdir()

    asked = []
    result = c.sync_workshop_mods(keep_unsubscribed=lambda name: asked.append(name) or False)

    assert asked == ["Cool Module"] and result["deleted"] == ["Cool Module"]
    assert c.pd.mod_item("Cool Module") is None
    assert not (c.ctx.game_folders["modules"] / "Cool Module.mod").exists()


def test_kept_unsubscribed_mod_loses_its_steam_link(tmp_path: Path) -> None:
    c, content = _setup(tmp_path)
    c.sync_workshop_mods()
    for p in sorted((content / "123").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    (content / "123").rmdir()

    result = c.sync_workshop_mods(keep_unsubscribed=lambda name: True)

    assert result["kept"] == ["Cool Module"]
    md = c.pd.mod_item("Cool Module")
    assert md.workshop_id == "" and md.web_link == ""


def test_a_module_another_mod_provides_is_not_duplicated(tmp_path: Path) -> None:
    """VB ``ModInfo.SteamOnly``: e.g. the same module downloaded from the Vault."""
    c, _content = _setup(tmp_path)
    c.create_mod("Cool Module (Vault)")
    payload = c.ctx.profile_mods_dir / "Cool Module (Vault)" / C.MOD_INSTALLER_DIR / "modules"
    payload.mkdir(parents=True)
    (payload / "Cool Module.mod").write_bytes(b"VAULT")
    c.create_installer("Cool Module (Vault)")

    result = c.sync_workshop_mods()

    assert result["created"] == [] and result["skipped"] == ["Cool Module"]


def test_the_users_name_for_a_subscription_is_used(tmp_path: Path) -> None:
    c, _content = _setup(tmp_path)
    c.workshop_refresh()
    c.rename_workshop_mod("123", "My Name For It")
    c._extractor._contents["My Name For It (123).7z"] = {"modules/Cool Module.mod": b"x"}

    assert c.sync_workshop_mods()["created"] == ["My Name For It"]


def test_stop_managing_delete_uninstalls(tmp_path: Path) -> None:
    """It dropped the mod definitions only, leaving their files in the game."""
    c, _content = _setup(tmp_path)
    c.sync_workshop_mods()
    assert (c.ctx.game_folders["modules"] / "Cool Module.mod").exists()

    c.stop_managing_workshop(keep=False)

    assert not (c.ctx.game_folders["modules"] / "Cool Module.mod").exists()
    assert not (c.ctx.profile_mods_dir / "Cool Module").exists()




def test_profile_load_runs_the_sync_and_asks_once_for_all(qtbot, tmp_path: Path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    c, content = _setup(tmp_path)
    (content / "456" / "modules").mkdir(parents=True)
    (content / "456" / "modules" / "Other.mod").write_bytes(b"O")
    c._extractor._contents["Other (456).7z"] = {"modules/Other.mod": b"O"}
    win = MainWindow(c)
    qtbot.addWidget(win)
    win._detect_workshop_changes()
    assert c.pd.mod_item("Cool Module") and c.pd.mod_item("Other")

    for wid in ("123", "456"):
        for p in sorted((content / wid).rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        (content / wid).rmdir()
    asked = []

    def answer(box):
        asked.append(box.text())
        box.checkBox().setChecked(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", answer)
    win._detect_workshop_changes()

    assert len(asked) == 1  # "Take the same action for all"
    assert c.pd.mod_item("Cool Module").workshop_id == ""
    assert c.pd.mod_item("Other").workshop_id == ""


def test_a_hak_only_item_is_named_from_its_steam_page(tmp_path: Path) -> None:
    """VB ``ModNameFromWeb``: an item with no .mod file was left as "Mod <id>"."""
    c, content = _setup(tmp_path)
    (content / "789" / "hak").mkdir(parents=True)
    (content / "789" / "hak" / "tiles.hak").write_bytes(b"H")
    url = "https://steamcommunity.com/sharedfiles/filedetails/?id=789"
    c._http.responses[url] = HttpResponse(
        url=url, status=200, text="<html><title>Steam Workshop::Lovely &amp; Tiles.</title>"
    )
    c._extractor._contents["Lovely & Tiles (789).7z"] = {"hak/tiles.hak": b"H"}

    assert "Lovely & Tiles" in c.sync_workshop_mods()["created"]


def test_a_mapid_rule_names_the_item_without_asking_steam(tmp_path: Path) -> None:
    from vaultkeeper.vault.download_rules import DownloadRules

    c, _content = _setup(tmp_path)
    c._download_rules = DownloadRules.from_text(
        "WorkshopIdMap\n\tMapId 123 = Cool Module (Workshop)\nEnd WorkshopIdMap\n"
    )
    c._extractor._contents["Cool Module (Workshop) (123).7z"] = {"modules/Cool Module.mod": b"x"}

    assert c.sync_workshop_mods()["created"] == ["Cool Module (Workshop)"]
    assert not c._http.calls


def test_steam_titles_are_not_fetched_while_unmanaged(tmp_path: Path) -> None:
    c, _content = _setup(tmp_path, managed=False)
    c.workshop_refresh()
    assert not c._http.calls
