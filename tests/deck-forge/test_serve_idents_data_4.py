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
    count every named ``key|you|`` ident (exactly or by a ``key|you|*`` wildcard)."""
    spec = spec_for(_sig(key))
    assert spec is not None
    assert spec.serve.oracle is None
    for ident in (key, *idents):
        assert spec.serve.counts_ident(f"{ident}|you|"), ident
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


def test_suspend_matters_serves_time_counter_references_not_its_own_name():
    serve = _ident_serve("suspend_matters", "suspend_makers", "extra_upkeep")
    # "Target permanent or suspended card" (CR 702.62b) names time counters.
    assert serve.matches(_card("Clockspinning"))
    assert serve.matches(_card("Paradox Haze"))
    # Impending Flux only names itself.
    assert not serve.matches(_card("Impending Flux"))


# ── 2026-10-20 pass (the 0.4-0.9 and < 0.4 census rows) ─────────────────────


def test_ltb_serves_bounce_payoffs_not_sacrifice_tethers():
    serve = _ident_serve("ltb_matters")
    # "Whenever a permanent is returned to your hand" — leaving the
    # battlefield (CR 603.6c) the "leaves the battlefield" regex never read.
    assert serve.matches(_card("Azorius Aethermage"))
    # "When this Aura leaves, that creature's controller sacrifices it" is a
    # tether on the reanimated creature, not a leaves payoff.
    assert not serve.matches(_card("Animate Dead"))


def test_lessons_serves_the_lane_and_learn_bearers():
    serve = _ident_serve("lessons_matter")
    # "If that spell is a Lesson" — a Lesson payoff the regex never named.
    assert serve.matches(_card("Toph, Hardheaded Teacher"))
    # Learn (CR 701.48a) rides the keyword field, as the regex served it.
    assert serve.matches(_card("Academic Dispute"))


def test_multicolor_serves_payoffs_and_converge_bearers():
    serve = _ident_serve("multicolor_matters")
    # Reveals one card of each colour pair: the regex wanted "multicolored".
    assert serve.matches(_card("Niv-Mizzet Reborn"))
    # Converge is an ability word (CR 207.2c): the keyword field carries it.
    assert serve.matches(_card("Bring to Light"))


def test_saga_serves_lore_payoffs_and_saga_references():
    serve = _ident_serve("saga_matters")
    assert "type_matters|you|Saga" in serve.signal_idents
    # Saga replicate: a Saga payoff with no "lore counter" in its text.
    assert serve.matches(_card("Ian Chesterton"))


def test_base_power_serves_payoffs_not_base_pt_setters():
    serve = _ident_serve("base_power_matters")
    assert serve.matches(_card("Bess, Soul Nourisher"))
    # A polymorph SETS base P/T (CR 613.4b); it rewards nothing.
    assert not serve.matches(_card("Turn to Frog"))


def test_arcane_serves_spirit_or_arcane_payoffs():
    serve = _ident_serve("arcane_matters")
    # Neither an Arcane card nor a splice card: the old serve missed both.
    assert serve.matches(_card("The Unspeakable"))
    assert serve.matches(_card("Petalmane Baku"))


def test_enlist_serves_the_lane():
    serve = _ident_serve("has_enlist")
    card = _card("Argivian Cavalier")
    assert serve.matches(card)
    assert "has_enlist|you|" in serve.matched_idents(card)


def test_exert_serves_the_keyword_not_the_vigilance_enablers():
    spec = spec_for(_sig("exert_matters"))
    assert spec is not None
    assert spec.serve.oracle is None
    assert spec.serve.matches(_card("Glorybringer"))
    # The lane's own key fires on vigilance enablers — the side the avenue
    # opens from, not the exert bodies it serves.
    assert not spec.serve.matches(_card("Intangible Virtue"))


def test_land_exchange_serves_land_steals():
    serve = _ident_serve("land_exchange")
    # "Gain control of a land you don't control" (no "exchange control of").
    assert serve.matches(_card("Herald of Leshrac"))


# Pass C (land denial, activated draw, untap, flash, Islands) ------------------


def _spec_serve(key, scope="you"):
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    return spec.serve


def test_land_denial_serves_sacrifice_lanes_not_the_bounce_remainder():
    serve = _spec_serve("land_denial")
    # "Each player ... sacrifices the rest" of their lands: no "sacrifices a land".
    assert serve.matches(_card("Cataclysm"))
    # "That player returns a land": no lane reads it, the named remainder.
    assert not serve.matches(_card("Mana Breach"))


def test_activated_draw_serves_costs_other_than_bare_tap():
    serve = _spec_serve("activated_draw")
    # "{T}, Discard a card: Draw a card" - the regex needed "{T}: draw a card".
    assert serve.matches(_card("Anje Falkenrath"))
    assert serve.matches(_card("Arcanis the Omnipotent"))


def test_power_tap_engine_serves_untap_engines_not_self_untaps():
    serve = _spec_serve("power_tap_engine")
    assert serve.matches(_card("Aphetto Alchemist"))
    # "Untap it" on itself re-taps no other engine; the regex served it.
    assert not serve.matches(_card("Blistercoil Weird"))


def test_flash_makers_serves_the_granter_lane():
    serve = _spec_serve("flash_makers")
    # Flash creature cards you own, granted from the battlefield (regex missed).
    assert serve.matches(_card("Teferi, Mage of Zhalfir"))
    assert serve.matches(_card("Leyline of Anticipation"))


def test_island_makers_serves_attack_restriction_bodies():
    serve = _spec_serve("island_makers")
    assert serve.matches(_card("Armored Galleon"))
    assert serve.matches(_card("Stormtide Leviathan"))
    # Carpet of Flowers' "X is the number of Islands target opponent controls" is
    # a payoff for opponents' Islands (typed since phase v0.118.0; a residue
    # before), the want the Island makers feed — the page shows it.
    assert serve.matches(_card("Carpet of Flowers"))


def test_island_matters_serves_island_effects():
    serve = _spec_serve("island_matters")
    assert serve.matches(_card("Armored Galleon"))
    assert serve.matches(_card("Stormtide Leviathan"))
    # Opponents' Islands fuel its mana (counts_opponents_land_type).
    assert serve.matches(_card("Carpet of Flowers"))


def _served(key, name, *, scope="you"):
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    return spec.serve.matches(_card(name))


def test_anthem_static_serves_subtype_anthems_not_cost_reducers():
    assert _served("anthem_static", "Allied Teamwork")
    # The regex read "creatures you control ... {X} less" across a cost clause.
    assert not _served("anthem_static", "Agatha of the Vile Cauldron")


def test_life_payment_insurance_serves_cant_lose_only():
    assert _served("life_payment_insurance", "Lich's Tomb")
    # "Your life total can't change" never lets you reach 0 life: not insurance.
    assert not _served("life_payment_insurance", "Platinum Emperion")


def test_per_target_payoff_serves_variable_target_counts():
    assert _served("per_target_payoff", "Abandon the Post")
    # A fixed-count mass ability on a permanent: out by design.
    assert not _served("per_target_payoff", "Arc Mage")


def test_target_own_payoff_serves_free_targeting():
    assert _served("target_own_payoff", "Reconnaissance")


def test_lose_unless_hand_serves_the_zero_life_negators():
    assert _served("lose_unless_hand", "Lich")
    # "You can't win" is no backstop against losing from the lose-trigger.
    assert not _served("lose_unless_hand", "Abyssal Persecutor")


def test_cheat_from_top_serves_put_on_top_not_surveil_reminders():
    assert _served("cheat_from_top", "Boggart Harbinger")
    assert not _served("cheat_from_top", "Curate")


def test_minus_counters_serves_placers_and_keyword_bearers():
    assert _served("minus_counters_matter", "Trigon of Infestation")
    # Infect bearers come in by keyword, not by the reminder text.
    assert _served("minus_counters_matter", "Blight Mamba")
    assert not _served("minus_counters_matter", "Everlasting Torment")


def test_land_destruction_serves_every_kind_not_symmetric_tap_taxes():
    assert _served("land_destruction", "Acid Rain")
    assert not _served("land_destruction", "Desolation")


def test_mass_death_payoff_serves_creature_wipes_not_mass_exile_text():
    assert _served("mass_death_payoff", "Akroma's Vengeance")
    assert not _served("mass_death_payoff", "Beyond the Quiet")


def test_tap_down_blockers_serves_the_lane_not_untap_cards():
    assert _served("tap_down_blockers", "Chrome Prowler")
    assert not _served("tap_down_blockers", "Provoke")


def test_kill_engine_serves_death_payoffs_not_draw_on_death():
    assert _served("kill_engine", "Dingus Staff")
    assert not _served("kill_engine", "Dark Prophecy")


def test_entered_attacker_serves_team_haste_not_self_pumps():
    assert _served("entered_attacker", "Brudiclad, Telchor Engineer")
    assert not _served("entered_attacker", "Griffin Protector")
