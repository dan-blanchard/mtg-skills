"""Tests for Pair reads — scored two-card mechanic interactions (ADR-0042).

A Pair read is a registered candidate ident-pattern x deck-anchor row with a
flat curated weight: per-lane additive synergy cannot price multiplicative
interactions (Mana Reflection under Zaxara serves ONE lane; the crowd plays
it because amplifier x X-commander multiplies). Rows live in one central
ledger with pins and CR-grounded rationales (the bridge-ledger discipline);
matched rows sum without decay (curation bounds stacking) into a separate
additive ``pair_score`` readout.
"""

from __future__ import annotations

import fnmatch

import pytest

from mtg_utils._deck_forge.pair_reads import (
    PAIR_READS,
    PairContext,
    build_pair_context,
    pair_score,
)
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir

# ── ledger hygiene (the bridge-ledger discipline) ────────────────────────────


def test_ledger_hygiene():
    assert PAIR_READS, "empty ledger"
    seen_ids = set()
    for row in PAIR_READS.values():
        assert row.pair_id not in seen_ids
        seen_ids.add(row.pair_id)
        assert row.anchor_kind in ("commander", "density"), row.pair_id
        assert row.weight >= 1.0, row.pair_id
        assert row.rationale.strip(), row.pair_id
        assert row.pins, row.pair_id
        assert row.candidate, row.pair_id
        for pat in (
            row.candidate
            + row.anchor
            + row.candidate_not
            + row.anchor_all
            + row.candidate_all
        ):
            assert "|" in pat, (row.pair_id, pat)  # ident-pattern shaped
        if row.anchor_kind == "density":
            assert row.threshold >= 2, row.pair_id


@pytest.mark.parametrize(
    "name",
    [
        # Every ledger pin, as literals the snapshot builder can scan.
        ("Mana Reflection"),
        ("Zendikar Resurgent"),
        ("Empty the Warrens"),
        ("Hordeling Outburst"),
        ("Ashnod's Altar"),
        ("Single Combat"),
        ("Master Warcraft"),
    ],
)
def test_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name


def test_every_pin_emits_the_candidate_pattern():
    # A pin is a real snapshot card whose OWN idents match the row's
    # candidate pattern — the convergence proof that the pattern is live.
    # Uses the ledger's own ident view (_card_idents), which adds the
    # record-derived cost-shape ident on top of the signal idents.
    from mtg_utils._deck_forge.pair_reads import _card_idents

    for row in PAIR_READS.values():
        for pin in row.pins:
            test_card_ir(pin)
            idents = _card_idents(test_card(pin))
            assert any(
                fnmatch.fnmatchcase(i, pat) for i in idents for pat in row.candidate
            ), (
                row.pair_id,
                pin,
                sorted(idents),
            )


# ── context + scoring ────────────────────────────────────────────────────────


def _zaxara_ctx() -> PairContext:
    test_card_ir("Zaxara, the Exemplary")
    return build_pair_context([test_card("Zaxara, the Exemplary")], [])


def test_amplifier_pairs_with_an_x_commander():
    # The flagship (ADR-0042): Mana Reflection under Zaxara — one lane of
    # additive credit, but the pair is the whole reason the crowd plays it.
    test_card_ir("Mana Reflection")
    score, rows = pair_score(test_card("Mana Reflection"), _zaxara_ctx())
    assert score >= 4.0, rows
    assert any(r["pair"] == "amplifier_x_commander" for r in rows)


def test_no_anchor_no_pair():
    # The same amplifier under a non-X commander pairs with nothing.
    test_card_ir("Krenko, Mob Boss")
    ctx = build_pair_context([test_card("Krenko, Mob Boss")], [])
    test_card_ir("Mana Reflection")
    score, rows = pair_score(test_card("Mana Reflection"), ctx)
    assert score == 0.0
    assert rows == []


def test_density_anchor_needs_the_threshold():
    # A combat puppeteer pairs only when the deck actually runs the goad
    # package (>= threshold emitters), not off one stray card.
    test_card_ir("Master Warcraft")
    warcraft = test_card("Master Warcraft")
    test_card_ir("Disrupt Decorum")
    goad = test_card("Disrupt Decorum")
    thin = build_pair_context([], [goad])
    thick = build_pair_context([], [goad, goad, goad])
    assert pair_score(warcraft, thin)[0] == 0.0
    assert pair_score(warcraft, thick)[0] > 0.0


def test_tribal_fodder_pairs_subject_matched():
    # Krenko's X counts GOBLINS (CR 608.2h: game information counted on
    # application) — Goblin fodder multiplies his activation, other tribes'
    # fodder does not. The row's subject-match requires the candidate's
    # token subject to equal the commander's.
    test_card_ir("Krenko, Mob Boss")
    ctx = build_pair_context([test_card("Krenko, Mob Boss")], [])
    test_card_ir("Empty the Warrens")
    _score, rows = pair_score(test_card("Empty the Warrens"), ctx)
    assert any(r["pair"] == "tribal_fodder_x_token_commander" for r in rows), rows
    # A Human/Soldier token maker feeds no Goblin count — no pair.
    test_card_ir("Bastion of Remembrance")
    _score2, rows2 = pair_score(test_card("Bastion of Remembrance"), ctx)
    assert not any(r["pair"] == "tribal_fodder_x_token_commander" for r in rows2), rows2


def test_rows_sum_without_decay_and_ride_the_readout():
    # rank_candidates: pair_score is additive on the depth sort and lands in
    # the readout. Zero-synergy candidates still surface on a strong pair.
    ctx = _zaxara_ctx()
    test_card_ir("Mana Reflection")
    reflection = test_card("Mana Reflection")
    ranked = rank_candidates(
        [reflection],
        active_signals=[Signal("xspell_matters", "you", "", "", "cmd")],
        pair_ctx=ctx,
    )
    sc = ranked[0]["score"]
    assert sc["pair_score"] >= 4.0
    assert sc["pairs"], sc


# ── Iteration 1 (ADR-0043 mining, 2026-07-17): 8 rows from 692 misses ────────
# Mined from the study's miss surface (19 adjudicators + synthesis), mapped to
# REAL idents and verified against bulk emissions. Mechanism extensions:
# multi-pattern candidate/anchor (any-of), candidate_not (a veto — the ETB
# row must not double-credit token MAKERS the fodder rows already price), and
# anchor_all (an all-of conjunction — an attack-rider pairs with a commander
# that has BOTH attack triggers AND trigger doubling, or Teysa's death
# doubling would mispair with attack riders).


@pytest.mark.parametrize(
    "name",
    [
        # Iteration-1 pins + context commanders, literals for the snapshot.
        ("Heraldic Banner"),
        ("Impact Tremors"),
        ("Roaming Throne"),
        ("Strionic Resonator"),
        ("Dictate of Erebos"),
        ("Guttersnipe"),
        ("Thousand-Year Elixir"),
        ("Hellrider"),
        ("Putrid Goblin"),
        ("Teysa Karlov"),
        ("Isshin, Two Heavens as One"),
        ("Talrand, Sky Summoner"),
        ("Muldrotha, the Gravetide"),
        ("Crucible of Fire"),
        ("Kindred Discovery"),
        ("Field of Souls"),
        ("Aetherflux Reservoir"),
        ("Seedborn Muse"),
        ("Leonin Warleader"),
    ],
)
def test_iteration1_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name


def _ctx_for(commander: str) -> PairContext:
    test_card_ir(commander)
    return build_pair_context([test_card(commander)], [])


@pytest.mark.parametrize(
    ("candidate", "commander", "row_id"),
    [
        # Anthem x swarm: per-body grants scale with the commander's token
        # output (CR 613.1g/613.4c layer-7 application to each of N bodies).
        ("Heraldic Banner", "Krenko, Mob Boss", "anthem_x_swarm_commander"),
        # ETB payoff x flood: each entering body is a separate trigger
        # instance (CR 603.2c) — X tokens per activation = X triggers.
        ("Impact Tremors", "Krenko, Mob Boss", "etb_payoff_x_flood_commander"),
        # Trigger doubler x trigger-engine commander (marquee, 4.5).
        (
            "Roaming Throne",
            "Isshin, Two Heavens as One",
            "trigger_doubler_x_trigger_commander",
        ),
        (
            "Strionic Resonator",
            "Teysa Karlov",
            "trigger_doubler_x_trigger_commander",
        ),
        # Death payoff x death engine (CR 603.6c dies triggers; the engine
        # sets deaths-per-turn).
        ("Dictate of Erebos", "Teysa Karlov", "death_payoff_x_death_commander"),
        # Cast payoff x cast-rate commander (each cast = a trigger, 603.2c).
        ("Guttersnipe", "Talrand, Sky Summoner", "cast_payoff_x_cast_commander"),
        # Untap engine x activated commander (marquee, 4.5): a second
        # activation per turn doubles commander output.
        (
            "Thousand-Year Elixir",
            "Krenko, Mob Boss",
            "untap_x_activated_commander",
        ),
        # Attack rider x attack-DOUBLING commander (anchor_all).
        (
            "Hellrider",
            "Isshin, Two Heavens as One",
            "attack_rider_x_attack_doubler_commander",
        ),
        # Self-recycling fodder x graveyard commander.
        (
            "Putrid Goblin",
            "Muldrotha, the Gravetide",
            "recursion_fodder_x_graveyard_commander",
        ),
    ],
)
def test_iteration1_rows_fire(candidate, commander, row_id):
    test_card_ir(candidate)
    _score, rows = pair_score(test_card(candidate), _ctx_for(commander))
    assert any(r["pair"] == row_id for r in rows), (candidate, commander, rows)


def test_etb_row_vetoes_token_makers():
    # Empty the Warrens IS a token maker — the fodder rows price it; the ETB
    # PAYOFF row must not double-credit the same clause (candidate_not veto).
    test_card_ir("Empty the Warrens")
    _score, rows = pair_score(
        test_card("Empty the Warrens"), _ctx_for("Krenko, Mob Boss")
    )
    assert not any(r["pair"] == "etb_payoff_x_flood_commander" for r in rows), rows


def test_attack_rider_needs_both_anchor_conditions():
    # Teysa doubles DEATH triggers, not attack triggers — an attack rider
    # must not pair with her (anchor_all: attack_matters AND trigger_doubling).
    test_card_ir("Hellrider")
    _score, rows = pair_score(test_card("Hellrider"), _ctx_for("Teysa Karlov"))
    assert not any(
        r["pair"] == "attack_rider_x_attack_doubler_commander" for r in rows
    ), rows


def test_doubler_row_skips_activated_only_commanders():
    # Krenko's engine is an ACTIVATED ability — a trigger doubler has nothing
    # to double, so the doubler row must not fire under him.
    test_card_ir("Roaming Throne")
    _score, rows = pair_score(test_card("Roaming Throne"), _ctx_for("Krenko, Mob Boss"))
    assert not any(r["pair"] == "trigger_doubler_x_trigger_commander" for r in rows), (
        rows
    )


# ── scoped_subject_gate (iteration-1 panel fix) ──────────────────────────────
# The precision panel killed subtype-scoped engines ranked into off-tribe
# decks with unanimous refuter votes: Myr Galvanizer "untaps each OTHER Myr"
# — it never touches Krenko or Urza — and Merrow Reejerey's whole engine
# runs at the deck's MERFOLK cast rate. Their idents now carry the scope
# (untap_engine|you|Myr); the gated rows only accept a scoped candidate
# whose subject matches the commander's own subtypes or a matching anchor
# ident's subject.


def test_untap_row_gates_off_tribe_scoped_untappers():
    test_card_ir("Myr Galvanizer")
    _score, rows = pair_score(test_card("Myr Galvanizer"), _ctx_for("Krenko, Mob Boss"))
    assert not any(r["pair"] == "untap_x_activated_commander" for r in rows), rows
    test_card_ir("Merrow Reejerey")
    _score2, rows2 = pair_score(
        test_card("Merrow Reejerey"), _ctx_for("Urza, Lord High Artificer")
    )
    assert not any(r["pair"] == "untap_x_activated_commander" for r in rows2), rows2
    assert not any(r["pair"] == "anthem_x_swarm_commander" for r in rows2), rows2


def test_untap_row_scoped_subject_passes_on_tribe():
    # The SAME Myr untapper under a Myr activated-ability commander is a
    # genuine engine — the gate compares against commander subtypes.
    ctx = PairContext(
        commander_idents=frozenset({"activated_ability|you|"}),
        commander_subtypes=frozenset({"myr"}),
    )
    test_card_ir("Myr Galvanizer")
    _score, rows = pair_score(test_card("Myr Galvanizer"), ctx)
    assert any(r["pair"] == "untap_x_activated_commander" for r in rows), rows


def test_anthem_row_subject_paths():
    # Goblin King's Goblin-scoped anthem matches Krenko's token_maker
    # subject (anchor-subject path) — fires; Merrow Reejerey's Merfolk
    # anthem under Krenko does not.
    test_card_ir("Goblin King")
    _score, rows = pair_score(test_card("Goblin King"), _ctx_for("Krenko, Mob Boss"))
    assert any(r["pair"] == "anthem_x_swarm_commander" for r in rows), rows
    test_card_ir("Merrow Reejerey")
    _score2, rows2 = pair_score(
        test_card("Merrow Reejerey"), _ctx_for("Krenko, Mob Boss")
    )
    assert not any(r["pair"] == "anthem_x_swarm_commander" for r in rows2), rows2


def test_unscoped_engines_unaffected_by_gate():
    # Thousand-Year Elixir ("target creature") and Heraldic Banner (chosen
    # color) carry no subtype scope — the gate must not touch them.
    test_card_ir("Thousand-Year Elixir")
    _s, rows = pair_score(
        test_card("Thousand-Year Elixir"), _ctx_for("Krenko, Mob Boss")
    )
    assert any(r["pair"] == "untap_x_activated_commander" for r in rows), rows
    test_card_ir("Heraldic Banner")
    _s2, rows2 = pair_score(test_card("Heraldic Banner"), _ctx_for("Krenko, Mob Boss"))
    assert any(r["pair"] == "anthem_x_swarm_commander" for r in rows2), rows2


# ── Iteration 2 (ADR-0043 amended protocol, 2026-07-18): 7 rows from the
# v2-panel mining sweep (20 miners + synthesis over both failure surfaces).
# New mechanism: candidate_all — an all-of conjunction on the CANDIDATE side
# (mirror of anchor_all): a count-payoff must BOTH be tribal-subject-matched
# AND carry a variable-P/T count read; a yard-stocker must BOTH tutor AND
# touch the graveyard. New plumbing: _card_idents emits a record-derived
# cost-shape ident ("xcost_spell|you|" when any face's mana cost carries
# {X}) — a cost read, not a signal lane.


@pytest.mark.parametrize(
    "name",
    [
        # Iteration-2 pins + context commanders, literals for the snapshot.
        ("Birthing Pod"),
        ("Fleshbag Marauder"),
        ("Elemental Bond"),
        ("Hellkite Charger"),
        ("Godo, Bandit Warlord"),
        ("Hardened Scales"),
        ("Ozolith, the Shattered Spire"),
        ("Battle Squadron"),
        ("Reckless One"),
        ("Buried Alive"),
        ("Unmarked Grave"),
        ("Fauna Shaman"),
        ("Sidisi, Undead Vizier"),
        ("Stroke of Genius"),
        ("Meren of Clan Nel Toth"),
        ("Wilhelt, the Rotcleaver"),
        ("Gishath, Sun's Avatar"),
        ("Atraxa, Praetors' Voice"),
    ],
)
def test_iteration2_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name


@pytest.mark.parametrize(
    ("candidate", "commander", "row_id"),
    [
        # Own-creature-death value x per-death payoff commander (CR 701.21a
        # sacrifice; CR 603.6c dies triggers): the "cost" side of the death
        # engine — every activation is effect + the commander's payoff.
        (
            "Birthing Pod",
            "Meren of Clan Nel Toth",
            "self_death_value_x_death_commander",
        ),
        (
            "Fleshbag Marauder",
            "Wilhelt, the Rotcleaver",
            "self_death_value_x_death_commander",
        ),
        # Power-threshold payoff x body-cheating commander (CR 608.2h).
        (
            "Elemental Bond",
            "Gishath, Sun's Avatar",
            "power_threshold_x_cheat_commander",
        ),
        # Extra combat x attack-trigger commander (CR 505.1a additional
        # combat phase; CR 603.2c one trigger instance per combat).
        (
            "Hellkite Charger",
            "Isshin, Two Heavens as One",
            "extra_combat_x_attack_trigger_commander",
        ),
        # Counter amplifier x counter-stream commander (CR 614.1a "instead"
        # replacement; CR 122.1).
        (
            "Hardened Scales",
            "Atraxa, Praetors' Voice",
            "counter_amplifier_x_counter_commander",
        ),
        (
            "Hardened Scales",
            "Zaxara, the Exemplary",
            "counter_amplifier_x_counter_commander",
        ),
        # Count payoff x tribal count engine (CR 608.2h): CDA P/T = tribe
        # count, subject-matched + candidate_all variable_pt.
        (
            "Battle Squadron",
            "Krenko, Mob Boss",
            "count_payoff_x_tribal_count_commander",
        ),
        ("Reckless One", "Krenko, Mob Boss", "count_payoff_x_tribal_count_commander"),
        # Yard stocker x graveyard commander (candidate_all: tutor AND
        # graveyard_matters on the same card).
        (
            "Buried Alive",
            "Muldrotha, the Gravetide",
            "yard_stocker_x_graveyard_commander",
        ),
        (
            "Fauna Shaman",
            "Muldrotha, the Gravetide",
            "yard_stocker_x_graveyard_commander",
        ),
        # {X}-cost spell x X-payoff commander (CR 601.2b: X announced once,
        # read by both the spell and the commander's trigger).
        ("Stroke of Genius", "Zaxara, the Exemplary", "xcost_spell_x_xspell_commander"),
    ],
)
def test_iteration2_rows_fire(candidate, commander, row_id):
    test_card_ir(candidate)
    _score, rows = pair_score(test_card(candidate), _ctx_for(commander))
    assert any(r["pair"] == row_id for r in rows), (candidate, commander, rows)


def test_count_payoff_needs_both_subject_and_count_read():
    # Goblin King is tribal-subject-matched to Krenko but carries no
    # variable-P/T count read — candidate_all must veto it; and Battle
    # Squadron under a Zombie commander is subject-mismatched.
    test_card_ir("Goblin King")
    _s, rows = pair_score(test_card("Goblin King"), _ctx_for("Krenko, Mob Boss"))
    assert not any(r["pair"] == "count_payoff_x_tribal_count_commander" for r in rows)
    test_card_ir("Battle Squadron")
    _s2, rows2 = pair_score(
        test_card("Battle Squadron"), _ctx_for("Wilhelt, the Rotcleaver")
    )
    assert not any(r["pair"] == "count_payoff_x_tribal_count_commander" for r in rows2)


def test_yard_stocker_needs_the_graveyard_half():
    # Sidisi, Undead Vizier tutors to HAND (no graveyard_matters ident) —
    # candidate_all vetoes; she is priced by the self-death row instead.
    test_card_ir("Sidisi, Undead Vizier")
    _s, rows = pair_score(
        test_card("Sidisi, Undead Vizier"), _ctx_for("Muldrotha, the Gravetide")
    )
    assert not any(r["pair"] == "yard_stocker_x_graveyard_commander" for r in rows)


def test_xcost_ident_is_record_derived():
    from mtg_utils._deck_forge.pair_reads import _card_idents

    test_card_ir("Stroke of Genius")
    assert "xcost_spell|you|" in _card_idents(test_card("Stroke of Genius"))
    test_card_ir("Guttersnipe")
    assert "xcost_spell|you|" not in _card_idents(test_card("Guttersnipe"))


def test_iteration2_rows_need_their_anchor():
    # The same candidates under an anchor-less commander pair with nothing.
    test_card_ir("Birthing Pod")
    _s, rows = pair_score(test_card("Birthing Pod"), _ctx_for("Krenko, Mob Boss"))
    assert not any(r["pair"] == "self_death_value_x_death_commander" for r in rows)
    test_card_ir("Elemental Bond")
    _s2, rows2 = pair_score(
        test_card("Elemental Bond"), _ctx_for("Talrand, Sky Summoner")
    )
    assert not any(r["pair"] == "power_threshold_x_cheat_commander" for r in rows2)
    test_card_ir("Hellkite Charger")
    _s3, rows3 = pair_score(test_card("Hellkite Charger"), _ctx_for("Krenko, Mob Boss"))
    assert not any(
        r["pair"] == "extra_combat_x_attack_trigger_commander" for r in rows3
    )
