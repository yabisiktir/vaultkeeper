

def test_user_rules_are_added_to_the_published_ones(tmp_path):
    # VB VaultDownloadRules.ReadFile appends "User Rules.txt" (comments dropped).
    from vaultkeeper.vault import rules_source

    base = rules_source.load_rules(tmp_path)
    assert base.create_installer("My Private Project") is True
    path = rules_source.ensure_user_rules_file(tmp_path)
    assert path.read_text().startswith("'")
    assert rules_source.user_rules_text(tmp_path) == ""
    path.write_text(path.read_text() + "NoInstallerProjects\nMy Private Project\n")

    rules = rules_source.load_rules(tmp_path)

    assert rules.create_installer("My Private Project") is False
