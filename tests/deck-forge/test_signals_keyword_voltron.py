"""Keyword re-audit (driving the agent toward 'rarely needed'):

1. Build-around KEYWORDS the extractor never read → direct keyword→signal map
   (Mentor/Training/… → counters; Battle cry/Battalion → go-wide; Exalted → voltron;
   Extort → drain; Amass → tokens). Each is rules-grounded (CR 702.x keyword defs).
2. KEYWORD-TRIBES: "Flying creatures you control …" / "creatures with deathtouch …"
   group creatures by a keyword characteristic (like subtype tribal, CR 109.3).
3. VOLTRON FALLBACK: a vanilla beater still has a deterministic plan — commander
   damage (CR 903.10a). When nothing else fires and the creature is voltron-viable
   (evasion keyword or power ≥4), surface a low-confidence voltron avenue.
"""

from mtg_utils._deck_forge.signals import coverage_gate, extract_signals


def _sigs(name="X", oracle="", type_line="Legendary Creature — Test", **kw):
    card = {"name": name, "oracle_text": oracle, "type_line": type_line}
    card.update(kw)
    return extract_signals(card)


def _keys(**kw):
    return {s.key for s in _sigs(**kw)}


def _subjects(key, **kw):
    return {s.subject for s in _sigs(**kw) if s.key == key}


# ── 1. build-around keyword → signal ──
def test_mentor_is_counters():
    assert "counters_matter" in _keys(keywords=["Mentor"])


def test_training_and_evolve_are_counters():
    assert "counters_matter" in _keys(keywords=["Training"])
    assert "counters_matter" in _keys(keywords=["Evolve"])


def test_battle_cry_is_go_wide_attack():
    assert "attack_matters" in _keys(keywords=["Battle cry"])


def test_exalted_is_voltron():
    assert "voltron_matters" in _keys(keywords=["Exalted"])


def test_extort_is_drain():
    sigs = _sigs(keywords=["Extort"])
    assert any(s.key == "lifeloss_matters" and s.scope == "opponents" for s in sigs)


def test_amass_is_tokens():
    assert "tokens_matter" in _keys(keywords=["Amass"])


def test_plain_flying_keyword_is_not_a_buildaround_signal():
    # Flying alone is not a build-around (it routes to the voltron fallback instead).
    k = _keys(
        keywords=["Flying"],
        type_line="Legendary Creature — Bird",
        power="2",
        toughness="2",
    )
    assert "counters_matter" not in k
    assert "attack_matters" not in k


# ── 2. keyword-tribes ──
def test_flying_creatures_you_control_is_keyword_tribe():
    assert "Flying" in _subjects(
        "keyword_tribe", oracle="Flying creatures you control get +1/+1."
    )


def test_creatures_with_deathtouch_is_keyword_tribe():
    assert "Deathtouch" in _subjects(
        "keyword_tribe", oracle="All creatures with deathtouch gain wither."
    )


def test_subtype_is_not_a_keyword_tribe():
    # "Goblin creatures you control" is subtype tribal, not a keyword tribe.
    subs = _subjects(
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
    # 2/2 with no evasion and no abilities → genuinely nothing (not even voltron).
    assert "voltron_matters" not in _keys(
        oracle="", type_line="Legendary Creature — Dog", power="2", toughness="2"
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
        "oracle_text": "",
        "type_line": "Legendary Creature — Avatar",
        "keywords": ["Flying", "Indestructible"],
        "power": "20",
        "toughness": "20",
    }
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "low_confidence"
