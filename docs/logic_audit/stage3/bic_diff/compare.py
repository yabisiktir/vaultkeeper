"""Compare NIT's BicFileReader fields with Vaultkeeper's on a folder of .bic files.

Run (from this folder; the corpus is a *copy*, never the live NWN folder):

    cp ".../NWN Installer Tool v8.0/NWN Installer Tool/bin/Debug/BicFileReader.dll" .
    mcs -nologo BicDump.cs -out:BicDump.exe && mono BicDump.exe CORPUS > nit_bic.tsv
    python vk_bic_dump.py CORPUS > vk_bic.tsv      # with Vaultkeeper's venv
    python compare.py
"""

import collections
from pathlib import Path

nit: dict = collections.defaultdict(dict)
vk: dict = collections.defaultdict(dict)
for path, target in (("nit_bic.tsv", nit), ("vk_bic.tsv", vk)):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        name, key, *value = line.split("\t")
        target[name][key] = value[0] if value else ""

diffs: collections.Counter = collections.Counter()
for name in sorted(nit):
    n = dict(nit[name])
    n["Name"] = f"{n.get('FirstName', '').strip()} {n.get('LastName', '').strip()}".strip()
    for key, b in vk[name].items():
        a = n.get(key, "?")
        if key == "StatInfo":
            a, b = ",".join(sorted(a.split(","))), ",".join(sorted(b.split(",")))
        if a != b:
            diffs[key] += 1
            print(f"{name:32} {key:14} NIT={a!r:40} VK={b!r}")
print(len(nit), "files;", dict(diffs) or "no differences")
