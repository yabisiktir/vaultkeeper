

# -- Matches show up in the real mod list (tshelpfindandrename.htm) -------------- #
def test_typing_a_find_selects_the_matching_mods_in_the_list(qtbot, tmp_path):
    """"The Mod names that match your Find criteria are selected in the Mod
    list." The dialog previewed what would change and never said which mods —
    and a rename you can see against the real list is one you are far likelier
    to notice is wrong."""
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    for name in ("Swordflight I", "Swordflight II", "Aielund"):
        controller.pd.add_mod(ModData(group="Adv", mod_name=name))

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_find_and_rename()
    dlg = win._find_rename_dialog
    qtbot.addWidget(dlg)

    dlg._find.setText("Swordflight")

    selected = sorted(win._tree.selected_mod_names())
    assert selected == ["Swordflight I", "Swordflight II"]


def test_clearing_the_find_clears_the_selection(qtbot, tmp_path):
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.pd.add_mod(ModData(group="Adv", mod_name="Swordflight"))

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_find_and_rename()
    dlg = win._find_rename_dialog
    qtbot.addWidget(dlg)

    dlg._find.setText("Sword")
    assert win._tree.selected_mod_names() == ["Swordflight"]

    dlg._find.setText("")
    assert win._tree.selected_mod_names() == []
