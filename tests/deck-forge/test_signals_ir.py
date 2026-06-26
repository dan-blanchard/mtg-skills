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
from mtg_utils.card_ir import (
    Ability,
    Card,
    Condition,
    Effect,
    Face,
    Filter,
    Quantity,
    Trigger,
)

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
    # A count-draw over your creatures is creatures_matter AND draw_for_each.
    assert ("creatures_matter", "you", "") in _sigs(ir)


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


# ── lifegain_matters: ADR-0027 C10 — A2 grant-lifelink + ARM-B self-loss ───────


def test_lifegain_from_grant_lifelink_source():
    # Talus Paladin "Allies you control gain lifelink": granting lifelink makes them a
    # lifegain SOURCE (CR 702.15b), same lane as the card's own lifelink keyword.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb"),
            effects=(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    counter_kind="lifelink",
                    subject=Filter(subtypes=("Ally",), controller="you"),
                    raw="gain lifelink",
                ),
            ),
        )
    )
    assert ("lifegain_matters", "you", "") in _sigs(ir)


def test_grant_lifelink_to_opponent_creatures_not_lifegain():
    # Over-fire guard: a hypothetical "creatures an opponent controls gain lifelink"
    # is not YOUR lifegain source — the grant subject is opp-controlled.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    counter_kind="lifelink",
                    subject=Filter(card_types=("Creature",), controller="opp"),
                    raw="creatures an opponent controls have lifelink",
                ),
            ),
        )
    )
    assert "lifegain_matters" not in {k for (k, _s, _u) in _sigs(ir)}


def test_lifegain_from_scaling_self_loss():
    # Dark Confidant "You lose life equal to its mana value" — a scaling self-bleed
    # (op=count) that wants lifegain to sustain it (CR 119.3).
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="upkeep"),
            effects=(
                Effect(
                    category="lose_life",
                    scope="you",
                    amount=Quantity(op="count", factor=1),
                    raw="You lose life equal to its mana value.",
                ),
            ),
        )
    )
    assert ("lifegain_matters", "you", "") in _sigs(ir)


def test_lifegain_from_recurring_upkeep_bleed():
    # Benthic Djinn "At the beginning of your upkeep, you lose 2 life" — a recurring
    # fixed >=2 upkeep bleed.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="upkeep"),
            effects=(
                Effect(
                    category="lose_life",
                    scope="you",
                    amount=Quantity(op="fixed", factor=2),
                    raw="At the beginning of your upkeep, you lose 2 life.",
                ),
            ),
        )
    )
    assert ("lifegain_matters", "you", "") in _sigs(ir)


def test_one_shot_fixed_self_loss_not_lifegain():
    # Over-fire guard: a one-shot fixed "you lose 2 life" rider on a removal / tutor /
    # draw spell (Infernal Grasp, Read the Bones) is NOT a sustain engine — factor>=2
    # alone is not enough without recurrence (upkeep) or scaling.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="lose_life",
                    scope="you",
                    amount=Quantity(op="fixed", factor=2),
                    raw="Destroy target creature. You lose 2 life.",
                ),
            ),
        )
    )
    assert "lifegain_matters" not in {k for (k, _s, _u) in _sigs(ir)}


def test_opponent_loses_life_is_not_self_sustain():
    # Over-fire guard: a scope-opp lose_life ("target opponent loses 2 life") is
    # opponent DRAIN (the lifeloss lane), never the self-sustain ARM-B.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="lose_life",
                    scope="opp",
                    amount=Quantity(op="count", factor=1),
                    raw="Target opponent loses life equal to ...",
                ),
            ),
        )
    )
    assert "lifegain_matters" not in {k for (k, _s, _u) in _sigs(ir)}


def test_lifegain_from_draw_bleed_engine():
    # Taborax / Disciple of Perdition: a death-triggered ability that BOTH draws and
    # makes you lose life is a Necropotence-style draw-bleed engine — recurrence is
    # the significance, so the fixed-factor-1 floor does not apply.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies"),
            effects=(
                Effect(category="draw", scope="you"),
                Effect(
                    category="lose_life",
                    scope="you",
                    amount=Quantity(op="fixed", factor=1),
                    raw="you draw a card and you lose 1 life",
                ),
            ),
        )
    )
    assert ("lifegain_matters", "you", "") in _sigs(ir)


# ── graveyard_matters (scoped) ────────────────────────────────────────────────


def test_graveyard_from_reanimate_scoped_opp():
    ir = _ir(
        Ability(kind="triggered", effects=(Effect(category="reanimate", scope="opp"),))
    )
    assert _sigs(ir) == [("graveyard_matters", "opponents", "")]


def test_graveyard_from_self_mill():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="you"),)))
    # A mill effect feeds a graveyard (graveyard_matters). ADR-0027: mill_matters
    # migrated to the Scryfall `Mill` keyword route (_IR_KEYWORD_MAP), NOT the `mill`
    # effect category — phase mislabels 3 non-mill effects (Bone Dancer, Scroll Rack,
    # Soldevi Digger) as `mill`, and every genuine mill carries the keyword. So the
    # blanket effect-category doer was dropped; a bare `mill` effect on a keyword-LESS
    # record now opens graveyard_matters only. CR 701.13.
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


def test_graveyard_from_castable_zone():
    ir = _ir(castable=("graveyard",))
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


# ── graveyard_matters pass 2 (from:graveyard recursion / search, exile-in-GY
#    hate, scope fidelity — ADR-0027) ───────────────────────────────────────────


def test_graveyard_bounce_from_graveyard_scoped_you():
    """A bounce returning cards FROM your graveyard to hand (Metallurgic Summonings,
    from:graveyard) fires graveyard_matters at you — _gy_scope reads "your graveyard"
    in the raw, overriding phase's recursion-target 'any' scope."""
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="bounce",
                    scope="any",
                    zones=("from:graveyard", "to:hand"),
                    raw="Return all instant and sorcery cards from your graveyard to "
                    "your hand.",
                ),
            ),
        )
    )
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


def test_graveyard_tutor_from_graveyard_scoped_you():
    """A tutor whose search reaches YOUR graveyard (recovered from:graveyard, scope
    you) fires graveyard_matters at you and cross-opens tutor_matters."""
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="tutor",
                    scope="you",
                    zones=("from:graveyard",),
                    raw="search your graveyard, hand, and/or library for an Aura.",
                ),
            ),
        )
    )
    assert ("graveyard_matters", "you", "") in _sigs(ir)


def test_graveyard_tutor_from_opponent_graveyard_scoped_opponents():
    """A tutor that searches an OPPONENT's graveyard (recovered from:graveyard, scope
    opp) fires graveyard_matters at opponents (GY hate)."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="tutor",
                    scope="opp",
                    zones=("from:graveyard",),
                    raw="Search target opponent's graveyard, hand, and library and "
                    "exile them.",
                ),
            ),
        )
    )
    assert ("graveyard_matters", "opponents", "") in _sigs(ir)


def test_graveyard_exile_in_graveyard_hate_scoped_opponents():
    """An exile of a card targeted IN an opponent's graveyard (in:graveyard, not
    from:graveyard — Disposal Mummy) fires graveyard_matters at opponents (GY hate);
    the in:graveyard hate path now covers it (it was double-missed before pass 2)."""
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="exile",
                    scope="any",
                    zones=("to:exile", "in:graveyard"),
                    raw="exile target card from an opponent's graveyard.",
                ),
            ),
        )
    )
    assert _sigs(ir) == [("graveyard_matters", "opponents", "")]


def test_graveyard_count_marker_opp_scope_fires_opponents():
    """The opponent-GY count marker (board_count, scope opp — Anticognition) fires
    graveyard_matters at opponents via the in:graveyard zone hook + _gy_scope."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="board_count",
                    scope="opp",
                    zones=("in:graveyard",),
                    raw="count of cards in a graveyard",
                ),
            ),
        )
    )
    assert _sigs(ir) == [("graveyard_matters", "opponents", "")]


def test_graveyard_bare_a_graveyard_recursion_defaults_you():
    """ADR-0027 v29: a recursion target with NO "opponent" tell ("Return target creature
    card from a graveyard" — a bare graveyard, structurally scope 'any' because the
    recursion target carries no controller) defaults to the SELF-graveyard 'you' (the
    graveyard_matters scope-discrimination contract forbids a ('graveyard_matters','any')
    avenue — signal_specs registers only 'you' / 'opponents'). A flexible "a graveyard"
    recursion is YOUR graveyard build-around; an explicit opponent's-GY tell still routes
    to 'opponents'. CR 400.7 / 701.17a."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="bounce",
                    scope="any",
                    zones=("from:graveyard", "to:hand"),
                    raw="Return target creature card from a graveyard to its owner's "
                    "hand.",
                ),
            ),
        )
    )
    assert _sigs(ir) == [("graveyard_matters", "you", "")]


# ── token_maker (subject-bearing) ─────────────────────────────────────────────


def test_token_maker_with_kindred_subject():
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(card_types=("Creature",), subtypes=("Goblin",)),
                ),
            ),
        )
    )
    # A creature-token-maker with a captured subject cross-opens creatures_matter
    # (the go-wide mass-token DOER), mirroring the regex SWEEP cross-open.
    # ADR-0027: type_matters migrated → hybrid path. Its token→tribe cross-open is
    # membership-gated, so assert the token_maker lane in isolation (membership off).
    sigs = sorted(
        (s.key, s.scope, s.subject)
        for s in extract_signals_ir(CARD, ir, include_membership=False)
    )
    assert sigs == [
        ("creatures_matter", "you", ""),
        ("token_maker", "you", "Goblin"),
    ]


def test_token_maker_picks_last_creature_subtype():
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",), subtypes=("Human", "Soldier")
                    ),
                ),
            ),
        )
    )
    # Subject-bearing creature-token-maker → cross-opens creatures_matter (go-wide).
    # ADR-0027: type_matters migrated → hybrid path. Its token→tribe cross-open is
    # membership-gated, so assert the token_maker lane in isolation (membership off).
    sigs = sorted(
        (s.key, s.scope, s.subject)
        for s in extract_signals_ir(CARD, ir, include_membership=False)
    )
    assert sigs == [
        ("creatures_matter", "you", ""),
        ("token_maker", "you", "Soldier"),
    ]


def test_token_maker_creature_token_no_subtype():
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(card_types=("Creature",)),
                ),
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
    # Not a creature-token maker (it's treasure_matters instead, not token_maker).
    assert "token_maker" not in {s.key for s in extract_signals_ir(CARD, ir)}


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


def test_self_death_trigger_with_payoff_is_self_death_payoff():
    """A 'when this dies, do X' self-death trigger (no subject + an effect) is
    self_death_payoff (Kokusho, Solemn), not aristocrats death_matters."""
    # scope="you" (the controller draws on its own death) so the incidental draw is a
    # self-cantrip, not a directed target_player_draws (which fires on scope="any").
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", scope="you"),
            effects=(Effect(category="draw", scope="you"),),
        )
    )
    assert _sigs(ir) == [("self_death_payoff", "you", "")]


def test_bare_self_death_trigger_emits_nothing():
    """A self-death trigger with no recovered effect fires neither lane."""
    ir = _ir(Ability(kind="triggered", trigger=Trigger(event="dies", scope="you")))
    assert _sigs(ir) == []


def test_attached_creature_death_is_not_self_death_payoff():
    """'Whenever equipped creature dies' (Skullclamp: AttachedTo → scope 'any',
    no subject filter) is not a SELF-death — fires neither death lane here."""
    # scope="you" on the draw (Skullclamp's controller draws) so it stays a self-cantrip,
    # not a directed target_player_draws (scope="any").
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", scope="any"),
            effects=(Effect(category="draw", scope="you"),),
        )
    )
    assert _sigs(ir) == []


# ── reanimator (creature that returns creature cards from a graveyard) ─────────

_CREATURE = {"name": "Test", "type_line": "Legendary Creature — Praetor"}
_SORCERY = {"name": "Test", "type_line": "Sorcery"}


def _reanimate_ir() -> Card:
    return _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="upkeep", scope="you"),
            effects=(
                Effect(
                    category="reanimate",
                    subject=Filter(card_types=("Creature",), controller="you"),
                ),
            ),
        )
    )


def test_reanimator_fires_for_creature_returning_creatures():
    sigs = {s.key for s in extract_signals_ir(_CREATURE, _reanimate_ir())}
    assert "reanimator" in sigs


def test_reanimator_not_for_noncreature_spell():
    """A reanimation sorcery is an enabler, not the reanimator archetype."""
    sigs = {s.key for s in extract_signals_ir(_SORCERY, _reanimate_ir())}
    assert "reanimator" not in sigs


def test_reanimator_not_for_permanent_return():
    """Returning a Permanent card (Sun Titan) is recursion, not reanimator."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="you"),
            effects=(
                Effect(
                    category="reanimate",
                    subject=Filter(card_types=("Permanent",), controller="you"),
                ),
            ),
        )
    )
    assert "reanimator" not in {s.key for s in extract_signals_ir(_CREATURE, ir)}


def test_reanimate_target_does_not_fire_creatures_matter():
    """A single reanimate target that's a 'creature you control' is NOT the
    go-wide creatures_matter lane (only an anthem/scaling is)."""
    sigs = {s.key for s in extract_signals_ir(_CREATURE, _reanimate_ir())}
    assert "creatures_matter" not in sigs


# ── Batch 2: effect-doer + trigger-payoff lanes ───────────────────────────────


def test_direct_damage_fires_for_offensive_damage():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="damage", scope="opp"),)))
    assert ("direct_damage", "you", "") in _sigs(ir)


def test_direct_damage_not_for_self_damage():
    """Incidental self-damage (painland, talisman: target you) is not direct_damage."""
    ir = _ir(
        Ability(kind="activated", effects=(Effect(category="damage", scope="you"),))
    )
    assert "direct_damage" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_place_counter_effect_does_not_flood_plus_one_matters():
    """A KINDLESS place_counter with no '+1/+1 counter' raw does not fire
    plus_one_matters (ADR-0027): a bare loyalty/charge/named-counter placement phase
    didn't tag p1p1 stays out of the +1/+1 lane (avoids loyalty/charge floods). The
    p1p1-kind and the '+1/+1 counter'-raw forms DO fire (tests below)."""
    ir = _ir(Ability(kind="triggered", effects=(Effect(category="place_counter"),)))
    assert "plus_one_matters" not in {s.key for s in extract_signals_ir(CARD, ir)}


# ── plus_one_matters shapes (ADR-0027) ─────────────────────────────────────────


def test_place_counter_p1p1_fires_plus_one_matters():
    """A +1/+1 counter PLACEMENT (the lane's core engine — Forgotten Ancient,
    Hardened Scales) fires plus_one_matters; the p1p1 kind discriminates it from
    loyalty/oil/shield placements."""
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="place_counter",
                    counter_kind="p1p1",
                    raw="put a +1/+1 counter on target creature",
                ),
            ),
        )
    )
    assert ("plus_one_matters", "you", "") in _sigs(ir)


def test_place_counter_blank_kind_with_p1p1_raw_fires():
    """The enters-with / modal-kicker form phase strips the kind from (counter_kind
    '') but whose raw names '+1/+1 counter' (Endless One, Orzhov Advokist) fires."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="place_counter",
                    counter_kind="",
                    raw="this creature enters with X +1/+1 counters on it",
                ),
            ),
        )
    )
    assert ("plus_one_matters", "you", "") in _sigs(ir)


def test_place_counter_blank_kind_without_p1p1_raw_excluded():
    """A blank-kind placement whose raw is NOT a +1/+1 counter (a named-counter card)
    stays out of the +1/+1 lane."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="place_counter",
                    counter_kind="",
                    raw="put a page counter on this artifact",
                ),
            ),
        )
    )
    assert "plus_one_matters" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_proliferate_fires_any_counter_matters():
    """Proliferate adds 'one counter of EACH KIND already there' (CR 701.34a) — it
    cares about counters GENERICALLY, so it opens the kind-agnostic any_counter_matters
    lane, NOT the +1/+1-specific plus_one_matters (ADR-0027 taxonomy)."""
    ir = _ir(Ability(kind="spell", effects=(Effect(category="proliferate"),)))
    keys = _sigs(ir)
    assert ("any_counter_matters", "you", "") in keys
    assert ("plus_one_matters", "you", "") not in keys


def test_removecounter_cost_with_p1p1_oracle_fires():
    """An ability whose COST removes +1/+1 counters (Triskelion ping) fires
    plus_one_matters when the oracle names '+1/+1 counter'."""
    card = {
        "name": "Triskelion",
        "oracle_text": (
            "This creature enters with three +1/+1 counters on it.\n"
            "Remove a +1/+1 counter from this creature: It deals 1 damage to "
            "any target."
        ),
    }
    ir = _ir(
        Ability(
            kind="activated",
            cost="removecounter",
            effects=(Effect(category="damage", raw="deals 1 damage to any target"),),
        )
    )
    assert "plus_one_matters" in {s.key for s in extract_signals_ir(card, ir)}


def test_removecounter_cost_without_p1p1_oracle_excluded():
    """A removecounter cost on a NON-+1/+1 counter card (a ki/depletion/charge sink)
    stays out of the +1/+1 lane (CR 122.1)."""
    card = {
        "name": "Gemstone Mine",
        "oracle_text": (
            "This land enters with three mining counters on it.\n"
            "{T}, Remove a mining counter: Add one mana of any color."
        ),
    }
    ir = _ir(
        Ability(
            kind="activated",
            cost="removecounter,tap",
            effects=(Effect(category="ramp", raw="add one mana"),),
        )
    )
    assert "plus_one_matters" not in {s.key for s in extract_signals_ir(card, ir)}


def test_counter_have_payoff_on_amount_subject_fires():
    """A count-form counter-HAVE payoff ('draw a card for each creature you control
    WITH a +1/+1 counter' — Inspiring Call): the Counters predicate rides
    amount.subject, not e.subject."""
    counted = Filter(
        card_types=("Creature",),
        controller="you",
        predicates=("Counters:P1P1:GE:1",),
    )
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="draw",
                    scope="you",
                    amount=Quantity(op="count", subject=counted),
                    raw="draw a card for each creature you control with a "
                    "+1/+1 counter on it",
                ),
            ),
        )
    )
    keys = _sigs(ir)
    # The P1P1 kind routes to plus_one_matters (NOT modified_matters — that lane reads
    # phase's direct `Modified` predicate, not every +1/+1 subject).
    assert ("plus_one_matters", "you", "") in keys
    assert ("modified_matters", "you", "") not in keys


def test_counter_have_payoff_on_trigger_subject_fires():
    """A counter-HAVE TRIGGER ('whenever a creature you control WITH a +1/+1 counter
    dies' — Laid to Rest): the Counters predicate rides the trigger subject."""
    tsub = Filter(
        card_types=("Creature",),
        controller="you",
        predicates=("Counters:P1P1:GE:1",),
    )
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", subject=tsub, scope="you"),
            effects=(Effect(category="gain_life", raw="you gain 2 life"),),
        )
    )
    assert ("plus_one_matters", "you", "") in _sigs(ir)


def test_counter_pred_routes_by_kind_off_plus_one():
    """ADR-0027 taxonomy: a 'creature WITH an M1M1 / oil / time counter' payoff routes
    to its OWN lane, NOT plus_one_matters (the +1/+1 lane). CR 122.1."""

    def _have(kind: str) -> set:
        sub = Filter(
            card_types=("Creature",),
            controller="you",
            predicates=(f"Counters:{kind}:GE:1",),
        )
        ir = _ir(
            Ability(
                kind="static",
                effects=(Effect(category="pump", subject=sub, raw="x get trample"),),
            )
        )
        return _sigs(ir)

    assert ("minus_counters_matter", "you", "") in _have("M1M1")
    assert ("oil_counter_matters", "you", "") in _have("oil")
    # A singleton named kind (time/bounty/fate/…) falls to the named catch-all.
    assert ("named_counter_misc", "you", "") in _have("time")
    # None of them open the +1/+1 lane.
    for kind in ("M1M1", "oil", "time"):
        assert ("plus_one_matters", "you", "") not in _have(kind)


def test_any_counter_pred_fires_any_counter_matters():
    """The kind-agnostic 'creature with ANY counter on it' payoff (Bulwark Ox,
    Innkeeper's Talent) opens any_counter_matters, not plus_one_matters."""
    sub = Filter(
        card_types=("Creature",),
        controller="you",
        predicates=("Counters:Any:GE:1",),
    )
    ir = _ir(
        Ability(
            kind="static",
            effects=(Effect(category="pump", subject=sub, raw="x get +1/+0"),),
        )
    )
    keys = _sigs(ir)
    assert ("any_counter_matters", "you", "") in keys
    assert ("plus_one_matters", "you", "") not in keys


def test_eq0_no_counter_gate_does_not_open_plus_one():
    """An EQ:0 'creature with NO counter' anti-synergy gate (Heartless Act, Damning
    Verdict) is the INVERSE of a counters payoff — it opens NO counter lane (CR 122.3
    / 700.9)."""
    sub = Filter(card_types=("Creature",), predicates=("Counters:Any:EQ:0",))
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(category="destroy", subject=sub, raw="destroy target creature"),
            ),
        )
    )
    keys = {k for (k, _s, _sub) in _sigs(ir)}
    assert "plus_one_matters" not in keys
    assert "any_counter_matters" not in keys
    assert "named_counter_misc" not in keys
    assert "modified_matters" not in keys


def test_modified_predicate_fires_modified_matters():
    """phase's direct `Modified` predicate (CR 700.9 — the Kamigawa-NEO 'modified
    creature' payoff: Chishiro, Thundering Raiju) opens modified_matters."""
    sub = Filter(card_types=("Creature",), controller="you", predicates=("Modified",))
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="attacks", subject=sub, scope="you"),
            effects=(Effect(category="draw", raw="draw a card"),),
        )
    )
    assert ("modified_matters", "you", "") in _sigs(ir)


def test_counter_move_p1p1_fires_plus_one_matters():
    """A +1/+1 counter MOVE (Bioshift) opens plus_one_matters alongside the dedicated
    counter_move lane; a non-p1p1 move stays out."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="counter_move",
                    counter_kind="p1p1",
                    raw="move any number of +1/+1 counters",
                ),
            ),
        )
    )
    keys = {s.key for s in extract_signals_ir(CARD, ir)}
    assert "plus_one_matters" in keys
    assert "counter_move" in keys


def test_pump_count_counter_payoff_fires():
    """A pump scaling with a BARE 'for each counter on' count (Kyler) is kind-agnostic
    → any_counter_matters; a '+1/+1 counter' scale routes to plus_one_matters
    (ADR-0027 taxonomy: the raw discriminates the counted kind)."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Human",),
                        controller="you",
                    ),
                    amount=Quantity(op="count"),
                    raw="Humans you control get +1/+1 for each counter on ~",
                ),
            ),
        )
    )
    assert ("any_counter_matters", "you", "") in _sigs(ir)
    # The "+1/+1 counter" form routes to the +1/+1-specific lane.
    ir2 = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Human",),
                        controller="you",
                    ),
                    amount=Quantity(op="count"),
                    raw="Humans you control get +1/+1 for each +1/+1 counter on ~",
                ),
            ),
        )
    )
    assert ("plus_one_matters", "you", "") in _sigs(ir2)


# ── removal_matters shapes (ADR-0027) ─────────────────────────────────────────


def test_damage_to_creature_fires_removal_matters():
    """A damage effect to a target creature (Flame Slash) fires removal_matters — the
    regex routed this only to direct_damage; the lane was never wired to damage."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="damage",
                    subject=Filter(card_types=("Creature",)),
                    amount=Quantity(op="fixed", factor=4),
                    raw="deals 4 damage to target creature",
                ),
            ),
        )
    )
    assert ("removal_matters", "you", "") in _sigs(ir)


def test_damage_to_any_target_not_removal():
    """A burn to 'any target' (subject None — Lightning Bolt-style) stays
    direct_damage, NOT removal."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="damage",
                    subject=None,
                    amount=Quantity(op="fixed", factor=3),
                    raw="deals 3 damage to any target",
                ),
            ),
        )
    )
    assert "removal_matters" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_destroy_subtype_only_fires_removal_matters():
    """'Destroy target Wall' (subtype-only subject, no card_types) fires
    removal_matters — it destroys a creature."""
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="destroy",
                    subject=Filter(subtypes=("Wall",)),
                    raw="Destroy target Wall",
                ),
            ),
        )
    )
    assert ("removal_matters", "you", "") in _sigs(ir)


def test_destroy_land_subtype_only_not_removal():
    """'Destroy target Island' (land subtype only) is NOT removal_matters (CR 305.6 —
    a bare land-subtype subject lacks _PERMANENT_TYPES and is not a non-land permanent
    subtype). ADR-0027: land_destruction is now a membership-gated cross-open (a
    creature commander's own repeatable LD), so a synthetic non-creature IR like this
    opens NEITHER lane — only the removal_matters exclusion is asserted here."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="destroy",
                    subject=Filter(subtypes=("Island",)),
                    raw="Destroy target Island",
                ),
            ),
        )
    )
    assert "removal_matters" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_mill_keyword_fires_mill_matters():
    # ADR-0027: mill_matters fires from the Scryfall `Mill` keyword array
    # (_IR_KEYWORD_MAP['mill'], read off the record dict), NOT the `mill` effect
    # category — phase mislabels non-mill effects as `mill`, and every genuine mill
    # carries the keyword. scope "any" (self-mill or opponent-mill). CR 701.13.
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="opp"),)))
    record = {"name": "Test", "keywords": ["Mill"]}
    keys = {(s.key, s.scope, s.subject) for s in extract_signals_ir(record, ir)}
    assert ("mill_matters", "any", "") in keys


def test_mill_effect_without_keyword_does_not_fire_mill_matters():
    # The bare `mill` effect category no longer opens mill_matters (the over-broad doer
    # arm was dropped — it mislabeled Bone Dancer / Scroll Rack / Soldevi Digger). A
    # keyword-LESS record carrying a `mill` effect opens graveyard_matters only.
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="you"),)))
    assert "mill_matters" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_cast_spell_trigger_fires_spellcast_matters():
    # ADR-0027 (SIDECAR 50): the structural arm fires on a `cast_spell` trigger
    # scope='any' over a typed-noncreature subject (Instant/Sorcery) when the card
    # oracle says "you cast" — the Talrand you-cast PAYOFF. phase scopes "you cast" and
    # the symmetric "a player casts" both 'any', so the oracle "you cast" is the gate.
    card = {
        "name": "Talrand",
        "oracle_text": (
            "Whenever you cast an instant or sorcery spell, create a 2/2 blue "
            "Drake creature token with flying."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                subject=Filter(card_types=("Instant", "Sorcery"), controller="any"),
                scope="any",
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_ir(card, ir)}
    assert ("spellcast_matters", "you") in keys


def test_bare_cast_spell_trigger_does_not_fire_spellcast_matters():
    # A bare scope='you' cast_spell trigger with no typed subject is the one-shot
    # "When you cast THIS spell" self-cast (Kozilek, Storm) — NOT the repeatable
    # spellslinger payoff. The structural arm must not fire (it needs scope='any' + a
    # typed subject); the byte-identical mirror also stays silent (CARD has no oracle).
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="cast_spell", scope="you"))
    )
    assert ("spellcast_matters", "you", "") not in _sigs(ir)


def test_attacks_trigger_fires_attack_matters():
    ir = _ir(Ability(kind="triggered", trigger=Trigger(event="attacks", scope="you")))
    assert ("attack_matters", "you", "") in _sigs(ir)


def test_bare_combat_damage_trigger_opens_no_combat_lane():
    """ADR-0027: a STRUCTURELESS combat_damage trigger (no oracle) fires NONE of the
    combat lanes. The unconditional structural `add(combat_damage_matters)` arm was
    DELETED — it over-fired the recipient (every combat_damage AND deals_damage trigger,
    regardless of player/creature/you recipient), because phase drops the recipient TYPE
    off the trigger (valid_target Typed[Creature] vs Player both project to subject=None).
    The base combat_damage_matters lane AND the recipient-specific combat_damage_to_opp /
    combat_damage_to_creature widen lanes are ALL recipient-discriminated by the joined-
    face oracle via the _IR_KEPT_DETECTORS mirrors, so a structureless IR with no oracle
    correctly opens NONE of them."""
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="combat_damage", scope="opp"))
    )
    sigs = _sigs(ir)
    assert ("combat_damage_matters", "opponents", "") not in sigs
    assert ("combat_damage_to_opp", "opponents", "") not in sigs
    assert ("combat_damage_to_creature", "any", "") not in sigs


def test_combat_damage_matters_fires_from_recipient_structure():
    """ADR-0027 (SIDECAR v41): the base CR-510.1b combat_damage_matters lane reads the
    STRUCTURED recipient TYPE phase carries on the combat_damage trigger's valid_target
    (project → trig.recipient). A player/planeswalker recipient ("to one of your
    opponents" → Typed{controller:Opponent} → recipient=("player",)) fires the base lane
    (scope opponents); the three recipient-word mirrors are deleted."""
    card = {
        "name": "Edric",
        "oracle_text": (
            "Whenever a creature deals combat damage to one of your opponents, "
            "its controller may draw a card."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="combat_damage", scope="opp", recipient=("player",)),
        )
    )
    sigs = sorted((s.key, s.scope, s.subject) for s in extract_signals_ir(card, ir))
    assert ("combat_damage_matters", "opponents", "") in sigs


# ── Batch 3: tribal type_matters from Filter subtypes ─────────────────────────


def test_type_matters_from_tribal_anthem():
    """'Goblins you control get +1/+1' → type_matters/you/Goblin."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Goblin",),
                        controller="you",
                    ),
                ),
            ),
        )
    )
    assert ("type_matters", "you", "Goblin") in _sigs(ir)


def test_type_matters_from_tribal_count():
    """'... for each Goblin you control' → type_matters/you/Goblin (the operand);
    the made Goblin token is token_maker, not a second type_matters."""
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(card_types=("Creature",), subtypes=("Goblin",)),
                    amount=Quantity(
                        op="count",
                        subject=Filter(subtypes=("Goblin",), controller="you"),
                    ),
                ),
            ),
        )
    )
    sigs = _sigs(ir)
    assert ("type_matters", "you", "Goblin") in sigs
    assert ("token_maker", "you", "Goblin") in sigs


def test_opponent_tribe_is_not_type_matters():
    """An opponent-controlled subtype filter is not YOUR tribal build-around."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="dies",
                scope="opp",
                subject=Filter(subtypes=("Goblin",), controller="opp"),
            ),
        )
    )
    assert not any(s.key == "type_matters" for s in extract_signals_ir(CARD, ir))


# ── grant_keyword team-anthem lanes (Batch 6) ─────────────────────────────────


def _grant(keyword: str, **filter_kw: object) -> Card:
    """A static granting ``keyword`` to the filtered set (the AddKeyword shape)."""
    return _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    counter_kind=keyword,
                    subject=Filter(**filter_kw),  # type: ignore[arg-type]
                ),
            ),
        )
    )


def test_team_evasion_grant_fires_for_flying_on_your_team():
    ir = _grant("flying", card_types=("Creature",), controller="you")
    assert ("team_evasion_grant", "you", "") in _sigs(ir)


def test_protection_grant_fires_for_team_indestructible():
    """Team-wide indestructible is the 'protect the wide board' want (Akroma's Will,
    Unbreakable Formation) — grouped with hexproof/shroud, distinct from evasion."""
    ir = _grant("indestructible", card_types=("Creature",), controller="you")
    sigs = _sigs(ir)
    assert ("protection_grant", "you", "") in sigs
    assert ("team_evasion_grant", "you", "") not in sigs


def test_grant_keyword_excludes_tribal_grant():
    """A Slivers-have-menace grant is tribal (type_matters), not a team-anthem lane."""
    ir = _grant(
        "menace", card_types=("Creature",), subtypes=("Sliver",), controller="you"
    )
    assert not any(
        s.key in ("team_evasion_grant", "protection_grant")
        for s in extract_signals_ir(CARD, ir)
    )


def test_grant_keyword_excludes_predicate_gated_grant():
    """A predicate (equipment EquippedBy / conditional SelfRef) means it is not a
    flat team anthem — the no-predicates gate that stops the +2197 flood."""
    ir = _grant(
        "flying",
        card_types=("Creature",),
        controller="you",
        predicates=("EquippedBy",),
    )
    assert ("team_evasion_grant", "you", "") not in _sigs(ir)


def test_all_creatures_kw_grant_is_symmetric_any_scope():
    """A controller-agnostic grant (Concordant Crossroads: all creatures have haste)
    is the symmetric lane at scope 'any', not a your-team anthem."""
    ir = _grant("haste", card_types=("Creature",), controller="any")
    sigs = _sigs(ir)
    assert ("all_creatures_kw_grant", "any", "") in sigs
    assert not any(s[0] in ("team_evasion_grant", "protection_grant") for s in sigs)


# ── discard_outlet (cost-based, self-discard split out) ───────────────────────


def test_discard_outlet_fires_for_discard_a_card_cost():
    """'Discard a card: ...' is a discard OUTLET (madness/reanimator fuel)."""
    ir = _ir(
        Ability(kind="activated", cost="discard", effects=(Effect(category="draw"),))
    )
    assert ("discard_outlet", "you", "") in _sigs(ir)


def test_self_discard_cost_is_not_a_discard_outlet():
    """'Discard this card' (Cycling / alt-costs) projects to 'discardself' and must
    NOT fire discard_outlet — the split that unblocks the lane without the flood."""
    ir = _ir(
        Ability(
            kind="activated", cost="discardself", effects=(Effect(category="draw"),)
        )
    )
    assert "discard_outlet" not in {s.key for s in extract_signals_ir(CARD, ir)}


# ── topdeck_stack (position-gated, your-library only) ─────────────────────────


def _topdeck(where: str, controller: str = "you") -> Card:
    """A put-into-library effect (the _library_position_effect shape): position in
    counter_kind, the moved cards as the subject."""
    return _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="topdeck_stack",
                    counter_kind=where,
                    subject=Filter(controller=controller),
                ),
            ),
        )
    )


def test_topdeck_stack_fires_for_top_put_of_your_cards():
    """Return a card to the TOP of your library (Mortuary Mire, Academy Ruins)."""
    assert ("topdeck_stack", "you", "") in _sigs(_topdeck("top"))


def test_topdeck_stack_fires_for_top_or_bottom_choice():
    """A player-choice 'both on top OR both on the bottom' put (Dream Cache) is a
    genuine top-stacking option → counter_kind 'topbottom' fires. ADR-0027."""
    assert ("topdeck_stack", "you", "") in _sigs(_topdeck("topbottom"))


def test_nth_from_top_is_not_topdeck_stack():
    """ADR-0027 gate tighten: 'Nth from the top' is the removal-TUCK position ("put
    target X into its owner's library third from the top" — Teferi, Oust, Chronostutter;
    CR 401.4), NOT self-library curation. It is excluded even when phase mislabels the
    subject controller as 'you' (Riptide Gearhulk — a per-opponent tuck phase parses
    controller=You). The arm fires only on counter_kind in {top, topbottom}."""
    assert "topdeck_stack" not in {
        s.key for s in extract_signals_ir(CARD, _topdeck("nthfromtop"))
    }


def test_bottom_put_is_not_topdeck_stack():
    """A Bottom put ('rest on the bottom', failed-tutor cleanup) is not a top-stack."""
    assert "topdeck_stack" not in {
        s.key for s in extract_signals_ir(CARD, _topdeck("bottom"))
    }


def test_bounce_to_top_removal_is_not_topdeck_stack():
    """'Put target permanent on top of its owner's library' is bounce removal — the
    moved cards are not yours (controller 'any'), so the self-stacking lane stays off."""
    assert "topdeck_stack" not in {
        s.key for s in extract_signals_ir(CARD, _topdeck("top", controller="any"))
    }


# ── predicate-enriched color/power build-around lanes (Batch 5) ───────────────


def _subject_pred(*predicates: str, controller: str = "you") -> Card:
    """A draw effect whose subject filter carries enriched predicates — the shape
    'draw a card for each creature you control with power 4 or greater' projects to."""
    return _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="etb",
                subject=Filter(
                    card_types=("Creature",),
                    controller=controller,
                    predicates=tuple(predicates),
                ),
            ),
        )
    )


def test_multicolor_matters_from_colorcount_ge2():
    assert ("multicolor_matters", "you", "") in _sigs(_subject_pred("ColorCount:GE:2"))


def test_colorcount_ge1_is_not_multicolor():
    """GE:1 = 'is colored', not multicolored (CR: 2+ colors)."""
    sigs = _sigs(_subject_pred("ColorCount:GE:1"))
    assert ("multicolor_matters", "you", "") not in sigs


def test_colorless_matters_fires_unscoped():
    """colorless reads unscoped like its regex (Ancient Stirrings reveals a colorless
    card) — controller 'any' still counts."""
    assert ("colorless_matters", "you", "") in _sigs(
        _subject_pred("ColorCount:EQ:0", controller="any")
    )


def test_power_matters_from_your_big_creature_filter():
    assert ("power_matters", "you", "") in _sigs(
        _subject_pred("PtComparison:Power:GE:4")
    )


def test_low_power_matters_from_your_small_creature_filter():
    assert ("low_power_matters", "you", "") in _sigs(
        _subject_pred("PtComparison:Power:LE:2")
    )


def test_power_filter_on_removal_target_does_not_fire():
    """'destroy target creature with power 4+' is controller 'any' — a removal TARGET,
    not a power build-around, so the you-gated lane stays off."""
    sigs = _sigs(_subject_pred("PtComparison:Power:GE:4", controller="any"))
    assert ("power_matters", "you", "") not in sigs


def test_dynamic_power_comparison_does_not_fire():
    """A relative '* (power less than this creature's)' fight-style check is not a
    fixed power threshold."""
    sigs = _sigs(_subject_pred("PtComparison:Power:LT:*"))
    assert ("low_power_matters", "you", "") not in sigs


def _ferocious_gate(*predicates: str, controller: str = "you") -> Card:
    """A Ferocious-style gated payoff — the power threshold rides the ability's
    Condition.subject ('if/while you control a creature with power N or greater' —
    Colossal Majesty, Heir of the Wilds). The shape the v23 projection emits and
    _condition_power_matters reads (ADR-0027)."""
    return _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="upkeep"),
            condition=Condition(
                kind="controlstype",
                subject=Filter(
                    card_types=("Creature",),
                    controller=controller,
                    predicates=tuple(predicates),
                ),
            ),
            effects=(Effect(category="draw", scope="you"),),
        )
    )


def test_power_matters_from_ferocious_condition_subject():
    """ADR-0027 — a Ferocious gate carrying PtComparison:Power:GE on its
    Condition.subject (Colossal Majesty) opens power_matters via the dedicated
    condition arm the v23 projection enables."""
    assert ("power_matters", "you", "") in _sigs(
        _ferocious_gate("PtComparison:Power:GE:4", "InZone")
    )


def test_condition_power_gate_for_defending_player_does_not_fire():
    """A gate keyed on the DEFENDING player's creature power (Mogg Jailer — controller
    'any') is anti-aggro hate, not a you-side power build-around. The you-gated lane
    stays off."""
    sigs = _sigs(_ferocious_gate("PtComparison:Power:LE:2", controller="any"))
    assert ("power_matters", "you", "") not in sigs
    assert ("low_power_matters", "you", "") not in sigs


def test_condition_subject_does_not_leak_legends_sibling():
    """ADR-0027 sibling guard — the Condition.subject power read is POWER-ONLY. A
    Legendary predicate on a Condition.subject must NOT open legends_matter (only
    e/amt/trigger subjects feed that lane), so the non-migrated sibling can't drift."""
    sigs = _sigs(_ferocious_gate("HasSupertype:Legendary"))
    assert ("legends_matter", "you", "") not in sigs


# ── color_hoser (removal keyed on a specific color) ───────────────────────────


def _removal(category: str, *predicates: str) -> Card:
    return _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category=category,
                    subject=Filter(
                        card_types=("Creature",), predicates=tuple(predicates)
                    ),
                ),
            ),
        )
    )


def test_color_hoser_fires_on_destroy_a_named_color():
    """'Destroy target blue creature' actively hoses blue (Blue Elemental Blast)."""
    assert ("color_hoser", "you", "") in _sigs(_removal("destroy", "HasColor:Blue"))


def test_restricted_removal_nonblack_is_not_color_hoser():
    """'Destroy target nonblack creature' (Doom Blade) is restricted removal sparing
    your color — NotColor, not a hoser. The lane must stay off."""
    sigs = _sigs(_removal("destroy", "NotColor:Black"))
    assert ("color_hoser", "you", "") not in sigs


def test_colorless_removal_is_not_color_hoser():
    """A plain removal with no color predicate never fires the hoser lane."""
    assert "color_hoser" not in {
        s.key for s in extract_signals_ir(CARD, _removal("destroy"))
    }


# ── composite-filter lanes (Batch 12) ─────────────────────────────────────────


def test_nonhuman_attackers_from_attack_trigger():
    """Winota: 'whenever a non-Human creature you control attacks' — NotSubtype:Human
    on the attacking subject, controller you."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="attacks",
                subject=Filter(
                    card_types=("Creature",),
                    controller="you",
                    predicates=("NotSubtype:Human",),
                ),
            ),
        )
    )
    assert ("nonhuman_attackers", "you", "") in _sigs(ir)


def test_typed_anthem_multi_from_anyof_pump():
    """'Each creature that's an Assassin, Mercenary, or Pirate gets +1/+1' — a pump
    over an AnyOf-of-subtypes creature filter."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("AnyOf:Assassin|Mercenary|Pirate",),
                    ),
                ),
            ),
        )
    )
    assert ("typed_anthem_multi", "you", "") in _sigs(ir)


# ── combat-forcing statics (Batch 13) ─────────────────────────────────────────


def _static_effect(category: str, scope: str = "any") -> Card:
    return _ir(
        Ability(kind="static", effects=(Effect(category=category, scope=scope),))
    )


def test_force_attack_fires_forced_attack():
    assert ("forced_attack", "any", "") in _sigs(_static_effect("force_attack"))


def test_cant_block_fires_cant_block_grant():
    assert ("cant_block_grant", "you", "") in _sigs(_static_effect("cant_block"))


def test_lure_fires_lure_matters():
    assert ("lure_matters", "you", "") in _sigs(_static_effect("lure"))


def test_evasion_denial_from_ignore_landwalk():
    assert ("evasion_denial", "opponents", "") in _sigs(
        _static_effect("evasion_denial", scope="opp")
    )


def test_base_pt_set_fires():
    # ADR-0027 Cluster C: the base_pt_set arm fires only when the effect's raw NAMES a
    # base P/T (the fixed-set toolbox) or carries the v32 SelfBasePt marker — so a bare
    # land/artifact mass-animate ("is a N/N creature") stays out of the lane. Lignify's
    # raw names "base power and toughness 0/4".
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="base_pt_set",
                    scope="any",
                    subject=Filter(card_types=("Creature",)),
                    raw="Enchanted creature is a Treefolk with base power and "
                    "toughness 0/4 and loses all abilities.",
                ),
            ),
        )
    )
    assert ("base_pt_set", "any", "") in _sigs(ir)


def test_base_pt_set_land_animator_not_in_lane():
    # ADR-0027 Cluster C: a land mass-animator ("All lands are 1/1 creatures" — Living
    # Plane) emits cat=="base_pt_set" but its raw NAMES no base P/T, so it stays out of
    # base_pt_set (it fires land_creatures_matter via its own arm — a land-creatures
    # theme, not a base-P/T-set build-around). CR 613.4b / 305.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="base_pt_set",
                    scope="any",
                    subject=Filter(card_types=("Land",), controller="any"),
                    raw="All lands are 1/1 creatures that are still lands.",
                ),
            ),
        )
    )
    assert "base_pt_set" not in {k for (k, _s, _u) in _sigs(ir)}


def _clone(*card_types, subtypes=()):
    return _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="clone",
                    subject=Filter(card_types=card_types, subtypes=subtypes),
                ),
            ),
        )
    )


def test_creature_clone_is_clone_matters_only():
    sigs = _sigs(_clone("Creature"))
    assert ("clone_matters", "you", "") in sigs
    assert not any(s[0].startswith("copy_") for s in sigs)


def test_spell_copy_is_its_own_lane_not_clone():
    """Twincast ('copy target spell') is spell_copy_matters, NOT a clone."""
    ir = _ir(Ability(kind="spell", effects=(Effect(category="spell_copy"),)))
    sigs = _sigs(ir)
    assert ("spell_copy_matters", "you", "") in sigs
    assert ("clone_matters", "you", "") not in sigs


def test_creature_subtype_clone_is_clone_matters():
    """Sunfrill Imitator copies a Dinosaur (a creature subtype) → clone_matters."""
    assert ("clone_matters", "you", "") in _sigs(_clone(subtypes=("Dinosaur",)))


def test_artifact_clone_is_copy_artifact_not_clone_matters():
    sigs = _sigs(_clone("Artifact"))
    assert ("copy_artifact", "you", "") in sigs
    assert ("clone_matters", "you", "") not in sigs


def test_permanent_clone_fans_out_to_every_type_lane():
    """A generic Permanent copy (Crystalline Resonance) counts toward copy_permanent
    AND every per-permanent-type lane — Dan's hierarchy."""
    sigs = {s[0] for s in _sigs(_clone("Permanent"))}
    assert {
        "copy_permanent",
        "clone_matters",
        "copy_artifact",
        "copy_enchantment",
        "copy_land",
        "copy_planeswalker",
    } <= sigs


def test_combat_buff_engine_from_begin_combat_pump():
    """A begin-combat trigger that pumps (Additive Evolution) — a co-occurrence."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="begin_combat", scope="you"),
            effects=(Effect(category="place_counter", counter_kind="p1p1"),),
        )
    )
    assert ("combat_buff_engine", "you", "") in _sigs(ir)


def test_damage_reflect_from_damage_received_plus_damage():
    """Boros Reckoner: when dealt damage, deals damage back (co-occurrence)."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="damage_received", scope="you"),
            effects=(Effect(category="damage"),),
        )
    )
    assert ("damage_reflect", "you", "") in _sigs(ir)


def test_damage_received_without_damage_is_not_reflect():
    """'When dealt damage, fight/gain a counter' is NOT a reflector."""
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="damage_received", scope="you"),
            effects=(Effect(category="place_counter"),),
        )
    )
    assert "damage_reflect" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_combat_force_on_opponents_still_feeds_stax():
    """The split must not regress stax: a force/can't-block static hobbling opponents
    is still a pillowfort tax."""
    sigs = _sigs(_static_effect("cant_block", scope="opp"))
    assert ("cant_block_grant", "you", "") in sigs
    assert ("stax_taxes", "opponents", "") in sigs


# ── ADR-0027 C6 stax — restriction-scope structure reads (REAL oracle text) ────
# The IR Effects below are EXACTLY what project.py emits for these real cards
# (verified against phase card-data.json); each carries the card's actual oracle raw.


def _stax_keys(ir: Card, oracle: str = "") -> set[str]:
    rec = {"name": "Test", "oracle_text": oracle}
    return {s.key for s in extract_signals_ir(rec, ir)}


def test_silence_addrestriction_opp_is_stax_taxes():
    """Silence: AddRestriction whose restriction.affected_players is
    OpponentsOfSourceController projects to a restriction scope='opp' (CR 604.1)."""
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="restriction",
                    scope="opp",
                    raw="Your opponents can't cast spells this turn.",
                ),
            ),
        )
    )
    assert "stax_taxes" in _stax_keys(ir, "Your opponents can't cast spells this turn.")


def test_enters_tapped_opponents_is_stax_taxes():
    """Imposing Sovereign / Kinjalli's Sunwing: the enters-tapped ChangeZone
    replacement projects to enters_tapped scope='opp' (valid_card.controller). CR
    614.1c."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="enters_tapped",
                    scope="opp",
                    subject=Filter(card_types=("Creature",), controller="opp"),
                    raw="Creatures your opponents control enter tapped.",
                ),
            ),
        )
    )
    assert _stax_keys(ir) == {"stax_taxes"}


def test_enters_tapped_symmetric_is_symmetric_stax():
    """Orb of Dreams: 'Permanents enter tapped' (valid_card.controller null) is
    symmetric — scope='each' (CR 604.1)."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="enters_tapped",
                    scope="each",
                    subject=Filter(card_types=("Permanent",), controller="any"),
                    raw="Permanents enter tapped.",
                ),
            ),
        )
    )
    assert _stax_keys(ir) == {"symmetric_stax"}


def test_symmetric_cost_tax_cofires_stax_taxes():
    """Sphere of Resistance / Thalia: a symmetric cost-tax (ModifyCost-Raise,
    counter_kind='stax_tax') is symmetric_stax AND co-fires stax_taxes — a symmetric
    tax still hobbles opponents (CR 601.2f)."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="restriction",
                    scope="each",
                    counter_kind="stax_tax",
                    subject=Filter(card_types=("Card",), controller="any"),
                    raw="Spells cost {1} more to cast.",
                ),
            ),
        )
    )
    assert _stax_keys(ir) == {"stax_taxes", "symmetric_stax"}


def test_symmetric_untap_lock_is_symmetric_only():
    """Back to Basics: a symmetric UNTAP lock (no stax_tax marker) is symmetric_stax
    only — it is not a cost/cast tax, so it does not co-fire stax_taxes."""
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="restriction",
                    scope="each",
                    subject=Filter(
                        card_types=("Land",), predicates=("NotSupertype:Basic",)
                    ),
                    raw="Nonbasic lands don't untap during their controllers' "
                    "untap steps.",
                ),
            ),
        )
    )
    keys = _stax_keys(ir)
    assert "symmetric_stax" in keys
    assert "stax_taxes" not in keys


def test_debuff_anthem_on_opponents_is_not_stax():
    """Elesh Norn / Cower in Fear: 'Creatures your opponents control get -2/-2' is a
    pump (debuff), NOT a restriction — the deleted byte-mirror's over-fire. The
    structural arm correctly keeps it OUT of stax (it rides debuff_matters)."""
    oracle = "Creatures your opponents control get -2/-2."
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="opp",
                    subject=Filter(card_types=("Creature",), controller="opp"),
                    raw=oracle,
                ),
            ),
        )
    )
    keys = _stax_keys(ir, oracle)
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_single_target_aura_untap_lock_is_not_symmetric_stax():
    """Dehydration: 'Enchanted creature doesn't untap' is a single-target Aura lock
    (CR 303.4) — restriction scope='any' pred=EnchantedBy — NOT a symmetric lock. The
    deleted byte-mirror wrongly fired symmetric_stax on it; the residue mirror drops
    the `doesn't untap during` branch, so it stays out."""
    oracle = "Enchanted creature doesn't untap during its controller's untap step."
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="restriction",
                    scope="any",
                    subject=Filter(
                        card_types=("Creature",), predicates=("EnchantedBy",)
                    ),
                    raw=oracle,
                ),
            ),
        )
    )
    assert "symmetric_stax" not in _stax_keys(ir, oracle)


def test_residue_mirror_recovers_wholly_dropped_opponent_cast_lock():
    """Dragonlord Dromoka: phase drops 'Your opponents can't cast spells during your
    turn' entirely (zero restriction Effect). The narrow residue keep-mirror recovers
    it as stax_taxes off the reminder-stripped oracle."""
    ir = _ir()  # no restriction Effect — phase emits nothing for this clause
    oracle = "Flying, lifelink\nYour opponents can't cast spells during your turn."
    assert "stax_taxes" in _stax_keys(ir, oracle)


# ── ADR-0027 C6 over-fire fix — single-attached pacify Aura is NOT stax ────────
# Real phase records (focused to the fields project_card reads), projected END-TO-END
# through project_card so this exercises _is_single_attached_restriction +
# _restriction_scope + the stax_tax marker gate, not a hand-built Effect.

_ARREST_REAL = {
    "name": "Arrest",
    "scryfall_oracle_id": "81728b98-8cf9-4734-a318-69184bb4d15c",
    "card_type": {
        "supertypes": [],
        "core_types": ["Enchantment"],
        "subtypes": ["Aura"],
    },
    "oracle_text": (
        "Enchant creature\nEnchanted creature can't attack or block, and its "
        "activated abilities can't be activated."
    ),
    "keywords": [],  # string-list (Scryfall) shape — Enchant kw not load-bearing here
    "abilities": [],
    "triggers": [],
    "static_abilities": [
        {"mode": "CantAttackOrBlock", "affected": {"type": "SelfRef"}},
        {
            "mode": {
                "CantBeActivated": {
                    "who": "AllPlayers",
                    "source_filter": {"type": "SelfRef"},
                    "exemption": "None",
                }
            },
            "affected": {"type": "SelfRef"},
        },
    ],
    "replacements": [],
}

_STATIC_ORB_REAL = {
    "name": "Static Orb",
    "scryfall_oracle_id": "0004ebd0-dfd6-4276-b4a6-de0003e94237",
    "card_type": {"supertypes": [], "core_types": ["Artifact"], "subtypes": []},
    "oracle_text": (
        "As long as this artifact is untapped, players can't untap more than two "
        "permanents during their untap steps."
    ),
    "keywords": [],
    "abilities": [],
    "triggers": [],
    "static_abilities": [
        {
            "mode": "Continuous",
            "affected": {"type": "SelfRef"},
            "condition": {"type": "Not", "condition": {"type": "SourceIsTapped"}},
            "description": (
                "As long as ~ is untapped, players can't untap more than two "
                "permanents during their untap steps."
            ),
        }
    ],
    "replacements": [],
}

_NULL_ROD_REAL = {
    "name": "Null Rod",
    "scryfall_oracle_id": "2f83ca86-e23d-40f7-8085-6928d8cfef9b",
    "card_type": {"supertypes": [], "core_types": ["Artifact"], "subtypes": []},
    "oracle_text": "Activated abilities of artifacts can't be activated.",
    "keywords": [],
    "abilities": [],
    "triggers": [],
    "static_abilities": [
        {
            "mode": {
                "CantBeActivated": {
                    "who": "AllPlayers",
                    "source_filter": {
                        "type": "Typed",
                        "type_filters": ["Artifact"],
                        "controller": None,
                        "properties": [],
                    },
                    "exemption": "None",
                }
            },
            "affected": None,
        }
    ],
    "replacements": [],
}


def _real_stax_keys(record: dict) -> set[str]:
    from mtg_utils._card_ir.project import project_card

    ir = project_card([record])
    return {s.key for s in extract_signals_ir(record, ir)}


def test_pacify_aura_arrest_is_not_stax():
    """Arrest: 'its activated abilities can't be activated' (CantBeActivated,
    who=AllPlayers) on a SelfRef Aura host is single-target pacify (CR 303.4), NOT a
    board-wide tax. The over-fire fix gates it out of BOTH stax lanes despite the
    AllPlayers ``who`` (which only says no player may act on that one creature)."""
    keys = _real_stax_keys(_ARREST_REAL)
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_symmetric_static_orb_still_symmetric_stax():
    """Static Orb: a symmetric 'players can't untap …' lock STILL fires symmetric_stax
    (untap-lock — no stax_tax co-fire), proving the fix does not over-suppress genuine
    board-wide stax."""
    keys = _real_stax_keys(_STATIC_ORB_REAL)
    assert "symmetric_stax" in keys
    assert "stax_taxes" not in keys


def test_prison_piece_null_rod_still_fires_both():
    """Null Rod: 'Activated abilities of artifacts can't be activated' — a real
    card-CLASS source_filter (Typed Artifact, no attach predicate) is genuine symmetric
    stax. It keeps firing symmetric_stax AND co-fires stax_taxes (stax_tax marker)."""
    keys = _real_stax_keys(_NULL_ROD_REAL)
    assert "symmetric_stax" in keys
    assert "stax_taxes" in keys


# ── ADR-0027 C6 FINAL — AFFECTED-ENTITY discriminator (not card type) ──────────
# What a restriction taxes is decided by WHO/WHAT it restricts, never by the host's
# card type (CR 303.4: an Aura attaches to an object OR a PLAYER — an "Enchant player"
# Curse is a player tax, an "Enchant creature" Aura is single-target pacify). The
# discriminator reads the restriction's AFFECTED ENTITY from the structured subject,
# supplement-recovered from the raw clause when phase mangled it (Lost in Thought's
# trailing "...for that player to ignore this effect" leaks the Effect to scope='opp'
# subject=None). A SINGLE creature → drop both lanes; a PLAYER / BOARD → keep. CR 303.4
# / 301.5 / 608.2.

_LOST_IN_THOUGHT_REAL = {
    "name": "Lost in Thought",
    "scryfall_oracle_id": "lost-in-thought-oid",
    "card_type": {
        "supertypes": [],
        "core_types": ["Enchantment"],
        "subtypes": ["Aura"],
    },
    "oracle_text": (
        "Enchant creature\nEnchanted creature can't attack or block, and its "
        "activated abilities can't be activated. Its controller may exile three "
        "cards from their graveyard for that player to ignore this effect until "
        "end of turn."
    ),
    # Scryfall string-list shape; the Aura subtype (not the Enchant kw) is the gate.
    "keywords": [],
    "abilities": [],
    "triggers": [],
    "static_abilities": [
        {"mode": "CantAttackOrBlock", "affected": {"type": "SelfRef"}},
        {
            "mode": {
                "CantBeActivated": {
                    "who": "AllPlayers",
                    "source_filter": {"type": "SelfRef"},
                    "exemption": "None",
                }
            },
            "affected": {"type": "SelfRef"},
        },
    ],
    "replacements": [],
}

_TRAPPED_IN_THE_TOWER_REAL = {
    "name": "Trapped in the Tower",
    "scryfall_oracle_id": "trapped-in-the-tower-oid",
    "card_type": {
        "supertypes": [],
        "core_types": ["Enchantment"],
        "subtypes": ["Aura"],
    },
    "oracle_text": (
        "Enchant creature without flying\nEnchanted creature can't attack or "
        "block, and its activated abilities can't be activated."
    ),
    "keywords": [],
    "abilities": [],
    "triggers": [],
    "static_abilities": [
        {"mode": "CantAttackOrBlock", "affected": {"type": "SelfRef"}},
        {
            "mode": {
                "CantBeActivated": {
                    "who": "AllPlayers",
                    "source_filter": {"type": "SelfRef"},
                    "exemption": "None",
                }
            },
            "affected": {"type": "SelfRef"},
        },
    ],
    "replacements": [],
}


def test_pacify_aura_lost_in_thought_is_not_stax():
    """Lost in Thought: the trailing '...for that player to ignore this effect'
    clause leaks the restriction Effect to scope='opp' subject=None (an over-fire the
    cleanly-structured `_is_single_attached_restriction` gate alone could not catch).
    The raw affected-entity supplement reads 'Enchanted creature' (a SINGLE creature)
    off the mangled (subject=None) restriction and excludes it from BOTH stax lanes."""
    keys = _real_stax_keys(_LOST_IN_THOUGHT_REAL)
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_pacify_aura_trapped_in_the_tower_is_not_stax():
    """Trapped in the Tower: 'Enchant creature without flying' on line 1 + 'can't
    attack' on line 2 form ONE un-split clause; the old residue regex bridged the
    newline (and matched `with` inside 'without'). The tightened regex AND the
    affected-entity ('Enchanted creature' = single) residue guard both keep it out of
    BOTH stax lanes."""
    keys = _real_stax_keys(_TRAPPED_IN_THE_TOWER_REAL)
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_equipment_player_tax_conquerors_flail_fires_stax_taxes():
    """Conqueror's Flail (Equipment): 'your opponents can't cast spells during your
    turn' is a genuine PLAYER tax — the affected entity is opponents, not the equipped
    creature (CR 303.4: card type is NOT the discriminator). The over-broad card-type
    gate wrongly dropped it; the affected-entity discriminator KEEPS it in stax_taxes."""
    oracle = (
        "Equipped creature gets +1/+1 for each color among permanents you control.\n"
        "As long as this Equipment is attached to a creature, your opponents can't "
        "cast spells during your turn.\nEquip {2}"
    )
    assert "stax_taxes" in _stax_keys(_ir(), oracle)


def test_aura_player_tax_curse_of_exhaustion_fires_stax():
    """Curse of Exhaustion ('Enchant player' Aura): 'Enchanted player can't cast more
    than one spell each turn' is a genuine PLAYER tax (Rule-of-Law on one opponent),
    NOT single-target creature pacify. The affected-entity discriminator KEEPS it —
    the card-type gate wrongly dropped every Aura-hosted player tax."""
    oracle = (
        "Enchant player\nEnchanted player can't cast more than one spell each turn."
    )
    assert "stax_taxes" in _stax_keys(_ir(), oracle)


def test_vow_single_target_cant_attack_you_is_not_stax():
    """Vow of Duty (single-target 'Enchant creature' Aura): 'Enchanted creature …
    can't attack you or planeswalkers you control' restricts the ONE enchanted
    creature — single-target pacify, NOT a board pillowfort. The `can't attack you`
    residue branch is ambiguous; the affected-entity guard ('Enchanted creature' =
    single, no player/board tell) keeps it out of BOTH lanes."""
    oracle = (
        "Enchant creature\nEnchanted creature gets +2/+2, has vigilance, and can't "
        "attack you or planeswalkers you control."
    )
    assert "stax_taxes" not in _stax_keys(_ir(), oracle)
    assert "symmetric_stax" not in _stax_keys(_ir(), oracle)


def test_board_counter_tax_with_that_creature_rider_still_fires():
    """Nils, Discipline Enforcer: 'Each creature with one or more counters … can't
    attack you … where X is the number of counters on that creature' is a BOARD tax —
    the trailing 'that creature' names the per-creature count, NOT the affected entity.
    'Each creature' is a board tell, so the discriminator keeps it firing (regression:
    a naive single-creature regex would match 'that creature' and wrongly drop it)."""
    oracle = (
        "Each creature with one or more counters on it can't attack you or "
        "planeswalkers you control unless its controller pays {X}, where X is the "
        "number of counters on that creature."
    )
    assert "stax_taxes" in _stax_keys(_ir(), oracle)


def test_single_target_etb_pacify_is_not_stax_taxes():
    """Spara's Adjudicators: 'target creature an opponent controls can't attack or
    block' is a single-target ETB pacify (CR 303.4-class single-object lock), not a
    board tax. The `(?<!target )` residue guard keeps it out of stax_taxes."""
    oracle = (
        "When this creature enters, target creature an opponent controls can't "
        "attack or block until your next turn."
    )
    assert "stax_taxes" not in _stax_keys(_ir(), oracle)


def test_board_pillowfort_attack_lock_still_fires_stax_taxes():
    """A genuine board pillowfort — 'Creatures you don't control can't attack you
    unless …' (class-wide, plural, no 'target') — STILL fires stax_taxes via the
    residue branch, proving the single-target guard does not over-suppress."""
    oracle = (
        "Creatures you don't control can't attack you unless their controller "
        "pays {2} for each of those creatures."
    )
    assert "stax_taxes" in _stax_keys(_ir(), oracle)


# ── named_permanent (named-card SYNERGY kept word mirror) ─────────────────────
# ADR-0027 Cluster D (SIGNALS-ONLY): named_permanent is the named-card SYNERGY lane
# (a card referencing a specific OTHER card by name). phase drops the referenced
# name, so the lane rides a BYTE-IDENTICAL kept word mirror (_NAMED_PERMANENT_SWEEP_RE
# in _IR_KEPT_DETECTORS over the reminder-stripped oracle, scope 'you'). It is NOT the
# CR 100.2a copy-limit `many_copies` field — that population is intentionally excluded.


def test_named_card_synergy_fires_named_permanent_from_kept_mirror():
    """A card naming a specific partner (CR 712.1) fires the kept-mirror lane."""
    card = {
        "name": "Festering Newt",
        "oracle_text": (
            "When this creature dies, target creature an opponent controls gets "
            "-1/-1 until end of turn. That creature gets -4/-4 instead if you "
            "control a creature named Bogbrew Witch."
        ),
    }
    ir = _ir(Ability(kind="triggered", trigger=Trigger(event="dies", scope="you")))
    sigs = sorted((s.key, s.scope, s.subject) for s in extract_signals_ir(card, ir))
    assert ("named_permanent", "you", "") in sigs


def test_copy_limit_field_alone_does_not_fire_named_permanent():
    """The CR 100.2a copy-limit population (ir.many_copies) is a DIFFERENT signal and
    is NOT folded into named_permanent — the dead `many_copies` arm was removed for the
    behavior-neutral migration. A card flagged many_copies but with only the deck-
    relaxation clause ("cards named X" — not "creature/permanent named X") must NOT
    fire named_permanent; only the synergy mirror does."""
    bare = {
        "name": "X",
        "oracle_text": "A deck can have any number of cards named X.",
    }
    ir = Card(oracle_id="x", name="X", many_copies=True)
    assert "named_permanent" not in {s.key for s in extract_signals_ir(bare, ir)}


def test_copy_limit_card_with_synergy_clause_fires_via_mirror_not_field():
    """Seven Dwarves is many_copies True AND names itself ("creature named Seven
    Dwarves") — it fires named_permanent via the SYNERGY mirror clause, not the
    copy-limit field (the lane is the named-card synergy lane, CR 712.1)."""
    card = {
        "name": "Seven Dwarves",
        "oracle_text": (
            "This creature gets +1/+1 for each other creature named Seven Dwarves "
            "you control.\n"
            "A deck can have up to seven cards named Seven Dwarves."
        ),
    }
    ir = Card(oracle_id="x", name="Seven Dwarves", many_copies=True)
    assert "named_permanent" in {s.key for s in extract_signals_ir(card, ir)}


def test_singleton_card_does_not_fire_named_permanent():
    card = {"name": "Test", "oracle_text": "Draw a card."}
    ir = _ir(Ability(kind="spell", effects=(Effect(category="draw"),)))
    assert "named_permanent" not in {s.key for s in extract_signals_ir(card, ir)}


# ── contract guards ───────────────────────────────────────────────────────────


def test_no_ir_returns_empty():
    assert extract_signals_ir(CARD, None) == []


def test_only_slice_keys_emitted():
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="dies", scope="you")),
        Ability(kind="spell", effects=(Effect(category="gain_life", scope="you"),)),
    )
    assert {s.key for s in extract_signals_ir(CARD, ir)} <= IR_SLICE_KEYS


# ── voltron_matters PAYOFF projection (ADR-0027) ──────────────────────────────
# The structural Aura/Equipment build-around, read from phase's IR instead of the
# oracle-regex floor/sweep rows. NOT migrated (the commander-damage MEMBERSHIP
# fallback stays on regex — it's gated on `not has_other_plan` over the full signal
# set, unreproducible in the IR slice), so these pin the *payoff* half only.


def _voltron(ir: Card) -> bool:
    return ("voltron_matters", "you", "") in _sigs(ir)


def test_voltron_payoff_attach_other_object():
    # Kor Outfitter — attaches ANOTHER Equipment onto a creature (build-around).
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="you"),
            effects=(
                Effect(
                    category="attach",
                    scope="any",
                    raw=(
                        "When ~ enters, you may attach target Equipment you "
                        "control to target creature you control."
                    ),
                ),
            ),
        )
    )
    assert _voltron(ir)


def test_voltron_payoff_cast_aura_equipment_trigger():
    # Sram / Kor Spiritdancer — a cast-an-Aura/Equipment-spell trigger.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                scope="any",
                subject=Filter(subtypes=("Aura",), controller="any"),
            ),
            effects=(Effect(category="draw", scope="you"),),
        )
    )
    assert _voltron(ir)


def test_voltron_payoff_tutor_for_equipment_card():
    # Godo — search your library for an Equipment card.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="you"),
            effects=(
                Effect(
                    category="tutor",
                    subject=Filter(card_types=("Artifact",), subtypes=("Equipment",)),
                ),
            ),
        )
    )
    assert _voltron(ir)


def test_voltron_payoff_attachment_state_predicate():
    # Koll / Reyav — cares about "enchanted or equipped" creatures.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("HasAnyAttachmentOf",),
                    ),
                ),
            ),
        )
    )
    assert _voltron(ir)


def test_voltron_payoff_excludes_equip_cost_self_attach():
    # A plain Equipment's own `Equip {N}` cost is the gear payload, NOT a voltron
    # build-around — the regex floor stays off it, so the projection must too.
    ir = _ir(
        Ability(
            kind="activated",
            cost="mana",
            effects=(Effect(category="attach", scope="any", raw="Equip {2}"),),
        )
    )
    assert not _voltron(ir)


def test_voltron_payoff_excludes_etb_self_attach():
    # "When this Equipment enters, attach it to target creature" (Mithril Coat) is
    # still self-attach (the gear), not a build-around.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="any"),
            effects=(
                Effect(
                    category="attach",
                    scope="any",
                    raw="When ~ enters, attach it to target creature you control.",
                ),
            ),
        )
    )
    assert not _voltron(ir)


def test_voltron_payoff_excludes_removal_aura():
    # Pacifism — a static "enchant creature" removal Aura carries no Attach EFFECT,
    # so it never opens the voltron lane (parity with the regex floor).
    ir = _ir(
        Ability(
            kind="static",
            effects=(Effect(category="restriction", scope="opp"),),
        )
    )
    assert not _voltron(ir)


def test_voltron_payoff_attachment_predicate_in_condition():
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", scope="you"),
            condition=Condition(
                kind="zonechangeobjectmatchesfilter",
                subject=Filter(
                    card_types=("Creature",), predicates=("HasAnyAttachmentOf",)
                ),
            ),
            effects=(Effect(category="bounce", scope="any"),),
        )
    )
    assert _voltron(ir)


# ── type-payoff shapes: tutor / mass-recursion (ADR-0027) ─────────────────────
# Generalized, type-parameterized: a search/dig of a card-type fires that type's
# matters lane (gated on subtypes==() — a subtype tutor is the narrower voltron/aura
# care); a MASS graveyard recursion of the type fires (gated out single-target).


def _matter_keys(ir: Card) -> set[tuple[str, str]]:
    return {
        (s.key, s.subject)
        for s in extract_signals_ir(CARD, ir)
        if s.key in ("artifacts_matter", "enchantments_matter")
    }


def test_type_tutor_fires_matters_lane():
    # Idyllic Tutor — "search your library for an enchantment card" (subtypes empty).
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="tutor",
                    subject=Filter(card_types=("Enchantment",), controller="any"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("enchantments_matter", "")}


def test_type_dig_fires_matters_lane():
    # Glint-Nest Crane — "look at the top four cards, put an artifact into your hand".
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="you"),
            effects=(
                Effect(
                    category="topdeck_select",
                    subject=Filter(card_types=("Artifact",), controller="any"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_composite_tutor_fires_both_lanes():
    # Enlightened Tutor — "an artifact or enchantment card" fires BOTH lanes.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="tutor",
                    subject=Filter(
                        card_types=("Artifact", "Enchantment"), controller="any"
                    ),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


def test_subtype_tutor_does_not_fire_matters_lane():
    # Steelshaper's Gift — "search for an Equipment card" is the narrower voltron care,
    # NOT artifacts_matter (the subtypes==() gate excludes it).
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="tutor",
                    subject=Filter(
                        card_types=("Artifact",),
                        subtypes=("Equipment",),
                        controller="any",
                    ),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == set()


def test_generic_permanent_tutor_does_not_fire_matters_lane():
    # Wargate — "a permanent card" is neither Artifact nor Enchantment.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="tutor",
                    subject=Filter(card_types=("Permanent",), controller="any"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == set()


def test_mass_recursion_fires_matters_lane():
    # Crystal Chimes — "return ALL enchantment cards from your graveyard" (mass tell
    # counter_kind='all', graveyard-sourced, controller you).
    ir = _ir(
        Ability(
            kind="activated",
            cost="mana,sacself,tap",
            effects=(
                Effect(
                    category="bounce",
                    counter_kind="all",
                    subject=Filter(
                        card_types=("Enchantment",),
                        controller="you",
                        predicates=("InZone",),
                    ),
                    zones=("from:graveyard", "to:hand", "in:graveyard"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("enchantments_matter", "")}


def test_single_target_recursion_fires_matters_lane():
    # SETTLED RULE (ADR-0027): a single-target TYPE-RESTRICTED recursion fires the lane
    # — the discriminator is the target FILTER's card-type, not mass-vs-single (CR
    # 115.1/115.10), since type-gating = only useful in that type's deck. Skull of Orm
    # ("return TARGET enchantment card") fires enchantments_matter; Argivian Find
    # (single-target COMPOSITE "artifact OR enchantment card") fires BOTH.
    skull = _ir(
        Ability(
            kind="activated",
            cost="mana,tap",
            effects=(
                Effect(
                    category="bounce",
                    subject=Filter(
                        card_types=("Enchantment",),
                        controller="you",
                        predicates=("InZone",),
                    ),
                    zones=("in:graveyard",),
                ),
            ),
        )
    )
    assert _matter_keys(skull) == {("enchantments_matter", "")}
    argivian = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="bounce",
                    subject=Filter(
                        card_types=("Artifact", "Enchantment"),
                        controller="you",
                        predicates=("InZone",),
                    ),
                    zones=("in:graveyard",),
                ),
            ),
        )
    )
    assert _matter_keys(argivian) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


def test_generic_target_recursion_does_not_fire_matters_lane():
    # The over-fire boundary: a GENERIC-target recursion ("return target card" —
    # Regrowth; "return target permanent card") is NOT type-gated, so it fires nothing.
    regrowth = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="bounce",
                    subject=Filter(controller="you", predicates=("InZone",)),
                    zones=("in:graveyard",),
                ),
            ),
        )
    )
    assert _matter_keys(regrowth) == set()


def test_composite_mass_recursion_fires_both_lanes_any_controller():
    # Open the Vaults — "return all artifact and enchantment cards from all graveyards"
    # (composite, controller any) fires both lanes.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="reanimate",
                    counter_kind="all",
                    subject=Filter(
                        card_types=("Artifact", "Enchantment"), controller="any"
                    ),
                    zones=("from:graveyard", "to:battlefield"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


def test_aura_subtype_recursion_routes_to_enchantments():
    # Dowsing Shaman — "return target Aura" (CR 205.3 — Auras are enchantments) routes
    # to a loose enchantments_matter member (no dedicated Aura lane).
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="bounce",
                    subject=Filter(
                        subtypes=("Aura",), controller="you", predicates=("InZone",)
                    ),
                    zones=("in:graveyard",),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("enchantments_matter", "")}


# ── token-maker + sac-payoff + cost-payer + becomes + ability-payoff (ADR-0027) ─


def test_artifact_token_maker_fires_artifacts_lane():
    # Beza / Emissary Green — a Treasure-token maker phase carries by SUBTYPE with an
    # empty card_types tuple (CR 205.3g) still fires artifacts_matter.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="etb", scope="you"),
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Treasure",), predicates=("Token",)),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_sac_artifact_effect_fires_artifacts_lane():
    # Giant Opportunity — "sacrifice two Foods" (artifact-token sac payoff) fires
    # artifacts_matter (Food is an artifact token).
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="sacrifice",
                    scope="you",
                    subject=Filter(subtypes=("Food",), controller="you"),
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_sac_an_artifact_cost_fires_artifacts_lane():
    # Atog — "Sacrifice an artifact: …" (cost-payer); project surfaces the typed
    # sacrifice marker so artifacts_matter fires.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="sacrifice",
                    scope="you",
                    subject=Filter(card_types=("Artifact",), controller="you"),
                    raw="cost: sacrifice artifact",
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_becomes_artifact_grant_fires_artifacts_lane():
    # Sydri / Karn's Touch — a becomes_type marker (granted Artifact card-type).
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="becomes_type",
                    scope="you",
                    subject=Filter(card_types=("Artifact",), controller="you"),
                    raw="grant: becomes a artifact",
                ),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_ability_of_artifact_trigger_fires_artifacts_lane():
    # Kurkesh — "whenever you activate an ability of an artifact" (event='other',
    # typed subject, scope != opp).
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="other",
                scope="any",
                subject=Filter(card_types=("Artifact",), predicates=("InZone",)),
            ),
        )
    )
    assert _matter_keys(ir) == {("artifacts_matter", "")}


def test_opponent_ability_punisher_does_not_fire_artifacts_lane():
    # Harsh Mentor — "whenever an OPPONENT activates an ability …" is a punisher; phase
    # collapses the multi-type subject to None, so it never fires the own-payoff lane.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="other", scope="opp", subject=None),
        )
    )
    assert _matter_keys(ir) == set()


def test_investigate_keyword_fires_artifacts_lane():
    # Deduce / Bygone Bishop — Investigate (CR 701.27) makes a Clue (a colorless
    # ARTIFACT); the Scryfall keyword is the anchor (phase drops the Clue subtype).
    ir = _ir(Ability(kind="spell", effects=(Effect(category="draw"),)))
    keys = {
        (s.key, s.subject)
        for s in extract_signals_ir({"name": "T", "keywords": ["Investigate"]}, ir)
        if s.key == "artifacts_matter"
    }
    assert keys == {("artifacts_matter", "")}


# ── include_membership threading (ADR-0027 membership-reuse pattern) ───────────
# extract_signals_ir gates the signals derived from what a card IS (own card-type,
# own-subtype tribal) on include_membership, mirroring extract_signals — so the
# deck-aggregate path (False for the 99) doesn't flood with every creature's race.

_ARTIFACT_CMD = {"name": "X", "type_line": "Legendary Artifact Creature — Golem"}
_TRIBAL_CMD = {"name": "X", "type_line": "Legendary Creature — Elf Warrior"}


def test_ir_membership_on_by_default():
    ir = _ir()
    keys = {(s.key, s.subject) for s in extract_signals_ir(_ARTIFACT_CMD, ir)}
    assert ("artifacts_matter", "") in keys


def test_ir_membership_off_drops_own_type_and_tribe():
    ir = _ir()
    art = {
        (s.key, s.subject)
        for s in extract_signals_ir(_ARTIFACT_CMD, ir, include_membership=False)
    }
    assert ("artifacts_matter", "") not in art
    trib = {
        (s.key, s.subject)
        for s in extract_signals_ir(_TRIBAL_CMD, ir, include_membership=False)
    }
    assert ("type_matters", "Elf") not in trib


def test_ir_membership_flag_does_not_touch_payoff_signals():
    # the voltron PAYOFF fires regardless of the flag (it's a text payoff, not
    # membership) — parity with the regex producer.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                scope="any",
                subject=Filter(subtypes=("Equipment",), controller="any"),
            ),
            effects=(Effect(category="draw", scope="you"),),
        )
    )
    on = {s.key for s in extract_signals_ir(_TRIBAL_CMD, ir)}
    off = {s.key for s in extract_signals_ir(_TRIBAL_CMD, ir, include_membership=False)}
    assert "voltron_matters" in on
    assert "voltron_matters" in off


def test_devour_keyword_opens_plus_one_matters():
    """Devour (CR 702.82) enters with +1/+1 counters per sacrificed creature — a
    definitional +1/+1 source, so the printed keyword opens plus_one_matters as well
    as devour_matters (Preyseizer Dragon, whose devour rides the keyword + a
    board_count, not a structured `devour` effect)."""
    card = {"name": "Preyseizer Dragon", "keywords": ["Flying", "Devour"]}
    keys = {s.key for s in extract_signals_ir(card, _ir())}
    assert "devour_matters" in keys
    assert "plus_one_matters" in keys


# ── opp_top_exile (ADR-0027 q2-D2 — name-lock / impulse-cast steal) ────────────


def test_opp_top_exile_from_impulse_cast_co_occurrence():
    # Sub-shape A: an exile Effect scope='opp' co-occurring (same ability) with a
    # cast_from_zone Effect scope='opp' — the "you may cast them" follow-through
    # (Villainous Wealth, Ragavan, Wrexial). Scope is the engine controller 'you'.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="exile",
                    scope="opp",
                    raw="Target opponent exiles the top X cards of their library.",
                ),
                Effect(
                    category="cast_from_zone",
                    scope="opp",
                    raw="You may cast any number of spells from among them.",
                ),
            ),
        )
    )
    assert ("opp_top_exile", "you", "") in _sigs(ir)


def test_opp_top_exile_from_library_tag():
    # Sub-shape B: an exile Effect scope='opp' carrying an 'in:library' zone tag
    # (Brainstealer Dragon, Ulamog the Defiler) — phase tagged the library origin
    # directly, so no cast_from_zone co-occurrence is required.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="end_step", scope="any"),
            effects=(
                Effect(
                    category="exile",
                    scope="opp",
                    zones=("to:exile", "in:library"),
                    raw="exile the top card of each opponent's library",
                ),
            ),
        )
    )
    assert ("opp_top_exile", "you", "") in _sigs(ir)


def test_opp_top_exile_does_not_fire_on_bare_opponent_exile_removal():
    # Precision: opponent-targeted exile-as-REMOVAL (Path to Exile, Agonizing
    # Remorse) is exile scope='opp' with NO cast_from_zone and NO 'in:library' — it
    # must never open the steal lane (CR 406 — exile is public, but only the play-it
    # follow-through is this lane).
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="exile",
                    scope="opp",
                    raw="Exile target creature an opponent controls.",
                ),
            ),
        )
    )
    assert not any(k == "opp_top_exile" for k, _, _ in _sigs(ir))


# ── direct_damage from a player-reaching damage doubler (ADR-0027 C7) ──────────


def test_player_reaching_doubler_emits_direct_damage():
    # A damage_doubling Effect with subject=None (absent / {Player} target_filter —
    # Furnace of Rath, Fiery Emancipation) reaches a player (CR 115.4): it feeds
    # direct_damage AND damage_doubling.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="damage_doubling",
                    scope="you",
                    raw="If a source would deal damage to a permanent or player, it "
                    "deals double that damage instead.",
                ),
            ),
        )
    )
    keys = {k for k, _, _ in _sigs(ir)}
    assert "damage_doubling" in keys
    assert "direct_damage" in keys


def test_creature_only_doubler_is_not_direct_damage():
    # A CreatureOnly doubler carries a Creature subject from the projection (Blind
    # Fury): players excluded (CR 120.1), so it stays out of direct_damage but still
    # opens damage_doubling.
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="damage_doubling",
                    scope="you",
                    subject=Filter(card_types=("Creature",)),
                    raw="If a creature would deal combat damage to a creature this "
                    "turn, it deals double that damage to that creature instead.",
                ),
            ),
        )
    )
    keys = {k for k, _, _ in _sigs(ir)}
    assert "damage_doubling" in keys
    assert "direct_damage" not in keys


def test_bare_fragment_doubler_marker_with_multiply_sibling_is_not_direct_damage():
    # Borborygmos / Chocobo / Cut bake the doubling into a real op=multiply `damage`
    # sibling (recipient scored by the base damage arm) PLUS a recipient-less
    # bare-fragment damage_doubling marker (subject=None). The marker must NOT
    # over-fire direct_damage — the card-level multiply-sibling gate suppresses it.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="damage",
                    scope="any",
                    amount=Quantity(op="multiply", factor=2),
                    raw="Target creature deals damage to itself equal to its power.",
                ),
            ),
        ),
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="damage_doubling",
                    scope="you",
                    raw="deals twice that much",
                ),
            ),
        ),
    )
    keys = {k for k, _, _ in _sigs(ir)}
    assert "damage_doubling" in keys
    assert "direct_damage" not in keys


# ── facedown_matters (ADR-0027 C9 — CR 708 Face-Down Spells and Permanents) ───
# Real-card IR shapes verified against the v49 sidecar (see commit body).


def test_facedown_from_turn_face_up_trigger_event():
    # Bonethorn Valesk: "Whenever a permanent is turned face up, this creature
    # deals 1 damage to any target." phase emits a turn_face_up TRIGGER event
    # (Permanent/any subject) — the generic phrasing the byte mirror's narrow
    # "turn it/that face up" pattern misses. Arm B.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="turn_face_up",
                subject=Filter(card_types=("Permanent",), controller="any"),
                scope="any",
            ),
            effects=(
                Effect(
                    category="damage",
                    raw="this creature deals 1 damage to any target.",
                ),
            ),
        )
    )
    assert "facedown_matters" in {k for k, _, _ in _sigs(ir)}


def test_facedown_from_subtype_marker_subject():
    # Ixidor, Reality Sculptor: "Face-down creatures get +1/+1." phase narrows the
    # static pump subject to subtype "Face-down". Arm C (exact subtype token).
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(card_types=("Creature",), subtypes=("Face-down",)),
                    raw="Face-down creatures get +1/+1.",
                ),
            ),
        )
    )
    assert "facedown_matters" in {k for k, _, _ in _sigs(ir)}


def test_facedown_from_predicate_marker_subject():
    # Sumala Sentry: "Whenever a face-down permanent you control is turned face up,
    # put a +1/+1 counter on it and on this creature." phase marks the trigger
    # subject with the FaceDown predicate. Arm C (exact predicate token) + arm B.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="turn_face_up",
                subject=Filter(
                    card_types=("Permanent",),
                    controller="you",
                    predicates=("FaceDown",),
                ),
                scope="you",
            ),
            effects=(
                Effect(
                    category="place_counter",
                    counter_kind="p1p1",
                    raw="put a +1/+1 counter on it and on this creature.",
                ),
            ),
        )
    )
    assert "facedown_matters" in {k for k, _, _ in _sigs(ir)}


def test_facedown_from_cloak_keyword():
    # Unexplained Absence: keyword Cloak (CR 701.58) — a face-down 2/2 maker that
    # phase does NOT carry in IR kw (cloak rides an effect category). The Scryfall
    # keyword array is the uniform anchor. Arm A.
    card = {"name": "Unexplained Absence", "keywords": ["Cloak"]}
    ir = _ir(
        Ability(
            kind="spell",
            effects=(Effect(category="other", raw="...cloaks the top card..."),),
        )
    )
    keys = {s.key for s in extract_signals_ir(card, ir)}
    assert "facedown_matters" in keys


def test_facedown_from_morph_keyword():
    # A vanilla Morph body (CR 702.37) with no structural face-down anchor —
    # keyword-array re-key. Arm A. Confirms morph/megamorph/disguise re-key.
    card = {"name": "Lumbering Laundry", "keywords": ["Disguise"]}
    ir = _ir(Ability(kind="spell", effects=(Effect(category="other", raw="..."),)))
    assert "facedown_matters" in {s.key for s in extract_signals_ir(card, ir)}


def test_dfc_subject_does_not_leak_facedown():
    # Exact-token guard: a "Double-faced Artifact" subtype subject (a DFC, the only
    # other face* subtype in the corpus) must NOT open facedown_matters — substring
    # "face" would leak it. CR 712 (DFC) ≠ CR 708 (face-down).
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    subject=Filter(subtypes=("Double-faced Artifact",)),
                    raw="Double-faced artifacts you control get +1/+1.",
                ),
            ),
        )
    )
    assert "facedown_matters" not in {k for k, _, _ in _sigs(ir)}


def test_transform_trigger_does_not_fire_facedown():
    # A CR-712 DFC transform trigger is a SEPARATE event from turn_face_up; arm B
    # reads only turn_face_up, so a transform payoff must NOT open facedown_matters.
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="transform",
                subject=Filter(card_types=("Permanent",), controller="you"),
                scope="you",
            ),
            effects=(Effect(category="draw", raw="draw a card."),),
        )
    )
    assert "facedown_matters" not in {k for k, _, _ in _sigs(ir)}


# ── ADR-0027 C8 (SIDECAR v50) — topdeck_selection / dig_until owner-resolved arms ──
# The OWNER now rides an additive top:you / top:opp zone tag
# (project._recover_top_of_library_owner); the signal arms gate on the OWNER, not the
# (often-'any') scope. CR 401.1 / 701.18 / 701.23.


def _keys(ir: Card) -> set[str]:
    return {s.key for s in extract_signals_ir(CARD, ir)}


def test_topdeck_selection_from_top_you_reveal():
    # Fact or Fiction — a reveal scope='any' (an opponent separates) whose library is
    # YOURS via the top:you tag. The owner-resolved arm fires topdeck_selection.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="reveal",
                    scope="any",
                    raw="Reveal the top five cards of your library.",
                    zones=("from:top", "to:graveyard", "top:you"),
                ),
            ),
        )
    )
    assert "topdeck_selection" in _keys(ir)


def test_topdeck_selection_excludes_opponent_library():
    # Gonti — a top:opp peek at an opponent's library is theft (CR 401.1), NOT the
    # controller's own top-of-deck curation. The owner gate keeps it OUT.
    ir = _ir(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="topdeck_select",
                    scope="opp",
                    raw="Look at the top four cards of target opponent's library.",
                    zones=("from:top", "to:exile", "top:opp"),
                ),
            ),
        )
    )
    assert "topdeck_selection" not in _keys(ir)


def test_dig_until_from_cheat_play_top_you_until():
    # Mass Polymorph — a reveal-UNTIL re-categorized to cheat_play, owner top:you, with
    # an "until you reveal" body → the owner-resolved dig_until arm fires.
    ir = _ir(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="cheat_play",
                    scope="you",
                    raw=(
                        "Reveal cards from the top of your library until you reveal "
                        "that many creature cards."
                    ),
                    zones=("from:top", "to:battlefield", "top:you"),
                ),
            ),
        )
    )
    assert "dig_until" in _keys(ir)


def test_dig_until_not_fired_by_until_end_of_turn_duration():
    # A reveal-the-top-card with an "until end of turn" DURATION rider (Stormchaser
    # Chimera, the Deceiver cycle) is NOT a dig-until-a-condition — the `until you`
    # discriminator keeps it out of dig_until (it is topdeck_selection only).
    ir = _ir(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="reveal",
                    scope="any",
                    raw=(
                        "Reveal the top card of your library. This creature gets "
                        "+X/+0 until end of turn."
                    ),
                    zones=("from:top", "top:you"),
                ),
            ),
        )
    )
    keys = _keys(ir)
    assert "dig_until" not in keys
    assert "topdeck_selection" in keys
