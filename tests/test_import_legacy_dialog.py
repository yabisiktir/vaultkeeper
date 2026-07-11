"""Tests for the legacy-NIT-Store import dialog."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.config.settings import Settings, save_settings  # noqa: E402
from vaultkeeper.ui.dialogs.import_legacy import ImportLegacyStore  # noqa: E402

_REAL_STORE = Path("/Users/example/Documents/NIT Store")


def test_dialog_lists_and_imports(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    import vaultkeeper.config.settings as S

    # Redirect the native store into tmp so the import writes there.
    native = tmp_path / "store"
    settings = Settings(store_root=str(native))
    settings_file = native / "settings.json"
    native.mkdir(parents=True)
    save_settings(settings, settings_file)
    monkeypatch.setattr(S, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(S, "save_settings", lambda s, *a, **k: save_settings(s, settings_file))

    # Build a tiny fake legacy store with one profile Data folder (empty mods).
    legacy = tmp_path / "Legacy NIT Store"
    (legacy / "Data" / "My Profile").mkdir(parents=True)

    imported = {}
    dlg = ImportLegacyStore(on_imported=lambda p: imported.setdefault("p", p))
    qtbot.addWidget(dlg)
    dlg.path_edit.setText(str(legacy))
    assert dlg.profiles.count() == 1
    assert dlg.profiles.item(0).text() == "My Profile"

    dlg.profiles.setCurrentRow(0)
    assert dlg.import_button.isEnabled()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._import()
    assert imported.get("p") == "My Profile"


@pytest.mark.skipif(
    not (_REAL_STORE / "Data").is_dir(), reason="No real NIT Store on this machine"
)
def test_dialog_lists_real_store_profiles(qtbot):
    dlg = ImportLegacyStore()
    qtbot.addWidget(dlg)
    dlg.path_edit.setText(str(_REAL_STORE))
    names = [dlg.profiles.item(i).text() for i in range(dlg.profiles.count())]
    assert "Enhanced Edition Mods" in names
