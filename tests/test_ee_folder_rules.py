"""EE library folders are folder rules (VB ``Mapper.DefineEeFolders``).

A mod laid out for the Enhanced Edition library ships files inside ``ovr/``,
``mus/``, ``txpk/`` or the EE ``mod/`` folder; NIT installs them into that
folder. Vaultkeeper routed them by extension instead (e.g. ``ovr/x.2da`` →
``override``): logic audit, docs/logic_audit/stage1_findings.md M1. Without EE,
NIT points "ovr" rules at ``override``.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from vaultkeeper.core.mapper import Mapper


@pytest.mark.parametrize(
    ("path", "folder"),
    [
        ("Mod/ovr/x.2da", "ovr"),
        ("Mod/OVR/sub/x.tga", "ovr"),
        ("Mod/mus/x.bmu", "mus"),
        ("Mod/txpk/x.erf", "txpk"),
        ("Mod/mod/x.2da", "mod"),
        ("Mod/override/x.2da", "override"),
    ],
)
def test_ee_library_folders_keep_their_folder(path: str, folder: str) -> None:
    assert Mapper(is_ee=True).get_mapped_folder(PurePosixPath(path)) == folder


def test_without_ee_ovr_rules_use_override() -> None:
    m = Mapper(is_ee=False)
    assert m.get_mapped_folder(PurePosixPath("Mod/bd hd textures modular/x.dds")) == "override"
    assert m.get_mapped_folder(PurePosixPath("Mod/ovr/x.2da")) == "override"


def test_ee_keeps_the_ovr_rule_for_named_packs() -> None:
    m = Mapper(is_ee=True)
    assert m.get_mapped_folder(PurePosixPath("Mod/bd hd textures modular/x.dds")) == "ovr"


def test_a_users_own_folder_rule_still_wins() -> None:
    m = Mapper(is_ee=True, overrides={"dir_mapping": {"mus": "music"}})
    assert m.get_mapped_folder(PurePosixPath("Mod/mus/x.bmu")) == "music"
