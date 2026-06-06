"""Targeted-pass detectors: recover the generic-frame-buried-effect commanders the
exhaustive sweep left at zero signal (grammar-revisit workflow, 2026-06-06). Each is
a precise per-axis detector, NOT a grammar — and must not regress the rules-lawyer
audit's combat-vs-noncombat damage distinction.

Oracle text is verbatim from the residual (real Scryfall cards), per ADR-0009.
"""

from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import Signal, extract_signals


def _sigs(oracle, name="X", **extra):
    card = {"name": name, "oracle_text": oracle, "type_line": "Legendary Creature"}
    card.update(extra)
    return extract_signals(card)


def _keys(oracle, **kw):
    return {s.key for s in _sigs(oracle, **kw)}


# ── 1. Blink / flicker: cross-sentence "Exile … . Return that card to the battlefield" ──
ROON = (
    "Vigilance, trample\n"
    "{2}, {T}: Exile another target creature. Return that card to the battlefield "
    "under its owner's control at the beginning of the next end step."
)


def test_roon_cross_sentence_flicker_fires():
    assert "blink_flicker" in _keys(ROON, name="Roon of the Hidden Realm")


def test_inline_flicker_still_fires():
    assert "blink_flicker" in _keys(
        "Exile target creature, then return it to the battlefield."
    )


def test_pure_exile_removal_is_not_flicker():
    assert "blink_flicker" not in _keys("Exile target creature.")


def test_reanimation_is_not_flicker():
    # the returned object is a graveyard card, not the exiled one — not a flicker.
    assert "blink_flicker" not in _keys(
        "Exile target creature. Return target creature card "
        "from your graveyard to the battlefield."
    )


def test_oring_removal_is_not_flicker():
    # Fiend Hunter / Journey to Nowhere: exile + leaves-delayed "return the exiled
    # card" is removal, not a flicker engine.
    assert "blink_flicker" not in _keys(
        "When this creature enters, you may exile another target creature. "
        "When this creature leaves the battlefield, return the exiled card "
        "to the battlefield."
    )


# ── 2. "Deals damage to an opponent" (any damage) — distinct from the combat axis ──
LU_XUN = (
    "Horsemanship\nWhenever Lu Xun deals damage to an opponent, you may draw a card."
)
ZHANG = (
    "Whenever Zhang Liao deals damage to an opponent, that opponent discards a card."
)


def test_damage_to_opp_fires_for_lu_xun():
    assert "damage_to_opp_matters" in _keys(LU_XUN, name="Lu Xun")


def test_lu_xun_damage_scope_is_opponents():
    sig = next(
        s for s in _sigs(LU_XUN, name="Lu Xun") if s.key == "damage_to_opp_matters"
    )
    assert sig.scope == "opponents"


def test_zhang_liao_damage_and_discard():
    k = _keys(ZHANG, name="Zhang Liao")
    assert "damage_to_opp_matters" in k
    assert "opponent_discard" in k


def test_noncombat_damage_does_not_fire_combat_axis():
    # rules-lawyer audit: combat keys require the literal word "combat".
    k = _keys(LU_XUN, name="Lu Xun")
    assert "combat_damage_matters" not in k
    assert "combat_damage_to_opp" not in k


def test_combat_damage_audit_preserved():
    # inverse: literal combat damage fires the combat axis, NOT the any-damage key.
    k = _keys("Whenever Foo deals combat damage to an opponent, draw a card.")
    assert "combat_damage_matters" in k
    assert "damage_to_opp_matters" not in k


# ── 3. Tribal ETB: "a <subtype> you control enters" ──
def test_tribal_etb_captures_subject():
    sigs = _sigs(
        "Whenever a Spider you control enters, draw a card.", name="Mary Jane Watson"
    )
    assert any(s.key == "type_matters" and s.subject == "Spider" for s in sigs)


def test_tribal_etb_no_junk_subject_for_creature():
    # "a creature you control enters" is generic creature_etb, never a junk subject.
    sigs = _sigs("Whenever a creature you control enters, draw a card.")
    assert not any(s.key == "type_matters" for s in sigs)
    assert all(s.subject != "creature" for s in sigs)


# ── 4. permanent_etb value engine: "another permanent you control enters" ──
AMARETH = (
    "Flying\n"
    "Whenever another permanent you control enters, look at the top card of your "
    "library. If it shares a card type with that permanent, you may reveal that card "
    "and put it into your hand."
)


def test_permanent_etb_fires_for_amareth():
    assert "permanent_etb" in _keys(AMARETH, name="Amareth, the Lustrous")


def test_permanent_etb_scope_you():
    sig = next(s for s in _sigs(AMARETH, name="Amareth") if s.key == "permanent_etb")
    assert sig.scope == "you"


def test_creature_etb_does_not_fire_permanent_etb():
    # a creature-only ETB is creature_etb, not the generic permanent axis.
    assert "permanent_etb" not in _keys(
        "Whenever a creature you control enters, draw a card."
    )


# ── new keys must have specs so the UI renders an avenue + serves() works ──
def test_new_keys_have_specs():
    for key, scope in (
        ("damage_to_opp_matters", "opponents"),
        ("permanent_etb", "you"),
    ):
        sig = Signal(key=key, scope=scope, subject="", text="", source="X")
        assert spec_for(sig) is not None, key
