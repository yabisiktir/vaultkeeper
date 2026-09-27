"""Vaultkeeper's download selection for Vault projects (logic audit 1c follow-up).

``urls TITLE...``  resolve project titles to Vault URLs (API search by title);
``select FILE``    for each URL in FILE, what the Download Project dialog offers:
                   the mod folder, group, files, and each prerequisite's files.

Runs isolated like the stage-2 runner: HOME / XDG / APPDATA and the app's home
point into a scratch folder, so the real store and settings are never read or
written. Output lines match the NIT harness's ``vault-select``: url, kind, value.
With ``VK_RECORD_DIR`` set, every API response is also saved there (the record).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def isolate() -> Path:
    home = Path(tempfile.mkdtemp(prefix="vk-1c-"))
    os.environ["HOME"] = str(home)
    for name, sub in (
        ("APPDATA", "Roaming"),
        ("LOCALAPPDATA", "Local"),
        ("XDG_CONFIG_HOME", ".config"),
        ("XDG_DATA_HOME", ".local/share"),
        ("XDG_CACHE_HOME", ".cache"),
    ):
        os.environ[name] = str(home / sub)
    import nwnfile.locations as loc

    import vaultkeeper.app_paths as ap

    ap._home = lambda: home
    loc._home = lambda: home
    return home


def controller(home: Path):
    from vaultkeeper.ui.controller import ProfileController

    mods = home / "Profiles" / "P"
    mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=mods,
        game_root=home / "NWN",
        store_path=home / "Data" / "P.json",
        is_ee=True,
    )


class Recording:
    """Wrap the HTTP client and keep every response body (the recorded replies)."""

    def __init__(self, inner, folder: Path) -> None:
        self.inner, self.folder = inner, folder
        folder.mkdir(parents=True, exist_ok=True)

    def get(self, url, **kw):
        r = self.inner.get(url, **kw)
        name = hashlib.sha1(url.encode()).hexdigest()[:16]
        (self.folder / f"{name}.json").write_text(
            json.dumps({"url": url, "status": r.status, "text": r.text}), encoding="utf-8"
        )
        return r

    def __getattr__(self, name):
        return getattr(self.inner, name)


def main() -> None:
    home = isolate()
    c = controller(home)
    c._vault_http()
    if os.environ.get("VK_RECORD_DIR"):
        c._http = Recording(c._http, Path(os.environ["VK_RECORD_DIR"]))
    c.download_rules(refresh=True)  # the live rules, as NIT reads them
    mode, *args = sys.argv[1:]
    if mode == "urls":
        from vaultkeeper.vault.api import VaultApi

        api = VaultApi(c.download_rules(), c._http)
        for title in args:
            found = api.search_by_title(title)
            exact = [f for f in found if f.title.lower() == title.lower()] or found[:1]
            print(f"{title}\t{exact[0].link if exact else ''}")
        return
    for url in Path(args[0]).read_text(encoding="utf-8").split():
        result = c.fetch_vault_project(url)
        print(f"{url}\ttitle\t{result.get('title', '')}")
        folder = result.get("mod_folder") or result.get("title", "")
        print(f"{url}\tmod_folder\t{folder}")
        print(f"{url}\tgroup\t{c.download_group(folder, result.get('group', ''))}")
        for f in result["files"] or []:
            print(f"{url}\tfile\t{f.filename}")
        if not result["files"]:
            print(f"{url}\tfile\t(none)")
        bundles = c.expand_prerequisites(
            result.get("required") or [], project_url=url, project_title=result.get("title", "")
        )
        for req in bundles:
            for f in req.get("files") or []:
                print(f"{url}\treq\t{req.get('title', '')} | {f.filename}")


if __name__ == "__main__":
    main()
