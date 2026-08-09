"""Looking inside a compressed file without unpacking it (reducefileclutter.htm).

The topic tells you to keep archives compressed and then promises you can still
see what is in them. Before this, selecting a ``.zip`` in the Contents pane fell
through to the text viewer and showed its bytes.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.archive_contents import ArchiveContentsDialog

_PAYLOAD = {
    "readme.txt": b"hello",
    "hak/thing.hak": b"x" * 40,
    "tlk/words.tlk": b"y" * 12,
}


def _controller(tmp_path: Path) -> tuple[ProfileController, Path]:
    md = ModData(group="G", mod_name="M")
    pd = ProfileData()
    pd.add_mod(md)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    controller._extractor = FakeArchiveExtractor(contents={"pack.zip": _PAYLOAD})
    archive = tmp_path / "mods" / "M" / ".Mod Installer" / "download" / "pack.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"PK\x03\x04not-really")
    return controller, archive


def test_listing_reads_the_index_and_never_extracts(tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    entries = controller.archive_listing(archive)

    assert [e["path"] for e in entries] == ["hak/thing.hak", "readme.txt", "tlk/words.tlk"]
    assert [e["size"] for e in entries] == [40, 5, 12]
    # The whole point of the topic: large archives stay compressed.
    assert controller._extractor.extract_calls == []


def test_listing_says_where_each_file_would_install(tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    folders = {e["path"]: e["folder"] for e in controller.archive_listing(archive)}

    assert folders["hak/thing.hak"] == "hak"
    assert folders["tlk/words.tlk"] == "tlk"
    # A readme installs nowhere, and saying so is the useful answer.
    assert folders["readme.txt"] == ""


def test_listing_declines_what_is_not_an_archive(tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    plain = archive.with_name("notes.txt")
    plain.write_text("hello")

    assert controller.archive_listing(plain) is None
    assert controller.archive_listing(archive.with_name("missing.zip")) is None


def test_listing_survives_a_backend_that_cannot_read_it(tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(available=False)

    assert controller.archive_listing(archive) is None


def test_dialog_lists_members_and_filters_them(qtbot, tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    dlg = ArchiveContentsDialog.show_for(controller, archive)
    assert dlg is not None
    qtbot.addWidget(dlg)

    assert dlg.table.topLevelItemCount() == 3
    assert "3 file(s)" in dlg.summary.text()
    assert "57 bytes" in dlg.summary.text()  # 40 + 5 + 12

    dlg.filter.setText("hak")
    shown = [dlg.table.topLevelItem(i).text(0) for i in range(dlg.table.topLevelItemCount())]
    assert shown == ["hak/thing.hak"]
    assert "1 of 3" in dlg.summary.text()

    dlg.filter.setText("")
    assert dlg.table.topLevelItemCount() == 3
    assert "3 file(s)" in dlg.summary.text()


def test_dialog_declines_when_the_archive_cannot_be_read(qtbot, tmp_path: Path) -> None:
    controller, archive = _controller(tmp_path)
    controller._extractor = FakeArchiveExtractor(available=False)

    assert ArchiveContentsDialog.show_for(controller, archive) is None


def test_display_info_opens_the_listing_for_an_archive(qtbot, tmp_path: Path) -> None:
    """The regression this closes: a .zip used to open in the text viewer."""
    from vaultkeeper.core.file_key import FileKeyInfo
    from vaultkeeper.ui.main_window import MainWindow

    controller, archive = _controller(tmp_path)
    md = controller.pd.mod_item("M")
    md.files = [FileKeyInfo.mod_file("G", "M", "download\\pack.zip")]

    window = MainWindow(controller)
    qtbot.addWidget(window)
    window._contents_mod = "M"
    window._contents.populate(controller.mod_contents_report("M"))
    window._contents.select_file(("download", "pack.zip"))

    window._on_display_contents_info()
    dialog = getattr(window, "_archive_contents", None)
    assert isinstance(dialog, ArchiveContentsDialog)
    assert dialog.table.topLevelItemCount() == 3
    dialog.close()


# -- Ctrl+O: open with the associated program (keyboardshortcuts.htm) -------- #


def test_open_uses_the_systems_own_program(qtbot, tmp_path, monkeypatch):
    """"Ctrl+O — Opens the selected folder or file with its associated program."

    There was no such command at all, so a .doc walkthrough or a .pdf map could
    be listed and never read.
    """
    from PySide6.QtGui import QDesktopServices

    from vaultkeeper.core.file_key import FileKeyInfo
    from vaultkeeper.ui.main_window import MainWindow

    controller, archive = _controller(tmp_path)
    md = controller.pd.mod_item("M")
    md.files = [FileKeyInfo.mod_file("G", "M", "download\\pack.zip")]

    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True
    )

    window = MainWindow(controller)
    qtbot.addWidget(window)
    window._contents_mod = "M"
    window._contents.populate(controller.mod_contents_report("M"))

    window._contents.select_file(("download", "pack.zip"))
    window._on_open_with_default_app()
    assert opened == [str(archive)]

    # Nothing selected opens the mod's own folder — the "or folder" half.
    window._contents.clearSelection()
    window._contents.setCurrentItem(None)
    window._on_open_with_default_app()
    assert opened[-1] == str(controller.mod_folder("M"))


def test_open_is_bound_to_the_pane_not_the_window(qtbot, tmp_path):
    """Window-wide it would fire with a mod selected and nothing to open."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut

    from vaultkeeper.ui.main_window import MainWindow

    controller, _ = _controller(tmp_path)
    window = MainWindow(controller)
    qtbot.addWidget(window)

    shortcut = window._open_shortcut
    assert shortcut.key().toString() == "Ctrl+O"
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    assert shortcut.parent() is window._contents
    # And no *other* Ctrl+O crept in at window level.
    others = [
        s
        for s in window.findChildren(QShortcut)
        if s.key().toString() == "Ctrl+O" and s is not shortcut
    ]
    assert others == []


def test_open_says_so_when_there_is_nothing_to_open(qtbot, tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    controller, _ = _controller(tmp_path)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window._contents_mod = "Ghost"  # no such mod folder

    window._on_open_with_default_app()
    assert "nothing there to open" in window.nit_status.mg_info.text()
