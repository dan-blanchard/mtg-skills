"""Keyword re-audit (driving the agent toward 'rarely needed'):

1. Build-around KEYWORDS the extractor never read → direct keyword→signal map
   (Mentor/Training/… → counters; Exalted → voltron; Extort → drain) — each is
   rules-grounded (CR 702.x keyword defs) and proven against the real Card IR via
   ``mtg_utils.testkit`` (``test_signals`` runs the production hybrid extractor).
2. KEYWORD-TRIBES: "Flying creatures you control …" / "creatures with deathtouch …"
   group creatures by a keyword characteristic (like subtype tribal, CR 109.3).
3. VOLTRON FALLBACK: a vanilla beater still has a deterministic plan — commander
   damage (CR 903.10a). When nothing else fires and the creature is voltron-viable
   (an evasion/resilience keyword or power ≥2), surface a low-confidence voltron avenue.
"""


from mtg_utils._deck_forge.signals import coverage_gate
from mtg_utils.testkit import test_card, test_signals


def _keys(name):
    return {s.key for s in test_signals(name)}


# ── 1. build-around keyword → signal ──────────────────────────────────────────


def test_mentor_is_counters():
    # Wojek Bodyguard: a Mentor (CR 702.113) creature — the keyword's own
    # counter-placement trigger opens plus_one_makers.
    assert "plus_one_makers" in _keys("Wojek Bodyguard")


def test_training_is_counters():
    # Hopeful Initiate: a Training (CR 702.152) creature — the keyword's own
    # counter-placement trigger opens plus_one_makers.
    assert "plus_one_makers" in _keys("Hopeful Initiate")


def test_evolve_is_counters():
    # Adaptive Snapjaw: Evolve (CR 702.114) places a +1/+1 counter when a bigger
    # creature enters — opens plus_one_makers. Real card over the committed snapshot.
    assert "plus_one_makers" in _keys("Adaptive Snapjaw")


def test_extort_is_drain():
    # Crypt Ghast: Extort (CR 702.101) is a structural per-spell `lose_life`
    # scoped to each opponent — the _matters sweep (ADR-0034) routes a card that
    # CAUSES opponents to lose life to lifeloss_makers, scope opponents.
    keys = {(s.key, s.scope) for s in test_signals("Crypt Ghast")}
    assert ("lifeloss_makers", "opponents") in keys


def test_plain_flying_keyword_is_not_a_buildaround_signal():
    # Flying alone is not a build-around (it routes to the voltron fallback
    # instead, not the counters/attack-matters lanes). Sigarda, Host of Herons:
    # Flying + Hexproof, no counter/attack engine.
    keys = _keys("Sigarda, Host of Herons")
    assert "plus_one_matters" not in keys
    assert "attack_matters" not in keys


# ── 2. keyword-tribes ──────────────────────────────────────────────────────────
# keyword_tribe ("Flying creatures you control …" / subject-carrying keyword
# grouping) is already exhaustively proven — Sephara/Flying, Fynn/Deathtouch,
# Isperia/Flying, and the subtype-vs-keyword-tribe distinction (Goblin King,
# Whirlwind never fire) — by
# tests/mtg-utils/test_crosswalk.py::test_keyword_tribe_subject_carrying_mirror.
# No duplicate kept here.


# ── 3. voltron fallback (commander damage, CR 903.10a) ─────────────────────────
def test_vanilla_beater_gets_voltron_fallback():
    # Isamaru, Hound of Konda: the iconic vanilla 2/2 legend — commander damage
    # is the only plan, so the themeless-creature fallback opens voltron, low
    # confidence. Real card over the committed snapshot.
    sigs = test_signals("Isamaru, Hound of Konda")
    volt = [s for s in sigs if s.key == "voltron_matters"]
    assert volt
    assert volt[0].confidence == "low"


def test_small_vanilla_no_voltron():
    # Fblthp, Lost on the Range: a 1/1 legend whose only text is a card-selection
    # ability, well below the commander-damage floor — voltron never fires.
    assert "voltron_matters" not in _keys("Fblthp, Lost on the Range")


# NOTE: "engine commander suppresses the voltron fallback" (CR 903.10a
# has_other_plan) is proven below by
# test_engine_commander_with_other_plan_does_not_fire_voltron (Krenko, Mob
# Boss) — no separate synthetic-shape duplicate kept here.


def test_voltron_fallback_routes_low_confidence():
    # Isamaru's ENTIRE signal set is low-confidence (type_matters + the voltron
    # fallback, both low) — coverage_gate flags it for agent scoping.
    name = "Isamaru, Hound of Konda"
    needs, reason = coverage_gate(test_card(name), test_signals(name))
    assert needs is True
    assert reason == "low_confidence"


# ── 4. the six voltron tell families ────────────────────────────────────────────
# Each family is a structural tell from the web-validated Power / Evasion /
# Protection triad (+ Background / Partner); an engine commander with another
# plan does NOT fire. All real cards over the real projected IR (ADR-0027 /
# task #25), via mtg_utils.testkit.
def test_tell_self_combat_damage_growth_fires_voltron():
    # (1) self combat-damage growth loop — Mirri grows herself on combat damage.
    assert "voltron_matters" in _keys("Mirri the Cursed")


def test_tell_equipment_aura_payoff_fires_voltron():
    # (2) Equipment/Aura PAYOFF — the structural _detect_voltron_payoff_ir arm.
    # Sram's "cast an Aura, Equipment, or Vehicle → draw" is the canonical payoff.
    assert "voltron_matters" in _keys("Sram, Senior Edificer")


def test_tell_evasion_self_fires_voltron():
    # (3) evasion on self — a flier is a commander-damage threat (CR 903.10a).
    # Sigarda, Host of Herons: Flying (+ Hexproof), no other engine.
    assert "voltron_matters" in _keys("Sigarda, Host of Herons")


def test_tell_self_protection_fires_voltron():
    # (4) protection on self — an unkillable body is the ideal Equipment/Aura
    # carrier. Cho-Manno's "prevent all damage to Cho-Manno" is the self-
    # protection tell.
    assert "voltron_matters" in _keys("Cho-Manno, Revolutionary")


def test_tell_background_fires_voltron():
    # (5) Background — a "Choose a Background" beater is a vanilla voltron body
    # (the Background grants the suit-up package). partner_background is
    # voltron-compat.
    assert "voltron_matters" in _keys("Wilson, Refined Grizzly")


def test_tell_partner_fires_voltron():
    # (6) Partner — a Partner commander pairs with a second commander; the
    # keyword maps to partner_background, which is voltron-COMPAT (it does not
    # suppress the fallback). Ardenn is the real overlap: a Partner that ALSO
    # suits up (attach Auras/Equipment).
    keys = _keys("Ardenn, Intrepid Archaeologist")
    assert "partner_background" in keys  # the compat tell (does not suppress)
    assert "voltron_matters" in keys


def test_engine_commander_with_other_plan_does_not_fire_voltron():
    # An engine commander whose primary identity is a NON-COMBAT resource engine
    # (here a token engine — Krenko) has another plan, so the IR-derived
    # has_other_plan silences the commander-damage tell. CR 903.10a.
    keys = _keys("Krenko, Mob Boss")
    assert "token_maker" in keys  # the engine the IR detects
    assert "voltron_matters" not in keys
