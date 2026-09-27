"""Run a stage-2 scenario in Vaultkeeper, sandboxed, and write snapshots in the
same format as the NIT harness (step<TAB>kind<TAB>key<TAB>value).

Isolation (mirrors the test suite's autouse fixtures): HOME / APPDATA / XDG_* and
``app_paths._home`` point into the sandbox, and ``send2trash`` moves files into a
sandbox "recycle-bin" folder instead of the real Trash. A guard aborts if any game
folder resolves outside the sandbox.

First run goes through the app's own path: ``auto_configure_first_run`` with the
same answers NIT got (EE, default group set), then ``answer_player_excludes``.

Usage: python run_vk_scenario.py <scenario.tsv> <outdir>
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALIASES = [
    "CRASHREPORT",
    "MODELCOMPILER",
    "CACHE",
    "NWSYNC",
    "OLDSERVERVAULT",
    "PATCH",
    "DEVELOPMENT",
    "HD0",
    "MODULES",
    "SAVES",
    "OVERRIDE",
    "HAK",
    "SCREENSHOTS",
    "CURRENTGAME",
    "LOGS",
    "TEMP",
    "TEMPCLIENT",
    "LOCALVAULT",
    "DMVAULT",
    "SERVERVAULT",
    "DATABASE",
    "PORTRAITS",
    "AMBIENT",
    "MOVIES",
    "MUSIC",
    "TLK",
]


def build_sandbox(sb: Path) -> dict[str, Path]:
    """Same shape as harness/make_sandbox.sh, POSIX paths in nwn.ini."""
    lib, user = sb / "eelib", sb / "user"
    (lib / "bin/win32").mkdir(parents=True)
    (lib / "data/nwm").mkdir(parents=True)
    (lib / "ovr").mkdir()
    (lib / "bin/win32/nwmain.exe").write_bytes(b"")
    (lib / "data/nwm/Chapter1.nwm").write_bytes(b"")
    user.mkdir()
    lines = ["[Alias]"]
    for a in ALIASES:
        if a == "HD0":
            lines.append(f"HD0={user}")
            continue
        (user / a.lower()).mkdir()
        lines.append(f"{a}={user / a.lower()}")
    for extra in ("erf", "nwm", "texturepacks"):
        (user / extra).mkdir(exist_ok=True)
    (user / "nwn.ini").write_text("\r\n".join(lines) + "\r\n")
    (user / "nwnplayer.ini").write_bytes(b"")
    for d in ("home", "store", "bin", "fx"):
        (sb / d).mkdir()
    subprocess.run([sys.executable, str(HERE / "make_fixtures.py"), str(sb / "fx")], check=True)
    shutil.copytree(sb / "fx/preexisting", user, dirs_exist_ok=True)
    return {
        "lib": lib,
        "user": user,
        "store": sb / "store",
        "home": sb / "home",
        "bin": sb / "bin",
        "fixtures": sb / "fx/fixtures",
    }


def isolate(p: dict[str, Path]) -> None:
    home = p["home"]
    os.environ["HOME"] = str(home)
    for name, sub in (
        ("APPDATA", "Roaming"),
        ("LOCALAPPDATA", "Local"),
        ("XDG_CONFIG_HOME", ".config"),
        ("XDG_DATA_HOME", ".local/share"),
        ("XDG_CACHE_HOME", ".cache"),
    ):
        os.environ[name] = str(home / sub)
    import send2trash

    import vaultkeeper.app_paths as ap

    ap._home = lambda: home

    def to_bin(path) -> None:
        src = Path(path)
        target = p["bin"] / src.name
        n = 1
        while target.exists():
            target = p["bin"] / f"{src.name} ({n})"
            n += 1
        shutil.move(str(src), str(target))

    send2trash.send2trash = to_bin


def snapshot(out, step: str, p: dict[str, Path], ctl, status: str) -> None:
    def w(kind: str, key: str, value: str) -> None:
        clean = (value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
        out.write(f"{step}\t{kind}\t{key}\t{clean}\n")

    for kind, root in (("game", p["user"]), ("lib", p["lib"])):
        for f in sorted(root.rglob("*"), key=lambda x: str(x).lower()):
            if f.is_file():
                data = f.read_bytes()
                w(
                    kind,
                    f.relative_to(root).as_posix(),
                    data.decode("latin-1") if len(data) < 200 else f"len={len(data)}",
                )
    mods_dir = ctl.ctx.profile_mods_dir
    for f in sorted(mods_dir.rglob("*"), key=lambda x: str(x).lower()):
        if f.is_file():
            rel = f.relative_to(mods_dir).as_posix()
            data = f.read_bytes()
            w(
                "store",
                rel,
                data.decode("latin-1")
                if len(data) < 200 and not rel.endswith(".rtf")
                else f"len={len(data)}",
            )
    pd = ctl.pd
    for name, md in pd.mod_list.items() if hasattr(pd, "mod_list") else []:
        if md.is_group_item:
            continue
        w(
            "mod",
            md.mod_name or name,
            f"group={md.group};installed={md.installed};installState={md.install_state.name};"
            f"modState={md.mod_state.name};deps={','.join(sorted(md.dependencies))}",
        )
    for fk, fd in pd.file_list.items():
        w("filedata", fk.full_key, repr(fd))
    w("status", "info", status)
    out.flush()


def main() -> None:
    script, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    sb = Path(tempfile.mkdtemp(prefix="vk_sb_", dir=outdir))
    p = build_sandbox(sb)
    isolate(p)
    log = (outdir / "vk_run.log").open("w")
    try:
        from vaultkeeper.ui.first_run import FirstRunChoices
        from vaultkeeper.ui.session import auto_configure_first_run

        choices = FirstRunChoices(
            game_root=str(p["lib"]), store_root=str(p["store"]), game_user_path=str(p["user"])
        )
        ctl = auto_configure_first_run(choices=choices, discover=lambda: [])
        if ctl is None:
            sys.exit("first run returned no controller")
        for name, path in ctl.ctx.game_folders.items():
            if sb not in Path(path).parents and Path(path) != sb:
                sys.exit(f"ABORT: game folder {name} outside sandbox: {path}")
        log.write(f"first run: {ctl.answer_player_excludes(player=True)}\n")
        # app.py start-up: NIT's managed restorers (VB RunAutoRestorers on first activation).
        log.write(f"auto restorers: {ctl.run_auto_restorers()}\n")

        with (outdir / "vk_snaps.tsv").open("w", encoding="utf-8") as out:
            snapshot(out, "00 start", p, ctl, "")
            n = 0
            for raw in script.read_text().splitlines():
                if not raw.strip() or raw.startswith("#"):
                    continue
                a = raw.split("\t")
                # "@stem" = the mod VK creates from a pasted source of that name (verbatim stem)
                a = [x[1:] if x.startswith("@") else x for x in a]
                op, lst = a[0], ([x.lstrip("@") for x in a[1].split("|")] if len(a) > 1 else [])
                n += 1
                step = f"{n:02d} {raw.replace(chr(9), ' ')}"
                status = ""
                try:
                    if op == "paste":
                        r = ctl.paste_mod_sources([p["fixtures"] / m for m in lst])
                        status = r.get("message", "")
                    elif op == "create_installer":
                        # Same sequence as MainWindow._on_create_installer (no wizard here).
                        from vaultkeeper.config.settings import load_settings

                        msgs = []
                        for m in lst:
                            was_installed = ctl._mod_installed(m)
                            r = ctl.build_installer_payload(m)
                            msgs.append(r.get("message", ""))
                            if r.get("ok"):
                                if load_settings().install_after_create:
                                    if not was_installed:
                                        ctl.install([m])
                                elif ctl._settings().installer_restore and was_installed:
                                    ctl.install([m])
                        status = " | ".join(msgs)
                    elif op == "set_dependency":
                        status = str(ctl.set_mod_dependencies(a[1], [a[2]]))
                    elif op == "install":
                        status = ctl.install(lst)
                    elif op == "uninstall":
                        status = ctl.uninstall(lst)
                    elif op == "edit_mod":
                        f = ctl.ctx.profile_mods_dir / a[1] / a[2]
                        if a[3] == "DELETE":
                            f.unlink()
                        else:
                            f.parent.mkdir(parents=True, exist_ok=True)
                            f.write_text(a[3])
                    elif op == "create_restorer":
                        # MainWindow._on_create_restorer: back up unowned files under a name.
                        status = ctl.create_restorer_from_installed(a[1])["message"]
                    elif op == "external_delete":
                        (p["user"] / a[1]).unlink()
                    elif op == "external_write":
                        (p["user"] / a[1]).write_text(a[2])
                    elif op == "rescan":
                        status = ctl.rescan_installed_state()
                    else:
                        status = f"unknown op {op}"
                except Exception:
                    tb = traceback.format_exc()
                    log.write(f"STEP {step} FAILED\n{tb}\n")
                    out.write(f"{step}\terror\t{op}\t{tb.strip().splitlines()[-1]}\n")
                log.write(f"STEP {step}: {status}\n")
                snapshot(out, step, p, ctl, str(status))
    finally:
        log.close()
        if not os.environ.get("KEEP_SB"):
            shutil.rmtree(sb, ignore_errors=True)


if __name__ == "__main__":
    main()
