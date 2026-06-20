"""Card IR schema + projection tests.

Fixtures are REAL phase-rs ``card-data.json`` face records (the exact nested
structures phase emits), so the projection is exercised against ground-truth
parser output rather than a fabricated shape. The three cards pin the hard axes
the IR exists to solve:

* Craterhoof Behemoth — a pump whose amount *scales with your creature count*
  (the operand-binding #1 pain), nested inside a GenericEffect.
* Shamanic Revelation — a draw scaling with creature count AND a life-gain that
  is 4x (creatures with power >= 4): operand + a property predicate.
* Tinybones, the Pickpocket — casts from *that player's* graveyard: the
  opponent-graveyard SCOPE phase buries in a description string, recovered by the
  supplement.
"""

from __future__ import annotations

from mtg_utils._card_ir.project import (
    _collect_effects,
    _copied_type_from_text,
    _dropped_static_markers,
    _filter,
    _graveyard_cast_grant_markers,
    _graveyard_count_markers,
    _has_graveyard_count,
    _lifeloss_markers,
    _modal_split_effects,
    _narrow_payoff_condition_refs,
    _narrow_token_subtype_makers,
    _narrow_trigger_other_refs,
    _norm_counter_kind,
    _predicate,
    _project_effect,
    _project_replacement,
    _quantity,
    _recover_count_operand,
    _recover_graveyard_zones,
    _sacrifice_cost_markers,
    _sacrifice_grant_markers,
    _sacrifice_player_scope,
    project_card,
)
from mtg_utils.card_ir import Ability, Card, Effect, Filter, Quantity, Trigger

# ── real phase records (focused to the fields project() reads) ────────────────

CRATERHOOF = {
    "name": "Craterhoof Behemoth",
    "scryfall_oracle_id": "8c52bd39-0586-48ca-b263-17210cf9feb6",
    "card_type": {"supertypes": [], "core_types": ["Creature"], "subtypes": ["Beast"]},
    "oracle_text": (
        "Haste\nWhen this creature enters, creatures you control gain trample and "
        "get +X/+X until end of turn, where X is the number of creatures you control."
    ),
    "keywords": ["Haste"],
    "triggers": [
        {
            "mode": "ChangesZone",
            "execute": {
                "kind": "Spell",
                "effect": {
                    "type": "GenericEffect",
                    "static_abilities": [
                        {
                            "mode": "Continuous",
                            "affected": {
                                "type": "Typed",
                                "type_filters": ["Creature"],
                                "controller": "You",
                                "properties": [],
                            },
                            "modifications": [
                                {
                                    "type": "AddDynamicPower",
                                    "value": {
                                        "type": "Ref",
                                        "qty": {
                                            "type": "ObjectCount",
                                            "filter": {
                                                "type": "Typed",
                                                "type_filters": ["Creature"],
                                                "controller": "You",
                                                "properties": [],
                                            },
                                        },
                                    },
                                },
                                {
                                    "type": "AddDynamicToughness",
                                    "value": {
                                        "type": "Ref",
                                        "qty": {
                                            "type": "ObjectCount",
                                            "filter": {
                                                "type": "Typed",
                                                "type_filters": ["Creature"],
                                                "controller": "You",
                                                "properties": [],
                                            },
                                        },
                                    },
                                },
                                {"type": "AddKeyword", "keyword": "Trample"},
                            ],
                            "description": (
                                "gain trample and get +x/+x until end of turn, "
                                "where x is the number of creatures you control"
                            ),
                        }
                    ],
                    "duration": "UntilEndOfTurn",
                    "target": None,
                },
            },
            "valid_card": {"type": "SelfRef"},
            "destination": "Battlefield",
            "trigger_zones": ["Battlefield"],
            "description": (
                "When ~ enters, creatures you control gain trample and get +X/+X "
                "until end of turn, where X is the number of creatures you control."
            ),
        }
    ],
}

SHAMANIC = {
    "name": "Shamanic Revelation",
    "scryfall_oracle_id": "d1d171de-1c6d-4fb9-817a-9c689c709f3d",
    "card_type": {"supertypes": [], "core_types": ["Sorcery"], "subtypes": []},
    "oracle_text": (
        "Draw a card for each creature you control.\nFerocious — You gain 4 life "
        "for each creature you control with power 4 or greater."
    ),
    "abilities": [
        {
            "kind": "Spell",
            "effect": {
                "type": "Draw",
                "count": {
                    "type": "Ref",
                    "qty": {
                        "type": "ObjectCount",
                        "filter": {
                            "type": "Typed",
                            "type_filters": ["Creature"],
                            "controller": "You",
                            "properties": [],
                        },
                    },
                },
                "target": {"type": "Controller"},
            },
            "description": "Draw a card for each creature you control.",
        },
        {
            "kind": "Spell",
            "effect": {
                "type": "GainLife",
                "amount": {
                    "type": "Multiply",
                    "factor": 4,
                    "inner": {
                        "type": "Ref",
                        "qty": {
                            "type": "ObjectCount",
                            "filter": {
                                "type": "Typed",
                                "type_filters": ["Creature"],
                                "controller": "You",
                                "properties": [
                                    {
                                        "type": "PowerGE",
                                        "value": {"type": "Fixed", "value": 4},
                                    }
                                ],
                            },
                        },
                    },
                },
                "player": "controller",
            },
            "description": (
                "Ferocious — You gain 4 life for each creature you control with "
                "power 4 or greater."
            ),
        },
    ],
}

TINYBONES = {
    "name": "Tinybones, the Pickpocket",
    "scryfall_oracle_id": "7bc4c7e2-6758-4a85-84e7-03ab93981106",
    "card_type": {
        "supertypes": ["Legendary"],
        "core_types": ["Creature"],
        "subtypes": ["Skeleton", "Rogue"],
    },
    "oracle_text": (
        "Deathtouch\nWhenever Tinybones deals combat damage to a player, you may "
        "cast target nonland permanent card from that player's graveyard, and mana "
        "of any type can be spent to cast that spell."
    ),
    "keywords": ["Deathtouch"],
    "triggers": [
        {
            "mode": "DamageDone",
            "execute": {
                "kind": "Spell",
                "effect": {
                    "type": "GenericEffect",
                    "static_abilities": [
                        {
                            "mode": "SpendManaAsAnyColor",
                            "affected": None,
                            "modifications": [],
                            "description": (
                                "cast target nonland permanent card from that "
                                "player's graveyard, and mana of any type can be "
                                "spent to cast that spell"
                            ),
                        }
                    ],
                    "duration": None,
                    "target": {"type": "Controller"},
                },
                "optional": True,
            },
            "valid_card": None,
            "trigger_zones": ["Battlefield"],
            "damage_kind": "CombatOnly",
            "valid_target": {"type": "Player"},
            "valid_source": {"type": "SelfRef"},
            "optional": True,
            "description": (
                "Whenever ~ deals combat damage to a player, you may cast target "
                "nonland permanent card from that player's graveyard, and mana of "
                "any type can be spent to cast that spell."
            ),
        }
    ],
}


# Heliod, God of the Sun — a devotion THRESHOLD (DevotionGE in a static's condition,
# wrapped in Not for the "less than five" form). batch 8 captured devotion only as a
# scaling amount; this pins the conditional path that surfaces the Theros gods.
HELIOD = {
    "name": "Heliod, God of the Sun",
    "scryfall_oracle_id": "4ea488b2-5ba0-4565-b928-570c8e03b926",
    "card_type": {
        "supertypes": ["Legendary"],
        "core_types": ["Enchantment", "Creature"],
        "subtypes": ["God"],
    },
    "oracle_text": (
        "Indestructible\nAs long as your devotion to white is less than five, "
        "Heliod isn't a creature.\nOther creatures you control have vigilance."
    ),
    "keywords": ["Indestructible"],
    "static_abilities": [
        {
            "mode": "Continuous",
            "affected": {"type": "SelfRef"},
            "modifications": [{"type": "RemoveType", "core_type": "Creature"}],
            "condition": {
                "type": "Not",
                "condition": {
                    "type": "DevotionGE",
                    "colors": ["White"],
                    "threshold": 5,
                },
            },
            "description": (
                "As long as your devotion to white is less than five, ~ isn't a "
                "creature."
            ),
        }
    ],
}


def _effects(card: Card) -> list[Effect]:
    return [e for a in card.all_abilities() for e in a.effects]


def _effect_with(card: Card, category: str) -> Effect:
    matches = [e for e in _effects(card) if e.category == category]
    assert matches, f"no {category} effect in {card.name}: {_effects(card)}"
    return matches[0]


# ── Craterhoof: operand-binding inside a GenericEffect ────────────────────────


def test_craterhoof_identity():
    card = project_card([CRATERHOOF])
    assert card.oracle_id == "8c52bd39-0586-48ca-b263-17210cf9feb6"
    assert card.name == "Craterhoof Behemoth"
    assert len(card.faces) == 1
    assert "Haste" in card.keywords


def test_craterhoof_etb_trigger():
    card = project_card([CRATERHOOF])
    triggered = [a for a in card.all_abilities() if a.kind == "triggered"]
    assert triggered, "Craterhoof should have a triggered ability"
    assert triggered[0].trigger is not None
    assert triggered[0].trigger.event == "etb"


def test_craterhoof_pump_scales_with_creature_count():
    """The #1 pain: the +X/+X is bound to YOUR creature count, not a flat string."""
    card = project_card([CRATERHOOF])
    pump = _effect_with(card, "pump")
    assert pump.amount is not None
    assert pump.amount.op == "count"
    assert pump.amount.subject == Filter(card_types=("Creature",), controller="you")


# ── Shamanic Revelation: operand + property predicate ─────────────────────────


def test_shamanic_draw_scales_with_creatures():
    card = project_card([SHAMANIC])
    draw = _effect_with(card, "draw")
    assert draw.amount == Quantity(
        op="count", factor=1, subject=Filter(card_types=("Creature",), controller="you")
    )
    assert draw.scope == "you"


def test_shamanic_lifegain_multiplies_by_power_filtered_count():
    card = project_card([SHAMANIC])
    life = _effect_with(card, "gain_life")
    assert life.amount is not None
    assert life.amount.op == "multiply"
    assert life.amount.factor == 4
    assert life.amount.subject == Filter(
        card_types=("Creature",), controller="you", predicates=("PowerGE:4",)
    )


# ── Tinybones: opponent-graveyard scope recovered by the supplement ───────────


def test_tinybones_combat_damage_trigger():
    card = project_card([TINYBONES])
    triggered = [a for a in card.all_abilities() if a.kind == "triggered"]
    assert triggered
    assert triggered[0].trigger is not None
    assert triggered[0].trigger.event == "combat_damage"


def test_tinybones_graveyard_cast_scoped_to_opponents():
    """phase buries 'that player's graveyard' in a description; the supplement
    must recover an opponent-scoped graveyard-cast effect."""
    card = project_card([TINYBONES])
    effs = _effects(card)
    gy = [e for e in effs if "graveyard" in e.raw.lower()]
    assert gy, f"expected a graveyard-referencing effect, got {effs}"
    assert all(e.scope == "opp" for e in gy), gy
    # cast-from-graveyard is reanimation-shaped for synergy purposes
    assert any(e.category in {"reanimate", "other"} for e in gy)


# ── Heliod: a devotion THRESHOLD recovered from a static's condition ──────────


def test_devotion_threshold_condition_emits_devotion_operand():
    """A static gated on DevotionGE (even negated) carries a devotion operand so the
    devotion_matters lane fires — batch 8 only saw devotion as a scaling amount."""
    card = project_card([HELIOD])
    devotion = [
        e for e in _effects(card) if e.amount is not None and e.amount.op == "devotion"
    ]
    assert devotion, f"expected a devotion-operand effect, got {_effects(card)}"
    assert devotion[0].scope == "you"


# ── predicate enrichment (color / count / power threshold kept) ───────────────


def test_predicate_keeps_color_count_and_power_threshold():
    assert _predicate({"type": "HasColor", "color": "Red"}) == "HasColor:Red"
    assert (
        _predicate({"type": "ColorCount", "comparator": "GE", "count": 2})
        == "ColorCount:GE:2"
    )
    assert (
        _predicate(
            {
                "type": "PtComparison",
                "stat": "Power",
                "comparator": "GE",
                "value": {"type": "Fixed", "value": 4},
            }
        )
        == "PtComparison:Power:GE:4"
    )
    # A dynamic (non-Fixed) comparison value collapses to '*' (relative, not a theme).
    assert (
        _predicate(
            {
                "type": "PtComparison",
                "stat": "Power",
                "comparator": "LT",
                "value": {"type": "Ref", "qty": {}},
            }
        )
        == "PtComparison:Power:LT:*"
    )
    # The legends/historic consumers must still see their exact strings.
    assert (
        _predicate({"type": "HasSupertype", "value": "Legendary"})
        == "HasSupertype:Legendary"
    )
    assert _predicate({"type": "Historic"}) == "Historic"


# ── composite filters: negation / disjunction become predicates, not types ────


def test_non_filter_is_a_negation_predicate_not_a_type():
    """A {Non: Land} entry must NOT read as a Land filter (the inverted-meaning bug
    that fed land_destruction off 'destroy target nonland permanent')."""
    f = _filter({"type": "Typed", "type_filters": ["Permanent", {"Non": "Land"}]})
    assert f is not None
    assert "Land" not in f.card_types
    assert "NotType:Land" in f.predicates


def test_non_subtype_filter_is_a_negation_predicate():
    f = _filter(
        {"type": "Typed", "type_filters": ["Creature", {"Non": {"Subtype": "Human"}}]}
    )
    assert f is not None
    assert "Human" not in f.subtypes
    assert "NotSubtype:Human" in f.predicates


def test_anyof_filter_becomes_a_disjunction_predicate():
    """{AnyOf: [...]} was dropped entirely; now a sorted AnyOf predicate."""
    f = _filter({"type": "Typed", "type_filters": [{"AnyOf": ["Sorcery", "Instant"]}]})
    assert f is not None
    assert "AnyOf:Instant|Sorcery" in f.predicates


# ── combat-forcing statics: split out of stax, self-drawbacks gated ───────────


def _static_card(mode, affected):
    return {
        "name": "T",
        "scryfall_oracle_id": "id-combat",
        "card_type": {"core_types": ["Enchantment"]},
        "oracle_text": "",
        "static_abilities": [{"mode": mode, "affected": affected, "modifications": []}],
    }


def test_must_attack_on_a_creature_set_is_force_attack():
    """'Creatures attack each combat if able' (Typed affected) → force_attack."""
    rec = _static_card(
        "MustAttack",
        {"type": "Typed", "type_filters": ["Creature"], "controller": None},
    )
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "force_attack" in cats
    assert "restriction" not in cats  # not stax


def test_self_must_attack_is_not_force_attack():
    """'This creature attacks each combat if able' (SelfRef) is a vanilla drawback,
    not a force-the-table theme — emits no force_attack."""
    rec = _static_card("MustAttack", {"type": "SelfRef"})
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "force_attack" not in cats


def test_self_must_be_blocked_is_lure():
    """A lure creature lures blockers to ITSELF — SelfRef IS the enabler."""
    rec = _static_card("MustBeBlockedByAll", {"type": "SelfRef"})
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "lure" in cats


def _pt_static(affected, mods, *, cda=False):
    return {
        "name": "T",
        "scryfall_oracle_id": "pt",
        "card_type": {"core_types": ["Enchantment"]},
        "oracle_text": "",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": affected,
                "modifications": mods,
                "characteristic_defining": cda,
            }
        ],
    }


def _spell(effect: dict, description: str = ""):
    return {
        "name": "T",
        "scryfall_oracle_id": "pc",
        "card_type": {"core_types": ["Sorcery"]},
        "oracle_text": "",
        "abilities": [{"kind": "Spell", "effect": effect, "description": description}],
    }


def test_set_tap_state_projects_to_tap_or_untap():
    """SetTapState (the single biggest parse gap) → tap / untap by its `state`."""
    untap = _effects(
        project_card([_spell({"type": "SetTapState", "state": {"type": "Untap"}})])
    )
    assert any(e.category == "untap" for e in untap)
    tap = _effects(
        project_card([_spell({"type": "SetTapState", "state": {"type": "Tap"}})])
    )
    assert any(e.category == "tap" for e in tap)


def test_create_delayed_trigger_recurses_into_stored_effect():
    """A delayed trigger's stored effect is parsed, not left 'other'."""
    rec = _spell(
        {
            "type": "CreateDelayedTrigger",
            "condition": {"type": "AtNextPhase", "phase": "End"},
            "effect": {"kind": "Spell", "effect": {"type": "Draw"}},
        }
    )
    assert any(e.category == "draw" for e in _effects(project_card([rec])))


def test_zero_ability_card_synthesizes_from_oracle():
    """A total phase parse failure (no abilities, no keywords) is synthesized from its
    oracle so the supplement dispatch fills the gap — 'Draw a card.' -> draw."""
    rec = {
        "name": "Phase-Failure",
        "scryfall_oracle_id": "za",
        "card_type": {"core_types": ["Enchantment"]},
        "oracle_text": "Draw a card.",
    }
    card = project_card([rec])
    assert any(e.category == "draw" for a in card.all_abilities() for e in a.effects)


def test_vanilla_card_is_full():
    """A textless vanilla card has no rules text — its complete mechanics are its
    types + P/T, which the IR carries, so there is nothing left to parse: `full`
    (not synthesized into a bogus 'other', and not the legacy `unparsed` mislabel)."""
    rec = {
        "name": "Vanilla Bear",
        "scryfall_oracle_id": "v",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "",
    }
    assert project_card([rec]).parse_confidence == "full"


def test_keyword_only_card_not_synthesized():
    """A keyword-only card is full via the keyword field — not turned partial by a
    bogus synthesized 'other' clause."""
    rec = {
        "name": "Flyer",
        "scryfall_oracle_id": "kw",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Flying",
        "keywords": ["Flying"],
    }
    assert project_card([rec]).parse_confidence == "full"


def test_supplement_verb_dispatch_recovers_unimplemented():
    """The supplement's leading-verb dispatch flips a phase-Unimplemented clause from
    'other' to its real category (deal damage -> damage, conjure -> make_token)."""
    dmg = _effects(
        project_card(
            [_spell({"type": "Unimplemented"}, "Deal 3 damage to any target.")]
        )
    )
    assert any(e.category == "damage" for e in dmg)
    tok = _effects(
        project_card([_spell({"type": "Unimplemented"}, "Conjure a duplicate card.")])
    )
    assert any(e.category == "make_token" for e in tok)


def test_supplement_strips_prefixes_before_verb_dispatch():
    """The grammar peels leading trigger / activation-cost / player prefixes so the
    effect verb dispatches: 'When ~ enters, draw' -> draw; '{2}, {T}: Draw' -> draw;
    'Target player reveals ...' -> reveal."""
    for desc, cat in [
        ("When ~ enters, draw a card.", "draw"),
        ("{2}, {T}: Draw a card.", "draw"),
        ("Target player reveals their hand.", "reveal"),
        ("Chapter 1 — Create a 1/1 Soldier.", "make_token"),
        ("At the beginning of your upkeep, you may draw a card.", "draw"),
    ]:
        cats = {
            e.category
            for e in _effects(project_card([_spell({"type": "Unimplemented"}, desc)]))
        }
        assert cat in cats, f"{desc!r} -> {cat}, got {cats}"


def test_supplement_becomes_and_look_recovery():
    """'<subject> becomes a 4/4' -> animate; 'becomes a copy of' -> clone; 'Look at
    the top N' -> topdeck_select."""
    assert any(
        e.category == "animate"
        for e in _effects(
            project_card(
                [
                    _spell(
                        {"type": "Unimplemented"}, "Target land becomes a 4/4 creature."
                    )
                ]
            )
        )
    )
    assert any(
        e.category == "topdeck_select"
        for e in _effects(
            project_card(
                [_spell({"type": "Unimplemented"}, "Look at the top five cards.")]
            )
        )
    )


def test_supplement_static_dispatch_recovers_failed_line():
    """A line phase's static parser choked on (carried in the diagnostic prefix) is
    re-parsed: an anthem -> pump."""
    rec = _spell(
        {"type": "Unimplemented"},
        "Static pattern matched but line failed static parser: "
        "Equipped creature gets +2/+2.",
    )
    assert any(e.category == "pump" for e in _effects(project_card([rec])))


def test_supplement_dispatch_leaves_unmatched_as_other():
    """A clause with no recognizable leading verb / static shape stays 'other' (no
    false recovery)."""
    rec = _spell({"type": "Unimplemented"}, "Otherwise")
    assert all(e.category == "other" for e in _effects(project_card([rec])))


def test_tier2_effects_map_to_real_categories():
    """Tier-2 parse-completeness: adapt/bolster put +1/+1 counters; myriad/encore
    make tokens; madness casts from exile; WinTheGame is a win effect (key fix)."""
    cases = {
        "Adapt": "place_counter",
        "Bolster": "place_counter",
        "Myriad": "make_token",
        "Encore": "make_token",
        "MadnessCast": "cast_from_zone",
        "WinTheGame": "win_game",
    }
    for etype, cat in cases.items():
        cats = {e.category for e in _effects(project_card([_spell({"type": etype})]))}
        assert cat in cats, f"{etype} -> {cat}, got {cats}"


def test_attach_and_shuffle_are_no_longer_other():
    assert any(
        e.category == "attach"
        for e in _effects(project_card([_spell({"type": "Attach"})]))
    )
    assert any(
        e.category == "shuffle"
        for e in _effects(project_card([_spell({"type": "Shuffle"})]))
    )


def test_copied_type_from_text_reads_after_copy_of():
    assert _copied_type_from_text("~ becomes a copy of target creature").card_types == (
        "Creature",
    )
    assert _copied_type_from_text(
        "becomes a copy of any creature or planeswalker"
    ).card_types == ("Creature", "Planeswalker")
    # A typeless referent ("copy of that card") → None (falls back to the sibling).
    assert _copied_type_from_text("~ becomes a copy of that card") is None


def test_parent_target_clone_recovers_type_from_clause():
    """A BecomeCopy with target ParentTarget recovers the copied type from its own
    'copy of <type>' text (the ParentTarget completeness gap)."""
    rec = {
        "name": "Cytoshape-like",
        "scryfall_oracle_id": "pt",
        "card_type": {"core_types": ["Sorcery"]},
        "oracle_text": "",
        "abilities": [
            {
                "kind": "Spell",
                "effect": {"type": "BecomeCopy", "target": {"type": "ParentTarget"}},
                "description": "Target creature becomes a copy of target creature.",
            }
        ],
    }
    clone = [e for e in _effects(project_card([rec])) if e.category == "clone"]
    assert clone
    assert clone[0].subject is not None
    assert "Creature" in clone[0].subject.card_types


def test_parent_target_clone_recovers_type_from_sibling():
    """When the clone clause says 'copy of that card' (typeless), recover from the
    sibling effect's target (Dimir Doppelganger: exile target creature card)."""
    rec = {
        "name": "Dimir-like",
        "scryfall_oracle_id": "dd",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "ChangeZone",
                    "origin": "Graveyard",
                    "destination": "Exile",
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Creature"],
                        "controller": None,
                    },
                },
                "sub_ability": {
                    "effect": {
                        "type": "BecomeCopy",
                        "target": {"type": "ParentTarget"},
                    },
                    "description": "~ becomes a copy of that card.",
                },
                "description": "Exile target creature card from a graveyard.",
            }
        ],
    }
    clone = [e for e in _effects(project_card([rec])) if e.category == "clone"]
    assert clone
    assert clone[0].subject is not None
    assert "Creature" in clone[0].subject.card_types


def test_or_composite_filter_unions_member_types():
    """Spark Double copies a Creature OR a Planeswalker — _filter unions the Or
    members so the copy hierarchy sees both types."""
    f = _filter(
        {
            "type": "Or",
            "filters": [
                {"type": "Typed", "type_filters": ["Creature"], "controller": "You"},
                {
                    "type": "Typed",
                    "type_filters": ["Planeswalker"],
                    "controller": "You",
                },
            ],
        }
    )
    assert f is not None
    assert set(f.card_types) == {"Creature", "Planeswalker"}
    assert f.controller == "you"


def test_set_base_pt_on_others_is_base_pt_set():
    """Lignify: sets a target creature's base P/T (SetPower + SetToughness)."""
    rec = _pt_static(
        {"type": "Typed", "type_filters": ["Creature"], "controller": "Opponent"},
        [{"type": "SetPower"}, {"type": "SetToughness"}],
    )
    assert "base_pt_set" in {e.category for e in _effects(project_card([rec]))}


def test_self_defining_star_pt_is_not_base_pt_set():
    """Tarmogoyf-style */* (characteristic-defining, sets its OWN P/T) is not a
    base-P/T TOOLBOX."""
    rec = _pt_static(
        {"type": "SelfRef"},
        [{"type": "SetDynamicPower"}, {"type": "SetDynamicToughness"}],
        cda=True,
    )
    assert "base_pt_set" not in {e.category for e in _effects(project_card([rec]))}


def test_self_animate_manland_is_not_base_pt_set():
    """A manland animating ITSELF (SelfRef) sets the source's P/T, not a toolbox."""
    rec = _pt_static(
        {"type": "SelfRef"}, [{"type": "SetPower"}, {"type": "SetToughness"}]
    )
    assert "base_pt_set" not in {e.category for e in _effects(project_card([rec]))}


def test_ignore_landwalk_is_evasion_denial():
    """Great Wall: IgnoreLandwalkForBlocking → evasion_denial (block through walk)."""
    rec = _static_card({"IgnoreLandwalkForBlocking": {"qualifier": "Mountain"}}, None)
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "evasion_denial" in cats


def test_double_triggers_static_is_trigger_doubling():
    """Yarok / Panharmonicon: a DoubleTriggers static → trigger_doubling (Batch 17)."""
    rec = _static_card({"DoubleTriggers": {"cause": "Any"}}, None)
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "trigger_doubling" in cats


def test_deck_copy_limit_unlimited_sets_many_copies():
    """The CR 100.2a copy-limit exception (Relentless Rats / Hare Apparent) → the
    authoritative named-deck flag, read from the structured deck_copy_limit field."""
    rec = {
        "name": "Relentless Rats",
        "scryfall_oracle_id": "rr",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "A deck can have any number of cards named Relentless Rats.",
        "deck_copy_limit": {"type": "Unlimited"},
    }
    assert project_card([rec]).many_copies is True


def test_upto_two_is_many_copies_but_upto_one_is_not():
    """Seven Dwarves (UpTo 7) is a named-deck card; Vazal's Megalegendary (UpTo 1) is
    a RESTRICTION to one copy — the opposite — so it is not many_copies."""
    base = {
        "name": "X",
        "scryfall_oracle_id": "x",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "",
    }
    assert project_card(
        [{**base, "deck_copy_limit": {"type": "UpTo", "data": 7}}]
    ).many_copies
    assert not project_card(
        [{**base, "deck_copy_limit": {"type": "UpTo", "data": 1}}]
    ).many_copies
    assert not project_card([base]).many_copies  # no field → singleton/4-of


def test_many_copies_survives_roundtrip():
    rec = {
        "name": "R",
        "scryfall_oracle_id": "r",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "",
        "deck_copy_limit": {"type": "Unlimited"},
    }
    card = project_card([rec])
    assert Card.from_dict(card.to_dict()).many_copies is True


def test_cast_with_flash_is_a_flash_grant():
    """Teferi / Yeva: CastWithKeyword{Flash} → cast_with_keyword carrying 'flash'."""
    rec = _static_card(
        {"CastWithKeyword": {"keyword": "Flash"}},
        {"type": "Typed", "type_filters": ["Creature"], "controller": "You"},
    )
    flash = [
        e
        for e in _effects(project_card([rec]))
        if e.category == "cast_with_keyword" and e.counter_kind == "flash"
    ]
    assert flash


# ── go-wide count-over-own-board projection (ADR-0027) ────────────────────────
# These pin the count-operand-over-own-board helper + the mass grant/untap markers
# that close the creatures_matter go-wide gaps phase's structured projection dropped.


def _board_count_effect(card: Card) -> Effect:
    return _effect_with(card, "board_count")


def test_set_dynamic_pt_recovers_creature_board_count():
    """Crusader of Odric: a characteristic-defining SetDynamicPower over an
    ObjectCount(creatures you control) — phase keeps the operand but folds the
    effect to a subjectless P/T; the board_count marker recovers it."""
    rec = {
        "name": "Crusader of Odric",
        "scryfall_oracle_id": "id-crusader",
        "card_type": {"core_types": ["Creature"], "subtypes": ["Soldier"]},
        "oracle_text": (
            "~'s power and toughness are each equal to the number of "
            "creatures you control."
        ),
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {"type": "SelfRef"},
                "characteristic_defining": True,
                "modifications": [
                    {
                        "type": "SetDynamicPower",
                        "value": {
                            "type": "Ref",
                            "qty": {
                                "type": "ObjectCount",
                                "filter": {
                                    "type": "Typed",
                                    "type_filters": ["Creature"],
                                    "controller": "You",
                                    "properties": [],
                                },
                            },
                        },
                    }
                ],
            }
        ],
    }
    e = _board_count_effect(project_card([rec]))
    assert e.amount is not None
    assert e.amount.op == "count"
    assert e.amount.subject == Filter(card_types=("Creature",), controller="you")


def test_modifycost_reduce_aggregate_power_recovers_board_count():
    """Ghalta: ModifyCost{Reduce} whose dynamic_count is an Aggregate(Sum, Power)
    over creatures you control — a cost reduction by total power."""
    rec = {
        "name": "Ghalta, Primal Hunger",
        "scryfall_oracle_id": "id-ghalta",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "This spell costs {X} less to cast, where X is the total "
        "power of creatures you control.",
        "static_abilities": [
            {
                "mode": {
                    "ModifyCost": {
                        "mode": "Reduce",
                        "amount": {"type": "Cost", "shards": [], "generic": 1},
                        "dynamic_count": {
                            "type": "Aggregate",
                            "function": "Sum",
                            "property": "Power",
                            "filter": {
                                "type": "Typed",
                                "type_filters": ["Creature"],
                                "controller": "You",
                                "properties": [],
                            },
                        },
                    }
                },
                "affected": {"type": "SelfRef"},
                "modifications": [],
            }
        ],
    }
    e = _board_count_effect(project_card([rec]))
    assert e.amount.subject == Filter(card_types=("Creature",), controller="you")


def test_quantity_lifts_aggregate_sum_filter():
    """A Ref→Aggregate(Sum, Toughness) lifts its filter as a count operand (Orysa's
    total-toughness gate, Hobbit's Sting's Sum-of-counts amount)."""
    node = {
        "type": "Ref",
        "qty": {
            "type": "Aggregate",
            "function": "Sum",
            "property": "Toughness",
            "filter": {
                "type": "Typed",
                "type_filters": ["Creature"],
                "controller": "You",
                "properties": [],
            },
        },
    }
    from mtg_utils._card_ir.project import _quantity

    q = _quantity(node)
    assert q is not None
    assert q.op == "count"
    assert q.subject == Filter(card_types=("Creature",), controller="you")


def test_cantbeblockedby_your_creatures_is_mass_evasion_grant():
    """Champion of Lambholt: a CantBeBlockedBy static over your generic creature set
    → a grant_keyword (mass evasion) the go-wide arm reads."""
    rec = _static_card(
        {
            "CantBeBlockedBy": {
                "filter": {"type": "Typed", "type_filters": ["Creature"]}
            }
        },
        {"type": "Typed", "type_filters": ["Creature"], "controller": "You"},
    )
    grants = [
        e
        for e in _effects(project_card([rec]))
        if e.category == "grant_keyword" and e.counter_kind == "unblockable"
    ]
    assert grants
    assert grants[0].subject is not None
    assert "Creature" in grants[0].subject.card_types


def test_untap_all_scope_marks_counter_kind_all():
    """Aggravated Assault: SetTapState{Untap} with scope All over creatures you
    control → an untap effect tagged counter_kind='all' (a mass untap)."""
    rec = {
        "name": "Aggravated Assault",
        "scryfall_oracle_id": "id-aggro",
        "card_type": {"core_types": ["Enchantment"]},
        "oracle_text": "{3}{R}{R}: Untap all creatures you control.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "SetTapState",
                    "state": {"type": "Untap"},
                    "scope": {"type": "All"},
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Creature"],
                        "controller": "You",
                        "properties": [],
                    },
                },
                "cost": None,
            }
        ],
    }
    e = _effect_with(project_card([rec]), "untap")
    assert e.counter_kind == "all"
    assert e.subject == Filter(card_types=("Creature",), controller="you")


def test_single_target_untap_is_not_marked_all():
    """'Untap target creature' (scope Single) is NOT a mass untap."""
    rec = {
        "name": "Seeker",
        "scryfall_oracle_id": "id-seeker",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "{T}: Untap target creature.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "SetTapState",
                    "state": {"type": "Untap"},
                    "scope": {"type": "Single"},
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                },
                "cost": {"type": "Tap"},
            }
        ],
    }
    untaps = [e for e in _effects(project_card([rec])) if e.category == "untap"]
    assert untaps
    assert all(e.counter_kind != "all" for e in untaps)


def test_oracle_mass_grant_marker_recovers_chosen_ability_grant():
    """Linvala: "Creatures you control gain that ability" — phase folds it to a
    choose; the oracle mass-grant marker recovers a generic creature grant_keyword."""
    rec = {
        "name": "Linvala, Shield of Sea Gate",
        "scryfall_oracle_id": "id-linvala",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": (
            "Sacrifice ~: Choose hexproof or indestructible. Creatures you control "
            "gain that ability until end of turn."
        ),
    }
    grants = [
        e
        for e in _effects(project_card([rec]))
        if e.category == "grant_keyword" and e.counter_kind == "mass_grant"
    ]
    assert grants
    assert grants[0].subject == Filter(card_types=("Creature",), controller="you")


def test_oracle_mass_grant_marker_excludes_subtype_lord():
    """A SUBTYPE lord ("Goblin creatures you control get +1/+1") is type_matters, not
    a generic mass grant — the bare-head anchor must NOT match it."""
    rec = {
        "name": "Goblin King",
        "scryfall_oracle_id": "id-gobking",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Goblin creatures you control get +1/+1 and have mountainwalk.",
    }
    grants = [
        e
        for e in _effects(project_card([rec]))
        if e.category == "grant_keyword" and e.counter_kind == "mass_grant"
    ]
    assert not grants


def test_for_each_creature_oracle_marker_recovers_count():
    """A "for each creature you control" scaling phase Unrecognized-parsed → a
    board_count marker (Eidolon / Siege Behemoth)."""
    rec = {
        "name": "Eidolon of Countless Battles",
        "scryfall_oracle_id": "id-eidolon",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "This creature gets +1/+1 for each creature you control.",
    }
    e = _board_count_effect(project_card([rec]))
    assert e.amount.subject == Filter(card_types=("Creature",), controller="you")


# ── artifacts/enchantments go-wide projection (ADR-0027) ──────────────────────
# Cover the count-over-own-board operand for the two permanent-type lanes, the
# composite (Artifact OR Enchantment) `Or` filter, the affinity/improvise keyword
# operands, and the board_grant over a generic own-board artifact/enchantment set.


def test_board_count_recovers_artifact_count_operand():
    """One with the Machine: a Draw whose count is an Aggregate(Max, ManaValue) over
    artifacts you control — the board_count marker recovers the generic artifact set."""
    rec = {
        "name": "One with the Machine",
        "scryfall_oracle_id": "id-otm",
        "card_type": {"core_types": ["Sorcery"]},
        "oracle_text": "Draw cards equal to the greatest mana value among "
        "artifacts you control.",
        "abilities": [
            {
                "kind": "Spell",
                "effect": {
                    "type": "Draw",
                    "count": {
                        "type": "Ref",
                        "qty": {
                            "type": "Aggregate",
                            "function": "Max",
                            "property": "ManaValue",
                            "filter": {
                                "type": "Typed",
                                "type_filters": ["Artifact"],
                                "controller": "You",
                                "properties": [],
                            },
                        },
                    },
                    "target": {"type": "Controller"},
                },
            }
        ],
    }
    card = project_card([rec])
    subjects = {
        e.amount.subject
        for e in _effects(card)
        if e.amount is not None and e.amount.subject is not None
    }
    assert Filter(card_types=("Artifact",), controller="you") in subjects


def test_board_count_composite_or_fires_both_artifact_and_enchantment():
    """Shambling Suit: a SetDynamicPower over an Or(artifacts you control,
    enchantments you control) — the composite Or yields BOTH a board_count over
    Artifact and one over Enchantment (each population is summed)."""
    rec = {
        "name": "Shambling Suit",
        "scryfall_oracle_id": "id-shambling",
        "card_type": {"core_types": ["Artifact", "Creature"]},
        "oracle_text": "~'s power is equal to the number of artifacts and/or "
        "enchantments you control.",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {"type": "SelfRef"},
                "characteristic_defining": True,
                "modifications": [
                    {
                        "type": "SetDynamicPower",
                        "value": {
                            "type": "Ref",
                            "qty": {
                                "type": "ObjectCount",
                                "filter": {
                                    "type": "Or",
                                    "filters": [
                                        {
                                            "type": "Typed",
                                            "type_filters": ["Artifact"],
                                            "controller": "You",
                                            "properties": [],
                                        },
                                        {
                                            "type": "Typed",
                                            "type_filters": ["Enchantment"],
                                            "controller": "You",
                                            "properties": [],
                                        },
                                    ],
                                },
                            },
                        },
                    }
                ],
            }
        ],
    }
    subjects = {
        e.amount.subject
        for e in _effects(project_card([rec]))
        if e.category == "board_count" and e.amount is not None
    }
    assert Filter(card_types=("Artifact",), controller="you") in subjects
    assert Filter(card_types=("Enchantment",), controller="you") in subjects


def test_affinity_keyword_recovers_typed_count_operand():
    """Affinity for enchantments (CR 702.41a) — the projection drops the subject to a
    bare keyword; the marker recovers the Enchantment board count (NOT Artifact)."""
    rec = {
        "name": "Brine Giant",
        "scryfall_oracle_id": "id-brine",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Affinity for enchantments",
        "keywords": [
            {"Affinity": {"type_filters": ["Enchantment"], "controller": None}}
        ],
    }
    subjects = {
        e.amount.subject
        for e in _effects(project_card([rec]))
        if e.category == "board_count" and e.amount is not None
    }
    assert Filter(card_types=("Enchantment",), controller="you") in subjects
    assert Filter(card_types=("Artifact",), controller="you") not in subjects


def test_improvise_keyword_recovers_artifact_count_operand():
    """Improvise (CR 702.126a) is always an artifact-tap count operand."""
    rec = {
        "name": "Whir of Invention",
        "scryfall_oracle_id": "id-whir",
        "card_type": {"core_types": ["Instant"]},
        "oracle_text": "Improvise",
        "keywords": ["Improvise"],
    }
    subjects = {
        e.amount.subject
        for e in _effects(project_card([rec]))
        if e.category == "board_count" and e.amount is not None
    }
    assert Filter(card_types=("Artifact",), controller="you") in subjects


def test_affinity_for_nonpermanent_type_emits_no_marker():
    """Affinity for snow lands / gates / a tribe is NOT an artifact/enchantment care —
    the marker emits nothing (the over-fire boundary on the bare Affinity keyword)."""
    rec = {
        "name": "Icebreaker Kraken",
        "scryfall_oracle_id": "id-kraken",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Affinity for snow lands",
        "keywords": [
            {
                "Affinity": {
                    "type_filters": ["Land", {"Supertype": "Snow"}],
                    "controller": None,
                }
            }
        ],
    }
    assert not [e for e in _effects(project_card([rec])) if e.category == "board_count"]


def test_board_grant_over_artifact_set_from_grant_ability():
    """Ragost: a continuous static GrantAbility + AddSubtype over "artifacts you
    control" → a board_grant over the generic artifact set (the grant ranges over the
    whole population)."""
    rec = {
        "name": "Ragost, Deft Gastronaut",
        "scryfall_oracle_id": "id-ragost",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Artifacts you control are Foods and have an ability.",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {
                    "type": "Typed",
                    "type_filters": ["Artifact"],
                    "controller": "You",
                    "properties": [],
                },
                "modifications": [
                    {"type": "AddSubtype", "subtype": "Food"},
                    {"type": "GrantAbility", "definition": {"kind": "Activated"}},
                ],
            }
        ],
    }
    e = _effect_with(project_card([rec]), "board_grant")
    assert e.subject == Filter(card_types=("Artifact",), controller="you")


def test_parameterized_keyword_grant_over_artifact_set_is_board_grant():
    """Elder Owyn Lyons: "Artifacts you control have ward {1}" — the parameterized
    keyword (a dict, not a bare string) surfaces as a board_grant over the artifact
    set, NOT a generic grant_keyword (which would move the creature keyword lanes)."""
    rec = {
        "name": "Elder Owyn Lyons",
        "scryfall_oracle_id": "id-owyn",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "Artifacts you control have ward {1}.",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {
                    "type": "Typed",
                    "type_filters": ["Artifact"],
                    "controller": "You",
                    "properties": [],
                },
                "modifications": [
                    {"type": "AddKeyword", "keyword": {"Ward": {"type": "Mana"}}}
                ],
            }
        ],
    }
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "board_grant" in cats
    assert "grant_keyword" not in cats


# ── quoted-grant-ability recursion (ADR-0027) ─────────────────────────────────


def _grant_ability_static(affected, definition):
    return {
        "mode": "Continuous",
        "affected": affected,
        "modifications": [{"type": "GrantAbility", "definition": definition}],
    }


def test_quoted_grant_destroy_recovers_inner_destroy_effect():
    """Manriki-Gusari: 'Equipped creature ... has "{T}: Destroy target Equipment."'.
    phase keeps the grant opaque (a GrantAbility modification); the recursion descends
    into the granted definition and recovers the inner destroy Effect (subject
    Equipment), so removal/artifact lanes can read it."""
    rec = {
        "name": "Manriki-Gusari",
        "scryfall_oracle_id": "id-manriki",
        "card_type": {"core_types": ["Artifact"], "subtypes": ["Equipment"]},
        "oracle_text": (
            'Equipped creature gets +1/+2 and has "{T}: Destroy target Equipment."'
        ),
        "static_abilities": [
            _grant_ability_static(
                {
                    "type": "Typed",
                    "type_filters": ["Creature"],
                    "controller": None,
                    "properties": [{"type": "EquippedBy"}],
                },
                {
                    "kind": "Activated",
                    "cost": {"type": "Tap"},
                    "effect": {
                        "type": "Destroy",
                        "target": {
                            "type": "Typed",
                            "type_filters": [{"Subtype": "Equipment"}],
                        },
                    },
                    "description": "{T}: Destroy target Equipment.",
                },
            )
        ],
    }
    e = _effect_with(project_card([rec]), "destroy")
    assert e.subject == Filter(subtypes=("Equipment",))


def test_quoted_grant_damage_recovers_inner_damage_effect():
    """Lavamancer's Skill: an Aura whose enchanted creature 'has "{T}: ~ deals 1
    damage to target creature."' — the recursion recovers the damage Effect with its
    creature target subject (removal_matters' source)."""
    rec = {
        "name": "Lavamancer's Skill",
        "scryfall_oracle_id": "id-lavamancer",
        "card_type": {"core_types": ["Enchantment"], "subtypes": ["Aura"]},
        "oracle_text": (
            'Enchanted creature has "{T}: This creature deals 1 damage to target '
            'creature."'
        ),
        "static_abilities": [
            _grant_ability_static(
                {
                    "type": "Typed",
                    "type_filters": ["Creature"],
                    "controller": None,
                    "properties": [{"type": "EnchantedBy"}],
                },
                {
                    "kind": "Activated",
                    "cost": {"type": "Tap"},
                    "effect": {
                        "type": "DealDamage",
                        "amount": {"type": "Fixed", "value": 1},
                        "target": {
                            "type": "Typed",
                            "type_filters": ["Creature"],
                        },
                    },
                    "description": "{T}: ~ deals 1 damage to target creature.",
                },
            )
        ],
    }
    e = _effect_with(project_card([rec]), "damage")
    assert "Creature" in e.subject.card_types


def test_quoted_grant_trigger_recovers_inner_put_counter():
    """Mephidross Vampire: 'Each creature you control ... has "Whenever ~ deals damage
    to a creature, put a +1/+1 counter on ~."' — a GrantTrigger modification; the
    recursion descends into the trigger's execute and recovers the place_counter
    (counter_kind p1p1)."""
    rec = {
        "name": "Mephidross Vampire",
        "scryfall_oracle_id": "id-mephidross",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": (
            'Each creature you control ... has "Whenever this creature deals damage '
            'to a creature, put a +1/+1 counter on this creature."'
        ),
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {
                    "type": "Typed",
                    "type_filters": ["Creature"],
                    "controller": "You",
                    "properties": [],
                },
                "modifications": [
                    {
                        "type": "GrantTrigger",
                        "trigger": {
                            "mode": "DamageDone",
                            "execute": {
                                "kind": "Spell",
                                "effect": {
                                    "type": "PutCounter",
                                    "counter_type": "P1P1",
                                    "count": {"type": "Fixed", "value": 1},
                                    "target": {"type": "SelfRef"},
                                },
                            },
                            "description": (
                                "Whenever ~ deals damage to a creature, put a "
                                "+1/+1 counter on ~."
                            ),
                        },
                    }
                ],
            }
        ],
    }
    e = _effect_with(project_card([rec]), "place_counter")
    assert e.counter_kind == "p1p1"


def test_quoted_grant_to_opponent_permanents_is_excluded():
    """SCOPE GATE (rules-lawyer): a quoted ability GRANTED to permanents an OPPONENT
    controls is THEIR ability, not yours — the recursion must NOT recover its inner
    removal/counters effect (it is not a care of yours)."""
    rec = {
        "name": "Curse Grant",
        "scryfall_oracle_id": "id-cursegrant",
        "card_type": {"core_types": ["Enchantment"]},
        "oracle_text": (
            'Creatures your opponents control have "{T}: Destroy target creature."'
        ),
        "static_abilities": [
            _grant_ability_static(
                {
                    "type": "Typed",
                    "type_filters": ["Creature"],
                    "controller": "Opponent",
                    "properties": [],
                },
                {
                    "kind": "Activated",
                    "cost": {"type": "Tap"},
                    "effect": {
                        "type": "Destroy",
                        "target": {
                            "type": "Typed",
                            "type_filters": ["Creature"],
                        },
                    },
                    "description": "{T}: Destroy target creature.",
                },
            )
        ],
    }
    cats = {e.category for e in _effects(project_card([rec]))}
    assert "destroy" not in cats


def test_damage_all_carries_mass_counter_kind_tell():
    """DamageAll ("deals N damage to each creature" — Breath Weapon) carries the
    counter_kind='all' mass tell so the single-target removal_matters arm (CR 115.1)
    can exclude the board-wipe form (CR 115.10)."""
    rec = {
        "name": "Breath Weapon",
        "scryfall_oracle_id": "id-breath",
        "card_type": {"core_types": ["Sorcery"]},
        "oracle_text": "Breath Weapon deals 2 damage to each non-Dragon creature.",
        "abilities": [
            {
                "kind": "Spell",
                "effect": {
                    "type": "DamageAll",
                    "amount": {"type": "Fixed", "value": 2},
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                },
            }
        ],
    }
    e = _effect_with(project_card([rec]), "damage")
    assert e.counter_kind == "all"


def test_destroy_all_carries_mass_counter_kind_tell():
    """DestroyAll ("destroy all creatures" — a board wipe) carries the
    counter_kind='all' mass tell so removal_matters excludes it (it is a board_wipe
    axis, not single-target removal)."""
    rec = {
        "name": "Day of Judgment",
        "scryfall_oracle_id": "id-doj",
        "card_type": {"core_types": ["Sorcery"]},
        "oracle_text": "Destroy all creatures.",
        "abilities": [
            {
                "kind": "Spell",
                "effect": {
                    "type": "DestroyAll",
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                },
            }
        ],
    }
    e = _effect_with(project_card([rec]), "destroy")
    assert e.counter_kind == "all"


def test_post_supplement_recovers_removal_target_subject():
    """Combo Attack: "deal damage … to target creature" is an Unimplemented effect
    phase leaves as `other`; the supplement re-derives the `damage` category, and the
    POST-supplement removal-target-subject pass rebuilds the single-target Creature
    subject so removal_matters can read it (the pre-supplement pass ran before the
    category existed)."""
    rec = {
        "name": "Combo Attack",
        "scryfall_oracle_id": "id-combo",
        "card_type": {"core_types": ["Instant"]},
        "oracle_text": (
            "Two target creatures your team controls each deal damage equal to "
            "their power to target creature."
        ),
        "abilities": [
            {
                "kind": "Spell",
                "effect": {
                    "type": "Unimplemented",
                    "description": (
                        "Two target creatures your team controls each deal damage "
                        "equal to their power to target creature."
                    ),
                },
            }
        ],
    }
    e = _effect_with(project_card([rec]), "damage")
    assert e.subject is not None
    assert "Creature" in e.subject.card_types


# ── mass zone-move tell (ADR-0027 type-payoff recursion) ──────────────────────


def test_changezoneall_graveyard_recursion_marks_mass():
    """Crystal Chimes: "Return ALL enchantment cards from your graveyard" is a
    ChangeZoneAll — counter_kind='all' marks the non-targeted go-wide form (CR 115.10)
    so the recursion payoff lane fires; the marker survives the supplement's
    category rewrite (ChangeZoneAll graveyard→hand re-parses to 'bounce')."""
    rec = {
        "name": "Crystal Chimes",
        "scryfall_oracle_id": "id-chimes",
        "card_type": {"core_types": ["Artifact"]},
        "oracle_text": "Return all enchantment cards from your graveyard to your hand.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "ChangeZoneAll",
                    "origin": "Graveyard",
                    "destination": "Hand",
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Enchantment"],
                        "controller": "You",
                        "properties": [{"type": "InZone", "zone": "Graveyard"}],
                    },
                },
                "description": "Return all enchantment cards from your graveyard "
                "to your hand.",
            }
        ],
    }
    eff = next(e for e in _effects(project_card([rec])) if e.category == "bounce")
    assert eff.counter_kind == "all"


def test_single_target_bounce_has_no_mass_tell():
    """Skull of Orm: "Return TARGET enchantment card" is a single-target Bounce
    (CR 115.1) — no mass tell, so the recursion payoff lane stays out."""
    rec = {
        "name": "Skull of Orm",
        "scryfall_oracle_id": "id-skull",
        "card_type": {"core_types": ["Artifact"]},
        "oracle_text": "Return target enchantment card from your graveyard to your "
        "hand.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "Bounce",
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Enchantment"],
                        "controller": "You",
                        "properties": [{"type": "InZone", "zone": "Graveyard"}],
                    },
                    "destination": None,
                },
            }
        ],
    }
    eff = next(e for e in _effects(project_card([rec])) if e.category == "bounce")
    assert eff.counter_kind == ""


# ── round-trip ────────────────────────────────────────────────────────────────


def test_roundtrip_lossless():
    for rec in (CRATERHOOF, SHAMANIC, TINYBONES):
        card = project_card([rec])
        assert Card.from_dict(card.to_dict()) == card


def test_empty_record_is_full():
    """An empty/textless record has no abilities to parse → `full` (nothing to
    parse), not the legacy `unparsed` mislabel."""
    card = project_card(
        [{"name": "Vanilla Bear", "scryfall_oracle_id": "x", "card_type": {}}]
    )
    assert card.parse_confidence == "full"
    assert card.all_abilities() == ()


def test_unresolved_effect_marks_partial():
    """A GenericEffect we can't structure (Tinybones' cast clause) → partial."""
    card = project_card([TINYBONES])
    assert card.parse_confidence in {"partial", "full"}


def test_bare_trigger_recovered_from_oracle():
    """phase kept the trigger CONDITION ("When ~ enters") but lost the effect — the
    effect survives in the oracle ("When this creature enters, draw a card."), so the
    bare-marker raw is spliced with the matching sentence and the supplement
    dispatches the verb. "this creature" folds to ~ just like the card name."""
    rec = {
        "name": "Test Trigger",
        "scryfall_oracle_id": "bt",
        "card_type": {"core_types": ["Creature"]},
        "oracle_text": "When this creature enters, draw a card.",
        "triggers": [
            {
                "execute": {
                    "effect": {"type": "GenericEffect", "static_abilities": []}
                },
                "description": "When ~ enters",
            }
        ],
    }
    card = project_card([rec])
    cats = [e.category for a in card.all_abilities() for e in a.effects]
    assert "draw" in cats
    assert "other" not in cats
    assert card.parse_confidence == "full"


def test_imports_dont_drag_in_phase_binary():
    """project_card must work from a record alone — no phase install needed."""
    assert isinstance(project_card([SHAMANIC]), Card)
    assert all(isinstance(a, Ability) for a in project_card([SHAMANIC]).all_abilities())


# ── build + load (hermetic: a temp card-data.json, no external deps) ───────────


def test_build_and_load_sidecar(tmp_path):
    """End-to-end: project a card-data.json into a sidecar and load it back,
    keyed by oracle_id, with the scaling operand surviving serialization."""
    import json

    from mtg_utils._card_ir.build import build_sidecar
    from mtg_utils._card_ir.load import clear_memory_cache, load_card_ir

    # phase keys card-data.json by lowercased face name.
    card_data = {r["name"].lower(): r for r in (CRATERHOOF, SHAMANIC, TINYBONES)}
    cdp = tmp_path / "card-data.json"
    cdp.write_text(json.dumps(card_data))
    out = tmp_path / "card-ir.json"

    written, stats = build_sidecar(card_data_path=cdp, out_path=out)
    assert written == out
    assert stats["cards"] == 3

    clear_memory_cache()
    ir = load_card_ir(out)
    assert set(ir) == {
        r["scryfall_oracle_id"] for r in (CRATERHOOF, SHAMANIC, TINYBONES)
    }

    crater = ir["8c52bd39-0586-48ca-b263-17210cf9feb6"]
    pump = next(e for e in _effects(crater) if e.category == "pump")
    assert pump.amount == Quantity(
        op="count", factor=1, subject=Filter(card_types=("Creature",), controller="you")
    )


def test_dfc_faces_grouped_by_oracle_id(tmp_path):
    """Two phase face-records sharing an oracle_id become one two-face Card."""
    import json

    from mtg_utils._card_ir.build import build_sidecar
    from mtg_utils._card_ir.load import clear_memory_cache, load_card_ir

    front = {
        "name": "Front",
        "scryfall_oracle_id": "dfc-1",
        "card_type": {},
        "keywords": ["Flying"],
    }
    back = {
        "name": "Back",
        "scryfall_oracle_id": "dfc-1",
        "card_type": {},
        "keywords": ["Haste"],
    }
    cdp = tmp_path / "cd.json"
    cdp.write_text(json.dumps({"front": front, "back": back}))
    out = tmp_path / "ir.json"
    build_sidecar(card_data_path=cdp, out_path=out)

    clear_memory_cache()
    card = load_card_ir(out)["dfc-1"]
    assert [f.name for f in card.faces] == ["Front", "Back"]
    assert card.keywords == ("Flying", "Haste")


# ── token-subtype maker recovery (ADR-0027) ───────────────────────────────────
def _maker_subtypes(ability: Ability) -> set[str]:
    return {
        st
        for e in ability.effects
        if e.category == "make_token" and isinstance(e.subject, Filter)
        for st in e.subject.subtypes
    }


def test_token_subtype_maker_recovery_from_choice_list():
    """A `choose` carrier whose raw lists named token subtypes (Transmutation Font's
    "create your choice of a Blood token, a Clue token, or a Food token") recovers a
    make_token marker per subtype, so each token-subtype lane can read it."""
    ability = Ability(
        kind="activated",
        cost="tap",
        effects=(
            Effect(
                category="choose",
                scope="any",
                raw="{T}: Create your choice of a Blood token, a Clue token, "
                "or a Food token.",
            ),
        ),
    )
    out = _narrow_token_subtype_makers(ability)
    assert _maker_subtypes(out) == {"Blood", "Clue", "Food"}


def test_token_subtype_maker_recovery_from_granted_ability():
    """A grant carrier (pump) whose raw folds a quoted "create a Blood token" ability
    (Ceremonial Knife) recovers the Blood make_token marker."""
    ability = Ability(
        kind="static",
        effects=(
            Effect(
                category="pump",
                scope="any",
                subject=Filter(card_types=("Creature",), predicates=("EquippedBy",)),
                raw='Equipped creature gets +1/+0 and has "Whenever ~ deals combat '
                'damage, create a Blood token."',
            ),
        ),
    )
    out = _narrow_token_subtype_makers(ability)
    assert _maker_subtypes(out) == {"Blood"}


def test_token_subtype_maker_recovery_ignores_non_carrier_and_bare_mention():
    """Append-only + carrier-gated: a non-carrier effect (e.g. a draw) whose raw
    happens to mention a token subtype recovers nothing; a real make_token carrier is
    left untouched (its own subject already carries the subtype)."""
    ability = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="draw",
                scope="you",
                raw="Whenever you draw a card, you may discard a Blood token.",
            ),
        ),
    )
    out = _narrow_token_subtype_makers(ability)
    assert out is ability  # nothing appended (draw is not a carrier)


# ── ADR-0027 tail-supplement markers (boast / connive-grant / scavenge / scry-
# replacement / extra-end / madness / mutate / foretell / phasing / exhaust /
# trigger-doubling / experience) ──────────────────────────────────────────────
def _cats(ability: Ability) -> set[str]:
    return {e.category for e in ability.effects}


def test_payoff_condition_refs_madness_mutate_foretell():
    """ "if it has madness" (Anje's untap loop), "if it has mutate" (Pollywog's draw
    payoff), and "to foretell" (Karfell's mana restriction) each append a precise
    payoff marker — even on a non-grant carrier (untap/draw/ramp)."""
    madness = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="untap",
                scope="you",
                raw="Whenever you discard a card, if it has madness, untap ~.",
            ),
        ),
    )
    assert "madness" in _cats(_narrow_payoff_condition_refs(madness))
    mutate = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="draw",
                scope="you",
                raw="Whenever you cast a creature spell, if it has mutate, draw "
                "a card, then discard a card.",
            ),
        ),
    )
    assert "mutate" in _cats(_narrow_payoff_condition_refs(mutate))
    foretell = Ability(
        kind="activated",
        cost="tap",
        effects=(
            Effect(
                category="ramp",
                scope="any",
                raw="{T}: Add {U}. Spend this mana only to foretell a card from "
                "your hand or cast an instant or sorcery spell.",
            ),
        ),
    )
    assert "foretell" in _cats(_narrow_payoff_condition_refs(foretell))


def test_payoff_condition_refs_no_bare_keyword_fire():
    """Anchored on the gating clause, not a bare keyword: a card that merely USES
    madness/mutate/foretell (its own keyword) without the "if it has …" / "to …"
    condition appends nothing."""
    ability = Ability(
        kind="static",
        effects=(
            Effect(
                category="grant_keyword",
                scope="you",
                raw="Madness {1}{R}. You may cast this card for its madness cost.",
            ),
        ),
    )
    assert _narrow_payoff_condition_refs(ability) is ability


def test_dropped_static_markers_boast_scavenge_scry_extra_end():
    """Statics phase drops entirely (surviving only on the face oracle) recover a
    marker: Birgi's boast amplifier, Varolz's graveyard-wide scavenge grant,
    Kenessos's scry replacement, Y'shtola's additional end step."""
    birgi = {
        "oracle_text": "Creatures you control can boast twice during each of your "
        "turns rather than once."
    }
    assert {"boast"} == {e.category for e in _dropped_static_markers(birgi, [])}
    varolz = {
        "oracle_text": "Each creature card in your graveyard has scavenge. The "
        "scavenge cost is equal to its mana cost."
    }
    assert {"scavenge"} == {e.category for e in _dropped_static_markers(varolz, [])}
    kenessos = {
        "oracle_text": "If you would scry a number of cards, scry that many cards "
        "plus one instead."
    }
    cats = {e.category for e in _dropped_static_markers(kenessos, [])}
    assert "scry_surveil" in cats
    yshtola = {
        "oracle_text": "Then if it's the first end step of the turn, there is an "
        "additional end step after this step."
    }
    cats = {e.category for e in _dropped_static_markers(yshtola, [])}
    assert "extra_end" in cats


def test_dropped_static_trigger_doubling_gated_to_no_structural():
    """The Masamune's granted "triggers an additional time" recovers a marker only
    when no structural trigger_doubling effect exists; a card that already carries
    the structural category (Panharmonicon-class) recovers nothing (no double-tag)."""
    masamune = {
        "oracle_text": 'Equipped creature has "If a creature dying causes a '
        "triggered ability of this creature or an emblem you own to trigger, that "
        'ability triggers an additional time."'
    }
    cats = {e.category for e in _dropped_static_markers(masamune, [])}
    assert "trigger_doubling" in cats
    structural = [
        Ability(kind="static", effects=(Effect(category="trigger_doubling"),))
    ]
    assert not _dropped_static_markers(masamune, structural)


def test_replacement_triple_damage_is_damage_doubling():
    """A DamageDone replacement with damage_modification Triple (Fiery Emancipation,
    City on Fire) projects to damage_doubling — the multiplier set covers triple,
    not just double, so the triplers stop falling through to a synthesized generic
    `damage` effect (which over-fired direct_damage)."""
    rep = {
        "event": "DamageDone",
        "description": "it deals triple that damage instead",
        "damage_modification": {"type": "Triple"},
    }
    ab = _project_replacement(rep)
    assert ab is not None
    assert [e.category for e in ab.effects] == ["damage_doubling"]


def test_add_target_replacement_nested_doubling_recovered():
    """An AddTargetReplacement installing a DamageDone replacement (Goblin Goliath,
    Isengard Unleashed) carries the amplifier as a NESTED damage_modification the
    generic redirect category drops — recover it as damage_doubling."""
    eff = {
        "type": "AddTargetReplacement",
        "replacement": {
            "event": "DamageDone",
            "damage_modification": {"type": "Double"},
            "description": "it deals double that damage instead",
        },
    }
    out = _project_effect(eff, "deal double")
    assert [e.category for e in out] == ["damage_doubling"]


def test_create_damage_replacement_doubling_recovered():
    """A CreateDamageReplacement with modification Double (Desperate Gambit's
    coin-flip one-shot) recovers a damage_doubling effect; a None/Prevent
    modification (a redirect/prevention) does not."""
    doubler = {
        "type": "CreateDamageReplacement",
        "modification": {"type": "Double"},
    }
    assert [e.category for e in _project_effect(doubler, "x")] == ["damage_doubling"]
    redirect = {"type": "CreateDamageReplacement", "modification": {"type": "Prevent"}}
    assert all(e.category != "damage_doubling" for e in _project_effect(redirect, "x"))


def test_dropped_static_damage_doubling_marker_gated():
    """A card whose doubler phase dropped the modification from (Neriv's "deals twice
    that much damage") recovers a damage_doubling marker, gated to faces with no
    structural one; "prevent half that damage" (Dark Sphere, a halver) recovers
    nothing."""
    neriv = {
        "oracle_text": "If a creature you control that entered this turn would deal "
        "damage, it deals twice that much damage instead."
    }
    assert "damage_doubling" in {e.category for e in _dropped_static_markers(neriv, [])}
    structural = [Ability(kind="static", effects=(Effect(category="damage_doubling"),))]
    assert not _dropped_static_markers(neriv, structural)
    halver = {
        "oracle_text": "prevent half that damage, rounded down.",
    }
    assert all(
        e.category != "damage_doubling" for e in _dropped_static_markers(halver, [])
    )


def test_dropped_static_force_attack_self_static_marker():
    """A self/team "attacks each combat if able" static phase drops entirely (Dauthi
    Slayer — no abilities) recovers a force_attack marker, gated to faces with no
    structural force_attack; the goad-reward redirect never matches it."""
    dauthi = {
        "oracle_text": "Shadow\nThis creature attacks each combat if able.",
    }
    cats = {e.category for e in _dropped_static_markers(dauthi, [])}
    assert "force_attack" in cats
    assert "goad_all" not in cats
    structural = [Ability(kind="static", effects=(Effect(category="force_attack"),))]
    assert all(
        e.category != "force_attack"
        for e in _dropped_static_markers(dauthi, structural)
    )


def test_dropped_static_goad_reward_marker():
    """A goad-REWARD payoff phase flattens to raw (Gahiji's "attacks one of your
    opponents", Kazuul's defending-player) recovers a goad_all marker (read into
    goad_matters); a self-force "each combat" never matches the reward pattern."""
    gahiji = {
        "oracle_text": "Whenever a creature attacks one of your opponents, that "
        "creature gets +2/+0 until end of turn.",
    }
    assert "goad_all" in {e.category for e in _dropped_static_markers(gahiji, [])}
    kazuul = {
        "oracle_text": "Whenever a creature an opponent controls attacks, if you're "
        "the defending player, create a 3/3 red Ogre creature token.",
    }
    assert "goad_all" in {e.category for e in _dropped_static_markers(kazuul, [])}
    self_force = {"oracle_text": "~ attacks each combat if able."}
    assert "goad_all" not in {
        e.category for e in _dropped_static_markers(self_force, [])
    }


def test_dropped_static_scavenge_not_ability_word():
    """Anchored on "has scavenge" (the grant), so Malanthrope's "Scavenge the Dead"
    ability WORD (CR 207.2c — no rules meaning) recovers nothing."""
    malanthrope = {
        "oracle_text": "Scavenge the Dead — When this creature enters, exile target "
        "player's graveyard. Put a +1/+1 counter on this creature for each creature "
        "card exiled this way."
    }
    assert not _dropped_static_markers(malanthrope, [])


def test_trigger_other_phasing_payoff_marker():
    """An event='other' trigger whose place_counter consequence keeps "permanents
    phase out" only in its raw (The War Doctor) appends a phasing payoff marker."""
    ability = Ability(
        kind="triggered",
        trigger=Trigger(event="other"),
        effects=(
            Effect(
                category="place_counter",
                scope="you",
                counter_kind="time",
                raw="Whenever one or more other permanents phase out, put a time "
                "counter on ~.",
            ),
        ),
    )
    assert "phasing" in _cats(_narrow_trigger_other_refs(ability))


def test_trigger_other_exhaust_fires_on_delayed_activated_trigger():
    """Pit Automaton's exhaust payoff is a delayed trigger inside an ACTIVATED
    ability (no event='other' trigger), so the exhaust marker must fire regardless
    of trigger kind."""
    ability = Ability(
        kind="activated",
        cost="mana,tap",
        effects=(
            Effect(
                category="state",
                scope="any",
                raw="{2}, {T}: When you next activate an exhaust ability that "
                "isn't a mana ability this turn, copy it.",
            ),
        ),
    )
    assert "exhaust" in _cats(_narrow_trigger_other_refs(ability))


def test_quantity_experience_counter_operand():
    """ "for each experience counter you have" (Ref → PlayerCounter{Experience})
    stamps op="experience" — the discriminator the experience_matters scaler lane
    reads, not a bare op="count"."""
    node = {"type": "Ref", "qty": {"type": "PlayerCounter", "kind": "Experience"}}
    q = _quantity(node)
    assert q is not None
    assert q.op == "experience"
    # a generic count operand stays op="count" (no false experience tag)
    generic = {"type": "ObjectCount", "filter": {"type": "Typed", "type_filters": []}}
    assert _quantity(generic).op == "count"


# ── graveyard_matters shapes (ADR-0027) ───────────────────────────────────────


def test_has_graveyard_count_recognizes_zoned_count_operands():
    """GraveyardSize, a graveyard-zoned ZoneCardCount/ZoneCardCountAtLeast, and a
    bare Zone(Graveyard) source (under a DistinctCardTypes count) are graveyard count
    operands; a hand-zoned count or a battlefield count is not."""
    assert _has_graveyard_count({"type": "GraveyardSize", "player": "Controller"})
    assert _has_graveyard_count(
        {"type": "ZoneCardCount", "zone": "Graveyard", "card_types": ["Instant"]}
    )
    assert _has_graveyard_count(
        {"type": "ZoneCardCountAtLeast", "zone": "Graveyard", "count": 7}
    )
    assert _has_graveyard_count(
        {"type": "DistinctCardTypes", "source": {"type": "Zone", "zone": "Graveyard"}}
    )
    assert not _has_graveyard_count(
        {"type": "ZoneCardCount", "zone": "Hand", "card_types": []}
    )
    assert not _has_graveyard_count({"type": "ObjectCount", "filter": {}})


def test_graveyard_count_marker_from_dynamic_power():
    """Enigma Drake's "power equal to … cards in your graveyard"
    (SetDynamicPower → Ref → ZoneCardCount(Graveyard)) recovers one in:graveyard
    count marker, so the zone-aware graveyard_matters hook (scope you) fires."""
    rec = {
        "name": "Enigma Drake",
        "oracle_text": "Flying\nEnigma Drake's power is equal to the number of "
        "instant and sorcery cards in your graveyard.",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {"type": "SelfRef"},
                "modifications": [
                    {
                        "type": "SetDynamicPower",
                        "value": {
                            "type": "Ref",
                            "qty": {
                                "type": "ZoneCardCount",
                                "zone": "Graveyard",
                                "card_types": ["Instant", "Sorcery"],
                                "scope": "Controller",
                            },
                        },
                    }
                ],
                "characteristic_defining": True,
            }
        ],
    }
    markers = _graveyard_count_markers(rec, [])
    assert len(markers) == 1
    assert markers[0].category == "board_count"
    assert markers[0].zones == ("in:graveyard",)
    # gated to faces with no structural in:graveyard count (no double-tag)
    structural = [
        Ability(
            kind="static",
            effects=(Effect(category="draw", zones=("in:graveyard",)),),
        )
    ]
    assert not _graveyard_count_markers(rec, structural)


def test_graveyard_count_marker_from_cost_reduction():
    """Pteramander's "{1} less … for each instant and sorcery card in your graveyard"
    keeps the operand in abilities[].cost_reduction.count — recovered as a marker."""
    rec = {
        "name": "Pteramander",
        "oracle_text": "{7}{U}: Adapt 4. This ability costs {1} less to activate for "
        "each instant and sorcery card in your graveyard.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {"type": "Adapt", "count": {"type": "Fixed", "value": 4}},
                "cost_reduction": {
                    "amount_per": 1,
                    "count": {
                        "type": "Ref",
                        "qty": {
                            "type": "ZoneCardCount",
                            "zone": "Graveyard",
                            "card_types": ["Instant", "Sorcery"],
                            "scope": "Controller",
                        },
                    },
                },
            }
        ],
    }
    markers = _graveyard_count_markers(rec, [])
    assert {"board_count"} == {m.category for m in markers}
    assert markers[0].zones == ("in:graveyard",)


def test_graveyard_count_marker_not_for_nongraveyard_count():
    """A card whose only count is over a NON-graveyard zone (hand) recovers no
    graveyard count marker."""
    rec = {
        "name": "Reckless Fireweaver",
        "static_abilities": [
            {
                "mode": "Continuous",
                "affected": {"type": "SelfRef"},
                "modifications": [
                    {
                        "type": "SetDynamicPower",
                        "value": {
                            "type": "Ref",
                            "qty": {"type": "ZoneCardCount", "zone": "Hand"},
                        },
                    }
                ],
            }
        ],
    }
    assert not _graveyard_count_markers(rec, [])


def test_recover_graveyard_zones_self_return():
    """World Breaker's "Return this card from your graveyard to your hand" parses as a
    SelfRef bounce with zones=() — the recovery adds in:graveyard so the scope-gate
    GY-recursion hook fires."""
    ability = Ability(
        kind="activated",
        cost="mana,sacrifice",
        effects=(
            Effect(
                category="bounce",
                scope="any",
                raw="{2}{C}, Sacrifice a land: Return this card from your graveyard "
                "to your hand.",
            ),
        ),
    )
    out = _recover_graveyard_zones(ability)
    assert "in:graveyard" in out.effects[0].zones


def test_recover_graveyard_zones_hand_or_graveyard_cheat():
    """Dakkon's "put an artifact card from your hand or graveyard onto the
    battlefield" loses the graveyard disjunct (cheat_play from:hand only) — the
    recovery adds from:graveyard so the GY→battlefield cheat hook fires."""
    ability = Ability(
        kind="activated",
        effects=(
            Effect(
                category="cheat_play",
                scope="any",
                zones=("from:hand", "to:battlefield"),
                raw="You may put an artifact card from your hand or graveyard onto "
                "the battlefield.",
            ),
        ),
    )
    out = _recover_graveyard_zones(ability)
    assert "from:graveyard" in out.effects[0].zones


def test_recover_graveyard_zones_self_mill_deposit():
    """Atris/Marchesa's "put one … into your hand and the other into your graveyard"
    self-mill deposit (phase dropped to:graveyard) recovers to:graveyard."""
    ability = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="topdeck_select",
                scope="any",
                zones=("to:hand",),
                raw="Put one of them into your hand and the other into your graveyard.",
            ),
        ),
    )
    out = _recover_graveyard_zones(ability)
    assert "to:graveyard" in out.effects[0].zones


def test_recover_graveyard_zones_excludes_dies():
    """A battlefield→graveyard 'dies' deposit is NOT self-mill — the recovery must
    not add to:graveyard when from:battlefield is present (death, not fill-the-yard)."""
    ability = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="mill",
                scope="any",
                zones=("from:battlefield", "to:graveyard"),
                raw="put it into your graveyard from the battlefield",
            ),
        ),
    )
    out = _recover_graveyard_zones(ability)
    # already had to:graveyard; recovery is append-only and leaves from:battlefield
    assert "from:battlefield" in out.effects[0].zones


def test_recover_count_operand_pump_for_each():
    """A pump whose "for each X" scaling phase dropped to op='fixed' (Pride of the
    Clouds, Strata Scythe) is lifted to op='count' with the counted permanent class as
    subject, so scaling_pump fires; the per-unit factor is preserved (Anya's +3/+3)."""
    pump = Ability(
        kind="static",
        effects=(
            Effect(
                category="pump",
                scope="any",
                amount=Quantity(op="fixed", factor=1),
                raw="~ gets +1/+1 for each other creature on the battlefield with "
                "flying.",
            ),
        ),
    )
    out = _recover_count_operand(pump)
    amt = out.effects[0].amount
    assert amt.op == "count"
    assert amt.subject is not None
    assert "Creature" in amt.subject.card_types
    anya = Ability(
        kind="static",
        effects=(
            Effect(
                category="pump",
                scope="you",
                amount=Quantity(op="fixed", factor=3),
                raw="~ gets +3/+3 for each opponent whose life total is less.",
            ),
        ),
    )
    assert _recover_count_operand(anya).effects[0].amount.factor == 3


def test_recover_count_operand_draw_and_guards():
    """A "draw a card for each creature it devoured" draw (Skullmulcher) lifts to
    op='count'; a bare "draw X cards" (Braingeyser — already op='count', no "for
    each") and a structured count are both left untouched."""
    skull = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="draw",
                scope="you",
                amount=Quantity(op="fixed", factor=1),
                raw="When ~ enters, draw a card for each creature it devoured.",
            ),
        ),
    )
    assert _recover_count_operand(skull).effects[0].amount.op == "count"
    braingeyser = Ability(
        kind="spell",
        effects=(
            Effect(
                category="draw",
                scope="any",
                amount=Quantity(op="count", factor=1),
                raw="Target player draws X cards.",
            ),
        ),
    )
    # op already count (not fixed) → untouched; no "for each" so never re-tagged.
    assert _recover_count_operand(braingeyser).effects[0].amount.op == "count"
    plain = Ability(
        kind="spell",
        effects=(
            Effect(
                category="draw",
                scope="you",
                amount=Quantity(op="fixed", factor=2),
                raw="Draw two cards.",
            ),
        ),
    )
    assert _recover_count_operand(plain).effects[0].amount.op == "fixed"


def test_graveyard_cast_grant_marker_from_emblem():
    """Jaya's emblem ("You may cast instant and sorcery spells from your graveyard")
    parses as category='emblem' with the cast permission only in raw — recovered as a
    cast_from_zone marker so graveyard_matters fires."""
    rec = {"name": "Jaya Ballard", "oracle_text": ""}
    abilities = [
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="emblem",
                    scope="any",
                    raw='You get an emblem with "You may cast instant and sorcery '
                    'spells from your graveyard."',
                ),
            ),
        )
    ]
    markers = _graveyard_cast_grant_markers(rec, abilities)
    assert {"cast_from_zone"} == {m.category for m in markers}
    assert markers[0].zones == ("from:graveyard",)


def test_graveyard_cast_grant_marker_from_oracle_fallback():
    """Danitha's "you may cast an Aura or Equipment spell from your graveyard" static
    leaves no carrier raw (its static_abilities row recovers no mode) — the oracle
    fallback recovers the cast_from_zone marker."""
    rec = {
        "name": "Danitha, New Benalia's Light",
        "oracle_text": "Vigilance, trample, lifelink\nOnce during each of your turns, "
        "you may cast an Aura or Equipment spell from your graveyard.",
    }
    markers = _graveyard_cast_grant_markers(rec, [])
    assert {"cast_from_zone"} == {m.category for m in markers}


def test_graveyard_cast_grant_marker_gated_to_no_structural():
    """A face with a structural cast_from_zone already recovers no grant marker."""
    rec = {"name": "X", "oracle_text": "cast a spell from your graveyard"}
    structural = [Ability(kind="spell", effects=(Effect(category="cast_from_zone"),))]
    assert not _graveyard_cast_grant_markers(rec, structural)


def test_activation_restriction_threshold_recovers_graveyard_zone():
    """Infected Vermin's "Activate only if there are seven or more cards in your
    graveyard" rides activation_restrictions (not the condition field) — the
    projected ability's condition carries the graveyard zone so the gate fires."""
    rec = {
        "name": "Infected Vermin",
        "card_type": {"core_types": ["Creature"], "subtypes": ["Rat"]},
        "oracle_text": "Threshold — {3}{B}: This creature deals 3 damage to each "
        "creature and each player. Activate only if there are seven or more cards in "
        "your graveyard.",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "DamageAll",
                    "amount": {"type": "Fixed", "value": 3},
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                    "player_filter": {"type": "All"},
                },
                "cost": {"type": "Mana", "cost": {"type": "Cost", "shards": ["Black"]}},
                "activation_restrictions": [
                    {
                        "type": "RequiresCondition",
                        "data": {
                            "condition": {
                                "type": "ZoneCardCountAtLeast",
                                "zone": "Graveyard",
                                "count": 7,
                            }
                        },
                    }
                ],
            }
        ],
    }
    card = project_card([rec])
    conds = [ab.condition for ab in card.all_abilities() if ab.condition is not None]
    assert any("graveyard" in c.zones for c in conds)


def test_graveyard_exile_cost_marks_exilegrave():
    """A "Exile this card from your graveyard" cost (Renew / escape, Boneyard
    Mycodrax) marks the cost `exilegrave` so the GY-fuel cost hook fires; a
    battlefield/hand exile cost stays the generic `exile` part."""
    renew = {
        "name": "Agent of Kotis",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "PutCounter",
                    "counter_type": "P1P1",
                    "count": {"type": "Fixed", "value": 2},
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                },
                "cost": {
                    "type": "Composite",
                    "costs": [
                        {
                            "type": "Mana",
                            "cost": {"type": "Cost", "shards": ["Blue"], "generic": 3},
                        },
                        {
                            "type": "Exile",
                            "count": 1,
                            "zone": "Graveyard",
                            "filter": {"type": "SelfRef"},
                        },
                    ],
                },
            }
        ],
    }
    ab = project_card([renew]).all_abilities()[0]
    assert "exilegrave" in (ab.cost or "")
    # a non-graveyard exile cost stays generic
    other = {
        "name": "X",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {"type": "Draw", "count": {"type": "Fixed", "value": 1}},
                "cost": {"type": "Exile", "count": 1, "zone": "Hand"},
            }
        ],
    }
    ab2 = project_card([other]).all_abilities()[0]
    assert "exilegrave" not in (ab2.cost or "")


def test_topdeck_stack_surfaces_graveyard_origin_zone():
    """Academy Ruins' "Put target artifact card from your graveyard on top of your
    library" (PutAtLibraryPosition with an InZone:Graveyard target) now surfaces
    in:graveyard so the zone-aware graveyard_matters hook reads the GY→library
    recursion."""
    rec = {
        "name": "Academy Ruins",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "PutAtLibraryPosition",
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Artifact"],
                        "controller": "You",
                        "properties": [{"type": "InZone", "zone": "Graveyard"}],
                    },
                    "count": {"type": "Fixed", "value": 1},
                    "position": {"type": "Top"},
                },
                "cost": {"type": "Tap"},
            }
        ],
    }
    eff = _effect_with(project_card([rec]), "topdeck_stack")
    assert "in:graveyard" in eff.zones


def test_recover_graveyard_zones_card_reference():
    """A card REFERENCED in/from a graveyard in a target_only / topdeck raw (Aberrant
    Mind's "choose target card in your graveyard") recovers in:graveyard; a deposit
    or a from:battlefield dies-event does not."""
    ref = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="target_only",
                scope="any",
                raw="When ~ enters, choose target instant or sorcery card in your "
                "graveyard.",
            ),
        ),
    )
    assert "in:graveyard" in _recover_graveyard_zones(ref).effects[0].zones
    # a dies-event card "put into a graveyard from the battlefield" is not recursion
    dies = Ability(
        kind="triggered",
        effects=(
            Effect(
                category="target_only",
                scope="any",
                raw="a card is put into a graveyard from the battlefield",
            ),
        ),
    )
    assert "in:graveyard" not in _recover_graveyard_zones(dies).effects[0].zones


def test_graveyard_count_marker_from_effect_amount():
    """Liliana Waker's "-X/-X where X is GraveyardSize" keeps the GraveyardSize in the
    ability effect subtree — recovered as an in:graveyard count marker."""
    rec = {
        "name": "Liliana, Waker of the Dead",
        "abilities": [
            {
                "kind": "Activated",
                "effect": {
                    "type": "Pump",
                    "power": {
                        "type": "Quantity",
                        "value": {
                            "type": "Multiply",
                            "factor": -1,
                            "inner": {
                                "type": "Ref",
                                "qty": {
                                    "type": "GraveyardSize",
                                    "player": {"type": "Controller"},
                                },
                            },
                        },
                    },
                    "target": {"type": "Typed", "type_filters": ["Creature"]},
                },
                "cost": {"type": "Loyalty", "amount": -3},
            }
        ],
    }
    markers = _graveyard_count_markers(rec, [])
    assert {"board_count"} == {m.category for m in markers}
    assert markers[0].zones == ("in:graveyard",)


# ── ADR-0027 sacrifice_matters: edict scope split + additional-cost marker ─────


def test_sacrifice_player_scope_edict_vs_you():
    """A Sacrifice effect's scope reads WHO sacrifices (the sacrificed object's
    controller): a forced opponent sac (TargetPlayer / DefendingPlayer / Opponent) →
    opp; each-player → each; a you/null self-sacrifice keeps the fallback ('any')."""
    you = {
        "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}
    }
    null = {
        "target": {"type": "Typed", "type_filters": ["Creature"], "controller": None}
    }
    edict = {"target": {"type": "Typed", "controller": "TargetPlayer"}}
    defend = {"target": {"type": "Typed", "controller": "DefendingPlayer"}}
    each = {"target": {"type": "Typed", "controller": "ScopedPlayer"}}
    nested = {"target": {"type": "Typed", "controller": {"type": "Opponent"}}}
    assert _sacrifice_player_scope(you, "any") == "any"
    assert _sacrifice_player_scope(null, "any") == "any"
    assert _sacrifice_player_scope(edict, "any") == "opp"
    assert _sacrifice_player_scope(defend, "any") == "opp"
    assert _sacrifice_player_scope(each, "any") == "each"
    assert _sacrifice_player_scope(nested, "any") == "opp"
    # an explicit You target overrides an opp fallback leaked by a downstream
    # target-player clause (Cabal Therapist) — the subject controller is the truth.
    assert _sacrifice_player_scope(you, "opp") == "any"


def test_predatory_nightstalker_edict_scope():
    """An edict ("target opponent sacrifice a creature") projects the Sacrifice
    effect at scope opp — the structural discriminator that keeps it out of the
    you-sacrifice lane while edict_matters still fires."""
    rec = {
        "name": "Predatory Nightstalker",
        "oracle_text": "When this creature enters, you may have target opponent "
        "sacrifice a creature of their choice.",
        "triggers": [
            {
                "mode": "ChangesZone",
                "destination": "Battlefield",
                "execute": {
                    "effect": {
                        "type": "Sacrifice",
                        "target": {
                            "type": "Typed",
                            "type_filters": ["Creature"],
                            "controller": "TargetPlayer",
                        },
                        "count": {"type": "Fixed", "value": 1},
                    }
                },
            }
        ],
    }
    card = project_card([rec])
    sacs = [
        e
        for f in card.faces
        for a in f.abilities
        for e in a.effects
        if e.category == "sacrifice"
    ]
    assert sacs
    assert all(e.scope == "opp" for e in sacs)


def test_sacrifice_cost_marker_from_additional_cost():
    """Altar's Reap keeps its "sacrifice a creature" additional cost in the record's
    additional_cost field but drops it off the projected spell — recovered as a
    you-sacrifice marker (the land-sac form is excluded)."""
    reap = {
        "name": "Altar's Reap",
        "oracle_text": "As an additional cost to cast this spell, sacrifice a "
        "creature.\nDraw two cards.",
        "additional_cost": {
            "type": "Required",
            "data": {
                "type": "Sacrifice",
                "target": {
                    "type": "Typed",
                    "type_filters": ["Creature"],
                    "controller": None,
                    "properties": [],
                },
                "count": 1,
            },
        },
    }
    markers = _sacrifice_cost_markers(reap, [])
    assert len(markers) == 1
    assert markers[0].category == "sacrifice"
    assert markers[0].scope == "you"
    assert markers[0].subject is not None
    assert markers[0].subject.card_types == ("Creature",)
    # land-only additional-cost sac (Crop Rotation / Harrow) is the land_sacrifice
    # lane, not sacrifice_matters → no marker.
    land = dict(reap)
    land["additional_cost"] = {
        "type": "Required",
        "data": {
            "type": "Sacrifice",
            "target": {"type": "Typed", "type_filters": ["Land"], "controller": None},
            "count": 1,
        },
    }
    assert not _sacrifice_cost_markers(land, [])
    # gated to faces with no structural sacrifice effect (no double-tag)
    structural = [
        Ability(kind="spell", effects=(Effect(category="sacrifice", scope="you"),))
    ]
    assert not _sacrifice_cost_markers(reap, structural)


def test_sacrifice_cost_marker_from_choice_and_kicker():
    """A Sacrifice nested in a Choice additional cost (Bone Shards "sacrifice a
    creature or discard") or a Kicker (Vicious Offering) is recovered; a Choice with
    only land-sac + non-sac alternatives is not."""
    bone = {
        "name": "Bone Shards",
        "additional_cost": {
            "type": "Required",
            "data": {
                "type": "Choice",
                "data": [
                    {
                        "type": "Sacrifice",
                        "target": {"type": "Typed", "type_filters": ["Creature"]},
                        "count": 1,
                    },
                    {"type": "Discard", "count": 1},
                ],
            },
        },
    }
    markers = _sacrifice_cost_markers(bone, [])
    assert len(markers) == 1
    assert markers[0].category == "sacrifice"
    assert markers[0].subject is not None
    assert markers[0].subject.card_types == ("Creature",)
    kicker = {
        "name": "Vicious Offering",
        "additional_cost": {
            "type": "Kicker",
            "data": {
                "costs": [
                    {
                        "type": "Sacrifice",
                        "target": {"type": "Typed", "type_filters": ["Creature"]},
                        "count": 1,
                    }
                ]
            },
        },
    }
    assert len(_sacrifice_cost_markers(kicker, [])) == 1


def test_sacrifice_grant_markers_shapes():
    """The granted/dropped sac-outlet recovery fires on a quoted granted outlet, a
    casualty grant, a free-spell pitch, a keyworded-cost sac, a pay-or-die
    alternative, and a modal bullet — but NOT on a quoted land-sac or a Ward cost."""

    def fires(text: str) -> bool:
        return bool(_sacrifice_grant_markers({"oracle_text": text}, []))

    assert fires('Enchanted creature has "Sacrifice a creature: ~ gets +2/+1."')
    assert fires("The first instant or sorcery spell you cast has casualty 2.")
    assert fires(
        "You may sacrifice a nontoken blue creature rather than pay this "
        "spell's mana cost. Counter target spell."
    )
    assert fires("Flashback—Sacrifice three creatures.")
    assert fires("Morph—Sacrifice another creature.")
    assert fires(
        "Noncreature spells you cast cost {2} less. Whenever you cast a "
        "noncreature spell, counter that spell unless you sacrifice a creature."
    )
    assert fires("• Destroy up to one target artifact.\n• Sacrifice an artifact: ...")
    assert fires("Cumulative upkeep—Sacrifice a creature.")
    # a quoted LAND-sac granted cost is the land_sacrifice lane, not this one
    assert not fires(
        'Activated abilities of nontoken Rebels cost an additional "Sacrifice '
        'a land" to activate.'
    )
    # a Ward cost is the OPPONENT's sacrifice, not a you-sac outlet
    assert not fires("Ward—Sacrifice a creature.\nFlying")
    # gated to faces with no structural sacrifice effect
    structural = [
        Ability(kind="spell", effects=(Effect(category="sacrifice", scope="you"),))
    ]
    assert not _sacrifice_grant_markers(
        {"oracle_text": "Cumulative upkeep—Sacrifice a creature."}, structural
    )


# ── ADR-0027 lifeloss_matters: self / drain markers ────────────────────────────


def test_lifeloss_markers_self_shapes():
    """The self life-loss recovery fires a lose_life scope=you marker on a pay-life
    additional cost, a free-spell pitch, a keyworded-cost / cumulative-upkeep / tax /
    Defiler pay-life, a granted / modal / dice / choose "you lose N life", and the
    "gain or lose life" payoff."""

    def self_marker(text: str, record: dict | None = None) -> bool:
        rec = {"oracle_text": text}
        if record:
            rec.update(record)
        return any(
            m.category == "lose_life" and m.scope == "you"
            for m in _lifeloss_markers(rec, [])
        )

    # additional_cost PayLife (bare and nested in a Choice)
    assert self_marker(
        "Destroy target creature.",
        {
            "additional_cost": {
                "type": "Required",
                "data": {
                    "type": "Choice",
                    "data": [
                        {"type": "PayLife", "amount": {"type": "Fixed", "value": 5}},
                        {"type": "Discard", "count": 1},
                    ],
                },
            }
        },
    )
    assert self_marker(
        "You may pay 1 life and exile a blue card from your hand rather than "
        "pay this spell's mana cost. Counter target spell."
    )
    assert self_marker("Flashback—{1}{U}, Pay 3 life.")
    assert self_marker("Cumulative upkeep—Pay 1 life.")
    assert self_marker(
        "At the beginning of your upkeep, tap this creature unless you pay 1 life."
    )
    assert self_marker(
        "As an additional cost to cast green permanent spells, you may pay 2 life."
    )
    assert self_marker("• You draw a card and you lose 1 life.")
    assert self_marker("1—9 | You draw a card and you lose 1 life.")
    assert self_marker("Whenever you gain or lose life during your turn, ...")


def test_lifeloss_markers_drain_shapes():
    """The drain recovery fires a lose_life scope=opp marker on a modal-bullet
    opponent loss, a quoted granted "target player loses N life", a "lost life this
    turn" payoff, and a dice-table opponent drain."""

    def drain_marker(text: str) -> bool:
        return any(
            m.category == "lose_life" and m.scope == "opp"
            for m in _lifeloss_markers({"oracle_text": text}, [])
        )

    assert drain_marker("• Target opponent loses 5 life.")
    assert drain_marker('Enchanted land has "{T}: Target player loses 3 life."')
    assert drain_marker(
        "At the beginning of each end step, if an opponent lost 3 or more life "
        "this turn, draw a card."
    )
    assert drain_marker("1—9 | Each opponent loses 2 life.")


def test_lifeloss_markers_excluded():
    """A Land card (the pay-life mana VETO), a face with a structural lose_life, and a
    Ward cost (the OPPONENT pays) recover no marker."""
    # Land card with a pay-life mana ability
    assert not _lifeloss_markers(
        {
            "oracle_text": "{T}, Pay 1 life: Add {G} or {W}.",
            "card_type": {"core_types": ["Land"]},
        },
        [],
    )
    # already has a structural lose_life
    structural = [
        Ability(kind="spell", effects=(Effect(category="lose_life", scope="you"),))
    ]
    assert not _lifeloss_markers(
        {"oracle_text": "You may pay 2 life rather than pay this spell's mana cost."},
        structural,
    )
    # a Ward cost is the opponent's life payment, not a you-loss engine
    assert not _lifeloss_markers({"oracle_text": "Ward—Pay 2 life.\nFlying"}, [])


# ── generalized modal-choose-split (ADR-0027 removal_matters shape 4 + reuse) ──


def test_modal_split_recovers_typed_mode_bodies():
    """A modal `choose` whose per-mode bodies phase keeps only in the sibling
    `mode_abilities` array (Mishra's "• Destroy target artifact or planeswalker",
    "• Mishra deals 3 damage", "• opponent discards") recovers each as a real typed
    Effect with its subject — the destroy bullet lands as destroy(Artifact,
    Planeswalker), not a subjectless `other` (CR 700.2)."""
    modes = [
        {
            "kind": "Spell",
            "effect": {
                "type": "Discard",
                "count": {"type": "Fixed", "value": 2},
                "target": {"type": "Typed", "controller": "Opponent"},
            },
        },
        {
            "kind": "Spell",
            "effect": {
                "type": "DealDamage",
                "amount": {"type": "Fixed", "value": 3},
                "target": {"type": "Any"},
            },
        },
        {
            "kind": "Spell",
            "effect": {
                "type": "Destroy",
                "target": {
                    "type": "Or",
                    "filters": [
                        {"type": "Typed", "type_filters": ["Artifact"]},
                        {"type": "Typed", "type_filters": ["Planeswalker"]},
                    ],
                },
            },
        },
    ]
    descs = [
        "Target opponent discards two cards.",
        "~ deals 3 damage to any target.",
        "Destroy target artifact or planeswalker.",
    ]
    effs = _modal_split_effects(modes, descs, "choose three —")
    cats = [e.category for e in effs]
    assert "destroy" in cats
    destroy = next(e for e in effs if e.category == "destroy")
    assert set(destroy.subject.card_types) == {"Artifact", "Planeswalker"}
    # the mode_description text rides each mode's raw as a bullet
    assert destroy.raw == "• Destroy target artifact or planeswalker."


def test_modal_split_via_collect_effects_prepends_choose_marker():
    """Driving the split through `_collect_effects` (the integration seam) on a
    placeholder GenericEffect node with a `mode_abilities` sibling prepends a
    `choose` marker and SUPPRESSES the empty placeholder (no stray `other`)."""
    node = {
        "effect": {"type": "GenericEffect", "static_abilities": []},
        "modal": {
            "mode_descriptions": [
                "Destroy target artifact.",
                "Destroy target enchantment.",
            ]
        },
        "mode_abilities": [
            {
                "kind": "Spell",
                "effect": {
                    "type": "Destroy",
                    "target": {"type": "Typed", "type_filters": ["Artifact"]},
                },
            },
            {
                "kind": "Spell",
                "effect": {
                    "type": "Destroy",
                    "target": {"type": "Typed", "type_filters": ["Enchantment"]},
                },
            },
        ],
    }
    effs = _collect_effects(node, "Choose one —")
    cats = [e.category for e in effs]
    assert cats[0] == "choose"
    assert cats.count("destroy") == 2
    assert "other" not in cats  # placeholder suppressed
    arts = {tuple(e.subject.card_types) for e in effs if e.category == "destroy"}
    assert ("Artifact",) in arts
    assert ("Enchantment",) in arts


def test_modal_split_text_recovers_unstructured_mode():
    """A mode whose body phase couldn't structure (a GenericEffect token bullet)
    falls back to supplement text-recovery so its category still surfaces (the prior
    floor), keeping the card from regressing to partial."""
    modes = [
        {"kind": "Spell", "effect": {"type": "GenericEffect", "static_abilities": []}},
    ]
    descs = ["You gain 3 life."]
    effs = _modal_split_effects(modes, descs, "choose one —")
    # the gain-life category recovered from the bullet text, not a bare `other`
    assert [e.category for e in effs] == ["gain_life"]


# ── enters-with self-counter replacement (ADR-0027 counters_matter shape 2a) ───


def test_enters_with_p1p1_replacement_projects_place_counter():
    """ "~ enters with N +1/+1 counters on it" parses as a Moved→Battlefield
    replacement whose execute is a PutCounter(P1P1). phase emits nothing structural
    for enters-with; the projection recovers a place_counter (kind p1p1, scope you)
    so the +1/+1 counters_matter lane fires (Faithful Watchdog, Mistcutter Hydra)."""
    rep = {
        "event": "Moved",
        "destination_zone": "Battlefield",
        "execute": {
            "kind": "Spell",
            "effect": {
                "type": "PutCounter",
                "counter_type": "P1P1",
                "count": {"type": "Fixed", "value": 3},
                "target": {"type": "SelfRef"},
            },
        },
        "description": "~ enters with three +1/+1 counters on it.",
    }
    ab = _project_replacement(rep)
    assert ab is not None
    assert [e.category for e in ab.effects] == ["place_counter"]
    e = ab.effects[0]
    assert e.counter_kind == "p1p1"
    assert e.scope == "you"


def test_enters_with_oil_replacement_routes_to_oil_kind():
    """A non-p1p1 enters-with kind (Oil) keeps its counter_kind so it routes to the
    oil_counter lane, NOT +1/+1 counters_matter (CR 122.1 — kinds are distinct)."""
    rep = {
        "event": "Moved",
        "destination_zone": "Battlefield",
        "execute": {
            "kind": "Spell",
            "effect": {
                "type": "PutCounter",
                "counter_type": "Oil",
                "count": {"type": "Fixed", "value": 3},
                "target": {"type": "SelfRef"},
            },
        },
        "description": "~ enters with three oil counters on it.",
    }
    ab = _project_replacement(rep)
    assert ab is not None
    assert ab.effects[0].counter_kind == "oil"


def test_moved_replacement_without_putcounter_is_ignored():
    """A Moved→Battlefield replacement whose execute is NOT a PutCounter (a generic
    enters-tapped / other ETB replacement) projects no place_counter ability."""
    rep = {
        "event": "Moved",
        "destination_zone": "Battlefield",
        "execute": {
            "kind": "Spell",
            "effect": {"type": "GenericEffect", "static_abilities": []},
        },
        "description": "~ enters tapped.",
    }
    assert _project_replacement(rep) is None


# ── enters-with-OTHER static grant (ADR-0027 counters_matter close, bucket D) ──


def test_changezone_replacement_with_putcounter_projects_place_counter():
    """ "Each other Angel you control enters with an additional +1/+1 counter on it"
    (Giada, Coin of Mastery, Oona's Blackguard) parses as a ChangeZone→Battlefield
    replacement whose execute is PutCounter(P1P1) — the SAME execute shape as the
    Moved self form, just a different event. The projection recovers a place_counter
    (kind p1p1, scope you) so the static +1/+1 grant opens counters_matter."""
    rep = {
        "event": "ChangeZone",
        "destination_zone": "Battlefield",
        "execute": {
            "kind": "Spell",
            "effect": {
                "type": "PutCounter",
                "counter_type": "P1P1",
                "count": {"type": "Fixed", "value": 1},
                "target": {"type": "SelfRef"},
            },
        },
        "valid_card": {
            "type": "Typed",
            "type_filters": [{"Subtype": "Angel"}],
            "controller": "You",
            "properties": [{"type": "Another"}],
        },
        "description": "Each other Angel you control enters with an additional "
        "+1/+1 counter on it for each Angel you already control.",
    }
    ab = _project_replacement(rep)
    assert ab is not None
    assert [e.category for e in ab.effects] == ["place_counter"]
    assert ab.effects[0].counter_kind == "p1p1"
    assert ab.effects[0].scope == "you"


# ── enter_with_counters nested on a Token effect (bucket A) ───────────────────


def test_token_enter_with_counters_projects_place_counter():
    """ "Create a 0/0 Fractal token. Put X +1/+1 counters on it" (Body of Research,
    the Fractal cycle, Slime Against Humanity) parses the placement as
    token.enter_with_counters — a property of the made token spec the structured
    projection (make_token) otherwise drops. _project_effect appends a place_counter
    (kind p1p1, scope you) so the token's +1/+1 counters open counters_matter."""
    eff = {
        "type": "Token",
        "name": "Fractal",
        "types": ["Creature", "Fractal"],
        "count": {"type": "Fixed", "value": 1},
        "enter_with_counters": [
            ["P1P1", {"type": "Ref", "qty": {"type": "ZoneCardCount"}}]
        ],
    }
    effs = _project_effect(eff, "Create a Fractal token. Put X +1/+1 counters on it.")
    cats = [e.category for e in effs]
    assert "make_token" in cats
    place = [e for e in effs if e.category == "place_counter"]
    assert place
    assert place[0].counter_kind == "p1p1"
    assert place[0].scope == "you"


def test_token_without_enter_with_counters_has_no_place_counter():
    """A plain token maker (no entering counters) projects make_token only — the
    enter_with_counters bind must not invent a placement."""
    eff = {
        "type": "Token",
        "name": "Soldier",
        "types": ["Creature", "Soldier"],
        "count": {"type": "Fixed", "value": 1},
    }
    effs = _project_effect(eff, "Create a 1/1 white Soldier creature token.")
    assert [e.category for e in effs] == ["make_token"]


# ── enter_with_counters nested on a ChangeZone/reanimate effect (bucket B) ────


def test_changezone_enter_with_counters_projects_place_counter():
    """ "Return target creature card from your graveyard to the battlefield with two
    additional +1/+1 counters on it" (Evil Reawakened, the Transmogrant cycle,
    Phoenix Chick) parses the rider as changezone.enter_with_counters. _project_effect
    appends a place_counter (kind p1p1) alongside the reanimate so the returned
    creature's entering counters open counters_matter (CR 614.13)."""
    eff = {
        "type": "ChangeZone",
        "destination": "Battlefield",
        "enter_with_counters": [["P1P1", {"type": "Fixed", "value": 2}]],
    }
    effs = _project_effect(
        eff, "Return target creature card from your graveyard with two +1/+1 counters."
    )
    # The change-zone move keeps its own (primary) effect; the rider is APPENDED as a
    # second place_counter — never replacing the move.
    assert len(effs) >= 2
    place = [e for e in effs if e.category == "place_counter"]
    assert place
    assert place[0].counter_kind == "p1p1"
    assert place[0].scope == "you"


# ── garbled counter_type normalization (the mis-parsed +1/+1 signature) ───────


def test_norm_counter_kind_recovers_garbled_plus_one():
    """phase sometimes leaks rider text into counter_type ("additional +1/+1",
    "flying and with X +1/+1", "trample. the token enters with X +1/+1"). The +1/+1
    signature survives in the raw string, so _norm_counter_kind collapses it to the
    clean p1p1 kind instead of a junk token no lane reads (Necromantic Summons,
    Dralnu's Pet, Printlifter Ooze, Turntimber Symbiosis)."""
    assert _norm_counter_kind("additional +1/+1") == "p1p1"
    assert _norm_counter_kind("flying and with X +1/+1") == "p1p1"
    assert _norm_counter_kind("trample. the token enters with X +1/+1") == "p1p1"
    assert _norm_counter_kind("a number of +1/+1") == "p1p1"
    # -1/-1 routes to the minus lane; clean + named kinds stay themselves.
    assert _norm_counter_kind("additional -1/-1") == "m1m1"
    assert _norm_counter_kind("P1P1") == "p1p1"
    assert _norm_counter_kind("Oil") == "oil"
    assert _norm_counter_kind("study") == "study"
