"""Tests for legacy-store onboarding: detection + import-dialog pre-fill + hint."""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui import session


def test_detect_legacy_store_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = tmp_path / "Documents" / "Neverwinter Nights"
    monkeypatch.setattr(
        "vaultkeeper.game.locations.user_documents_dir", lambda *a, **k: docs
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert session.detect_legacy_store() is None


def test_detect_legacy_store_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = tmp_path / "Documents" / "Neverwinter Nights"
    store = tmp_path / "Documents" / "NIT Store"
    (store / "Data").mkdir(parents=True)
    monkeypatch.setattr(
        "vaultkeeper.game.locations.user_documents_dir", lambda *a, **k: docs
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert session.detect_legacy_store() == store


def test_import_dialog_prefills_detected_store(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "NIT Store"
    (store / "Data" / "P").mkdir(parents=True)
    # migrate.list_profiles reads Data/ subfolders; give it one.
    monkeypatch.setattr(session, "detect_legacy_store", lambda: store)

    from vaultkeeper.ui.dialogs.import_legacy import ImportLegacyStore

    dlg = ImportLegacyStore()
    qtbot.addWidget(dlg)
    assert dlg.path_edit.text() == str(store)
    # Setting the path lists the profiles it contains.
    assert dlg.profiles.count() == 1
    assert dlg.profiles.item(0).text() == "P"


def test_empty_profile_shows_import_hint(
    qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from vaultkeeper.core.profile_data import ProfileData
    from vaultkeeper.persistence.profile_store import save_profile
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    monkeypatch.setattr(
        "vaultkeeper.ui.session.detect_legacy_store", lambda: tmp_path / "NIT Store"
    )
    pd = ProfileData()
    pd.ensure_mandatory_groups()  # no real mods
    store = tmp_path / "Data" / "Empty.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    win = MainWindow(controller=controller)
    qtbot.addWidget(win)
    assert "Import Legacy NIT Store" in win._details.toHtml()
