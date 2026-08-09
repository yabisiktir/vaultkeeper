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
    # The index answers this, so a solid 7z is never decompressed to find a readme.
    assert extractor.extract_calls == []


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
    _write(root / "Alpha" / "ReadMe.txt", b"contents")
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"downloads")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    assert dlg.contents.topLevelItemCount() == 1
    assert dlg.contents.topLevelItem(0).text(0) == "ReadMe.txt"
    assert dlg.downloads.topLevelItemCount() == 1
    # The Downloads pane shows the qualified DocName (VB LvDocs), not the raw name.
    assert dlg.downloads.topLevelItem(0).text(0) == "Alpha Guide.pdf"
    assert "Downloaded documents detected: 1" in dlg.summary.text()


# -- DocInfo naming (VB DocInfo) ------------------------------------------ #


def _dl(entries, name):
    return next(e for e in entries if e.file_name == name)


def test_docname_qualifies_and_title_cases_loose_file(tmp_path):
    mod = tmp_path / "Cool Mod"
    _write(mod / C.DOWNLOADS_DIR / "readme_notes.txt")
    entries = scan_mod_docs("Cool Mod", mod)
    # Qualifier = mod name; stem title-cased ("_"→space); extension re-added.
    assert _dl(entries, "readme_notes.txt").doc_name == "Cool Mod Readme Notes.txt"


def test_docname_version_toggle(tmp_path):
    mod = tmp_path / "Mod"
    _write(mod / C.DOWNLOADS_DIR / "guide_v2.txt")

    keep = _dl(scan_mod_docs("Mod", mod, remove_version=False), "guide_v2.txt")
    assert keep.doc_name == "Mod Guide V2.txt"

    strip = _dl(scan_mod_docs("Mod", mod, remove_version=True), "guide_v2.txt")
    assert strip.doc_name == "Mod Guide.txt"


# -- CRC dedup + numbering (VB ProcessDocs) ------------------------------- #


def test_crc_match_marks_download_as_present(tmp_path):
    mod = tmp_path / "Mod"
    _write(mod / "ReadMe.txt", b"same-bytes")  # Contents
    _write(mod / C.DOWNLOADS_DIR / "readme.txt", b"same-bytes")  # identical CRC

    entries = scan_mod_docs("Mod", mod)
    dl = _dl(entries, "readme.txt")
    assert dl.copy is False  # already present -> not copied
    assert dl.name_match  # linked to the Contents match
    assert dl.doc_name == "ReadMe.txt"  # adopts the existing doc's name
    ct = _dl(entries, "ReadMe.txt")
    assert ct.name_match  # Contents doc linked back


def test_duplicate_docnames_are_numbered(tmp_path):
    mod = tmp_path / "Mod"
    # Two distinct docs that qualify to the same DocName ("Mod Readme.txt").
    _write(mod / C.DOWNLOADS_DIR / "a" / "readme.txt", b"one")
    _write(mod / C.DOWNLOADS_DIR / "b" / "readme.txt", b"two")

    entries = scan_mod_docs("Mod", mod)
    names = sorted(e.doc_name for e in entries if e.source == "Downloads")
    assert names == ["Mod Readme 1.txt", "Mod Readme 2.txt"]


# -- Copy action (VB BtCopy_Click) ---------------------------------------- #


def test_copy_docs_lands_under_docname_in_mod_root(tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()

    report = controller.doc_organiser_report(["Alpha"])
    row = report["downloads"][0]
    result = controller.copy_docs_to_mod(
        "Alpha", [{"source": row["source_path"], "doc_name": row["doc_name"]}]
    )
    assert result["copied"] == 1
    assert result["errors"] == 0
    # Copied into the mod ROOT (not .Mod Installer) under the qualified name.
    landed = root / "Alpha" / "Alpha Guide.pdf"
    assert landed.is_file()
    assert landed.read_bytes() == b"pdf"


def test_copy_docs_overwrites_and_errors_on_missing_source(tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"new")
    _write(root / "Alpha" / "Alpha Guide.pdf", b"old")  # pre-existing target
    controller._extractor = FakeArchiveExtractor()

    report = controller.doc_organiser_report(["Alpha"])
    src = report["downloads"][0]["source_path"]
    result = controller.copy_docs_to_mod(
        "Alpha",
        [
            {"source": src, "doc_name": "Alpha Guide.pdf"},  # overwrites
            {"source": str(tmp_path / "gone.txt"), "doc_name": "x.txt"},  # missing
        ],
    )
    assert result["copied"] == 1
    assert result["errors"] == 1
    assert (root / "Alpha" / "Alpha Guide.pdf").read_bytes() == b"new"


def test_copy_doc_from_archive_reextracts(tmp_path):
    """A doc inside a _Downloads archive is copied out by re-extraction."""
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "pack.7z", b"archive")
    controller._extractor = FakeArchiveExtractor(
        contents={"pack.7z": {"docs/ReadMe.txt": b"archived-doc-body"}}
    )

    report = controller.doc_organiser_report(["Alpha"])
    archive_rows = [r for r in report["downloads"] if r["from_archive"]]
    assert archive_rows, "the archived ReadMe should be reported"
    row = archive_rows[0]
    assert row["archive"] == "_Downloads/pack.7z"
    assert row["inner"].endswith("ReadMe.txt")

    result = controller.copy_docs_to_mod(
        "Alpha",
        [{"archive": row["archive"], "inner": row["inner"], "doc_name": row["doc_name"]}],
    )
    assert result["copied"] == 1
    copied = root / "Alpha" / row["doc_name"]
    assert copied.is_file() and copied.read_bytes() == b"archived-doc-body"


def test_archive_source_helper():
    from vaultkeeper.game.documentation import DocEntry, archive_source

    entry = DocEntry(
        mod="M", file_name="ReadMe.txt", source="Downloads",
        folder="pack.7z!docs", size=1, full_path=Path("/tmp/x"), from_archive=True,
    )
    assert archive_source(entry) == ("pack.7z", "docs/ReadMe.txt")
    # A loose file has no archive source.
    loose = DocEntry(
        mod="M", file_name="a.txt", source="Downloads", folder="", size=1,
        full_path=Path("/tmp/a"), from_archive=False,
    )
    assert archive_source(loose) is None


# -- Dialog copy behaviour ------------------------------------------------ #


def test_dialog_downloads_checkable_and_copy_button(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    from PySide6.QtCore import Qt

    item = dlg.downloads.topLevelItem(0)
    assert item.checkState(0) == Qt.CheckState.Checked  # default = copy
    assert dlg.copy_button.isEnabled()

    dlg._on_copy()

    # The file landed in the mod root, and on refresh the download is now a CRC
    # match (already present) -> disabled and unchecked.
    assert (root / "Alpha" / "Alpha Guide.pdf").is_file()
    assert dlg.contents.topLevelItemCount() == 1
    refreshed = dlg.downloads.topLevelItem(0)
    assert refreshed.checkState(0) == Qt.CheckState.Unchecked
    assert refreshed.isDisabled()
    assert not dlg.copy_button.isEnabled()


# -- Document preview (VB DisplayFile) ------------------------------------ #


def test_doc_preview_text_rtf_binary_and_missing(tmp_path):
    from vaultkeeper.core.rtf import write_rtf

    controller = _controller(tmp_path, "Alpha")

    txt = tmp_path / "readme.txt"
    txt.write_text("Hello docs", encoding="utf-8")
    assert controller.doc_preview(str(txt)) == {"kind": "text", "text": "Hello docs"}

    rtf = tmp_path / "notes.rtf"
    rtf.write_text(write_rtf(["Line one"]), encoding="utf-8")
    result = controller.doc_preview(str(rtf))
    assert result["kind"] == "text"
    assert "Line one" in result["text"]

    pdf = tmp_path / "guide.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert controller.doc_preview(str(pdf))["kind"] == "open_with"

    assert controller.doc_preview(str(tmp_path / "gone.txt"))["kind"] == "missing"


def test_dialog_selecting_doc_shows_preview(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "ReadMe.txt", b"the readme body")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)
    # The Contents pane auto-selects its first item -> preview shows its content.
    assert "the readme body" in dlg.preview.toPlainText()


def test_dialog_version_toggle_strips_version(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide_v2.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)
    assert dlg.downloads.topLevelItem(0).text(0) == "Alpha Guide V2.pdf"

    dlg.version_check.setChecked(True)  # VB CmVersion toggle
    assert dlg.downloads.topLevelItem(0).text(0) == "Alpha Guide.pdf"


def test_dialog_uncheck_all(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "a.txt", b"a")
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "b.txt", b"b")
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)
    assert dlg.copy_button.isEnabled()  # both checked by default

    dlg._on_uncheck_all()
    from PySide6.QtCore import Qt

    for i in range(dlg.downloads.topLevelItemCount()):
        assert dlg.downloads.topLevelItem(i).checkState(0) == Qt.CheckState.Unchecked
    assert not dlg.copy_button.isEnabled()


def test_dialog_matched_download_is_disabled(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "ReadMe.txt", b"dup")  # Contents
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "readme.txt", b"dup")  # identical
    controller._extractor = FakeArchiveExtractor()

    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    from PySide6.QtCore import Qt

    item = dlg.downloads.topLevelItem(0)
    assert item.isDisabled()
    assert item.checkState(0) == Qt.CheckState.Unchecked
    assert not dlg.copy_button.isEnabled()


# -- Rename / Rename To (VB CmRename / CmRenameTo) ------------------------- #


def test_dialog_rename_download_updates_target(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    item = dlg.downloads.topLevelItem(0)
    assert item.text(0) == "Alpha Guide.pdf"
    result = dlg._apply_rename(item, "Alpha Manual.pdf")
    assert result.ok
    assert item.text(0) == "Alpha Manual.pdf"
    assert item.data(0, Qt.ItemDataRole.UserRole)["doc_name"] == "Alpha Manual.pdf"
    assert item.checkState(0) == Qt.CheckState.Checked

    # A copy now lands under the renamed target.
    dlg._on_copy()
    assert (root / "Alpha" / "Alpha Manual.pdf").is_file()


def test_dialog_on_rename_prompts_and_applies(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)
    dlg.downloads.setCurrentItem(dlg.downloads.topLevelItem(0))

    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: ("Alpha Renamed.pdf", True)
    )
    dlg._on_rename()
    assert dlg.downloads.topLevelItem(0).text(0) == "Alpha Renamed.pdf"


def test_dialog_rename_rejects_wrong_extension(qtbot, tmp_path):
    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "guide.pdf", b"pdf")
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    item = dlg.downloads.topLevelItem(0)
    result = dlg._apply_rename(item, "Alpha Manual.txt")
    assert not result.ok
    assert 'must use ".pdf"' in result.message
    assert item.text(0) == "Alpha Guide.pdf"  # unchanged


def test_dialog_rename_to_offers_contents_names(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller = _controller(tmp_path, "Alpha")
    root = tmp_path / "Profiles" / "P"
    _write(root / "Alpha" / "Handbook.pdf", b"content-pdf")  # Contents doc
    _write(root / "Alpha" / C.DOWNLOADS_DIR / "extra.pdf", b"download-pdf")  # Download
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    item = dlg.downloads.topLevelItem(0)
    dlg.downloads.setCurrentItem(item)
    # Rename To offers the existing Contents doc name (VB suggests info.DocName).
    actions = [a.text() for a in dlg.rename_to_menu.actions()]
    assert "Handbook.pdf" in actions

    dlg._rename_to("Handbook.pdf")
    assert item.text(0) == "Handbook.pdf"
    assert item.checkState(0) == Qt.CheckState.Checked


# --------------------------------------------------------------------------- #
# Properties (VB CmProperties / TsProperties)
# --------------------------------------------------------------------------- #
def test_properties_describes_the_selected_document(qtbot, tmp_path, monkeypatch):
    """VB opens the Windows shell properties dialog; there is no portable one.

    So the facts are shown directly — which also lets it say what the shell
    could not: that a document came out of an archive, or already matches one
    in the mod.
    """
    from PySide6.QtWidgets import QMessageBox

    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.informativeText()))

    controller = _controller(tmp_path, "Alpha")
    _write(tmp_path / "Profiles" / "P" / "Alpha" / C.DOWNLOADS_DIR / "ReadMe.txt", b"hello")
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)

    dlg.downloads.setCurrentItem(dlg.downloads.topLevelItem(0))
    dlg._on_properties()

    assert shown, "the properties dialog was not shown"
    text = shown[0]
    assert "ReadMe.txt" in text
    assert "Alpha" in text
    assert "Size: 5 B" in text
    assert "_Downloads" in text  # where it came from


def test_properties_does_nothing_without_a_selection(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(1))
    controller = _controller(tmp_path, "Alpha")
    controller._extractor = FakeArchiveExtractor()
    dlg = DocOrganiser.show_for(controller, ["Alpha"])
    qtbot.addWidget(dlg)
    dlg._on_properties()
    assert shown == []


# --------------------------------------------------------------------------- #
# Archives are described from their index, not unpacked
# --------------------------------------------------------------------------- #
class _ListingExtractor:
    """An extractor that can list, and records whether anything was extracted."""

    available = True

    def __init__(self, entries):
        self._entries = entries
        self.extract_calls: list = []
        self.member_calls: list = []

    def list_entries(self, archive):
        return list(self._entries)

    def extract(self, archive, dest):
        self.extract_calls.append(archive)
        from vaultkeeper.core.archive import ExtractResult

        return ExtractResult(ok=False, dest=dest, exit_code=1, error="should not run")

    def extract_members(self, archive, dest, members):
        self.member_calls.append((archive, tuple(members)))
        from vaultkeeper.core.archive import ExtractResult

        return ExtractResult(ok=True, dest=dest, files=[], exit_code=0)


def test_an_archives_docs_come_from_its_index_without_unpacking(tmp_path):
    """The 20s → 0.04s fix: a listing carries path, size and CRC.

    On the owner's store this scan extracted 2 GB to find one readme, because a
    solid 7z still decompresses its block to yield a single 112-byte file.
    """
    mod = tmp_path / "Alpha"
    _write(mod / C.DOWNLOADS_DIR / "pack.7z", b"archive bytes")

    extractor = _ListingExtractor(
        [
            {"path": "Pack/readme.txt", "size": 112, "crc": 0xF9070A2E},
            {"path": "Pack/data/big.hak", "size": 9_000_000, "crc": 1},
        ]
    )
    entries = scan_mod_docs("Alpha", mod, extractor=extractor)

    assert extractor.extract_calls == [], "nothing may be unpacked to build the report"
    assert extractor.member_calls == [], "not even the doc member is needed"

    docs = [e for e in entries if e.from_archive]
    assert len(docs) == 1, "only the readme is documentation"
    doc = docs[0]
    assert doc.file_name == "readme.txt"
    assert doc.size == 112                 # from the index
    assert doc.checksum == 0xF9070A2E      # ditto, so CRC dedup still works
    assert doc.folder.startswith("_Downloads/pack.7z!")


def test_an_unlistable_archive_still_falls_back_to_extraction(tmp_path):
    # An odd format or an older backend must report its docs, not none.
    mod = tmp_path / "Alpha"
    _write(mod / C.DOWNLOADS_DIR / "pack.7z", b"archive bytes")

    class _NoListing(FakeArchiveExtractor):
        def list_entries(self, archive):
            return None

    extractor = _NoListing()
    scan_mod_docs("Alpha", mod, extractor=extractor)
    assert extractor.extract_calls, "the fallback must still extract"


def test_the_index_crc_still_dedupes_against_a_contents_doc(tmp_path):
    """A doc already copied into the mod must still be recognised.

    The CRC now comes from the archive index rather than from the extracted
    bytes; if the two disagreed, every archive doc would offer itself for
    copying again.
    """
    from vaultkeeper.core.crc import crc32_file

    mod = tmp_path / "Alpha"
    existing = mod / "readme.txt"
    _write(existing, b"the same bytes")
    _write(mod / C.DOWNLOADS_DIR / "pack.7z", b"archive bytes")

    extractor = _ListingExtractor(
        [{"path": "Pack/readme.txt", "size": 14, "crc": crc32_file(existing)}]
    )
    entries = scan_mod_docs("Alpha", mod, extractor=extractor)

    archived = next(e for e in entries if e.from_archive)
    assert archived.copy is False, "a CRC match must not offer to copy again"
    assert archived.name_match
