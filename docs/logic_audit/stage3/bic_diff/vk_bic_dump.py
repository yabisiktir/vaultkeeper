import sys
from pathlib import Path

from nwnfile.formats.bic_reader import BicFileReader

STATS = ("Str", "Dex", "Con", "Int", "Wis", "Cha")
reader = BicFileReader()
for f in sorted(Path(sys.argv[1]).glob("*.bic")):
    i = reader.read_file(f)
    rows = {
        "ClassInfo": ",".join(f"{c}:{lv}" for c, lv in i.classes),
        "Deity": i.deity,
        "Experience": i.experience,
        "Name": i.name,
        "Gender": i.gender.value,
        "Gold": i.gold,
        "GoodEvil": i.alignment_good_evil,
        "LawfulChaotic": i.alignment_lawful_chaotic,
        "MaxHitPoints": i.hit_points,
        "Portrait": i.portrait_resref,
        "Race": i.race_id,
        "StatInfo": ",".join(f"{k}:{i.abilities.get(k)}" for k in STATS),
    }
    for k, v in rows.items():
        print(f"{f.name}\t{k}\t{v}")
