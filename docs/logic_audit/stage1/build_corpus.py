"""Build the stage-1 corpus of mod-relative file paths (nothing is extracted).

Sources, each tagged so a finding can be traced back:
  store:   files inside the Vaultkeeper store's installer folders (real mods)
  archive: `7z l -slt` listings of NWN archives (listing only, no extraction)
  userdir: names of files already in the real NWN user folder (names only)
  synth:   generated edge cases from BOTH apps' mapping tables

Output: corpus.tsv  ->  source<TAB>relative/path  (forward slashes, rooted at a
neutral mod folder so no path component collides with a mapping rule).

Usage: python build_corpus.py <nit tables.txt> [out]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from vaultkeeper.core.mapper import Mapper

HOME = Path.home()
STORE = HOME / "Library/Application Support/Vaultkeeper/Store/Profiles"
USERDIR = HOME / "Documents/Neverwinter Nights"
ARCHIVES = [
    HOME / "Downloads" / n
    for n in (
        "PRC8.7z",
        "The Aielund Saga [PRC8].7z",
        "Swordflight Series [PRC8-CEP3].7z",
        "Neverwinter Nights Campaigns [PRC8].7z",
        "[PRC] Neverwinter Nights - Doom of Icewind Dale.rar",
        "PRC8 Manual.7z",
    )
]
MOD = "ZqMod"  # neutral top folder: matches no dir-mapping key in either app
USERDIR_FOLDERS = (
    "hak",
    "override",
    "modules",
    "portraits",
    "tlk",
    "music",
    "ambient",
    "movies",
    "erf",
    "localvault",
    "database",
    "development",
    "patch",
)


def from_store() -> list[tuple[str, str]]:
    out = []
    for inst in STORE.glob("*/*/.Mod Installer"):
        for f in inst.rglob("*"):
            if f.is_file():
                out.append(("store", f"{MOD}/{f.relative_to(inst).as_posix()}"))
    return out


def from_archives() -> list[tuple[str, str]]:
    out = []
    for a in ARCHIVES:
        if not a.exists():
            continue
        listing = subprocess.run(["7z", "l", "-slt", str(a)], capture_output=True, text=True).stdout
        block: dict[str, str] = {}
        for line in listing.splitlines() + [""]:
            if line.strip() == "":
                # p7zip 17 has no "Folder" key; directories carry a "D" attribute
                is_dir = block.get("Folder") == "+" or block.get("Attributes", "").startswith("D")
                if block.get("Path") and "Size" in block and not is_dir:
                    out.append(("archive", f"{MOD}/{block['Path'].replace(chr(92), '/')}"))
                block = {}
            elif " = " in line:
                k, v = line.split(" = ", 1)
                block[k] = v
    return out


def from_userdir(per_folder: int = 400) -> list[tuple[str, str]]:
    out = []
    for folder in USERDIR_FOLDERS:
        d = USERDIR / folder
        if not d.is_dir():
            continue
        names = sorted(p.name for p in d.iterdir() if p.is_file())[:per_folder]
        # both as-shipped-in-its-folder and loose at the mod root
        out += [("userdir", f"{MOD}/{folder}/{n}") for n in names]
        out += [("userdir", f"{MOD}/{n}") for n in names[:50]]
    return out


def synth(nit_tables: Path) -> list[tuple[str, str]]:
    nit: dict[str, dict[str, str]] = {}
    for line in nit_tables.read_text(encoding="utf-8-sig").splitlines():
        t, k, v = line.split("=", 2)
        nit.setdefault(t, {})[k] = v
    m = Mapper(is_ee=True)
    exts = sorted(
        {*nit.get("ExtMapping", {}), *m.ext_mapping, ".txt", ".dll", ".xyz", ""}, key=str.lower
    )
    folders = sorted(
        {
            *nit.get("DirMapping", {}),
            *m.dir_mapping,
            *nit.get("FolderMoves", {}).values(),
            *m.folder_moves.values(),
            *nit.get("NwnFolders", {}),
            *nit.get("ExcludeFolders", {}),
            *m.exclude_folders,
        },
        key=str.lower,
    )
    out = []
    for ext in exts:
        for variant in (ext, ext.upper()):
            name = f"sample{variant}"
            out.append(("synth", f"{MOD}/{name}"))
            for folder in folders:
                for fv in {folder, folder.upper()}:
                    if "\\" in fv:  # "parent\child" keys
                        parent, child = fv.split("\\", 1)
                        out.append(("synth", f"{MOD}/{parent}/{child}/{name}"))
                    else:
                        out.append(("synth", f"{MOD}/{fv}/{name}"))
                        out.append(("synth", f"{MOD}/{fv}/sub/{name}"))
    for ext, prefixes in list(nit.get("ExceptionPrefixes", {}).items()) + [
        (k, "|".join(v)) for k, v in m.exception_prefixes.items()
    ]:
        for p in prefixes.split("|"):
            bare = ext.lstrip(".")
            out += [
                ("synth", f"{MOD}/{p}x{ext}"),
                ("synth", f"{MOD}/X{p}{bare}{ext}"),
                ("synth", f"{MOD}/{p.upper()}x{ext.upper()}"),
            ]
    for name in {
        *nit.get("ExceptionFiles", {}),
        *m.exception_files,
        *nit.get("ExcludeFiles", {}),
        *m.exclude_files,
        *nit.get("ExcludeMods", {}),
        *m.exclude_mods,
    }:
        out += [
            ("synth", f"{MOD}/{name}"),
            ("synth", f"{MOD}/{name.upper()}"),
            ("synth", f"{MOD}/hak/{name}"),
        ]
    return out


def main() -> None:
    tables = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("corpus.tsv")
    rows = from_store() + from_archives() + from_userdir() + synth(tables)
    seen, uniq = set(), []
    for src, p in rows:
        if p not in seen:
            seen.add(p)
            uniq.append((src, p))
    out.write_text("".join(f"{s}\t{p}\n" for s, p in uniq), encoding="utf-8")
    counts: dict[str, int] = {}
    for s, _ in uniq:
        counts[s] = counts.get(s, 0) + 1
    print(f"{len(uniq)} paths -> {out}  {counts}")


if __name__ == "__main__":
    main()
