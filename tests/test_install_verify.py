"""Tests for the install-ledger verifier + FileData/InstalledFileData NRBF mappers."""

from __future__ import annotations

from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import State
from vaultkeeper.game.install_verify import (
    InstallLedger,
    verify_install_states,
    verify_ledger,
    verify_located,
    verify_placement,
    verify_winners,
)
from vaultkeeper.persistence.nrbf.mapping import map_file_data, map_installed_file_data
from vaultkeeper.persistence.nrbf.reader import NrbfClass


def _fk_obj(group: str, mod: str, folder: str, filename: str) -> NrbfClass:
    return NrbfClass(
        "FileKeyInfo",
        "NWN Installer Tool",
        {"_Group": group, "_ModName": mod, "_Folder": folder, "_Filename": filename},
    )


# -- NRBF mappers ----------------------------------------------------------- #
def test_map_file_data() -> None:
    key = FileKeyInfo("G", "M", "hak", "a.hak")
    obj = NrbfClass(
        "FileData",
        "NWN Installer Tool",
        {"_FileState": int(State.INSTALLED), "_Extension": ".hak",
         "_ByteSize": 10, "_FileCRC": 123},
    )
    fd = map_file_data(key, obj)
    assert fd.extension == ".hak"
    assert fd.byte_size == 10
    assert fd.file_crc == 123
    assert fd.file_state == State.INSTALLED


def test_map_installed_file_data_uses_installer_value_and_tolerates_null() -> None:
    key = FileKeyInfo(C.GROUP_INSTALLED, C.INSTALLED_FILES_LABEL, "hak", "a.hak")
    obj = NrbfClass(
        "InstalledFileData",
        "NWN Installer Tool",
        {
            "_FileState": int(State.INSTALLED),
            "_Extension": ".hak",
            "_ByteSize": 10,
            "_FileCRC": 5,
            "InstallerValue": "CoolMod",  # NOT _Installer (spec §2.2)
            "_ModFiles": [_fk_obj("G", "CoolMod", "hak", "a.hak")],
            # legacy conflicts may hold a null entry — must be tolerated
            "_ModFileConflicts": [_fk_obj("G", "CoolMod", "hak", "a.hak"), None],
        },
    )
    ifd = map_installed_file_data(key, obj)
    assert ifd.installer == "CoolMod"
    assert [f.mod_name for f in ifd.mod_files] == ["CoolMod"]
    assert len(ifd.mod_file_conflicts) == 1  # the null was skipped


# -- Verifier logic --------------------------------------------------------- #
def _installed(folder: str, filename: str, installer: str, mod_files: list[FileKeyInfo]):
    key = FileKeyInfo(C.GROUP_INSTALLED, C.INSTALLED_FILES_LABEL, folder, filename)
    ifd = InstalledFileData(key=key, installer=installer, file_state=State.INSTALLED)
    ifd.mod_files.extend(mod_files)
    ifd.mod_file_conflicts.extend(mod_files)
    return key, ifd


def test_verify_winners_agree_and_mismatch() -> None:
    a = FileKeyInfo("100. Alpha", "ModA", "hak", "x.hak")
    b = FileKeyInfo("200. Beta", "ModB", "hak", "x.hak")
    winner = max([a, b], key=cmp_to_key(FileKeyInfo.comparer))
    loser = a if winner is b else b

    key, ifd = _installed("hak", "x.hak", winner.mod_name, [a, b])
    checked, findings = verify_winners(InstallLedger(installed={key: ifd}))
    assert checked == 1 and not findings  # port winner == recorded installer

    key2, ifd2 = _installed("hak", "x.hak", loser.mod_name, [a, b])  # wrong winner
    _, findings2 = verify_winners(InstallLedger(installed={key2: ifd2}))
    assert len(findings2) == 1 and findings2[0].kind == "winner"


def test_verify_placement_flags_wrong_folder() -> None:
    key, ifd = _installed(
        "hak", "x.hak", "ModA", [FileKeyInfo("G", "ModA", "override", "x.hak")]
    )
    _, findings = verify_placement(InstallLedger(installed={key: ifd}))
    assert len(findings) == 1 and findings[0].kind == "placement"


def test_verify_located_present_absent_and_skips(tmp_path: Path) -> None:
    (tmp_path / "hak").mkdir()
    (tmp_path / "hak" / "present.hak").write_bytes(b"x")
    k1, i1 = _installed("hak", "present.hak", "ModA",
                        [FileKeyInfo("G", "ModA", "hak", "present.hak")])
    k2, i2 = _installed("hak", "absent.hak", "ModA",
                        [FileKeyInfo("G", "ModA", "hak", "absent.hak")])
    # config-isolation folders are skipped, not failed:
    k3, i3 = _installed("nwn", "nwn.ini", "cfg", [FileKeyInfo("G", "cfg", "nwn", "nwn.ini")])
    ledger = InstallLedger(installed={k1: i1, k2: i2, k3: i3})
    checked, findings = verify_located(ledger, {"hak": tmp_path / "hak", "nwn": tmp_path})
    assert checked == 2  # present + absent (nwn config skipped)
    assert len(findings) == 1 and findings[0].file_key.endswith("absent.hak")


def _mod(group: str, name: str, files: list[FileKeyInfo], state: State):
    from vaultkeeper.core.mod_data import ModData

    md = ModData(group=group, mod_name=name)
    md.files.extend(files)
    md.mod_state = state
    return md


def test_verify_install_states_flags_ignored_and_hallucinated(tmp_path: Path) -> None:
    from vaultkeeper.core.profile_data import ProfileData

    (tmp_path / "hak").mkdir()
    (tmp_path / "hak" / "present.hak").write_bytes(b"x")
    folders = {"hak": tmp_path / "hak"}

    pd = ProfileData()
    pd.add_mod(_mod("G", "OK", [FileKeyInfo("G", "OK", "hak", "present.hak")],
                    State.INSTALLED))  # present + installed -> fine
    pd.add_mod(_mod("G", "Ignored", [FileKeyInfo("G", "Ignored", "hak", "present.hak")],
                    State.NOT_INSTALLED))  # present but says not-installed
    pd.add_mod(_mod("G", "Ghost", [FileKeyInfo("G", "Ghost", "hak", "missing.hak")],
                    State.INSTALLED))  # says installed but absent

    checked, findings = verify_install_states(pd, folders)
    assert checked == 3
    kinds = {f.file_key: f.kind for f in findings}
    assert kinds == {"Ignored": "ignored", "Ghost": "hallucination"}


def test_verify_install_states_ignores_config_and_markers(tmp_path: Path) -> None:
    from vaultkeeper.core.profile_data import ProfileData

    pd = ProfileData()
    pd.add_mod(_mod(
        "G", "ConfigOnly",
        [FileKeyInfo("G", "ConfigOnly", C.MOD_NIT_DIR, "ConfigOnly.nitres"),
         FileKeyInfo("G", "ConfigOnly", C.MOD_ROOT_FOLDER, "nwn.ini")],
        State.INSTALLED,
    ))
    checked, findings = verify_install_states(pd, {})
    assert checked == 0 and not findings  # only config / markers -> not content


def test_verify_install_states_partial_state_is_not_ignored(tmp_path: Path) -> None:
    from vaultkeeper.core.profile_data import ProfileData

    (tmp_path / "mod").mkdir()
    (tmp_path / "mod" / "c.mod").write_bytes(b"m")
    pd = ProfileData()
    # SOME_INSTALLED with the file present is correct detection (base campaign), not ignored.
    pd.add_mod(_mod("G", "Base", [FileKeyInfo("G", "Base", "mod", "c.mod")],
                    State.SOME_INSTALLED))
    checked, findings = verify_install_states(pd, {"mod": tmp_path / "mod"})
    assert checked == 1 and not findings


def test_verify_ledger_aggregate_pass(tmp_path: Path) -> None:
    (tmp_path / "hak").mkdir()
    (tmp_path / "hak" / "x.hak").write_bytes(b"data")
    a = FileKeyInfo("100. Alpha", "ModA", "hak", "x.hak")
    b = FileKeyInfo("200. Beta", "ModB", "hak", "x.hak")
    winner = max([a, b], key=cmp_to_key(FileKeyInfo.comparer))
    key, ifd = _installed("hak", "x.hak", winner.mod_name, [a, b])
    report = verify_ledger(
        InstallLedger(installed={key: ifd}), game_folders={"hak": tmp_path / "hak"}
    )
    assert report.ok
    assert report.winners_checked == 1
    assert report.located_checked == 1
    assert "MATCH" in report.summary()
