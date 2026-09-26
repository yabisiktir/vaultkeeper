"""Build the tiny stage-2 fixtures (a few hundred bytes in total).

  <root>/fixtures/<mod>/...   mod sources to paste (identical for both apps)
  <root>/preexisting/...      files placed in the game user folder BEFORE start,
                              to see how each app treats a file it didn't install

Every file's content names its owner, so a snapshot hash shows which copy won.
Usage: python make_fixtures.py <root>
"""

import sys
from pathlib import Path

FIXTURES = {
    "Alpha Pack": [
        "alpha.hak",
        "shared.2da",
        "portraits/po_alphah.tga",
        "music/mus_alpha.bmu",
        "readme.txt",
    ],
    "Beta Pack": ["beta.hak", "shared.2da", "beta.tlk"],
    "Gamma Addon": ["gamma.hak", "gamma_item.uti"],
    "Delta Patch": ["patch/delta_patch.hak"],
    "Epsilon Base": ["epsilon.hak", "epsilon.tlk"],
    "Zeta Addon": ["zeta.hak"],
}
PREEXISTING = ["override/shared.2da"]

# Archives (built with 7z from these trees; nothing large). name -> {path in archive: None}
# A value of another archive name nests that archive inside.
ARCHIVES = {
    "theta_pack_v12.7z": ["hak/theta.hak", "override/theta.2da", "readme.txt", "docs/manual.txt"],
    "Iota Addons.zip": ["Iota Addons/hak/iota.hak", "Iota Addons/tlk/iota.tlk"],
    "kappa_bundle.zip": ["kappa_haks.7z", "kappa_readme.txt"],
    "kappa_haks.7z": ["kappa.hak", "portraits/po_kappah.tga"],
}


def main() -> None:
    root = Path(sys.argv[1])
    for mod, files in FIXTURES.items():
        for rel in files:
            p = root / "fixtures" / mod / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(f"{mod.upper()}::{rel}".encode())
    import shutil
    import subprocess
    import tempfile

    built = {}
    for name in sorted(ARCHIVES, key=lambda n: n != "kappa_haks.7z"):  # nested one first
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ARCHIVES[name]:
                q = Path(tmp) / rel
                q.parent.mkdir(parents=True, exist_ok=True)
                if rel in built:
                    shutil.copy(built[rel], q)
                else:
                    q.write_bytes(f"{name.upper()}::{rel}".encode())
            out = root / "fixtures" / name
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["7z", "a", "-bd", "-y", str(out), "."], cwd=tmp, check=True, capture_output=True
            )
            built[name] = out
    for rel in PREEXISTING:
        p = root / "preexisting" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"ORIGINAL::{rel}".encode())


if __name__ == "__main__":
    main()
