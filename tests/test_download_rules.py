"""Tests for the Vault download-rules parser and the scraper-info record."""

from __future__ import annotations

from vaultkeeper.vault.download_rules import DEFAULT_REMOVED_CHARS, DownloadRules
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo

_RULES = """\
' a comment line
SaveNameRemovedChars=()&-

GameSaveNameMap
From Sands of Fate 2 - Gem Tower
To SoF2
From Old Save
To New Mod
End GameSaveNameMap

PrefixFilenames
cep2_
prc8_
End PrefixFilenames

Extensions
.tmp
bak
End Extensions

NoInstallerProjects
Some Character Pack
End NoInstallerProjects

Redirects
From http://old.example/x
To http://new.example/x
End Redirects

UnsupportedProjects
This project cannot be auto-downloaded.
http://vault.example/unsupported
End UnsupportedProjects
"""


class TestParsing:
    def test_save_name_rules(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.save_name_rules["Sands of Fate 2 - Gem Tower"] == "SoF2"
        assert rules.save_name_rules["Old Save"] == "New Mod"

    def test_removed_chars_override(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.save_name_removed_chars == "()&-"

    def test_default_removed_chars(self):
        assert DownloadRules().save_name_removed_chars == DEFAULT_REMOVED_CHARS

    def test_prefix_filenames(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.prefix_filenames == ["cep2_", "prc8_"]
        assert rules.is_prefix_filename("CEP2_top.hak")
        assert not rules.is_prefix_filename("random.hak")

    def test_excluded_extensions(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.is_excluded_extension(".tmp")
        assert rules.is_excluded_extension("bak")
        assert rules.is_excluded_extension(".bak")  # with dot too
        assert not rules.is_excluded_extension(".hak")

    def test_redirects(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.redirects["http://old.example/x"] == "http://new.example/x"

    def test_no_installer_projects(self):
        rules = DownloadRules.from_text(_RULES)
        assert not rules.create_installer("Some Character Pack")
        assert rules.create_installer("A Real Adventure")

    def test_unsupported_split(self):
        rules = DownloadRules.from_text(_RULES)
        assert rules.is_unsupported("http://vault.example/unsupported")
        assert "This project cannot be auto-downloaded." in rules.message_lines

    def test_comments_and_blanks_ignored(self):
        rules = DownloadRules.from_text("' comment\n\n# hash\n; semi\n")
        assert rules.save_name_rules == {}

    def test_duplicate_from_keeps_first(self):
        text = "GameSaveNameMap\nFrom A\nTo First\nFrom A\nTo Second\nEnd GameSaveNameMap\n"
        assert DownloadRules.from_text(text).save_name_rules["A"] == "First"


class TestScraperInfo:
    def test_defaults(self):
        vsi = VaultScraperInfo(project_title="My Mod", filename="mod.zip")
        assert vsi.status is FileStatus.AVAILABLE
        assert vsi.status_text == "Available"

    def test_excluded_toggles_status(self):
        vsi = VaultScraperInfo()
        vsi.excluded = True
        assert vsi.status is FileStatus.EXCLUDED
        vsi.excluded = False
        assert vsi.status is FileStatus.AVAILABLE

    def test_clone_is_independent(self):
        vsi = VaultScraperInfo(project_title="A", byte_size=10)
        clone = vsi.clone()
        clone.byte_size = 20
        assert vsi.byte_size == 10


def test_rules_feed_game_mapper(tmp_path):
    # The download rules' save-name map is threaded into the play loop's GameMapper.
    from vaultkeeper.core.profile_data import ProfileData
    from vaultkeeper.ui.play_loop import PlayLoop

    (tmp_path / "Data").mkdir()
    rules = DownloadRules.from_text(
        "GameSaveNameMap\nFrom Raw Name\nTo Canonical\nEnd GameSaveNameMap\n"
    )
    loop = PlayLoop(
        ProfileData(),
        profile_mods_dir=tmp_path / "Profiles" / "P",
        data_dir=tmp_path / "Data",
        saves_dir=tmp_path / "saves",
        log_path=tmp_path / "log.txt",
        download_rules=rules,
    )
    assert loop.game_mapper.save_name_rules["Raw Name"] == "Canonical"
    assert loop.game_mapper.save_name_removed_chars == "()&"


class TestRulePreferences:
    """VB VaultDownloadRules "Apply rule preferences": each one off empties a table."""

    @staticmethod
    def _prefs(**off):
        from vaultkeeper.config.settings import Settings

        settings = Settings()
        for key, value in off.items():
            setattr(settings, key, value)
        return settings

    def test_everything_applies_by_default(self):
        rules = DownloadRules.from_text(_RULES).with_preferences(self._prefs())
        assert rules.get_final_url("http://old.example/x") == "http://new.example/x"
        assert rules.is_excluded_extension(".tmp")

    def test_one_preference_off_leaves_the_others(self):
        rules = DownloadRules.from_text(_RULES)
        no_redirects = rules.with_preferences(self._prefs(rules_redirects=False))
        assert no_redirects.get_final_url("http://old.example/x") == "http://old.example/x"
        assert no_redirects.is_excluded_extension(".tmp")
        assert rules.redirects, "the cached rules stay whole"

        no_extensions = rules.with_preferences(self._prefs(rules_exclude_extensions=False))
        assert not no_extensions.is_excluded_extension(".tmp")
        assert no_extensions.get_final_url("http://old.example/x") == "http://new.example/x"

    def test_the_master_switch_turns_every_rule_off(self):
        rules = DownloadRules.from_text(_RULES).with_preferences(
            self._prefs(rules_enabled=False)
        )
        assert rules.get_final_url("http://old.example/x") == "http://old.example/x"
        assert not rules.is_excluded_extension(".tmp")
        assert rules.projects == {}

    def test_project_files_off_keeps_folder_and_group(self):
        from vaultkeeper.vault.download_rules import ProjectRule

        rules = DownloadRules(
            projects={"x": ProjectRule(title="X", mod_folder="Xm", downloads=["a.zip"])}
        ).with_preferences(self._prefs(rules_project_files=False))
        assert rules.projects["x"].mod_folder == "Xm"
        assert rules.projects["x"].downloads == []
