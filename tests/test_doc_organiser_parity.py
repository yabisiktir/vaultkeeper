"""Doc Organiser, as NIT does it (logic audit stage 3i).

NIT extracts archives found inside archives too (``BgProcessDocs`` extract loop),
naming each doc after the archive it came out of. Vaultkeeper read only the
outer archive's index, so a readme inside a .zip inside a .7z was never found.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.game.documentation import scan_mod_docs
from vaultkeeper.ui.controller import ProfileController

EXTRACTOR = FakeArchiveExtractor(
    contents={
        "big_pack_v2.7z": {"hak/pack.hak": b"HAK", "extras/docs_bundle.zip": b"ZIP"},
        "docs_bundle.zip": {"read_me.txt": b"README"},
        "plain.7z": {"notes.txt": b"NOTES"},
    }
)


def _mod(tmp_path: Path) -> Path:
    mod = tmp_path / "Profiles" / "P" / "Big Pack"
    downloads = mod / C.DOWNLOADS_DIR
    downloads.mkdir(parents=True)
    for name in ("big_pack_v2.7z", "plain.7z"):
        (downloads / name).write_bytes(b"x")
    return mod


def test_docs_inside_an_inner_archive_are_found(tmp_path: Path) -> None:
    mod = _mod(tmp_path)

    docs = {e.doc_name for e in scan_mod_docs("Big Pack", mod, extractor=EXTRACTOR)}

    # Named after the archive each came from, as NIT's qualifier is.
    assert docs == {"Docs Bundle Read Me.txt", "Plain Notes.txt"}


def test_an_inner_archive_doc_can_be_copied(tmp_path: Path) -> None:
    mod = _mod(tmp_path)
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Big Pack")
    c._extractor = EXTRACTOR
    report = c.doc_organiser_report(["Big Pack"])
    row = next(r for r in report["downloads"] if r["doc_name"] == "Docs Bundle Read Me.txt")
    selection = {"doc_name": row["doc_name"]}
    selection.update(
        {"archive": row["archive"], "inner": row["inner"]}
        if row.get("archive")
        else {"source": row["source_path"]}
    )

    result = c.copy_docs_to_mod("Big Pack", [selection])

    assert result["copied"] == 1
    assert (mod / "Docs Bundle Read Me.txt").read_bytes() == b"README"


def _window(qtbot, tmp_path: Path, monkeypatch):
    from vaultkeeper.ui.dialogs import doc_organiser
    from vaultkeeper.ui.main_window import MainWindow

    _mod(tmp_path)
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Big Pack")
    c._extractor = EXTRACTOR
    win = MainWindow(c)
    qtbot.addWidget(win)
    opened: list = []
    monkeypatch.setattr(
        doc_organiser.DocOrganiser,
        "show_for",
        classmethod(lambda cls, controller, names, parent=None: opened.append(names)),
    )
    return win, opened


def test_after_a_download_the_organiser_is_offered(qtbot, tmp_path: Path, monkeypatch) -> None:
    """VB ``IsRunDocOrganiser`` after Download Project / Update Downloads."""
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings

    win, opened = _window(qtbot, tmp_path, monkeypatch)
    asked = []

    def answer(box):
        asked.append(box.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", answer)
    win._offer_doc_organiser(["Big Pack"], "Big Pack downloaded")

    assert asked == ["Do you want to run the Documentation Organiser?"]
    assert opened == [["Big Pack"]]
    assert load_settings().run_doc_organiser == "yes"  # "Always" is ticked by default

    win._offer_doc_organiser(["Big Pack"], "Big Pack downloaded")
    assert len(asked) == 1 and len(opened) == 2  # remembered


def test_nothing_to_copy_means_no_question(qtbot, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    win, opened = _window(qtbot, tmp_path, monkeypatch)
    win.controller.create_mod("Empty")

    def fail(box):
        raise AssertionError("asked")

    monkeypatch.setattr(QMessageBox, "exec", fail)
    win._offer_doc_organiser(["Empty"], "Empty downloaded")
    assert opened == []
