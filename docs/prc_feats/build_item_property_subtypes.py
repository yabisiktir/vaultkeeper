#!/usr/bin/env python3
"""Regenerate the item-property feat/spell subtype tables from the installed PRC hak.

The "Bonus Feat" and "Cast Spell" item properties store a ``Subtype`` that is an
``iprp_feats.2da`` / ``iprp_spells.2da`` *row* — an indirection, not a feat/spell
id. Those tables ship inside the PRC hakpak; each row's ``FeatIndex`` / ``SpellIndex``
column points at feat.2da / spells.2da, which the bundled name tables already
cover. This resolves the indirection so a property reads e.g.
``"Bonus Feat: Cleave"`` / ``"Cast Spell: Fireball"``.

**Source**: the owner's installed PRC 2da hak (default
``~/Documents/Neverwinter Nights/hak/prc8_2das.hak``), read with the project's
:class:`ErfReader`. Pass a different hak path as ``argv[1]``. The installed hak is
authoritative — it is newer than, and disagrees with, the Leto help's spell chart.

Output (subtype -> resolved name, so the runtime is self-contained):

* ``game/data/Item Property Feat Subtypes.json.gz``   (iprp_feats -> feat names)
* ``game/data/Item Property Spell Subtypes.json.gz``  (iprp_spells -> spell names)
* ``game/data/Item Property OnHit Spell Subtypes.json.gz`` (iprp_onhitspell -> spell)
* ``game/data/Item Property Spell Levels.json``       (iprp_spells -> innate level)

**Grounded**: FeatIndex/SpellIndex names come from the bundled feat/spell tables;
rows that don't resolve are dropped (a leftover ``Label`` fallback keeps the game's
own token when the index is present but unnamed).

Run: ``python docs/prc_feats/build_item_property_subtypes.py [prc_2das_hak]``.
"""

from __future__ import annotations

import gzip
import json
import shlex
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
from vaultkeeper.core.formats.erf_reader import ErfReader  # noqa: E402
from vaultkeeper.game.character_reference import default_reference  # noqa: E402

_DATA = _REPO / "src/vaultkeeper/game/data"
_FEAT_OUT = _DATA / "Item Property Feat Subtypes.json.gz"
_SPELL_OUT = _DATA / "Item Property Spell Subtypes.json.gz"
_SPELL_LEVEL_OUT = _DATA / "Item Property Spell Levels.json"
_ONHIT_SPELL_OUT = _DATA / "Item Property OnHit Spell Subtypes.json.gz"
_2DA = 2017


def _read_2da(reader: ErfReader, hak: Path, name: str) -> tuple[list[str], dict[int, list[str]]]:
    resource = reader.find_resource(hak, name, res_type=_2DA)
    if resource is None:
        raise SystemExit(f"{name}.2da not found in {hak}")
    lines = reader.read_resource_bytes(hak, resource).decode("latin-1").splitlines()
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


def _index_of(header: list[str], *candidates: str) -> int:
    for name in candidates:
        if name in header:
            return header.index(name)
    raise SystemExit(f"none of {candidates} in 2da header {header}")


def _resolve(hak: Path, table: str, index_col: str, name_of) -> dict[str, str]:
    reader = ErfReader()
    header, rows = _read_2da(reader, hak, table)
    idx = _index_of(header, index_col)
    label = header.index("Label") if "Label" in header else None
    out: dict[int, str] = {}
    for subtype, cols in rows.items():
        raw = cols[idx] if idx < len(cols) else "****"
        name = name_of(int(raw)) if raw not in ("****", "") and raw.lstrip("-").isdigit() else None
        if not name and label is not None and label < len(cols) and cols[label] != "****":
            name = cols[label].replace("_", " ")
        if name:
            out[subtype] = name
    return {str(k): out[k] for k in sorted(out)}


def main(argv: list[str]) -> int:
    default = Path.home() / "Documents/Neverwinter Nights/hak/prc8_2das.hak"
    hak = Path(argv[1]) if len(argv) > 1 else default
    if not hak.is_file():
        raise SystemExit(f"PRC 2da hak not found: {hak}")
    ref = default_reference()

    def feat_name(fid: int) -> str | None:
        if 0 <= fid < len(ref.feat_names):
            return ref.feat_names[fid][0]
        return ref.prc_feat_names.get(fid)

    feats = _resolve(hak, "iprp_feats", "FeatIndex", feat_name)
    spells = _resolve(hak, "iprp_spells", "SpellIndex", ref.spell_names.get)
    onhit_spells = _resolve(hak, "iprp_onhitspell", "SpellIndex", ref.spell_names.get)

    for out, table in (
        (_FEAT_OUT, feats), (_SPELL_OUT, spells), (_ONHIT_SPELL_OUT, onhit_spells)
    ):
        payload = json.dumps(table, ensure_ascii=False, sort_keys=True).encode("utf-8")
        with gzip.open(out, "wb", compresslevel=9) as fh:
            fh.write(payload)
        print(f"wrote {len(table)} subtypes -> {out}")

    # Cast Spell subtype -> the spell's innate level (iprp_spells InnateLvl column).
    header, rows = _read_2da(ErfReader(), hak, "iprp_spells")
    idx = _index_of(header, "InnateLvl")
    levels = {
        str(sub): int(cols[idx])
        for sub, cols in rows.items()
        if idx < len(cols) and cols[idx].lstrip("-").isdigit()
    }
    _SPELL_LEVEL_OUT.write_text(
        json.dumps(levels, sort_keys=True, indent=0) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(levels)} spell levels -> {_SPELL_LEVEL_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
