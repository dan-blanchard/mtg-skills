"""Stage-2 consumer output-diff harness + minimal compat adapter (ADR-0035).

CI-safe and fixture-driven: strict-loads the committed crosswalk fixture
(``crosswalk_fixture_cards.json``) against the committed mirror schema, builds
the minimal compat ``Card`` (``_card_ir.compat``), and proves the four
non-Signal consumers' IR reads (``ranking`` / ``budgets`` / ``cut_check`` /
tuner ``metrics``+``bracket``) run unchanged over it — with **no** bulk /
sidecar / phase / network. The old-IR side of the corpus diff is hand-built
here (the harness mechanics under test, not projection fidelity — that is the
gated baseline run's job).
"""

from __future__ import annotations

import json
from functools import lru_cache

import pytest

from mtg_utils._card_ir.compat import CompatCoverage, compat_card
from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._deck_forge import budgets, ranking
from mtg_utils._deck_forge import crosswalk_consumer_diff as ccd
from mtg_utils._tuner.bracket import _ir_has_extra_turn
from mtg_utils._tuner.metrics import _ir_wincon
from mtg_utils.card_ir import Ability, Card, Effect, Face, Quantity
from mtg_utils.cut_check import detect_triggers

FIXTURE = "crosswalk_fixture_cards.json"


@lru_cache(maxsize=1)
def _fixture() -> dict:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return json.loads(path.read_text())


def _cards() -> dict[str, dict]:
    return _fixture()["cards"]


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _compat(name: str, cov: CompatCoverage | None = None) -> Card:
    rec = _cards()[name]
    root = strict_load_card(rec, _schema(), name=name)
    tree = build_concept_tree(root, name=name, oracle_id=rec["scryfall_oracle_id"])
    return compat_card(tree, cov)


def _effects(card: Card) -> list[Effect]:
    return [e for ab in card.all_abilities() for e in ab.effects]


# ── the adapter builds over the whole fixture corpus ──────────────────────────


def test_compat_builds_for_every_fixture_card():
    cov = CompatCoverage()
    for name in _cards():
        card = _compat(name, cov)
        assert isinstance(card, Card)
        assert card.oracle_id
        for ab in card.all_abilities():
            assert ab.kind  # never empty
            for e in ab.effects:
                assert e.category  # explicit "other", never empty/None
    # The fixture corpus exercises both sides of the accounting.
    assert cov.ported["draw"] > 0
    assert cov.ported["damage"] > 0
    assert cov.ported["make_token"] > 0
    assert any(k.startswith("tag:") for k in cov.unported)
    rows = cov.coverage_rows()
    assert all(len(r) == 3 for r in rows)
    assert {r[0] for r in rows} == set(cov.ported) | set(cov.unported)


# ── field-level mappings the consumers read ───────────────────────────────────


def test_trigger_event_upkeep_dark_confidant():
    card = _compat("Dark Confidant")
    trig = [ab for ab in card.all_abilities() if ab.kind == "triggered"]
    assert trig
    assert trig[0].trigger is not None
    assert trig[0].trigger.event == "upkeep"


def test_trigger_event_combat_damage_coastal_piracy():
    card = _compat("Coastal Piracy")
    events = [
        ab.trigger.event
        for ab in card.all_abilities()
        if ab.kind == "triggered" and ab.trigger is not None
    ]
    assert "combat_damage" in events


def test_trigger_event_etb_rename():
    card = _compat("Mulldrifter")
    events = [
        ab.trigger.event
        for ab in card.all_abilities()
        if ab.kind == "triggered" and ab.trigger is not None
    ]
    assert "etb" in events


def test_fixed_damage_amount_lightning_bolt():
    effects = [e for e in _effects(_compat("Lightning Bolt")) if e.category == "damage"]
    assert effects
    amt = effects[0].amount
    assert amt is not None
    assert (amt.op, amt.factor) == ("fixed", 3)


def test_make_token_subject_splits_core_types_from_subtypes():
    effects = [
        e for e in _effects(_compat("Krenko, Mob Boss")) if e.category == "make_token"
    ]
    assert effects
    sub = effects[0].subject
    assert sub is not None
    assert "Creature" in sub.card_types
    assert "Goblin" in sub.subtypes


def test_mass_marker_and_scope_wrath_of_god():
    effects = [e for e in _effects(_compat("Wrath of God")) if e.category == "destroy"]
    assert effects
    assert effects[0].counter_kind == "all"
    assert effects[0].scope == "each"


def test_dynamic_pump_magnitude_keeps_sign():
    # ADR-0039 step 5.5 fix: Toxic Deluge's "-X/-X" (scaled by life paid) is
    # a Variable power/toughness node, not Fixed — _pump_pt now keeps its
    # SIGN (Quantity(op="variable", factor=-1)) instead of dropping to
    # None, matching project.py's _pump_toughness/_signed_pt_mod.
    effects = [e for e in _effects(_compat("Toxic Deluge")) if e.category == "pump"]
    assert effects
    tuf = effects[0].toughness
    assert tuf is not None
    assert (tuf.op, tuf.factor) == ("variable", -1)


def test_damage_each_player_scope_reads_player_filter():
    # ADR-0039 step 5.5 fix: a DamageEachPlayer node carries NO
    # target/player/owner/recipient/valid_target field at all (only
    # player_filter), which the generic recipient-field scan never read,
    # so it defaulted to "you" — misreading Brazen Dwarf's "deals 1 damage
    # to each opponent" as SELF-damage. Matches project.py's own read
    # (verified against project_card: scope="opp").
    effects = [e for e in _effects(_compat("Brazen Dwarf")) if e.category == "damage"]
    assert effects
    assert effects[0].scope == "opp"


def test_graveyard_zone_on_raise_dead_bounce():
    effects = [e for e in _effects(_compat("Raise Dead")) if e.category == "bounce"]
    assert effects
    assert any("graveyard" in z for z in effects[0].zones)


def test_pump_mass_vs_target_split():
    # Languish (PumpAll -4/-4) is the mass ``pump`` with a signed toughness.
    languish = [e for e in _effects(_compat("Languish")) if e.category == "pump"]
    assert languish
    tuf = languish[0].toughness
    assert tuf is not None
    assert (tuf.op, tuf.factor) == ("fixed", -4)
    # ADR-0039 step 5.5 fix: single-vs-mass routes on the effect TAG alone
    # (PumpAll = mass, plain Pump = pump_target), matching project.py's
    # own tag-only ``_EFFECT_CATEGORY`` row exactly. Bile Blight ("Target
    # creature and all other creatures with the same name as that
    # creature get -3/-3") carries a plain "Pump" tag — its Typed target
    # is the SAME shape a genuine single "target creature" pump uses
    # (Giant Growth), which the OLD ``tag_of(target) in ("Typed", "Or",
    # "And")`` heuristic wrongly read as "mass" (corpus-measured: every
    # Typed-target Pump instance sampled, Bile Blight included, names
    # "target" in its own oracle text — none are a genuine no-target mass
    # anthem, which project as a SEPARATE static-role modification
    # instead — Overrun never even reaches this branch). Bile Blight is
    # now pump_target, matching legacy; its -3 toughness still carries.
    bile = [e for e in _effects(_compat("Bile Blight")) if e.category == "pump_target"]
    assert bile
    assert bile[0].toughness is not None
    assert bile[0].toughness.factor == -3
    # v0.23.0 update (task #84): phase now ALSO emits the "all other
    # creatures with the same name" sweep half as its own ``PumpAll``
    # sub-ability (an ``And(Typed(Creature, Another, SameNameAsParentTarget),
    # Not(ParentTarget))`` subject) — the tag-only route correctly reads
    # that second node as mass. Bile Blight genuinely IS a mass effect (the
    # same-name sweep is exactly how it clears a token line-up — CR 201.2a
    # name comparison; CR 611.2c one-shot continuous effect over a set the
    # effect doesn't target), so BOTH categories now coexist: the targeted
    # half stays ``pump_target``, the sweep half is the mass ``pump``.
    mass = [e for e in _effects(_compat("Bile Blight")) if e.category == "pump"]
    assert mass
    assert mass[0].toughness is not None
    assert mass[0].toughness.factor == -3
    # Giant Growth ("Target creature gets +3/+3") is the textbook single
    # target — ALSO a Typed target, ALSO now pump_target (was misrouted to
    # the mass "pump" bucket pre-fix even though its buff sign never
    # tripped budgets._ir_board_wipe's debuff-only gate).
    giant_growth = [
        e for e in _effects(_compat("Giant Growth")) if e.category == "pump_target"
    ]
    assert giant_growth
    assert not [e for e in _effects(_compat("Giant Growth")) if e.category == "pump"]


def test_unported_effect_degrades_to_other_and_is_tallied():
    cov = CompatCoverage()
    # Boros Reckoner's damage-redirect trigger parses to a GenericEffect node;
    # tag:GenericEffect stays a documented explicit miss (62% indecisive), so
    # it degrades to "other" and is tallied. (Path to Exile no longer probes
    # this path — its Shuffle node ports to "shuffle" post-exit-gate.)
    card = _compat("Boros Reckoner", cov)
    assert any(e.category == "other" for e in _effects(card))
    assert "tag:GenericEffect" in cov.unported


# ── the production consumers run unchanged over the compat card ───────────────


def test_budgets_reads_over_compat():
    assert budgets._ir_draws(_compat("Coastal Piracy"))
    assert budgets._ir_board_wipe(_compat("Wrath of God"))
    assert budgets._ir_board_wipe(_compat("Evacuation"))  # mass bounce
    assert budgets._ir_board_wipe(_compat("Languish"))  # mass -4/-4 shrink
    assert not budgets._ir_board_wipe(_compat("Lightning Bolt"))
    assert budgets._ir_recursion_only(_compat("Raise Dead"))
    assert not budgets._ir_recursion_only(_compat("Boomerang"))


def test_tuner_reads_over_compat():
    assert _ir_has_extra_turn(_compat("Time Warp"))
    assert not _ir_has_extra_turn(_compat("Lightning Bolt"))
    assert _ir_wincon(_compat("Thassa's Oracle"))
    assert not _ir_wincon(_compat("Braingeyser"))


def test_cut_check_reads_over_compat():
    rows = detect_triggers(
        {},
        trigger_types=["upkeep"],
        opponents=3,
        ir=_compat("Dark Confidant"),
    )
    assert any(
        r["matches_trigger_type"] and r["matched_type"] == "upkeep" for r in rows
    )


def test_ranking_payoff_reads_over_compat():
    # An activated board-impacting damage ability is a payoff (Walking Ballista).
    ballista = _compat("Walking Ballista")
    assert any(ranking._ability_is_payoff(ab) for ab in ballista.all_abilities())
    # A static "creatures you control get +1/+1" anthem is a payoff.
    anthem = _compat("Glorious Anthem")
    assert any(ranking._ability_is_payoff(ab) for ab in anthem.all_abilities())


# ── the corpus diff harness ───────────────────────────────────────────────────


def _bulk_rec(name: str) -> dict:
    rec = _cards()[name]
    return {
        "oracle_id": rec["scryfall_oracle_id"],
        "name": name,
        "oracle_text": rec.get("oracle_text") or "",
        "legalities": {"commander": "legal"},
    }


def _oid(name: str) -> str:
    return _cards()[name]["scryfall_oracle_id"]


# A hand-built old IR for Lightning Bolt that mirrors the compat reads — the
# two sides must AGREE on every consumer view.
_OLD_BOLT = Card(
    oracle_id="bolt",
    name="Lightning Bolt",
    faces=(
        Face(
            name="Lightning Bolt",
            abilities=(
                Ability(
                    kind="spell",
                    effects=(
                        Effect(
                            category="damage",
                            amount=Quantity(op="fixed", factor=3),
                            scope="any",
                            raw="~ deals 3 damage to any target.",
                        ),
                    ),
                ),
            ),
        ),
    ),
)

# A deliberately WRONG old IR for Time Warp (no extra_turn effect) — the
# bracket view must DISAGREE and attribute the diff to ``extra_turn``.
_OLD_WARP_EMPTY = Card(
    oracle_id="warp",
    name="Time Warp",
    faces=(Face(name="Time Warp", abilities=()),),
)


def _run_harness(names: list[str], ir_index: dict) -> dict:
    records = [_cards()[n] for n in names]
    bulk_index = {_oid(n): _bulk_rec(n) for n in names}
    return ccd.diff_corpus_consumers(
        records, bulk_index, ir_index, _schema(), commander_only=True
    )


def test_harness_join_and_skip_accounting():
    names = ["Lightning Bolt", "Time Warp"]
    ir_index = {_oid("Lightning Bolt"): _OLD_BOLT}  # Time Warp missing → skipped
    report = _run_harness(names, ir_index)
    assert report["joined"] == 1
    assert report["skipped"]["not_in_ir"] == 1
    for name in ccd.CONSUMERS:
        assert report["consumers"][name]["cards"] == 1


def test_harness_agreement_on_faithful_old_ir():
    report = _run_harness(["Lightning Bolt"], {_oid("Lightning Bolt"): _OLD_BOLT})
    for name in ccd.CONSUMERS:
        row = report["consumers"][name]
        assert (row["cards"], row["agree"]) == (1, 1), name


def test_harness_disagreement_is_counted_and_attributed():
    report = _run_harness(
        ["Lightning Bolt", "Time Warp"],
        {
            _oid("Lightning Bolt"): _OLD_BOLT,
            _oid("Time Warp"): _OLD_WARP_EMPTY,
        },
    )
    assert report["joined"] == 2
    bracket_row = report["consumers"]["bracket"]
    assert bracket_row["cards"] == 2
    assert bracket_row["agree"] == 1
    assert "extra_turn" in bracket_row["per_category"]
    assert any(e["name"] == "Time Warp" for e in bracket_row["examples"])
    # ranking/budgets/cut_check/metrics see no consumer-visible difference for
    # an empty-vs-extra_turn IR (no triggers, no payoffs, no roles).
    assert report["consumers"]["metrics"]["agree"] == 2


def test_harness_coverage_rows_present():
    report = _run_harness(["Lightning Bolt"], {_oid("Lightning Bolt"): _OLD_BOLT})
    buckets = {b for b, _, _ in report["coverage"]}
    assert "damage" in buckets


def test_report_renders_markdown():
    report = _run_harness(
        ["Lightning Bolt", "Time Warp"],
        {
            _oid("Lightning Bolt"): _OLD_BOLT,
            _oid("Time Warp"): _OLD_WARP_EMPTY,
        },
    )
    text = ccd.render_consumer_report(report)
    assert "Per-consumer agreement" in text
    assert "Compat coverage" in text
    assert "bracket" in text
    assert "extra_turn" in text


# ── exit gate: the compat adapter grown to the 341-key crosswalk surface ──────
# One assertion per structural routing BRANCH in _effect_category /
# _static_effect (the flat map rows are near-zero-risk lookups; a
# representative sample is pinned below). Every card + category was measured
# against the joined corpus before landing the mapping.


def _cats(name: str) -> set[str]:
    return {e.category for e in _effects(_compat(name))}


def test_change_zone_structural_splits():
    # library/hand → battlefield = cheat_play; graveyard → library = shuffle.
    assert "cheat_play" in _cats("Bribery")
    assert "shuffle" in _cats("Kozilek, Butcher of Truth")


def test_tap_untap_split_untap_ports_tap_stays_miss():
    assert "untap" in _cats("Act of Treason")  # SetTapState.state == Untap
    cov = CompatCoverage()
    _compat("Cryptic Command", cov)  # a Tap SetTapState — no old category
    assert "concept:tap_untap" in cov.unported


def test_extra_phase_field_split():
    assert "extra_combat" in _cats("Aurelia, the Warleader")
    assert "extra_upkeep" in _cats("Paradox Haze")


def test_give_player_counter_kind_split():
    # CR 122.1 — player-counter kinds are non-interchangeable; route on kind.
    assert "poison" in _cats("Fynn, the Fangbearer")
    assert "experience_counter" in _cats("Ezuri, Claw of Progress")
    assert "rad_counter" in _cats("Tato Farmer")
    assert "ticket_counter" in _cats("Carnival Carnivore")


def test_tag_split_concepts_route_on_tag():
    assert "clone" in _cats("Mirror Match")  # copy_token: CopyTokenBlockingAttacker
    assert "manifest" in _cats("Cloudform")  # facedown: Manifest
    assert "cloak" in _cats("Cryptic Coat")  # facedown: Cloak
    assert "goad" in _cats("Alela, Cunning Conqueror")  # goad: Goad
    assert "goad_all" in _cats("Disrupt Decorum")  # goad: GoadAll
    assert "pump_target" in _cats("Unleash Fury")  # double_pt: DoublePT


def test_flat_concept_and_tag_routes():
    assert "counter_spell" in _cats("Blue Elemental Blast")  # concept
    assert "regenerate" in _cats("River Boa")  # concept
    assert "topdeck_stack" in _cats("Brainstorm")  # put_library_position
    assert "transform" in _cats("Voldaren Bloodcaster")  # tag:Transform
    assert "emblem" in _cats("Spirit Water Revival")  # tag:CreateEmblem


def test_static_mod_tag_routes():
    assert "changeling" in _cats("Maskwood Nexus")  # AddAllCreatureTypes
    assert "combat_damage_mod" in _cats("Doran, the Siege Tower")  # AssignFromTough
    assert "characteristic_pt" in _cats("Maro")  # SetDynamicPower
