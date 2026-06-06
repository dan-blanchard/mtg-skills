"""Tests for signal specs: how a signal maps to cards that FEED it.

Headline guard: a card that feeds an *opponents'-graveyard* signal must mill
opponents, not yourself. Self-mill must NOT register as serving it.
"""

from mtg_utils._deck_forge.signal_specs import search_filters, serves, spec_for
from mtg_utils._deck_forge.signals import Signal


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


SELF_MILL = {
    "name": "Self Mill",
    "oracle_text": "Put the top four cards of your library into your graveyard.",
}
OPPONENT_MILL = {
    "name": "Mind Grind",
    "oracle_text": "Each opponent mills four cards.",
}
TOKEN_MAKER = {
    "name": "Token Maker",
    "oracle_text": "Create three 1/1 white Soldier creature tokens.",
}
BURN = {"name": "Bolt", "oracle_text": "Bolt deals 3 damage to any target."}
LIFEGAIN = {"name": "Healer", "oracle_text": "You gain 4 life."}


def test_opponents_graveyard_signal_served_by_opponent_mill_not_self_mill():
    sig = _sig("graveyard_matters", "opponents")
    assert serves(OPPONENT_MILL, sig) is True
    assert serves(SELF_MILL, sig) is False


def test_your_graveyard_signal_served_by_self_mill():
    sig = _sig("graveyard_matters", "you")
    assert serves(SELF_MILL, sig) is True


def test_creature_etb_served_by_token_maker_not_burn():
    sig = _sig("creature_etb", "you")
    assert serves(TOKEN_MAKER, sig) is True
    assert serves(BURN, sig) is False


def test_lifegain_served_by_lifegain_card():
    assert serves(LIFEGAIN, _sig("lifegain_matters", "you")) is True


def test_spec_for_returns_label_and_avenue():
    spec = spec_for(_sig("creature_etb", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue


def test_search_filters_inject_color_identity_and_format():
    filters = search_filters(
        _sig("creature_etb", "you"), color_identity="GW", fmt="commander"
    )
    assert filters["color_identity"] == "GW"
    assert filters["format"] == "commander"
    # carries the spec's discriminating filter (oracle and/or presets)
    assert "oracle" in filters or "preset_names" in filters


def test_unknown_signal_has_no_spec_and_serves_false():
    sig = _sig("totally_unknown_signal", "you")
    assert spec_for(sig) is None
    assert serves(TOKEN_MAKER, sig) is False


# --- land-creatures theme (the Jyoti case) -------------------------------------

LAND_CREATURE_PAYOFF = {
    "name": "Sylvan Advocate",
    "type_line": "Creature — Elf Druid Ally",
    "oracle_text": (
        "Vigilance\nAs long as you control six or more lands, this creature "
        "and land creatures you control get +2/+2."
    ),
}
PLANT_MAKER = {
    "name": "Avenger of Zendikar",
    "type_line": "Creature — Elemental",
    "oracle_text": (
        "When Avenger of Zendikar enters, create a 0/1 green Plant creature "
        "token for each land you control."
    ),
}
CLONE = {
    "name": "Silent Hallcreeper",
    "type_line": "Enchantment Creature — Horror",
    "oracle_text": "This creature becomes a copy of another target creature.",
}
MANLAND = {
    "name": "Mishra's Factory",
    "type_line": "Land",
    "oracle_text": (
        "{T}: Add {C}.\n{1}: Mishra's Factory becomes a 2/2 Assembly-Worker "
        "artifact creature until end of turn. It's still a land."
    ),
}


def test_land_creatures_spec_exists_with_extra_avenues():
    spec = spec_for(_sig("land_creatures_matter", "you"))
    assert spec is not None
    assert spec.label
    assert spec.avenue
    # The engine offers multiple precise sub-avenues, not one generic search.
    assert spec.extras


def test_land_creatures_serve_is_precise():
    sig = _sig("land_creatures_matter", "you")
    assert serves(LAND_CREATURE_PAYOFF, sig) is True  # references "land creatures"
    assert serves(PLANT_MAKER, sig) is False  # Plant tokens aren't land creatures
    assert serves(CLONE, sig) is False  # a clone is not a land creature


def _avenue_dicts(spec):
    """Engine avenue dicts (main + extras), as build_app emits them."""
    out = [{"label": spec.label, "search": dict(spec.search)}]
    out += [{"label": sa.label, "search": dict(sa.search)} for sa in spec.extras]
    return out


def _sig_sub(key, subject, scope="you"):
    return Signal(key=key, scope=scope, subject=subject, text="", source="cmd")


def test_subject_spec_built_for_tribal_signal():
    spec = spec_for(_sig_sub("type_matters", "Goblin"))
    assert spec is not None
    assert "Goblin" in spec.label
    assert spec.search.get("card_type") == "Goblin"


def test_subject_spec_serve_matches_subject_reference():
    sig = _sig_sub("type_matters", "Goblin")
    lord = {
        "oracle_text": "Other Goblins you control get +1/+1.",
        "type_line": "Creature — Goblin",
    }
    off = {"oracle_text": "Draw a card.", "type_line": "Sorcery"}
    assert serves(lord, sig) is True
    assert serves(off, sig) is False


def test_token_maker_subject_spec_and_generic_fallback():
    sub = spec_for(_sig_sub("token_maker", "Construct"))
    assert sub is not None
    assert "Construct" in sub.label
    assert sub.search.get("card_type") == "Construct"
    generic = spec_for(_sig_sub("token_maker", ""))  # no subject → static spec
    assert generic is not None
    assert "oracle" in generic.search


def test_all_new_floor_keys_have_specs():
    new_keys = [
        ("treasure_matters", "you"),
        ("artifacts_matter", "you"),
        ("enchantments_matter", "you"),
        ("tokens_matter", "you"),
        ("stax_taxes", "opponents"),
        ("blink_flicker", "you"),
        ("mill_matters", "any"),
        ("goad_matters", "opponents"),
        ("proliferate_matters", "you"),
        ("magecraft_matters", "you"),
        ("extra_combats", "you"),
        ("extra_turns", "you"),
    ]
    for key, scope in new_keys:
        spec = spec_for(_sig_sub(key, "", scope))
        assert spec is not None, key
        assert spec.label, key
        assert spec.search, key


def test_search_filters_for_subject_signal_inject_identity():
    filters = search_filters(
        _sig_sub("type_matters", "Goblin"), color_identity="R", fmt="commander"
    )
    assert filters["card_type"] == "Goblin"
    assert filters["color_identity"] == "R"
    assert filters["format"] == "commander"


def test_land_creature_avenue_searches_exclude_false_positives():
    """The exact bug class the user hit: a Plant-token maker and a clone must not
    be surfaced by ANY land-creature avenue, while a real creature-land is."""
    from mtg_utils._deck_forge.ranking import score_candidate

    avenues = _avenue_dicts(spec_for(_sig("land_creatures_matter", "you")))

    def served(card):
        return set(score_candidate(card, active_signals=[], avenues=avenues)["served"])

    assert served(MANLAND)  # a real creature-land is surfaced by some avenue
    assert not served(PLANT_MAKER)  # Avenger's Plant tokens — surfaced by none
    assert not served(CLONE)  # Silent Hallcreeper clone — surfaced by none
