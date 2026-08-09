"""CAPABILITY_STATUS must not claim a command is ported when it has no handler.

This has gone wrong three times — createcharrestorers.htm, newtopic55.htm and
newtopic73.htm — always the same way: a *present control id* read as a working
feature. The file exists to hold verdicts, so a wrong one is worse than an
unreviewed one. Checking it is cheap, so it is checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vaultkeeper.ui.main_window import MainWindow

DOC = Path(__file__).resolve().parents[1] / "docs" / "parity_audit" / "CAPABILITY_STATUS.md"

#: Ids named in prose *about* a gap rather than in a verdict. Each is a sentence
#: explaining that the command is not wired, so finding it unwired is the point.
_EXEMPT = {"MsMoveToDev"}


def _claimed_ported(text: str) -> set[str]:
    """Command ids appearing on a line that calls something ported."""
    found: set[str] = set()
    for line in text.splitlines():
        if "Ported" not in line or "GAP" in line or "was not" in line:
            continue
        found.update(re.findall(r"`((?:Ms|Rbn|Ts|Bt)[A-Za-z]+)`", line))
    return found - _EXEMPT


@pytest.fixture()
def window(qtbot) -> MainWindow:
    win = MainWindow(None)
    qtbot.addWidget(win)
    return win


def test_every_command_claimed_ported_has_a_handler(window):
    from vaultkeeper.ui.ribbon import RIBBON_TABS

    known = set(window.nit_menu.actions_by_id)
    known |= {item.action for _title, items in RIBBON_TABS for item in items}
    known |= set(window.quick_toolbar.actions_by_id)
    implemented = window.implemented_commands()

    claimed = _claimed_ported(DOC.read_text())
    assert claimed, "the sweep found no claims at all — has the format changed?"

    # An id the chrome does not carry is a typo in the doc, which is worth
    # knowing separately from a claim that is simply untrue.
    unknown = sorted(c for c in claimed if c not in known)
    assert unknown == [], f"CAPABILITY_STATUS names commands that do not exist: {unknown}"

    unwired = sorted(c for c in claimed if c not in implemented)
    assert unwired == [], (
        "CAPABILITY_STATUS says these are ported and nothing is wired to them: "
        f"{unwired}"
    )
