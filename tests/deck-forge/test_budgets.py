"""Tests for slot budgets vs the (soft) Command Zone template (band model, ADR-0024)."""

from mtg_utils._deck_forge.budgets import (
    _ir_board_wipe,
    _ir_draws,
    protects,
    role_of,
    slot_budgets,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity
from mtg_utils.testkit import test_card, test_card_ir

FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "oracle_text": "({T}: Add {G}.)",
}
LLANOWAR = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "oracle_text": "{T}: Add {G}.",
    "produced_mana": ["G"],
}
MURDER = {
    "name": "Murder",
    "type_line": "Instant",
    "oracle_text": "Destroy target creature.",
}
COUNTERSPELL = {
    "name": "Counterspell",
    "type_line": "Instant",
    "oracle_text": "Counter target spell.",
    "keywords": [],
}
DIVINATION = {
    "name": "Divination",
    "type_line": "Sorcery",
    "oracle_text": "Draw two cards.",
}
# task #83: board-wipe is now a structural view over the crosswalk `mass_removal`
# signal (theme_presets.py), which needs a real `oracle_id` to resolve (see
# `_signal_keys_for`) — a hand-typed dict with no oracle_id can no longer be
# classified via the preset fallback `_matches_preset` reads in `role_of` /
# `slot_budgets`. Seed the crosswalk trees memo (test_card_ir, CI-safe via the
# committed snapshot) before pulling the real minimal Scryfall record.
test_card_ir("Wrath of God")
WRATH = test_card("Wrath of God")
FLESHBAG = {
    "name": "Fleshbag Marauder",
    "type_line": "Creature — Zombie Warrior",
    "oracle_text": (
        "When this creature enters, each player sacrifices a creature of their choice."
    ),
}
PACIFISM = {
    "name": "Pacifism",
    "type_line": "Enchantment — Aura",
    "oracle_text": "Enchant creature\nEnchanted creature can't attack or block.",
}
# Over-fire guard: a creature whose OWN "can't attack or block" is a drawback (keyed on
# "This creature", not "Enchanted creature") is not removal.
LUPINE = {
    "name": "Lupine Prototype",
    "type_line": "Artifact Creature — Wolf Construct",
    "oracle_text": "This creature can't attack or block unless a player has no cards in hand.",
}
# Over-fire guard: sacrifice as an activated COST (you choose to pay) is not an edict.
VISCERA = {
    "name": "Viscera Seer",
    "type_line": "Creature — Vampire Wizard",
    "oracle_text": "Sacrifice a creature: Scry 1.",
}


def test_empty_deck_bands_scale_to_deck_size():
    b100 = slot_budgets([], deck_size=100)
    assert b100["ramp"]["min"] == 10
    assert b100["ramp"]["max"] == 12
    assert b100["lands"]["min"] == 36
    assert b100["lands"]["max"] == 38
    b60 = slot_budgets([], deck_size=60)
    assert b60["ramp"]["min"] == 6  # round(10 * 0.6)
    assert b60["ramp"]["max"] == 7  # round(12 * 0.6)


def test_role_classification_folds_counterspells_into_interaction():
    assert "lands" in role_of(FOREST)
    assert "ramp" in role_of(LLANOWAR)
    assert "interaction" in role_of(MURDER)
    assert "interaction" in role_of(COUNTERSPELL)  # counterspell folds into interaction
    assert "card_draw" in role_of(DIVINATION)
    assert "board_wipe" in role_of(WRATH)


def test_edicts_and_pacify_auras_count_as_interaction():
    # role_of is the universal coverage fallback, so forced-sacrifice (edicts) and
    # pacification auras — both REMOVAL regardless of commander — must register as
    # interaction. Fleshbag (creature-edict) and Pacifism (neutralize aura) were missed.
    assert "interaction" in role_of(FLESHBAG)
    assert "interaction" in role_of(PACIFISM)
    # Over-fire guards: a sacrifice COST (Viscera Seer) and a creature with a "can't
    # attack" DRAWBACK on itself (Lupine Prototype) are not removal.
    assert "interaction" not in role_of(VISCERA)
    assert "interaction" not in role_of(LUPINE)


def test_interaction_excludes_infect_creatures_and_graveyard_recursion():
    # The interaction TEMPLATE role is "targeted removal + counterspells" (budgets
    # docstring). Two over-fires inflated it: (1) the creature-removal preset's
    # Fight/Infect/Wither KEYWORDS tagged static combat creatures (CR 702.90a infect is
    # a static combat ability, not spot removal); (2) the removal/bounce "return target
    # permanent ... hand" regexes matched graveyard recursion ("return target permanent
    # CARD from your graveyard"). Both must be excluded.
    blighted_agent = {
        "name": "Blighted Agent",
        "type_line": "Creature — Human Rogue",
        "oracle_text": "Infect (This creature deals damage to creatures in the form of "
        "-1/-1 counters and to players in the form of poison counters.)\n"
        "Blighted Agent can't be blocked.",
        "keywords": ["Infect"],
    }
    swarmlord = {
        "name": "Phyrexian Swarmlord",
        "type_line": "Creature — Phyrexian Insect",
        "oracle_text": "Infect\nAt the beginning of your upkeep, create a 1/1 green and "
        "black Insect creature token with infect for each poison counter your opponents "
        "have.",
        "keywords": ["Infect"],
    }
    unnatural_restoration = {
        "name": "Unnatural Restoration",
        "type_line": "Instant",
        "oracle_text": "Return target permanent card from your graveyard to your hand.",
        "keywords": [],
    }
    assert "interaction" not in role_of(blighted_agent)
    assert "interaction" not in role_of(swarmlord)
    assert "interaction" not in role_of(unnatural_restoration)
    # Genuine targeted removal / bounce still counts.
    murder = {
        "name": "Murder",
        "type_line": "Instant",
        "oracle_text": "Destroy target creature.",
        "keywords": [],
    }
    boomerang = {
        "name": "Boomerang",
        "type_line": "Instant",
        "oracle_text": "Return target permanent to its owner's hand.",
        "keywords": [],
    }
    prey_upon = {
        "name": "Prey Upon",
        "type_line": "Sorcery",
        "oracle_text": "Target creature you control fights target creature you don't "
        "control.",
        "keywords": [],
    }
    assert "interaction" in role_of(murder)
    assert "interaction" in role_of(boomerang)
    assert "interaction" in role_of(prey_upon)


def test_protection_is_advisory_not_a_counted_role():
    # Counterspell counts as both interaction (template) AND protection (Tier-2 flag).
    # protects() gates on the `counterspell` preset, which moved to a structural
    # view (task #83) — it needs a real oracle_id to resolve, so this assertion
    # uses the testkit snapshot record rather than the synthetic COUNTERSPELL
    # dict (which the other assertions here still use — they don't exercise the
    # counterspell preset's match arm).
    from mtg_utils import testkit

    testkit.test_card_ir("Counterspell")  # seeds the crosswalk trees memo
    real_counterspell = testkit.test_card("Counterspell")
    assert protects(real_counterspell) is True
    assert protects(MURDER) is False
    assert "protection" not in role_of(COUNTERSPELL)  # never a counted role


def test_protection_requires_granting_not_a_self_keyword():
    # A permanent that is merely indestructible/hexproof itself protects only itself.
    self_indestructible = {
        "name": "Darksteel Reactor",
        "type_line": "Artifact",
        "oracle_text": 'Indestructible (Effects that say "destroy" don\'t destroy this artifact.)\nAt the beginning of your upkeep, you may put a charge counter on this artifact.\nWhen this artifact has twenty or more charge counters on it, you win the game.',
        "keywords": ["Indestructible"],
    }
    self_hexproof = {
        "name": "Carnage Tyrant",
        "type_line": "Creature — Dinosaur",
        "oracle_text": "This spell can't be countered.\nTrample, hexproof",
        "keywords": ["Trample", "Hexproof"],
    }
    assert protects(self_indestructible) is False
    assert protects(self_hexproof) is False
    # Granting a protective quality to ANOTHER permanent does count.
    grants = {
        "name": "Swiftfoot Boots",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has hexproof and haste. (It can't be the target of spells or abilities your opponents control. It can attack and {T} no matter when it came under your control.)\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    }
    save = {
        "name": "Boros Charm",
        "type_line": "Instant",
        "oracle_text": "Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain indestructible until end of turn.\n• Target creature gains double strike until end of turn.",
    }
    assert protects(grants) is True
    assert protects(save) is True
    # Pillow-fort / attack-deterrent effects protect YOU the player.
    pillow = {
        "name": "Ghostly Prison",
        "type_line": "Enchantment",
        "oracle_text": "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.",
    }
    assert protects(pillow) is True


def test_protection_recognizes_redirect_and_totem_armor():
    # Free redirect answers (CR 115.7 — "change the target"/"choose new targets for
    # target spell or ability") answer removal like a counterspell, and umbra/totem
    # armor (CR 702.89a) grants a destroy-replacement shield to your permanents. Both
    # were missed, so Misdirection/Deflecting Swat/Umbra Mystic bucketed filler and the
    # tuner proposed cutting them "serves no avenue (filler)". They must read as
    # protection (spine), never filler.
    misdirection = {
        "name": "Misdirection",
        "type_line": "Instant",
        "oracle_text": (
            "You may exile a blue card from your hand rather than pay this spell's "
            "mana cost.\nChange the target of target spell with a single target."
        ),
    }
    deflecting_swat = {
        "name": "Deflecting Swat",
        "type_line": "Instant",
        "oracle_text": (
            "If you control a commander, you may cast this spell without paying its "
            "mana cost.\nYou may choose new targets for target spell or ability."
        ),
    }
    umbra_mystic = {
        "name": "Umbra Mystic",
        "type_line": "Creature — Elf Mystic",
        "oracle_text": (
            "Auras attached to permanents you control have totem armor. (If such a "
            "permanent would be destroyed, instead remove all damage from it and "
            "destroy that Aura.)"
        ),
    }
    assert protects(misdirection) is True
    assert protects(deflecting_swat) is True
    assert protects(umbra_mystic) is True
    # Over-fire guard: a copy spell redirects "the copy", not an answer — not protection.
    twincast = {
        "name": "Twincast",
        "type_line": "Instant",
        "oracle_text": (
            "Copy target instant or sorcery spell. You may choose new targets for "
            "the copy."
        ),
    }
    assert protects(twincast) is False


def test_protection_excludes_self_only_saves():
    # A creature that only phases/regenerates ITSELF is self-protection — doesn't count.
    self_phase = {
        "name": "Frenetic Efreet",
        "type_line": "Creature — Efreet",
        "oracle_text": "Flying\n{0}: Flip a coin. If you win the flip, this creature phases out. If you lose the flip, sacrifice this creature. (While it's phased out, it's treated as though it doesn't exist. It phases in before you untap during your next untap step.)",
    }
    assert protects(self_phase) is False
    # Saving / shielding OTHERS still counts.
    fog = {
        "name": "Fog",
        "type_line": "Instant",
        "oracle_text": "Prevent all combat damage that would be dealt this turn.",
    }
    save_target = {
        "name": "Sejiri Refuge Save",
        "type_line": "Instant",
        "oracle_text": "Regenerate target creature you control.",
    }
    assert protects(fog) is True
    assert protects(save_target) is True


def test_current_counts_reflect_deck():
    b = slot_budgets([FOREST, LLANOWAR, MURDER, DIVINATION, WRATH], deck_size=100)
    assert b["lands"]["current"] == 1
    assert b["ramp"]["current"] == 1
    assert b["card_draw"]["current"] == 1
    assert b["board_wipe"]["current"] == 1
    assert b["interaction"]["current"] >= 1


def test_deviation_signs_short_in_band_and_over():
    # 1 ramp source against a 10-12 band → short by 9.
    short = slot_budgets([LLANOWAR], deck_size=100)
    assert short["ramp"]["deviation"] == -9
    assert short["ramp"]["remaining"] == 9
    # 12 ramp sources → in band → deviation 0, remaining 0.
    rocks = [
        {
            "name": f"Rock {i}",
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}.",
            "produced_mana": ["C"],
        }
        for i in range(12)
    ]
    inband = slot_budgets(rocks, deck_size=100)
    assert inband["ramp"]["deviation"] == 0
    assert inband["ramp"]["remaining"] == 0
    # 15 ramp sources → over the 12 ceiling → +3.
    over = slot_budgets(rocks + rocks[:3], deck_size=100)
    assert over["ramp"]["deviation"] == 3


def test_shape_scales_control_interaction_up():
    flat = slot_budgets([], deck_size=100, shape=None)
    control = slot_budgets([], deck_size=100, shape="control")
    assert flat["interaction"]["max"] == 12
    assert control["interaction"]["min"] == 12
    assert control["interaction"]["max"] == 15
    # Aggro trims wraths.
    aggro = slot_budgets([], deck_size=100, shape="aggro")
    assert aggro["board_wipe"]["max"] == 2


# ── card_draw via Card IR (ADR-0027, A3) ─────────────────────────────────────
# role_of resolves card_draw from the candidate's IR ``draw`` category when present
# (the dict fixtures above carry no oracle_id, so they exercise the preset
# fallback). These exercise the structured ``_ir_draws`` classifier directly.


def _ir(*abilities: Ability) -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=abilities),))


def test_ir_draw_for_you_fills_card_draw():
    # Real projected IR: "Draw two cards" (Divination → draw/you) and an upkeep draw
    # (Phyrexian Arena → draw/you + lose_life/you) both fill it.
    assert _ir_draws(test_card_ir("Divination")) is True
    assert _ir_draws(test_card_ir("Phyrexian Arena")) is True
    # Symmetric "each player draws" (Howling Mine → draw/any) still fills your slot.
    assert _ir_draws(test_card_ir("Howling Mine")) is True
    # Connive (Ledger Shredder → connive) is card advantage too — its own IR category.
    assert _ir_draws(test_card_ir("Ledger Shredder")) is True


def test_ir_non_draw_and_opponent_draw_do_not_fill_card_draw():
    # Real projected IR: a damage spell (Lightning Bolt → damage/any) is not draw.
    assert _ir_draws(test_card_ir("Lightning Bolt")) is False
    # Logic probe (kept synthetic): a pure opponent-only draw (a giveaway, scope 'opp')
    # doesn't fill YOUR card_draw slot. No real card projects to a draw/opp effect —
    # phase attributes "target opponent draws" to scope 'you' (e.g. Master of the Feast),
    # so this pins the scope=='opp' branch of _ir_draws that real IR can't reach today.
    giveaway = _ir(
        Ability(kind="spell", effects=(Effect(category="draw", scope="opp"),))
    )
    assert _ir_draws(giveaway) is False


def _ir_effect(**kw):
    """One spell effect wrapped in a Card IR, for board-wipe structural probes."""
    return Card(
        oracle_id="x",
        name="T",
        faces=(
            Face(name="T", abilities=(Ability(kind="spell", effects=(Effect(**kw),)),)),
        ),
    )


def test_ir_board_wipe_reads_mass_marker_and_subject_gate():
    # phase parses single-vs-mass; the projection keeps it (DestroyAll/DamageAll/BounceAll
    # → counter_kind="all"; fixed mass -N/-N → cat=pump, negative amount, temporary). The
    # board_wipe role can read that structurally instead of by oracle regex. Shapes below
    # are the ones the real cards project to (verified against the v0.9.0 card-data).
    creature = Filter(card_types=("Creature",))
    permanent = Filter(card_types=("Permanent",), predicates=("NotType:Land",))
    # Mass creature destroy (Wrath / Damnation / Crux) — board wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(category="destroy", counter_kind="all", subject=creature)
        )
        is True
    )
    # Mass nonland-permanent destroy (Culling Ritual) — board wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(category="destroy", counter_kind="all", subject=permanent)
        )
        is True
    )
    # Mass damage to each creature (Blasphemous Act) — board wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="damage",
                counter_kind="all",
                amount=Quantity(op="fixed", factor=13),
                subject=creature,
            )
        )
        is True
    )
    # One-sided mass destroy of opponents' creatures — board wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="destroy",
                counter_kind="all",
                subject=Filter(card_types=("Creature",), controller="opp"),
            )
        )
        is True
    )
    # Single-target destroy (Murder) — NOT a wipe (no mass marker).
    assert (
        _ir_board_wipe(
            _ir_effect(category="destroy", counter_kind="", subject=creature)
        )
        is False
    )
    # Mass destroy gated to LANDS (Armageddon) = mass land denial, NOT a creature sweeper.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="destroy",
                counter_kind="all",
                subject=Filter(card_types=("Land",)),
            )
        )
        is False
    )
    # Mass destroy of artifacts+enchantments (Bane of Progress) — not a creature sweeper.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="destroy",
                counter_kind="all",
                subject=Filter(card_types=("Artifact", "Enchantment")),
            )
        )
        is False
    )
    # Self-only mass bounce ("return each creature YOU CONTROL" — Denizen of the Deep) is
    # a drawback, not board control.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="bounce",
                counter_kind="all",
                subject=Filter(card_types=("Creature",), controller="you"),
            )
        )
        is False
    )
    # Mass graveyard recursion ("return all creature cards from your graveyard" —
    # Lychguard) is not removal.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="bounce",
                counter_kind="all",
                zones=("from:graveyard", "to:hand"),
                subject=Filter(card_types=("Creature",)),
            )
        )
        is False
    )
    # Mass -X/-X shrink (SIDECAR v74 Effect.toughness): a mass pump whose TOUGHNESS factor
    # is negative can kill — fixed (Drown -2/-2) and variable (Toxic Deluge -X/-X) both.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="pump",
                toughness=Quantity(op="fixed", factor=-2),
                subject=creature,
            )
        )
        is True
    )
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="pump",
                toughness=Quantity(op="variable", factor=-1),
                subject=creature,
            )
        )
        is True
    )
    # Power-only -2/-0 (Marsh Gas), toughness factor 0 — harmless, NOT a wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="pump",
                amount=Quantity(op="fixed", factor=-2),
                toughness=Quantity(op="fixed", factor=0),
                subject=creature,
            )
        )
        is False
    )
    # +X/+X mass anthem (toughness > 0) is a buff, and a SINGLE-target shrink is
    # pump_target — neither is a board wipe.
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="pump",
                toughness=Quantity(op="fixed", factor=2),
                subject=creature,
            )
        )
        is False
    )
    assert (
        _ir_board_wipe(
            _ir_effect(
                category="pump_target",
                toughness=Quantity(op="fixed", factor=-2),
                subject=creature,
            )
        )
        is False
    )


def test_board_wipe_role_reads_real_ir_mass_destroy():
    # Real projected IR (committed snapshot): Wrath of God is a structural board wipe.
    assert _ir_board_wipe(test_card_ir("Wrath of God")) is True
    # A mass -X/-X shrink SPELL (Toxic Deluge) — via the SIDECAR-v74 Effect.toughness.
    # ADR-0039 step 5.5 fix: _card_ir.compat._pump_pt now threads a DYNAMIC pump
    # magnitude's SIGN (Quantity(op="variable", factor=+-1)) the same way project.py's
    # _pump_toughness/_signed_pt_mod always has — Toxic Deluge's "-X/-X" (scaled by
    # life paid) keeps its negative sign even though X itself is unfixed, so the
    # mass-shrink board-wipe read now agrees on both flags.
    assert _ir_board_wipe(test_card_ir("Toxic Deluge")) is True


def test_static_mass_debuff_anthem_is_board_wipe():
    # SIDECAR v75: a STATIC mass-debuff anthem (Elesh Norn's "Creatures your opponents
    # control get -2/-2") now carries Effect.toughness on its static-mod pump, so it reads
    # as a structural board wipe — while its own "+2/+2" buff (controller=you, factor > 0)
    # does not flip it.
    assert _ir_board_wipe(test_card_ir("Elesh Norn, Grand Cenobite")) is True


def test_ir_recursion_only_vetoes_pure_graveyard_return():
    # F10 structural veto: a card whose ONLY interaction-shaped effect is a graveyard
    # bounce (Pharika's Mender: "return target creature OR enchantment card from your
    # graveyard") is recursion, not interaction — the bounce/removal presets misfire on
    # the "X or Y card" form their (?!\s+card\b) anchor can't exclude. A battlefield
    # bounce, a -X/-X shrink, a tuck, or any destroy/edict means a real answer → not
    # vetoed. Needs SIDECAR v76 per-effect graveyard zones (no sibling bleed).
    from mtg_utils._deck_forge.budgets import _ir_recursion_only

    def _gy(*zones):
        return Card(
            oracle_id="x",
            name="T",
            faces=(
                Face(
                    name="T",
                    abilities=(
                        Ability(
                            kind="spell",
                            effects=(Effect(category="bounce", zones=zones),),
                        ),
                    ),
                ),
            ),
        )

    # Pure graveyard recursion → vetoed.
    assert _ir_recursion_only(_gy("in:graveyard")) is True
    # A battlefield bounce is a real tempo answer → not recursion-only.
    assert _ir_recursion_only(_gy()) is False
    assert _ir_recursion_only(_gy("in:battlefield", "in:graveyard")) is False
    # A graveyard bounce alongside a real answer (edict) → not recursion-only.
    assert (
        _ir_recursion_only(
            Card(
                oracle_id="x",
                name="T",
                faces=(
                    Face(
                        name="T",
                        abilities=(
                            Ability(
                                kind="spell",
                                effects=(
                                    Effect(category="bounce", zones=("in:graveyard",)),
                                    Effect(category="sacrifice", scope="opp"),
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )
        is False
    )
    # No graveyard bounce at all can never be vetoed (real removal — mass destroy).
    assert _ir_recursion_only(test_card_ir("Wrath of God")) is False


def test_ir_redirect_is_structural():
    # phase parses redirect answers (Misdirection, Deflecting Swat) as cat=redirect, so
    # protects() reads that structurally instead of the "change the target / choose new
    # targets" regex (kept as the no-IR fallback — Misdirection/Deflecting Swat have no
    # oracle_id in the test record, so the regex still covers the inline-dict test above).
    from mtg_utils._deck_forge.budgets import _ir_redirect

    assert _ir_redirect(_ir_effect(category="redirect")) is True
    assert _ir_redirect(_ir_effect(category="destroy")) is False
