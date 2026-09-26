"""Which copy of a shared file wins when conflicting mods are installed together.

NIT's ``InstallMods`` sorts the batch's files by ``FileKeyInfo.Comparer`` (group,
then mod name), reverses, and keeps the first of each file key — so the mod that
sorts last wins, exactly as if the mods had been installed one at a time.
Vaultkeeper used to keep whichever mod the caller listed first (found by the
logic audit, docs/logic_audit/stage2_findings.md U1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _add_mod(c: ProfileController, tmp_path: Path, mod: str, files: dict[str, str]) -> None:
    """A mod with source files in its folder, built the way Create Installer builds it."""
    c.create_mod(mod)
    folder = tmp_path / "Profiles" / "P" / mod
    for rel, text in files.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    c.build_installer_payload(mod)


@pytest.mark.parametrize("order", [["Alpha Pack", "Beta Pack"], ["Beta Pack", "Alpha Pack"]])
def test_batch_install_keeps_the_priority_winner(tmp_path: Path, order: list[str]) -> None:
    c = _controller(tmp_path)
    _add_mod(c, tmp_path, "Alpha Pack", {"override/shared.2da": "ALPHA", "hak/alpha.hak": "A"})
    _add_mod(c, tmp_path, "Beta Pack", {"override/shared.2da": "BETA-LONGER", "hak/beta.hak": "B"})

    c.install(order)

    override = c.ctx.game_folders["override"]
    assert (override / "shared.2da").read_text() == "BETA-LONGER"
    # Both mods' own files still land.
    assert (c.ctx.game_folders["hak"] / "alpha.hak").read_text() == "A"
    assert (c.ctx.game_folders["hak"] / "beta.hak").read_text() == "B"


def test_batch_install_matches_one_at_a_time(tmp_path: Path) -> None:
    together, apart = tmp_path / "together", tmp_path / "apart"
    for root in (together, apart):
        root.mkdir()
    results = []
    plans = (
        (together, [["Alpha Pack", "Beta Pack"]]),
        (apart, [["Alpha Pack"], ["Beta Pack"]]),
    )
    for root, installs in plans:
        c = _controller(root)
        _add_mod(c, root, "Alpha Pack", {"override/shared.2da": "ALPHA"})
        _add_mod(c, root, "Beta Pack", {"override/shared.2da": "BETA-LONGER"})
        for batch in installs:
            c.install(batch)
        results.append((c.ctx.game_folders["override"] / "shared.2da").read_text())
    assert results[0] == results[1] == "BETA-LONGER"
