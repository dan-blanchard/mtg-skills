"""Signal specs: how each scoped signal maps to cards that FEED it.

For every signal the engine recognizes, a ``SignalSpec`` carries:
  - a human ``label`` + an ``avenue`` blurb (the exploration-avenue text),
  - a ``search`` fragment (``card_search`` kwargs that FIND enablers in-identity),
  - a ``serve`` regex (does a given card oracle feed this signal?).

Scope drives the discriminator that matters most: an *opponents'-graveyard* signal
is fed by milling opponents, not yourself — so self-mill does not register as
serving it. This is the deterministic encoding of the Tinybones guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS, SWEEP_LABELS
from mtg_utils.card_classify import get_oracle_text

_IC = re.IGNORECASE


@dataclass(frozen=True)
class SubAvenue:
    """An additional, separately-searchable angle on the same signal. A theme like
    land-creatures has genuinely distinct buckets — be the land-creatures (manlands),
    reward them (payoffs), turn lands into creatures (animators) — each needing its
    own precise search, so one signal fans out into several explorable avenues."""

    label: str
    avenue: str
    search: dict


@dataclass(frozen=True)
class SignalSpec:
    label: str
    avenue: str
    search: dict  # card_search kwargs fragment (oracle / preset_names / card_type)
    serve: re.Pattern[str]  # matcher on a candidate card's oracle text
    extras: tuple[SubAvenue, ...] = ()  # additional precise sub-avenues (optional)


def _spec(label, avenue, search, serve, extras=()):
    return SignalSpec(
        label=label,
        avenue=avenue,
        search=search,
        serve=re.compile(serve, _IC),
        extras=tuple(extras),
    )


SPECS: dict[tuple[str, str], SignalSpec] = {
    ("creature_etb", "you"): _spec(
        "Creatures entering — yours",
        "cheap ways to flood your board with creatures",
        {
            "oracle": (
                r"create .*creature token"
                r"|put .*creature card.*onto the battlefield"
            )
        },
        (r"create .*creature token|put .*creature.*onto the battlefield"),
    ),
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        {"oracle": r"whenever a creature an opponent controls enters"},
        r"opponent.*creature.*enters",
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
        {"oracle": r"create .*creature token"},
        r"create .*creature token|creatures you control get",
    ),
    # Land-creatures theme (e.g. Jyoti, Moag Ancient). Three precise, disjoint
    # angles — proven clean against bulk so a Plant-token maker (Avenger) or a
    # clone (Silent Hallcreeper) is never surfaced:
    #   main   — creature-lands: a Land that "becomes a … creature" (manlands)
    #   extra  — payoffs: cards that reference "land creature(s)" (anthems)
    #   extra  — animators: effects that turn YOUR lands into creatures
    ("land_creatures_matter", "you"): _spec(
        "Creature-lands",
        "lands that are or become creatures — the backbone of a land-creatures deck",
        {"card_type": "Land", "oracle": r"becomes a [^.]*creature"},
        r"\bland creatures?\b",
        extras=(
            SubAvenue(
                "Land-creature payoffs",
                "anthems and abilities that specifically pump land creatures",
                {"oracle": r"\bland creatures?\b"},
            ),
            SubAvenue(
                "Animate your lands",
                "effects that turn lands you control into creatures",
                {"oracle": r"lands? you control[^.]*become[^.]*creature"},
            ),
        ),
    ),
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"opponent[^.]*\bmill|mill[^.]*opponent|each opponent[^.]*graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard",
        {"oracle": r"into your graveyard|surveil"},
        r"into your graveyard|from your graveyard|surveil\b|self-mill",
    ),
    ("lifegain_matters", "you"): _spec(
        "Lifegain",
        "incidental and repeatable lifegain",
        {"oracle": r"gain .* life"},
        r"gain \d+ life|gain x life|gains? [^.]*life|lifelink",
    ),
    ("counters_matter", "any"): _spec(
        "+1/+1 counters",
        "counter generators and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        r"\+1/\+1 counter|proliferate",
    ),
    ("draw_matters", "you"): _spec(
        "Draw triggers / wheels",
        "draw-trigger payoffs and extra-draw engines (Nekusar / Chasm Skulker space)",
        {"oracle": r"whenever you draw|draw an additional card"},
        r"whenever you draw|draws? (?:your )?(?:second|an additional) card",
    ),
    ("spellcast_matters", "you"): _spec(
        "Spellslinger",
        "cheap instants/sorceries and cantrips to chain casts",
        {"oracle": r"draw a card"},
        r"draw a card|prowess|magecraft",
    ),
    ("sacrifice_matters", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create .*token|sacrifice"},
        r"create .*token|sacrifice (?:a|an|another)",
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create .*token|whenever .* dies"},
        r"create .*token|sacrifice (?:a|an|another)|whenever .* dies",
    ),
    ("attack_matters", "you"): _spec(
        "Combat",
        "haste enablers and evasive/aggressive bodies",
        {"oracle": r"haste|create .*creature token"},
        r"haste|create .*creature token",
    ),
    ("landfall", "you"): _spec(
        "Landfall",
        "extra land drops and land fetch",
        {
            "oracle": (
                r"search your library for .*land"
                r"|play an additional land|onto the battlefield"
            )
        },
        (
            r"search your library for .*land"
            r"|play an additional land|onto the battlefield"
        ),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        r"create [^.]*creature token",
    ),
    ("treasure_matters", "you"): _spec(
        "Treasure",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        r"\btreasure\b",
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        {"card_type": "Artifact"},
        r"artifacts? you control|for each artifact|\bmetalcraft\b|\baffinity\b",
    ),
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b",
    ),
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b|whenever .*token.*enters|\bpopulate\b",
    ),
    ("stax_taxes", "opponents"): _spec(
        "Stax & taxes",
        "tax and restriction effects aimed at your opponents",
        {
            "oracle": (
                r"opponents? can't"
                r"|spells your opponents cast cost"
                r"|creatures your opponents control"
            )
        },
        r"opponents? can't|spells your opponents cast cost|your opponents",
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects to re-use enter-the-battlefield abilities",
        {"preset_names": ("blink",)},
        r"exile[^.]*?return[^.]*?battlefield",
    ),
    ("mill_matters", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        {"preset_names": ("mill",)},
        r"\bmills?\b",
    ),
    ("goad_matters", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        {"preset_names": ("goad",)},
        r"\bgoad",
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate and counter generators",
        {"preset_names": ("proliferate",)},
        r"\bproliferate\b|\+1/\+1 counter",
    ),
    ("magecraft_matters", "you"): _spec(
        "Magecraft / spellslinger",
        "cheap instants and sorceries and cantrips to trigger magecraft",
        {"oracle": r"draw a card"},
        r"\bmagecraft\b|\bprowess\b|instant or sorcery",
    ),
    ("extra_combats", "you"): _spec(
        "Extra combats",
        "additional combat phases and the attackers to exploit them",
        {"oracle": r"additional combat phase|extra combat"},
        r"additional combat|extra combat",
    ),
    ("extra_turns", "you"): _spec(
        "Extra turns",
        "additional-turn effects",
        {"oracle": r"extra turn|additional turn|take an extra"},
        r"extra turn|additional turn",
    ),
    # ── Rules mined from the zero-signal commander tail ─────────────────────────
    ("combat_damage_matters", "opponents"): _spec(
        "Combat damage",
        "evasive attackers and extra-combat enablers to keep connecting",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals combat damage to (?:a player|an opponent|one of your opponents)"
        r"|can't be blocked|\bmenace\b",
    ),
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount",
        {"oracle": r"\{x\}|with mana value"},
        r"\{x\}|mana value \d|\bstorm\b",
    ),
    ("cast_from_exile", "you"): _spec(
        "Impulse / cast-from-exile",
        "impulse-draw enablers and cast-from-exile payoffs",
        {"oracle": r"from the top of your library|from exile"},
        r"from the top of your library|from exile|\bplot\b",
        extras=(
            SubAvenue(
                "Top-of-library engines",
                "cards that let you play off the top of your library",
                {"oracle": r"from the top of your library"},
            ),
        ),
    ),
    ("discard_matters", "you"): _spec(
        "Discard",
        "loot/connive discard outlets and discard payoffs",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard",
    ),
    ("lifeloss_matters", "opponents"): _spec(
        "Drain",
        "repeatable life-drain and aristocrats payoffs",
        {"oracle": r"each opponent loses|target opponent loses|whenever .* dies"},
        r"opponent[^.]*loses [^.]*life|whenever an opponent loses life|\bextort\b",
    ),
    ("lifeloss_matters", "you"): _spec(
        "Self life-loss",
        "ways to pay or lose life on demand to fuel your payoffs",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you lose life|you lose \d+ life|pay \d+ life",
    ),
    ("lands_matter", "you"): _spec(
        "Lands matter",
        "ramp, extra land drops, and recursion to maximize your land count",
        {
            "oracle": (
                r"search your library for .*land"
                r"|play an additional land"
                r"|put .*land card.*onto the battlefield"
            )
        },
        r"the number of lands you control|for each land you control"
        r"|play an additional land",
    ),
    ("card_draw_engine", "you"): _spec(
        "Card-advantage engine",
        "protection, recursion, and payoffs for a repeatable draw engine",
        {"preset_names": ("card-draw",)},
        r"draw \w+ cards?|draw cards equal to|draws? an additional card",
    ),
    ("card_draw_engine", "each"): _spec(
        "Group draw / wheel",
        "symmetric draw with punisher payoffs (Nekusar-style)",
        {"oracle": r"each player draws|whenever .* draws a card"},
        r"each player draws|draws? an additional card",
    ),
    ("direct_damage", "you"): _spec(
        "Burn / pingers",
        "repeatable direct damage — pingers, burn, and damage doublers",
        {"preset_names": ("burn",)},
        r"deals \d+ damage to any target|\{t\}[^.]*deals .*damage|double the damage",
    ),
    ("mana_amplifier", "you"): _spec(
        "Big mana",
        "mana doublers plus the X-spells and expensive bombs to spend it on",
        {"oracle": r"\{x\}|add .* mana|search your library for .*land"},
        r"tap.*for mana.*add|add .* mana of any|\{x\}",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    ("voltron_matters", "you"): _spec(
        "Voltron / equipment & auras",
        "equipment, auras, equip-cost reducers, and tutors to suit up one creature",
        {"preset_names": ("equip",)},
        r"equipped creature|enchanted creature gets|equip \{"
        r"|attach [^.]*(?:equipment|aura)"
        r"|equipment you control|for each (?:equipment|aura)",
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, and cheap creatures to crew them",
        {"preset_names": ("crew",)},
        r"\bvehicles? you control\b|\bcrew\b|create [^.]*vehicle artifact",
    ),
    ("scry_surveil_matters", "you"): _spec(
        "Scry / surveil matters",
        "cheap repeatable scry and surveil to fire your topdeck-selection payoffs",
        {"oracle": r"\b(?:scry|surveil)\b"},
        r"\b(?:scry|surveil)\b",
    ),
    # ── Named-mechanic long tail ────────────────────────────────────────────────
    ("monarch_matters", "you"): _spec(
        "Monarch",
        "become and defend the monarch — evasion and combat-damage triggers",
        {"oracle": r"\bthe monarch\b|becomes? the monarch"},
        r"\bthe monarch\b",
    ),
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "take and hold the initiative; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("ring_matters", "you"): _spec(
        "The Ring",
        "Ring-bearer payoffs and ways to tempt you with the Ring",
        {"oracle": r"ring tempts you|ring-bearer"},
        r"ring tempts you|ring-bearer",
    ),
    ("venture_matters", "you"): _spec(
        "Venture / dungeons",
        "venture enablers and dungeon-completion payoffs",
        {"oracle": r"venture into the dungeon|\bdungeon\b"},
        r"venture into the dungeon|\bdungeon\b",
    ),
    ("energy_matters", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        {"oracle": r"\{e\}|energy counter"},
        r"\{e\}|energy counter",
    ),
    ("devotion_matters", "you"): _spec(
        "Devotion",
        "heavy colored pips to grow devotion and devotion payoffs",
        {"oracle": r"devotion to"},
        r"devotion to",
    ),
    ("superfriends_matters", "you"): _spec(
        "Superfriends",
        "planeswalkers plus proliferate and loyalty payoffs to protect them",
        {"oracle": r"planeswalker|loyalty"},
        r"planeswalkers? you control|loyalty counters?",
    ),
    ("historic_matters", "you"): _spec(
        "Historic",
        "artifacts, legendaries, and Sagas — the historic permanents that trigger it",
        {"oracle": r"\bhistoric\b|\blegendary\b|\bsaga\b"},
        r"\bhistoric\b",
    ),
    ("legends_matter", "you"): _spec(
        "Legends matter",
        "legendary creatures and the payoffs that reward a board of legends",
        {"oracle": r"\blegendary\b"},
        r"legendary creatures? you control|another legendary|for each legendary",
    ),
    ("big_hand_matters", "you"): _spec(
        "Big hand / no max hand size",
        "card draw and no-max-hand-size payoffs that reward a full grip",
        {"oracle": r"cards in your hand|no maximum hand size"},
        r"maximum hand size|cards in your hand",
    ),
    ("party_matters", "you"): _spec(
        "Party",
        "Clerics, Rogues, Warriors, and Wizards to assemble a full party",
        {"oracle": r"your party|assemble.*party|\bcleric|\brogue|\bwarrior|\bwizard"},
        r"\bparty\b",
    ),
    ("exile_matters", "you"): _spec(
        "Exile pile matters",
        "impulse/foretell exile enablers and payoffs for cards in exile",
        {"oracle": r"exile the top|in exile|from exile"},
        r"cards? (?:you own )?in exile|for each card[^.]*exile",
    ),
    ("experience_matters", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters and scale with them",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    ("poison_matters", "opponents"): _spec(
        "Poison / infect",
        "infect and toxic threats plus proliferate to finish with poison",
        {"oracle": r"\binfect\b|\btoxic\b|poison counter|proliferate"},
        r"poison counter|\binfect\b|\btoxic\b",
    ),
    ("modified_matters", "you"): _spec(
        "Modified",
        "counters, Auras, and Equipment to keep creatures modified",
        {"oracle": r"\bmodified\b|\+1/\+1 counter|aura or equipment"},
        r"\bmodified\b",
    ),
    ("mutate_matters", "you"): _spec(
        "Mutate",
        "mutate creatures and mutate-trigger payoffs",
        {"oracle": r"\bmutate\b"},
        r"\bmutate\b",
    ),
    ("food_matters", "you"): _spec(
        "Food",
        "Food makers plus sacrifice outlets and lifegain payoffs",
        {"oracle": r"\bfood\b"},
        r"\bfood\b",
    ),
    ("clue_matters", "you"): _spec(
        "Clues / investigate",
        "investigate enablers and artifact/draw payoffs for Clues",
        {"oracle": r"\bclue\b|investigate"},
        r"\bclue\b|investigate",
    ),
    ("blood_matters", "you"): _spec(
        "Blood tokens",
        "Blood makers plus rummage and sacrifice payoffs",
        {"oracle": r"blood token"},
        r"blood token",
    ),
    ("daynight_matters", "you"): _spec(
        "Day / Night",
        "daybound/nightbound creatures and day-night transition payoffs",
        {"oracle": r"\bdaybound\b|\bnightbound\b|\bday\b|\bnight\b"},
        r"daybound|nightbound|becomes night|becomes day",
    ),
    ("voting_matters", "each"): _spec(
        "Voting / council",
        "will-of-the-council and vote effects — multiplayer politics",
        {"oracle": r"\bvote\b|will of the council|council's dilemma"},
        r"\bvote\b|will of the council",
    ),
    ("coven_matters", "you"): _spec(
        "Coven",
        "creatures with different powers to turn on coven",
        {"oracle": r"\bcoven\b|different powers"},
        r"\bcoven\b",
    ),
    ("doubling_matters", "you"): _spec(
        "Doubling",
        "token/counter doublers and the payoffs that exploit doubled output",
        {"oracle": r"twice that many|double the (?:number|amount)"},
        r"twice that many|double the (?:number|amount)",
    ),
    ("second_spell_matters", "you"): _spec(
        "Second-spell / storm-lite",
        "cheap spells and cantrips to reliably cast a second spell each turn",
        {"oracle": r"instant or sorcery|draw a card|\bstorm\b"},
        r"second spell you cast|cast your second spell",
    ),
    # ── Mechanics recovered from the "rejected" families ────────────────────────
    ("token_copy_matters", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        {"oracle": r"token that's a copy|tokens? that are copies|\bpopulate\b"},
        r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|\bpopulate\b",
    ),
    ("specialize_matters", "you"): _spec(
        "Specialize",
        "Backgrounds and specialize payoffs to swap a creature's mode",
        {"oracle": r"\bspecialize\b|\bbackground\b"},
        r"\bspecialize\b",
    ),
    ("dice_matters", "you"): _spec(
        "Dice rolling",
        "dice-rolling enablers and roll-result payoffs",
        {"oracle": r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|\bd20\b"},
        r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|whenever you roll",
    ),
    ("crimes_matter", "you"): _spec(
        "Crimes",
        "targeted removal and abilities that count as committing a crime",
        {"oracle": r"commit a crime|target (?:opponent|player)|target.*spell"},
        r"commit(?:s|ted)? a crime|whenever you commit",
    ),
    ("connive_matters", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        {"oracle": r"\bconnives?\b|draw a card, then discard"},
        r"\bconnives?\b",
    ),
    ("spell_copy_matters", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        {"oracle": r"copy (?:target|that)|instant or sorcery|\bstorm\b"},
        r"copy target (?:instant|sorcery|spell)|\bcopy that spell\b|\bstorm\b",
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp_matters", "you"): _spec(
        "Ramp / big mana",
        "mana rocks, dorks, and land ramp to accelerate into your payoffs",
        {"oracle": r"add \{|search your library for .*\bland\b"},
        r"\{t\}[^.]*:\s*add|add .* mana|search your library for .*\bland\b",
    ),
    ("removal_matters", "you"): _spec(
        "Removal / interaction",
        "spot removal and burn to clear blockers and threats",
        {"oracle": r"destroy target|exile target|deals .* damage to target"},
        r"destroy target|exile target (?:creature|permanent)"
        r"|deals .* damage to target creature",
    ),
    ("counter_control", "you"): _spec(
        "Counterspells / control",
        "counterspells and stack interaction",
        {"oracle": r"counter target"},
        r"counter target",
    ),
    ("team_buff", "you"): _spec(
        "Team keyword grants",
        "keyword grants and anthems for your board",
        {"oracle": r"creatures you control (?:gain|have)"},
        r"creatures? you control (?:gain|gains|have|has)",
    ),
    ("tutor_matters", "you"): _spec(
        "Tutors",
        "tutors to assemble your key pieces and combos",
        {"oracle": r"search your library for"},
        r"search your library for",
    ),
    ("untap_engine", "you"): _spec(
        "Untap engine",
        "untap effects to reuse tap abilities and generate value",
        {"oracle": r"untap (?:target|all|another|each)"},
        r"untap (?:target|all|another|each)",
    ),
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        {"oracle": r"gain control of"},
        r"gain control of",
    ),
    ("opponent_discard", "opponents"): _spec(
        "Hand attack",
        "forced discard and hand disruption aimed at opponents",
        {"oracle": r"opponent discards|each player discards|target player discards"},
        r"opponent[^.]*discards|each player discards|target player discards",
    ),
    ("evasion_self", "you"): _spec(
        "Evasion / unblockable",
        "unblockable and evasion to keep connecting — strong for voltron",
        {"oracle": r"can't be blocked|\bunblockable\b"},
        r"can't be blocked",
    ),
    ("clone_matters", "you"): _spec(
        "Clones / copies",
        "clone effects plus strong creatures worth copying",
        {"oracle": r"becomes a copy|copy of (?:target|another)"},
        r"becomes a copy|copy of (?:target|another)",
    ),
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put big creatures onto the battlefield from hand or library",
        {"oracle": r"onto the battlefield"},
        r"onto the battlefield from your (?:hand|library)"
        r"|put .*creature card.*onto the battlefield",
    ),
    ("bounce_tempo", "you"): _spec(
        "Bounce / tempo",
        "bounce effects for tempo and ETB re-use",
        {"oracle": r"return target .*to (?:its|their) owner's hand"},
        r"return target .*owner's hand",
    ),
    ("cascade_matters", "you"): _spec(
        "Cascade",
        "high-value spells to hit off cascade plus more cascade enablers",
        {"oracle": r"\bcascade\b"},
        r"\bcascade\b",
    ),
    ("regenerate_matters", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        {"oracle": r"\bregenerate\b"},
        r"\bregenerate\b",
    ),
    ("opponent_cast_matters", "opponents"): _spec(
        "Punish opponents' spells",
        "taxes and punishers that trigger when opponents cast",
        {"oracle": r"whenever an opponent casts|spells? your opponents cast"},
        r"whenever an opponent casts|opponents? cast",
    ),
    ("opponent_draw_matters", "opponents"): _spec(
        "Punish opponents' draw",
        "wheels and draw-denial punishers that trigger on opponents drawing",
        {"oracle": r"whenever an opponent draws|each opponent draws"},
        r"whenever an opponent draws|opponents? draws?",
    ),
    ("opponent_search_matters", "opponents"): _spec(
        "Punish opponents' tutors / selection",
        "stax and punishers for opponents who search, scry, or surveil",
        {"oracle": r"opponent[^.]*(?:search|scry|surveil)|search(?:es)? their library"},
        r"opponent[^.]*(?:scries|surveils|searches)|search their library",
    ),
}

# Subject-bearing signal keys: their spec is built dynamically from the captured
# subtype (a Goblin lord and a Sliver lord must not share one static spec).
_SUBJECT_KEYS = frozenset({"type_matters", "token_maker", "typed_spellcast"})
_SUBJECT_TEMPLATES = {
    "type_matters": ("{s} tribal", "{s}s and the anthems/lords that reward them"),
    "token_maker": ("{s} tokens", "more {s} token makers and {s} payoffs"),
    "typed_spellcast": ("{s} spells", "{s}s and {s}-spell payoffs"),
}


def _subject_spec(signal) -> SignalSpec:
    """Build a spec for a subject-bearing signal by interpolating the subtype."""
    subj = signal.subject
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        # card_type matches the type-line substring → finds the tribe itself.
        search={"card_type": subj},
        serve=re.compile(rf"\b{re.escape(subj)}s?\b", _IC),
        extras=(
            SubAvenue(
                f"{subj} payoffs",
                f"anthems and abilities that reward your {subj}s",
                {"oracle": rf"{re.escape(subj)}s? you control"},
            ),
        ),
    )


# Auto-register an avenue for every exhaustively-mined sweep key that doesn't
# already have a hand-written spec (the same-key widens reuse their existing spec).
def _humanize(key: str) -> str:
    base = key.replace("_matters", "").replace("_", " ").strip()
    return (base[:1].upper() + base[1:]) if base else key


_SPECCED_KEYS = {k for (k, _scope) in SPECS}
for _d in SWEEP_DETECTORS:
    if _d["key"] in _SPECCED_KEYS:
        continue  # hand-written spec already covers this axis
    _ident = (_d["key"], _d["scope"])
    if _ident in SPECS:
        continue
    _polished = SWEEP_LABELS.get(_d["key"])
    if _polished:
        _label, _avenue = _polished
    else:
        _label = _humanize(_d["key"])
        _avenue = f"support and payoffs for the {_label.lower()} axis"
    SPECS[_ident] = _spec(_label, _avenue, {"oracle": _d["regex"]}, _d["regex"])


def spec_for(signal) -> SignalSpec | None:
    """Resolve a spec. Subject-bearing signals build a per-subject spec; otherwise
    exact (key, scope) → (key, any) → first entry by key."""
    if signal.key in _SUBJECT_KEYS and signal.subject:
        return _subject_spec(signal)
    exact = SPECS.get((signal.key, signal.scope))
    if exact is not None:
        return exact
    any_scope = SPECS.get((signal.key, "any"))
    if any_scope is not None:
        return any_scope
    return next((spec for (key, _), spec in SPECS.items() if key == signal.key), None)


def serves(card: dict, signal) -> bool:
    """True if ``card``'s oracle text feeds ``signal`` (scope-aware)."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.search(get_oracle_text(card) or "") is not None


def search_filters(signal, *, color_identity: str, fmt: str) -> dict:
    """Build ``card_search`` kwargs to find cards that feed ``signal`` in-identity."""
    spec = spec_for(signal)
    base = dict(spec.search) if spec else {}
    base["color_identity"] = color_identity
    base["format"] = fmt
    return base
