"""Tests for the Vault downloader (offline via FakeHttpClient)."""

from __future__ import annotations

import pytest

from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.downloader import Downloader
from vaultkeeper.vault.http import (
    FakeHttpClient,
    HttpResponse,
    TransferCancelled,
)
from vaultkeeper.vault.scraper import VaultScraper
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo


def _resp(url: str, content: bytes, status: int = 200) -> HttpResponse:
    return HttpResponse(url, status, headers={"Content-Length": str(len(content))}, content=content)


def test_download_file_writes_to_disk(tmp_path):
    url = "http://cdn/mod.zip"
    http = FakeHttpClient({url: _resp(url, b"ZIPDATA")})
    vsi = VaultScraperInfo(direct_url=url, filename="mod.zip")
    result = Downloader(http).download_file(vsi, tmp_path)
    assert result.ok
    assert result.path == tmp_path / "mod.zip"
    assert (tmp_path / "mod.zip").read_bytes() == b"ZIPDATA"
    assert vsi.status is FileStatus.DOWNLOADED
    assert vsi.byte_size == 7


def test_resolves_direct_url_when_missing(tmp_path):
    counter = "http://vault/counter?fid=1"
    direct = "http://cdn/x.zip"
    http = FakeHttpClient(
        {
            counter: HttpResponse(counter, 302, headers={"Location": direct}),
            direct: _resp(direct, b"DATA"),
        }
    )
    scraper = VaultScraper(DownloadRules(), http)
    vsi = VaultScraperInfo(counter_url=counter, filename="x.zip")
    result = Downloader(http, scraper=scraper).download_file(vsi, tmp_path)
    assert result.ok
    assert (tmp_path / "x.zip").read_bytes() == b"DATA"


def test_filename_derived_from_url(tmp_path):
    url = "http://cdn/path/My%20Mod.zip"
    http = FakeHttpClient({url: _resp(url, b"D")})
    vsi = VaultScraperInfo(direct_url=url)  # no filename set
    result = Downloader(http).download_file(vsi, tmp_path)
    assert result.path.name == "My Mod.zip"


def test_http_error_sets_error_status(tmp_path):
    url = "http://cdn/missing.zip"
    http = FakeHttpClient({url: HttpResponse(url, 404)})
    vsi = VaultScraperInfo(direct_url=url, filename="missing.zip")
    result = Downloader(http).download_file(vsi, tmp_path)
    assert not result.ok
    assert "404" in result.error
    assert vsi.status is FileStatus.ERROR


def test_no_url_is_error(tmp_path):
    result = Downloader(FakeHttpClient()).download_file(VaultScraperInfo(), tmp_path)
    assert not result.ok
    assert result.error == "no URL"


def test_download_all_skips_excluded_and_reports_progress(tmp_path):
    a = VaultScraperInfo(direct_url="http://cdn/a.zip", filename="a.zip")
    b = VaultScraperInfo(direct_url="http://cdn/b.zip", filename="b.zip")
    c = VaultScraperInfo(direct_url="http://cdn/c.zip", filename="c.zip")
    c.excluded = True
    http = FakeHttpClient(
        {
            "http://cdn/a.zip": _resp("http://cdn/a.zip", b"A"),
            "http://cdn/b.zip": _resp("http://cdn/b.zip", b"B"),
        }
    )
    progress: list[tuple[int, int]] = []
    dl = Downloader(http, on_progress=lambda i, n, v: progress.append((i, n)))
    results = dl.download_all([a, b, c], tmp_path)
    assert len(results) == 2  # c excluded
    assert progress == [(0, 2), (1, 2)]
    assert (tmp_path / "a.zip").exists() and (tmp_path / "b.zip").exists()
    assert not (tmp_path / "c.zip").exists()


# -- streaming: the Vault serves files well past a gigabyte -------------------- #
def test_a_file_is_streamed_to_disk_rather_than_read_into_memory(tmp_path):
    """CEP 3 is served as a 1.2 GB file and a 0.9 GB one.

    Buffering either needs more RAM than the machine can spare before a byte
    reaches the disk, and that does not surface as a failed download — it takes
    the application down. So the downloader must use the streaming call, not
    ``get``, and a client that only offers ``get`` is not enough.
    """
    url = "http://cdn/huge.zip"
    http = FakeHttpClient({url: _resp(url, b"BIG" * 10)})
    vsi = VaultScraperInfo(direct_url=url, filename="huge.zip")
    Downloader(http).download_file(vsi, tmp_path)
    assert http.streamed == [(url, tmp_path / "huge.zip")]


def test_progress_is_reported_within_a_file_not_only_between_files(tmp_path):
    """"Downloading part 1 of 2" says nothing for the twenty minutes it takes."""
    url = "http://cdn/mod.zip"
    http = FakeHttpClient({url: _resp(url, b"ZIPDATA")})
    seen: list[tuple[str, int, int]] = []
    vsi = VaultScraperInfo(direct_url=url, filename="mod.zip")
    Downloader(
        http, on_bytes=lambda info, done, total: seen.append((info.filename, done, total))
    ).download_file(vsi, tmp_path)
    assert seen == [("mod.zip", 7, 7)]


def test_a_failed_download_leaves_the_status_wrong_not_a_stub_file(tmp_path):
    http = FakeHttpClient({})  # 404
    vsi = VaultScraperInfo(direct_url="http://cdn/gone.zip", filename="gone.zip")
    result = Downloader(http).download_file(vsi, tmp_path)
    assert not result.ok and "404" in result.error
    assert vsi.status is FileStatus.ERROR
    assert not (tmp_path / "gone.zip").exists()


def test_cancelling_removes_the_part_file_rather_than_leaving_a_short_one(tmp_path):
    """A half file under the archive's own name is indistinguishable from a whole one."""
    url = "http://cdn/huge.zip"
    http = FakeHttpClient({url: _resp(url, b"BIG" * 10)})
    vsi = VaultScraperInfo(direct_url=url, filename="huge.zip")

    def stop(_info, _done, _total):
        raise TransferCancelled()

    with pytest.raises(TransferCancelled):
        Downloader(http, on_bytes=stop).download_file(vsi, tmp_path)
    assert not (tmp_path / "huge.zip").exists()
    # Nothing was kept, so the file is simply available again.
    assert vsi.status is FileStatus.AVAILABLE
