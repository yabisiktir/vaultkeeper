"""Tests for BIK→WBM conversion (VB NIT.ConvertBik / BgConverter)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.game.bik_convert import BikConverter, FakeBikConverter, ffmpeg_command
from vaultkeeper.ui.controller import ProfileController


def test_ffmpeg_command_matches_vb():
    argv = ffmpeg_command("ffmpeg", Path("/m/in.bik"), Path("/m/out.wbm"))
    # VB: ffmpeg -i <bik> -c:v libvpx -b:v 1M -c:a libvorbis -y -f webm <wbm>
    assert argv[:1] == ["ffmpeg"]
    assert "-c:v" in argv and "libvpx" in argv
    assert "libvorbis" in argv
    # str(Path(...)), not the literal: ffmpeg is handed the path as the host
    # spells it, which is "\m\out.wbm" on Windows.
    assert argv[-3:] == ["-f", "webm", str(Path("/m/out.wbm"))]
    assert argv[1:3] == ["-i", str(Path("/m/in.bik"))]


def test_converter_runs_command(tmp_path):
    calls = []

    def runner(argv):
        calls.append(argv)
        (tmp_path / "out.wbm").write_bytes(b"WEBM")
        return 0

    conv = BikConverter(exe="ffmpeg", runner=runner)
    assert conv.available
    assert conv.convert(tmp_path / "in.bik", tmp_path / "out.wbm")
    assert calls and calls[0][0] == "ffmpeg"


def test_converter_unavailable(monkeypatch):
    monkeypatch.setattr(BikConverter, "_discover", classmethod(lambda cls: None))
    conv = BikConverter(exe=None)
    assert not conv.available
    assert not conv.convert(Path("a.bik"), Path("b.wbm"))


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_build_installer_converts_bik(tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("MoviesMod")
    mod = tmp_path / "Profiles" / "P" / "MoviesMod"
    (mod / "intro.bik").write_bytes(b"BIK ")
    controller._bik_backend = FakeBikConverter()

    result = controller.build_installer_payload("MoviesMod", convert_bik=True)
    assert result["ok"]
    assert result["converted"] == 1
    # The converted .wbm landed in the movies folder; the .bik did not.
    installer = mod / C.MOD_INSTALLER_DIR
    wbm = list(installer.rglob("intro.wbm"))
    assert wbm, "converted .wbm should be in the installer"
    assert not list(installer.rglob("intro.bik"))


def test_build_installer_bik_passthrough_when_off(tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("MoviesMod")
    mod = tmp_path / "Profiles" / "P" / "MoviesMod"
    (mod / "intro.bik").write_bytes(b"BIK ")

    result = controller.build_installer_payload("MoviesMod", convert_bik=False)
    assert result["converted"] == 0
    # With conversion off, the .bik is copied as-is (mapped to movies).
    installer = mod / C.MOD_INSTALLER_DIR
    assert list(installer.rglob("intro.bik"))
