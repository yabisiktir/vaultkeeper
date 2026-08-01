"""Vaultkeeper's application icon."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_ICONS = _ROOT / "assets" / "icons"


@pytest.mark.parametrize("size", [16, 32, 48, 64, 128, 256, 512, 1024])
def test_every_size_is_committed(size):
    assert (_ICONS / f"icon_{size}.png").is_file()


def test_the_installer_formats_are_built():
    assert (_ICONS / "icon.ico").is_file()
    icns = _ICONS / "icon.icns"
    assert icns.is_file() and icns.read_bytes()[:4] == b"icns"


def test_the_windows_icon_reaches_256():
    data = (_ICONS / "icon.ico").read_bytes()
    _, _kind, count = struct.unpack_from("<HHH", data, 0)
    sizes = {struct.unpack_from("<BBBBHHII", data, 6 + i * 16)[0] or 256 for i in range(count)}
    assert 256 in sizes, "modern Windows icon views want 256"


def test_the_app_icon_is_no_longer_a_single_16px_image(qtbot):
    """It used to return one 16x16 PNG, which every larger context scaled up."""
    from vaultkeeper.ui import resources as R

    icon = R.app_icon()
    widths = sorted(s.width() for s in icon.availableSizes())
    assert max(widths) >= 512, f"largest is only {max(widths)}px"
    assert len(widths) >= 6, "one size means scaling everywhere"


def test_it_falls_back_when_the_generated_assets_are_missing(qtbot, monkeypatch):
    """A bare checkout without a make_icons run must still show something."""
    from vaultkeeper.ui import resources as R

    monkeypatch.setattr(R, "app_icon_dir", lambda: None)
    assert not R.app_icon().isNull()


def test_it_is_found_from_a_frozen_layout(monkeypatch, tmp_path):
    import sys

    from vaultkeeper.ui import resources as R

    frozen = tmp_path / "assets" / "icons"
    frozen.mkdir(parents=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert R.app_icon_dir() == frozen


def test_the_two_apps_share_a_look_but_not_a_mark():
    """Vaultkeeper ships the editor, so they should read as a family — and still
    be told apart in a dock."""
    import sys

    from PySide6.QtGui import QImage

    sys.path.insert(0, str(_ROOT / "scripts"))
    import make_icons

    mine = make_icons.draw(256)
    theirs = QImage(str(_ROOT.parent / "nwn-save-editor" / "assets" / "icons" / "icon_256.png"))
    if theirs.isNull():
        pytest.skip("the editor checkout is not beside this one")

    assert mine.size() == theirs.size()
    differing = sum(
        mine.pixel(x, y) != theirs.pixel(x, y)
        for x in range(0, 256, 4) for y in range(0, 256, 4)
    )
    assert differing > 200, "the two marks are too alike to tell apart"
