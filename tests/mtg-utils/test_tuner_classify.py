"""Spine / Engine / Filler / land / commander classification (tuner substrate)."""

from mtg_utils._deck_forge.signals import rank_deck_signals
from mtg_utils._tuner.classify import classify_deck
from mtg_utils.hydrated_deck import HydratedDeck

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "oracle_text": (
        "{T}: Create a number of 1/1 red Goblin creature tokens equal to the number "
        "of Goblins you control."
    ),
    "cmc": 4.0,
    "color_identity": ["R"],
}
RABBLEMASTER = {
    "name": "Goblin Rabblemaster",
    "type_line": "Creature — Goblin Warrior",
    "oracle_text": (
        "At the beginning of combat on your turn, create a 1/1 red Goblin creature "
        "token with haste."
    ),
    "cmc": 3.0,
}
DUAL = {
    "name": "Beast Within With Tokens",
    "type_line": "Instant",
    "oracle_text": (
        "Destroy target permanent. Create a 1/1 red Goblin creature token."
    ),
    "cmc": 3.0,
}
RAMP_ROCK = {
    "name": "Mind Stone",
    "type_line": "Artifact",
    "oracle_text": "{T}: Add {C}.",
    "produced_mana": ["C"],
    "cmc": 2.0,
}
MURDER = {
    "name": "Murder",
    "type_line": "Instant",
    "oracle_text": "Destroy target creature.",
    "cmc": 3.0,
}
VANILLA = {
    "name": "Hill Giant",
    "type_line": "Creature — Giant",
    "oracle_text": "",
    "cmc": 4.0,
}
MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "oracle_text": "({T}: Add {R}.)",
    "cmc": 0.0,
}

_ALL = [KRENKO, RABBLEMASTER, DUAL, RAMP_ROCK, MURDER, VANILLA, MOUNTAIN]


def _classified():
    deck = {
        "format": "commander",
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": c["name"], "quantity": 1} for c in _ALL if c is not KRENKO],
    }
    index = {c["name"]: c for c in _ALL}
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    signals = rank_deck_signals(hd.records, {"Krenko, Mob Boss"})
    classes = classify_deck(hd, signals, {"Krenko, Mob Boss"})
    return {c.name: c for c in classes}


def test_buckets():
    by_name = _classified()
    assert by_name["Krenko, Mob Boss"].bucket == "commander"
    assert by_name["Mountain"].bucket == "land"
    assert by_name["Mind Stone"].bucket == "spine"  # ramp
    assert by_name["Murder"].bucket == "spine"  # interaction
    assert by_name["Hill Giant"].bucket == "filler"  # serves nothing


def test_engine_card_serves_an_avenue():
    by_name = _classified()
    rabble = by_name["Goblin Rabblemaster"]
    assert rabble.bucket == "engine"
    assert rabble.served  # serves the goblin/token avenue


def test_dual_purpose_spine_card():
    by_name = _classified()
    dual = by_name["Beast Within With Tokens"]
    assert dual.bucket == "spine"  # interaction wins the bucket
    assert dual.dual_purpose is True  # but it also feeds the token avenue
    assert dual.served
