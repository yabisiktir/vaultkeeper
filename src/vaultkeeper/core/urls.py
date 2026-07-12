"""URL helpers ported from LazWorks ``WebOperations``/``Extensions``.

Small, dependency-free validation used when a user types a web page address (a
mod's Neverwinter Vault link). Faithful to VB ``CheckScheme`` (a bare ``www.``
host gets an ``http://`` scheme) and ``IsUrl`` (a valid, non-file URI).

Divergence (noted): VB's link validation also does a live ``WebPageExists``
network check. That is a UX convenience, not correctness — the port keeps
validation offline and syntactic, matching its testable, network-optional design.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Schemes a web page address may use (a mod link is always http(s); ftp allowed).
_WEB_SCHEMES = ("http", "https", "ftp")


def check_scheme(link: str) -> str:
    """Prepend ``http://`` to a bare ``www.`` host (VB ``CheckScheme``)."""
    if link.lower().startswith("www."):
        return f"http://{link}"
    return link


def is_url(link: str) -> bool:
    """True if ``link`` is a valid web page address (VB ``IsUrl``).

    A ``www.`` host is accepted (scheme is inferred); anything else needs an
    explicit web scheme and host. Local file paths and malformed text are rejected.
    """
    if not link:
        return False
    try:
        parsed = urlparse(check_scheme(link.strip()))
    except ValueError:
        return False
    return parsed.scheme in _WEB_SCHEMES and bool(parsed.netloc)
