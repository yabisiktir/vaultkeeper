"""Noticing when Google Drive answers a download with a page instead of the file."""

from __future__ import annotations

import pytest

from vaultkeeper.vault.drive_download import (
    DriveDownloadError,
    confirm_url,
    describe_page,
    fetch,
    filename_from,
    is_page,
    looks_like_archive,
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


# -- fetching ---------------------------------------------------------------- #
def test_an_archive_lands_under_the_name_drive_suggests(tmp_path):
    """The measured case: the folder's largest modules serve bytes immediately."""
    archive = b"7z\xbc\xaf\x27\x1c" + b"payload"
    response = HttpResponse(
        download_url(FILE_ID), 200,
        {"Content-Type": "application/octet-stream",
         "Content-Disposition": 'attachment; filename="A Call for Heroes [PRC8-CEP3].7z"'},
        content=archive,
    )
    result = fetch(_client(response), FILE_ID, tmp_path)
    assert result.filename == "A Call for Heroes [PRC8-CEP3].7z"
    assert result.path.read_bytes() == archive
    assert result.size == len(archive)


def test_nothing_is_held_in_memory_to_decide_what_arrived(tmp_path):
    """The whole point: an 83 MB archive is judged on disk, by its first bytes.

    Deciding from a buffered body would mean holding the file to find out whether
    it *is* the file — which for a big download is how an application dies rather
    than how a download fails.
    """
    archive = b"7z\xbc\xaf\x27\x1c" + b"\x00" * 4096
    client = _client(HttpResponse(
        download_url(FILE_ID), 200, {"Content-Type": "application/octet-stream"},
        content=archive,
    ))
    seen: list[tuple[int, int]] = []
    result = fetch(client, FILE_ID, tmp_path, on_chunk=lambda d, t: seen.append((d, t)))
    assert result.path.read_bytes() == archive
    assert seen  # progress was reported while it streamed
    assert [c for c in client.calls] == [("GET", download_url(FILE_ID))]  # fetched once


def test_a_confirmation_page_is_followed_rather_than_saved(tmp_path):
    confirmed = (
        "https://drive.usercontent.google.com/download"
        f"?id={FILE_ID}&export=download&confirm=t"
    )
    archive = b"7z\xbc\xaf\x27\x1c" + b"real"
    client = FakeHttpClient({
        download_url(FILE_ID): HttpResponse(
            download_url(FILE_ID), 200, {"Content-Type": "text/html"},
            content=CONFIRM_HTML.encode(),
        ),
        confirmed: HttpResponse(
            confirmed, 200, {"Content-Type": "application/octet-stream"}, content=archive
        ),
    })
    result = fetch(client, FILE_ID, tmp_path, fallback_name="heroes.7z")
    assert result.path.read_bytes() == archive
    assert result.filename == "heroes.7z"


def test_a_quota_page_raises_and_leaves_nothing_on_disk(tmp_path):
    """Trusting the 200 would leave a web page named .7z, found only much later."""
    response = HttpResponse(
        download_url(FILE_ID), 200, {"Content-Type": "text/html"},
        content=QUOTA_HTML.encode(),
    )
    with pytest.raises(DriveDownloadError, match="too many times"):
        fetch(_client(response), FILE_ID, tmp_path, fallback_name="heroes.7z")
    assert list(tmp_path.iterdir()) == []


def test_a_page_with_no_content_type_is_still_caught_by_its_first_byte(tmp_path):
    response = HttpResponse(
        download_url(FILE_ID), 200, content=b"<html>Sign in with accounts.google.com</html>"
    )
    with pytest.raises(DriveDownloadError, match="shared publicly"):
        fetch(_client(response), FILE_ID, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_refused_request_says_so(tmp_path):
    with pytest.raises(DriveDownloadError, match="404"):
        fetch(FakeHttpClient({}), FILE_ID, tmp_path)


# -- the suggested name ------------------------------------------------------ #
def test_the_filename_comes_from_the_content_disposition():
    assert filename_from('attachment; filename="A Call for Heroes [PRC8-CEP3].7z"') == (
        "A Call for Heroes [PRC8-CEP3].7z"
    )
    assert filename_from("") == ""
