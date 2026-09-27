"""A mod's own ``nitconfig`` folder is never copied into its installer (audit M2).

NIT maps ``nitconfig/*`` like any folder rule, so a source folder that carries
identifier files — a copied installer, a published archive unpacked into a mod —
has them copied into the new installer: the mod's own identifier (harmless, the
build writes one anyway) and any other mod's ``.nitins`` / ``.nitres`` too, which
would then mark that other mod as installed whenever this one is. Vaultkeeper
skips ``nitconfig`` sources and writes only the mod's own identifier. Deliberate.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def test_only_the_mods_own_identifier_is_in_the_installer(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Alpha")
    source = profile_mods / "Alpha"
    (source / "alpha.hak").write_text("A")
    (source / "nitconfig").mkdir()
    (source / "nitconfig" / "Other Mod.nitins").write_text("")
    (source / "nitconfig" / "Old Restorer.nitres").write_text("")

    assert c.build_installer_payload("Alpha")["ok"]

    nit = source / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
    assert sorted(p.name for p in nit.iterdir()) == ["Alpha.nitins"]
    assert c.pd.mod_item("Alpha").is_installer() and not c.pd.mod_item("Alpha").is_restorer()
