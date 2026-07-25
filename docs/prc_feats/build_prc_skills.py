#!/usr/bin/env python3
"""Regenerate ``game/data/PRC Skills.json`` from the PRC8 online manual.

Companion to :mod:`build_prc_feats`. The Character Explorer maps a ``.bic``
SkillList *by position* — the Nth skill struct's ``Rank`` is skill id N, named by
line N of the bundled ``Skill Names.txt`` (base NWN, ids 0-27). PRC adds skills at
ids 28+, which fall past that table, so :meth:`CharacterReference.skills` showed
them as ``Unknown 1``, ``Unknown 2`` ... This builds the extension table.

**Source of truth**: the PRC8 manual's per-skill pages, one file per skill id::

    https://raptio.us/english/content/skills/<id>.html   ->  <title> :: Content :: NAME

Skill ids are positional (id = skills.2da row = the page's number = the ``.bic``
SkillList index), so the page number *is* the id. As a safety guard the script
re-fetches the base ids (0 .. base count - 1) and refuses to write unless every
one matches the bundled ``Skill Names.txt`` line — proving the site's id space is
still aligned with ours before we trust ids past the base range.

**Grounded, not invented**: every name comes verbatim from the page ``<title>``.
Only ids >= the base ``Skill Names.txt`` length are written (base owns 0-27;
``CharacterReference.skills`` looks it up first).

Run: ``python docs/prc_feats/build_prc_skills.py`` (needs network access to
raptio.us). Writes ``src/vaultkeeper/game/data/PRC Skills.json``.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://raptio.us/english/content"
SKILLS_DIR_URL = f"{BASE}/skills/"

_DATA = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data"
_BASE_NAMES = _DATA / "Skill Names.txt"
_OUT = _DATA / "PRC Skills.json"

_PAGE = re.compile(r'href="([0-9]+)\.html"')
_TITLE = re.compile(r"<title>.*?::\s*Content\s*::\s*(.*?)</title>", re.S)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("ISO-8859-1")


def _page_name(feat_id: int) -> str | None:
    match = _TITLE.search(_get(f"{BASE}/skills/{feat_id}.html"))
    return html.unescape(match.group(1)).strip() if match else None


def _base_names() -> list[str]:
    """Bundled base ``Skill Names.txt`` — one name per line, index = skill id."""
    data = _BASE_NAMES.read_bytes()
    has_bom = data[:2] in (b"\xff\xfe", b"\xfe\xff")
    text = data.decode("utf-16") if has_bom else data.decode("latin-1")
    return text.splitlines()


def build() -> dict[str, str]:
    base = _base_names()
    ids = sorted({int(n) for n in _PAGE.findall(_get(SKILLS_DIR_URL))})
    names = {i: _page_name(i) for i in ids if (time.sleep(0.15) or True)}

    # Alignment guard: the site's base ids must match our bundled base table,
    # else the id spaces have diverged and ids past the base range can't be trusted.
    for skill_id, base_name in enumerate(base):
        if names.get(skill_id) != base_name:
            raise SystemExit(
                f"alignment mismatch at skill id {skill_id}: "
                f"site={names.get(skill_id)!r} base={base_name!r} — aborting"
            )

    return {
        str(skill_id): names[skill_id]
        for skill_id in ids
        if skill_id >= len(base) and names.get(skill_id)
    }


def main() -> int:
    table = build()
    _OUT.write_text(
        json.dumps(table, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(table)} PRC skills -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
