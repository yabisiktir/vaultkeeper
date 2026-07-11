"""Tests for the state-aware Contents pane (VB FvContents)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.file_view import ContentsView, file_state_brush


def _controller(tmp_path: Path, mod: ModData) -> ProfileController:
    pd = ProfileData()
    pd.add_mod(mod)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )


def test_mod_contents_report_groups_and_states(tmp_path: Path) -> None:
    md = ModData(group="G", mod_name="M")
    md.files = [
        FileKeyInfo.mod_file("G", "M", "hak\\b.hak"),
        FileKeyInfo.mod_file("G", "M", "hak\\a.hak"),
        FileKeyInfo.mod_file("G", "M", "tlk\\c.tlk"),
    ]
    controller = _controller(tmp_path, md)
    # Give two files a known state via FileList.
    from vaultkeeper.core.file_data import FileData

    for fk in md.files:
        controller.pd.file_list[fk] = FileData(
            key=fk, file_state=State.NOT_INSTALLED, extension=fk.extension,
            modified=None, byte_size=10,
        )
    controller.pd.file_list[md.files[1]].file_state = State.INSTALLED  # hak/a.hak

    report = controller.mod_contents_report("M")
    assert report["count"] == 3
    assert report["installed"] == 1
    # Folders natural-sorted: hak before tlk; files sorted within.
    assert [g["folder"] for g in report["folders"]] == ["hak", "tlk"]
    hak_files = [f["name"] for f in report["folders"][0]["files"]]
    assert hak_files == ["a.hak", "b.hak"]
    assert report["folders"][0]["files"][0]["state"] == State.INSTALLED


def test_mod_contents_report_missing_mod(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    report = controller.mod_contents_report("does-not-exist")
    assert report == {"folders": [], "count": 0, "installed": 0}


def test_file_state_brush() -> None:
    assert file_state_brush(State.INSTALLED) is not None
    assert file_state_brush(State.MATCH_OVERRIDE) is not None
    assert file_state_brush(State.OVERRIDDEN) is not None
    assert file_state_brush(State.NOT_INSTALLED) is None
    assert file_state_brush(State.UNKNOWN) is None


def test_contents_view_populate(qtbot) -> None:
    view = ContentsView()
    qtbot.addWidget(view)
    report = {
        "folders": [
            {
                "folder": "hak",
                "files": [
                    {"name": "a.hak", "state": State.INSTALLED, "size": 10, "size_text": "10 B"},
                    {
                        "name": "b.hak",
                        "state": State.NOT_INSTALLED,
                        "size": 20,
                        "size_text": "20 B",
                    },
                ],
            }
        ],
        "count": 2,
        "installed": 1,
    }
    view.populate(report)
    assert view.topLevelItemCount() == 1
    folder = view.topLevelItem(0)
    assert folder.text(0) == "hak"
    assert folder.childCount() == 2
    assert folder.child(0).text(0) == "a.hak"
    assert folder.child(0).text(1) == "10 B"
