"""Serve specs in ``signal_specs/data_4.py`` whose oracle-regex serve arm was
replaced by the lanes' structural idents (Pass A, 2026-10-18; plan
``docs/plans/serve-idents-and-avenue-support.md`` §2).

Each test pins the conversion on both sides of the boundary with real cards: a
card the old regex missed (or reached only by accident) that the lane's ident
now serves, and a card the old regex served on prose noise (reminder text, an
ability-word name) that no longer feeds the avenue.
"""

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


def _ident_serve(key, *idents):
    """The spec's serve, asserted to be ident-only (no oracle regex arm) and to
    carry every named ``key|you|`` ident."""
    spec = spec_for(_sig(key))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in (key, *idents):
        assert f"{ident}|you|" in spec.serve.signal_idents
    return spec.serve


def test_excess_damage_serves_the_lane_not_trample_reminder_text():
    serve = _ident_serve("excess_damage")
    assert serve.matches(_card("Flame Spill"))
    # The regex read "excess damage" in a conditional trample's reminder text.
    assert not serve.matches(_card("Charging War Boar"))


def test_recast_etb_serves_the_lane_bleeds_and_sneak_bodies():
    serve = _ident_serve("recast_etb")
    # An each-opponent ETB bleed phrased as a villainous choice (regex missed).
    assert serve.matches(_card("Sycorax Commander"))
    # The Sneak keyword arm: the bounce-replay engine the avenue is built on.
    assert serve.matches(_card("Oroku Saki, Shredder Rising"))
    assert serve.matches(_card("Burglar Rat"))
    # A Saga chapter's creature-enters drain is no recastable body.
    assert not serve.matches(_card("Thunder of Unity"))


def test_madness_serves_the_lane_not_ability_word_names():
    serve = _ident_serve("madness_matters")
    assert serve.matches(_card("Anje Falkenrath"))
    # "Crown of Madness" is an ability word, not the madness mechanic.
    assert not serve.matches(_card("Bloodboil Sorcerer"))


def test_speed_makers_serves_the_lane():
    serve = _ident_serve("speed_makers")
    # Changes an opponent's speed; the regex had no "that opponent's speed" arm.
    assert serve.matches(_card("Spikeshell Harrier"))


def test_speed_matters_serves_the_engines_through_the_makers_sibling():
    serve = _ident_serve("speed_matters", "speed_makers")
    # Scales with speed but never says "max speed" outside reminder text: the
    # makers sibling serves it on purpose now, not via the reminder.
    assert serve.matches(_card("The Speed Demon"))


def test_discover_serves_the_lane():
    serve = _ident_serve("discover_makers")
    assert serve.matches(_card("Curator of Sun's Creation"))


def test_undying_persist_serves_grants_not_ability_word_names():
    serve = _ident_serve("has_undying_persist")
    assert serve.matches(_card("Cauldron of Souls"))
    # "Undying Vengeance" is an ability word, not the undying keyword.
    assert not serve.matches(_card("Shadow of the Goblin"))


def test_cycling_serves_the_lane():
    serve = _ident_serve("cycling_matters")
    assert serve.matches(_card("Drake Haven"))


def test_kicked_spell_serves_the_lane():
    serve = _ident_serve("kicked_spell_matters")
    assert serve.matches(_card("Verazol, the Split Current"))


def test_colorless_serves_colorless_card_payoffs():
    serve = _ident_serve("colorless_matters")
    assert serve.matches(_card("Forsaken Monument"))
    # "a colorless card" — the regex only knew creature / spell / permanent.
    assert serve.matches(_card("Ancient Stirrings"))


def test_exalted_lone_attacker_serves_the_lane():
    serve = _ident_serve("exalted_lone_attacker")
    assert serve.matches(_card("Nick Fury, Spymaster"))


def test_flash_matters_serves_the_lane():
    serve = _ident_serve("flash_matters")
    assert serve.matches(_card("Alela, Cunning Conqueror"))


def test_team_evasion_grant_serves_pump_and_grant_anthems():
    serve = _ident_serve("team_evasion_grant")
    # "get +1/+1 and have flying": the regex wanted the grant right after
    # "creatures you control".
    assert serve.matches(_card("Eldrazi Monument"))


def test_suspend_makers_serves_the_time_counter_lane():
    serve = _ident_serve("suspend_makers", "suspend_matters", "extra_upkeep")
    # Impending enters with time counters; the makers regex never named it.
    assert serve.matches(_card("Lurker in the Deep"))
    assert serve.matches(_card("Paradox Haze"))


def test_saddle_serves_the_lane():
    serve = _ident_serve("saddle_matters")
    assert serve.matches(_card("Kolodin, Triumph Caster"))


def test_suspect_makers_serves_the_lane():
    serve = _ident_serve("suspect_makers")
    assert serve.matches(_card("Frantic Scapegoat"))


def test_suspect_matters_serves_payoffs_and_the_makers_that_feed_them():
    serve = _ident_serve("suspect_matters", "suspect_makers")
    assert serve.matches(_card("Agency Coroner"))
    # "suspect it" — a maker the "suspected" regex never saw.
    assert serve.matches(_card("Barbed Servitor"))


def test_cmdzone_ability_serves_the_lane():
    serve = _ident_serve("cmdzone_ability")
    assert serve.matches(_card("Oloro, Ageless Ascetic"))
