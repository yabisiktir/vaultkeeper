"""Is there a newer Vaultkeeper? (VB ``MsUpdateNow`` / ``bhnitdownload.htm``.)

VB downloads a 7-Zip from the Vault and unpacks it over itself. This does not:
it asks the project's releases what the latest version is and, if that is newer,
offers to open the release page.

Replacing a running application's own files is the part of a self-updater that
goes wrong, and it goes wrong on the machine of whoever least wanted it to. The
useful half — *there is a new one, here it is* — needs none of that.

Nothing is sent. This reads a public releases list; it does not report who
asked, or what they have installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The releases feed for the project (the API's "latest release" endpoint).
RELEASES_URL = "https://api.github.com/repos/yabisiktir/vaultkeeper/releases/latest"

#: Where a person goes to get it. The API answers with this too, but a fallback
#: matters: a missing release page is worse than a stale one.
RELEASES_PAGE = "https://github.com/yabisiktir/vaultkeeper/releases"


@dataclass(frozen=True)
class UpdateCheck:
    """What the releases feed said."""

    #: True only when a *newer* version was found.
    available: bool = False
    current: str = ""
    latest: str = ""
    url: str = RELEASES_PAGE
    notes: str = ""
    message: str = ""
    error: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    """``"v1.2.3-beta"`` → ``(1, 2, 3)``. Unparseable text sorts lowest.

    Deliberately forgiving: a tag is written by a person, and refusing to
    compare "v1.2" with "1.2.0" would make the check fail exactly when it is
    most wanted.
    """
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers[:4])


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is a later version than ``current``."""
    left, right = parse_version(latest), parse_version(current)
    if not left:
        return False
    # Pad so (1, 2) and (1, 2, 0) compare equal rather than by length.
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def check_for_update(http, current_version: str) -> UpdateCheck:
    """Ask the project whether there is a newer release than ``current_version``."""
    try:
        response = http.get(RELEASES_URL, timeout=10)
        status = getattr(response, "status_code", 0)
        if status == 404:
            # No release has been published yet; that is not a failure.
            return UpdateCheck(
                current=current_version,
                message="No releases have been published yet.",
            )
        if status >= 400:
            return UpdateCheck(
                current=current_version,
                error=f"The releases list answered HTTP {status}.",
                message=f"Could not check for updates (HTTP {status}).",
            )
        data = response.json()
    except Exception as ex:
        return UpdateCheck(
            current=current_version,
            error=str(ex),
            message=f"Could not check for updates: {ex}",
        )

    latest = str(data.get("tag_name") or data.get("name") or "").strip()
    url = str(data.get("html_url") or "") or RELEASES_PAGE
    notes = str(data.get("body") or "").strip()
    if not latest:
        return UpdateCheck(
            current=current_version,
            url=url,
            message="The releases list gave no version number.",
        )
    if is_newer(latest, current_version):
        return UpdateCheck(
            available=True,
            current=current_version,
            latest=latest,
            url=url,
            notes=notes,
            message=f"Vaultkeeper {latest} is available. You have {current_version}.",
        )
    return UpdateCheck(
        current=current_version,
        latest=latest,
        url=url,
        message=f"You have the latest version ({current_version}).",
    )
