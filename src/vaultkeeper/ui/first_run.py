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

    if not FirstRunDialog.worth_asking(installs, options):
        return None

    dialog = FirstRunDialog(installs, options, getattr(recommended, "path", Path()), parent)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return None
    return FirstRunChoices(
        game_root=dialog.game_root,
        store_root=dialog.store_root,
        group_set=dialog.group_set,
    )
