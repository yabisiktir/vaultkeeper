#!/usr/bin/env python3
"""Regenerate ``game/data/PRC Races.json`` from the PRC8 manual.

A ``.bic``'s ``Race`` field is a racialtypes.2da row id. The base
``character.RACE_NAMES`` table covers base NWN (0-29); PRC adds custom races at
higher ids (e.g. 159 = Bralani Eladrin), so a PRC character's race was shown as
the "Human" fallback. This builds the extension table.

**Source**: the owner's local PRC8 HTML manual, one page per race id::

    content/races/<id>.html   ->   <title> :: Content :: NAME

Pass the manual root as ``argv[1]`` (default ``~/Downloads/manual``). Race id =
racialtypes.2da row = the page number = the ``.bic`` ``Race`` field.

**Alignment guard**: base ids 0-6 must read Dwarf..Human before ids past the base
set are trusted. **Grounded, not invented**: names are verbatim page titles. Only
ids not already in base ``RACE_NAMES`` are written (base wins for its own ids).

Run: ``python docs/prc_feats/build_prc_races.py [manual_root]``.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
from vaultkeeper.game.character import RACE_NAMES  # noqa: E402

_CORE = {
    0: "Dwarf", 1: "Elf", 2: "Gnome", 3: "Halfling",
    4: "Half-Elf", 5: "Half-Orc", 6: "Human",
}
_OUT = _REPO / "src/vaultkeeper/game/data/PRC Races.json"
_TITLE = re.compile(r"<title>.*?::\s*Content\s*::\s*(.*?)</title>", re.S)


def _name(path: Path) -> str | None:
    match = _TITLE.search(path.read_text(encoding="ISO-8859-1"))
    return html.unescape(match.group(1)).strip() if match else None


def build(manual_root: Path) -> dict[str, str]:
    races_dir = manual_root / "english" / "content" / "races"
    names: dict[int, str] = {}
    for page in races_dir.glob("[0-9]*.html"):
        if page.stem.isdigit():
            name = _name(page)
            if name:
                names[int(page.stem)] = name

    for race_id, expected in _CORE.items():
        if names.get(race_id) != expected:
            raise SystemExit(
                f"alignment mismatch at race id {race_id}: "
                f"manual={names.get(race_id)!r} expected={expected!r} — aborting"
            )

    return {str(rid): names[rid] for rid in sorted(names) if rid not in RACE_NAMES}


def main(argv: list[str]) -> int:
    manual_root = Path(argv[1]) if len(argv) > 1 else Path.home() / "Downloads/manual"
    if not (manual_root / "english" / "content").is_dir():
        raise SystemExit(f"PRC manual not found under {manual_root} (need english/content)")
    table = build(manual_root)
    _OUT.write_text(
        json.dumps(table, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(table)} PRC races -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
