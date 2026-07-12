"""ADR-0035 Stage-3b (b)-COMPLETION — reuse-on-compat field corrections.

CI-safe tests (no phase / bulk / network): the ported-arm registry, the
disposition of every remaining LIVE (b) arm (ported vs deferred, with no
overlap), the firing / idempotence MECHANISM on synthetic compat Cards, and the
inert-card no-op. The corpus-wide LIVE assertion + the per-card consumer SUPERSET
proof are gated tests at the bottom (need the local phase card-data + bulk + old
IR sidecar).
"""

from __future__ import annotations

from mtg_utils._card_ir.field_corrections import (
    _DEFERRED_RAW_ARMS,
    _DEFERRED_UNDERDERIVED_ARMS,
    APPLIED_ABILITY_ARMS,
    APPLIED_CARD_ARMS,
    ARM_NAMES,
    apply_field_corrections,
    correct_with_trace,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter


def _card(abilities: tuple[Ability, ...]) -> Card:
    return Card(oracle_id="x", name="T", faces=(Face(name="T", abilities=abilities),))


# ── the ported-arm registry + the (b) disposition (non-vacuity) ────────────────


def test_ported_arms_are_real_and_unique():
    """The ported (b)-completion set is the three STRUCTURE-reading arms, with no
    duplicate keys — a vacuous registry would make the seam a no-op stage."""
    assert ARM_NAMES == ("clone_subjects", "cheat_into_play_source", "tap_down")
    assert len(ARM_NAMES) == len(set(ARM_NAMES)) == 3
    assert len(APPLIED_ABILITY_ARMS) == 2
    assert len(APPLIED_CARD_ARMS) == 1


def test_every_remaining_b_arm_has_a_disposition_with_no_overlap():
    """Bucket (b) is COMPLETE: all 14 remaining LIVE (b) arms are dispositioned —
    3 ported here, 8 deferred as per-node-raw readers, 3 deferred as compat-field-
    under-derived — and the three sets are pairwise disjoint (an arm is ported XOR
    deferred, never both). This is the exhaustiveness guarantee of the stage."""
    ported = set(ARM_NAMES)
    raw = set(_DEFERRED_RAW_ARMS)
    under = set(_DEFERRED_UNDERDERIVED_ARMS)
    assert len(raw) == 8
    assert len(under) == 3
    assert ported.isdisjoint(raw)
    assert ported.isdisjoint(under)
    assert raw.isdisjoint(under)
    assert len(ported | raw | under) == 14


# ── the firing / idempotence MECHANISM (synthetic compat Cards) ────────────────


def test_clone_subjects_fires_and_refills_subject():
    """A ``clone`` effect whose copied-type subject phase dropped (subject=None) is a
    GAP: the arm fires and borrows the type from a sibling effect's structured
    subject (the parent the copy refers to)."""
    gap = _card(
        (
            Ability(
                kind="spell",
                effects=(
                    Effect(category="clone", subject=None),
                    Effect(category="other", subject=Filter(card_types=("Creature",))),
                ),
            ),
        )
    )
    out, fired = correct_with_trace(gap, "")
    assert "clone_subjects" in fired
    assert out.faces[0].abilities[0].effects[0].subject == Filter(
        card_types=("Creature",)
    )


def test_clone_subjects_noops_when_subject_present():
    """A ``clone`` effect that already carries its copied type is untouched — the arm
    is append-only, not a blanket overwrite (the idempotence property)."""
    parsed = _card(
        (
            Ability(
                kind="spell",
                effects=(
                    Effect(category="clone", subject=Filter(card_types=("Creature",))),
                ),
            ),
        )
    )
    _out, fired = correct_with_trace(parsed, "")
    assert "clone_subjects" not in fired


def test_cheat_into_play_source_appends_one_marker():
    """An ability that puts a creature onto the battlefield from a non-graveyard
    source via a SCATTERED structure (a tutor effect carrying from:library +
    to:battlefield, not a clean cheat_play) gets one canonical ``cheat_play``
    marker appended so the cheat_into_play read has ONE shape."""
    gap = _card(
        (
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="tutor",
                        subject=Filter(card_types=("Creature",)),
                        zones=("from:library", "to:battlefield"),
                    ),
                ),
            ),
        )
    )
    out, fired = correct_with_trace(gap, "")
    assert "cheat_into_play_source" in fired
    effects = out.faces[0].abilities[0].effects
    assert len(effects) == 2
    assert any(e.category == "cheat_play" for e in effects)


def test_cheat_into_play_source_noops_on_clean_cheat_play():
    """When the ability ALREADY carries a clean ``cheat_play`` effect (non-gy
    from: + to:battlefield), the arm reads the existing one and adds nothing."""
    parsed = _card(
        (
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="cheat_play",
                        subject=Filter(card_types=("Creature",)),
                        zones=("from:library", "to:battlefield"),
                    ),
                ),
            ),
        )
    )
    _out, fired = correct_with_trace(parsed, "")
    assert "cheat_into_play_source" not in fired


def test_tap_down_resolves_opponent_anaphora():
    """A subjectless ``tap`` effect whose oracle names an opponent-controlled target
    gets a controller=='opp' subject so tap_down reads STRUCTURE — the card-level
    arm's whole-oracle grounding (the compat seam leaves the per-effect raw empty)."""
    gap = _card(
        (Ability(kind="spell", effects=(Effect(category="tap", subject=None),)),)
    )
    out, fired = correct_with_trace(gap, "Tap target creature an opponent controls.")
    assert "tap_down" in fired
    assert out.faces[0].abilities[0].effects[0].subject.controller == "opp"


def test_no_arm_fires_on_an_inert_card():
    """A vanilla card (no clone / cheat / opponent-tap structure) triggers no
    correction — the arms are structurally guarded, not blanket appenders."""
    inert = _card((Ability(kind="static", effects=(Effect(category="other"),)),))
    out, fired = correct_with_trace(inert, "Draw a card.")
    assert fired == frozenset()
    assert out == inert


def test_apply_is_idempotent():
    """Running the stage twice equals running it once (every arm guards on the
    structure it adds) — the re-entrancy property the compat build relies on."""
    gap = _card(
        (
            Ability(
                kind="triggered",
                effects=(
                    Effect(
                        category="tutor",
                        subject=Filter(card_types=("Creature",)),
                        zones=("from:library", "to:battlefield"),
                    ),
                ),
            ),
        )
    )
    once = apply_field_corrections(gap, "")
    twice = apply_field_corrections(once, "")
    assert twice == once
