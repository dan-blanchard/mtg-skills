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
    _copied_type_from_text,
    _filter,
    _predicate,
    project_card,
)
from mtg_utils.card_ir import Ability, Card, Effect, Filter, Quantity

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
