"""Reading the PRC-ified modules folder on Google Drive."""

from __future__ import annotations

from vaultkeeper.vault.drive_folder import (
    DriveEntry,
    DriveFolder,
    build_tags,
    file_id,
    folder_id,
    is_module_archive,
    listing_url,
    module_title,
    parse_folder,
)
from vaultkeeper.vault.http import FakeHttpClient, HttpResponse

#: Real ``embeddedfolderview`` markup, trimmed. Its shape is the whole point:
#: a row nests several ``</div>`` before its title.
FOLDER_HTML = """
<div class="flip-entries">
<div class="flip-entry" id="entry-1zxholh5LK" tabindex="0" role="link">
 <div class="flip-entry-info">
  <a href="https://drive.google.com/drive/folders/1zxholh5LK" target="_blank">
   <div class="flip-entry-visual"><div class="flip-entry-visual-card">
    <div class="flip-entry-icon"><div aria-label="Folder" class="x"></div></div>
   </div></div>
   <div class="flip-entry-title">Base Modules</div>
  </a>
 </div>
</div>
<div class="flip-entry" id="entry-1hWSQvwh31" tabindex="0" role="link">
 <div class="flip-entry-info">
  <a href="https://drive.google.com/file/d/1hWSQvwh31/view?usp=drive_web">
   <div class="flip-entry-visual"><div class="flip-entry-visual-card">
    <div class="flip-entry-icon"><div aria-label="7z" class="x"></div></div>
   </div></div>
   <div class="flip-entry-title">A Call for Heroes [PRC8-CEP3].7z</div>
  </a>
 </div>
</div>
</div>
"""


# -- parsing the listing ------------------------------------------------------ #
def test_a_row_is_read_despite_the_divs_nested_before_its_title():
    """Matching a row's closing tag stops inside the icon markup and finds no name.

    An earlier version did exactly that and parsed the real folder as empty.
    """
    entries = parse_folder(FOLDER_HTML)
    assert [e.name for e in entries] == ["Base Modules", "A Call for Heroes [PRC8-CEP3].7z"]


def test_folders_and_files_are_told_apart_by_their_link():
    folder, archive = parse_folder(FOLDER_HTML)
    assert folder.is_folder and not archive.is_folder
    assert folder.folder_url.endswith("1zxholh5LK")
    assert folder.download_url == ""
    assert "id=1hWSQvwh31" in archive.download_url


def test_an_unparseable_page_yields_nothing_rather_than_half_a_folder():
    assert parse_folder("") == []
    assert parse_folder("<html><body>Sign in</body></html>") == []


def test_a_row_repeated_in_grid_and_list_views_is_counted_once():
    assert len(parse_folder(FOLDER_HTML + FOLDER_HTML)) == 2


# -- what a file name tells us ------------------------------------------------ #
def test_the_title_drops_the_build_tag_and_extension():
    """What is left is what to search the Vault for."""
    assert module_title("A Call for Heroes [PRC8-CEP3].7z") == "A Call for Heroes"
    assert module_title("AL1 - Siege of Shadowdale EE [PRC8].7z") == (
        "AL1 - Siege of Shadowdale EE"
    )


def test_the_build_tag_names_this_archive_s_dependencies():
    """More trustworthy than the Vault page, which describes the *original*."""
    assert build_tags("A Call for Heroes [PRC8-CEP3].7z") == ("PRC8", "CEP3")
    assert build_tags("A Hunt Through the Dark [PRC8].7z") == ("PRC8",)
    assert build_tags("Something Plain.7z") == ()


def test_a_hyphen_in_the_name_is_not_mistaken_for_a_tag_separator():
    assert module_title("AL2 - Crimson Tides of Tethyr EE [PRC8].7z") == (
        "AL2 - Crimson Tides of Tethyr EE"
    )


def test_only_archives_count_as_modules():
    assert is_module_archive(DriveEntry("x", "A Mod [PRC8].7z"))
    assert not is_module_archive(DriveEntry("x", "Base Modules", is_folder=True))
    assert not is_module_archive(DriveEntry("x", "readme.txt"))


# -- ids out of whatever the user pastes -------------------------------------- #
def test_a_folder_id_is_found_in_a_pasted_url():
    assert folder_id(
        "https://drive.google.com/drive/folders/16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA"
    ) == "16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA"


def test_a_bare_id_is_accepted_and_nonsense_is_not():
    assert folder_id("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA")
    assert folder_id("") == ""
    assert folder_id("not a drive link") == ""
    assert listing_url("not a drive link") == ""


def test_a_file_id_is_found_in_a_pasted_file_url():
    assert file_id(
        "https://drive.google.com/file/d/1hWSQvwh319UV9t1xuG5tsfDvONK3o4nU/view?usp=drive_web"
    ) == "1hWSQvwh319UV9t1xuG5tsfDvONK3o4nU"


def test_the_listing_uses_the_embedded_view_not_the_app_page():
    """Drive's own page builds its list in JavaScript from obfuscated markup."""
    assert "embeddedfolderview" in listing_url("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA")


# -- the folder reader -------------------------------------------------------- #
def _folder(html: str, ok: bool = True) -> DriveFolder:
    url = listing_url("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA")
    response = HttpResponse(url, 200 if ok else 404, {}, html)
    return DriveFolder(FakeHttpClient({url: response}))


def test_modules_are_listed_without_the_subfolders_and_sorted():
    drive = _folder(FOLDER_HTML)
    mods = drive.modules("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA")
    assert [m.title for m in mods] == ["A Call for Heroes"]
    assert [f.name for f in drive.subfolders("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA")] == [
        "Base Modules"
    ]


def test_a_failed_request_is_not_an_exception():
    """Drive is someone else's server; it can be down or ask for a sign-in."""
    assert _folder("", ok=False).list("16p0VI7qPmIV8Zq2MYw6T0niRBEUbrvCA") == []
