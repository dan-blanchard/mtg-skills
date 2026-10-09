"""Tests for slot budgets vs the (soft) Command Zone template (band model, ADR-0024)."""

import pytest

from mtg_utils._analysis.budgets import (
    CONSTRUCTED_TEMPLATE,
    LIMITED_TEMPLATE,
    slot_budgets,
    template_for,
)
from mtg_utils._analysis.roles import _ir_board_wipe, _ir_draws, protects, role_of
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity
from mtg_utils.testkit import test_card, test_card_ir


def _text_only(name):
    """The real record for *name* with its ``oracle_id`` stripped (ADR-0056's
    missing-field rule). ``role_of`` reads a card with no ``oracle_id`` through the
    oracle-text fallback, not the signal path; these fixtures pin that fallback,
    so they must not resolve a concept tree."""
    record = test_card(name)
    record.pop("oracle_id", None)
    return record


FOREST = _text_only("Forest")
LLANOWAR = _text_only("Llanowar Elves")
# task #86: `removal` (the last regex-bearing built-in preset) flipped to a
# structural (signal_keys) view — needs a real oracle_id to resolve, same as
# `board-wipe`/WRATH below. `counterspell` was already structural (task #83).
test_card_ir("Murder")
MURDER = test_card("Murder")
test_card_ir("Counterspell")
COUNTERSPELL = test_card("Counterspell")
# task #83: board-wipe is now a structural view over the crosswalk `mass_removal`
# signal (theme_presets.py), which needs a real `oracle_id` to resolve (see
# `_signal_keys_for`) — a hand-typed dict with no oracle_id can no longer be
# classified via the preset fallback `_matches_preset` reads in `role_of` /
# `slot_budgets`. Seed the crosswalk trees memo (test_card_ir, CI-safe via the
# committed snapshot) before pulling the real minimal Scryfall record.
test_card_ir("Wrath of God")
WRATH = test_card("Wrath of God")
# creature-edict is a task #83 structural view (concept-only, no regex arm
# left), so Fleshbag keeps its real oracle_id to resolve the crosswalk tree.
FLESHBAG = test_card("Fleshbag Marauder")
# Over-fire guard: a creature whose OWN "can't attack or block" is a drawback (keyed on
# "This creature", not "Enchanted creature") is not removal.
LUPINE = _text_only("Lupine Prototype")
# Over-fire guard: sacrifice as an activated COST (you choose to pay) is not an edict.
VISCERA = _text_only("Viscera Seer")


# The flat Command Zone lands row, for tests that only read other roles.
_BAND = (36, 38)


def test_empty_deck_bands_scale_to_deck_size():
    b100 = slot_budgets([], deck_size=100, land_band=_BAND)
    assert b100["ramp"]["min"] == 10
    assert b100["ramp"]["max"] == 12
    assert b100["lands"]["min"] == 36
    assert b100["lands"]["max"] == 38
    b60 = slot_budgets([], deck_size=60, land_band=(22, 23))
    assert b60["ramp"]["min"] == 6  # round(10 * 0.6)
    assert b60["ramp"]["max"] == 7  # round(12 * 0.6)


def _rock(i):
    return {
        "name": f"Rock {i}",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}.",
        "produced_mana": ["C"],
    }


def test_lands_row_is_the_passed_band_never_a_rederivation():
    # ADR-0041 (finished): the "lands" row IS mana_audit's band. A re-derivation
    # from this call's own ramp tally over the passed records (12 rocks here would
    # once have derived [38, 41] on its own) no longer exists; the passed band is
    # the row, and omitting it is a TypeError, never a silently different band.
    records = [_rock(i) for i in range(12)]
    b = slot_budgets(records, deck_size=100, land_band=(50, 60))
    assert b["lands"]["min"] == 50
    assert b["lands"]["max"] == 60
    assert b["ramp"]["current"] == 12
    with pytest.raises(TypeError):
        slot_budgets(records, deck_size=100)  # type: ignore[call-arg]


def test_role_classification_folds_counterspells_into_interaction():
    assert "lands" in role_of(FOREST)
    assert "ramp" in role_of(LLANOWAR)
    assert "interaction" in role_of(MURDER)
    assert "interaction" in role_of(COUNTERSPELL)  # counterspell folds into interaction
    # Task #83: card-draw converted to a structural view (signal_keys +
    # concept, no patterns arm), which needs a real oracle_id to resolve —
    # the synthetic DIVINATION dict (no oracle_id) degrades to no-match,
    # same as any other structural-view preset against a synthetic
    # fixture. Route through the committed testkit snapshot instead.
    test_card_ir("Divination")
    assert "card_draw" in role_of(test_card("Divination"))
    assert "board_wipe" in role_of(WRATH)


def test_edicts_and_pacify_auras_count_as_interaction():
    # role_of is the universal coverage fallback, so forced-sacrifice (edicts) must
    # register as interaction. Fleshbag (creature-edict) was missed.
    test_card_ir("Fleshbag Marauder")  # seeds the crosswalk trees memo
    assert "interaction" in role_of(FLESHBAG)
    # Over-fire guards: a sacrifice COST (Viscera Seer) and a creature with a "can't
    # attack" DRAWBACK on itself (Lupine Prototype) are not removal.
    assert "interaction" not in role_of(VISCERA)
    assert "interaction" not in role_of(LUPINE)
    # Task #86 (the `removal` preset's structural-view flip) briefly dropped
    # pacify auras out of `interaction` — the 9-key signal_keys union
    # `removal` reads has no lane for "neutralizes a permanent without
    # destroying/exiling/countering/bouncing/fighting/-X'ing it" (Pacifism
    # structurally reads as `enchantments_matter`, not a removal-family
    # effect — correct routing, not a lane bug). Task #87 restores the
    # credit via the dedicated `pacify-aura` preset (signal_keys=
    # ("pacify_makers",)) — see roles.py's `_INTERACTION_PRESETS` comment.
    test_card_ir("Pacifism")  # seeds the crosswalk trees memo
    assert "interaction" in role_of(test_card("Pacifism"))
    test_card_ir("Arrest")
    assert "interaction" in role_of(test_card("Arrest"))
    # Over-fire guard (task #87): the "Rage"/"Vow" cycles pump the creature
    # they restrict (a combat ENABLER, not a neutralizer) — see
    # crosswalk_signals._pacify_aura_compensates's own docstring. (Cagemail:
    # "gets +2/+2 and can't attack" — no OTHER interaction-family signal
    # co-occurs, unlike Undying Rage's own self-return-to-hand bounce_tempo.)
    test_card_ir("Cagemail")
    assert "interaction" not in role_of(test_card("Cagemail"))


def test_interaction_excludes_infect_creatures_and_graveyard_recursion():
    # The interaction TEMPLATE role is "targeted removal + counterspells" (budgets
    # docstring). Two over-fires inflated it: (1) the creature-removal preset's
    # Fight/Infect/Wither KEYWORDS tagged static combat creatures (CR 702.90a infect is
    # a static combat ability, not spot removal); (2) the removal/bounce "return target
    # permanent ... hand" regexes matched graveyard recursion ("return target permanent
    # CARD from your graveyard"). Both must be excluded.
    blighted_agent = _text_only("Blighted Agent")
    swarmlord = _text_only("Phyrexian Swarmlord")
    unnatural_restoration = _text_only("Unnatural Restoration")
    assert "interaction" not in role_of(blighted_agent)
    assert "interaction" not in role_of(swarmlord)
    assert "interaction" not in role_of(unnatural_restoration)
    # Genuine targeted removal / bounce still counts. `removal`/`bounce` are
    # structural views (task #86 / task #83) — real testkit records.
    test_card_ir("Boomerang")  # seeds the crosswalk trees memo
    test_card_ir("Prey Upon")  # seeds the crosswalk trees memo
    assert "interaction" in role_of(MURDER)
    assert "interaction" in role_of(test_card("Boomerang"))
    assert "interaction" in role_of(test_card("Prey Upon"))


def test_protection_is_advisory_not_a_counted_role():
    # Counterspell counts as both interaction (template) AND protection (Tier-2 flag):
    # the `protects-board` preset protects() reads includes `counter_control`.
    assert protects(COUNTERSPELL) is True
    assert protects(MURDER) is False
    assert "protection" not in role_of(COUNTERSPELL)  # never a counted role


@pytest.mark.parametrize(
    "name",
    [
        # A protective keyword given to something else of yours (CR 702.11b
        # hexproof, 702.12b indestructible, 702.16b protection, 702.18a shroud).
        "Swiftfoot Boots",  # equipped creature
        "Avacyn, Angel of Hope",  # "other permanents you control"
        "Darksteel Forge",  # artifacts you control
        "Sterling Grove",  # other enchantments you control
        "Tamiyo's Safekeeping",  # target permanent you control
        "Apostle's Blessing",  # a ChooseOneOf branch's grant to the target
        "Boros Charm",  # one mode of three
        "Leyline of Sanctity",  # "You have hexproof" (CR 702.11c)
        "Shalai, Voice of Plenty",  # you, and other creatures you control
        # Saves for something else (CR 701.19a, 702.26b, 615.1).
        "Regenerate",
        "Teferi's Protection",
        "Fog",
        # Umbra armor shields the enchanted permanent (CR 702.89a).
        "Hyena Umbra",
        # Pillowfort: attack taxes, bans and limits on attacking you.
        "Ghostly Prison",
        "Silent Arbiter",
        "Crawlspace",
        # Redirect answers (CR 115.7) and counterspells (CR 701.6a).
        "Misdirection",
        "Deflecting Swat",
        "Counterspell",
        # Ledgered bridges: the protective clause is parked by phase.
        "Umbra Mystic",  # "Auras attached to permanents you control have umbra armor"
        "Dauntless Bodyguard",  # "The chosen creature gains indestructible"
        "Akiri, Fearless Voyager",
        "Blinding Powder",
        "Ajani Steadfast",  # its emblem's prevention shield
        "Emissary of Grudges",
        "Assault Suit",
        "Nick Fury, Spymaster",
        # Defensive neutralisers: damage an opponent's object would deal is
        # prevented (CR 615.1).
        "Resistance Fighter",
        "Kiora, the Crashing Wave",
        "Dovin, Hand of Control",
        # Our walk: an ability redirect, a back-referenced creature, umbra armor.
        "Reroute",
        "Doors of Durin",
        "Maze's Mantle",
        "Dog Umbra",
        "Estrid, the Masked",
        "Orzhov Advokist",
        "The Second Doctor",
        "Willie Lumpkin, Postman",
        # Spell thieves answer removal like a counterspell (Dan, 2026-10-08).
        "Commandeer",
        "Aethersnatch",
        "Perplexing Chimera",
        # A granted combat-damage prevention neutralising an attacker (CR 615.1).
        "Sokrates, Athenian Teacher",
        # Damage can't take your life below 1 (a replacement, CR 614.1a).
        "Angel's Grace",
        "Angel of Grace",
        "Gore Vassal",  # "regenerate it" — aimable at your own creature
    ],
)
def test_protection_protects_your_board_or_you(name):
    assert protects(test_card(name)) is True


@pytest.mark.parametrize(
    "name",
    [
        # Protects only itself — not your board.
        "Darksteel Reactor",
        "Carnage Tyrant",
        "Dragonlord Ojutai",  # "~ has hexproof as long as it's untapped"
        "Fleecemane Lion",  # monstrous: it has hexproof and indestructible
        "Thrun, the Last Troll",  # "{1}{G}: Regenerate ~"
        "Frenetic Efreet",  # its own coin-flip phase-out
        # "Prevent all damage that would be dealt by enchanted creature": a
        # pacifying Aura neutralises the creature, it doesn't protect yours.
        "Temporal Isolation",
        # A copy spell changes the COPY's targets, not an answer.
        "Twincast",
        "Murder",
        # Phasing out an opponent's creature indefinitely is removal.
        "Oubliette",
        # A shield over every player's objects alike protects no one's board.
        "Crumbling Sanctuary",
        "Plated Pegasus",
        # The keyword comes with animating the permanent, not shielding it.
        "Avalanche Caller",
        "Sylvan Awakening",
        "Kamahl, Heart of Krosa",
        "Wrenn and Realmbreaker",
        "Kamahl's Will",
        "Sparkshaper Visionary",
    ],
)
def test_protection_excludes_self_only_and_non_protection(name):
    assert protects(test_card(name)) is False


def test_protection_has_no_text_degrade():
    # A card the signal path can't see is not protection (unlike is_ramp, which
    # degrades to ramp_by_text): the signal path never guesses from text.
    synthetic = {
        "name": "Test Shield",
        "type_line": "Instant",
        "oracle_text": "Target creature you control gains indestructible until end "
        "of turn.",
    }
    assert protects(synthetic) is False


def test_current_counts_reflect_deck():
    # Task #83: see test_role_classification_folds_counterspells_into_interaction
    # for why DIVINATION routes through the testkit snapshot here.
    test_card_ir("Divination")
    b = slot_budgets(
        [FOREST, LLANOWAR, MURDER, test_card("Divination"), WRATH],
        deck_size=100,
        land_band=_BAND,
    )
    assert b["lands"]["current"] == 1
    assert b["ramp"]["current"] == 1
    assert b["card_draw"]["current"] == 1
    assert b["board_wipe"]["current"] == 1
    assert b["interaction"]["current"] >= 1


def test_deviation_signs_short_in_band_and_over():
    # 1 ramp source against a 10-12 band → short by 9.
    short = slot_budgets([LLANOWAR], deck_size=100, land_band=_BAND)
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
    inband = slot_budgets(rocks, deck_size=100, land_band=_BAND)
    assert inband["ramp"]["deviation"] == 0
    assert inband["ramp"]["remaining"] == 0
    # 15 ramp sources → over the 12 ceiling → +3.
    over = slot_budgets(rocks + rocks[:3], deck_size=100, land_band=_BAND)
    assert over["ramp"]["deviation"] == 3


def test_shape_scales_control_interaction_up():
    flat = slot_budgets([], deck_size=100, land_band=_BAND, shape=None)
    control = slot_budgets([], deck_size=100, land_band=_BAND, shape="control")
    assert flat["interaction"]["max"] == 12
    assert control["interaction"]["min"] == 12
    assert control["interaction"]["max"] == 15
    # Aggro trims wraths.
    aggro = slot_budgets([], deck_size=100, land_band=_BAND, shape="aggro")
    assert aggro["board_wipe"]["max"] == 2


# ── card_draw via Card IR (ADR-0027, A3) ─────────────────────────────────────
# role_of resolves card_draw from the candidate's IR ``draw`` category when present
# (the ``_text_only`` fixtures above carry no oracle_id, so they exercise the
# preset fallback). These exercise the structured ``_ir_draws`` classifier directly.


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


def test_role_of_unions_card_draw_preset_for_nested_draw_for_each():
    """task #93: ``_ir_draws`` only tags a whole-ability's DIRECT effect
    chain, so a ``draw_for_each`` reached only through a nested branch —
    Truth or Consequences' Will-of-the-council Vote branch ("For each
    truth vote, draw a card.") — never sets ``category="draw"`` on the
    compat IR at all, even though the crosswalk's ``card-draw`` preset
    (``card_draw_engine`` + ``draw_for_each`` since task #86) correctly
    fires. ``role_of`` must union the preset in unconditionally (not just
    as the no-IR fallback) so this class isn't budget-invisible."""
    ir = test_card_ir("Truth or Consequences")
    assert _ir_draws(ir) is False  # the compat-IR walk alone still misses it
    assert "card_draw" in role_of(test_card("Truth or Consequences"))


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
    from mtg_utils._analysis.roles import _ir_recursion_only

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


# ── per-family templates ──────────────────────────────────────────────────────


def _creature(i, cmc):
    return {
        "name": f"Beast {i}",
        "type_line": "Creature — Beast",
        "oracle_text": "",
        "cmc": float(cmc),
    }


def test_template_default_is_the_commander_rows_with_labels():
    b = slot_budgets([], deck_size=100, land_band=_BAND)
    assert list(b) == ["lands", "ramp", "card_draw", "interaction", "board_wipe"]
    assert b["ramp"]["label"] == "Ramp"
    assert all(row["advisory"] is False for row in b.values())
    assert template_for("commander").base_size == 100


def test_constructed_template_is_its_own_bands_not_a_scaled_commander():
    b = slot_budgets(
        [], deck_size=60, land_band=(22, 24), template=CONSTRUCTED_TEMPLATE
    )
    assert list(b) == ["lands", "interaction", "card_draw", "creatures"]
    assert (b["interaction"]["min"], b["interaction"]["max"]) == (4, 12)
    assert "ramp" not in b
    assert "board_wipe" not in b
    assert b["lands"]["min"] == 22  # the passed band, never the template's
    assert b["creatures"]["advisory"] is True
    assert b["creatures"]["label"] == "Creatures (type line)"


def test_constructed_interaction_counts_a_sweeper_and_creatures_by_type_line():
    records = [WRATH, MURDER, COUNTERSPELL, _creature(1, 2), _creature(2, 3)]
    b = slot_budgets(
        records, deck_size=60, land_band=(22, 24), template=CONSTRUCTED_TEMPLATE
    )
    assert b["interaction"]["current"] == 3  # Wrath folds into interaction
    assert b["creatures"]["current"] == 2


def test_constructed_shape_bands_scale_by_archetype():
    aggro = slot_budgets(
        [],
        deck_size=60,
        land_band=(20, 22),
        shape="aggro",
        template=CONSTRUCTED_TEMPLATE,
    )
    control = slot_budgets(
        [],
        deck_size=60,
        land_band=(24, 26),
        shape="control",
        template=CONSTRUCTED_TEMPLATE,
    )
    assert aggro["creatures"]["min"] > control["creatures"]["max"]
    assert control["interaction"]["min"] > aggro["interaction"]["max"]


def test_limited_template_rows_and_curve_buckets():
    records = [_creature(i, 2) for i in range(5)] + [_creature(9, 6), MURDER]
    b = slot_budgets(
        records, deck_size=40, land_band=(16, 17), template=LIMITED_TEMPLATE
    )
    assert list(b) == [
        "lands",
        "creatures",
        "interaction",
        "two_drops",
        "three_drops",
        "six_plus",
    ]
    assert b["creatures"]["current"] == 6
    assert b["two_drops"]["current"] == 5
    assert b["six_plus"]["current"] == 1
    assert (b["creatures"]["min"], b["creatures"]["max"]) == (14, 17)
    assert b["interaction"]["current"] == 1


def test_template_scales_from_its_own_base_size():
    # An 80-card (Yorion) constructed deck scales 60-card bands by 4/3, not by 0.8
    # of a Commander deck.
    b = slot_budgets(
        [], deck_size=80, land_band=(29, 32), template=CONSTRUCTED_TEMPLATE
    )
    assert (b["interaction"]["min"], b["interaction"]["max"]) == (5, 16)


def test_template_fills_is_the_one_membership_read():
    assert CONSTRUCTED_TEMPLATE.fills("interaction", WRATH)
    assert CONSTRUCTED_TEMPLATE.fills("creatures", _creature(1, 2))
    assert not CONSTRUCTED_TEMPLATE.fills("creatures", MURDER)
    assert not CONSTRUCTED_TEMPLATE.fills("ramp", LLANOWAR)  # no such row


def test_unknown_family_fails_loud():
    with pytest.raises(ValueError, match="no template"):
        template_for("cube")
