"""Verify the port's install logic against the ORIGINAL tool's recorded ledger.

The original NWN Installer Tool records exactly what it installed in two NRBF
dictionaries per profile — ``nit.InstallData_Format_002``
(``Dict[FileKeyInfo, InstalledFileData]``: every installed game file + which mod
won it + CRC + the conflicting mod files) and ``nit.FileData_Format_002``. That
recorded ledger is authoritative ground truth, so we can check the port's install
*logic* against it without running the original or touching the game:

* **Winner parity** — for every installed file with a conflict, does the port's
  "last by :meth:`FileKeyInfo.comparer` wins" rule pick the same owning mod the
  original recorded? (The correctness heart of conflict resolution.)
* **Placement consistency** — every conflicting mod file sits in the same game
  folder as the installed file it maps onto.
* **Content parity** (optional, live) — for each recorded file with a real CRC,
  the file currently on disk in the game folders matches the recorded CRC, so the
  port reads the same bytes the original did.

Pure/headless: reading + comparing take a directory of ``nit.*`` files and an
optional ``{folder: path}`` game-folder map; nothing here mutates state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.crc import crc32_file
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.persistence.nrbf.mapping import import_file_list, import_installed_list

INSTALL_DATA_FILE = "nit.InstallData_Format_002"
FILE_DATA_FILE = "nit.FileData_Format_002"


@dataclass
class InstallLedger:
    """The original tool's recorded install ledger for one profile."""

    installed: dict[FileKeyInfo, InstalledFileData] = field(default_factory=dict)
    files: dict[FileKeyInfo, FileData] = field(default_factory=dict)


@dataclass
class Finding:
    """One disagreement between the port and the original's recorded ledger."""

    kind: str  # "winner" | "placement" | "content"
    file_key: str
    expected: str  # what the original recorded
    actual: str  # what the port computes
    detail: str = ""


@dataclass
class VerifyReport:
    installed_count: int = 0
    winners_checked: int = 0
    placements_checked: int = 0
    located_checked: int = 0
    contents_checked: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def of_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]

    def summary(self) -> str:
        w = len(self.of_kind("winner"))
        p = len(self.of_kind("placement"))
        loc = len(self.of_kind("located"))
        c = len(self.of_kind("content"))
        verdict = "MATCH" if self.ok else "MISMATCH"
        return (
            f"{verdict}: {self.installed_count} installed files recorded by the original.\n"
            f"  winners:    {self.winners_checked - w}/{self.winners_checked} agree\n"
            f"  placements: {self.placements_checked - p}/{self.placements_checked} agree\n"
            f"  located:    {self.located_checked - loc}/{self.located_checked} found on disk\n"
            f"  contents:   {self.contents_checked - c}/{self.contents_checked} CRC match"
            f"{' (original recorded no CRCs)' if self.contents_checked == 0 else ''}"
        )


def load_ledger(profile_data_dir: Path) -> InstallLedger:
    """Read the original's recorded install ledger from a profile data directory."""
    ledger = InstallLedger()
    install_file = profile_data_dir / INSTALL_DATA_FILE
    file_file = profile_data_dir / FILE_DATA_FILE
    if install_file.is_file():
        ledger.installed = import_installed_list(install_file.read_bytes())
    if file_file.is_file():
        ledger.files = import_file_list(file_file.read_bytes())
    return ledger


def _port_winner(mod_files: list[FileKeyInfo]) -> str:
    """The port's owning mod for a set of conflicting mod files (greatest by comparer).

    Mirrors ``ProfileData.set_installer``: with one candidate it wins outright; with
    several, the last by :meth:`FileKeyInfo.comparer` (they are all installed here,
    since they are an installed file's CRC-matching set).
    """
    winner = max(mod_files, key=cmp_to_key(FileKeyInfo.comparer))
    return winner.mod_name


def verify_winners(ledger: InstallLedger) -> tuple[int, list[Finding]]:
    """Check the port picks the same conflict winner the original recorded."""
    checked = 0
    findings: list[Finding] = []
    for fk, ifd in ledger.installed.items():
        if not ifd.mod_files:
            continue  # default classification (Original / Unknown / character), not a mod
        checked += 1
        actual = _port_winner(list(ifd.mod_files))
        if actual.lower() != ifd.installer.lower():
            findings.append(
                Finding(
                    "winner",
                    fk.full_key,
                    ifd.installer,
                    actual,
                    detail=f"{len(ifd.mod_files)} conflicting mod file(s)",
                )
            )
    return checked, findings


def verify_placement(ledger: InstallLedger) -> tuple[int, list[Finding]]:
    """Check each conflicting mod file sits in the installed file's game folder."""
    checked = 0
    findings: list[Finding] = []
    for fk, ifd in ledger.installed.items():
        target = fk.folder.lower()
        for mod_file in ifd.mod_file_conflicts:
            checked += 1
            if mod_file.folder.lower() != target:
                findings.append(
                    Finding(
                        "placement",
                        fk.full_key,
                        f"folder '{fk.folder}'",
                        f"mod file '{mod_file.full_key}' in '{mod_file.folder}'",
                    )
                )
    return checked, findings


def verify_located(
    ledger: InstallLedger, game_folders: dict[str, Path]
) -> tuple[int, list[Finding]]:
    """Check the port can locate every file the original recorded as installed.

    CRC-free: for each installed file, resolve its game folder from ``game_folders``
    and confirm the file exists there. This exercises the folder resolution (the EE
    user-dir split) against the original's authoritative installed set — if the
    original said it installed ``hak/foo.hak`` and the port looks somewhere the file
    isn't, that is a resolution finding. ``nitconfig`` markers (``.nitins`` /
    ``.nitres``) are NIT-managed and only present when NIT itself installed the mod,
    so their absence is not counted as a mismatch.
    """
    # Folders whose absence is expected, not a parity failure:
    #  - nitconfig: NIT identifier markers, only present when NIT installed the mod.
    #  - nwn (root): the game config files (nwn.ini / settings.tml / *.bak) which the
    #    port handles via config-isolation and never treats as installed game content.
    expected_absent = {C.MOD_NIT_DIR.lower(), C.MOD_ROOT_FOLDER.lower()}
    checked = 0
    findings: list[Finding] = []
    for fk in ledger.installed:
        if fk.folder.lower() in expected_absent:
            continue
        checked += 1
        folder = game_folders.get(fk.folder) or game_folders.get(fk.folder.lower())
        if folder is None:
            findings.append(
                Finding(
                    "located", fk.full_key, f"folder '{fk.folder}' mapped",
                    "no such game folder",
                )
            )
            continue
        if not (folder / fk.filename).is_file():
            findings.append(
                Finding(
                    "located",
                    fk.full_key,
                    "file present",
                    "not found",
                    detail=str(folder / fk.filename),
                )
            )
    return checked, findings


def verify_contents(
    ledger: InstallLedger, game_folders: dict[str, Path]
) -> tuple[int, list[Finding]]:
    """Check the file on disk matches the recorded CRC (the port reads the same bytes).

    Only files the original recorded with a real CRC and that resolve to an existing
    path in ``game_folders`` are checked; the rest (CRC 0 / missing folder / absent
    file) are skipped rather than counted as mismatches.
    """
    checked = 0
    findings: list[Finding] = []
    for fk, ifd in ledger.installed.items():
        if ifd.file_crc == 0:
            continue
        folder = game_folders.get(fk.folder) or game_folders.get(fk.folder.lower())
        if folder is None:
            continue
        path = folder / fk.filename
        if not path.is_file():
            continue
        checked += 1
        actual = crc32_file(path)
        if actual != ifd.file_crc:
            findings.append(
                Finding(
                    "content",
                    fk.full_key,
                    f"crc {ifd.file_crc}",
                    f"crc {actual}",
                    detail=str(path),
                )
            )
    return checked, findings


def verify_ledger(
    ledger: InstallLedger, *, game_folders: dict[str, Path] | None = None
) -> VerifyReport:
    """Run all available checks and aggregate into a report.

    ``game_folders`` (folder name -> absolute path) enables the live content/CRC
    check; omit it to run only the offline winner + placement checks.
    """
    report = VerifyReport(installed_count=len(ledger.installed))
    report.winners_checked, w = verify_winners(ledger)
    report.placements_checked, p = verify_placement(ledger)
    report.findings.extend(w)
    report.findings.extend(p)
    if game_folders is not None:
        report.located_checked, loc = verify_located(ledger, game_folders)
        report.contents_checked, c = verify_contents(ledger, game_folders)
        report.findings.extend(loc)
        report.findings.extend(c)
    return report
