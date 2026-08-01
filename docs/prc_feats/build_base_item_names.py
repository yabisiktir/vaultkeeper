#!/usr/bin/env python3
"""Regenerate ``game/data/Base Item Names.json`` from the base game's ``baseitems.2da``.

An item's ``BaseItem`` field is a ``baseitems.2da`` row (Longsword, Ring, Helmet …).
That table lives in the base game's BIF archive, and its ``Name`` column is a
``dialog.tlk`` StrRef. Read it with the KEY/BIF reader + resolve the StrRef via the
tlk, so the Inventory tab can show an item's *type*.

**Source**: the game install (default the ``nwn_path`` Steam location). Pass the
install root as ``argv[1]``. Writes ``{ "<base item id>": "type name" }``.

Run: ``python docs/prc_feats/build_base_item_names.py [game_root]``.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
from nwnfile.formats.key_bif_reader import KeyBifReader  # noqa: E402
from nwnfile.formats.tlk_reader import TlkReader  # noqa: E402

_OUT = _REPO / "src/vaultkeeper/game/data/Base Item Names.json"
_DEFAULT_ROOT = Path.home() / (
    "Library/Application Support/Steam/steamapps/common/Neverwinter Nights"
)


def _parse_2da(text: str) -> tuple[list[str], dict[int, list[str]]]:
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.strip().startswith("2DA")) + 1
    while not lines[i].strip():
        i += 1
    header = lines[i].split()
    rows: dict[int, list[str]] = {}
    for line in lines[i + 1:]:
        if not line.strip():
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        if parts and parts[0].isdigit():
            rows[int(parts[0])] = parts[1:]
    return header, rows


def _dialog_tlk(game_root: Path):
    for lang in ("en", "de", "fr", "it", "es", "pl"):
        candidate = game_root / "lang" / lang / "data" / "dialog.tlk"
        if candidate.is_file():
            return TlkReader().read(candidate)
    return None


def build(game_root: Path) -> dict[str, str]:
    reader = KeyBifReader.for_install(game_root)
    if reader is None:
        raise SystemExit(f"no KEY/BIF archive under {game_root}/data")
    text = reader.read_2da_text("baseitems")
    if text is None:
        raise SystemExit("baseitems.2da not found in the base data")
    tlk = _dialog_tlk(game_root)
    if tlk is None:
        raise SystemExit(f"dialog.tlk not found under {game_root}/lang/*/data")

    header, rows = _parse_2da(text)
    name_idx = header.index("Name")
    names: dict[int, str] = {}
    for item_id, cols in rows.items():
        raw = cols[name_idx] if name_idx < len(cols) else "****"
        if raw not in ("****", "") and raw.lstrip("-").isdigit():
            text_value = tlk.get(int(raw))
            if text_value:
                names[item_id] = text_value
    return {str(k): names[k] for k in sorted(names)}


def main(argv: list[str]) -> int:
    game_root = Path(argv[1]) if len(argv) > 1 else _DEFAULT_ROOT
    table = build(game_root)
    _OUT.write_text(
        json.dumps(table, ensure_ascii=False, sort_keys=True, indent=0) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(table)} base item names -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
