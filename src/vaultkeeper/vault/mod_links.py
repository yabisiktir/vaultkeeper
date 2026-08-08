"""Finding and checking a mod's Vault page (VB ``FindLinkFromName`` / ``ValidateModLinks``).

A mod's recorded web link goes stale in ways nothing local can notice: the Vault
migrated off ``neverwintervault.net``, projects were renamed, the Rolo Vault
archive was never migrated at all. The link still looks like a link — it just no
longer leads anywhere.

The interesting part is **how a page is identified**, because a title search is
not enough. "A Call for Heroes" matches three Selendi modules and a music pack,
and no amount of ranking can tell which one an archive came from. NIT's answer,
ported here: search by title, then ask each candidate project what files it
publishes, and keep the ones whose **filenames the mod has already downloaded**.
That is evidence rather than resemblance — the mod folder holds
``almraiven.rar``, and exactly one Vault project publishes a file by that name.

Where the evidence runs out, this returns a *list* and never a decision. One
candidate is an answer; several are a question for the user; none is a "not
found". Guessing attaches the wrong page, and the wrong page is what the next
person downloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from vaultkeeper.vault.download_rules import DownloadRules

#: The mod-folder name NIT recognises as the Project Q archive, which publishes
#: many mods under one page and so never matches by filename the usual way.
PROJECT_Q_ARCHIVE = "Project Q Archive"

#: How many of a search's hits are opened to see what they publish. A search for
#: a common word can return dozens, and each is a request; the ones filed as the
#: same sort of thing as the mod are tried first, so the cut falls on the
#: least-likely.
MAX_PROJECT_LOOKUPS = 15


class Verdict(Enum):
    """What validating one mod's link concluded (VB's five report sections)."""

    OK = "ok"
    #: The Vault answers, but with a different address than the one recorded.
    REVISED = "revised"
    #: A Vault project address the Vault does not recognise.
    INVALID = "invalid"
    #: A live Rolo Vault address — real, but not a project page.
    ROLOVAULT = "rolovault"
    #: An eligible mod with no link recorded at all.
    NO_LINK = "no_link"
    #: A link somewhere else entirely (Nexus, a forum). Left alone.
    NON_VAULT = "non_vault"


#: Report section titles, in the order NIT writes them.
_SECTIONS: tuple[tuple[Verdict, str], ...] = (
    (Verdict.REVISED, "Revised Vault Web Links"),
    (Verdict.ROLOVAULT, "Non-Migrated Rolovault Web Links"),
    (Verdict.INVALID, "Invalid Vault Web Links"),
    (Verdict.NO_LINK, "Mods with no Web Link"),
    (Verdict.NON_VAULT, "Non-Vault Web Links"),
)


@dataclass(frozen=True)
class LinkCandidate:
    """A Vault project page that might be this mod's, and why it might be."""

    title: str
    url: str
    #: ``"files"`` — the page publishes a file the mod holds. Evidence.
    #: ``"title"`` — the page's title *is* the mod's name, and nothing else
    #: matched. Suggestive, and never written without someone agreeing to it.
    matched: str = "files"

    @property
    def is_evidence(self) -> bool:
        return self.matched == "files"


@dataclass(frozen=True)
class ModLinkInput:
    """What deciding a mod's link needs, gathered by the caller.

    Kept separate from ``ModData`` so this module never touches the profile
    store or the filesystem, and so a test can state a case in four lines.
    """

    name: str
    web_link: str = ""
    #: Every file the mod holds, installer payload excluded — the evidence.
    filenames: tuple[str, ...] = ()
    #: Whether the mod installs a ``.mod``/``.nwm``. A module's page is under
    #: ``/module/``; a hakpak's is not, and that halves the candidates.
    is_module: bool = False
    #: Whether a missing link is worth going to look for. A restorer or a
    #: base-game module has no Vault page and never will.
    eligible: bool = True


@dataclass
class LinkFinding:
    """One mod's verdict, and what to do about it."""

    mod: str
    verdict: Verdict
    current: str = ""
    suggested: str = ""
    #: Populated when several pages match and only the user can choose.
    candidates: list[LinkCandidate] = field(default_factory=list)

    @property
    def actionable(self) -> bool:
        """Whether accepting this finding would change the mod's link."""
        return bool(self.suggested) and self.suggested != self.current


def search_name(mod_name: str, rules: DownloadRules | None = None) -> str:
    """A mod folder name reduced to something the Vault might have titled it.

    Users name folders for themselves — "CTP Almraiven v1.2 (EE)" — and the
    Vault titled it "Almraiven". VB strips the packager prefixes the rules list,
    the Enhanced Edition suffix, and special-cases the two collections whose
    folder names never resemble their page titles.
    """
    rules = rules or DownloadRules()
    name = (mod_name or "").strip()
    if name.lower().startswith("cep"):
        # "CEP v3.x" is titled "CEP 3" — the version marks are the difference.
        return name.replace("v", "").replace("3.x", "3")
    if name.lower().startswith("project q v1"):
        return PROJECT_Q_ARCHIVE
    for prefix in rules.find_link_ignore_prefixes:
        if name.lower().startswith(f"{prefix.lower()} "):
            name = name[len(prefix) + 1:].strip()
    if name.lower().endswith(" (ee)"):
        name = name[: -len(" (ee)")].strip()
    return name


def search_names(mod_name: str, rules: DownloadRules | None = None) -> list[str]:
    """Every name worth searching the Vault for, most specific first.

    The Vault matches titles by *containment*, so a folder name carrying one
    word the page does not use returns nothing at all rather than a near miss.
    "Cep 3 Community Expansion Pack" finds nothing; "CEP 3" finds the page —
    because the folder spells out what its own first word already abbreviates.

    So a shorter form is tried when the longer one comes back empty. Order is
    the whole point: the specific name is asked first, and the broader one only
    when there was nothing to lose.
    """
    names: list[str] = []
    for candidate in (search_name(mod_name, rules), _without_spelled_out(mod_name)):
        cleaned = (candidate or "").strip()
        if cleaned and cleaned.lower() not in {n.lower() for n in names}:
            names.append(cleaned)
    return names


def _without_spelled_out(mod_name: str) -> str:
    """Drop a run of words that merely spells out an abbreviation beside it.

    "Cep 3 Community Expansion Pack" → "Cep 3"; "PRC Player Resource
    Consortium" → "PRC". Nothing about CEP is written down here — the rule is
    that a word is redundant when the letters of the words after it spell it.
    """
    words = (mod_name or "").split()
    for index, word in enumerate(words):
        letters = word.strip(".,()-")
        if not letters.isalpha() or not 2 <= len(letters) <= 6:
            continue
        for start in range(index + 1, len(words)):
            run = words[start: start + len(letters)]
            if len(run) < len(letters):
                break
            initials = "".join(part[0] for part in run if part)
            if initials.lower() == letters.lower():
                return " ".join(words[:start] + words[start + len(letters):]).strip()
    return ""


def find_candidates(
    mod: ModLinkInput, api, rules: DownloadRules | None = None
) -> list[LinkCandidate]:
    """Vault pages that might be this mod's, strongest evidence first.

    Files first: a page that publishes a file the mod holds is the mod's page,
    near enough to certain. Where there is no such page, an **exactly** matching
    title is offered instead — because a mod repackaged by someone else has the
    Vault's content under a different filename, which is the commonest way for
    the evidence to be absent while the page plainly exists. Those candidates
    are marked, and never written without a person agreeing to them.
    """
    rules = rules or DownloadRules()
    held = {name.lower() for name in mod.filenames}

    for title in search_names(mod.name, rules):
        hits = api.search_by_title(title)
        if not hits:
            continue  # nothing to weigh; try a broader name
        found = _weigh(hits, mod, api, held, _comparable(title))
        if found:
            return found
    return []


def _weigh(hits, mod: ModLinkInput, api, held: set[str], wanted: str):
    """Sort the search hits into file matches and name matches."""
    by_file: list[LinkCandidate] = []
    by_title: list[LinkCandidate] = []
    for hit in sorted(hits, key=lambda h: not _same_kind(mod, h.link))[:MAX_PROJECT_LOOKUPS]:
        named = _comparable(hit.title) == wanted
        project = api.project_by_id(hit.project_id) if hit.project_id else None
        if project is None:
            continue
        url = hit.link or project.link
        if any((f.filename or "").lower() in held for f in project.files):
            # Evidence outranks the page's filing. CEP 3 ships an optional
            # module among fifteen haks, which makes it look like a module here
            # while the Vault files it under hakpak — and it publishes the very
            # archive sitting in the mod's folder.
            by_file.append(LinkCandidate(hit.title, url, "files"))
        elif named and _same_kind(mod, hit.link):
            # A name alone is weak, so it has to agree about the kind too.
            by_title.append(LinkCandidate(hit.title, url, "title"))
    return _preferred_first(by_file) or _preferred_first(by_title)


def _same_kind(mod: ModLinkInput, link: str) -> bool:
    """Whether a page is filed as the same sort of thing the mod looks like."""
    return mod.is_module == ("/module/" in (link or "").lower())


def _comparable(title: str) -> str:
    """A title reduced to what two names have to share to be the same name."""
    return " ".join((title or "").lower().replace("-", " ").split())


def _preferred_first(candidates: list[LinkCandidate]) -> list[LinkCandidate]:
    """Float a prelude/prologue to the top (VB's own special case).

    A series' first chapter is what someone downloading "the module" almost
    always means, and it sorts alphabetically wherever its title happens to fall.
    """
    marked = [c for c in candidates if _is_prelude(c.title)]
    rest = [c for c in candidates if not _is_prelude(c.title)]
    return marked + sorted(rest, key=lambda c: c.title.lower())


def _is_prelude(title: str) -> bool:
    low = (title or "").lower()
    return "prelude" in low or "prolog" in low


def check_link(
    mod: ModLinkInput, api, rules: DownloadRules | None = None
) -> LinkFinding:
    """Validate one mod's recorded link (VB ``BgProcessLinks``, one iteration)."""
    rules = rules or DownloadRules()
    link = (mod.web_link or "").strip()

    if not link:
        if not mod.eligible:
            return LinkFinding(mod.name, Verdict.OK)
        return _from_candidates(mod, api, rules, Verdict.NO_LINK)

    if rules.is_rolovault_url(link):
        # Live, but the archive was never migrated, so the API has no record of
        # it. The only route to a project page is by name.
        return _from_candidates(mod, api, rules, Verdict.ROLOVAULT, current=link)

    if not rules.is_vault_project_url(link):
        return LinkFinding(mod.name, Verdict.NON_VAULT, current=link)

    project = api.project_by_url(link)
    if project is None:
        return _from_candidates(mod, api, rules, Verdict.INVALID, current=link)
    canonical = project.link or link
    if canonical != link:
        # The page moved — the commonest case being the .net to .org migration.
        return LinkFinding(mod.name, Verdict.REVISED, current=link, suggested=canonical)
    return LinkFinding(mod.name, Verdict.OK, current=link)


def _from_candidates(
    mod: ModLinkInput,
    api,
    rules: DownloadRules,
    fallback: Verdict,
    *,
    current: str = "",
) -> LinkFinding:
    """A finding from whatever the search turned up, or ``fallback`` if nothing.

    One page holding one of the mod's own files is an answer. Anything less —
    several such pages, or a page that only shares the mod's *name* — is a
    question, recorded with its candidates and left for someone to settle. A
    batch that writes a wrong link writes it to a hundred mods at once.
    """
    candidates = find_candidates(mod, api, rules)
    if len(candidates) == 1 and candidates[0].is_evidence:
        return LinkFinding(
            mod.name,
            Verdict.REVISED,
            current=current,
            suggested=candidates[0].url,
            candidates=candidates,
        )
    return LinkFinding(mod.name, fallback, current=current, candidates=candidates)


def validate_links(
    mods, api, rules: DownloadRules | None = None, *, on_progress=None
) -> list[LinkFinding]:
    """Check every mod's link, dropping the ones that need no attention.

    ``on_progress(done, total)`` is called after each mod; it is the only way a
    pass over a few hundred mods, each a web request, says anything while it runs.
    """
    rules = rules or DownloadRules()
    mods = list(mods)
    findings = []
    for index, mod in enumerate(mods, start=1):
        finding = check_link(mod, api, rules)
        if finding.verdict is not Verdict.OK:
            findings.append(finding)
        if on_progress is not None:
            on_progress(index, len(mods))
    return findings


def summary_line(findings: list[LinkFinding], total: int) -> str:
    """The one-line tally NIT puts in the status bar and atop the report."""
    counts = {verdict: 0 for verdict, _ in _SECTIONS}
    for finding in findings:
        if finding.verdict in counts:
            counts[finding.verdict] += 1
    return (
        f"Mod links processed: {total}. "
        f"Revised: {counts[Verdict.REVISED]}. "
        f"Rolovault: {counts[Verdict.ROLOVAULT]}. "
        f"Invalid: {counts[Verdict.INVALID]}. "
        f"No link: {counts[Verdict.NO_LINK]}. "
        f"Non-Vault: {counts[Verdict.NON_VAULT]}."
    )


def report_text(findings: list[LinkFinding], total: int) -> str:
    """The validation report, section by section (VB's report file)."""
    indent = " " * 4
    lines = ["", summary_line(findings, total)]
    for verdict, heading in _SECTIONS:
        rows = [f for f in findings if f.verdict is verdict]
        lines += ["", heading]
        if not rows:
            lines.append(f"{indent}None.")
            continue
        for finding in sorted(rows, key=lambda f: f.mod.lower()):
            if verdict is Verdict.NO_LINK and not finding.candidates:
                lines.append(f"{indent}{finding.mod}")
                continue
            lines.append(f"{indent}{finding.mod}: {finding.current or 'None'}")
            pad = " " * len(finding.mod)
            if finding.suggested:
                lines.append(f"{indent}{pad}  Correct link: {finding.suggested}")
            elif finding.candidates:
                count = len(finding.candidates)
                why = (
                    "matched by name only"
                    if not finding.candidates[0].is_evidence
                    else "possible"
                )
                lines.append(
                    f"{indent}{indent}{count} page{'s' if count != 1 else ''} {why} — "
                    "confirm with Find Mod's Web Page Link:"
                )
                for candidate in finding.candidates:
                    lines.append(f"{indent}{indent}{candidate.title}: {candidate.url}")
    return "\n".join(lines) + "\n"
