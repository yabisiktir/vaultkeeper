#!/usr/bin/env python3
"""Regenerate ``game/data/PRC Feat Descriptions.json.gz`` from the PRC8 manual.

Companion to :mod:`build_prc_feats`. That script gives PRC feats their *names*;
this one gives them their *descriptions*, so the Character Explorer's feat pane
shows real text instead of "Feat description is not available." for community
feats.

**Source**: the owner's local download of the PRC8 HTML manual (same export as
raptio.us, but offline so all ~15k pages are cheap to read). Each feat page has
its body text in the ``<div>`` right after the ``div_paddedicon`` block::

    content/class_feats/2213.html
      <div class="div_paddedicon"></div>
      <div>Type of Feat: Class Specific<br />Prerequisite: ...<br />Use: Automatic.</div>

Pass the manual root as ``argv[1]`` (the directory containing ``english/content``);
it defaults to ``~/Downloads/manual``. Descriptions are keyed by the *feat id*
(the page's number = the ``.bic`` FeatList id), for exactly the ids already in the
bundled ``PRC Feats.json`` so names and descriptions stay aligned.

**Grounded, not invented**: every description is the verbatim page body (``<br>``
→ newline, tags stripped, entities unescaped, runs of blank lines collapsed).
Output is gzip-compressed JSON (~8.6 MB of text → ~1.1 MB) and loaded transparently
by ``CharacterReference`` (see ``load_prc_feat_descriptions``).

Run: ``python docs/prc_feats/build_prc_feat_descriptions.py [manual_root]``.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import sys
from pathlib import Path

#: Feat subdirectories under ``<manual>/english/content`` (a feat id lives in one).
FEAT_DIRS = ("feats", "class_feats", "epic_feats", "class_epic_feats", "master_feats")

_DATA = Path(__file__).resolve().parents[2] / "src/vaultkeeper/game/data"
_FEAT_NAMES = _DATA / "PRC Feats.json"
_OUT = _DATA / "PRC Feat Descriptions.json.gz"

_DESC = re.compile(r'div_paddedicon"\s*>.*?</div>\s*<div>(.*?)</div>', re.S)


def extract_description(page: str) -> str | None:
    """The feat page's body text — the div after ``div_paddedicon`` — or ``None``."""
    match = _DESC.search(page)
    if not match:
        return None
    body = re.sub(r"<br\s*/?>", "\n", match.group(1))
    body = re.sub(r"<[^>]+>", "", body)
    body = html.unescape(body).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body or None


def build(manual_root: Path) -> dict[str, str]:
    content = manual_root / "english" / "content"
    feat_ids = [int(k) for k in json.loads(_FEAT_NAMES.read_text(encoding="utf-8"))]
    descriptions: dict[int, str] = {}
    for feat_id in feat_ids:
        for directory in FEAT_DIRS:
            page_path = content / directory / f"{feat_id}.html"
            if page_path.is_file():
                text = extract_description(page_path.read_text(encoding="ISO-8859-1"))
                if text:
                    descriptions[feat_id] = text
                break
    return {str(feat_id): descriptions[feat_id] for feat_id in sorted(descriptions)}


def main(argv: list[str]) -> int:
    manual_root = Path(argv[1]) if len(argv) > 1 else Path.home() / "Downloads/manual"
    if not (manual_root / "english" / "content").is_dir():
        raise SystemExit(f"PRC manual not found under {manual_root} (need english/content)")
    table = build(manual_root)
    payload = json.dumps(table, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with gzip.open(_OUT, "wb", compresslevel=9) as fh:
        fh.write(payload)
    print(f"wrote {len(table)} PRC feat descriptions -> {_OUT} ({_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
