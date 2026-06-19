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


# ── graveyard_matters (scoped) ────────────────────────────────────────────────


def test_graveyard_from_reanimate_scoped_opp():
    ir = _ir(
        Ability(kind="triggered", effects=(Effect(category="reanimate", scope="opp"),))
    )
    assert _sigs(ir) == [("graveyard_matters", "opponents", "")]


def test_graveyard_from_self_mill():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="you"),)))
    # A mill effect feeds a graveyard AND is a mill payoff (mill_matters).
    assert _sigs(ir) == [("graveyard_matters", "you", ""), ("mill_matters", "any", "")]


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
    # A creature-token-maker with a captured subject cross-opens creatures_matter
    # (the go-wide mass-token DOER), mirroring the regex SWEEP cross-open.
    assert _sigs(ir) == [
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
                    subject=Filter(
                        card_types=("Creature",), subtypes=("Human", "Soldier")
                    ),
                ),
            ),
        )
    )
    # Subject-bearing creature-token-maker → cross-opens creatures_matter (go-wide).
    assert _sigs(ir) == [
        ("creatures_matter", "you", ""),
        ("token_maker", "you", "Soldier"),
    ]


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
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", scope="you"),
            effects=(Effect(category="draw"),),
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
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="dies", scope="any"),
            effects=(Effect(category="draw"),),
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


def test_place_counter_effect_does_not_flood_counters_matter():
    """place_counter -> counters_matter is deferred (needs counter-kind), so a bare
    counter-placing effect does not fire the lane (avoids loyalty/charge floods)."""
    ir = _ir(Ability(kind="triggered", effects=(Effect(category="place_counter"),)))
    assert "counters_matter" not in {s.key for s in extract_signals_ir(CARD, ir)}


def test_mill_effect_fires_mill_matters():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="mill", scope="opp"),)))
    assert ("mill_matters", "any", "") in _sigs(ir)


def test_cast_spell_trigger_fires_spellcast_matters():
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="cast_spell", scope="you"))
    )
    assert ("spellcast_matters", "you", "") in _sigs(ir)


def test_attacks_trigger_fires_attack_matters():
    ir = _ir(Ability(kind="triggered", trigger=Trigger(event="attacks", scope="you")))
    assert ("attack_matters", "you", "") in _sigs(ir)


def test_combat_damage_trigger_fires_combat_damage_to_opp():
    ir = _ir(
        Ability(kind="triggered", trigger=Trigger(event="combat_damage", scope="opp"))
    )
    assert ("combat_damage_to_opp", "opponents", "") in _sigs(ir)


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


def test_topdeck_stack_fires_for_nth_from_top():
    assert ("topdeck_stack", "you", "") in _sigs(_topdeck("nthfromtop"))


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
    assert ("base_pt_set", "any", "") in _sigs(_static_effect("base_pt_set"))


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


# ── named_permanent (deck_copy_limit field) ───────────────────────────────────


def test_many_copies_card_fires_named_permanent():
    ir = Card(oracle_id="x", name="Relentless Rats", many_copies=True)
    assert ("named_permanent", "you", "") in _sigs(ir)


def test_singleton_card_does_not_fire_named_permanent():
    ir = _ir(Ability(kind="spell", effects=(Effect(category="draw"),)))
    assert "named_permanent" not in {s.key for s in extract_signals_ir(CARD, ir)}


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
