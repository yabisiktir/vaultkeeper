"""The frozen-app build: that its inputs exist and its promises are kept.

Freezing is not run here, but everything the spec depends on is checked. These
failures all have the same shape — the build succeeds and the shipped app is
broken at runtime — which is exactly the kind worth catching early.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = _ROOT / "packaging" / "vaultkeeper.spec"


def _spec() -> str:
    return _SPEC.read_text(encoding="utf-8")


def test_the_spec_and_its_driver_exist():
    assert _SPEC.is_file()
    assert (_ROOT / "scripts" / "build_app.py").is_file()


def test_it_freezes_the_real_entry_point():
    assert '"vaultkeeper" / "__main__.py"' in _spec()
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["gui-scripts"]["vaultkeeper"] == "vaultkeeper.__main__:main"


def test_the_ui_images_are_bundled():
    """resources.py looks these up by name at runtime, so not one of the ~456
    files is discoverable statically. Miss them and every button is blank."""
    assert '"vaultkeeper/ui/resources"' in _spec()
    assert (_ROOT / "src" / "vaultkeeper" / "ui" / "resources" / "images").is_dir()


def test_both_packages_game_data_is_bundled():
    """Read as files relative to their own module, not as package resources."""
    spec = _spec()
    assert '"vaultkeeper/game/data"' in spec
    assert '"nwnfile/data"' in spec


def test_the_editors_game_data_is_located_through_the_package():
    """A fixed path would be an editable install here and site-packages in CI."""
    assert "_nwnfile_data()" in _spec()
    assert "import nwnfile" in _spec()


def test_seven_zip_is_bundled_for_this_platform_only():
    """It is required — archive.py has no pure-Python fallback — but shipping all
    four platforms' binaries would waste 9 MB of every download."""
    spec = _spec()
    assert "sevenzip_slug()" in spec
    assert 'f"external/bin/{_SLUG}"' in spec
    from vaultkeeper.core.archive import platform_slug

    assert (_ROOT / "external" / "bin" / platform_slug()).is_dir()


def test_the_seven_zip_licence_travels_with_it():
    """Its terms require reproducing them wherever the binary goes."""
    from vaultkeeper.core.archive import platform_slug

    assert (_ROOT / "external" / "bin" / platform_slug() / "License.txt").is_file()


def test_the_save_editors_lazy_screens_are_named():
    """Vaultkeeper opens the editor, whose screens are imported by section key."""
    spec = _spec()
    assert "nwnsaveeditor.ui.editor.screens" in spec
    assert "vaultkeeper.ui.dialogs" in spec


@pytest.mark.parametrize("module", ["QtWebEngineCore", "Qt3DCore", "QtQuick"])
def test_the_qt_we_never_use_is_excluded(module):
    assert module in _spec()


def test_nothing_we_import_is_excluded():
    """QtSql stays: the campaign database work may need it, unlike the editor."""
    spec = _spec()
    for needed in ("PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtCore", "PySide6.QtSvg"):
        assert f'"{needed}"' not in spec, f"{needed} is used and must not be excluded"


def test_a_macos_artifact_says_which_cpu_it_is_for():
    driver = (_ROOT / "scripts" / "build_app.py").read_text(encoding="utf-8")
    assert "macos-{mac_arch()}" in driver


def test_build_output_is_not_committed():
    ignored = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/dist/" in ignored and "/build/" in ignored


def _load_build_app():
    import importlib.util

    path = _ROOT / "scripts" / "build_app.py"
    spec = importlib.util.spec_from_file_location("vk_build_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


def test_dmg_creation_retries_while_the_source_is_busy(tmp_path, monkeypatch):
    """CI's freshly-written .app is still being indexed, so hdiutil intermittently
    reports 'Resource busy'; that must be retried, not fail the build."""
    build_app = _load_build_app()
    results = [
        _FakeResult(1, "hdiutil: create failed - Resource busy"),
        _FakeResult(1, "hdiutil: create failed - Resource busy"),
        _FakeResult(0),
    ]
    calls = []

    def fake_run(*_a, **_k):
        calls.append(1)
        return results.pop(0)

    monkeypatch.setattr(build_app.subprocess, "run", fake_run)
    monkeypatch.setattr(build_app.time, "sleep", lambda _s: None)

    build_app._create_dmg(tmp_path / "src", tmp_path / "out.dmg")
    assert len(calls) == 3, "it should retry past the two busy failures"


def test_dmg_creation_does_not_retry_a_real_error(tmp_path, monkeypatch):
    """A genuine failure (not 'busy') is raised at once — no pointless retries."""
    import subprocess

    build_app = _load_build_app()
    calls = []

    def fake_run(*_a, **_k):
        calls.append(1)
        return _FakeResult(1, "hdiutil: no space left on device")

    monkeypatch.setattr(build_app.subprocess, "run", fake_run)
    monkeypatch.setattr(build_app.time, "sleep", lambda _s: None)

    with pytest.raises(subprocess.CalledProcessError):
        build_app._create_dmg(tmp_path / "src", tmp_path / "out.dmg")
    assert len(calls) == 1, "a non-busy error must not be retried"
