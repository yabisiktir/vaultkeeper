"""VaultScraper — resolve Neverwinter Vault download URLs (VB ``VaultScraper``).

This first slice ports the URL-resolution logic (``VaultScraperInfo.SetDirectUrl``):
turn a project's *counter* link into the real *direct* download URL by following the
server redirect, and read the file size. The HTTP client is injected so this is
tested against recorded responses, not the live Vault. Full project-page HTML
scraping (extracting the file list) builds on this next.
"""

from __future__ import annotations

from vaultkeeper.core.log import get_logger
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.http import HttpClient, RequestsHttpClient
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo

log = get_logger(__name__)


class VaultScraper:
    """Resolves Vault download links using injected download rules + HTTP client."""

    def __init__(
        self, rules: DownloadRules | None = None, http: HttpClient | None = None
    ) -> None:
        self.rules = rules or DownloadRules()
        self.http = http or RequestsHttpClient()

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
