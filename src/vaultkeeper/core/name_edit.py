"""Name-editor validation (VB ``NameTextEditor`` / ``ValidateName``).

The original tool renames mods, files and documents through a shared *Name Text
Editor* whose caller supplies a ``ValidateName`` callback. :func:`validate_name` is
the reusable, headless port of that rule set (as used by ``DocOrganiser.ValidateName``,
DocOrganiser.vb:533): a new name must be non-blank, not reserved, actually changed,
keep the original extension, and not clash with an existing name.

Name comparisons are **case-sensitive** (VB ``String.Compare(…, CaseSensitive)``), so
changing only the letter case counts as a real change; the extension comparison is
case-insensitive (NWN extensions are lower-case).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from vaultkeeper.core.reserved import is_reserved_name_or_prefix


@dataclass
class NameValidation:
    """Result of validating a proposed name (VB ``NameTextEditor`` status)."""

    ok: bool
    message: str = ""


def _extension(name: str) -> str:
    """Extension including the dot, lower-cased (VB ``GetExtension``; ``""`` if none)."""
    return PurePosixPath(name.replace("\\", "/")).suffix.lower()


def validate_name(
    name: str,
    *,
    initial: str,
    existing: Iterable[str],
    name_type: str = "Document",
) -> NameValidation:
    """Validate a proposed new name (VB ``ValidateName``, DocOrganiser.vb:533).

    ``initial`` is the name being edited (must change and its extension preserved);
    ``existing`` is every current name in the list (a case-sensitive clash is rejected).
    Returns :class:`NameValidation` with the exact VB status message on failure.
    """
    if name == "":
        return NameValidation(False, f"You have not specified a {name_type} name")
    if is_reserved_name_or_prefix(name):
        return NameValidation(False, f'"{name}" is a reserved name')
    if name == initial:  # case-sensitive: only a real change is allowed
        return NameValidation(False, f'"{name}" has not been changed')
    if _extension(name) != _extension(initial):
        return NameValidation(
            False,
            f'"{name}" must use "{_extension(initial)}" as the extension',
        )
    if any(name == other for other in existing):  # case-sensitive clash
        return NameValidation(False, f'"{name}" already exists')
    return NameValidation(True)
