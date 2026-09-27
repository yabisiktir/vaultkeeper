"""Screen-parity inventory: every NIT form -> VK screen, help topics, parity status.

Run from vaultkeeper/: python docs/screen_parity/inventory.py > docs/screen_parity/inventory.md
Sources: the v8.0 source tree's ``*.Designer.vb`` (one per form), the bundled help
(``src/vaultkeeper/ui/resources/help/*.htm``), VK's ui modules (a module "ports"
a form when its source names it: ``VB <Form>`` / ``<Form>.vb``), and the parity
write-ups (``docs/PARITY.md``, ``docs/parity_audit/DIALOG_PARITY.md``).
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VK = HERE.parents[1]
NIT = VK.parent / "NWN Installer Tool v8.0" / "NWN Installer Tool"
HELP = VK / "src" / "vaultkeeper" / "ui" / "resources" / "help"
UI = VK / "src" / "vaultkeeper" / "ui"
DOCS = [VK / "docs" / "PARITY.md", VK / "docs" / "parity_audit" / "DIALOG_PARITY.md"]


def main() -> None:
    forms = sorted(p.name[: -len(".Designer.vb")] for p in NIT.glob("*.Designer.vb"))
    modules = {p: p.read_text(encoding="utf-8", errors="replace") for p in UI.rglob("*.py")}
    helps = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in HELP.glob("*.htm")}
    docs = "\n".join(p.read_text(encoding="utf-8") for p in DOCS if p.exists())
    print("| NIT form | VK module(s) | VK title | help topic → screenshots | in parity docs |")
    print("|---|---|---|---|---|")
    for form in forms:
        word = re.compile(rf"\b{re.escape(form)}\b")
        mods = sorted(
            str(p.relative_to(UI)) for p, text in modules.items()
            if re.search(rf"(VB[^\n]{{0,40}}\b{re.escape(form)}\b|\b{re.escape(form)}\.vb\b)", text)
        )
        dialogs = [m for m in mods if m.startswith("dialogs/")] or mods
        keys, titles = [], []
        for m in dialogs:
            text = modules[UI / m]
            keys += re.findall(r'help_button\(\s*"([^"]+)"', text)
            titles += re.findall(r'setWindowTitle\(\s*"([^"]+)"', text)
        topics = []
        for key in dict.fromkeys(keys):
            name = key.lower() + ".htm"
            if name in helps:
                shots = re.findall(r'src="lib/([^"]+)"', helps[name])
                topics.append(f"{name} → {', '.join(shots[:3]) or 'no image'}")
        title = titles[0] if titles else ""
        mentioned = "yes" if word.search(docs) or (title and title in docs) else ""
        print(
            f"| {form} | {', '.join(dialogs[:2]) or '—'} | {title} | "
            f"{'; '.join(topics[:2]) or '—'} | {mentioned} |"
        )


if __name__ == "__main__":
    main()
