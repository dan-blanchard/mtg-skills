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
    "Strip Mine": {
        # Single-target land removal from a land source — matches the same
        # regex branch as Sinkhole but with different surrounding oracle.
        "keywords": [],
        "oracle_text": "{T}: Add {C}.\n{T}, Sacrifice this land: Destroy target land.",
    },
    "Wasteland": {
        # Non-basic land destruction — exercises the [^.]*? gap (the
        # modifier "nonbasic" sits between "target" and "land").
        "keywords": [],
        "oracle_text": (
            "{T}: Add {C}.\n{T}, Sacrifice this land: Destroy target nonbasic land."
        ),
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
    "Boomerang": {
        # Universal bounce — "target permanent" not "target creature".
        # Exercises the bounce preset's permanent alternative and the
        # relaxed `removal` umbrella bounce pattern.
        "keywords": [],
        "oracle_text": "Return target permanent to its owner's hand.",
    },
    "Prey Upon": {
        # Fight — exercises the `fights? target\b` branch in creature-
        # removal and `removal` umbrella.
        "keywords": ["Fight"],
        "oracle_text": (
            "Target creature you control fights target creature you don't "
            "control. (Each deals damage equal to its power to the other.)"
        ),
    },
    "Electrolyze": {
        # Divided damage — exercises the divided-damage branch.
        "keywords": [],
        "oracle_text": (
            "Electrolyze deals 2 damage divided as you choose among one or "
            "two targets.\nDraw a card."
        ),
    },
    "Disfigure": {
        # Target-creature-gets-minus-N — exercises that branch.
        "keywords": [],
        "oracle_text": "Target creature gets -2/-2 until end of turn.",
    },
    "Farewell": {
        # Modal mass exile — exercises `exile all creatures` (board-wipe)
        # and the `\bexile\s+all\b` branch in the `removal` umbrella.
        "keywords": [],
        "oracle_text": (
            "Choose one or more —\n"
            "• Exile all artifacts.\n"
            "• Exile all creatures.\n"
            "• Exile all enchantments.\n"
            "• Exile all graveyards."
        ),
    },
    # ── New keyword-mechanic fixtures (2024-2026 sets) ──
    "Aang, the Last Airbender": {
        # Airbend keyword — exile and let owner recast for {2}.
        # NOT bounce (never returns to hand). Own preset.
        "keywords": ["Flying", "Airbend"],
        "oracle_text": (
            "Flying\n"
            "When Aang enters, airbend up to one other target nonland "
            "permanent. (Exile it. While it's exiled, its owner may cast "
            "it for {2} rather than its mana cost.)\n"
            "Whenever you cast a Lesson spell, Aang gains lifelink until "
            "end of turn."
        ),
    },
    "Aang's Iceberg": {
        # Waterbend — flavor rename of scry; the card has both Waterbend
        # and Scry keywords because its reminder text invokes scry.
        "keywords": ["Flash", "Waterbend", "Scry"],
        "oracle_text": (
            "Flash\n"
            "When this enchantment enters, exile up to one other target "
            "nonland permanent until this enchantment leaves the "
            "battlefield.\n"
            "Waterbend {3}: Sacrifice this enchantment. If you do, scry 2."
        ),
    },
    "Contagion Clasp": {
        "keywords": ["Proliferate"],
        "oracle_text": (
            "When this artifact enters, put a -1/-1 counter on target "
            "creature.\n"
            "{4}, {T}: Proliferate."
        ),
    },
    "Atraxa, Praetors' Voice": {
        # Bundles flying/vigilance/deathtouch/lifelink + Proliferate.
        "keywords": ["Deathtouch", "Flying", "Lifelink", "Vigilance", "Proliferate"],
        "oracle_text": (
            "Flying, vigilance, deathtouch, lifelink\n"
            "At the beginning of your end step, proliferate."
        ),
    },
    "Disrupt Decorum": {
        "keywords": ["Goad"],
        "oracle_text": (
            "Goad all creatures you don't control. (Until your next turn, "
            "those creatures attack each combat if able and attack a "
            "player other than you if able.)"
        ),
    },
    "Storm-Kiln Artist": {
        # Magecraft spellslinger — creates Treasure on each instant/sorcery.
        "keywords": ["Treasure", "Magecraft"],
        "oracle_text": (
            "This creature gets +1/+0 for each artifact you control.\n"
            "Magecraft — Whenever you cast or copy an instant or sorcery "
            "spell, create a Treasure token."
        ),
    },
    "Archmage Emeritus": {
        "keywords": ["Magecraft"],
        "oracle_text": (
            "Magecraft — Whenever you cast or copy an instant or sorcery "
            "spell, draw a card."
        ),
    },
    "Berta, Wise Extrapolator": {
        # Increment keyword from Secrets of Strixhaven — +1/+1 counter
        # trigger on 5+-mana spells relative to creature's P/T.
        "keywords": ["Increment"],
        "oracle_text": (
            "Increment (Whenever you cast a spell, if the amount of mana "
            "you spent is greater than this creature's power or "
            "toughness, put a +1/+1 counter on this creature.)\n"
            "Whenever one or more +1/+1 counters are put on Berta, add "
            "one mana of any color."
        ),
    },
    "Colorstorm Stallion": {
        # Opus keyword from Secrets of Strixhaven — big-spells trigger
        # with a lesser mode for any instant/sorcery.
        "keywords": ["Haste", "Ward", "Opus"],
        "oracle_text": (
            "Ward {1}, haste\n"
            "Opus — Whenever you cast an instant or sorcery spell, this "
            "creature gets +1/+1 until end of turn. If five or more mana "
            "was spent to cast that spell, create a token that's a copy "
            "of this creature."
        ),
    },
    "Efflorescence": {
        # Infusion keyword from Secrets of Strixhaven — lifegain-matters.
        "keywords": ["Infusion"],
        "oracle_text": (
            "Put two +1/+1 counters on target creature.\n"
            "Infusion — If you gained life this turn, that creature also "
            "gains trample and indestructible until end of turn."
        ),
    },
    "Change of Plans": {
        # Connive — draw-then-discard with +1/+1 on nonland discard.
        "keywords": ["Connive"],
        "oracle_text": (
            "Each of X target creatures you control connive. You may have "
            "any number of them phase out."
        ),
    },
    "Chemister's Insight": {
        # Scryfall's keywords array lists both "Jump" and "Jump-start" for
        # jump-start cards — keep both to match real data.
        "keywords": ["Jump", "Jump-start"],
        "oracle_text": (
            "Draw two cards.\n"
            "Jump-start (You may cast this card from your graveyard by "
            "discarding a card in addition to paying its other costs. "
            "Then exile this card.)"
        ),
    },
    "Angel of Sanctions": {
        "keywords": ["Flying", "Embalm"],
        "oracle_text": (
            "Flying\n"
            "When this creature enters, you may exile target nonland "
            "permanent an opponent controls until this creature leaves "
            "the battlefield.\n"
            "Embalm {5}{W}"
        ),
    },
    "Kroxa, Titan of Death's Hunger": {
        "keywords": ["Escape"],
        "oracle_text": (
            "When Kroxa enters, sacrifice it unless it escaped.\n"
            "Whenever Kroxa enters or attacks, each opponent discards a "
            "card, then each opponent who didn't discard a nonland card "
            "this way loses 3 life.\n"
            "Escape—{B}{B}{R}{R}, Exile five other cards from your "
            "graveyard."
        ),
    },
    # ── Edict + land-animation + spell-copy family fixtures ──
    "Diabolic Edict": {
        "keywords": [],
        "oracle_text": "Target player sacrifices a creature of their choice.",
    },
    "Sheoldred's Edict": {
        "keywords": [],
        "oracle_text": (
            "Choose one —\n"
            "• Each opponent sacrifices a nontoken creature of their choice.\n"
            "• Each opponent sacrifices a creature token of their choice.\n"
            "• Each opponent sacrifices a planeswalker of their choice."
        ),
    },
    "Shard of the Void Dragon": {
        "keywords": ["Flying", "Matter Absorption", "Spear of the Void Dragon"],
        "oracle_text": (
            "Flying\n"
            "Spear of the Void Dragon — Whenever this creature attacks, each "
            "opponent sacrifices a nonland permanent of their choice.\n"
            "Matter Absorption — Whenever an artifact is put into a "
            "graveyard from the battlefield or is put into exile from the "
            "battlefield, put two +1/+1 counters on this creature."
        ),
    },
    "Martyr's Bond": {
        "keywords": [],
        "oracle_text": (
            "Whenever this enchantment or another nonland permanent you "
            "control is put into a graveyard from the battlefield, each "
            "opponent sacrifices a permanent of their choice that shares "
            "a card type with it."
        ),
    },
    "Mutavault": {
        "keywords": [],
        "oracle_text": (
            "{T}: Add {C}.\n"
            "{1}: This land becomes a 2/2 creature with all creature types "
            "until end of turn. It's still a land."
        ),
    },
    "Treetop Village": {
        "keywords": [],
        "oracle_text": (
            "This land enters tapped.\n"
            "{T}: Add {G}.\n"
            "{1}{G}: This land becomes a 3/3 green Ape creature with "
            "trample until end of turn. It's still a land."
        ),
    },
    "Wildfire": {
        "keywords": [],
        "oracle_text": (
            "Each player sacrifices four lands of their choice. Wildfire "
            "deals 4 damage to each creature."
        ),
    },
    "Tribute to the Wild": {
        "keywords": [],
        "oracle_text": (
            "Each opponent sacrifices an artifact or enchantment of their choice."
        ),
    },
    "Dromoka's Command": {
        "keywords": ["Fight"],
        "oracle_text": (
            "Choose two —\n"
            "• Prevent all damage target instant or sorcery spell would "
            "deal this turn.\n"
            "• Target player sacrifices an enchantment of their choice.\n"
            "• Put a +1/+1 counter on target creature.\n"
            "• Target creature you control fights target creature you "
            "don't control."
        ),
    },
    "Weather the Storm": {
        "keywords": ["Storm"],
        "oracle_text": (
            "You gain 3 life.\n"
            "Storm (When you cast this spell, copy it for each spell "
            "cast before it this turn.)"
        ),
    },
    "Train of Thought": {
        "keywords": ["Replicate"],
        "oracle_text": (
            "Replicate {1}{U} (When you cast this spell, copy it for each "
            "time you paid its replicate cost.)\n"
            "Draw a card."
        ),
    },
    "Last Thoughts": {
        "keywords": ["Cipher"],
        "oracle_text": (
            "Draw a card.\n"
            "Cipher (Then you may exile this spell card encoded on a "
            "creature you control. Whenever that creature deals combat "
            "damage to a player, its controller may cast a copy of the "
            "encoded card without paying its mana cost.)"
        ),
    },
    # ── Secrets of Strixhaven fixtures ──
    "Improvisation Capstone": {
        # Paradigm keyword — spell-copy via recurring free-cast from exile.
        "keywords": ["Paradigm"],
        "oracle_text": (
            "Exile cards from the top of your library until you exile cards "
            "with total mana value 4 or greater. You may cast any number of "
            "spells from among them without paying their mana costs.\n"
            "Paradigm (Then exile this spell. After you first resolve a "
            "spell with this name, you may cast a copy of it from exile "
            "without paying its mana cost at the beginning of each of "
            "your first main phases.)"
        ),
    },
    "Scathing Shadelock // Venomous Words": {
        # Prepared keyword + prepare layout — creature + paired spell on
        # split faces. Oracle text is empty at top level on Scryfall;
        # the real text lives in card_faces.
        "keywords": ["Prepared"],
        "oracle_text": "",
    },
    # ── Keyword individual-preset fixtures (Scryfall-verified, 2024-2026 sets) ──
    "Scorn Effigy": {
        "keywords": ["Foretell"],
        "oracle_text": "Foretell {0} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)",
    },
    "Djinn of Fool's Fall": {
        "keywords": ["Flying", "Plot"],
        "oracle_text": "Flying\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    },
    "Voidcalled Devotee": {
        "keywords": ["Haste", "Warp", "Conjure"],
        "oracle_text": "Haste\nWhenever this creature attacks, conjure a card named Cantor of the Refrain into your graveyard.\nWarp {1}{B}",
    },
    "Unnatural Summons": {
        "keywords": ["Manifest", "Manifest dread", "Rebound"],
        "oracle_text": "If you weren't the starting player, this spell costs {1} less to cast.\nManifest dread.\nRebound",
    },
    "Lurker in the Deep": {
        "keywords": ["Impending", "Seek", "Manifest", "Conjure"],
        "oracle_text": "Impending 3—{2}{U}{U}\nWhenever Lurker in the Deep enters or attacks, seek a nonland card.\nWhenever you seek one or more cards during your turn, conjure a duplicate of each of those cards into your hand, then manifest those duplicates.",
    },
    "Surge of Acclaim": {
        "keywords": ["Jump", "Seek", "Jump-start", "Start your engines!"],
        "oracle_text": "Choose one. If you have max speed, choose both instead.\n• Seek a card with start your engines!\n• Seek a nonland card.\nJump-start",
    },
    "Appeal // Authority": {
        "keywords": ["Aftermath"],
        "oracle_text": None,
    },
    "Oona's Grace": {
        "keywords": ["Retrace"],
        "oracle_text": "Target player draws a card.\nRetrace (You may cast this card from your graveyard by discarding a land card in addition to paying its other costs.)",
    },
    "Baithook Angler // Hook-Haunt Drifter": {
        "keywords": ["Flying", "Transform", "Disturb"],
        "oracle_text": None,
    },
    "Spider-Islanders": {
        "keywords": ["Mayhem"],
        "oracle_text": "Mayhem {1}{R} (You may cast this card from your graveyard for {1}{R} if you discarded it this turn. Timing rules still apply.)",
    },
    "Ureni's Counsel": {
        "keywords": ["Seek", "Harmonize"],
        "oracle_text": "This spell costs {1} less to cast for each Dragon card in your library.\nSeek a Dragon card.\nHarmonize {8}{R}{R}",
    },
    "Cut of the Profits": {
        "keywords": ["Casualty"],
        "oracle_text": "Casualty 3 (As you cast this spell, you may sacrifice a creature with power 3 or greater. When you do, copy this spell.)\nYou draw X cards and you lose X life.",
    },
    "Ghastly Discovery": {
        "keywords": ["Conspire"],
        "oracle_text": "Draw two cards, then discard a card.\nConspire (As you cast this spell, you may tap two untapped creatures you control that share a color with it. When you do, copy it.)",
    },
    "Incarnation Technique": {
        "keywords": ["Mill", "Demonstrate"],
        "oracle_text": "Demonstrate (When you cast this spell, you may copy it. If you do, choose an opponent to also copy it.)\nMill five cards, then return a creature card from your graveyard to the battlefield.",
    },
    "Wake the Reflections": {
        "keywords": ["Populate"],
        "oracle_text": "Populate. (Create a token that's a copy of a creature token you control.)",
    },
    "Gríma Wormtongue": {
        "keywords": ["Amass"],
        "oracle_text": "Your opponents can't gain life.\n{T}, Sacrifice another creature: Target player loses 1 life. If the sacrificed creature was legendary, amass Orcs 2.",
    },
    "Fountainport Charmer": {
        "keywords": ["Offspring"],
        "oracle_text": 'Offspring {2}\nWhen Fountainport Charmer enters, creature cards in your hand perpetually gain "This spell costs {1} less to cast."',
    },
    "Paranormal Analyst": {
        "keywords": ["Manifest", "Manifest dread"],
        "oracle_text": "Whenever you manifest dread, put a card you put into your graveyard this way into your hand.",
    },
    "Ransom Note": {
        "keywords": ["Surveil", "Goad", "Cloak"],
        "oracle_text": "When this artifact enters, surveil 1.\n{2}, Sacrifice this artifact: Choose one —\n• Cloak the top card of your library.\n• Goad target creature.\n• Draw a card.",
    },
    "Eyes of Gitaxias": {
        "keywords": ["Incubate", "Transform"],
        "oracle_text": 'Incubate 3. (Create an Incubator token with three +1/+1 counters on it and "{2}: Transform this token." It transforms into a 0/0 Phyrexian artifact creature.)\nDraw a card.',
    },
    "Accomplished Automaton": {
        "keywords": ["Fabricate"],
        "oracle_text": "Fabricate 1 (When this creature enters, put a +1/+1 counter on it or create a 1/1 colorless Servo artifact creature token.)",
    },
    "Debtors' Transport": {
        "keywords": ["Afterlife"],
        "oracle_text": "Afterlife 2 (When this creature dies, create two 1/1 white and black Spirit creature tokens with flying.)",
    },
    "Dalkovan Outrider": {
        "keywords": ["Mobilize"],
        "oracle_text": "Mobilize 2\nWhenever you sacrifice a permanent, the topmost creature card in your library perpetually gets +1/+1.",
    },
    "Broodmate Tyrant": {
        "keywords": ["Flying", "Encore"],
        "oracle_text": "Flying\nWhen this creature enters, create a 5/5 red Dragon creature token with flying.\nEncore {5}{B}{R}{G}",
    },
    "The Master, Multiplied": {
        "keywords": ["Myriad"],
        "oracle_text": "Myriad\nThe \"legend rule\" doesn't apply to creature tokens you control.\nTriggered abilities you control can't cause you to sacrifice or exile creature tokens you control.",
    },
    "Dromoka's Gift": {
        "keywords": ["Bolster"],
        "oracle_text": "Bolster 4. (Choose a creature with the least toughness among creatures you control and put four +1/+1 counters on it.)",
    },
    "Burrenton Bombardier": {
        "keywords": ["Flying", "Reinforce"],
        "oracle_text": "Flying\nReinforce 2—{2}{W} ({2}{W}, Discard this card: Put two +1/+1 counters on target creature.)",
    },
    "Gluttonous Cyclops": {
        "keywords": ["Monstrosity"],
        "oracle_text": "{5}{R}{R}: Monstrosity 3. (If this creature isn't monstrous, put three +1/+1 counters on it and it becomes monstrous.)",
    },
    "Simic Initiate": {
        "keywords": ["Graft"],
        "oracle_text": "Graft 1 (This creature enters with a +1/+1 counter on it. Whenever another creature enters, you may move a +1/+1 counter from this creature onto it.)",
    },
    "Disowned Ancestor": {
        "keywords": ["Outlast"],
        "oracle_text": "Outlast {1}{B} ({1}{B}, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.)",
    },
    "Knight of the Pilgrim's Road": {
        "keywords": ["Renown"],
        "oracle_text": "Renown 1 (When this creature deals combat damage to a player, if it isn't renowned, put a +1/+1 counter on it and it becomes renowned.)",
    },
    "Adaptive Snapjaw": {
        "keywords": ["Evolve"],
        "oracle_text": "Evolve (Whenever a creature you control enters, if that creature has greater power or toughness than this creature, put a +1/+1 counter on this creature.)",
    },
    "Skitter Eel": {
        "keywords": ["Adapt"],
        "oracle_text": "{2}{U}: Adapt 2. (If this creature has no +1/+1 counters on it, put two +1/+1 counters on it.)",
    },
    "Arcbound Worker": {
        "keywords": ["Modular"],
        "oracle_text": "Modular 1 (This creature enters with a +1/+1 counter on it. When it dies, you may put its +1/+1 counters on target artifact creature.)",
    },
    "Apprentice Sharpshooter": {
        "keywords": ["Reach", "Training"],
        "oracle_text": "Reach\nTraining (Whenever this creature attacks with another creature with greater power, put a +1/+1 counter on this creature.)",
    },
    "Lead by Example": {
        "keywords": ["Support"],
        "oracle_text": "Support 2. (Put a +1/+1 counter on each of up to two target creatures.)",
    },
    "Snake of the Golden Grove": {
        "keywords": ["Tribute"],
        "oracle_text": "Tribute 3 (As this creature enters, an opponent of your choice may put three +1/+1 counters on it.)\nWhen this creature enters, if tribute wasn't paid, you gain 4 life.",
    },
    "Amber-Plate Ainok": {
        "keywords": ["Double team", "Endure"],
        "oracle_text": "Double team\nAt the beginning of your second main phase, if this creature is tapped, it endures 1.",
    },
    "Gorger Wurm": {
        "keywords": ["Devour"],
        "oracle_text": "Devour 1 (As this creature enters, you may sacrifice any number of creatures. It enters with that many +1/+1 counters on it.)",
    },
    "Enraged Revolutionary": {
        "keywords": ["Dethrone"],
        "oracle_text": "Dethrone (Whenever this creature attacks the player with the most life or tied for most life, put a +1/+1 counter on it.)",
    },
    "Toph, Greatest Earthbender": {
        "keywords": ["Earthbend"],
        "oracle_text": "When Toph enters, earthbend X, where X is the amount of mana spent to cast her.\nLand creatures you control have double strike.",
    },
    "Harvest Gwyllion": {
        "keywords": ["Wither"],
        "oracle_text": "Wither (This deals damage to creatures in the form of -1/-1 counters.)",
    },
    "Gixian Recycler": {
        "keywords": ["Unearth", "Conjure"],
        "oracle_text": "When Gixian Recycler dies or is put into your graveyard from your hand or library, conjure a card named Gixian Recycler into your graveyard.\nUnearth {1}{B}",
    },
    "Sidisi's Faithful": {
        "keywords": ["Exploit"],
        "oracle_text": "Exploit (When this creature enters, you may sacrifice a creature.)\nWhen this creature exploits a creature, return target creature to its owner's hand.",
    },
    "Unicycle": {
        "keywords": ["First strike", "Haste", "Crew", "Equip"],
        "oracle_text": "First strike, haste\nEquipped creature has first strike and haste.\nEquip {1}\nCrew 1",
    },
    "Blitz Automaton": {
        "keywords": ["Haste", "Prototype"],
        "oracle_text": "Prototype {2}{R} — 3/2 (You may cast this spell with different mana cost, color, and size. It keeps its abilities and types.)\nHaste",
    },
    "Mai and Zuko": {
        "keywords": ["Firebending"],
        "oracle_text": "Firebending 3\nYou may cast Ally spells and artifact spells as though they had flash.",
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
