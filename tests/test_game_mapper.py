"""Tests for the GameMapper resolution ladder."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.game.game_mapper import (
    GameMapper,
    GameMapperContext,
    ModuleInfo,
    ResponseType,
    SaveNameInfo,
    UserResponses,
)


class FakeReader:
    """A ModuleInfoReader that returns canned info keyed by file name."""

    def __init__(self, mapping: dict[str, ModuleInfo] | None = None) -> None:
        self.mapping = mapping or {}

    def read(self, path: Path) -> ModuleInfo | None:
        return self.mapping.get(path.name)


class RecordingPrompter:
    """Prompter that records calls and returns pre-programmed answers."""

    def __init__(self, *, mod_choice: str = "", specify=(False, ""), profile_idx=0):
        self.mod_choice = mod_choice
        self.specify_answer = specify
        self.profile_idx = profile_idx
        self.choose_mod_calls: list[list[str]] = []
        self.specify_calls: list[str] = []

    def choose_mod(self, mod_list):
        self.choose_mod_calls.append(list(mod_list))
        return self.mod_choice or mod_list[0]

    def specify_mod_name(self, identifier, message):
        self.specify_calls.append(identifier)
        return self.specify_answer

    def choose_profile(self, message, options):
        return self.profile_idx


def _installed_mod(pd: ProfileData, group: str, name: str) -> None:
    pd.add_mod(ModData(group=group, mod_name=name, mod_state=State.INSTALLED))


def _install_module_file(
    pd: ProfileData, filename: str, conflicts: list[tuple[str, str]]
) -> None:
    """Register an installed module file with the given (group, mod_name) conflicts."""
    ik = FileKeyInfo.installed("modules", filename)
    installer = conflicts[0][1] if conflicts else "Unknown source"
    ifd = InstalledFileData(key=ik, installer=installer)
    for group, mod_name in conflicts:
        ifd.mod_file_conflicts.append(
            FileKeyInfo.mod_file(group, mod_name, f"modules\\{filename}")
        )
    pd.add_installed(ifd)


def _ctx(tmp_path: Path, active: str = "Profile A") -> GameMapperContext:
    return GameMapperContext(
        profiles_dir=tmp_path / "Profiles",
        active_profile=active,
        data_dir=tmp_path / "Data",
    )


def _mapper(pd, ctx, reader=None, prompter=None, **kw) -> GameMapper:
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    return GameMapper(
        pd, ctx,
        module_reader=reader or FakeReader(),
        prompter=prompter,
        auto_scan=False,
        **kw,
    )


class TestLogNameResolution:
    def test_single_installed_conflict_wins(self, tmp_path):
        pd = ProfileData()
        _installed_mod(pd, "Adventures", "My Mod")
        _install_module_file(pd, "mymod.mod", [("Adventures", "My Mod")])
        gm = _mapper(pd, _ctx(tmp_path))
        assert gm.log_name_to_mod_name("mymod") == "My Mod"

    def test_nwm_fallback_when_no_mod(self, tmp_path):
        pd = ProfileData()
        _installed_mod(pd, "Campaign", "Premium Mod")
        _install_module_file(pd, "premium.nwm", [("Campaign", "Premium Mod")])
        gm = _mapper(pd, _ctx(tmp_path))
        assert gm.log_name_to_mod_name("premium") == "Premium Mod"

    def test_patch_conflict_excluded(self, tmp_path):
        pd = ProfileData()
        _installed_mod(pd, "Adventures", "My Mod")
        _installed_mod(pd, "Patches", "Community Patch")
        _install_module_file(
            pd, "mymod.mod",
            [("Adventures", "My Mod"), ("Patches", "Community Patch")],
        )
        gm = _mapper(pd, _ctx(tmp_path))
        # "Community Patch" is filtered out by is_not_patch, leaving one winner.
        assert gm.log_name_to_mod_name("mymod") == "My Mod"

    def test_multiple_non_patch_asks_user_and_remembers(self, tmp_path):
        pd = ProfileData()
        _installed_mod(pd, "A", "Mod One")
        _installed_mod(pd, "B", "Mod Two")
        _install_module_file(pd, "shared.mod", [("A", "Mod One"), ("B", "Mod Two")])
        prompter = RecordingPrompter(mod_choice="Mod Two")
        gm = _mapper(pd, _ctx(tmp_path), prompter=prompter)
        assert gm.log_name_to_mod_name("shared") == "Mod Two"
        assert prompter.choose_mod_calls == [["Mod One", "Mod Two"]]
        # A second call reuses the remembered choice, no new prompt.
        assert gm.log_name_to_mod_name("shared") == "Mod Two"
        assert len(prompter.choose_mod_calls) == 1

    def test_unknown_log_name_cancel_uses_log_name(self, tmp_path):
        pd = ProfileData()
        prompter = RecordingPrompter(specify=(False, ""))
        gm = _mapper(pd, _ctx(tmp_path), prompter=prompter)
        assert gm.log_name_to_mod_name("orphan") == "orphan"
        assert gm.user_choices.log_to_mod_names["orphan"] == "orphan"

    def test_unknown_log_name_typed_is_remembered(self, tmp_path):
        pd = ProfileData()
        prompter = RecordingPrompter(specify=(True, "Typed Name"))
        gm = _mapper(pd, _ctx(tmp_path), prompter=prompter)
        assert gm.log_name_to_mod_name("orphan") == "Typed Name"
        # Remembered: a second call does not prompt again.
        assert gm.log_name_to_mod_name("orphan") == "Typed Name"
        assert len(prompter.specify_calls) == 1


class TestScanAndSaveName:
    def _make_profile_tree(self, tmp_path: Path, profile: str, mod: str, filename: str):
        modules = (
            tmp_path / "Profiles" / profile / mod / ".Mod Installer" / "modules"
        )
        modules.mkdir(parents=True)
        (modules / filename).write_bytes(b"\x00")
        return modules / filename

    def test_scan_builds_save_names(self, tmp_path):
        self._make_profile_tree(tmp_path, "Profile A", "My Adventure", "adv.mod")
        pd = ProfileData()
        _installed_mod(pd, "Adventures", "My Adventure")
        reader = FakeReader({"adv.mod": ModuleInfo("Beorunna", "An epic", "adv.mod")})
        gm = _mapper(pd, _ctx(tmp_path), reader=reader)
        gm.refresh(force=True)
        assert gm.is_save_name("Beorunna")
        assert gm.save_name_to_mod_name("Beorunna") == "My Adventure"

    def test_scan_demo_uses_module_filename(self, tmp_path):
        self._make_profile_tree(tmp_path, "Profile A", "Demo Mod", "demo.mod")
        pd = ProfileData()
        reader = FakeReader({"demo.mod": ModuleInfo("_DEMO", "d", "demo.mod")})
        gm = _mapper(pd, _ctx(tmp_path), reader=reader)
        gm.refresh(force=True)
        # _DEMO save name is replaced with the module filename stem.
        assert gm.is_save_name("demo")

    def test_full_campaign_is_not_ignored(self, tmp_path):
        modules = (
            tmp_path / "Profiles" / "Profile A" / "Original" / ".Mod Installer" / "modules"
        )
        modules.mkdir(parents=True)
        # A complete original campaign (all siblings present) is a real install.
        for name in [
            "Chapter1.nwm", "Chapter1E.nwm", "Chapter2.nwm", "Chapter2E.nwm",
            "Chapter3.nwm", "Chapter4.nwm", "Prelude.nwm",
        ]:
            (modules / name).write_bytes(b"\x00")
        gm = _mapper(ProfileData(), _ctx(tmp_path))
        assert gm.ignore_mod_file(modules / "Chapter2.nwm") is False

    def test_partial_campaign_patch_is_ignored(self, tmp_path):
        # A CPP-style partial set (a campaign file with siblings MISSING) is ignored.
        modules = (
            tmp_path / "Profiles" / "Profile A" / "CPP" / ".Mod Installer" / "modules"
        )
        modules.mkdir(parents=True)
        (modules / "Chapter2.nwm").write_bytes(b"\x00")  # siblings absent
        gm = _mapper(ProfileData(), _ctx(tmp_path))
        assert gm.ignore_mod_file(modules / "Chapter2.nwm") is True

    def test_non_campaign_file_is_not_ignored(self, tmp_path):
        modules = tmp_path / "m"
        modules.mkdir()
        (modules / "myadventure.mod").write_bytes(b"\x00")
        gm = _mapper(ProfileData(), _ctx(tmp_path))
        assert gm.ignore_mod_file(modules / "myadventure.mod") is False

    def test_unknown_save_name_cancel_uses_save_name(self, tmp_path):
        pd = ProfileData()
        prompter = RecordingPrompter(specify=(False, ""))
        gm = _mapper(pd, _ctx(tmp_path), prompter=prompter)
        assert gm.save_name_to_mod_name("Mystery") == "Mystery"
        assert gm.user_choices.sav_to_mod_names["Mystery"] == "Mystery"

    def test_blank_and_no_saves_pass_through(self, tmp_path):
        gm = _mapper(ProfileData(), _ctx(tmp_path))
        assert gm.save_name_to_mod_name("") == ""
        assert gm.save_name_to_mod_name("No games have been saved") == (
            "No games have been saved"
        )


class TestMapEntries:
    def test_trailing_dots_and_removed_chars(self, tmp_path):
        pd = ProfileData()
        gm = _mapper(pd, _ctx(tmp_path), save_name_removed_chars=":")
        gm.save_names = {"My: Save.": SaveNameInfo()}
        gm.create_map_entries()
        # "My: Save." -> strip trailing dot, remove ":" -> "My Save" maps back.
        assert gm.save_name_map.get("My Save") == "My: Save."


class TestPredicates:
    def test_is_mod_name_via_profile_db(self, tmp_path):
        pd = ProfileData()
        _installed_mod(pd, "A", "Known Mod")
        gm = _mapper(pd, _ctx(tmp_path))
        assert gm.is_mod_name("Known Mod")
        assert not gm.is_mod_name("Nope")


class TestRenameAndPersistence:
    def test_rename_mod_rewrites_cache(self, tmp_path):
        tree = (
            tmp_path / "Profiles" / "Profile A" / "Old Name" / ".Mod Installer" / "modules"
        )
        tree.mkdir(parents=True)
        (tree / "adv.mod").write_bytes(b"\x00")
        pd = ProfileData()
        reader = FakeReader({"adv.mod": ModuleInfo("Beorunna", "d", "adv.mod")})
        gm = _mapper(pd, _ctx(tmp_path), reader=reader)
        gm.refresh(force=True)
        gm.rename_mod("Old Name", "New Name")
        mfi = next(iter(gm.save_names["Beorunna"].mod_files.values()))
        assert mfi.mod_name == "New Name"
        assert "New Name" in next(iter(gm.save_names["Beorunna"].mod_files.keys()))

    def test_user_choices_round_trip(self, tmp_path):
        pd = ProfileData()
        prompter = RecordingPrompter(specify=(True, "Chosen"))
        ctx = _ctx(tmp_path)
        gm = _mapper(pd, ctx, prompter=prompter)
        gm.save_name_to_mod_name("SaveX")  # remembers SaveX -> Chosen
        # A fresh mapper loads the persisted choices and resolves without prompting.
        gm2 = _mapper(pd, ctx, prompter=RecordingPrompter(specify=(False, "")))
        assert gm2.save_name_to_mod_name("SaveX") == "Chosen"


class TestUserResponses:
    def test_rename_mod_updates_all_tables(self):
        ur = UserResponses()
        ur.add("log1", "Old", ResponseType.LOG)
        ur.add("sav1", "Old", ResponseType.SAV)
        ur.add("prof1", "Old", ResponseType.PROFILE)
        ur.add_choice("Old")
        assert ur.rename_mod("Old", "New")
        assert ur.log_to_mod_names["log1"] == "New"
        assert ur.sav_to_mod_names["sav1"] == "New"
        assert ur.profile_choices["prof1"] == "New"
        assert "New" in ur.mod_choices
