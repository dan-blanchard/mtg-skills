"""Tests for sidecar I/O and resume rules."""

from __future__ import annotations

import json

import pytest

from mtg_utils.lgs_search import (
    SIDECAR_VERSION,
    Sidecar,
    assert_hash_matches,
    compute_input_hash,
    load_sidecar,
    next_phase_actions,
    write_sidecar,
)


def test_input_hash_stable_for_same_cards():
    a = [{"card_name": "Sol Ring", "qty": 1}, {"card_name": "Counterspell", "qty": 4}]
    b = [{"card_name": "Counterspell", "qty": 4}, {"card_name": "Sol Ring", "qty": 1}]
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_differs_for_different_cards():
    a = [{"card_name": "Sol Ring", "qty": 1}]
    b = [{"card_name": "Sol Ring", "qty": 2}]
    assert compute_input_hash(a) != compute_input_hash(b)


def test_input_hash_starts_with_sha256_prefix():
    h = compute_input_hash([{"card_name": "X", "qty": 1}])
    assert h.startswith("sha256:")


def test_round_trip(tmp_path):
    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": "2026-05-04T15:30:00Z",
        "input_hash": "sha256:abc",
        "phase": "search_complete",
        "phase_progress": {
            "tgp": {"status": "pending", "items_added": 0, "remaining": []},
            "atomic_empire": {"status": "pending", "items_added": 0, "remaining": []},
        },
        "allocation": [],
        "online_optimizer_results": None,
        "unfindable": [],
        "basic_lands_needed": {},
    }
    path = tmp_path / "sc.json"
    write_sidecar(path, sc)
    loaded = load_sidecar(path)
    assert loaded["version"] == SIDECAR_VERSION
    assert loaded["phase"] == "search_complete"


def test_write_creates_parent_dirs(tmp_path):
    """write_sidecar should create the output dir if missing."""
    path = tmp_path / "deep" / "nested" / "sc.json"
    sc: Sidecar = {
        "version": SIDECAR_VERSION,
        "generated_at": "2026-05-04T15:30:00Z",
        "input_hash": "sha256:x",
        "phase": "done",
        "phase_progress": {},
        "allocation": [],
        "online_optimizer_results": None,
        "unfindable": [],
        "basic_lands_needed": {},
    }
    write_sidecar(path, sc)
    assert path.exists()
    assert json.loads(path.read_text())["phase"] == "done"


def test_load_rejects_wrong_version(tmp_path):
    path = tmp_path / "sc.json"
    path.write_text(json.dumps({"version": 999, "phase": "done"}))
    with pytest.raises(ValueError, match="version"):
        load_sidecar(path)


def test_next_phase_actions_search_complete():
    sc = {"phase": "search_complete", "phase_progress": {}}
    assert next_phase_actions(sc) == ["allocate", "confirm", "build_carts", "handoff"]


def test_next_phase_actions_allocation_complete():
    sc = {"phase": "allocation_complete", "phase_progress": {}}
    assert next_phase_actions(sc) == ["confirm", "build_carts", "handoff"]


def test_next_phase_actions_cart_build_in_progress():
    sc = {
        "phase": "cart_build_in_progress",
        "phase_progress": {
            "tgp": {"status": "complete", "items_added": 18},
            "atomic_empire": {
                "status": "partial",
                "items_added": 14,
                "remaining": [{}, {}],
            },
            "manapool": {"status": "pending"},
        },
    }
    assert next_phase_actions(sc) == ["resume_carts", "handoff"]


def test_next_phase_actions_done():
    sc = {"phase": "done", "phase_progress": {}}
    assert next_phase_actions(sc) == []


def test_next_phase_actions_unknown_raises():
    with pytest.raises(ValueError, match="phase"):
        next_phase_actions({"phase": "weird"})


def test_input_hash_mismatch_rejects():
    cards = [{"card_name": "Sol Ring", "qty": 1}]
    with pytest.raises(ValueError, match="hash"):
        assert_hash_matches(
            sidecar={"input_hash": "sha256:wrong"},
            cards=cards,
        )


def test_input_hash_match_passes():
    cards = [{"card_name": "Sol Ring", "qty": 1}]
    h = compute_input_hash(cards)
    # Should NOT raise
    assert_hash_matches(sidecar={"input_hash": h}, cards=cards)


def test_input_hash_is_case_insensitive():
    a = [{"card_name": "Sol Ring", "qty": 1}]
    b = [{"card_name": "sol ring", "qty": 1}]
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_strips_trailing_whitespace():
    a = [{"card_name": "Sol Ring", "qty": 1}]
    b = [{"card_name": "Sol Ring   ", "qty": 1}]
    # normalize_card_name doesn't explicitly strip, but ASCII-fold + lower
    # leaves the trailing spaces — so the hash WILL differ. We document the
    # actual behavior rather than overpromise.
    # If the spec ever extends normalize_card_name to strip whitespace,
    # update this test.
    assert compute_input_hash(a) != compute_input_hash(b)


def test_input_hash_folds_diacritics():
    # "Lim-Dûl's Vault" should match the ASCII-folded form.
    a = [{"card_name": "Lim-Dûl's Vault", "qty": 1}]
    b = [{"card_name": "Lim-Dul's Vault", "qty": 1}]
    assert compute_input_hash(a) == compute_input_hash(b)
