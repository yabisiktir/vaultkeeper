"""Tests for the Vault HTTP seam and URL-resolution scraper."""

from __future__ import annotations

from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
from vaultkeeper.vault.scraper import VaultScraper
from vaultkeeper.vault.scraper_info import FileStatus, VaultScraperInfo


class TestHttpResponse:
    def test_header_case_insensitive(self):
        r = HttpResponse("u", 200, headers={"Content-Length": "42", "Location": "/x"})
        assert r.header("content-length") == "42"
        assert r.location == "/x"
        assert r.content_length == 42
        assert r.ok

    def test_bad_content_length(self):
        assert HttpResponse("u", 200, headers={"Content-Length": "?"}).content_length == 0

    def test_not_ok(self):
        assert not HttpResponse("u", 404).ok


class TestFakeHttpClient:
    def test_records_calls_and_defaults_404(self):
        http = FakeHttpClient()
        resp = http.get("http://x")
        assert resp.status == 404
        assert http.calls == [("GET", "http://x")]


class TestResolveDirectUrl:
    def test_follows_redirect_location(self):
        counter = "http://vault.example/counter?fid=99"
        http = FakeHttpClient(
            {counter: HttpResponse(counter, 302, headers={"Location": "http://cdn/x.zip"})}
        )
        scraper = VaultScraper(http=http)
        vsi = VaultScraperInfo(counter_url=counter)
        assert scraper.resolve_direct_url(vsi) == "http://cdn/x.zip"
        assert vsi.direct_url == "http://cdn/x.zip"

    def test_ftp_rewritten_to_https(self):
        counter = "http://vault.example/counter"
        http = FakeHttpClient(
            {counter: HttpResponse(counter, 302, headers={"Location": "ftp://cdn/x.zip"})}
        )
        vsi = VaultScraperInfo(counter_url=counter)
        assert VaultScraper(http=http).resolve_direct_url(vsi) == "https://cdn/x.zip"

    def test_no_location_keeps_counter(self):
        counter = "http://vault.example/direct.zip"
        http = FakeHttpClient({counter: HttpResponse(counter, 200)})
        vsi = VaultScraperInfo(counter_url=counter)
        assert VaultScraper(http=http).resolve_direct_url(vsi) == counter

    def test_redirect_rule_applied_first(self):
        rules = DownloadRules(redirects={"http://old/c": "http://new/c"})
        http = FakeHttpClient(
            {"http://new/c": HttpResponse("http://new/c", 302, headers={"Location": "http://cdn/x"})}
        )
        vsi = VaultScraperInfo(counter_url="http://old/c")
        scraper = VaultScraper(rules=rules, http=http)
        assert scraper.resolve_direct_url(vsi) == "http://cdn/x"
        # The rule-mapped URL was the one actually fetched.
        assert ("HEAD", "http://new/c") in http.calls

    def test_rolovault_keeps_counter_synced(self):
        counter = "http://vault.example/counter"
        http = FakeHttpClient(
            {counter: HttpResponse(counter, 302, headers={"Location": "http://rolovault.com/f/1"})}
        )
        vsi = VaultScraperInfo(counter_url=counter)
        direct = VaultScraper(http=http).resolve_direct_url(vsi)
        assert vsi.counter_url == direct  # counter re-pointed to the rolovault URL

    def test_network_error_sets_error_status(self):
        class Boom:
            def head(self, *a, **k):
                raise OSError("no network")

            def get(self, *a, **k):
                raise OSError("no network")

        vsi = VaultScraperInfo(counter_url="http://x/c")
        scraper = VaultScraper(http=Boom())
        assert scraper.resolve_direct_url(vsi) == "http://x/c"
        assert vsi.status is FileStatus.ERROR


class TestFetchSize:
    def test_reads_content_length(self):
        direct = "http://cdn/x.zip"
        http = FakeHttpClient(
            {direct: HttpResponse(direct, 200, headers={"Content-Length": "1048576"})}
        )
        vsi = VaultScraperInfo(direct_url=direct)
        assert VaultScraper(http=http).fetch_size(vsi) == 1048576
        assert vsi.byte_size == 1048576


class TestScrapeFiles:
    def test_extracts_file_row(self):
        html = (
            "<div>intro</div>\n"
            '<span class="file-icon"></span> '
            '<a href="http://cdn/mymod.zip" length=1048576>My Mod.zip</a>\n'
            "<div>footer</div>\n"
        )
        files = VaultScraper().scrape_files(html, title="My Project")
        assert len(files) == 1
        vsi = files[0]
        assert vsi.project_title == "My Project"
        assert vsi.description == "My Mod.zip"
        assert vsi.counter_url == "http://cdn/mymod.zip"
        assert vsi.byte_size == 1048576

    def test_relative_href_gets_base_url(self):
        html = '<i class="file-icon"></i><a href="/files/x.hak">x.hak</a>\n'
        files = VaultScraper().scrape_files(html, base_url="http://vault.example")
        assert files[0].counter_url == "http://vault.example/files/x.hak"

    def test_count_php_wrapper_unwrapped(self):
        html = (
            '<span class="file-icon"></span>'
            '<a href="/downloads/count.php?fid=5&url=http://cdn/real.zip">real.zip</a>\n'
        )
        files = VaultScraper().scrape_files(html, base_url="http://vault.example")
        assert files[0].counter_url == "http://cdn/real.zip"

    def test_html_entities_decoded(self):
        html = '<span class="file-icon"></span><a href="http://cdn/a.zip">A &amp; B.zip</a>\n'
        assert VaultScraper().scrape_files(html)[0].description == "A & B.zip"

    def test_non_file_lines_ignored(self):
        html = "<a href='http://x'>not a file</a>\nplain text\n"
        assert VaultScraper().scrape_files(html) == []

    def test_multiple_files(self):
        html = (
            '<span class="file-icon"></span><a href="http://cdn/a.zip">a.zip</a>\n'
            '<span class="file-icon"></span><a href="http://cdn/b.hak">b.hak</a>\n'
        )
        files = VaultScraper().scrape_files(html)
        assert [f.description for f in files] == ["a.zip", "b.hak"]

    def test_redirect_rule_applied_to_scraped_url(self):
        rules = DownloadRules(redirects={"http://old/a.zip": "http://new/a.zip"})
        html = '<span class="file-icon"></span><a href="http://old/a.zip">a.zip</a>\n'
        files = VaultScraper(rules=rules).scrape_files(html)
        assert files[0].counter_url == "http://new/a.zip"
