"""Tests for the theme_presets module.

Two layers of coverage:

1. Unit tests for the Preset dataclass and registry API.
2. Golden fixture tests: for every preset in PRESETS, iterate its
   should_match / should_not_match tuples and assert matching behavior.
   Fixture card data (keywords + oracle_text) lives in FIXTURE_CARDS
   below. When adding a card to a preset's should_match, also add its
   Scryfall-accurate oracle_text and keywords here.
"""

from __future__ import annotations

import os
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mtg_utils.theme_presets import (
    PRESETS,
    Preset,
    get_preset,
    list_presets,
    matches,
)

# ─── Fixture cards ─────────────────────────────────────────────────────────
#
# Oracle text and keywords are as printed on Scryfall (most recent Oracle
# update). Keeping them here lets us test preset behavior without needing
# bulk Scryfall data at test time. When a preset adds a new card to its
# should_match list, add its fixture entry here.

FIXTURE_CARDS: dict[str, dict] = {
    # ── Generic reference cards ──
    "Lightning Bolt": {
        "keywords": [],
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    },
    "Counterspell": {
        "keywords": [],
        "oracle_text": "Counter target spell.",
    },
    "Llanowar Elves": {
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    },
    "Command Tower": {
        "keywords": [],
        "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
    },
    "Swords to Plowshares": {
        "keywords": [],
        "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
    },
    "Wrath of God": {
        "keywords": [],
        "oracle_text": "Destroy all creatures. They can't be regenerated.",
    },
    # ── Evergreen keyword bearers ──
    "Serra Angel": {
        "keywords": ["Flying", "Vigilance"],
        "oracle_text": "Flying, vigilance",
    },
    "Baleful Strix": {
        "keywords": ["Flying", "Deathtouch"],
        "oracle_text": (
            "Flying, deathtouch\n"
            "When Baleful Strix enters the battlefield, draw a card."
        ),
    },
    "Goldvein Hydra": {
        "keywords": ["Vigilance", "Treasure", "Haste", "Trample"],
        "oracle_text": (
            "Vigilance, trample, haste\n"
            "This creature enters with X +1/+1 counters on it.\n"
            "When this creature dies, create a number of tapped Treasure "
            "tokens equal to its power."
        ),
    },
    "Goblin Guide": {
        "keywords": ["Haste"],
        "oracle_text": (
            "Haste\n"
            "Whenever Goblin Guide attacks, defending player reveals the top "
            "card of their library. If it's a land card, that player puts it "
            "into their hand."
        ),
    },
    "Monastery Swiftspear": {
        "keywords": ["Haste", "Prowess"],
        "oracle_text": (
            "Haste\nProwess (Whenever you cast a noncreature spell, this "
            "creature gets +1/+1 until end of turn.)"
        ),
    },
    "Tymna the Weaver": {
        "keywords": ["Lifelink", "Partner"],
        "oracle_text": (
            "Lifelink\nAt the beginning of your postcombat main phase, you "
            "may pay X life, where X is the number of opponents that were "
            "dealt combat damage this turn. If you do, draw X cards.\nPartner"
        ),
    },
    "White Knight": {
        "keywords": ["First strike", "Protection"],
        "oracle_text": "First strike\nProtection from black",
    },
    "Invisible Stalker": {
        "keywords": ["Hexproof"],
        "oracle_text": (
            "Hexproof (This creature can't be the target of spells or "
            "abilities your opponents control.)\n"
            "This creature can't be blocked."
        ),
    },
    "Darksteel Myr": {
        "keywords": ["Indestructible"],
        "oracle_text": (
            'Indestructible (Damage and effects that say "destroy" don\'t '
            "destroy this creature. If its toughness is 0 or less, it still "
            "dies.)"
        ),
    },
    "Giant Spider": {
        "keywords": ["Reach"],
        "oracle_text": "Reach (This creature can block creatures with flying.)",
    },
    # ── Removal type-specific fixtures ──
    "Doom Blade": {
        "keywords": [],
        "oracle_text": "Destroy target nonblack creature.",
    },
    "Shatter": {
        "keywords": [],
        "oracle_text": "Destroy target artifact.",
    },
    "Disenchant": {
        # Bridge card: artifact-removal AND enchantment-removal.
        "keywords": [],
        "oracle_text": "Destroy target artifact or enchantment.",
    },
    "Sinkhole": {
        "keywords": [],
        "oracle_text": "Destroy target land.",
    },
    "Armageddon": {
        # Mass-land-removal test fixture. Banned in the shared-library
        # format but included here so land-removal preset has test coverage.
        "keywords": [],
        "oracle_text": "Destroy all lands.",
    },
    "Hero's Downfall": {
        "keywords": [],
        "oracle_text": "Destroy target creature or planeswalker.",
    },
    "Vindicate": {
        # Universal removal — destroys any permanent.
        "keywords": [],
        "oracle_text": "Destroy target permanent.",
    },
    "Beast Within": {
        # Universal removal with a rider. Key false-positive test for
        # creature-removal: the oracle mentions "creature token" AFTER the
        # destroy clause, so naive regex `destroy target .* creature` could
        # wrongly match. The [^.]* sentence-boundary gate prevents this.
        "keywords": [],
        "oracle_text": (
            "Destroy target permanent. Its controller creates a 3/3 green "
            "Beast creature token."
        ),
    },
    "Maelstrom Pulse": {
        # Universal removal with a modifier between "target" and
        # "permanent" — exercises the [^.]*? gap in the regex.
        "keywords": [],
        "oracle_text": (
            "Destroy target nonland permanent and all other permanents "
            "with the same name as that permanent."
        ),
    },
    "Nicol Bolas, Planeswalker": {
        # Planeswalker-ability universal removal via "+3: Destroy target
        # noncreature permanent." Loyalty costs use the U+2212 MINUS SIGN
        # (escaped as \u2212 below) to match Scryfall's oracle text.
        "keywords": [],
        "oracle_text": (
            "+3: Destroy target noncreature permanent.\n"
            "\u22122: Gain control of target creature.\n"
            "\u22129: Nicol Bolas deals 7 damage to target player or "
            "planeswalker. That player or that planeswalker's controller "
            "discards seven cards, then sacrifices seven permanents of "
            "their choice."
        ),
    },
    "Toxic Deluge": {
        # Mass -X/-X creature removal — exercises the `-X/-X` pattern
        # that was previously dead due to \b not matching before `-`.
        "keywords": [],
        "oracle_text": (
            "As an additional cost to cast this spell, pay X life.\n"
            "All creatures get -X/-X until end of turn."
        ),
    },
    "Reclamation Sage": {
        # ETB artifact/enchantment removal creature.
        "keywords": [],
        "oracle_text": (
            "When this creature enters, you may destroy target artifact or enchantment."
        ),
    },
    "Blade Splicer": {
        # Create-singular-token test case for the `tokens` preset (I1).
        "keywords": [],
        "oracle_text": (
            "When Blade Splicer enters the battlefield, create a 3/3 "
            "colorless Golem artifact creature token with first strike."
        ),
    },
    "Fury": {
        "keywords": ["Double strike", "Evoke"],
        "oracle_text": (
            "Double strike\nWhen this creature enters, it deals 4 damage "
            "divided as you choose among any number of targets.\n"
            "Evoke—Exile a red card from your hand."
        ),
    },
    "Obeka, Splitter of Seconds": {
        "keywords": ["Menace"],
        "oracle_text": (
            "Menace\nWhenever Obeka, Splitter of Seconds deals combat damage "
            "to a player, you get that many additional upkeep steps after "
            "this phase."
        ),
    },
    "Wall of Omens": {
        "keywords": ["Defender"],
        "oracle_text": (
            "Defender\nWhen Wall of Omens enters the battlefield, draw a card."
        ),
    },
    "Snapcaster Mage": {
        "keywords": ["Flash"],
        "oracle_text": (
            "Flash\nWhen Snapcaster Mage enters the battlefield, target "
            "instant or sorcery card in your graveyard gains flashback until "
            "end of turn. The flashback cost is equal to its mana cost."
        ),
    },
    "Dictate of Erebos": {
        "keywords": ["Flash"],
        "oracle_text": (
            "Flash\nWhenever a creature you control dies, each opponent "
            "sacrifices a creature."
        ),
    },
    "Star Whale": {
        # Note: Star Whale grants ward to OTHER creatures but doesn't have it
        # itself, so "Ward" is not in its keywords array.
        "keywords": ["Flying", "Vigilance", "Suspend"],
        "oracle_text": (
            "Flying, vigilance\nOther creatures you control have ward {2}.\n"
            "Suspend 6—{1}{U}"
        ),
    },
    # ── Named keyword abilities ──
    "Preordain": {
        "keywords": ["Scry"],
        "oracle_text": "Scry 2, then draw a card.",
    },
    "Omen of the Sun": {
        "keywords": ["Flash", "Scry"],
        "oracle_text": (
            "Flash\n"
            "When this enchantment enters, create two 1/1 white Human "
            "Soldier creature tokens and you gain 2 life.\n"
            "{2}{W}, Sacrifice this enchantment: Scry 2."
        ),
    },
    "Magma Jet": {
        "keywords": ["Scry"],
        "oracle_text": "Magma Jet deals 2 damage to any target.\nScry 2.",
    },
    "Thought Erasure": {
        "keywords": ["Surveil"],
        "oracle_text": (
            "Surveil 1, then target opponent reveals their hand. You choose "
            "a nonland card from it. That player exiles that card."
        ),
    },
    "Ransack the Lab": {
        # Despite the name evoking surveil, Ransack the Lab predates the
        # formal Surveil keyword — its oracle is the long-form filter-to-
        # graveyard phrasing and its keywords array is empty.
        "keywords": [],
        "oracle_text": (
            "Look at the top three cards of your library. Put one of them "
            "into your hand and the rest into your graveyard."
        ),
    },
    "Notion Rain": {
        "keywords": ["Surveil"],
        "oracle_text": "Surveil 2, then draw two cards. You lose 2 life.",
    },
    "Sinister Sabotage": {
        "keywords": ["Surveil"],
        "oracle_text": "Counter target spell.\nSurveil 1.",
    },
    "Bloodbraid Elf": {
        "keywords": ["Haste", "Cascade"],
        "oracle_text": "Haste\nCascade",
    },
    "Shardless Agent": {
        "keywords": ["Cascade"],
        "oracle_text": "Cascade",
    },
    "Lingering Souls": {
        "keywords": ["Flashback"],
        "oracle_text": (
            "Create two 1/1 white and black Spirit creature tokens with "
            "flying.\nFlashback {1}{B}"
        ),
    },
    "Faithless Looting": {
        "keywords": ["Flashback"],
        "oracle_text": ("Draw two cards, then discard two cards.\nFlashback {2}{R}"),
    },
    "Deep Analysis": {
        "keywords": ["Flashback"],
        "oracle_text": (
            "Target player draws two cards and loses 2 life.\n"
            "Flashback—{1}{U}, Pay 3 life."
        ),
    },
    "Gatekeeper of Malakir": {
        "keywords": ["Kicker"],
        "oracle_text": (
            "Kicker {B}{B}\n"
            "When Gatekeeper of Malakir enters the battlefield, if it was "
            "kicked, target player sacrifices a creature."
        ),
    },
    "Ketria Triome": {
        "keywords": ["Cycling"],
        "oracle_text": (
            "Ketria Triome enters the battlefield tapped.\n"
            "({T}: Add {G}, {U}, or {R}.)\nCycling {3}"
        ),
    },
    "Mulldrifter": {
        "keywords": ["Flying", "Evoke"],
        "oracle_text": (
            "Flying\nWhen Mulldrifter enters the battlefield, draw two cards.\n"
            "Evoke {2}{U}"
        ),
    },
    "Fallen Shinobi": {
        "keywords": ["Ninjutsu"],
        "oracle_text": (
            "Ninjutsu {1}{U}{B}\n"
            "Whenever Fallen Shinobi deals combat damage to a player, that "
            "player exiles the top two cards of their library. You may play "
            "those cards this turn, and you may spend mana as though it were "
            "mana of any color to cast those spells."
        ),
    },
    "Noble Hierarch": {
        "keywords": ["Exalted"],
        "oracle_text": (
            "Exalted (Whenever a creature you control attacks alone, that "
            "creature gets +1/+1 until end of turn.)\n{T}: Add {G}, {W}, or {U}."
        ),
    },
    "Qasali Pridemage": {
        "keywords": ["Exalted"],
        "oracle_text": (
            "Exalted\n{1}, Sacrifice Qasali Pridemage: Destroy target "
            "artifact or enchantment."
        ),
    },
    "Abbot of Keral Keep": {
        "keywords": ["Prowess"],
        "oracle_text": (
            "Prowess\nWhen Abbot of Keral Keep enters the battlefield, exile "
            "the top card of your library. Until end of turn, you may cast "
            "that card."
        ),
    },
    "Fatal Push": {
        "keywords": ["Revolt"],
        "oracle_text": (
            "Destroy target creature if it has mana value 2 or less.\n"
            "Revolt — Destroy that creature if it has mana value 4 or less "
            "instead if a permanent you controlled left the battlefield this "
            "turn."
        ),
    },
    "Thraben Inspector": {
        "keywords": ["Investigate"],
        "oracle_text": ("When Thraben Inspector enters the battlefield, investigate."),
    },
    "Courser of Kruphix": {
        "keywords": ["Landfall"],
        "oracle_text": (
            "Play with the top card of your library revealed.\n"
            "You may play lands from the top of your library.\n"
            "Whenever a land enters the battlefield under your control, you "
            "gain 1 life."
        ),
    },
    "Bloodghast": {
        # Conditional haste isn't a real Haste keyword per Scryfall.
        "keywords": ["Landfall"],
        "oracle_text": (
            "This creature can't block.\n"
            "This creature has haste as long as an opponent has 10 or less "
            "life.\n"
            "Landfall — Whenever a land you control enters, you may return "
            "this card from your graveyard to the battlefield."
        ),
    },
    "Murderous Cut": {
        "keywords": ["Delve"],
        "oracle_text": "Delve\nDestroy target creature.",
    },
    "Ancestral Vision": {
        "keywords": ["Suspend"],
        "oracle_text": "Suspend 4—{U}\nTarget player draws three cards.",
    },
    "Skullclamp": {
        "keywords": ["Equip"],
        "oracle_text": (
            "Equipped creature gets +1/-1.\n"
            "Whenever equipped creature dies, draw two cards.\n"
            "Equip {1}"
        ),
    },
    "Helm of the Host": {
        "keywords": ["Equip"],
        "oracle_text": (
            "At the beginning of combat on your turn, create a token that's "
            "a copy of equipped creature, except the token isn't legendary. "
            "That token gains haste.\nEquip {5}"
        ),
    },
    # ── Functional cards (regex-matched) ──
    "Stitcher's Supplier": {
        # Scryfall now treats Mill as a keyword. The oracle was also shortened
        # to use the `mill N cards` verb with reminder text.
        "keywords": ["Mill"],
        "oracle_text": (
            "When this creature enters or dies, mill three cards. "
            "(Put the top three cards of your library into your graveyard.)"
        ),
    },
    "Satyr Wayfinder": {
        "keywords": [],
        "oracle_text": (
            "When Satyr Wayfinder enters the battlefield, reveal the top "
            "four cards of your library. You may put a land card from among "
            "them into your hand. Put the rest into your graveyard."
        ),
    },
    "Grisly Salvage": {
        "keywords": [],
        "oracle_text": (
            "Reveal the top five cards of your library. You may put a "
            "creature or land card from among them into your hand. Put the "
            "rest into your graveyard."
        ),
    },
    "Thragtusk": {
        # Lifegain fixture (ETB gain 5 life).
        "keywords": [],
        "oracle_text": (
            "When Thragtusk enters, you gain 5 life.\n"
            "When Thragtusk leaves the battlefield, create a 3/3 green "
            "Beast creature token."
        ),
    },
    "Lightning Helix": {
        # Multicolor lifegain fixture (gains life as a rider).
        "keywords": [],
        "oracle_text": (
            "Lightning Helix deals 3 damage to any target. You gain 3 life."
        ),
    },
    "Scavenging Ooze": {
        # +1/+1 counter fixture (puts a counter on itself).
        "keywords": [],
        "oracle_text": (
            "{G}: Exile target card from a graveyard. If it was a creature "
            "card, put a +1/+1 counter on Scavenging Ooze and you gain 1 life."
        ),
    },
    "Contingency Plan": {
        # Oracle was retconned to Surveil 5 (Scryfall Oracle update). The
        # card is now a surveil card — the self-mill regex still correctly
        # does NOT match because the "rest" ends up on top of the library,
        # not in the graveyard. Kept as the self-mill negative test case.
        "keywords": ["Surveil"],
        "oracle_text": (
            "Surveil 5. (Look at the top five cards of your library, then "
            "put any number of them into your graveyard and the rest on "
            "top of your library in any order.)"
        ),
    },
    "Mana Leak": {
        "keywords": [],
        "oracle_text": "Counter target spell unless its controller pays {3}.",
    },
    "Remand": {
        "keywords": [],
        "oracle_text": (
            "Counter target spell. If that spell is countered this way, put "
            "it into its owner's hand instead of into that player's graveyard.\n"
            "Draw a card."
        ),
    },
    "Reanimate": {
        "keywords": [],
        "oracle_text": (
            "Put target creature card from a graveyard onto the battlefield "
            "under your control. You lose life equal to its mana value."
        ),
    },
    "Regrowth": {
        "keywords": [],
        "oracle_text": "Return target card from your graveyard to your hand.",
    },
    "Eternal Witness": {
        "keywords": [],
        "oracle_text": (
            "When Eternal Witness enters the battlefield, you may return "
            "target card from your graveyard to your hand."
        ),
    },
    "Ponder": {
        "keywords": [],
        "oracle_text": (
            "Look at the top three cards of your library, then put them back "
            "in any order. You may shuffle.\nDraw a card."
        ),
    },
    "Brainstorm": {
        "keywords": [],
        "oracle_text": (
            "Draw three cards, then put two cards from your hand on top of "
            "your library in any order."
        ),
    },
    "Rhystic Study": {
        "keywords": [],
        "oracle_text": (
            "Whenever an opponent casts a spell, you may draw a card unless "
            "that player pays {1}."
        ),
    },
    "Howling Mine": {
        # Third-person "draws a card" test case for the `cantrip` preset (I2).
        "keywords": [],
        "oracle_text": (
            "Howling Mine enters the battlefield tapped.\n"
            "At the beginning of each player's draw step, if Howling Mine "
            "is untapped, that player draws an additional card."
        ),
    },
    "Viscera Seer": {
        "keywords": ["Scry"],
        "oracle_text": (
            "Sacrifice a creature: Scry 1. "
            "(Look at the top card of your library. You may put that card "
            "on the bottom.)"
        ),
    },
    "Ashnod's Altar": {
        "keywords": [],
        "oracle_text": "Sacrifice a creature: Add {C}{C}.",
    },
    "Sakura-Tribe Elder": {
        "keywords": [],
        "oracle_text": (
            "Sacrifice Sakura-Tribe Elder: Search your library for a basic "
            "land card, put that card onto the battlefield tapped, then "
            "shuffle."
        ),
    },
    "Cultivate": {
        "keywords": [],
        "oracle_text": (
            "Search your library for up to two basic land cards, reveal "
            "those cards, put one onto the battlefield tapped and the other "
            "into your hand, then shuffle."
        ),
    },
    "Unsummon": {
        "keywords": [],
        "oracle_text": "Return target creature to its owner's hand.",
    },
}


# ─── Unit tests ────────────────────────────────────────────────────────────


class TestPreset:
    def test_is_frozen(self):
        p = get_preset("flying")
        with pytest.raises(FrozenInstanceError):
            p.name = "other"  # type: ignore[misc]

    def test_matches_by_keyword(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        assert p.matches({"keywords": ["Flying"]}) is True
        assert p.matches({"keywords": ["Vigilance"]}) is False
        assert p.matches({"keywords": []}) is False

    def test_keyword_match_is_case_insensitive(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        assert p.matches({"keywords": ["flying"]}) is True
        assert p.matches({"keywords": ["FLYING"]}) is True

    def test_matches_by_pattern(self):
        p = Preset(
            name="t",
            description="",
            patterns=(re.compile(r"deals? \d+ damage", re.IGNORECASE),),
        )
        assert p.matches({"oracle_text": "Deals 3 damage"}) is True
        assert p.matches({"oracle_text": "Counter target spell."}) is False

    def test_combines_keyword_and_pattern_with_or(self):
        p = Preset(
            name="t",
            description="",
            keywords=("Flying",),
            patterns=(re.compile(r"matches", re.IGNORECASE),),
        )
        assert p.matches({"keywords": ["Flying"], "oracle_text": ""})
        assert p.matches({"keywords": [], "oracle_text": "this matches"})
        assert not p.matches({"keywords": [], "oracle_text": "no"})

    def test_no_keywords_no_patterns_never_matches(self):
        p = Preset(name="t", description="")
        assert p.matches({"keywords": ["Flying"], "oracle_text": "anything"}) is False

    def test_missing_keywords_array_is_safe(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        # No keywords key at all — should treat as empty.
        assert p.matches({}) is False


class TestRegistry:
    def test_has_expected_keyword_presets(self):
        for expected in (
            "flying",
            "vigilance",
            "scry",
            "surveil",
            "flashback",
            "cascade",
            "cycling",
            "kicker",
            "evoke",
            "ninjutsu",
            "exalted",
            "prowess",
            "investigate",
            "landfall",
            "dredge",
            "miracle",
        ):
            assert expected in PRESETS, f"missing keyword preset: {expected}"

    def test_has_expected_functional_presets(self):
        for expected in (
            "top-manipulation",
            "self-mill",
            "counterspell",
            "removal",
            "board-wipe",
            "bounce",
            "discard",
            "tutors",
            "tokens",
            "sacrifice-outlet",
            "burn",
            "reanimate",
            "graveyard-return",
            "cantrip",
            "card-draw",
        ):
            assert expected in PRESETS, f"missing functional preset: {expected}"

    def test_registry_is_immutable(self):
        with pytest.raises(TypeError):
            PRESETS["new"] = Preset(name="new", description="")  # type: ignore[index]

    def test_all_names_unique(self):
        names = [p.name for p in PRESETS.values()]
        assert len(names) == len(set(names))

    def test_all_presets_have_nonempty_description(self):
        for name, p in PRESETS.items():
            assert p.description.strip(), f"preset {name!r} has empty description"

    def test_list_presets_covers_every_registry_entry(self):
        """Guards against accidentally omitting a preset from a group tuple."""
        listed = list_presets()
        assert set(listed.keys()) == set(PRESETS.keys())
        assert len(listed) == len(PRESETS)


class TestApi:
    def test_get_preset_returns_same_object(self):
        p1 = get_preset("flying")
        p2 = get_preset("flying")
        assert p1 is p2

    def test_get_preset_unknown_raises_keyerror(self):
        with pytest.raises(KeyError, match="unknown preset"):
            get_preset("doesnt-exist")

    def test_matches_convenience(self):
        assert matches("flying", {"keywords": ["Flying"]}) is True
        assert matches("flying", {"keywords": []}) is False

    def test_list_presets_returns_sorted_name_to_description(self):
        presets = list_presets()
        names = list(presets.keys())
        assert names == sorted(names)
        # Spot-check a few entries
        assert "flying" in presets
        assert "self-mill" in presets
        for name, desc in presets.items():
            assert isinstance(desc, str), name
            assert desc.strip(), name


# ─── Golden fixture tests ──────────────────────────────────────────────────
#
# Every preset's should_match and should_not_match tuples must hold against
# the inline FIXTURE_CARDS. This catches regex drift if an Oracle update
# changes a card's text, or if a preset's pattern accidentally breaks.


def _get_fixture(card_name: str) -> dict:
    card = FIXTURE_CARDS.get(card_name)
    if card is None:
        msg = (
            f"no fixture data for {card_name!r}. Add an entry to "
            f"FIXTURE_CARDS in test_theme_presets.py with keywords and "
            f"oracle_text from Scryfall."
        )
        raise pytest.fail.Exception(msg)
    return card


@pytest.mark.parametrize(
    ("preset_name", "card_name"),
    [(name, card) for name, preset in PRESETS.items() for card in preset.should_match],
)
def test_preset_should_match(preset_name: str, card_name: str):
    preset = PRESETS[preset_name]
    card = _get_fixture(card_name)
    assert preset.matches(card), (
        f"preset {preset_name!r} should match {card_name!r} but did not.\n"
        f"Card keywords: {card.get('keywords')}\n"
        f"Oracle text: {card.get('oracle_text')!r}"
    )


@pytest.mark.parametrize(
    ("preset_name", "card_name"),
    [
        (name, card)
        for name, preset in PRESETS.items()
        for card in preset.should_not_match
    ],
)
def test_preset_should_not_match(preset_name: str, card_name: str):
    preset = PRESETS[preset_name]
    card = _get_fixture(card_name)
    assert not preset.matches(card), (
        f"preset {preset_name!r} should NOT match {card_name!r} but did.\n"
        f"Card keywords: {card.get('keywords')}\n"
        f"Oracle text: {card.get('oracle_text')!r}"
    )


# ─── Integration tests against real Scryfall bulk data ────────────────────
#
# Opt-in: these only run when ``MTG_UTILS_BULK_DATA`` points to a Scryfall
# default-cards.json. They protect against two kinds of drift:
#
# 1. FIXTURE drift — the inline ``FIXTURE_CARDS`` entry for a card has
#    oracle_text or keywords that don't match what Scryfall actually prints.
#    (This happened during development: Ransack the Lab was claimed to have
#    the Surveil keyword, which its real oracle lacks.)
# 2. PRESET drift — the preset's regex or keyword list no longer matches
#    the real card even though the fixture does. E.g., a Scryfall Oracle
#    rewording breaks a regex.
#
# Both are caught by comparing fixture data to real data and by running the
# preset against real data. Skipped by default to keep CI fast and offline.


@pytest.fixture(scope="module")
def real_bulk_index() -> dict[str, dict]:
    """Load Scryfall bulk data into a name→card dict, or skip."""
    path_str = os.environ.get("MTG_UTILS_BULK_DATA")
    if not path_str:
        pytest.skip(
            "MTG_UTILS_BULK_DATA not set; integration tests skipped. "
            "Set it to a Scryfall default-cards.json path to enable."
        )

    path = Path(path_str).expanduser()
    if not path.exists():
        pytest.skip(f"bulk data file not found: {path}")

    from mtg_utils.bulk_loader import load_bulk_cards

    cards = load_bulk_cards(path)
    # Keep the first matching printing for each oracle name; skip tokens and
    # emblem layouts.
    index: dict[str, dict] = {}
    for c in cards:
        if c.get("layout") in ("token", "double_faced_token", "art_series", "emblem"):
            continue
        name = c.get("name")
        if name and name not in index:
            index[name] = c
    return index


class TestFixturesAgainstRealData:
    """Verify FIXTURE_CARDS matches real Scryfall data where both exist."""

    @pytest.mark.parametrize("card_name", sorted(FIXTURE_CARDS.keys()))
    def test_fixture_keywords_match_real(self, card_name, real_bulk_index):
        real = real_bulk_index.get(card_name)
        if real is None:
            pytest.fail(
                f"fixture card {card_name!r} not found in Scryfall bulk. "
                f"Either the name is wrong or this card has been rename-merged."
            )
        fixture = FIXTURE_CARDS[card_name]
        real_kws = set(real.get("keywords") or [])
        fixture_kws = set(fixture.get("keywords") or [])
        assert fixture_kws == real_kws, (
            f"Fixture keywords for {card_name!r} don't match Scryfall.\n"
            f"  Fixture: {sorted(fixture_kws)}\n"
            f"  Real:    {sorted(real_kws)}\n"
            f"Update FIXTURE_CARDS[{card_name!r}]['keywords'] to the real list."
        )


class TestPresetsAgainstRealData:
    """Verify every should_match / should_not_match claim against real data."""

    @pytest.mark.parametrize(
        ("preset_name", "card_name"),
        [(n, c) for n, p in PRESETS.items() for c in p.should_match],
    )
    def test_should_match_against_real(self, preset_name, card_name, real_bulk_index):
        real = real_bulk_index.get(card_name)
        if real is None:
            pytest.fail(f"card {card_name!r} not in real Scryfall bulk data")
        preset = PRESETS[preset_name]
        assert preset.matches(real), (
            f"preset {preset_name!r} does not match real Scryfall data for "
            f"{card_name!r}.\n"
            f"  Real keywords: {real.get('keywords')}\n"
            f"  Real oracle:   {real.get('oracle_text')!r}"
        )

    @pytest.mark.parametrize(
        ("preset_name", "card_name"),
        [(n, c) for n, p in PRESETS.items() for c in p.should_not_match],
    )
    def test_should_not_match_against_real(
        self, preset_name, card_name, real_bulk_index
    ):
        real = real_bulk_index.get(card_name)
        if real is None:
            pytest.fail(f"card {card_name!r} not in real Scryfall bulk data")
        preset = PRESETS[preset_name]
        assert not preset.matches(real), (
            f"preset {preset_name!r} unexpectedly matches real Scryfall data "
            f"for {card_name!r}.\n"
            f"  Real keywords: {real.get('keywords')}\n"
            f"  Real oracle:   {real.get('oracle_text')!r}"
        )
