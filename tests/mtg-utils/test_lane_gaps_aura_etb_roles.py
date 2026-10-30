"""w40 miss-taxonomy lane reads: the Aura plan beyond Voltron, the typed
enters payoffs, and two role reads (Clue engines draw, a split-sentence exile
removes).

* ``aura_matters|any|`` — a payoff counting creatures enchanted by an Aura,
  whoever controls them (Killian, Decisive Mentor), with every Aura that can go
  on a creature as its ``aura`` doer, negative and control Auras included;
* ``artifacts_matter|you|etb`` / ``enchantments_matter|you|etb`` — "whenever an
  artifact / enchantment you control enters" (Yotian Dissident, Ondu
  Spiritdancer), served by the Clue and Treasure pages too;
* ``card_draw_engine|you|clue`` — a repeating trigger that investigates
  (Tireless Tracker): the ``card_draw`` role;
* Dispatch's metalcraft exile, a Spell ability of its own whose "that
  creature" is the tap's target: ``exile_removal``, the ``interaction`` role.

Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.lanes import SERVED_SIGNAL_KEYS
from mtg_utils._analysis.lanes.card_advantage import CLUE_ENGINE
from mtg_utils._analysis.lanes.counters_voltron import AURA_ON_CREATURE
from mtg_utils._analysis.roles import role_of
from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _sig(key: str, scope: str, subject: str) -> Signal:
    return Signal(key=key, scope=scope, subject=subject, text="", source="test")


# ── aura_matters: Auras on any creature ────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # "Whenever one or more creatures that are enchanted by an Aura you
        # control attack, draw a card" — his enters trigger goads them (CR
        # 701.15b), so the attackers are opponents' creatures.
        "Killian, Decisive Mentor",
        # "goad each creature your opponents control that's enchanted by an Aura
        # you control"
        "Kaima, the Fractured Calm",
        # "Whenever an enchanted creature dies, draw a card for each Aura you
        # controlled that was attached to it"
        "Hateful Eidolon",
        # "Each creature that's enchanted by an Aura you control can't attack you"
        "Eriette of the Charmed Apple",
    ],
)
def test_enchanted_creature_payoff_counts_any_controller(name):
    # CR 303.4b: the object an Aura is attached to is enchanted, whoever
    # controls it — voltron_matters reads only your own creatures.
    assert ("aura_matters", "any", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Darksteel Mutation",  # Enchant creature, a control Aura
        "Nurgle's Rot",  # Enchant creature an opponent controls
        "Kaya's Ghostform",  # Enchant creature or planeswalker you control
        "Spirit Loop",  # Enchant creature you control
        "Pacifism",
        "Rune of Mortality",  # Enchant permanent
        "Nyxborn Wolf",  # bestow (CR 702.103b)
        "Bronzehide Lion",  # returns as an Aura on a creature you control
        "Monstrous Rage",  # a Monster Role token attached (CR 303.7)
    ],
)
def test_aura_for_a_creature_is_the_doer(name):
    idents = _idents(name)
    assert ("aura_matters", "any", AURA_ON_CREATURE) in idents
    # Its "enchanted creature" is the one it is attached to: no payoff.
    assert ("aura_matters", "any", "") not in idents


@pytest.mark.parametrize(
    "name",
    [
        "Utopia Sprawl",  # Enchant Forest
        "Curse of Opulence",  # Enchant player
        "Grizzly Bears",
        # "if this creature is enchanted": the card's own state, no population
        "Dreampod Druid",
    ],
)
def test_no_aura_on_a_creature_reads_nothing(name):
    assert not {i for i in _idents(name) if i[0] == "aura_matters"}


def test_aura_plan_is_served_and_its_auras_are_doers():
    assert "aura_matters" in SERVED_SIGNAL_KEYS
    assert ("aura_matters", AURA_ON_CREATURE) in signal_keys.DOER_SUBJECTS
    spec = SPECS[("aura_matters", "any")]
    assert avenue_spec_for(_sig("aura_matters", "any", AURA_ON_CREATURE)) is spec
    # The Voltron serve vetoes a control Aura; this one serves it.
    assert spec.serve.matches(test_card("Darksteel Mutation"))
    assert spec.serve.matches(test_card("Killian, Decisive Mentor"))
    assert not spec.serve.matches(test_card("Utopia Sprawl"))


# ── typed enters payoffs: subject etb ───────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Yotian Dissident", "artifacts_matter"),
        ("Arcbound Crusher", "artifacts_matter"),
        ("Kappa Cannoneer", "artifacts_matter"),
        ("Sarinth Steelseeker", "artifacts_matter"),
        ("Ondu Spiritdancer", "enchantments_matter"),
        ("Slumbering Keepguard", "enchantments_matter"),
        ("Grim Guardian", "enchantments_matter"),  # constellation
        ("Victor, Valgavoth's Seneschal", "enchantments_matter"),
    ],
)
def test_enters_trigger_payoff_carries_etb(name, key):
    # CR 603.6a: "Whenever a [type] enters" — the broad payoff ident stays too.
    idents = _idents(name)
    assert (key, "you", "etb") in idents
    assert (key, "you", "") in idents


@pytest.mark.parametrize("name", ["Sythis, Harvest's Hand", "Thraben Inspector"])
def test_cast_trigger_and_maker_carry_no_etb(name):
    # A cast trigger (CR 601.2i) and a Clue maker are no enters payoff.
    assert not {i for i in _idents(name) if i[2] == "etb"}


@pytest.mark.parametrize(
    ("key", "scope"),
    [
        ("clue_makers", "you"),
        ("clue_matters", "you"),
        ("treasure_makers", "you"),
        ("treasure_matters", "you"),
    ],
)
def test_artifact_token_pages_serve_the_artifact_enters_payoff(key, scope):
    # A created token is put onto the battlefield (CR 111.1), so every Clue or
    # Treasure entering triggers it.
    assert SPECS[(key, scope)].serve.matches(test_card("Yotian Dissident"))


def test_etb_subject_opens_the_type_avenue():
    spec = avenue_spec_for(_sig("artifacts_matter", "you", "etb"))
    assert spec is SPECS[("artifacts_matter", "you")]


# ── Clue engines are card draw ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Tireless Tracker",
        "Chalk Outline",
        "Lonis, Cryptozoologist",
        "Eloise, Nephalia Sleuth",
    ],
)
def test_repeating_investigate_is_a_draw_engine(name):
    # CR 701.16a investigate = create a Clue; CR 111.10f a Clue sacrifices to
    # draw a card.
    assert ("card_draw_engine", "you", CLUE_ENGINE) in _idents(name)
    assert "card_draw" in role_of(test_card(name))


@pytest.mark.parametrize("name", ["Thraben Inspector", "Drag the Canal"])
def test_one_shot_clue_is_no_engine(name):
    assert ("card_draw_engine", "you", CLUE_ENGINE) not in _idents(name)


def test_clue_engine_is_not_on_the_draw_engine_page():
    assert avenue_spec_for(_sig("card_draw_engine", "you", CLUE_ENGINE)) is None


# ── a conditional exile in a sentence of its own ────────────────────────────


def test_metalcraft_exile_of_the_tapped_creature_is_removal():
    # "Tap target creature. Metalcraft — … exile that creature." CR 608.2c: the
    # spell's instructions are read as a whole.
    assert ("exile_removal", "you", "") in _idents("Dispatch")
    assert "interaction" in role_of(test_card("Dispatch"))
