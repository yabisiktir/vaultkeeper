"""Read a public Google Drive folder — the PRC-ified modules collection.

These are Neverwinter Vault modules rebuilt to run under PRC. The Drive folder
holds only the archive; what each one *needs* is documented on the Vault, not
here, so installing one means pairing the two (see :mod:`~vaultkeeper.vault.scraper`
``extract_required_projects``).

**Listing comes from ``embeddedfolderview``, deliberately.** Drive's own folder
page builds its list in JavaScript from obfuscated markup with generated class
names — scraping it would break on any redesign, silently. The embedded view
returns plain HTML that has been stable for years: one ``div.flip-entry`` per
item, carrying the file id in its element id and the name in a child span. It is
still an unofficial endpoint and can change; everything here fails soft, and a
listing that cannot be parsed returns empty rather than half a folder.

Names carry their own dependency hints. ``A Call for Heroes [PRC8-CEP3].7z``
says this build wants PRC8 and CEP3 — and that is more trustworthy for *this*
archive than the Vault page, which describes the original module and may name a
different CEP, or none.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

#: The stable listing endpoint. ``#list`` only picks the view; the server ignores it.
_EMBED = "https://drive.google.com/embeddedfolderview?id={id}#list"

#: A file's direct download. Large files answer with a virus-scan interstitial
#: instead of bytes — see :func:`confirm_url`.
_DOWNLOAD = "https://drive.google.com/uc?export=download&id={id}"

#: One row of the embedded view: ``<div class="flip-entry" id="entry-<id>">``.
#: Matched by its opening tag only — a row nests four or five ``</div>`` before
#: its title, so any attempt to match the closing tag stops inside the icon
#: markup and misses the name entirely. Each row is instead taken as the slice
#: up to the next row.
_ENTRY_START = re.compile(r'id="entry-([A-Za-z0-9_-]+)"', re.IGNORECASE)
_TITLE = re.compile(
    r'<div[^>]+class="[^"]*flip-entry-title[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
#: Folders link to ``/drive/folders/…``; files to ``/file/d/…``.
_FOLDER_HREF = re.compile(r"/drive/folders/", re.IGNORECASE)

#: ``…/folders/<id>`` or ``…?id=<id>`` — what a user is likely to paste.
_FOLDER_ID = re.compile(r"/folders/([A-Za-z0-9_-]{10,})")
_ID_PARAM = re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})")
_FILE_ID = re.compile(r"/file/d/([A-Za-z0-9_-]{10,})")

#: The ``[PRC8-CEP3]`` style tag in a file name, and the pieces inside it.
_TAG_BLOCK = re.compile(r"\[([^\]]+)\]")


@dataclass(frozen=True)
class DriveEntry:
    """One item in a Drive folder."""

    file_id: str
    name: str
    is_folder: bool = False

    @property
    def download_url(self) -> str:
        return "" if self.is_folder else download_url(self.file_id)

    @property
    def folder_url(self) -> str:
        return folder_url(self.file_id) if self.is_folder else ""

    @property
    def title(self) -> str:
        """The module's name, without the build tag or extension."""
        return module_title(self.name)

    @property
    def tags(self) -> tuple[str, ...]:
        """Dependency hints the file name carries, e.g. ``("PRC8", "CEP3")``."""
        return build_tags(self.name)


def folder_id(url_or_id: str) -> str:
    """The folder id from a pasted Drive URL, or the id itself."""
    text = (url_or_id or "").strip()
    if not text:
        return ""
    for pattern in (_FOLDER_ID, _ID_PARAM):
        match = pattern.search(text)
        if match:
            return match.group(1)
    # A bare id: no scheme, no slashes, and Drive's alphabet.
    if not urlsplit(text).scheme and "/" not in text and re.fullmatch(
        r"[A-Za-z0-9_-]{10,}", text
    ):
        return text
    return ""


def file_id(url_or_id: str) -> str:
    """The file id from a pasted Drive file URL, or the id itself."""
    text = (url_or_id or "").strip()
    match = _FILE_ID.search(text) or _ID_PARAM.search(text)
    if match:
        return match.group(1)
    if not urlsplit(text).scheme and "/" not in text and re.fullmatch(
        r"[A-Za-z0-9_-]{10,}", text
    ):
        return text
    return ""


def listing_url(folder: str) -> str:
    """The embedded-view URL for a folder id or URL (empty if unrecognisable)."""
    ident = folder_id(folder)
    return _EMBED.format(id=ident) if ident else ""


def folder_url(ident: str) -> str:
    return f"https://drive.google.com/drive/folders/{ident}"


def download_url(ident: str) -> str:
    return _DOWNLOAD.format(id=ident)


def parse_folder(html: str) -> list[DriveEntry]:
    """Every entry in an ``embeddedfolderview`` page, folders first as Drive lists them."""
    text = html or ""
    starts = list(_ENTRY_START.finditer(text))
    entries: list[DriveEntry] = []
    seen: set[str] = set()
    for index, match in enumerate(starts):
        ident = match.group(1)
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        body = text[match.end() : end]
        title = _TITLE.search(body)
        if ident in seen or title is None:
            continue
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip()
        if not name:
            continue
        seen.add(ident)
        entries.append(DriveEntry(ident, name, bool(_FOLDER_HREF.search(body))))
    return entries


def module_title(filename: str) -> str:
    """``"AL1 - Siege of Shadowdale EE [PRC8].7z"`` -> ``"AL1 - Siege of Shadowdale EE"``.

    What is left is what to search the Vault for; the tag and extension are ours,
    not part of the module's published name.
    """
    name = (filename or "").strip()
    for suffix in (".7z", ".zip", ".rar", ".exe"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return _TAG_BLOCK.sub(" ", name).replace("_", " ").strip(" -–—")


def build_tags(filename: str) -> tuple[str, ...]:
    """The bracketed build tags, e.g. ``("PRC8", "CEP3")`` from ``[PRC8-CEP3]``.

    Split on ``-`` and ``+``, but only where both sides look like a tag
    (letters then digits), so a hyphen inside a name is left alone.
    """
    out: list[str] = []
    for block in _TAG_BLOCK.findall(filename or ""):
        for piece in re.split(r"[-+]", block):
            piece = piece.strip()
            if piece and re.fullmatch(r"[A-Za-z]{2,}\d*(\.\d+)?", piece):
                out.append(piece.upper())
    return tuple(dict.fromkeys(out))


def is_module_archive(entry: DriveEntry) -> bool:
    """Whether an entry is a downloadable module rather than a subfolder."""
    return not entry.is_folder and entry.name.lower().endswith(
        (".7z", ".zip", ".rar", ".exe")
    )


class DriveFolder:
    """Lists a public Drive folder through an injected HTTP client."""

    def __init__(self, http) -> None:
        self._http = http

    def list(self, folder: str) -> list[DriveEntry]:
        """Entries in ``folder`` (id or URL); empty when it cannot be read."""
        url = listing_url(folder)
        if not url:
            return []
        try:
            response = self._http.get(url)
        except Exception:
            return []
        if not getattr(response, "ok", False):
            return []
        return parse_folder(getattr(response, "text", "") or "")

    def modules(self, folder: str) -> list[DriveEntry]:
        """Only the downloadable archives, sorted by title."""
        return sorted(
            (e for e in self.list(folder) if is_module_archive(e)),
            key=lambda e: e.title.lower(),
        )

    def subfolders(self, folder: str) -> list[DriveEntry]:
        return [e for e in self.list(folder) if e.is_folder]
