"""Compare NIT's and Vaultkeeper's download selection (1c follow-up).

Usage: compare_vault_select.py nit_select.tsv vk_select.tsv
"""

import collections
import sys
from pathlib import Path


def load(path: str) -> dict:
    data: dict = collections.defaultdict(lambda: collections.defaultdict(set))
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        url, kind, value = (line.split("\t") + ["", ""])[:3]
        if kind == "req":
            parts = [p.strip() for p in value.split("|")]
            project, file = parts[0], parts[1] if len(parts) > 1 else ""
            if value == "(none)":
                continue
            data[url]["req_project"].add(project.lower())
            if file:
                data[url]["req_file"].add(f"{project.lower()} | {file.lower()}")
        elif kind == "file":
            if value != "(none)":
                data[url]["file"].add(value.lower())
        else:
            data[url][kind].add(value)
    return data


nit, vk = load(sys.argv[1]), load(sys.argv[2])
same = 0
for url in nit:
    diffs = []
    for kind in ("title", "mod_folder", "group", "file", "req_project", "req_file"):
        a, b = nit[url].get(kind, set()), vk[url].get(kind, set())
        if a != b:
            diffs.append((kind, sorted(a - b), sorted(b - a)))
    title = next(iter(nit[url].get("title", {url})))
    if not diffs:
        same += 1
        continue
    print(f"== {title}")
    for kind, only_nit, only_vk in diffs:
        print(f"   {kind:12} NIT only: {only_nit}")
        print(f"   {'':12} VK only:  {only_vk}")
print(f"{same} of {len(nit)} projects identical")
