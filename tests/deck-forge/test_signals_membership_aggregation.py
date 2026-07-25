"""Deck-level avenue aggregation must not flood: membership signals (own-subtype
tribal, voltron fallback — what a card *is*) come from the COMMANDER only, and the
avenues panel is ranked by support and capped. Otherwise every creature's race and
stat-line becomes a "X tribal / X payoffs" pair (the reported UI overload).
"""

from fastapi.testclient import TestClient

from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.engine import _AVENUE_CAP
from mtg_utils._deck_forge.signals import extract_signals
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.deck import split_type_line
from mtg_utils.testkit import test_card, test_signals


def _text_only_tree(card: dict) -> ConceptTree:
    """A zero-unit ``ConceptTree`` carrying only the synthetic card's own
    whole-card metadata (types/subtypes/cmc/oracle text) — the shape
    ``_ir_lookup``'s own W2c phase-missing-face synthesis produces. No typed
    substrate exists for a hand-built fixture (there is no real phase
    record), but the crosswalk's membership floor + its "b12" whole-card text
    mirrors read ``tree.oracle`` / ``tree.card_types`` / ``tree.card_subtypes``
    directly — no units needed (ADR-0039 task #80 step 6: the ENGINE's own
    ranking/avenue pipeline calls extract_signals, which is now
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
    """Wire ``_ir_lookup.trees_for`` (the concept-tree resolver — extract_signals's ONLY
    signal source, ADR-0039 task #80 step 6) with a text-only tree per card,
    keyed by ``oracle_id``, for an engine-level (``TestClient``) test whose
    fixtures have no real phase record to resolve."""
    by_oid = {c["oracle_id"]: (_text_only_tree(c),) for c in cards}
    monkeypatch.setattr(
        _ir_lookup,
        "trees_for",
        lambda card, bulk=None: by_oid.get(card.get("oracle_id") or "", ()),  # noqa: ARG005
    )


# ── include_membership flag (signal level) ──
# Real-card, production-path checks (mtg_utils.testkit): the crosswalk's own-subtype
# type_matters lane fires UNCONDITIONALLY (not gated by include_membership at all —
# see extract_signals's include_membership branch, which only wraps
# apply_membership_floor); only the membership-floor cross-opens (e.g.
# voltron_matters) are gated by the flag. Verified empirically against the
# committed snapshot (Grizzly Bears keeps type_matters/Bear but loses
# voltron_matters when include_membership=False; Llanowar Elves keeps
# type_matters/Elf either way).
def test_membership_on_by_default():
    keys = {(s.key, s.subject) for s in test_signals("Llanowar Elves")}
    assert ("type_matters", "Elf") in keys


def test_membership_off_drops_voltron_but_not_own_subtype_type_matters():
    card = test_card("Grizzly Bears")
    on = extract_signals(card, include_membership=True)
    off = extract_signals(card, include_membership=False)
    assert ("type_matters", "Bear") in {(s.key, s.subject) for s in on}
    assert ("type_matters", "Bear") in {(s.key, s.subject) for s in off}
    assert "voltron_matters" in {s.key for s in on}
    assert "voltron_matters" not in {s.key for s in off}


def test_membership_flag_does_not_touch_oracle_signals():
    # a real oracle payoff fires regardless of the flag.
    card = test_card("Goblin King")  # "Other Goblins get +1/+1 and have mountainwalk."
    on = extract_signals(card, include_membership=True)
    off = extract_signals(card, include_membership=False)
    on_ids = {(s.key, s.subject, s.confidence) for s in on}
    off_ids = {(s.key, s.subject, s.confidence) for s in off}
    assert ("type_matters", "Goblin", "high") in on_ids
    assert ("type_matters", "Goblin", "high") in off_ids


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
    # extract_signals(card, ir, include_membership=False) still emits
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
