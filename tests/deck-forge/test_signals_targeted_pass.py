"""Targeted-pass detectors: recover the generic-frame-buried-effect commanders the
exhaustive sweep left at zero signal (grammar-revisit workflow, 2026-06-06). Each is
a precise per-axis detector, NOT a grammar — and must not regress the rules-lawyer
audit's combat-vs-noncombat damage distinction.

Every extraction assertion runs the production ``extract_signals`` over a
real card from the committed snapshot (``mtg_utils.testkit``) — a synthetic no-
``oracle_id`` dict can no longer reach the crosswalk at all post-ADR-0039, so the
old inline-oracle-text fixtures here are replaced by real cards carrying the same
shape. Bare key-membership for these keys is already proven by
``tests/deck-forge/test_signal_keys_real_cards.py``'s ``_REAL_CASES`` table; tests
kept here assert something beyond that — a scope, an exclusion, or several
exclusions bundled per axis — using a different representative card wherever one
is available, so the two files' regression coverage stays independent.
"""

import pytest

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_signals


# ── 1. Blink / flicker: cross-sentence "Exile … . Return that card to the battlefield" ──
def test_roon_cross_sentence_flicker_fires():
    # Roon's "Exile another target creature. Return that card …" is the cross-sentence
    # flicker the targeted pass recovered.
    assert "blink_flicker" in {s.key for s in test_signals("Roon of the Hidden Realm")}


def test_inline_flicker_still_fires():
    # Ephemerate — "Exile target creature you control, then return it to the
    # battlefield …" is the inline (same-sentence) flicker shape.
    assert "blink_flicker" in {s.key for s in test_signals("Ephemerate")}


def test_pure_exile_removal_is_not_flicker():
    # Path to Exile — pure exile removal, no return clause at all.
    assert "blink_flicker" not in {s.key for s in test_signals("Path to Exile")}


def test_exile_removal_axis_and_its_exclusions():
    # Genuine battlefield exile removal → exile_removal fires (Banishing Light,
    # Path to Exile).
    assert "exile_removal" in {s.key for s in test_signals("Banishing Light")}
    assert "exile_removal" in {s.key for s in test_signals("Path to Exile")}
    # BLINK self-own (CR 603.6e the object returns) → the blink/graveyard lanes, NOT
    # removal: Ephemerate's self-target exile+return is held out by the
    # RETURN + SELF_TARGET exclusions.
    assert "exile_removal" not in {s.key for s in test_signals("Ephemerate")}
    # GY-source exile (CR 406.2 never touches the battlefield) → held out by the
    # from-zone exclusion: The Scarab God's "Exile target creature card from a
    # graveyard" never reads as battlefield removal.
    assert "exile_removal" not in {s.key for s in test_signals("The Scarab God")}
    # (the SUSPEND exclusion — a temporary exile with time counters is not
    # removal — is covered by suspend_matters's own cases in
    # test_keyword_gaps.py / test_signal_specs.py; no snapshot-resident card
    # combines "exile target creature" with Suspend to re-prove it here.)


def test_oring_removal_is_not_flicker():
    # Oblivion Ring: exile + leaves-delayed "return the exiled card" is removal, not
    # a flicker engine.
    assert "blink_flicker" not in {s.key for s in test_signals("Oblivion Ring")}
    assert "exile_removal" in {s.key for s in test_signals("Oblivion Ring")}


# ── 2. "Deals damage to an opponent" (any damage) — distinct from the combat axis ──
def test_lu_xun_damage_scope_is_opponents():
    sig = next(
        s
        for s in test_signals("Lu Xun, Scholar General")
        if s.key == "damage_to_opp_matters"
    )
    assert sig.scope == "opponents"


def test_zhang_liao_damage_and_discard():
    # damage_to_opp_matters AND opponent_discard are both IR-served. Zhang Liao's
    # "that opponent discards a card" fires opponent_discard alongside it.
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
    # Edric's "deals combat damage to one of your opponents" carries the structured
    # combat recipient; the any-damage key needs the structural DamageToPlayer
    # marker for a non-combat trigger, absent here.
    hyb = {s.key for s in test_signals("Edric, Spymaster of Trest")}
    assert "combat_damage_matters" in hyb
    assert "damage_to_opp_matters" not in hyb


# ── 3. Tribal ETB: "a <subtype> you control enters" ──
def test_tribal_etb_captures_subject():
    # Mary Jane Watson's "Whenever a Spider you control enters" captures the Spider
    # subject.
    sigs = test_signals("Mary Jane Watson")
    assert any(s.key == "type_matters" and s.subject == "Spider" for s in sigs)


def test_tribal_etb_no_junk_subject_for_creature():
    # Impact Tremors: "Whenever a creature you control enters, this enchantment
    # deals 1 damage to each opponent." — the generic creature_etb axis, never a
    # junk "creature" type_matters subject.
    sigs = test_signals("Impact Tremors")
    assert "creature_etb" in {s.key for s in sigs}
    assert not any(s.key == "type_matters" for s in sigs)


# ── 4. permanent_etb value engine: "another permanent you control enters" ──
def test_permanent_etb_scope_you():
    sig = next(
        s for s in test_signals("Amareth, the Lustrous") if s.key == "permanent_etb"
    )
    assert sig.scope == "you"


def test_creature_etb_does_not_fire_permanent_etb():
    # a creature-only ETB is creature_etb, not the generic permanent axis: Impact
    # Tremors' "a creature you control enters" never opens permanent_etb.
    assert "permanent_etb" not in {s.key for s in test_signals("Impact Tremors")}


def _idents(name):
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "ident", "expected"),
    [
        # A card or permanent other than this one put onto the battlefield under
        # your control.
        ("Rampant Growth", "permanent_etb|you|put", True),  # a land search
        ("Skyshroud Ranger", "permanent_etb|you|put", True),  # a land from hand
        ("Dredge the Mire", "permanent_etb|you|put", True),  # theirs, for you
        ("Ephemerate", "permanent_etb|you|put", True),  # a blink's return
        ("Path to Exile", "permanent_etb|you|put", False),  # the target's controller
        ("Nether Shadow", "permanent_etb|you|put", False),  # puts only itself
        ("Mox Diamond", "permanent_etb|you|put", False),  # puts only itself
        # A token copy of the card itself.
        ("Pack Rat", "token_copy_makers|you|self", True),
        ("Aven Initiate", "token_copy_makers|you|self", True),  # embalm
        ("Herald of the Host", "token_copy_makers|you|self", True),  # myriad
        ("Parallel Lives", "token_copy_makers|you|self", False),  # copies others
        # A card put onto the battlefield face down; a morph is cast.
        ("Manifest Dread", "facedown_makers|you|manifest", True),
        ("Ainok Tracker", "facedown_makers|you|manifest", False),
        # A cost paid by returning a land you control to hand.
        ("Coral Atoll", "permanent_etb|you|replay", True),
        ("Coral Atoll", "permanent_recast|you|replay", False),  # a land only
        # Tokens and puts read off the tree: a Role (parked, recovered), a
        # granted myriad, a token-increase replacement, a parked reanimation of
        # an opponent's card for you (CR 110.2a), an Attraction (CR 701.51b),
        # empowering Jace (CR 701.71a), a spellbook draft onto the battlefield,
        # a granted offspring.
        ("Become Brutes", "permanent_etb|you|put", True),
        ("Blade of Selves", "permanent_etb|you|put", True),
        ("Xorn", "permanent_etb|you|put", True),
        ("Bone Dancer", "permanent_etb|you|put", True),
        ("Thrilling Encore", "permanent_etb|you|put", True),
        ("Ride Guide", "permanent_etb|you|put", True),
        ("Jace's Machinations", "permanent_etb|you|put", True),
        ("Masterpiece Vault", "permanent_etb|you|put", True),
        ("Zinnia, Valley's Voice", "permanent_etb|you|put", True),
        ("Hunted Troll", "permanent_etb|you|put", False),  # an opponent's tokens
        # An enters watcher over more than one of your permanent types; "artifact
        # creature" is one object's types.
        ("Haliya, Guided by Light", "permanent_etb|you|", True),
        ("Canoptek Spyder", "permanent_etb|you|", False),
        # Its controller manifests: not yours.
        ("Reality Shift", "facedown_makers|you|manifest", False),
        # A trigger's event creature exiled and returned (CR 400.7).
        ("Gossip's Talent", "blink_flicker|you|enabler", True),
    ],
)
def test_permanents_entering_doers(name, ident, expected):
    assert (ident in _idents(name)) is expected


def test_permanent_etb_pages_what_makes_permanents_enter():
    """The "Permanents entering" page reads idents: makers, puts, the other
    engines and the ETB doublers; an enters drawback or an opponent's search
    makes nothing enter. Its doers open no avenue of their own."""
    from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for
    from mtg_utils.testkit import test_card, test_card_ir

    serve = SPECS[("permanent_etb", "you")].serve
    assert serve.oracle is None
    for name in (
        "Rampant Growth",
        "Krenko, Mob Boss",
        "Panharmonicon",
        "Amulet of Vigor",
        "Pack Rat",
        "Whitemane Lion",
        "Mulldrifter",
        "Manifest Dread",
    ):
        test_card_ir(name)
        assert serve.matches(test_card(name)), name
    for name in ("Phage the Untouchable", "Hidden Horror", "Path to Exile"):
        test_card_ir(name)
        assert not serve.matches(test_card(name)), name
    for key, subject in (
        ("permanent_etb", "put"),
        ("token_copy_makers", "self"),
        ("facedown_makers", "manifest"),
    ):
        sig = Signal(key=key, scope="you", subject=subject, text="", source="X")
        assert avenue_spec_for(sig) is None, (key, subject)


# ── new keys must have specs so the UI renders an avenue + serves() works ──
def test_new_keys_have_specs():
    for key, scope in (
        ("damage_to_opp_matters", "opponents"),
        ("permanent_etb", "you"),
    ):
        sig = Signal(key=key, scope=scope, subject="", text="", source="X")
        assert spec_for(sig) is not None, key
