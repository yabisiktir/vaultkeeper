"""Character Restorers — keeping the character you played a mod with.

A Restorer is a mod whose payload is a copy of files already installed, so they
can be put back later. A *Character* Restorer is one holding ``.bic`` files:
the character builds you used, saved alongside the mod they belong to, so that
reinstalling or moving on does not lose them.

The files it adopts are the ones **no mod owns**. A character you rolled in the
game is installed in the user folder and belongs to nothing Vaultkeeper put
there, which is exactly what marks it as yours rather than a mod's.

Grouping is the part with judgement in it. Neverwinter Nights numbers a
character's files — ``Aribeth.bic``, ``Aribeth1.bic``, ``Aribeth2.bic`` — so the
trailing digits are stripped to find the character behind them, and each
character becomes one restorer. Where every unowned file turns out to be one
character, the mod being played names it; where there are several, only the user
can say which belongs to what.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Character files, as the mapper names the extension.
CHARACTER_EXTENSION = ".bic"

#: Default prefix for a generated restorer's name (VB
#: ``ConfigCharacterRestorerPrefix``). The hyphen is the original's convention,
#: and it sorts these together above ordinary mods.
DEFAULT_PREFIX = "-"


@dataclass(frozen=True)
class CharacterGroup:
    """One character and every file belonging to it."""

    name: str
    #: ``FileKeyInfo`` for each of that character's installed files.
    files: tuple

    @property
    def count(self) -> int:
        return len(self.files)


def base_name(filename: str) -> str:
    """The character behind a numbered file name (VB ``GetCharacterList``).

    ``Aribeth2.bic`` → ``Aribeth``. A name that is *all* digits keeps its digits;
    stripping them would leave nothing to call the restorer.
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    trimmed = stem.rstrip("0123456789")
    return trimmed or stem


def group_characters(file_keys) -> list[CharacterGroup]:
    """Unowned character files gathered per character, in a stable order."""
    buckets: dict[str, list] = {}
    for key in file_keys:
        buckets.setdefault(base_name(key.filename), []).append(key)
    return [
        CharacterGroup(name, tuple(files))
        for name, files in sorted(buckets.items(), key=lambda kv: kv[0].lower())
    ]


def restorer_name(prefix: str, character: str) -> str:
    """What the restorer mod is called.

    The prefix is glued straight on when it is punctuation — "-Aribeth" is the
    original's own convention and reads better than "- Aribeth" — and separated
    by a space when it is a word.
    """
    prefix = (prefix or "").strip()
    if not prefix:
        return character
    if prefix[-1].isalnum():
        return f"{prefix} {character}"
    return f"{prefix}{character}"
