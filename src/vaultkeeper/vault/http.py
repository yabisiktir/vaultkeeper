"""A minimal, injectable HTTP client seam for the Vault scraper/downloader.

The scraping and download workflows (VB ``VaultScraper`` / ``DownloadProject``) do
real web requests; keeping them behind this seam lets the logic be tested with a
``FakeHttpClient`` (recorded responses) instead of hitting the live Neverwinter Vault.
The default :class:`RequestsHttpClient` uses ``requests``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

USER_AGENT = "Vaultkeeper/1.0"


@dataclass
class HttpResponse:
    """A single HTTP response (headers are looked up case-insensitively)."""

    url: str  # the final URL (after any redirects the client followed)
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""
    content: bytes = b""

    def header(self, name: str) -> str:
        """Case-insensitive header lookup ("" when absent)."""
        low = name.lower()
        for key, value in self.headers.items():
            if key.lower() == low:
                return value
        return ""

    @property
    def location(self) -> str:
        return self.header("Location")

    @property
    def content_length(self) -> int:
        try:
            return int(self.header("Content-Length"))
        except ValueError:
            return 0

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


class HttpClient(Protocol):
    """The operations the scraper/downloader need."""

    def get(
        self, url: str, *, allow_redirects: bool = True, timeout: float = 30
    ) -> HttpResponse:  # pragma: no cover - protocol
        ...

    def head(
        self, url: str, *, allow_redirects: bool = False, timeout: float = 30
    ) -> HttpResponse:  # pragma: no cover - protocol
        ...


class RequestsHttpClient:
    """Default HTTP client backed by ``requests``."""

    def __init__(self, user_agent: str = USER_AGENT) -> None:
        self._headers = {"User-Agent": user_agent}

    def get(
        self, url: str, *, allow_redirects: bool = True, timeout: float = 30
    ) -> HttpResponse:
        return self._request("get", url, allow_redirects, timeout)

    def head(
        self, url: str, *, allow_redirects: bool = False, timeout: float = 30
    ) -> HttpResponse:
        return self._request("head", url, allow_redirects, timeout)

    def _request(
        self, method: str, url: str, allow_redirects: bool, timeout: float
    ) -> HttpResponse:
        import requests

        resp = requests.request(
            method,
            url,
            headers=self._headers,
            allow_redirects=allow_redirects,
            timeout=timeout,
        )
        text = "" if method == "head" else resp.text
        content = b"" if method == "head" else resp.content
        return HttpResponse(
            url=resp.url,
            status=resp.status_code,
            headers={k: v for k, v in resp.headers.items()},
            text=text,
            content=content,
        )


class FakeHttpClient:
    """Test client returning canned responses, recording the requests made."""

    def __init__(self, responses: dict[str, HttpResponse] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    def get(
        self, url: str, *, allow_redirects: bool = True, timeout: float = 30
    ) -> HttpResponse:
        self.calls.append(("GET", url))
        return self.responses.get(url, HttpResponse(url=url, status=404))

    def head(
        self, url: str, *, allow_redirects: bool = False, timeout: float = 30
    ) -> HttpResponse:
        self.calls.append(("HEAD", url))
        return self.responses.get(url, HttpResponse(url=url, status=404))
