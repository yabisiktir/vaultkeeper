#!/usr/bin/env python3
"""Regenerate ``game/data/PRC Classes.json`` from the PRC8 manual.

The Character Explorer names a character's classes from the base
``character.CLASS_NAMES`` table (base NWN class ids). PRC adds ~200 prestige/base
classes at higher ids; a ``.bic`` that has one stored a class id the port didn't
know, so it was dropped from the class breakdown (only its levels counted). This
builds the extension table so those classes show by name.

**Source**: the owner's local PRC8 HTML manual. Class pages live in two dirs and
share one id space (id = classes.2da row = the ``.bic`` ``Class`` field = the
page number)::

    content/base_classes/<id>.html       (Barbarian..Wizard + PRC base classes)
    content/prestige_classes/<id>.html   (creature classes + PRC prestige classes)
      <title> :: Content :: NAME

Pass the manual root as ``argv[1]`` (default ``~/Downloads/manual``).

**Alignment guard**: the core PC class ids 0-10 must read Barbarian..Wizard,
proving the manual's class id space still lines up with the ``.bic``/base table
before we trust ids past it. **Grounded, not invented**: names are verbatim page
titles. Only ids *not* already in base ``CLASS_NAMES`` are written (base wins for
its own ids — e.g. it keeps "Red Dragon Disciple" over the manual's "Dragon
Disciple").

Run: ``python docs/prc_feats/build_prc_classes.py [manual_root]``.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
from vaultkeeper.game.character import CLASS_NAMES  # noqa: E402

CLASS_DIRS = ("base_classes", "prestige_classes")
_CORE_PC = {
    0: "Barbarian", 1: "Bard", 2: "Cleric", 3: "Druid", 4: "Fighter", 5: "Monk",
    6: "Paladin", 7: "Ranger", 8: "Rogue", 9: "Sorcerer", 10: "Wizard",
}

_OUT = _REPO / "src/vaultkeeper/game/data/PRC Classes.json"
_DESC_OUT = _REPO / "src/vaultkeeper/game/data/PRC Class Descriptions.json.gz"
_TITLE = re.compile(r"<title>.*?::\s*Content\s*::\s*(.*?)</title>", re.S)
_DESC = re.compile(r'div_paddedicon"\s*>.*?</div>\s*<div>(.*?)</div>', re.S)


def _parse(path: Path) -> tuple[str | None, str | None]:
    page = path.read_text(encoding="ISO-8859-1")
    title = _TITLE.search(page)
    name = html.unescape(title.group(1)).strip() if title else None
    body = _DESC.search(page)
    desc = None
    if body:
        text = re.sub(r"<br\s*/?>", "\n", body.group(1))
        text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
        desc = re.sub(r"\n{3,}", "\n\n", text) or None
    return name, desc


def build(manual_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    content = manual_root / "english" / "content"
    names: dict[int, str] = {}
    descs: dict[int, str] = {}
    for directory in CLASS_DIRS:
        for page in (content / directory).glob("[0-9]*.html"):
            if not page.stem.isdigit():
                continue
            class_id = int(page.stem)
            name, desc = _parse(page)
            if name and class_id not in names:
                names[class_id] = name
                if desc:
                    descs[class_id] = desc

    for class_id, expected in _CORE_PC.items():
        if names.get(class_id) != expected:
            raise SystemExit(
                f"alignment mismatch at class id {class_id}: "
                f"manual={names.get(class_id)!r} expected={expected!r} — aborting"
            )

    extension = [cid for cid in sorted(names) if cid not in CLASS_NAMES]
    return (
        {str(cid): names[cid] for cid in extension},
        {str(cid): descs[cid] for cid in extension if cid in descs},
    )


def main(argv: list[str]) -> int:
    manual_root = Path(argv[1]) if len(argv) > 1 else Path.home() / "Downloads/manual"
    if not (manual_root / "english" / "content").is_dir():
        raise SystemExit(f"PRC manual not found under {manual_root} (need english/content)")
    names, descs = build(manual_root)
    _OUT.write_text(
        json.dumps(names, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    payload = json.dumps(descs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with gzip.open(_DESC_OUT, "wb", compresslevel=9) as fh:
        fh.write(payload)
    print(f"wrote {len(names)} PRC classes -> {_OUT}")
    print(f"wrote {len(descs)} PRC class descriptions -> {_DESC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
