"""Convert an Official/Premium .nwm so the Toolset can open it (newtopic59.htm)."""

from __future__ import annotations

import struct
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.game.nwm_convert import (
    CONVERTED_DEPS_MOD,
    CONVERTED_GROUP,
    module_dependencies,
)
from vaultkeeper.ui.controller import ProfileController

# -- A minimal .nwm carrying a module.ifo with hak/tlk references ---------- #


def _module_ifo(haks: list[str], tlk: str = "") -> bytes:
    """A real GFF module.ifo naming ``haks`` in Mod_HakList and ``tlk``."""
    from nwnfile.formats.gff import Gff, GffField, GffList, GffStruct, GffType

    root = GffStruct(struct_type=0xFFFFFFFF)
    hak_list = GffList(
        structs=[
            GffStruct(struct_type=8, fields={"Mod_Hak": GffField(GffType.CRESREF, h)})
            for h in haks
        ]
    )
    root.fields["Mod_HakList"] = GffField(GffType.LIST, hak_list)
    if tlk:
        root.fields["Mod_CustomTlk"] = GffField(GffType.CRESREF, tlk)
    from nwnfile.formats.gff import write_gff

    return write_gff(Gff(file_type="IFO ", version="V3.2", root=root))


def _nwm(path: Path, haks: list[str], tlk: str = "") -> Path:
    """Write a minimal ERF (.nwm) whose only resource is a module.ifo."""
    payload = _module_ifo(haks, tlk)

    key_offset = 32
    res_offset = key_offset + 24  # one 24-byte key entry
    data_offset = res_offset + 8  # one 8-byte resource entry

    header = struct.pack(
        "<4s4s6i",
        b"MOD ",
        b"V1.0",
        0,  # loc_count
        0,  # loc_size
        1,  # entry_count
        0,  # loc_offset
        key_offset,
        res_offset,
    )
    resref = b"module".ljust(16, b"\x00")
    key = resref + struct.pack("<iHH", 0, 2014, 0)  # res_id 0, type 2014 (ifo)
    res = struct.pack("<Ii", data_offset, len(payload))
    path.write_bytes(header + key + res + payload)
    return path


# -- Reading a module's dependencies --------------------------------------- #


def test_module_dependencies_reads_haks_and_tlk(tmp_path):
    nwm = _nwm(tmp_path / "Chapter1.nwm", ["cep2_add_top", "prc_consortium"], "dialog")
    haks, tlks = module_dependencies(nwm)
    assert haks == ["cep2_add_top", "prc_consortium"]
    assert tlks == ["dialog"]


def test_module_dependencies_of_something_unreadable_is_empty(tmp_path):
    junk = tmp_path / "notreal.nwm"
    junk.write_bytes(b"not an erf at all")
    assert module_dependencies(junk) == ([], [])


# -- The conversion -------------------------------------------------------- #


def _controller(tmp_path: Path, *, is_ee: bool = True) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root = tmp_path / "NWN"
    for folder in ("modules", "hak", "tlk"):
        (game_root / folder).mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
        is_ee=is_ee,
    )


def test_convert_creates_a_mod_holding_the_module_as_mod(tmp_path):
    controller = _controller(tmp_path)
    nwm = _nwm(tmp_path / "Prelude.nwm", [])

    result = controller.convert_nwm_to_mod(nwm)

    assert result["ok"] is True
    assert result["mod_name"] == "Prelude"
    assert result["group"] == CONVERTED_GROUP
    # The module is now a .mod under the converted mod's modules folder.
    mod_copy = (
        controller.ctx.profile_mods_dir
        / "Prelude"
        / C.MOD_INSTALLER_DIR
        / "modules"
        / "Prelude.mod"
    )
    assert mod_copy.is_file()
    assert mod_copy.read_bytes() == nwm.read_bytes()
    # It landed in the ZZZ group.
    assert controller.pd.mod_item("Prelude").group == CONVERTED_GROUP


def test_convert_refuses_a_non_nwm(tmp_path):
    controller = _controller(tmp_path)
    plain = tmp_path / "thing.hak"
    plain.write_bytes(b"x")
    result = controller.convert_nwm_to_mod(plain)
    assert result["ok"] is False


def test_convert_refuses_to_repeat_itself(tmp_path):
    controller = _controller(tmp_path)
    nwm = _nwm(tmp_path / "Prelude.nwm", [])
    assert controller.convert_nwm_to_mod(nwm)["ok"] is True
    second = controller.convert_nwm_to_mod(nwm)
    assert second["ok"] is False
    assert "already" in second["message"]


def test_convert_on_ee_gathers_the_named_haks_and_tlk(tmp_path):
    controller = _controller(tmp_path, is_ee=True)
    # The game actually has two of the three haks and the tlk on disk.
    (controller.ctx.game_folders["hak"] / "cep2_add_top.hak").write_bytes(b"HAK")
    (controller.ctx.game_folders["tlk"] / "dialog.tlk").write_bytes(b"TLK")
    nwm = _nwm(tmp_path / "Chapter1.nwm", ["cep2_add_top", "missing_hak"], "dialog")

    result = controller.convert_nwm_to_mod(nwm)

    assert result["dependencies_mod"] == CONVERTED_DEPS_MOD
    deps = controller.ctx.profile_mods_dir / CONVERTED_DEPS_MOD / C.MOD_INSTALLER_DIR
    # The hak the game has is carried; the one it does not is skipped, not faked.
    assert (deps / "hak" / "cep2_add_top.hak").is_file()
    assert not (deps / "hak" / "missing_hak.hak").exists()
    assert (deps / "tlk" / "dialog.tlk").is_file()


def test_convert_on_non_ee_builds_no_dependency_mod(tmp_path):
    controller = _controller(tmp_path, is_ee=False)
    (controller.ctx.game_folders["hak"] / "cep2_add_top.hak").write_bytes(b"HAK")
    nwm = _nwm(tmp_path / "Chapter1.nwm", ["cep2_add_top"])

    result = controller.convert_nwm_to_mod(nwm)

    assert result["dependencies_mod"] == ""
    assert CONVERTED_DEPS_MOD not in controller.pd.mod_list


def test_a_second_conversion_reuses_the_dependency_mod(tmp_path):
    controller = _controller(tmp_path, is_ee=True)
    (controller.ctx.game_folders["hak"] / "a.hak").write_bytes(b"A")
    (controller.ctx.game_folders["hak"] / "b.hak").write_bytes(b"B")
    controller.convert_nwm_to_mod(_nwm(tmp_path / "One.nwm", ["a"]))
    controller.convert_nwm_to_mod(_nwm(tmp_path / "Two.nwm", ["b"]))

    deps = controller.ctx.profile_mods_dir / CONVERTED_DEPS_MOD / C.MOD_INSTALLER_DIR
    assert (deps / "hak" / "a.hak").is_file()
    assert (deps / "hak" / "b.hak").is_file()
    # Still one dependency mod, not two.
    assert sum(1 for m in controller.pd.mod_list if m == CONVERTED_DEPS_MOD) == 1
