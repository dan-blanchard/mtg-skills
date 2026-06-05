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
