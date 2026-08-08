"""Tests for the Vault API client and the published download-rules source.

The JSON in these fixtures is the shape the live API actually returns — captured
from ``projects/by-url``, ``projects/by-title`` and ``files/by-fid`` — so a change
at the Vault shows up here as a failing assertion rather than as an empty file
list in front of a user.
"""

from __future__ import annotations

import json

from vaultkeeper.vault import rules_source
from vaultkeeper.vault.api import VaultApi, project_from_json, project_id_from_url
from vaultkeeper.vault.download_rules import DownloadRules
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse

API = "https://neverwintervault.org/api/v1/"

PROJECT_JSON = {
    "project_id": 11455,
    "title": "Neverwinter Nights Mod Installer Tool - NIT",
    "link": "https://neverwintervault.org/project/nwn1/other/tool/nit",
    "attachments": [
        {
            "description": "NWN Installer Tool v8-0.7z",
            "filename": "nwn_installer_tool_v8-0.7z",
            "link": "https://neverwintervault.org/sites/all/modules/pubdlcnt/"
            "pubdlcnt.php?fid=295004",
            "size_bytes": 37554426,
            "download_count": 1,
        },
        {
            "description": "Version History.txt",
            "filename": "nwn_installer_tool_version_history_126.txt",
            "link": "https://neverwintervault.org/files/history.txt",
            "size_bytes": 216126,
            "download_count": 0,
        },
    ],
    "required_projects": [
        {"type": "external", "title": "7-Zip", "link": "https://www.7-zip.org"}
    ],
    "votes_count": 42,
    "average_rating": 9.7,
}


def _json_response(url: str, payload) -> HttpResponse:
    return HttpResponse(url, 200, text=json.dumps(payload))


def _api(payloads: dict) -> VaultApi:
    http = FakeHttpClient({url: _json_response(url, body) for url, body in payloads.items()})
    return VaultApi(DownloadRules(), http)


class TestProjectFromJson:
    def test_attachments_become_download_records(self):
        project = project_from_json(PROJECT_JSON)
        assert [f.filename for f in project.files] == [
            "nwn_installer_tool_v8-0.7z",
            "nwn_installer_tool_version_history_126.txt",
        ]
        # The size arrives with the listing; the scraper needed a HEAD per file.
        assert project.files[0].byte_size == 37554426
        assert project.files[0].project_title.startswith("Neverwinter Nights Mod")

    def test_required_projects_keep_their_kind(self):
        required = project_from_json(PROJECT_JSON).required
        assert required == [
            {"title": "7-Zip", "url": "https://www.7-zip.org", "type": "external"}
        ]

    def test_rating_and_votes(self):
        project = project_from_json(PROJECT_JSON)
        assert (project.votes, project.rating) == (42, 9.7)

    def test_missing_fields_do_not_raise(self):
        project = project_from_json({})
        assert (project.project_id, project.title, project.files) == (0, "", [])

    def test_junk_values_are_survivable(self):
        project = project_from_json(
            {"project_id": "x", "average_rating": "n/a", "attachments": ["not a dict"]}
        )
        assert (project.project_id, project.rating, project.files) == (0, 0.0, [])

    def test_redirect_rules_apply_to_attachment_links(self):
        rules = DownloadRules(redirects={"http://old/f.7z": "http://new/f.7z"})
        data = {"attachments": [{"filename": "f.7z", "link": "http://old/f.7z"}]}
        assert project_from_json(data, rules).files[0].counter_url == "http://new/f.7z"

    def test_filename_stands_in_for_a_missing_label(self):
        data = {"attachments": [{"filename": "f.7z", "link": "http://x/f.7z"}]}
        assert project_from_json(data).files[0].description == "f.7z"


class TestProjectIdFromUrl:
    def test_numeric_project_link(self):
        assert project_id_from_url("https://neverwintervault.org/project/11455") == 11455

    def test_readable_link_has_no_id(self):
        assert project_id_from_url("https://neverwintervault.org/project/nwn1/module/x") == 0

    def test_empty(self):
        assert project_id_from_url("") == 0


class TestVaultApi:
    def test_fetch_project_by_url(self):
        url = "https://neverwintervault.org/project/nwn1/other/tool/nit"
        api = _api({f"{API}projects/by-url?url={_quoted(url)}": PROJECT_JSON})
        files = api.fetch_project(url)
        assert [f.filename for f in files] == [
            "nwn_installer_tool_v8-0.7z",
            "nwn_installer_tool_version_history_126.txt",
        ]

    def test_a_numeric_link_is_fetched_by_id_instead(self):
        api = _api({f"{API}projects/11455": PROJECT_JSON})
        files = api.fetch_project("https://neverwintervault.org/project/11455")
        assert len(files) == 2
        assert api.last_query == f"{API}projects/11455"

    def test_fetch_required_projects(self):
        api = _api({f"{API}projects/11455": PROJECT_JSON})
        required = api.fetch_required_projects("https://neverwintervault.org/project/11455")
        assert [r["title"] for r in required] == ["7-Zip"]

    def test_search_by_title(self):
        payload = {
            "query": "Aielund",
            "results": [
                {"project_id": 1861, "title": "Aielund Hakpack", "link": "http://v/1861"},
                {"project_id": 31006, "title": "After Aielund 1.1", "link": "http://v/31006"},
            ],
        }
        api = _api({f"{API}projects/by-title?title=Aielund": payload})
        found = api.search_by_title("Aielund")
        assert [f.project_id for f in found] == [1861, 31006]
        assert found[0].title == "Aielund Hakpack"

    def test_search_with_no_title_makes_no_request(self):
        api = _api({})
        assert api.search_by_title("  ") == []
        assert api.http.calls == []

    def test_file_by_fid(self):
        payload = {
            "type": "file",
            "filename": "nwn_installer_tool_v8-0.7z",
            "link": "https://neverwintervault.org/pubdlcnt.php?fid=295004",
            "size_bytes": 37554426,
        }
        api = _api({f"{API}files/by-fid?fid=295004": payload})
        info = api.file_by_fid(295004)
        assert info is not None
        assert (info.filename, info.byte_size) == ("nwn_installer_tool_v8-0.7z", 37554426)

    def test_description_is_asked_for_separately(self):
        url = "https://neverwintervault.org/project/nwn1/other/tool/nit"
        detailed = dict(PROJECT_JSON, description="What it does.")
        api = _api(
            {
                f"{API}projects/by-url?url={_quoted(url)}": PROJECT_JSON,
                f"{API}projects/11455?include_description=1": detailed,
            }
        )
        project = api.project_by_url(url, description=True)
        assert project is not None
        assert project.description == "What it does."

    def test_an_unreachable_vault_yields_no_files(self):
        class Boom:
            calls: list = []

            def get(self, url, **kw):
                raise OSError("no route to host")

        api = VaultApi(DownloadRules(), Boom())
        assert api.fetch_project("https://neverwintervault.org/project/11455") == []

    def test_malformed_json_yields_no_files(self):
        url = f"{API}projects/11455"
        http = FakeHttpClient({url: HttpResponse(url, 200, text="<html>not json</html>")})
        api = VaultApi(DownloadRules(), http)
        assert api.fetch_project("https://neverwintervault.org/project/11455") == []

    def test_size_is_not_re_requested_when_the_api_gave_one(self):
        api = _api({})
        info = project_from_json(PROJECT_JSON).files[0]
        assert api.fetch_size(info) == 37554426
        assert api.http.calls == []  # no HEAD; the listing already said

    def test_the_counter_link_is_still_followed_to_the_file(self):
        counter = "https://neverwintervault.org/pubdlcnt.php?fid=295004"
        http = FakeHttpClient(
            {counter: HttpResponse(counter, 302, headers={"Location": "http://cdn/x.7z"})}
        )
        api = VaultApi(DownloadRules(), http)
        info = project_from_json(PROJECT_JSON).files[0]
        info.counter_url = counter
        assert api.resolve_direct_url(info) == "http://cdn/x.7z"

    def test_the_api_address_comes_from_the_rules_not_the_code(self):
        rules = DownloadRules()
        rules.api.base = "https://elsewhere.example/v2/"
        rules.api.by_id = "p/"
        payload = {"project_id": 7, "title": "Moved", "attachments": []}
        http = FakeHttpClient(
            {"https://elsewhere.example/v2/p/7": _json_response("x", payload)}
        )
        project = VaultApi(rules, http).project_by_id(7)
        assert project is not None and project.title == "Moved"


def _quoted(url: str) -> str:
    from urllib.parse import quote

    return quote(url, safe="")


class TestRulesParsing:
    def test_api_addresses_are_read_from_the_rules(self):
        rules = DownloadRules.from_text(
            "RevisionNumber = 213\n"
            "ApiUrl = https://neverwintervault.org/api/v1/\n"
            "ApiByUrl = projects/by-url?url=\n"
            "ApiById = projects/\n"
            "ApiByFid = files/by-fid\n"
            "ApiSearchByTitle = projects/by-title?title=\n"
        )
        assert rules.revision == 213
        assert rules.api.base == "https://neverwintervault.org/api/v1/"
        assert rules.api.by_url == "projects/by-url?url="
        assert rules.api.by_fid == "files/by-fid"
        assert rules.api.query("projects/7") == (
            "https://neverwintervault.org/api/v1/projects/7"
        )

    def test_a_rules_file_without_them_still_has_working_defaults(self):
        rules = DownloadRules.from_text("SaveNameRemovedChars = ()&\n")
        assert rules.api.base.startswith("https://neverwintervault.org/api/")
        assert rules.revision == 0

    def test_a_bad_revision_number_does_not_raise(self):
        assert DownloadRules.from_text("RevisionNumber = soon\n").revision == 0

    def test_redirect_urls_containing_equals_are_not_mistaken_for_keywords(self):
        rules = DownloadRules.from_text(
            "Redirects\nFrom http://a/x?id=1\nTo http://b/y?id=2\nEnd Redirects\n"
        )
        assert rules.redirects == {"http://a/x?id=1": "http://b/y?id=2"}


class TestRulesSource:
    def test_the_bundled_rules_are_real_and_parse(self):
        text = rules_source.bundled_rules_text()
        assert text, "the published rules file must ship with the package"
        rules = DownloadRules.from_text(text)
        assert rules.revision > 0
        assert rules.api.base.startswith("https://")
        assert rules.save_name_rules, "the save-name map is what the play loop needs"

    def test_filename_carries_the_format_version(self):
        assert rules_source.rules_filename(3) == "DownloadRulesV3.txt"

    def test_two_hosts_are_published_primary_first(self):
        urls = rules_source.rules_urls()
        assert [name for name, _ in urls] == ["Online", "NexusMods"]
        assert all(url.endswith("DownloadRulesV3.txt") for _, url in urls)

    def test_fetched_rules_are_cached_for_next_time(self, tmp_path):
        text = "RevisionNumber = 999\nApiUrl = https://example/api/\n"
        url = rules_source.rules_urls()[0][1]
        http = FakeHttpClient({url: HttpResponse(url, 200, text=text)})
        rules = rules_source.load_rules(tmp_path, http)
        assert rules.revision == 999
        assert rules_source.cache_file(tmp_path).read_text(encoding="utf-8") == text

    def test_the_standby_host_is_used_when_the_first_fails(self, tmp_path):
        first, second = (url for _, url in rules_source.rules_urls())
        http = FakeHttpClient(
            {
                first: HttpResponse(first, 503),
                second: HttpResponse(second, 200, text="RevisionNumber = 42\n"),
            }
        )
        assert rules_source.load_rules(tmp_path, http).revision == 42

    def test_a_fresh_cache_is_not_re_fetched(self, tmp_path):
        rules_source.cache_file(tmp_path).write_text(
            "RevisionNumber = 7\n", encoding="utf-8"
        )
        http = FakeHttpClient()
        assert rules_source.load_rules(tmp_path, http).revision == 7
        assert http.calls == []

    def test_the_bundled_copy_is_the_floor_when_offline(self, tmp_path):
        class Boom:
            calls: list = []

            def get(self, url, **kw):
                raise OSError("offline")

        rules = rules_source.load_rules(tmp_path, Boom())
        assert rules.revision > 0  # the bundled file, not an empty rule set

    def test_no_http_client_means_no_request_at_all(self, tmp_path):
        assert rules_source.load_rules(tmp_path, None).revision > 0

    def test_a_windows_1252_rules_file_is_read(self, tmp_path):
        # The published file is cp1252 — it carries typographic apostrophes in
        # project names, and decoding it as UTF-8 fails on the first one.
        body = "RevisionNumber = 5\nUnsupportedProjects\nIt’s broken\nEnd UnsupportedProjects\n"
        rules_source.cache_file(tmp_path).write_bytes(body.encode("cp1252"))
        rules = rules_source.load_rules(tmp_path, None)
        assert rules.revision == 5
        assert rules.message_lines == ["It’s broken"]

    def test_the_legacy_unversioned_file_is_still_read(self, tmp_path):
        (tmp_path / "DownloadRules.txt").write_text(
            "RevisionNumber = 3\n", encoding="utf-8"
        )
        assert rules_source.load_rules(tmp_path, None).revision == 3
