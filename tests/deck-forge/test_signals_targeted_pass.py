"""Targeted-pass detectors: recover the generic-frame-buried-effect commanders the
exhaustive sweep left at zero signal (grammar-revisit workflow, 2026-06-06). Each is
a precise per-axis detector, NOT a grammar — and must not regress the rules-lawyer
audit's combat-vs-noncombat damage distinction.

Oracle text is verbatim from the residual (real Scryfall cards), per ADR-0009.
"""

from mtg_utils._deck_forge._signals_ir import extract_signals_ir
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Trigger
from mtg_utils.testkit import test_card, test_signals


def _sigs(oracle, name="X", **extra):
    card = {"name": name, "oracle_text": oracle, "type_line": "Legendary Creature"}
    card.update(extra)
    return extract_signals(card)


def _keys(oracle, **kw):
    return {s.key for s in _sigs(oracle, **kw)}


def _bare_ir() -> Card:
    """A minimal non-None Card IR — routes extract_signals_ir through the IR path
    so a kept-mirror-served migrated key (which scans the oracle directly) fires
    (ADR-0039 task #80 step 6: these synthetic fixtures have no real oracle_id, so
    they can never resolve a crosswalk tree)."""
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(oracle, name="X", **extra):
    """ADR-0027 v34: blink_flicker migrated — the regex path no longer emits it; the
    hybrid IR path serves it via the byte-identical kept mirror (which scans the oracle
    directly, so any non-None IR routes to it)."""
    card = {"name": name, "oracle_text": oracle, "type_line": "Legendary Creature"}
    card.update(extra)
    return {s.key for s in extract_signals_ir(card, _bare_ir())}


# ── 1. Blink / flicker: cross-sentence "Exile … . Return that card to the battlefield" ──
def test_roon_cross_sentence_flicker_fires():
    # Roon's "Exile another target creature. Return that card …" is the cross-sentence
    # flicker the targeted pass recovered; real card over real projected IR (#25).
    assert "blink_flicker" in {s.key for s in test_signals("Roon of the Hidden Realm")}


def test_inline_flicker_still_fires():
    assert "blink_flicker" in _keys_hybrid(
        "Exile target creature, then return it to the battlefield."
    )


def test_pure_exile_removal_is_not_flicker():
    # ADR-0027 v34: assert via the hybrid path (the migrated IR + kept mirror must drop
    # it, not just the now-silent regex path).
    assert "blink_flicker" not in _keys_hybrid("Exile target creature.")


def test_c13_narrowed_exile_mirror_drops_overfires():
    # ADR-0027 C13: the kept exile_removal mirror was narrowed from the broad SWEEP regex
    # to the E-bucket phase-parse-miss tail only. Over the bare-IR hybrid path (no
    # structured exile effect), the mirror must drop the over-fires it used to re-supply,
    # each re-homed to its correct lane. Real-card oracle text.
    # Genuine single-target battlefield exile → STILL fires (Banishing Light, Drach'Nyen).
    assert "exile_removal" in _keys_hybrid(
        "When this enchantment enters, exile target nonland permanent an "
        "opponent controls until this enchantment leaves the battlefield.",
        name="Banishing Light",
    )
    assert "exile_removal" in _keys_hybrid(
        "When Drach'Nyen enters, exile up to one target creature.",
        name="Drach'Nyen",
    )
    # BLINK self-own (CR 603.6e the object returns) → graveyard_matters/blink lanes, NOT
    # removal: held out by the RETURN + SELF_TARGET exclusions.
    assert "exile_removal" not in _keys_hybrid(
        "Exile target creature you control, then return that card to the "
        "battlefield under its owner's control.",
        name="Cloudshift-like",
    )
    # GY-source exile (CR 406.2 never touches the battlefield) → graveyard_matters: held
    # out by the from-zone exclusion AND the direct graveyard guard.
    assert "exile_removal" not in _keys_hybrid(
        "Exile target creature card from a graveyard.", name="Cemetery-Reaper-like"
    )
    assert "exile_removal" not in _keys_hybrid(
        "Exile target enchantment, instant, or sorcery card with equal or lesser "
        "mana value from an opponent's graveyard. Copy the exiled card.",
        name="Saruman-like",
    )
    # SUSPEND (CR 702.62a temporary) → suspend_matters: held out by the suspend exclusion.
    assert "exile_removal" not in _keys_hybrid(
        "Exile target creature with three time counters on it. Suspend.",
        name="Suspend-like",
    )


def test_reanimation_is_not_flicker():
    # the returned object is a graveyard card, not the exiled one — not a flicker.
    assert "blink_flicker" not in _keys_hybrid(
        "Exile target creature. Return target creature card "
        "from your graveyard to the battlefield."
    )


def test_oring_removal_is_not_flicker():
    # Fiend Hunter / Journey to Nowhere: exile + leaves-delayed "return the exiled
    # card" is removal, not a flicker engine.
    assert "blink_flicker" not in _keys_hybrid(
        "When this creature enters, you may exile another target creature. "
        "When this creature leaves the battlefield, return the exiled card "
        "to the battlefield."
    )


# ── 2. "Deals damage to an opponent" (any damage) — distinct from the combat axis ──
# ADR-0027 β: damage_to_opp_matters migrated regex→Card IR. The regex path NO LONGER
# emits it (the HAND_FLOOR producer is deleted); the lane fires from the hybrid IR path —
# a STRUCTURAL deals_damage trigger carrying project's DamageToPlayer recipient marker
# (Lu Xun's "deals damage to an opponent" → valid_target Typed/Opponent), with a byte-
# identical kept mirror covering the textual tail. opponent_discard (Zhang Liao) is a
# SEPARATE lane ALSO migrated to the IR (ADR-0027). All proven against real projected
# IR via the committed snapshot (#25).
def test_damage_to_opp_migrated_off_regex_onto_ir():
    # The regex path no longer emits it; the hybrid IR path does (structural marker).
    assert "damage_to_opp_matters" not in {
        s.key for s in extract_signals(test_card("Lu Xun, Scholar General"))
    }
    assert "damage_to_opp_matters" in {
        s.key for s in test_signals("Lu Xun, Scholar General")
    }


def test_lu_xun_damage_scope_is_opponents():
    sig = next(
        s
        for s in test_signals("Lu Xun, Scholar General")
        if s.key == "damage_to_opp_matters"
    )
    assert sig.scope == "opponents"


def test_zhang_liao_damage_and_discard():
    # ADR-0027: damage_to_opp_matters AND opponent_discard are both now IR-served. Zhang
    # Liao's "that opponent discards a card" fires opponent_discard from the hybrid path
    # (the byte-identical _OPPONENT_DISCARD_MIRROR kept-mirror over the oracle).
    hyb = {s.key for s in test_signals("Zhang Liao, Hero of Hefei")}
    assert "damage_to_opp_matters" in hyb
    assert "opponent_discard" in hyb


def test_noncombat_damage_does_not_fire_combat_axis():
    # rules-lawyer audit: combat keys require the literal word "combat". Lu Xun's
    # Horsemanship damage is the any-damage axis, NOT the combat axis.
    hyb = {s.key for s in test_signals("Lu Xun, Scholar General")}
    assert "combat_damage_matters" not in hyb
    assert "combat_damage_to_opp" not in hyb


def test_combat_damage_audit_preserved():
    # inverse: literal combat damage fires the combat axis, NOT the any-damage key.
    # ADR-0027 (SIDECAR v41): the combat lanes read the structured recipient; the bare
    # IR carries no combat trigger, so the player recipient is recovered from the folded
    # oracle ("deals combat damage to an opponent") via the supplement parser. The
    # any-damage key needs the structural DamageToPlayer marker (a bare deals_damage IR),
    # absent here, so it stays silent — and literal "combat damage" never carries it.
    card = {
        "name": "Foo",
        "oracle_text": "Whenever Foo deals combat damage to an opponent, draw a card.",
        "type_line": "Legendary Creature",
    }
    bare = Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))
    k = {s.key for s in extract_signals_ir(card, bare)}
    assert "combat_damage_matters" in k
    assert "damage_to_opp_matters" not in k


# ── 3. Tribal ETB: "a <subtype> you control enters" ──
def test_tribal_etb_captures_subject():
    # ADR-0027: type_matters migrated → hybrid path. Mary Jane Watson's "Whenever a
    # Spider you control enters" captures the Spider subject; real projected IR (#25).
    sigs = test_signals("Mary Jane Watson")
    assert any(s.key == "type_matters" and s.subject == "Spider" for s in sigs)


def test_tribal_etb_no_junk_subject_for_creature():
    # "a creature you control enters" is generic creature_etb, never a junk subject.
    sigs = _sigs("Whenever a creature you control enters, draw a card.")
    assert not any(s.key == "type_matters" for s in sigs)
    assert all(s.subject != "creature" for s in sigs)


# ── 4. permanent_etb value engine: "another permanent you control enters" ──
# ADR-0027: permanent_etb migrated to the Card IR (an `etb` Trigger with a Permanent-
# you-control subject), so it is served via extract_signals_hybrid, not the regex
# path. (The structural-IR proof — Amareth — also lives in test_migrated_keys.)
def test_permanent_etb_fires_for_amareth():
    # Amareth's "Whenever another permanent you control enters" is the generic permanent
    # value-engine axis; real card over real projected IR (#25).
    assert "permanent_etb" in {s.key for s in test_signals("Amareth, the Lustrous")}


def test_permanent_etb_scope_you():
    sig = next(
        s for s in test_signals("Amareth, the Lustrous") if s.key == "permanent_etb"
    )
    assert sig.scope == "you"


def test_creature_etb_does_not_fire_permanent_etb():
    # a creature-only ETB is creature_etb, not the generic permanent axis (the IR's
    # 'Creature'-subject etb trigger opens creature_etb, never permanent_etb).
    card = {
        "name": "X",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
        "type_line": "Legendary Creature",
    }
    ir = Card(
        oracle_id="y",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(
                            event="etb",
                            scope="you",
                            subject=Filter(card_types=("Creature",), controller="you"),
                        ),
                        effects=(Effect(category="draw", scope="you", raw="draw"),),
                    ),
                ),
            ),
        ),
    )
    assert "permanent_etb" not in {s.key for s in extract_signals_ir(card, ir)}


# ── new keys must have specs so the UI renders an avenue + serves() works ──
def test_new_keys_have_specs():
    for key, scope in (
        ("damage_to_opp_matters", "opponents"),
        ("permanent_etb", "you"),
    ):
        sig = Signal(key=key, scope=scope, subject="", text="", source="X")
        assert spec_for(sig) is not None, key
