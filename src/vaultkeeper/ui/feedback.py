"""Reporting a problem: a pre-filled issue on the project.

Two things make a bug report useful, and both are things people reasonably fail
to supply: which version, and what they were running it on. Neither is a secret
and both are known here, so they are filled in rather than asked for.

Nothing is transmitted. This builds a URL; the browser opens a form the user can
read, edit, or close. That distinction matters — an application that quietly
posts a payload containing paths and versions is doing something the user has
not agreed to, and this is a menu item, not a consent.
"""

from __future__ import annotations

import platform
from urllib.parse import quote

#: Where the code lives. Feedback goes to the project it is about.
REPOSITORY = "https://github.com/yabisiktir/vaultkeeper"

_BODY = """\
<!-- Thanks for reporting. Please replace the italics below. -->

### What happened

*What you did, and what happened instead of what you expected.*

### Steps to reproduce

1. *…*

### Environment

| | |
|---|---|
| Vaultkeeper | {app} |
| Python | {python} |
| Qt (PySide6) | {qt} |
| Platform | {system} |

<!-- If the log helps: Help -> Vaultkeeper Log, and paste or attach it. -->
"""


def app_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("vaultkeeper")
    except PackageNotFoundError:
        from vaultkeeper import __version__

        return __version__


def _qt_version() -> str:
    try:
        from PySide6 import __version__ as pyside

        return pyside
    except Exception:
        return "unknown"


def environment() -> dict[str, str]:
    """What a maintainer always has to ask for.

    Deliberately no paths, no user name, no machine name — a version and an OS
    are enough to reproduce almost anything, and the report is public.
    """
    return {
        "app": app_version(),
        "python": platform.python_version(),
        "qt": _qt_version(),
        "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }


def feedback_body() -> str:
    """The issue body, with the environment already filled in."""
    return _BODY.format(**environment())


def feedback_url(repository: str = REPOSITORY) -> str:
    """A ``new issue`` URL for this project, pre-filled.

    Left untitled on purpose: a title someone wrote themselves says what the
    problem is, and a placeholder one tends to survive to the issue list.
    """
    return (
        f"{repository}/issues/new"
        f"?labels={quote('feedback')}"
        f"&body={quote(feedback_body(), safe='')}"
    )
