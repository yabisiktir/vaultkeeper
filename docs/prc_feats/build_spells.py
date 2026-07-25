#!/usr/bin/env python3
"""Regenerate the bundled spell tables from the PRC8 manual.

The Character Explorer never read a ``.bic``'s spell lists, so there was no spell
name table at all. This builds one covering *both* base NWN and PRC spells (there
is no base spell file to preserve — the manual is the sole source):

* ``game/data/Spell Names.json``            — ``{"<spell id>": "name"}``
* ``game/data/Spell Descriptions.json.gz``  — ``{"<spell id>": "text"}`` (gzipped)

**Source**: the owner's local PRC8 HTML manual. Spell pages live in two dirs and
share one id space (id = spells.2da row = the ``.bic`` ``Spell`` WORD = the page
number)::

    content/spells/<id>.html        (base + PRC spells)
    content/epic_spells/<id>.html   (epic spells)
      <title> :: Content :: NAME          -> the name
      <div> after div_paddedicon          -> the description body

Pass the manual root as ``argv[1]`` (default ``~/Downloads/manual``).

**Grounded, not invented**: names are verbatim page titles, descriptions the
verbatim page body (``<br>`` → newline, tags stripped). Id alignment is sanity-
checked semantically — the caster's low-level known spells resolve to real
cantrips (Resistance/Daze/Light/…) — since there is no prior spell table to diff
against.

Run: ``python docs/prc_feats/build_spells.py [manual_root]``.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import sys
from pathlib import Path

SPELL_DIRS = ("spells", "epic_spells")

_DATA = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data"
_NAMES_OUT = _DATA / "Spell Names.json"
_DESC_OUT = _DATA / "Spell Descriptions.json.gz"

_TITLE = re.compile(r"<title>.*?::\s*Content\s*::\s*(.*?)</title>", re.S)
_DESC = re.compile(r'div_paddedicon"\s*>.*?</div>\s*<div>(.*?)</div>', re.S)


def _parse(page: str) -> tuple[str | None, str | None]:
    title = _TITLE.search(page)
    name = html.unescape(title.group(1)).strip() if title else None
    if name and ("\n" in name or set(name) <= set("*-?. ")):
        name = None
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
    for directory in SPELL_DIRS:
        for page_path in (content / directory).glob("[0-9]*.html"):
            if not page_path.stem.isdigit():
                continue
            spell_id = int(page_path.stem)
            name, desc = _parse(page_path.read_text(encoding="ISO-8859-1"))
            if name is not None:
                names.setdefault(spell_id, name)
            if desc is not None:
                descs.setdefault(spell_id, desc)
    return (
        {str(k): names[k] for k in sorted(names)},
        {str(k): descs[k] for k in sorted(descs)},
    )


def main(argv: list[str]) -> int:
    manual_root = Path(argv[1]) if len(argv) > 1 else Path.home() / "Downloads/manual"
    if not (manual_root / "english" / "content").is_dir():
        raise SystemExit(f"PRC manual not found under {manual_root} (need english/content)")
    names, descs = build(manual_root)
    _NAMES_OUT.write_text(
        json.dumps(names, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    payload = json.dumps(descs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with gzip.open(_DESC_OUT, "wb", compresslevel=9) as fh:
        fh.write(payload)
    print(f"wrote {len(names)} spell names -> {_NAMES_OUT}")
    print(f"wrote {len(descs)} spell descriptions -> {_DESC_OUT} ({_DESC_OUT.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
