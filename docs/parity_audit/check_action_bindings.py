#!/usr/bin/env python3
"""Action-level parity guardrail (complements form_bindings + the symbol ledger).

Every VB top-level *command* (menu item ``Ms*`` / ribbon button ``Rbn*``) must be
either (a) defined in the port — referenced by its id in the ``ui/`` sources, so it
is wired or consciously greyed — or (b) explicitly categorised in ``seeds.json``
(Ported/Partial/Deferred/Divergence).  A command that is neither is an unaccounted
action: the port never even defined it.  This catches the action-level equivalent of
a missing/merged form (fix-by-default).

In-dialog toolbar buttons (``Ts*`` inside a specific dialog) are intentionally out of
scope here — they are the responsibility of that dialog's binding in
``form_bindings.json`` (the port implements them as plain widgets without the VB id).

Usage:  python check_action_bindings.py <port_src_dir>
Exit 0 = every VB command accounted; exit 1 = uncategorised commands remain.
"""

from __future__ import annotations

import csv
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

#: Menu/ribbon structural containers, not commands.
STRUCTURAL = {"MsMenu", "MsMain", "MsgStatus", "MsStatus"}


def _vb_commands() -> set[str]:
    out: set[str] = set()
    with open(HERE / "ledger_controls.csv") as f:
        for r in csv.DictReader(f):
            name = r["control"]
            if (
                (name.startswith("Ms") or name.startswith("Rbn"))
                and r["ctype"] != "ToolStripSeparator"
                and name not in STRUCTURAL
            ):
                out.add(name)
    return out


def _port_defined(port_src: Path) -> set[str]:
    pat = re.compile(r'"((?:Ms|Rbn|Ts)[A-Za-z0-9]+)"')
    out: set[str] = set()
    for f in glob.glob(str(port_src / "vaultkeeper" / "ui" / "**" / "*.py"), recursive=True):
        out |= set(pat.findall(Path(f).read_text()))
    return out


def _categorised() -> set[str]:
    seeds = json.loads((HERE / "seeds.json").read_text())
    out: set[str] = set()
    for spec in seeds.values():
        if isinstance(spec, dict) and "names" in spec:
            out |= set(spec["names"])
    return out


def main() -> int:
    port_src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "src"
    vb = _vb_commands()
    defined = _port_defined(port_src)
    categorised = _categorised()
    unaccounted = sorted(vb - defined - categorised)

    print(f"VB menu/ribbon commands: {len(vb)}")
    print(f"  defined in port:       {len(vb & defined)}")
    print(f"  categorised in seeds:  {len(vb & categorised - defined)}")
    print(f"  UNACCOUNTED:           {len(unaccounted)}")
    if unaccounted:
        print("\nUNACCOUNTED COMMANDS (wire them, or categorise in seeds.json):")
        for c in unaccounted:
            print(f"  {c}")
    print("\nRESULT:", "CLEAN" if not unaccounted else "OPEN FINDINGS")
    return 0 if not unaccounted else 1


if __name__ == "__main__":
    raise SystemExit(main())
