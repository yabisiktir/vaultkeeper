"""Tests for the persisted patch-hak ordering (VB HakPatchManager.UpdateSequenceFile)."""

from __future__ import annotations

from vaultkeeper.core.hak_patch import (
    read_patch_sequence,
    save_patch_sequence,
    update_patch_sequence,
)


def test_read_missing_sequence(tmp_path):
    assert read_patch_sequence(tmp_path) == []


def test_save_and_read_round_trip(tmp_path):
    save_patch_sequence(tmp_path, ["a", "b", "c"])
    assert read_patch_sequence(tmp_path) == ["a", "b", "c"]


def test_update_appends_new_and_dedups(tmp_path):
    save_patch_sequence(tmp_path, ["base"])
    seq = update_patch_sequence(tmp_path, ["base", "extra", "BASE", "more"])
    # Existing 'base' kept once (case-insensitive), new stems appended in order.
    assert seq == ["base", "extra", "more"]
    assert read_patch_sequence(tmp_path) == ["base", "extra", "more"]


def test_update_preserves_prior_order(tmp_path):
    update_patch_sequence(tmp_path, ["z", "a"])
    seq = update_patch_sequence(tmp_path, ["m"])
    assert seq == ["z", "a", "m"]  # prior order preserved, new appended
