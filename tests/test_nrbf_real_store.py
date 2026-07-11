"""Validate the NRBF importer against a real legacy NIT Store, when present.

The store lives outside the repo (a user's machine); these are skipped when it is
absent, mirroring the real-BIC test. When present they prove the reader + field
mappings decode genuine .NET BinaryFormatter payloads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_STORE = Path("/Users/example/Documents/NIT Store")
_PROFILE = "Enhanced Edition Mods"

pytestmark = pytest.mark.skipif(
    not (_STORE / "Data" / _PROFILE).is_dir(), reason="No real NIT Store on this machine"
)


def test_migrate_real_profile_imports_mods() -> None:
    from vaultkeeper.persistence.nrbf.migrate import list_profiles, migrate_profile

    assert _PROFILE in list_profiles(_STORE)
    pd = migrate_profile(_STORE, _PROFILE)
    mods = [m for m in pd.mod_list.values() if not m.is_group_item]
    assert len(mods) >= 10  # the real store has ~21 mods
    # Real group names come through (reserved buckets).
    groups = {m.group for m in mods}
    assert "799.  Mods Installed by NWN" in groups
    # A real mod name is present.
    names = {m.mod_name for m in mods}
    assert any("Neverwinter Nights" in n for n in names)


def test_real_moddata_field_names_match_mapping() -> None:
    from vaultkeeper.persistence.nrbf.migrate import find_latest_data_file
    from vaultkeeper.persistence.nrbf.reader import NrbfClass, read_nrbf

    f = find_latest_data_file(_STORE / "Data" / _PROFILE, "ModData")
    assert f is not None
    root = read_nrbf(f.read_bytes())

    out: list = []

    def find(o, seen):
        if id(o) in seen or out:
            return
        seen.add(id(o))
        if isinstance(o, NrbfClass):
            if o.name.endswith(".ModData"):
                out.append(o)
                return
            for v in o.members.values():
                find(v, seen)
        elif isinstance(o, list):
            for v in o:
                find(v, seen)

    find(root, set())
    assert out, "no ModData instance found"
    members = set(out[0].members)
    # The exact serialized field names the mapping relies on (incl. the VB typo).
    for field in ("_Group", "_ModName", "_ModState", "_Rating", "_BestWeapon",
                  "_Dependencies", "_Files", "_WebLink", "LevelEndtValue"):
        assert field in members, field
