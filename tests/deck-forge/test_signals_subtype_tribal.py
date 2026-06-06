"""Own-subtype tribal: a creature's own creature type is a deterministic
characteristic (CR 109.3) that tribal cards key off (CR 205.3 / 702.38a) — so a
Giant commander is a viable Giants build even with no tribal *oracle* text. Verified
with rules-lawyer that subtype, not rules text, is the tribal anchor.

Marked LOW confidence (membership ≠ a tribal payoff) and gated to supported RACE
tribes — generic class types (Human/Soldier/Wizard) only matter with explicit oracle
support, which already fires a high-confidence type_matters.
"""

from mtg_utils._deck_forge.signals import coverage_gate, extract_signals


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
    sig = next(
        s
        for s in _sigs(
            "Goblin Lord",
            "Legendary Creature — Goblin",
            "Other Goblins you control get +1/+1.",
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
