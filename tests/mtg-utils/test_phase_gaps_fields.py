"""Overlay field corrections (ADR-0035 Stage-3b (b)): phase parses the node but
stamps one field wrong, and ``overlay_corrections`` re-reads it on the Layer-2
overlay — the effect's ``ConceptNode`` decoration (a ``scope`` or ``subject``
mark), an ``AbilityUnit.corrections`` row (``FieldCorrection``) for a def or a
filter with no ``ConceptNode`` of its own, or the unit's derived
``trigger_event``.

Each arm has a ``retirement_canary`` over the raw phase record (it fails
RETIRE-READY once phase stamps the field right), a test that the arm writes the
correction while the mirror node keeps phase's own stamp (substrate purity),
and the lane-side idents the correction moves, proven on the real cards.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest

from mtg_utils._analysis.lanes.animate_land_types import _animated_filters
from mtg_utils._card_ir.crosswalk import (
    ANAPHORIC,
    SUSPENDED_CARD,
    AbilityUnit,
    ConceptNode,
    FieldCorrection,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_phase_records, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


def _units(name: str) -> list[AbilityUnit]:
    test_card_ir(name)  # seeds the trees from the snapshot's phase records
    return [u for t in trees_for(test_card(name)) for u in t.units]


def _corrections(name: str, arm: str) -> list[FieldCorrection]:
    return [fc for u in _units(name) for fc in u.corrections if fc.arm == arm]


def _effects(name: str, tag: str) -> list[ConceptNode]:
    return [c for u in _units(name) for c in u.effects if tag_of(c.node) == tag]


def _walk(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _type(node: object) -> object:
    return node.get("type") if isinstance(node, dict) else None


def _raw_nodes(name: str) -> list[dict]:
    return [n for rec in test_phase_records(name) for n in _walk(rec)]


def _retire(name: str, arm: str, field: str) -> str:
    return (
        f"{name}: RETIRE-READY — phase now stamps the {field} right. Drop {name} "
        f"from this canary; once no card is left, delete "
        f"overlay_corrections.{arm} and the lane read that opts into it."
    )


# ── cant_untap_object: "that creature doesn't untap" stamped SelfRef ──────────

_CANT_UNTAP_OBJECTS = [
    "Mesmerizing Benthid",  # its token's "that creature doesn't untap"
    "Wall of Stolen Identity",  # "tap the copied creature and it doesn't untap"
    "Tsabo's Web",  # "Each land with an activated ability … doesn't untap"
    "Telekinesis",  # "Tap target creature. … It doesn't untap"
]


@pytest.mark.parametrize(
    "name",
    [
        "Scion of Stygia",  # "Tap that creature. It doesn't untap …"
        "Code of Constraint",  # "tap that creature and it doesn't untap"
    ],
)
def test_a_typed_cant_untap_object_is_a_tapper(name):
    """Phase v0.118.0 stamps these untap locks' affected object itself (they
    left the canary): no correction, and still a tapper (CR 502.3)."""
    assert not _corrections(name, "cant_untap_object")
    assert "tapper_engine|any|" in _idents(name)


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _CANT_UNTAP_OBJECTS)
def test_cant_untap_object_canary(name):
    stamps = [
        n["affected"]
        for n in _raw_nodes(name)
        if n.get("mode") == "CantUntap" and "affected" in n
    ]
    assert stamps
    assert all(_type(a) == "SelfRef" for a in stamps), _retire(
        name, "_arm_cant_untap_object", "untap lock's affected object"
    )


@pytest.mark.parametrize("name", _CANT_UNTAP_OBJECTS)
def test_cant_untap_object_is_a_tapper(name):
    (fc,) = _corrections(name, "cant_untap_object")
    assert fc.field == "affected"
    assert fc.value == ANAPHORIC
    assert fc.node.affected.to_dict()["type"] == "SelfRef"  # phase's own stamp
    # CR 502.3: an effect keeping another player's permanent from untapping.
    assert "tapper_engine|any|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Brass Gnat",  # "~ doesn't untap during your untap step"
        "Mana Vault",
        "Apes of Rath",  # "Whenever ~ attacks, it doesn't untap …": itself
    ],
)
def test_a_self_untap_drawback_stays_no_tapper(name):
    assert not _corrections(name, "cant_untap_object")
    assert "tapper_engine|any|" not in _idents(name)


# ── anaphoric_pump: "it gets -1/-0" stamped SelfRef ───────────────────────────


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Blood Lust", "Six-Sided Die"])
def test_anaphoric_pump_canary(name):
    pumps = [n for n in _raw_nodes(name) if _type(n) == "Pump"]
    assert any(_type(p.get("target")) == "SelfRef" for p in pumps), _retire(
        name, "_arm_anaphoric_pump", "pump's target"
    )


def test_a_delayed_triggers_it_is_the_watched_creature():
    # "Until your next turn, whenever a creature an opponent controls attacks,
    # it gets -1/-0" — the attacker, not Jace. Phase v0.118.0 stamps the pump's
    # target itself (Jace left the canary), so no correction applies.
    (pump,) = _effects("Jace, Architect of Thought", "Pump")
    assert ANAPHORIC not in pump.subject
    idents = _idents("Jace, Architect of Thought")
    assert "self_pump|you|" not in idents
    assert "debuff_makers|any|" in idents


@pytest.mark.parametrize("name", ["Blood Lust", "Six-Sided Die"])
def test_a_spells_it_is_the_chosen_creature(name):
    pumps = _effects(name, "Pump")
    assert pumps
    assert all(ANAPHORIC in c.subject for c in pumps)
    assert "debuff_makers|any|" in _idents(name)


def test_a_creature_pumping_itself_stays_a_self_pump():
    assert not any(ANAPHORIC in c.subject for c in _effects("Shivan Dragon", "Pump"))
    assert "self_pump|you|" in _idents("Shivan Dragon")


# ── tap_other_player: "that player controls" stamped controller: You ──────────

_TAPS_ANOTHER_PLAYERS = [
    "Delirium",  # "Tap target creature that player controls"
    "Mana Web",  # "tap all lands that player controls"
    "Arena",  # "target creature of an opponent's choice they control"
]


def test_a_typed_that_players_permanent_is_a_tapper():
    """Yosei, the Morning Star's "Tap up to five target permanents that player
    controls": phase v0.118.0 types the controller itself (Yosei left the
    canary), so no correction applies, and it's still a tapper."""
    assert not _corrections("Yosei, the Morning Star", "tap_other_player")
    assert "tapper_engine|any|" in _idents("Yosei, the Morning Star")


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _TAPS_ANOTHER_PLAYERS)
def test_tap_other_player_canary(name):
    controllers = [
        (n.get("target") or {}).get("controller")
        for n in _raw_nodes(name)
        if _type(n) == "SetTapState"
    ]
    assert "You" in controllers, _retire(
        name, "_arm_tap_other_player", "tapped filter's controller"
    )


@pytest.mark.parametrize("name", _TAPS_ANOTHER_PLAYERS)
def test_tapping_another_players_permanent_is_a_tapper(name):
    assert _corrections(name, "tap_other_player")
    assert "tapper_engine|any|" in _idents(name)


def test_that_players_creature_is_no_own_target():
    # Delirium taps "target creature that player controls" — an opponent's
    # creature on an opponent's turn, never your own permanent.
    assert "own_target_spell|you|" not in _idents("Delirium")
    assert "tap_down|opponents|" in _idents("Delirium")
    assert "tap_down|opponents|" in _idents("Mana Web")


def test_tapping_your_own_creatures_is_no_tapper():
    # "you may tap any number of untapped creatures you control. You gain 2 life
    # for each creature tapped this way" taps no threat.
    assert not _corrections("Jaddi Lifestrider", "tap_other_player")
    assert "tapper_engine|any|" not in _idents("Jaddi Lifestrider")


# ── self_animation: "it becomes a 5/3" stamped TriggeringSource ───────────────


@pytest.mark.retirement_canary
def test_self_animation_canary():
    """Moved from the animation lane's enters-only ``TriggeringSource`` gate,
    which the correction retired."""
    (record,) = test_phase_records("Hidden Guerrillas")
    (trigger,) = record["triggers"]
    (static,) = trigger["execute"]["effect"]["static_abilities"]
    assert static["affected"]["type"] == "TriggeringSource", _retire(
        "Hidden Guerrillas", "_arm_self_animation", "animated object"
    )


@pytest.mark.parametrize("name", ["Hidden Guerrillas", "Opal Archangel"])
def test_an_enchantment_animating_itself_animates_nothing_else(name):
    # "if ~ is an enchantment, it becomes a … creature" — itself (Hidden
    # Guerrillas's ruling: "When it turns into a creature, it is no longer an
    # enchantment"), never the cast spell.
    (fc,) = _corrections(name, "self_animation")
    assert fc.value == "SelfRef"
    assert "animate_makers" not in _keys(name)


def test_an_uncorrected_cast_trigger_animation_reads_no_spell():
    # Without the correction, Hidden Guerrillas's animation is phase's
    # ``TriggeringSource`` under a cast trigger: the watched object is the cast
    # artifact spell, never an animated permanent, so the read stays out.
    (unit,) = [u for u in _units("Hidden Guerrillas") if u.origin == "trigger"]
    assert unit.trigger_event == "cast_spell"
    assert not list(_animated_filters(replace(unit, corrections=())))


def test_an_enters_triggers_it_still_animates_the_entering_vehicle():
    assert "animate_makers|you|Artifact" in _idents("Kolodin, Triumph Caster")


# ── animated_object: "enchanted artifact … is a creature" stamped SelfRef ─────

_ANIMATED_OBJECTS = ["Alacrian Armory", "Animate Artifact", "Siege Modification"]


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _ANIMATED_OBJECTS)
def test_animated_object_canary(name):
    animations = [
        n
        for n in _raw_nodes(name)
        if "affected" in n
        and any(
            _type(m) == "AddType" and m.get("core_type") == "Creature"
            for m in n.get("modifications") or ()
        )
    ]
    assert any(_type(n["affected"]) == "SelfRef" for n in animations), _retire(
        name, "_arm_animated_object", "animated object"
    )


@pytest.mark.parametrize("name", _ANIMATED_OBJECTS)
def test_an_animated_vehicle_or_artifact_is_an_artifact_animation(name):
    # CR 613.1d: a type-changing effect; the object is the chosen target or the
    # enchanted permanent (CR 303.4b), never the card itself.
    (fc,) = _corrections(name, "animated_object")
    assert fc.value.to_dict()["type"] in ("Typed", "Or")
    assert "animate_makers|you|Artifact" in _idents(name)


def test_a_mass_tap_ends_the_animated_thread():
    # "Tap all lands you control. ~ becomes a 3/3 Turtle artifact creature."
    assert not _corrections("Chimeric Idol", "animated_object")
    assert "animate_makers" not in _keys("Chimeric Idol")


# ── counter_added_zone_change: "is put into exile" typed CounterAdded ─────────


@pytest.mark.retirement_canary
def test_counter_added_zone_change_canary():
    modes = [
        (t.get("mode"), _type(t.get("valid_card")))
        for rec in test_phase_records("Athreos, Shroud-Veiled")
        for t in rec.get("triggers") or ()
    ]
    assert ("CounterAdded", "Any") in modes, _retire(
        "Athreos, Shroud-Veiled",
        "_arm_counter_added_zone_change",
        "exile trigger's mode",
    )


def test_a_coin_counter_exile_return_is_no_counter_payoff():
    # "Whenever a creature with a coin counter on it … is put into exile,
    # return that card" watches a zone change, not a counter placement.
    events = {
        u.trigger_event for u in _units("Athreos, Shroud-Veiled") if u.trigger_event
    }
    assert "counter_added" not in events
    assert "changes_zone" in events
    assert "counter_place_trigger|you|" not in _idents("Athreos, Shroud-Veiled")
    assert "counter_place_trigger|you|" in _idents("Generous Patron")


# ── graveyard_owner: the exile's dropped graveyard owner ──────────────────────

_DROPPED_OWNERS = {
    "Rooting Moloch": "you",  # "from your graveyard"
    "Grime Gorger": "opponents",  # "from defending player's graveyard"
    "Skullsnatcher": "opponents",  # "from that player's graveyard"
    "Zombie Cannibal": "opponents",
    "Savior of Ollenbock": "any",  # "creature card from a graveyard"
}


def _graveyard_exiles(name: str) -> list[dict]:
    return [
        n
        for n in _raw_nodes(name)
        if _type(n) == "ChangeZone"
        and n.get("origin") == "Graveyard"
        and n.get("destination") == "Exile"
    ]


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", list(_DROPPED_OWNERS))
def test_graveyard_owner_canary(name):
    """Moved from the graveyard-hate arm's ``_GY_OPP_RE`` description check,
    which the correction replaced."""
    exiles = _graveyard_exiles(name)
    assert exiles
    for exile in exiles:
        target = exile["target"]
        owner = target.get("controller") or any(
            _type(p) == "Owned" for p in target.get("properties") or ()
        )
        assert not owner, _retire(name, "_arm_graveyard_owner", "graveyard's owner")


@pytest.mark.parametrize(("name", "owner"), list(_DROPPED_OWNERS.items()))
def test_graveyard_owner_reads_the_exiles_own_clause(name, owner):
    (exile,) = _effects(name, "ChangeZone")
    assert exile.scope == owner
    assert len(_graveyard_exiles(name)) == 1  # the one exile the arm decorated


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("Grime Gorger", "opponents"),  # hate on the defending player's graveyard
        ("Savior of Ollenbock", "any"),  # hate on any graveyard
        ("Skullsnatcher", "opponents"),
    ],
)
def test_graveyard_hate_reads_the_corrected_owner(name, scope):
    idents = {i for i in _idents(name) if i.startswith("graveyard_matters|")}
    assert f"graveyard_matters|{scope}|" in idents
    assert "graveyard_matters|you|" not in idents


def test_exiling_from_your_own_graveyard_is_no_hate():
    idents = _idents("Rooting Moloch")
    assert "graveyard_matters|any|" not in idents
    assert "graveyard_matters|opponents|" not in idents


def test_owners_in_disagreeing_sentences_stand_the_arm_down():
    # "Exile up to two target cards from a single graveyard. If this spell was
    # kicked, instead exile target player's graveyard."
    assert {c.scope for c in _effects("Waste Management", "ChangeZone")} == {"each"}
    assert {"graveyard_matters|any|", "graveyard_matters|opponents|"} <= _idents(
        "Waste Management"
    )


def test_cards_put_into_graveyards_this_way_name_no_owner():
    assert {c.scope for c in _effects("Stitcher Geralf", "ChangeZone")} == {"each"}


# ── player_counter_kind: "whenever you get one or more {E}" ───────────────────


@pytest.mark.retirement_canary
def test_player_counter_kind_canary():
    """Moved from the energy read's unconditional ``CounterPlayerAddedAll`` row,
    which the correction gated on the kind."""
    (record,) = test_phase_records("Territorial Gorger")
    (trigger,) = record["triggers"]
    assert trigger["mode"] == "CounterPlayerAddedAll"
    named = [k for k, v in trigger.items() if "counter" in k.lower() and v]
    assert not named, _retire(
        "Territorial Gorger", "_arm_player_counter_kind", f"counter kind ({named})"
    )


def test_an_energy_get_trigger_is_an_energy_payoff():
    # CR 107.14: {E} is an energy counter.
    (fc,) = _corrections("Territorial Gorger", "player_counter_kind")
    assert fc.value == "energy"
    assert "energy_matters" in _keys("Territorial Gorger")


# ── suspended_card_target: "or suspended card" dropped off a bounce ───────────


@pytest.mark.retirement_canary
def test_suspended_card_target_canary():
    (bounce,) = [n for n in _raw_nodes("Venser's Diffusion") if _type(n) == "Bounce"]
    assert _type(bounce["target"]) == "Typed", _retire(
        "Venser's Diffusion", "_arm_suspended_card_target", "bounce's target"
    )


def test_bouncing_a_suspended_card_is_a_suspend_reference():
    # CR 702.62b: a suspended card is in exile, has suspend and a time counter.
    (bounce,) = _effects("Venser's Diffusion", "Bounce")
    assert SUSPENDED_CARD in bounce.subject
    assert "suspend_matters|you|" in _idents("Venser's Diffusion")
    assert "suspend_matters|you|" in _idents("Clockspinning")
