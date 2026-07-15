#!/usr/bin/env python3
"""VB.NET symbol + Designer inventory extractor for the NIT parity audit.

Produces the machine-generated *denominator* of the original app: every class /
module, every Sub / Function / Property / Operator, every event handler
(`Handles` clause), and every Designer control + a set of layout-critical
properties. The point is that the denominator is derived mechanically from the
source, so coverage can be measured and nothing can be silently missed.

Outputs (CSV, to the given out dir):
  members.csv    one row per Sub/Function/Property/Operator (+ Handles target)
  handlers.csv   the subset that are event handlers (behavior units)
  controls.csv   one row per Designer control + key properties
  types.csv      one row per class/module/structure (with member counts)
  summary.txt    headline counts
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# ---- regexes -------------------------------------------------------------
TYPE_RE = re.compile(
    r"^\s*(?:(?:Public|Friend|Private|Protected|Partial|Shared|MustInherit|"
    r"NotInheritable|Overloads)\s+)*"
    r"(Class|Module|Structure|Interface|Enum)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
END_TYPE_RE = re.compile(r"^\s*End\s+(Class|Module|Structure|Interface|Enum)\b", re.IGNORECASE)

# member: Sub / Function / Property / Operator (skip Declare/Delegate/Event)
MEMBER_RE = re.compile(
    r"^\s*(?:(?:Public|Friend|Private|Protected|Shared|Overrides|Overridable|"
    r"MustOverride|NotOverridable|Overloads|Shadows|Default|ReadOnly|WriteOnly|"
    r"Async|Iterator|Partial)\s+)*"
    r"(Sub|Function|Property|Operator)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
HANDLES_RE = re.compile(r"\bHandles\s+(.+?)\s*$", re.IGNORECASE)

# Designer: control declarations + assignments
DECL_RE = re.compile(
    r"^\s*(?:Friend|Public|Private|Protected)\s+WithEvents\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s+As\s+(?:New\s+)?([A-Za-z0-9_.]+)",
    re.IGNORECASE,
)
ASSIGN_RE = re.compile(
    r"^\s*Me\.([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$"
)
# properties on a control we care about for layout/experience parity
KEY_PROPS = {
    "Text", "TextAlign", "Alignment", "Dock", "Anchor", "Checked", "CheckState",
    "Image", "ImageKey", "Visible", "Enabled", "TabIndex", "TabAlignment",
    "RightToLeft", "AutoSize", "FlatStyle", "DisplayStyle", "ForeColor",
    "BackColor", "SelectionMode", "View", "DropDownItems", "Multiline",
}


def strip_comment(line: str) -> str:
    # naive: drop trailing ' comment when not inside a string
    out, in_str = [], False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        if ch == "'" and not in_str:
            break
        out.append(ch)
    return "".join(out)


def extract_code_file(path: Path, rows_types, rows_members, rows_handlers):
    type_stack = []  # (kind, name)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # join VB line-continuations ( trailing " _")
    joined = []
    buf, start = "", 0
    for i, raw in enumerate(lines, start=1):
        code = strip_comment(raw)
        if code.rstrip().endswith(" _"):
            if not buf:
                start = i
            buf += code.rstrip()[:-1] + " "
            continue
        if buf:
            joined.append((start, buf + code))
            buf = ""
        else:
            joined.append((i, code))
    for lineno, code in joined:
        m = TYPE_RE.match(code)
        if m:
            type_stack.append([m.group(1), m.group(2), 0])
            continue
        if END_TYPE_RE.match(code):
            if type_stack:
                kind, name, count = type_stack.pop()
                rows_types.append(
                    {"file": path.name, "kind": kind, "type": name, "members": count}
                )
            continue
        mm = MEMBER_RE.match(code)
        if mm:
            kind, name = mm.group(1), mm.group(2)
            enclosing = type_stack[-1][1] if type_stack else "(none)"
            if type_stack:
                type_stack[-1][2] += 1
            hm = HANDLES_RE.search(code)
            handles = hm.group(1).strip() if hm else ""
            row = {
                "file": path.name,
                "type": enclosing,
                "member": name,
                "kind": kind,
                "handles": handles,
                "line": lineno,
            }
            rows_members.append(row)
            if handles:
                rows_handlers.append(row)
    # flush any unterminated types (files with partial nesting quirks)
    while type_stack:
        kind, name, count = type_stack.pop()
        rows_types.append({"file": path.name, "kind": kind, "type": name, "members": count})


def extract_designer(path: Path, rows_controls):
    form = path.name.replace(".Designer.vb", "")
    controls = {}  # name -> {type, props{}}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        code = strip_comment(raw)
        d = DECL_RE.match(code)
        if d:
            controls.setdefault(d.group(1), {"type": d.group(2), "props": {}})
            continue
        a = ASSIGN_RE.match(code)
        if a:
            ctrl, prop, val = a.group(1), a.group(2), a.group(3)
            if prop in KEY_PROPS:
                controls.setdefault(ctrl, {"type": "?", "props": {}})
                controls[ctrl]["props"].setdefault(prop, val)
    for name, info in controls.items():
        rows_controls.append(
            {
                "form": form,
                "control": name,
                "ctype": info["type"],
                "text": info["props"].get("Text", ""),
                "align": info["props"].get("TextAlign", "")
                or info["props"].get("Alignment", "")
                or info["props"].get("TabAlignment", ""),
                "dock": info["props"].get("Dock", ""),
                "anchor": info["props"].get("Anchor", ""),
                "props": ";".join(f"{k}={v}" for k, v in info["props"].items()),
            }
        )


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rows_types, rows_members, rows_handlers, rows_controls = [], [], [], []
    for vb in sorted(src.rglob("*.vb")):
        if "obj" in vb.parts or "My Project" in str(vb):
            continue
        if vb.name.endswith(".Designer.vb"):
            extract_designer(vb, rows_controls)
        else:
            extract_code_file(vb, rows_types, rows_members, rows_handlers)

    def dump(name, rows, fields):
        with (out / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    dump("types.csv", rows_types, ["file", "kind", "type", "members"])
    dump("members.csv", rows_members, ["file", "type", "member", "kind", "handles", "line"])
    dump("handlers.csv", rows_handlers, ["file", "type", "member", "kind", "handles", "line"])
    dump("controls.csv", rows_controls,
         ["form", "control", "ctype", "text", "align", "dock", "anchor", "props"])

    summary = [
        f"types (class/module/struct):   {len(rows_types)}",
        f"members (sub/func/prop/oper):  {len(rows_members)}",
        f"event handlers (Handles):      {len(rows_handlers)}",
        f"designer controls:             {len(rows_controls)}",
        f"designer forms:                {len({r['form'] for r in rows_controls})}",
    ]
    (out / "summary.txt").write_text("\n".join(summary) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
