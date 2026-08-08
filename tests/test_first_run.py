"""The first-run screen: two questions, and when not to ask them.

The point of this screen is the two choices that otherwise go wrong in silence —
which installation, and which drive holds the store. The tests that matter are
the ones proving it stays out of the way when there is nothing to decide, and
that dismissing it costs nothing.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.editions import Edition
from nwnfile.locations import GameInstall

from vaultkeeper.game.store_volumes import StoreVolume
from vaultkeeper.ui.dialogs.first_run import FirstRunDialog
from vaultkeeper.ui.first_run import FirstRunChoices
from vaultkeeper.ui.session import auto_configure_first_run

GB = 1024 ** 3


def _install(root: str, edition=Edition.ENHANCED) -> GameInstall:
    return GameInstall(root=Path(root), edition=edition)


def _volumes(*specs) -> list[StoreVolume]:
    return [StoreVolume(Path(p), free, is_default=d) for p, free, d in specs]


# -- whether to ask at all ------------------------------------------------------ #
class TestWorthAsking:
    def test_one_install_and_one_place_is_not_a_question(self):
        """A dialog with nothing to decide teaches people to dismiss dialogs."""
        assert not FirstRunDialog.worth_asking(
            [_install("/games/NWN")], _volumes(("/default", 50 * GB, True))
        )

    def test_two_installs_is_a_question(self):
        assert FirstRunDialog.worth_asking(
            [_install("/steam/NWN"), _install("/gog/NWN")],
            _volumes(("/default", 50 * GB, True)),
        )

    def test_two_places_for_the_store_is_a_question(self):
        assert FirstRunDialog.worth_asking(
            [_install("/games/NWN")],
            _volumes(("/default", 20 * GB, True), ("/big/Vaultkeeper", 900 * GB, False)),
        )


# -- the dialog ----------------------------------------------------------------- #
class TestDialog:
    def _dialog(self, qtbot, installs=None, volumes=None, recommended="/big/Vaultkeeper"):
        installs = installs or [_install("/steam/NWN"), _install("/gog/NWN")]
        volumes = volumes or _volumes(
            ("/big/Vaultkeeper", 900 * GB, False), ("/default", 20 * GB, True)
        )
        dlg = FirstRunDialog(installs, volumes, Path(recommended))
        qtbot.addWidget(dlg)
        return dlg

    def test_every_install_is_offered(self, qtbot):
        dlg = self._dialog(qtbot)
        shown = [dlg.install_combo.itemData(i) for i in range(dlg.install_combo.count())]
        assert shown == ["/steam/NWN", "/gog/NWN"]

    def test_the_first_install_is_preselected_so_continue_is_the_old_behaviour(self, qtbot):
        assert self._dialog(qtbot).game_root == "/steam/NWN"

    def test_the_recommended_store_is_preselected(self, qtbot):
        assert self._dialog(qtbot).store_root == "/big/Vaultkeeper"

    def test_the_ordinary_place_can_still_be_chosen(self, qtbot):
        dlg = self._dialog(qtbot)
        dlg.store_combo.setCurrentIndex(dlg.store_combo.findData("/default"))
        assert dlg.store_root == "/default"

    def test_a_network_volume_says_so(self, qtbot):
        volumes = [
            StoreVolume(Path("/default"), 20 * GB, is_default=True),
            StoreVolume(Path("/nas/Vaultkeeper"), 900 * GB, is_network=True),
        ]
        dlg = self._dialog(qtbot, volumes=volumes, recommended="/default")
        labels = [dlg.store_combo.itemText(i) for i in range(dlg.store_combo.count())]
        assert any("(network)" in text for text in labels)

    def test_the_install_label_names_what_it_is(self, qtbot):
        dlg = self._dialog(qtbot, installs=[_install("/steam/NWN")])
        assert "/steam/NWN" in dlg.install_combo.itemText(0)
        assert "Enhanced" in dlg.install_combo.itemText(0)


# -- what the answers do -------------------------------------------------------- #
def _settings(tmp_path):
    from vaultkeeper.config.settings import Settings

    # game_user_path matters: left unset, configure_profile auto-detects the
    # *real* NWN user folder and scans it — which made these tests depend on the
    # developer's own mods and took eight seconds each.
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    return (
        Settings(
            store_root=str(tmp_path / "default-store"), game_user_path=str(user_dir)
        ),
        tmp_path / "s.json",
    )


def test_the_chosen_install_is_the_one_configured(tmp_path):
    """Not installs[0] — that silent pick is the whole reason for the screen."""
    settings, path = _settings(tmp_path)
    installs = [_install(str(tmp_path / "steam")), _install(str(tmp_path / "gog"))]
    controller = auto_configure_first_run(
        settings,
        choices=FirstRunChoices(game_root=str(tmp_path / "gog")),
        settings_path=path,
        discover=lambda: installs,
    )
    assert controller is not None
    assert Path(settings.nwn_path) == tmp_path / "gog"


def test_the_chosen_store_is_where_the_profile_lands(tmp_path):
    settings, path = _settings(tmp_path)
    chosen = tmp_path / "big" / "Vaultkeeper"
    controller = auto_configure_first_run(
        settings,
        choices=FirstRunChoices(
            game_root=str(tmp_path / "steam"), store_root=str(chosen)
        ),
        settings_path=path,
        discover=lambda: [_install(str(tmp_path / "steam"))],
    )
    assert controller is not None
    assert Path(settings.store_root) == chosen
    assert chosen.is_dir()


def test_no_answers_behaves_exactly_as_before(tmp_path):
    """A dismissed dialog must cost nothing — first install, default store."""
    settings, path = _settings(tmp_path)
    installs = [_install(str(tmp_path / "steam")), _install(str(tmp_path / "gog"))]
    controller = auto_configure_first_run(
        settings, choices=None, settings_path=path, discover=lambda: installs
    )
    assert controller is not None
    assert Path(settings.nwn_path) == tmp_path / "steam"
    assert Path(settings.store_root) == tmp_path / "default-store"


def test_a_hand_picked_folder_works_when_discovery_found_nothing(tmp_path):
    """Browse… on the screen must not need the install to have been discovered."""
    settings, path = _settings(tmp_path)
    controller = auto_configure_first_run(
        settings,
        choices=FirstRunChoices(game_root=str(tmp_path / "elsewhere")),
        settings_path=path,
        discover=lambda: [],
    )
    assert controller is not None
    assert Path(settings.nwn_path) == tmp_path / "elsewhere"


def test_nothing_found_and_nothing_chosen_leaves_it_to_set_up_profile(tmp_path):
    settings, path = _settings(tmp_path)
    assert (
        auto_configure_first_run(
            settings, choices=None, settings_path=path, discover=lambda: []
        )
        is None
    )


def test_an_already_configured_profile_is_never_disturbed(tmp_path):
    from vaultkeeper.config.settings import Settings

    settings = Settings(active_profile="My Mods")
    assert auto_configure_first_run(settings, settings_path=tmp_path / "s.json") is None
