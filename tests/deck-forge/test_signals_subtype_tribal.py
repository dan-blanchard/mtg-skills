"""Own-subtype tribal: a creature's own creature type is a deterministic
characteristic (CR 109.3) that tribal cards key off (CR 205.3 / 702.38a) — so a
Giant commander is a viable Giants build even with no tribal *oracle* text. Verified
with rules-lawyer that subtype, not rules text, is the tribal anchor.

Marked LOW confidence (membership ≠ a tribal payoff) and gated to supported RACE
tribes — generic class types (Human/Soldier/Wizard) only matter with explicit oracle
support, which already fires a high-confidence type_matters.
"""

from mtg_utils._deck_forge._signals_ir import extract_signals_ir
from mtg_utils._deck_forge.signals import (
    coverage_gate,
    extract_signals,
)
from mtg_utils.card_ir import Card, Face


def _bare_ir() -> Card:
    # A non-None IR routes the hybrid to the IR arm for ADR-0027 migrated keys whose
    # source reads the record's oracle_text via a kept mirror (e.g. typed_spellcast).
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _card(name, type_line, oracle=""):
    return {"name": name, "type_line": type_line, "oracle_text": oracle}


def _sigs(name, type_line, oracle=""):
    return extract_signals(_card(name, type_line, oracle))


def _subjects(name, type_line, oracle=""):
    return {
        s.subject for s in _sigs(name, type_line, oracle) if s.key == "type_matters"
    }


# ── race-tribe members are recovered from their subtype, no oracle needed ──
def test_giant_commander_gets_giant_tribal():
    assert "Giant" in _subjects("Bartel Runeaxe", "Legendary Creature — Giant Warrior")


def test_elder_dragon_gets_dragon_not_elder():
    subs = _subjects("Chromium", "Legendary Creature — Elder Dragon")
    assert "Dragon" in subs
    assert "Elder" not in subs  # Elder has no tribal support → excluded


def test_bird_knight_gets_both():
    subs = _subjects("Syr Cadian, Knight Owl", "Legendary Creature — Bird Knight")
    assert {"Bird", "Knight"} <= subs


# ── generic class types are NOT offered (avoid flooding every Human/Soldier) ──
def test_warrior_class_type_excluded():
    # Giant is offered, Warrior (a class) is not.
    subs = _subjects("Bartel Runeaxe", "Legendary Creature — Giant Warrior")
    assert "Warrior" not in subs


def test_human_soldier_gets_no_subtype_tribal():
    assert _subjects("General Jarkeld", "Legendary Creature — Human Soldier") == set()


def test_avatar_is_not_a_supported_tribe():
    assert _subjects("Autumn Willow", "Legendary Creature — Avatar") == set()


# ── non-creatures never emit creature-tribal ──
def test_noncreature_no_tribal():
    assert _subjects("Some Equipment", "Legendary Artifact — Equipment") == set()


# ── confidence: membership is LOW; an oracle payoff stays HIGH ──
def test_own_subtype_tribal_is_low_confidence():
    sig = next(
        s
        for s in _sigs("Bartel Runeaxe", "Legendary Creature — Giant Warrior")
        if s.key == "type_matters" and s.subject == "Giant"
    )
    assert sig.confidence == "low"


def test_oracle_payoff_stays_high_confidence():
    # a Goblin that also REWARDS Goblins: the oracle signal (high) must win the dedup.
    # ADR-0027: type_matters migrated → hybrid path.
    sig = next(
        s
        for s in extract_signals_ir(
            _card(
                "Goblin Lord",
                "Legendary Creature — Goblin",
                "Other Goblins you control get +1/+1.",
            ),
            _bare_ir(),
        )
        if s.key == "type_matters" and s.subject == "Goblin"
    )
    assert sig.confidence == "high"


# ── coverage gate: a bare race-member is surfaced but flagged for agent confirmation ──
def test_bare_tribe_member_routes_to_agent_low_confidence():
    c = _card("Bartel Runeaxe", "Legendary Creature — Giant Warrior")
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "low_confidence"


# ── precision gate: non-creature-type nouns must NEVER mint a tribal subject ──
# (Audit: 'the' (article), basic land types, and 'time' polluted CREATURE_SUBTYPES;
#  'the' alone served ~11,458 cards via its \bThes?\b serve. CR 205.3m: these are not
#  creature types — 'the' is an article, forest/island/mountain are basic LAND types
#  (CR 305.6), and the only two-word creature type is 'Time Lord', not bare 'Time'.)
def test_basic_land_type_is_not_a_creature_tribe():
    subs = _subjects(
        "Titania, Nature's Force",
        "Legendary Creature — Elemental",
        "Whenever a Forest you control enters, create a 5/3 green Elemental creature "
        "token.",
    )
    assert "Forest" not in subs


def test_check_land_reference_is_not_a_creature_tribe():
    subs = _subjects(
        "Sunpetal Grove",
        "Land",
        "Sunpetal Grove enters tapped unless you control a Plains or a Forest.",
    )
    assert "Forest" not in subs
    assert "Plains" not in subs


def test_article_is_not_a_typed_spellcast_subject():
    # Taigam: "exile the spell you cast …" captured 'the' → typed_spellcast subject='The'.
    # ADR-0027: typed_spellcast migrated to the IR (a kept mirror re-running the SAME
    # _detect_typed_spellcast producer + _resolve_subject vocab gate, which drops the
    # article), so assert against the HYBRID path to keep the guard meaningful.
    sigs = extract_signals_ir(
        _card(
            "Taigam, Master Opportunist",
            "Legendary Creature — Human Wizard",
            "Whenever you cast your second spell each turn, copy that spell. Then "
            "exile the spell you cast with four time counters on it.",
        ),
        _bare_ir(),
    )
    assert all(s.subject != "The" for s in sigs)


def test_time_counter_reference_is_not_a_creature_tribe():
    subs = _subjects(
        "TARDIS",
        "Legendary Artifact — Vehicle",
        "If you control a Time Lord, the next spell you cast this turn costs {3} less.",
    )
    assert "Time" not in subs


def test_real_tribe_still_minted_after_vocab_prune():
    # the prune must not remove a genuine creature tribe.
    assert "Goblin" in _subjects(
        "Goblin King",
        "Creature — Goblin",
        "Other Goblins you control get +1/+1 and have mountainwalk.",
    )
