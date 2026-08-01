"""Logging setup — one place, stdlib ``logging`` (no third-party logger).

The old port had a loguru/stdlib split brain; Vaultkeeper standardises on stdlib
``logging``. This configures a rotating file handler under the OS cache dir plus
an optional console handler, and exposes :func:`get_logger` for modules to use.
The VB app's ``db.Log``/``ui.InfoLog`` status-text concept is a UI concern and is
layered on top later; this module is the plumbing.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from vaultkeeper.app_paths import cache_root

_CONFIGURED = False
_LOG_NAME = "vaultkeeper"

#: Loggers belonging to the packages Vaultkeeper sits on. They name themselves so
#: they can be used without Vaultkeeper; when it *is* running, their output
#: belongs in its log alongside everything else.
ADOPTED_LOGGERS = ("nwnfile",)


def log_file_path() -> Path:
    return cache_root() / "logs" / "vaultkeeper.log"


def configure_logging(
    *,
    level: int = logging.INFO,
    to_console: bool = True,
    log_path: Path | None = None,
) -> None:
    """Configure Vaultkeeper's logger once (idempotent).

    Safe to call from the app entry point; repeated calls are no-ops so tests and
    re-entry don't stack handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger = logging.getLogger(_LOG_NAME)
    logger.setLevel(level)
    logger.propagate = False

    path = log_path or log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if to_console:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

    # The packages Vaultkeeper is built on log under their own names, so that they
    # carry no dependency on any particular application's logging. Attaching the
    # same handlers keeps their lines in Vaultkeeper's log where they were before.
    for name in ADOPTED_LOGGERS:
        adopted = logging.getLogger(name)
        adopted.setLevel(level)
        adopted.propagate = False
        for handler in logger.handlers:
            adopted.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of Vaultkeeper's logger (e.g. ``get_logger(__name__)``)."""
    if name is None or name == _LOG_NAME:
        return logging.getLogger(_LOG_NAME)
    return logging.getLogger(_LOG_NAME).getChild(name)
