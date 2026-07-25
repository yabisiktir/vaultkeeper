#!/usr/bin/env python3
"""Regenerate the bundled PRC skill tables from the PRC8 manual.

Companion to :mod:`build_prc_feats`. The Character Explorer maps a ``.bic``
SkillList *by position* — the Nth skill struct's ``Rank`` is skill id N, named by
line N of the bundled ``Skill Names.txt`` (base NWN, ids 0-27). PRC adds skills at
ids 28+, which fall past that table, so :meth:`CharacterReference.skills` showed
them as ``Unknown 1``, ``Unknown 2`` ... This builds the extension tables:

* ``game/data/PRC Skills.json``             — ``{"<skill id>": "name"}``
* ``game/data/PRC Skill Descriptions.json`` — ``{"<skill id>": "text"}``

**Source**: the owner's local PRC8 HTML manual. Each skill has its own page::

    content/skills/<id>.html
      <title> :: Content :: NAME      -> the name
      <div> after div_paddedicon      -> the description body

Pass the manual root as ``argv[1]`` (default ``~/Downloads/manual``). Skill ids
are positional (id = skills.2da row = the page number = the ``.bic`` SkillList
index).

**Alignment guard**: the base ids (0 .. base count - 1) must match the bundled
``Skill Names.txt`` line for line, proving the manual's id space still lines up
with ours before we trust ids past it. **Grounded, not invented**: names are
verbatim page titles, descriptions verbatim page bodies. Only ids >= the base
``Skill Names.txt`` length are written (base owns 0-27).

Run: ``python docs/prc_feats/build_prc_skills.py [manual_root]``.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

_DATA = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data"
_BASE_NAMES = _DATA / "Skill Names.txt"
_NAMES_OUT = _DATA / "PRC Skills.json"
_DESC_OUT = _DATA / "PRC Skill Descriptions.json"

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


def _base_names() -> list[str]:
    """Bundled base ``Skill Names.txt`` — one name per line, index = skill id."""
    data = _BASE_NAMES.read_bytes()
    has_bom = data[:2] in (b"\xff\xfe", b"\xfe\xff")
    text = data.decode("utf-16") if has_bom else data.decode("latin-1")
    return text.splitlines()


def build(manual_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    base = _base_names()
    skills_dir = manual_root / "english" / "content" / "skills"
    names: dict[int, str] = {}
    descs: dict[int, str] = {}
    for page in skills_dir.glob("[0-9]*.html"):
        if not page.stem.isdigit():
            continue
        name, desc = _parse(page)
        skill_id = int(page.stem)
        if name:
            names[skill_id] = name
        if desc:
            descs[skill_id] = desc

    # Alignment guard: the manual's base ids must match our bundled base table.
    for skill_id, base_name in enumerate(base):
        if names.get(skill_id) != base_name:
            raise SystemExit(
                f"alignment mismatch at skill id {skill_id}: "
                f"manual={names.get(skill_id)!r} base={base_name!r} — aborting"
            )

    extension = [sid for sid in sorted(names) if sid >= len(base)]
    return (
        {str(sid): names[sid] for sid in extension},
        {str(sid): descs[sid] for sid in extension if sid in descs},
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
    _DESC_OUT.write_text(
        json.dumps(descs, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(names)} PRC skills -> {_NAMES_OUT}")
    print(f"wrote {len(descs)} PRC skill descriptions -> {_DESC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
