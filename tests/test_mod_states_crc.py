"""Mod states need the CRCs of a freshly built installer (logic audit S3).

VB ``UpdateProfileData`` runs ``CalculateChecksums`` before ``UpdateFileStates``.
Vaultkeeper scanned a rebuilt installer's files but left their CRC at 0, so any
two same-named files "matched": a mod whose ``shared.2da`` another mod had
overwritten showed *Match Override* instead of *Installed and Overridden*, and a
not-installed mod sharing it *Some and Match* instead of *Some and Overridden*.
Checked against NIT's own run of stage 2's "basic" scenario, step by step.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _two_mods(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    for name, body in (("Alpha", "ALPHA-SHARED"), ("Beta", "BETA-SHARED!!")):
        c.create_mod(name)
        (profile_mods / name / "shared.2da").write_text(body)
        (profile_mods / name / f"{name.lower()}.hak").write_text(name)
        assert c.build_installer_payload(name)["ok"]
    return c


def _state(c: ProfileController, name: str) -> State:
    return c.pd.mod_item(name).mod_state


def test_built_installer_files_have_their_crc(tmp_path: Path) -> None:
    c = _two_mods(tmp_path)
    crcs = {
        fk.mod_name: fd.file_crc
        for fk, fd in c.pd.file_list.items()
        if fk.filename == "shared.2da"
    }
    assert crcs["Alpha"] and crcs["Beta"] and crcs["Alpha"] != crcs["Beta"]


def test_states_of_two_mods_sharing_a_file(tmp_path: Path) -> None:
    c = _two_mods(tmp_path)

    c.install(["Alpha"])
    assert (_state(c, "Alpha"), _state(c, "Beta")) == (
        State.INSTALLED,
        State.SOME_AND_OVERRIDDEN,
    )

    c.install(["Beta"])
    assert (_state(c, "Alpha"), _state(c, "Beta")) == (
        State.INSTALLED_AND_OVERRIDDEN,
        State.INSTALLED,
    )

    c.uninstall(["Alpha"])
    assert (_state(c, "Alpha"), _state(c, "Beta")) == (
        State.SOME_AND_OVERRIDDEN,
        State.INSTALLED,
    )
