"""The shared effect walk over phase's branch shapes (``core._walk_effects`` /
``reads.effect_child_items``): an "otherwise" ``else_ability``, a ``ChooseOneOf``'s
``branches``, a ``RollDie``'s ``results`` rows and a ``Vote``'s
``per_choice_effect`` — which the walk reads, which signals rest on a branch
another player picks or only a natural 20 reaches (served LOW, off the certain
records ``_card_ir.branches.certain_records`` prunes), and the owner reads
(``effect_player_reach`` / ``effect_owner_player_scope``) through them.

Every card is a real card from the committed snapshot (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.branches import (
    BRANCH_MISREADS,
    apply_misreads,
    certain_records,
    resolve_path,
)
from mtg_utils._card_ir.crosswalk import (
    ConceptTree,
    effect_player_reach,
    effects_exclusive,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _tree(name: str) -> ConceptTree:
    trees = trees_for(test_card(name))
    assert trees, f"{name}: no trees"
    return trees[0]


def _idents(name: str) -> set[tuple[str, str]]:
    return {(s.key, s.scope) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


def _reach_of(name: str, tag: str) -> set[str | None]:
    """``effect_player_reach`` of every ``tag`` node anywhere on the card, read
    from its unit root by a deep walk."""
    tree = _tree(name)
    return {
        effect_player_reach(u.node, n)
        for u in tree.units
        for n in u.iter_typed()
        if tag_of(n) == tag
    }


def _confidence(name: str, key: str, scope: str) -> str | None:
    hits = {
        s.confidence for s in test_signals(name) if (s.key, s.scope) == (key, scope)
    }
    assert len(hits) <= 1, hits
    return next(iter(hits), None)


# ── What the walk reads ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "key", "scope"),
    [
        # ChooseOneOf branches, the controller's choice: phase v0.104.0 moved
        # these "+1/-1 or -1/+1" pumps into branches.
        ("Endling", "self_pump", "you"),
        ("Endling", "debuff_makers", "any"),
        ("Shorecrasher Elemental", "self_pump", "you"),
        ("Pemmin's Aura", "pump_makers", "you"),
        ("Liliana of the Dark Realms", "scaling_pump", "you"),
        # d20 results rows.
        ("Farideh's Fireball", "symmetric_damage_each", "each"),
        ("Myrkul's Edict", "edict_makers", "opponents"),
        ("Power of Persuasion", "bounce_tempo", "you"),
        # an "otherwise" branch.
        ("Sphinx Sovereign", "lifeloss_makers", "opponents"),
    ],
)
def test_walk_reads_controller_branches(name, key, scope):
    assert (key, scope) in _idents(name)


def test_owner_reads_descend_vote_and_else_branches():
    """``_find_owner_wrapper`` descends a vote's ``per_choice_effect`` (Tyrant's
    Choice's "each opponent sacrifices") and an ``else_ability`` (Sphinx
    Sovereign's "Otherwise, each opponent loses 3 life"), so the branch
    wrapper's ``player_scope`` is read."""
    assert _reach_of("Tyrant's Choice", "Sacrifice") == {"opponents"}
    assert _reach_of("Sphinx Sovereign", "LoseLife") == {"opponents"}


# ── Confidence: Dan's verdicts (2026-10-09) ──────────────────────────────────


@pytest.mark.parametrize(
    ("name", "key", "scope"),
    [
        # Dan's verdict: a vote's outcome counts as something the card does.
        ("Tyrant's Choice", "edict_makers", "opponents"),
        ("Magister of Worth", "mass_removal", "you"),
        # friend-or-foe is the controller's labelling (Pir's Whim's ruling):
        # "each foe sacrifices" is an edict, "each friend searches" ramp.
        ("Pir's Whim", "edict_makers", "opponents"),
        ("Pir's Whim", "ramp", "you"),
        # die-roll rows with a real range.
        ("Contact Other Plane", "card_draw_engine", "you"),
        # 2-9 is a real range: high, though the 20 row is low.
        ("Treasure Chest", "treasure_makers", "you"),
    ],
)
def test_controller_decided_branches_count_high(name, key, scope):
    assert _confidence(name, key, scope) == "high"


@pytest.mark.parametrize(
    ("name", "key", "scope"),
    [
        # a villainous choice is the opponent's (CR 701.55a): every read of its
        # branches, the raw-node lanes' too.
        ("Dr. Eggman", "opponent_discard", "opponents"),
        ("Dr. Eggman", "cheat_into_play", "you"),
        ("Damocles Base, Sword of Kang", "lifeloss_makers", "opponents"),
        ("Damocles Base, Sword of Kang", "edict_makers", "opponents"),
        ("Midnight Crusader Shuttle", "edict_makers", "opponents"),
        ("Sycorax Commander", "opponent_discard", "opponents"),
        ("Sycorax Commander", "direct_damage", "you"),
        # "each opponent may sacrifice … or discard …": each opponent chooses
        # (Osseous Sticktwister's ruling).
        ("Osseous Sticktwister", "edict_makers", "opponents"),
        ("Zoyowa Lava-Tongue", "edict_makers", "opponents"),
        # "any player may sacrifice two lands …": every player's option.
        ("Worms of the Earth", "land_sacrifice_makers", "each"),
        # "that player may pay {2} … Otherwise" (a misread registry row).
        ("Fraying Line", "mass_removal", "you"),
        # rows only a natural 20 reaches, structural reads and text tails alike.
        ("Mathise, Surge Channeler", "spell_copy_makers", "you"),
        ("Treasure Chest", "cheat_into_play", "you"),
        ("Treasure Chest", "tutor", "you"),
        ("The Deck of Many Things", "win_lose_game", "any"),
    ],
)
def test_other_players_choices_and_natural_20_rows_count_low(name, key, scope):
    assert _confidence(name, key, scope) == "low"


def test_opponents_choices_are_theirs():
    """The villainous "that opponent discards …" is the opponent's loot, not
    yours; Master of Ceremonies' Citizens hang on its opponents' choices, so
    its class tribe (Druid) doesn't open."""
    assert "discard_makers" not in _keys("Dr. Eggman")
    assert "discard_makers" not in _keys("Sycorax Commander")
    assert ("type_matters", "Druid") not in {
        (s.key, s.subject) for s in test_signals("Master of Ceremonies")
    }


def test_certain_records_prune_another_players_otherwise():
    """Zur's Weirding: "any other player may pay 2 life. If a player does, … .
    Otherwise, that player draws a card" — the Otherwise after another player's
    option is pruned from the certain records."""
    recs = test_phase_records("Zur's Weirding")
    pruned = certain_records(recs)
    assert pruned is not None
    path = ("replacements", 0, "execute", "sub_ability", "sub_ability", "else_ability")
    assert resolve_path(recs[0], path)
    assert not resolve_path(pruned[0], path)


def test_friend_or_foe_sides():
    """Friend-or-foe: the controller labels every player, themselves included
    (Pir's Whim's ruling); the lane reads a friend as your side and a foe as an
    opponent. The label is the vote's ``choices[player_scope.choice_index]``
    under ``voter_scope: ControllerLabels``."""
    assert _reach_of("Pir's Whim", "SearchLibrary") == {None}  # friends: you
    assert _reach_of("Pir's Whim", "Sacrifice") == {"opponents"}  # foes
    assert "sacrifice_outlets" not in _keys("Pir's Whim")
    # friends wheel their hands: no hand attack.
    assert "opponent_discard" not in _keys("Khorvath's Fury")
    # foes return a creature they control: nothing of yours is recast.
    assert "permanent_recast" not in _keys("Zndrsplt's Judgment")
    assert ("token_copy_makers", "you") in _idents("Zndrsplt's Judgment")


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # each player exiles off their own library and casts it.
        ("Omen Machine", "each"),
        # the owner of an unrestricted target permanent casts it.
        ("Audacious Swap", "any"),
    ],
)
def test_impulse_scope_names_who_casts(name, scope):
    assert {s.scope for s in test_signals(name) if s.key == "impulse_top_play"} == {
        scope
    }


def test_champion_drawback_stays_out_of_the_walk():
    """Champion's "sacrifice it unless you exile another creature you control"
    (CR 702.72a) is a drawback: neither its choice nor its "otherwise, sacrifice"
    branch is a self-ETB payload or a reason to clone."""
    (enters,) = [
        u for u in _tree("Changeling Hero").units if u.trigger_event == "enters"
    ]
    tags = {tag_of(c.node) for c in enters.effects}
    assert not tags & {"Sacrifice", "ChangeZone"}
    assert not {"self_etb_payload", "wants_cloning"} & _keys("Changeling Hero")


# ── Near misses the branch walk exposed ──────────────────────────────────────


def test_exclusive_branches_are_no_blink():
    """Search for Survivors: "If it's a creature card, put it onto the
    battlefield. Otherwise, exile it." The exile and the return are
    alternatives (``effects_exclusive``), so no blink; Lae'zel's Acrobatics
    exiles and returns in one d20 row, which is."""
    tree = _tree("Search for Survivors")
    (unit,) = [u for u in tree.units if u.effects]
    zone_moves = [c.node for c in unit.effects if tag_of(c.node) == "ChangeZone"]
    to_bf = [n for n in zone_moves if getattr(n, "destination", None) == "Battlefield"]
    to_exile = [n for n in zone_moves if getattr(n, "destination", None) == "Exile"]
    assert to_bf
    assert to_exile
    assert effects_exclusive(unit.node, to_bf[0], to_exile[0])
    assert "blink_flicker" not in _keys("Search for Survivors")
    assert "blink_flicker" in _keys("Lae'zel's Acrobatics")


def test_chosen_player_sacrifice_is_no_outlet():
    """Myrkul's Edict's d20 row "Choose an opponent. That player sacrifices a
    creature" names the sacrificed creature's controller as a ``ChosenPlayer``."""
    assert "sacrifice_outlets" not in _keys("Myrkul's Edict")


@pytest.mark.parametrize(
    "name",
    [
        "Aberrant Mind Sorcerer",  # a d20 row returns the chosen graveyard card
        "Loathsome Troll",  # graveyard-only activation returns this card
        "Pulse of the Fields",  # an instant returns itself from the stack (CR 110.1)
    ],
)
def test_returns_to_hand_that_are_no_bounce(name):
    assert "bounce_tempo" not in _keys(name)


def test_redrawing_the_replaced_card_is_no_draw_engine():
    """CR 614.6: a replaced draw never happens. Enduring Renewal's "Otherwise,
    draw a card" only gives back the draw it replaced; Notion Thief moves an
    opponent's draw to you, and Plagiarize's parked "if target player would
    draw" leaves the drawer unknown, so both stay engines."""
    assert "card_draw_engine" not in _keys("Enduring Renewal")
    assert "card_draw_engine" in _keys("Notion Thief")
    assert "card_draw_engine" in _keys("Plagiarize")


def test_suspected_condition_is_a_state_reference():
    """Agrus Kos's "If it's suspected, exile it. Otherwise, suspect it": the
    suspect verb is in the else branch and the condition reads the suspected
    designation (CR 701.60b). Nelly Borca's suspected-creature reference is a
    goad target, not a condition, so the verb still wins there."""
    assert "suspect_matters" in _keys("Agrus Kos, Spirit of Justice")
    assert "suspect_matters" not in _keys("Nelly Borca, Impulsive Accuser")


# ── Retirement canaries: the misread registry (``_card_ir.branches``) ────────


def _row(card: str):
    (row,) = [r for r in BRANCH_MISREADS if r.card == card]
    return row


def _dropped(card: str) -> list[object]:
    """What each of the card's registry paths resolves to in phase's record."""
    rec = test_phase_records(card)[0]
    return [resolve_path(rec, path) for path in _row(card).drop]


@pytest.mark.retirement_canary
def test_other_player_branch_misreads_canary():
    """Retirement canary for Fraying Line's registry row: phase v0.104.0 files
    "that player may pay {2}" as a ``PayCost`` the controller pays, so its
    "Otherwise" branch reads as the controller's call."""
    (rec,) = test_phase_records("Fraying Line")
    payer = resolve_path(rec, ("triggers", 1, "execute", "effect", "payer"))
    assert isinstance(payer, dict)
    assert payer.get("type") == "Controller", (
        "branches.BRANCH_MISREADS (Fraying Line): RETIRE-READY — phase no longer "
        "files the payment as the controller's. Drop its registry row (and this "
        "canary) and check its mass_removal still reads LOW."
    )
    (else_branch,) = _dropped("Fraying Line")
    assert isinstance(else_branch, dict)
    assert _confidence("Fraying Line", "mass_removal", "you") == "low"


@pytest.mark.retirement_canary
def test_phantom_choice_discard_canary():
    """Retirement canary for Osseous Sticktwister's registry row: phase v0.104.0
    parses "Then ~ deals damage … to each opponent who didn't sacrifice a
    permanent or discard a card this way" as a second choice whose branch is a
    discard."""
    (branch,) = _dropped("Osseous Sticktwister")
    assert isinstance(branch, dict)
    assert (branch.get("effect") or {}).get("type") == "Discard", (
        "branches.BRANCH_MISREADS (Osseous Sticktwister): RETIRE-READY — phase no "
        "longer reads the damage clause as a discard choice. Drop its registry row "
        "(and this canary)."
    )
    assert "discard_outlet" not in _keys("Osseous Sticktwister")


@pytest.mark.retirement_canary
def test_unnarrowed_grant_branch_canary():
    """Retirement canary for Spitting Slug's registry row: phase v0.104.0 reads
    "Otherwise, each creature blocking or blocked by this creature gains first
    strike" as every creature gaining it."""
    (else_branch,) = _dropped("Spitting Slug")
    assert isinstance(else_branch, dict)
    affected = [
        sdef.get("affected") or {}
        for sdef in (else_branch.get("effect") or {}).get("static_abilities") or ()
    ]
    assert affected
    assert any(not a.get("properties") for a in affected), (
        "branches.BRANCH_MISREADS (Spitting Slug): RETIRE-READY — phase keeps the "
        "blocking-or-blocked narrowing now. Drop its registry row (and this canary)."
    )
    assert "all_creatures_kw_grant" not in _keys("Spitting Slug")


def test_every_branch_misread_has_its_canary_and_applies():
    """``bump-phase-pin``'s graduation step runs the ``retirement_canary`` tests:
    each registry row names one here, and its paths resolve in phase's record."""
    for row in BRANCH_MISREADS:
        test = globals().get(row.canary)
        assert test is not None, f"{row.card}: no canary {row.canary}"
        assert any(m.name == "retirement_canary" for m in test.pytestmark)
        assert all(_dropped(row.card)), row.card
        if row.when == "always":
            rec = test_phase_records(row.card)[0]
            assert apply_misreads(rec) != rec
