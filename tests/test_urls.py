"""Tests for the URL validation helpers (core/urls.py)."""

from __future__ import annotations

import pytest

from vaultkeeper.core.urls import check_scheme, is_url


def test_check_scheme_prepends_http_to_www():
    assert check_scheme("www.example.com") == "http://www.example.com"
    assert check_scheme("WWW.Example.com") == "http://WWW.Example.com"
    # An explicit scheme is left untouched.
    assert check_scheme("https://x.org") == "https://x.org"
    assert check_scheme("example.com") == "example.com"


@pytest.mark.parametrize(
    "link",
    [
        "https://neverwintervault.org/project/nwn1/cep",
        "http://example.com",
        "www.example.com",  # scheme inferred
        "ftp://files.example.com/x",
    ],
)
def test_is_url_accepts_web_addresses(link):
    assert is_url(link)


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        "not a url",
        "example.com",  # bare host without www. / scheme (VB New Uri throws)
        "/local/path/file.txt",
        "C:\\Users\\me\\file.txt",
        "mailto:someone@example.com",  # not a web page scheme
    ],
)
def test_is_url_rejects_non_web(link):
    assert not is_url(link)
