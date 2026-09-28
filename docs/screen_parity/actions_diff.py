"""List each NIT form's actions that have no counterpart caption on its VK screen.

Run from vaultkeeper/: python docs/screen_parity/actions_diff.py [Form ...] > actions_diff.md
Reads nit/<Form>.controls.txt (the harness dump) and vk/<Form>.controls.txt (from
vk_shots.py). An action is a button, check box, radio button, toolstrip item, menu
item or tab. A caption counts as matched when one normalised caption contains the
other ("Delete" matches "Delete Archive"), so what is left is worth a look, not
a verdict: the README records the verdicts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIT_KINDS = {
    "ButtonPlus", "Button", "CheckBox", "RadioButton", "LabelCheckBox", "TabPage",
    "ToolStripButton", "ToolStripMenuItem", "ToolStripDropDownButton", "ToolStripSplitButton",
}
#: Captions that name no action (designer placeholders, the help "?").
_NOISE = re.compile(r"^(toolstripbutton\d*|toolstripmenuitem\d*|button\d*|checkbox\d*|help|\?)$")


def _norm(text: str) -> str:
    text = text.replace("&", "").replace("…", "").replace("...", "")
    text = re.sub(r"\s+(ctrl|shift|alt)\+.*$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" :").lower()


def nit_actions(path: Path) -> list[tuple[str, str, bool]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.strip().split("\t")
        if len(cols) < 3 or cols[0] not in NIT_KINDS:
            continue
        text = cols[2]
        if not text.strip() and len(cols) > 5:
            text = cols[5]  # a toolstrip item with no text: its tooltip
        hidden = "hidden" in cols[3:]
        if _norm(text) and not _NOISE.match(_norm(text)):
            out.append((cols[0], text.strip(), hidden))
    return out


def vk_captions(path: Path) -> list[str]:
    return [_norm(line.split("\t", 1)[-1]) for line in path.read_text().splitlines() if line]


def unmatched(form: str) -> list[tuple[str, str, bool]] | None:
    nit, vk = HERE / "nit" / f"{form}.controls.txt", HERE / "vk" / f"{form}.controls.txt"
    if not nit.exists() or not vk.exists():
        return None
    theirs = vk_captions(vk)
    return [
        (kind, text, hidden)
        for kind, text, hidden in nit_actions(nit)
        if not any(_norm(text) in c or (c and c in _norm(text)) for c in theirs)
    ]


def main(forms: list[str]) -> None:
    suffix = ".controls.txt"
    forms = forms or sorted(p.name[: -len(suffix)] for p in (HERE / "vk").glob(f"*{suffix}"))
    print("| NIT form | NIT actions with no matching VK caption |\n|---|---|")
    for form in forms:
        rows = unmatched(form)
        if rows is None:
            continue
        cell = "; ".join(f"{t}{' (hidden)' if h else ''}" for _k, t, h in rows) or "—"
        print(f"| {form} | {cell} |")


if __name__ == "__main__":
    main(sys.argv[1:])
