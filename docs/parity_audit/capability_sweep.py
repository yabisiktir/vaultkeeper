#!/usr/bin/env python3
"""List every user-facing capability the original documents, and its port status.

Why this exists
---------------
The earlier parity instruments all shared one anchor: **things already ported**.
``DIALOG_PARITY.md`` was "a pass over every *ported* dialog that has a help
topic". The Help-button coverage pass mapped topics to dialogs that *have* a
Help button. The ledger counts methods and handlers per VB file, so a flow made
of seven questions inside one ``NIT_Shown`` handler reads as one row.

None of them can find a capability that was never started, and one duly hid:
NIT's first run asks seven setup questions (``firsttimeexecution.htm``), which
has no form of its own, no Help button, and lives inside two form events. The
port asks two.

So the denominator here is the **help topic set** — 236 topics, each describing
something a user can do — rather than the dialog set. A topic with no port
evidence is not automatically a gap, but it is automatically a *question*, and
questions are what the other instruments stopped generating.

Usage
-----
    python docs/parity_audit/capability_sweep.py            # unreviewed topics
    python docs/parity_audit/capability_sweep.py --all      # every topic
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELP = ROOT / "src" / "vaultkeeper" / "ui" / "resources" / "help"
SRC = ROOT / "src" / "vaultkeeper"
STATUS = Path(__file__).with_name("CAPABILITY_STATUS.md")


def topics() -> list[tuple[str, str]]:
    """``(filename, title)`` for every bundled help topic."""
    found = []
    for path in sorted(HELP.glob("*.htm")):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
        title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip() if match else ""
        found.append((path.name, title))
    return found


def reviewed() -> dict[str, str]:
    """Topics already given a verdict in ``CAPABILITY_STATUS.md``.

    The table's first column is the topic file; the last is the verdict. Kept as
    prose rather than data so the reasoning travels with the verdict.

    A row often covers several topics at once ("a.htm / b.htm"), because one
    verdict genuinely answers both. Each name is taken separately — matching the
    whole cell meant those rows marked *nothing* reviewed, so a topic with a
    written verdict kept being offered up for review.
    """
    if not STATUS.is_file():
        return {}
    verdicts = {}
    for line in STATUS.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) < 2:
            continue
        for name in re.findall(r"[\w.\-]+\.htm\b", cells[0]):
            verdicts[name] = cells[-1]
    return verdicts


def evidence(title: str) -> str:
    """A port symbol that looks like it implements ``title``, or "".

    Only a hint for whoever reviews the topic — deliberately crude, because a
    confident guess here would recreate the very problem this script exists to
    expose.
    """
    words = [w for w in re.findall(r"[A-Za-z]{5,}", title) if w.lower() not in _NOISE]
    for word in words:
        hits = [
            p
            for p in SRC.rglob("*.py")
            if word.lower() in p.read_text(errors="replace").lower()
        ]
        if hits:
            return f"{word} -> {hits[0].relative_to(SRC)}"
    return ""


_NOISE = {
    "installer", "neverwinter", "nights", "using", "which", "there", "these",
    "about", "their", "would", "should", "where", "while", "tools", "does",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="include reviewed topics")
    args = parser.parse_args()

    verdicts = reviewed()
    rows = topics()
    shown = 0
    for name, title in rows:
        verdict = verdicts.get(name)
        if verdict and not args.all:
            continue
        shown += 1
        mark = verdict or "UNREVIEWED"
        print(f"{name:36s} {title[:52]:54s} {mark}")
    print(
        f"\n{len(rows)} topics — {len(verdicts)} reviewed, "
        f"{len(rows) - len(verdicts)} not. Showing {shown}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
