"""Tests for the logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from vaultkeeper.core.log import configure_logging, get_logger


def test_get_logger_is_child_of_root() -> None:
    log = get_logger("mymod")
    assert log.name == "vaultkeeper.mymod"
    assert get_logger().name == "vaultkeeper"


def test_configure_logging_writes_file(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "vk.log"
    # Reset the module guard so this test can configure into a temp path.
    import vaultkeeper.core.log as logmod

    logmod._CONFIGURED = False
    logger = get_logger()
    logger.handlers.clear()
    configure_logging(level=logging.DEBUG, to_console=False, log_path=log_path)
    get_logger("t").info("hello world")
    for h in logger.handlers:
        h.flush()
    assert log_path.exists()
    assert "hello world" in log_path.read_text(encoding="utf-8")
