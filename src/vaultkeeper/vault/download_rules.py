"""DownloadRules — the Neverwinter Vault download-rules engine (VB ``VaultDownloadRules``).

The rules are a section-based text file (fetched/cached by NIT) that drives how mods
are downloaded from the Vault: save-name mappings (consumed by GameMapper), filename
prefixes, excluded extensions, URL redirects, unsupported projects, etc. Section-header
lines (matching the ``_STATEMENTS`` table) switch parsing state; inside a section,
``From``/``To`` pairs build maps and bare lines add list entries.

This is a headless port of the parser + accessors — the file is *injected* as text
(no paths/network coupling), so it is fully testable. The web-scraping / download
workflow (VaultScraper, DownloadProject) build on top of this later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Default characters stripped from save names (VB ``SaveNameRemovedChars``).
DEFAULT_REMOVED_CHARS = "()&"

#: The Vault's API, as the rules file ships it. These are *defaults* only — the
#: point of the rules carrying them is that the Vault can move its API without
#: anyone shipping a new Vaultkeeper, so the parsed values always win.
DEFAULT_API_URL = "https://neverwintervault.org/api/v1/"
DEFAULT_API_BY_URL = "projects/by-url?url="
DEFAULT_API_BY_ID = "projects/"
DEFAULT_API_BY_FID = "files/by-fid"
DEFAULT_API_SEARCH_BY_TITLE = "projects/by-title?title="

#: Query appended to a by-id request to ask for the project's description. NIT
#: holds this in its NwVault assembly rather than in the rules file, so it is a
#: constant here too.
API_FULL_DESCRIPTION = "?include_description=1"


@dataclass
class ApiEndpoints:
    """Where the Vault's API lives and how each query is spelled.

    A value straight out of the rules file: ``base`` is absolute, the rest are
    fragments appended to it (VB ``NwVault.Definitions.Api*``).
    """

    base: str = DEFAULT_API_URL
    by_url: str = DEFAULT_API_BY_URL
    by_id: str = DEFAULT_API_BY_ID
    by_fid: str = DEFAULT_API_BY_FID
    search_by_title: str = DEFAULT_API_SEARCH_BY_TITLE

    def query(self, fragment: str) -> str:
        """``base`` + ``fragment``, with exactly one slash between them."""
        return f"{self.base.rstrip('/')}/{fragment.lstrip('/')}"

#: Section-header line -> internal section id (subset of the VB ``Statements`` map).
_STATEMENTS: dict[str, str] = {
    "GameSaveNameMap": "save_names",
    "End GameSaveNameMap": "reset",
    "PrefixFilenames": "prefixes",
    "End PrefixFilenames": "reset",
    "Extensions": "extensions",
    "End Extensions": "reset",
    "NoInstallerProjects": "no_installer",
    "End NoInstallerProjects": "reset",
    "Redirects": "redirects",
    "End Redirects": "reset",
    "UnsupportedProjects": "unsupported",
    "End UnsupportedProjects": "reset",
}


def _keyword_param(line: str, keyword: str) -> str:
    """Text after a ``<keyword> `` prefix (VB ``GetKeywordParameter``)."""
    return line[len(keyword):].strip()


def _equals_param(line: str) -> str:
    """Text after the first ``=`` (VB ``GetEqualsParameter``)."""
    _, _, rest = line.partition("=")
    return rest.strip()


@dataclass
class DownloadRules:
    """Parsed Vault download rules (the subset the port currently uses)."""

    save_name_rules: dict[str, str] = field(default_factory=dict)
    save_name_removed_chars: str = DEFAULT_REMOVED_CHARS
    prefix_filenames: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    no_installer_projects: list[str] = field(default_factory=list)
    redirects: dict[str, str] = field(default_factory=dict)
    unsupported_urls: list[str] = field(default_factory=list)
    message_lines: list[str] = field(default_factory=list)
    #: URL query key that marks a download counter link (VB ``FileIdPrefix``).
    file_id_prefix: str = ""
    #: The Vault API addresses this rules file specifies (defaults when it says
    #: nothing, so an old cached file still leaves a usable client).
    api: ApiEndpoints = field(default_factory=ApiEndpoints)
    #: ``RevisionNumber`` — bumped by whoever edits the published rules. Shown so
    #: a user can tell which rules are in force; 0 when the file omits it.
    revision: int = 0

    # -- Parsing ----------------------------------------------------------- #
    @classmethod
    def from_text(cls, text: str) -> DownloadRules:
        """Parse the rules-file text into a :class:`DownloadRules`."""
        rules = cls()
        section = "reset"
        from_name = ""
        from_url = ""
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in "'#;":  # blank / comment
                continue
            if line in _STATEMENTS:
                section = _STATEMENTS[line]
                from_name = from_url = ""
                continue
            if line.lower().startswith("savenameremovedchars"):
                rules.save_name_removed_chars = _equals_param(line)
                continue
            if line.lower().startswith("fileidprefix"):
                rules.file_id_prefix = _equals_param(line)
                continue
            if rules._settle_keyword(line):
                continue

            if section == "save_names":
                from_name = rules._from_to(line, from_name, rules.save_name_rules)
            elif section == "redirects":
                from_url = rules._from_to(line, from_url, rules.redirects)
            elif section == "prefixes":
                rules.prefix_filenames.append(line)
            elif section == "extensions":
                rules.exclude_extensions.append(line.lower())
            elif section == "no_installer":
                rules.no_installer_projects.append(line)
            elif section == "unsupported":
                low = line.lower()
                if low.startswith(("http", "ftp")):
                    rules.unsupported_urls.append(line)
                else:
                    rules.message_lines.append(line)
        return rules

    def _settle_keyword(self, line: str) -> bool:
        """Apply a top-level ``Keyword = value`` line; True when one was recognised.

        Only the keywords the port acts on. The rest of the file — 224 per-project
        blocks giving each Vault project its mod folder and group — is not parsed
        here, and unknown lines are left to the section handling below.
        """
        key, sep, _ = line.partition("=")
        if not sep:
            return False
        name = key.strip().lower()
        value = _equals_param(line)
        if name == "apiurl":
            self.api.base = value
        elif name == "apibyurl":
            self.api.by_url = value
        elif name == "apibyid":
            self.api.by_id = value
        elif name == "apibyfid":
            self.api.by_fid = value
        elif name == "apisearchbytitle":
            self.api.search_by_title = value
        elif name == "revisionnumber":
            try:
                self.revision = int(value)
            except ValueError:
                self.revision = 0
        else:
            return False
        return True

    @staticmethod
    def _from_to(line: str, pending: str, target: dict[str, str]) -> str:
        """Handle a ``From``/``To`` pair line; returns the new pending ``From`` key."""
        if line.lower().startswith("from"):
            return _keyword_param(line, "From")
        if line.lower().startswith("to"):
            value = _keyword_param(line, "To")
            if pending and pending not in target:
                target[pending] = value
            return ""
        return pending

    # -- Accessors --------------------------------------------------------- #
    def is_prefix_filename(self, filename: str) -> bool:
        """True if ``filename`` starts with a known download prefix."""
        low = filename.lower()
        return any(low.startswith(p.lower()) for p in self.prefix_filenames)

    def is_excluded_extension(self, extension: str) -> bool:
        """True if ``extension`` (with or without the dot) is excluded."""
        ext = extension.lower()
        return ext in self.exclude_extensions or ext.lstrip(".") in (
            e.lstrip(".") for e in self.exclude_extensions
        )

    def is_unsupported(self, url: str) -> bool:
        """True if ``url`` is listed as an unsupported project."""
        low = url.lower()
        return any(low == u.lower() or low.startswith(u.lower()) for u in self.unsupported_urls)

    def create_installer(self, project_title: str) -> bool:
        """False if the project is flagged as not-installer (VB ``CreateInstaller``)."""
        return project_title not in self.no_installer_projects

    def formatted_url(self, url: str) -> str:
        """Normalise a URL for comparison (VB ``FormattedUrl``)."""
        return url.strip()

    def get_final_url(self, url: str) -> str:
        """Apply any configured redirect for ``url`` (VB ``GetFinalUrl``)."""
        url = self.formatted_url(url)
        return self.redirects.get(url, url)
