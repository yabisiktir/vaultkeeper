"""Where the Vault download rules come from (VB ``VaultDownloadRules`` hosting).

The rules file is **published online, not shipped with the application** — that is
the whole point of it. When the Vault changes an address, moves its API or a
project's files land somewhere new, the rules are edited once on the server and
every installation picks the change up; nobody waits for a release. NIT's author
asked specifically that the port keep this property, so the rules are fetched
here rather than being frozen into the code.

Three sources, in order:

1. the two published copies (LazWorks first, NexusMods as the standby),
2. the local cache of whichever last succeeded,
3. the copy bundled in this package.

The bundle is the floor, not the plan: a machine with no network still gets a
complete, coherent rules file instead of no rules at all — which is what the port
had before, since it only ever read a local file the user had to supply.
"""

from __future__ import annotations

import time
from pathlib import Path

from nwnfile.log import get_logger

from vaultkeeper.vault.download_rules import DownloadRules

log = get_logger(__name__)

#: Rules-file format version. NIT bumps this when statements change, and the
#: version is part of the filename, so an old application keeps reading the file
#: it understands after a newer format is published beside it.
RULES_VERSION = 3

#: The rules filename, before the version suffix (VB ``RulesBaseFilename``).
RULES_BASENAME = "DownloadRules"

#: Published copies, primary first (VB ``RulesFileUrlList``: the ``BaseLazWorksUrl``
#: and ``BaseNexusRulesUrl`` of *Application Definitions.txt*).
_RULES_HOSTS = (
    ("Online", "https://lazworks.azurewebsites.net/"),
    ("NexusMods", "https://file-metadata.nexusmods.com/file/nexus-readmes/180/869/"),
)

#: How long a cached copy is trusted before another fetch is attempted. A day
#: matches how often the rules actually change, and means opening Download
#: Project ten times in an afternoon does not make ten requests.
CACHE_MAX_AGE = 24 * 60 * 60


def rules_filename(version: int = RULES_VERSION) -> str:
    """``DownloadRulesV3.txt`` (VB ``RulesFilename``)."""
    return f"{RULES_BASENAME}V{version}.txt"


def rules_urls(version: int = RULES_VERSION) -> list[tuple[str, str]]:
    """``(host name, URL)`` for each published copy, primary first."""
    return [(name, base + rules_filename(version)) for name, base in _RULES_HOSTS]


def _decode(data: bytes) -> str:
    """Rules text from bytes.

    The published file is Windows-1252 — it contains typographic apostrophes in
    project names — so decoding it as UTF-8 fails outright. cp1252 maps every
    byte, so this cannot raise.
    """
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1252", errors="replace")


def bundled_rules_text(version: int = RULES_VERSION) -> str:
    """The copy shipped inside this package ("" when there is none)."""
    path = Path(__file__).resolve().parent / "data" / rules_filename(version)
    try:
        return _decode(path.read_bytes())
    except OSError:
        return ""


def cache_file(data_dir: Path, version: int = RULES_VERSION) -> Path:
    """Where a fetched rules file is kept."""
    return Path(data_dir) / rules_filename(version)


def _cached_text(data_dir: Path, version: int) -> str:
    """The cached rules text, else the legacy unversioned file, else ""."""
    for name in (rules_filename(version), f"{RULES_BASENAME}.txt"):
        path = Path(data_dir) / name
        try:
            return _decode(path.read_bytes())
        except OSError:
            continue
    return ""


def _cache_age(data_dir: Path, version: int) -> float:
    """Seconds since the cache was written; ``inf`` when there is no cache."""
    try:
        return max(0.0, time.time() - cache_file(data_dir, version).stat().st_mtime)
    except OSError:
        return float("inf")


#: The user's own rules, appended to the published ones (VB ``Paths.UserRulesFile``).
USER_RULES_FILENAME = "User Rules.txt"

_USER_RULES_HEADER = """\
' Your own download rules, added after the published Download Rules each time they
' are read (VB NIT's "User Rules.txt"). Use the same statements as the published
' file, typically to add projects to NoInstallerProjects and similar lists.
'
' - Lines starting with ' or # are comments.
' - Nothing here is validated: a rule with a mistake in it can stop downloads
'   working until it is fixed or removed.
' - Do not add configuration statements.
' - Changes take effect the next time the rules are read.
"""


def user_rules_file(data_dir: Path) -> Path:
    """Where the user's own rules live, beside the cached rules."""
    return Path(data_dir) / USER_RULES_FILENAME


def ensure_user_rules_file(data_dir: Path) -> Path:
    """The user rules file, created with an explanatory header when missing."""
    path = user_rules_file(data_dir)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_USER_RULES_HEADER, encoding="utf-8")
    return path


def user_rules_text(data_dir: Path) -> str:
    """The rule lines of the user rules file, comments and blanks dropped."""
    try:
        raw = _decode(user_rules_file(data_dir).read_bytes())
    except OSError:
        return ""
    lines = []
    for line in raw.splitlines():
        stripped = line.strip().strip("\t")
        if stripped and not stripped.startswith(("'", "#")):
            lines.append(line)
    if lines:
        log.info("Rule lines in the User Rules file: %d", len(lines))
    return "\n".join(lines)


def _with_user_rules(text: str, data_dir: Path) -> str:
    """The published rules followed by the user's (VB ``ReadFile``)."""
    extra = user_rules_text(data_dir)
    return f"{text.rstrip()}\n{extra}\n" if extra else text


def fetch_rules_text(http, version: int = RULES_VERSION) -> str:
    """Download the rules from the first host that answers ("" if none do)."""
    for name, url in rules_urls(version):
        try:
            response = http.get(url, allow_redirects=True)
        except Exception as ex:  # offline, DNS, TLS — try the standby
            log.info("Download rules unavailable from %s: %s", name, ex)
            continue
        if not getattr(response, "ok", False):
            log.info("Download rules unavailable from %s: HTTP %s", name, response.status)
            continue
        text = getattr(response, "text", "") or _decode(getattr(response, "content", b""))
        if text.strip():
            log.info("Download rules read from %s", name)
            return text
    return ""


def load_rules(
    data_dir: Path,
    http=None,
    *,
    refresh: bool = False,
    version: int = RULES_VERSION,
) -> DownloadRules:
    """The download rules, fetching a fresh copy when the cache is stale.

    ``refresh`` forces a fetch regardless of the cache's age. With no ``http``
    the network is not touched at all, which is what tests and every offline
    caller want.
    """
    data_dir = Path(data_dir)
    stale = refresh or _cache_age(data_dir, version) > CACHE_MAX_AGE
    if http is not None and stale:
        text = fetch_rules_text(http, version)
        # NIT fetches its Module Data IFO table from the same site; refresh it too.
        from vaultkeeper.game.module_data import fetch_module_data

        fetch_module_data(http, data_dir)
        if text:
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                cache_file(data_dir, version).write_text(text, encoding="utf-8")
            except OSError as ex:  # a read-only store still gets today's rules
                log.warning("Could not cache the download rules: %s", ex)
            return DownloadRules.from_text(_with_user_rules(text, data_dir))

    text = _cached_text(data_dir, version) or bundled_rules_text(version)
    return DownloadRules.from_text(_with_user_rules(text, data_dir))
