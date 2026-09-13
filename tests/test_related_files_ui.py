"""Main-window wiring for related files and the uninstall safety prompts."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _window(qtbot, tmp_path: Path, *mods: ModData) -> MainWindow:
    pd = ProfileData()
    for mod in mods:
        pd.add_mod(mod)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    win = MainWindow(controller=controller)
    qtbot.addWidget(win)
    return win


def _doc_child(win: MainWindow):
    """The Contents-pane row for the mod's documentation file."""
    for i in range(win._contents.topLevelItemCount()):
        group = win._contents.topLevelItem(i)
        if group.text(0) == "Documentation":
            return group.child(0)
    return None


def test_contents_pane_lists_and_opens_documentation(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    (root).mkdir(parents=True)
    (root / "Walkthrough.pdf").write_text("map")

    win._on_selection_changed(["M"])

    doc_item = _doc_child(win)
    assert doc_item is not None
    assert doc_item.text(0) == "Walkthrough.pdf"

    # Selecting it exposes the real path (so Open/View can reach it).
    win._contents.setCurrentItem(doc_item)
    assert win._selected_contents_path() == root / "Walkthrough.pdf"

    # Its right-click menu is the read-only set — no Cut/Paste/Delete on a doc.
    menu = win._build_contents_menu()
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == ["View File", "Display Info", "Open\tCtrl+O", "Copy Name"]


def test_double_click_routes_by_kind(qtbot, tmp_path: Path, monkeypatch) -> None:
    """A related doc opens in its app; an installer file opens the in-app viewer."""
    win = _window(qtbot, tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    root.mkdir(parents=True)
    (root / "Walkthrough.pdf").write_text("map")
    win._on_selection_changed(["M"])

    calls: list[str] = []
    monkeypatch.setattr(win, "_on_open_with_default_app", lambda: calls.append("open"))
    monkeypatch.setattr(win, "_on_view_contents_file", lambda *a: calls.append("view"))

    # A documentation row -> open with the OS app.
    win._contents.setCurrentItem(_doc_child(win))
    win._on_contents_double_click()
    assert calls == ["open"]


def test_details_panel_shows_documentation_links(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    root.mkdir(parents=True)
    (root / "ReadMe.txt").write_text("hi")

    win._on_selection_changed(["M"])
    assert "ReadMe.txt" in win._mod_info.text()
    assert win._doc_paths  # a token -> path mapping was built
    token, path = next(iter(win._doc_paths.items()))
    assert Path(path) == root / "ReadMe.txt"


def _install(win: MainWindow, *names: str) -> None:
    """Force the given mods to the installed state (real install data is absent)."""
    for name in names:
        win.controller.pd.mod_item(name).mod_state = State.INSTALLED


def test_open_mod_folder_action_present_for_single_selection(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path, ModData(group="G", mod_name="M"))
    (tmp_path / "mods" / "M").mkdir(parents=True)
    win._select_mod_by_name("M")  # a real tree selection
    menu = win._build_mods_context_menu()
    assert any(a.text() == "Open Mod Folder" for a in menu.actions())


def test_confirm_uninstall_drops_declined_dependant(qtbot, tmp_path: Path, monkeypatch) -> None:
    base = ModData(group="G", mod_name="Base")
    base.files = [FileKeyInfo.mod_file("G", "Base", "hak\\b.hak")]
    dep = ModData(group="G", mod_name="Dep")
    dep.dependencies = ["Base"]
    win = _window(qtbot, tmp_path, base, dep)
    _install(win, "Base", "Dep")

    # A mod other installed mods need prompts; declining drops it.
    monkeypatch.setattr(win, "_confirm", lambda *a, **k: False)
    assert win._confirm_uninstall(["Base"]) == []

    # Accepting keeps it.
    monkeypatch.setattr(win, "_confirm", lambda *a, **k: True)
    assert win._confirm_uninstall(["Base"]) == ["Base"]


def test_confirm_uninstall_warns_on_campaign_modules(qtbot, tmp_path: Path, monkeypatch) -> None:
    ee = ModData(group="G", mod_name="EEMod")
    ee.files = [FileKeyInfo.mod_file("G", "EEMod", "mod\\camp.mod")]
    win = _window(qtbot, tmp_path, ee)
    _install(win, "EEMod")

    prompts: list[str] = []

    def record(_title: str, text: str) -> bool:
        prompts.append(text)
        return False

    monkeypatch.setattr(win, "_confirm", record)
    assert win._confirm_uninstall(["EEMod"]) == []
    assert any("Enhanced Edition" in p for p in prompts)


def test_confirm_uninstall_plain_mod_without_prompt(qtbot, tmp_path: Path, monkeypatch) -> None:
    plain = ModData(group="G", mod_name="Plain")
    plain.files = [FileKeyInfo.mod_file("G", "Plain", "hak\\a.hak")]
    win = _window(qtbot, tmp_path, plain)
    _install(win, "Plain")

    def fail(*_a, **_k):  # a plain mod raises no confirmation at all
        raise AssertionError("no prompt expected for a plain mod")

    monkeypatch.setattr(win, "_confirm", fail)
    assert win._confirm_uninstall(["Plain"]) == ["Plain"]


def test_downloads_group_lists_archives(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    (root / C.DOWNLOADS_DIR).mkdir(parents=True)
    (root / C.DOWNLOADS_DIR / "pack.zip").write_text("z")

    win._on_selection_changed(["M"])
    labels = [
        win._contents.topLevelItem(i).text(0)
        for i in range(win._contents.topLevelItemCount())
    ]
    assert C.DOWNLOADS_DIR in labels
