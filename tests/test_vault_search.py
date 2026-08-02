"""Finding the Vault page for a PRC-ified archive — ranked, never auto-picked."""

from __future__ import annotations

from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
from vaultkeeper.vault.vault_search import (
    Candidate,
    VaultSearch,
    normalise,
    parse_results,
    rank,
    search_url,
    similarity,
)

#: The real shape: each project is linked twice, once as an untitled image link.
RESULTS_HTML = """
<ol class="search-results">
 <li><a href="/project/nwn1/module/almraiven"><img src="thumb.png"></a>
     <a href="/project/nwn1/module/almraiven">Almraiven</a></li>
 <li><a href="/project/nwn1/hakpak/combined/selendi-combo-hak-paks">Selendi Combo Hak Paks</a></li>
 <li><a href="/project/nwn1/module/selendi-call-heroes-4">Selendi: Call to Heroes 4</a></li>
 <li><a href="/project/nwn1/audio/music/selendi-music-pack">Selendi Music Pack</a></li>
</ol>
"""


def _search(html: str, query: str = "Almraiven", ok: bool = True) -> VaultSearch:
    url = search_url(query)
    return VaultSearch(FakeHttpClient({url: HttpResponse(url, 200 if ok else 500, {}, html)}))


# -- reading a results page --------------------------------------------------- #
def test_a_project_linked_twice_is_one_result_keeping_the_title():
    """The image link has no text; its titled partner supplies the name."""
    results = parse_results(RESULTS_HTML)
    assert len(results) == 4
    assert results[0].title == "Almraiven"
    assert results[0].url == "/project/nwn1/module/almraiven"


def test_the_kind_comes_from_the_path():
    kinds = {c.url: c.kind for c in parse_results(RESULTS_HTML)}
    assert kinds["/project/nwn1/module/almraiven"] == "module"
    assert kinds["/project/nwn1/hakpak/combined/selendi-combo-hak-paks"] == "hakpak"


def test_a_page_with_no_projects_is_not_an_error():
    assert parse_results("<html>nothing here</html>") == []
    assert parse_results("") == []


def test_a_candidate_knows_its_absolute_url():
    assert parse_results(RESULTS_HTML)[0].full_url == (
        "https://neverwintervault.org/project/nwn1/module/almraiven"
    )


# -- ranking, because the Vault's own relevance is poor ----------------------- #
def test_the_matching_module_outranks_the_noise():
    """Searching the live Vault for this puts a music pack near the top."""
    ranked = rank("Almraiven", parse_results(RESULTS_HTML))
    assert ranked[0].title == "Almraiven"


def test_a_module_beats_an_equally_similar_hakpak():
    """A module is what is being installed; the rest are its dependencies."""
    same = [
        Candidate("Widget", "/project/nwn1/hakpak/widget", "hakpak"),
        Candidate("Widget", "/project/nwn1/module/widget", "module"),
    ]
    assert rank("Widget", same)[0].kind == "module"


def test_a_title_containing_the_whole_query_ranks_highly():
    """"Almraiven" inside "Almraiven EE" is almost certainly the right page."""
    assert similarity("Almraiven", "Almraiven EE") >= 0.9


def test_words_that_carry_no_identity_are_ignored():
    assert normalise("The Siege of Shadowdale EE") == "siege shadowdale"
    assert similarity("A Call for Heroes", "Call for Heroes") >= 0.9


def test_an_unrelated_result_does_not_score_like_a_match():
    assert similarity("Almraiven", "Steam Grids for Neverwinter Nights") < 0.5


def test_untitled_results_are_dropped_rather_than_ranked_blank():
    assert rank("x", [Candidate("", "/project/nwn1/module/x", "module")]) == []


# -- the search --------------------------------------------------------------- #
def test_the_search_returns_candidates_not_a_decision():
    """Picking the wrong page attaches the wrong dependencies — a broken install."""
    found = _search(RESULTS_HTML).find("Almraiven")
    assert len(found) == 4
    assert found[0].title == "Almraiven"


def test_results_are_capped_so_the_user_reads_a_short_list():
    assert len(_search(RESULTS_HTML).find("Almraiven", limit=2)) == 2


def test_an_empty_title_is_not_searched_for():
    assert _search(RESULTS_HTML).find("  ") == []


def test_a_failed_search_yields_nothing_rather_than_raising():
    assert _search("", ok=False).find("Almraiven") == []


def test_the_query_is_url_encoded():
    assert "A%20Call%20for%20Heroes" in search_url("A Call for Heroes")
