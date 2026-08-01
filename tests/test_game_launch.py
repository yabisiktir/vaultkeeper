"""Tests for cross-platform NWN launch command building."""

from __future__ import annotations

from pathlib import Path

from nwnfile.locations import HostOS

from vaultkeeper.game.game_launch import launch_argv, resolve_executable


def _make_bin(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith(".app"):
        p.mkdir()
    else:
        p.write_bytes(b"\x7fELF")
    return p


def test_resolve_macos_bundle(tmp_path):
    _make_bin(tmp_path, "bin/macos/nwmain.app")
    exe = resolve_executable(tmp_path, HostOS.MACOS)
    assert exe is not None and exe.name == "nwmain.app"


def test_resolve_linux_x86_and_arm(tmp_path):
    _make_bin(tmp_path, "bin/linux-arm64/nwmain-linux")
    exe = resolve_executable(tmp_path, HostOS.LINUX)
    assert exe is not None and "arm64" in str(exe)


def test_resolve_missing_is_none(tmp_path):
    assert resolve_executable(tmp_path, HostOS.WINDOWS) is None


def test_macos_bundle_argv_with_user_dir(tmp_path):
    _make_bin(tmp_path, "bin/macos/nwmain.app")
    argv = launch_argv(
        tmp_path, host=HostOS.MACOS, user_dir=Path("/Users/x/Documents/NWN")
    )
    assert argv[0] == "open"
    assert argv[1].endswith("nwmain.app")
    assert "--args" in argv
    assert "-userDirectory" in argv


def test_linux_direct_argv(tmp_path):
    exe = _make_bin(tmp_path, "bin/linux-x86/nwmain-linux")
    argv = launch_argv(tmp_path, host=HostOS.LINUX, user_dir=Path("/home/x/.local/nwn"))
    assert argv == [str(exe), "-userDirectory", "/home/x/.local/nwn"]


def test_steam_fallback_when_no_executable(tmp_path):
    argv = launch_argv(tmp_path, host=HostOS.MACOS, steam_app_id="704450")
    assert argv == ["open", "steam://run/704450"]


def test_no_executable_no_steam_is_empty(tmp_path):
    assert launch_argv(tmp_path, host=HostOS.LINUX) == []


def test_prefer_steam_over_direct(tmp_path):
    _make_bin(tmp_path, "bin/win32/nwmain.exe")
    argv = launch_argv(
        tmp_path, host=HostOS.WINDOWS, steam_app_id="704450", prefer_steam=True
    )
    assert argv == ["cmd", "/c", "start", "", "steam://run/704450"]


def test_toolset_resolution(tmp_path):
    _make_bin(tmp_path, "bin/macos/nwtoolset.app")
    exe = resolve_executable(tmp_path, HostOS.MACOS, toolset=True)
    assert exe is not None and exe.name == "nwtoolset.app"


def test_run_binary_resolves_mac_bundle_inner(tmp_path):
    from vaultkeeper.game.game_launch import run_binary

    inner = tmp_path / "bin/macos/nwmain.app/Contents/MacOS/nwmain"
    inner.parent.mkdir(parents=True)
    inner.write_bytes(b"\x00")
    got = run_binary(tmp_path, HostOS.MACOS)
    assert got == inner


def test_wait_argv_uses_inner_binary_on_mac(tmp_path):
    inner = tmp_path / "bin/macos/nwmain.app/Contents/MacOS/nwmain"
    inner.parent.mkdir(parents=True)
    inner.write_bytes(b"\x00")
    argv = launch_argv(
        tmp_path, host=HostOS.MACOS, user_dir=Path("/u/nwn"), wait=True
    )
    # Direct binary (not "open"), so QProcess can await exit.
    assert argv[0] == str(inner)
    assert argv[0] != "open"
    assert "-userDirectory" in argv


def test_run_binary_none_when_bundle_missing_inner(tmp_path):
    from vaultkeeper.game.game_launch import run_binary

    (tmp_path / "bin/macos/nwmain.app").mkdir(parents=True)  # bundle without binary
    assert run_binary(tmp_path, HostOS.MACOS) is None
