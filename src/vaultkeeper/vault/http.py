"""A minimal, injectable HTTP client seam for the Vault scraper/downloader.

The scraping and download workflows (VB ``VaultScraper`` / ``DownloadProject``) do
real web requests; keeping them behind this seam lets the logic be tested with a
``FakeHttpClient`` (recorded responses) instead of hitting the live Neverwinter Vault.
The default :class:`RequestsHttpClient` uses ``requests``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

USER_AGENT = "Vaultkeeper/1.0"

#: Read a streamed body a megabyte at a time.
CHUNK_SIZE = 1 << 20

#: Progress while streaming a download: (bytes written so far, total or 0).
ChunkFn = Callable[[int, int], None]

#: Content types worth turning into text. A hakpak is not one of them — the
#: Vault's CEP 3 download is 1.2 GB, and asking ``requests`` for ``.text`` decodes
#: every byte of it into a ``str`` that can be four times larger again. Holding
#: the bytes, the decoded copy and the write buffer at once is what exhausts
#: memory on a big download; the scraper only ever wants text from pages.
_TEXTUAL = ("text/", "html", "xml", "json", "javascript", "urlencoded")

#: With no Content-Type to go on, decode only a body small enough to be a page.
_UNTYPED_LIMIT = 4 << 20


def _wants_text(content_type: str, size: int) -> bool:
    """Whether a body of this type should be decoded to text at all."""
    lowered = (content_type or "").lower()
    if lowered:
        return any(marker in lowered for marker in _TEXTUAL)
    return size <= _UNTYPED_LIMIT


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

    def download(
        self,
        url: str,
        dest: Path,
        *,
        on_chunk: ChunkFn | None = None,
        timeout: float = 300,
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

    def download(
        self,
        url: str,
        dest: Path,
        *,
        on_chunk: ChunkFn | None = None,
        timeout: float = 300,
    ) -> HttpResponse:
        """Stream a body straight to ``dest``, never holding it in memory.

        The Vault serves single files well past a gigabyte. Reading one into a
        ``bytes`` and writing it out again needs twice its size in RAM before a
        byte reaches the disk, so this is the only sane way to fetch them —
        ``.text`` and ``.content`` on the returned response are deliberately empty.
        Nothing is written unless the response is OK.
        """
        import requests

        with requests.get(
            url,
            headers=self._headers,
            stream=True,
            allow_redirects=True,
            timeout=timeout,
        ) as resp:
            response = HttpResponse(
                url=resp.url,
                status=resp.status_code,
                headers={k: v for k, v in resp.headers.items()},
            )
            if not response.ok:
                return response
            written = 0
            expected = response.content_length
            with open(dest, "wb") as handle:
                for chunk in resp.iter_content(CHUNK_SIZE):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    if on_chunk is not None:
                        on_chunk(written, expected)
        return response

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
        content = b"" if method == "head" else resp.content
        text = (
            resp.text
            if content and _wants_text(resp.headers.get("Content-Type", ""), len(content))
            else ""
        )
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
        #: ``(url, destination)`` for every streamed download, so a test can tell
        #: a streamed transfer from one buffered through ``get``.
        self.streamed: list[tuple[str, Path]] = []

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

    def download(
        self,
        url: str,
        dest: Path,
        *,
        on_chunk: ChunkFn | None = None,
        timeout: float = 300,
    ) -> HttpResponse:
        """Write a recorded body to ``dest``, as the streaming client would."""
        self.calls.append(("GET", url))
        self.streamed.append((url, Path(dest)))
        response = self.responses.get(url, HttpResponse(url=url, status=404))
        if not response.ok:
            return response
        data = response.content or response.text.encode("utf-8")
        Path(dest).write_bytes(data)
        if on_chunk is not None:
            on_chunk(len(data), response.content_length or len(data))
        return response
