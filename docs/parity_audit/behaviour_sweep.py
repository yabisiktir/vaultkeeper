#!/usr/bin/env python3
"""Find the behaviours a command diff cannot see.

Why this exists
---------------
Three instruments now, each blind where the last one looks:

* ``DIALOG_PARITY.md`` compares **controls** on screens already ported.
* ``capability_sweep.py`` compares **help topics** — user-facing capability,
  including flows with no screen. It found the first-run gap.
* this one compares **behaviours**: every ``Handles`` clause in the original.

The command diff (209 ids, in ``CAPABILITY_STATUS.md``) reads a menu item's id
and calls the port complete at 197/209. It cannot see a behaviour with no
caption and no menu entry — a right-click, a double-click, a keypress. Four such
gaps had already been found by hand and none by a tool: the Character Explorer's
Restorer button, the play-time readout, double-click-to-install, and a settings
field nothing reads.

Two checks, both cheap:

``--behaviours``
    Right-click / double-click / keypress handlers in the VB. Small enough
    (about 30) to review completely, which is the point: an instrument nobody
    finishes reading is not an instrument.

``--settings``
    Settings this port writes and never reads. A preference the user can tick
    that changes nothing is worse than a missing one, because it lies. Found
    ``startup_sound`` and ``portrait_image_web_page`` before it was written down.

Usage
-----
    python docs/parity_audit/behaviour_sweep.py --behaviours
    python docs/parity_audit/behaviour_sweep.py --settings
    VB_SOURCE=/path/to/'NWN Installer Tool' … --behaviours   # non-default source
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "vaultkeeper"
VB_DEFAULT = ROOT.parent / "NWN Installer Tool v8.0" / "NWN Installer Tool"

#: Events with no caption, no menu entry and no help button — invisible to every
#: other instrument, and where four of the found gaps lived.
QUIET_EVENTS = {
    "MouseUp",
    "MouseDown",
    "DoubleClick",
    "MouseDoubleClick",
    "ItemActivate",
    "KeyDown",
}

#: Settings whose only readers are the screens that edit them. Those two are not
#: evidence that anything *uses* the value.
_EDITORS = ("config/settings.py", "settings_dialog.py", "basic_settings.py")


def vb_source() -> Path:
    return Path(os.environ.get("VB_SOURCE", VB_DEFAULT))


def behaviours() -> list[tuple[str, str, str, str]]:
    """``(form, control, event, handler)`` for every quiet behaviour in the VB."""
    source = vb_source()
    if not source.is_dir():
        print(f"VB source not found at {source} (set VB_SOURCE)", file=sys.stderr)
        return []
    found = []
    for path in sorted(source.glob("*.vb")):
        if path.name.endswith(".Designer.vb"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(
            r"Sub\s+(\w+)\s*\([^)]*\)\s*Handles\s+([\w\s.,]+?)(?:\r?\n|$)", text
        ):
            handler, clauses = match.group(1), match.group(2)
            for clause in clauses.split(","):
                clause = clause.strip()
                if "." not in clause:
                    continue
                control, _, event = clause.rpartition(".")
                if event.strip() in QUIET_EVENTS:
                    found.append(
                        (path.stem, control.strip(), event.strip(), handler)
                    )
    return found


def dead_settings() -> list[str]:
    """Settings fields nothing outside the settings screens ever reads."""
    tree = ast.parse((SRC / "config" / "settings.py").read_text(encoding="utf-8"))
    fields = [
        node.target.id
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef) and cls.name == "Settings"
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and not node.target.id.startswith("_")
    ]
    bodies = {
        path: path.read_text(encoding="utf-8", errors="replace")
        for path in SRC.rglob("*.py")
        if not any(marker in str(path) for marker in _EDITORS)
    }
    return [
        field
        for field in fields
        if not any(re.search(rf"\b{field}\b", text) for text in bodies.values())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--behaviours", action="store_true")
    parser.add_argument("--settings", action="store_true")
    args = parser.parse_args()
    if not (args.behaviours or args.settings):
        parser.error("choose --behaviours and/or --settings")

    if args.behaviours:
        rows = behaviours()
        print(f"# Quiet behaviours in the original: {len(rows)}\n")
        for form, control, event, handler in sorted(rows):
            print(f"{form:24s} {control:22s} {event:17s} {handler}")
        print()

    if args.settings:
        dead = dead_settings()
        print(f"# Settings written but never read: {len(dead)}\n")
        for field in dead:
            print(f"   {field}")
        if dead:
            print(
                "\nA preference that changes nothing is worse than a missing one:\n"
                "it lies to whoever ticks it."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
