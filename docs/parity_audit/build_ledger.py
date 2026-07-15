#!/usr/bin/env python3
"""Build the parity coverage ledger.

Reads the machine-generated VB denominator (the *.csv produced by extract_vb.py),
auto-matches every VB symbol / control against the Python port, applies the known
statuses from seeds.json, and writes:

  ledger_members.csv    every method/property   + match + status
  ledger_handlers.csv   the event-handler subset + match + status
  ledger_controls.csv   every designer control  + match + status
  DASHBOARD.md          human-readable rollup + the work queue

STATUS vocabulary
  verified (set by a human during the sweep, or seeded):
    Ported | Partial | Deferred | Divergence | MISSING
  machine-initial (the queue to work):
    AUTO-PORTED  a name match exists in the port (spot-check, then confirm Ported)
    GAP?         no match found in the port (investigate first)
    N/A          framework/designer-generated noise (New/Dispose/InitializeComponent…)

Usage:
    python extract_vb.py "<vb src dir>" ./out
    python build_ledger.py ./out "<port src dir>" .
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FRAMEWORK_NOISE = {
    "new", "dispose", "initializecomponent", "finalize", "tostring", "equals",
    "gethashcode", "onload", "onclosing", "onformclosing", "onpaint", "onresize",
    "getenumerator", "compareto", "clone",
}


def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    s = s.replace("__", "_")
    return s.lower()


def build_port_index(port_src: Path):
    """token(lower) -> set(files); plus a lowercased blob for comment/string hits."""
    token_files: dict[str, set[str]] = defaultdict(set)
    blob_parts: list[str] = []
    tok = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for py in sorted(port_src.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = str(py.relative_to(port_src))
        text = py.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        blob_parts.append(f"\n### {rel}\n{low}")
        for m in tok.finditer(text):
            token_files[m.group(0).lower()].add(rel)
    return token_files, "".join(blob_parts)


def match(name: str, token_files, blob) -> tuple[str, list[str]]:
    """Return (match_kind, port_files). kind in strong|comment|none."""
    forms = {name.lower(), snake(name)}
    hits: set[str] = set()
    for f in forms:
        if len(f) >= 3 and f in token_files:
            hits |= token_files[f]
    if hits:
        return "strong", sorted(hits)[:3]
    # comment / string reference (VB names are frequently cited in port docstrings)
    key = name.lower()
    if len(key) >= 6 and key in blob:
        # locate which file(s) mention it
        files = []
        for chunk in blob.split("\n### ")[1:]:
            fname, _, body = chunk.partition("\n")
            if key in body:
                files.append(fname)
            if len(files) >= 3:
                break
        return "comment", files
    return "none", []


def load_seeds(path: Path) -> dict[str, tuple[str, str]]:
    data = json.loads(path.read_text())
    out: dict[str, tuple[str, str]] = {}
    for group, spec in data.items():
        if not isinstance(spec, dict) or "names" not in spec:
            continue
        for n in spec["names"]:
            out[n] = (spec["status"], spec.get("note", ""))
    return out


def initial_status(name, match_kind, seeds):
    if name in seeds:
        return seeds[name][0], seeds[name][1]
    if name.lower() in FRAMEWORK_NOISE:
        return "N/A", "framework/designer-generated"
    if match_kind == "strong":
        return "AUTO-PORTED", ""
    if match_kind == "comment":
        return "AUTO-PORTED", "matched in comment/docstring"
    return "GAP?", ""


def main():
    outdir = Path(sys.argv[1])       # denominator CSVs (from extract_vb.py)
    port_src = Path(sys.argv[2])     # port src dir
    dest = Path(sys.argv[3])         # where to write ledger + dashboard
    seeds = load_seeds(dest / "seeds.json")
    token_files, blob = build_port_index(port_src)

    def read(name):
        with (outdir / name).open() as f:
            return list(csv.DictReader(f))

    members = read("members.csv")
    controls = read("controls.csv")

    # ---- members / handlers ----
    for r in members:
        mk, files = match(r["member"], token_files, blob)
        st, note = initial_status(r["member"], mk, seeds)
        r["match"] = mk
        r["port_hint"] = " | ".join(files)
        r["status"] = st
        r["notes"] = note
        r["vb_ref"] = f"{r['file']}:{r['line']}"
    handlers = [r for r in members if r["handles"]]

    # ---- controls ----
    for r in controls:
        mk, files = match(r["control"], token_files, blob)
        st, note = initial_status(r["control"], mk, seeds)
        r["match"] = mk
        r["port_hint"] = " | ".join(files)
        r["status"] = st
        r["notes"] = note

    mfields = ["file", "type", "member", "kind", "handles", "vb_ref",
               "match", "port_hint", "status", "notes"]
    cfields = ["form", "control", "ctype", "text", "align", "dock", "anchor",
               "match", "port_hint", "status", "notes"]

    def dump(name, rows, fields):
        with (dest / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    dump("ledger_members.csv", members, mfields)
    dump("ledger_handlers.csv", handlers, mfields)
    dump("ledger_controls.csv", controls, cfields)

    write_dashboard(dest, members, handlers, controls)
    print("ledger + dashboard written to", dest)


def status_counts(rows):
    return Counter(r["status"] for r in rows)


def write_dashboard(dest, members, handlers, controls):
    def pct(rows, statuses):
        n = sum(1 for r in rows if r["status"] in statuses)
        return f"{n} ({100*n//max(len(rows),1)}%)"

    accounted = {"Ported", "Partial", "Deferred", "Divergence", "MISSING", "N/A"}
    lines = []
    A = lines.append
    A("# NIT → Vaultkeeper parity coverage ledger\n")
    A("Machine-generated denominator of the original VB app, auto-matched against the")
    A("Python port. Every row carries a status; the audit is complete when no row is")
    A("`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).\n")
    A("Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`\n")

    A("## Coverage\n")
    A("| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |")
    A("|---|---|---|---|")
    for label, rows in (("Methods/props", members), ("Event handlers", handlers),
                        ("Designer controls", controls)):
        queue = sum(1 for r in rows if r["status"] in ("AUTO-PORTED", "GAP?"))
        A(f"| {label} | {len(rows)} | {pct(rows, accounted)} | {queue} |")
    A("")

    for label, rows in (("Methods/props", members), ("Event handlers", handlers),
                        ("Designer controls", controls)):
        A(f"### {label} — status breakdown")
        for st, n in status_counts(rows).most_common():
            A(f"- `{st}`: {n}")
        A("")

    # per-VB-file rollup: where the gaps concentrate
    A("## Where to look — GAP? density by VB file (methods)\n")
    A("Files with the most unmatched methods surface first; these are the sweep priorities.\n")
    A("| VB file | methods | GAP? | AUTO-PORTED | accounted |")
    A("|---|---|---|---|---|")
    byfile = defaultdict(list)
    for r in members:
        byfile[r["file"]].append(r)
    rankable = []
    for f, rows in byfile.items():
        gap = sum(1 for r in rows if r["status"] == "GAP?")
        auto = sum(1 for r in rows if r["status"] == "AUTO-PORTED")
        acc = sum(1 for r in rows if r["status"] in accounted)
        rankable.append((gap, f, len(rows), auto, acc))
    for gap, f, tot, auto, acc in sorted(rankable, reverse=True)[:30]:
        A(f"| {f} | {tot} | {gap} | {auto} | {acc} |")
    A("")

    # the immediate work queue: GAP? methods (non-noise), by file
    A("## Work queue — GAP? methods (no port match; investigate)\n")
    A("First 60 shown. A `GAP?` means the auto-matcher found no name/comment hit in the")
    A("port — it is a *candidate* miss to confirm, not a proven gap (the port may")
    A("implement it under a different name).\n")
    A("| VB ref | class | method | kind |")
    A("|---|---|---|---|")
    gaps = [r for r in members if r["status"] == "GAP?"]
    for r in gaps[:60]:
        A(f"| {r['vb_ref']} | {r['type']} | {r['member']} | {r['kind']} |")
    A(f"\n_({len(gaps)} GAP? methods total; see ledger_members.csv for the full list.)_\n")

    # confirmed findings surfaced during design
    A("## Findings (confirmed divergences)\n")
    A("These are real divergences confirmed against the VB source during audit design")
    A("(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that")
    A("the command-level audit did not.\n")
    A("1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` "
      "`ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` "
      "for each, so empty groups still render (enabling drag-into-empty-group). The port's "
      "`FileView.populate` only emits groups that have members. → behavior gap.")
    A("2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` "
      "(tabs left-packed); the port centers them. → designer-property gap.")
    A("3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` "
      "keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences "
      "(`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. "
      "Some map to ported features under other names, but genuinely-unmodelled ones include "
      "`ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, "
      "`ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings "
      "sub-sweep (enumerate every pref key, classify, build the missing ones).\n")

    (dest / "DASHBOARD.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
