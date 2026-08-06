"""Guards for the bug class that only shows up on another operating system.

Every failure these describe was found the same way: the code ran green on macOS
for months, CI finally executed on Windows, and the assumption fell over. They
run on every platform, but they are written so the *macOS* run is what catches a
Windows regression — a guard that only fails on Windows is a guard that tells you
too late.

Two rules come out of it.

**Say which path flavour you mean.** ``pathlib.Path`` and ``PurePath`` mean "the
rules of whatever OS is running this", which is right for touching the local disk
and wrong for classifying a string whose convention you already know. Reading a
POSIX mount point, or an NWN file key that always uses backslashes, is a question
about the *string*, and the answer must not change with the machine asking it.
Use ``PurePosixPath``/``PureWindowsPath`` there.

**Say which encoding you mean.** ``read_text()`` and ``write_text()`` default to
the locale encoding, which is UTF-8 on macOS and Linux and cp1252 on Windows. A
source file or a mod name containing an em-dash then raises there and nowhere
else.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "vaultkeeper"
TESTS = Path(__file__).resolve().parent


def _python_files(*roots: Path) -> list[Path]:
    return sorted(p for root in roots for p in root.rglob("*.py"))


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
def _text_calls_without_encoding(tree: ast.AST) -> list[tuple[str, int]]:
    """``.read_text()``/``.write_text()`` calls that do not pin an encoding."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"read_text", "write_text"}:
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        found.append((node.func.attr, node.lineno))
    return found


def test_shipped_code_always_pins_a_text_encoding() -> None:
    # src only: test fixtures that write and read back their own ASCII are
    # self-consistent, but anything the user can put a character into, or any
    # file we did not author, has to say utf-8 or Windows decodes it as cp1252.
    offenders = [
        f"{p.relative_to(SRC)}:{line} ({call})"
        for p in _python_files(SRC)
        for call, line in _text_calls_without_encoding(ast.parse(p.read_text("utf-8")))
    ]
    assert not offenders, "pass encoding=\"utf-8\":\n  " + "\n  ".join(offenders)


def test_the_suite_reads_our_own_sources_as_utf8() -> None:
    # test_help_viewer scans every source file for help ids; it decoded them with
    # the locale codec and died on Windows at the first em-dash. Prove the corpus
    # really does contain bytes that cp1252 cannot handle, so this stays honest.
    non_ascii = [p for p in _python_files(SRC) if any(b > 127 for b in p.read_bytes())]
    assert non_ascii, "expected some sources to hold non-ASCII text"
    for p in non_ascii:
        p.read_text(encoding="utf-8")  # must not raise anywhere


# --------------------------------------------------------------------------- #
# Path flavour
# --------------------------------------------------------------------------- #
def test_posix_mount_detection_does_not_depend_on_the_host() -> None:
    # The original bug: is_network_path used PurePath, which is PureWindowsPath
    # on Windows, where the root part is "\\" and never "/" — so every /Volumes,
    # /mnt, /media and /net path was reported as local.
    from nwnfile.locations import is_network_path

    for shared in ("/Volumes/share/NWN", "/mnt/nas/NWN", "/media/x/NWN", "/net/h/NWN"):
        assert is_network_path(shared), shared
    for local in ("/Users/x/NWN", "/home/x/NWN", "/opt/nwn"):
        assert not is_network_path(local), local


def test_pureposixpath_is_what_makes_that_answer_stable() -> None:
    # Why the fix is the flavour and not the parsing: these two disagree about
    # the same string, and PurePath is an alias for whichever one the host uses.
    assert PurePosixPath("/mnt/nas").parts[0] == "/"
    assert PureWindowsPath("/mnt/nas").parts[0] == "\\"
    # And the case that makes "just normalise the separators" wrong: a backslash
    # is a legal character in a POSIX filename, so this really is two different
    # readings of one string rather than one of them being a mistake.
    assert len(PurePosixPath(r"override\o.2da").parts) == 1
    assert len(PureWindowsPath(r"override\o.2da").parts) == 2


@pytest.mark.parametrize("source", ["a.hak", "/mods/Alpha/a.hak", "C:/mods/a.hak"])
def test_mapper_maps_the_same_file_however_it_is_spelled(source: str) -> None:
    # The mapper does use the ambient PurePath, and there that is correct: every
    # caller hands it a real filesystem path or a bare filename, never one of the
    # backslash-joined file keys the profile stores. What has to hold on all
    # three platforms is that only the *name* decides the target folder.
    from vaultkeeper.core.mapper import Mapper

    assert Mapper().get_mapped_folder(source) == Mapper().get_mapped_folder("a.hak")


def test_mapper_would_be_wrong_if_handed_a_backslash_file_key() -> None:
    # Documents the boundary rather than a behaviour: a profile file key like
    # "hak\\a.hak" is one filename to POSIX and two components to Windows, so
    # feeding keys to the mapper would make it host-dependent. Callers must
    # split keys themselves (mapper.py does exactly that, on "\\" and "/").
    key = r"hak\a.hak"
    assert PurePosixPath(key).name == key           # POSIX sees no folder
    assert PureWindowsPath(key).name == "a.hak"     # Windows does
