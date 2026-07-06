"""Small text/number/date helpers ported from LazWorks ``Extensions.vb``.

Only the handful of extension methods the play-loop needs are ported here, with
their exact semantics preserved (e.g. ``ToInteger`` returns ``-1`` — not ``0`` —
for non-numeric input, and ``ToPlural``'s suffix pluralisation quirks).
"""

from __future__ import annotations

from datetime import date, datetime

#: LazWorks/.NET invariant date format used by ``ToDateString`` ("dd MMM yyyy").
_DATE_FORMAT = "%d %b %Y"


def to_int(value: str) -> int:
    """LazWorks ``String.ToInteger``: the integer value, or ``-1`` if not numeric."""
    try:
        # VB ``CInt`` on an integer string; floats round, but our inputs are ints.
        return int(round(float(value.strip())))
    except (ValueError, AttributeError):
        return -1


def to_date_string(value: datetime | date) -> str:
    """LazWorks ``Date.ToDateString`` — ``"dd MMM yyyy"`` in the invariant culture."""
    return value.strftime(_DATE_FORMAT)


def parse_date_string(value: str) -> datetime | None:
    """Parse a ``"dd MMM yyyy"`` string back to a ``datetime`` (``None`` on failure)."""
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT)
    except (ValueError, TypeError):
        return None


def to_plural(value: int, suffix: str = "s") -> str:
    """LazWorks ``Integer.ToPlural(suffix)`` — pluralise ``suffix`` for ``value``.

    ``abs(value) == 1`` keeps the singular; a trailing ``y`` (except "day") becomes
    ``ies``; ``ss`` gets ``es``; ``ex`` becomes ``ices``; everything else takes ``s``.
    ``value`` is formatted with thousands separators and no decimals ("#,0").
    """
    number = f"{value:,}"
    if abs(value) == 1:
        return f"{number} {suffix}"
    if suffix != "day" and suffix.endswith("y"):
        return f"{number} {suffix[:-1]}ies"
    if suffix.endswith("ss"):
        return f"{number} {suffix}es"
    if suffix.endswith("ex"):
        return f"{number} {suffix[:-2]}ices"
    return f"{number} {suffix}s"
