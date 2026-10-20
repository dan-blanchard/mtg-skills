"""Signal specs data slice 1/4: SPECS dict entries (lines 1749-3416 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

import re

from mtg_utils._analysis._sweep_detectors import (
    ABILITY_COPY_REGEX,
    BASE_PT_SET_REGEX,
    BLOCKED_MATTERS_REGEX,
    COMBAT_BUFF_ENGINE_SWEEP_REGEX,
    COPY_LIMIT_REGEX,
    COUNTER_DISTRIBUTE_SERVE_REGEX,
    CREATURE_PING_REGEX,
    DAMAGE_EQUAL_POWER_REGEX,
    DAMAGE_PREVENTION_REGEX,
    DEBUFF_SWEEP_REGEX,
    DIES_RECURSION_REGEX,
    FLASH_GRANT_REGEX,
    FORCED_ATTACK_SWEEP_REGEX,
    FREE_CAST_REGEX,
    GLOBAL_ABILITY_GRANT_REGEX,
    GROUP_HUG_DRAW_REGEX,
    KEYWORD_COUNTER_REGEX,
    KEYWORD_GRANT_TARGET_REGEX,
    NAMED_PERMANENT_REGEX,
    NONCOMBAT_DAMAGE_PAYOFF_REGEX,
    NONCREATURE_CAST_PUNISH_REGEX,
    OPPONENT_COUNTER_GRANT_REGEX,
    PROTECTION_GRANT_REGEX,
    PUMP_MATTERS_REGEX,
    SCALING_PUMP_SWEEP_REGEX,
    SELF_COUNTER_GROW_SWEEP_REGEX,
    SPELL_KEYWORD_GRANT_REGEX,
    SWEEP_LABELS,
    TARGET_PLAYER_DRAWS_REGEX,
    TOPDECK_STACK_SWEEP_REGEX,
    TOUGHNESS_COMBAT_REGEX,
    TRIBE_DAMAGE_TRIGGER_REGEX,
    VARIABLE_PT_SWEEP_REGEX,
)
from mtg_utils._analysis.lanes.card_advantage import REANIMATED_SELF_RETURNS

from ._shared import (
    _ART_SUBTYPES,
    _BOARD_PROTECTION_EXTRA,
    _BOARD_WIPE_EXTRA,
    _CAST_FROM_GY_EXTRA,
    _CHOSEN_TYPE_IDENTS,
    _COMBAT_SUPPORT_EXTRA,
    _COPY_EXTRA,
    _COUNT_ANTHEM_SWEEP_REGEX,
    _COUNTER_DOUBLER_EXTRA,
    _COUNTER_KEYWORD_EXTRA,
    _COUNTER_RESILIENCE_EXTRA,
    _COUNTERS_PACKAGE,
    _CREATURE_COST_EXTRA,
    _DAMAGE_SOAK_EXTRA,
    _DEATH_DRAIN_EXTRA,
    _DEATHTOUCH_GEAR_EXTRA,
    _DEATHTOUCH_GEAR_ORACLE,
    _DIES_RECURSION_EXTRA,
    _DIES_RECURSION_ORACLE,
    _DRAWBACK_EXTRA,
    _EDICT_SWEEP_REGEX,
    _ENCH_SUBTYPES,
    _ETB_DOUBLER_EXTRA,
    _ETB_PAYOFF_EXTRA,
    _ETB_VALUE_EXTRA,
    _EXTRA_COMBAT_EXTRA,
    _FLICKER_EXTRA,
    _FORCE_ATTACK_EXTRA,
    _FORCE_FEED_EXTRA,
    _GOWIDE_ANTHEM_EXTRA,
    _GOWIDE_MAKER_EXTRA,
    _IC,
    _KEYWORD_COUNTER_EXTRA,
    _LANDFALL_ORACLE,
    _LANDS_FROM_GRAVE_EXTRA,
    _LURE_EXTRA,
    _NONCOMBAT_BURN_EXTRA,
    _PILLOWFORT_EXTRA,
    _PLUS_ONE_SERVE_IDENTS,
    _POWER_FLING_EXTRA,
    _PROLIFERATE_EXTRA,
    _REANIMATE_ORACLE,
    _REANIMATION_EXTRA,
    _REANIMATOR_SERVE_ORACLE,
    _SAC_OUTLET_EXTRA,
    _SELF_BOUNCE_EXTRA,
    _SELF_PUMP_SWEEP_REGEX,
    _SELF_RECUR_EXTRA,
    _SELF_SAC_CREATURE_EXTRA,
    _SELF_SAC_CREATURE_ORACLE,
    _SPELLSLINGER_SPEC,
    _STAX_SERVE_ORACLE,
    _TAPPER_ENGINE_SWEEP_REGEX,
    _TARGETED_BUFF_EXTRA,
    _TARGETING_SWEEP_REGEX,
    _TEAM_PROTECT_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_IDENTS,
    _TRIBAL_ETB_MULTI_SWEEP_REGEX,
    _TRIGGER_COPY_EXTRA,
    _TYPED_ENTERS_PUNISH_SWEEP_REGEX,
    _VOLTRON_PROTECT_EXTRA,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
    _sweep_spec_with_extras,
)


def _lifegain_spec(label: str, avenue: str) -> SignalSpec:
    """The Lifegain avenue's spec, one per key: the payoffs (lifegain_matters), the
    sources (lifegain_makers) and the self-bleed engines that want lifegain beside
    them (wants_lifegain). All three serve the whole package, sources and payoffs
    together; lifelink is a keyword, so it serves off keywords[]."""
    return _spec(
        label,
        avenue,
        {"oracle": r"gain .* life"},
        # Serve rides the lane (2026-10-18): over the commander pool regex 2205,
        # idents 2412, both 2054. Regex-only 151: 96 Food makers (the gain sits in
        # the Food token, which the lane doesn't read as lifegain_makers — backlog),
        # 20 lifegain hosers (Sulfuric Vortex, Tainted Remedy), gifts to an
        # opponent (Path of Peace, Fiery Justice) and 5 lifelink grants on a token,
        # counter or Aura (Charismatic Conqueror, Duskfang Mentor). Ident-only 358:
        # 291 lifelink bearers the keyword arm already served, and 67 payoffs the
        # regex missed (Angelic Accord, Voracious Wurm, the Infusion cards, Test of
        # Endurance). The 134 self-bleed engines (Dark Confidant, Phyrexian Arena)
        # emit wants_lifegain, not a served ident: they want lifegain, they don't
        # supply it.
        None,
        serve_idents=frozenset({"lifegain_makers|you|*", "lifegain_matters|you|*"}),
        serve_keywords=("lifelink",),
    )


# The "your graveyard" serve (graveyard_makers / graveyard_matters, you): both lanes.
_OWN_GRAVEYARD_IDENTS = frozenset({"graveyard_makers|you|", "graveyard_matters|you|"})

# The Treasure serve (treasure_makers / treasure_matters, you): both lanes.
_TREASURE_IDENTS = frozenset({"treasure_makers|you|", "treasure_matters|you|"})

# Creatures entering your battlefield, as the lanes read them: the creature-token
# makers, a creature cheat, a creature that reanimates (damage_for_each,
# creature_etb).
_CREATURES_ENTERING_IDENTS = _TOKEN_MAKER_IDENTS | {
    "cheat_into_play|you|Creature",
    "reanimator|you|",
}

# The aristocrats serve (sacrifice_outlets you, death_matters any): the creature-
# token fodder, the outlets, the death payoffs on every side, the edicts, and the
# death-value fodder (a permanent whose own death trigger replaces it).
_ARISTOCRATS_IDENTS = _TOKEN_MAKER_IDENTS | {
    "sacrifice_outlets|you|",
    "death_matters|any|",
    "death_matters|you|",
    "death_matters|opponents|",
    "edict_makers|opponents|",
    "edict_makers|each|",
    "self_death_payoff|you|",
}

# The kind-agnostic counter serve (any_counter_matters / any_counter_makers, you).
_ANY_COUNTER_IDENTS = frozenset(
    {
        "any_counter_matters|you|",
        "any_counter_makers|you|",
        "proliferate_makers|you|",
        "counter_doubling|you|",
    }
)

# The proliferate serve (proliferate_matters / proliferate_makers, you): proliferate
# itself, the counter sources it multiplies (+1/+1, poison, oil, any kind), the
# counter payoffs and the doublers.
_PROLIFERATE_IDENTS = _ANY_COUNTER_IDENTS | frozenset(
    {
        "proliferate_matters|you|",
        "plus_one_makers|you|",
        "plus_one_matters|you|",
        "poison_makers|opponents|",
        "poison_matters|opponents|",
        "oil_counter_makers|you|",
        "oil_counter_matters|you|",
    }
)


# Each-opponent group burn: the symmetric-damage serve's adjacency (a Pestilence
# deck also wants Sizzle). The branch of the old serve regex.
_GROUP_BURN_ORACLE = r"deals \d+ damage to each opponent"
_GROUP_BURN_EXTRA = SubAvenue(
    "Group burn",
    "burn that hits each opponent, beside the sweepers and pingers that hit everyone",
    {"oracle": _GROUP_BURN_ORACLE},
    serve=Serve(oracle=re.compile(_GROUP_BURN_ORACLE, _IC)),
)

# The "is dealt damage" payoff search (card-search only; the serve is the lane).
_SOAK_PAYOFF_SEARCH = (
    r"whenever a creature you control is dealt damage"
    r"|whenever enchanted creature is dealt damage"
)

SPECS_1: dict[tuple[str, str], SignalSpec] = {
    # task B-1: chosen_type_matters — wildcard tribal payoffs (Door of
    # Destinies, Herald's Horn, Urza's Incubator): choose a creature type as
    # it enters (CR 614.12), pay off the chosen type. The deck-building move
    # when the deck ITSELF emits this (it runs Herald's Horn already): more
    # of the same open payoffs, plus the tribe's bodies to point them at.
    ("chosen_type_matters", "any"): _spec(
        "Chosen-type tribal payoffs",
        "open type-of-choice payoffs (Door of Destinies, Herald's Horn) that "
        "serve whatever tribe the deck fields",
        # Structural search AND serve (verified-review F5): a text arm
        # ("choose a creature type") re-admits every punisher chooser the
        # lane's emission gates exclude (Engineered Plague chooses too).
        # The preset's signal_keys arm and the serve's ident arm both ride
        # the punish-gated emission.
        {"preset_names": ("chosen-type-payoff",)},
        None,
        serve_idents=_CHOSEN_TYPE_IDENTS,
    ),
    # task B-2: damage_for_each — board-count damage, subject-less form (Mob
    # Justice, Massive Raid: "equal to the number of creatures you control").
    # The deck-building move when the deck emits this: raise the count — the
    # same go-wide fuel the creature-ETB lane serves. One "any"-scoped entry
    # resolves both emitted scopes via the (key, "any") fallback.
    ("damage_for_each", "any"): _spec(
        "Board-count damage",
        "go-wide fuel — token makers and cheap bodies that raise the count "
        "your board-scaled burn (Mob Justice, Massive Raid) reads",
        # Search finds cards that FEED the signal (verified-review F6): the
        # go-wide fuel the avenue text promises, never more board-count burn
        # emitters the serve below would then reject.
        {"oracle": r"create [^.]*creature tokens?"},
        # Serve rides the lanes: the token makers plus the creatures put onto the
        # battlefield (a creature cheat, a creature that reanimates). The regex's
        # reanimation spells (Reanimate, Ashen Powder) are the creature_etb
        # avenue's, not go-wide fuel.
        None,
        serve_idents=_CREATURES_ENTERING_IDENTS,
    ),
    ("creature_etb", "you"): _spec(
        "Creatures entering — yours",
        "cheap ways to flood your board with creatures",
        {
            "oracle": (
                r"create .*creature token"
                r"|put .*creature card.*onto the battlefield"
            )
        },
        # Serve rides the lanes (the token makers, creature cheats, creatures that
        # reanimate); reanimation spells, which no ident separates from a
        # return to hand, ride the Reanimation extra.
        None,
        serve_idents=_CREATURES_ENTERING_IDENTS,
        # An ETB commander wants the high-value ETB creatures and the doublers, not just
        # the punisher payoffs — same extras the blink lane uses (A3).
        extras=(
            _REANIMATION_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _TRIGGER_COPY_EXTRA,
            _FLICKER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
    ),
    # The search anchors on "a creature an opponent controls enters" (creature before
    # opponent, so Bloodthirst's "an opponent was dealt damage ... this creature enters"
    # stays out); the serve is the lane's ident.
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        {"oracle": r"whenever a creature an opponent controls enters"},
        # Serve rides the lane. "Creatures your opponents control enter tapped" statics
        # (Imposing Sovereign, Kinjalli's Sunwing) are stax_taxes', not an ETB trigger;
        # the lane gains Aboleth Spawn.
        None,
        serve_idents=frozenset({"creature_etb|opponents|"}),
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
        {"oracle": r"create .*creature token"},
        # Serve rides the lanes: the token makers, team buffs and anthems (token
        # anthems — Intangible Virtue — are tokens_matter), the go-wide payoffs
        # themselves, and the board-power payoffs (Ghalta's "costs {X} less, where
        # X is the total power of creatures you control" — power_matters). A
        # tribe's own grant ("Sliver creatures you control have …") is the tribal
        # avenue's.
        None,
        serve_idents=_TOKEN_MAKER_IDENTS
        | {
            "team_buff|you|",
            "anthem_static|you|*",
            "tokens_matter|you|",
            "creatures_matter|you|",
            "power_matters|you|",
        },
        # A go-wide board full of creature ETBs also wants the doubler (Panharmonicon);
        # creature-spell cost reducers (Goreclaw, Herald's Horn) deploy more bodies
        # (cost_reduction carries no spell type to serve them by ident).
        extras=(
            _ETB_PAYOFF_EXTRA,
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _CREATURE_COST_EXTRA,
        ),
    ),
    # Creature-recursion engine (Hua Tuo, Adun, Othelm): repeatably return/put a
    # creature card from your graveyard. Wants loop fuel — SELF-SACRIFICING creatures
    # (the sac is value AND refuels the graveyard, Spore Frog), ETB-value bodies, and
    # self-recur fodder. The full self-sac pool is on-theme (like a tribe), not
    # over-broad: the LANE is narrow (~21 recursion commanders).
    ("creature_recursion", "you"): _spec(
        "Creature recursion",
        "loop fuel for a graveyard creature-recursion engine — self-sacrificing "
        "creatures, ETB-value bodies, and self-recurring fodder",
        {"oracle": _SELF_SAC_CREATURE_ORACLE},
        _SELF_SAC_CREATURE_ORACLE,
        extras=(_SELF_SAC_CREATURE_EXTRA, _ETB_VALUE_EXTRA, _SELF_RECUR_EXTRA),
    ),
    # Power matters (CR 208): a commander whose engine keys on creature POWER — cost
    # reduction by total/greatest power (Ghalta) or a power-N-or-greater threshold
    # (Goreclaw, Gargos). The structured `power_min` serve credits genuine big bodies
    # regardless of oracle text; the search proxies them by high CMC (no `power` search
    # key exists). serve_power_min=4 = the canonical Goreclaw "power 4 or greater".
    ("power_matters", "you"): _spec(
        "Big creatures / power matters",
        "high-power bodies to exploit your power-based payoffs (cost reduction, "
        "power thresholds) — big beaters, not utility dorks",
        {"card_type": "Creature", "cmc_min": 5},
        # Credit the power-threshold PAYOFFS/enablers too (Garruk's Uprising, ferocious
        # dorks: "creature with power 4 or greater"), not just the big bodies.
        r"power \d+ or (?:greater|more)|with power \d+ or|\bferocious\b",
        serve_power_min=4,
        extras=(_POWER_FLING_EXTRA,),
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
        # The lane adds the land animators (Quirion Druid, earthbend, Nissa, Who Shakes
        # the World); exile / destroy a land creature (Consuming Sinkhole) is no longer
        # served.
        None,
        serve_idents=frozenset({"land_creatures_matter|you|"}),
        extras=(
            SubAvenue(
                "Land-creature payoffs",
                "anthems and abilities that specifically pump land creatures",
                {"oracle": r"\bland creatures?\b"},
            ),
            SubAvenue(
                "Animate your lands",
                "effects that turn lands you control into creatures",
                # second alt catches mass animators that name the land type
                # directly ("All Forests ... are 1/1 ... creatures" - Life and
                # Limb, Living Plane), the Yedora-Forest-lands payoff.
                {
                    "oracle": r"(?:lands?|forests?) you control[^.]*become[^.]*creature"
                    r"|all (?:lands?|forests?)[^.]*(?:are|become)[^.]*creature"
                },
            ),
            SubAvenue(
                "Forest-bounce untap engines",
                # Quirion/Scryb Ranger family: bounce a Forest/land you control
                # to untap a creature -- or, with Oboro Breezecaller, an animated
                # land, re-tapping it for mana. Narrow but real in forest-animation
                # decks; the bounce cost is the precision gate (a plain {T}: untap
                # is not this).
                "bounce a Forest/land you control to untap a creature or land",
                {
                    "oracle": r"return a (?:forest|land) you control to its "
                    r"owner's hand[^.]*untap"
                },
            ),
        ),
    ),
    # Widen to recover graveyard-HATE payoffs (exile an opponent's graveyard, count
    # cards in opponents' graveyards) the mill-only serve missed — still scoped to
    # OPPONENTS (self-mill never qualifies, the Tinybones guard).
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"(?:each opponent|target opponent|an opponent|that player|target player"
        # "each player mills" is SYMMETRIC mill — it fills opponents' graveyards too
        # (Breach the Multiverse, Dread Summons, Syr Konrad fuel).
        r"|each player) mills"
        r"|opponent[^.]*\bmill|mill[^.]*opponent"
        r"|exile (?:target player'?s?|each opponent'?s?|a) graveyard"
        r"|(?:cards?|creature cards?)[^.]*in [^.]*opponents'? graveyards?"
        r"|each opponent'?s graveyard"
        # Reanimation/cast that pulls from ANOTHER player's graveyard — "[creature card]
        # in/from a/each/target/that player's (or opponent's) graveyard" (Sepulchral /
        # Diluvian Primordial, Ink-Eyes, Breach the Multiverse). The opponent-graveyard
        # reanimator (Tariel, Valgavoth) wants these; anchored to a player/opponent
        # graveyard so a self-graveyard reanimator ("from your graveyard") stays out.
        r"|(?:creature|planeswalker|permanent|those|that)[^.]*"
        r"\b(?:in|from) (?:a|each|target|that) (?:player|opponent)(?:'?s)? graveyard"
        # Exile-mill artifacts (Pyxis, Mesmeric Orb-style): a player-subject exiling the
        # top of a LIBRARY is an exile-mill enabler (Circu).
        r"|(?:each player|target player|an opponent|each opponent|that player)"
        r"[^.]*exiles?[^.]*\blibrar"
        # Old reveal-mill (Mind Funeral, Mind Grind, Telemin Performance, Mirko's own
        # ability): "reveals cards from the top of THEIR library until … then puts them
        # into their graveyard" — pre-keyword mill that never says "mills". Anchored on
        # an opponent-owned library ("their/that player's/each opponent's") so a self-
        # mill ("from YOUR library", Avenging Druid) stays out of the opponents lane.
        r"|reveals? cards? from the top of "
        r"(?:their|that player'?s?|each opponent'?s?) library until"
        r"[\s\S]{0,140}?\bput[\s\S]{0,70}?graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard, plus the high-ETB and "
        "self-recurring creatures worth putting there and bringing back",
        {"oracle": r"into your graveyard|surveil"},
        # Serve rides the lanes, shared with graveyard_makers|you below.
        None,
        serve_idents=_OWN_GRAVEYARD_IDENTS,
        # A graveyard/reanimator deck recurs creatures with strong ETBs (Fleshbag
        # Marauder, Eternal Witness), self-recurring fodder (Gravecrawler), and
        # self-sacrificing creatures it loops for repeated value (Spore Frog).
        extras=(_ETB_VALUE_EXTRA, _SELF_RECUR_EXTRA, _SELF_SAC_CREATURE_EXTRA),
        # Cards whose graveyard mechanic is a KEYWORD (reminder text, stripped) — every
        # one uses your graveyard, so a graveyard deck wants them (CR 702.x).
        serve_keywords=(
            "dredge",
            "flashback",
            "jump-start",
            "retrace",
            "aftermath",
            "encore",
            "escape",
            "disturb",
            "unearth",
            "embalm",
            "eternalize",
            "scavenge",
            "recover",
            "soulshift",
            "delve",
            "gravestorm",
            "haunt",
        ),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the graveyard split. graveyard_makers
    # fires when the card PERFORMS a graveyard mechanic (reanimate / self-mill / GY
    # recursion / GY-cast grant / GY-hate exile / self-recast-from-GY keywords). The
    # avenue it OPENS is the rest of the graveyard engine — more self-mill / recursion /
    # cast-from-GY tools plus the high-ETB and self-recurring bodies worth binning. Same
    # serve pool as the graveyard_matters 'you' payoff (a graveyard deck wants makers
    # and payoffs together — ADR-0034 keeps the avenue composing both roles).
    ("graveyard_makers", "you"): _spec(
        "Graveyard engine",
        "self-mill, recursion, and cast-from-graveyard tools that fill and reuse your "
        "graveyard, plus the high-ETB and self-recurring creatures worth binning",
        {"oracle": r"into your graveyard|surveil"},
        # Serve rides the lanes, shared with graveyard_matters|you above.
        None,
        serve_idents=_OWN_GRAVEYARD_IDENTS,
        extras=(_ETB_VALUE_EXTRA, _SELF_RECUR_EXTRA, _SELF_SAC_CREATURE_EXTRA),
        serve_keywords=(
            "dredge",
            "flashback",
            "jump-start",
            "retrace",
            "aftermath",
            "encore",
            "escape",
            "disturb",
            "unearth",
            "embalm",
            "eternalize",
            "scavenge",
            "recover",
            "soulshift",
            "delve",
            "gravestorm",
            "haunt",
        ),
    ),
    # _matters sweep (ADR-0034): the opponent-facing MAKER — graveyard HATE (exile from
    # an opponent's graveyard) and opponent-mill performed by the card. Same serve pool
    # as the graveyard_matters 'opponents' avenue (GY-hate makers ride the makers lane
    # per the split; the payoff side keeps its own opponents serve).
    ("graveyard_makers", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"(?:each opponent|target opponent|an opponent|that player|target player"
        r"|each player) mills"
        r"|opponent[^.]*\bmill|mill[^.]*opponent"
        r"|exile (?:target player'?s?|each opponent'?s?|a) graveyard"
        r"|(?:cards?|creature cards?)[^.]*in [^.]*opponents'? graveyards?"
        r"|each opponent'?s graveyard"
        r"|(?:creature|planeswalker|permanent|those|that)[^.]*"
        r"\b(?:in|from) (?:a|each|target|that) (?:player|opponent)(?:'?s)? graveyard"
        r"|(?:each player|target player|an opponent|each opponent|that player)"
        r"[^.]*exiles?[^.]*\blibrar"
        r"|reveals? cards? from the top of "
        r"(?:their|that player'?s?|each opponent'?s?) library until"
        r"[\s\S]{0,140}?\bput[\s\S]{0,70}?graveyard",
    ),
    # The PAYOFF that pairs with the FUEL above: reanimation effects + cast-from-grave
    # creatures, because Celes-style commanders reward a creature re-entering play from
    # the graveyard, not merely a full graveyard. See _REANIMATE_ORACLE above.
    ("reanimator", "you"): _spec(
        "Reanimation",
        "reanimation effects that return a creature from your graveyard to the "
        "battlefield — each one fires your payoff and you choose the target",
        {"oracle": _REANIMATE_ORACLE},
        _REANIMATOR_SERVE_ORACLE,
        # persist/undying (CR 702.79/702.93) return the creature FROM THE GRAVEYARD on
        # death, so it re-enters from a graveyard and fires the reanimator payoff.
        # Disturb is read by its route instead: it casts the back face, a creature
        # or an Aura (Brine Comber's).
        serve_keywords=("escape", "persist", "undying"),
        # A creature that comes back by itself onto the battlefield or cast from
        # the graveyard; a token copy or a return to hand is sacrifice fodder
        # (_SELF_RECUR_EXTRA), not a reanimation.
        serve_self_recur=REANIMATED_SELF_RETURNS,
        # A reanimator deck wants the high-ETB creatures it reanimates (Mulldrifter,
        # Plaguecrafter), not just the reanimation spells.
        extras=(_CAST_FROM_GY_EXTRA, _ETB_VALUE_EXTRA),
    ),
    # Lifegain: the payoffs and the self-bleed engines that want them share the
    # "Lifegain" label, so focus reads them as one avenue.
    ("lifegain_matters", "you"): _lifegain_spec(
        "Lifegain", "incidental and repeatable lifegain"
    ),
    # _matters sweep (ADR-0034): the MAKER side of the lifegain split — cards that
    # PERFORM the lifegain (the lifelink keyword / a structured `gain_life` Effect / a
    # grant-lifelink Effect).
    ("lifegain_makers", "you"): _lifegain_spec(
        "Lifegain (makers)",
        "lifegain sources — incidental and repeatable lifegain doers",
    ),
    ("wants_lifegain", "you"): _lifegain_spec(
        "Lifegain",
        "lifegain to offset your own life payments — the sources and payoffs of "
        "the Lifegain package",
    ),
    ("plus_one_matters", "any"): _spec(
        "+1/+1 counters",
        "counter generators, doublers, and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        # Serve on the lanes' idents, once plus_one_makers read the
        # keyword actions that place +1/+1 counters: the makers, the payoffs, the
        # doublers (Doubling Season) and proliferate.
        None,
        serve_idents=_PLUS_ONE_SERVE_IDENTS,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _KEYWORD_COUNTER_EXTRA,
            _COUNTER_KEYWORD_EXTRA,
            _PROLIFERATE_EXTRA,
            _COUNTER_RESILIENCE_EXTRA,
        ),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the +1/+1 split — cards that PLACE
    # +1/+1 counters (the place_counter doers, the +1/+1 keyword bearers, amass /
    # fabricate / devour). The avenue still offers the whole +1/+1 package (the makers
    # plus the whenever-a-counter / has-a-counter payoffs together), so this spec copies
    # the kept plus_one_matters serve content; only the role label differs.
    ("plus_one_makers", "any"): _spec(
        "+1/+1 counters (makers)",
        "counter generators, doublers, and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        None,
        serve_idents=_PLUS_ONE_SERVE_IDENTS,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _KEYWORD_COUNTER_EXTRA,
            _COUNTER_KEYWORD_EXTRA,
            _PROLIFERATE_EXTRA,
            _COUNTER_RESILIENCE_EXTRA,
        ),
    ),
    # ADR-0027 — any_counter_matters: the KIND-AGNOSTIC counter lane (CR 701.34a —
    # proliferate adds "one counter of each kind already there", so it cares about
    # counters generically). The "has any counter" / "for each counter on" / move-
    # double-remove-a-counter payoffs (Bulwark Ox, Innkeeper's Talent, Iroh, Cleopatra,
    # The Swarmlord) want proliferate, counter-doublers, and any-kind counter sources,
    # NOT only +1/+1. Distinct from plus_one_matters (the +1/+1-specific lane) and the
    # per-kind oil/rad/named lanes. CR 122.1 / 701.34a.
    ("any_counter_matters", "you"): _spec(
        "Any counters",
        "proliferate, counter doublers, and any-counter sources",
        {"oracle": r"proliferate|for each counter|move .* counter|\bcounter on\b"},
        # Serve rides the lanes. Lane gaps: devour's entry counters (Mycoloth),
        # "whenever you proliferate" payoffs (Scheming Aspirant, Tam), granted doublers
        # (Evolution Vat), "for each counter on ~" scalers (Kinsbaile Borderguard).
        None,
        serve_idents=_ANY_COUNTER_IDENTS,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _PROLIFERATE_EXTRA,
        ),
    ),
    # _matters sweep (ADR-0034): the DOER half of the any_counter split. A deck whose
    # commander/cards PERFORM kind-agnostic counter manipulation (proliferate, counter
    # relocation, any-kind removal) wants MORE such engines — proliferate sources and
    # counter-movers that compound the kind-agnostic plan. Same search as the payoff
    # lane; the label reframes it as the maker/engine avenue. CR 122.1 / 701.34a.
    ("any_counter_makers", "you"): _spec(
        "Any-counter engines",
        "proliferate, counter movers, and any-kind counter manipulation",
        {"oracle": r"proliferate|for each counter|move .* counter|\bcounter on\b"},
        # Serve rides the lanes, shared with any_counter_matters.
        None,
        serve_idents=_ANY_COUNTER_IDENTS,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _PROLIFERATE_EXTRA,
        ),
    ),
    # task #93: counter_hate — an opponent-directed counter-placement DENIAL
    # (Blightbeetle, Suncleanser — CR 701.71), a narrow anti-counters stax
    # tell distinct from the payoff lanes above. Only 2 commander-legal
    # cards carry the exact shape; the search widens slightly to any
    # "opponents/opponent...can't...counter(s)" hate text so a deck-forge
    # search surfaces siblings if a future set prints more.
    ("counter_hate", "opponents"): _spec(
        "Counter denial",
        "deny opponents' counters (anti-+1/+1, anti-proliferate stax)",
        {"oracle": r"opponents?[^.]*can.t (?:have|get)[^.]*counters?"},
        # Serve rides the lane (2026-10-18): regex missed Suncleanser's two-sentence
        # 'loses all counters. That player can't get'
        None,
        serve_idents=frozenset({"counter_hate|opponents|"}),
    ),
    # np_boons task #5: adapt_matters — Biomancer's Familiar's re-adapt
    # enabler (CR 701.46a), a 1-card population today; the search widens
    # slightly (any "adapt(s) as though"/"adapt again" idiom) so a future
    # printing surfaces without a code change.
    ("adapt_matters", "you"): _spec(
        "Adapt support",
        "enable or re-trigger Adapt (CR 701.46) on creatures you control",
        {"oracle": r"\badapts?\b"},
        # Serve rides the lane (2026-10-18): regex and lane served the same card; the
        # lane is now the one source
        None,
        serve_idents=frozenset({"adapt_matters|you|"}),
    ),
    # Hand spec (overrides the mined sweep detector) so the avenue can fan out a
    # dedicated "Flip fixing" sub-avenue. The flat coin-flip search returns ~60 generic
    # "flip a coin" payoffs and buries Krark's-Thumb-style fixers past the package cap,
    # even though fixing flips is the whole point of a coin-flip deck.
    ("coin_flip", "any"): _spec(
        "Coin flips",
        "coin-flip payoffs and outlets",
        {
            "oracle": (
                r"flip a coin|flip (?:two|three|\d+) coins"
                r"|flip (?:one or more|a number of) coins"
                r"|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip"
                r"|come up heads"
            )
        },
        # Serve rides the lane (2026-10-18): regex missed 'Flip five coins' / 'each
        # player flips a coin' (Ral Zarek, Goblin Assassin)
        None,
        serve_idents=frozenset({"coin_flip|you|"}),
        extras=(
            # A flip FIXER either re-flips/ignores (the Krark's Thumb family) or
            # declaratively GRANTS the result ("come up heads AND you win", Edgar). The
            # bare branches `come up heads` / `you win … flip` (e21b7d6) wrongly caught
            # PAYOFFS that reference a flip result as a CONDITION: Mana Clash ("come up
            # heads on the same flip"), Two-Headed Giant ("if both come up heads"),
            # Squee's Revenge ("if you win all the flips, draw"). A regex can't separate
            # a grant from a condition, so we match only the declarative grant. Verified
            # against bulk: this yields EXACTLY {Krark's Thumb, Edgar}.
            SubAvenue(
                "Flip fixing",
                "cards that bias, repeat, or ignore unfavorable coin flips "
                "(Krark's Thumb effects)",
                {
                    "oracle": (
                        r"instead flip [^.]*coin|\breflip"
                        r"|flip [^.]*coins? again|flip an additional coin"
                        r"|come up heads and you win"
                    )
                },
            ),
        ),
    ),
    ("draw_matters", "you"): _spec(
        "Draw triggers / wheels",
        "draw-trigger payoffs and extra-draw engines (Nekusar / Chasm Skulker space)",
        {"oracle": r"whenever you draw|draw an additional card"},
        # The draw payoffs plus the symmetric draw engines and wheels (Howling Mine,
        # Wheel of Fortune). Lane gaps: extra draw-step draws (Grafted Skullcap),
        # granted "whenever you draw" (Diviner's Wand), ordinal draws (Lady Octopus).
        None,
        serve_idents=frozenset({"draw_matters|you|", "card_draw_engine|each|"}),
    ),
    # Spellslinger. A card FEEDS this iff casting it is "casting an instant or sorcery"
    # — fixed by its TYPE (CR 601.2), OR it has prowess (CR 702.108a, a keyword payoff),
    # OR it carries a magecraft / "whenever you cast a (noncreature|instant|sorcery)
    # spell" trigger (magecraft is an ability word — CR 207.2c — so it lives ONLY in
    # prose). Bare "draw a card" is none of these: it mislabeled ~1250 value permanents
    # (Rhystic Study, Esper Sentinel, The One Ring) as Spellslinger. Copies aren't cast
    # (CR 707.10), so spell-copy payoffs belong to spell_copy, not here.
    ("spellcast_matters", "you"): _SPELLSLINGER_SPEC,
    # `create .*token` was type-blind — it served every Treasure/Clue/Food maker
    # (~428 in WBR), none of which are sacrifice fodder. Require the literal "creature
    # token" (CR 111.10 token types); and exclude "sacrifice a land" (fetchlands) from
    # the outlet branch.
    ("sacrifice_outlets", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create [^.]*creature token|sacrifice"},
        # Fodder tokens, outlets, death payoffs on every side, edicts and death-value
        # fodder (Ichor Wellspring). Saga reminders and basic-land sacrifices are noise;
        # lane gaps: punisher edicts (Torment of Hailfire), granted dies-draws (Henzie),
        # haunt.
        None,
        serve_idents=_ARISTOCRATS_IDENTS,
        extras=(
            _SELF_RECUR_EXTRA,
            _DEATH_DRAIN_EXTRA,
            _BOARD_WIPE_EXTRA,
            _SELF_SAC_CREATURE_EXTRA,
            # Dies-return GRANTERS (Feign Death, Supernatural Stamina, Undying Evil):
            # loop a key creature with a sac outlet — core aristocrats fuel.
            _DIES_RECURSION_EXTRA,
        ),
    ),
    # Self-death PAYOFF (Kokusho / Junji / Ryusei / Lord Xander): the commander's OWN
    # "when ~ dies, <value>" trigger is the engine, so it wants to re-fire that death.
    # Serves dies-recursion (return it after the trigger → repeat), sac outlets (kill it
    # on demand), and reanimation (recast). Distinct from death_matters (aristocrats,
    # OTHER creatures dying). Verified: Kokusho/Junji's top EDHREC synergy cards are
    # exactly these dies-return grants.
    ("self_death_payoff", "you"): _spec(
        "Self-death payoff",
        "ways to re-fire your commander's own death trigger — return it after death, "
        "sacrifice it on demand, reanimate it",
        {"oracle": _DIES_RECURSION_ORACLE},
        # Serve rides the lane (2026-10-18): regex missed dies-return Auras/Equipment
        # (False Demise); served 'Undying' names
        None,
        serve_idents=frozenset({"dies_recursion|you|"}),
        extras=(_DIES_RECURSION_EXTRA, _SAC_OUTLET_EXTRA, _REANIMATION_EXTRA),
    ),
    # A forced/symmetric-sacrifice commander (Braids, Endrek Sahr — "each player
    # sacrifices") loses its OWN board too, so it wants recurring fodder to survive:
    # recurring token makers ("create … creature token") and self-recurring creatures
    # (Reassembling Skeleton). The opponent-only-edict half is rare among commanders.
    # task B-3: keep_n_wrath — choose-N-keep-the-rest resets (Single Combat,
    # Cataclysm). A voltron deck's favorite sweeper: the one big threat is
    # exactly what you keep, and the reset dodges targeted removal (the
    # disjoint-from-edicts adjudication — CR 701.21a fresh choice vs a
    # TrackedSet back-reference). Serve: the rebuild package mass_removal
    # already serves (protection + reanimation), never the wipe itself.
    ("keep_n_wrath", "each"): _spec(
        "Keep-N wraths",
        "choose-N-keep-the-rest board resets that spare your one big threat",
        {"oracle": r"(?:then )?(?:sacrifices?|destroys?) the rest"},
        # Serve = the rebuild package ONLY (verified-review F7): the wipe
        # pattern itself served redundant wraths above actual protection/
        # reanimation cards. The search still FINDS more keep-N wraths
        # (that is the Find surface's job); the serve scores what helps
        # you rebuild through one.
        None,
        extras=(_BOARD_PROTECTION_EXTRA, _REANIMATION_EXTRA),
        serve_keywords=("indestructible",),
    ),
    ("keep_n_wrath", "opponents"): _spec(
        "One-sided keep-N",
        "opponents keep N and sacrifice the rest while your board is "
        "untouched (Archfiend of Depravity)",
        {"oracle": r"opponents? choose[^.]*then sacrifices? the rest"},
        None,
        extras=(_BOARD_PROTECTION_EXTRA,),
    ),
    # task B-5: combat_choice_makers — you make opponents' attack/block
    # declarations (CR 508.1a / 509.1a transferred to you). Pairs with the
    # forced-combat package: goad, forced attack, combat support.
    ("combat_choice_makers", "opponents"): _spec(
        "Combat puppeteer",
        "cards that let you make attack and block choices for opponents "
        "(Master Warcraft, Odric) — pair with goad and forced-attack effects",
        {
            "oracle": r"you choose which creatures? (?:attack|block)"
            r"|choose how those creatures? blocks?"
        },
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"combat_choice_makers|opponents|"}),
        extras=(_FORCE_ATTACK_EXTRA, _COMBAT_SUPPORT_EXTRA),
    ),
    ("edict_makers", "each"): _spec(
        *SWEEP_LABELS["edict_makers"],
        {"oracle": _EDICT_SWEEP_REGEX},
        # Serve rides the lanes: the edicts and the creature-token makers that
        # feed your side of a symmetric one.
        None,
        serve_idents=_TOKEN_MAKER_IDENTS
        | {"edict_makers|each|", "edict_makers|opponents|"},
        extras=(_SELF_RECUR_EXTRA, _DEATH_DRAIN_EXTRA),
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create [^.]*creature token|whenever .* dies"},
        # Serve rides the lanes, shared with sacrifice_outlets: the same classified
        # remainder.
        None,
        serve_idents=_ARISTOCRATS_IDENTS,
        extras=(
            _SELF_RECUR_EXTRA,
            _DEATH_DRAIN_EXTRA,
            _BOARD_WIPE_EXTRA,
            _SELF_SAC_CREATURE_EXTRA,
            # Dies-return granters (Feign Death, Undying Evil) — aristocrats loop fuel.
            _DIES_RECURSION_EXTRA,
        ),
    ),
    # The bare word `haste` matched its reminder text and incidental mentions ("loses
    # haste"). Gate on the Haste keyword (CR 702.10) + the team-grant phrasing; anchor
    # the token branch to the literal "creature token".
    # The serve once credited only haste-grant + token-makers — 40/223 (18%) of the
    # attack-trigger payoff axis. Widen with the "whenever you attack" / "whenever a
    # creature you control attacks" alternation (CR 508 declare-attackers triggers) so
    # the avenue surfaces attack-trigger payoffs (Hellrider, Adeline, Shared Animosity),
    # not just speed. Anchored on "you attack" / "you control attacks" so a defensive
    # "whenever a creature attacks you" trigger never matches.
    ("attack_matters", "you"): _spec(
        "Combat",
        "attack-trigger payoffs, haste enablers, and aggressive bodies",
        {
            "oracle": r"haste|create .*creature token"
            r"|whenever you attack|you control attacks"
        },
        r"(?:gains?|gain|have|has) haste|create [^.]*creature token"
        r"|whenever you attack\b"
        r"|whenever (?:a|an|another|one or more)[^.]*creatures? you control attacks?"
        # Single-creature attack triggers + combat-damage riders are the aggro payoff
        # bodies (Vicious Conquistador, Hellrider); "(?! you)" keeps defensive
        # "attacks you" triggers out.
        r"|whenever [^.]*\battacks\b(?! you)"
        r"|whenever [^.]*deals combat damage to "
        r"(?:a player|an opponent|each opponent|that player)"
        # Combat keyword-anthems that buff your attackers (Blade Historian, Odric:
        # "attacking creatures you control have double strike" / "gain first strike").
        r"|(?:attacking )?creatures you control (?:have|gain|get)[^.]*"
        r"(?:double strike|first strike|trample|menace|deathtouch|vigilance"
        r"|indestructible|can't be blocked)"
        # Equipment/Auras suit up the attacker (a combat deck wants the gear).
        r"|equipped creature|enchanted creature gets|\bequip \{"
        # Extra combats (Combat Celebrant, Moraug, Aggravated Assault): every added
        # combat phase is another round of attack triggers — a top attack payoff. The
        # narrow extra_combats lane already served these, but attack-trigger commanders
        # (Winota, Johan, Umaro) open attack_matters, not extra_combats. An extra TURN
        # (Time Warp) is the strict superset — a whole turn, combat included, so the
        # attack replays; Narset (free-casts on attack) snowballs hardest off it.
        r"|additional combat phase"
        r"|takes? (?:an?|two|another|that many)?\s*extra turns?",
        serve_keywords=("haste",),
    ),
    # The bare `onto the battlefield` branch matched every cheat-into-play and
    # reanimation effect (Sneak Attack, Reanimate). Anchor it to a LAND card, mirroring
    # lands_matter (CR 305 — landfall fires on a land entering, not any permanent).
    # The landfall lane wants the PAYOFFS most of all (Lotus Cobra / Scute Swarm /
    # Tatyova — "Landfall — whenever a land you control enters …"), then the enablers
    # that fire them repeatedly: extra land drops (Azusa / Dryad) and land recursion
    # (Crucible / Ramunap — "play lands from your graveyard"). The old serve credited
    # only fetch + extra-lands, so every landfall payoff read as off-theme.
    ("landfall", "you"): _spec(
        "Landfall",
        "landfall payoffs plus the extra land drops, fetch, and recursion firing them",
        {"oracle": _LANDFALL_ORACLE},
        _LANDFALL_ORACLE,
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        # Serve rides the lanes: the creature-token makers (amass, endure and
        # populate included) and the token payoffs, token anthems among them
        # (Intangible Virtue — tokens_matter).
        None,
        serve_idents=_TOKEN_MAKER_IDENTS | {"tokens_matter|you|"},
        # Offspring (CR keyword) makes a 1/1 token copy of the creature — token-making
        # in stripped reminder text, so credit it via the Scryfall keyword.
        serve_keywords=("offspring",),
        extras=(_TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA, _GOWIDE_ANTHEM_EXTRA),
    ),
    # Serve on the lanes' idents, shared with treasure_makers below: the makers
    # read granted / target-player / replacement Treasure creation, and the
    # payoff reads any filter naming Treasures, the "if mana from a Treasure was
    # spent" condition included. The regex's remainder is opponents' Treasures
    # (gift, "target opponent creates", CR 111.2), an opponent's permanent turned
    # into a Treasure, a treasure counter, and two gaps (Jetmir's Fixer's and
    # Excess's phase residues).
    ("treasure_matters", "you"): _spec(
        "Treasure",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        None,
        serve_idents=_TREASURE_IDENTS,
    ),
    # _matters sweep (ADR-0034): treasure split. The make_token MAKER arm
    # (treasure_makers, cards that create Treasure tokens) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (treasure_matters) both serve the same
    # Treasure ramp/fixing/sacrifice avenue. The union == the old treasure_matters;
    # only the role label differs.
    ("treasure_makers", "you"): _spec(
        "Treasure makers",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        # Serve rides the lanes, shared with treasure_matters above.
        None,
        serve_idents=_TREASURE_IDENTS,
    ),
    # Pariah combo (Cho-Manno, Anti-Venom): an unkillable commander that prevents damage
    # to itself wants the redirect effects (Pariah / Pariah's Shield: "damage dealt to
    # you is dealt to enchanted/equipped creature instead") plus the indestructible /
    # protection grants that keep the redirect target alive.
    ("damage_redirect", "you"): _spec(
        "Damage redirection",
        "redirect-all-damage effects (Pariah) onto your unkillable creature, damage "
        "prevention to blank it, plus indestructible/protection to keep it alive",
        {"oracle": r"damage that would be dealt to you|prevent [^.]*damage"},
        # Serve on the lanes' idents: the redirects (CR 614.9 —
        # Pariah's static form included) and damage PREVENTION (CR 615), which
        # blanks the soaked damage a redirect-to-self commander (Hazduhr,
        # Cho-Manno) takes. Left out: life floors (Worship, Ali from Cairo —
        # board_protection; Worship's ruling: the damage is still dealt, so it
        # blanks nothing a creature soaks). The redirects phase parks as residues
        # (Kjeldoran Royal Guard, Turn the Tables, Kor Chant) recover (the
        # ``damage_redirect`` token).
        None,
        serve_idents=frozenset({"damage_redirect|you|", "damage_prevention|you|"}),
        extras=(
            _VOLTRON_PROTECT_EXTRA,
            # PROFIT from the soaked damage: a redirect-to-self commander
            # (Daughter of Autumn) takes the redirected hit HERSELF (CR 614.9),
            # so payoffs watching "a creature you control is dealt damage"
            # (Rite of Passage) or an Aura on the soak creature (Druid's Call)
            # fire. NOT generic enrage ("whenever THIS creature is dealt
            # damage"): the original creature is never dealt the redirected
            # damage. The serve is the damage_received_matters lane.
            SubAvenue(
                "Profit from the soaked damage",
                "payoffs that fire when a creature you control is dealt damage",
                {"oracle": _SOAK_PAYOFF_SEARCH},
                serve=Serve(signal_idents=frozenset({"damage_received_matters|you|"})),
            ),
        ),
    ),
    # The soak payoffs themselves (Rite of Passage, Druid's Call): fed by the
    # redirects that move damage onto one creature of yours (CR 614.9).
    ("damage_received_matters", "you"): _spec(
        "Damage-received payoffs",
        "redirects that move damage onto your creature, plus more soak payoffs",
        {"oracle": _SOAK_PAYOFF_SEARCH},
        None,
        serve_idents=frozenset(
            {"damage_received_matters|you|", "damage_redirect|you|"}
        ),
    ),
    # Vanilla (Ruxa, Muraganda Petroglyphs): creatures with NO rules text (the tribe)
    # plus the "creatures with no abilities" payoffs.
    ("vanilla_matters", "you"): _spec(
        "Vanilla beaters",
        "efficient creatures with no abilities plus the payoffs that reward them",
        {"card_type": "Creature"},
        # The lane serves the regex's one card plus Ruxa and Jasmine Boreal of the Seven
        # ("no abilities" payoffs).
        None,
        serve_idents=frozenset({"vanilla_matters|you|"}),
        serve_vanilla=True,
    ),
    # Banding (CR 702.22a): a banding commander (Ayesha, Jarkeld) wants other banding
    # creatures to form attacking/blocking bands. Keyword[]-anchored + the oracle word.
    ("has_banding", "you"): _spec(
        "Banding",
        "creatures with banding to form attacking and blocking bands",
        {"oracle": r"\bbanding\b"},
        r"\bbands? with other|\bbanding\b",
        serve_keywords=("banding",),
    ),
    # Outlaw tribal (Vial Smasher): the 5 outlaw creature types plus "outlaws you
    # control" anthems/payoffs. (CR: outlaw = Assassin/Mercenary/Pirate/Rogue/Warlock.)
    ("outlaw_matters", "you"): _spec(
        "Outlaws",
        "outlaws (Assassins / Mercenaries / Pirates / Rogues / Warlocks) plus the "
        "anthems and payoffs that reward a board of them",
        {
            "oracle": (
                r"\boutlaws?\b"
                r"|create[s]?[^.]*\b(?:mercenary|pirate|rogue|assassin|warlock)\b"
                r"[^.]*\btoken"
            )
        },
        # ALSO serve outlaw-TOKEN makers ("create a 1/1 red Mercenary token" — those
        # tokens are outlaws) and outlaw RECURSION ("return … outlaw creature cards"),
        # not just cards whose own type line is an outlaw subtype. The outlaw payoffs
        # and outlaw-token makers. Tokens an opponent creates (Pursued Whale, Warren
        # Weirding) drop out; outlaw recursion modes (Kami of Restless Shadows) are a
        # lane gap.
        None,
        serve_idents=frozenset(
            {
                "outlaw_matters|you|",
                "token_maker|you|Assassin",
                "token_maker|you|Mercenary",
                "token_maker|you|Pirate",
                "token_maker|you|Rogue",
                "token_maker|you|Warlock",
            }
        ),
        serve_types=("assassin", "mercenary", "pirate", "rogue", "warlock"),
    ),
    # Snow (Isu the Abominable): snow permanents (Snow type), snow payoffs ("number of
    # snow permanents"), and snow mana. "snow" is essentially only the MTG supertype.
    ("snow_matters", "you"): _spec(
        "Snow",
        "snow permanents, snow lands, and snow-count payoffs",
        {"oracle": r"\bsnow\b"},
        # The lane serves the non-snow payoffs (Glacial Revelation, Rimewind
        # Cryomancer); the snow permanents themselves serve through the type arm.
        None,
        serve_idents=frozenset({"snow_matters|you|"}),
        serve_types=("snow",),
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        {"card_type": "Artifact"},
        r"artifacts? you control|for each artifact|\bmetalcraft\b|\baffinity\b"
        r"|artifact spells? you cast cost"
        # Type-GRANTERS that turn your stuff into artifacts enable the whole deck
        # (Mycosynth Lattice, Liquimetal Coating, March of the Machines).
        r"|becomes? an? artifact|(?:are|is an?) artifacts?"
        # Every artifact subtype (CR 205.3g) IS an artifact: makers ("create a Treasure
        # / Vehicle / Equipment … token"), references ("Equipment/Vehicles you control",
        # "for each Treasure"), and Investigate (makes a Clue) all feed artifact-count /
        # affinity / metalcraft.
        r"|create [^.]*\b(?:" + _ART_SUBTYPES + r")\b[^.]*token"
        r"|\b(?:" + _ART_SUBTYPES + r")s? you control\b"
        r"|for each (?:an? )?(?:" + _ART_SUBTYPES + r")\b"
        r"|\binvestigate\b"
        # Artifact dig/tutor: "reveal an artifact card … put it into your hand"
        # (Casey Jones, Glint-Nest Crane, Ingenious Smith) finds the deck's payoffs.
        r"|reveal an artifact card[^.]*put it into your hand",
        # BEING an artifact is on-theme: an artifact-count / affinity / metalcraft deck
        # counts every artifact — lands (Seat of the Synod), rocks (Mind Stone),
        # Equipment, Vehicles — even with no "artifact" in the oracle. The oracle-only
        # serve missed these and wrongly read them as generic "good stuff".
        serve_types=("artifact",),
    ),
    # Serve augmented with "whenever you cast an enchantment" so the 14 plain CREATURES
    # that trigger on enchantment casts (Verduran/Mesa Enchantress, Sythis) — missed by
    # both the {card_type:Enchantment} type-serve and the count regex — are credited.
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b"
        r"|whenever you cast an enchantment"
        # Enchantment-GRANTERS (Enchanted Evening, Nyx: "are enchantments in addition").
        r"|(?:are|is|becomes?) (?:an? )?enchantments? in addition"
        # Every enchantment subtype (CR 205.3h) IS an enchantment: Role/Shard/Aura
        # token makers plus references ("Auras/Sagas you control", "for each Saga",
        # "whenever a Class you control …") all feed constellation / enchantment-count.
        r"|create [^.]*(?:" + _ENCH_SUBTYPES + r"|enchantment)[^.]*token"
        r"|\b(?:" + _ENCH_SUBTYPES + r")s? you control\b"
        r"|for each (?:an? )?(?:" + _ENCH_SUBTYPES + r")\b"
        r"|whenever (?:a|an|another) (?:" + _ENCH_SUBTYPES + r")\b",
        # BEING an enchantment is on-theme: constellation / enchantment-count counts
        # every enchantment (Auras, Sagas, enchantment creatures like Spirited
        # Companion), even with no "enchantment" in the oracle.
        serve_types=("enchantment",),
    ),
    # A color-hoser commander (color_hoser) wants the color-changing "Painter" toolbox
    # so its color payoff (bounce/restrict/punish a named color) applies to EVERY
    # permanent: making opponents' creatures blue makes Llawan's "blue creatures"
    # clauses catch them (color is a layer-5 characteristic the hoser checks: CR 105.2).
    # Serve is the change-a-color toolbox: Painter's Servant ("are the chosen color"),
    # the -lace / -Wisps cycles + Distorting Lens ("becomes the color of your choice"),
    # and the text-changers (Mind Bend / Sleight of Mind / Glamerdye / Alter Reality:
    # "replacing all instances of one color"). Anchored on a CHANGE verb so a
    # protection-from-color trick (Gods Willing) or mana fixer never matches.
    ("color_hoser", "you"): _spec(
        "Color-bending",
        "color-changing 'Painter' cards that force your color payoff onto everything",
        {
            "oracle": r"becomes the color of your choice|are the chosen color"
            r"|replacing all instances of one color"
        },
        r"becomes the color of your choice"
        r"|(?:spell or permanent|permanent or spell|target permanent|target creature) "
        r"becomes (?:white|blue|black|red|green)\b"
        r"|are the chosen color"
        r"|replacing all instances of one color"
        # Anti-color HATE is what these commanders (Major Teroh, Ascendant Evincar,
        # Crovax, Dromar, Llawan) actually want — make/keep everything a color, then
        # hose it. Only the 6 color_hoser commanders open the lane, so the narrow
        # color-hate stays scoped to the decks that exploit it.
        r"|(?:destroy|exile|return) all (?:non)?(?:white|blue|black|red|green) "
        r"(?:creature|permanent)s?"
        r"|protection from (?:white|blue|black|red|green)"
        r"|(?:white|blue|black|red|green) creatures? can't (?:attack|block|be)"
        r"|can't cast (?:white|blue|black|red|green)",
    ),
    # ADR-0027: tokens_matter migrated to the Card IR (the lane fires from
    # crosswalk_signals._tokens_matter). This serve spec was
    # always hand-registered and independent of the two deleted _HAND_FLOOR producers,
    # so it survives unchanged — its curated SEARCH regex below differs from the
    # detector (the detector's go-wide count-scaler + token-doubler arms are supplied
    # here as the _GOWIDE_*/_TOKEN_DOUBLER_EXTRA avenues instead).
    # The greedy `whenever .*token.*enters` spanned clauses and matched attack-trigger
    # token-makers and NONtoken-ETB payoffs (Darksteel Splicer). Anchor the entering
    # object to a token in the SAME clause.
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b"
        r"|whenever (?:a|one or more|another)[^.]*?\btokens?\b[^.]*?\benters\b"
        r"|\bpopulate\b"
        # Amass creates or grows an Army CREATURE token (CR 701.47), so an amass card is
        # a token maker (Mouth of Sauron / Grishnákh want the amass package). Like
        # Mobilize, its token-making lives in stripped reminder text, so credit it.
        r"|\bamass\b",
        # NB: GENERIC single-token makers are deliberately NOT in the serve — a single
        # maker is generically good (every deck runs some), not archetype-UNIQUE, so
        # serving all 2315 floods the lane. But MASS makers ("create 2+/X tokens at
        # once" — _GOWIDE_MAKER_EXTRA) ARE the go-wide build-around and kind-agnostic
        # here (this lane has no subject; Leonardo/Adeline count ANY creature), so they
        # belong. They stay OFF the per-subject token_maker lane, where kind matters
        # (Krenko wants Goblin makers, not Saprolings).
        # EXCEPTION: Mobilize is a bounded (~28-card) Warrior-token SWARM keyword whose
        # token-making lives in stripped reminder text — credit the keyword so a
        # Mobilize/go-wide commander (Zurgo) covers the rest of its swarm package.
        serve_keywords=("mobilize",),
        extras=(
            _TOKEN_DOUBLER_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _GOWIDE_ANTHEM_EXTRA,
            _GOWIDE_MAKER_EXTRA,
            _TEAM_PROTECT_EXTRA,
        ),
    ),
    # The bare `your opponents` alternative matched any card that merely names opponents
    # (Edric's draw trigger, Telepathy's hand reveal). Serve the actual restriction/tax
    # SHAPES instead (CR 601.2f cost increases, prohibitions) — which also recovers the
    # symmetric taxes the old regex missed (Thalia: "Noncreature spells cost {1} more").
    ("stax_taxes", "opponents"): _spec(
        "Stax & taxes",
        "tax and restriction effects — opponent taxes, symmetric locks, and hatebears",
        {
            "oracle": (
                r"opponents? can't"
                r"|spells your opponents cast cost"
                r"|creatures your opponents control"
            )
        },
        _STAX_SERVE_ORACLE,
    ),
    # Symmetric-stax commander (Hokori, Winter Orb-style locks): wants the SAME stax
    # piece pool — it runs opponent-taxes + symmetric locks + hatebears alike. Shares
    # the stax serve; hand-written so the auto-register doesn't bind a narrower one.
    ("symmetric_stax", "each"): _spec(
        "Symmetric stax",
        "stax pieces a symmetric-lock deck runs — taxes, locks, and hatebears",
        {"oracle": r"players? can't|enters?(?: the battlefield)? tapped|can't be"},
        _STAX_SERVE_ORACLE,
    ),
    # ADR-0027: symmetric_damage_each's SWEEP_DETECTORS row was deleted (detection moved
    # to the Card IR — the v22 damage Effect scope=='each' arm + each-player mirror).
    # The search keeps a board-wide each-everyone regex via regex= (the strangler
    # pattern), so the "sweepers and pingers that hit everyone" pool still surfaces; it
    # is a SEARCH, so it intentionally keeps the each-opponent reach the DETECTOR split
    # dropped — a Pestilence deck wants Pyrohemia AND Sizzle-style group burn. The serve
    # is the lane's ident, with each-opponent burn as the Group burn extra.
    ("symmetric_damage_each", "each"): _sweep_spec_with_extras(
        "symmetric_damage_each",
        (_GROUP_BURN_EXTRA,),
        regex=(
            r"deals \d+ damage to each (?:player|opponent and|"
            r"creature and each player)"
            r"|deals \d+ damage to each opponent"
            r"|deals \d+ damage to each player"
            r"|deals (?:\d+|x) damage to each (?:creature|nonartifact creature)"
            r"[^.]*and each player"
        ),
        # Gains the variable symmetric burns (Price of Progress, Acidic Soil);
        # each-opponent burn (Boltwave, Sizzle) is the Group burn extra.
        serve_idents=frozenset({"symmetric_damage_each|each|"}),
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects, the high-ETB creatures worth re-using, and the "
        "doublers that multiply each enter trigger",
        {"preset_names": ("blink",)},
        # Same-sentence "exile … then return … battlefield" (Restoration Angel), PLUS
        # the two-sentence form "exile … . Return it/that/those … battlefield"
        # (Flickerwisp, Charming Prince). The pronoun anchor + single-period limit keep
        # an unrelated exile-removal-then-return-a-land off the lane.
        r"exile[^.]*?return[^.]*?battlefield"
        r"|exile[^.]{0,90}?\.\s*returns? (?:it|them|that|those)[^.]{0,50}?battlefield",
        # Death-return is a distinct mechanic (dies_recursion), offered as its own
        # avenue here — a blink deck re-uses ETBs via death too, but it isn't flicker.
        # Self-bounce recast engines (Whitemane Lion, Kor Skyfisher, Jeskai Barricade)
        # re-fire an ETB by returning your own creature and recasting — staple
        # blink-deck value, so they belong here too.
        extras=(
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
    ),
    ("mill_makers", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        {"preset_names": ("mill",)},
        # Serve rides the lane (2026-10-18): regex and lane served the same 579 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"mill_makers|any|"}),
    ),
    ("goad_makers", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        {"preset_names": ("goad",)},
        # Serve rides the lane (2026-10-18): regex missed forced-attack + attack-your-
        # foes incentives (Alluring Siren, Breena)
        None,
        serve_idents=frozenset({"goad_makers|opponents|"}),
        # politics: make yourself a bad target too; force-attack: feed the payoff by
        # making opponents swing (Kazuul rewards being attacked).
        extras=(_PILLOWFORT_EXTRA, _FORCE_ATTACK_EXTRA),
    ),
    # Fog / damage-prevention commanders durdle defensively — pillowfort is a top
    # EDHREC pick for them (4 commanders in the evidence). Keep the mined fog regex
    # (ADR-0027: damage_prevention migrated, SWEEP_DETECTORS row deleted, so pass the
    # pinned DAMAGE_PREVENTION_REGEX explicitly — the serve never drifts from the mine).
    ("damage_prevention", "you"): _sweep_spec_with_extras(
        "damage_prevention",
        (_PILLOWFORT_EXTRA, _DAMAGE_SOAK_EXTRA),
        regex=DAMAGE_PREVENTION_REGEX,
        # Serve rides the lane (2026-10-18): regex missed redirect-to-self + prevent-1
        # statics (Beacon of Destiny, Gisela)
        serve_idents=frozenset({"damage_prevention|you|", "damage_redirect|you|"}),
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate plus any-kind counter sources and doublers (Vorinclex)",
        {"preset_names": ("proliferate",)},
        # Lane gaps: loyalty-counter placers (Oath of Gideon, Commodore Guff), empower
        # Jace, "whenever you proliferate" payoffs (Scheming Aspirant). The +1/+1
        # package's documented exclusions and planeswalkers naming a loyalty counter are
        # out.
        None,
        serve_idents=_PROLIFERATE_IDENTS,
        extras=(_COUNTER_DOUBLER_EXTRA, _KEYWORD_COUNTER_EXTRA),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the proliferate split — cards
    # that PERFORM proliferate (the Scryfall keyword carriers Atraxa / Evolution
    # Sage / Karn's Bastion + the keyword-less native proliferators). A
    # proliferate-makers commander wants MORE proliferate engines plus the
    # any-kind counter sources and doublers those engines multiply — same serve
    # pool as the payoff lane (the avenue legitimately offers makers + payoffs
    # together, ADR-0034).
    ("proliferate_makers", "you"): _spec(
        "Proliferate",
        "proliferate engines plus any-kind counter sources and doublers",
        {"preset_names": ("proliferate",)},
        # Serve rides the lanes, shared with proliferate_matters.
        None,
        serve_idents=_PROLIFERATE_IDENTS,
        extras=(_COUNTER_DOUBLER_EXTRA, _KEYWORD_COUNTER_EXTRA),
    ),
    # Hand-promote EVERY mined +1/+1-counter lane with the shared counters package so a
    # counters commander surfaces sources (Forgotten Ancient), doublers (Hardened
    # Scales), keyword counters, and proliferate no matter which fragmented lane opened.
    # ADR-0027 β: self_counter_grow migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted — a structural SelfRef-marker arm + a narrowed mirror), so the search
    # keeps the old regex via the pinned SELF_COUNTER_GROW_SWEEP_REGEX; the serve is
    # the lanes' idents.
    ("self_counter_grow", "you"): _sweep_spec_with_extras(
        "self_counter_grow",
        _COUNTERS_PACKAGE,
        regex=SELF_COUNTER_GROW_SWEEP_REGEX,
        # Self growth plus the self-growing keyword actions (explore, earthbend,
        # connive) and named self counters. "On it" on another creature (bolster,
        # tribute) is noise; lane gaps: energy-paid growth (the Thriving cycle),
        # conditional enters-with counters.
        serve_idents=frozenset(
            {
                "self_counter_grow|you|",
                "explore_makers|you|",
                "earthbend_makers|you|",
                "connive_makers|you|",
            }
        ),
    ),
    # ADR-0027 tranche2-B: counter_manipulation's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — counter_move/remove_counter effects + a kept
    # cost mirror). The serve keeps the old regex via regex= (strangler pattern).
    ("counter_manipulation", "you"): _sweep_spec_with_extras(
        "counter_manipulation",
        _COUNTERS_PACKAGE,
        regex=(
            r"(?:remove|move) (?:a|one|any number of|x|\d+) "
            r"(?:\+1/\+1|-1/-1) counters?|(?:remove|move) "
            r"(?:a|one|any number of|x|\d+) [^.]{0,20}?"
            r"(?:\+1/\+1|-1/-1) counters?"
        ),
        # Serve rides the lane (2026-10-18): regex missed 'Remove all/two +1/+1
        # counters' costs (Experiment One)
        serve_idents=frozenset({"counter_manipulation|you|"}),
    ),
    # ADR-0027 β: counter_distribute's SWEEP_DETECTORS row was deleted (detection moved
    # to the Card IR — the MassEach structural arm + narrowed mirror). The serve keeps a
    # board-wide regex via regex= (the strangler pattern), DROPPING the deleted regex's
    # plain self-enters arm (a self-grower doesn't spread) and ADDING the tribal-mass
    # "each <tribe> you control" form the structural arm catches via PutCounterAll.
    ("counter_distribute", "you"): _sweep_spec_with_extras(
        "counter_distribute",
        _COUNTERS_PACKAGE,
        regex=COUNTER_DISTRIBUTE_SERVE_REGEX,
        # Serve rides the lane (2026-10-18): regex missed typed-subject distributes ('on
        # each Vampire': Edgar Markov)
        serve_idents=frozenset({"counter_distribute|you|"}),
    ),
    # ADR-0027 tranche2-B: counter_place_trigger's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_added trigger event). The regex
    # stays on the search side; the serve rides the lane, which reads
    # granted triggers (Cursed Wombat, Danny Pink) and your placement on a creature
    # you don't control (Kros, Generous Patron).
    ("counter_place_trigger", "you"): _sweep_spec_with_extras(
        "counter_place_trigger",
        _COUNTERS_PACKAGE,
        regex=(
            r"whenever (?:you put|.*put) (?:one or more )?\+1/\+1 counters? on"
            r"|whenever one or more \+1/\+1 counters? (?:are|is) put on"
            r"|whenever you put (?:a|one or more|two|\d+) [^.]*counters? on"
            r"|whenever (?:a|one or more) [^.]*counters? (?:is|are) put on"
        ),
        serve_idents=frozenset({"counter_place_trigger|you|"}),
    ),
    # ADR-0027 tranche2-C: keyword_counter's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR); reuse the shared KEYWORD_COUNTER_REGEX for the serve pool.
    ("keyword_counter", "you"): _sweep_spec_with_extras(
        "keyword_counter",
        _COUNTERS_PACKAGE,
        regex=KEYWORD_COUNTER_REGEX,
        # Serve rides the lane (2026-10-18): regex missed choice-of-counter + double-
        # strike counters (Heightened Reflexes)
        serve_idents=frozenset({"keyword_counter|any|"}),
    ),
    # ADR-0027 tranche2-B-3: spell_keyword_grant / target_player_draws had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — the whole
    # cast_with_keyword category, and a draw effect with scope=='any'), so each spec is
    # hand-registered: the search fragment is the old regex (a shared _sweep_detectors
    # constant), the serve is the lane's ident.
    ("spell_keyword_grant", "you"): _spec(
        *SWEEP_LABELS["spell_keyword_grant"],
        {"oracle": SPELL_KEYWORD_GRANT_REGEX},
        # The lane reads grants the fixed keyword list missed (flash, rebound,
        # flashback, storm on a next spell — Cast Through Time, Dark Apostle); Wicker
        # Picker (an Un-card) drops out.
        None,
        serve_idents=frozenset({"spell_keyword_grant|you|"}),
    ),
    # ADR-0027: flash_grant's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a cast_with_keyword{flash} static + the byte-identical FLASH_GRANT_REGEX
    # kept mirror). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing the deleted regex (now the shared
    # FLASH_GRANT_REGEX constant) so the served flash-enabler pool never drifts.
    ("flash_grant", "you"): _spec(
        *SWEEP_LABELS["flash_grant"],
        {"oracle": FLASH_GRANT_REGEX},
        FLASH_GRANT_REGEX,
    ),
    ("target_player_draws", "any"): _spec(
        *SWEEP_LABELS["target_player_draws"],
        {"oracle": TARGET_PLAYER_DRAWS_REGEX},
        # The lane serves "draws X cards" and "its controller draws" (Braingeyser, Blue
        # Sun's Zenith) beyond the regex's "draws a card".
        None,
        serve_idents=frozenset({"target_player_draws|any|"}),
    ),
    # ADR-0027: group_hug_draw's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a `draw` effect with scope=='each', plus a byte-identical kept word
    # mirror for the 4 cards phase under-structures). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex (now the shared GROUP_HUG_DRAW_REGEX constant)
    # so the served group-hug pool never drifts.
    ("group_hug_draw", "each"): _spec(
        *SWEEP_LABELS["group_hug_draw"],
        {"oracle": GROUP_HUG_DRAW_REGEX},
        # Serve rides the lane (2026-10-18): regex missed the wheel idiom 'each player
        # ... then draws seven' (Timetwister)
        None,
        serve_idents=frozenset({"group_hug_draw|each|"}),
    ),
    # ADR-0027: dies_recursion's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — the undying/persist keyword bearers via _IR_KEYWORD_MAP plus a
    # byte-identical DIES_RECURSION_REGEX kept word mirror for the bare dies-return
    # grants / keyword-less granters). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex (now the shared DIES_RECURSION_REGEX constant) so the served
    # dies-recursion pool never drifts. CR 700.4 / 603.6c.
    ("dies_recursion", "you"): _spec(
        *SWEEP_LABELS["dies_recursion"],
        {"oracle": DIES_RECURSION_REGEX},
        # Serve rides the lane (2026-10-18): regex missed dies-return Auras/Equipment
        # (Gift of Immortality); served 'Undying' names
        None,
        serve_idents=frozenset({"dies_recursion|you|"}),
    ),
    # A card that brings itself back for another use (lanes.card_advantage.
    # recurs_itself): a grind deck running Bloodghast or Gravecrawler wants more of
    # the threats that don't stay dead. Search and serve both ride the key (the
    # ``self-recurring`` preset).
    ("self_recurring", "you"): _spec(
        "Self-recursion",
        "cards that come back for another use — from the graveyard, by re-"
        "suspending, or by returning to your hand",
        {"preset_names": ("self-recurring",)},
        None,
        serve_idents=frozenset({"self_recurring|you|"}),
    ),
    # Task #19 SPLIT — named_synergy (the named-card SYNERGY half of the old
    # named_permanent lane). Detection reads phase's typed ``Named`` reference to a
    # permanent (``lanes._named_synergy``), the clauses phase parks riding the
    # ``named_synergy_parked_reference`` ledger row. Hand-registered (scope "you"): the
    # search fragment is NAMED_PERMANENT_REGEX, the serve is the lane's ident.
    # SWEEP_LABELS keeps the human label.
    ("named_synergy", "you"): _spec(
        *SWEEP_LABELS["named_synergy"],
        {"oracle": NAMED_PERMANENT_REGEX},
        # Gains the "for each creature named" payoffs (Plague Rats, Shield of Kaldra).
        # Legend makers ("if you don't control a creature named X", Rufus Shinra) and
        # Seven Dwarves are lane gaps.
        None,
        serve_idents=frozenset({"named_synergy|you|"}),
    ),
    # Task #19 SPLIT — copy_limit (the COPY-LIMIT half, CR 100.2a). Detection is
    # STRUCTURAL (the IR `many_copies` field, read in crosswalk_signals.py), but
    # the SERVE pool stays oracle-defined: a copy-limit deck wants MORE cards
    # sharing the relaxed name + go-wide-on-one-name payoffs, found by the
    # COPY_LIMIT_REGEX scan ("A deck can have any number of / up to N cards
    # named X"). Scope "you". CR 100.2a.
    ("copy_limit", "you"): _spec(
        *SWEEP_LABELS["copy_limit"],
        {"oracle": COPY_LIMIT_REGEX},
        # Serve rides the lane (2026-10-18): regex and lane served the same 13 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"copy_limit|you|"}),
    ),
    # ADR-0027: topdeck_stack's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a STRUCTURAL arm over phase's `topdeck_stack` Effect + a kept word
    # mirror). Hand-registered (scope "you"): the search fragment is the pinned
    # TOPDECK_STACK_SWEEP_REGEX, the serve is the lane's ident. SWEEP_LABELS keeps the
    # human label. CR 401.4.
    ("topdeck_stack", "you"): _spec(
        *SWEEP_LABELS["topdeck_stack"],
        {"oracle": TOPDECK_STACK_SWEEP_REGEX},
        # The lane adds graveyard-to-top (Academy Ruins, Reclaim) and top-of-library
        # play engines (Future Sight); surveil's reminder text, all the regex's extras,
        # is noise.
        None,
        serve_idents=frozenset({"topdeck_stack|you|"}),
    ),
    # ADR-0027 (q2-D3): noncreature_cast_punish's SWEEP_DETECTORS row is deleted
    # (detection moved to the Card IR — a cast_spell trigger scope=='opp' over a
    # noncreature subject, plus a kept word mirror for the symmetric "a player casts"
    # half). Hand-registered: the search fragment is the deleted regex, the serve is the
    # lane's ident. SWEEP_LABELS still carries the human label.
    ("noncreature_cast_punish", "any"): _spec(
        *SWEEP_LABELS["noncreature_cast_punish"],
        {"oracle": NONCREATURE_CAST_PUNISH_REGEX},
        # Gains the "first noncreature spell each turn" punishers (Esper Sentinel).
        # Casts that reward or copy (Golem's Heart, Hive Mind) are out; In the Eye of
        # Chaos is a lane gap.
        None,
        serve_idents=frozenset({"noncreature_cast_punish|any|"}),
    ),
    # ADR-0027 β: global_ability_grant's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the board_grant + counter_kind="grant_ability" marker read by
    # crosswalk_signals.py). The SERVE pool stays oracle-defined, so hand-register the
    # spec the sweep auto-register loop used to build (scope "any", the deleted SWEEP
    # row's scope), reusing the EXACT deleted regex (pinned as
    # GLOBAL_ABILITY_GRANT_REGEX) so the serve never drifts. SWEEP_LABELS keeps label.
    ("global_ability_grant", "any"): _spec(
        *SWEEP_LABELS["global_ability_grant"],
        {"oracle": GLOBAL_ABILITY_GRANT_REGEX},
        # Serve rides the lane (2026-10-18): regex missed quoted grants to a
        # typed/qualified subject (Esika, Rishkar)
        None,
        serve_idents=frozenset({"global_ability_grant|any|"}),
    ),
    # ADR-0027 β: keyword_grant_target's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the single_target_grant marker read by crosswalk_signals.py).
    # The SERVE pool stays oracle-defined (the creatures worth granting evasion
    # /protection to), so hand-register the spec the sweep loop built (scope
    # "you", the deleted SWEEP row's scope), reusing the EXACT deleted regex (pinned as
    # KEYWORD_GRANT_TARGET_REGEX) so the serve never drifts. SWEEP_LABELS keeps label.
    ("keyword_grant_target", "you"): _spec(
        *SWEEP_LABELS["keyword_grant_target"],
        {"oracle": KEYWORD_GRANT_TARGET_REGEX},
        # Serve rides the lane (2026-10-18): regex missed multi-target / attacking-
        # creature grants (Aerial Guide, Aim High)
        None,
        serve_idents=frozenset({"keyword_grant_target|you|"}),
    ),
    # ADR-0027 Cluster D: protection_grant's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR — the structural protective-keyword grant arm in
    # crosswalk_signals.py UNION a byte-identical PROTECTION_GRANT_REGEX kept
    # mirror). The SERVE pool stays oracle-defined (the creatures worth
    # protecting with hexproof/protection), so hand-register the spec the
    # sweep auto-register loop used to build (scope "you", the deleted SWEEP
    # row's scope), reusing the EXACT deleted regex (pinned as
    # PROTECTION_GRANT_REGEX) so the serve never drifts. SWEEP_LABELS
    # keeps the human label.
    ("protection_grant", "you"): _spec(
        *SWEEP_LABELS["protection_grant"],
        {"oracle": PROTECTION_GRANT_REGEX},
        PROTECTION_GRANT_REGEX,
    ),
    # ADR-0027 β: debuff_makers's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the negative-pump (factor<0) / non-self m1m1 structural arm + a
    # byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool stays oracle-defined,
    # so hand-register the spec the sweep auto-register loop used to build (scope "any",
    # the deleted SWEEP row's scope), reusing the EXACT deleted regex (pinned as
    # DEBUFF_SWEEP_REGEX) so the serve pool never drifts. SWEEP_LABELS keeps the label.
    #
    # Serve on the lane's idents (the regex stays the search): the lane reads
    # the variable and one-sided shrinks, the static "-X/-X" Auras and board
    # shrinks, granted shrink abilities and one-shot base-P/T sets the regex
    # served, and leaves out what it over-served — your own -1/-1 counters
    # (blight, CR 701.68a), a creature shrinking itself, flanking reminder text.
    ("debuff_makers", "any"): _spec(
        *SWEEP_LABELS["debuff_makers"],
        {"oracle": DEBUFF_SWEEP_REGEX},
        None,
        serve_idents=frozenset({"debuff_makers|any|", "debuff_makers|you|"}),
    ),
    # ADR-0027 β: pump_makers's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a kept _IR_KEPT_DETECTORS mirror; the lane is unstructurable, so no
    # structural arm). Hand-registered (scope "you"): the search fragment is
    # PUMP_MATTERS_REGEX (== _PUMP_ORACLE, which the _PUMP_EXTRA SubAvenue reuses), the
    # serve is the lane's ident. SWEEP_LABELS keeps the label.
    ("pump_makers", "you"): _spec(
        *SWEEP_LABELS["pump_makers"],
        {"oracle": PUMP_MATTERS_REGEX},
        # The lane reads every targeted pump the regex did, plus anaphoric "it gets"
        # (Spidery Grasp), team pumps (Surge to Victory) and attack-trigger pumps
        # (Fervent Champion).
        None,
        serve_idents=frozenset({"pump_makers|you|"}),
    ),
    # ADR-0027 β: free_cast's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR via a kept _FREE_CAST_MIRROR; the IR has no 'free' flag, so no structural
    # arm). Hand-registered (scope "you"): the search fragment is FREE_CAST_REGEX, the
    # serve is the lanes' idents. SWEEP_LABELS keeps the label.
    ("free_cast", "you"): _spec(
        *SWEEP_LABELS["free_cast"],
        {"oracle": FREE_CAST_REGEX},
        # The free casts plus the cascade (granted too: Maelstrom Nexus, Yidris) and
        # discover makers. Keyword reminders that recast the card itself (plot, rebound,
        # suspend, cipher, ripple) are self-recasts, not the bombs this avenue casts
        # free.
        None,
        serve_idents=frozenset(
            {
                "free_cast|you|",
                "cascade_makers|you|",
                "cascade_matters|you|",
                "discover_makers|you|",
            }
        ),
    ),
    # ADR-0027 β: tribe_damage_trigger's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build (scope "you", the deleted SWEEP row's scope), reusing the shared
    # TRIBE_DAMAGE_TRIGGER_REGEX so the serve pool never drifts. SWEEP_LABELS still
    # carries the human label.
    ("tribe_damage_trigger", "you"): _spec(
        *SWEEP_LABELS["tribe_damage_trigger"],
        {"oracle": TRIBE_DAMAGE_TRIGGER_REGEX},
        # Serve rides the lane (2026-10-18): regex missed keyword/counter subjects
        # ('with deathtouch': Fynn), served Quest for Pure Flame
        None,
        serve_idents=frozenset({"tribe_damage_trigger|you|"}),
    ),
    # ADR-0027 β: timing_control's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build (scope "any", the deleted SWEEP row's scope), reusing the deleted regex so
    # the serve pool never drifts. SWEEP_LABELS still carries the human label.
    ("timing_control", "any"): _spec(
        *SWEEP_LABELS["timing_control"],
        {
            "oracle": (
                r"cast spells (?:and activate abilities )?only during their own"
                r"|spells? only any time they could cast a sorcery"
                r"|can cast spells only"
            )
        },
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"timing_control|any|"}),
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B): sacrifice_protection / secret_writedown had
    # their SWEEP_DETECTORS rows deleted (detection moved to the Card IR — kept_detector
    # word mirrors), so the sweep auto-register loop no longer builds their serve. Hand-
    # register each at scope "you", reusing the deleted regex as both search and serve
    # so the SERVE pool never drifts. SWEEP_LABELS still carries the human label.
    # secret_writedown reuses the NARROWED mirror (without the companion "your
    # sideboard" arm) so its serve no longer surfaces the companion-reminder cards
    # companion_keyword owns.
    ("sacrifice_protection", "you"): _spec(
        *SWEEP_LABELS["sacrifice_protection"],
        {"oracle": r"can't cause you to sacrifice|can't be sacrificed"},
        # Serve rides the lane (2026-10-18): regex and lane served the same 11 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"sacrifice_protection|you|"}),
    ),
    ("secret_writedown", "you"): _spec(
        *SWEEP_LABELS["secret_writedown"],
        {
            "oracle": (
                r"secretly (?:write|choose|name)"
                r"|before the game begins[^.]*(?:write|name|choose)"
                r"|from outside the game"
            )
        },
        r"secretly (?:write|choose|name)"
        r"|before the game begins[^.]*(?:write|name|choose)"
        r"|from outside the game",
    ),
    # ADR-0027 tranche2-B (t2b3-B): opponent_counter_grant's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR — a detrimental bounty/stun counter on an
    # opponent's permanent). Hand-registered at the "opponents" scope it fires at: the
    # search fragment is OPPONENT_COUNTER_GRANT_REGEX, the serve is the lane's ident.
    ("opponent_counter_grant", "opponents"): _spec(
        *SWEEP_LABELS["opponent_counter_grant"],
        {"oracle": OPPONENT_COUNTER_GRANT_REGEX},
        # The lane adds stun counters on an opponent's creature (Freeze in Place) and
        # -1/-1 counters on theirs (Archfiend of Ifnir).
        None,
        serve_idents=frozenset({"opponent_counter_grant|opponents|"}),
    ),
    # ADR-0027 tranche2-B: counter_replace_bonus's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_doubling replacement category).
    # The serve keeps the old regex via regex= (strangler pattern).
    ("counter_replace_bonus", "you"): _sweep_spec_with_extras(
        "counter_replace_bonus",
        _COUNTERS_PACKAGE,
        regex=(
            r"that many plus (?:one|two|\d+) [^.]*counters? are put"
            r"|put that many plus"
            r"|if (?:one or more )?\+1/\+1 counters? would be put on"
            r"|one or more counters? would be (?:put|placed)"
            r"[^.]*(?:that many plus|twice that many)"
        ),
        # Serve rides the lane (2026-10-18): regex missed the 'twice that many' doublers
        # (Doubling Season, Vorinclex)
        serve_idents=frozenset({"counter_replace_bonus|you|"}),
    ),
    # ADR-0027: counter_move's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — phase's MoveCounters effect). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec reusing the deleted regex as the
    # serve pattern, keeping the counter-doubler fan-out package.
    ("counter_move", "you"): _spec(
        *SWEEP_LABELS["counter_move"],
        {
            "oracle": (
                r"\bmove (?:a|one|that|any number of|all|x|\d+|one or more) "
                r"[^.]{0,30}?counters?\b (?:from|onto|to)"
            )
        },
        # Serve rides the lane (2026-10-18): regex missed 'put its counters on target
        # creature' (Essence Channeler)
        None,
        serve_idents=frozenset({"counter_move|you|"}),
        extras=_COUNTERS_PACKAGE,
    ),
    # Beginning-of-combat / attack-buff commanders are combat decks — surface the gear
    # and keyword-anthems that grow their attackers. ADR-0027 Cluster D: combat_buff_
    # engine migrated to the IR (its SWEEP_DETECTORS row is deleted), so the search
    # keeps the pinned COMBAT_BUFF_ENGINE_SWEEP_REGEX; the serve is the lane's ident.
    ("combat_buff_engine", "you"): _sweep_spec_with_extras(
        "combat_buff_engine",
        (_COMBAT_SUPPORT_EXTRA,),
        regex=COMBAT_BUFF_ENGINE_SWEEP_REGEX,
        # Gains beginning-of-combat counters and buffs (Nessian Hornbeetle, Kimahri).
        # Block / becomes-blocked self pumps and flanking / exalted reminders drop out.
        serve_idents=frozenset({"combat_buff_engine|you|"}),
    ),
    # A "becomes blocked" payoff (General Marhault: +3/+3 for each creature blocking it)
    # wants Lure effects — forcing every able creature to block maxes the per-blocker
    # bonus. ADR-0027 Cluster D: the SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the structural becomes_blocked arm UNION a byte-identical
    # BLOCKED_MATTERS_REGEX kept mirror), so pass the pinned regex explicitly (the
    # auto-register loop no longer reaches the deleted row); the serve pool is the same.
    ("blocked_matters", "you"): _sweep_spec_with_extras(
        "blocked_matters", (_LURE_EXTRA,), regex=BLOCKED_MATTERS_REGEX
    ),
    # Heroic / target-matters: the payoff fires when YOU target your own creature, so
    # surface the single-target pumps/protection that do it (Gods Willing, Brute Force).
    ("targeting_matters", "any"): _spec(
        *SWEEP_LABELS["targeting_matters"],
        {"oracle": _TARGETING_SWEEP_REGEX},
        # Ward's reminder text ("becomes the target of a spell or ability an opponent
        # controls", CR 702.21a) is out: ward is protection, not a heroic payoff.
        None,
        serve_idents=frozenset({"targeting_matters|any|"}),
        extras=(_TARGETED_BUFF_EXTRA,),
    ),
    # Green creature-cast commanders (Gwenna, Runadi, Eshki) ramp into fatties: surface
    # creature cost reducers (Goreclaw) and genuine bombs (Ghalta — power_min=6 keeps it
    # to true fatties, not every 5/5 the trigger would also accept).
    # ADR-0027: creature_cast_trigger migrated to the Card IR (a cast_spell trigger with
    # a Creature subject + an effect-raw / face-oracle "whenever/when [player] casts a …
    # creature spell" scan). Its SWEEP_DETECTORS row is deleted; the serve keeps the old
    # regex (passed explicitly so the spec no longer depends on the deleted row).
    ("creature_cast_trigger", "you"): _sweep_spec_with_extras(
        "creature_cast_trigger",
        (_CREATURE_COST_EXTRA, _SELF_BOUNCE_EXTRA),
        serve_power_min=6,
        regex=(
            r"whenever (?:you|a player|an opponent|each opponent) casts? a creature "
            r"spell|whenever (?:a|another) creature spell is cast"
        ),
        # Serve rides the lane (2026-10-18): regex missed typed creature-spell triggers
        # (Emrakul's Influence, Donal)
        serve_idents=frozenset({"creature_cast_trigger|any|"}),
    ),
    # Toughness-as-power (Doran, Arcades) decks want bodies whose TOUGHNESS beats
    # their power, and Walls: a creature assigns combat damage equal to its power
    # (CR 510.1a), Doran swaps in toughness, so a 6/6 gains nothing. (Damage
    # reflection keeps toughness >= 4 below: a big body survives to reflect.)
    # ADR-0027 β: the serve keeps the deleted regex producers via the pinned
    # TOUGHNESS_COMBAT_REGEX constant.
    ("toughness_combat", "you"): _sweep_spec_with_extras(
        "toughness_combat",
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
        regex=TOUGHNESS_COMBAT_REGEX,
        # Serve rides the lane (2026-10-18): regex and lane agree but for Loxodon
        # Lifechanter's total-toughness read
        serve_idents=frozenset({"toughness_combat|you|"}),
    ),
    # ADR-0027 β: ability_copy migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds its spec). Hand-
    # registered: the search fragment is the pinned ABILITY_COPY_REGEX, the serve is the
    # lane's ident. SWEEP_LABELS still carries the label.
    ("ability_copy", "you"): _sweep_spec_with_extras(
        "ability_copy",
        regex=ABILITY_COPY_REGEX,
        # Demonstrate's reminder ("you may copy it") is a spell copy (CR 702.144a), not
        # an ability copy, so it is out.
        serve_idents=frozenset({"ability_copy|you|"}),
    ),
    # ADR-0027: damage_reflect's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the on-card damage_received+damage co-occurrence + a damage_reflect
    # marker for the quoted reflection grant). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec reusing the deleted regex as the serve
    # pattern, keeping the high-toughness/defender serve dimensions.
    ("damage_reflect", "you"): _spec(
        *SWEEP_LABELS["damage_reflect"],
        {
            "oracle": (
                r"whenever [^.]*is dealt damage, (?:it|this creature) "
                r"deals that much damage"
            )
        },
        # Serve rides the lane (2026-10-18): regex missed enrage + Aura/global
        # reflectors (Repercussion, Arcbond)
        None,
        serve_idents=frozenset({"damage_reflect|you|"}),
        serve_toughness_min=4,
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
    ),
    # Power doublers (Rhonas, Mr. Orfeo) want high BASE power to double; power-as-damage
    # pingers/fighters (Itzquinth) want high power for more damage. Both lanes credit
    # the fat bodies they exploit (Ghalta / Worldspine Wurm), not just the engine cards.
    # ADR-0027: power_double migrated to the Card IR (a pump/pump_target effect whose
    # raw carries the "double … power" word-mirror); its SWEEP_DETECTORS row is deleted,
    # so the serve passes the deleted regex explicitly to keep the serve pool.
    ("power_double", "you"): _sweep_spec_with_extras(
        "power_double",
        (_POWER_FLING_EXTRA,),
        serve_power_min=5,
        regex=(
            r"double the power|doubles? the power and toughness"
            r"|power(?: and toughness)? (?:is|are) doubled|double [A-Z][a-z']+ power"
            r"|doubles? [^.]*power until end of turn"
        ),
        # Serve rides the lane (2026-10-18): regex missed 'double target creature's
        # power' (Exponential Growth)
        serve_idents=frozenset({"power_double|you|"}),
    ),
    # Firebreathing / variable-P/T decks pump power, then fling it for damage. ADR-0027:
    # self_pump migrated to the Card IR (its SWEEP_DETECTORS row is deleted); the search
    # keeps the old regex via the `regex=` arg, the serve is the lane's ident.
    ("self_pump", "you"): _sweep_spec_with_extras(
        "self_pump",
        (_POWER_FLING_EXTRA,),
        regex=_SELF_PUMP_SWEEP_REGEX,
        # Gains +N/-N and sacrifice-fed self pumps (Mistwalker). Pumps of a target
        # creature are noise; granted firebreathing (Shiv's Embrace, Kusari-Gama) is a
        # lane gap.
        serve_idents=frozenset({"self_pump|you|"}),
    ),
    # ADR-0027: tapper_engine migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a `tap` Effect with a target subject + a "doesn't
    # untap" restriction raw), so hand-register the spec the sweep loop used to build,
    # reusing the deleted regex as both search and serve.
    # Serve on the lane's ident once it reads granted tap abilities and
    # triggers (an Equipment's "{T}: Tap target creature"); the regex stays the
    # search.
    ("tapper_engine", "any"): _spec(
        *SWEEP_LABELS["tapper_engine"],
        {"oracle": _TAPPER_ENGINE_SWEEP_REGEX},
        None,
        serve_idents=frozenset({"tapper_engine|any|"}),
    ),
    # ADR-0027: count_anthem migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a team +N/+N pump scaling with a board count over a
    # generic creature Filter you control), so hand-register the spec the sweep loop
    # used to build: the search fragment is the deleted regex, the serve is the lane's
    # ident.
    ("count_anthem", "you"): _spec(
        *SWEEP_LABELS["count_anthem"],
        {"oracle": _COUNT_ANTHEM_SWEEP_REGEX},
        # Gains X-valued team pumps (Craterhoof Behemoth, Jodah). Tribe-subject count
        # anthems (Armament Master, Joraga Warcaller) are a lane gap.
        None,
        serve_idents=frozenset({"count_anthem|you|"}),
    ),
    # ADR-0027 #24g: scaling_pump migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection is the structural _is_scaling_count `pump` arm reading the
    # supplement-recovered op=count operand; the kept word mirror is DELETED too), so
    # the auto-register loop no longer builds this spec. Hand-registered: the pinned
    # regex is the search fragment only (NOT a detection path), the serve is the lane's
    # ident.
    ("scaling_pump", "you"): _spec(
        *SWEEP_LABELS["scaling_pump"],
        {"oracle": SCALING_PUMP_SWEEP_REGEX},
        # Adds the X-valued scalers (Craterhoof's "where X is"). Lane gaps: Dark Matter
        # Manipulator, Ellivere, Vren.
        None,
        serve_idents=frozenset({"scaling_pump|you|"}),
    ),
    # ADR-0027 Cluster C: base_pt_set migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to the structural cat=="base_pt_set" arm UNION the
    # carved BASE_PT_SET_REGEX kept word mirror), so the auto-register loop no longer
    # builds this spec. Hand-register the spec the sweep loop used to build, reusing the
    # CARVED regex (base-P/T-set-only, not the 4-mechanic umbrella) as both search and
    # serve — the serve pool is set-P/T effects + the creatures that exploit a set base
    # P/T. Scope 'any' (the deleted SWEEP row's scope).
    ("base_pt_set", "any"): _spec(
        *SWEEP_LABELS["base_pt_set"],
        {"oracle": BASE_PT_SET_REGEX},
        # Serve rides the lane (2026-10-18): regex missed X-valued sets (Biomass
        # Mutation, Mirror Entity)
        None,
        serve_idents=frozenset({"base_pt_set|any|", "base_power_matters|you|"}),
    ),
    # ADR-0027: tribal_etb_multi migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to an etb trigger with a creature-subtype subject), so
    # hand-register the spec the sweep loop used to build: the deleted regex is the
    # search fragment, the serve is the lane's ident.
    ("tribal_etb_multi", "you"): _spec(
        *SWEEP_LABELS["tribal_etb_multi"],
        {"oracle": _TRIBAL_ETB_MULTI_SWEEP_REGEX},
        # The lane reads every typed "whenever this or another <type> enters" (Lathliss,
        # Chasm Guide); typeless ones (Flayer of the Hatebound) are out.
        None,
        serve_idents=frozenset({"tribal_etb_multi|you|"}),
    ),
    # ADR-0027: typed_enters_punish migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to an etb trigger whose consequence burns the
    # opponents), so hand-register the spec the sweep loop used to build: the deleted
    # regex is the search fragment, the serve is the lane's ident.
    ("typed_enters_punish", "you"): _spec(
        *SWEEP_LABELS["typed_enters_punish"],
        {"oracle": _TYPED_ENTERS_PUNISH_SWEEP_REGEX},
        # The lane adds Impact Tremors, landfall and artifact-enters pingers.
        None,
        serve_idents=frozenset({"typed_enters_punish|you|"}),
    ),
    # Force-attack / goad commander (Kratos) wants extra combats to swing again.
    # ADR-0027: forced_attack migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted), so pass the deleted SWEEP regex explicitly as the search fragment (the
    # IR arm + DET kept mirror drive the firing); the serve is the lanes' idents.
    ("forced_attack", "you"): _sweep_spec_with_extras(
        "forced_attack",
        (_EXTRA_COMBAT_EXTRA, _COMBAT_SUPPORT_EXTRA),
        regex=FORCED_ATTACK_SWEEP_REGEX,
        # Forced attacks plus goad (the regex read goad's reminder); gains "attacks this
        # turn if able" (Goblin Diplomats, Incite).
        serve_idents=frozenset(
            {"forced_attack|any|", "forced_attack|you|", "goad_makers|opponents|"}
        ),
    ),
    # Donate commander (Jon Irenicus, Harmless Offering) wants drawback creatures to
    # hand to opponents for the downside.
    # ADR-0027: donate_makers had its SWEEP_DETECTORS row deleted (detection moved to
    # the Card IR — a gain_control raw-recipient discriminator). The serve pool stays
    # oracle-defined, so pass the deleted regex explicitly.
    ("donate_makers", "you"): _sweep_spec_with_extras(
        "donate_makers",
        (_DRAWBACK_EXTRA, _FORCE_FEED_EXTRA),
        regex=(
            r"(?:target opponent|another player|target player|that player"
            r"|each opponent|each other player) gains control of[^.]*you control"
            r"|(?:target opponent|another player|target player|that player) "
            r"gains control of"
        ),
        # Serve rides the lane (2026-10-18): regex missed 'may have that player gain
        # control' donates (Assault Suit)
        serve_idents=frozenset({"donate_makers|you|"}),
    ),
    # ADR-0027 t2b4-C: damage_to_you_punish's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — an _IR_KEPT_DETECTORS word mirror; phase drops
    # the opp-source filter and the "to you" recipient). The serve was auto-registered
    # from the SWEEP row (scope "opponents"), so hand-register it with the old regex.
    ("damage_to_you_punish", "opponents"): _sweep_spec_with_extras(
        "damage_to_you_punish",
        regex=(
            r"whenever a source an opponent controls deals damage to you"
            r"|whenever (?:a|an) (?:opponent|source[^.]*opponent)[^.]*deals "
            r"(?:combat )?damage to you"
        ),
        # Serve rides the lane (2026-10-18): regex missed 'creatures an opponent
        # controls deal combat damage to you' (Norn's Decree)
        serve_idents=frozenset({"damage_to_you_punish|opponents|"}),
    ),
    # ADR-0027 t2b5-A: the SWEEP_DETECTORS rows for draft_spellbook / each_mode_player
    # / flip_self / miracle_grant were deleted (detection moved to the Card IR — each is
    # a signals._IR_KEPT_DETECTORS word mirror). Their serves were auto-registered from
    # the SWEEP rows, so hand-register each with the old regex + scope so the
    # auto-register loop's missing-row lookup never runs and the serve never drifts.
    ("draft_spellbook", "you"): _sweep_spec_with_extras(
        "draft_spellbook",
        regex=r"\bdraft a card\b|spellbook",
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        serve_idents=frozenset({"draft_spellbook|you|"}),
    ),
    ("each_mode_player", "each"): _sweep_spec_with_extras(
        "each_mode_player",
        regex=r"each mode must target a different player",
        # Serve rides the lane (2026-10-18): regex and lane served the same seven cards;
        # the lane is now the one source
        serve_idents=frozenset({"each_mode_player|each|"}),
    ),
    ("flip_self", "you"): _sweep_spec_with_extras(
        "flip_self",
        regex=r"\bflip this creature\b",
        # Adds flips worded "flip it" / "flip <name>" (the ki-counter Kamigawa flips,
        # Erayo); Chaos Orb and Falling Star are dexterity flips.
        serve_idents=frozenset({"flip_self|you|"}),
    ),
    ("miracle_grant", "you"): _sweep_spec_with_extras(
        "miracle_grant",
        regex=r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle",
        # Serve rides the lane (2026-10-18): regex and lane served the same three cards;
        # the lane is now the one source
        serve_idents=frozenset({"miracle_grant|you|"}),
    ),
    # Legend-rule-off commander (Brothers Yamazaki) wants self-copy effects to run
    # multiple copies of itself. ADR-0027 β: legend_rule_off's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR via a byte-identical _IR_KEPT_DETECTORS
    # mirror), so pass the deleted regex explicitly (the serve pool stays oracle-
    # defined and never drifts from the deleted SWEEP row).
    ("legend_rule_off", "you"): _sweep_spec_with_extras(
        "legend_rule_off",
        (_COPY_EXTRA,),
        regex=r"the .legend rule. doesn't apply",
        # Serve rides the lane (2026-10-18): regex and lane served the same ten cards;
        # the lane is now the one source
        serve_idents=frozenset({"legend_rule_off|you|"}),
    ),
    # A self-blinking commander (Norin) re-enters constantly, firing "whenever a
    # creature enters" payoffs (Impact Tremors) and doublers (Panharmonicon).
    # ADR-0027 t2b4-C: self_blink's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the name-aware fulltext detector + the per-clause
    # _SELF_BLINK_SWEEP_RE mirror). The search fragment is the deleted regex; the serve
    # is the lanes' idents.
    ("self_blink", "you"): _sweep_spec_with_extras(
        "self_blink",
        (_ETB_PAYOFF_EXTRA, _ETB_VALUE_EXTRA, _ETB_DOUBLER_EXTRA),
        regex=(
            r"exile (?:up to one |another |a |target )?(?:other )?target "
            r"(?:creature|permanent)[^.]*\.?\s*return (?:that|those|it|the[^.]*)"
            r"[^.]*to the battlefield"
            r"|exile (?:any number of|all|each)[^.]*creatures[^.]*return"
            r"|exile [A-Z][a-z']+\.\s*return (?:it|that card|them)[^.]*"
            r"to the battlefield"
        ),
    ),
    # A repeatable-wrath commander (Mageta) wants to rebuild after the sweep:
    # reanimation (Breath of Life) plus indestructible bombs (Zetalpa) that survive it.
    # ADR-0027: mass_removal migrated to the Card IR (detection moved to the structural
    # counter_kind=='all' destroy/exile/damage + negative-pump arms; its SWEEP_DETECTORS
    # row is deleted). The SERVE pool stays oracle-defined (board wipes + the
    # rebuild-after-wrath package), so pass the deleted regex inline so the
    # auto-register loop's missing-row lookup never runs.
    ("mass_removal", "you"): _sweep_spec_with_extras(
        "mass_removal",
        (_REANIMATION_EXTRA, _BOARD_PROTECTION_EXTRA),
        serve_keywords=("indestructible",),
        regex=(
            "destroy all (?:other )?(?:nonland )?(?:permanents|creatures|artifacts"
            "|enchantments|other creatures)|deals? \\d+ damage to each (?:creature"
            "|nonlegendary creature|other creature)|exile all (?:creatures|permanents)"
            "|exile all (?:black|white|blue|red|green) creatures|all creatures get -\\d"
            "|destroy all [^.]*creatures except|destroy all other creatures"
        ),
        # Serve rides the lane (2026-10-18): regex served -N/-0 tricks (Ivory Charm),
        # missed typed/named wipes (Bile Blight)
        serve_idents=frozenset({"mass_removal|you|"}),
    ),
    # ADR-0027 β: variable_pt migrated to the Card IR (SWEEP row deleted); the search
    # keeps the deleted regex via the pinned VARIABLE_PT_SWEEP_REGEX constant, the serve
    # is the lane's ident.
    ("variable_pt", "you"): _sweep_spec_with_extras(
        "variable_pt",
        (_POWER_FLING_EXTRA,),
        regex=VARIABLE_PT_SWEEP_REGEX,
        # Gains power- or toughness-only CDAs (Anax). Lane gaps: animated or token CDAs
        # (Chimeric Mass, Svogthos) and pay-life P/T (Minion of the Wastes).
        serve_idents=frozenset({"variable_pt|any|"}),
    ),
    # ADR-0027 β: creature_ping migrated to the Card IR (SWEEP row deleted); the serve
    # keeps the deleted regex via the pinned CREATURE_PING_REGEX constant.
    ("creature_ping", "you"): _sweep_spec_with_extras(
        "creature_ping",
        (_DEATHTOUCH_GEAR_EXTRA,),
        serve_power_min=5,
        regex=CREATURE_PING_REGEX,
        # Serve rides the lane (2026-10-18): regex missed tap-and-bite + granted bites
        # (Abyssal Hunter, Burning Anger)
        serve_idents=frozenset({"creature_ping|you|"}),
    ),
    # Extra upkeep STEPS (Obeka, The Ninth Doctor): each added upkeep step is another
    # instance every "at the beginning of your/each upkeep" ability triggers in (CR
    # 500.7 / 503 / 603.2), so the whole upkeep-trigger pool IS the payoff package.
    # The narrow OPEN regex lives in the sweep detector; this hand-spec exists so the
    # auto-register doesn't bind the serve to that 4-card open regex — it serves the
    # broad upkeep-trigger pool instead. The lane opens for only the ~2 extra-upkeep
    # commanders, so the broad serve never floods an unrelated deck.
    ("extra_upkeep", "you"): _spec(
        "Extra upkeeps",
        "repeatable upkeep-trigger payoffs, multiplied by every added upkeep step",
        {"oracle": r"at the beginning of (?:your|each) upkeep"},
        r"at the beginning of (?:your|each) upkeep",
    ),
    # Extra end steps (Y'shtola Rhul): every "at the beginning of your/each end step"
    # payoff (Agent of Treachery, Chimil, the Inner Sun) re-triggers in each added end
    # step (CR 513). Same open-gated-narrow / serve-broad split as Extra upkeeps.
    ("extra_end_step", "you"): _spec(
        "Extra end steps",
        "end-step-trigger payoffs, multiplied by every added end step",
        {"oracle": r"at the beginning of (?:your|each) end step"},
        r"at the beginning of (?:your|each) end step",
    ),
    # Extra draw steps (opened by a beginning-phase grant, CR 501/504): "at the
    # beginning of your draw step" payoffs re-trigger in each added draw step.
    ("extra_draw_step", "you"): _spec(
        "Extra draw steps",
        "draw-step-trigger payoffs, multiplied by every added draw step",
        {"oracle": r"at the beginning of (?:your|each) draw step"},
        r"at the beginning of (?:your|each) draw step",
    ),
    # Deathtouch gear (Basilisk Collar) makes any ping / power-as-damage lethal — credit
    # it on the noncombat-damage and power-fling lanes too, not only the Burn lane.
    # ADR-0027: noncombat_damage_payoff migrated to the Card IR (SWEEP row deleted); the
    # serve keeps the deleted regex via the pinned NONCOMBAT_DAMAGE_PAYOFF_REGEX
    # constant.
    ("noncombat_damage_payoff", "you"): _sweep_spec_with_extras(
        "noncombat_damage_payoff",
        (_DEATHTOUCH_GEAR_EXTRA, _NONCOMBAT_BURN_EXTRA),
        regex=NONCOMBAT_DAMAGE_PAYOFF_REGEX,
        # Serve rides the lane (2026-10-18): regex and lane served the same 107 cards;
        # the lane is now the one source
        serve_idents=frozenset({"noncombat_damage_payoff|you|"}),
    ),
    # Power-as-damage / fling commander (Brion Stoutarm) wants big bodies as fling
    # fodder (power_min) plus the power-fling payoffs and deathtouch gear.
    # ADR-0027 β: damage_equal_power migrated to the Card IR (SWEEP row deleted); the
    # serve keeps the deleted regex via the pinned DAMAGE_EQUAL_POWER_REGEX constant.
    ("damage_equal_power", "you"): _sweep_spec_with_extras(
        "damage_equal_power",
        (_DEATHTOUCH_GEAR_EXTRA, _POWER_FLING_EXTRA),
        serve_power_min=6,
        regex=DAMAGE_EQUAL_POWER_REGEX,
        # Serve rides the lane (2026-10-18): regex missed bite spells phrased 'to each
        # other creature' (Chandra's Ignition)
        serve_idents=frozenset({"creature_ping|you|", "damage_equal_power|you|"}),
    ),
    # Repeatable "deals N damage to each creature" board pinger (Tibor, Pestilence,
    # Pyrohemia): deathtouch on the source makes each ping lethal (CR 702.2b) -- a
    # recurring one-sided board wipe. The lane's whole point IS that enabler, so it
    # serves the same gear the Burn/fling lanes do, via the shared constant.
    ("aoe_ping", "you"): _spec(
        "Deathtouch board sweep",
        "your recurring damage to each creature + deathtouch on the source = a "
        "repeatable one-sided wipe (CR 702.2b)",
        {"oracle": _DEATHTOUCH_GEAR_ORACLE},
        # The main serve is the repeatable each-creature pingers (Crypt Rats,
        # Pestilence, Tibor and Lumia); the deathtouch gear (Basilisk Collar) is the
        # shared Deathtouch enablers extra.
        None,
        serve_idents=frozenset({"aoe_ping|you|"}),
        extras=(_DEATHTOUCH_GEAR_EXTRA,),
    ),
    # Same archetype as spellcast_matters (a magecraft commander triggers off the same
    # instants/sorceries as a prowess one), so it shares the one _SPELLSLINGER_SPEC — a
    # commander firing both detectors now renders a single "Spellslinger" avenue, not
    # two near-identical lanes (Phase C). CR 207.2c: magecraft = the cast trigger.
    ("magecraft_matters", "you"): _SPELLSLINGER_SPEC,
    ("extra_combats", "you"): _spec(
        "Extra combats",
        "additional combat phases and the attackers to exploit them",
        {"oracle": r"additional combat phase|extra combat"},
        # Serve rides the lane (2026-10-18): regex and lane served the same 44 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"extra_combats|you|"}),
    ),
    ("extra_turns", "you"): _spec(
        "Extra turns",
        "additional-turn effects",
        {"oracle": r"extra turn|additional turn|take an extra"},
        # Serve rides the lane (2026-10-18): regex served the extra-turn haters ('skips
        # that turn instead': Stranglehold)
        None,
        serve_idents=frozenset({"extra_turns|you|"}),
    ),
}
