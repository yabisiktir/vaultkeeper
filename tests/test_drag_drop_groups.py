"""Tests for FileView drag-to-group (move mods between groups)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.file_view import _ROLE_GROUP_NAME, FileView


class _FakeDropEvent:
    """Minimal stand-in for QDropEvent (position + accept/setDropAction)."""

    def __init__(self, point: QPoint) -> None:
        self._point = point
        self.accepted = False
        self.action = None

    def position(self) -> QPointF:
        return QPointF(self._point)

    def setDropAction(self, action) -> None:  # noqa: N802 (Qt API shape)
        self.action = action

    def accept(self) -> None:
        self.accepted = True


def test_fileview_items_carry_group(qtbot) -> None:
    view = FileView("Mods")
    qtbot.addWidget(view)
    a = ModData(group="Alpha", mod_name="A")
    b = ModData(group=C.GROUP_NONE, mod_name="B")  # hidden group -> top level
    view.populate([("Alpha", [a]), (C.GROUP_NONE, [b])])

    header = view.topLevelItem(0)
    assert header.data(0, _ROLE_GROUP_NAME) == "Alpha"
    assert header.child(0).data(0, _ROLE_GROUP_NAME) == "Alpha"
    # The No-Group mod is a top-level row carrying its group.
    top_b = view.topLevelItem(1)
    assert top_b.data(0, _ROLE_GROUP_NAME) == C.GROUP_NONE


def test_dropevent_emits_target_group(qtbot, monkeypatch) -> None:
    view = FileView("Mods")
    qtbot.addWidget(view)
    a = ModData(group="Alpha", mod_name="A")
    view.populate([("Alpha", [a]), ("Beta", [])])
    header_beta = view.topLevelItem(1)

    # Pretend the drop lands on the Beta header, with A selected.
    monkeypatch.setattr(view, "itemAt", lambda _pt: header_beta)
    monkeypatch.setattr(view, "selected_mod_names", lambda: ["A"])

    emitted: list = []
    view.mods_dropped_on_group.connect(lambda names, grp: emitted.append((names, grp)))
    event = _FakeDropEvent(QPoint(5, 5))
    view.dropEvent(event)

    assert emitted == [(["A"], "Beta")]
    assert event.accepted


def test_dropevent_empty_area_is_no_group(qtbot, monkeypatch) -> None:
    view = FileView("Mods")
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "itemAt", lambda _pt: None)
    monkeypatch.setattr(view, "selected_mod_names", lambda: ["A"])
    emitted: list = []
    view.mods_dropped_on_group.connect(lambda names, grp: emitted.append((names, grp)))
    view.dropEvent(_FakeDropEvent(QPoint(0, 0)))
    assert emitted == [(["A"], C.GROUP_NONE)]


def test_main_window_drop_moves_mod(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.main_window import MainWindow

    pd = ProfileData()
    pd.add_mod(ModData(group="Alpha", mod_name="A"))
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

    win._on_mods_dropped_on_group(["A"], "Beta")
    assert controller.pd.mod_item("A").group == "Beta"
    # Persisted.
    reloaded = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    assert reloaded.pd.mod_item("A").group == "Beta"
