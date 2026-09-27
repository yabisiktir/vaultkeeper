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

import copy
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

#: Edition/version conditions a ``Project`` block can make its lines depend on
#: (VB ``If NWN Downloads`` … ``If ERF Downloads``), by the header's middle word.
_CONDITIONS = {"nwn": "nwn", "ee": "ee", "1.69": "1.69", "1.68": "1.68", "erf": "erf"}

#: Keywords that, inside a condition, name something other than a file (VB
#: ``ExternalKeywords``: the file is fetched from that address, not the Vault).
_EXTERNAL_KEYWORDS = ("externalfile", "rolovaultfile")


@dataclass
class ProjectRule:
    """What the published rules say about one Vault project.

    The rules file carries 224 of these. They are how a download knows it should
    land in "CEP v3.x" under "100.  Community Packs" rather than in a folder
    named after the page title, and which of a project's eleven attachments are
    the ones you actually want.

    Parts of a block depend on the game (VB ``If EE Downloads`` / ``If NWN
    Downloads`` / ``If 1.69`` / ``If 1.68`` / ``If ERF``): the Community Patch
    lives in a different folder and ships a different archive for each edition.
    Those lines are kept in :attr:`conditionals` and folded in by :meth:`for_game`;
    ask that for the rule that applies to a profile.
    """

    title: str = ""
    #: The mod folder this project belongs in (VB ``ModFolder``).
    mod_folder: str = ""
    #: The group that folder belongs to (VB ``Group``).
    group: str = ""
    #: Files never offered for download — superseded hotfixes, stray readmes.
    excludes: list[str] = field(default_factory=list)
    #: When non-empty, the only files ticked by default (VB ``Downloads``).
    downloads: list[str] = field(default_factory=list)
    #: Prerequisite project pages the Vault page itself does not list.
    required_projects: list[str] = field(default_factory=list)
    #: False when the block says ``IgnoreExcludes``: none of the exclusions
    #: (this project's, the file-type or description ones) hold anything back.
    apply_excludes: bool = True
    #: Extensions offered even though the rules exclude them everywhere else.
    include_extensions: list[str] = field(default_factory=list)
    #: Direct file links among the prerequisites that are not wanted.
    exclude_direct_links: list[str] = field(default_factory=list)
    #: Prerequisite projects (by title) the Vault lists but this one does not need.
    exclude_required_projects: list[str] = field(default_factory=list)
    #: Per-file prerequisites (VB ``RequiredFiles From <project>``): of that
    #: prerequisite, only these files — keyed by its lowercased title.
    required_files: dict[str, list[str]] = field(default_factory=dict)
    #: Files fetched from an address outside the Vault project (VB ``ExternalFile``).
    external_files: list[str] = field(default_factory=list)
    #: Game-dependent lines in file order, as (condition, line); see :meth:`for_game`.
    conditionals: list[tuple[str, str]] = field(default_factory=list)
    #: The block's install-wizard lines (``WizardTitle`` … ``End SelectMany``),
    #: in the wizard file's own syntax; empty when the project has none.
    wizard_text: str = ""

    def merge(self, other: ProjectRule) -> None:
        """Fold a second block for the same project into this one.

        The published file names two projects twice, and in both cases the two
        blocks carry *different* keys — one gives "The Speaker in Dreams" its mod
        folder and the other its excludes. Taking whichever came last would
        quietly drop half of each, so they are combined instead.
        """
        for name in ("mod_folder", "group", "wizard_text"):
            if not getattr(self, name):
                setattr(self, name, getattr(other, name))
        for name in (
            "excludes",
            "downloads",
            "required_projects",
            "include_extensions",
            "exclude_direct_links",
            "exclude_required_projects",
            "external_files",
        ):
            existing = getattr(self, name)
            known = {value.lower() for value in existing}
            existing.extend(v for v in getattr(other, name) if v.lower() not in known)
        self.apply_excludes = self.apply_excludes and other.apply_excludes
        for key, names in other.required_files.items():
            self.required_files.setdefault(key, []).extend(names)
        self.conditionals.extend(other.conditionals)

    def for_game(
        self, *, is_ee: bool, nwn_version: str = "1.69", exclude_erf: bool = True
    ) -> ProjectRule:
        """This rule as it applies to one game (VB ``ReadFile`` → ``AddConditional``).

        NIT decides each ``If`` block while reading the file, for the profile it
        was opened for; here the file is read once and each profile asks. On
        Enhanced Edition NIT treats the version as 1.69. An ``If ERF`` block names
        files that are only wanted when ``.erf`` files are installed: with the
        default "exclude ERF" mapping they are held back, otherwise they join the
        wanted files — but only when the project has a ``Downloads`` list at all.
        """
        rule = copy.deepcopy(self)
        rule.conditionals = []
        met = {"ee" if is_ee else "nwn", "1.69" if is_ee else (nwn_version or "1.69")}
        for condition, line in self.conditionals:
            if condition == "erf":
                if exclude_erf:
                    rule.excludes.append(line)
                elif rule.downloads:
                    rule.downloads.append(line)
                continue
            if condition not in met:
                continue
            key, sep, value = line.partition("=")
            keyword = key.strip().lower()
            if sep and keyword == "modfolder":
                rule.mod_folder = value.strip()
            elif sep and keyword in _EXTERNAL_KEYWORDS:
                url = value.strip()
                if keyword == "rolovaultfile":
                    url = url.replace("ftp:", "https:")
                rule.external_files.append(url)
                # Named in the wanted list too, or the whitelist would drop it.
                rule.downloads.append(external_filename(url))
            else:
                rule.downloads.append(line)
        return rule

    def is_excluded(self, filename: str) -> bool:
        low = (filename or "").lower()
        return any(low == name.lower() for name in self.excludes)

    def wanted(self, filename: str) -> bool:
        """Whether this file is offered at all.

        A ``Downloads`` block is a **whitelist**, not a set of ticks: where one
        exists, everything else the project publishes is held back exactly as an
        ``Excludes`` entry would be (VB ``DownloadProject.Methods.vb:735`` sets
        ``vsi.Excluded`` and skips the row). Community Music Pack publishes
        thirty-odd files and names three; the other twenty-seven are not choices.
        """
        if not self.downloads:
            return True
        return (filename or "").lower() in {name.lower() for name in self.downloads}

    def required_files_for(self, *titles: str) -> list[str] | None:
        """The only files wanted from a prerequisite, if this rule names them.

        A prerequisite is known by more than one title — the one the Vault gives
        it, the one its address suggests — so any of them may match.
        """
        for title in titles:
            names = self.required_files.get((title or "").strip().lower())
            if names is not None:
                return names
        return None


def external_filename(url: str) -> str:
    """The file name an external download will have (its last path segment)."""
    from urllib.parse import unquote, urlsplit

    return unquote(urlsplit(url).path.rsplit("/", 1)[-1])


#: ``Key = value`` lines inside a ``Project`` block that this port acts on.
_PROJECT_VALUES = {"modfolder": "mod_folder", "group": "group"}

#: List blocks inside a ``Project`` block, by their opening word.
_PROJECT_BLOCKS = {
    "excludes": "excludes",
    "downloads": "downloads",
    "requiredprojects": "required_projects",
    "includeextensions": "include_extensions",
    "excludedirectlinks": "exclude_direct_links",
    "excluderequiredprojects": "exclude_required_projects",
    "externalfiles": "external_files",
    "rolovaultfiles": "external_files",
}

#: Wizard keywords (VB ``WizardInfo.C``). Their lines are kept verbatim for the
#: wizard parser; the ones that open a list are closed by their own ``End``.
_WIZARD_BLOCKS = ("selectone", "selectmany", "installerexcludes")
_WIZARD_LINES = ("wizardtitle", "extractarchives")


def _parse_project(title: str, lines: list[str], index: int) -> tuple[ProjectRule, int]:
    """Read one ``Project = …`` block; returns the rule and the line after it.

    Deliberately forgiving. The rules are published by someone else and edited by
    hand — the file in front of me opens ``Excludes`` sixty-nine times and closes
    ``End Exclude`` twice — so a sub-block ends at *any* ``End`` line, and the
    project itself always ends at ``End Project``. A typo then costs one block
    rather than swallowing the rest of the file.
    """
    rule = ProjectRule(title=title.strip())
    #: What the lines of the open block go to: a field name, ("if", condition),
    #: ("required", title), "wizard", or "" for a block this port swallows.
    collecting: str | tuple[str, str] | None = None
    wizard: list[str] = []
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line[0] in "'#;":
            continue
        low = line.lower()
        if low == "end project":
            break
        if low.startswith("end "):
            if collecting == "wizard":
                wizard.append(line)
            collecting = None
            continue
        if collecting is not None:
            if collecting == "wizard":
                wizard.append(line)
            elif isinstance(collecting, tuple):
                kind, name = collecting
                if kind == "if":
                    rule.conditionals.append((name, line))
                else:
                    rule.required_files.setdefault(name, []).append(line)
            elif collecting:  # "" means a block this port swallows whole
                target = getattr(rule, collecting)
                if collecting == "external_files":
                    line = line.replace("ftp:", "https:")
                if line.lower() not in {v.lower() for v in target}:
                    target.append(line)
            continue
        words = low.split()
        if words[0] == "if" and len(words) >= 2:
            # "If EE Downloads" … "End If": only for that edition or version.
            collecting = ("if", _CONDITIONS.get(words[1], f"?{words[1]}"))
            continue
        if low == "ignoreexcludes":
            rule.apply_excludes = False
            continue
        if low.startswith("requiredfiles"):
            # "RequiredFiles From <project>": only these files of that prerequisite.
            name = line[len("requiredfiles"):].strip()
            if name.lower().startswith("from "):
                name = name[5:]
            collecting = ("required", name.strip().lower())
            continue
        keyword = low.partition("=")[0].strip()
        if keyword in _WIZARD_LINES:
            wizard.append(line)
            continue
        if keyword in _WIZARD_BLOCKS:
            wizard.append(line)
            collecting = "wizard"
            continue
        key, sep, _ = line.partition("=")
        if sep:
            field_name = _PROJECT_VALUES.get(key.strip().lower())
            if field_name:
                setattr(rule, field_name, _equals_param(line))
            continue
        # A bare word opens a sub-block. Any this port does not know is still
        # entered, so its contents are swallowed rather than mistaken for the
        # project's own keys.
        collecting = _PROJECT_BLOCKS.get(words[0], "")
    rule.wizard_text = "\n".join(wizard)
    return rule, index


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
    "VaultProjectTypes": "project_types",
    "End VaultProjectTypes": "reset",
    "ExceptionUrls": "exception_urls",
    "End ExceptionUrls": "reset",
    "ExcludeRules": "reset",
    "End ExcludeRules": "reset",
    "Contains": "contains",
    "End Contains": "reset",
    "StartsWith": "starts_with",
    "End StartsWith": "reset",
    "EndsWith": "ends_with",
    "End EndsWith": "reset",
    "End ExcludeFiles": "reset",
}
#: The same, looked up case-insensitively as NIT does (``Option Compare Text``).
_STATEMENTS_LOWER = {k.lower(): v for k, v in _STATEMENTS.items()}


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
    #: What a Vault project address looks like (VB ``VaultDomain`` /
    #: ``OldVaultDomain`` / ``RoloVaultDomain``). Scheme-less on purpose — the
    #: rules match on the host and path, not on http vs https.
    vault_domain: str = "//neverwintervault.org/project"
    old_vault_domain: str = "//neverwintervault.net/project"
    rolovault_domain: str = "//neverwintervault.org/rolovault"
    #: The game segments a project URL may carry (``nwn1``, ``nwnee``).
    vault_project_types: list[str] = field(default_factory=list)
    #: Vault project pages that do not follow the standard URL shape.
    exception_urls: list[str] = field(default_factory=list)
    #: Mod-name prefixes to drop before searching the Vault for a title
    #: (VB ``FindLinkIgnorePrefixes``: cmp, ctp, cpp — packager initials).
    find_link_ignore_prefixes: list[str] = field(default_factory=list)
    #: Per-project rules, keyed by lowercased project title (see
    #: :class:`ProjectRule`). 224 of them in the published file.
    projects: dict[str, ProjectRule] = field(default_factory=dict)
    #: Files held back per project, keyed by lowercased title (VB ``ExcludeFiles``,
    #: from ``ExcludeFiles From <project>``). Applies to projects with no
    #: ``Project`` block too — a test module, a trailer, a superseded zip.
    exclude_files: dict[str, list[str]] = field(default_factory=dict)
    #: File *descriptions* that mark a file as not wanted (VB ``ExcludeContains``
    #: / ``ExcludeStartsWith`` / ``ExcludeEndsWith``): "outdated", "Mac ", " old".
    exclude_contains: list[str] = field(default_factory=list)
    exclude_starts_with: list[str] = field(default_factory=list)
    exclude_ends_with: list[str] = field(default_factory=list)

    # -- Parsing ----------------------------------------------------------- #
    @classmethod
    def from_text(cls, text: str) -> DownloadRules:
        """Parse the rules-file text into a :class:`DownloadRules`."""
        rules = cls()
        section = "reset"
        from_name = ""
        from_url = ""
        exclude_project = ""
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            index += 1
            if not line or line[0] in "'#;":  # blank / comment
                continue
            if line.lower().startswith("project ="):
                rule, index = _parse_project(_equals_param(line), lines, index)
                if rule.title:
                    key = rule.title.lower()
                    known = rules.projects.get(key)
                    if known is None:
                        rules.projects[key] = rule
                    else:
                        known.merge(rule)
                continue
            if line.lower() in _STATEMENTS_LOWER:
                section = _STATEMENTS_LOWER[line.lower()]
                from_name = from_url = exclude_project = ""
                continue
            if line.lower().startswith("excludefiles"):
                # "ExcludeFiles From <project>" … "End ExcludeFiles".
                name = line[len("excludefiles"):].strip()
                if name.lower().startswith("from "):
                    name = name[5:]
                exclude_project = name.strip().lower()
                section = "exclude_files"
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
            elif section == "project_types":
                rules.vault_project_types.append(line)
            elif section == "exception_urls":
                rules.exception_urls.append(line)
            elif section == "exclude_files":
                rules.exclude_files.setdefault(exclude_project, []).append(line)
            elif section == "contains":
                rules.exclude_contains.append(line.strip('"'))
            elif section == "starts_with":
                rules.exclude_starts_with.append(line.strip('"'))
            elif section == "ends_with":
                rules.exclude_ends_with.append(line.strip('"'))
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
        elif name == "vaultdomain":
            self.vault_domain = value
        elif name == "oldvaultdomain":
            self.old_vault_domain = value
        elif name == "rolovaultdomain":
            self.rolovault_domain = value
        elif name == "findlinkignoreprefixes":
            self.find_link_ignore_prefixes = [
                p.strip() for p in value.split(",") if p.strip()
            ]
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

    def is_description_excluded(self, description: str) -> bool:
        """True when a file's description marks it as not wanted (VB ``IsDescriptionExcluded``).

        "Outdated", "(Mac)", "old version", "Do not use": the Vault has no field
        for a superseded file, so authors say it in the description.
        """
        text = (description or "").lower()
        return (
            any(text.startswith(p.lower()) for p in self.exclude_starts_with)
            or any(text.endswith(p.lower()) for p in self.exclude_ends_with)
            or any(p.lower() in text for p in self.exclude_contains)
        )

    def is_excluded(
        self,
        title: str,
        filename: str,
        description: str = "",
        rule: ProjectRule | None = None,
    ) -> bool:
        """True when the rules hold this file of this project back (VB ``IsExcluded``).

        Three reasons, in NIT's order: the project names the file
        (``ExcludeFiles From`` or the project's own ``Excludes``); its type is
        excluded everywhere (``.txt``) and the project does not take it back
        with ``IncludeExtensions``; or its description says it is obsolete.
        A project that says ``IgnoreExcludes`` is the caller's to honour. Pass
        ``rule`` when it has been settled for a game (:meth:`rule_for_game`).
        """
        low = (filename or "").lower()
        key = (title or "").strip().lower()
        if rule is None:
            rule = self.projects.get(key)
        named = list(self.exclude_files.get(key, []))
        if rule is not None:
            named += rule.excludes
        if any(low == n.lower() for n in named):
            return True
        ext = "." + low.rsplit(".", 1)[1] if "." in low else ""
        if ext and self.is_excluded_extension(ext):
            taken_back = rule is not None and any(
                ext == e.lower() or ext.lstrip(".") == e.lower().lstrip(".")
                for e in rule.include_extensions
            )
            if not taken_back:
                return True
        return self.is_description_excluded(description)

    def rule_for_game(
        self, title: str, *, is_ee: bool, nwn_version: str = "1.69", exclude_erf: bool = True
    ) -> ProjectRule | None:
        """:meth:`project_rule` with its game-dependent lines settled for one game."""
        rule = self.project_rule(title)
        if rule is None:
            return None
        return rule.for_game(is_ee=is_ee, nwn_version=nwn_version, exclude_erf=exclude_erf)

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

    def project_rule(self, title: str) -> ProjectRule | None:
        """The published rule for a project title, if there is one."""
        return self.projects.get((title or "").strip().lower())

    def is_vault_project_url(self, url: str) -> bool:
        """True if ``url`` addresses a Vault project page (VB ``IsValidVaultUrl``).

        A project page is ``<vault domain>/<game>/…`` for one of the game types
        the rules name, plus the handful of pages listed as exceptions because
        they predate that shape.
        """
        low = (url or "").strip().lower()
        if not low:
            return False
        if any(low == e.strip().lower() for e in self.exception_urls):
            return True
        domains = [d for d in (self.vault_domain, self.old_vault_domain) if d]
        types = self.vault_project_types or ["nwn1", "nwnee"]
        return any(
            f"{domain.lower()}/{kind.lower()}" in low
            for domain in domains
            for kind in types
        )

    def is_rolovault_url(self, url: str) -> bool:
        """True if ``url`` points into the Rolo Vault archive (VB ``IsRolovaultUrl``).

        A live address, but not a project page — the archive was never migrated,
        so these have no API record and have to be looked up by name instead.
        """
        domain = (self.rolovault_domain or "").lower()
        return bool(domain) and domain in (url or "").lower()

    def get_final_url(self, url: str) -> str:
        """Apply any configured redirect for ``url`` (VB ``GetFinalUrl``)."""
        url = self.formatted_url(url)
        return self.redirects.get(url, url)
