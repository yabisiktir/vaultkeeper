#!/usr/bin/env python3
"""Surface-level parity guardrail (complements the symbol ledger).

The symbol ledger matches VB *members* against the port globally, so a concept
that appears *anywhere* in the port counts as covered.  That is blind to the
"two distinct VB forms folded into one port surface" failure mode (e.g. Basic +
Advanced Settings collapsing into one dialog).  This checker binds each VB Form
to a *dedicated* port surface and fails on any fold/merge/missing that has not
been consciously signed off — so structural divergences are fix-by-default.

Usage:  python check_form_bindings.py <port_src_dir>
Exit 0 = clean; exit 1 = open findings (THINNED / MISSING without accepted:true,
or a DEDICATED/FOLDED port file that does not exist).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> int:
    port_src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "src"
    data = json.loads((HERE / "form_bindings.json").read_text())
    bindings = data["bindings"]

    # Every VB form in the ledger must have a binding.
    forms = {
        r.split(":")[0]
        for r in _control_forms()
    }
    missing_binding = sorted(f for f in forms if f not in bindings)

    findings: list[str] = []
    file_errors: list[str] = []

    for form, spec in bindings.items():
        verdict = spec["verdict"]
        if verdict in ("THINNED", "MISSING") and not spec.get("accepted"):
            findings.append(f"  [{verdict}] {form}: {spec.get('note', '')}")
        # For dedicated/folded surfaces, sanity-check any concrete .py file exists.
        if verdict in ("DEDICATED", "FOLDED_OK"):
            for token in spec.get("port", "").replace("+", " ").split():
                if token.endswith(".py"):
                    rel = token if token.startswith("ui/") or token.startswith(
                        "game/"
                    ) or token.startswith("core/") else None
                    if rel and not (port_src / "vaultkeeper" / rel).exists():
                        file_errors.append(f"  {form}: port file not found: {rel}")

    from collections import Counter

    counts = Counter(s["verdict"] for s in bindings.values())
    print("Form-binding verdicts:")
    for v, n in counts.most_common():
        print(f"  {v:10s} {n}")
    print(f"  TOTAL      {len(bindings)}")

    ok = True
    if missing_binding:
        ok = False
        print("\nVB forms with NO binding (add them to form_bindings.json):")
        for f in missing_binding:
            print(f"  {f}")
    if file_errors:
        ok = False
        print("\nBound port files that do not exist:")
        print("\n".join(file_errors))
    if findings:
        ok = False
        print("\nOPEN FINDINGS (fix, or mark \"accepted\": true to sign off):")
        print("\n".join(findings))

    print("\nRESULT:", "CLEAN" if ok else "OPEN FINDINGS")
    return 0 if ok else 1


def _control_forms() -> list[str]:
    cf = json.loads((HERE / "control_forms.json").read_text())
    return [k for k in cf if k != "_comment"]


if __name__ == "__main__":
    raise SystemExit(main())
