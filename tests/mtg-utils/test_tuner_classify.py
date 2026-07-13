"""Spine / Engine / Filler / land / commander classification (tuner substrate)."""

from mtg_utils import testkit
from mtg_utils._deck_forge.signals import rank_deck_signals
from mtg_utils._tuner.classify import classify_deck
from mtg_utils.hydrated_deck import HydratedDeck

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "oracle_text": (
        "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control."
    ),
    "cmc": 4.0,
    "color_identity": ["R"],
}
RABBLEMASTER = {
    "name": "Goblin Rabblemaster",
    "type_line": "Creature — Goblin Warrior",
    "oracle_text": (
        "Other Goblin creatures you control attack each combat if able.\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token with haste.\nWhenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Goblin."
    ),
    "cmc": 3.0,
}
# DUAL and MURDER need a REAL, crosswalk-resolvable oracle_id: ``role_of``
# (budgets.py) buckets "interaction" via ``get_preset("removal").matches``,
# a structural (``signal_keys``) view since task #86 (the last regex-bearing
# built-in preset flip) — it never matches a synthetic no-oracle_id dict.
# DUAL is a real Goblin/Warrior creature ("Goblin Cratermaker") whose modal
# ability fires the bare ``removal`` key (probed via ``test_signals``: keys
# {"colorless_matters", "removal", "type_matters"}) — its OWN type-line
# membership (Goblin, Warrior) is what makes it serve the same "Goblin
# tribal" / "Warrior tribal" avenues Krenko's commander-derived signals
# open, so it's genuinely dual-purpose in THIS deck, not just a stand-in.
testkit.test_card_ir("Goblin Cratermaker")  # seeds the crosswalk trees memo
DUAL = testkit.test_card("Goblin Cratermaker")
RAMP_ROCK = {
    "name": "Mind Stone",
    "type_line": "Artifact",
    "oracle_text": "{T}: Add {C}.\n{1}, {T}, Sacrifice this artifact: Draw a card.",
    "produced_mana": ["C"],
    "cmc": 2.0,
}
testkit.test_card_ir("Murder")  # seeds the crosswalk trees memo
MURDER = testkit.test_card("Murder")
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
    dual = by_name["Goblin Cratermaker"]
    assert dual.bucket == "spine"  # interaction wins the bucket
    assert dual.dual_purpose is True  # but it also feeds the Goblin/Warrior avenue
    assert dual.served


def test_serving_protection_card_buckets_spine_not_engine():
    # classify checked `served` before `protects`, so a protection card that ALSO serves
    # an avenue (Heroic Intervention serves the "Grant protection" lane) bucketed engine
    # — and the stranded-cut pass then cut it WHILE the scorecard flagged the deck
    # protection-short. Protection must outrank generic avenue-serving (classify
    # docstring: "protection is conditional Spine (Tier-2), never filler").
    from mtg_utils._deck_forge.signals import Signal

    heroic = {
        "name": "Heroic Intervention",
        "type_line": "Instant",
        "oracle_text": "Permanents you control gain hexproof and indestructible until "
        "end of turn.",
        "cmc": 2.0,
    }
    deck = {
        "format": "commander",
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [{"name": "Heroic Intervention", "quantity": 1}],
    }
    index = {KRENKO["name"]: KRENKO, heroic["name"]: heroic}
    hd = HydratedDeck.from_parsed(deck, by_name=index)
    # Synthetic active signal so the grant-protection lane is served without needing the
    # IR sidecar (the activation gate is exercised elsewhere; here we test bucket order).
    sigs = [
        Signal(key="protection_grant", scope="you", subject="", text="", source="x")
    ]
    classes = {c.name: c for c in classify_deck(hd, sigs, {"Krenko, Mob Boss"})}
    hi = classes["Heroic Intervention"]
    assert hi.served  # it does serve the grant-protection lane
    assert hi.bucket == "spine"  # but protection outranks engine
    assert hi.dual_purpose is True
