"""Tests for Rate — per-card cost-effectiveness percentiles (ADR-0042).

Rate = percentile of effect-per-mana within the card's peer class, derived
from the card's own concept trees (crowd- and deck-independent). Neutral 0.5
whenever the formulas can't measure the card — Rate never punishes what it
can't read. The effect side is structural: token bodies x stats per mana,
damage per mana (per-activation cost for activated engines), cards per mana;
Storm doubles a spell's effect (the copies are the card's whole point).
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.rate import (
    RateIndex,
    build_rate_index,
    effect_metric,
    rate_for,
)
from mtg_utils.testkit import snapshot_records, test_card, test_card_ir


def _metric(name: str):
    test_card_ir(name)  # seeds the crosswalk trees memo
    return effect_metric(test_card(name))


# ── effect_metric: (class, effect-per-mana) or None ──────────────────────────


def test_token_class_measures_bodies_times_stats_per_mana():
    test_card_ir("Hordeling Outburst")
    cls, value = effect_metric(test_card("Hordeling Outburst"))
    # Three 1/1 bodies for 3 mana: 3 x (1+1)/2 = 3 stats / 3 mv = 1.0.
    assert cls == "tokens"
    assert value == pytest.approx(1.0)


def test_storm_doubles_a_spell_effect():
    test_card_ir("Empty the Warrens")
    cls, value = effect_metric(test_card("Empty the Warrens"))
    # Two 1/1 bodies for 4 mana, doubled by Storm: 2 x 1 x 2 / 4 = 1.0 —
    # the copies are the card's whole point (CR 702.40a: one copy per prior
    # spell this turn; x2 is the deliberately-conservative floor).
    assert cls == "tokens"
    assert value == pytest.approx(1.0)


def test_damage_class_uses_per_activation_cost_for_engines():
    # Fires of Mount Doom: ETB 2 damage / 3 mv = 0.67, activated 2 damage
    # per {2}{R} activation = 0.67 — the engine's rate is what one
    # activation buys, not the sunk body cost.
    cls, value = _metric("Fires of Mount Doom")
    assert cls == "damage"
    assert value == pytest.approx(2 / 3, abs=0.01)


def test_bolt_rate_beats_fires_rate():
    _, bolt = _metric("Lightning Bolt")
    _, fires = _metric("Fires of Mount Doom")
    assert bolt > fires


def test_draw_class_cards_per_mana():
    cls, value = _metric("Divination")
    assert cls == "draw"
    assert value == pytest.approx(2 / 3, abs=0.01)


def test_unmeasurable_card_is_none():
    # A counterspell has no token/damage/draw read — no class, no judgment.
    test_card_ir("Counterspell")
    assert effect_metric(test_card("Counterspell")) is None


# ── the index: percentiles within class, neutral outside ─────────────────────


@pytest.fixture(scope="module")
def snapshot_index() -> RateIndex:
    return build_rate_index(snapshot_records())


def test_rate_is_a_percentile_within_the_class(snapshot_index):
    test_card_ir("Lightning Bolt")
    test_card_ir("Fires of Mount Doom")
    bolt = rate_for(test_card("Lightning Bolt"), snapshot_index)
    fires = rate_for(test_card("Fires of Mount Doom"), snapshot_index)
    assert 0.0 <= fires < bolt <= 1.0


def test_unmeasured_cards_rate_neutral(snapshot_index):
    test_card_ir("Counterspell")
    assert rate_for(test_card("Counterspell"), snapshot_index) == 0.5
    # No trees at all (a bare dict with no oracle_id) → neutral too.
    assert rate_for({"name": "X", "oracle_text": ""}, snapshot_index) == 0.5


def test_no_index_is_neutral_for_everyone():
    test_card_ir("Lightning Bolt")
    assert rate_for(test_card("Lightning Bolt"), None) == 0.5
