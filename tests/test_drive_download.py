"""Noticing when Google Drive answers a download with a page instead of the file."""

from __future__ import annotations

import pytest

from vaultkeeper.vault.drive_download import (
    DriveDownloadError,
    confirm_url,
    describe_page,
    filename_from,
    is_page,
    looks_like_archive,
    resolve,
)
from vaultkeeper.vault.drive_folder import download_url
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse

FILE_ID = "1hWSQvwh319UV9t1xuG5tsfDvONK3o4nU"

CONFIRM_HTML = """
<html><body><form id="download-form" action="https://drive.usercontent.google.com/download">
<input type="hidden" name="id" value="1hWSQvwh319UV9t1xuG5tsfDvONK3o4nU">
<input type="hidden" name="export" value="download">
<input type="hidden" name="confirm" value="t">
</form></body></html>
"""

QUOTA_HTML = "<html><body><p>Sorry, you can't view or download this file at this time.</p>\
<p>Too many users have viewed or downloaded this file recently. Quota exceeded.</p></body></html>"


def _client(response: HttpResponse) -> FakeHttpClient:
    return FakeHttpClient({download_url(FILE_ID): response})


# -- telling bytes from a page ------------------------------------------------ #
def test_an_archive_is_recognised_by_its_magic():
    assert looks_like_archive(b"7z\xbc\xaf\x27\x1c\x00\x04")
    assert looks_like_archive(b"PK\x03\x04rest")
    assert not looks_like_archive(b"<!DOCTYPE html>")
    assert not looks_like_archive(b"")


def test_html_is_detected_by_content_type_or_by_its_first_byte():
    """All three Drive failures arrive as HTTP 200 with HTML."""
    assert is_page("text/html; charset=utf-8")
    assert is_page("application/octet-stream", b"  <html>")
    assert not is_page("application/octet-stream", b"7z\xbc\xaf\x27\x1c")


# -- saying why -------------------------------------------------------------- #
def test_a_quota_page_is_explained_as_a_quota_page():
    assert "too many times" in describe_page(QUOTA_HTML)


def test_a_sign_in_page_says_sharing_changed():
    assert "shared publicly" in describe_page(
        "<html><a href='https://accounts.google.com/signin'>Sign in</a></html>"
    )


def test_an_unrecognised_page_still_says_something_useful():
    assert "page instead of the file" in describe_page("<html>odd</html>")


# -- getting past the confirmation ------------------------------------------- #
def test_the_confirm_form_becomes_a_url():
    url = confirm_url(CONFIRM_HTML)
    assert url.startswith("https://drive.usercontent.google.com/download?")
    assert "confirm=t" in url and f"id={FILE_ID}" in url


def test_a_bare_confirm_token_is_also_handled():
    """Drive has used both shapes; only one of them is a form."""
    url = confirm_url('<a href="/uc?export=download&confirm=abc123&id=x">Download</a>', FILE_ID)
    assert "confirm=abc123" in url and FILE_ID in url


def test_a_page_with_no_way_forward_yields_no_url():
    assert confirm_url(QUOTA_HTML) == ""


# -- resolving --------------------------------------------------------------- #
def test_bytes_resolve_to_the_plain_download_url():
    """The measured case: the folder's largest modules serve bytes immediately."""
    response = HttpResponse(
        download_url(FILE_ID), 200,
        {"Content-Type": "application/octet-stream",
         "Content-Disposition": 'attachment; filename="A Call for Heroes [PRC8-CEP3].7z"',
         "Content-Length": "72026148"},
    )
    result = resolve(_client(response), FILE_ID, head=b"7z\xbc\xaf\x27\x1c")
    assert result.url == download_url(FILE_ID)
    assert result.filename == "A Call for Heroes [PRC8-CEP3].7z"
    assert result.size == 72026148


def test_a_confirmation_page_is_followed_rather_than_saved():
    response = HttpResponse(
        download_url(FILE_ID), 200, {"Content-Type": "text/html"}, CONFIRM_HTML
    )
    assert "confirm=t" in resolve(_client(response), FILE_ID).url


def test_a_quota_page_raises_instead_of_writing_html_as_a_7z():
    """Trusting the 200 would leave a web page on disk named .7z."""
    response = HttpResponse(
        download_url(FILE_ID), 200, {"Content-Type": "text/html"}, QUOTA_HTML
    )
    with pytest.raises(DriveDownloadError, match="too many times"):
        resolve(_client(response), FILE_ID)


# -- the suggested name ------------------------------------------------------ #
def test_the_filename_comes_from_the_content_disposition():
    assert filename_from('attachment; filename="A Call for Heroes [PRC8-CEP3].7z"') == (
        "A Call for Heroes [PRC8-CEP3].7z"
    )
    assert filename_from("") == ""
