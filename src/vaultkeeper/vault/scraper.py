"""VaultScraper — resolve Neverwinter Vault download URLs (VB ``VaultScraper``).

This first slice ports the URL-resolution logic (``VaultScraperInfo.SetDirectUrl``):
turn a project's *counter* link into the real *direct* download URL by following the
server redirect, and read the file size. The HTTP client is injected so this is
tested against recorded responses, not the live Vault. Full project-page HTML
scraping (extracting the file list) builds on this next.
"""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import unquote, urlsplit

from vaultkeeper.core.log import get_logger
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.http import HttpClient, RequestsHttpClient
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo

log = get_logger(__name__)

#: Marker present on each downloadable-file row of a Vault project page.
_FILE_MARKER = "file-icon"
_ANCHOR_TEXT = re.compile(r"<a[^>]+>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href=["']?([^"'>\s]+)""", re.IGNORECASE)
_LENGTH = re.compile(r"length=([0-9]+)", re.IGNORECASE)


def _title_from_url(url: str) -> str:
    """A readable project title from the URL's last path segment."""
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return unquote(slug).replace("-", " ").replace("_", " ").strip()


class VaultScraper:
    """Resolves Vault download links using injected download rules + HTTP client."""

    def __init__(
        self, rules: DownloadRules | None = None, http: HttpClient | None = None
    ) -> None:
        self.rules = rules or DownloadRules()
        self.http = http or RequestsHttpClient()

    def fetch_project(
        self, url: str, *, title: str = ""
    ) -> list[VaultScraperInfo]:
        """Fetch a project page and scrape its downloadable files."""
        try:
            resp = self.http.get(url, allow_redirects=True)
        except OSError as ex:
            log.warning("Vault project fetch failed for %s: %s", url, ex)
            return []
        if not resp.ok or not resp.text:
            return []
        split = urlsplit(resp.url or url)
        base_url = f"{split.scheme}://{split.netloc}"
        return self.scrape_files(
            resp.text, title=title or _title_from_url(url), base_url=base_url
        )

    def scrape_files(
        self, html: str, *, title: str = "", base_url: str = ""
    ) -> list[VaultScraperInfo]:
        """Extract the downloadable files from a project page (VB ``ExtractAttachments``).

        Each file row (a line containing ``file-icon``) yields a record with the
        display text, the (rule-resolved, absolute) counter URL and the byte size.
        """
        infos: list[VaultScraperInfo] = []
        for line in html.splitlines():
            if _FILE_MARKER in line:
                info = self._extract_file(line, title, base_url)
                if info is not None:
                    infos.append(info)
        return infos

    def _extract_file(
        self, line: str, title: str, base_url: str
    ) -> VaultScraperInfo | None:
        anchor = _ANCHOR_TEXT.search(line)
        href = _HREF.search(line)
        if anchor is None or href is None:
            return None
        vsi = VaultScraperInfo(project_title=title)
        vsi.description = html_lib.unescape(anchor.group(1)).strip()

        url = href.group(1).strip()
        if not url.lower().startswith("http"):
            url = base_url + url
        # A "count.php?...=http..." wrapper unwraps to the inner URL.
        idx = url.lower().find("=http")
        if "count.php" in url.lower() and idx != -1:
            url = url[idx + 1:]
        vsi.counter_url = self.rules.get_final_url(unquote(url))

        length = _LENGTH.search(line)
        if length is not None:
            try:
                vsi.byte_size = int(length.group(1))
            except ValueError:
                vsi.byte_size = 0
        return vsi

    def resolve_direct_url(self, vsi: VaultScraperInfo) -> str:
        """Set and return ``vsi.direct_url`` from its counter URL.

        Applies any redirect rule, then follows the counter link's server redirect
        (``Location``) to the real file (``ftp:`` rewritten to ``https:``); falls back
        to the counter URL when there is no redirect.
        """
        counter = self.rules.get_final_url(vsi.counter_url)
        if not counter:
            vsi.direct_url = ""
            return ""
        try:
            resp = self.http.head(counter, allow_redirects=False)
        except OSError as ex:  # network failure -> keep the counter URL
            log.warning("Vault HEAD failed for %s: %s", counter, ex)
            vsi.status = FileStatus.ERROR
            vsi.direct_url = counter
            return counter

        location = resp.location
        if location:
            if location.lower().startswith("ftp:"):
                location = "https:" + location[len("ftp:"):]
            vsi.direct_url = location
        else:
            vsi.direct_url = counter

        # Rolo Vault links: keep the counter URL if downloads must not be counted.
        if "rolovault" in vsi.direct_url.lower():
            vsi.counter_url = vsi.direct_url
        return vsi.direct_url

    def fetch_size(self, vsi: VaultScraperInfo) -> int:
        """Populate ``vsi.byte_size`` from the direct URL's ``Content-Length``."""
        url = vsi.direct_url or self.resolve_direct_url(vsi)
        if not url:
            return 0
        try:
            resp = self.http.head(url, allow_redirects=True)
        except OSError as ex:
            log.warning("Vault size HEAD failed for %s: %s", url, ex)
            return vsi.byte_size
        vsi.byte_size = resp.content_length
        return vsi.byte_size
