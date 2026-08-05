"""Validate the NRBF importer against a real legacy NIT Store, when present.

The store lives outside the repo (a user's machine); these are skipped when it is
absent, mirroring the real-BIC test. When present they prove the reader + field
mappings decode genuine .NET BinaryFormatter payloads.
"""

from __future__ import annotations

import pytest

from tests import real_data

_STORE = real_data.nit_store()
_PROFILE = "Enhanced Edition Mods"

pytestmark = pytest.mark.skipif(
    _STORE is None or not (_STORE / "Data" / _PROFILE).is_dir(), reason=real_data.REASON
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


def test_install_ledger_decodes_and_matches() -> None:
    """The port's install logic matches the original's recorded ledger (real store)."""
    from vaultkeeper.game.install_verify import load_ledger, verify_ledger

    ledger = load_ledger(_STORE / "Data" / _PROFILE)
    assert len(ledger.installed) > 50  # the real profile records ~286 installed files
    # Offline checks (winner + placement) must fully agree with the original's record.
    report = verify_ledger(ledger)
    assert report.winners_checked > 0
    assert not report.of_kind("winner"), report.of_kind("winner")[:3]
    assert not report.of_kind("placement"), report.of_kind("placement")[:3]


def test_install_states_no_ignored_or_hallucinated() -> None:
    """Real profile: no mod is ignored (present but says not-installed) or hallucinated."""
    from nwnfile.locations import discover_installs

    from vaultkeeper.game.install_verify import verify_install_states
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.session import default_game_user_path

    installs = discover_installs()
    if not installs:
        import pytest as _pytest
        _pytest.skip("no NWN install discovered")
    controller = ProfileController.open_profile(
        profile_mods_dir=_STORE / "Profiles" / _PROFILE,
        game_root=installs[0].root,
        store_path=None,
        game_user_dir=default_game_user_path(),
    )
    checked, findings = verify_install_states(controller.pd, controller.ctx.game_folders)
    assert checked > 0
    ignored = [f for f in findings if f.kind == "ignored"]
    hallucinated = [f for f in findings if f.kind == "hallucination"]
    assert not ignored, ignored
    assert not hallucinated, hallucinated
