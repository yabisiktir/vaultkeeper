"""Tests for the Qt GameMapper prompter."""

from __future__ import annotations

import pytest

from vaultkeeper.ui.prompter import QtGameMapperPrompter


def test_choose_mod_returns_selection(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getItem",
        lambda *a, **k: ("Mod Two", True),
    )
    p = QtGameMapperPrompter()
    assert p.choose_mod(["Mod One", "Mod Two"]) == "Mod Two"


def test_choose_mod_cancel_falls_back_to_first(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getItem", lambda *a, **k: ("", False)
    )
    p = QtGameMapperPrompter()
    assert p.choose_mod(["Mod One", "Mod Two"]) == "Mod One"


def test_choose_mod_empty_list(qtbot):
    assert QtGameMapperPrompter().choose_mod([]) == ""


def test_specify_mod_name_typed(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getText",
        lambda *a, **k: ("  Typed Name  ", True),
    )
    ok, name = QtGameMapperPrompter().specify_mod_name("orphan", "msg")
    assert ok and name == "Typed Name"


def test_specify_mod_name_cancel(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getText", lambda *a, **k: ("", False)
    )
    ok, name = QtGameMapperPrompter().specify_mod_name("orphan", "msg")
    assert not ok


def test_specify_mod_name_blank_is_not_ok(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getText", lambda *a, **k: ("   ", True)
    )
    ok, _ = QtGameMapperPrompter().specify_mod_name("orphan", "msg")
    assert not ok


def test_choose_profile_returns_index(qtbot, monkeypatch):
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getItem",
        lambda *a, **k: ("Profile B (Mod)", True),
    )
    idx = QtGameMapperPrompter().choose_profile("msg", ["Profile A (Mod)", "Profile B (Mod)"])
    assert idx == 1


def test_prompter_drives_gamemapper_choice(qtbot, monkeypatch, tmp_path):
    # End-to-end: an ambiguous log name resolves via the Qt prompter.
    from vaultkeeper.core.file_data import InstalledFileData
    from vaultkeeper.core.file_key import FileKeyInfo
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.core.profile_data import ProfileData
    from vaultkeeper.core.state import State
    from vaultkeeper.game.game_mapper import GameMapper, GameMapperContext
    from vaultkeeper.game.module_reader import ErfModuleReader

    pd = ProfileData()
    for group, name in (("A", "Mod One"), ("B", "Mod Two")):
        pd.add_mod(ModData(group=group, mod_name=name, mod_state=State.INSTALLED))
    ik = FileKeyInfo.installed("modules", "shared.mod")
    ifd = InstalledFileData(key=ik, installer="Mod One")
    for group, name in (("A", "Mod One"), ("B", "Mod Two")):
        ifd.mod_file_conflicts.append(
            FileKeyInfo.mod_file(group, name, "modules\\shared.mod")
        )
    pd.add_installed(ifd)

    (tmp_path / "Data").mkdir()
    monkeypatch.setattr(
        "vaultkeeper.ui.prompter.QInputDialog.getItem",
        lambda *a, **k: ("Mod Two", True),
    )
    gm = GameMapper(
        pd,
        GameMapperContext(
            profiles_dir=tmp_path / "Profiles",
            active_profile="P",
            data_dir=tmp_path / "Data",
        ),
        module_reader=ErfModuleReader(),
        prompter=QtGameMapperPrompter(),
        auto_scan=False,
    )
    assert gm.log_name_to_mod_name("shared") == "Mod Two"


@pytest.fixture(autouse=True)
def _needs_qt(qtbot):
    # Ensure a QApplication exists for QInputDialog references.
    yield
