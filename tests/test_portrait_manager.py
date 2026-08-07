"""Portrait Manager — the control set the original tool documents (VB PortraitManager).

The port had drifted a long way from the shipped help topic: no Previous/Next, no
Find Portrait, no Options menu, no context menu, no size report — and a ``Remove``
button that deleted the files, where the original marks a portrait and then writes
the mark into the mod's installer wizard, which the Wizard Builder can undo.

These cover the restored behaviour, and in particular that excluding never
deletes.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt

from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager


def _controller(portraits, *, settings=None, **overrides):
    """A stand-in controller. ``overrides`` replace individual methods."""
    calls: dict[str, list] = {"exclude": [], "installer": []}

    def report(*, include_override=False):
        rows = [p for p in portraits if include_override or p["folder"] == "portraits"]
        return {"portraits": rows, "count": len(rows)}

    def exclude(mod, resrefs):
        calls["exclude"].append((mod, sorted(resrefs)))
        return {"ok": True, "excluded": len(resrefs), "message": f"Excluded from {mod}."}

    def create_installer(mod):
        calls["installer"].append(mod)
        return True

    controller = SimpleNamespace(
        installed_portraits_report=report,
        exclude_portraits_from_installer=exclude,
        create_installer=create_installer,
        invalid_portrait_sizes=lambda *, include_override=False: {
            "invalid": [],
            "checked": 0,
        },
        settings=settings
        or SimpleNamespace(
            portrait_include_override=False,
            portrait_always_select_next=True,
            tga_editor_path="",
            portrait_image_web_page="",
        ),
        save_settings=lambda: None,
        calls=calls,
    )
    for name, value in overrides.items():
        setattr(controller, name, value)
    return controller


def _portraits():
    return [
        {"resref": "po_hero", "mod": "Heroes Pack", "group": "C", "folder": "portraits",
         "sizes": {}},
        {"resref": "po_villain", "mod": "Heroes Pack", "group": "C", "folder": "portraits",
         "sizes": {}},
        {"resref": "po_king", "mod": "Royal Set", "group": "C", "folder": "portraits",
         "sizes": {}},
        {"resref": "po_loose", "mod": "Unknown source", "group": "", "folder": "override",
         "sizes": {}},
    ]


def test_lists_installed_portraits_with_mod(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    # The override entry is hidden until the option asks for it.
    assert dlg._tree.topLevelItemCount() == 3
    row0 = dlg._tree.topLevelItem(0)
    assert "po_hero" in row0.text(0)
    assert row0.text(2) == "Heroes Pack"


def test_the_name_column_is_wide_enough_to_tell_rows_apart(qtbot):
    # What the bug looked like: names differ only near their ends, so a
    # default-width column rendered a screenful of identical "AdreannaMA…" rows.
    names = [f"AdreannaMage{n:02d}" for n in range(1, 6)]
    rows = [
        {"resref": n, "mod": "Portraits", "group": "", "folder": "portraits", "sizes": {}}
        for n in names
    ]
    dlg = PortraitManager(_controller(rows))
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)

    metrics = dlg._tree.fontMetrics()
    widest = max(metrics.horizontalAdvance(n) for n in names)
    assert dlg._tree.columnWidth(0) >= widest, "the portrait name column truncates"


def test_unknown_source_is_explained_rather_than_just_shown(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg._override_action.setChecked(True)  # bring the loose override portrait in
    index = next(
        i for i in range(dlg._tree.topLevelItemCount())
        if dlg._tree.topLevelItem(i).text(0).startswith("po_loose")
    )
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(index))
    assert "no mod in this profile installed it" in dlg._caption.text()
    # Nothing that needs an owning mod may be offered for it.
    assert not dlg._exclude_button.isEnabled()
    assert not dlg._installer_button.isEnabled()


def test_select_invokes_callback_with_mod(qtbot):
    selected = []
    dlg = PortraitManager(_controller(_portraits()), on_select=selected.append)
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(2))  # po_king / Royal Set
    dlg._on_select_mod()
    assert selected == ["Royal Set"]
    assert not dlg.isVisible()


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
def test_previous_and_next_walk_the_list_and_stop_at_the_ends(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    assert dlg._index() == 0
    assert not dlg._prev_button.isEnabled()  # already at the top

    dlg._move(1)
    assert dlg._index() == 1
    dlg._move(-1)
    assert dlg._index() == 0

    dlg._move(-1)  # off the top: stays put rather than wrapping
    assert dlg._index() == 0

    for _ in range(10):
        dlg._move(1)
    assert dlg._index() == dlg._tree.topLevelItemCount() - 1
    assert not dlg._next_button.isEnabled()


def test_find_selects_a_portrait_by_name(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg._find.setText("king")
    assert dlg._current()["resref"] == "po_king"
    # Unmatched text leaves the selection alone rather than clearing it.
    dlg._find.setText("nothing-matches-this")
    assert dlg._current()["resref"] == "po_king"


def test_find_wraps_so_enter_walks_the_matches(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg._on_find("po_")           # from the top: first match
    first = dlg._current()["resref"]
    dlg._on_find("po_", step=1)   # Enter: the one after it
    assert dlg._current()["resref"] != first


# --------------------------------------------------------------------------- #
# Excluding — the part that must never delete
# --------------------------------------------------------------------------- #
def test_excluding_only_marks_until_apply(qtbot):
    controller = _controller(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_exclude()

    assert dlg._pending == {"po_hero"}
    assert controller.calls["exclude"] == [], "nothing may be written before Apply"
    assert dlg._apply_button.isEnabled()
    assert "✗" in dlg._tree.topLevelItem(0).text(0)


def test_excluding_selects_the_next_when_asked_to(qtbot):
    controller = _controller(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._move(1)          # travelling forwards
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_exclude()
    assert dlg._index() == 1

    controller.settings.portrait_always_select_next = False
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_exclude()
    assert dlg._index() == 0, "selection must stay put when the option is off"


def test_undo_takes_a_mark_back(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_exclude()
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    dlg._on_undo_exclude()
    assert dlg._pending == set()
    assert not dlg._apply_button.isEnabled()


def test_apply_groups_the_marks_by_mod(qtbot, monkeypatch):
    from vaultkeeper.ui.dialogs import portrait_manager as pm

    monkeypatch.setattr(
        pm.QMessageBox, "question", lambda *a, **k: pm.QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(pm.QMessageBox, "information", lambda *a, **k: None)

    controller = _controller(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    for index in (0, 1, 2):  # two from Heroes Pack, one from Royal Set
        dlg._tree.setCurrentItem(dlg._tree.topLevelItem(index))
        dlg._pending.add(dlg._current()["resref"])
    dlg._on_apply_excludes()

    assert controller.calls["exclude"] == [
        ("Heroes Pack", ["po_hero", "po_villain"]),
        ("Royal Set", ["po_king"]),
    ]
    assert dlg._pending == set(), "marks are cleared once written"


def test_apply_does_nothing_when_the_confirmation_is_declined(qtbot, monkeypatch):
    from vaultkeeper.ui.dialogs import portrait_manager as pm

    monkeypatch.setattr(
        pm.QMessageBox, "question", lambda *a, **k: pm.QMessageBox.StandardButton.No
    )
    controller = _controller(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    dlg._pending.add("po_hero")
    dlg._on_apply_excludes()
    assert controller.calls["exclude"] == []
    assert dlg._pending == {"po_hero"}


def test_there_is_no_button_that_deletes_portrait_files(qtbot):
    # The regression this whole file exists for: a "Remove" action used to
    # unlink() the files. Excluding is reversible through the Wizard Builder;
    # deleting is not, and the two must not be confused again.
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    assert not hasattr(dlg, "_on_remove")
    assert not hasattr(dlg, "_remove_button")


# --------------------------------------------------------------------------- #
# Options, context menu, image strip
# --------------------------------------------------------------------------- #
def test_the_override_option_widens_the_list_and_is_remembered(qtbot):
    controller = _controller(_portraits())
    dlg = PortraitManager(controller)
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 3

    dlg._override_action.setChecked(True)
    assert dlg._tree.topLevelItemCount() == 4
    assert controller.settings.portrait_include_override is True


def test_actions_needing_a_configured_path_stay_hidden(qtbot):
    """VB shows neither until a TGA editor / web page is configured.

    Shown, not merely constructed: an unshown dialog hides its children anyway,
    so the earlier version of this test passed while the buttons appeared on
    screen. A QToolBar owns the widget through a QWidgetAction and re-shows it
    with that action, so hiding the widget alone does not survive show() — which
    it did not, on Windows.
    """
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)

    # Hidden is asserted on the widget *and* the action: the widget is what the
    # user sees, and the action is what the fix drives.
    assert not dlg._edit_button.isVisible()
    assert not dlg._link_button.isVisible()
    assert not dlg._toolbar_actions["_edit_button"].isVisible()
    assert not dlg._toolbar_actions["_link_button"].isVisible()

    dlg._settings.tga_editor_path = "/usr/bin/gimp"
    dlg._settings.portrait_image_web_page = "https://example.invalid"
    dlg._refresh_actions()

    # Shown is asserted on the action only. Whether a ribbon entry then fits on
    # screen is layout: on a narrower toolbar Qt moves the last entries into the
    # overflow menu, where the widget reports itself invisible while still being
    # perfectly available. That happens on Windows, whose UI font is wider.
    assert dlg._toolbar_actions["_edit_button"].isVisible()
    assert dlg._toolbar_actions["_link_button"].isVisible()


def test_the_image_strip_zones_navigate_and_the_middle_does_not(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(1))

    assert dlg._zone(5) == -1                       # left edge: back
    assert dlg._zone(dlg._strip.width() - 5) == 1   # right edge: forward
    assert dlg._zone(dlg._strip.width() / 2) == 0   # middle: edit, not navigate

    # At the ends the edge stops offering a move there is nowhere to make.
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))
    assert dlg._zone(5) == 0
    assert dlg._zone_cursor(5) == Qt.CursorShape.ArrowCursor


def test_the_context_menu_offers_the_same_actions(qtbot):
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    # Built from the toolbar buttons, as VB builds it from the ribbon ones.
    for button in (dlg._exclude_button, dlg._apply_button, dlg._select_button):
        assert button is not None
    assert dlg._options_button.menu() is not None
    assert [a.text() for a in dlg._options_button.menu().actions() if a.text()] == [
        "Include Portraits in Override and Ovr",
        "Always Select Next Portrait",
        "Invalid Portrait Size Report",
    ]


def test_the_size_report_says_so_when_everything_is_valid(qtbot, monkeypatch):
    from vaultkeeper.ui.dialogs import portrait_manager as pm

    shown = []
    monkeypatch.setattr(
        pm.QMessageBox, "information", lambda _p, _t, text, *a, **k: shown.append(text)
    )
    dlg = PortraitManager(_controller(_portraits()))
    qtbot.addWidget(dlg)
    dlg._on_size_report()
    assert shown and "valid" in shown[0]


def test_empty_source_is_safe(qtbot):
    dlg = PortraitManager(_controller([]))
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 0
    assert not dlg._select_button.isEnabled()
    assert not dlg._exclude_button.isEnabled()
    assert not dlg._apply_button.isEnabled()
    assert not dlg._prev_button.isEnabled()
    assert not dlg._next_button.isEnabled()


# --------------------------------------------------------------------------- #
# The controller side of the size report
# --------------------------------------------------------------------------- #
def _write_tga(path, width, height):
    header = bytearray(18)
    header[2] = 2
    header[12] = width & 0xFF
    header[13] = width >> 8
    header[14] = height & 0xFF
    header[15] = height >> 8
    header[16] = 24
    path.write_bytes(bytes(header) + bytes(width * height * 3))


def test_invalid_portrait_sizes_follows_the_original_rule(tmp_path, monkeypatch):
    """VB flags a file whose size is neither required *nor any valid portrait size*.

    So a 128x256 file named "…h.tga" is in the wrong slot but is still a real
    portrait size, and is left alone; only an image that is no portrait size at
    all is reported. The second half of that rule is what stops every misfiled
    image being called broken.
    """
    from vaultkeeper.ui.controller import ProfileController

    good = tmp_path / "po_goodh.tga"
    _write_tga(good, 256, 512)          # exactly right
    slot = tmp_path / "po_sloth.tga"
    _write_tga(slot, 128, 256)          # a valid portrait size, wrong slot
    junk = tmp_path / "po_junkh.tga"
    _write_tga(junk, 100, 100)          # no portrait size at all

    entries = [
        {"resref": p.name[:-5], "mod": "M", "group": "", "folder": "portraits",
         "sizes": {"h": p}}
        for p in (good, slot, junk)
    ]
    monkeypatch.setattr(
        ProfileController,
        "installed_portraits_report",
        lambda self, *, include_override=False: {"portraits": entries, "count": 3},
    )
    report = ProfileController.invalid_portrait_sizes(object.__new__(ProfileController))

    flagged = {row["file"] for row in report["invalid"]}
    assert flagged == {"po_junkh.tga"}, "only the non-portrait size is invalid"
    assert report["checked"] == 3


def test_the_required_sizes_match_the_original_tool():
    # Defs.PortraitInfo. Portraits are twice as tall as they are wide; the
    # nwnfile docstring used to claim they were square.
    from vaultkeeper.ui.controller import ProfileController

    assert ProfileController.PORTRAIT_REQUIRED_SIZES == {
        "h": (256, 512),
        "l": (128, 256),
        "m": (64, 128),
        "s": (32, 64),
        "t": (16, 32),
    }
