"""Related-files access: a mod's docs/walkthroughs and _Downloads are reachable.

Vaultkeeper's Contents pane once listed only installable game files, so a mod's
readme/walkthrough (which live in the mod folder, not the installer) could not be
opened. ``mod_related_files`` restores them (VB FvContents browsed the whole mod
folder); ``uninstall_warnings`` restores NIT's per-mod uninstall confirmations.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import FileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *mods: ModData) -> ProfileController:
    pd = ProfileData()
    for mod in mods:
        pd.add_mod(mod)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_mod_related_files_lists_docs_and_downloads(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    # Loose docs in the mod root (walkthrough is the one people ask for).
    _write(root / "ReadMe.txt")
    _write(root / "Walkthrough.pdf")
    # A downloaded archive under _Downloads.
    _write(root / C.DOWNLOADS_DIR / "pack.zip")
    _write(root / C.DOWNLOADS_DIR / "notes.txt")
    # Noise that must NOT appear: an installer file, a reserved file, a dot-file.
    _write(root / C.MOD_INSTALLER_DIR / "hak" / "a.hak")
    _write(root / C.PLAY_TIME_FILE)
    _write(root / ".hidden.txt")
    # A non-doc loose file in the root is not documentation, so it is excluded.
    _write(root / "installer.exe")

    report = controller.mod_related_files("M")
    labels = [g["folder"] for g in report["folders"]]
    assert labels[0] == "Documentation"  # docs group sorts first
    assert C.DOWNLOADS_DIR in labels

    docs = next(g for g in report["folders"] if g["folder"] == "Documentation")
    doc_names = {f["name"] for f in docs["files"]}
    assert doc_names == {"ReadMe.txt", "Walkthrough.pdf"}
    assert all(g["kind"] == "related" for g in report["folders"])
    # Every related file carries a real, existing absolute path.
    for group in report["folders"]:
        for f in group["files"]:
            assert Path(f["path"]).is_file()

    downloads = next(g for g in report["folders"] if g["folder"] == C.DOWNLOADS_DIR)
    dl_names = {f["name"] for f in downloads["files"]}
    assert dl_names == {"pack.zip", "notes.txt"}  # archives and docs both shown


def test_mod_related_files_none_when_no_folder(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    # No mod folder on disk, and an unknown mod.
    assert controller.mod_related_files("M") == {"folders": [], "count": 0}
    assert controller.mod_related_files("nope") == {"folders": [], "count": 0}


def test_mod_related_files_prunes_installer_subtree(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    root = tmp_path / "mods" / "M"
    # A .txt buried in the installer tree must not be surfaced as documentation.
    _write(root / C.MOD_INSTALLER_DIR / "hak" / "buried.txt")
    _write(root / "real-readme.txt")
    report = controller.mod_related_files("M")
    names = {f["name"] for g in report["folders"] for f in g["files"]}
    assert names == {"real-readme.txt"}


def test_uninstall_warnings_dependants(tmp_path: Path) -> None:
    base = ModData(group="G", mod_name="Base", mod_state=State.INSTALLED)
    dep1 = ModData(group="G", mod_name="Dep1", mod_state=State.INSTALLED)
    dep1.dependencies = ["Base"]
    dep2 = ModData(group="G", mod_name="Dep2", mod_state=State.INSTALLED)
    dep2.dependencies = ["Base"]
    controller = _controller(tmp_path, base, dep1, dep2)
    warn = controller.uninstall_warnings("Base")
    assert warn["dependants"] == 2
    assert warn["campaign"] == ""
    # A mod nothing depends on raises no dependants warning.
    assert controller.uninstall_warnings("Dep1")["dependants"] == 0


def test_uninstall_warnings_campaign_modules(tmp_path: Path) -> None:
    ee = ModData(group="G", mod_name="EEMod", mod_state=State.INSTALLED)
    ee.files = [FileKeyInfo.mod_file("G", "EEMod", "mod\\camp.mod")]
    nwm = ModData(group="G", mod_name="NwmMod", mod_state=State.INSTALLED)
    nwm.files = [FileKeyInfo.mod_file("G", "NwmMod", "nwm\\prem.nwm")]
    controller = _controller(tmp_path, ee, nwm)
    assert (
        controller.uninstall_warnings("EEMod")["campaign"]
        == "modules included in the Enhanced Edition"
    )
    assert controller.uninstall_warnings("NwmMod")["campaign"] == "original campaign modules"


def test_uninstall_warnings_none_for_plain_mod(tmp_path: Path) -> None:
    md = ModData(group="G", mod_name="Plain", mod_state=State.INSTALLED)
    md.files = [FileKeyInfo.mod_file("G", "Plain", "hak\\a.hak")]
    controller = _controller(tmp_path, md)
    # Register the file so folder set is populated the way install would.
    controller.pd.file_list[md.files[0]] = FileData(
        key=md.files[0], file_state=State.INSTALLED, extension=".hak",
        modified=None, byte_size=10,
    )
    warn = controller.uninstall_warnings("Plain")
    assert warn == {"dependants": 0, "campaign": ""}
