"""Downloader — fetch resolved Vault files to disk (VB ``DownloadProject`` download).

Downloads a list of :class:`VaultScraperInfo` files into a target directory (a mod's
``_Downloads`` folder), resolving the direct URL first when needed and reporting
progress. The HTTP client is injected, so the workflow is tested offline. The
project-page HTML scrape that produces the file list builds on this next.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from nwnfile.log import get_logger

from vaultkeeper.vault.http import HttpClient, RequestsHttpClient
from vaultkeeper.vault.scraper import VaultScraper
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo

log = get_logger(__name__)

#: Progress callback: (index, total, file being downloaded).
ProgressFn = Callable[[int, int, VaultScraperInfo], None]


@dataclass
class DownloadResult:
    """Outcome of downloading one file."""

    info: VaultScraperInfo
    path: Path | None = None
    ok: bool = False
    error: str = ""


def _filename_from_url(url: str) -> str:
    """The last path segment of a URL, percent-decoded (fallback filename)."""
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return name or "download.bin"


class Downloader:
    """Downloads Vault files to disk (progress + direct-URL resolution injected)."""

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        scraper: VaultScraper | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.http = http or RequestsHttpClient()
        self.scraper = scraper
        self.on_progress = on_progress

    def download_file(self, vsi: VaultScraperInfo, dest_dir: Path) -> DownloadResult:
        """Download one file into ``dest_dir``; updates ``vsi`` status/size/filename."""
        url = vsi.direct_url
        if not url and self.scraper is not None:
            url = self.scraper.resolve_direct_url(vsi)
        url = url or vsi.counter_url
        if not url:
            vsi.status = FileStatus.ERROR
            return DownloadResult(vsi, error="no URL")

        try:
            resp = self.http.get(url, allow_redirects=True)
        except OSError as ex:
            vsi.status = FileStatus.ERROR
            log.warning("Vault download failed for %s: %s", url, ex)
            return DownloadResult(vsi, error=str(ex))
        if not resp.ok:
            vsi.status = FileStatus.ERROR
            return DownloadResult(vsi, error=f"HTTP {resp.status}")

        name = vsi.local_filename or vsi.filename or _filename_from_url(url)
        dest = dest_dir / name
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
        except OSError as ex:
            vsi.status = FileStatus.ERROR
            log.warning("Unable to write %s: %s", dest, ex)
            return DownloadResult(vsi, error=str(ex))

        vsi.local_filename = name
        vsi.byte_size = len(resp.content)
        vsi.status = FileStatus.DOWNLOADED
        return DownloadResult(vsi, path=dest, ok=True)

    def download_all(
        self, files: list[VaultScraperInfo], dest_dir: Path
    ) -> list[DownloadResult]:
        """Download every non-excluded file, reporting progress. Returns results."""
        wanted = [f for f in files if not f.excluded]
        results: list[DownloadResult] = []
        for index, vsi in enumerate(wanted):
            if self.on_progress is not None:
                self.on_progress(index, len(wanted), vsi)
            results.append(self.download_file(vsi, dest_dir))
        return results
