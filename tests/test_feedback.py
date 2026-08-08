"""Send Feedback: where it goes and what it carries.

It used to draft an email to the original author's personal address. The tests
that matter here are the ones about *what is disclosed* and *what is sent*: a
public issue body should carry a version and an OS, and nothing that identifies
the machine or the person.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from vaultkeeper.ui import feedback


def _query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_it_points_at_this_project_not_the_original_author():
    """Surazal maintains NIT, not this port, and never agreed to support it."""
    url = feedback.feedback_url()
    assert url.startswith("https://github.com/yabisiktir/vaultkeeper/issues/new")
    assert "mailto:" not in url
    assert "lazweb" not in url and "surazal" not in url.lower()


def test_the_environment_is_filled_in_because_it_is_always_asked_for():
    body = _query(feedback.feedback_url())["body"]
    env = feedback.environment()
    for value in env.values():
        assert value in body
    assert "Steps to reproduce" in body


def test_nothing_identifying_is_disclosed():
    """The report is public. A version and an OS reproduce almost anything."""
    import getpass
    import platform

    body = feedback.feedback_body().lower()
    for secret in (getpass.getuser(), platform.node()):
        if secret and len(secret) > 2:
            assert secret.lower() not in body


def test_no_placeholder_title_survives_into_the_issue_list():
    assert "title" not in _query(feedback.feedback_url())


def test_it_is_labelled_so_it_can_be_found():
    assert _query(feedback.feedback_url())["labels"] == "feedback"


def test_the_body_survives_url_encoding_intact():
    from urllib.parse import unquote

    body = _query(feedback.feedback_url())["body"]
    assert unquote(body) == body  # parse_qs already decoded it
    assert "| Vaultkeeper |" in body  # the table came through


def test_a_different_repository_can_be_pointed_at():
    url = feedback.feedback_url("https://example.invalid/o/r")
    assert url.startswith("https://example.invalid/o/r/issues/new")


def test_the_version_is_reported_even_when_the_package_is_not_installed(monkeypatch):
    import importlib.metadata as md

    def boom(_name):
        raise md.PackageNotFoundError

    monkeypatch.setattr(md, "version", boom)
    assert feedback.app_version()  # falls back to __version__, never raises
