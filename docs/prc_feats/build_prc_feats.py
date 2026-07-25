#!/usr/bin/env python3
"""Regenerate ``game/data/PRC Feats.json`` from the PRC8 online manual.

The Character Explorer maps a ``.bic`` FeatList id -> name by *line index* in the
bundled ``Feat Names.txt`` (base NWN, ids 0-1115). PRC (Player Resource
Consortium) adds thousands of feats whose ids run into the tens of thousands, so
those feats fall off the end of the base table and vanish. This script builds the
extension table PRC feats are looked up in.

**Source of truth** (owner's guidance): the PRC8 manual at raptio.us. Its master
alphabetical index links every feat to its own page, and the *feat id is embedded
in that page's URL* — and that id is exactly the id stored in the ``.bic``
FeatList. So the index gives ``id -> name`` directly (the link target's number is
the id, the link text is the name).

    https://raptio.us/english/content/feats/alphasortedfeats.html
      <a href="../class_feats/2213.html" ...>Divine Strike</a>   ->  2213: "Divine Strike"

The index uses four sibling directories under ``.../content/`` — ``feats``,
``class_feats``, ``epic_feats`` and ``class_epic_feats`` — all sharing the single
feat.2da id space.

**Grounded, not invented** (project rule): every name here comes verbatim from
raptio.us. Two deliberate exclusions keep the data honest rather than complete:

* Names the site itself never supplies cleanly — a handful of poorly-named PRC
  feats carry a multi-paragraph *description* in the name field (both in the index
  link text and on their own page). We drop any name containing a newline (and any
  empty/punctuation-only name) so it surfaces as ``Unknown feat <id>`` in the UI
  rather than dumping a paragraph. None affect real characters observed so far.
* Base ids (< the base ``Feat Names.txt`` length) — the base table stays the sole
  authority there (``CharacterReference.feats`` looks it up first), so this file
  only carries the extension (id >= 1116).

**Supplemental ids.** The alphabetical index is not exhaustive of feat.2da: a few
feats real characters actually have (Jump, Lightning Bolt, ...) are absent from it
but *do* have their own page. Rather than crawl all ~26k ids, we resolve a small
supplemental list — ids observed in real ``.bic`` files but missing from the index
— from each id's own page (``<title> :: Content :: NAME``). Grounding over
completeness: we name what real data uses, from the authoritative page.

Run: ``python docs/prc_feats/build_prc_feats.py`` (needs network access to
raptio.us). Writes ``src/vaultkeeper/game/data/PRC Feats.json``.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://raptio.us/english/content"
INDEX_URL = f"{BASE}/feats/alphasortedfeats.html"
FEAT_DIRS = ("feats", "class_feats", "epic_feats", "class_epic_feats")

#: Ids seen in real localvault ``.bic`` files that the alphabetical index omits.
#: Resolved individually from each id's own PRC page (see module docstring).
SUPPLEMENTAL_IDS = (2884, 2898, 4978, 4995, 4996, 4997, 4999)

#: Base ``Feat Names.txt`` owns ids [0, BASE_FEAT_COUNT); this table is the extension.
BASE_FEAT_COUNT = 1116

_OUT = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data/PRC Feats.json"

_ANCHOR = re.compile(r'<a\s+href="\.\./([a-z_]+)/([0-9]+)\.html"[^>]*>(.*?)</a>', re.S)
_TITLE = re.compile(r"<title>.*?::\s*Content\s*::\s*(.*?)</title>", re.S)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("ISO-8859-1")


def _clean(text: str) -> str:
    """Strip nested tags + unescape entities from an anchor's / title's text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _usable(name: str) -> bool:
    """A real feat name is a single non-empty line, not a punctuation placeholder."""
    return bool(name) and "\n" not in name and not set(name) <= set("*-?. ")


def parse_index(text: str) -> dict[int, str]:
    """``id -> name`` for every anchor in the alphabetical index (first id wins)."""
    ids: dict[int, str] = {}
    for _dir, num, inner in _ANCHOR.findall(text):
        ids.setdefault(int(num), _clean(inner))
    return ids


def resolve_page(feat_id: int) -> str | None:
    """Name for a feat id from its own page's ``<title>``, trying each directory."""
    for directory in FEAT_DIRS:
        try:
            page = _get(f"{BASE}/{directory}/{feat_id}.html")
        except Exception:
            continue
        match = _TITLE.search(page)
        if match:
            return _clean(match.group(1))
    return None


def build() -> dict[str, str]:
    ids = parse_index(_get(INDEX_URL))
    for feat_id in SUPPLEMENTAL_IDS:
        if feat_id not in ids:
            name = resolve_page(feat_id)
            if name:
                ids[feat_id] = name
            time.sleep(0.3)
    return {
        str(feat_id): name
        for feat_id, name in sorted(ids.items())
        if feat_id >= BASE_FEAT_COUNT and _usable(name)
    }


def main() -> int:
    table = build()
    _OUT.write_text(
        json.dumps(table, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(table)} PRC feats -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
