"""Deck-level avenue aggregation must not flood: membership signals (own-subtype
tribal, voltron fallback — what a card *is*) come from the COMMANDER only, and the
avenues panel is ranked by support and capped. Otherwise every creature's race and
stat-line becomes a "X tribal / X payoffs" pair (the reported UI overload).
"""

from fastapi.testclient import TestClient

from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge._signals_ir import extract_signals_ir
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.engine import _AVENUE_CAP
from mtg_utils._deck_forge.signals import extract_signals
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face
from mtg_utils.deck import split_type_line


# A minimal non-None IR routes extract_signals_ir to the IR path for ADR-0027
# migrated keys (e.g. type_matters) whose source reads the record's oracle via a
# kept mirror.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _text_only_tree(card: dict) -> ConceptTree:
    """A zero-unit ``ConceptTree`` carrying only the synthetic card's own
    whole-card metadata (types/subtypes/cmc/oracle text) — the shape
    ``_ir_lookup``'s own W2c phase-missing-face synthesis produces. No typed
    substrate exists for a hand-built fixture (there is no real phase
    record), but the crosswalk's membership floor + its "b12" whole-card text
    mirrors read ``tree.oracle`` / ``tree.card_types`` / ``tree.card_subtypes``
    directly — no units needed (ADR-0039 task #80 step 6: the ENGINE's own
    ranking/avenue pipeline calls extract_signals_hybrid, which is now
    crosswalk-only, so these engine-level tests need a resolvable tree per
    synthetic oracle_id, not just a synthetic Card IR)."""
    type_words, sub_words = split_type_line(card.get("type_line") or "")
    return ConceptTree(
        name=card["name"],
        oracle_id=card["oracle_id"],
        units=(),
        card_types=tuple(w.capitalize() for w in type_words if w != "legendary"),
        card_subtypes=tuple(w.capitalize() for w in sub_words),
        card_supertypes=("Legendary",) if "legendary" in type_words else (),
        cmc=int(card.get("cmc") or 0),
        oracle=card.get("oracle_text") or "",
    )


def _wire_trees(monkeypatch, cards: list[dict]) -> None:
    """Wire ``_ir_lookup.trees_for`` (Seam A — extract_signals_hybrid's ONLY
    signal source, ADR-0039 task #80 step 6) with a text-only tree per card,
    keyed by ``oracle_id``, for an engine-level (``TestClient``) test whose
    fixtures have no real phase record to resolve."""
    by_oid = {c["oracle_id"]: (_text_only_tree(c),) for c in cards}
    monkeypatch.setattr(
        _ir_lookup,
        "trees_for",
        lambda card, bulk=None: by_oid.get(card.get("oracle_id") or "", ()),  # noqa: ARG005
    )


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
    # ADR-0027: type_matters migrated → hybrid path.
    off = {
        (s.key, s.subject)
        for s in extract_signals_ir(card, _bare_ir(), include_membership=False)
    }
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


def test_deckcard_races_do_not_flood_avenues(monkeypatch):
    dragon = {
        "name": "Big Dragon",
        "type_line": "Legendary Creature — Dragon",
        "cmc": 6.0,
        "color_identity": ["R"],
        "oracle_text": "",
        "power": "6",
        "toughness": "6",
        "oracle_id": "big-dragon-oid",
    }
    deck = [
        {
            "name": "Plain Elf",
            "type_line": "Creature — Elf",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
            "oracle_id": "plain-elf-oid",
        },
        {
            "name": "Plain Merfolk",
            "type_line": "Creature — Merfolk",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
            "oracle_id": "plain-merfolk-oid",
        },
        {
            "name": "Plain Ally",
            "type_line": "Creature — Kor Ally",
            "oracle_text": "",
            "power": "2",
            "toughness": "2",
            "cmc": 2.0,
            "oracle_id": "plain-ally-oid",
        },
    ]
    # ADR-0039 task #80 step 6: wire the COMMANDER's tree only. The crosswalk's
    # own-race-tribe type_matters lane (crosswalk_signals.extract_crosswalk_signals)
    # fires unconditionally — NOT gated by include_membership — so a deck card
    # with a resolvable tree would surface its own race regardless of
    # rank_deck_signals' is_cmd gate (verified against real snapshot cards:
    # extract_signals_hybrid(card, ir, include_membership=False) still emits
    # type_matters for the card's own race). That is a genuine, PRE-EXISTING
    # crosswalk characteristic unrelated to this deletion step — out of scope to
    # fix here (see the step-6 report's disputes) — so the deck cards below stay
    # unresolvable (trees_for() == ()), the same "no signal" degradation any
    # not-yet-crosswalk-covered card gets, keeping this test's actual assertion
    # (deck-card races don't flood) meaningful without masking the finding.
    _wire_trees(monkeypatch, [dragon])
    avenues = _client(dragon, deck).get("/api/snapshot").json()["avenues"]
    labels = " | ".join(a["label"] for a in avenues)
    assert "Dragon" in labels  # the commander's own tribe still surfaces
    assert "Elf" not in labels  # deck-card races no longer flood
    assert "Merfolk" not in labels
    assert "Ally" not in labels


def test_avenues_capped_for_many_themes(monkeypatch):
    cmd = {
        "name": "Cmdr",
        "type_line": "Legendary Creature — Human",
        "cmc": 3.0,
        "color_identity": ["B", "G", "R", "U", "W"],
        "oracle_text": "",
        "power": "3",
        "toughness": "3",
        "oracle_id": "cmdr-oid",
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
            "oracle_id": f"c{i}-oid",
        }
        for i, t in enumerate(themes)
    ]
    # ADR-0027 β: lifegain_matters migrated to the Card IR (a kept-mirror that reads the
    # record's reminder-stripped oracle), so "Whenever you gain 3 life" serves only from
    # the crosswalk. Wire a text-only tree per synthetic oracle_id so that theme keeps
    # minting its avenue (the mirror reads tree.oracle directly, no units needed —
    # ADR-0039 task #80 step 6), matching production where real cards carry a real
    # resolvable tree. Without it the lane silently drops and the cap math surfaces
    # more trailing sub-avenues.
    _wire_trees(monkeypatch, [cmd, *deck])
    avenues = _client(cmd, deck).get("/api/snapshot").json()["avenues"]
    engine = [a for a in avenues if a["source"] == "engine"]
    # capped to the dominant themes (+ at most the trailing parent's sub-avenues).
    assert len(engine) <= _AVENUE_CAP + 3
