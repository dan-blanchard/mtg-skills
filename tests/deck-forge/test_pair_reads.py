"""Tests for Pair reads — scored two-card mechanic interactions (ADR-0042).

A Pair read is a registered candidate ident-pattern x deck-anchor row with a
flat curated weight: per-lane additive synergy cannot price multiplicative
interactions (Mana Reflection under Zaxara serves ONE lane; the crowd plays
it because amplifier x X-commander multiplies). Rows live in one central
ledger with pins and CR-grounded rationales (the bridge-ledger discipline);
matched rows sum without decay (curation bounds stacking) into a separate
additive ``pair_score`` readout.
"""

from __future__ import annotations

import fnmatch

import pytest

from mtg_utils._deck_forge.pair_reads import (
    PAIR_READS,
    PairContext,
    build_pair_context,
    pair_score,
)
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir

# ── ledger hygiene (the bridge-ledger discipline) ────────────────────────────


def test_ledger_hygiene():
    assert PAIR_READS, "empty ledger"
    seen_ids = set()
    for row in PAIR_READS.values():
        assert row.pair_id not in seen_ids
        seen_ids.add(row.pair_id)
        assert row.anchor_kind in ("commander", "density"), row.pair_id
        assert row.weight >= 1.0, row.pair_id
        assert row.rationale.strip(), row.pair_id
        assert row.pins, row.pair_id
        assert "|" in row.candidate, row.pair_id  # ident-pattern shaped
        if row.anchor_kind == "density":
            assert row.threshold >= 2, row.pair_id


@pytest.mark.parametrize(
    "name",
    [
        # Every ledger pin, as literals the snapshot builder can scan.
        ("Mana Reflection"),
        ("Zendikar Resurgent"),
        ("Empty the Warrens"),
        ("Hordeling Outburst"),
        ("Ashnod's Altar"),
        ("Single Combat"),
        ("Master Warcraft"),
    ],
)
def test_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name


def test_every_pin_emits_the_candidate_pattern():
    # A pin is a real snapshot card whose OWN idents match the row's
    # candidate pattern — the convergence proof that the pattern is live.
    from mtg_utils.theme_presets import _signal_idents_for

    for row in PAIR_READS.values():
        for pin in row.pins:
            test_card_ir(pin)
            idents = _signal_idents_for(test_card(pin))
            assert any(fnmatch.fnmatchcase(i, row.candidate) for i in idents), (
                row.pair_id,
                pin,
                sorted(idents),
            )


# ── context + scoring ────────────────────────────────────────────────────────


def _zaxara_ctx() -> PairContext:
    test_card_ir("Zaxara, the Exemplary")
    return build_pair_context([test_card("Zaxara, the Exemplary")], [])


def test_amplifier_pairs_with_an_x_commander():
    # The flagship (ADR-0042): Mana Reflection under Zaxara — one lane of
    # additive credit, but the pair is the whole reason the crowd plays it.
    test_card_ir("Mana Reflection")
    score, rows = pair_score(test_card("Mana Reflection"), _zaxara_ctx())
    assert score >= 4.0, rows
    assert any(r["pair"] == "amplifier_x_commander" for r in rows)


def test_no_anchor_no_pair():
    # The same amplifier under a non-X commander pairs with nothing.
    test_card_ir("Krenko, Mob Boss")
    ctx = build_pair_context([test_card("Krenko, Mob Boss")], [])
    test_card_ir("Mana Reflection")
    score, rows = pair_score(test_card("Mana Reflection"), ctx)
    assert score == 0.0
    assert rows == []


def test_density_anchor_needs_the_threshold():
    # A combat puppeteer pairs only when the deck actually runs the goad
    # package (>= threshold emitters), not off one stray card.
    test_card_ir("Master Warcraft")
    warcraft = test_card("Master Warcraft")
    test_card_ir("Disrupt Decorum")
    goad = test_card("Disrupt Decorum")
    thin = build_pair_context([], [goad])
    thick = build_pair_context([], [goad, goad, goad])
    assert pair_score(warcraft, thin)[0] == 0.0
    assert pair_score(warcraft, thick)[0] > 0.0


def test_tribal_fodder_pairs_subject_matched():
    # Krenko's X counts GOBLINS (CR 608.2h: game information counted on
    # application) — Goblin fodder multiplies his activation, other tribes'
    # fodder does not. The row's subject-match requires the candidate's
    # token subject to equal the commander's.
    test_card_ir("Krenko, Mob Boss")
    ctx = build_pair_context([test_card("Krenko, Mob Boss")], [])
    test_card_ir("Empty the Warrens")
    _score, rows = pair_score(test_card("Empty the Warrens"), ctx)
    assert any(r["pair"] == "tribal_fodder_x_token_commander" for r in rows), rows
    # A Human/Soldier token maker feeds no Goblin count — no pair.
    test_card_ir("Bastion of Remembrance")
    _score2, rows2 = pair_score(test_card("Bastion of Remembrance"), ctx)
    assert not any(r["pair"] == "tribal_fodder_x_token_commander" for r in rows2), rows2


def test_rows_sum_without_decay_and_ride_the_readout():
    # rank_candidates: pair_score is additive on the depth sort and lands in
    # the readout. Zero-synergy candidates still surface on a strong pair.
    ctx = _zaxara_ctx()
    test_card_ir("Mana Reflection")
    reflection = test_card("Mana Reflection")
    ranked = rank_candidates(
        [reflection],
        active_signals=[Signal("xspell_matters", "you", "", "", "cmd")],
        pair_ctx=ctx,
    )
    sc = ranked[0]["score"]
    assert sc["pair_score"] >= 4.0
    assert sc["pairs"], sc
