"""Tests for logging setup and the message-history throttle."""

from __future__ import annotations

import logging
from pathlib import Path

from vaultkeeper.core.log import configure_logging, get_logger
from vaultkeeper.core.message_history import MessageHistory


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


def test_message_history_throttle(tmp_path: Path) -> None:
    hist = MessageHistory(path=tmp_path / "mh.json")
    key = "anneal.null_conflict"
    assert hist.should_display(key, max_times=2)
    hist.record(key)
    assert hist.should_display(key, max_times=2)  # shown once, limit 2
    hist.record(key)
    assert not hist.should_display(key, max_times=2)  # limit reached
    assert hist.count(key) == 2


def test_message_history_persists(tmp_path: Path) -> None:
    path = tmp_path / "mh.json"
    MessageHistory(path=path).record("k")
    # Fresh instance reads the persisted count.
    assert MessageHistory(path=path).count("k") == 1


def test_message_history_reset(tmp_path: Path) -> None:
    hist = MessageHistory(path=tmp_path / "mh.json")
    hist.record("a")
    hist.record("b")
    hist.reset("a")
    assert hist.count("a") == 0
    assert hist.count("b") == 1
    hist.reset()
    assert hist.count("b") == 0
