"""Keyword re-audit (driving the agent toward 'rarely needed'):

1. Build-around KEYWORDS the extractor never read → direct keyword→signal map
   (Mentor/Training/… → counters; Battle cry/Battalion → go-wide; Exalted → voltron;
   Extort → drain; Amass → tokens). Each is rules-grounded (CR 702.x keyword defs).
2. KEYWORD-TRIBES: "Flying creatures you control …" / "creatures with deathtouch …"
   group creatures by a keyword characteristic (like subtype tribal, CR 109.3).
3. VOLTRON FALLBACK: a vanilla beater still has a deterministic plan — commander
   damage (CR 903.10a). When nothing else fires and the creature is voltron-viable
   (an evasion/resilience keyword or power ≥2), surface a low-confidence voltron avenue.
"""

from mtg_utils._deck_forge.signals import (
    coverage_gate,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Card, Face


def _sigs(name="X", oracle="", type_line="Legendary Creature — Test", **kw):
    card = {"name": name, "oracle_text": oracle, "type_line": type_line}
    card.update(kw)
    return extract_signals(card)


def _keys(**kw):
    return {s.key for s in _sigs(**kw)}


def _subjects(key, **kw):
    return {s.subject for s in _sigs(**kw) if s.key == key}


def _hybrid_subjects(key, name="X", oracle="", type_line="Enchantment", **kw):
    """Subjects from the HYBRID (IR) path. ADR-0027 migrated keyword_tribe to the
    Card IR as a subject-carrying kept mirror that reads the card's oracle_text, so a
    vanilla IR (the mirror reads the record, not the IR structure) is enough to run
    the IR path."""
    card = {"name": name, "oracle_text": oracle, "type_line": type_line}
    card.update(kw)
    ir = Card(oracle_id="x", name=name, faces=(Face(name=name),))
    return {s.subject for s in extract_signals_hybrid(card, ir) if s.key == key}


# ── 1. build-around keyword → signal ──
def _counter_keyword_ir(name: str):
    """The IR phase projects for a +1/+1-counter keyword (mentor/training/evolve …):
    a place_counter(p1p1) effect. ADR-0027 migrated plus_one_matters to the IR, so the
    keyword opens the lane STRUCTURALLY, not via the regex keyword path."""
    from mtg_utils._card_ir.project import project_card

    return project_card(
        [
            {
                "name": name,
                "card_type": {"core_types": ["Creature"]},
                "triggers": [
                    {
                        "mode": "Attacks",
                        "execute": {
                            "effect": {
                                "type": "PutCounter",
                                "counter_type": "P1P1",
                                "count": {"type": "Fixed", "value": 1},
                                "target": {"type": "Target"},
                            }
                        },
                    }
                ],
            }
        ]
    )


def test_mentor_is_counters():
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    card = {"name": "Mentor Lord", "type_line": "Creature", "keywords": ["Mentor"]}
    keys = {
        s.key for s in extract_signals_hybrid(card, _counter_keyword_ir("Mentor Lord"))
    }
    assert "plus_one_matters" in keys


def test_training_and_evolve_are_counters():
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    for kw in ("Training", "Evolve"):
        card = {"name": f"{kw} Lord", "type_line": "Creature", "keywords": [kw]}
        keys = {
            s.key
            for s in extract_signals_hybrid(card, _counter_keyword_ir(f"{kw} Lord"))
        }
        assert "plus_one_matters" in keys, kw


def test_battle_cry_is_go_wide_attack():
    # ADR-0027: attack_matters is migrated. Battle cry (CR 702.91) carries its "whenever
    # this creature attacks" trigger in stripped reminder text, so the lane fires from the
    # Battle cry keyword in _IR_KEYWORD_MAP via the hybrid — not the regex keyword path.
    from mtg_utils._deck_forge.signals import extract_signals_hybrid
    from mtg_utils.card_ir import Card, Face

    card = {
        "name": "X",
        "oracle_text": "",
        "type_line": "Legendary Creature — Test",
        "keywords": ["Battle cry"],
    }
    ir = Card(
        oracle_id="x", name="X", faces=(Face(name="X", keywords=("Battle cry",)),)
    )
    assert "attack_matters" not in {s.key for s in extract_signals(card)}
    assert "attack_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_exalted_is_voltron():
    assert "voltron_matters" in _keys(keywords=["Exalted"])


def test_extort_is_drain():
    # ADR-0027: lifeloss_matters is migrated. phase models Extort (CR 702.101) as a
    # structural `lose_life` ("each opponent loses 1 life"), so a real extort card
    # fires the lane from the IR — not the regex keyword path.
    from mtg_utils._card_ir.project import project_card
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    card = {
        "name": "Extort Lord",
        "type_line": "Legendary Creature — Test",
        "keywords": ["Extort"],
        "oracle_text": "Extort",
    }
    ir = project_card(
        [
            {
                "name": "Extort Lord",
                "card_type": {"core_types": ["Creature"]},
                "triggers": [
                    {
                        "mode": "SpellCast",
                        "execute": {
                            "effect": {
                                "type": "LoseLife",
                                "target": {"type": "EachOpponent"},
                                "count": {"type": "Fixed", "value": 1},
                            }
                        },
                    }
                ],
            }
        ]
    )
    sigs = extract_signals_hybrid(card, ir)
    assert any(s.key == "lifeloss_matters" and s.scope == "opponents" for s in sigs)


def test_amass_is_tokens():
    # ADR-0027: tokens_matter is migrated. Amass (CR 701.47) carries its Army-token
    # making in stripped reminder text, so the lane fires from the Amass keyword in
    # _IR_KEYWORD_MAP via the hybrid — not the regex keyword path (which was deleted).
    from mtg_utils._deck_forge.signals import extract_signals_hybrid
    from mtg_utils.card_ir import Card, Face

    card = {
        "name": "X",
        "oracle_text": "",
        "type_line": "Legendary Creature — Test",
        "keywords": ["Amass"],
    }
    ir = Card(oracle_id="x", name="X", faces=(Face(name="X", keywords=("Amass",)),))
    assert "tokens_matter" not in {s.key for s in extract_signals(card)}
    assert "tokens_matter" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_plain_flying_keyword_is_not_a_buildaround_signal():
    # Flying alone is not a build-around (it routes to the voltron fallback instead).
    k = _keys(
        keywords=["Flying"],
        type_line="Legendary Creature — Bird",
        power="2",
        toughness="2",
    )
    assert "plus_one_matters" not in k
    assert "attack_matters" not in k


# ── 2. keyword-tribes ── (ADR-0027: keyword_tribe migrated to the Card IR via a
# subject-carrying kept mirror; these assert against the HYBRID/IR path now.)
def test_flying_creatures_you_control_is_keyword_tribe():
    assert "Flying" in _hybrid_subjects(
        "keyword_tribe", oracle="Flying creatures you control get +1/+1."
    )


def test_creatures_with_deathtouch_is_keyword_tribe():
    assert "Deathtouch" in _hybrid_subjects(
        "keyword_tribe", oracle="All creatures with deathtouch gain wither."
    )


def test_subtype_is_not_a_keyword_tribe():
    # "Goblin creatures you control" is subtype tribal, not a keyword tribe.
    subs = _hybrid_subjects(
        "keyword_tribe", oracle="Other Goblin creatures you control get +1/+1."
    )
    assert "Goblin" not in subs


# ── 3. voltron fallback (commander damage) ──
def test_vanilla_beater_gets_voltron_fallback():
    # 10/10 flier with no build-around oracle → voltron avenue, low confidence.
    sigs = _sigs(
        name="Mechtitan",
        oracle="",
        type_line="Legendary Creature — Robot",
        keywords=["Flying", "Vigilance", "Trample"],
        power="10",
        toughness="10",
    )
    volt = [s for s in sigs if s.key == "voltron_matters"]
    assert volt
    assert volt[0].confidence == "low"


def test_small_vanilla_no_voltron():
    # A 1/1 themeless legend is below the commander-damage floor → nothing. (A 2/2
    # vanilla legend like Isamaru now DOES open voltron — the iconic cheap voltron
    # commander; see test_cheap_vanilla_legend_opens_voltron_fallback in test_signals.)
    assert "voltron_matters" not in _keys(
        oracle="", type_line="Legendary Creature — Dog", power="1", toughness="1"
    )


def test_voltron_fallback_suppressed_when_real_signal_exists():
    # a commander with a strong build-around must NOT also get the vanilla fallback.
    sigs = _sigs(
        oracle="Other Goblins you control get +1/+1.",
        type_line="Legendary Creature — Goblin",
        keywords=["Menace"],
        power="5",
        toughness="5",
    )
    assert "voltron_matters" not in {s.key for s in sigs}


def test_voltron_fallback_routes_low_confidence():
    c = {
        "name": "Marit Lage",
        "oracle_text": "Flying, indestructible",
        "type_line": "Token Legendary Creature — Avatar",
        "keywords": ["Flying", "Indestructible"],
        "power": "20",
        "toughness": "20",
    }
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "low_confidence"
