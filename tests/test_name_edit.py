"""Tests for reusable name validation + reserved-name rules (VB NameTextEditor/ValidateName)."""

from __future__ import annotations

from vaultkeeper.core import constants as C
from vaultkeeper.core.name_edit import validate_name
from vaultkeeper.core.reserved import is_reserved_name_or_prefix


def test_reserved_names_and_prefixes():
    assert is_reserved_name_or_prefix(C.DOWNLOADS_DIR)
    assert is_reserved_name_or_prefix(C.MOD_INSTALLER_DIR)
    assert is_reserved_name_or_prefix("_downloads")  # case-insensitive
    assert is_reserved_name_or_prefix("Some Restorers (Auto)")  # (Auto) suffix
    assert is_reserved_name_or_prefix(C.PLAY_TIME_FILE)  # prefix + name
    assert is_reserved_name_or_prefix(".Installer Wizard.nitwiz")
    assert is_reserved_name_or_prefix("799.  Mods Installed by NWN")  # group name
    assert not is_reserved_name_or_prefix("ReadMe.txt")
    assert not is_reserved_name_or_prefix("Walkthrough.pdf")


def test_validate_blank():
    assert validate_name("", initial="a.txt", existing=[]).message == (
        "You have not specified a Document name"
    )
    # name_type flows into the message.
    assert "Mod" in validate_name("", initial="a", existing=[], name_type="Mod").message


def test_validate_reserved():
    result = validate_name("_Downloads", initial="a.txt", existing=[])
    assert not result.ok
    assert result.message == '"_Downloads" is a reserved name'


def test_validate_unchanged_is_case_sensitive():
    # Exactly the same name -> rejected.
    assert not validate_name("ReadMe.txt", initial="ReadMe.txt", existing=[]).ok
    # Only the case changed -> that IS a change (VB CaseSensitive compare).
    assert validate_name("readme.txt", initial="ReadMe.txt", existing=[]).ok


def test_validate_extension_must_match():
    result = validate_name("readme.pdf", initial="readme.txt", existing=[])
    assert not result.ok
    assert result.message == '"readme.pdf" must use ".txt" as the extension'


def test_validate_duplicate_case_sensitive():
    existing = ["ReadMe.txt", "Guide.txt"]
    assert not validate_name("Guide.txt", initial="ReadMe.txt", existing=existing).ok
    # A different case does not clash (case-sensitive comparison).
    assert validate_name("guide.txt", initial="ReadMe.txt", existing=existing).ok


def test_validate_ok():
    assert validate_name("NewName.txt", initial="Old.txt", existing=["Old.txt"]).ok
