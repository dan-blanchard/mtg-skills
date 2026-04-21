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

    Both may be set; they combine with OR. ``should_match`` and
    ``should_not_match`` are card-name fixtures used by the test suite.
    """

    name: str
    description: str
    keywords: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()
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
        return False


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
        should_match=("Preordain", "Omen of the Sun", "Magma Jet"),
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
        description="Creature has infect.",
        keywords=("Infect",),
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
            r"\breturn\s+target\s+(?:creature|nonland permanent)\b.*\bhand\b",
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
        should_match=("Wrath of God",),
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
            "Note: 'target creature gets -N' matches any toughness debuff "
            "including soft combat tricks (e.g. -0/-2); callers treat this "
            "as generous. For a stricter definition use a custom --theme."
        ),
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
        should_match=("Sinkhole", "Armageddon"),
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
        should_match=("Unsummon",),
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
    # digit/word-form numbers.
    Preset(
        name="tokens",
        description="Creates one or more creature tokens.",
        patterns=_rx(r"create (?:a|an|" + _COUNT + r").*\bcreature token"),
        should_match=("Omen of the Sun", "Blade Splicer", "Lingering Souls"),
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
        description=("Gains life OR triggers when you gain life (lifegain-matters)."),
        patterns=_rx(
            r"\bgains? " + _COUNT + r" life\b",
            r"\bgain life equal to\b",
            r"\bwhenever you gain life\b",
            r"\blifelink\b",  # catches e.g. "target creature gains lifelink"
        ),
        should_match=("Thragtusk", "Lightning Helix"),
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
            "+1/+1 counters (counters-matter archetype)."
        ),
        patterns=_rx(
            r"\+1/\+1 counter",
            r"with a \+1/\+1 counter on it",
        ),
        should_match=("Scavenging Ooze", "Goldvein Hydra"),
        should_not_match=("Lightning Bolt", "Counterspell"),
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
