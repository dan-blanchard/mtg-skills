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

from mtg_utils._card_ir.project import _filter, _predicate, project_card
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


# ── round-trip ────────────────────────────────────────────────────────────────


def test_roundtrip_lossless():
    for rec in (CRATERHOOF, SHAMANIC, TINYBONES):
        card = project_card([rec])
        assert Card.from_dict(card.to_dict()) == card


def test_empty_record_is_unparsed():
    card = project_card(
        [{"name": "Vanilla Bear", "scryfall_oracle_id": "x", "card_type": {}}]
    )
    assert card.parse_confidence == "unparsed"
    assert card.all_abilities() == ()


def test_unresolved_effect_marks_partial():
    """A GenericEffect we can't structure (Tinybones' cast clause) → partial."""
    card = project_card([TINYBONES])
    assert card.parse_confidence in {"partial", "full"}


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
