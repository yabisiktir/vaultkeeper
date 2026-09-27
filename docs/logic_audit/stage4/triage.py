"""Stage 4 triage: which ledger rows still need a VB-vs-Python review.

Every member of the original (``../../parity_audit/ledger_members.csv``) is put in
one bucket:

* ``covered``  — its file was executed or compared line by line in a stage
                 (``STAGE_FILES``); the verdict is in that stage's write-up;
* ``no-logic`` — a member of a *form* (a file with a ``.Designer.vb``) whose body
                 changes nothing a user keeps: no profile data, files, settings
                 writes, mapper, processes or network (``SIGNALS``). Layout,
                 painting, focus, tooltips, enabling controls. Members of data
                 and logic classes are never put here: a pure computation
                 (``ModData.SetModState``) is logic without any of those signals;
* ``trivial``  — a data/logic-class member of three lines or fewer (field
                 accessors, one-line delegations);
* ``n/a``      — ledger ``N/A`` (enums, plain properties, designer members);
* ``review``   — everything else: logic no stage ran. Reviewed by hand in
                 ``../stage4_review.md``, core files first (``CORE``).

Rows with a verdict in ``verdicts.csv`` are reviewed; ``residual.csv`` lists the rest.

Usage: python triage.py  →  residual.csv + a summary on stdout.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE.parent.parent / "parity_audit" / "ledger_members.csv"
VB = HERE.parents[3] / "NWN Installer Tool v8.0" / "NWN Installer Tool"

#: Files a stage ran (harness / differential) or compared line by line.
STAGE_FILES = {
    "1a mapping": ["Mapper.vb"],
    "1b names": ["NIT.Paste.vb"],
    "1c rules/selection": [
        "VaultDownloadRules.vb", "VaultDownloadRules.ProjectInfo.vb", "VaultScraper.vb",
        "VaultScraperInfo.vb", "DownloadProject.vb", "DownloadProject.Methods.vb",
    ],
    "2 install scenarios": [
        "InstallationManager.vb", "InstallationManager.SetInfo.vb", "ModInstallationManager.vb",
        "InstalledFileData.vb", "FileData.vb", "FileKeyInfo.vb", "ChangeData.vb",
    ],
    "3a first run": ["CreateNwnFolder.vb", "ExtendedEditionDialogue.vb", "AliasSectionEditor.vb"],
    "3b settings": [],
    "3c recovery": [],
    "3d saves": [
        "GameSaves.vb", "GameSaveInfo.vb", "GameMapper.vb", "GameMapper.UserResponses.vb",
    ],
    "3e play data": [
        "PlayDataManager.vb", "PlayDataManager.ClientLog.vb", "PlayDataManager.PlayData.vb",
    ],
    "3f installer tooling": [
        "CreateInstaller.vb", "UpdateInstaller.vb", "WizardBuilder.vb", "WizardInfo.vb",
        "PublishMod.vb", "CreateMissingInstallers.vb",
    ],
    "3g portraits/start screens": [
        "PortraitManager.vb", "StartScreenInfo.vb", "StartScreenManager.vb",
    ],
    "3h workshop": [
        "SteamWorkshop.vb", "SteamWorkshop.IdInfo.vb", "SteamWorkshop.ModInfo.vb",
        "SteamWorkshop.IdFileInfo.vb", "WorkshopViewer.vb", "WorkshopNameEditor.vb",
    ],
    "3i documents": [
        "DocOrganiser.vb", "DocOrganiser.DocInfo.vb", "DocOrganiser.ProcessDocs.vb",
    ],
    "3j characters": [
        "BicFileInfo.vb", "BicNameInfo.vb", "CharacterViewer.vb", "CharacterFilter.vb",
    ],
}
FILE_STAGE = {f: stage for stage, files in STAGE_FILES.items() for f in files}

#: Core files: the ones whose logic decides what is on disk. Reviewed first.
CORE = [
    "ProfileData.vb", "ModData.vb", "NIT.Common.vb", "NIT.Menu.vb", "NIT.Workers.vb",
    "HakPatchManager.vb", "Paths.vb", "ProfileData.Properties.vb", "ProfileInfo.vb",
    "ProfileInfoManager.vb", "GroupMemberData.vb", "Defs.vb", "NIT.ModView.vb",
    "InstallationAnalyser.vb", "DependencyManager.vb", "ErfFileReader.vb",
]

#: Something a user keeps changes: profile data, files, settings, mapping, processes.
SIGNALS = re.compile(
    r"\bpd\.|\bpim\.|\bhpm\.|\bFS\.|My\.Computer\.FileSystem|\bFile\.|\bDirectory\."
    r"|My\.Settings\.\w+\s*=[^=]|\bMap\.|\.Save\(|SaveFile|WriteAllText|Process\.Start"
    r"|RunProgram|ZipManager|\bVault\b|\bRegistry|DeleteFile|MoveFile|CopyFile|RenameFile"
    r"|InstallMods|UninstallMods|PerformCreateInstaller|CreateModFolder|RemoveMods",
    re.IGNORECASE,
)
_END = re.compile(r"^\s*End\s+(Sub|Function|Property|Operator)\b", re.IGNORECASE)
_START = re.compile(
    r"^\s*(?:(?:Public|Friend|Private|Protected|Shared|Overrides|Overridable|MustOverride|"
    r"NotOverridable|Overloads|Shadows|Default|ReadOnly|WriteOnly|Async|Iterator|Partial)\s+)*"
    r"(Sub|Function|Property|Operator|Class|Module|Structure|Enum)\s",
    re.IGNORECASE,
)


def body(file: str, line: int) -> str:
    try:
        lines = (VB / file).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    out = []
    for i, text in enumerate(lines[line - 1 :]):
        if i and _START.match(text):
            break  # the next member: this one had no End (an auto-property)
        stripped = text.split("'", 1)[0] if "\"" not in text else text
        out.append(stripped)
        if _END.match(text):
            break
    return "\n".join(out)


def is_form(file: str) -> bool:
    return (VB / file.replace(".vb", ".Designer.vb")).exists() or (
        VB / (file.split(".")[0] + ".Designer.vb")
    ).exists()


def main() -> None:
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8")))
    buckets: Counter = Counter()
    per_file: dict = defaultdict(Counter)
    residual = []
    for r in rows:
        file = r["file"]
        if r["status"] == "N/A":
            bucket = "n/a"
        elif file in FILE_STAGE:
            bucket = "covered"
        else:
            ref = r["vb_ref"].rsplit(":", 1)
            text = body(file, int(ref[1])) if len(ref) == 2 and ref[1].isdigit() else ""
            signals = sorted({m.group(0).strip().lower() for m in SIGNALS.finditer(text)})
            code = [ln for ln in text.splitlines() if ln.strip()]
            if is_form(file):
                bucket = "review" if signals else "no-logic"
            else:
                bucket = "review" if len(code) > 3 else "trivial"
            if bucket == "review":
                residual.append({**r, "signals": " ".join(signals[:6]), "lines": len(code)})
        buckets[bucket] += 1
        per_file[file][bucket] += 1
    done = set()
    verdicts = HERE / "verdicts.csv"
    if verdicts.exists():
        done = {(v["file"], v["member"]) for v in csv.DictReader(verdicts.open(encoding="utf-8"))}
    reviewed = sum(1 for r in residual if (r["file"], r["member"]) in done)
    residual = [r for r in residual if (r["file"], r["member"]) not in done]
    print(f"reviewed: {reviewed}; still to review: {len(residual)}")
    order = {f: i for i, f in enumerate(CORE)}
    def position(r: dict) -> tuple:
        line = r["vb_ref"].rsplit(":", 1)[-1]
        return (order.get(r["file"], len(CORE)), r["file"], int(line) if line.isdigit() else 0)

    residual.sort(key=position)
    fields = ["file", "member", "vb_ref", "status", "lines", "signals", "notes"]
    with (HERE / "residual.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in residual:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    print(dict(buckets), "of", len(rows))
    left = Counter(r["file"] for r in residual)
    for f, n in left.most_common():
        print(f"{n:4} {f}")


if __name__ == "__main__":
    main()
