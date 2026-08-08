"""The Neverwinter Vault's own API, as an alternative to scraping its pages.

NIT v8.0 replaced page scraping with this, and the reason is worth stating: the
Vault is being redesigned, and a redesign moves the HTML a scraper depends on
without changing a single fact the scraper was after. An API answers with the
facts — the project's title, its attachments, their real filenames and sizes,
what it requires — and it answers in one request.

Concretely, against the same project page:

* the scraper reads a filename out of a link's display text, and asks the server
  a separate HEAD request per file to learn how big it is;
* the API states ``filename`` and ``size_bytes`` outright.

Both produce :class:`~vaultkeeper.vault.scraper_info.VaultScraperInfo` records, so
the download workflow above them cannot tell which one it was given — the choice
is a setting, and scraping stays as the fallback for as long as the pages exist.

The addresses are **not** hardcoded: they come from the download rules, which are
published online, so the Vault can move its API without a new release here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from nwnfile.log import get_logger

from vaultkeeper.vault.download_rules import API_FULL_DESCRIPTION, DownloadRules
from vaultkeeper.vault.http import HttpClient, RequestsHttpClient
from vaultkeeper.vault.scraper_info import VaultScraperInfo

log = get_logger(__name__)


@dataclass
class ApiResult:
    """One API response: its URL, the decoded JSON, and why it failed if it did.

    VB ``NwVault.ApiResult``. A failure carries the reason rather than raising,
    because every caller's answer to "the Vault is unreachable" is the same —
    show nothing and say so — and a message is more use than a traceback.
    """

    url: str
    data: dict | list | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.data is not None


@dataclass(frozen=True)
class FoundProject:
    """A project a title search matched (VB ``NwVault.ProjectId``)."""

    project_id: int
    title: str
    link: str


@dataclass
class ApiProject:
    """A Vault project as the API describes it (VB ``NwVault.ProjectItem``)."""

    project_id: int = 0
    title: str = ""
    link: str = ""
    description: str = ""
    votes: int = 0
    rating: float = 0.0
    #: Downloadable files, in the order the project lists them.
    files: list[VaultScraperInfo] = field(default_factory=list)
    #: What the project says it needs — ``{"title", "url", "type"}`` each. A
    #: ``type`` of ``external`` is a web page (7-Zip's home page), not a file.
    required: list[dict[str, str]] = field(default_factory=list)


def _text(value) -> str:
    return "" if value is None else str(value)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def project_from_json(data: dict, rules: DownloadRules | None = None) -> ApiProject:
    """Build an :class:`ApiProject` from a decoded ``projects/…`` response."""
    rules = rules or DownloadRules()
    project = ApiProject(
        project_id=_int(data.get("project_id")),
        title=_text(data.get("title")),
        link=_text(data.get("link") or data.get("url")),
        description=_text(data.get("description") or data.get("full_description")),
        votes=_int(data.get("votes_count")),
    )
    try:
        project.rating = float(data.get("average_rating") or 0.0)
    except (TypeError, ValueError):
        project.rating = 0.0

    for entry in data.get("attachments") or []:
        if not isinstance(entry, dict):
            continue
        info = VaultScraperInfo(project_title=project.title)
        # The API separates what the scraper had to conflate: ``description`` is
        # the label the project chose to show, ``filename`` is what lands on disk.
        info.description = _text(entry.get("description")) or _text(entry.get("filename"))
        info.filename = _text(entry.get("filename"))
        info.counter_url = rules.get_final_url(_text(entry.get("link") or entry.get("url")))
        info.byte_size = _int(entry.get("size_bytes"))
        project.files.append(info)

    for entry in data.get("required_projects") or []:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title"))
        if title:
            project.required.append(
                {
                    "title": title,
                    "url": _text(entry.get("link") or entry.get("url")),
                    "type": _text(entry.get("type")),
                }
            )
    return project


class VaultApi:
    """Queries the Vault's API through the same injected HTTP client as the scraper."""

    def __init__(
        self, rules: DownloadRules | None = None, http: HttpClient | None = None
    ) -> None:
        self.rules = rules or DownloadRules()
        self.http = http or RequestsHttpClient()
        #: The last query made, for the error/status line the dialogs show.
        self.last_query = ""
        self._links = None

    # -- Requests ---------------------------------------------------------- #
    def _get(self, query: str) -> ApiResult:
        """Perform one API query and decode its JSON."""
        url = self.rules.api.query(query)
        self.last_query = url
        try:
            response = self.http.get(url, allow_redirects=True)
        except Exception as ex:
            log.warning("Vault API request failed for %s: %s", url, ex)
            return ApiResult(url, error=str(ex))
        if not getattr(response, "ok", False):
            return ApiResult(url, error=f"HTTP {getattr(response, 'status', 0)}")
        try:
            return ApiResult(url, data=json.loads(response.text or ""))
        except ValueError as ex:
            log.warning("Vault API returned malformed JSON for %s: %s", url, ex)
            return ApiResult(url, error=f"Malformed response: {ex}")

    def project_by_url(self, url: str, *, description: bool = False) -> ApiProject | None:
        """The project at a Vault page URL (``None`` when it cannot be read).

        The Vault's by-URL query does not serve the description, so asking for one
        costs a second request by id — which is what NIT does too.
        """
        result = self._get(f"{self.rules.api.by_url}{quote(url or '', safe='')}")
        if not isinstance(result.data, dict):
            return None
        project = project_from_json(result.data, self.rules)
        if description and not project.description and project.project_id:
            detailed = self.project_by_id(project.project_id, description=True)
            if detailed is not None:
                return detailed
        return project

    def project_by_id(self, project_id: int, *, description: bool = False) -> ApiProject | None:
        """The project with this Vault id — one request fewer than by URL."""
        query = f"{self.rules.api.by_id}{int(project_id)}"
        if description:
            query += API_FULL_DESCRIPTION
        result = self._get(query)
        if not isinstance(result.data, dict):
            return None
        return project_from_json(result.data, self.rules)

    def search_by_title(self, title: str) -> list[FoundProject]:
        """Projects whose title partially matches ``title`` (empty on failure)."""
        query = (title or "").strip()
        if not query:
            return []
        result = self._get(f"{self.rules.api.search_by_title}{quote(query, safe='')}")
        payload = result.data if isinstance(result.data, dict) else {}
        found = []
        for entry in payload.get("results") or []:
            if isinstance(entry, dict) and _text(entry.get("title")):
                found.append(
                    FoundProject(
                        project_id=_int(entry.get("project_id")),
                        title=_text(entry.get("title")),
                        link=_text(entry.get("link") or entry.get("url")),
                    )
                )
        return found

    def file_by_fid(self, fid: int | str) -> VaultScraperInfo | None:
        """The file behind a ``…pubdlcnt.php?fid=N`` counter link.

        A counter link says nothing about what it points at; this is how a name
        and a size are had for one without downloading it.
        """
        result = self._get(f"{self.rules.api.by_fid}?fid={quote(str(fid), safe='')}")
        if not isinstance(result.data, dict):
            return None
        info = VaultScraperInfo()
        info.filename = _text(result.data.get("filename"))
        info.description = info.filename
        info.counter_url = _text(result.data.get("link") or result.data.get("url"))
        info.byte_size = _int(result.data.get("size_bytes"))
        return info if info.filename or info.counter_url else None

    # -- The scraper's interface, so callers need not care which is in use --- #
    def fetch_project(self, url: str, *, title: str = "") -> list[VaultScraperInfo]:
        """The project's downloadable files (VaultScraper's method, via the API)."""
        project = self._project_for(url)
        if project is None:
            return []
        if title:
            for info in project.files:
                info.project_title = title
        return project.files

    def fetch_required_projects(self, url: str) -> list[dict[str, str]]:
        """The projects this one requires — title and URL, as the scraper returns."""
        project = self._project_for(url)
        return [] if project is None else project.required

    def _project_for(self, url: str) -> ApiProject | None:
        """By id when the URL carries one, else by URL."""
        project_id = project_id_from_url(url)
        if project_id:
            return self.project_by_id(project_id)
        return self.project_by_url(url)

    # -- Turning a counter link into the file behind it ---------------------- #
    # The API describes files; it does not serve them. Every attachment link is
    # still the Vault's download-counting redirect, and following it is the same
    # work whichever way the list was obtained — so it stays in one place.
    @property
    def _link_resolver(self):
        from vaultkeeper.vault.scraper import VaultScraper

        if self._links is None:
            self._links = VaultScraper(self.rules, self.http)
        return self._links

    def resolve_direct_url(self, vsi: VaultScraperInfo) -> str:
        """Set and return ``vsi.direct_url`` by following its counter link."""
        return self._link_resolver.resolve_direct_url(vsi)

    def fetch_size(self, vsi: VaultScraperInfo) -> int:
        """The file's size — already known from the API, so no request is made."""
        if vsi.byte_size:
            return vsi.byte_size
        return self._link_resolver.fetch_size(vsi)


def project_id_from_url(url: str) -> int:
    """A Vault project id read out of a URL, or 0.

    Only ``/project/<digits>`` style links carry one; the readable
    ``/project/nwn1/module/<slug>`` links do not, and must be resolved by URL.
    """
    parts = [p for p in urlsplit(url or "").path.split("/") if p]
    for index, part in enumerate(parts):
        if part.lower() in ("project", "node") and index + 1 < len(parts):
            candidate = parts[index + 1]
            if candidate.isdigit():
                return int(candidate)
    return 0
