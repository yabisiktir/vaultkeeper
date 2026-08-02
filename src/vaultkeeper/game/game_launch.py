"""Game launch — cross-platform NWN launch commands (VB ``NIT.Workers`` Play/Toolset).

The VB app launches Diamond via ``nwmain``/``runas`` and EE via the Steam app id or a
direct executable with ``-userDirectory``. This ports the launch strategy for the
supported hosts, resolving the platform binary under ``bin/<platform>`` and building
the argv (with the per-tool config-isolation ``-userDirectory`` pointing at the game
user dir). The argv builder is pure and tested; the UI layer runs it (``QProcess``)
and, on exit, hands the start/stop times to :meth:`PlayLoop.process_session`.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.locations import HostOS

#: Per-host launcher: (bin subdir, executable name, is a macOS .app bundle).
_EE_LAUNCHER: dict[HostOS, tuple[str, str, bool]] = {
    HostOS.MACOS: ("bin/macos", "nwmain.app", True),
    HostOS.LINUX: ("bin/linux-x86", "nwmain-linux", False),
    HostOS.WINDOWS: ("bin/win32", "nwmain.exe", False),
}
#: The NWN:EE toolset binary per host (bundles/exe alongside the game binary).
_EE_TOOLSET: dict[HostOS, tuple[str, str, bool]] = {
    HostOS.MACOS: ("bin/macos", "nwtoolset.app", True),
    HostOS.LINUX: ("bin/linux-x86", "nwtoolset-linux", False),
    HostOS.WINDOWS: ("bin/win32", "nwtoolset.exe", False),
}
#: On arm64 Linux the binary lives in a different subdir.
_LINUX_ARM = ("bin/linux-arm64", "nwmain-linux", False)


def resolve_executable(
    game_root: Path, host: HostOS, *, toolset: bool = False
) -> Path | None:
    """The platform game (or toolset) executable under ``game_root``, or ``None``."""
    table = _EE_TOOLSET if toolset else _EE_LAUNCHER
    candidates = [table[host]]
    if host is HostOS.LINUX:
        candidates.append(_LINUX_ARM if not toolset else _LINUX_ARM)
    for subdir, name, _bundle in candidates:
        path = game_root / subdir / name
        if path.exists():
            return path
    return None


def bundle_binary(app_path: Path) -> Path:
    """The runnable binary inside a macOS ``.app`` bundle (``…/Contents/MacOS/<name>``)."""
    return app_path / "Contents" / "MacOS" / app_path.stem


def run_binary(
    game_root: Path, host: HostOS, *, toolset: bool = False
) -> Path | None:
    """The actual *waitable* executable (resolving a macOS bundle to its binary)."""
    exe = resolve_executable(game_root, host, toolset=toolset)
    if exe is None:
        return None
    if host is HostOS.MACOS and exe.suffix == ".app":
        inner = bundle_binary(exe)
        return inner if inner.exists() else None
    return exe


def launch_argv(
    game_root: Path,
    *,
    host: HostOS,
    user_dir: Path | None = None,
    steam_app_id: str | None = None,
    prefer_steam: bool = False,
    toolset: bool = False,
    wait: bool = False,
) -> list[str]:
    """Build the launch argv for the game (or toolset).

    Prefers a direct executable launch (so ``-userDirectory`` config isolation is
    honoured). With ``wait=True`` a macOS ``.app`` is launched via its inner binary
    (not ``open``) so the caller can wait for the game to exit. Falls back to the
    Steam URL protocol when the binary can't be found (or ``prefer_steam`` is set)
    and a Steam app id is known.
    """
    exe = resolve_executable(game_root, host, toolset=toolset)
    if exe is None or prefer_steam:
        # The Steam fallback runs the *game*: steam://run/<id> knows nothing
        # about the toolset. Using it for a toolset request launched Neverwinter
        # Nights instead — which is not a degraded result but a different action
        # than the one asked for. The EE toolset ships on Windows only, so on
        # macOS and Linux this is the normal path, not an edge case.
        if steam_app_id and not toolset:
            return _steam_argv(steam_app_id, host)
        if exe is None:
            return []

    game_args: list[str] = []
    if user_dir is not None:
        game_args += ["-userDirectory", str(user_dir)]

    if host is HostOS.MACOS and exe.suffix == ".app":
        if wait:
            # Launch the bundle's binary directly so QProcess can await exit.
            inner = bundle_binary(exe)
            if inner.exists():
                return [str(inner), *game_args]
        # Otherwise let the OS open the bundle (detaches).
        argv = ["open", str(exe)]
        if game_args:
            argv += ["--args", *game_args]
        return argv
    return [str(exe), *game_args]


def _steam_argv(app_id: str, host: HostOS) -> list[str]:
    """Open the ``steam://run/<id>`` protocol URL on the host."""
    url = f"steam://run/{app_id}"
    if host is HostOS.MACOS:
        return ["open", url]
    if host is HostOS.WINDOWS:
        return ["cmd", "/c", "start", "", url]
    return ["xdg-open", url]
