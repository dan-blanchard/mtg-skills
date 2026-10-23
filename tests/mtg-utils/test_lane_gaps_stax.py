"""Phase D lane gaps, the stax slice (``lanes/stax_and_tempo.py``,
``tree_synthesis/control_stax.py``, ``tree_synthesis/types_tribal.py``).

The stax census reads the rule-setting hosers it missed (land-type setters,
search hosers, cast counter-taxes, nonbasic punishers, forced skips,
Containment Priest); a mass tap of a target player's creatures is tap_down;
color and creature-type changers, own-hand scalers, Vehicle support,
opponent-library peeks, enter-trigger pumps, land shields, control swaps and
death drains each reach the key a held serve spec reads. Real cards only
(``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import tag_of
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


_STAX = ("stax_taxes", "opponents", "")
_SYM = ("symmetric_stax", "each", "")


# ── stax: the rule-setting hosers ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # Nonbasic lands are Mountains (CR 305.7) — every player's nonbasics.
        ("Blood Moon", _SYM),
        ("Magus of the Moon", _SYM),
        # "If an opponent would search a library …" (RestrictLibrarySearchToTop).
        ("Aven Mindcensor", _STAX),
        # Cast counter-taxes: everyone's spells, an opponent's spells.
        ("Nether Void", _SYM),
        ("Nether Void", _STAX),
        ("Chancellor of the Annex", _STAX),
        # Nonbasic punishers: a tap-for-mana trigger, a count of nonbasic lands.
        ("Burning Earth", _SYM),
        ("Price of Progress", _SYM),
        # Skips forced on an opponent (CR 614.10).
        ("Brine Elemental", _STAX),
        ("Blinding Angel", _STAX),
        # Replacement hosers: uncast creatures, extra turns.
        ("Containment Priest", _SYM),
        ("Ugin's Nexus", _SYM),
        # Fatespinner's parked skip (the canary below).
        ("Fatespinner", _STAX),
    ],
)
def test_stax_hosers_are_read(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Chronatog",  # you skip your own turn
        "Moment of Silence",  # a same-turn combat fog
        "Hope-Ender Coatl",  # its own cast trigger counters an opponent's spell
        "Spreading Seas",  # an Aura's one land
        "Rampant Growth",  # basic-land ramp
        "Necropotence",  # skips your own draw step
    ],
)
def test_non_stax_stays_out(name):
    assert not _keys(name) & {"stax_taxes", "symmetric_stax"}


@pytest.mark.parametrize("name", ["Aven Mindcensor", "Stranglehold"])
def test_opponent_search_hosers_punish_tutors(name):
    assert ("opponent_search_matters", "opponents", "") in _idents(name)


@pytest.mark.retirement_canary
def test_fatespinner_skip_is_still_parked_canary():
    """Retirement canary for ``control_stax._fatespinner_parked_skip``: phase
    v0.104.0 parks Fatespinner's "The player skips each instance of the chosen
    step or phase this turn" as an ``Unimplemented`` (``unbound_subject``)
    sub-ability of a labeled ``Choose``."""
    test_signals("Fatespinner")  # seeds the snapshot's trees (CI-safe)
    parked = [
        sub
        for tree in trees_for(test_card("Fatespinner"))
        for unit in tree.units
        if unit.origin == "trigger"
        for sub in [
            getattr(
                getattr(getattr(unit.node, "execute", None), "sub_ability", None),
                "effect",
                None,
            )
        ]
        if tag_of(sub) == "Unimplemented"
    ]
    assert parked, (
        "control_stax._fatespinner_parked_skip: RETIRE-READY — phase now types "
        "Fatespinner's skip; read it structurally and delete the bridge."
    )


# ── tap_down: a mass tap of a target player's creatures ──────────────────────


@pytest.mark.parametrize("name", ["Sleep", "Dawnglare Invoker"])
def test_mass_tap_of_target_player_is_tap_down(name):
    assert ("tap_down", "opponents", "") in _idents(name)


# ── color_change: changers and color-keyed mass effects ──────────────────────


@pytest.mark.parametrize(
    "name", ["Purelace", "Painter's Servant", "Sleight of Mind", "Crimson Wisps"]
)
def test_color_changers_fire_color_change(name):
    assert ("color_change", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Hope-Ender Coatl",  # devoid's characteristic-defining colorlessness
        "Oko, Thief of Crowns",  # a green Elk is an animation, not a recolor
    ],
)
def test_color_riders_are_not_changers(name):
    assert ("color_change", "you", "") not in _idents(name)


@pytest.mark.parametrize("name", ["Hibernation", "Wash Out", "Light of Day"])
def test_color_keyed_mass_effects_are_payoffs(name):
    assert ("color_change", "you", "payoff") in _idents(name)


def test_colorless_wipe_is_no_color_payoff():
    assert ("color_change", "you", "payoff") not in _idents("Wrath of God")


# ── type_change: creature-type changers ──────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"), [("Imagecrafter", "any"), ("Standardize", "each")]
)
def test_creature_type_changers_reach_others(name, scope):
    # A target creature (Imagecrafter) or every creature (Standardize) becomes
    # the type you choose: a creature that may be an opponent's.
    assert ("type_changers", scope, "") in _idents(name)


@pytest.mark.parametrize("name", ["Conspiracy", "Psychic Paper"])
def test_own_type_setters_reach_no_others(name):
    # Your own creatures (Conspiracy) or the equipped one (Psychic Paper).
    scopes = {sc for k, sc, _su in _idents(name) if k == "type_changers"}
    assert not scopes & {"any", "each"}


# ── big_hand_matters: "for each card in your hand" ───────────────────────────


@pytest.mark.parametrize(
    "name", ["Empyrial Armor", "Spontaneous Generation", "Gerrard's Wisdom"]
)
def test_own_hand_scalers_are_big_hand_payoffs(name):
    assert ("big_hand_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Dread Slag",  # -4/-4 for each card: rewards an empty hand
        "Damia, Sage of Stone",  # refills to seven
        "Demonic Lore",  # you lose life for each card
    ],
)
def test_empty_hand_payoffs_are_not_big_hand(name):
    assert "big_hand_matters" not in _keys(name)


# ── vehicles_matter: support beside the Vehicles ─────────────────────────────


@pytest.mark.parametrize(
    "name", ["Intrepid Stablemaster", "Sram, Senior Edificer", "Kitsune Ace"]
)
def test_vehicle_support(name):
    assert ("vehicles_matter", "you", "") in _idents(name)


def test_creature_or_vehicle_removal_is_not_support():
    assert "vehicles_matter" not in _keys("Bounce Off")


# ── opp_top_exile: seeing another player's library top ───────────────────────


@pytest.mark.parametrize("name", ["Field of Dreams", "Eye Spy"])
def test_opponent_library_peeks(name):
    assert ("opp_top_exile", "you", "peek") in _idents(name)


def test_own_scry_is_no_peek():
    assert ("opp_top_exile", "you", "peek") not in _idents("Opt")


# ── the rest ─────────────────────────────────────────────────────────────────


def test_scried_this_turn_is_a_scry_payoff():
    assert ("scry_surveil_matters", "you", "") in _idents("Surveillance Phantasm")


def test_enter_trigger_pump_on_the_entering_creature():
    assert ("entered_attacker", "you", "etb_pump") in _idents("Primal Forcemage")
    # Herd Gnarr pumps only itself.
    assert ("entered_attacker", "you", "etb_pump") not in _idents("Herd Gnarr")


@pytest.mark.parametrize("name", ["Terra Eternal", "Marwyn, the Preserver"])
def test_land_shields(name):
    assert ("land_protection", "you", "shield") in _idents(name)


def test_a_mana_dork_is_no_land_shield():
    assert "land_protection" not in _keys("Llanowar Elves")


@pytest.mark.parametrize("name", ["Switcheroo", "Gilded Drake"])
def test_exchange_control_is_a_swap(name):
    assert ("control_exchange", "you", "swap") in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Blood Artist", "Zulaport Cutthroat", "Vengeful Dead", "Pitiless Plunderer"],
)
def test_death_drains_are_kill_engine_payoffs(name):
    assert ("kill_engine", "you", "payoff") in _idents(name)


def test_a_land_death_trigger_is_no_kill_payoff():
    assert ("kill_engine", "you", "payoff") not in _idents("Dingus Egg")
