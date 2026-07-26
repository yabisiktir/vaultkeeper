#!/usr/bin/env python3
"""Regenerate ``game/data/Item Property Names.json`` from the Leto-PRC help.

An item's ``PropertiesList`` stores each magical property as a ``PropertyName`` id
(itempropdef.2da row) plus Subtype / CostTable / CostValue. To name the property
type ("Ability Bonus", "Enhancement Bonus", "Bonus Feat", …) we need that id-to-name
table. The Leto-PRC character editor documents it in a readable help page.

**Source**: the owner's Leto-PRC install, ``Help/Advanced/PropertyName.html`` — a
plain ``<id>: <name>`` list covering base NWN + PRC item properties. Pass the
``Help/Advanced`` directory as ``argv[1]`` (default
``~/Documents/leto/Leto-PRC/Help/Advanced``).

**Grounded, not invented**: names are verbatim from the page. The small subtype
tables (abilities, damage types) live as constants in
:mod:`vaultkeeper.game.item_properties` (standard NWN reference data).

Run: ``python docs/prc_feats/build_item_properties.py [leto_advanced_dir]``.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

_OUT = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data/Item Property Names.json"
_ROW = re.compile(r"(\d+):\s*([^\n0-9][^\n]*?)\s*(?=\d+:|\Z)")


def build(advanced_dir: Path) -> dict[str, str]:
    page = (advanced_dir / "PropertyName.html").read_text(encoding="ISO-8859-1")
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    names: dict[int, str] = {}
    for match in _ROW.finditer(text):
        name = match.group(2).strip()
        if name:
            names[int(match.group(1))] = name
    return {str(pid): names[pid] for pid in sorted(names)}


def main(argv: list[str]) -> int:
    default = Path.home() / "Documents/leto/Leto-PRC/Help/Advanced"
    advanced = Path(argv[1]) if len(argv) > 1 else default
    if not (advanced / "PropertyName.html").is_file():
        raise SystemExit(f"PropertyName.html not found under {advanced}")
    table = build(advanced)
    if table.get("0") != "Ability Bonus":
        raise SystemExit(f"unexpected first property {table.get('0')!r} — aborting")
    _OUT.write_text(
        json.dumps(table, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(table)} item property names -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
