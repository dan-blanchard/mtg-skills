"""Unit tests for the IR-backed signal path (Milestone A2 — 5-key vertical slice).

These build Card IR objects directly (no phase dependency) and assert
``extract_signals_ir`` emits the same Signal(key, scope, subject) the regex path
does for the five slice keys, with the IR's structural advantages: a tribal
filter is type_matters (not creatures_matter), and scope comes from the trigger's
own subject (aristocrats death is YOUR creature dying).
"""

from __future__ import annotations

from mtg_utils._deck_forge.signals import (
    IR_SLICE_KEYS,
    extract_signals_ir,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger

CARD = {"name": "Test"}


def _ir(*abilities: Ability, castable: tuple[str, ...] = ()) -> Card:
    return Card(
        oracle_id="x",
        name="Test",
        faces=(Face(name="Test", abilities=tuple(abilities)),),
        castable_zones=castable,
    )


def _sigs(ir: Card) -> list[tuple[str, str, str]]:
    return sorted((s.key, s.scope, s.subject) for s in extract_signals_ir(CARD, ir))


# ── creatures_matter (generic creatures, not tribal) ──────────────────────────


def test_creatures_matter_from_anthem():
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(card_types=("Creature",), controller="you"),
                ),
            ),
        )
    )
    assert _sigs(ir) == [("creatures_matter", "you", "")]


def test_creatures_matter_from_scaling_amount():
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="draw",
                    amount=Quantity(
                        op="count",
                        subject=Filter(card_types=("Creature",), controller="you"),
                    ),
                ),
            ),
        )
    )
    assert _sigs(ir) == [("creatures_matter", "you", "")]


def test_tribal_filter_is_not_creatures_matter():
    """A Goblin-count operand is type_matters territory, NOT creatures_matter."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="draw",
                    amount=Quantity(
                        op="count",
                        subject=Filter(
                            card_types=("Creature",),
                            subtypes=("Goblin",),
                            controller="you",
                        ),
                    ),
                ),
            ),
        )
    )
    assert ("creatures_matter", "you", "") not in _sigs(ir)


# ── lifegain_matters ──────────────────────────────────────────────────────────


def test_lifegain_from_gain_life_effect():
    ir = _ir(
        Ability(kind="spell", effects=(Effect(category="gain_life", scope="you"),))
    )
    assert _sigs(ir) == [("lifegain_matters", "you", "")]


def test_lifegain_from_life_gained_trigger():
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="life_gained", scope="you"))
    )
    assert _sigs(ir) == [("lifegain_matters", "you", "")]


def test_opponent_gain_life_is_not_lifegain_payoff():
    ir = _ir(
        Ability(kind="spell", effects=(Effect(category="gain_life", scope="opp"),))
    )
    assert _sigs(ir) == []


# ── graveyard_matters (scoped) ────────────────────────────────────────────────


def test_graveyard_from_reanimate_scoped_opp():
    ir = _ir(
        Ability(kind="triggered", effects=(Effect(category="reanimate", scope="opp"),))
    )
    assert _sigs(ir) == [("graveyard_matters", "opponents", "")]


def test_graveyard_from_self_mill():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="you"),)))
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


def test_graveyard_from_castable_zone():
    ir = _ir(castable=("graveyard",))
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


# ── token_maker (subject-bearing) ─────────────────────────────────────────────


def test_token_maker_with_kindred_subject():
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="make_token",
                    subject=Filter(card_types=("Creature",), subtypes=("Goblin",)),
                ),
            ),
        )
    )
    assert _sigs(ir) == [("token_maker", "you", "Goblin")]


def test_token_maker_picks_last_creature_subtype():
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="make_token",
                    subject=Filter(
                        card_types=("Creature",), subtypes=("Human", "Soldier")
                    ),
                ),
            ),
        )
    )
    assert _sigs(ir) == [("token_maker", "you", "Soldier")]


def test_token_maker_creature_token_no_subtype():
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(category="make_token", subject=Filter(card_types=("Creature",))),
            ),
        )
    )
    assert _sigs(ir) == [("token_maker", "you", "")]


def test_non_creature_token_is_not_token_maker():
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="make_token",
                    subject=Filter(card_types=("Artifact",), subtypes=("Treasure",)),
                ),
            ),
        )
    )
    assert _sigs(ir) == []


# ── death_matters (scope from the trigger's own subject) ──────────────────────


def test_death_matters_from_other_creatures_dying():
    """Aristocrats: a dies trigger about OTHER creatures (a real subject filter)."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="dies",
                scope="you",
                subject=Filter(card_types=("Creature",), controller="you"),
            ),
        )
    )
    assert _sigs(ir) == [("death_matters", "you", "")]


def test_self_death_trigger_is_not_death_matters():
    """A 'when this dies' self-death trigger (no subject) is self_death_payoff,
    not aristocrats death_matters."""
    ir = _ir(Ability(kind="triggered", trigger=Trigger(event="dies", scope="you")))
    assert _sigs(ir) == []


# ── contract guards ───────────────────────────────────────────────────────────


def test_no_ir_returns_empty():
    assert extract_signals_ir(CARD, None) == []


def test_only_slice_keys_emitted():
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="dies", scope="you")),
        Ability(kind="spell", effects=(Effect(category="gain_life", scope="you"),)),
    )
    assert {s.key for s in extract_signals_ir(CARD, ir)} <= IR_SLICE_KEYS
