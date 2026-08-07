#!/usr/bin/env python3
"""Control-set parity heuristic (the deepest layer, complements form_bindings).

form_bindings proves each VB dialog has a dedicated port surface; this estimates
whether that surface reproduces the dialog's *individual controls*.  For every
DEDICATED/FOLDED form it lists the VB interactive controls (buttons / checkboxes /
radios / lists / combos / menu items, with captions), filters designer
placeholders, and flags the ones whose caption keywords do not appear in the bound
port file — candidate control-level thin-outs for review.

This is a *lead generator*, not a verdict: caption/­widget wording differs across
WinForms↔Qt, so a flagged control may still be present under a different label.
Each flag is adjudicated (see CONTROL_PARITY_FINDINGS.md).  Run it to refresh the
suspicious-form ranking.

Usage:  python check_control_parity.py [<port_src_dir>] [--form <Name>]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

#: Interactive control name prefixes (buttons / checks / radios / lists / combos / menus).
INTERACTIVE = ("Cb", "Rb", "Bt", "Bu", "Ts", "Cm", "Lv", "Co", "Ms", "Rbn")

#: Captions that are WinForms designer placeholders, not real labels.
_PLACEHOLDER = re.compile(
    r"^(ToolStrip|ButtonLabel|MenuStrip|RibbonPage|StatusStrip|ContextMenuStrip|"
    r"ToolStripButton|ToolStripDropDownButton|ToolStripMenuItem|Nothing|999|None|"
    r"ColumnHeader|Label\d)",
    re.IGNORECASE,
)
_STOP = {
    "with", "when", "that", "your", "from", "this", "only", "used", "the", "and",
    "for", "you", "want", "have", "are", "will", "into", "each",
}


def _load_bindings() -> dict:
    return json.loads((HERE / "form_bindings.json").read_text())["bindings"]


def _form_controls() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    with open(HERE / "ledger_controls.csv") as f:
        for r in csv.DictReader(f):
            name, text = r["control"], (r["text"] or "").strip().strip('"& ')
            if (
                name.startswith(INTERACTIVE)
                and text
                and len(text) > 1
                and r["ctype"] != "ToolStripSeparator"
                and not _PLACEHOLDER.match(text)
            ):
                out.setdefault(r["form"], []).append((name, text))
    return out


def _port_text(spec: dict, src: Path) -> str:
    txt = ""
    for tok in spec.get("port", "").replace("+", " ").split():
        if tok.endswith(".py"):
            p = src / "vaultkeeper" / tok
            if p.exists():
                txt += p.read_text().lower()
    return txt


def _covered(caption: str, ptext: str) -> bool:
    words = [w for w in re.findall(r"[a-z]+", caption.lower()) if len(w) > 3 and w not in _STOP]
    if not words:
        return True
    return sum(1 for w in words if w in ptext) / len(words) >= 0.5


def main() -> int:
    args = sys.argv[1:]
    only = None
    if "--form" in args:
        i = args.index("--form")
        only = args[i + 1]
        args = args[:i] + args[i + 2 :]
    src = Path(args[0]) if args else HERE.parent.parent / "src"

    bindings = _load_bindings()
    controls = _form_controls()
    rows = []
    for form, spec in bindings.items():
        if spec["verdict"] not in ("DEDICATED", "FOLDED_OK"):
            continue
        if only and form != only:
            continue
        ctrls = controls.get(form, [])
        ptext = _port_text(spec, src)
        if not ctrls or not ptext:
            continue
        missing = [c for c in ctrls if not _covered(c[1], ptext)]
        rows.append((len(missing) / len(ctrls), form, ctrls, missing))

    rows.sort(reverse=True)
    for _frac, form, ctrls, missing in rows:
        if not missing and not only:
            continue
        print(f"\n== {form}  ({len(ctrls) - len(missing)}/{len(ctrls)} covered) ==")
        for name, cap in missing:
            print(f"   MISSING? {name:22s} {cap!r}")
        if only:
            print("   -- all controls --")
            for name, cap in ctrls:
                print(f"     {name:22s} {cap!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
