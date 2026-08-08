# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Vaultkeeper.

Run through ``scripts/build_app.py``. Frozen per OS: a PySide6 app cannot be
cross-built, so each artifact is produced on the machine it targets.

Vaultkeeper carries three things the editor does not:

* **7-Zip.** There is no pure-Python fallback for reading a mod's archive — see
  ``core/archive.py`` — so a build without it installs nothing. Only this
  platform's binary is bundled; shipping all four would waste 9 MB.
* **The UI image set** (~1,180 files, 19 MB), which ``ui/resources.py`` looks up
  by name at runtime, so none of it can be discovered statically.
* **The save editor**, which is a dependency rather than a copy. Freezing picks
  it up automatically; what needs saying is its lazily-imported screens.

Everything read as a file rather than a package resource has to land at the path
the code computes from ``__file__``, or the build succeeds and fails at runtime.
"""

import platform
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"


def _nwnfile_data() -> Path:
    """Where the save editor's bundled game tables actually are."""
    import nwnfile

    return Path(nwnfile.__file__).resolve().parent / "data"


def sevenzip_slug() -> str:
    """The external/bin folder for the machine being built on."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows-x64"
    return "linux-arm64" if platform.machine() in ("aarch64", "arm64") else "linux-x64"


_SLUG = sevenzip_slug()

datas = [
    # Looked up by name at runtime — nothing here is statically discoverable.
    (str(SRC / "vaultkeeper" / "ui" / "resources"), "vaultkeeper/ui/resources"),
    # Read by path relative to their own module.
    (str(SRC / "vaultkeeper" / "game" / "data"), "vaultkeeper/game/data"),
    # The published Vault download rules, as the floor under the online copy: a
    # frozen app with no network still needs a complete rule set.
    (str(SRC / "vaultkeeper" / "vault" / "data"), "vaultkeeper/vault/data"),
    # The save editor's game tables, same arrangement, from its package.
    # Located through the installed package rather than a fixed path: it may be
    # an editable install beside this repo, or site-packages on a CI runner.
    (str(_nwnfile_data()), "nwnfile/data"),
    # Application icons for both apps.
    (str(ROOT / "assets" / "icons"), "assets/icons"),
    # This platform's 7-Zip and the licence its terms require us to ship.
    (str(ROOT / "external" / "bin" / _SLUG), f"external/bin/{_SLUG}"),
    (str(ROOT / "external" / "tools.toml"), "external"),
]

hiddenimports = [
    # Imported lazily by name, so static analysis cannot see them.
    *collect_submodules("vaultkeeper.ui.dialogs"),
    *collect_submodules("nwnsaveeditor.ui.editor.screens"),
    *collect_submodules("nwnsaveeditor.ui.dialogs"),
]

#: Qt we do not use. PySide6 is large; this is where most of the saving is.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtQuick3D",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "tkinter", "matplotlib", "numpy", "scipy", "pandas", "PIL", "pytest",
]

a = Analysis(
    [str(SRC / "vaultkeeper" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vaultkeeper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX and macOS code signing do not get along
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icons" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vaultkeeper",
)

app = BUNDLE(
    coll,
    name="Vaultkeeper.app",
    icon=str(ROOT / "assets" / "icons" / "icon.icns"),
    bundle_identifier="net.vaultkeeper.app",
    version="0.0.1",
    info_plist={
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "GPL-3.0-or-later",
    },
)
