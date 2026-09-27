"""A mod name from a raw archive name (VB ``ModPasteInfo.ModNameFromFile``).

Archives are usually named for machines — ``angel_falls_prelude_v24.7z``,
``8191_overrides.7z`` — and NIT turns them into names for people: "Angel Falls
Prelude v24", "8191 Overrides". It does so with LazWorks ``ToSentence``, whose
CamelCase splitter also damages names that were already clean ("Tales of Arterra
( EE)", "The  Aielund  Saga"; logic audit N2). This port applies NIT's word rules
to raw names only and leaves a name that already reads like one as it is.
"""

from __future__ import annotations

import re

#: Words NIT leaves in lower case (VB ``Case "to", "a", "from", "the", "of"``).
_SMALL_WORDS = {"to", "a", "from", "the", "of"}

#: Packager and game acronyms NIT upper-cases.
_ACRONYMS = {"cep", "cpp", "ctp", "csp", "cmp", "nwn", "nwncq", "gui"}

#: A version word: v24, v1.72, v2.x.
_VERSION = re.compile(r"v\d[\w.]*", re.IGNORECASE)

#: A part number in Roman numerals, I to XXXIX. NIT upper-cases any word made
#: only of the letters I V X L C D M, which catches "mix", "dim" and "civil" too;
#: series are numbered in the low numbers, so this keeps the intent without those.
_ROMAN = re.compile(r"x{0,3}(ix|iv|v?i{0,3})")

#: Project Q archives are named q<version> (VB: "q" + numeric → "Project Q v…").
_PROJECT_Q = re.compile(r"q(\d+(?:\.\d+)*)", re.IGNORECASE)


def is_raw_name(name: str) -> bool:
    """Whether ``name`` still reads like a file name: underscores, or no capitals."""
    return "_" in name or name == name.lower()


def mod_name_from_file(stem: str) -> str:
    """The mod name NIT would give an archive or folder called ``stem``.

    ``angel_falls_prelude_v24`` → "Angel Falls Prelude v24"; ``q22`` → "Project
    Q v22"; ``cep_2.65_haks`` → "CEP 2.65 Haks". A name that is already clean
    ("Tales of Arterra (EE)") is returned unchanged.
    """
    name = " ".join((stem or "").replace("_", " ").split())
    if not name:
        return stem
    quest = _PROJECT_Q.fullmatch(name)
    if quest:
        return f"Project Q v{quest.group(1)}"
    if not is_raw_name(stem):
        return name
    if " " not in name:
        # One word: capitalised, as ToSentence leaves it ("Winterwildlands055").
        return name[:1].upper() + name[1:]

    words = []
    for word in name.split(" "):
        low = word.lower()
        if low in _SMALL_WORDS:
            words.append(low)
        elif low in _ACRONYMS:
            words.append(word.upper())
        elif _VERSION.fullmatch(word):
            words.append(low)
        elif _ROMAN.fullmatch(low):
            words.append(word.upper())
        else:
            words.append(word[:1].upper() + word[1:])
    sentence = " ".join(words)
    return sentence[:1].upper() + sentence[1:]
