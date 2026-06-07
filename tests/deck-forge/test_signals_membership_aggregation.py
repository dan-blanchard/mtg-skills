"""Deck-level avenue aggregation must not flood: membership signals (own-subtype
tribal, voltron fallback — what a card *is*) come from the COMMANDER only, and the
avenues panel is ranked by support and capped. Otherwise every creature's race and
stat-line becomes a "X tribal / X payoffs" pair (the reported UI overload).
"""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.engine import _AVENUE_CAP
from mtg_utils._deck_forge.signals import extract_signals
from mtg_utils._deck_forge.state import DeckSession, ForgeState

VANILLA_ELF = {
    "name": "Plain Elf",
    "type_line": "Legendary Creature — Elf Warrior",
    "oracle_text": "",
    "power": "3",
    "toughness": "3",
}


# ── include_membership flag (signal level) ──
def test_membership_on_by_default():
    keys = {(s.key, s.subject) for s in extract_signals(VANILLA_ELF)}
    assert ("type_matters", "Elf") in keys


def test_membership_off_drops_own_subtype_and_voltron():
    sigs = extract_signals(VANILLA_ELF, include_membership=False)
    assert ("type_matters", "Elf") not in {(s.key, s.subject) for s in sigs}
    assert "voltron_matters" not in {s.key for s in sigs}


def test_membership_flag_does_not_touch_oracle_signals():
    # a real oracle payoff fires regardless of the flag.
    card = {
        "name": "Goblin Lord That Is An Elf",
        "type_line": "Legendary Creature — Elf",
        "oracle_text": "Other Goblins you control get +1/+1.",
    }
    off = {(s.key, s.subject) for s in extract_signals(card, include_membership=False)}
    assert ("type_matters", "Goblin") in off  # oracle Goblin payoff survives
    assert ("type_matters", "Elf") not in off  # own-subtype membership suppressed


# ── deck aggregation (the UI bug) ──
def _client(commander, deck_cards):
    idx = {c["name"]: c for c in (commander, *deck_cards)}
    session = DeckSession("commander")
    session.add(commander["name"], zone="commanders")
    for c in deck_cards:
        session.add(c["name"])
    state = ForgeState(
        by_name=idx, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    return TestClient(build_app(state))


def test_deckcard_races_do_not_flood_avenues():
    dragon = {
        "name": "Big Dragon",
        "type_line": "Legendary Creature — Dragon",
        "cmc": 6.0,
        "color_identity": ["R"],
        "oracle_text": "",
        "power": "6",
        "toughness": "6",
    }
    deck = [
        {
            "name": "Plain Elf",
            "type_line": "Creature — Elf",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
        },
        {
            "name": "Plain Merfolk",
            "type_line": "Creature — Merfolk",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
        },
        {
            "name": "Plain Ally",
            "type_line": "Creature — Kor Ally",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
        },
    ]
    avenues = _client(dragon, deck).get("/api/snapshot").json()["avenues"]
    labels = " | ".join(a["label"] for a in avenues)
    assert "Dragon" in labels  # the commander's own tribe still surfaces
    assert "Elf" not in labels  # deck-card races no longer flood
    assert "Merfolk" not in labels
    assert "Ally" not in labels


def test_avenues_capped_for_many_themes():
    cmd = {
        "name": "Cmdr",
        "type_line": "Legendary Creature — Human",
        "cmc": 3.0,
        "color_identity": ["B", "G", "R", "U", "W"],
        "oracle_text": "",
        "power": "3",
        "toughness": "3",
    }
    themes = [
        "Create a Treasure token.",
        "Destroy target creature.",
        "Exile target creature.",
        "Counter target spell.",
        "Search your library for a card.",
        "Each opponent loses 2 life.",
        "Whenever you gain 3 life, draw a card.",
        "Untap target permanent.",
        "Return target creature to its owner's hand.",
        "Gain control of target creature.",
        "Create a Food token.",
        "Whenever you scry or surveil, draw a card.",
        "Whenever you cast a spell, this deals 1 damage to an opponent.",
        "Create three 1/1 Soldier creature tokens.",
    ]
    deck = [
        {
            "name": f"C{i}",
            "type_line": "Sorcery",
            "cmc": 2.0,
            "color_identity": ["B"],
            "oracle_text": t,
        }
        for i, t in enumerate(themes)
    ]
    avenues = _client(cmd, deck).get("/api/snapshot").json()["avenues"]
    engine = [a for a in avenues if a["source"] == "engine"]
    # capped to the dominant themes (+ at most the trailing parent's sub-avenues).
    assert len(engine) <= _AVENUE_CAP + 3
