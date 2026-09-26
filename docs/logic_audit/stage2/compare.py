"""Compare NIT and Vaultkeeper stage-2 snapshots step by step.

Compared per step (after normalisation):
  game   files in the game user folder and their content (which mod's copy won)
  lib    files in the EE library folder
  store  the profile's mod folders (installer layout, identifiers)
  mod    per-mod state: installed flag, mod state, dependencies (group names differ
         by group-set naming and are reported once, not per step)
Ignored as environment noise: nwn.ini / nwnplayer.ini / *.bak (each app writes
its own paths), and NIT's first-run "(Auto)" restorer files are reported once.

Usage: python compare.py <dir with nit_snaps.tsv and vk_snaps.tsv>
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

NOISE = ("nwn.ini", "nwnplayer.ini", ".bak", "userpatch.ini")


def load(path: Path) -> dict[str, dict[tuple[str, str], str]]:
    steps: dict[str, dict[tuple[str, str], str]] = collections.OrderedDict()
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        parts = (line.split("\t") + ["", "", ""])[:4]
        step, kind, key, value = parts
        steps.setdefault(step, {})[(kind, key)] = value
    return steps


def modname(x: str) -> str:
    """NIT renames pasted archives (stage-1 N1); compare mod names loosely."""
    return " ".join(x.replace("_", " ").lower().split())


def norm(kind: str, key: str, value: str) -> tuple[str, str] | None:
    k = key.replace("\\", "/")
    if kind in ("game", "lib", "store") and any(k.lower().endswith(n) for n in NOISE):
        return None
    if kind == "store":
        k = k.replace("/.Mod Installer/", "/<installer>/")
        first, _, rest = k.partition("/")
        k = f"{modname(first)}/{rest}"
        k = "/".join(modname(x) if x.endswith((".nitins", ".nitres")) else x for x in k.split("/"))
    if kind == "game" and k.lower().endswith((".nitins", ".nitres")):
        k = "/".join(k.split("/")[:-1] + [modname(k.split("/")[-1])])
    if kind == "mod":
        k = modname(k)
    if kind == "mod":
        fields = dict(f.split("=", 1) for f in value.split(";") if "=" in f)
        fields.pop("group", None)
        fields.pop("installState", None)
        # enum spelling differs (SomeAndOverridden vs SOME_AND_OVERRIDDEN)
        fields = {
            a: (b.replace("_", "").lower() if a == "modState" else b) for a, b in fields.items()
        }
        value = ";".join(f"{a}={b}" for a, b in sorted(fields.items()))
    return k.lower(), value


PATCH_INIS = ("userpatch.ini", "nwnpatch.ini")


def patch_view(snap: dict[tuple[str, str], str]) -> dict[tuple[str, str], str]:
    """Which patch haks are listed, and in which file (location compared separately)."""
    out = {}
    for (kind, key), value in snap.items():
        name = key.replace("\\", "/").split("/")[-1].lower()
        if kind in ("game", "lib") and name in PATCH_INIS:
            haks = sorted(
                v.split("=", 1)[1].strip().lower()
                for v in value.split()
                if v.lower().startswith("patchfile") and "=" in v and v.split("=", 1)[1].strip()
            )
            out[("patch", f"{kind}/{name}")] = ",".join(haks) or "(empty)"
    return out


def view(
    snap: dict[tuple[str, str], str], kinds=("game", "lib", "store", "mod")
) -> dict[tuple[str, str], str]:
    out = {}
    for (kind, key), value in snap.items():
        if kind not in kinds:
            continue
        n = norm(kind, key, value)
        if n:
            out[(kind, n[0])] = n[1]
    return out


def main() -> None:
    d = Path(sys.argv[1])
    nit, vk = load(d / "nit_snaps.tsv"), load(d / "vk_snaps.tsv")
    print(f"steps: NIT {len(nit)}  VK {len(vk)}")
    for (ns, nsnap), vsnap in zip(nit.items(), vk.values(), strict=False):
        a, b = {**view(nsnap), **patch_view(nsnap)}, {**view(vsnap), **patch_view(vsnap)}
        diffs = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        errs = [v for (k, _), v in vsnap.items() if k == "error"] + [
            v for (k, _), v in nsnap.items() if k == "error"
        ]
        print(f"\n=== {ns}   ({len(diffs)} differences)")
        ninfo = nsnap.get(("status", "info"), "")
        vinfo = vsnap.get(("status", "info"), "")
        if ninfo or vinfo:
            print(f"    status  NIT: {ninfo[:110]!r}\n            VK:  {vinfo[:110]!r}")
        for e in errs:
            print(f"    ERROR {e[:160]}")
        for kind, key in diffs:
            left = str(a.get((kind, key), "—"))[:40]
            right = str(b.get((kind, key), "—"))[:40]
            print(f"    {kind:5} {key[:62]:62} NIT={left:40} VK={right}")


if __name__ == "__main__":
    main()
