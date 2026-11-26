"""Iteration-3 recast-loop lanes (mining-2 synthesis, lane-gap batch).

The v2-panel mining sweep's biggest un-priced miss cluster: one-shot ETB
value permanents under commanders that repeatably re-deliver them
(Muldrotha's 13-card cluster, Meren's re-arm trio, Chulane's bounce
package). Enters triggers fire on EVERY entry (CR 603.6a), so the pair is
(one-shot clause) x (recasts per game).

* self_etb_payload — a self-ETB trigger whose payload is a VALUE concept
  (destroy / draw / sacrifice / damage / discard / mill / tutor / exile):
  Shriekmaw, Mulldrifter, Fleshbag Marauder. Wider than wants_cloning's
  clone-worthy gate (has_self_etb_value), which stays untouched.

Every case runs the production ``extract_signals`` over the REAL
committed-snapshot IR (ADR-0027/0039) — no synthetic trees.
"""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_card_ir, test_signals


def _idents_of(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Shriekmaw", True),  # ETB destroy (the removal half v1 missed)
        ("Ravenous Chupacabra", True),  # ETB destroy
        ("Reclamation Sage", True),  # ETB artifact/enchantment destroy
        ("Mulldrifter", True),  # ETB draw
        ("Fleshbag Marauder", True),  # ETB edict sacrifice
        ("Acidic Slime", True),  # ETB destroy
        ("Grizzly Bears", False),  # no ETB trigger at all
        ("Impact Tremors", False),  # ETB OBSERVER, not a self-ETB carrier
    ],
)
def test_self_etb_payload_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("self_etb_payload|you|" in _idents_of(name)) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Arm 1: graveyard-cast permission static.
        ("Muldrotha, the Gravetide", True),
        # Arm 2: reanimation trigger (graveyard target -> battlefield).
        ("Meren of Clan Nel Toth", True),
        ("Sun Titan", True),
        # Arm 3: activated self-bounce toward replay.
        ("Chulane, Teller of Tales", True),
        # Not recast engines.
        ("Krenko, Mob Boss", False),
        ("Talrand, Sky Summoner", False),
        # A graveyard-cast permission over instants/sorceries only re-delivers
        # spells, never a permanent (CR 110.4a) — arm 1's near misses.
        ("Maestros Ascendancy", False),
        ("Kess, Dissident Mage", False),
    ],
)
def test_permanent_recast_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("permanent_recast|you|" in _idents_of(name)) is expected


@pytest.mark.parametrize(
    ("name", "subject", "expected"),
    [
        # A permanent card from a graveyard onto the battlefield.
        ("Argivian Restoration", "reanimate", True),  # an artifact card
        ("Animate Dead", "reanimate", True),  # the Aura's own reattach
        ("Glimpse the Core", "reanimate", True),  # a Cave card (a land subtype)
        ("Teyo, Aegis Adept", "reanimate", True),  # the emblem's end-step return
        ("Revival Experiment", "reanimate", True),  # a recovered residue
        ("Reassembling Skeleton", "reanimate", False),  # returns only itself
        ("Raise Dead", "reanimate", False),  # to hand, not the battlefield
        ("Regrowth", "reanimate", False),  # "target card" may be an instant
        # A permanent you control returned to your hand to cast again.
        ("Whitemane Lion", "replay", True),
        ("Kor Skyfisher", "replay", True),
        # A bounce land returns only a land: no other enters value to replay.
        ("Azorius Chancery", "replay", False),
        # Reanimation of a card an earlier clause chose (a back-reference).
        ("Jolted Awake", "reanimate", True),
        ("Revivify", "reanimate", True),
        ("Blinking Spirit", "replay", False),  # returns only itself
        ("Unsummon", "replay", False),  # any creature: tempo
        ("Zndrsplt's Judgment", "replay", False),  # each player returns their own
        # A land card back from your graveyard, or played from it.
        ("Life from the Loam", "land", True),  # to hand
        ("Glimpse the Core", "land", True),  # a Cave card onto the battlefield
        ("Crucible of Worlds", "land", True),  # play lands from your graveyard
        ("Sacred Ground", "land", True),  # the ledgered Unknown-mode event
        ("Raise Dead", "land", False),  # a creature card
        ("Argivian Restoration", "land", False),  # an artifact card
    ],
)
def test_permanent_recast_doer_subjects(name, subject, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert (f"permanent_recast|you|{subject}" in _idents_of(name)) is expected


def test_recast_doers_open_no_avenue_and_feed_the_self_etb_page():
    """A one-shot re-delivery feeds a self-ETB card's page and opens no avenue of
    its own (``signal_keys.PAGE_ONLY_SUBJECTS``), and is no voltron plan."""
    from mtg_utils._analysis.signal_base import Signal
    from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for
    from mtg_utils.testkit import test_card

    for subject in ("reanimate", "replay", "land"):
        sig = Signal("permanent_recast", "you", subject, "", "x", "high")
        assert avenue_spec_for(sig) is None
    serve = SPECS[("self_etb_payload", "you")].serve
    assert serve.oracle is None
    for name in ("Whitemane Lion", "Argivian Restoration", "Ephemerate", "Sun Titan"):
        test_card_ir(name)
        assert serve.matches(test_card(name)), name
    for name in ("Reassembling Skeleton", "Unsummon", "Raise Dead"):
        test_card_ir(name)
        assert not serve.matches(test_card(name)), name
    # Whitemane Lion's replay is no other plan: it keeps its carrier membership.
    assert "voltron_matters|you|carrier" in _idents_of("Whitemane Lion")


def test_recast_row_fires_and_gates():
    from mtg_utils._analysis.pair_reads import build_pair_context, pair_score
    from mtg_utils.testkit import test_card

    def ctx(commander):
        test_card_ir(commander)
        return build_pair_context([test_card(commander)], [])

    # Shriekmaw x Muldrotha: the loop the mining sweep named first.
    test_card_ir("Shriekmaw")
    _s, rows = pair_score(test_card("Shriekmaw"), ctx("Muldrotha, the Gravetide"))
    assert any(r["pair"] == "etb_value_x_recast_commander" for r in rows), rows
    # Mulldrifter x Meren: reanimation arm.
    test_card_ir("Mulldrifter")
    _s2, rows2 = pair_score(test_card("Mulldrifter"), ctx("Meren of Clan Nel Toth"))
    assert any(r["pair"] == "etb_value_x_recast_commander" for r in rows2), rows2
    # No recast anchor -> no row.
    _s3, rows3 = pair_score(test_card("Shriekmaw"), ctx("Krenko, Mob Boss"))
    assert not any(r["pair"] == "etb_value_x_recast_commander" for r in rows3), rows3


# ── iteration-4: own-target spells (Feather's miss file) ─────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ephemerate", True),  # "target creature you control"
        ("Feat of Resistance", True),
        ("Fall of the Hammer", True),  # first target is your own creature
        ("Murder", False),  # any-target removal
        # 4b widening: a beneficial targeted pump is own-directed in
        # practice (the strict arm alone left Feather's top-250 flat).
        ("Infuriate", True),
        ("Defiant Strike", True),
        ("Shock", False),  # targeted damage, not a pump
        # only the word "target" targets (CR 115.1, 115.10a): a mass effect's
        # population, a sacrifice (CR 701.21a: the player's own choice) and a
        # choice made on resolution are no target of yours
        ("Basri's Solidarity", False),  # "each creature you control"
        ("Scale Blessing", False),
        ("Part the Veil", False),  # "all creatures you control"
        ("Ghostway", False),
        ("Liliana's Triumph", False),  # "each opponent sacrifices"
        ("Clip Wings", False),
        ("Balance", False),
        ("Clarion Ultimatum", False),  # "Choose five permanents you control"
        # one target per opponent is that opponent's ("that player controls")
        ("Mega Flare", False),
        ("Shellshock", False),
        # a real "target creature you control" beside a mass effect still counts
        ("Strength of the Coalition", True),
        # earthbend's own rule targets a land you control (CR 701.66a)
        ("Earthbending Lesson", True),
        # the beneficial arm's sign gate reads "-X" and a negated count too
        ("Death Wind", False),
        ("Sickening Shoal", False),
        ("Flunk", False),
        # Dan's ruling (2026-11-26): a GenericEffect pump and a P/T-raising
        # counter on the spell's one target creature are beneficial too
        ("Angelic Blessing", True),
        ("Brute Strength", True),
        ("Battlegrowth", True),
        ("Travel Preparations", True),
        # a -1/-1 counter is no beneficial boost
        ("Blight Rot", False),
        # a cycling trigger's target is the ability's, not the spell's
        ("Decree of Savagery", False),
        # "the chosen creatures get +X/+X": an "it" back to a resolution choice
        ("Spry and Mighty", False),
        # the opponent chooses a creature they control
        ("Evangelize", False),
        # a boost on the creature the same spell gains control of is aimed at
        # an opponent's creature (the coordinator's call, 2026-11-26)
        ("Goatnap", False),
        ("Mark of Mutiny", False),
        ("Price of Loyalty", False),
        # an untap-and-pump with no control change stays beneficial
        ("Act of Heroism", True),
        # a GenericEffect pump on "it" (the static read through its owner)
        ("Aim High", True),
        ("Spidery Grasp", True),
        # ... but not on the creature the spell steals
        ("Unwilling Recruit", False),
        # an ability's target is not the spell's (CR 115.1a): a graveyard
        # activation, a delayed trigger the spell creates
        ("Wither and Bloom", False),
        ("Fatal Fissure", False),
        # a boost on a creature the spell destroys anyway (the coordinator's
        # call); a conditional destroy stays a boost
        ("Blood Frenzy", False),
        ("Berserk", True),
        # +N/-M lowers toughness: not beneficial
        ("Lash of Malice", False),
        # a counter that raises no P/T
        ("Boon of Safety", False),
        # forecast is an ability, not the spell
        ("Steeling Stance", False),
        # support's keyword rule targets (kept)
        ("Press into Service", True),
    ],
)
def test_own_target_spell_emission(name, expected):
    test_card_ir(name)  # snapshot residency (parametrize -> bare variable)
    assert ("own_target_spell|you|" in _idents_of(name)) is expected


def test_own_target_row_fires_and_gates():
    from mtg_utils._analysis.pair_reads import build_pair_context, pair_score
    from mtg_utils.testkit import test_card

    test_card_ir("Feather, the Redeemed")
    ctx = build_pair_context([test_card("Feather, the Redeemed")], [])
    test_card_ir("Ephemerate")
    _s, rows = pair_score(test_card("Ephemerate"), ctx)
    assert any(r["pair"] == "own_target_spell_x_rebate_commander" for r in rows), rows
    test_card_ir("Krenko, Mob Boss")
    ctx2 = build_pair_context([test_card("Krenko, Mob Boss")], [])
    _s2, rows2 = pair_score(test_card("Ephemerate"), ctx2)
    assert not any(r["pair"] == "own_target_spell_x_rebate_commander" for r in rows2), (
        rows2
    )


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Mega Flare", "Shellshock"])
def test_per_opponent_target_controller_canary(name):
    """ "For each opponent, choose up to one target creature that player
    controls": phase types the target ``controller: You`` inside a body it
    repeats for each opponent. ``crosswalk.effect_owner_targets_per_opponent``
    reads the repeat, so the target is that opponent's. Fails once phase types
    the controller; then the repeat read can stay or go."""
    from mtg_utils.testkit import test_phase_records

    (rec,) = test_phase_records(name)
    bodies = []
    body = rec["abilities"][0]
    while isinstance(body, dict):
        bodies.append(body)
        body = body.get("sub_ability")
    (choose,) = [b for b in bodies if b["effect"]["type"] == "TargetOnly"]
    assert choose["effect"]["target"]["controller"] == "You", (
        f"per-opponent target controller: RETIRE-READY — phase types {name}'s "
        "target as that player's. Delete this canary."
    )
    assert choose["repeat_for"]["qty"]["type"] == "PlayerCount"


def test_effect_targets_keeps_a_spell_target_and_drops_a_chosen_one():
    """``crosswalk.effect_targets`` builds on ``acts_on_a_group``: Redirect's
    ``ChangeTargets`` ("change the targets of target spell", scoped ``All``)
    stays a target; Spry and Mighty's pump of "the chosen creatures" is an "it"
    back to a choice made on resolution, no target."""
    from mtg_utils._card_ir.crosswalk import effect_targets, tag_of
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    def reads(name, tag):
        return {
            effect_targets(u.node, c.node)
            for t in trees_for(test_card(name))
            for u in t.units
            for c in u.effects
            if tag_of(c.node) == tag
        }

    assert reads("Redirect", "ChangeTargets") == {True}
    assert reads("Spry and Mighty", "Pump") == {False}
