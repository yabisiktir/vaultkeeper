"""Turning a Drive file id into something downloadable, and noticing when it isn't.

Drive does not always answer a download with the file. It may return a page
instead — a virus-scan confirmation for very large files, a "quota exceeded"
notice when a popular file has been fetched too often, or a sign-in prompt if
sharing changed. All three arrive as HTTP 200 with HTML, so a downloader that
trusts the status code writes the page to disk under the archive's name and the
failure only surfaces later, as a corrupt 7z.

Measured on the PRC-ified folder (2026-08-02): the fourteen largest modules, up
to 83 MB, all served ``application/octet-stream`` straight away via
``drive.usercontent.google.com`` — the confirmation step did not appear at all.
So this is a guard, not the main path. It is still worth having: none of the
three failures above is under our control or announces itself in the status.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.vault.drive_folder import download_url

#: 7-Zip, ZIP and RAR magic — what a module archive should begin with.
_ARCHIVE_MAGIC = (b"7z\xbc\xaf\x27\x1c", b"PK\x03\x04", b"Rar!")

#: The confirm form Drive serves for a file it wants acknowledged.
_FORM_ACTION = re.compile(r'<form[^>]+action="([^"]+)"', re.IGNORECASE)
_INPUT = re.compile(
    r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"', re.IGNORECASE
)
#: Older responses carried the token as a cookie or query parameter instead.
_CONFIRM_TOKEN = re.compile(r"confirm=([0-9A-Za-z_-]+)")

_QUOTA = re.compile(r"quota|too many users|exceeded", re.IGNORECASE)
_SIGNIN = re.compile(r"accounts\.google\.com|sign ?in", re.IGNORECASE)


@dataclass(frozen=True)
class DriveFile:
    """A downloaded archive: where it came from, and where it landed."""

    url: str
    filename: str = ""
    size: int = 0
    path: Path | None = None


class DriveDownloadError(RuntimeError):
    """Drive answered with a page instead of the file."""


def looks_like_archive(head: bytes) -> bool:
    """Whether the first bytes are an archive rather than a web page."""
    return bool(head) and head.startswith(_ARCHIVE_MAGIC)


def is_page(content_type: str, head: bytes = b"") -> bool:
    """Whether a response is HTML — the shape all three failures take."""
    if "text/html" in (content_type or "").lower():
        return True
    return bool(head) and head.lstrip()[:1] == b"<"


def describe_page(html: str) -> str:
    """Why Drive refused, in words worth showing someone."""
    if _QUOTA.search(html or ""):
        return (
            "Google Drive is refusing this download for now: the file has been "
            "fetched too many times recently. It usually clears within a day."
        )
    if _SIGNIN.search(html or ""):
        return (
            "Google Drive is asking for a sign-in, so this file is no longer "
            "shared publicly."
        )
    return (
        "Google Drive returned a page instead of the file — most likely its "
        "confirmation step for a large download."
    )


def confirm_url(html: str, fallback_id: str = "") -> str:
    """The URL that gets past a confirmation page, or ``""``.

    Handles both shapes Drive has used: a hidden-input form, and a bare
    ``confirm=<token>`` in a link.
    """
    text = html or ""
    action = _FORM_ACTION.search(text)
    if action:
        url = html_lib.unescape(action.group(1))
        params = {
            html_lib.unescape(name): html_lib.unescape(value)
            for name, value in _INPUT.findall(text)
        }
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            return f"{url}{'&' if '?' in url else '?'}{query}"
        return url
    token = _CONFIRM_TOKEN.search(text)
    if token and fallback_id:
        return f"{download_url(fallback_id)}&confirm={token.group(1)}"
    return ""


def filename_from(disposition: str) -> str:
    """The name Drive suggests, from ``Content-Disposition``."""
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition or "")
    return html_lib.unescape(match.group(1)).strip() if match else ""


def fetch(
    http,
    file_ident: str,
    dest_dir: Path,
    *,
    fallback_name: str = "",
    on_chunk=None,
) -> DriveFile:
    """Download a Drive file into ``dest_dir``, refusing to keep a page.

    Streamed to a part-file and judged on what actually arrived, because there is
    no way to ask Drive in advance: the confirmation, quota and sign-in responses
    are all HTTP 200, and the only thing that distinguishes the archive is that it
    begins ``7z``. Judging it from a buffered body instead would mean holding the
    whole file in memory to find out, which for a big one is how an application
    dies rather than how a download fails.

    A confirmation step is followed once. Anything else Drive says raises
    :class:`DriveDownloadError` with the reason, and nothing is left on disk.
    """
    from vaultkeeper.vault.http import TransferCancelled

    url = download_url(file_ident)
    part = dest_dir / f".{file_ident}.part"
    try:
        response = http.download(url, part, on_chunk=on_chunk)
    except TransferCancelled:
        _discard(part)
        raise
    if not response.ok:
        _discard(part)
        raise DriveDownloadError(f"Google Drive answered HTTP {response.status}.")

    if _is_page_on_disk(response, part):
        body = _read_page(part)
        target = confirm_url(body, file_ident)
        _discard(part)
        if not target:
            raise DriveDownloadError(describe_page(body))
        url = target
        try:
            response = http.download(url, part, on_chunk=on_chunk)
        except TransferCancelled:
            _discard(part)
            raise
        if not response.ok or _is_page_on_disk(response, part):
            body = _read_page(part) if response.ok else ""
            _discard(part)
            raise DriveDownloadError(describe_page(body))

    name = (
        filename_from(_header(response, "Content-Disposition"))
        or fallback_name
        or f"{file_ident}.7z"
    )
    final = dest_dir / name
    part.replace(final)
    return DriveFile(url, name, final.stat().st_size, final)


def _is_page_on_disk(response, path: Path) -> bool:
    """Whether what landed is HTML rather than an archive."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    return is_page(_header(response, "Content-Type"), head)


def _read_page(path: Path) -> str:
    """A refusal page's text. Only ever called on something already known to be one."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _discard(path: Path) -> None:
    path.unlink(missing_ok=True)


def _header(response, name: str) -> str:
    return response.header(name) if hasattr(response, "header") else ""
