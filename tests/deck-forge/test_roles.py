"""The template-role owner (ADR-0051): ``roles.is_ramp`` is ONE answer, read off the
signal path, for every surface that counts or sources ramp.

Real snapshot cards throughout (``mtg_utils.testkit``) — the production
``extract_signals`` path, not hand-built oracle dicts. The text degrade
(``card_classify.ramp_by_text``) keeps its own tests in ``test_card_classify.py``.
"""

import pytest

from mtg_utils._analysis.roles import DeckMana, _restriction_admits, is_ramp, role_of
from mtg_utils._card_ir.crosswalk.reads import ObjectFacts
from mtg_utils._tuner.issues import ROLE_SEARCH, _reliable_ramp
from mtg_utils.card_classify import is_land
from mtg_utils.testkit import snapshot_records, test_card, test_signals
from mtg_utils.theme_presets import get_preset, has_signal_coverage


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


@pytest.mark.parametrize(
    "name",
    [
        "Sol Ring",  # rock
        "Llanowar Elves",  # dork
        "Cultivate",  # land-fetch-to-battlefield (lf_ramp)
        # Number-word mana — the text read's blind spot ("Add three mana of any one
        # color" has no "{" / "one mana" after "add"), so these never counted.
        "Gilded Lotus",
        "Black Lotus",
        "Zaxara, the Exemplary",
        "Azusa, Lost but Seeking",  # extra land PLAY (the concept arm)
        "Burgeoning",  # land PUT (extra_land_drop)
        "Dockside Extortionist",  # a Treasure maker you keep
        "Uncle Iroh",  # firebending
    ],
)
def test_ramp_is_read_off_the_signal_path(name):
    card = _real(name)
    assert is_ramp(card)
    assert "ramp" in role_of(card)


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Bolt",
        "Demonic Tutor",
        "Sylvan Scrying",  # a land tutor TO HAND adds no mana and drops no land
        "Murder",
    ],
)
def test_non_ramp_is_not_ramp(name):
    assert not is_ramp(_real(name))


def test_a_land_is_the_mana_base_never_ramp():
    # Command Tower fires the `ramp` KEY (a fixing land) — the role and its preset
    # still say no: lands are the `lands` role and the land band's business (CR 305),
    # and a land-filled search page would starve the tuner's ramp sourcing.
    tower = _real("Command Tower")
    assert "ramp" in {s.key for s in test_signals("Command Tower")}
    assert not get_preset("ramp").matches(tower)
    assert not is_ramp(tower)
    assert role_of(tower) == {"lands"}


def test_a_treasure_handed_to_an_opponent_is_not_ramp():
    # Both fire `treasure_makers|you` (phase scopes the maker, not the recipient);
    # the Token node's own `owner` tells them apart.
    offer = _real("An Offer You Can't Refuse")  # "Its controller creates two Treasure"
    assert "treasure_makers" in {s.key for s in test_signals(offer["name"])}
    assert not is_ramp(offer)
    assert is_ramp(_real("Smothering Tithe"))
    # One Treasure for you, one for an opponent — still yours.
    assert is_ramp(_real("Generous Plunderer"))


def test_a_card_the_signal_path_cannot_see_degrades_to_text():
    rock = {
        "name": "Test Rock",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}.",
    }
    assert not has_signal_coverage(rock)
    assert is_ramp(rock)
    bear = {"name": "Test Bear", "type_line": "Creature — Bear", "oracle_text": ""}
    assert not is_ramp(bear)


def test_covered_card_never_falls_back_to_text():
    # Covered + no ramp signal ⇒ not ramp, even when the text read would say yes: a
    # DFC whose BACK face is a land joins "{T}: Add …" into the card's oracle text.
    bolt = _real("Lightning Bolt")
    assert has_signal_coverage(bolt)
    lying = {**bolt, "oracle_text": "{T}: Add {R}."}
    assert not is_ramp(lying)


def test_the_preset_and_the_role_agree_on_every_covered_card():
    """The agreement test that replaces the "mirrors is_ramp" comments: over the whole
    snapshot, the preset the tuner SEARCHES by and the role the budgets row COUNTS by
    are the same set — and the text degrade is never consulted for a covered card."""
    preset = get_preset(ROLE_SEARCH["ramp"]["preset_names"][0])
    records = snapshot_records()
    matched = {r["name"] for r in records if preset.matches(r)}
    counted = {r["name"] for r in records if "ramp" in role_of(r)}
    assert matched == counted
    assert len(matched) > 40


def test_the_tuner_ramp_search_page_is_nonland_ramp():
    """A search page is small and cmc-ascending, so a preset that matched mana lands
    (the `ramp` key fires for every fixing land) filled it with lands and starved the
    sourcing. Every preset hit must survive the tuner's own nonland gate."""
    preset = get_preset("ramp")
    hits = [r for r in snapshot_records() if preset.matches(r)]
    assert hits
    # The tuner's gate is ``is_land`` (the FRONT face): a Saga // Land DFC such as
    # Welcome to . . . // Jurassic Park is a nonland card the tuner may source.
    assert not [r["name"] for r in hits if is_land(r)]
    # The precision filter removes a rock whose every mana / Treasure ability is
    # gated on a condition (CR 602.5), and nothing else. Mox Amber has no gate: its
    # ruling says you can activate it with no legendary permanent (it then adds no
    # mana). Fanatic of Rhonas' first ability is ungated.
    names = {r["name"] for r in hits}
    gated = {"Mox Opal", "Mox Jasper", "Tablet of Compleation", "Boxing Ring"}
    ungated = {"Mox Amber", "Fanatic of Rhonas", "Sol Ring", "Arcane Signet"}
    assert gated | ungated <= names
    dropped = {r["name"] for r in hits if not _reliable_ramp(r)}
    assert gated <= dropped
    assert not ungated & dropped


@pytest.mark.parametrize("name", ["Skyshroud Claim", "Hunting Wilds"])
def test_multi_land_fetch_is_ramp(name):
    # "up to two Forest cards" — the text read's fetch pattern never matched it.
    assert is_ramp(_real(name))


def test_a_seed_outlives_signal_keys_read_without_trees(monkeypatch):
    """CI order bug: with no phase cache, a card read before any test seeded its
    trees memoizes empty trees and an empty signal-key set; a later ``test_card``
    must re-seed the real trees and drop the stale keys, or Cultivate stops being
    ramp for the rest of the process (main's CI failure before this fix)."""
    from mtg_utils import theme_presets
    from mtg_utils._card_ir import trees

    oid = test_card("Cultivate")["oracle_id"]
    monkeypatch.setitem(trees._TREES_MEMO, oid, ())  # read with no phase data
    monkeypatch.setitem(theme_presets._SIGNAL_KEY_INDEX, oid, frozenset())
    # The failing test's own path: seed the real trees, then read the role.
    assert is_ramp(_real("Cultivate"))


# --- The deck context: mana the deck can't use isn't ramp ------------------------


def _deck(commander: str | None, *spells: str) -> DeckMana:
    """A deck's mana context: its commander and its nonland cards (one copy each)."""
    return DeckMana.of(
        [_real(commander)] if commander else [],
        [(_real(name), 1) for name in spells],
    )


_OMNATH = "Omnath, Locus of the Void"  # colorless identity, a creature
_KRENKO = "Krenko, Mob Boss"  # mono-red, a creature
_MEMNARCH = "Memnarch"  # colorless, an artifact creature


@pytest.mark.parametrize(
    "name",
    [
        # Its ruling: under a colorless commander it "produces no mana. It doesn't
        # produce {C}." (Commander's Sphere's ruling says the same.)
        "Arcane Signet",
        "Commander's Sphere",
        # Ruling: "If your legendary creatures and legendary planeswalkers are all
        # colorless, ... you won't add any mana."
        "Mox Amber",
        # Ruling: if "the exiled card is colorless", it "can't add mana".
        "Chrome Mox",
    ],
)
def test_deck_colored_mana_is_dead_under_a_colorless_commander(name):
    card = _real(name)
    assert is_ramp(card)  # the card alone is ramp
    assert not is_ramp(card, deck_mana=_deck(_OMNATH))
    assert is_ramp(card, deck_mana=_deck(_KRENKO))


@pytest.mark.parametrize("name", ["Mox Opal", "Mind Stone", "Sol Ring"])
def test_colorless_or_any_color_mana_stays_ramp_under_a_colorless_commander(name):
    assert is_ramp(_real(name), deck_mana=_deck(_OMNATH))


def test_artifact_only_mana_is_ramp_where_the_deck_can_spend_it():
    """The Mightstone and Weakstone's {C}{C} "can't be spent to cast nonartifact
    spells" (CR 106.6). It's ramp when it can cast the commander or a third of the
    deck — an artifact deck under a creature commander included."""
    stone = _real("The Mightstone and Weakstone")
    assert is_ramp(stone, deck_mana=_deck(_MEMNARCH))
    assert not is_ramp(stone, deck_mana=_deck(_OMNATH, "Lightning Bolt", "Cultivate"))
    artifacts = _deck(_OMNATH, "Sol Ring", "Mind Stone", "Lightning Bolt")
    assert is_ramp(stone, deck_mana=artifacts)
    assert "card_draw" in role_of(stone, deck_mana=_deck(_OMNATH))


def test_one_usable_mana_ability_keeps_a_source_live():
    """Eldrazi Temple's {C}{C} is Eldrazi-only, but its plain {C} works for anyone."""
    assert _deck(_OMNATH).dead_mana(_real("Eldrazi Temple")) is None


@pytest.mark.parametrize(
    ("restriction", "subtypes", "admits"),
    [
        ("Instant, Sorcery, Demon, and Spirit", {"Spirit"}, True),
        ("Vampire, Cleric, And/or Demon", {"Cleric"}, True),
        ("Vampire, Cleric, And/or Demon", {"Goblin"}, False),
        ("Outlaw", {"Pirate"}, True),  # CR 700.12
        ("Colorless Eldrazi", {"Goblin"}, False),
        ("Unrecognizedword", set(), True),  # never condemned on vocabulary alone
    ],
)
def test_spell_type_restrictions_read_their_lists(restriction, subtypes, admits):
    facts = ObjectFacts(
        types=frozenset({"Creature"}),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(),
        colors=frozenset({"B"}),
    )
    assert _restriction_admits(restriction, facts) is admits


def test_noncreature_restriction_admits_a_planeswalker():
    facts = ObjectFacts(
        types=frozenset({"Planeswalker"}),
        subtypes=frozenset(),
        supertypes=frozenset({"Legendary"}),
        colors=frozenset({"B", "G"}),
    )
    assert _restriction_admits("Noncreature", facts)


def test_without_a_commander_deck_colored_mana_is_untouched():
    assert is_ramp(_real("Arcane Signet"), deck_mana=_deck(None, "Sol Ring"))


def test_the_tuner_never_sources_dead_ramp():
    assert not _reliable_ramp(_real("Arcane Signet"), deck_mana=_deck(_OMNATH))
    assert _reliable_ramp(_real("Arcane Signet"), deck_mana=_deck(_KRENKO))
