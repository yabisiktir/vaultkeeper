"""Render Vaultkeeper's main window to a PNG, without a human at the screen.

    python scripts/window_shot.py
    scripts/win_test.sh --shot          # the same thing, inside a Windows bottle

Why
---
A test proves the widgets behave. It does not prove they are *visible*: a label
can be clipped, a panel can come up empty, a theme can render black on black,
and every assertion still passes. Those only show up by looking -- which is why
they survive until somebody runs the app on the platform that has the problem.

This builds the real window, lets Qt lay it out and paint, and writes what came
out. Run it under Wine (see ``win_test.sh --shot``) and the PNG shows the
*Windows* rendering, so the two can be compared side by side from one machine.
That is how a clipped tab label in the save editor was found: macOS's UI font is
narrow enough to hide it, Windows' is not.

It grabs from inside Qt rather than shelling out to a screenshot tool. That
captures the window itself rather than whatever is on the desktop, needs no
Screen Recording permission, and works with no display attached at all --
``QT_QPA_PLATFORM=offscreen`` is enough.

The profile is built in a scratch directory, so a run never touches a real
store. Point --store-root at a real one to photograph real content instead.

Exit status is the number of windows that failed to build, so it is usable as a
smoke check in a pipeline.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

DEFAULT_OUT = REPO / "build" / "screenshots"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="window_shot.py",
        description="Render Vaultkeeper's main window to a PNG.",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"directory for the PNGs (default: {DEFAULT_OUT.relative_to(REPO)})",
    )
    parser.add_argument(
        "--store-root", type=Path, default=None,
        help="an existing store to open; a scratch one is created if omitted",
    )
    parser.add_argument(
        "--game-root", type=Path, default=None,
        help="the installed game; only affects what the window reports about it",
    )
    parser.add_argument(
        "--profile", default="Screenshot", help="profile name to open"
    )
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=920)
    parser.add_argument(
        "--settle", type=int, default=4000,
        help="milliseconds to let timers and deferred fills finish before grabbing",
    )
    parser.add_argument(
        "--prefix", default="", help="prefix for the output filenames, e.g. 'win-'"
    )
    return parser.parse_args(argv)


def settle(app, ms: int) -> None:
    """Run the event loop for a while.

    Not cosmetic: several panels fill on a QTimer so that a large store does not
    block the window, and grabbing too early photographs a half-built one.
    """
    from PySide6.QtCore import QDeadlineTimer, QEventLoop

    deadline = QDeadlineTimer(ms)
    while not deadline.hasExpired():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def grab(widget, path: Path, app, args) -> None:
    widget.resize(args.width, args.height)
    widget.show()
    settle(app, args.settle)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not widget.grab().save(str(path)):
        raise RuntimeError(f"Qt could not write {path}")
    size = widget.size()
    print(f"  wrote {path}  ({size.width()}x{size.height()})")


def shoot_main_window(app, args, scratch: Path) -> None:
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.main_window import MainWindow
    from vaultkeeper.ui.session import configure_profile

    store_root = args.store_root or scratch / "Store"
    game_root = args.game_root or scratch / "NWN"
    print(f"  store root: {store_root}")
    print(f"  game root : {game_root}")

    controller = configure_profile(
        str(game_root),
        args.profile,
        settings=Settings(store_root=str(store_root)),
        settings_path=scratch / "settings.json",
    )
    window = MainWindow(controller)
    grab(window, args.out / f"{args.prefix}vaultkeeper.png", app, args)
    window.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    print(f"platform plugin: {app.platformName()}")

    failures = 0
    with tempfile.TemporaryDirectory(prefix="vaultkeeper-shot-") as tmp:
        scratch = Path(tmp)
        for label, shoot in (("main window", shoot_main_window),):
            print(f"{label}:")
            try:
                shoot(app, args, scratch)
            except Exception:
                failures += 1
                traceback.print_exc()
                print(f"  !! {label} FAILED")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
