"""Stage 5 check for R3: the install wizards the rules define, NIT vs Vaultkeeper.

Compares NIT's parsed ``ProjectInfo.Wizard`` (harness ``rules-dump``) with
``parse_wizard_text`` over Vaultkeeper's ``ProjectRule.wizard_text`` for the same
rules file: title, ExtractArchives, SelectOne / SelectMany (with texts, displays
and default ticks), InstallerExcludes and RunWizard.

Usage: python diff_rule_wizards.py <nit rules dump> <DownloadRulesV3.txt NIT read>
"""

import collections
import re
import sys
from pathlib import Path

from vaultkeeper.game.wizard import parse_wizard_text
from vaultkeeper.vault.download_rules import DownloadRules

nit: dict[str, dict[str, str]] = collections.defaultdict(dict)
for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    t, f, v = (line.split("\t") + ["", ""])[:3]
    if f.startswith("Wizard."):
        nit[t.lower()][f[7:]] = v
rules = DownloadRules.from_text(Path(sys.argv[2]).read_text(encoding="cp1252"))

bad = collections.defaultdict(list)
running = 0
for t in sorted(nit):
    n = nit[t]
    rule = rules.project_rule(t)
    info = parse_wizard_text(rule.wizard_text if rule else "", "")
    if len(info.select_one) == 1:  # VB End Project drops a lone choice
        info.select_one.clear()
    running += info.run_wizard
    vk = {
        "Title": info.title_value or "Mod Installer Wizard",
        "ExtractArchives": str(info.extract_archives),
        "SelectOneText": info.select_one_text,
        "SelectManyText": info.select_many_text,
        "SelectOne": sorted(f"{k}:{v}".lower() for k, v in info.select_one.items()),
        "SelectMany": sorted(
            f"{p.key}:{p.display}:{p.checked}".lower() for p in info.select_many
        ),
        "InstallerExcludes": sorted(x.lower() for x in info.installer_excludes),
        "RunWizard": str(info.run_wizard),
    }
    ref = dict(n)
    ref["SelectOne"] = sorted(x.lower() for x in n["SelectOne"].split("|") if x)
    # NIT dumps SelectMany as serialised CheckBoxes: Name = key, Text, Checked.
    ref["SelectMany"] = sorted(
        f"{m['Name']}:{m['Text']}:{m['Checked']}".lower()
        for m in (
            dict(kv.split("=", 1) for kv in box.strip("{}").split(";") if "=" in kv)
            for box in re.findall(r"\{[^{}]*\}", n["SelectMany"])
        )
    )
    ref["InstallerExcludes"] = sorted(x.lower() for x in n["InstallerExcludes"].split("|") if x)
    for field, value in vk.items():
        if ref.get(field) != value:
            bad[field].append((t, str(ref.get(field))[:120], str(value)[:120]))

print(f"projects: {len(nit)}; wizards that run in VK: {running}; "
      f"in NIT: {sum(d['RunWizard'] == 'True' for d in nit.values())}")
for field in ("Title", "ExtractArchives", "SelectOneText", "SelectManyText", "SelectOne",
              "SelectMany", "InstallerExcludes", "RunWizard"):
    print(f"\n{field}: {len(bad[field])} differ")
    for x in bad[field][:8]:
        print("   ", x)
