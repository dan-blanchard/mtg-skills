"""EDHREC blind-spot pass: recover zero-signal commanders whose archetype EDHREC
revealed AND whose own oracle text deterministically implies it (ADR-0009 — EDHREC
is a diagnostic, never a ranking input; detectors key off oracle text, not memory).

Single-clause widens vs full-text detectors (the extractor splits clauses on '.', so
trigger→payoff patterns spanning a sentence boundary need a full-text pass).
"""

from mtg_utils._card_ir.project import project_card
from mtg_utils._deck_forge.signals import extract_signals, extract_signals_hybrid


def _sigs(oracle, name="X", **extra):
    card = {"name": name, "oracle_text": oracle, "type_line": "Legendary Creature"}
    card.update(extra)
    return extract_signals(card)


def _keys(oracle, **kw):
    return {s.key for s in _sigs(oracle, **kw)}


def _hybrid_sigs(oracle, name="X", **extra):
    # ADR-0027: migrated keys (lifeloss_matters) are served from the IR; build the IR
    # from the same oracle so the hybrid reads it like production.
    card = {"name": name, "oracle_text": oracle, "type_line": "Legendary Creature"}
    card.update(extra)
    ir = project_card([{**card, "card_type": {"core_types": ["Creature"]}}])
    return extract_signals_hybrid(card, ir)


# ── Gogo: clone via bare infinitive "become a copy of" ──
GOGO = (
    "At the beginning of combat on your turn, you may have Gogo become a copy of "
    "another target creature you control until end of turn, except its name is Gogo."
)


def test_gogo_become_a_copy_fires_clone():
    assert "clone_matters" in _keys(GOGO, name="Gogo, Mysterious Mime")


def test_token_copy_still_not_clone():
    assert "clone_matters" not in _keys(
        "Create a token that's a copy of target creature."
    )


# ── Grond: Army tribal via "you control an Army" word order + vocab ──
GROND = "Trample\nAs long as it's your turn and you control an Army, Grond is an artifact creature."


def test_grond_army_tribal():
    sigs = _sigs(GROND, name="Grond, the Gatebreaker")
    assert any(s.key == "type_matters" and s.subject == "Army" for s in sigs)


def test_you_control_a_creature_no_junk_subject():
    sigs = _sigs("Whenever you control a creature, draw a card.")
    assert not any(s.key == "type_matters" for s in sigs)


# ── Sensei Golden-Tail: Samurai tribal via "becomes a Samurai in addition" ──
SENSEI = (
    "{1}{W}, {T}: Put a training counter on target creature. That creature gains "
    "bushido 1 and becomes a Samurai in addition to its other creature types."
)


def test_sensei_samurai_tribal():
    sigs = _sigs(SENSEI, name="Sensei Golden-Tail")
    assert any(s.key == "type_matters" and s.subject == "Samurai" for s in sigs)


# ── Veldrane / landwalk = conditional evasion ──
def test_landwalk_is_evasion():
    assert "evasion_self" in _keys(
        "{1}{B}{B}: Veldrane gets -3/-0 and gains forestwalk until end of turn.",
        name="Veldrane of Sengir",
    )
    assert "evasion_self" in _keys("This creature has islandwalk.")


# ── Xantcha / Haktos: forced-attack "attacks each combat if able" ──
def test_xantcha_forced_attack():
    assert "forced_attack" in _keys(
        "Xantcha attacks each combat if able and can't attack its owner.",
        name="Xantcha, Sleeper Agent",
    )


def test_haktos_forced_attack():
    assert "forced_attack" in _keys(
        "Haktos attacks each combat if able.", name="Haktos the Unscarred"
    )


# ── The Actualizer: life-loss with an interposed relative clause ──
def test_lifeloss_with_relative_clause():
    # ADR-0027: lifeloss_matters is IR-served; phase emits the structural lose_life.
    sigs = _hybrid_sigs(
        "Each opponent who guessed incorrectly loses 3 life.", name="The Actualizer"
    )
    assert any(s.key == "lifeloss_matters" and s.scope == "opponents" for s in sigs)


def test_plain_lifeloss_still_fires():
    assert "lifeloss_matters" in {
        s.key for s in _hybrid_sigs("Each opponent loses 2 life.")
    }


# ── Norin: self-blink (full text — exile-by-name + cross-sentence return) ──
NORIN = (
    "When a player casts a spell or a creature attacks, exile Norin. Return it to "
    "the battlefield under its owner's control at the beginning of the next end step."
)


def test_norin_self_blink():
    # ADR-0027 t2b4-C: self_blink migrated to the Card IR — the regex path no longer
    # emits it; the name-aware fulltext detector + the per-clause SWEEP mirror run in the
    # IR path (any non-None IR routes there; both read the record's oracle_text + name).
    assert "self_blink" not in _keys(NORIN, name="Norin the Wary")
    assert "self_blink" in {s.key for s in _hybrid_sigs(NORIN, name="Norin the Wary")}


def test_no_blink_without_exile_return():
    # a self-referential trigger that isn't an exile-and-return is not a blink.
    assert "self_blink" not in {
        s.key
        for s in _hybrid_sigs(
            "When Norin attacks, you draw a card.", name="Norin the Wary"
        )
    }


# ── Aurelia: beginning-of-combat single-target pump (full text, spans period) ──
AURELIA = (
    "Flying\nMentor\nAt the beginning of combat on your turn, choose up to one target "
    "creature you control. Until end of turn, that creature gets +2/+0, gains trample "
    "if it's red, and gains vigilance if it's white."
)


def test_aurelia_combat_buff_engine():
    assert "combat_buff_engine" in _keys(AURELIA, name="Aurelia, Exemplar of Justice")


def test_static_anthem_not_combat_buff():
    # no beginning-of-combat trigger → not a combat-buff engine.
    assert "combat_buff_engine" not in _keys("Creatures you control get +1/+1.")


# ── Alpharael: loot/rummage across a sentence boundary ──
ALPHARAEL = (
    "When Alpharael enters, draw two cards. Then discard two cards unless you "
    "discard an artifact card."
)


def test_alpharael_loot_is_discard():
    assert "discard_matters" in _keys(ALPHARAEL, name="Alpharael, Dreaming Acolyte")


def test_draw_then_unrelated_not_loot():
    # draw followed by an unrelated sentence must not read as a loot outlet.
    assert "discard_matters" not in _keys("Draw two cards. You gain 3 life.")
