"""Theme presets for archetype detection.

A canonical, tested library of named matchers for common MTG mechanics.
Each preset bundles a keyword list (matched against Scryfall's ``keywords``
array) and/or a list of regex patterns (matched against oracle text).
Callers use ``get_preset(name).matches(card)`` to test a single card.

Presets ship with test fixtures (``should_match`` / ``should_not_match``
card-name tuples). ``tests/mtg-utils/test_theme_presets.py`` pins each
preset against those fixtures so regex drift is caught before landing.

# Why keywords, not just regex

Scryfall's ``keywords`` array is the authoritative source for named
keyword abilities. Matching by keyword avoids the false-positive problem
regex has with flavor text, reminder text on older printings, and cards
that mention a keyword without having it (e.g. "Target creature gets
flying"). When a theme is a keyword ability (flying, scry, flashback,
cascade, cycling, …) the preset uses the keyword list only.

Regex is reserved for FUNCTIONAL themes without a matching keyword
(removal, mill, reanimate, counterspells, burn, tokens, …). Oracle text
uses both digit and word number forms ("scry 2" vs "mill three cards"),
so the :data:`_COUNT` atom below covers both.

# Public API

- :class:`Preset` — frozen dataclass with name, description, match
  conditions, and test fixtures.
- :func:`get_preset` — look up a preset by name.
- :func:`matches` — convenience wrapper around ``get_preset(name).matches(card)``.
- :func:`list_presets` — ``name -> description`` for discoverability.
- :data:`PRESETS` — the full registry as a frozen dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from mtg_utils.card_classify import get_oracle_text

# Matches a count in digit form, word form (one..twelve), or X. IGNORECASE
# is applied at pattern compile time, so word forms match "Three" too.
_COUNT = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|X)"


@dataclass(frozen=True)
class Preset:
    """A named, testable theme matcher.

    A card matches if ANY declared condition matches:

    - ``keywords``: the card's ``keywords`` array contains any of these
      (case-insensitive).
    - ``patterns``: any regex matches the card's oracle text.
    - ``type_patterns``: any regex matches the card's ``type_line``.
      Useful for kindred/tribal themes where the card's identity comes
      from its creature type (e.g., Llanowar Elves is an Elf whether or
      not its oracle mentions the word).
    - ``layouts``: the card's Scryfall ``layout`` field equals one of
      these (case-sensitive, matching Scryfall values like
      ``"adventure"``, ``"prototype"``, ``"split"``, ``"saga"``).

    All four may be set; they combine with OR. ``should_match`` and
    ``should_not_match`` are card-name fixtures used by the test suite.
    """

    name: str
    description: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()
    type_patterns: tuple[re.Pattern[str], ...] = ()
    layouts: tuple[str, ...] = ()
    should_match: tuple[str, ...] = ()
    should_not_match: tuple[str, ...] = ()

    def matches(self, card: dict) -> bool:
        if self.keywords:
            card_kws = {k.lower() for k in (card.get("keywords") or [])}
            if card_kws & {k.lower() for k in self.keywords}:
                return True
        if self.patterns:
            oracle = get_oracle_text(card)
            if any(p.search(oracle) for p in self.patterns):
                return True
        if self.type_patterns:
            type_line = card.get("type_line") or ""
            if any(p.search(type_line) for p in self.type_patterns):
                return True
        return bool(self.layouts) and card.get("layout") in self.layouts


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    """Compile a tuple of patterns with IGNORECASE."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


# ─── Evergreen keyword abilities ──────────────────────────────────────────
# These match via the card's ``keywords`` array — no regex needed.

_EVERGREEN_KEYWORDS: tuple[Preset, ...] = (
    Preset(
        name="flying",
        description="Creature has flying (evergreen).",
        keywords=("Flying",),
        should_match=("Serra Angel", "Baleful Strix"),
        should_not_match=("Llanowar Elves", "Lightning Bolt"),
    ),
    Preset(
        name="vigilance",
        description="Creature has vigilance (evergreen).",
        keywords=("Vigilance",),
        should_match=("Serra Angel",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="trample",
        description="Creature has trample (evergreen).",
        keywords=("Trample",),
        should_match=("Goldvein Hydra",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="haste",
        description="Creature has haste (evergreen).",
        keywords=("Haste",),
        should_match=("Goblin Guide", "Monastery Swiftspear"),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="deathtouch",
        description="Creature has deathtouch (evergreen).",
        keywords=("Deathtouch",),
        should_match=("Baleful Strix",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="lifelink",
        description="Creature has lifelink (evergreen).",
        keywords=("Lifelink",),
        should_match=("Tymna the Weaver",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="first-strike",
        description="Creature has first strike (evergreen).",
        keywords=("First strike",),
        should_match=("White Knight",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="double-strike",
        description="Creature has double strike (evergreen).",
        keywords=("Double strike",),
        should_match=("Fury",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="reach",
        description="Creature has reach (evergreen).",
        keywords=("Reach",),
        should_match=("Giant Spider",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="menace",
        description="Creature has menace (evergreen).",
        keywords=("Menace",),
        should_match=("Obeka, Splitter of Seconds",),
        should_not_match=("Llanowar Elves",),
    ),
    Preset(
        name="defender",
        description="Creature has defender (evergreen).",
        keywords=("Defender",),
        should_match=("Wall of Omens",),
        should_not_match=("Serra Angel",),
    ),
    Preset(
        name="flash",
        description="Permanent has flash (evergreen).",
        keywords=("Flash",),
        should_match=("Snapcaster Mage", "Dictate of Erebos"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="hexproof",
        description="Permanent has hexproof (evergreen).",
        keywords=("Hexproof",),
        should_match=("Invisible Stalker",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="indestructible",
        description="Permanent has indestructible (evergreen).",
        keywords=("Indestructible",),
        should_match=("Darksteel Myr",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="ward",
        description="Permanent has ward (evergreen).",
        keywords=("Ward",),
        # Note: Star Whale grants ward to OTHER creatures but doesn't have
        # it itself, so it isn't a valid fixture for this preset.
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="protection",
        description="Permanent has protection from something (evergreen).",
        keywords=("Protection",),
        should_match=("White Knight",),
        should_not_match=("Lightning Bolt",),
    ),
)

# ─── Named non-evergreen keyword abilities ────────────────────────────────

_KEYWORD_ABILITIES: tuple[Preset, ...] = (
    Preset(
        name="scry",
        description="Card performs scry N (look at top, may bottom).",
        keywords=("Scry",),
        # Aang's Iceberg has Scry in its keywords array (its waterbend
        # ability scries), so it matches via the Scry keyword directly.
        should_match=("Preordain", "Omen of the Sun", "Magma Jet", "Aang's Iceberg"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="surveil",
        description="Card performs surveil N (look at top, may discard).",
        keywords=("Surveil",),
        should_match=("Thought Erasure", "Notion Rain", "Sinister Sabotage"),
        # Ransack the Lab is sometimes misremembered as surveil but its actual
        # oracle text is "Look at the top three ... put the rest into your
        # graveyard" — no Surveil keyword.
        should_not_match=("Lightning Bolt", "Ransack the Lab"),
    ),
    Preset(
        name="cascade",
        description="Spell has cascade.",
        keywords=("Cascade",),
        should_match=("Bloodbraid Elf", "Shardless Agent"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="flashback",
        description="Spell has flashback.",
        keywords=("Flashback",),
        should_match=("Lingering Souls", "Faithless Looting", "Deep Analysis"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="kicker",
        description="Spell has a kicker cost.",
        keywords=("Kicker",),
        should_match=("Gatekeeper of Malakir",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cycling",
        description="Card has cycling.",
        keywords=("Cycling",),
        should_match=("Ketria Triome",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="evoke",
        description="Creature has evoke.",
        keywords=("Evoke",),
        should_match=("Mulldrifter", "Fury"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="ninjutsu",
        description="Creature has ninjutsu.",
        keywords=("Ninjutsu",),
        should_match=("Fallen Shinobi",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="exalted",
        description="Permanent has exalted.",
        keywords=("Exalted",),
        should_match=("Noble Hierarch", "Qasali Pridemage"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="prowess",
        description="Creature has prowess.",
        keywords=("Prowess",),
        should_match=("Monastery Swiftspear", "Abbot of Keral Keep"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="revolt",
        description="Card cares about revolt.",
        keywords=("Revolt",),
        should_match=("Fatal Push",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="investigate",
        description="Card creates a Clue (investigate).",
        keywords=("Investigate",),
        should_match=("Thraben Inspector",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="landfall",
        description=("Card has landfall (whenever a land enters under your control)."),
        keywords=("Landfall",),
        # Only match the "under your control" variant — the opponent-land
        # trigger form (Tectonic Edge-style, "whenever a land enters the
        # battlefield under an opponent's control") is a different mechanic.
        patterns=_rx(
            r"\blandfall\b",
            r"whenever a land (?:you control )?enters",
            r"whenever a land enters the battlefield under your control",
        ),
        should_match=("Courser of Kruphix", "Bloodghast"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="dredge",
        description="Card has dredge (BANNED in shared-library format).",
        keywords=("Dredge",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="miracle",
        description="Spell has miracle (BANNED in shared-library format).",
        keywords=("Miracle",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="storm",
        description="Spell has storm.",
        keywords=("Storm",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="infect",
        description=(
            "Creature has infect (damage to players = poison counters; "
            "damage to creatures = -1/-1 counters). Includes Poisonous, "
            "the classic 'deals combat damage to a player = N poison' "
            "keyword that Infect generalizes."
        ),
        keywords=("Infect", "Poisonous"),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="toxic",
        description="Creature has toxic.",
        keywords=("Toxic",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="delve",
        description="Spell has delve.",
        keywords=("Delve",),
        should_match=("Murderous Cut",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mill",
        description=(
            "Card has the Mill keyword action (puts cards into a "
            "graveyard from a library). Covers both self-mill and "
            "targeted mill."
        ),
        keywords=("Mill",),
        should_match=("Stitcher's Supplier",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="suspend",
        description="Card has suspend.",
        keywords=("Suspend",),
        should_match=("Star Whale", "Ancestral Vision"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="undying",
        description="Creature has undying.",
        keywords=("Undying",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="persist",
        description="Creature has persist.",
        keywords=("Persist",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="equip",
        description="Equipment with an equip cost.",
        keywords=("Equip",),
        should_match=("Skullclamp", "Helm of the Host"),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="paradigm",
        description=(
            "Spell-copy: exile this spell on resolution. After the first "
            "spell with this name resolves, you may cast a copy of it "
            "from exile for free at the beginning of each of your first "
            "main phases. Recurring free-cast from exile (Secrets of "
            "Strixhaven)."
        ),
        keywords=("Paradigm",),
        should_match=("Improvisation Capstone",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="prepared",
        description=(
            "Creature paired with a spell on a split face (Secrets of "
            "Strixhaven 'prepare' layout). The creature becomes prepared "
            "under a trigger condition (first main phase, attack, etc.). "
            "While prepared, you may cast the paired spell; doing so "
            "unprepares the creature. A conditional two-card single-slot "
            "design, closer in spirit to Adventure than to spell-copy."
        ),
        keywords=("Prepared",),
        layouts=("prepare",),
        should_match=("Scathing Shadelock // Venomous Words",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Individual keyword presets (cast-later / graveyard-cast / spell-copy
    # / tokens / plus-one-counters / misc) ──
    Preset(
        name="foretell",
        description=(
            "Cast-later: exile from hand for {2}, cast for foretell cost next turn or "
            "later (CR 702.145)."
        ),
        keywords=("Foretell",),
        should_match=("Scorn Effigy",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="plot",
        description=(
            "Cast-later: exile from hand, cast for its mana cost on a future turn as a "
            "sorcery (CR 702.167)."
        ),
        keywords=("Plot",),
        should_match=("Djinn of Fool's Fall",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="warp",
        description=(
            "Cast-later: cast from hand for warp cost, exile at the next end step, "
            "cast "
            "again from exile later (CR 702.185)."
        ),
        keywords=("Warp",),
        should_match=("Voidcalled Devotee",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="rebound",
        description=(
            "Cast-later: cast from hand, exile at resolution, cast from exile next "
            "turn "
            "(CR 702.88)."
        ),
        keywords=("Rebound",),
        should_match=("Unnatural Summons",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="impending",
        description=(
            "Cast-later: cast for impending cost; enters as a non-creature enchantment "
            "with time counters and becomes a creature later (CR 702.182)."
        ),
        keywords=("Impending",),
        should_match=("Lurker in the Deep",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="jump-start",
        description=(
            "Graveyard-cast: cast from graveyard by discarding a card in addition to "
            "other costs (CR 702.133)."
        ),
        keywords=("Jump-start",),
        should_match=("Surge of Acclaim",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="aftermath",
        description=(
            "Graveyard-cast: split card whose second half can only be cast from the "
            "graveyard (CR 702.127)."
        ),
        keywords=("Aftermath",),
        should_match=("Appeal // Authority",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="retrace",
        description=(
            "Graveyard-cast: cast from graveyard by discarding a land in addition to "
            "other costs (CR 702.81)."
        ),
        keywords=("Retrace",),
        should_match=("Oona's Grace",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="disturb",
        description=(
            "Graveyard-cast: cast a transformed double-faced card from the graveyard "
            "(CR 702.146)."
        ),
        keywords=("Disturb",),
        should_match=("Baithook Angler // Hook-Haunt Drifter",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mayhem",
        description=(
            "Graveyard-cast: cast from graveyard for the mayhem cost if discarded this "
            "turn (CR 702.187)."
        ),
        keywords=("Mayhem",),
        should_match=("Spider-Islanders",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="harmonize",
        description=(
            "Graveyard-cast: cast from graveyard for a harmonize cost; tap a creature "
            "you control to reduce the cost by {1} (CR 702.180)."
        ),
        keywords=("Harmonize",),
        should_match=("Ureni's Counsel",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="casualty",
        description=(
            "Spell-copy: as you cast, sacrifice a creature with power N or greater to "
            "copy this spell (CR 702.153)."
        ),
        keywords=("Casualty",),
        should_match=("Cut of the Profits",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="replicate",
        description=(
            "Spell-copy: when you cast, pay the replicate cost any number of times to "
            "create that many copies (CR 702.42)."
        ),
        keywords=("Replicate",),
        should_match=("Train of Thought",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cipher",
        description=(
            "Spell-copy: encode this spell on a creature you control; whenever that "
            "creature deals combat damage to a player, you may cast a copy of the "
            "encoded spell (CR 702.99). Niche Dimir mechanic from Gatecrash."
        ),
        keywords=("Cipher",),
        should_match=("Last Thoughts",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="conspire",
        description=(
            "Spell-copy: tap two untapped creatures sharing a color with this spell to "
            "copy it (CR 702.75)."
        ),
        keywords=("Conspire",),
        should_match=("Ghastly Discovery",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="demonstrate",
        description=(
            "Spell-copy: when you cast, you may copy it; if you do, choose an opponent "
            "to copy it too (CR 702.152)."
        ),
        keywords=("Demonstrate",),
        should_match=("Incarnation Technique",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="populate",
        description=(
            "Tokens: create a copy of a creature token you control (CR 701.36)."
        ),
        keywords=("Populate",),
        should_match=("Wake the Reflections",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="amass",
        description=(
            "Tokens: create a Zombie Army creature token or grow the one you have with "
            "+1/+1 counters (CR 701.47)."
        ),
        keywords=("Amass",),
        should_match=("Gríma Wormtongue",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="offspring",
        description=(
            "Tokens: pay extra as you cast a creature to create a 1/1 token copy of it "
            "when it enters (CR 702.175)."
        ),
        keywords=("Offspring",),
        should_match=("Fountainport Charmer",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="manifest",
        description=(
            "Tokens: put a card face down onto the battlefield as a 2/2 creature (CR "
            "701.40)."
        ),
        keywords=("Manifest",),
        should_match=("Paranormal Analyst",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="cloak",
        description=(
            "Tokens: manifest with ward {2} — a 2/2 face-down creature with ward {2} "
            "(CR 701.58)."
        ),
        keywords=("Cloak",),
        should_match=("Ransom Note",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="incubate",
        description=(
            "Tokens: create an Incubator token that transforms into a 3/3 colorless "
            "Phyrexian when 2+ +1/+1 counters are on it (CR 701.53)."
        ),
        keywords=("Incubate",),
        should_match=("Eyes of Gitaxias",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="fabricate",
        description=(
            "Tokens and +1/+1 counters: when this creature enters, choose to create N "
            "1/1 Servo tokens OR put N +1/+1 counters on it (CR 702.123)."
        ),
        keywords=("Fabricate",),
        should_match=("Accomplished Automaton",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="afterlife",
        description=(
            "Tokens: when this creature dies, create N 1/1 white-and-black Spirit "
            "tokens with flying (CR 702.135)."
        ),
        keywords=("Afterlife",),
        should_match=("Debtors' Transport",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="mobilize",
        description=(
            "Tokens: whenever this creature attacks, create N tapped-and-attacking red "
            "Warrior tokens that are sacrificed at end of combat (CR 702.181)."
        ),
        keywords=("Mobilize",),
        should_match=("Dalkovan Outrider",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="encore",
        description=(
            "Tokens: pay the encore cost and exile this creature from your graveyard "
            "to "
            "create a token copy of it for each opponent, each attacking that opponent "
            "(CR 702.141)."
        ),
        keywords=("Encore",),
        should_match=("Broodmate Tyrant",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="myriad",
        description=(
            "Tokens: whenever this creature attacks, for each other opponent, create a "
            "tapped-and-attacking token copy attacking that opponent (CR 702.116)."
        ),
        keywords=("Myriad",),
        should_match=("The Master, Multiplied",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="bolster",
        description=(
            "+1/+1 counters: choose a creature you control with the least toughness "
            "and "
            "put N +1/+1 counters on it (CR 701.39)."
        ),
        keywords=("Bolster",),
        should_match=("Dromoka's Gift",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="reinforce",
        description=(
            "+1/+1 counters: pay reinforce cost and discard this card to put N +1/+1 "
            "counters on target creature (CR 702.77)."
        ),
        keywords=("Reinforce",),
        should_match=("Burrenton Bombardier",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="monstrosity",
        description=(
            "+1/+1 counters: pay an activated cost to put N +1/+1 counters on this "
            "creature and make it monstrous (CR 701.37)."
        ),
        keywords=("Monstrosity",),
        should_match=("Gluttonous Cyclops",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="graft",
        description=(
            "+1/+1 counters: enters with N +1/+1 counters on it; may move one counter "
            "to another creature entering the battlefield (CR 702.58)."
        ),
        keywords=("Graft",),
        should_match=("Simic Initiate",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="outlast",
        description=(
            "+1/+1 counters: sorcery-speed activated ability that puts a +1/+1 counter "
            "on this creature (CR 702.107)."
        ),
        keywords=("Outlast",),
        should_match=("Disowned Ancestor",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="renown",
        description=(
            "+1/+1 counters: when this creature deals combat damage to a player for "
            "the "
            "first time, becomes renowned with N +1/+1 counters (CR 702.112)."
        ),
        keywords=("Renown",),
        should_match=("Knight of the Pilgrim's Road",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="evolve",
        description=(
            "+1/+1 counters: whenever a creature with greater power OR toughness "
            "enters "
            "under your control, put a +1/+1 counter on this creature (CR 702.100)."
        ),
        keywords=("Evolve",),
        should_match=("Adaptive Snapjaw",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="adapt",
        description=(
            "+1/+1 counters: pay adapt cost to put N +1/+1 counters on this creature "
            "if "
            "it has no +1/+1 counters (CR 701.46)."
        ),
        keywords=("Adapt",),
        should_match=("Skitter Eel",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="modular",
        description=(
            "+1/+1 counters: artifact creature enters with N +1/+1 counters; when it "
            "dies, may move them to another artifact creature (CR 702.43)."
        ),
        keywords=("Modular",),
        should_match=("Arcbound Worker",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="training",
        description=(
            "+1/+1 counters: whenever this creature and at least one other creature "
            "with greater power attack, put a +1/+1 counter on this creature (CR "
            "702.149)."
        ),
        keywords=("Training",),
        should_match=("Apprentice Sharpshooter",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="support",
        description=(
            "+1/+1 counters: put a +1/+1 counter on each of up to N target creatures "
            "(CR 701.41)."
        ),
        keywords=("Support",),
        should_match=("Lead by Example",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="tribute",
        description=(
            "+1/+1 counters: an opponent chooses whether this creature enters with N "
            "+1/+1 counters or instead triggers an additional ability (CR 702.104)."
        ),
        keywords=("Tribute",),
        should_match=("Snake of the Golden Grove",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="endure",
        description=(
            "+1/+1 counters OR tokens: modal — choose to put N +1/+1 counters on a "
            "creature or create an N/N Spirit token (CR 702.62)."
        ),
        keywords=("Endure",),
        should_match=("Amber-Plate Ainok",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="devour",
        description=(
            "+1/+1 counters: as this creature enters, you may sacrifice any number of "
            "creatures; it enters with N +1/+1 counters per creature sacrificed this "
            "way (CR 702.82)."
        ),
        keywords=("Devour",),
        should_match=("Gorger Wurm",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="dethrone",
        description=(
            "+1/+1 counters: whenever this creature attacks the player with the most "
            "life, put a +1/+1 counter on it (CR 702.105)."
        ),
        keywords=("Dethrone",),
        should_match=("Enraged Revolutionary",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="earthbend",
        description=(
            "Land animation: turn a target land you control into a 0/0 creature with "
            "haste and put N +1/+1 counters on it. When that land dies or is exiled, "
            "return it tapped (CR 701.66)."
        ),
        keywords=("Earthbend",),
        should_match=("Toph, Greatest Earthbender",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="wither",
        description=(
            "Creature damage: whenever this creature deals damage to a creature, that "
            "damage is dealt as -1/-1 counters instead (CR 702.80)."
        ),
        keywords=("Wither",),
        should_match=("Harvest Gwyllion",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="unearth",
        description=(
            "Reanimate: pay unearth cost to return this card from your graveyard to "
            "the "
            "battlefield with haste; exile it at the beginning of the next end step "
            "(CR "
            "702.84)."
        ),
        keywords=("Unearth",),
        should_match=("Gixian Recycler",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="exploit",
        description=(
            "Sacrifice trigger: when this creature enters, you may sacrifice a "
            "creature "
            "for an additional effect (CR 702.110)."
        ),
        keywords=("Exploit",),
        should_match=("Sidisi's Faithful",),
        should_not_match=("Lightning Bolt",),
    ),
    # crew/prototype/firebending are defined as standalone presets in
    # _FUNCTIONAL_PRESETS below (with richer descriptions + layout support).
)

# ─── Functional regex presets ─────────────────────────────────────────────
# Themes without a matching keyword ability. Each pattern is tested against
# the should_match / should_not_match fixtures in the test suite.

_FUNCTIONAL_PRESETS: tuple[Preset, ...] = (
    # Top-of-library manipulation: scry + surveil keywords, plus "look/reveal/
    # exile the top" non-keyword phrasings. Handles both singular ("the top
    # card") and plural ("the top four cards") forms.
    Preset(
        name="top-manipulation",
        description=(
            "Any effect that looks at, reveals, scries, surveils, or "
            "exiles cards from the top of the library."
        ),
        keywords=("Scry", "Surveil"),
        patterns=_rx(
            r"look at the top (?:card\b|" + _COUNT + r" cards?)",
            r"reveal the top (?:card\b|" + _COUNT + r" cards?)",
            r"exile the top (?:card\b|" + _COUNT + r" cards?)",
        ),
        should_match=(
            "Preordain",
            "Thought Erasure",
            "Abbot of Keral Keep",
            "Satyr Wayfinder",
        ),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Self-mill: two phrasings. Modern cards like Stitcher's Supplier say
    # "put the top N cards of your library into your graveyard" directly.
    # Filter cards (Satyr Wayfinder, Grisly Salvage, Ransack the Lab,
    # Commune with the Gods) say "reveal/look at the top N cards of your
    # library" and then put "the rest" into your graveyard. The second
    # pattern requires the explicit "put the rest ... graveyard" anchor so
    # it doesn't false-match Contingency-Plan-style cards whose oracle
    # mentions "graveyard" for unrelated reasons.
    Preset(
        name="self-mill",
        description=(
            "Puts cards from YOUR library into YOUR graveyard "
            "(graveyard-value, not targeted mill)."
        ),
        patterns=_rx(
            r"put the top " + _COUNT + r" cards? of your library into your graveyard",
            r"(?:reveal|look at) the top "
            + _COUNT
            + r" cards? of your library[\s\S]*?the rest into your graveyard",
        ),
        should_match=(
            "Stitcher's Supplier",
            "Satyr Wayfinder",
            "Grisly Salvage",
            "Ransack the Lab",
        ),
        # Contingency Plan is the canonical false-positive test case —
        # its oracle reveals top 5 but returns them to the library.
        should_not_match=("Lightning Bolt", "Counterspell", "Contingency Plan"),
    ),
    # Counter target <spell|ability>. Does NOT match "+1/+1 counter" because
    # "counter target" is a specific phrase.
    Preset(
        name="counterspell",
        description="Counters a target spell or ability.",
        patterns=_rx(r"counter target .*\b(spell|ability)\b"),
        should_match=("Counterspell", "Mana Leak", "Remand", "Sinister Sabotage"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Creature/permanent removal — copied from cube_balance._REMOVAL_PATTERNS.
    # Intentionally generous: catches hard and soft removal both. Used by
    # cube-balance for its removal density metric.
    Preset(
        name="removal",
        description=(
            "Creature/permanent removal — destroy/exile/counter/damage/"
            "bounce/fight/-X effects (intentionally generous)."
        ),
        patterns=_rx(
            r"\bdestroy\s+target\b",
            r"\bdestroy\s+all\b",
            r"\bdestroy\s+(?:each|up to)\b",
            r"\bexile\s+target\b",
            r"\bexile\s+all\b",
            r"\bexile\s+up to\b",
            r"\bcounter\s+target\b",
            r"\bdeals?\s+\d+\s+damage\s+to\s+(?:target\s+creature|any target)",
            r"\bdeals?\s+\d+\s+damage\s+divided\b.*\btargets?\b",
            r"\breturn\s+target\s+(?:creature|(?:nonland )?permanent)\b.*\bhand\b",
            r"\bfights?\s+target\b",
            r"\btarget\s+creature\s+gets\s+-\d",
            # Toxic Deluge, Black Sun's Zenith style mass -N/-N. The `\b`
            # around `-X/-X` is intentionally dropped — `-` isn't a word
            # character, so `\b-` can never match. Use a looser anchor.
            r"(?<!\w)-X/-X\b",
        ),
        should_match=(
            "Swords to Plowshares",
            "Lightning Bolt",
            "Counterspell",
            "Wrath of God",
            "Toxic Deluge",
            "Prey Upon",  # fight branch
            "Electrolyze",  # divided-damage branch
            "Disfigure",  # -N/-N branch
            "Boomerang",  # universal bounce branch
            "Farewell",  # exile-all branch
        ),
        should_not_match=("Llanowar Elves", "Command Tower"),
    ),
    # Board wipe — subset of removal that hits all/many creatures.
    Preset(
        name="board-wipe",
        description="Destroys or damages all creatures (board-wide removal).",
        patterns=_rx(
            r"\bdestroy all (?:creatures|nonland)",
            r"\bexile all (?:creatures|nonland)",
            r"\bdeals? " + _COUNT + r" damage to each creature",
        ),
        should_match=("Wrath of God", "Farewell"),
        should_not_match=("Lightning Bolt", "Swords to Plowshares"),
    ),
    # ── Type-specific removal ──
    #
    # These are strict: they match cards that NAME the target type (or its
    # umbrellas like "creature or planeswalker"). Cards with universal
    # "destroy target permanent" phrasing (Vindicate, Beast Within) appear
    # only in `universal-removal`; count both presets to get the full set
    # of cards that can answer a given type.
    #
    # All patterns use [^.]* to stay within a single sentence, avoiding
    # false-positives like Beast Within where "creature token" appears
    # AFTER the destroy clause.
    #
    # Overlap warning: presets deliberately overlap where cards can answer
    # multiple types — e.g. Lightning Bolt matches both `creature-removal`
    # and `planeswalker-removal` via "any target" burn, and Hero's
    # Downfall matches both via "creature or planeswalker". This is
    # correct (Bolt CAN kill either) but callers summing counts across
    # presets will double-count these cards. Use set-union semantics on
    # the `cards` list in each theme's audit result if you need
    # deduplicated totals.
    Preset(
        name="creature-removal",
        description=(
            "Single-target creature removal: destroy/exile target creature, "
            "damage-to-creature, fight, -X/-X, creature-or-planeswalker. "
            "Includes the Fight keyword action (CR 701.14), Infect "
            "(702.90 — damage to creatures as -1/-1 counters), and Wither "
            "(702.80 — like infect but creature-only). Note: 'target "
            "creature gets -N' matches any toughness debuff including soft "
            "combat tricks (e.g. -0/-2); callers treat this as generous. "
            "For a stricter definition use a custom --theme."
        ),
        keywords=("Fight", "Infect", "Wither"),
        patterns=_rx(
            r"(?:destroy|exile) target [^.]*?\bcreature\b",
            r"\bdeals? \d+ damage to (?:target creature|any target)",
            r"\bdeals? \d+ damage divided [^.]*?targets?\b",
            r"\bfights? target\b",
            r"\btarget creature gets -\d",
            # Mass -N/-N removal (Toxic Deluge, Black Sun's Zenith).
            # `-` isn't a word char, so `\b-` never matches; use a
            # negative-lookbehind anchor instead.
            r"(?<!\w)-X/-X\b",
        ),
        should_match=(
            "Swords to Plowshares",
            "Doom Blade",
            "Lightning Bolt",
            "Hero's Downfall",
            "Toxic Deluge",
            "Prey Upon",  # fight branch
            "Electrolyze",  # divided-damage branch
            "Disfigure",  # -N/-N branch
        ),
        should_not_match=(
            "Counterspell",  # counters a spell, doesn't remove a creature
            "Llanowar Elves",
            "Beast Within",  # universal-removal, not creature-specific
            "Shatter",  # artifact-specific
        ),
    ),
    Preset(
        name="artifact-removal",
        description=(
            "Single-target artifact removal: destroy/exile target artifact "
            "(including 'target artifact or enchantment' bridge spells)."
        ),
        patterns=_rx(
            r"(?:destroy|exile) target [^.]*?\bartifact\b",
        ),
        should_match=("Shatter", "Disenchant", "Reclamation Sage"),
        should_not_match=("Lightning Bolt", "Wrath of God", "Sinkhole"),
    ),
    Preset(
        name="enchantment-removal",
        description=(
            "Single-target enchantment removal: destroy/exile target "
            "enchantment (including 'target artifact or enchantment')."
        ),
        patterns=_rx(
            r"(?:destroy|exile) target [^.]*?\benchantment\b",
        ),
        should_match=("Disenchant", "Reclamation Sage"),
        should_not_match=("Lightning Bolt", "Shatter", "Sinkhole"),
    ),
    Preset(
        name="land-removal",
        description=(
            "Land destruction, single-target or mass (MLD). Includes "
            "Sinkhole, Strip Mine, Wasteland, Armageddon, Jokulhaups."
        ),
        patterns=_rx(
            r"(?:destroy|exile) target [^.]*?\bland\b",
            r"\bdestroy all [^.]*?\blands?\b",
            r"\bexile all [^.]*?\blands?\b",
        ),
        should_match=("Sinkhole", "Strip Mine", "Wasteland", "Armageddon"),
        should_not_match=("Lightning Bolt", "Doom Blade", "Wrath of God"),
    ),
    Preset(
        name="planeswalker-removal",
        description=(
            "Single-target planeswalker removal: destroy/exile target "
            "planeswalker, damage to planeswalker, creature-or-planeswalker."
        ),
        patterns=_rx(
            r"(?:destroy|exile) target [^.]*?\bplaneswalker\b",
            r"\bdeals? \d+ damage to (?:target planeswalker|any target"
            r"|target creature or planeswalker)",
        ),
        should_match=("Hero's Downfall", "Lightning Bolt"),
        should_not_match=("Counterspell", "Shatter"),
    ),
    Preset(
        name="universal-removal",
        description=(
            "Destroys or exiles any permanent regardless of type. Covers "
            "the canonical universal answers (Vindicate, Beast Within, "
            "Abrupt Decay, Assassin's Trophy) plus type/color-restricted "
            "universal effects: 'destroy target noncreature permanent' "
            "(Woodfall Primus, Rootgrapple, Nicol Bolas +3), 'destroy "
            "target [color] permanent' (Elemental Blasts, Paladin cycle), "
            "and 'destroy target noncreature, nonland permanent' "
            "(Witherbloom Command). Cards here are in addition to the "
            "type-specific presets — check both for full coverage of a "
            "given permanent type."
        ),
        patterns=_rx(
            # Matches "destroy/exile target [...]permanent" with any
            # modifiers (nonland, noncreature, color-restricted, etc.)
            # between target and permanent. The [^.]*? sentence-boundary
            # gate prevents matching across the period into an unrelated
            # later clause (e.g., Beast Within's "creates a 3/3 ... token"
            # sentence).
            r"(?:destroy|exile) target [^.]*?\bpermanent\b",
        ),
        should_match=(
            "Vindicate",
            "Beast Within",
            "Maelstrom Pulse",
            "Nicol Bolas, Planeswalker",
        ),
        should_not_match=(
            "Lightning Bolt",
            "Swords to Plowshares",  # creature-only
            "Shatter",  # artifact-only
            "Wrath of God",  # mass, not single-target universal
        ),
    ),
    # Bounce — return target creature/permanent to hand.
    Preset(
        name="bounce",
        description=(
            "Returns a target creature, nonland permanent, or permanent "
            "to its owner's hand."
        ),
        patterns=_rx(
            r"return target (?:creature|nonland permanent|permanent)"
            r"\b.*\b(?:to|into) .*\bhand\b",
        ),
        should_match=("Unsummon", "Boomerang"),
        should_not_match=("Lightning Bolt",),
    ),
    # Targeted discard — opponent discards card(s).
    Preset(
        name="discard",
        description="Forces a target player or opponent to discard cards.",
        patterns=_rx(
            r"target (?:opponent|player) (?:discards|reveals (?:their|his/her) hand)",
            r"each (?:player|opponent) discards",
        ),
        should_match=(),  # fixture cards added if Thoughtseize etc. exist in test data
        should_not_match=("Lightning Bolt",),
    ),
    # Tutors — search your library for a card.
    Preset(
        name="tutors",
        description=(
            "Searches your library for a card (BANNED in shared-library format)."
        ),
        patterns=_rx(r"\bsearch (?:your|target opponent's|a) library\b"),
        should_match=("Sakura-Tribe Elder", "Cultivate"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Creature-token creation. Oracle text uses both singular ("create a
    # 1/1 ... creature token") and plural ("create two 1/1 ... creature
    # tokens"), so the count atom here accepts "a"/"an" in addition to
    # digit/word-form numbers. Includes Embalm and Eternalize — their
    # reminder text says "Create a token that's a copy of it" (omitting
    # "creature token" literally), so the regex misses them; the keyword
    # tuple catches them instead.
    Preset(
        name="tokens",
        description=(
            "Creates one or more creature tokens. Covers the broad family "
            "of keywords that create creature tokens: Embalm and "
            "Eternalize (Zombie copies from graveyard), Populate (copy "
            "your own token), Amass (Zombie Army), Offspring (1/1 copy), "
            "Manifest and Cloak (face-down 2/2), Incubate (Incubator "
            "transform token), Fabricate (Servos), Afterlife (Spirits "
            "on death), Mobilize (attacking Warriors), Encore (attacking "
            "copies), Myriad (combat token copies)."
        ),
        keywords=(
            "Embalm",
            "Eternalize",
            "Populate",
            "Amass",
            "Offspring",
            "Manifest",
            "Cloak",
            "Incubate",
            "Fabricate",
            "Afterlife",
            "Mobilize",
            "Encore",
            "Myriad",
        ),
        patterns=_rx(r"create (?:a|an|" + _COUNT + r").*\bcreature token"),
        should_match=(
            "Omen of the Sun",
            "Blade Splicer",
            "Lingering Souls",
            "Angel of Sanctions",  # Embalm
        ),
        should_not_match=("Lightning Bolt",),
    ),
    # Sacrifice outlet: "sacrifice X: <effect>" (colon makes it an activated
    # ability cost, per Lucky Paper). The "^" anchor means start-of-paragraph
    # to avoid false-matching cards that reference sacrificing in other ways.
    Preset(
        name="sacrifice-outlet",
        description=(
            "Has a repeatable activated ability whose cost includes "
            "sacrificing a creature or permanent."
        ),
        patterns=_rx(
            r"(?m)^sacrifice (?:a|another) (?:creature|permanent|artifact)[^.]*:",
            r", sacrifice (?:a|another) (?:creature|permanent|artifact)[^.]*:",
        ),
        should_match=("Viscera Seer", "Ashnod's Altar"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Burn: direct damage to creature or player.
    Preset(
        name="burn",
        description=(
            "Deals direct damage to a creature, player, planeswalker, or any target."
        ),
        patterns=_rx(
            r"deals? "
            + _COUNT
            + r" damage to (?:any target|target creature|target player|"
            r"target (?:opponent|planeswalker)|target (?:creature, player,|"
            r"creature or player))"
        ),
        should_match=("Lightning Bolt",),
        should_not_match=("Counterspell", "Llanowar Elves"),
    ),
    # Reanimate-to-battlefield: the classic "put target creature card from a
    # graveyard onto the battlefield" effect.
    Preset(
        name="reanimate",
        description=(
            "Puts a creature card from a graveyard onto the battlefield "
            "(reanimator-style, not just grave-to-hand)."
        ),
        patterns=_rx(
            r"(?:put|return) target creature card.*graveyard.*"
            r"(?:onto|to) the battlefield",
            r"return enchanted creature card.*to the battlefield",
        ),
        should_match=("Reanimate",),
        should_not_match=("Lightning Bolt", "Counterspell", "Regrowth"),
    ),
    # Graveyard-to-hand recursion (Eternal Witness-style).
    Preset(
        name="graveyard-return",
        description=(
            "Returns a card from a graveyard to a player's hand "
            "(Eternal Witness, Regrowth, Raise Dead)."
        ),
        patterns=_rx(
            r"return .*\bcard\b.*from (?:a|your|target [^.]*) graveyard.*"
            r"(?:to|into) .*\bhand\b",
        ),
        should_match=("Regrowth", "Eternal Witness"),
        should_not_match=("Lightning Bolt",),
    ),
    # Simple cantrip: "draw a card". Matches Ponder, Opt, Think Twice, and
    # any spell with a rider "draw a card". False-positive risk on cards that
    # make OPPONENTS draw — those are caught by the pattern boundary (drawing
    # effects use "you draw" or bare "draw", not "target opponent draws").
    Preset(
        name="cantrip",
        description=(
            "Draws exactly ONE card as a rider or primary effect. For "
            "multi-card draw effects use 'card-draw'."
        ),
        # Matches three distinct phrasings: the bare infinitive ("draw a
        # card", most spells), the third-person trigger form ("draws a
        # card", Cephalid Broker-style), and the group-hug phrasing ("draws
        # an additional card", Howling Mine / Kami of the Crescent Moon).
        patterns=_rx(r"\bdraws? (?:a|an additional) card\b"),
        should_match=("Ponder", "Remand", "Rhystic Study", "Howling Mine"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Card draw (multi-card effects): draws 2+ cards in a single effect.
    # Does not overlap with cantrip.
    Preset(
        name="card-draw",
        description="Draws two or more cards in a single effect.",
        patterns=_rx(
            r"\bdraws? " + _COUNT + r" cards?\b",
            r"\bdraw cards equal to\b",
        ),
        should_match=("Mulldrifter", "Deep Analysis", "Brainstorm"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # Lifegain — gains life AS an effect, OR cares about gaining life as a
    # payoff (whenever-trigger). Typed broadly because lifegain as an
    # archetype includes both the "taps" and the "matters" sides.
    Preset(
        name="lifegain",
        description=(
            "Gains life OR triggers when you gain life (lifegain-matters). "
            "Includes the Secrets of Strixhaven `Infusion` payoff whose "
            "trigger is 'if you gained life this turn, <bonus>'."
        ),
        keywords=("Infusion",),
        patterns=_rx(
            r"\bgains? " + _COUNT + r" life\b",
            r"\bgain life equal to\b",
            r"\bwhenever you gain life\b",
            r"\blifelink\b",  # catches e.g. "target creature gains lifelink"
        ),
        should_match=("Thragtusk", "Lightning Helix", "Efflorescence"),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # +1/+1 counters — puts +1/+1 counters on a creature, OR cares about
    # creatures with +1/+1 counters. Covers the classic counters-matter
    # archetype (Simic, Abzan, Hardened Scales, etc.). Excludes other
    # counter types (loyalty, charge, time, etc.) by anchoring on the
    # literal "+1/+1" token.
    Preset(
        name="plus-one-counters",
        description=(
            "Puts +1/+1 counters on creatures OR cares about creatures with "
            "+1/+1 counters (counters-matter archetype). Includes every "
            "keyword whose primary mechanic is adding +1/+1 counters: "
            "Bolster, Increment (SOS), Reinforce, Monstrosity, Graft, "
            "Outlast, Renown, Evolve, Adapt, Modular, Fabricate (modal), "
            "Training, Support, Tribute, Endure (modal), Devour, Dethrone."
        ),
        keywords=(
            "Bolster",
            "Increment",
            "Reinforce",
            "Monstrosity",
            "Graft",
            "Outlast",
            "Renown",
            "Evolve",
            "Adapt",
            "Modular",
            "Fabricate",
            "Training",
            "Support",
            "Tribute",
            "Endure",
            "Devour",
            "Dethrone",
        ),
        patterns=_rx(
            r"\+1/\+1 counter",
            r"with a \+1/\+1 counter on it",
        ),
        should_match=(
            "Scavenging Ooze",
            "Goldvein Hydra",
            "Berta, Wise Extrapolator",
        ),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # Cantrip gets Connive added via keywords tuple — Connive's core effect
    # is "draw a card, then discard a card" (with a +1/+1 rider on nonland
    # discards), so it's card-filtering; matches cantrip's single-card-draw
    # semantics.
    Preset(
        name="connive",
        description=(
            "Keyword action from Streets of New Capenna: draw a card, "
            "then discard a card. If a nonland card was discarded, put "
            "a +1/+1 counter on the conniving creature."
        ),
        keywords=("Connive",),
        should_match=("Change of Plans",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Cost-reduction via tapping (Convoke / Improvise / Waterbend) ──
    #
    # All three let you tap untapped permanents rather than pay mana to
    # cast a spell. Convoke (702.51) taps creatures; Improvise (702.126)
    # taps artifacts; Waterbend (701.67) taps both — it's the Avatar
    # crossover's generalized "each tap pays for {1}" cost mechanic.
    Preset(
        name="convoke",
        description=(
            "Tap untapped creatures you control rather than pay mana to "
            "cast a spell (CR 702.51)."
        ),
        keywords=("Convoke",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="improvise",
        description=(
            "Tap untapped artifacts you control rather than pay mana to "
            "cast a spell (CR 702.126). Artifact-cost-reduction sibling "
            "of Convoke."
        ),
        keywords=("Improvise",),
        should_match=(),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="waterbend",
        description=(
            "Alt-cost mechanic from the Avatar crossover (CR 701.67). "
            "While paying a waterbend cost, tap untapped artifacts or "
            "creatures to help — each tap pays for {1}. Generalizes "
            "Convoke + Improvise into a single keyword action."
        ),
        keywords=("Waterbend",),
        should_match=("Aang's Iceberg",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Airbend (Avatar crossover) ──
    #
    # Per CR 701.65 (glossary says "Airbend", not "Airbending" — the
    # Scryfall keywords array uses "Airbend"): exiles one or more
    # permanents/spells; the owner of each exiled card may cast it
    # from exile for {2}. Mechanically closer to Warp/Suspend than
    # to bounce; NOT in the `bounce` preset because airbend never
    # returns cards to hand.
    #
    # Does NOT include Warp (CR 702.185) — Warp is a cast-from-hand-
    # for-alternative-cost-then-exile-at-EOT keyword (a suspend-like
    # cast-later mechanic), distinct enough from airbend's "exile
    # someone else's thing, they may recast for {2}" mechanic that
    # bundling them would conflate politically very different cards.
    Preset(
        name="airbend",
        description=(
            "Exile a permanent or spell and let its owner cast it from "
            "exile for {2} (Airbend, Avatar crossover, CR 701.65)."
        ),
        keywords=("Airbend",),
        should_match=("Aang, the Last Airbender",),
        should_not_match=("Lightning Bolt", "Unsummon", "Boomerang"),
    ),
    # ── Proliferate ──
    Preset(
        name="proliferate",
        description=(
            "Choose any number of permanents and/or players with counters "
            "and add another counter of each kind. Scales with +1/+1, "
            "poison, -1/-1, charge, loyalty counters — so proliferate "
            "decks usually pair with counter-producing archetypes."
        ),
        keywords=("Proliferate",),
        should_match=("Contagion Clasp", "Atraxa, Praetors' Voice"),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Goad (political / multiplayer) ──
    Preset(
        name="goad",
        description=(
            "Forces a creature to attack each combat — and to attack a "
            "player other than its controller. Strong multiplayer "
            "politics mechanic."
        ),
        keywords=("Goad",),
        should_match=("Disrupt Decorum",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Magecraft (Strixhaven spellslinger) ──
    Preset(
        name="magecraft",
        description=(
            "Triggers 'whenever you cast or copy an instant or sorcery "
            "spell' — the Strixhaven spellslinger payoff. Mechanically "
            "overlaps with Prowess (combat buff on spell cast) but "
            "Magecraft can trigger any effect, so it gets its own preset."
        ),
        keywords=("Magecraft",),
        should_match=("Storm-Kiln Artist", "Archmage Emeritus"),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Opus (Secrets of Strixhaven big-spells trigger) ──
    Preset(
        name="opus",
        description=(
            "Triggers on instant/sorcery casts with a 5+-mana threshold. "
            "The effect can be anything — not just combat buffs — and "
            "Opus cards typically have a lesser mode that triggers for "
            "cheaper instants/sorceries as well. Big-spells-matter "
            "spellslinger archetype."
        ),
        keywords=("Opus",),
        should_match=("Colorstorm Stallion",),
        should_not_match=("Lightning Bolt", "Monastery Swiftspear"),
    ),
    # ── Graveyard-cast umbrella (cast-from-graveyard mechanics) ──
    #
    # Strict: only keywords that actually CAST the card from the
    # graveyard. Notably excludes:
    #   * Embalm/Eternalize — create a TOKEN COPY, not cast the card.
    #     These live in the `tokens` preset.
    #   * Unearth — RETURNS the card to the battlefield, not cast.
    #     Lives in the `reanimate` preset.
    Preset(
        name="graveyard-cast",
        description=(
            "Umbrella for 'cast this card from the graveyard' keyword "
            "mechanics: Flashback, Jump-start, Aftermath, Retrace, "
            "Escape, Disturb, Mayhem. Graveyard-value payoff. The "
            "narrower `flashback` preset still exists; use this one "
            "when you want the full cast-from-graveyard archetype "
            "density."
        ),
        keywords=(
            "Flashback",
            "Jump-start",
            "Aftermath",
            "Retrace",
            "Escape",
            "Disturb",
            "Mayhem",
            "Harmonize",
        ),
        should_match=(
            "Lingering Souls",  # Flashback
            "Chemister's Insight",  # Jump-start
            "Kroxa, Titan of Death's Hunger",  # Escape
        ),
        should_not_match=(
            "Lightning Bolt",
            "Counterspell",
            "Angel of Sanctions",  # Embalm creates a token, not cast
        ),
    ),
    # ── Cast-later family (exile-then-cast-later mechanics) ──
    Preset(
        name="cast-later",
        description=(
            "Cards that are cast at a time other than normal spell timing — "
            "exiled or held to be cast on a future turn, often for an "
            "alternative cost. Covers Suspend, Foretell, Plot, Warp, "
            "Rebound, Impending, and Adventure (matched via the 'adventure' "
            "layout since Scryfall doesn't tag it as a keyword)."
        ),
        keywords=(
            "Suspend",
            "Foretell",
            "Plot",
            "Warp",
            "Rebound",
            "Impending",
        ),
        layouts=("adventure",),
        should_match=(
            "Ancestral Vision",  # Suspend
            "Scorn Effigy",  # Foretell
            "Djinn of Fool's Fall",  # Plot
            "Voidcalled Devotee",  # Warp
        ),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # ── Spell-copy family ──
    Preset(
        name="spell-copy",
        description=(
            "Copies a spell (self or another spell). Covers Storm, "
            "Casualty, Replicate, Cipher, Conspire, Demonstrate, and the "
            "Secrets of Strixhaven 'Paradigm' recurring free-cast-from-"
            "exile mechanic. Does NOT include Splice (which adds text "
            "onto an Arcane spell rather than copying) or Prepared "
            "(which casts a paired spell, not a copy of the current one)."
        ),
        keywords=(
            "Storm",
            "Casualty",
            "Replicate",
            "Cipher",
            "Conspire",
            "Demonstrate",
            "Paradigm",
        ),
        should_match=(
            "Weather the Storm",
            "Cut of the Profits",  # Casualty
            "Train of Thought",  # Replicate
            "Last Thoughts",  # Cipher
            "Improvisation Capstone",  # Paradigm
        ),
        should_not_match=("Lightning Bolt", "Counterspell"),
    ),
    # ── Edict family (forced-sacrifice) ──
    Preset(
        name="edict",
        description=(
            "Forced-sacrifice effects. Defender chooses which permanent "
            "to sacrifice (a kind of removal that bypasses hexproof/"
            "indestructible). Covers the Annihilator keyword + 'target/"
            "each player sacrifices a <type>' regex."
        ),
        keywords=("Annihilator",),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*"
            r"(?:creature|permanent|artifact|land|enchantment|planeswalker)",
        ),
        should_match=("Diabolic Edict",),
        should_not_match=("Lightning Bolt", "Wrath of God", "Vindicate"),
    ),
    Preset(
        name="creature-edict",
        description=(
            "Forced-sacrifice of a creature (Diabolic Edict, Fleshbag "
            "Marauder, Plaguecrafter, Liliana's Triumph, Sheoldred's "
            "Edict). Mass forms like Barter in Blood also match. "
            "Includes 'creature or planeswalker' modals."
        ),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*creatures?",
        ),
        should_match=("Diabolic Edict",),
        should_not_match=("Lightning Bolt", "Shatter", "Sinkhole"),
    ),
    Preset(
        name="artifact-edict",
        description=(
            "Forced-sacrifice of an artifact — rare category, mostly "
            "Tribute to the Wild, Pick Your Poison, Perilous Predicament."
        ),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*artifacts?",
        ),
        should_match=("Tribute to the Wild",),
        should_not_match=("Lightning Bolt", "Diabolic Edict"),
    ),
    Preset(
        name="enchantment-edict",
        description=(
            "Forced-sacrifice of an enchantment — rare category "
            "(Dromoka's Command, Pharika's Libation, Abzan Advantage)."
        ),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*enchantments?",
        ),
        should_match=("Dromoka's Command",),
        should_not_match=("Lightning Bolt",),
    ),
    Preset(
        name="land-edict",
        description=(
            "Forced-sacrifice of a land. Includes mass LD like Wildfire "
            "and Epicenter, plus Smallpox-style combined effects."
        ),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*lands?",
        ),
        should_match=("Wildfire",),
        should_not_match=("Lightning Bolt", "Armageddon"),
    ),
    Preset(
        name="planeswalker-edict",
        description=(
            "Forced-sacrifice of a planeswalker — very rare. Usually "
            "appears as 'sacrifices a creature or planeswalker' in modern "
            "edict design (Sheoldred's Edict, Angrath's Rampage), so this "
            "overlaps heavily with creature-edict."
        ),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*"
            r"(?:[^.]*? )?planeswalkers?",
        ),
        should_match=("Sheoldred's Edict",),
        should_not_match=("Lightning Bolt", "Diabolic Edict"),
    ),
    Preset(
        name="universal-edict",
        description=(
            "Forced-sacrifice of any permanent type. Includes "
            "Annihilator (CR 702.86) — attack trigger forcing defender "
            "to sacrifice N permanents of their choice — and spells "
            "like Shard of the Void Dragon, World Queller, Martyr's "
            "Bond, Rishadan Brigand."
        ),
        keywords=("Annihilator",),
        patterns=_rx(
            r"(?:target|each)(?:\s+\w+)*?\s+(?:player|opponent)s?"
            r"\s+sacrifices?\s+"
            r"(?:a|an|\d+|one|two|three|four|five)?\s*"
            r"(?:nonland )?permanents?",
        ),
        should_match=("Shard of the Void Dragon", "Martyr's Bond"),
        should_not_match=("Lightning Bolt", "Diabolic Edict", "Wildfire"),
    ),
    # ── Land-animation (manlands + Earthbend) ──
    Preset(
        name="land-animation",
        description=(
            "Turns a land into a creature. Covers manland cards via "
            "regex (Treetop Village, Celestial Colonnade, Mutavault, "
            "Creeping Tar Pit, etc.) and the Earthbend keyword from "
            "the Avatar crossover (CR 701.66)."
        ),
        keywords=("Earthbend",),
        patterns=_rx(
            # Matches self-animating lands ("this land becomes a creature")
            # and targeted land-animation ("target land becomes a creature").
            r"(?:this|target) land [^.]*?becomes? a[^.]*?\bcreature\b",
            r"land (?:you control )?becomes? a[^.]*?\bcreature\b",
        ),
        should_match=("Mutavault", "Treetop Village"),
        should_not_match=("Lightning Bolt", "Counterspell", "Sinkhole"),
    ),
    # ── Vehicles (Crew) ──
    Preset(
        name="crew",
        description=(
            "Vehicles with a crew cost — tap creatures with total power "
            "N or greater to animate the Vehicle until end of turn "
            "(CR 702.122). Vehicles are a distinct archetype."
        ),
        keywords=("Crew",),
        should_match=("Unicycle",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Prototype (alt-cost smaller mode) ──
    Preset(
        name="prototype",
        description=(
            "Cast the card for its prototype cost with different mana "
            "value, color, and power/toughness — usually a smaller, "
            "cheaper mode (CR 702.160). The Scryfall layout is also "
            "'prototype' on these cards."
        ),
        keywords=("Prototype",),
        layouts=("prototype",),
        should_match=("Blitz Automaton",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Firebending (combat-triggered red mana) ──
    Preset(
        name="firebending",
        description=(
            "Combat-triggered red mana: whenever this creature attacks, "
            "add N red mana until end of combat (CR 702.189). Avatar "
            "crossover mechanic."
        ),
        keywords=("Firebending",),
        should_match=("Mai and Zuko",),
        should_not_match=("Lightning Bolt",),
    ),
    # ── Turn manipulation ──────────────────────────────────────────────
    # Extra-turn / extra-combat / extra-upkeep payoffs that commander
    # archetypes (Obeka, Aurelia, Godo, Isshin, Narset) are built around.
    # These are not keyword abilities — pure oracle-text regex.
    Preset(
        name="extra-turns",
        description=(
            "Take another turn after this one. Time Walk effects — the "
            "pillar of Obeka / Narset / Sakashima extra-turns archetypes "
            "(Time Walk, Temporal Manipulation, Nexus of Fate, "
            "Expropriate, Temporal Trespass)."
        ),
        patterns=_rx(r"take an (?:extra|additional) turn"),
        should_match=("Time Walk", "Temporal Manipulation", "Nexus of Fate"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    Preset(
        name="extra-combats",
        description=(
            "Additional combat phase. Aggravated Assault, Seize the Day, "
            "Waves of Aggression — the pillar of Aurelia / Godo / Isshin "
            "commander archetypes and multi-combat 60-card lists."
        ),
        patterns=_rx(r"additional combat phase"),
        should_match=("Aggravated Assault", "Seize the Day", "Waves of Aggression"),
        should_not_match=("Lightning Bolt", "Serra Angel"),
    ),
    Preset(
        name="extra-upkeeps",
        description=(
            "Additional upkeep step. Paradox Haze and Obeka Splitter of "
            "Seconds turn beginning-of-upkeep triggers into repeatable "
            "engines — the core of upkeep-payoff archetypes."
        ),
        patterns=_rx(r"additional upkeep steps?"),
        should_match=("Obeka, Splitter of Seconds", "Paradox Haze"),
        should_not_match=("Lightning Bolt", "Llanowar Elves"),
    ),
    # ── Blink / ETB abuse ──────────────────────────────────────────────
    # Exile-then-return-to-battlefield cards that re-trigger enter-the-
    # battlefield effects. [^.]*? gate prevents crossing sentence
    # boundaries, so Angel of Sanctions ("exile ... until this creature
    # leaves the battlefield" — exile + battlefield but no "return") does
    # not falsely match.
    Preset(
        name="blink",
        description=(
            "ETB abuse: exile then return to the battlefield. Soulherder, "
            "Ephemerate, Eldrazi Displacer, Conjurer's Closet, "
            "Restoration Angel — re-trigger enter-the-battlefield effects "
            "by flickering creatures in and out of exile."
        ),
        patterns=_rx(r"exile[^.]*?return[^.]*?battlefield"),
        should_match=("Soulherder", "Ephemerate", "Conjurer's Closet"),
        should_not_match=("Lightning Bolt", "Angel of Sanctions"),
    ),
)


def _build_registry() -> MappingProxyType[str, Preset]:
    """Construct the immutable PRESETS registry."""
    all_presets = _EVERGREEN_KEYWORDS + _KEYWORD_ABILITIES + _FUNCTIONAL_PRESETS
    names_seen: dict[str, Preset] = {}
    for p in all_presets:
        if p.name in names_seen:
            msg = f"duplicate preset name: {p.name!r}"
            raise ValueError(msg)
        names_seen[p.name] = p
    return MappingProxyType(names_seen)


PRESETS: MappingProxyType[str, Preset] = _build_registry()


def get_preset(name: str) -> Preset:
    """Look up a preset by name. Raises KeyError if unknown."""
    try:
        return PRESETS[name]
    except KeyError as exc:
        msg = f"unknown preset {name!r}. Known: {', '.join(sorted(PRESETS.keys()))}"
        raise KeyError(msg) from exc


def matches(name: str, card: dict) -> bool:
    """Convenience wrapper: ``get_preset(name).matches(card)``."""
    return get_preset(name).matches(card)


def list_presets() -> dict[str, str]:
    """Return ``name -> description`` for every preset, sorted by name."""
    return {name: PRESETS[name].description for name in sorted(PRESETS)}
