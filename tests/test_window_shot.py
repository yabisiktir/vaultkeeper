"""The screenshot script is a smoke check, so it has to keep working.

``scripts/window_shot.py`` builds the real main window and paints it to a PNG.
Its value is catching what assertions cannot -- a clipped label, an empty panel,
a theme that renders invisible -- by producing something a person can look at,
and by producing it on Windows from a Mac (see ``scripts/win_test.sh --shot``).

That only helps if the script itself still runs, which is what these check. The
run here is the whole thing end to end: a real MainWindow, laid out and painted,
written out and read back. If the window cannot be built at all, this fails long
before anybody thinks to look at a screenshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def window_shot():
    sys.path.insert(0, str(_ROOT / "scripts"))
    import window_shot as module

    return module


@pytest.mark.integration
def test_it_writes_a_png_of_the_real_main_window(window_shot, qtbot, tmp_path, monkeypatch):
    """One run, checked for everything — building the window is the slow part."""
    # The default run builds its profile in a temporary directory so a screenshot
    # never touches a real store. Watch that it is both used and cleaned up.
    created: list[Path] = []
    real_mkdtemp = window_shot.tempfile.mkdtemp

    def spy(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(window_shot.tempfile, "mkdtemp", spy)

    # Auto-detecting the EE user folder walks the real machine and takes about
    # twelve seconds here. The script should do that; this test should not, and
    # skipping it is the difference between ~13s and well under one.
    from vaultkeeper.ui import session

    monkeypatch.setattr(session, "default_game_user_path", lambda: None)

    # settle=0: the deferred fills are worth waiting for when a human will look
    # at the result, but here the question is only whether it builds and paints.
    # --store-root and --game-root keep it off any real store as well.
    failures = window_shot.main(
        ["--out", str(tmp_path), "--settle", "0", "--width", "900", "--height", "600",
         "--store-root", str(tmp_path / "Store"), "--game-root", str(tmp_path / "NWN")]
    )
    assert failures == 0

    written = list(tmp_path.glob("*.png"))
    assert written, "no screenshot was written"

    from PySide6.QtGui import QImage

    image = QImage(str(written[0]))
    assert not image.isNull(), "the file is not a readable image"
    assert (image.width(), image.height()) == (900, 600)

    assert created, "expected a scratch directory to be used"
    assert not any(p.exists() for p in created), "the scratch profile was not cleaned up"


def test_its_arguments_stay_what_the_wrapper_passes(window_shot):
    # win_test.sh --shot calls this with --prefix and --game-root; a rename here
    # would break that quietly, since the wrapper cannot type-check itself.
    args = window_shot.parse_args(["--prefix", "win-", "--game-root", "/g"])
    assert args.prefix == "win-"
    assert args.game_root == Path("/g")
    assert args.out == window_shot.DEFAULT_OUT

    wrapper = (_ROOT / "scripts" / "win_test.sh").read_text(encoding="utf-8")
    assert "--prefix win-" in wrapper
    assert "window_shot.py" in wrapper


def test_the_output_directory_is_ignored_by_git(window_shot):
    # The default lands in build/, which .gitignore covers. A screenshot is
    # output, not source, and committing one by reflex is how a repo ends up
    # with somebody's save folder in it.
    default = window_shot.DEFAULT_OUT.relative_to(_ROOT)
    assert default.parts[0] == "build"
    ignored = (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any(line.strip() in {"build/", "/build/"} for line in ignored)
