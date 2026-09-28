"""Inventory NIT's common dialog frame, form by form, for DIALOG_FRAME.md.

Run from vaultkeeper/:
    python docs/screen_parity/frame_inventory.py > docs/screen_parity/frame_inventory.md

From each NIT control dump (nit/<Form>.controls.txt) it picks out the frame:
the header icon (a 32x32 PictureBox; its image from the form's Designer.vb),
the description (the label beside it), the "?" help button (a 22x22 ButtonLabel,
whose name is the help topic), the footer status label (MsgLabel) and the footer
buttons. The VK columns say what the counterpart has today: its module (from
inventory.py) and whether it has a Help button (from vk/<Form>.controls.txt).
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VB = HERE.parents[2] / "NWN Installer Tool v8.0" / "NWN Installer Tool"


def _rows(form: str) -> list[list[str]]:
    lines = (HERE / "nit" / f"{form}.controls.txt").read_text(errors="replace").splitlines()
    return [line.strip().split("\t") for line in lines[1:]]


def _bounds(cols: list[str]) -> tuple[int, ...] | None:
    for col in cols[2:]:
        if re.fullmatch(r"-?\d+,-?\d+,\d+,\d+", col):
            return tuple(int(n) for n in col.split(","))
    return None


def _icon(form: str, picture: str) -> str:
    designer = VB / f"{form}.Designer.vb"
    if not designer.exists():
        return ""
    source = designer.read_text(errors="replace")
    found = re.search(rf"Me\.{re.escape(picture)}\.Image = .*Resources\.(\w+)", source)
    return found.group(1) if found else "(resx)"


def frame(form: str) -> dict:
    icon = description = help_name = status = ""
    buttons: list[str] = []
    for cols in _rows(form):
        kind, name = cols[0], cols[1] if len(cols) > 1 else ""
        text = cols[2] if len(cols) > 2 else ""
        box = _bounds(cols)
        if kind == "PictureBox" and box and box[2:] == (32, 32) and not icon:
            icon = _icon(form, name) or name
        elif kind == "Label" and box and box[0] == 41 and not description:
            description = text.strip()
        elif (
            kind == "ButtonLabel" and box and box[2:] == (22, 22) and not help_name
            and name.startswith("Bh") and not name.startswith("BhBrowse")
        ):
            help_name = name
        elif kind == "MsgLabel" and not status:
            status = name
        elif kind == "ButtonPlus" and "hidden" not in cols:
            buttons.append(text.replace("&", ""))
    return {
        "icon": icon, "description": description, "help": help_name,
        "status": status, "buttons": buttons,
    }


IMAGES = HERE.parents[1] / "src" / "vaultkeeper" / "ui" / "resources" / "images"


def bundled(icon: str) -> str:
    """Whether VK already ships the header icon (so the frame needs no new asset)."""
    if not icon or icon.startswith("("):
        return ""
    return " ✓" if any(IMAGES.glob(f"{icon}.*")) else " ✗"


def vk_has_help(form: str) -> str:
    dump = HERE / "vk" / f"{form}.controls.txt"
    if not dump.exists():
        return "?"
    return "yes" if any(line.endswith("\tHelp") for line in dump.read_text().splitlines()) else "no"


def main() -> None:
    forms = sorted(p.name[: -len(".controls.txt")] for p in (HERE / "nit").glob("*.controls.txt"))
    print("Header icon: ✓ already bundled in Vaultkeeper, ✗ would need copying from NIT.\n")
    columns = (
        "NIT form", "Header icon", "Description", "? help topic",
        "Footer status", "Footer buttons", "VK Help button",
    )
    print("| " + " | ".join(columns) + " |")
    print("|---|---|---|---|---|---|---|")
    for form in forms:
        f = frame(form)
        if not (f["icon"] or f["description"] or f["help"]):
            header = "—"
        else:
            header = f"`{f['icon']}`{bundled(f['icon'])}" if f["icon"] else "—"
        desc = (f["description"][:90] + "…") if len(f["description"]) > 90 else f["description"]
        print(
            f"| {form} | {header} | {desc or '—'} | {f['help'] or '—'} | {f['status'] or '—'} "
            f"| {', '.join(f['buttons']) or '—'} | {vk_has_help(form)} |"
        )


if __name__ == "__main__":
    main()
