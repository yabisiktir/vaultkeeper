"""Installation sets — named install-state snapshots (VB InstallationManager).

Covers the headless data model + apply-diff + validation, the controller's
load/save/create/rename/delete/apply, and the editor dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.game.installation_sets import (
    SET_CHECKPOINT,
    SET_CURRENT,
    SET_USER,
    STATE_INSTALLED,
    STATE_SOME,
    STATE_UNINSTALLED,
    GroupEntry,
    InstallationSet,
    ModEntry,
    apply_diff,
    build_set,
    sets_from_json,
    sets_to_json,
    validate_sets,
)
from vaultkeeper.game.start_screen import AUTO_GROUP
from vaultkeeper.ui.controller import ProfileController


# -- headless model -------------------------------------------------------- #
def test_build_set_marks_every_mod_installed():
    s = build_set("Snap", SET_CHECKPOINT, {"GroupA": ["A1", "A2"], "GroupB": ["B1"]})
    assert s.set_type == SET_CHECKPOINT
    assert [g.name for g in s.groups] == ["GroupA", "GroupB"]
    assert all(m.desired_installed for g in s.groups for m in g.mods)
    assert s.state() == STATE_INSTALLED


def test_group_and_set_state():
    g = GroupEntry("G", [ModEntry("a", True), ModEntry("b", False)])
    assert g.state() == STATE_SOME
    s = InstallationSet("S", SET_USER, groups=[g])
    assert s.state() == STATE_SOME
    empty = InstallationSet("E", SET_USER, groups=[GroupEntry("G", [ModEntry("x", False)])])
    assert empty.state() == STATE_UNINSTALLED


def test_apply_diff_installs_and_uninstalls():
    s = InstallationSet(
        "S",
        SET_USER,
        groups=[
            GroupEntry("G", [ModEntry("want_in", True), ModEntry("want_out", False)]),
            GroupEntry("H", [ModEntry("already_in", True), ModEntry("already_out", False)]),
        ],
    )
    installs, uninstalls = apply_diff(s, current_installed={"want_out", "already_in"})
    assert installs == ["want_in"]
    assert uninstalls == ["want_out"]


def test_apply_diff_dedups_across_groups():
    s = InstallationSet(
        "S",
        SET_USER,
        groups=[
            GroupEntry("G", [ModEntry("dup", True)]),
            GroupEntry("H", [ModEntry("dup", True)]),
        ],
    )
    installs, uninstalls = apply_diff(s, current_installed=set())
    assert installs == ["dup"]


def test_validate_drops_deleted_groups_and_mods():
    s = InstallationSet(
        "S",
        SET_USER,
        groups=[
            GroupEntry("Gone", [ModEntry("x", True)]),
            GroupEntry("Live", [ModEntry("keep", True), ModEntry("deletedmod", True)]),
        ],
    )
    result = validate_sets(
        [s], existing_mods={"keep": "Live"}, existing_groups={"Live"}
    )
    assert result.total == 2  # the whole "Gone" group + the deleted mod
    assert result.removed_groups == 1
    assert result.removed_mods == 1
    assert [g.name for g in s.groups] == ["Live"]
    assert [m.name for m in s.groups[0].mods] == ["keep"]


def test_validate_skips_current_set():
    s = InstallationSet("Current", SET_CURRENT, groups=[GroupEntry("Gone", [])])
    assert validate_sets([s], existing_mods={}, existing_groups=set()).total == 0
    assert len(s.groups) == 1


def test_sets_validation_changes_info():
    from vaultkeeper.game.installation_sets import SetsValidation

    assert SetsValidation().changes_info() == "Sets updated: no changes."
    assert (
        SetsValidation(removed_groups=1, removed_mods=3).changes_info()
        == "Sets updated: 4 changes. Groups removed: 1. Mods removed: 3."
    )
    assert (
        SetsValidation(removed_mods=1).changes_info()
        == "Sets updated: 1 change. Mods removed: 1."
    )


def test_json_round_trip_excludes_current():
    sets = [
        InstallationSet("Current", SET_CURRENT, groups=[GroupEntry("G", [])]),
        build_set("Snap", SET_CHECKPOINT, {"G": ["a"]}),
    ]
    data = sets_to_json(sets)
    assert len(data) == 1  # the current set is not persisted
    restored = sets_from_json(data)
    assert restored[0].name == "Snap"
    assert restored[0].groups[0].mods[0].name == "a"


def test_sets_from_json_tolerates_garbage():
    assert sets_from_json(None) == []
    assert sets_from_json("nope") == []


# -- controller ------------------------------------------------------------ #
def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    ctrl = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    return ctrl


def _add_mod(ctrl, name, group, *, installed):
    state = State.INSTALLED if installed else State.NOT_INSTALLED
    ctrl.pd.add_mod(ModData(group=group, mod_name=name, mod_state=state))


def test_installed_by_group_filters_and_sorts(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Beta", "GroupB", installed=True)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    _add_mod(ctrl, "NotInst", "GroupA", installed=False)  # excluded (not installed)
    _add_mod(ctrl, "AutoMod", AUTO_GROUP, installed=True)  # excluded (auto group)

    by_group = ctrl.installed_by_group()
    assert list(by_group.keys()) == ["GroupA", "GroupB"]  # win-sorted groups
    assert by_group["GroupA"] == ["Alpha"]
    assert by_group["GroupB"] == ["Beta"]
    assert AUTO_GROUP not in by_group


def test_load_has_current_first(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    sets = ctrl.load_installation_sets()
    assert sets[0].set_type == SET_CURRENT
    assert sets[0].name == "Current"
    assert sets[0].groups[0].mods[0].name == "Alpha"


def test_create_checkpoint_persists(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    name = ctrl.create_installation_checkpoint()
    sets = ctrl.load_installation_sets()
    assert any(s.name == name and s.set_type == SET_CHECKPOINT for s in sets)
    # Persisted to disk.
    assert ctrl._installation_sets_file().exists()


def test_create_user_set_and_rename_and_delete(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    ctrl.create_installation_set("My Set")
    assert any(s.name == "My Set" and s.editable for s in ctrl.load_installation_sets())

    ctrl.rename_installation_set("My Set", "Renamed")
    names = {s.name for s in ctrl.load_installation_sets()}
    assert "Renamed" in names and "My Set" not in names

    ctrl.delete_installation_set("Renamed")
    assert "Renamed" not in {s.name for s in ctrl.load_installation_sets()}


def test_load_prunes_stale_mods(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    ctrl.create_installation_set("Set")
    # Remove the mod from the profile -> the set's entry should be pruned on reload.
    ctrl.pd.remove_mod("Alpha")
    sets = ctrl.load_installation_sets()
    the_set = next(s for s in sets if s.name == "Set")
    assert all(m.name != "Alpha" for g in the_set.groups for m in g.mods)


def test_apply_routes_installs_and_uninstalls(tmp_path, monkeypatch):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "InstalledMod", "GroupA", installed=True)
    _add_mod(ctrl, "MissingMod", "GroupA", installed=False)

    calls = {"install": None, "uninstall": None}

    def record(key, msg):
        def _fn(names):
            calls[key] = names
            return msg

        return _fn

    monkeypatch.setattr(ctrl, "install", record("install", "installed"))
    monkeypatch.setattr(ctrl, "uninstall", record("uninstall", "uninstalled"))

    # A set that wants MissingMod installed and InstalledMod removed.
    s = InstallationSet(
        "S",
        SET_USER,
        groups=[
            GroupEntry(
                "GroupA",
                [ModEntry("MissingMod", True), ModEntry("InstalledMod", False)],
            )
        ],
    )
    msg = ctrl.apply_installation_set(s)
    assert calls["uninstall"] == ["InstalledMod"]
    assert calls["install"] == ["MissingMod"]
    assert "installed" in msg and "uninstalled" in msg


def test_apply_noop_when_already_matching(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    s = ctrl.load_installation_sets()[0]  # the Current set matches reality
    assert "already applied" in ctrl.apply_installation_set(s)


# -- dialog ---------------------------------------------------------------- #
def test_dialog_lists_current_first(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    assert dlg.set_list.count() >= 1
    assert "Current" in dlg.set_list.item(0).text()
    # The tree shows the current set's mod.
    assert dlg.tree.topLevelItemCount() == 1
    assert dlg.tree.topLevelItem(0).text(0) == "GroupA"


def test_dialog_new_checkpoint(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    before = dlg.set_list.count()
    dlg._on_new_checkpoint()
    assert dlg.set_list.count() == before + 1


def test_dialog_apply_calls_controller(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    applied = {}

    def fake_apply(s):
        applied["set"] = s
        return "ok"

    monkeypatch.setattr(ctrl, "apply_installation_set", fake_apply)
    dlg.set_list.setCurrentRow(0)
    dlg._on_apply()
    assert applied["set"] is not None


def test_command_opens_manager_and_is_enabled(tmp_path, qtbot):
    """MsInstallationManager / RbnInstallationManager dispatch to the manager and are
    no longer greyed out (they now have a real handler)."""
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    assert "MsInstallationManager" in win.implemented_commands()
    assert win.nit_menu.actions_by_id["MsInstallationManager"].isEnabled()
    win._on_command("MsInstallationManager")
    assert win._installation_manager.isVisible()


def test_controller_surfaces_reconciliation_summary(tmp_path):
    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "Live", installed=True)
    # A saved user set references a group that no longer exists → pruned on load.
    stale = InstallationSet(
        "S",
        SET_USER,
        groups=[
            GroupEntry("Gone", [ModEntry("ghost", True)]),
            GroupEntry("Live", [ModEntry("Alpha", True)]),
        ],
    )
    ctrl.save_installation_sets([stale])
    assert ctrl.installation_sets_changes_info() == ""  # nothing loaded yet
    ctrl.load_installation_sets()
    info = ctrl.installation_sets_changes_info()
    assert info == "Sets updated: 1 change. Groups removed: 1."


def test_dialog_shows_reconciliation_summary(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "Live", installed=True)
    ctrl.save_installation_sets(
        [InstallationSet("S", SET_USER, groups=[GroupEntry("Gone", [ModEntry("g", True)])])]
    )
    dlg = InstallationManager.show_for(ctrl)
    qtbot.addWidget(dlg)
    assert "Groups removed: 1" in dlg._status.text()


# -- sorting the set list (VB TsCreated / TsUpdated / TsSetName + TsAscending) -- #
def _sort_dialog(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    return dlg


def _named_sets():
    from vaultkeeper.game.installation_sets import SET_CURRENT, InstallationSet

    return [
        InstallationSet(name="Current", set_type=SET_CURRENT, created="2026-09-09"),
        InstallationSet(name="Beta", set_type="user", created="2026-01-02"),
        InstallationSet(name="Alpha", set_type="user", created="2026-03-09"),
        InstallationSet(name="Gamma", set_type="user", created="2026-02-05"),
    ]


def test_sets_sort_by_the_chosen_key_and_direction(tmp_path, qtbot):
    dlg = _sort_dialog(tmp_path, qtbot)
    sets = _named_sets()

    dlg.sort_key.setCurrentIndex(dlg.sort_key.findData("name"))
    assert [s.name for s in dlg._sorted_sets(sets)] == [
        "Current", "Alpha", "Beta", "Gamma",
    ]

    dlg.sort_key.setCurrentIndex(dlg.sort_key.findData("created"))
    assert [s.name for s in dlg._sorted_sets(sets)] == [
        "Current", "Beta", "Gamma", "Alpha",
    ], "oldest first"

    dlg.sort_desc.setChecked(True)
    assert [s.name for s in dlg._sorted_sets(sets)] == [
        "Current", "Alpha", "Gamma", "Beta",
    ], "newest first"


def test_the_current_set_stays_at_the_top_whatever_the_sort(tmp_path, qtbot):
    """It is the live state, not a snapshot.

    Sorting it into the middle of a date order would make the list read as if
    the live state had gone missing.
    """
    dlg = _sort_dialog(tmp_path, qtbot)
    sets = _named_sets()
    for key in ("name", "created", "updated"):
        dlg.sort_key.setCurrentIndex(dlg.sort_key.findData(key))
        for descending in (False, True):
            dlg.sort_desc.setChecked(descending)
            assert dlg._sorted_sets(sets)[0].name == "Current"


# -- Group Selector (VB TsGroupSelector / LvGroupSelector) ------------------- #
def _selector_dialog(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    _add_mod(ctrl, "Beta", "GroupB", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    return ctrl, dlg


def _select_set(dlg, name):
    for i in range(dlg.set_list.count()):
        if name in dlg.set_list.item(i).text():
            dlg.set_list.setCurrentRow(i)
            return dlg._current_set
    raise AssertionError(f"no set named {name}")


def test_group_selector_is_offered_only_for_editable_sets(tmp_path, qtbot):
    """VB enables the toggle only for a User set.

    A checkable list you cannot change is worse than no list at all.
    """
    ctrl, dlg = _selector_dialog(tmp_path, qtbot)
    _select_set(dlg, "Current")  # the live state, not editable
    assert not dlg.selector_toggle.isEnabled()
    assert dlg.group_selector.isHidden()

    ctrl.create_installation_set("Mine")
    dlg._reload("Mine")
    _select_set(dlg, "Mine")
    assert dlg.selector_toggle.isEnabled()


def test_ticking_a_group_adds_it_whole_and_unticking_removes_it(tmp_path, qtbot):
    ctrl, dlg = _selector_dialog(tmp_path, qtbot)
    ctrl.create_installation_set("Mine")
    dlg._reload("Mine")
    iset = _select_set(dlg, "Mine")
    dlg.selector_toggle.setChecked(True)

    names = [dlg.group_selector.item(i).text() for i in range(dlg.group_selector.count())]
    assert set(names) == {"GroupA", "GroupB"}

    # Everything starts in the set (it was checkpointed from what is installed).
    before = {g.name for g in iset.groups}
    target = dlg.group_selector.item(names.index("GroupA"))

    target.setCheckState(Qt.CheckState.Unchecked)
    assert "GroupA" not in {g.name for g in iset.groups}, "unticking must remove it"

    target.setCheckState(Qt.CheckState.Checked)
    after = {g.name for g in iset.groups}
    assert "GroupA" in after, "ticking must add it back"
    assert after == before
    # ...and it comes back with its mods, not as an empty group.
    group = next(g for g in iset.groups if g.name == "GroupA")
    assert [m.name for m in group.mods] == ["Alpha"]
    assert all(m.desired_installed for m in group.mods)


def test_dialog_f2_renames_the_selected_set(tmp_path, qtbot, monkeypatch):
    """renameinstallationsets.htm: "press F2 or click Rename"."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

    ctrl = _controller(tmp_path)
    _add_mod(ctrl, "Alpha", "GroupA", installed=True)
    dlg = InstallationManager(ctrl)
    qtbot.addWidget(dlg)
    dlg._on_new_checkpoint()  # a non-Current set that can be renamed

    # Select the new checkpoint (Current is guarded against rename).
    for row in range(dlg.set_list.count()):
        if "Current" not in dlg.set_list.item(row).text():
            dlg.set_list.setCurrentRow(row)
            break

    renamed = {}
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: ("Renamed Set", True)
    )
    monkeypatch.setattr(
        ctrl, "rename_installation_set",
        lambda old, new: renamed.update(old=old, new=new),
    )

    f2 = next(
        s for s in dlg.set_list.findChildren(QShortcut)
        if s.key().toString() == "F2"
    )
    assert f2.context() == Qt.ShortcutContext.WidgetShortcut
    f2.activated.emit()
    assert renamed["new"] == "Renamed Set"
