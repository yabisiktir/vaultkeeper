"""Choosing where the store lives.

The store grows to the size of a whole mod collection, so the drive it lands on
matters. These tests pin the judgement: the ordinary place wins unless somewhere
else has *much* more room, and a volume is never offered twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.game import store_volumes as sv


def _fake_volumes(monkeypatch, mounts: dict[Path, int], *, writable=True) -> None:
    """Pretend the machine has exactly these mount points, with this free space."""
    monkeypatch.setattr(sv, "_mount_points", lambda: list(mounts))

    def free(path: Path) -> int:
        for mount, size in mounts.items():
            if path == mount or mount in path.parents:
                return size
        return 0

    monkeypatch.setattr(sv, "_free", free)
    monkeypatch.setattr(sv.os, "access", lambda p, mode: writable)
    # One device id per mount, so distinct mounts read as distinct volumes.
    monkeypatch.setattr(
        sv, "_volume_key", lambda p: next(
            (m for m in mounts if p == m or m in p.parents), (str(p),)
        )
    )


GB = 1024 ** 3


class TestCandidates:
    def test_the_default_is_always_offered_and_marked(self, monkeypatch):
        default = Path("/Users/me/Library/App Support/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/"): 5 * GB})
        options = sv.candidates(default)
        assert [v.is_default for v in options].count(True) == 1
        assert options[0].path == default

    def test_the_default_is_offered_even_when_it_is_the_smallest(self, monkeypatch):
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 1 * GB, Path("/big"): 900 * GB})
        options = sv.candidates(default)
        assert any(v.is_default for v in options)
        assert options[0].path == Path("/big") / sv.STORE_DIR_NAME  # roomiest first

    def test_a_volume_is_offered_once(self, monkeypatch):
        """The default usually sits *on* one of the mounts; it must not double up."""
        default = Path("/big/somewhere/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/big"): 900 * GB})
        assert len(sv.candidates(default)) == 1

    def test_a_full_volume_is_not_offered(self, monkeypatch):
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 1 * GB, Path("/full"): 0})
        assert [v.path for v in sv.candidates(default)] == [default]

    def test_a_volume_we_cannot_write_to_is_not_offered(self, monkeypatch):
        default = Path("/small/Vaultkeeper")
        _fake_volumes(
            monkeypatch, {Path("/small"): 1 * GB, Path("/readonly"): 900 * GB},
            writable=False,
        )
        assert [v.path for v in sv.candidates(default)] == [default]

    def test_the_store_lands_in_a_named_folder_not_the_volume_root(self, monkeypatch):
        _fake_volumes(monkeypatch, {Path("/small"): 1 * GB, Path("/big"): 900 * GB})
        options = sv.candidates(Path("/small/Vaultkeeper"))
        assert options[0].path == Path("/big/Vaultkeeper")


class TestRecommended:
    def test_the_ordinary_place_wins_when_the_difference_is_small(self, monkeypatch):
        """Sending a store to a second disk for 30% more room is not worth it."""
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 100 * GB, Path("/big"): 130 * GB})
        assert sv.recommended(default).is_default

    def test_a_much_roomier_volume_wins(self, monkeypatch):
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 20 * GB, Path("/big"): 900 * GB})
        best = sv.recommended(default)
        assert not best.is_default
        assert best.path == Path("/big/Vaultkeeper")

    def test_the_margin_is_inclusive(self, monkeypatch):
        """At exactly twice the room the other volume does have twice the room."""
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 100 * GB, Path("/big"): 200 * GB})
        assert not sv.recommended(default).is_default

    def test_just_under_the_margin_favours_the_default(self, monkeypatch):
        default = Path("/small/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/small"): 100 * GB, Path("/big"): 199 * GB})
        assert sv.recommended(default).is_default

    def test_with_only_one_volume_there_is_nothing_to_weigh(self, monkeypatch):
        default = Path("/only/Vaultkeeper")
        _fake_volumes(monkeypatch, {Path("/only"): 50 * GB})
        assert sv.recommended(default).is_default


class TestOnThisMachine:
    """Unmocked, against whatever this machine really has."""

    def test_it_answers_without_raising(self):
        from vaultkeeper.app_paths import data_root

        options = sv.candidates(data_root())
        assert options, "the default must always be offered"
        assert any(v.is_default for v in options)
        # By path: free space moves between scans, so the values would differ.
        best = sv.recommended(data_root(), options=options)
        assert best.path in {v.path for v in options}
        assert not best.is_network, "a store must not be put on a NAS by default"

    def test_free_space_reads_a_path_that_does_not_exist_yet(self):
        """The store folder is usually not created until it is chosen."""
        assert sv._free(Path.home() / "no" / "such" / "folder" / "here") > 0

    @pytest.mark.parametrize("size,expected", [(0, "0 bytes"), (1536, "1.5 KB")])
    def test_sizes_read_as_sizes(self, size, expected):
        assert sv._human(size) == expected


class TestNetworkVolumes:
    """A NAS share has room and is still the wrong home for a store."""

    def _with_network(self, monkeypatch, network: set):
        _fake_volumes(monkeypatch, {Path("/local"): 20 * GB, Path("/nas"): 900 * GB})
        monkeypatch.setattr(sv, "_is_network", lambda p: p in network)

    def test_a_network_volume_is_never_recommended(self, monkeypatch):
        self._with_network(monkeypatch, {Path("/nas")})
        assert sv.recommended(Path("/local/Vaultkeeper")).is_default

    def test_but_it_is_still_offered(self, monkeypatch):
        self._with_network(monkeypatch, {Path("/nas")})
        options = sv.candidates(Path("/local/Vaultkeeper"))
        nas = next(v for v in options if v.path == Path("/nas/Vaultkeeper"))
        assert nas.is_network
        assert "(network)" in nas.label

    def test_a_roomy_local_volume_is_still_recommended(self, monkeypatch):
        self._with_network(monkeypatch, set())     # /nas is local after all
        best = sv.recommended(Path("/local/Vaultkeeper"))
        assert not best.is_default and best.path == Path("/nas/Vaultkeeper")
