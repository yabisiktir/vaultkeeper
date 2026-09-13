"""Installing a mod pulls in the mods it depends on (VB ``InstallMods``).

NIT's ``InstallMods`` always includes a mod's uninstalled dependencies
(``IncludeDependencies``); only *uninstalling* dependencies is gated by a setting.
Vaultkeeper's install had dropped this, so a mod that requires CEP installed
without CEP. These cover the restored behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    installer = profile_mods / name / C.MOD_INSTALLER_DIR
    for rel, data in files.items():
        target = installer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _controller(tmp_path: Path, *mods: ModData) -> ProfileController:
    pd = ProfileData()
    for mod in mods:
        pd.add_mod(mod)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )


def test_with_install_dependencies_is_recursive_and_uninstalled_only(tmp_path: Path) -> None:
    ctrl = _controller(
        tmp_path,
        *[ModData(group="G", mod_name=n) for n in ("A", "B", "C", "D", "Missing_dep")],
    )
    ctrl.pd.mod_item("A").dependencies = ["B", "Ghost"]  # Ghost isn't in the profile
    ctrl.pd.mod_item("B").dependencies = ["C"]
    ctrl.pd.mod_item("C").dependencies = ["D"]
    # C is already installed -> not added, and NOT recursed into (so D is skipped).
    ctrl.pd.mod_item("C").mod_state = State.INSTALLED

    result = ctrl._with_install_dependencies(["A"])
    assert result[0] == "A"  # the requested mod stays first
    assert set(result) == {"A", "B"}  # B pulled in; C installed, D behind C, Ghost absent


def test_install_pulls_in_dependency(tmp_path: Path) -> None:
    profile_mods = tmp_path / "mods"
    _make_mod(profile_mods, "Adventure", {"hak/adv.hak": b"ADV"})
    _make_mod(profile_mods, "CEP", {"hak/cep.hak": b"CEPDATA"})
    game_root = tmp_path / "NWN"
    ctrl = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )
    ctrl.pd.mod_item("Adventure").dependencies = ["CEP"]
    assert not ctrl.pd.mod_item("CEP").installed

    ctrl.install(["Adventure"])

    assert ctrl.pd.mod_item("Adventure").installed
    assert ctrl.pd.mod_item("CEP").installed  # dependency pulled in
    # And its file actually landed somewhere in the game folder (state is only set
    # after the copy succeeds; prove the bytes are really there too).
    assert any(p.name == "cep.hak" for p in game_root.rglob("cep.hak"))


def test_install_does_not_reinstall_installed_dependency(tmp_path: Path) -> None:
    profile_mods = tmp_path / "mods"
    _make_mod(profile_mods, "Adventure", {"hak/adv.hak": b"ADV"})
    _make_mod(profile_mods, "CEP", {"hak/cep.hak": b"CEPDATA"})
    ctrl = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    ctrl.pd.mod_item("Adventure").dependencies = ["CEP"]
    ctrl.install(["CEP"])  # CEP already installed
    assert ctrl.pd.mod_item("CEP").installed
    # Installing Adventure now must not choke on the already-installed dependency.
    ctrl.install(["Adventure"])
    assert ctrl.pd.mod_item("Adventure").installed
    assert ctrl.pd.mod_item("CEP").installed
