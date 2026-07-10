"""Help content model (VB ``HelpFileManager`` + the HelpNDoc CHM).

The original tool ships a compiled HTML Help file (``.chm``) whose topics are keyed
by control name: a dialog's Help button or a menu item opens ``<ControlName>.htm``
inside the CHM (``HelpFileManager.Open``, LazWorks Library/HelpFileManager.vb:97).

The CHM has been extracted and bundled under ``ui/resources/help/`` (236 HTML topics,
their screenshots, css/js). This module is the headless model over that content:

* :func:`help_root` — the bundled help directory.
* :func:`topic_for_control` — resolve a VB control name to its ``<name>.htm`` file
  (case-insensitive, matching the CHM's case-insensitive topic lookup).
* :func:`parse_toc` / :func:`load_toc` — the table of contents tree from ``toc.hhc``
  (the HHC sitemap: ``Name`` + ``Local`` per node, nested by ``<ul>``).
* :func:`topic_title` / :func:`read_topic` — a topic's ``<title>`` and raw HTML.

No Qt here — the :class:`~vaultkeeper.ui.dialogs.help_viewer.HelpViewer` renders it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

#: TOC sitemap file inside the extracted CHM (HTML Help Contents).
TOC_FILE = "toc.hhc"
#: Default topic when no control name is given (VB opens the CHM's TOC root).
DEFAULT_TOPIC = "MsViewHelp.htm"


def help_root() -> Path:
    """The bundled help directory (extracted CHM)."""
    return _HELP_ROOT


def available() -> bool:
    """True if the help content is present."""
    return (_HELP_ROOT / TOC_FILE).is_file()


_index_cache: dict[str, Path] | None = None


def _index() -> dict[str, Path]:
    """Case-insensitive ``lower(filename) -> path`` index of the topic files."""
    global _index_cache
    if _index_cache is None:
        _index_cache = {}
        if _HELP_ROOT.is_dir():
            for path in _HELP_ROOT.glob("*.htm"):
                _index_cache[path.name.lower()] = path
    return _index_cache


def topic_for_control(control_name: str) -> Path | None:
    """Resolve a VB control name to its topic file (VB ``Open`` → ``<name>.htm``).

    Case-insensitive (CHM topic lookup is case-insensitive); a trailing ``.htm`` on
    the input is tolerated. Returns ``None`` if the topic does not exist.
    """
    if not control_name:
        return topic_for_control(DEFAULT_TOPIC)
    name = control_name.lower()
    if not name.endswith(".htm"):
        name += ".htm"
    return _index().get(name)


@dataclass
class TocNode:
    """A table-of-contents entry (HHC sitemap object)."""

    name: str
    local: str = ""
    children: list[TocNode] = field(default_factory=list)


class _TocParser(HTMLParser):
    """Builds the TOC tree from the HHC nested ``<ul>``/sitemap-object structure."""

    def __init__(self) -> None:
        super().__init__()
        self.root: list[TocNode] = []
        self._stack: list[list[TocNode]] = [self.root]
        self._pending: TocNode | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "ul":
            parent = self._stack[-1]
            # A nested list holds the children of the most recent node.
            self._stack.append(parent[-1].children if parent else parent)
        elif tag == "object" and (attr.get("type") or "").lower() == "text/sitemap":
            self._pending = TocNode(name="")
        elif tag == "param" and self._pending is not None:
            key = (attr.get("name") or "").lower()
            value = attr.get("value") or ""
            if key == "name":
                self._pending.name = value
            elif key == "local":
                self._pending.local = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "object" and self._pending is not None:
            if self._pending.name:
                self._stack[-1].append(self._pending)
            self._pending = None
        elif tag == "ul" and len(self._stack) > 1:
            self._stack.pop()


def parse_toc(hhc_text: str) -> list[TocNode]:
    """Parse HHC sitemap text into a tree of :class:`TocNode`."""
    parser = _TocParser()
    parser.feed(hhc_text)
    return parser.root


def load_toc() -> list[TocNode]:
    """Load and parse the bundled ``toc.hhc`` (empty list if absent)."""
    toc = _HELP_ROOT / TOC_FILE
    if not toc.is_file():
        return []
    return parse_toc(toc.read_text(encoding="utf-8", errors="replace"))


_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def read_topic(path: Path) -> str:
    """Read a topic's raw HTML (UTF-8, lenient)."""
    return path.read_text(encoding="utf-8", errors="replace")


def topic_title(path: Path) -> str:
    """The ``<title>`` of a topic file, falling back to its stem."""
    try:
        match = _TITLE_RE.search(read_topic(path))
    except OSError:
        match = None
    if match:
        return match.group(1).strip()
    return path.stem
