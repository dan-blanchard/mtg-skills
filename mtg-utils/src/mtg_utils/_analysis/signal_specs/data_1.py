"""Signal specs data slice 1/4: SPECS dict entries (lines 1749-3416 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

import re

from mtg_utils._analysis._sweep_detectors import (
    SWEEP_LABELS,
)
from mtg_utils._analysis.lanes.card_advantage import REANIMATED_SELF_RETURNS
from mtg_utils._analysis.signal_keys import STEP_TRIGGER_KEYS

from ._shared import (
    _BOARD_PROTECTION_EXTRA,
    _BOARD_WIPE_EXTRA,
    _CAST_FROM_GY_EXTRA,
    _CHOSEN_TYPE_IDENTS,
    _COMBAT_SUPPORT_EXTRA,
    _COPY_EXTRA,
    _COUNTER_DOUBLER_EXTRA,
    _COUNTER_KEYWORD_EXTRA,
    _COUNTER_RESILIENCE_EXTRA,
    _COUNTERS_PACKAGE,
    _CREATURE_COST_EXTRA,
    _DAMAGE_SOAK_EXTRA,
    _DEATH_DRAIN_EXTRA,
    _DEATH_PAYOFF_IDENTS,
    _DEATHTOUCH_GEAR_EXTRA,
    _DIES_RECURSION_EXTRA,
    _DRAWBACK_EXTRA,
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
    _LANDS_FROM_GRAVE_EXTRA,
    _LURE_EXTRA,
    _NONCOMBAT_BURN_EXTRA,
    _PILLOWFORT_EXTRA,
    _PLUS_ONE_SERVE_IDENTS,
    _POWER_FLING_EXTRA,
    _PROLIFERATE_EXTRA,
    _REANIMATION_EXTRA,
    _SAC_OUTLET_EXTRA,
    _SELF_BOUNCE_EXTRA,
    _SELF_RECUR_EXTRA,
    _SELF_SAC_CREATURE_EXTRA,
    _SPELLSLINGER_SPEC,
    _TARGETED_BUFF_EXTRA,
    _TEAM_PROTECT_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_IDENTS,
    _TRIGGER_COPY_EXTRA,
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

# The "opponents' graveyards" serve (graveyard_makers / graveyard_matters,
# opponents): the opponent-graveyard makers and payoffs plus the opponent mill
# makers.
_OPPONENT_GRAVEYARD_IDENTS = frozenset(
    {
        "graveyard_makers|opponents|",
        "graveyard_matters|opponents|",
        "mill_makers|opponents|",
    }
)

# The stax serve (stax_taxes, opponents / symmetric_stax, each): opponent taxes and
# symmetric locks.
_STAX_IDENTS = frozenset({"stax_taxes|opponents|", "symmetric_stax|each|"})

# The Treasure serve (treasure_makers / treasure_matters, you): both lanes.
_TREASURE_IDENTS = frozenset({"treasure_makers|you|", "treasure_matters|you|"})

# Creatures entering your battlefield, as the lanes read them: the creature-token
# makers, a creature cheat, a creature that reanimates (damage_for_each,
# creature_etb).
_CREATURES_ENTERING_IDENTS = _TOKEN_MAKER_IDENTS | {
    "cheat_into_play|you|Creature",
    "reanimator|you|",
    "creature_recursion|you|battlefield",
}

# The aristocrats serve (sacrifice_outlets you, death_matters any): the creature-
# token fodder, the outlets, the death payoffs on every side, the edicts, and the
# death-value fodder (a permanent whose own death trigger replaces it).
_ARISTOCRATS_IDENTS = (
    _TOKEN_MAKER_IDENTS
    | _DEATH_PAYOFF_IDENTS
    | {
        "sacrifice_outlets|you|",
        "edict_makers|opponents|",
        "edict_makers|each|",
        "self_death_payoff|you|",
    }
)

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
# deck also wants Sizzle) — direct_damage's ``each_opponent`` subject.
_GROUP_BURN_EXTRA = SubAvenue(
    "Group burn",
    "burn that hits each opponent, beside the sweepers and pingers that hit everyone",
    serve=Serve(signal_idents=frozenset({"direct_damage|you|each_opponent"})),
)


def _extra_step_spec(label: str, key: str, step: str) -> SignalSpec:
    """An extra-step key's spec: the makers and the triggers each added step
    repeats (its ``STEP_TRIGGER_KEYS`` payoff key, which resolves to this spec but
    opens no avenue — only a maker does)."""
    noun = step if step.endswith("step") else f"{step} step"
    hyphenated = step.replace(" ", "-")
    return _spec(
        label,
        f"{hyphenated}-trigger payoffs, multiplied by every added {noun}",
        None,
        serve_idents=frozenset({f"{key}|you|", f"{STEP_TRIGGER_KEYS[key]}|you|"}),
    )


_EXTRA_UPKEEPS = _extra_step_spec("Extra upkeeps", "extra_upkeep", "upkeep")
_EXTRA_END_STEPS = _extra_step_spec("Extra end steps", "extra_end_step", "end step")
_EXTRA_DRAW_STEPS = _extra_step_spec("Extra draw steps", "extra_draw_step", "draw step")


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
        None,
        serve_idents=_CHOSEN_TYPE_IDENTS,
        search={"preset_names": ("chosen-type-payoff",)},
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
        # Serve rides the lanes: the token makers plus the creatures put onto the
        # battlefield (a creature cheat, reanimation or recursion to the battlefield).
        None,
        serve_idents=_CREATURES_ENTERING_IDENTS,
    ),
    ("creature_etb", "you"): _spec(
        "Creatures entering — yours",
        "cheap ways to flood your board with creatures",
        # Serve rides the lanes (the token makers, creature cheats, creatures that
        # reanimate, creature recursion onto the battlefield).
        None,
        serve_idents=_CREATURES_ENTERING_IDENTS,
        # An ETB commander wants the high-value ETB creatures and the doublers, not just
        # the punisher payoffs — same extras the blink lane uses (A3).
        extras=(
            _ETB_PAYOFF_EXTRA,
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _TRIGGER_COPY_EXTRA,
            _FLICKER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
    ),
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        # Serve rides the lane. "Creatures your opponents control enter tapped" statics
        # (Imposing Sovereign, Kinjalli's Sunwing) are stax_taxes', not an ETB trigger;
        # the lane gains Aboleth Spawn.
        None,
        serve_idents=frozenset({"creature_etb|opponents|"}),
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
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
    # over-broad: the LANE is narrow. The main serve is the self-sacrifice outlets
    # (the lane's own ident); the leftover regex hits are Slivers lending a
    # sacrifice ability and reminder-text noise.
    ("creature_recursion", "you"): _spec(
        "Creature recursion",
        "loop fuel for a graveyard creature-recursion engine — self-sacrificing "
        "creatures, ETB-value bodies, and self-recurring fodder",
        None,
        serve_idents=frozenset({"sacrifice_outlets|you|self"}),
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
        # The power-threshold payoffs and enablers ride the lane (Garruk's Uprising,
        # ferocious dorks); what the old pattern added beyond it was crew, saddle and
        # station costs, evasion and removal filters that merely name a power.
        None,
        serve_idents=frozenset({"power_matters|you|"}),
        serve_power_min=4,
        extras=(_POWER_FLING_EXTRA,),
        search={"card_type": "Creature", "cmc_min": 5},
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
        # The lane adds the land animators (Quirion Druid, earthbend, Nissa, Who Shakes
        # the World); exile / destroy a land creature (Consuming Sinkhole) is no longer
        # served. The creature-lands themselves (Mutavault, Dryad Arbor) are the
        # ``self`` subject, and as lands they feed the theme's depth.
        None,
        serve_idents=frozenset(
            {
                "land_creatures_matter|you|",
                "land_creatures_matter|you|animator",
                "land_creatures_matter|you|self",
            }
        ),
        serve_lands_feed=True,
        extras=(
            SubAvenue(
                "Land-creature payoffs",
                "anthems and abilities that specifically pump land creatures",
                serve=Serve(signal_idents=frozenset({"land_creatures_matter|you|"})),
            ),
            SubAvenue(
                "Animate your lands",
                "effects that turn lands you control into creatures",
                serve=Serve(
                    signal_idents=frozenset({"land_creatures_matter|you|animator"})
                ),
            ),
            SubAvenue(
                "Forest-bounce untap engines",
                # Quirion/Scryb Ranger family: bounce a Forest/land you control
                # to untap a creature -- or, with Oboro Breezecaller, an animated
                # land, re-tapping it for mana. Narrow but real in forest-animation
                # decks; the bounce cost is the precision gate (a plain {T}: untap
                # is not this).
                "bounce a Forest/land you control to untap a creature or land",
                serve=Serve(
                    oracle=re.compile(
                        r"return a (?:forest|land) you control to its "
                        r"owner's hand[^.]*untap",
                        _IC,
                    )
                ),
            ),
        ),
    ),
    # Widen to recover graveyard-HATE payoffs (exile an opponent's graveyard, count
    # cards in opponents' graveyards) the mill-only serve missed — still scoped to
    # OPPONENTS (self-mill never qualifies, the Tinybones guard).
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        # Serve rides the lanes: the opponent-graveyard makers and payoffs plus the
        # opponent mill makers. The old pattern's leftovers are opponent library-
        # exile riders (ingest, impulse theft) the lanes read as neither.
        None,
        serve_idents=_OPPONENT_GRAVEYARD_IDENTS,
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard, plus the high-ETB and "
        "self-recurring creatures worth putting there and bringing back",
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
        # Same serve as the matters lane: both ride the opponent-graveyard idents
        # and the opponent mill makers.
        None,
        serve_idents=_OPPONENT_GRAVEYARD_IDENTS,
    ),
    # The PAYOFF that pairs with the FUEL above: reanimation effects + cast-from-grave
    # creatures, because Celes-style commanders reward a creature re-entering play from
    # the graveyard, not merely a full graveyard. See _REANIMATION_EXTRA (_shared).
    ("reanimator", "you"): _spec(
        "Reanimation",
        "reanimation effects that return a creature from your graveyard to the "
        "battlefield — each one fires your payoff and you choose the target",
        None,
        # Serve rides the lanes: reanimation and creature recursion onto the
        # battlefield. Cast-from-graveyard stays the extra below.
        serve_idents=frozenset(
            {"reanimator|you|", "creature_recursion|you|battlefield"}
        ),
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
    # counter-movers that compound the kind-agnostic plan. Same serve as the payoff
    # lane; the label reframes it as the maker/engine avenue. CR 122.1 / 701.34a.
    ("any_counter_makers", "you"): _spec(
        "Any-counter engines",
        "proliferate, counter movers, and any-kind counter manipulation",
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
    # cards carry the exact shape.
    ("counter_hate", "opponents"): _spec(
        "Counter denial",
        "deny opponents' counters (anti-+1/+1, anti-proliferate stax)",
        # Serve rides the lane (2026-10-18): regex missed Suncleanser's two-sentence
        # 'loses all counters. That player can't get'
        None,
        serve_idents=frozenset({"counter_hate|opponents|"}),
    ),
    # np_boons task #5: adapt_matters — Biomancer's Familiar's re-adapt
    # enabler (CR 701.46a), a 1-card population today.
    ("adapt_matters", "you"): _spec(
        "Adapt support",
        "enable or re-trigger Adapt (CR 701.46) on creatures you control",
        # Serve rides the lane (2026-10-18): regex and lane served the same card; the
        # lane is now the one source
        None,
        serve_idents=frozenset({"adapt_matters|you|"}),
    ),
    # Hand spec (overrides the mined sweep detector) so the avenue can fan out a
    # dedicated "Flip fixing" sub-avenue. The flat coin-flip page returns ~60 generic
    # "flip a coin" payoffs and buries Krark's-Thumb-style fixers past the package cap,
    # even though fixing flips is the whole point of a coin-flip deck.
    ("coin_flip", "any"): _spec(
        "Coin flips",
        "coin-flip payoffs and outlets",
        # Serve rides the lane (2026-10-18): regex missed 'Flip five coins' / 'each
        # player flips a coin' (Ral Zarek, Goblin Assassin)
        None,
        serve_idents=frozenset({"coin_flip|you|", "coin_flip|you|fixer"}),
        extras=(
            # A flip FIXER replaces your flips (Krark's Thumb, CR 614.1a) or fixes
            # their result (Edgar, King of Figaro's Two-Headed Coin, CR 705.3): the
            # lane's ``fixer`` subject.
            SubAvenue(
                "Flip fixing",
                "cards that bias, repeat, or ignore unfavorable coin flips "
                "(Krark's Thumb effects)",
                serve=Serve(signal_idents=frozenset({"coin_flip|you|fixer"})),
            ),
        ),
    ),
    ("draw_matters", "you"): _spec(
        "Draw triggers / wheels",
        "draw-trigger payoffs and extra-draw engines (Nekusar / Chasm Skulker space)",
        # The draw payoffs plus the symmetric draw engines and wheels (Howling Mine,
        # Wheel of Fortune), extra draw-step draws (Grafted Skullcap) and a granted
        # "whenever you draw" (Diviner's Wand) included. Lane gap: ordinal draws.
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
        # Serve = the rebuild package ONLY (verified-review F7): the wipe
        # pattern itself served redundant wraths above actual protection/
        # reanimation cards; the serve scores what helps you rebuild
        # through one.
        None,
        extras=(_BOARD_PROTECTION_EXTRA, _REANIMATION_EXTRA),
        serve_keywords=("indestructible",),
    ),
    ("keep_n_wrath", "opponents"): _spec(
        "One-sided keep-N",
        "opponents keep N and sacrifice the rest while your board is "
        "untouched (Archfiend of Depravity)",
        # The one-sided resets alone: the deck's own symmetric keep-N wraths are
        # the ``each`` ident, never this lane's depth.
        None,
        serve_idents=frozenset({"keep_n_wrath|opponents|"}),
        extras=(_BOARD_PROTECTION_EXTRA,),
    ),
    # task B-5: combat_choice_makers — you make opponents' attack/block
    # declarations (CR 508.1a / 509.1a transferred to you). Pairs with the
    # forced-combat package: goad, forced attack, combat support.
    ("combat_choice_makers", "opponents"): _spec(
        "Combat puppeteer",
        "cards that let you make attack and block choices for opponents "
        "(Master Warcraft, Odric) — pair with goad and forced-attack effects",
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"combat_choice_makers|opponents|"}),
        extras=(_FORCE_ATTACK_EXTRA, _COMBAT_SUPPORT_EXTRA),
    ),
    ("edict_makers", "each"): _spec(
        *SWEEP_LABELS["edict_makers"],
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
    # Combat: attack-trigger payoffs (Hellrider, Adeline, Shared Animosity) and the
    # haste / token enablers that feed them (CR 508 declare-attackers triggers).
    ("attack_matters", "you"): _spec(
        "Combat",
        "attack-trigger payoffs, haste enablers, and aggressive bodies",
        # Serves the attack triggers, token makers, combat-damage payoffs, attack
        # buffs, extra combats and the team haste / combat-keyword grants; remainder
        # is pacifism Auras, reminder-text haste (dash, unearth) and global haste.
        None,
        serve_idents=frozenset(
            {
                "attack_matters|you|",
                "token_maker|you|*",
                "combat_damage_to_opp|opponents|",
                "combat_damage_matters|opponents|",
                "combat_buff_engine|you|",
                "exalted_lone_attacker|you|",
                "extra_combats|you|",
                "extra_turns|you|",
                "entered_attacker|you|",
                "entered_attacker|you|etb_pump",
                "nonhuman_attackers|you|",
                "keyword_grant_target|you|haste",
                "team_buff|you|haste",
                "team_buff|you|double strike",
                "team_buff|you|first strike",
                "team_buff|you|trample",
                "team_buff|you|menace",
                "team_buff|you|deathtouch",
                "team_buff|you|vigilance",
                "team_buff|you|indestructible",
                "team_evasion_grant|you|*",
            }
        ),
        serve_keywords=("haste",),
        extras=(
            SubAvenue(
                "Equipment and Auras that suit up the attacker",
                "gear that makes the attacker bigger or evasive — a combat deck wants "
                "the equipment",
                serve=Serve(
                    types=frozenset({"equipment"}),
                    signal_idents=frozenset(
                        {
                            "voltron_makers|you|pump",
                            "aura_equip_kw_grant|you|*",
                            "voltron_matters|you|",
                        }
                    ),
                ),
            ),
        ),
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
        None,
        # Serve rides the lanes: landfall payoffs, extra land drops, and land ramp.
        # Land recursion from the graveyard stays the extra.
        serve_idents=frozenset(
            {"landfall|you|", "extra_land_drop|you|", "ramp|you|land"}
        ),
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
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
                serve=Serve(signal_idents=frozenset({"damage_received_matters|you|"})),
            ),
        ),
    ),
    # The soak payoffs themselves (Rite of Passage, Druid's Call): fed by the
    # redirects that move damage onto one creature of yours (CR 614.9).
    ("damage_received_matters", "you"): _spec(
        "Damage-received payoffs",
        "redirects that move damage onto your creature, plus more soak payoffs",
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
        # The lane serves the regex's one card plus Ruxa and Jasmine Boreal of the Seven
        # ("no abilities" payoffs).
        None,
        serve_idents=frozenset({"vanilla_matters|you|"}),
        serve_vanilla=True,
        search={"card_type": "Creature"},
    ),
    # Banding (CR 702.22a): a banding commander (Ayesha, Jarkeld) wants other banding
    # creatures to form attacking/blocking bands. Keyword[]-anchored + the oracle word.
    ("has_banding", "you"): _spec(
        "Banding",
        "creatures with banding to form attacking and blocking bands",
        # Serve rides the lane (bands with other, banding grants) beside the keyword;
        # the regex-only leftovers are one-off banding grants phase reads elsewhere.
        None,
        serve_idents=frozenset({"has_banding|you|"}),
        serve_keywords=("banding",),
    ),
    # Outlaw tribal (Vial Smasher): the 5 outlaw creature types plus "outlaws you
    # control" anthems/payoffs. (CR: outlaw = Assassin/Mercenary/Pirate/Rogue/Warlock.)
    ("outlaw_matters", "you"): _spec(
        "Outlaws",
        "outlaws (Assassins / Mercenaries / Pirates / Rogues / Warlocks) plus the "
        "anthems and payoffs that reward a board of them",
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
        # The lane serves the non-snow payoffs (Glacial Revelation, Rimewind
        # Cryomancer); the snow permanents themselves serve through the type arm.
        None,
        serve_idents=frozenset({"snow_matters|you|"}),
        serve_types=("snow",),
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        None,
        # Serve rides the lanes: artifact-count payoffs and artifact makers
        # (tokens included), plus the Treasure / Clue / Food / Blood / incubate makers.
        serve_idents=frozenset(
            {
                "artifacts_matter|you|*",
                "treasure_makers|you|",
                "clue_makers|you|",
                "food_makers|you|",
                "blood_makers|you|",
                "incubate_makers|you|",
            }
        ),
        # BEING an artifact is on-theme: an artifact-count / affinity / metalcraft deck
        # counts every artifact — lands (Seat of the Synod), rocks (Mind Stone),
        # Equipment, Vehicles — even with no "artifact" in the oracle. The oracle-only
        # serve missed these and wrongly read them as generic "good stuff".
        serve_types=("artifact",),
        search={"card_type": "Artifact"},
    ),
    # Serve augmented with "whenever you cast an enchantment" so the 14 plain CREATURES
    # that trigger on enchantment casts (Verduran/Mesa Enchantress, Sythis) — missed by
    # both the {card_type:Enchantment} type-serve and the count regex — are credited.
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        None,
        # Serve rides the lane: enchantment-count and constellation payoffs and
        # enchantment makers.
        serve_idents=frozenset({"enchantments_matter|you|*"}),
        # BEING an enchantment is on-theme: constellation / enchantment-count counts
        # every enchantment (Auras, Sagas, enchantment creatures like Spirited
        # Companion), even with no "enchantment" in the oracle.
        serve_types=("enchantment",),
        search={"card_type": "Enchantment"},
    ),
    # A color-hoser commander wants the color-changing "Painter" toolbox (Painter's
    # Servant, the -lace cycle, Mind Bend) so its color payoff applies to EVERY
    # permanent: making opponents' creatures blue lets Llawan's clauses catch them.
    ("color_hoser", "you"): _spec(
        "Color-bending",
        "color-changing 'Painter' cards that force your color payoff onto everything",
        # Serve rides the color-hate lane (the color-hoser commanders want to make
        # everything a color, then hose it) and the color-changers. The regex-only
        # leftovers are printed protection from a color, which is no hate.
        None,
        serve_idents=frozenset({"color_hoser|you|", "color_change|you|"}),
    ),
    # Tokens matter: the lane fires from crosswalk_signals._tokens_matter (ADR-0027);
    # the go-wide count-scaler and token-doubler arms are the _GOWIDE_* /
    # _TOKEN_DOUBLER_EXTRA avenues.
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        # Serve rides the token-payoff lane plus the amass makers (an Army token,
        # whose making lives in stripped reminder text); populate and token-count
        # payoffs are the lane's.
        None,
        # Single-token makers stay out (generically good, not archetype-unique); mass
        # makers ride _GOWIDE_MAKER_EXTRA. Mobilize's tokens live in stripped reminder
        # text, so the keyword is credited.
        serve_keywords=("mobilize",),
        serve_idents=frozenset({"tokens_matter|you|*", "amass_makers|you|"}),
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
        # Serve rides the two stax lanes (opponent taxes and symmetric locks); the
        # old pattern also served cost-increase and tapped-entry text on ordinary
        # cards.
        None,
        serve_idents=_STAX_IDENTS,
    ),
    # Symmetric-stax commander (Hokori, Winter Orb-style locks): wants the SAME stax
    # piece pool — it runs opponent-taxes + symmetric locks + hatebears alike. Shares
    # the stax serve; hand-written so the auto-register doesn't bind a narrower one.
    ("symmetric_stax", "each"): _spec(
        "Symmetric stax",
        "stax pieces a symmetric-lock deck runs — taxes, locks, and hatebears",
        None,
        serve_idents=_STAX_IDENTS,
    ),
    # ADR-0027: symmetric_damage_each's SWEEP_DETECTORS row was deleted (detection moved
    # to the Card IR — the v22 damage Effect scope=='each' arm + each-player mirror).
    # The serve is the lane's ident, with each-opponent burn (the reach the DETECTOR
    # split dropped) as the Group burn extra — a Pestilence deck wants Pyrohemia AND
    # Sizzle-style group burn.
    ("symmetric_damage_each", "each"): _sweep_spec_with_extras(
        "symmetric_damage_each",
        (_GROUP_BURN_EXTRA,),
        # Gains the variable symmetric burns (Price of Progress, Acidic Soil);
        # each-opponent burn (Boltwave, Sizzle) is the Group burn extra.
        serve_idents=frozenset({"symmetric_damage_each|each|"}),
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects, the high-ETB creatures worth re-using, and the "
        "doublers that multiply each enter trigger",
        # Serves the lane's enablers (Restoration Angel, Flickerwisp); bare blink
        # bodies ride the ETB-value extra. Remainder: reanimation and Saga text, plus
        # Teferi's Time Twist and Cosmic Intervention (a phase misparse).
        None,
        # Death-return (dies_recursion) and self-bounce recast engines (Whitemane
        # Lion, Kor Skyfisher) are their own avenues below: a blink deck re-uses ETBs
        # that way too.
        serve_idents=frozenset({"blink_flicker|you|enabler"}),
        extras=(
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
        search={"preset_names": ("blink",)},
    ),
    ("mill_makers", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        # Serve rides the lane (2026-10-18): regex and lane served the same 579 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"mill_makers|any|"}),
        search={"preset_names": ("mill",)},
    ),
    ("goad_makers", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        # Serve rides the lane (2026-10-18): regex missed forced-attack + attack-your-
        # foes incentives (Alluring Siren, Breena)
        None,
        serve_idents=frozenset({"goad_makers|opponents|"}),
        # politics: make yourself a bad target too; force-attack: feed the payoff by
        # making opponents swing (Kazuul rewards being attacked).
        extras=(_PILLOWFORT_EXTRA, _FORCE_ATTACK_EXTRA),
        search={"preset_names": ("goad",)},
    ),
    # Fog / damage-prevention commanders durdle defensively — pillowfort is a top
    # EDHREC pick for them (4 commanders in the evidence). ADR-0027: damage_prevention
    # migrated (its SWEEP_DETECTORS row deleted); the serve is the lanes' idents.
    ("damage_prevention", "you"): _sweep_spec_with_extras(
        "damage_prevention",
        (_PILLOWFORT_EXTRA, _DAMAGE_SOAK_EXTRA),
        # Serve rides the lane (2026-10-18): regex missed redirect-to-self + prevent-1
        # statics (Beacon of Destiny, Gisela)
        serve_idents=frozenset({"damage_prevention|you|", "damage_redirect|you|"}),
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate plus any-kind counter sources and doublers (Vorinclex)",
        # Lane gaps: loyalty-counter placers (Oath of Gideon, Commodore Guff), empower
        # Jace, "whenever you proliferate" payoffs (Scheming Aspirant). The +1/+1
        # package's documented exclusions and planeswalkers naming a loyalty counter are
        # out.
        None,
        serve_idents=_PROLIFERATE_IDENTS,
        extras=(_COUNTER_DOUBLER_EXTRA, _KEYWORD_COUNTER_EXTRA),
        search={"preset_names": ("proliferate",)},
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
        # Serve rides the lanes, shared with proliferate_matters.
        None,
        serve_idents=_PROLIFERATE_IDENTS,
        extras=(_COUNTER_DOUBLER_EXTRA, _KEYWORD_COUNTER_EXTRA),
        search={"preset_names": ("proliferate",)},
    ),
    # Hand-promote EVERY mined +1/+1-counter lane with the shared counters package so a
    # counters commander surfaces sources (Forgotten Ancient), doublers (Hardened
    # Scales), keyword counters, and proliferate no matter which fragmented lane opened.
    # ADR-0027 β: self_counter_grow migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted — a structural SelfRef-marker arm + a narrowed mirror); the serve is the
    # lanes' idents.
    ("self_counter_grow", "you"): _sweep_spec_with_extras(
        "self_counter_grow",
        _COUNTERS_PACKAGE,
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
    # cost mirror).
    ("counter_manipulation", "you"): _sweep_spec_with_extras(
        "counter_manipulation",
        _COUNTERS_PACKAGE,
        # Serve rides the lane (2026-10-18): regex missed 'Remove all/two +1/+1
        # counters' costs (Experiment One)
        serve_idents=frozenset({"counter_manipulation|you|"}),
    ),
    # ADR-0027 β: counter_distribute's SWEEP_DETECTORS row was deleted (detection moved
    # to the Card IR — the MassEach structural arm + narrowed mirror).
    ("counter_distribute", "you"): _sweep_spec_with_extras(
        "counter_distribute",
        _COUNTERS_PACKAGE,
        # Serve rides the lane (2026-10-18): regex missed typed-subject distributes ('on
        # each Vampire': Edgar Markov)
        serve_idents=frozenset({"counter_distribute|you|"}),
    ),
    # ADR-0027 tranche2-B: counter_place_trigger's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_added trigger event). The serve
    # rides the lane, which reads granted triggers (Cursed Wombat, Danny Pink) and
    # your placement on a creature you don't control (Kros, Generous Patron).
    ("counter_place_trigger", "you"): _sweep_spec_with_extras(
        "counter_place_trigger",
        _COUNTERS_PACKAGE,
        serve_idents=frozenset({"counter_place_trigger|you|"}),
    ),
    # ADR-0027 tranche2-C: keyword_counter's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR); the serve is the lane's ident.
    ("keyword_counter", "you"): _sweep_spec_with_extras(
        "keyword_counter",
        _COUNTERS_PACKAGE,
        # Serve rides the lane (2026-10-18): regex missed choice-of-counter + double-
        # strike counters (Heightened Reflexes)
        serve_idents=frozenset({"keyword_counter|any|"}),
    ),
    # ADR-0027 tranche2-B-3: spell_keyword_grant / target_player_draws had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — the whole
    # cast_with_keyword category, and a draw effect with scope=='any'), so each spec is
    # hand-registered; the serve is the lane's ident.
    ("spell_keyword_grant", "you"): _spec(
        *SWEEP_LABELS["spell_keyword_grant"],
        # The lane reads grants the fixed keyword list missed (flash, rebound,
        # flashback, storm on a next spell — Cast Through Time, Dark Apostle); Wicker
        # Picker (an Un-card) drops out.
        None,
        serve_idents=frozenset({"spell_keyword_grant|you|"}),
    ),
    # ADR-0027: flash_grant reads the Card IR (a cast_with_keyword{flash} static;
    # the FLASH_GRANT_REGEX kept mirror is retired), so hand-register the spec the
    # sweep auto-register loop used to build.
    ("flash_grant", "you"): _spec(
        *SWEEP_LABELS["flash_grant"],
        None,
        # Serve rides the lane. Self-castability ("as though it had flash if...")
        # stays out by design; Aluren, Final-Word Phantom and Scout's Warning are
        # phase gaps.
        serve_idents=frozenset({"flash_grant|you|"}),
    ),
    ("target_player_draws", "any"): _spec(
        *SWEEP_LABELS["target_player_draws"],
        # The lane serves "draws X cards" and "its controller draws" (Braingeyser, Blue
        # Sun's Zenith) beyond the regex's "draws a card".
        None,
        serve_idents=frozenset({"target_player_draws|any|"}),
    ),
    # ADR-0027: group_hug_draw's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a `draw` effect with scope=='each', plus a byte-identical kept word
    # mirror for the 4 cards phase under-structures), so hand-register the spec the
    # sweep auto-register loop used to build.
    ("group_hug_draw", "each"): _spec(
        *SWEEP_LABELS["group_hug_draw"],
        # Serve rides the lane (2026-10-18): regex missed the wheel idiom 'each player
        # ... then draws seven' (Timetwister)
        None,
        serve_idents=frozenset({"group_hug_draw|each|"}),
    ),
    # dies_recursion: the undying / persist bearers and granters and the bare
    # dies-return grants, read off the Card IR. CR 700.4 / 603.6c.
    ("dies_recursion", "you"): _spec(
        *SWEEP_LABELS["dies_recursion"],
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
        None,
        serve_idents=frozenset({"self_recurring|you|"}),
        search={"preset_names": ("self-recurring",)},
    ),
    # Task #19 SPLIT — named_synergy (the named-card SYNERGY half of the old
    # named_permanent lane). Detection reads phase's typed ``Named`` reference to a
    # permanent (``lanes._named_synergy``), the clauses phase parks riding the
    # ``named_synergy_parked_reference`` ledger row. Hand-registered (scope "you"); the
    # serve is the lane's ident.
    # SWEEP_LABELS keeps the human label.
    ("named_synergy", "you"): _spec(
        *SWEEP_LABELS["named_synergy"],
        # Gains the "for each creature named" payoffs (Plague Rats, Shield of Kaldra).
        # Legend makers ("if you don't control a creature named X", Rufus Shinra) and
        # Seven Dwarves are lane gaps.
        None,
        serve_idents=frozenset({"named_synergy|you|"}),
    ),
    # Task #19 SPLIT — copy_limit (the COPY-LIMIT half, CR 100.2a). Detection is
    # STRUCTURAL (the IR `many_copies` field, read in crosswalk_signals.py): a
    # copy-limit deck wants MORE cards sharing the relaxed name ("A deck can have
    # any number of / up to N cards named X") + go-wide-on-one-name payoffs. Scope
    # "you". CR 100.2a.
    ("copy_limit", "you"): _spec(
        *SWEEP_LABELS["copy_limit"],
        # Serve rides the lane (2026-10-18): regex and lane served the same 13 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"copy_limit|you|"}),
    ),
    # ADR-0027: topdeck_stack's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a STRUCTURAL arm over phase's `topdeck_stack` Effect + a kept word
    # mirror). Hand-registered (scope "you"); the serve is the lane's ident.
    # SWEEP_LABELS keeps the human label. CR 401.4.
    ("topdeck_stack", "you"): _spec(
        *SWEEP_LABELS["topdeck_stack"],
        # The lane adds graveyard-to-top (Academy Ruins, Reclaim) and top-of-library
        # play engines (Future Sight); surveil's reminder text, all the regex's extras,
        # is noise.
        None,
        serve_idents=frozenset({"topdeck_stack|you|"}),
    ),
    # ADR-0027 (q2-D3): noncreature_cast_punish's SWEEP_DETECTORS row is deleted
    # (detection moved to the Card IR — a cast_spell trigger scope=='opp' over a
    # noncreature subject, plus a kept word mirror for the symmetric "a player casts"
    # half). Hand-registered; the serve is the lane's ident. SWEEP_LABELS still carries
    # the human label.
    ("noncreature_cast_punish", "any"): _spec(
        *SWEEP_LABELS["noncreature_cast_punish"],
        # Gains the "first noncreature spell each turn" punishers (Esper Sentinel).
        # Casts that reward or copy (Golem's Heart, Hive Mind) are out; In the Eye of
        # Chaos is a lane gap.
        None,
        serve_idents=frozenset({"noncreature_cast_punish|any|"}),
    ),
    # ADR-0027 β: global_ability_grant's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the board_grant + counter_kind="grant_ability" marker read by
    # crosswalk_signals.py), so hand-register the spec the sweep auto-register loop
    # used to build (scope "any", the deleted SWEEP row's scope). SWEEP_LABELS keeps
    # label.
    ("global_ability_grant", "any"): _spec(
        *SWEEP_LABELS["global_ability_grant"],
        # Serve rides the lane (2026-10-18): regex missed quoted grants to a
        # typed/qualified subject (Esika, Rishkar)
        None,
        serve_idents=frozenset({"global_ability_grant|any|"}),
    ),
    # ADR-0027 β: keyword_grant_target's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the single_target_grant marker read by crosswalk_signals.py).
    # Hand-register the spec the sweep loop built (scope "you", the deleted SWEEP
    # row's scope). SWEEP_LABELS keeps label.
    ("keyword_grant_target", "you"): _spec(
        *SWEEP_LABELS["keyword_grant_target"],
        # Serve rides the lane (2026-10-18): regex missed multi-target / attacking-
        # creature grants (Aerial Guide, Aim High). Every granted keyword (the
        # lane's subject) is a targeted grant.
        None,
        serve_idents=frozenset({"keyword_grant_target|you|*"}),
    ),
    # ADR-0027 Cluster D: protection_grant's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR — the structural protective-keyword grant arm; the
    # PROTECTION_GRANT_REGEX kept mirror is retired), so hand-register the spec the
    # sweep auto-register loop used to
    # build (scope "you", the deleted SWEEP row's scope). SWEEP_LABELS keeps the
    # human label.
    ("protection_grant", "you"): _spec(
        *SWEEP_LABELS["protection_grant"],
        # Serve rides the lane; the old pattern's extras were self-granted shroud and
        # hexproof abilities and reminder-text mentions, not grants to your board.
        None,
        serve_idents=frozenset({"protection_grant|you|"}),
    ),
    # ADR-0027 β: debuff_makers's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the negative-pump (factor<0) / non-self m1m1 structural arm + a
    # byte-identical _IR_KEPT_DETECTORS mirror), so hand-register the spec the sweep
    # auto-register loop used to build (scope "any", the deleted SWEEP row's scope).
    # SWEEP_LABELS keeps the label.
    #
    # Serve on the lane's idents: the lane reads
    # the variable and one-sided shrinks, the static "-X/-X" Auras and board
    # shrinks, granted shrink abilities and one-shot base-P/T sets the regex
    # served, and leaves out what it over-served — your own -1/-1 counters
    # (blight, CR 701.68a), a creature shrinking itself, flanking reminder text.
    ("debuff_makers", "any"): _spec(
        *SWEEP_LABELS["debuff_makers"],
        None,
        serve_idents=frozenset({"debuff_makers|any|", "debuff_makers|you|"}),
    ),
    # ADR-0027 β: pump_makers's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a kept _IR_KEPT_DETECTORS mirror; the lane is unstructurable, so no
    # structural arm). Hand-registered (scope "you"); the serve is the lane's ident.
    # SWEEP_LABELS keeps the label.
    ("pump_makers", "you"): _spec(
        *SWEEP_LABELS["pump_makers"],
        # The lane reads every targeted pump the regex did, plus anaphoric "it gets"
        # (Spidery Grasp), team pumps (Surge to Victory) and attack-trigger pumps
        # (Fervent Champion).
        None,
        serve_idents=frozenset({"pump_makers|you|"}),
    ),
    # ADR-0027 β: free_cast's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR via a kept _FREE_CAST_MIRROR; the IR has no 'free' flag, so no structural
    # arm). Hand-registered (scope "you"); the serve is the lanes' idents. SWEEP_LABELS
    # keeps the label.
    ("free_cast", "you"): _spec(
        *SWEEP_LABELS["free_cast"],
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
    # to the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror), so hand-register
    # the spec the sweep auto-register loop used to build (scope "you", the deleted
    # SWEEP row's scope). SWEEP_LABELS still carries the human label.
    ("tribe_damage_trigger", "you"): _spec(
        *SWEEP_LABELS["tribe_damage_trigger"],
        # Serve rides the lane (2026-10-18): regex missed keyword/counter subjects
        # ('with deathtouch': Fynn), served Quest for Pure Flame
        None,
        serve_idents=frozenset({"tribe_damage_trigger|you|"}),
    ),
    # ADR-0027 β: timing_control's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror), so hand-register the
    # spec the sweep auto-register loop used to build (scope "any", the deleted SWEEP
    # row's scope). SWEEP_LABELS still carries the human label.
    ("timing_control", "any"): _spec(
        *SWEEP_LABELS["timing_control"],
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"timing_control|any|"}),
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B): sacrifice_protection / secret_writedown had
    # their SWEEP_DETECTORS rows deleted (detection moved to the Card IR — kept_detector
    # word mirrors), so the sweep auto-register loop no longer builds their serve. Hand-
    # register each at scope "you". SWEEP_LABELS still carries the human label.
    ("sacrifice_protection", "you"): _spec(
        *SWEEP_LABELS["sacrifice_protection"],
        # Serve rides the lane (2026-10-18): regex and lane served the same 11 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"sacrifice_protection|you|"}),
    ),
    ("secret_writedown", "you"): _spec(
        *SWEEP_LABELS["secret_writedown"],
        # Serve rides the lane: the secret-choice cards and the learn (sideboard)
        # cards. Regex-only leftovers are hidden-agenda conspiracies and reminder
        # text.
        None,
        serve_idents=frozenset({"secret_writedown|you|", "secret_writedown|you|learn"}),
    ),
    # ADR-0027 tranche2-B (t2b3-B): opponent_counter_grant's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR — a detrimental bounty/stun counter on an
    # opponent's permanent). Hand-registered at the "opponents" scope it fires at; the
    # serve is the lane's ident.
    ("opponent_counter_grant", "opponents"): _spec(
        *SWEEP_LABELS["opponent_counter_grant"],
        # The lane adds stun counters on an opponent's creature (Freeze in Place) and
        # -1/-1 counters on theirs (Archfiend of Ifnir).
        None,
        serve_idents=frozenset({"opponent_counter_grant|opponents|"}),
    ),
    # ADR-0027 tranche2-B: counter_replace_bonus's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_doubling replacement category).
    ("counter_replace_bonus", "you"): _sweep_spec_with_extras(
        "counter_replace_bonus",
        _COUNTERS_PACKAGE,
        # Serve rides the lane (2026-10-18): regex missed the 'twice that many' doublers
        # (Doubling Season, Vorinclex)
        serve_idents=frozenset({"counter_replace_bonus|you|"}),
    ),
    # ADR-0027: counter_move's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — phase's MoveCounters effect). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec, keeping the counter-doubler fan-out
    # package.
    ("counter_move", "you"): _spec(
        *SWEEP_LABELS["counter_move"],
        # Serve rides the lane (2026-10-18): regex missed 'put its counters on target
        # creature' (Essence Channeler)
        None,
        serve_idents=frozenset({"counter_move|you|"}),
        extras=_COUNTERS_PACKAGE,
    ),
    # Beginning-of-combat / attack-buff commanders are combat decks — surface the gear
    # and keyword-anthems that grow their attackers. ADR-0027 Cluster D: combat_buff_
    # engine migrated to the IR (its SWEEP_DETECTORS row is deleted); the serve is the
    # lane's ident.
    ("combat_buff_engine", "you"): _sweep_spec_with_extras(
        "combat_buff_engine",
        (_COMBAT_SUPPORT_EXTRA,),
        # Gains beginning-of-combat counters and buffs (Nessian Hornbeetle, Kimahri).
        # Block / becomes-blocked self pumps and flanking / exalted reminders drop out.
        serve_idents=frozenset({"combat_buff_engine|you|"}),
    ),
    # A "becomes blocked" payoff (General Marhault: +3/+3 for each creature blocking it)
    # wants Lure effects — forcing every able creature to block maxes the per-blocker
    # bonus. ADR-0027 Cluster D: the SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the structural becomes_blocked arm; the BLOCKED_MATTERS_REGEX kept
    # mirror is retired); the serve is the lane's ident.
    ("blocked_matters", "you"): _sweep_spec_with_extras(
        "blocked_matters",
        (_LURE_EXTRA,),
        serve_idents=frozenset({"blocked_matters|you|"}),
    ),
    # Heroic / target-matters: the payoff fires when YOU target your own creature, so
    # surface the single-target pumps/protection that do it (Gods Willing, Brute Force).
    ("targeting_matters", "any"): _spec(
        *SWEEP_LABELS["targeting_matters"],
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
    # creature spell" scan). Its SWEEP_DETECTORS row is deleted; the serve is the
    # lane's ident.
    ("creature_cast_trigger", "you"): _sweep_spec_with_extras(
        "creature_cast_trigger",
        (_CREATURE_COST_EXTRA, _SELF_BOUNCE_EXTRA),
        serve_power_min=6,
        # Serve rides the lane (2026-10-18): regex missed typed creature-spell triggers
        # (Emrakul's Influence, Donal)
        serve_idents=frozenset({"creature_cast_trigger|any|"}),
    ),
    # Toughness-as-power (Doran, Arcades) decks want bodies whose TOUGHNESS beats
    # their power, and Walls: a creature assigns combat damage equal to its power
    # (CR 510.1a), Doran swaps in toughness, so a 6/6 gains nothing. (Damage
    # reflection keeps toughness >= 4 below: a big body survives to reflect.)
    ("toughness_combat", "you"): _sweep_spec_with_extras(
        "toughness_combat",
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
        # Serve rides the lane (2026-10-18): regex and lane agree but for Loxodon
        # Lifechanter's total-toughness read
        serve_idents=frozenset({"toughness_combat|you|"}),
    ),
    # ADR-0027 β: ability_copy migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds its spec). Hand-
    # registered; the serve is the lane's ident. SWEEP_LABELS still carries the label.
    ("ability_copy", "you"): _sweep_spec_with_extras(
        "ability_copy",
        # Demonstrate's reminder ("you may copy it") is a spell copy (CR 702.144a), not
        # an ability copy, so it is out.
        serve_idents=frozenset({"ability_copy|you|"}),
    ),
    # ADR-0027: damage_reflect's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the on-card damage_received+damage co-occurrence + a damage_reflect
    # marker for the quoted reflection grant). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec.
    ("damage_reflect", "you"): _spec(
        "Damage reflection",
        "more damage reflectors (Boros Reckoner, Arcbond) to turn each hit around",
        # Serve rides the lane (2026-10-18): regex missed enrage + Aura/global
        # reflectors (Repercussion, Arcbond). The toughness >= 4, toughness >
        # power and defender arms went 2026-10-24 (the serve-arm guard): the
        # damage a reflector deals is the damage dealt to IT, so another big body
        # reflects nothing (Roaming Throne, Wall of Omens paged as feeders).
        None,
        serve_idents=frozenset({"damage_reflect|you|"}),
    ),
    # Power doublers (Rhonas, Mr. Orfeo) want high BASE power to double; power-as-damage
    # pingers/fighters (Itzquinth) want high power for more damage. Both lanes credit
    # the fat bodies they exploit (Ghalta / Worldspine Wurm), not just the engine cards.
    # ADR-0027: power_double migrated to the Card IR (a pump/pump_target effect whose
    # raw carries the "double … power" word-mirror); its SWEEP_DETECTORS row is
    # deleted.
    ("power_double", "you"): _sweep_spec_with_extras(
        "power_double",
        (_POWER_FLING_EXTRA,),
        serve_power_min=5,
        # Serve rides the lane (2026-10-18): regex missed 'double target creature's
        # power' (Exponential Growth)
        serve_idents=frozenset({"power_double|you|"}),
    ),
    # Firebreathing / variable-P/T decks pump power, then fling it for damage. ADR-0027:
    # self_pump migrated to the Card IR (its SWEEP_DETECTORS row is deleted); the serve
    # is the lane's ident.
    ("self_pump", "you"): _sweep_spec_with_extras(
        "self_pump",
        (_POWER_FLING_EXTRA,),
        # Gains +N/-N and sacrifice-fed self pumps (Mistwalker). Pumps of a target
        # creature are noise; granted firebreathing (Shiv's Embrace, Kusari-Gama) is a
        # lane gap.
        serve_idents=frozenset({"self_pump|you|"}),
    ),
    # ADR-0027: tapper_engine migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a `tap` Effect with a target subject + a "doesn't
    # untap" restriction raw), so hand-register the spec the sweep loop used to build.
    # Serve on the lane's ident once it reads granted tap abilities and
    # triggers (an Equipment's "{T}: Tap target creature").
    ("tapper_engine", "any"): _spec(
        *SWEEP_LABELS["tapper_engine"],
        None,
        serve_idents=frozenset({"tapper_engine|any|"}),
    ),
    # ADR-0027: count_anthem migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a team +N/+N pump scaling with a board count over a
    # generic creature Filter you control), so hand-register the spec the sweep loop
    # used to build; the serve is the lane's ident.
    ("count_anthem", "you"): _spec(
        *SWEEP_LABELS["count_anthem"],
        # Gains X-valued team pumps (Craterhoof Behemoth, Jodah). Tribe-subject count
        # anthems (Armament Master, Joraga Warcaller) are a lane gap.
        None,
        serve_idents=frozenset({"count_anthem|you|"}),
    ),
    # ADR-0027 #24g: scaling_pump migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection is the structural _is_scaling_count `pump` arm reading the
    # supplement-recovered op=count operand; the kept word mirror is DELETED too), so
    # the auto-register loop no longer builds this spec. Hand-registered; the serve is
    # the lane's ident.
    ("scaling_pump", "you"): _spec(
        *SWEEP_LABELS["scaling_pump"],
        # Adds the X-valued scalers (Craterhoof's "where X is"). Lane gaps: Dark Matter
        # Manipulator, Ellivere, Vren.
        None,
        serve_idents=frozenset({"scaling_pump|you|"}),
    ),
    # ADR-0027 Cluster C: base_pt_set migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to the structural cat=="base_pt_set" arm; the
    # carved BASE_PT_SET_REGEX kept word mirror is retired), so the auto-register loop
    # no longer builds this spec. Hand-register the spec the sweep loop used to
    # build — the serve pool is set-P/T effects + the creatures that exploit a set
    # base P/T. Scope 'any' (the deleted SWEEP row's scope).
    ("base_pt_set", "any"): _spec(
        *SWEEP_LABELS["base_pt_set"],
        # Serve rides the lane (2026-10-18): regex missed X-valued sets (Biomass
        # Mutation, Mirror Entity)
        None,
        serve_idents=frozenset({"base_pt_set|any|", "base_power_matters|you|"}),
    ),
    # ADR-0027: tribal_etb_multi migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to an etb trigger with a creature-subtype subject), so
    # hand-register the spec the sweep loop used to build; the serve is the lane's
    # ident.
    ("tribal_etb_multi", "you"): _spec(
        *SWEEP_LABELS["tribal_etb_multi"],
        # The lane reads every typed "whenever this or another <type> enters" (Lathliss,
        # Chasm Guide); typeless ones (Flayer of the Hatebound) are out.
        None,
        serve_idents=frozenset({"tribal_etb_multi|you|"}),
    ),
    # ADR-0027: typed_enters_punish migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to an etb trigger whose consequence burns the
    # opponents), so hand-register the spec the sweep loop used to build; the serve is
    # the lane's ident.
    ("typed_enters_punish", "you"): _spec(
        *SWEEP_LABELS["typed_enters_punish"],
        # The lane adds Impact Tremors, landfall and artifact-enters pingers.
        None,
        serve_idents=frozenset({"typed_enters_punish|you|"}),
    ),
    # Force-attack / goad commander (Kratos) wants extra combats to swing again.
    # ADR-0027: forced_attack migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted; the IR arm + DET kept mirror drive the firing); the serve is the lanes'
    # idents.
    ("forced_attack", "you"): _sweep_spec_with_extras(
        "forced_attack",
        (_EXTRA_COMBAT_EXTRA, _COMBAT_SUPPORT_EXTRA),
        # Forced attacks plus goad (the regex read goad's reminder); gains "attacks this
        # turn if able" (Goblin Diplomats, Incite).
        serve_idents=frozenset(
            {"forced_attack|any|", "forced_attack|you|", "goad_makers|opponents|"}
        ),
    ),
    # Donate commander (Jon Irenicus, Harmless Offering) wants drawback creatures to
    # hand to opponents for the downside.
    # ADR-0027: donate_makers had its SWEEP_DETECTORS row deleted (detection moved to
    # the Card IR — a gain_control raw-recipient discriminator).
    ("donate_makers", "you"): _sweep_spec_with_extras(
        "donate_makers",
        (_DRAWBACK_EXTRA, _FORCE_FEED_EXTRA),
        # Serve rides the lane (2026-10-18): regex missed 'may have that player gain
        # control' donates (Assault Suit)
        serve_idents=frozenset({"donate_makers|you|"}),
    ),
    # ADR-0027 t2b4-C: damage_to_you_punish's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — an _IR_KEPT_DETECTORS word mirror; phase drops
    # the opp-source filter and the "to you" recipient). The serve was auto-registered
    # from the SWEEP row (scope "opponents"), so hand-register it.
    ("damage_to_you_punish", "opponents"): _sweep_spec_with_extras(
        "damage_to_you_punish",
        # Serve rides the lane (2026-10-18): regex missed 'creatures an opponent
        # controls deal combat damage to you' (Norn's Decree)
        serve_idents=frozenset({"damage_to_you_punish|opponents|"}),
    ),
    # ADR-0027 t2b5-A: the SWEEP_DETECTORS rows for draft_spellbook / each_mode_player
    # / flip_self / miracle_grant were deleted (detection moved to the Card IR — each is
    # a signals._IR_KEPT_DETECTORS word mirror). Their serves were auto-registered from
    # the SWEEP rows, so hand-register each with its scope so the auto-register loop's
    # missing-row lookup never runs.
    ("draft_spellbook", "you"): _sweep_spec_with_extras(
        "draft_spellbook",
        # Serve rides the lane (2026-10-18): regex and lane served the same five cards;
        # the lane is now the one source
        serve_idents=frozenset({"draft_spellbook|you|"}),
    ),
    ("each_mode_player", "each"): _sweep_spec_with_extras(
        "each_mode_player",
        # Serve rides the lane (2026-10-18): regex and lane served the same seven cards;
        # the lane is now the one source
        serve_idents=frozenset({"each_mode_player|each|"}),
    ),
    ("flip_self", "you"): _sweep_spec_with_extras(
        "flip_self",
        # Adds flips worded "flip it" / "flip <name>" (the ki-counter Kamigawa flips,
        # Erayo); Chaos Orb and Falling Star are dexterity flips.
        serve_idents=frozenset({"flip_self|you|"}),
    ),
    ("miracle_grant", "you"): _sweep_spec_with_extras(
        "miracle_grant",
        # Serve rides the lane (2026-10-18): regex and lane served the same three cards;
        # the lane is now the one source
        serve_idents=frozenset({"miracle_grant|you|"}),
    ),
    # Legend-rule-off commander (Brothers Yamazaki) wants self-copy effects to run
    # multiple copies of itself. ADR-0027 β: legend_rule_off's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR via a byte-identical _IR_KEPT_DETECTORS
    # mirror).
    ("legend_rule_off", "you"): _sweep_spec_with_extras(
        "legend_rule_off",
        (_COPY_EXTRA,),
        # Serve rides the lane (2026-10-18): regex and lane served the same ten cards;
        # the lane is now the one source
        serve_idents=frozenset({"legend_rule_off|you|"}),
    ),
    # A self-blinking commander (Norin) re-enters constantly, firing "whenever a
    # creature enters" payoffs (Impact Tremors) and doublers (Panharmonicon).
    # ADR-0027 t2b4-C: self_blink's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the name-aware fulltext detector + the per-clause
    # _SELF_BLINK_SWEEP_RE mirror). The serve is the lanes' idents.
    ("self_blink", "you"): _sweep_spec_with_extras(
        "self_blink",
        (_ETB_PAYOFF_EXTRA, _ETB_VALUE_EXTRA, _ETB_DOUBLER_EXTRA),
        # Serve rides the self-blink lane plus the blink enablers; the one regex hit
        # it drops is Teferi's Time Twist, a phase misparse.
        serve_idents=frozenset({"self_blink|you|", "blink_flicker|you|enabler"}),
    ),
    # A repeatable-wrath commander (Mageta) wants to rebuild after the sweep:
    # reanimation (Breath of Life) plus indestructible bombs (Zetalpa) that survive it.
    # ADR-0027: mass_removal migrated to the Card IR (detection moved to the structural
    # counter_kind=='all' destroy/exile/damage + negative-pump arms; its SWEEP_DETECTORS
    # row is deleted), so hand-register it so the auto-register loop's missing-row
    # lookup never runs.
    ("mass_removal", "you"): _sweep_spec_with_extras(
        "mass_removal",
        (_REANIMATION_EXTRA, _BOARD_PROTECTION_EXTRA),
        serve_keywords=("indestructible",),
        # Serve rides the lane (2026-10-18): regex served -N/-0 tricks (Ivory Charm),
        # missed typed/named wipes (Bile Blight)
        serve_idents=frozenset({"mass_removal|you|"}),
    ),
    # ADR-0027 β: variable_pt migrated to the Card IR (SWEEP row deleted); the serve is
    # the lane's ident.
    ("variable_pt", "you"): _sweep_spec_with_extras(
        "variable_pt",
        (_POWER_FLING_EXTRA,),
        # Gains power- or toughness-only CDAs (Anax). Lane gaps: animated or token CDAs
        # (Chimeric Mass, Svogthos) and pay-life P/T (Minion of the Wastes).
        serve_idents=frozenset({"variable_pt|any|"}),
    ),
    # ADR-0027 β: creature_ping migrated to the Card IR (SWEEP row deleted).
    ("creature_ping", "you"): _sweep_spec_with_extras(
        "creature_ping",
        (_DEATHTOUCH_GEAR_EXTRA,),
        serve_power_min=5,
        # Serve rides the lane (2026-10-18): regex missed tap-and-bite + granted bites
        # (Abyssal Hunter, Burning Anger)
        serve_idents=frozenset({"creature_ping|you|"}),
    ),
    # Extra steps (CR 500.9): each added upkeep (Obeka, The Ninth Doctor), end step
    # (Y'shtola Rhul) or draw step (a beginning-phase grant, CR 501.1) is another
    # instance every "at the beginning of" trigger of that step fires in.
    ("extra_upkeep", "you"): _EXTRA_UPKEEPS,
    ("upkeep_triggers", "you"): _EXTRA_UPKEEPS,
    ("extra_end_step", "you"): _EXTRA_END_STEPS,
    ("end_step_triggers", "you"): _EXTRA_END_STEPS,
    ("extra_draw_step", "you"): _EXTRA_DRAW_STEPS,
    ("draw_step_triggers", "you"): _EXTRA_DRAW_STEPS,
    # Deathtouch gear (Basilisk Collar) makes any ping / power-as-damage lethal — credit
    # it on the noncombat-damage and power-fling lanes too, not only the Burn lane.
    # ADR-0027: noncombat_damage_payoff migrated to the Card IR (SWEEP row deleted).
    ("noncombat_damage_payoff", "you"): _sweep_spec_with_extras(
        "noncombat_damage_payoff",
        (_DEATHTOUCH_GEAR_EXTRA, _NONCOMBAT_BURN_EXTRA),
        # Serve rides the lane (2026-10-18): regex and lane served the same 107 cards;
        # the lane is now the one source
        serve_idents=frozenset({"noncombat_damage_payoff|you|"}),
    ),
    # Power-as-damage / fling commander (Brion Stoutarm) wants big bodies as fling
    # fodder (power_min) plus the power-fling payoffs and deathtouch gear.
    # ADR-0027 β: damage_equal_power migrated to the Card IR (SWEEP row deleted).
    ("damage_equal_power", "you"): _sweep_spec_with_extras(
        "damage_equal_power",
        (_DEATHTOUCH_GEAR_EXTRA, _POWER_FLING_EXTRA),
        serve_power_min=6,
        # Serve rides the lane (2026-10-18): regex missed bite spells phrased 'to each
        # other creature' (Chandra's Ignition)
        serve_idents=frozenset({"creature_ping|you|", "damage_equal_power|you|"}),
    ),
    # Repeatable "deals N damage to each creature" board pinger (Tibor, Pestilence,
    # Pyrohemia): deathtouch on the source makes each ping lethal (CR 702.2b) -- a
    # recurring one-sided board wipe. The lane's whole point IS that enabler, so it
    # serves the same gear the Burn/fling lanes do, via the shared extra.
    ("aoe_ping", "you"): _spec(
        "Deathtouch board sweep",
        "your recurring damage to each creature + deathtouch on the source = a "
        "repeatable one-sided wipe (CR 702.2b)",
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
        # Serve rides the lane (2026-10-18): regex and lane served the same 44 cards;
        # the lane is now the one source
        None,
        serve_idents=frozenset({"extra_combats|you|"}),
    ),
    ("extra_turns", "you"): _spec(
        "Extra turns",
        "additional-turn effects",
        # Serve rides the lane (2026-10-18): regex served the extra-turn haters ('skips
        # that turn instead': Stranglehold)
        None,
        serve_idents=frozenset({"extra_turns|you|"}),
    ),
}
