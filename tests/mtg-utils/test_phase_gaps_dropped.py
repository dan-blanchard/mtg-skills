"""Phase gaps around dropped triggers: triggers phase reads with an
``Unknown`` mode, faces phase emits no record for, keyword grants the token lanes
missed, and four repo-side reads.

Each gap is pinned on the real card (``mtg_utils.testkit``). A phase workaround
retires itself: the four new ledger rows (``explore_payoff_trigger_unknown_mode``,
``foretell_payoff_trigger_unknown_mode``, ``reflexive_food_trigger_dropped``,
``modal_venture_dropped``) through ``test_bridge_ledger``'s convergence check, the
superfriends parked-text veto and the missing aftermath faces through the
``retirement_canary`` tests below.
"""

import pytest

from mtg_utils._analysis.tree_synthesis.control_stax import (
    _PARKED_YOU_OR_YOUR_PLANESWALKERS_RX,
)
from mtg_utils._card_ir.crosswalk import (
    cost_reduction_count_filters,
    counter_pred_kinds,
    defends_you,
    effect_filter,
    filter_predicates,
    keyword_token_creations,
    overload_sweep,
    tag_of,
    watches_attacks_on_you,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _tree(name: str):
    (tree,) = trees_for(test_card(name))
    return tree


# ── Unknown trigger modes and dropped modes, served by ledger rows ───────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # "Whenever a creature you control explores a land / nonland card"
        # (CR 701.44a), an Unknown mode.
        ("Nicanzil, Current Conductor", "explore_matters|you|"),
        # "Whenever you foretell a card" (CR 702.143a), an Unknown mode.
        ("Dream Devourer", "foretell_matters|you|"),
        # The reflexive "When you do, create a Food token" (CR 603.12): an
        # Unknown "when you do" mode with no execute.
        ("The Fourth Doctor", "food_makers|you|"),
        # "Create a Treasure token and venture into the dungeon" (CR 701.49a):
        # the venture dropped.
        ("You Find a Cursed Idol", "venture_makers|you|"),
    ],
)
def test_dropped_trigger_payoffs_are_served(name, ident):
    assert ident in _idents(name)


def test_a_when_you_do_without_food_makes_no_food():
    # Dialogue Tree's "when you do" is the same Unknown mode; its trigger makes
    # no Food, so the row's match leaves it out.
    assert "food_makers|you|" not in _idents("Dialogue Tree")


def test_a_venture_hoser_is_no_venture_maker():
    # "Your opponents can't venture into the dungeon more than once each turn."
    assert "venture_makers|you|" not in _idents("Keen-Eared Sentry")


@pytest.mark.parametrize("name", ["Motion Sickness", "The Most Dangerous Gamer"])
def test_attraction_unknown_modes_were_already_served(name):
    # "Whenever you visit / open an Attraction" are Unknown modes too; the
    # attractions_matter sweep row reads them already (no new bridge).
    assert "attractions_matter|you|" in _idents(name)


# ── the superfriends veto over parked attack recipients ──────────────────────

_PARKED_ATTACK_RECIPIENTS = [
    "Vengeful Pharaoh",  # an Unknown trigger mode
    "Tenuous Truce",  # an Unknown trigger mode
    "Trove of Temptation",  # an effect_structure residue
    "Ever-Watching Threshold",  # an unparsed_condition residue
    "Sivitri, Dragon Master",  # an unparsed_quantity residue
    "Varchild, Betrayer of Kjeldor",  # a hollow static
    "Illusionist's Gambit",  # a hollow static
]


@pytest.mark.parametrize("name", _PARKED_ATTACK_RECIPIENTS)
def test_protective_cards_are_not_superfriends_payoffs(name):
    # Each names "you or planeswalkers you control" together: CR 506.2 makes
    # that pair what an attack can reach, so an attack restriction or watcher
    # on it is protection, not a planeswalker payoff. Reading Vengeful
    # Pharaoh's combat-damage case the same way is the arm's own decision.
    assert "superfriends_matters|you|" not in _idents(name)


@pytest.mark.retirement_canary
def test_assault_suit_superfriends_leftover_canary():
    """A known leftover: Assault Suit's "can't attack you or planeswalkers you
    control" leaves no node and no parked text (phase v0.104.0 keeps only the
    +2/+2 and haste; no CantAttack with a defended field), so the superfriends
    arm still misreads it. When phase writes the defended field, ``defends_you``
    stands the arm down and this fails."""
    assert not defends_you(_tree("Assault Suit"))
    assert "superfriends_matters|you|" in _idents("Assault Suit"), (
        "Assault Suit: RETIRE-READY — the superfriends arm stands down now; "
        "move it into test_protective_cards_are_not_superfriends_payoffs."
    )


def test_a_structural_superfriends_payoff_beside_a_parked_recipient_stays():
    # Ajani Steadfast's emblem parks "damage to you or a planeswalker you
    # control", but its -2's loyalty counters are a structural payoff.
    assert "superfriends_matters|you|" in _idents("Ajani Steadfast")


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", _PARKED_ATTACK_RECIPIENTS)
def test_parked_attack_recipient_canary(name):
    """Retirement canary for ``control_stax._parks_you_or_your_planeswalkers``'s
    parked-text arm: phase v0.104.0 parks each card's "you or a planeswalker you
    control" clause (an Unknown trigger mode, a residue, a hollow static) where
    ``defends_you`` / ``watches_attacks_on_you`` can't read it. When phase types
    the recipient, those reads stand the superfriends arm down themselves."""
    tree = _tree(name)
    parked = [*tree.residues(), *tree.unknown_trigger_modes(), *tree.hollow_statics()]
    still_parked = any(_PARKED_YOU_OR_YOUR_PLANESWALKERS_RX.search(t) for t in parked)
    typed = defends_you(tree) or watches_attacks_on_you(tree)
    retire = (
        f"{name}: RETIRE-READY — phase now types the attack recipient (or no "
        "longer parks it). Drop the card from this canary; when none is left, "
        "delete control_stax._parks_you_or_your_planeswalkers."
    )
    assert still_parked, retire
    assert not typed, retire


# ── faces phase emits no record for ──────────────────────────────────────────

_MISSING_FACES = {
    # aftermath back halves: CR 702.127a casts them from the graveyard.
    "Rags // Riches": ("Riches", "gain_control"),
    "Reduce // Rubble": ("Rubble", "tapper_engine"),
    "Indulge // Excess": ("Excess", "treasure_makers"),
}


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", list(_MISSING_FACES))
def test_missing_aftermath_face_canary(name):
    """Phase v0.104.0 emits no record at all for these aftermath halves (the
    ADR-0038 W2c gap: no node to recover, so no bridge here). The face reads only
    as a zero-unit text-only tree. When phase emits the face, check the key the
    face should serve through its own tree."""
    face, key = _MISSING_FACES[name]
    names = {r["name"] for r in test_phase_records(name)}
    assert face not in names, (
        f"{name}: RETIRE-READY — phase now emits a {face!r} record. Check it "
        f"serves {key} and drop it from this canary."
    )


# ── keyword grants the token lane missed ─────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # CR 702.135a: afterlife's Spirit tokens.
        ("Afterlife Insurance", (("Afterlife", "Spirit"),)),
        # CR 702.181a: mobilize's Warrior tokens.
        ("Infantry Shield", (("Mobilize", "Warrior"),)),
    ],
)
def test_granted_token_keywords(name, expected):
    assert keyword_token_creations(_tree(name), granted=True) == expected
    (_kw, subtype), *_ = expected
    assert f"token_maker|you|{subtype}" in _idents(name)


def test_a_printed_afterlife_is_not_a_grant():
    # Ministrant of Obligation's own afterlife is phase's expanded Token trigger.
    tree = _tree("Ministrant of Obligation")
    assert keyword_token_creations(tree, granted=True) == ()
    assert "token_maker|you|Spirit" in _idents("Ministrant of Obligation")


# ── repo-side reads ──────────────────────────────────────────────────────────


def test_replacement_added_map_token_is_read():
    # "instead create those tokens plus an additional Map token": the Map's
    # explore ability (CR 701.44a) reaches the card through the known-token walk.
    assert "explore_makers|you|" in _idents("Worldwalker Helm")


def test_enters_with_counters_replacement_makes_plus_one():
    # "put it onto the battlefield with two +1/+1 counters on it instead" (CR
    # 122.6: counters given as it enters are counters put on it).
    assert "plus_one_makers|you|" in _idents("Dodecapod")


@pytest.mark.parametrize("name", ["Hamza, Guardian of Arashin", "Starport Security"])
def test_cost_reductions_counting_plus_one_creatures(name):
    tree = _tree(name)
    filters = [f for u in tree.units for f in cost_reduction_count_filters(u.node)]
    assert any("P1P1" in counter_pred_kinds(f) for f in filters)
    assert "plus_one_matters|you|" in _idents(name)


def test_a_creature_type_death_condition_is_morbid():
    # "if a Phyrexian died under your control this turn" — Phyrexian is a
    # creature type (CR 205.3m).
    assert "death_matters|any|" in _idents("Brimaz, Blight of Oreskos")


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("The Gold Saucer", "treasure_makers|you|"),
        ("Invert Polarity", "gain_control|you|"),
        ("Invert Polarity", "counter_control|you|"),
        ("Winter Sky", "mass_removal|you|"),
        ("Krark, the Thumbless", "spell_copy_makers|you|"),
        ("Goblin Artisans", "activated_draw|you|"),
    ],
)
def test_coin_flip_outcomes_are_walked(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # "If you lose the flip, return ~ to its owner's hand."
        ("Scoria Wurm", "bounce_tempo|you|"),
        ("Wild Wurm", "bounce_tempo|you|"),
        # "If you win the flip, return ~ to its owner's hand."
        ("Viashino Sandswimmer", "bounce_tempo|you|"),
        # A win that exiles the card itself and returns it transformed: the
        # transform vehicle, not a blink (Frenetic Sliver's untransformed return
        # is one — test_lane_reads_off_the_ir).
        ("Ral, Monsoon Mage // Ral, Leyline Prodigy", "blink_flicker|you|enabler"),
        # "If you lose the flip, counter target artifact spell you control …"
        ("Goblin Artisans", "counter_control|you|"),
        # "If you lose the flip, return that spell to its owner's hand" — the
        # trigger watches spells you cast, so the spell is yours.
        ("Krark, the Thumbless", "bounce_tempo|you|"),
        # "If you lose the flip, destroy all permanents named Wirefly" — the
        # tokens its winning flip creates.
        ("Wirefly Hive", "mass_removal|you|"),
    ],
)
def test_coin_flip_drawback_outcomes_are_skipped(name, ident):
    assert ident not in _idents(name)


@pytest.mark.parametrize("name", ["Damn", "Electrickery"])
def test_an_overloaded_spell_is_a_sweep(name):
    """Overload changes every "target" to "each" (CR 702.96a): Damn's destroy
    and Electrickery's damage sweep the board when overloaded, so the
    ``mass_removal`` lane reads them — and the board-wipe role counts them."""
    assert "mass_removal|you|" in _idents(name)


def test_an_overloaded_bounce_is_a_mass_bounce():
    assert "mass_bounce|any|" in _idents("Cyclonic Rift")


@pytest.mark.parametrize(
    ("name", "mode"),
    [
        ("Damn", "destroy"),
        ("Cyclonic Rift", "bounce"),
        ("Mizzium Mortars", "damage"),
        ("Downsize", None),  # "-4/-0": no toughness shrink, nothing dies
    ],
)
def test_overload_sweep_names_what_overload_makes_of_the_base_mode(name, mode):
    """The one read of "overload makes this a sweep" (CR 702.96a-b): the base
    mode's targeted effect on every object it could target."""
    tree = _tree(name)
    modes = {overload_sweep(tree, u, c) for u in tree.units for c in u.effects}
    assert modes - {None} == ({mode} if mode else set())


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "mass_tag"), [("Damn", "DestroyAll"), ("Cyclonic Rift", "BounceAll")]
)
def test_overload_sweep_is_read_from_the_base_mode(name, mass_tag):
    """Retirement canary for ``crosswalk.overload_sweep``: phase v0.104.0 keeps
    overload as an alternative cost and types only the targeted base mode, so
    the lanes and the board-wipe read take the sweep off it. When phase types
    the overloaded mode as a mass node, the base-mode read is redundant —
    retire it."""
    tree = _tree(name)
    assert any(alt.kind == "overload" for alt in tree.card_alt_costs)
    assert not tree.has_typed(mass_tag), (
        f"{name}: RETIRE-READY — phase types the overloaded sweep; drop "
        "``crosswalk.overload_sweep`` and its callers (the mass_removal / "
        "mass_bounce lanes, kills_creatures_en_masse, job_quality/board_wipe.py's "
        "_tree_sweeps and _overload_cost)."
    )


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "preds"),
    [
        # "{1}{W}: Each creature without flanking blocking this creature gets
        # -1/-1" — phase keeps "without flanking" and drops "blocking it".
        ("Knight of Valor", ("WithoutKeyword",)),
        # "Whenever this creature becomes blocked, each creature blocking it
        # gets -1/-1" — phase types a bare creature sweep.
        ("Baneblade Scoundrel", ()),
    ],
)
def test_combat_scope_shrinks_parse_as_board_sweeps(name, preds):
    """Retirement canary for the combat-scope vetoes in
    ``lanes.mana_and_wipes._mass_shrink`` (phase_parse_bug [P12]): phase
    v0.104.0 drops the "blocking it" clause from these one-combat shrinks
    (CR 702.25a: flanking's -1/-1 hits only the blocking creature), leaving a
    ``PumpAll`` over the board, so the shrink walk vetoes a ``becomes_blocked``
    / ``blocks`` trigger unit and a ``WithoutKeyword:Flanking`` filter. Once
    phase types the combat scope the filter changes shape — retire the
    vetoes."""
    filters = [
        effect_filter(c.node)
        for tree in trees_for(test_card(name))
        for u in tree.units
        for c in u.effects
        if tag_of(c.node) == "PumpAll"
    ]
    assert filters
    assert all(filter_predicates(f) == preds for f in filters), (
        f"{name}: RETIRE-READY — phase types the combat scope of this shrink; "
        "drop _mass_shrink's becomes_blocked / blocks and WithoutKeyword:Flanking "
        "vetoes (lanes/mana_and_wipes.py) and check the board-wipe preset still "
        "excludes the card."
    )
