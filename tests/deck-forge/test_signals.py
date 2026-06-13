"""Tests for deterministic signal extraction (the discovery-engine keystone).

The headline guard: a signal that concerns OPPONENTS' graveyards must be scoped
"opponents", never a generic graveyard signal that would justify self-mill (the
Tinybones overgeneralization the whole tool exists to prevent).
"""

from mtg_utils._deck_forge.signals import Signal, aggregate_signals, extract_signals


def _keys(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def test_creature_etb_scoped_to_you():
    card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert ("creature_etb", "you") in _keys(card)


def test_creature_etb_scoped_to_opponents():
    card = {
        "name": "Punisher",
        "oracle_text": "Whenever a creature an opponent controls enters, it deals 1 damage to them.",
    }
    assert ("creature_etb", "opponents") in _keys(card)


def test_graveyard_signal_scoped_to_opponents_not_generic():
    # The Tinybones case: benefits from OPPONENTS' graveyards filling.
    card = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Whenever an opponent puts one or more cards into their graveyard, "
            "you may exile a card from that graveyard and play it."
        ),
    }
    sigs = extract_signals(card)
    gy = [s for s in sigs if s.key == "graveyard_matters"]
    assert gy, "expected a graveyard signal"
    assert all(s.scope == "opponents" for s in gy)
    # It must NOT be scoped to 'you' — that would justify self-mill.
    assert ("graveyard_matters", "you") not in _keys(card)


def test_graveyard_signal_scoped_to_you_for_reanimator():
    card = {
        "name": "Reanimator",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("graveyard_matters", "you") in _keys(card)


def test_lifegain_matters():
    card = {
        "name": "Soul Warden's Friend",
        "oracle_text": "Whenever you gain life, put a +1/+1 counter on this creature.",
    }
    assert ("lifegain_matters", "you") in _keys(card)


def test_vanilla_keyword_card_has_no_signals():
    card = {"name": "Air Elemental", "oracle_text": "Flying"}
    assert extract_signals(card) == []


JYOTI = {
    "name": "Jyoti, Moag Ancient",
    "oracle_text": (
        "When Jyoti enters, create a 1/1 green Forest Dryad land creature token "
        "for each time you've cast your commander from the command zone this game. "
        "(They're affected by summoning sickness.)\n"
        "At the beginning of each combat, land creatures you control get +X/+X "
        "until end of turn, where X is Jyoti's power."
    ),
}


def test_land_creatures_matter_detected_on_jyoti():
    keys = _keys(JYOTI)
    # The defining theme of the commander — must be its own signal, not collapsed
    # into generic "creatures matter".
    assert ("land_creatures_matter", "you") in keys
    # The generic go-wide signal still fires too (regression safety).
    assert ("creatures_matter", "you") in keys


def test_land_creatures_matter_from_anthem_payoff():
    sylvan = {
        "name": "Sylvan Advocate",
        "oracle_text": (
            "Vigilance\nAs long as you control six or more lands, this creature "
            "and land creatures you control get +2/+2."
        ),
    }
    assert ("land_creatures_matter", "you") in _keys(sylvan)


def test_plant_token_maker_is_not_a_land_creatures_signal():
    # Avenger makes *Plant* creature tokens — never "land creatures". The whole
    # point of the scoped vocabulary: this must NOT register as land-creatures.
    avenger = {
        "name": "Avenger of Zendikar",
        "oracle_text": (
            "When Avenger of Zendikar enters, create a 0/1 green Plant creature "
            "token for each land you control."
        ),
    }
    keys = _keys(avenger)
    assert ("land_creatures_matter", "you") not in keys
    assert ("land_creatures_matter", "any") not in keys


def test_signal_carries_source_and_quote():
    card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    sig = next(s for s in extract_signals(card) if s.key == "creature_etb")
    assert sig.source == "ETB Boss"
    assert "creature you control enters" in sig.text.lower()


def test_aggregate_dedupes_across_records():
    a = {
        "name": "A",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    b = {
        "name": "B",
        "oracle_text": "Whenever a creature you control enters, gain 1 life.",
    }
    agg = aggregate_signals([a, b])
    etb = [s for s in agg if s.key == "creature_etb" and s.scope == "you"]
    assert len(etb) == 1  # deduped by (key, scope, subject)


def test_signal_is_hashable_frozen():
    s = Signal(key="x", scope="you", subject="", text="t", source="c")
    assert len({s, s}) == 1


# ── Reanimator payoff: "entered/cast from a graveyard" (Celes, Rune Knight) ──────
# The generic graveyard_matters lane is the FUEL (fill your yard / self-mill); a
# commander that rewards a creature ENTERING from a graveyard (reanimation) or being
# CAST from a graveyard (escape/disturb) is a reanimator PAYOFF — its own avenue.
CELES = {
    "name": "Celes, Rune Knight",
    "type_line": "Legendary Creature — Human Wizard Knight",
    "oracle_text": (
        "When Celes enters, discard any number of cards, then draw that many cards "
        "plus one.\n"
        "Whenever one or more other creatures you control enter, if one or more of them "
        "entered from a graveyard or was cast from a graveyard, put a +1/+1 counter on "
        "each creature you control."
    ),
    "color_identity": ["B", "R", "W"],
}


def test_reanimator_payoff_detected_for_celes():
    assert ("reanimator", "you") in _keys(CELES)


def test_reanimator_and_graveyard_fuel_both_fire_for_celes():
    keys = _keys(CELES)
    assert ("reanimator", "you") in keys  # the payoff (reanimation/cast-from-grave)
    assert ("graveyard_matters", "you") in keys  # the fuel (fill your own graveyard)


def test_reanimator_quotes_the_payoff_clause():
    sig = next(s for s in extract_signals(CELES) if s.key == "reanimator")
    assert sig.scope == "you"
    assert "from a graveyard" in sig.text.lower()


def test_reanimator_not_fired_by_regrowth_to_hand():
    # Returning a card to HAND is graveyard-return, not reanimation — no payoff trigger.
    card = {
        "name": "Regrowth",
        "oracle_text": "Return target card from your graveyard to your hand.",
    }
    assert ("reanimator", "you") not in _keys(card)


def test_reanimator_not_fired_by_plain_reanimation_spell():
    # A reanimation spell is an ENABLER (found by the avenue's search), not itself the
    # payoff trigger — its text says "to the battlefield", never "enters/cast from".
    card = {
        "name": "Animate Dead-like",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("reanimator", "you") not in _keys(card)


# ── Aristocrats: death-trigger doublers open the lane (the Teysa case) ───────────
# A commander that DOUBLES death triggers ("if a creature dying causes a triggered
# ability ... that ability triggers an additional time") is an aristocrats commander
# even though it never says "whenever ... dies". It must open the death lane so the
# drain payoffs (Blood Artist / Zulaport) surface.
def test_death_trigger_doubler_opens_aristocrats_lane():
    teysa = {
        "name": "Teysa Karlov",
        "oracle_text": (
            "If a creature dying causes a triggered ability of a permanent you control "
            "to trigger, that ability triggers an additional time.\n"
            "Creature tokens you control have vigilance and lifelink."
        ),
    }
    assert any(k == "death_matters" for k, _ in _keys(teysa))


def test_dies_in_passing_does_not_open_aristocrats():
    # A one-off non-death clause must NOT mint the aristocrats lane (no over-general).
    card = {
        "name": "Exiler",
        "oracle_text": "When this creature deals combat damage to a player, exile it.",
    }
    assert not any(k == "death_matters" for k, _ in _keys(card))


# ── Landfall: a land-recursion commander opens the lands lane (the Windgrace case) ─
# A commander whose payoff replays lands from the graveyard ("return … land cards from
# your graveyard to the battlefield") is a lands-matter commander and must open the
# landfall lane so its payoffs (Lotus Cobra / Scute Swarm) surface, even with no literal
# "landfall" / "play an additional land".
def test_land_recursion_commander_opens_landfall_lane():
    windgrace = {
        "name": "Lord Windgrace",
        "oracle_text": (
            "−3: Return up to two target land cards from your graveyard to the "
            "battlefield."
        ),
    }
    assert ("landfall", "you") in _keys(windgrace)
