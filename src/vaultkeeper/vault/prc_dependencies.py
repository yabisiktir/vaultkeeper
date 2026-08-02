"""What a PRC-ified module needs, from two sources that can disagree.

Installing one of these means combining:

* the **archive's own build tag** — ``A Call for Heroes [PRC8-CEP3].7z`` says
  this file wants PRC8 and CEP3;
* the **Vault page** for the module, whose "Required projects" field lists
  everything else it needs — tilesets, haks, override content.

They are not interchangeable. The Vault page describes the *original* module;
the archive is a rebuild. So where both name something from the same family and
disagree — the page says CEP 2.65, the file name says CEP3 — the file name is
about the thing actually being installed and the page is about its ancestor.

That is a good reason to prefer the archive, and not a good enough reason to
decide silently: the tag is three characters written by hand by whoever
published the folder, and a wrong CEP is a broken install. So a disagreement
becomes a :class:`Choice` the user resolves, with the archive's answer marked as
recommended. Everything the two sources agree on, or that only one of them
mentions, is settled without asking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Families we can recognise well enough to notice a disagreement within one.
#: Anything else is compared by its normalised name, so two spellings of the
#: same tileset still match but unrelated projects never collide.
#: ``\b`` is wrong here: there is no word boundary between the "p" of CEP and
#: the "3" of CEP3, so ``^cep\b`` matched "CEP 3" and missed "CEP3" — putting two
#: spellings of one answer in different families and agreeing with itself twice.
#: A lookahead for a letter is the real test: it admits CEP, CEP3 and CEP 2.65
#: while leaving a word that merely starts with those letters alone.
_FAMILIES = (
    ("PRC", re.compile(r"^prc(?![a-z])|player.?resource", re.IGNORECASE)),
    ("CEP", re.compile(r"^cep(?![a-z])|community.?expansion", re.IGNORECASE)),
)


def family_of(name: str) -> str:
    """The dependency family a requirement belongs to (``"CEP"``, ``"PRC"``, …)."""
    text = (name or "").strip()
    for family, pattern in _FAMILIES:
        if pattern.search(text):
            return family
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass(frozen=True)
class Requirement:
    """One thing the module needs, and where we learned of it."""

    name: str
    source: str  # "archive" (the build tag) or "vault" (the page)
    url: str = ""

    @property
    def family(self) -> str:
        return family_of(self.name)


@dataclass(frozen=True)
class Choice:
    """A family the two sources disagree about — the user picks."""

    family: str
    options: tuple[Requirement, ...]
    recommended: Requirement

    @property
    def question(self) -> str:
        return (
            f"{self.family}: the archive is built for "
            f"{self._named('archive')}, but the Vault page for this module lists "
            f"{self._named('vault')}."
        )

    def _named(self, source: str) -> str:
        names = [r.name for r in self.options if r.source == source]
        return ", ".join(names) if names else "none"


@dataclass
class Plan:
    """Everything to install, plus whatever the user still has to settle."""

    agreed: list[Requirement] = field(default_factory=list)
    choices: list[Choice] = field(default_factory=list)

    @property
    def settled(self) -> bool:
        return not self.choices

    def resolve(self, picks: dict[str, str]) -> list[Requirement]:
        """The final list, given ``{family: chosen name}`` for each choice.

        A family left unanswered falls back to the recommendation rather than
        being dropped — a missing dependency breaks the install, and the
        recommendation is the archive's own tag.
        """
        out = list(self.agreed)
        for choice in self.choices:
            wanted = picks.get(choice.family)
            chosen = next(
                (o for o in choice.options if o.name == wanted), choice.recommended
            )
            out.append(chosen)
        return out


def merge(archive_tags, vault_required) -> Plan:
    """Combine an archive's build tags with a Vault page's required projects.

    ``archive_tags`` is a sequence of names (``("PRC8", "CEP3")``);
    ``vault_required`` the ``[{"title", "url"}, …]`` the scraper returns.
    """
    from_archive = [Requirement(str(t), "archive") for t in (archive_tags or ()) if t]
    from_vault = [
        Requirement(str(p.get("title", "")).strip(), "vault", str(p.get("url", "")))
        for p in (vault_required or ())
        if str(p.get("title", "")).strip()
    ]

    grouped: dict[str, list[Requirement]] = {}
    for requirement in [*from_archive, *from_vault]:
        grouped.setdefault(requirement.family, []).append(requirement)

    plan = Plan()
    for family, members in grouped.items():
        archive = [m for m in members if m.source == "archive"]
        vault = [m for m in members if m.source == "vault"]
        if not archive or not vault:
            # Only one source knows about it — nothing to disagree about.
            plan.agreed.extend(_dedupe(members))
            continue
        if _same(archive, vault):
            plan.agreed.append(archive[0])  # the archive's spelling, arbitrarily
            continue
        plan.choices.append(
            Choice(family, tuple(_dedupe(members)), recommended=archive[0])
        )
    return plan


def _same(left: list[Requirement], right: list[Requirement]) -> bool:
    """Whether two sides name the same thing, ignoring spacing and case.

    ``CEP3`` and ``CEP 3`` are the same answer written differently; ``CEP3`` and
    ``CEP 2.65`` are not.
    """
    return _keys(left) == _keys(right)


def _keys(items: list[Requirement]) -> set[str]:
    return {re.sub(r"[^a-z0-9]+", "", i.name.lower()) for i in items}


def _dedupe(items: list[Requirement]) -> list[Requirement]:
    seen: set[str] = set()
    out: list[Requirement] = []
    for item in items:
        key = re.sub(r"[^a-z0-9]+", "", item.name.lower())
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
