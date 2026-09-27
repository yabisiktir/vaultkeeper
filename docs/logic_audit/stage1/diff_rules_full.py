"""Stage 5 re-check of 1c: every per-project field NIT parses vs Vaultkeeper.

Compares NIT's parsed rules (harness `rules-dump`, EE profile, default
"exclude ERF") with ``DownloadRules.rule_for_game(is_ee=True)`` on the same
rules file, field by field. Wizard fields are compared separately (R3).

Usage: python diff_rules_full.py <nit rules dump> <DownloadRulesV3.txt NIT read>
"""

import collections
import re
import sys
from pathlib import Path

from vaultkeeper.vault.download_rules import DownloadRules, external_filename

nit: dict[str, dict[str, str]] = collections.defaultdict(dict)
excludes: dict[str, set[str]] = collections.defaultdict(set)
for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    t, f, v = (line.split("\t") + ["", ""])[:3]
    if f == "Excludes":
        excludes[t.lower()] |= {x.lower() for x in v.split("|") if x}
    else:
        nit[t.lower()][f] = v
rules = DownloadRules.from_text(Path(sys.argv[2]).read_text(encoding="cp1252"))


def s(values):
    # NIT keeps the literal "End Exclude" line as a file name (R6, VK better).
    return sorted({v.lower() for v in values if v and v.lower() != "end exclude"})


def split(v):
    return [x for x in v.split("|") if x]


print(f"projects: NIT {len(nit)}  VK {len(rules.projects)}")
print("  only in NIT:", sorted(set(nit) - set(rules.projects)))
print("  only in VK: ", sorted(set(rules.projects) - set(nit)))

bad = collections.defaultdict(list)
for t in sorted(set(nit) & set(rules.projects)):
    n = nit[t]
    r = rules.rule_for_game(t, is_ee=True)
    checks = {
        "ModFolder": (n["ModFolder"].lower(), r.mod_folder.lower()),
        "Group": (n["Group"].lower(), r.group.lower()),
        "ApplyExcludes": (n["ApplyExcludes"], str(r.apply_excludes)),
        "Files": (s(split(n["Files"])), s(r.downloads)),
        "AddRequired": (s(split(n["AddRequired"])), s(r.required_projects)),
        "IncludeExtensions": (s(split(n["IncludeExtensions"])), s(r.include_extensions)),
        "ExcludeDirectLinks": (s(split(n["ExcludeDirectLinks"])), s(r.exclude_direct_links)),
        "ExcludeRequiredProjects": (
            s(split(n["ExcludeRequiredProjects"])),
            s(r.exclude_required_projects),
        ),
        "RequiredFiles": (
            sorted(
                (k.lower(), tuple(s(v.split(","))))
                for k, _, v in (x.partition(":") for x in split(n["RequiredFiles"]))
            ),
            sorted((k, tuple(s(v))) for k, v in r.required_files.items()),
        ),
        "ExternalFiles": (
            s(re.findall(r"FileLink=([^;]*)", n["ExternalFiles"])),
            s(r.external_files),
        ),
    }
    for field, (a, b) in checks.items():
        if a != b:
            bad[field].append((t, a, b))

# Excludes: NIT's ExcludeFiles table (project Excludes + ExcludeFiles From + If ERF).
with_excludes = {k for k, r in rules.projects.items() if r.excludes}
for t in sorted(set(excludes) | set(rules.exclude_files) | with_excludes):
    r = rules.rule_for_game(t, is_ee=True)
    vk = set(s(rules.exclude_files.get(t, []) + (r.excludes if r else [])))
    if set(s(excludes.get(t, set()))) != vk:
        bad["Excludes"].append((t, s(excludes.get(t, set())), sorted(vk)))

for field in ("ModFolder", "Group", "ApplyExcludes", "Files", "AddRequired", "Excludes",
              "IncludeExtensions", "ExcludeDirectLinks", "ExcludeRequiredProjects",
              "RequiredFiles", "ExternalFiles"):
    print(f"\n{field}: {len(bad[field])} differ")
    for x in bad[field]:
        print("   ", str(x)[:220])

print("\nGlobal description excludes:",
      len(rules.exclude_contains), len(rules.exclude_starts_with), len(rules.exclude_ends_with),
      "extensions:", rules.exclude_extensions)
_ = external_filename
