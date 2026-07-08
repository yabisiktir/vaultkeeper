"""Tests for the Mod Documentation Organiser (domain scan + report + dialog).

Covers the bounded VB ``DocOrganiser`` slice: find documentation files in a mod's
root folder (Contents) and its ``_Downloads`` tree (Downloads, incl. archives via
the injected extractor), grounded on the VB doc-extension list. The copy action is
deferred, so these exercise the read-only report and the dialog population.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.core.archive import FakeArchiveExtractor  # noqa: E402
from vaultkeeper.game.documentation import (  # noqa: E402
    is_doc_file,
    scan_mod_docs,
)
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.doc_organiser import DocOrganiser  # noqa: E402


def _write(path: Path, data: bytes = b"doc") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# -- Doc predicate (VB TextFiles / ExcludeFiles) -------------------------- #


def test_is_doc_file_matches_doc_extensions():
    for name in ("ReadMe.txt", "guide.PDF", "notes.rtf", "index.html", "x.docx"):
        assert is_doc_file(name), name


def test_is_doc_file_rejects_non_docs_and_excluded():
    assert not is_doc_file("module.hak")
    assert not is_doc_file("portrait.tga")
    assert not is_doc_file("nwcontinst.exe")  # excluded
    assert not is_doc_file("manifest.txt")  # excluded despite .txt


# -- Domain scan ---------------------------------------------------------- #


def test_scan_finds_contents_and_downloads(tmp_path):
    mod = tmp_path / "Alpha"
    _write(mod / "ReadMe.txt")  # Contents
    _write(mod / "portrait.tga")  # not a doc
    _write(mod / C.PLAY_TIME_FILE)  # reserved .rtf — must be skipped
    _write(mod / C.DOWNLOADS_DIR / "Walkthrough.pdf")  # Downloads
    _write(mod / C.DOWNLOADS_DIR / "sub" / "hints.doc")  # nested Downloads
    _write(mod / C.DOWNLOADS_DIR / "big.hak")  # not a doc

    entries = scan_mod_docs("Alpha", mod)
    by_name = {e.file_name: e for e in entries}
    assert set(by_name) == {"ReadMe.txt", "Walkthrough.pdf", "hints.doc"}
    assert by_name["ReadMe.txt"].source == "Contents"
    assert by_name["ReadMe.txt"].folder == ""
    assert by_name["Walkthrough.pdf"].source == "Downloads"
    assert by_name["hints.doc"].folder == "_Downloads/sub"
    # Reserved play-time RTF is not mistaken for a document.
    assert C.PLAY_TIME_FILE not in by_name


def test_scan_missing_folder_is_empty(tmp_path):
    assert scan_mod_docs("Ghost", tmp_path / "nope") == []


def test_scan_extracts_docs_from_archives(tmp_path):
    mod = tmp_path / "Beta"
    _write(mod / C.DOWNLOADS_DIR / "pack.7z", b"archive")
    extractor = FakeArchiveExtractor(
        contents={"pack.7z": {"inside.txt": b"hi", "art.tga": b"x"}}
    )

    entries = scan_mod_docs("Beta", mod, extractor=extractor)
    names = {e.file_name for e in entries}
    assert names == {"inside.txt"}  # only the doc, not art.tga
    inside = next(e for e in entries if e.file_name == "inside.txt")
    assert inside.folder.startswith("_Downloads/pack.7z!")
    assert extractor.extract_calls  # the seam was used


def test_scan_without_extractor_skips_archives(tmp_path):
    mod = tmp_path / "Gamma"
    _write(mod / C.DOWNLOADS_DIR / "pack.7z", b"archive")
    assert scan_mod_docs("Gamma", mod, extractor=None) == []


# -- Controller report ---------------------------------------------------- #


def _controller(tmp_path: Path, *mods: str) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in mods:
        (profile_mods / name / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    game_root = tmp_path / "steamapps" / "common" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )


def test_report_scans_selected_mods(tmp_path):
    controller = _controller(tmp_path, "Alpha", "Beta")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "ReadMe.txt")
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf")
    _write(root / "Beta" / "manual.txt")
    controller._extractor = FakeArchiveExtractor()  # avoid real 7-Zip

    report = controller.doc_organiser_report(["Alpha"])
    assert report["mods"] == 1
    assert {r["file"] for r in report["contents"]} == {"ReadMe.txt"}
    assert {r["file"] for r in report["downloads"]} == {"guide.pdf"}
    assert "Downloaded documents detected: 1" in report["summary"]
    assert "Documents in Contents: 1" in report["summary"]
    # Beta was not selected, so its docs are absent.
    assert all(r["mod"] == "Alpha" for r in report["rows"])


def test_report_defaults_to_all_mods(tmp_path):
    controller = _controller(tmp_path, "Alpha", "Beta")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "a.txt")
    _write(root / "Beta" / "b.txt")
    controller._extractor = FakeArchiveExtractor()

    report = controller.doc_organiser_report()
    assert report["mods"] == 2
    assert {r["mod"] for r in report["rows"]} == {"Alpha", "Beta"}


def test_report_empty_when_no_docs(tmp_path):
    controller = _controller(tmp_path, "Alpha")
    controller._extractor = FakeArchiveExtractor()
    report = controller.doc_organiser_report(["Alpha"])
    assert report["rows"] == []
    assert report["summary"] == (
        "Scanned 1 mod. Downloaded documents detected: None. "
        "Documents in Contents: None."
    )


# -- Dialog --------------------------------------------------------------- #


def test_dialog_populates_both_panes(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "ReadMe.txt")
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    assert dlg.contents.topLevelItemCount() == 1
    assert dlg.contents.topLevelItem(0).text(0) == "ReadMe.txt"
    assert dlg.downloads.topLevelItemCount() == 1
    assert dlg.downloads.topLevelItem(0).text(0) == "guide.pdf"
    assert "Downloaded documents detected: 1" in dlg.summary.text()
