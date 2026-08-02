"""The HTTP seam — what it decodes, and what it refuses to hold in memory.

These are about one failure: downloading the Vault's CEP 3 (a 1.2 GB file and a
0.9 GB one) took the whole application down rather than failing as a download.
Two separate things were buffering it.
"""

from __future__ import annotations

import pytest

from vaultkeeper.vault.http import (
    FakeHttpClient,
    HttpResponse,
    RequestsHttpClient,
    _wants_text,
)


class _FakeRequestsResponse:
    """Stands in for a ``requests`` response, and screams if ``.text`` is touched."""

    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type} if content_type else {}
        self.url = "http://cdn/thing"
        self.status_code = 200

    @property
    def text(self) -> str:
        raise AssertionError("decoded a body that should never have been decoded")


def test_a_binary_body_is_never_decoded_to_text(monkeypatch):
    """``requests``' ``.text`` on a 1.2 GB hakpak builds a str several times larger.

    Holding the bytes, that decoded copy, and the write buffer at once is what
    actually exhausted memory. Nothing wants text from an archive.
    """
    response = _FakeRequestsResponse(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64, "application/zip")
    monkeypatch.setattr(
        "requests.request", lambda *a, **k: response, raising=False
    )
    result = RequestsHttpClient().get("http://cdn/thing")
    assert result.text == ""  # not decoded — and the property would have raised
    assert result.content.startswith(b"7z")


def test_pages_are_still_decoded(monkeypatch):
    """The scraper reads every project page out of ``.text``; that must keep working."""

    class _Page(_FakeRequestsResponse):
        @property
        def text(self) -> str:
            return self.content.decode()

    monkeypatch.setattr(
        "requests.request",
        lambda *a, **k: _Page(b"<html>hi</html>", "text/html; charset=utf-8"),
        raising=False,
    )
    assert RequestsHttpClient().get("http://vault/p").text == "<html>hi</html>"


@pytest.mark.parametrize(
    ("content_type", "size", "expected"),
    [
        ("text/html; charset=utf-8", 500, True),
        ("application/json", 500, True),
        ("application/xhtml+xml", 500, True),
        ("application/octet-stream", 500, False),
        ("application/x-7z-compressed", 500, False),
        ("", 500, True),  # untyped and small enough to be a page
        ("", 1 << 30, False),  # untyped and the size of a hakpak
    ],
)
def test_what_counts_as_text(content_type, size, expected):
    assert _wants_text(content_type, size) is expected


def test_the_fake_client_streams_to_disk_like_the_real_one(tmp_path):
    url = "http://cdn/a.zip"
    http = FakeHttpClient({url: HttpResponse(url, 200, content=b"DATA")})
    seen: list[tuple[int, int]] = []
    response = http.download(url, tmp_path / "a.zip", on_chunk=lambda d, t: seen.append((d, t)))
    assert response.ok
    assert (tmp_path / "a.zip").read_bytes() == b"DATA"
    assert seen == [(4, 4)]


def test_nothing_is_written_when_the_server_refuses(tmp_path):
    http = FakeHttpClient({})
    response = http.download("http://cdn/gone.zip", tmp_path / "gone.zip")
    assert not response.ok
    assert not (tmp_path / "gone.zip").exists()
