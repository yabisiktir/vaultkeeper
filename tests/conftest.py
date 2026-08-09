"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Run all Qt-based tests headlessly (no display needed). Set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path_factory, monkeypatch) -> Iterator[None]:
    """Redirect Vaultkeeper's config/data roots to a per-test temp home.

    ``config_root``/``data_root`` derive from :func:`vaultkeeper.app_paths._home`.
    Without this, any test that calls ``save_settings(settings)`` (no explicit
    path — e.g. MainWindow's recent-mods / window-geometry saves) would write to
    the developer's REAL ``~/Library/Application Support/Vaultkeeper`` store,
    polluting live user data and leaking state between tests (which caused the
    order-dependent recent-mods failures). Each test gets a clean isolated home.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr("vaultkeeper.app_paths._home", lambda: home)
    # ★ Patching _home() is not enough off macOS. config_root/data_root/cache_root
    # prefer the platform's environment variables and only fall back to the home
    # directory, so on Windows every test shared — and wrote into — the machine's
    # real %APPDATA%. It stayed hidden until a test saved a setting that a later
    # test read back (Recent Mods pinning), which then failed only on Windows.
    for name, sub in (
        ("APPDATA", "Roaming"),
        ("LOCALAPPDATA", "Local"),
        ("XDG_CONFIG_HOME", ".config"),
        ("XDG_DATA_HOME", ".local/share"),
        ("XDG_CACHE_HOME", ".cache"),
    ):
        monkeypatch.setenv(name, str(home / sub))
    yield


@pytest.fixture(autouse=True)
def recycle_bin(tmp_path_factory, monkeypatch) -> Iterator[Path]:
    """Send recycle-bin deletes to a per-test folder, not the machine's Trash.

    ``fs.delete(to_trash=True)`` calls ``send2trash``, which really does put the
    path in the developer's Trash — the suite was quietly leaving seven pytest
    temp folders in it per run. Worse, it made the interesting half of a
    recycle-bin delete untestable: "it can be got back" is the whole promise of
    ``restoringdeletedsavesfromtherecy.htm``, and there was nowhere to look.

    Yields the folder, so a test can assert what landed there.
    """
    import send2trash

    bin_dir = tmp_path_factory.mktemp("recycle-bin")

    def to_bin(path) -> None:
        source = Path(path)
        target = bin_dir / source.name
        # Same name twice is normal; a real recycle bin keeps both.
        count = 1
        while target.exists():
            target = bin_dir / f"{source.name} ({count})"
            count += 1
        shutil.move(str(source), str(target))

    monkeypatch.setattr(send2trash, "send2trash", to_bin)
    yield bin_dir


@pytest.fixture(autouse=True)
def _fresh_install_caches() -> Iterator[None]:
    """Empty nwnfile's install-keyed caches between tests.

    The game tables are cached against the folder they were read from, so a test
    writing different 2DA content to a path another test already used would
    otherwise be answered from that other test's data.
    """
    from nwnfile import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def temp_dir() -> Iterator[Path]:
    """A throwaway temp directory (used by the salvaged binary-reader tests)."""
    path = Path(tempfile.mkdtemp(prefix="vaultkeeper_test_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
