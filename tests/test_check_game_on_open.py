"""A saved profile is checked against the game folder when it opens (logic audit 3a).

NIT's ``LoadProfile`` runs ``CheckInstalledFiles`` on every load — at start-up
and on every profile switch — and anneals the mods it affects. The game folder
is shared with other profiles, the game and whatever else the user runs;
Vaultkeeper showed a profile as it was when last closed.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path, profile: str = "P") -> ProfileController:
    profile_mods = tmp_path / "Profiles" / profile
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / f"{profile}.json",
    )


def _installed_alpha(tmp_path: Path) -> ProfileController:
    c = _open(tmp_path)
    c.create_mod("Alpha")
    source = tmp_path / "Profiles" / "P" / "Alpha"
    (source / "alpha.hak").write_text("A")
    (source / "alpha.2da").write_text("TWO")
    assert c.build_installer_payload("Alpha")["ok"]
    c.install(["Alpha"])
    assert c.pd.mod_item("Alpha").mod_state == State.INSTALLED
    return c


def test_a_file_deleted_outside_shows_on_the_next_open(tmp_path: Path) -> None:
    c = _installed_alpha(tmp_path)
    (c.ctx.game_folders["hak"] / "alpha.hak").unlink()

    reopened = _open(tmp_path)

    assert reopened.pd.mod_item("Alpha").mod_state == State.SOME_INSTALLED
    assert any("mods affected: 1" in n for n in reopened.startup_notes)


def test_a_file_overwritten_outside_is_seen_as_overridden(tmp_path: Path) -> None:
    c = _installed_alpha(tmp_path)
    (c.ctx.game_folders["override"] / "alpha.2da").write_text("SOMETHING ELSE ENTIRELY")

    reopened = _open(tmp_path)

    states = {
        fk.filename: fd.file_state
        for fk, fd in reopened.pd.file_list.items()
        if fk.mod_name == "Alpha"
    }
    assert states["alpha.2da"] == State.OVERRIDDEN


def test_an_unchanged_game_says_nothing(tmp_path: Path) -> None:
    _installed_alpha(tmp_path)
    _open(tmp_path)  # records anything written after the last scan

    assert _open(tmp_path).startup_notes == []
