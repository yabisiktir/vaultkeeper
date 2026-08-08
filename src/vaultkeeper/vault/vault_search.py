"""Finding the Vault page for a PRC-ified archive, for the user to confirm.

The Drive folder gives a file name; the requirements live on the module's Vault
page. Bridging the two means a search, and the Vault's own relevance is not good
enough to trust blindly — searching its site for "A Call for Heroes" returns
*Selendi: Call to Heroes 4* and a music pack above anything else, and "Almraiven"
does not put Almraiven first at all.

So results are **ranked here and confirmed by the user**, never auto-selected.
The ranking exists to put the likely answer at the top of a short list, not to
make the decision: picking the wrong page attaches the wrong dependencies, and
that is a broken install rather than a wrong label.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import quote, urlsplit

_BASE = "https://neverwintervault.org"
_SEARCH = _BASE + "/search/node/{query}"

#: Project links in a results page. Each appears twice — once as an image link
#: with no text, once with the title — so results are keyed by URL and the
#: titled one wins.
_RESULT = re.compile(
    r'<a[^>]+href="(/project/nwn1/[^"#?]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)

#: ``/project/nwn1/module/…`` -> "module". What kind of thing a result is. The
#: game segment is not pinned to ``nwn1``: the API answers with ``nwnee`` pages
#: too, and an Enhanced Edition module is still a module.
_KIND = re.compile(r"^/project/[^/]+/([^/]+)", re.IGNORECASE)

#: A module is what we are looking for; the rest are usually its dependencies.
_PREFERRED_KINDS = ("module",)

#: Words that say nothing about which module this is.
_NOISE = re.compile(r"\b(the|a|an|of|and|for|ee|remastered|edition|part)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    """One Vault page that might be the module's."""

    title: str
    url: str
    kind: str = ""
    score: float = 0.0

    @property
    def full_url(self) -> str:
        return self.url if self.url.startswith("http") else _BASE + self.url


def search_url(title: str) -> str:
    return _SEARCH.format(query=quote((title or "").strip()))


def normalise(text: str) -> str:
    """Lowercased, punctuation-free, without words that carry no identity."""
    plain = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return " ".join(_NOISE.sub(" ", plain).split())


def similarity(query: str, title: str) -> float:
    """How much a result's title looks like what we searched for, 0…1."""
    left, right = normalise(query), normalise(title)
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    # A title that contains the whole query is a strong signal that a pure
    # character ratio understates — "almraiven" inside "almraiven ee" scores
    # only moderately, yet is almost certainly the right page.
    if left in right or right in left:
        ratio = max(ratio, 0.9)
    return ratio


def parse_results(html: str) -> list[Candidate]:
    """Project pages linked from a search-results page, in the order given."""
    best: dict[str, str] = {}
    order: list[str] = []
    for url, raw in _RESULT.findall(html or ""):
        title = html_lib.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()
        title = " ".join(title.split())
        if url not in best:
            order.append(url)
            best[url] = title
        elif title and not best[url]:
            best[url] = title  # the titled anchor beats the image one
    out = []
    for url in order:
        kind_match = _KIND.match(url)
        out.append(Candidate(best[url], url, kind_match.group(1) if kind_match else ""))
    return out


def rank(query: str, candidates) -> list[Candidate]:
    """Candidates most-likely first, modules ahead of equally-similar hakpaks."""
    scored = []
    for candidate in candidates:
        if not candidate.title:
            continue  # an image link whose partner supplied no title
        score = similarity(query, candidate.title)
        if candidate.kind in _PREFERRED_KINDS:
            score += 0.15
        scored.append(
            Candidate(candidate.title, candidate.url, candidate.kind, round(score, 4))
        )
    return sorted(scored, key=lambda c: (-c.score, c.title.lower()))


class VaultSearch:
    """Searches the Vault through an injected HTTP client.

    Given an ``api`` it asks the Vault's own title search instead of reading a
    results page. The ranking above is applied either way — the Vault's order is
    what it is, and the reason this class exists is that it cannot be trusted to
    put the right module first.
    """

    def __init__(self, http, api=None) -> None:
        self._http = http
        self._api = api

    def find(self, title: str, *, limit: int = 10) -> list[Candidate]:
        """Ranked candidates for ``title``; empty when the search cannot be read.

        Never returns a decision — the caller shows these and the user picks.
        """
        query = (title or "").strip()
        if not query:
            return []
        if self._api is not None:
            return rank(query, self._api_candidates(query))[:limit]
        try:
            response = self._http.get(search_url(query))
        except Exception:
            return []
        if not getattr(response, "ok", False):
            return []
        return rank(query, parse_results(getattr(response, "text", "") or ""))[:limit]

    def _api_candidates(self, query: str) -> list[Candidate]:
        """Title-search hits from the API, in the shape the ranking expects."""
        found = []
        for hit in self._api.search_by_title(query):
            kind_match = _KIND.match(urlsplit(hit.link).path or "")
            found.append(
                Candidate(hit.title, hit.link, kind_match.group(1) if kind_match else "")
            )
        return found
