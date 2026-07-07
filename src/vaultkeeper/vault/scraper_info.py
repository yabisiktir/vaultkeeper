"""VaultScraperInfo — a downloadable Vault file record (VB ``VaultScraperInfo``).

One entry in a scraped Vault project: the project title/description, the counter and
direct download URLs, the filename and size, and where it will land (mod folder /
group) with a download status. Pure data — the network scrape/redirect resolution
lives in the scraper (Phase 6), which sets ``direct_url``/``byte_size`` on these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FileStatus(Enum):
    """Download status of a Vault file."""

    AVAILABLE = "available"
    DOWNLOAD = "download"
    DOWNLOADED = "downloaded"
    EXCLUDED = "excluded"
    ERROR = "error"


_STATUS_TEXT = {
    FileStatus.AVAILABLE: "Available",
    FileStatus.DOWNLOAD: "Download",
    FileStatus.DOWNLOADED: "Downloaded",
    FileStatus.EXCLUDED: "Excluded",
    FileStatus.ERROR: "Error",
}


@dataclass
class VaultScraperInfo:
    """Information about one downloadable file from a Vault project."""

    project_title: str = ""
    description: str = ""
    counter_url: str = ""
    direct_url: str = ""
    filename: str = ""
    local_filename: str = ""
    byte_size: int = 0
    mod_folder: str = ""
    group: str = ""
    status: FileStatus = FileStatus.AVAILABLE
    _excluded: bool = field(default=False, repr=False)

    @property
    def status_text(self) -> str:
        return _STATUS_TEXT.get(self.status, "")

    @property
    def excluded(self) -> bool:
        return self._excluded

    @excluded.setter
    def excluded(self, value: bool) -> None:
        self._excluded = value
        self.status = FileStatus.EXCLUDED if value else FileStatus.AVAILABLE

    def clone(self) -> VaultScraperInfo:
        info = VaultScraperInfo(
            project_title=self.project_title,
            description=self.description,
            counter_url=self.counter_url,
            direct_url=self.direct_url,
            filename=self.filename,
            local_filename=self.local_filename,
            byte_size=self.byte_size,
            mod_folder=self.mod_folder,
            group=self.group,
            status=self.status,
        )
        info._excluded = self._excluded
        return info
