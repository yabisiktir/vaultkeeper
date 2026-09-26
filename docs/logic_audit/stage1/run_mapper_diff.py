"""Stage 1a: differential test of the file Mapper (NIT v8.0 vs Vaultkeeper).

For every corpus path, both apps answer the same five questions:
  map       target folder                      (Mapper.GetMappedFolder / get_mapped_folder)
  map-erf   target folder with the ERF check    (erfCheck=True / erf_check=True)
  excl-fi   excluded file? (name or parent\\name) (IsExcludedFile(FileInfo) / is_excluded_file x2)
  excl-dir  path contains an excluded folder?   (ContainsExcludedFolder / contains_excluded_folder)
  demo      demo/starter module?                 (IsDemoMod / is_demo_mod)

Run once per first-run mode (Player / Builder). Paths are rooted at a neutral
folder on both sides (C:\\zq\\... for NIT, /zq/... for Vaultkeeper) and compared
as normalised values (folder names, lower-cased; booleans).

Usage: python run_mapper_diff.py <corpus.tsv> <workdir>
Writes <workdir>/mapper_<mode>.tsv (every mismatch) and prints grouped patterns.
"""

from __future__ import annotations

import collections
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from vaultkeeper.core.mapper import Mapper

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent / "harness"
DRIVE_C = Path.home() / "Library/Application Support/CrossOver/Bottles/NIT/drive_c"
NITDIFF = DRIVE_C / "nitdiff"
QUERIES = ("map", "map-erf", "excl-fi", "excl-dir", "demo")
NIT_CMD = {"excl-dir": "Mapper.ContainsExcludedFolder", "demo": "Mapper.IsDemoMod"}


def run_nit(paths: list[str], mode: str, work: Path) -> dict[tuple[str, str], str]:
    rules = (HARNESS / "dialog_rules.tsv").read_text()
    if mode == "builder":
        rules = rules.replace("\tContinue\tPlayer", "\tContinue\tBuilder")
    rules_file = work / f"rules_{mode}.tsv"
    rules_file.write_text(rules)
    lines = []
    for p in paths:
        win = "C:\\zq\\" + p.replace("/", "\\")
        for q in QUERIES:
            lines.append(f"{NIT_CMD.get(q, q)}\t{win}")
    subprocess.run(
        [str(HARNESS / "make_sandbox.sh"), str(DRIVE_C)], check=True, capture_output=True
    )
    (NITDIFF / "in.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = dict(os.environ, NITDIFF_RULES=str(rules_file))
    subprocess.run([str(HARNESS / "run_nit.sh"), "900"], env=env, capture_output=True, text=True)
    out = NITDIFF / "out.tsv"
    if not out.exists():
        sys.exit("NIT produced no output:\n" + (NITDIFF / "harness.log").read_text()[-3000:])
    shutil.copy(NITDIFF / "harness.log", work / f"harness_{mode}.log")
    back = {v: k for k, v in NIT_CMD.items()}
    res = {}
    for line in out.read_text(encoding="utf-8-sig").splitlines():
        cmd, arg, val = (line.split("\t") + ["", ""])[:3]
        rel = arg[len("C:\\zq\\") :].replace("\\", "/")
        res[(back.get(cmd, cmd), rel)] = val
    # the sandbox is only needed during the run
    shutil.rmtree(NITDIFF / "sb", ignore_errors=True)
    return res


def run_vk(paths: list[str], mode: str) -> dict[tuple[str, str], str]:
    m = Mapper(is_ee=True)
    if mode == "player":
        m.apply_player_excludes()
    res = {}
    for p in paths:
        pp = PurePosixPath("/zq") / p
        res[("map", p)] = m.get_mapped_folder(pp)
        res[("map-erf", p)] = m.get_mapped_folder(pp, erf_check=True)
        res[("excl-fi", p)] = str(
            m.is_excluded_file(pp.name) or m.is_excluded_file(f"{pp.parent.name}\\{pp.name}")
        )
        res[("excl-dir", p)] = str(m.contains_excluded_folder(str(pp)))
        res[("demo", p)] = str(m.is_demo_mod(pp.name))
    return res


def norm(v: str) -> str:
    return v.strip().lower()


def main() -> None:
    corpus, work = Path(sys.argv[1]), Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    rows = [line.split("\t") for line in corpus.read_text(encoding="utf-8").splitlines()]
    source = {p: s for s, p in rows}
    paths = [p for _, p in rows]
    for mode in ("player", "builder"):
        nit = run_nit(paths, mode, work)
        vk = run_vk(paths, mode)
        mism = []
        for p in paths:
            for q in QUERIES:
                a, b = nit.get((q, p), "<missing>"), vk[(q, p)]
                if norm(a) != norm(b):
                    mism.append((q, source[p], p, a, b))
        with (work / f"mapper_{mode}.tsv").open("w", encoding="utf-8") as f:
            f.write("query\tsource\tpath\tNIT\tVK\n")
            f.writelines("\t".join(m) + "\n" for m in mism)
        total = len(paths) * len(QUERIES)
        print(f"\n=== {mode}: {len(mism)} mismatches of {total} answers")
        # group by (query, NIT answer, VK answer, extension) to expose patterns
        groups = collections.Counter(
            (q, a, b, PurePosixPath(p).suffix.lower()) for q, _, p, a, b in mism
        )
        for (q, a, b, ext), n in groups.most_common(40):
            ex = next(
                p
                for qq, _, p, aa, bb in mism
                if (qq, aa, bb) == (q, a, b) and PurePosixPath(p).suffix.lower() == ext
            )
            print(f"{n:6}  {q:8} ext={ext or '-':6} NIT={a!r:14} VK={b!r:14} e.g. {ex}")


if __name__ == "__main__":
    main()
