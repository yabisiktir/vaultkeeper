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
