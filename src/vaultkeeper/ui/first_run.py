"""Asking the first-run questions, and getting on with it when there are none.

Kept apart from the dialog so the decision *whether* to ask is testable without
a screen, and so :mod:`vaultkeeper.ui.session` never imports Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nwnfile.log import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class FirstRunChoices:
    """What the user settled, or nothing when there was nothing to settle."""

    game_root: str = ""
    store_root: str = ""
    group_set: str = ""
    #: The Enhanced Edition user-files folder, when it had to be asked for
    #: (VB ExtendedEditionDialogue); "" when it was found or not asked.
    game_user_path: str = ""
    #: Whether the user turned Enhanced Edition detection off at that prompt
    #: (VB PrivateExtendedDisabled).
    disable_ee_detection: bool = False


def ask_first_run_choices(parent=None) -> FirstRunChoices | None:
    """Put the first-run questions, when there is anything to settle.

    Returns ``None`` when nothing was asked or the user closed the dialog — the
    caller then configures itself exactly as it did before, so a dismissed
    dialog costs nothing.
    """
    from nwnfile.locations import discover_installs

    from vaultkeeper.app_paths import data_root
    from vaultkeeper.game import store_volumes

    try:
        installs = [i for i in discover_installs() if i.exists()]
    except Exception:  # discovery touches the filesystem and Steam's config
        log.exception("Install discovery failed on first run")
        return None
    if not installs:
        return None  # nothing found: the manual Set Up Profile flow takes over

    try:
        options = store_volumes.candidates(data_root())
        recommended = store_volumes.recommended(data_root(), options=options)
    except Exception:
        log.exception("Could not work out where the store could go")
        options, recommended = [], None

    from vaultkeeper.ui.dialogs.first_run import FirstRunDialog

    game_root = store_root = group_set = ""
    if FirstRunDialog.worth_asking(installs, options):
        dialog = FirstRunDialog(
            installs, options, getattr(recommended, "path", Path()), parent
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        game_root, store_root, group_set = (
            dialog.game_root,
            dialog.store_root,
            dialog.group_set,
        )

    # The 5th first-run question: an Enhanced Edition install whose user-files
    # folder cannot be located. Independent of the install/store questions —
    # a single install on a single volume still needs asking when the folder is
    # missing (the flagship first-run blind spot).
    user_folder, disabled = _ask_ee_user_folder(installs, game_root, parent)

    if not (game_root or store_root or group_set or user_folder or disabled):
        return None
    return FirstRunChoices(
        game_root=game_root,
        store_root=store_root,
        group_set=group_set,
        game_user_path=user_folder,
        disable_ee_detection=disabled,
    )


def _ask_ee_user_folder(installs, chosen_root: str, parent) -> tuple[str, bool]:
    """Prompt for the EE user-files folder when it is installed but unlocatable.

    Returns ``(user_folder, detection_disabled)``; ``("", False)`` when there is
    nothing to ask — the install is classic, or the folder resolves already, or
    the user cancels. Mirrors VB ``DetectExtended`` → ``SolicitEnhanced``.
    """
    from nwnfile.locations import Edition

    from vaultkeeper.ui.session import default_game_user_path

    install = next(
        (i for i in installs if str(i.root) == chosen_root),
        installs[0],
    )
    if install.edition != Edition.ENHANCED or default_game_user_path() is not None:
        return "", False

    from vaultkeeper.ui.dialogs.extended_edition import ExtendedEditionDialog

    dialog = ExtendedEditionDialog(parent)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return "", False
    return dialog.user_folder, dialog.detection_disabled
