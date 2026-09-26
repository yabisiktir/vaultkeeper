"""Stage 1c: compare NIT's parsed download rules (harness `rules-dump`) with
Vaultkeeper's DownloadRules on the SAME rules file.

Usage: python diff_rules.py <nit rules.txt dump> <DownloadRulesV3.txt that NIT used>
"""

import collections
import sys
from pathlib import Path

from vaultkeeper.vault.download_rules import DownloadRules

nit: dict[str, dict[str, str]] = collections.defaultdict(dict)
for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    t, f, v = (line.split("\t") + ["", ""])[:3]
    nit[t.lower()][f] = v
vk = DownloadRules.from_text(Path(sys.argv[2]).read_text(encoding="cp1252")).projects

print(f"projects: NIT {len(nit)}  VK {len(vk)}")
print("  only in NIT:", sorted(set(nit) - set(vk)))
print("  only in VK: ", sorted(set(vk) - set(nit)))


def norm_list(values):
    return sorted(v.lower() for v in values if v and v.lower() != "end exclude")


PAIRS = {
    "ModFolder": "mod_folder",
    "Group": "group",
    "Files": "downloads",
    "AddRequired": "required_projects",
    "Excludes": "excludes",
}
for nf, vf in PAIRS.items():
    bad = []
    for t in sorted(set(nit) & set(vk)):
        a, b = nit[t].get(nf, ""), getattr(vk[t], vf)
        same = (
            norm_list(a.split("|")) == norm_list(b)
            if isinstance(b, list)
            else a.lower() == b.lower()
        )
        if not same:
            bad.append((t, a[:90], ("|".join(b) if isinstance(b, list) else b)[:90]))
    print(f"\n{nf} vs {vf}: {len(bad)} differ")
    for x in bad:
        print("   ", x)

DEFAULTS = {
    "ApplyExcludes": "True",
    "Wizard.RunWizard": "False",
    "Wizard.SuppressWizardCreation": "False",
    "Wizard.ExtractArchives": "False",
    "Wizard.ExtractedArchives": "False",
}
SKIP = {"Wizard.ModName", "Wizard.SelectOneText", "Wizard.SelectManyText", "Wizard.Title"}
print("\nFields Vaultkeeper does not parse (projects carrying a non-default value):")
for f in sorted({f for d in nit.values() for f in d} - set(PAIRS) - SKIP):
    hit = [t for t, d in nit.items() if d.get(f, "") not in ("", DEFAULTS.get(f, ""))]
    if hit:
        print(f"  {len(hit):4}  {f:30} {', '.join(hit[:6])}{' …' if len(hit) > 6 else ''}")
