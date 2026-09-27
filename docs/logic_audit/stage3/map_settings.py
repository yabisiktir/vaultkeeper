"""Stage 3b: NIT's My.Settings vs Vaultkeeper's Settings — mapping and defaults.

For every NIT setting (``My Project/Settings.settings``): its type and default,
the Vaultkeeper field whose comment cites it (``VB ``Name``​``), that field's
default, and whether the two defaults agree. Unmapped NIT settings are listed
with NIT's own description (``Settings.Config.vb``) for triage.

Usage: python map_settings.py <NIT source dir>
"""

import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from vaultkeeper.config.settings import Settings

src = Path(sys.argv[1])
ns = {"s": "http://schemas.microsoft.com/VisualStudio/2004/01/settings"}
root = ET.parse(src / "My Project" / "Settings.settings").getroot()
nit = []
for el in root.find("s:Settings", ns):
    v = el.find("s:Value", ns)
    nit.append((el.get("Name"), el.get("Type"), (v.text or "") if v is not None else ""))

# Descriptions from Settings.Config.vb: {"Name", New Preference(group, "caption", ...
config = (src / "Settings.Config.vb").read_text(encoding="utf-8-sig", errors="replace")
captions = dict(re.findall(r'\{"(\w+)",\s*New Preference\([^,]+,\s*"([^"]*)"', config))

# VK fields and the VB names their comments cite.
vk_src = Path("src/vaultkeeper/config/settings.py").read_text()
tree = ast.parse(vk_src)
lines = vk_src.splitlines()
cites: dict[str, list[str]] = {}
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "Settings":
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                i = item.lineno - 2
                comment = []
                while i >= 0 and lines[i].strip().startswith("#"):
                    comment.insert(0, lines[i])
                    i -= 1
                for name in set(re.findall(r"\b([A-Z]\w+)\b", " ".join(comment))):
                    cites.setdefault(name, []).append(item.target.id)
defaults = Settings()


def norm(value: str, typ: str):
    if typ == "System.Boolean":
        return value.strip().lower() == "true"
    if typ in ("System.Int32", "System.Int64", "System.Decimal", "System.Double"):
        try:
            return float(value)
        except ValueError:
            return value
    return value


mapped = unmapped = differ = 0
rows = []
for name, typ, default in nit:
    fields = cites.get(name, [])
    if not fields:
        unmapped += 1
        rows.append(
            ("UNMAPPED", name, typ.split(".")[-1], default[:40], "", "", captions.get(name, ""))
        )
        continue
    mapped += 1
    for field in fields:
        vk = getattr(defaults, field, None)
        a = norm(default, typ)
        b = float(vk) if isinstance(vk, (int, float)) and not isinstance(vk, bool) else vk
        same = a == b or (a in ("", None) and b in ("", None, [], {}))
        if not same:
            differ += 1
        verdict = "same" if same else "DIFF"
        rows.append(
            (verdict, name, typ.split(".")[-1], default[:40], field, repr(vk)[:40],
             captions.get(name, ""))
        )

print(f"NIT settings: {len(nit)}  mapped: {mapped}  unmapped: {unmapped}  differ: {differ}")
for r in rows:
    if r[0] != "same":
        print("\t".join(r))
