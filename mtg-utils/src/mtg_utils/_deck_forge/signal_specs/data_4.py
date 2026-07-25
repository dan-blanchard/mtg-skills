"""Signal specs data slice 4/4: SPECS dict entries (lines 5824-6510 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

import re

from mtg_utils._deck_forge._sweep_detectors import (
    SWEEP_LABELS,
)

from ._shared import (
    _CHEAP_EVASION_EXTRA,
    _CRIPPLING_DRAWBACK_ORACLE,
    _DIES_RECURSION_EXTRA,
    _ENLIST_FODDER_EXTRA,
    _FLICKER_EXTRA,
    _GY_TO_TOP_ORACLE,
    _IC,
    _KILL_DRAIN_ORACLE,
    _LANDS_FROM_GRAVE_EXTRA,
    _MASS_DEATH_PAYOFF_ORACLE,
    _MULTI_TARGET_ORACLE,
    _REDIRECT_SERVE_ORACLE,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
)

SPECS_4: dict[tuple[str, str], SignalSpec] = {
    # ── Hand-spec overrides for mined sweep keys that need a STRUCTURED serve ────
    # (a keyword/veto dimension the auto-registered oracle-only sweep serve can't carry;
    #  the sweep regex still drives EXTRACTION, these refine the classifier).
    #
    # excess_damage: the "excess damage" phrase is the payoff; the ENABLERS are trample
    # bodies (CR 702.19) — add the keyword so the 940 trample creatures become servable.
    ("excess_damage", "you"): _spec(
        "Excess damage",
        "trample and big hits to exploit excess damage",
        {"oracle": r"\bexcess damage\b"},
        r"\bexcess damage\b",
        serve_keywords=("trample",),
    ),
    # anthem_static: a STATIC anthem, not a one-shot pump — VETO "until end of turn"
    # (those are pump_makers). Oracle-with-temporal-guard (no structured 'is-static').
    ("anthem_static", "you"): _spec(
        "Static anthem",
        "go-wide creatures to ride the anthem",
        {
            "oracle": (
                r"(?:other [a-z]+ creatures|creatures you control"
                r"|[a-z]+ creatures you control|nonblack creatures|other creatures"
                r"|(?:white|blue|black|red|green) creatures"
                r"|creatures you control of the chosen colou?r)"
                r" get \+\d/\+\d"
            )
        },
        r"(?:other [a-z]+ creatures|creatures you control"
        r"|[a-z]+ creatures you control|nonblack creatures|other creatures"
        r"|(?:white|blue|black|red|green) creatures"
        r"|creatures you control of the chosen colou?r)"
        r" get \+\d/\+\d",
        serve_not=r"get \+\d/\+\d[^.]*until end of turn",
    ),
    # ADR-0027: activated_draw had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the structural tap-cost + draw-effect IR arm). It had NO
    # hand-written serve, so the sweep auto-register loop built it; now that the row is
    # gone, hand-register the spec the loop used to build, reusing SWEEP_LABELS + the
    # deleted regex (the SERVE pool stays oracle-defined — repeatable {T}:Draw engines).
    ("activated_draw", "you"): _spec(
        *SWEEP_LABELS["activated_draw"],
        {"oracle": r"\{t\}: draw a card"},
        r"\{t\}: draw a card",
    ),
    # free_creature_payoff (Satoru): the "no mana was spent to cast" payoff wants 0-cost
    # CREATURES (Ornithopter / Memnite / Phyrexian Walker / Kobolds / Shield Sphere) —
    # not 0-cost mana rocks (Lotus Petal). AND mana_cost {0} with a creature type: each
    # alone is imprecise (mana_cost {0} alone serves Mishra's Bauble; the type alone
    # serves every creature).
    ("free_creature_payoff", "you"): SignalSpec(
        label="Free creatures",
        avenue="0-cost creatures (cast for no mana) to trigger the payoff",
        search={"card_type": "Creature", "cmc_max": 0},
        serve=Serve(
            all_of=(
                Serve(types=frozenset({"creature"})),
                Serve(mana_cost=re.compile(r"^\{0\}$")),
            )
        ),
    ),
    # Mass-death payoff (Tobias, Nevinyrral, Gadrak, Mahadi): a reward that SCALES with
    # creatures dying this turn wants board wipes (force the big turn) + mass-reanim
    # (refill after). The "for each ... died this turn" floor detector opens it; the
    # serve is wipes + whole-graveyard reanimation (single-target Reanimate excluded —
    # that's the reanimator lane, not a board refill).
    ("mass_death_payoff", "you"): _spec(
        "Mass-death payoff",
        "board wipes that force a mass-death turn, plus mass-reanimation to refill the "
        "board after",
        {"oracle": _MASS_DEATH_PAYOFF_ORACLE},
        _MASS_DEATH_PAYOFF_ORACLE,
    ),
    # Per-target payoff (Hinata): the discount scales with target count, so serve spells
    # whose target count is VARIABLE — "any number of targets" (Aurelia's Fury) and
    # "X target" spells (Distorting Wake). A single fixed-target removal (Doom Blade) is
    # only a {1} discount, not the payoff, so it isn't credited.
    ("per_target_payoff", "you"): _spec(
        "Multi-target spells",
        "variable / X-target spells whose per-target discount compounds (any number of "
        "targets, X target permanents)",
        {"oracle": _MULTI_TARGET_ORACLE},
        _MULTI_TARGET_ORACLE,
    ),
    # Ability-strip targets (Abigale): big creatures with a crippling drawback she
    # strips then buffs. ANDs the drawback clause with power >= 5 (Serve.all_of), so a
    # big vanilla beater (no drawback) and a small drawback creature are both excluded.
    ("ability_strip_payoff", "you"): SignalSpec(
        label="Ability-strip targets",
        avenue="big creatures whose crippling drawback gets stripped, then buffed into "
        "a beater",
        search={"oracle": _CRIPPLING_DRAWBACK_ORACLE},
        serve=Serve(
            all_of=(
                Serve(oracle=re.compile(_CRIPPLING_DRAWBACK_ORACLE, _IC)),
                Serve(power_min=5),
            )
        ),
    ),
    # Arcane tribal (The Unspeakable + the Kamigawa Kirins / Spiritcraft legends): the
    # Arcane-subtype instants & sorceries (CR 205.3k) the commander recurs / pays off,
    # plus the splice-onto-Arcane cards that ride them.
    ("arcane_matters", "you"): _spec(
        "Arcane spells",
        "Arcane-subtype instants and sorceries (Kamigawa) plus splice-onto-Arcane",
        {"card_type": "Arcane"},
        r"splice onto arcane",
        serve_types=("arcane",),
    ),
    # Enlist (Aradesh): other enlist creatures (the keyword bearers) plus the big
    # stay-back fodder to tap for their power.
    ("has_enlist", "you"): _spec(
        "Enlist",
        "enlist creatures plus big stay-back fodder to tap for their power",
        {"oracle": r"\benlist\b"},
        r"\benlisted? (?:a|another) creature",
        serve_keywords=("enlist",),
        extras=(_ENLIST_FODDER_EXTRA,),
    ),
    # Power-scaling tap engine (Mona Lisa, Marwyn, Selvala, Alena): UNTAP effects re-tap
    # the engine for another payoff; ranking surfaces the repeatable untappers first.
    ("power_tap_engine", "you"): _spec(
        "Untap effects",
        "untap effects that re-tap the power-scaling ability for another activation",
        {"oracle": r"untap (?:another )?target (?:creature|permanent)|\buntap it\b"},
        r"untap (?:another )?target (?:creature|permanent)|\buntap it\b"
        r"|untap all [^.]*you control",
    ),
    # Recastable ETB aggressors (Oroku Saki + the TMNT Sneak legends): cheap creatures
    # whose ENTER trigger bleeds opponents (each opponent discards / loses life), so
    # bouncing and recasting them repeats the bleed. The aggressive-ETB subset is the
    # precise recast payoff (color identity filters it per commander) — NOT every ETB
    # creature, which would be goodstuff.
    ("recast_etb", "you"): _spec(
        "Recastable ETB aggressors",
        "cheap creatures whose enter-trigger bleeds opponents, to bounce and recast",
        {"oracle": r"when[^.]*enters[^.]*each opponent (?:discards|loses|sacrifices)"},
        r"when[^.]*enters[^.]*each opponent (?:discards|loses|sacrifices)",
    ),
    # Exert (Johan, Heliod God of the Sun): when your team has vigilance / never taps to
    # attack, an exert creature's only downside (won't untap) vanishes, so serve the
    # exert creatures (the Scryfall keyword is the precise gate).
    ("exert_matters", "you"): _spec(
        "Exert",
        "exert creatures — their 'won't untap' cost is free when your team doesn't tap",
        {"oracle": r"\bexert\b"},
        r"you may exert this creature",
        serve_keywords=("exert",),
    ),
    # Target redirect (Rayne draws when an opponent targets your stuff): shunt the
    # opponent's spell onto a cheap permanent so you still draw but the real target is
    # safe (Spellskite, Misdirection, Bolt Bend).
    ("target_redirect", "you"): _spec(
        "Target redirection",
        "redirect an opponent's spell onto a cheap permanent (still triggers, stays "
        "safe)",
        {
            "oracle": r"change (?:a|the) target of target spell"
            r"|change (?:that|the) spell'?s target to"
            r"|choose new targets for target"
        },
        # task B-4: the choose-new-targets-for-target template (Deflecting
        # Swat, Wild Ricochet) was a verified serve gap; Fork's "for the
        # copy" cannot match the \btarget\b-anchored form (CR 707.10c).
        _REDIRECT_SERVE_ORACLE,
        serve_idents=frozenset({"spell_redirect|you|"}),
    ),
    # task B-4: the DOER side (split from the payoff key above per the
    # counter_control precedent) — deck-side key when the deck already runs
    # redirect instruments.
    ("spell_redirect", "you"): _spec(
        "Spell redirection",
        "redirect effects that turn opponents' targeted spells into blowouts "
        "or protection (Wild Ricochet, Bolt Bend)",
        {
            "oracle": r"change (?:a|the) target of target spell"
            r"|choose new targets for target"
        },
        _REDIRECT_SERVE_ORACLE,
        serve_idents=frozenset({"spell_redirect|you|"}),
    ),
    # Free-spell storm (Thrasta): cost drops per spell cast this turn, so it wants FREE
    # (0-cost) NONLAND spells to chain. all_of(cmc<=0, spell-type) excludes 0-mv basics
    # (a land is not a spell cast).
    ("free_spell_storm", "you"): SignalSpec(
        label="Free spells",
        avenue="0-cost spells to chain so the commander's cost keeps dropping",
        search={"cmc_max": 0},
        serve=Serve(
            all_of=(
                Serve(cmc_max=0),
                Serve(
                    types=frozenset(
                        {
                            "instant",
                            "sorcery",
                            "artifact",
                            "creature",
                            "enchantment",
                            "planeswalker",
                        }
                    )
                ),
            )
        ),
    ),
    # Scavenge fuel (Varolz): scavenge turns a graveyard creature's POWER into +1/+1
    # counters, so it wants the highest-power creatures as the biggest payloads.
    ("scavenge_fuel", "you"): _spec(
        "High-power scavenge fuel",
        "high-power creatures to scavenge for big +1/+1-counter payloads",
        {"card_type": "Creature"},
        None,
        serve_power_min=7,
    ),
    # Land control / exchange (Sharkey): a land-control commander wants land-EXCHANGE
    # effects to swap a weak land for an opponent's best while it taxes the rest.
    ("land_exchange", "you"): _spec(
        "Land exchange",
        "swap control of lands to steal opponents' best while you tax the rest",
        {"oracle": r"exchange control of[^.]*\bland\b"},
        r"exchange control of[^.]*\bland\b",
    ),
    # Self-life-payment insurance (Selenia, Beledros, Vilis): a commander that pays its
    # own life repeatedly wants life-loss insurance so the payments don't kill it
    # (Phyrexian Unlife, Angel's Grace, Platinum Angel).
    ("life_payment_insurance", "you"): _spec(
        "Life-loss insurance",
        "cards that stop you losing the game from heavy self-life-payment",
        {
            "oracle": r"don'?t lose the game for having|can'?t lose the game"
            r"|your life total can'?t change"
        },
        r"don'?t lose the game for having|can'?t lose the game"
        r"|your life total can'?t change|you don'?t lose the game",
    ),
    # Target-your-own payoff (Monk Gyatso): free ways to target your own creatures so a
    # "when targeted" payoff fires on demand (en-Kor cycle, {0}-equip like Shuko).
    ("target_own_payoff", "you"): _spec(
        "Target-your-own enablers",
        "free/cheap ways to target your own creatures (en-Kor, {0}-equip)",
        {
            "oracle": r"\{0\}:[^.]*target (?:a |another )?creature you control"
            r"|equip \{0\}"
        },
        r"\{0\}:[^.]*target (?:a |another )?(?:creature|permanent) you control"
        r"|equip \{0\}",
    ),
    # Multicolor matters (Niv-Mizzet Reborn + the gold-cards commanders): the multicolor
    # PAYOFFS — "whenever you cast a multicolored spell", converge, "multicolored
    # creatures you control" — not every gold card (which would be the whole deck).
    ("multicolor_matters", "you"): _spec(
        "Multicolor payoffs",
        "cards that reward casting multicolored spells, plus converge",
        {
            "oracle": r"whenever you cast a multicolored|\bconverge\b"
            r"|multicolored (?:creature|permanent|spell)s? you"
        },
        r"whenever you cast a multicolored"
        r"|multicolored (?:creature|permanent|spell)s? you (?:control|cast)"
        r"|\bconverge\b|cast (?:a|your) multicolored",
    ),
    # A repeatable land-destruction commander (Numot) wants the LD support package:
    # more land destruction (main), own-land recursion to survive symmetric LD (reuse
    # the lands-from-graveyard extra), and land-loss PUNISHERS that turn each destroyed
    # land into damage/value (Dingus Egg, Price of Glory).
    ("land_destruction", "you"): _spec(
        "Land destruction",
        "blow up lands repeatedly — the Armageddon/Numot stax-LD plan",
        {"oracle": r"destroy (?:up to (?:one|two|three) )?target lands?"},
        r"destroy (?:up to (?:one|two|three) )?target lands?"
        r"|destroy all lands|destroy target nonbasic land"
        r"|each (?:player|opponent)[^.]*sacrifices? a land",
        extras=(
            SubAvenue(
                "Punish land loss",
                "turn every destroyed land into damage or value (Dingus Egg, "
                "Price of Glory)",
                {
                    "oracle": r"whenever a land(?: card)? is put into a graveyard"
                    r"|whenever a player taps a land[^.]*destroy"
                },
            ),
            _LANDS_FROM_GRAVE_EXTRA,
        ),
    ),
    # A cheat-from-top commander (Vaevictis, Hans Eriksson) reveals its top card and
    # puts a permanent into play, so it wants to STACK its top with a bomb: graveyard-
    # to-top recursion and deliberate put-on-top effects choose what gets cheated in.
    ("cheat_from_top", "you"): _spec(
        "Stack your top",
        "put a bomb on top of your library to be cheated in — graveyard-to-top "
        "recursion and put-on-top effects",
        {"oracle": _GY_TO_TOP_ORACLE},
        _GY_TO_TOP_ORACLE
        + r"|put (?:a|two|three|\w+) cards? from your hand on top of your library"
        + r"|on top of your library in any order",
    ),
    # A repeatable creature-KILLER (Diaochan {T}-destroy, Visara, Kalitas) is an
    # aristocrats-style death engine with no sac outlet of its own: every kill it makes
    # fires on-death payoffs. Serve the drain/damage payoffs (Blood Artist, Zulaport,
    # Vicious Shadows) only — NOT the full aristocrats kit (fodder/sac outlets), which a
    # control-removal commander doesn't want.
    ("kill_engine", "you"): _spec(
        "Death payoffs",
        "your repeatable creature kills fire on-death drain/damage every turn — "
        "Blood Artist, Zulaport Cutthroat, Vicious Shadows",
        {"oracle": _KILL_DRAIN_ORACLE},
        _KILL_DRAIN_ORACLE,
    ),
    # Phasing-lands (Taniwha): your lands phase back each turn, so symmetric land-denial
    # stax (Mana Breach / Overburden — every player bounces/sacs a land) hits opponents
    # permanently while you recover. Asymmetric land denial.
    ("land_denial", "you"): _spec(
        "Land denial",
        "symmetric land-bounce/sac stax that hits opponents while your lands phase",
        {
            "oracle": r"whenever a player[^.]*(?:returns? a land|sacrifices? a land)"
            r"|that player (?:returns?|sacrifices?) a land"
        },
        r"whenever a player[^.]*(?:returns? a land|sacrifices? a land)"
        r"|that player (?:returns?|sacrifices?) a land"
        r"|each player sacrifices a land",
    ),
    # Cast-from-hand-or-lose (Phage): negate the drawback — command-zone-to-hand so it's
    # cast normally, "can't lose the game" backstops, and "ETBs don't trigger" silences
    # the lose-trigger when the commander is cheated into play.
    ("lose_unless_hand", "you"): _spec(
        "Drawback negation",
        "command-zone-to-hand, can't-lose, and ETB-silencers for a cast-from-hand-or-"
        "lose commander",
        {
            "oracle": r"can'?t lose the game|into your hand from the command zone"
            r"|creatures entering[^.]*don'?t (?:cause|trigger)"
        },
        r"can'?t lose the game|into your hand from the command zone"
        r"|from the command zone[^.]*your hand"
        r"|creatures entering[^.]*don'?t (?:cause|trigger)"
        r"|abilities (?:don'?t|do not) trigger",
    ),
    # Land protection (Noyan Dar, Kamahl, the Tophs): a land-animation commander's
    # creature-lands die to creature removal / wraths / land destruction, so it wants
    # indestructible-lands, untargetable-lands, and land recursion to keep them.
    ("land_protection", "you"): _spec(
        "Land protection",
        "keep your animated lands alive: indestructible, untargetable, land recursion",
        {
            "oracle": r"all lands[^.]*indestructible|lands?[^.]*can'?t be[^.]*target"
            r"|lands?[^.]*hexproof"
        },
        r"lands?[^.]*(?:have|gain|with)[^.]*indestructible|all lands[^.]*indestructible"
        r"|lands?[^.]*can'?t be[^.]*target|lands?[^.]*hexproof"
        r"|whenever[^.]*causes? a land[^.]*graveyard",
    ),
    # Newly-entered attacker payoff (Samut): wants HASTE + ETB-pump anthems so a
    # creature that entered this turn can attack at once for value. Ogre Battledriver /
    # Primal Forcemage pump entering creatures; mass-haste lets them swing.
    ("entered_attacker", "you"): _spec(
        "Haste + ETB pump",
        "haste and enter-trigger pump so freshly-entered creatures attack at once",
        {
            "oracle": r"creature you control enters[^.]*(?:gets? \+|gains? haste|and "
            r"haste)|creatures you control (?:get|have|gain)[^.]*haste"
        },
        r"(?:another |a )?creature you control enters[^.]*(?:gets? \+|gains? haste|and "
        r"haste)|creatures you control (?:get|have|gain)[^.]*haste",
    ),
    # ADR-0034 _matters sweep — island lane split by role.
    # island_makers (the islandwalk DOER side — islandwalk bearers / granters /
    # token-makers): wants more islandwalk granters plus effects that turn opponents'
    # lands into Islands (so islandwalk connects), and island-count payoffs.
    ("island_makers", "you"): _spec(
        "Islandwalk makers",
        "islandwalk granters plus make opponents' lands Islands so it connects",
        {
            "oracle": r"lands?[^.]*are islands|becomes? an island|flood counter"
            r"|\bislandwalk\b"
        },
        r"(?:nonbasic |all )?lands?[^.]*are islands|becomes? an island|flood counter"
        r"|\bislandwalk\b|number of islands",
    ),
    # island_matters (the Zhou Yu cares-about-Islands PAYOFF side): effects that turn
    # opponents' lands into Islands so the attack restriction is met, plus island-count
    # payoffs. Quicksilver Fountain (flood counters → Islands) and Stormtide Leviathan
    # ("All lands are Islands") feed it; a mana dork does not.
    ("island_matters", "you"): _spec(
        "Island matters",
        "make opponents' lands Islands so the attack restriction is met",
        {"oracle": r"lands?[^.]*are islands|becomes? an island|flood counter"},
        r"(?:nonbasic |all )?lands?[^.]*are islands|becomes? an island|flood counter"
        r"|number of islands",
    ),
    # Tap down blockers (Tromokratis): effects that tap OPPONENTS' creatures (Sleep,
    # Blustersquall) so the defender can't field enough blockers, letting the
    # "unblockable unless all block" commander through.
    ("tap_down_blockers", "you"): _spec(
        "Tap down blockers",
        "effects that tap opponents' creatures so they can't all block",
        {
            "oracle": r"tap all creatures (?:target|that|defending) player"
            r"[^.]*control|tap target creature you don'?t control"
        },
        r"tap all creatures (?:target|that|defending) player[^.]*control"
        r"|tap all creatures target opponent[^.]*control"
        r"|tap target creature you don'?t control"
        r"|tap all creatures you don'?t control",
    ),
    # ltb_matters: VETO the O-Ring exile-until-leaves removal (Banishing Light) — that
    # already routes to exile_until_leaves, so excluding it here is lossless.
    # ADR-0027 β: ltb_matters migrated to the Card IR (a structural `leaves`-trigger arm
    # + a narrowed _LTB_MATTERS_MIRROR, SIDECAR v11). This serve spec was always hand-
    # registered with its own curated SEARCH regex + serve_not O-Ring veto, independent
    # of the deleted SWEEP detector, so it survives unchanged. CR 603.6e.
    ("ltb_matters", "you"): _spec(
        "Leaves-the-battlefield",
        "sacrifice and blink fodder to trigger LTB",
        {
            "oracle": (
                r"left the battlefield[^.]*this turn"
                r"|whenever [^.]*(?:leaves|leave) the battlefield"
                r"|when [^.]* leaves the battlefield"
            )
        },
        r"a permanent (?:you controlled )?left the battlefield"
        r"|whenever [^.]*(?:leaves the battlefield|leave the battlefield)"
        r"|when [^.]* leaves the battlefield",
        serve_not=r"exile [^.]*until [^.]*leaves the battlefield",
        # Flicker your own permanents to FIRE the LTB trigger (and a fresh ETB) on
        # demand — the "blink fodder" the blurb promises (Ghostly Flicker / Eerie
        # Interlude). Reuses the precise flicker classifier. Death (dies) is also an LTB
        # event (CR 603.6c), so dies-recursion is offered as its own avenue too.
        extras=(_FLICKER_EXTRA, _DIES_RECURSION_EXTRA),
    ),
    # ── Keyword-coverage audit (CR 702/701) keyword[]-anchored avenues ──────────
    # Serve the keyword[] bearers via serve_keywords (Scryfall's authoritative field —
    # maximally precise, never matches reminder text) plus the payoff/grant phrasing.
    ("madness_matters", "you"): _spec(
        "Madness",
        "madness cards (discard them to cast for their madness cost) plus the discard "
        "outlets and madness-granters that enable the loop",
        {"oracle": r"\bmadness\b"},
        r"\bmadness\b|if it has madness",
        serve_keywords=("madness",),
    ),
    # ADR-0034 _matters sweep: the MAKER side of the speed split. speed_makers
    # fires when a card PERFORMS/advances the speed mechanic (Start-your-engines,
    # the keyword-less speed-changer). The avenue it opens is the engine that
    # advances your speed — the your-turn life-loss sources (cheap evasive
    # attackers that chip an opponent each turn).
    ("speed_makers", "you"): _spec(
        "Speed engine",
        "Start-your-engines and speed-advancer bodies, plus the your-turn "
        "life-loss sources that advance your speed",
        {"oracle": r"start your engines|your speed"},
        r"start your engines|your speed",
        serve_keywords=("start your engines!",),
        extras=(_CHEAP_EVASION_EXTRA,),
    ),
    # ADR-0034 _matters sweep: the PAYOFF side. speed_matters keeps the Max-speed
    # abilities, which only function at speed 4 (they care-about having reached
    # max speed and advance nothing).
    ("speed_matters", "you"): _spec(
        "Max speed",
        "Max-speed payoffs that reward reaching speed 4",
        {"oracle": r"max speed"},
        r"max speed",
        serve_keywords=("max speed",),
    ),
    ("discover_makers", "you"): _spec(
        "Discover",
        "discover sources to dig for free, plus low-mana-value nonland spells worth "
        "flipping into",
        {"oracle": r"\bdiscover \d|\bdiscover x\b"},
        r"\bdiscover \d|\bdiscover x\b|whenever you discover",
        serve_keywords=("discover",),
    ),
    # ADR-0027 / _matters sweep (ADR-0034): the Foretell lane migrated to the Card IR
    # and then SPLIT into foretell_makers (the `foretell` keyword bearers + grant /
    # "to foretell" enabler markers that PERFORM the mechanic) and foretell_matters
    # (the Foretold-card payoffs — Niko Defies Destiny). Both serve the SAME foretell
    # pool (the avenue composes maker + payoff), so both reuse the same oracle regex.
    ("foretell_makers", "you"): _spec(
        "Foretell",
        "foretell cards to bank in exile plus enablers that let you foretell",
        {"oracle": r"\bforetell\b|foretold"},
        r"\bforetell\b|foretold",
        serve_keywords=("foretell",),
    ),
    ("foretell_matters", "you"): _spec(
        "Foretell",
        "foretell cards to bank in exile plus the payoffs that reward foretold cards",
        {"oracle": r"\bforetell\b|foretold"},
        r"\bforetell\b|foretold",
        serve_keywords=("foretell",),
    ),
    ("has_undying_persist", "you"): _spec(
        "Undying / Persist",
        "Undying and Persist bodies (free, repeatable death-return fodder) plus the "
        "anthems and grants that hand out the keyword",
        {"oracle": r"\b(?:undying|persist)\b"},
        r"\b(?:undying|persist)\b|(?:have|gain|gains|with) (?:undying|persist)",
        serve_keywords=("undying", "persist"),
    ),
    # ── Two-regex payoff avenues (serve = the broad axis, search = enabler pool) ──
    ("minus_counters_matter", "you"): _spec(
        "-1/-1 counters",
        "Wither/Infect bearers and -1/-1 placers plus the payoffs that reward a board "
        "shrinking under -1/-1 counters (Hapatra, Necroskitter, Nest of Scarabs)",
        {"oracle": r"-1/-1 counter"},
        r"-1/-1 counter",
        serve_keywords=("wither", "infect"),
    ),
    ("cycling_matters", "you"): _spec(
        "Cycling",
        "cycling cards to churn through your deck plus the payoffs that reward each "
        "cycle (Astral Slide, Drake Haven, Faith of the Devoted)",
        {"preset_names": ("cycling",)},
        r"whenever you cycle|cycles? or discard"
        r"|whenever (?:a player|another player) cycles",
        serve_keywords=("cycling",),
    ),
    ("kicked_spell_matters", "you"): _spec(
        "Kicked spells",
        "kicker/multikicker spells plus the payoffs that trigger on casting a kicked "
        "spell (Verazol, Hallar, Rumbling Aftershocks)",
        {"oracle": r"\bkicker\b|\bkicked\b"},
        r"whenever you cast a kicked spell|if (?:that|it) (?:spell )?was kicked",
        serve_keywords=("kicker", "multikicker"),
    ),
    # colorless-hate counterspells ("Counter target colorless spell" — Ceremonious
    # Rejection, Consign to Memory) match the oracle arm but are NOT payoffs: veto them.
    ("colorless_matters", "you"): _spec(
        "Colorless / Eldrazi",
        "Devoid and Eldrazi colorless bodies plus the anthems, cost reducers, and "
        "cast-triggers that reward casting colorless creatures and spells",
        {"oracle": r"colorless (?:creature|spell|permanent)"},
        r"colorless (?:creature|spell|permanent)s?",
        serve_keywords=("devoid",),
        serve_types=("eldrazi",),
        serve_not=r"counter target colorless",
    ),
    # ADR-0027 #24n G1 — base_power_matters (NEW niche lane). The payoffs that REWARD /
    # SCALE WITH / SELECT creatures by their BASE power or toughness (CR 613.4b refer,
    # not set): Bess Soul Nourisher's 1/1 ETB count, Zinnia's base-power-1 go-wide
    # scale, Duskana's draw-per base-2/2, Primo's base-0 combat trigger, Rapid
    # Augmenter's base-1 haste grant, Sword of the Squeak's equip scale. SERVE/SEARCH on
    # the base-reference grammar (a base-power/toughness count/condition); the kept
    # word mirror retired in favor of the structural `BasePtRef` read.
    ("base_power_matters", "you"): _spec(
        "Base power/toughness",
        "the small base-P/T tribe — anthems and triggers that reward creatures by "
        "their base power or toughness (Bess, Zinnia, Duskana, Primo, Rapid Augmenter, "
        "Sword of the Squeak)",
        {"oracle": r"with base (?:power|toughness)"},
        r"with base (?:power|toughness)",
    ),
    ("exalted_lone_attacker", "you"): _spec(
        "Exalted / lone attacker",
        "Exalted enablers plus the payoffs that reward a single attacker connecting "
        "(Rafiq, Sublime Archangel, Angelic Exaltation)",
        {"oracle": r"attacks alone|\bexalted\b"},
        r"attacks alone",
        serve_keywords=("exalted",),
    ),
    # ADR-0034 _matters sweep SPLIT: the MAKER side of the old flash_matters — the
    # flash-GRANTERS (cast your spells as though they had flash — Leyline of
    # Anticipation, Vedalken Orrery, Yeva) plus flash creatures to ambush-cast.
    ("flash_makers", "you"): _spec(
        "Flash",
        "flash creatures to ambush-cast plus the flash-granters that build the deck "
        "around instant-speed play",
        {"preset_names": ("flash",)},
        r"cast[^.]{0,60}spells?[^.]{0,30}as though they had flash",
        serve_keywords=("flash",),
    ),
    # ADR-0034 _matters sweep SPLIT: the PAYOFF side — the opponent-turn cast triggers
    # that reward instant-speed play (Alela). Same flash serve pool as flash_makers.
    ("flash_matters", "you"): _spec(
        "Flash",
        "opponent-turn cast payoffs plus flash creatures and granters that build the "
        "deck around instant-speed play",
        {"preset_names": ("flash",)},
        r"whenever you cast (?:a |your first )?spells? "
        r"during (?:an|each|any) opponent",
        serve_keywords=("flash",),
    ),
    ("team_evasion_grant", "you"): _spec(
        "Team evasion grant",
        "effects that hand an evasion keyword (menace / fear / flying / can't be "
        "blocked) to your whole board for a go-wide alpha strike",
        {
            "oracle": r"creatures you control (?:gain|have)[^.]{0,40}?"
            r"(?:menace|fear|intimidate|horsemanship|flying|can't be blocked)"
        },
        r"(?:other |attacking )?creatures you control (?:gain|have)\b"
        r"[^.]{0,40}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk"
        r"|flying|can't be blocked)\b"
        r"|(?:other |attacking )?creatures you control[^.]*can't be blocked",
    ),
    # Override the auto-registered saga_matters sweep spec: surface the FULL Saga pool
    # via a subtype search (the sweep spec only found lore-counter cards), and serve the
    # Sagas (serve_types) plus the lore-counter/chapter payoffs (Tom Bombadil, Narci).
    ("saga_matters", "you"): _spec(
        "Sagas",
        "Sagas to chain chapter abilities, plus the lore-counter and chapter-retrigger "
        "payoffs that reward them",
        {"card_type": "Saga"},
        r"lore counter|sagas? you control|chapter abilit|read ahead",
        serve_types=("saga",),
    ),
    ("lessons_matter", "you"): _spec(
        "Lessons",
        "Lesson spells (your wishboard payload) plus the Learn enablers and Lesson "
        "payoffs that reward casting them",
        {"card_type": "Lesson"},
        r"lesson spells?|cast (?:an? )?(?:artifact or )?lesson|lesson card",
        serve_types=("lesson",),
    ),
    # Override the auto-registered suspend_matters sweep spec (serve was `\bsuspend\b`
    # only): widen to the whole time-counter superstructure — Suspend (702.62),
    # Vanishing (702.63), Impending, and time-counter/time-travel manipulation (701.56).
    ("suspend_matters", "you"): _spec(
        "Suspend / time counters",
        "suspend, vanishing, and impending cards plus the time-counter manipulators "
        "and payoffs (As Foretold, Jhoira, Dust of Moments) that exploit them",
        {"oracle": r"\bsuspend\b|time counter"},
        r"\bsuspend\b|\bvanishing\b|\bimpending\b|time counter|time travel"
        # Suspend removes a TIME counter each upkeep (CR 702.62), so extra upkeeps /
        # beginning phases (Paradox Haze, Sphinx of the Second Sun) accelerate it.
        r"|additional upkeep step|additional beginning phase"
        # Counter-manipulation that references suspended cards (Clockspinning, Dust of
        # Moments, Timebender) — direct suspend support, generic "counter" not "time".
        r"|suspended cards?",
        serve_keywords=("suspend", "vanishing", "impending"),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the suspend split — cards that
    # PERFORM suspend (the keyword bearers: Ancestral Vision, Aeon Chronicler). The
    # avenue it opens is more suspend bodies plus the time-counter accelerators that
    # cash them in early; the broad serve overlaps suspend_matters (ADR-0034: a serve
    # avenue legitimately combines makers + payoffs + targets).
    ("suspend_makers", "you"): _spec(
        "Suspend (makers)",
        "cards that suspend themselves plus the time-counter accelerators that cast "
        "them early (Paradox Haze, Jhoira)",
        {"oracle": r"\bsuspend\b|time counter"},
        r"\bsuspend\b|time counter|time travel"
        r"|additional upkeep step|additional beginning phase",
        serve_keywords=("suspend",),
    ),
    ("saddle_matters", "you"): _spec(
        "Saddle / Mounts",
        "Mounts to ride plus the cheap wide creatures that pay the Saddle cost and the "
        "attacks-while-saddled payoffs (Calamity, Gitrog Ravenous Ride)",
        {"oracle": r"\bsaddle\b|\bsaddled\b|\bmount\b"},
        r"\bsaddled\b|whenever you saddle|while saddled",
        serve_keywords=("saddle",),
    ),
    ("suspect_makers", "you"): _spec(
        "Suspect makers",
        "cards that suspect creatures (menace + can't block) to fuel your "
        "suspected-creature payoffs",
        {"oracle": r"\bsuspect\b"},
        r"\bsuspects?\b",
    ),
    ("suspect_matters", "you"): _spec(
        "Suspect payoffs",
        "payoffs that reward having suspected creatures",
        {"oracle": r"\bsuspected\b"},
        r"\bsuspected\b",
    ),
    # ADR-0027: cmdzone_ability had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a 'command' ability-zone / condition-zone
    # structural arm + a kept word mirror for the static-Eminence cost-reducer). The
    # SERVE pool stays oracle-defined, so hand-register the spec the sweep auto-
    # register loop used to build, reusing the deleted regex.
    ("cmdzone_ability", "you"): _spec(
        *SWEEP_LABELS["cmdzone_ability"],
        {
            "oracle": (
                r"is (?:on the battlefield or )?in the command zone"
                r"|activate this ability only if[^.]*command zone"
            )
        },
        (
            r"is (?:on the battlefield or )?in the command zone"
            r"|activate this ability only if[^.]*command zone"
        ),
    ),
}
