"""Signal specs data slice 2/4: SPECS dict entries (lines 3417-4562 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

from mtg_utils._deck_forge._sweep_detectors import (
    COMBAT_DAMAGE_TO_CREATURE_REGEX,
    COMBAT_DAMAGE_TO_OPP_REGEX,
    SWEEP_LABELS,
    UNSPENT_MANA_REGEX,
    VOID_WARP_MAKERS_REGEX,
    VOID_WARP_MATTERS_REGEX,
)

from ._shared import (
    _COMBAT_SUPPORT_EXTRA,
    _COST_REDUCER_EXTRA,
    _COUNTERS_PACKAGE,
    _DAMAGE_AMPLIFIER_EXTRA,
    _DEATHTOUCH_GEAR_EXTRA,
    _DIG_UNTIL_SWEEP_REGEX,
    _DISCARD_OUTLET_SWEEP_REGEX,
    _DRAW_FOR_EACH_SWEEP_REGEX,
    _ETB_PAYOFF_EXTRA,
    _EXTRA_COMBAT_EXTRA,
    _GOWIDE_ANTHEM_EXTRA,
    _IMPULSE_SWEEP_REGEX,
    _LANDFALL_ORACLE,
    _LANDS_FROM_GRAVE_EXTRA,
    _LOYALTY_DOUBLER_EXTRA,
    _MANA_AMP_EXTRA,
    _ONE_PUNCH_ORACLE,
    _OPP_LIBRARY_THEFT_ORACLE,
    _PARADOX_PAYOFF_EXTRA,
    _PILLOWFORT_EXTRA,
    _PUMP_EXTRA,
    _STEAL_CAST_ORACLE,
    _SYM_MANA_EXTRA,
    _THEFT_SWEEP_REGEX,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_EXTRA,
    _TOPDECK_SELECTION_SWEEP_REGEX,
    _TYPE_CHANGER_ORACLE,
    _VOLTRON_PROTECT_EXTRA,
    SignalSpec,
    _spec,
    _sweep_spec_with_extras,
)

SPECS_2: dict[tuple[str, str], SignalSpec] = {
    # ── Rules mined from the zero-signal commander tail ─────────────────────────
    # Serve the payoff trigger (CR 510 combat damage) + true-unblockable enablers. The
    # bare `\bmenace\b` matched every menace creature AND the menace/flying REMINDER
    # "can't be blocked except by …" — surfacing vanilla evasive bodies, not connect
    # payoffs. Drop it; gate `can't be blocked` against the "except" reminder.
    ("combat_damage_matters", "opponents"): _spec(
        "Combat damage",
        "evasive attackers and extra-combat enablers to keep connecting",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals combat damage to (?:a player|an opponent|one of your opponents"
        r"|each opponent)|can't be blocked(?! except)|\bunblockable\b",
        # A combat-damage-trigger commander needs to CONNECT and survive: gear to suit
        # up (Ojutai), instant pump to push through / survive blocks (Benton), and extra
        # combats to multiply the trigger (Neheb -> Relentless Assault, Seize the Day).
        extras=(_COMBAT_SUPPORT_EXTRA, _PUMP_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted, so the serve hand-spec passes the pinned
    # COMBAT_DAMAGE_TO_OPP_REGEX (the EXACT deleted regex) so serve / mirror
    # never drift.
    ("combat_damage_to_opp", "opponents"): _sweep_spec_with_extras(
        "combat_damage_to_opp",
        (
            _COMBAT_SUPPORT_EXTRA,
            _PUMP_EXTRA,
            _DAMAGE_AMPLIFIER_EXTRA,
            _EXTRA_COMBAT_EXTRA,
        ),
        regex=COMBAT_DAMAGE_TO_OPP_REGEX,
    ),
    # ADR-0027 β: combat_damage_to_creature migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted (the auto-loop used to register a plain spec —
    # search == serve == its regex, no extras). Hand-register the byte-identical
    # plain spec reusing the pinned regex so the avenue resolves exactly as before
    # (connect-with-creatures payoffs — Ohran Viper, the basilisks, Toxin Sliver).
    ("combat_damage_to_creature", "any"): _spec(
        *SWEEP_LABELS["combat_damage_to_creature"],
        {"oracle": COMBAT_DAMAGE_TO_CREATURE_REGEX},
        COMBAT_DAMAGE_TO_CREATURE_REGEX,
    ),
    # Group-mana commanders (Shizuko, Yurlok) want symmetric mana-doublers / punishers +
    # join-forces ramp beyond the bare "each player adds {" the sweep regex credits.
    # Unspent-mana commander (Omnath, Kruphix) keeps mana between steps -> wants mana
    # amplification (untap-all-lands + doublers) to bank more. The sweep's bare "unspent
    # mana" serve credited none; promote it to a hand-spec with the amp extra.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a kept-mirror — its
    # SWEEP_DETECTORS row is deleted, so pass the EXACT deleted regex via ``regex=``
    # (pinned as UNSPENT_MANA_REGEX) so the serve search/serve pool never drifts.
    ("unspent_mana", "you"): _sweep_spec_with_extras(
        "unspent_mana",
        (_MANA_AMP_EXTRA,),
        regex=UNSPENT_MANA_REGEX,
    ),
    # ADR-0027: group_mana migrated to the Card IR — its SWEEP_DETECTORS row is deleted
    # (detection moved to a non-controller-recipient discriminator on phase's ramp
    # effect raw), so hand-register the spec the sweep loop used to build, inlining the
    # deleted regex + the symmetric-mana extra.
    ("group_mana", "each"): _spec(
        *SWEEP_LABELS["group_mana"],
        {
            "oracle": (
                r"each player adds \{|that player adds \{"
                r"|the active player[^.]*adds? \{"
                r"|a player (?:loses?|losing)[^.]*mana[^.]*lose"
            )
        },
        (
            r"each player adds \{|that player adds \{"
            r"|the active player[^.]*adds? \{"
            r"|a player (?:loses?|losing)[^.]*mana[^.]*lose"
        ),
        extras=(_SYM_MANA_EXTRA,),
    ),
    # The discount-exploiting target set is defined by high cmc (structured) + X-spells
    # — not the generic words "mana value", which matched 453 cards (Disdainful Stroke,
    # Abrupt Decay). Drop that branch; gate on cmc (expensive bombs) + {x} + storm.
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount, plus more cost "
        "reducers to stack the discount",
        {"oracle": r"\{x\}|with mana value"},
        r"\{x\}|\bstorm\b",
        serve_cmc_min=7,
        extras=(_COST_REDUCER_EXTRA,),
    ),
    # Cast-from-exile MATTERS: payoffs + explicit "cast/play from exile" enablers (plot,
    # suspend, "whenever you cast a spell from exile", paradox). NOT impulse draw (its
    # own avenue, the impulse_top_play sweep) and NOT play-from-top-of-library
    # (`play_from_top` below) — both are different mechanics. The "you may play … from
    # exile" branch REQUIRES the literal "from exile", so a bare impulse "you may play
    # those cards" reads as impulse, not as this payoff lane.
    ("cast_from_exile", "you"): _spec(
        "Cast-from-exile",
        "payoffs and enablers that cast or play cards from exile (plot, suspend, "
        '"whenever you cast a spell from exile")',
        {"oracle": r"from exile|\b(?:plot|suspend|foretell|rebound)\b"},
        r"spells? you cast from exile"
        r"|whenever you cast a spell from exile"
        r"|you may (?:play|cast) (?:it|that card|those cards?|them|the exiled)"
        r"[^.]*?from exile"
        r"|" + _STEAL_CAST_ORACLE + r"|\bplot\b",
        # Suspend (CR 702.62a), Foretell (702.143), Rebound (702.88a), and Plot all CAST
        # the card from exile — authoritative Scryfall keywords, not regex-from-prose.
        serve_keywords=("plot", "suspend", "foretell", "rebound"),
        extras=(_PARADOX_PAYOFF_EXTRA,),
    ),
    # Impulse (top-of-YOUR-library exile-and-play): hand-written so the serve also
    # credits the "exile then cast it for as long as it remains exiled" engines
    # (Gonti, Hostage Taker, Thief of Sanity) the bare "play those cards this turn"
    # sweep regex missed, plus the cast-from-exile PAYOFFS an impulse deck triggers by
    # casting its exiled cards (Wild-Magic Sorcerer: "the first spell you cast from
    # exile … has cascade"). Detector regex (commander side) is unchanged.
    ("impulse_top_play", "you"): _spec(
        *SWEEP_LABELS["impulse_top_play"],
        {"oracle": _IMPULSE_SWEEP_REGEX},
        _IMPULSE_SWEEP_REGEX
        + r"|"
        + _STEAL_CAST_ORACLE
        + r"|spells? you cast from exile|first spell you cast from exile"
        # The bare "Whenever you cast a spell from exile" trigger payoff (Passionate
        # Archaeologist, Nalfeshnee) the impulse deck fires by casting its exiled cards.
        + r"|whenever you cast a spell from exile",
        # Paradox payoffs (Keeper of Secrets) — casting from exile IS from-anywhere-
        # other-than-hand, so an impulse deck triggers them too.
        extras=(_PARADOX_PAYOFF_EXTRA,),
    ),
    # X-spells matter (CR 107.3 / 202.1): an X-matters commander (Zaxara, Rosheen,
    # Zimone) is built from spells whose printed mana cost contains {X} and wants the
    # X-doublers / copy-the-X-spell payoffs (Unbound Flourishing). The serve credits
    # {X}-cost cards via the structured mana_cost dimension (the X-spells themselves)
    # PLUS oracle X-payoffs. A broad but genuinely on-theme pool — an X deck wants the
    # universe of X-spells, so breadth here is coverage, not noise.
    ("xspell_matters", "you"): _spec(
        "X spells",
        "X-spells (cards with {X} in their cost) plus the X-doublers and "
        "copy-the-X-spell payoffs an X-matters deck is built around",
        {
            "oracle": r"\{X\} in (?:its|their) (?:mana )?cost"
            r"|cost (?:that )?contains \{X\}"
        },
        r"\{x\} in (?:its|their) (?:mana )?cost"
        r"|cost (?:that )?contains? \{x\}"
        r"|spells? you cast with \{x\}",
        serve_mana_cost=r"\{X\}",
        # task B-6: the X-DOUBLERS the avenue text always promised, delivered
        # structurally — a mana amplifier (Mana Reflection, Nyxbloom Ancient,
        # Zendikar Resurgent, Doubling Cube, Crypt Ghast) has neither an {X}
        # cost nor the copy prose, so Mana Reflection under Zaxara ranked as
        # filler (the 2026-07-16 study's adjudicated gap). Implements the
        # big_mana ledgered call ("Dan: big-mana-generators -> X-spells"):
        # generators serve the X lane, never the sinks lane. Symmetric
        # doublers (Mana Flare) ride too — on-theme for an X deck, which
        # spends the shared mana better.
        serve_idents=frozenset({"mana_amplifier|you|"}),
    ),
    # Theft (steal an OPPONENT's cards and cast them): serve credits the opponent-
    # library dig (Gonti, Black Cat, Thief of Sanity) and the steal-and-cast engines
    # (Hostage Taker). Opponent-anchored / "remains exiled"-anchored so a self-impulse
    # engine (Valakut Exploration — your own library, "until end of next turn") stays
    # out. Detector regex unchanged.
    ("theft_makers", "opponents"): _spec(
        *SWEEP_LABELS["theft_makers"],
        {"oracle": _THEFT_SWEEP_REGEX},
        _THEFT_SWEEP_REGEX
        + r"|"
        + _OPP_LIBRARY_THEFT_ORACLE
        + r"|"
        + _STEAL_CAST_ORACLE,
    ),
    # _matters sweep (ADR-0034): the WANTS side of the theft split. wants_theft fires
    # (LOW) when the commander itself rewards casting what you don't own (a don't-own
    # payoff — Don Andres, Vaan, Gonti Canny) or steals battlefield permanents
    # (gain_control). The avenue it OPENS is the theft ENABLERS that feed that payoff —
    # the same steal-and-cast pool as theft_makers (Gonti, Hostage Taker, the impulse-
    # from-opponent engines). Same opponent-anchored serve regex; the maker/payoff split
    # is in MEMBERSHIP, the avenue legitimately offers the doers to a wants commander.
    ("wants_theft", "opponents"): _spec(
        *SWEEP_LABELS["wants_theft"],
        {"oracle": _THEFT_SWEEP_REGEX},
        _THEFT_SWEEP_REGEX
        + r"|"
        + _OPP_LIBRARY_THEFT_ORACLE
        + r"|"
        + _STEAL_CAST_ORACLE,
    ),
    # ADR-0027: void_warp_matters migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds this spec). The serve
    # pool stays oracle-defined, so it reuses the shared VOID_WARP_MATTERS_REGEX
    # constant (the EXACT deleted detector regex) — serve / kept mirror never drift.
    ("void_warp_matters", "you"): _spec(
        *SWEEP_LABELS["void_warp_matters"],
        {"oracle": VOID_WARP_MATTERS_REGEX},
        VOID_WARP_MATTERS_REGEX,
    ),
    # _matters sweep (ADR-0034) — the MAKER arm of the void_warp split: cards that
    # PERFORM/GRANT the Warp alt-cast (the keyword bearer/granter, the em-dash warp-cost
    # form, the graveyard self-cast). Same oracle-defined serve pool, reusing the shared
    # VOID_WARP_MAKERS_REGEX constant so serve / kept mirror never drift.
    ("void_warp_makers", "you"): _spec(
        *SWEEP_LABELS["void_warp_makers"],
        {"oracle": VOID_WARP_MAKERS_REGEX},
        VOID_WARP_MAKERS_REGEX,
    ),
    # Play from the TOP OF YOUR LIBRARY — Future Sight / Bolas's Citadel / Oracle of Mul
    # Daya. Casts from the LIBRARY zone (not exile), so it's its own avenue, distinct
    # from cast-from-exile and impulse. Needs a play/cast verb so look/scry/mill don't
    # match. ADR-0027 β: detection moved to the Card IR (a STATIC cast_from_zone+from:
    # library Effect over phase's TopOfLibraryCastPermission mode + a per-clause
    # mirror);
    # this SERVE pool stays oracle-defined, so the regex is pinned inline here (the
    # sweep
    # auto-register no longer builds it — its SWEEP_DETECTORS row is deleted).
    ("play_from_top", "you"): _spec(
        "Play from the top of your library",
        "engines that let you play or cast off the top of your library (Future Sight, "
        "Bolas's Citadel) — top-of-library control and extra-land effects amplify them",
        {"oracle": r"(?:play|cast)\b[^.]*?\bfrom the top of your library"},
        r"(?:play|cast)\b[^.]*?\bfrom the top of your library",
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the discard split. discard_makers
    # fires on a loot/rummage/connive OUTLET (a draw+discard co-occurrence — Faithless
    # Looting, Merfolk Looter, Windfall). The avenue it OPENS is the discard PAYOFFS
    # those outlets power ("whenever you discard …" — Containment Construct, Rielle)
    # plus more outlets (the same self-discard pool as discard_matters), so an outlet
    # engine finds its payoffs. The maker/payoff split is in MEMBERSHIP; the avenue
    # legitimately offers both.
    ("discard_makers", "you"): _spec(
        "Loot / discard outlets",
        "loot/connive/rummage outlets plus the discard payoffs they power",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard"
        r"|\bdiscard (?:x|\d+|two|three|four|all)\b",
    ),
    ("discard_matters", "you"): _spec(
        "Discard",
        "discard payoffs and the self-discard outlets that feed them",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard"
        # Self-discard OUTLETS the loot/connive forms missed: wheels ("discard all the
        # cards in your hand") and "discard X/N cards" as a cost (Turbulent Dreams,
        # Firestorm). Imperative "discard " (no trailing s) keeps forced-OPPONENT
        # discard ("target player discardS") out — the opponent_discard lane.
        r"|\bdiscard (?:x|\d+|two|three|four|all)\b",
    ),
    # Discard OUTLET commander (a loot/rummage engine): hand-written so the serve adds
    # the discard PAYOFFS it powers ("whenever you discard …" — Containment Construct,
    # Rielle, Glint-Horn Buccaneer) alongside the outlets the sweep regex already
    # credits. Detector regex unchanged (same key → auto-register skips it).
    ("discard_outlet", "you"): _spec(
        *SWEEP_LABELS["discard_outlet"],
        {"oracle": _DISCARD_OUTLET_SWEEP_REGEX},
        _DISCARD_OUTLET_SWEEP_REGEX + r"|whenever you discard",
    ),
    # ADR-0027 dig library-owner scope (SIDECAR v27): dig_until migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label / avenue
    # / oracle, reusing the shared DIG_UNTIL_REGEX constant so serve and the kept-mirror
    # detector never drift.
    ("dig_until", "you"): _spec(
        *SWEEP_LABELS["dig_until"],
        {"oracle": _DIG_UNTIL_SWEEP_REGEX},
        _DIG_UNTIL_SWEEP_REGEX,
    ),
    # ADR-0027 per-clause draw raw (SIDECAR v32): draw_for_each migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label / avenue
    # / oracle, reusing the shared DRAW_FOR_EACH_REGEX constant so serve and the
    # kept-mirror detector never drift.
    ("draw_for_each", "you"): _spec(
        *SWEEP_LABELS["draw_for_each"],
        {"oracle": _DRAW_FOR_EACH_SWEEP_REGEX},
        _DRAW_FOR_EACH_SWEEP_REGEX,
    ),
    # ADR-0027 topdeck library-owner scope (SIDECAR v28): topdeck_selection migrated to
    # the Card IR (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer
    # builds this serve). Hand-register the spec the sweep loop used to build — same
    # label / avenue / oracle, reusing the shared TOPDECK_SELECTION_REGEX constant so
    # serve and the kept-mirror detector never drift.
    ("topdeck_selection", "you"): _spec(
        *SWEEP_LABELS["topdeck_selection"],
        {"oracle": _TOPDECK_SELECTION_SWEEP_REGEX},
        _TOPDECK_SELECTION_SWEEP_REGEX,
    ),
    # Drain. The serve required "opponent" adjacent to "loses", so it MISSED the
    # keystone aristocrats drains worded "target/that player loses N life" (Blood
    # Artist, Falkenrath Noble). Add the player-loses branch; "each player" is excluded
    # to keep symmetric self-damage out of the opponents-drain avenue.
    # Serve/search widened with the past-tense "lost life this turn" THRESHOLD wording
    # (Spectacle / Rakdos payoffs — Stromkirk Bloodthief, Rakdos Lord of Riots) the
    # continuous "loses life" branches missed. Opponent-anchored so a self "you lost
    # life this turn" payoff (Ludevic) never matches.
    ("lifeloss_matters", "opponents"): _spec(
        "Drain",
        "repeatable life-drain and aristocrats payoffs",
        {
            "oracle": r"each opponent loses|target opponent loses|whenever .* dies"
            r"|(?:an? |each )?opponents? lost life this turn"
        },
        r"opponent[^.]*loses [^.]*life|whenever an opponent loses life|\bextort\b"
        r"|(?:target player|that player|a player) loses? [^.]*\blife\b"
        r"|(?:an? opponent|each opponent|opponents?|a player|each player)"
        r"(?: who)? lost life this turn"
        # Damage to a player IS life loss (CR 120.3a), so pingers / group-slug that deal
        # damage to opponents (Kessig Flamebreather, Mogis) are drain payoffs too —
        # including symmetric group-slug "that player" / "each player" (Sulfuric Vortex,
        # Roiling Vortex), a drain/aggro staple.
        r"|deals (?:\d+|x|that much) damage to "
        r"(?:each opponent|target opponent|each of your opponents"
        r"|that player|each player)",
    ),
    # The bare `pay \d+ life` matched 39 painlands/fetchlands (Blood Crypt, Sacred
    # Foundry) that are mana fixing, not a life-as-resource engine. VETO lands; keep the
    # lose-life payoff/enabler clauses.
    ("lifeloss_matters", "you"): _spec(
        "Self life-loss",
        "ways to pay or lose life on demand to fuel your payoffs, plus the life-total "
        "swaps/resets and recovery that turn a low life total into an advantage",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you (?:gain or )?lose life|you lose (?:\d+|x) life"
        r"|pay (?:\d+|x) life"
        # Life-as-a-resource payoffs (Selenia): swap/reset your low life total (Axis of
        # Mortality / Repay in Kind / Magus of the Mirror), recover it (Children of
        # Korlis), or win from it (Near-Death Experience).
        r"|exchange life totals?|life totals? becomes?|lowest life total"
        r"|gain life equal to[^.]*lost|life you(?:'ve| have)? lost this turn"
        r"|if you have [^.]*life[^.]*win the game",
        serve_not=r"\bas this land enters\b|enters tapped",
    ),
    # _matters sweep (ADR-0034): the MAKER side of the lifeloss split — cards that
    # PERFORM the life loss (a structured `lose_life` drain, a `life_payment`
    # marker, a paylife activation cost buying a non-ramp engine). The avenue still
    # offers the whole package (makers + drain/aristocrats payoffs together — ADR
    # -0034: serve is unaffected in spirit), so these specs copy the kept
    # lifeloss_matters serve content; only the role label differs. opponents = the
    # drain doers; you = the self life-as-resource doers.
    ("lifeloss_makers", "opponents"): _spec(
        "Drain (makers)",
        "repeatable life-drain doers plus the aristocrats payoffs they enable",
        {
            "oracle": r"each opponent loses|target opponent loses|whenever .* dies"
            r"|(?:an? |each )?opponents? lost life this turn"
        },
        r"opponent[^.]*loses [^.]*life|whenever an opponent loses life|\bextort\b"
        r"|(?:target player|that player|a player) loses? [^.]*\blife\b"
        r"|(?:an? opponent|each opponent|opponents?|a player|each player)"
        r"(?: who)? lost life this turn"
        r"|deals (?:\d+|x|that much) damage to "
        r"(?:each opponent|target opponent|each of your opponents"
        r"|that player|each player)",
    ),
    ("lifeloss_makers", "you"): _spec(
        "Self life-loss (makers)",
        "ways to pay or lose life on demand to fuel your payoffs, plus the life-total "
        "swaps/resets and recovery that turn a low life total into an advantage",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you (?:gain or )?lose life|you lose (?:\d+|x) life"
        r"|pay (?:\d+|x) life"
        r"|exchange life totals?|life totals? becomes?|lowest life total"
        r"|gain life equal to[^.]*lost|life you(?:'ve| have)? lost this turn"
        r"|if you have [^.]*life[^.]*win the game",
        serve_not=r"\bas this land enters\b|enters tapped",
    ),
    # Celebration (WOE): all 11 cards carry the exact phrase, so serve == open. A
    # Celebration commander floods nonland permanents each turn to switch the payoffs
    # on; the lane surfaces the other Celebration cards (Grand Ball Guest, Raging
    # Battle Mouse). Niche by design — the phrase appears nowhere else.
    ("celebration_matters", "you"): _spec(
        "Celebration",
        "ways to deploy two or more nonland permanents a turn, plus the payoffs",
        {
            "oracle": (
                r"two or more nonland permanents entered the battlefield "
                r"under your control this turn"
            )
        },
        r"two or more nonland permanents entered the battlefield "
        r"under your control this turn",
    ),
    # Tapped-creatures-matter: tap your team freely, then cash in the count (Throne of
    # the God-Pharaoh, Dragonscale General, Harvest Season) — backed by the grants that
    # make tapping safe (Masako: block while tapped; Saryth: deathtouch; Oak Street
    # Innkeeper: hexproof). \btapped excludes convoke's "untapped creatures".
    ("tapped_matters", "you"): _spec(
        "Tapped creatures matter",
        "payoffs that scale with tapped creatures, plus grants that make tapping safe",
        {
            "oracle": (
                r"number of tapped creatures you control"
                r"|\btapped creatures you control (?:have|get|gain|are|can|with)"
                r"|or more tapped creatures|for each tapped creature you control"
            )
        },
        r"number of tapped creatures you control"
        r"|\btapped creatures you control (?:have|get|gain|are|can|with)"
        r"|or more tapped creatures|for each tapped creature you control",
    ),
    # Land sacrifice (Gitrog, Titania, Slogurk): lands hitting the graveyard is the
    # payoff, so repeatable "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb)
    # are the engine. Distinct from sacrifice_outlets (which excludes "sacrifice a land"
    # — the fetchland guard) and from landfall (lands ENTERING).
    ("land_sacrifice_matters", "you"): _spec(
        "Land sacrifice",
        "repeatable sac-a-land outlets and the payoffs for lands hitting the graveyard",
        {
            "oracle": (
                r"sacrifice a land(?: card)?:"
                r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
                r"put into[^.]*graveyard"
            )
        },
        r"sacrifice a land(?: card)?:"
        r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
        r"put into[^.]*graveyard"
        r"|whenever you sacrifice (?:a|one or more|another) lands?",
    ),
    # _matters sweep (ADR-0034): the MAKER arm — cards that PERFORM the land
    # sacrifice (repeatable "Sacrifice a land:" outlets — Zuran Orb, Sylvan
    # Safekeeper — plus symmetric "each player sacrifices N lands" wraths). These
    # are the enablers a land-to-graveyard payoff deck (Gitrog, Titania) wants as
    # fuel; the leaves/dies PAYOFF trigger lives in land_sacrifice_matters above.
    ("land_sacrifice_makers", "you"): _spec(
        "Land sacrifice (makers)",
        "sac-a-land outlets and symmetric land wraths to fuel your land-to-grave"
        " payoffs",
        {
            "oracle": (
                r"sacrifice a land(?: card)?:"
                r"|each player sacrifices [^.]*land"
            )
        },
        r"sacrifice a land(?: card)?:"
        r"|each player sacrifices [^.]*land"
        r"|whenever you sacrifice (?:a|one or more|another) lands?",
    ),
    # Keyword soup (Odric Lunarch Marshal, Akroma Vision): shares many evergreen
    # keywords across the team, so it wants creatures stacked with keywords. Serve any
    # creature with >=3 evergreen keywords (Aerial Responder, Zetalpa, Danitha) — the
    # structural keyword_count_min dimension, since "has 3+ keywords" is in keywords[],
    # not prose. Only the >=5-keyword soup-sharers open it, so the broad serve is on-
    # theme breadth, not over-fire.
    ("keyword_soup_makers", "you"): _spec(
        "Keyword soup",
        "creatures stacked with evergreen keywords to share across your team",
        {"oracle": r"\b(?:flying|first strike|double strike|trample|vigilance)\b"},
        None,
        serve_keyword_count_min=3,
    ),
    # The SWEEP also fires a separate `keyword_soup` signal (Rayami absorbs keywords
    # from dead creatures; Akroma Vision / Indominus Rex share them) — same payoff, so
    # give it the same keyword-dense-creature serve, not the narrow sweep regex it'd
    # otherwise auto-register. Hand-speccing the key makes the sweep loop skip it.
    ("keyword_soup", "you"): _spec(
        "Keyword soup",
        "creatures stacked with evergreen keywords to share or absorb",
        {"oracle": r"\b(?:flying|first strike|double strike|trample|vigilance)\b"},
        None,
        serve_keyword_count_min=3,
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
        # The "number of lands" PAYOFF (Molimo's P/T) PLUS the land ramp / fetch /
        # recursion that grows the count — lands_matter is the same archetype as
        # landfall, so it wants the same enablers (reuse _LANDFALL_ORACLE). Also the
        # creature pump that scales with a basic-land subtype "you control" (Blanchwood
        # Armor, Primal Bellow) — the mono-color go-tall payoff scales the same way as
        # Molimo's own P/T. Anchored to "you control" so opponent-basic pumps
        # (Crusading Knight) stay out.
        r"the number of lands you control|for each land you control"
        r"|(?:gets?|get) \+[\dx]+/\+[\dx]+[^.]{0,40}?(?:for each|number of) "
        r"(?:plains|islands?|swamps?|mountains?|forests?) you control|"
        + _LANDFALL_ORACLE,
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # An ENGINE is recurring or bulk draw — NOT a one-shot cantrip. The serve's
    # `draw \w+ cards?` let \w+ eat the article in "draw a card", mislabeling ~753
    # one-shot cantrips (Remand, Cryptic Command) as engines — contradicting the
    # extractor's own _CARD_DRAW_RE. Mirror that: a recurring "at the beginning of …
    # draw" OR a bulk 2+ / additional draw. (Single-draw permanents like Rhystic Study
    # are surfaced by their own triggers' signals, not this avenue.)
    ("card_draw_engine", "you"): _spec(
        "Card-advantage engine",
        "protection, recursion, and payoffs for a repeatable draw engine",
        {"preset_names": ("card-draw",)},
        r"at the beginning of [^.]*\bdraws? "
        r"(?:a|an|two|three|four|five|six|seven|eight|nine|ten|x|\d+)[^.]*\bcard"
        r"|draws? (?:two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?"
        r"|draw cards equal to|draws? an additional card",
    ),
    # Drop the self-only `draws? an additional card` (it belongs to the YOU engine); the
    # EACH avenue is symmetric/group draw only.
    ("card_draw_engine", "each"): _spec(
        "Group draw / wheel",
        "symmetric draw with punisher payoffs (Nekusar-style)",
        {"oracle": r"each player draws|whenever .* draws a card"},
        r"each player[^.]*draws?|that player draws|whenever a player draws",
    ),
    # task #83 (theme-preset structural views): cantrip — a bounded single-draw
    # rider (Preordain/Opt-shaped), the crosswalk_signals._cantrip lane's key. A
    # cantrip deck wants more of the same (low-opportunity-cost card selection)
    # plus spellslinger payoffs (prowess/magecraft) that reward casting a dense
    # instant/sorcery base.
    ("cantrip", "you"): _spec(
        "Cantrips",
        "more low-opportunity-cost card selection and spellslinger payoffs",
        {"oracle": r"draws? (?:a|an additional) card"},
        r"draws? (?:a|an additional) card",
        serve_types=("Instant", "Sorcery"),
    ),
    # Serve the damage DOUBLERS the blurb already promises — replacement effects (CR
    # 701.10g) worded "deals double/twice that much damage" / "deals that much damage
    # plus" / "if a source … would deal damage … instead" (Furnace of Rath, Gratuitous
    # Violence, Torbran). The old `double the damage` literal missed all of them.
    ("direct_damage", "you"): _spec(
        "Burn / pingers",
        "repeatable direct damage — pingers, burn, and damage doublers",
        {"preset_names": ("burn",)},
        r"deals \d+ damage to any target|\{t\}[^.]*deals .*damage"
        r"|deals (?:double|twice) that (?:much )?damage|deals that much damage plus"
        r"|if a source[^.]*would deal damage[^.]*instead"
        # Burn-redirect: convert creature damage into player damage (Repercussion) —
        # a ping/wipe deck turns it into reach (ping/wipe + this = burn the table).
        r"|creature is dealt damage[^.]*deals? that (?:much )?damage to"
        # Symmetric "punisher" burn enchantments (Manabarbs, Roiling Vortex,
        # Spellshock): recurring damage to each/that player.
        r"|deals \d+ damage to (?:each|that|target) (?:player|opponent|creature)"
        r"|whenever (?:a|an|each) (?:player|opponent)[^.]*deals \d+ damage"
        # Land-enter / tap-a-land punishers (Ankh of Mishra, Zo-Zu, War's Toll).
        r"|whenever (?:a|each) (?:player taps a )?land(?: enters| for mana)?"
        r"[^.]*deals \d+ damage",
        extras=(_DEATHTOUCH_GEAR_EXTRA,),
    ),
    # `add .* mana of any` captured fixing (Birds, City of Brass), not amplification.
    # Serve the doublers/triplers (a "tap … for mana" trigger that adds/produces extra)
    # plus the {x} X-spend payoffs.
    ("mana_amplifier", "you"): _spec(
        "Big mana",
        "mana doublers plus the X-spells and expensive bombs to spend it on",
        {"oracle": r"\{x\}|add .* mana|search your library for .*land"},
        r"you tap [^.]*for mana[^.]*(?:add|produces?)"
        r"|produces? (?:twice|three times|\w+ times|an additional|double)"
        r"|doubles?[^.]*mana|\{x\}",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    # Voltron suits up one creature with Equipment (CR 301.5) and BUFF Auras (CR 303).
    # Gate on the Equipment/Aura subtype, but VETO pure-control Auras (Pacifism /
    # Faith's Fetters — ~167 of them) that pacify rather than buff. Keep the oracle as a
    # residual for equip-cost reducers / tutors that aren't themselves Equipment.
    ("voltron_matters", "you"): _spec(
        "Voltron / equipment & auras",
        "equipment, auras, equip-cost reducers, and tutors to suit up one creature",
        {"preset_names": ("equip",)},
        r"equipped creature|enchanted creature gets|equip \{"
        r"|attach [^.]*(?:equipment|aura)"
        r"|equipment you control|for each (?:equipment|aura)"
        r"|cast an? (?:aura|equipment)|cast aura and equipment"
        # Aura/Equipment cost reducers (Danitha) and tutors (Open the Armory,
        # Steelshaper's Gift) are top-synergy voltron payoffs that aren't Equipment.
        r"|(?:aura|equipment)s?[^.]*spells? you cast cost"
        r"|search your library for an? (?:aura|equipment)",
        serve_types=("equipment", "aura"),
        serve_keywords=("reconfigure",),
        # Voltron buffs YOUR creature (CR 303.4 / 702.5). An Aura that enchants a
        # PLAYER (a Curse, CR 205.3h) or a LAND (a ramp/utility aura) never attaches
        # to your creature, so it isn't voltron — veto it so the type gate (which
        # credits any Aura) can't manufacture a phantom voltron theme from curses
        # and land-auras.
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls"
        r"|enchant (?:player|land|forest|island|swamp|mountain|plains)",
        # Extra combats let the suited-up threat swing again — a top voltron payoff.
        extras=(_VOLTRON_PROTECT_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the voltron split — cards that
    # PERFORM the gear-attaching/fetching (attach-OTHER, Equipment/Aura tutors,
    # "unattach", aura recursion). The avenue still offers the whole package (makers +
    # the equipment/aura payoffs they enable — ADR-0034: serve is unaffected in
    # spirit), so this copies the kept voltron_matters serve content; only the role
    # label differs (the gear-attachers / suit-tutors, plus the suit to attach).
    ("voltron_makers", "you"): _spec(
        "Voltron gear-attachers & tutors",
        "attach/fetch effects plus the equipment, auras, and equip-cost reducers they "
        "load onto one creature",
        {"preset_names": ("equip",)},
        r"equipped creature|enchanted creature gets|equip \{"
        r"|attach [^.]*(?:equipment|aura)"
        r"|equipment you control|for each (?:equipment|aura)"
        r"|cast an? (?:aura|equipment)|cast aura and equipment"
        r"|(?:aura|equipment)s?[^.]*spells? you cast cost"
        r"|search your library for an? (?:aura|equipment)",
        serve_types=("equipment", "aura"),
        serve_keywords=("reconfigure",),
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls"
        r"|enchant (?:player|land|forest|island|swamp|mountain|plains)",
        extras=(_VOLTRON_PROTECT_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # An extreme power-for-cost beater (Lord of Tresserhorn 10/4, Yargle 18/6) wins by
    # connecting ONCE for lethal — serve the damage amplifiers that convert raw power
    # into a kill: grant infect (power -> poison) and grant double strike (2x). Distinct
    # from voltron (equipment/auras): these are the combat tricks/auras that close.
    ("one_punch", "you"): _spec(
        "One-punch finishers",
        "amplify your huge body into a one-shot kill — grant infect or double strike "
        "(Tainted Strike, Temur Battle Rage, Grafted Exoskeleton)",
        {"oracle": _ONE_PUNCH_ORACLE},
        _ONE_PUNCH_ORACLE,
    ),
    # A non-Human-attack-trigger engine (Winota) wants evasive attackers that reliably
    # connect — fliers, a useful ~25% narrowing (Dan's own line: "non-Humans" at 96% is
    # not a useful avenue, "fliers at 25%" is). Serve the Flying keyword (the bodies:
    # Ornithopter, Aven Mindcensor, Archon of Emeria) plus flying-granting anthems; the
    # flying Humans it surfaces are premium cheat-into-play targets, also wanted.
    ("nonhuman_attackers", "you"): _spec(
        "Evasive attackers",
        "fliers that connect to trigger your non-Human attack payoff (and flying "
        "Humans to cheat into play)",
        {"card_type": "Creature", "keyword": "flying"},
        r"(?:gains?|have|has) flying|creatures you control[^.]*flying",
        serve_keywords=("flying",),
    ),
    # A reclaim-OWNED commander (Meneldor, The Neutrinos) profits from control-EXCHANGE:
    # donate a dud you own, take their bomb, then reclaim your dud (you still own it).
    # Serve the swaps ("exchange control of …" — Puca's Mischief, Switcheroo, Gilded
    # Drake), NOT one-way theft ("gain control") — you don't OWN a stolen creature, so
    # the commander can't reclaim it.
    ("control_exchange", "you"): _spec(
        "Control swaps",
        "exchange-control effects — donate a dud you own, take their bomb, then "
        "reclaim your dud (Puca's Mischief, Perplexing Chimera, Spawnbroker)",
        {"oracle": r"exchange control of"},
        r"exchange control of"
        r"|exchange (?:control of )?(?:that|those) (?:creature|permanent)",
    ),
    # Kira shields your creatures from removal, so PERMANENT theft sticks: a contingent
    # steal (Sower, Roil — lost if the thief dies) can't be undone, and a theft engine
    # (Empress Galina) survives. Serve the non-temporary theft; the `until end of turn`
    # veto drops Threaten-style steals, which gain nothing from protection.
    ("theft_protection", "you"): _spec(
        "Protected theft",
        "theft creatures whose steal sticks because you shield them from removal — "
        "Sower of Temptation, Roil Elemental, Empress Galina",
        {"oracle": r"gain control of [^.]*target (?:creature|permanent)"},
        r"gain control of (?:up to one )?target "
        r"(?:creature|permanent|nonland permanent|legendary permanent)",
        serve_not=r"until end of turn",
    ),
    # A big-mana commander (Neheb, Sunastian) wants X-spell mana SINKS to dump its mana
    # into. Serve X-damage spells that scale with the mana paid (Fireball, Crackle with
    # Power, Jaya's Immolating Inferno); a fixed-cost burn (Lightning Bolt) and a mana
    # GENERATOR (Mana Flare) are not sinks. (Dan: big-mana-generators -> X-spells.)
    ("big_mana", "you"): _spec(
        "X-spell sinks",
        "X-spells to pour your big mana into — Fireball, Comet Storm, Crackle with "
        "Power, Jaya's Immolating Inferno",
        {"oracle": r"deals x damage|x damage to|times x damage"},
        r"deals x damage|x damage to|deals [^.]*times x damage"
        r"|of up to x target|to each of up to x",
    ),
    # A commander that exiles/takes opponents' library TOPS (Circu, Ragavan, Grenzo)
    # wants to SEE those tops — play-with-top-revealed shows what it will exile/steal.
    # A shuffle-peek (Psychic Surgery) isn't a continuous top-reveal and stays out.
    ("opp_top_exile", "you"): _spec(
        "See opponents' tops",
        "reveal opponents' library tops so you exile/steal the best card — Field of "
        "Dreams, Wizened Snitches, Lantern of Insight",
        {"oracle": r"top card of their (?:library|libraries) revealed"},
        r"plays? with the top card of their (?:libraries|library) revealed"
        r"|look at the top card of (?:each|target|that) (?:opponent|player)",
    ),
    # Fblthp makes 0-cost cards free to plot off the top, fueling the artifact-combo /
    # storm engine. Serve cards whose mana cost is exactly {0} (Ornithopter, Memnite,
    # Welding Jar) — matching on mana_cost excludes lands (no mana cost) for free, and a
    # 1-cost card (Sol Ring) is not a free plot. NOT a raw-stat vanilla-body serve: his
    # ability specifically makes mana-value-0 the relevant property.
    ("free_plot", "you"): _spec(
        "Free plots (0-cost)",
        "0-cost cards — free to plot off the top, the artifact-combo / storm fuel "
        "(Ornithopter, Memnite, Welding Jar)",
        {"card_type": "Artifact", "cmc_max": 0},
        None,
        serve_mana_cost=r"^\{0\}$",
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, support, and creatures to crew them",
        {"preset_names": ("crew",)},
        # Also credit vehicle SUPPORT: cheat a Vehicle into play, ramp/cost-reduction
        # for Vehicle spells (Oviya, Intrepid Stablemaster), not just core text.
        r"\bvehicles? you control\b|\bcrew\b|create [^.]*vehicle artifact"
        r"|\bvehicles? (?:card|spell)s?\b",
    ),
    ("low_power_matters", "you"): _spec(
        "Small creatures matter",
        "payoffs and anthems that reward your low-power creatures attacking and going "
        "wide (Raid Bombardment, Reconnaissance Mission)",
        {
            "oracle": r"creatures? you control with power \d+ or (?:less|fewer)"
            r"|creature spells?[^.]*with power \d+ or (?:less|fewer)"
        },
        # Oracle-only: the "you control with power N or less" anchor is what the payoffs
        # share; NO power_max serve (it would flood the lane with vanilla small bodies).
        # Also the casting-ENABLER form "cast a creature spell with power N or less"
        # (Assemble the Players) — a low-power build-around, still not a vanilla body.
        r"creatures? you control with power \d+ or (?:less|fewer)"
        r"|creature spells?[^.]*with power \d+ or (?:less|fewer)",
    ),
    ("scry_surveil_matters", "you"): _spec(
        "Scry / surveil matters",
        "scry and surveil to fire these payoffs — note surveil also fills your "
        "graveyard (see Your graveyard), while scry is pure top-of-library selection",
        {"oracle": r"\b(?:scry|surveil)\b"},
        r"\b(?:scry|surveil)\b",
    ),
    # ── Named-mechanic long tail ────────────────────────────────────────────────
    # _matters sweep (ADR-0034): monarch split. The MAKER side — cards that GRANT
    # the monarch ("you become the monarch", CR 725). The avenue it opens is the
    # full monarch package (the grant + the evasion/combat-damage payoffs that
    # defend it), so the search stays broad; only the lane KEY encodes the doer role.
    ("monarch_makers", "you"): _spec(
        "Monarch (become)",
        "become the monarch — plus the evasion and combat triggers that defend it",
        {"oracle": r"\bthe monarch\b|becomes? the monarch"},
        r"\bthe monarch\b",
        extras=(_PILLOWFORT_EXTRA,),
    ),
    ("monarch_matters", "you"): _spec(
        "Monarch",
        "defend the monarch — evasion and combat-damage triggers",
        {"oracle": r"\bthe monarch\b|becomes? the monarch"},
        r"\bthe monarch\b",
        extras=(_PILLOWFORT_EXTRA,),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the initiative split — cards that
    # TAKE the initiative (CR 720). The avenue it opens is the full initiative package
    # (takers + the "have the initiative" payoffs + Undercity venture), so the search
    # stays broad; only the lane KEY encodes the doer role.
    ("initiative_makers", "you"): _spec(
        "Initiative (take)",
        "take the initiative; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "hold the initiative payoffs; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("ring_matters", "you"): _spec(
        "The Ring",
        "Ring-bearer payoffs — cards rewarded by the Ring tempting you",
        {"oracle": r"whenever the ring tempts you|ring-bearer"},
        r"whenever the ring tempts you|ring-bearer",
    ),
    # _matters sweep (ADR-0034): the maker side of the ring split. ring_tempters
    # fires on a NATIVE tempt action (the card itself does "the Ring tempts you" —
    # Boromir). The avenue it OPENS is the Ring-bearer payoffs to reward the tempting
    # (the ring_matters serve) plus more ways to tempt yourself.
    ("ring_tempters", "you"): _spec(
        "Tempt the Ring",
        "ways to tempt yourself with the Ring (advance the Ring-bearer)",
        {"oracle": r"the ring tempts you"},
        r"the ring tempts you",
    ),
    # _matters sweep (ADR-0034): the MAKER side of the venture split — cards that
    # venture / take the initiative (CR 701.46 / 720). The avenue it opens is the
    # venture enablers package; only the lane KEY encodes the doer role.
    ("venture_makers", "you"): _spec(
        "Venture (enablers)",
        "venture enablers — cards that venture into the dungeon",
        {"oracle": r"venture into the dungeon|\bdungeon\b"},
        r"venture into the dungeon|\bdungeon\b",
    ),
    ("venture_matters", "you"): _spec(
        "Venture / dungeons",
        "dungeon-completion payoffs and dungeon-trigger doublers",
        {"oracle": r"venture into the dungeon|\bdungeon\b"},
        r"venture into the dungeon|\bdungeon\b",
    ),
    # _matters sweep (ADR-0034): the energy split. energy_makers fires on cards
    # that PRODUCE energy (a real `energy` Effect — "you get {E}"); its avenue
    # serves the rest of the energy engine (more producers + the sinks that spend
    # it). Same oracle search as the old combined lane.
    ("energy_makers", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        {"oracle": r"\{e\}|energy counter"},
        r"\{e\}|energy counter",
    ),
    # The PAYOFF side of the energy split: a card that SPENDS / references energy
    # without producing its own (a "Pay {E}{E}:" sink, a "whenever you get {E}"
    # trigger, a doubler). It wants the producers that fuel it — same energy
    # search pool.
    ("energy_matters", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        {"oracle": r"\{e\}|energy counter"},
        r"\{e\}|energy counter",
    ),
    # Devotion (CR 700.5) counts single-color mana SYMBOLS among permanents you control,
    # so the enablers are structurally heavy-pip permanents — a dimension oracle text
    # can't express. Keep `devotion to` for the payoffs; add the pip gate (≥2 of one
    # color, nonland permanent) for the enablers the old serve was blind to.
    ("devotion_matters", "you"): _spec(
        "Devotion",
        "heavy colored pips to grow devotion and devotion payoffs",
        {"oracle": r"devotion to"},
        r"devotion to",
        serve_min_devotion=2,
    ),
    # The central body of the archetype IS the planeswalkers (type) and the proliferate
    # payoffs (keyword) — both authoritative Scryfall fields the oracle-only serve named
    # none of (43/303 → 303/303 served, zero added FPs per the audit).
    ("superfriends_matters", "you"): _spec(
        "Superfriends",
        "planeswalkers plus proliferate and loyalty payoffs to protect them",
        {"oracle": r"planeswalker|loyalty"},
        r"planeswalkers? you control|loyalty counters?",
        serve_types=("planeswalker",),
        serve_keywords=("proliferate",),
        extras=(_PILLOWFORT_EXTRA, _LOYALTY_DOUBLER_EXTRA),  # protect the walkers
        # (EDHREC: 3 commanders) + a GENERIC (any-permanent) counter doubler, which
        # also doubles LOYALTY — see _LOYALTY_DOUBLER_EXTRA for the ADR-0036/0037
        # Stage 5 #62 adjudication (serve-layer adjacency, never lane membership).
    ),
    # Historic (CR 700.6) = artifact, legendary, OR Saga — all type_line tokens. The
    # serve named only the keyword; gate on the three structural categories.
    ("historic_matters", "you"): _spec(
        "Historic",
        "artifacts, legendaries, and Sagas — the historic permanents that trigger it",
        {"oracle": r"\bhistoric\b|\blegendary\b|\bsaga\b"},
        r"\bhistoric\b",
        serve_types=("legendary", "artifact", "saga"),
    ),
    ("legends_matter", "you"): _spec(
        "Legends matter",
        "legendary creatures and the payoffs that reward a board of legends",
        {"oracle": r"\blegendary\b"},
        r"legendary creatures? you control|another legendary|for each legendary",
        serve_types=("legendary",),
    ),
    # The bare `cards in your hand` matched stax/hand-size references (Ensnaring Bridge,
    # Ivory Tower). Require a no-max-hand-size or a full-grip payoff/scaling phrase.
    # _matters sweep (ADR-0034): the big-hand lane SPLITS by role at emission
    # (big_hand_makers = the no-max-hand-size ENABLERS; big_hand_matters = the
    # cards-in-hand PAYOFFS). Per ADR-0034 only MEMBERSHIP splits — the serve avenue
    # still offers enablers + payoffs together, so BOTH specs keep the broad serve pool.
    ("big_hand_makers", "you"): _spec(
        "No maximum hand size",
        "no-max-hand-size enablers and the payoffs that reward a full grip",
        {"oracle": r"cards in your hand|no maximum hand size"},
        r"maximum hand size"
        r"|(?:\d+|five|six|seven|eight) or more cards in (?:your )?hand"
        r"|for each card in your hand|equal to the number of cards in your hand",
    ),
    ("big_hand_matters", "you"): _spec(
        "Big hand payoffs",
        "card draw and no-max-hand-size payoffs that reward a full grip",
        {"oracle": r"cards in your hand|no maximum hand size"},
        r"maximum hand size"
        r"|(?:\d+|five|six|seven|eight) or more cards in (?:your )?hand"
        r"|for each card in your hand|equal to the number of cards in your hand",
    ),
    # A party (CR 700.x) is one each of Cleric/Rogue/Warrior/Wizard — those creature
    # SUBTYPES are the members. The bare `\bparty\b` caught 3 flavor FPs; gate the
    # members on the subtype field, keep the party-phrase oracle for the payoffs.
    ("party_matters", "you"): _spec(
        "Party",
        "Clerics, Rogues, Warriors, and Wizards to assemble a full party",
        {"oracle": r"your party|assemble.*party|\bcleric|\brogue|\bwarrior|\bwizard"},
        r"your party|members? of your party|full party|creatures? in your party"
        r"|assemble[^.]*party",
        serve_types=("cleric", "rogue", "warrior", "wizard"),
    ),
    ("exile_matters", "you"): _spec(
        "Exile pile matters",
        "impulse/foretell exile enablers and payoffs for cards in exile",
        {"oracle": r"exile the top|in exile|from exile"},
        r"cards? (?:you own )?in exile|for each card[^.]*exile",
    ),
    # _matters sweep (ADR-0034): split the conflated experience lane by role.
    # experience_makers = the MAKER arm (cards that GAIN experience counters —
    # Ezuri, Mizzix, Kalemne); experience_matters = the PAYOFF arm (cards that
    # SCALE off your experience count — Atreus draw-X, Azula pump-X). Both reuse
    # the same {"oracle": "experience counter"} search pool.
    ("experience_makers", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    ("experience_matters", "you"): _spec(
        "Experience payoffs",
        "payoffs that scale with experience counters",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    # _matters sweep (ADR-0034): poison split by role. poison_makers = the MAKER arm
    # (infect/toxic threats + poison-counter givers that DEAL the poison);
    # poison_matters = the PAYOFF arm (cards that REWARD a high poison count —
    # Corrupted, proliferate-to-finish). Both reuse the same search pool: the serve
    # avenue legitimately composes infect/toxic threats AND the poison payoffs
    # together (ADR-0034: only membership splits by role, the avenue offers both).
    ("poison_makers", "opponents"): _spec(
        "Poison / infect",
        "infect and toxic threats to stack poison counters on opponents",
        {"oracle": r"\binfect\b|\btoxic\b|poison counter|proliferate"},
        r"poison counter|\binfect\b|\btoxic\b",
    ),
    ("poison_matters", "opponents"): _spec(
        "Poison payoffs",
        "payoffs that reward a high poison count plus proliferate to finish",
        {"oracle": r"\binfect\b|\btoxic\b|poison counter|proliferate"},
        r"poison counter|\binfect\b|\btoxic\b",
    ),
    # "Modified" (CR 122) = a creature with a +1/+1 counter, Aura, OR Equipment. The
    # serve named only the literal word (the payoffs); the ENABLERS are structurally
    # Equipment/Aura permanents and counter-placers. Add those dimensions.
    ("modified_matters", "you"): _spec(
        "Modified",
        "counters, Auras, and Equipment to keep creatures modified",
        {"oracle": r"\bmodified\b|\+1/\+1 counter|aura or equipment"},
        r"\bmodified\b|\+1/\+1 counters?",
        serve_types=("equipment", "aura"),
    ),
    ("has_mutate", "you"): _spec(
        "Mutate",
        "mutate creatures and mutate-trigger payoffs",
        {"oracle": r"\bmutate\b"},
        r"\bmutate\b",
    ),
    # _matters sweep (ADR-0034): food split. The make_token MAKER arm
    # (food_makers, cards that create Food tokens) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (food_matters) both serve the same Food
    # makers-plus-sacrifice-and-lifegain avenue. The union == the old
    # food_matters; only the role label differs.
    ("food_makers", "you"): _spec(
        "Food tokens",
        "Food makers plus sacrifice outlets and lifegain payoffs",
        {"oracle": r"\bfood token|foods? you control|sacrifice a food"},
        # Food-GRANTERS (Ragost, The Food Court, Ygra: "are Foods in addition").
        r"\bfood token|foods? you control|sacrifice a food"
        r"|(?:are|is|becomes?) (?:an? )?foods? in addition",
    ),
    ("food_matters", "you"): _spec(
        "Food token payoffs",
        "cards that sacrifice or reference Food tokens, plus lifegain payoffs",
        {"oracle": r"\bfood token|foods? you control|sacrifice a food"},
        # Food-GRANTERS (Ragost, The Food Court, Ygra: "are Foods in addition").
        r"\bfood token|foods? you control|sacrifice a food"
        r"|(?:are|is|becomes?) (?:an? )?foods? in addition",
    ),
    # Hand-spec overriding the mined sweep detector so the serve also credits color
    # GRANTERS / fixers — "are the chosen color" (Painter's Servant, Shifting Sky) and
    # "<color> in addition to its colors" (Indigo Faerie) — not just "becomes the color
    # of your choice / all colors". Kept precise (no bare "becomes blue") to avoid
    # mana-color false positives.
    # Type change (the TYPE analog of color_change): a creature-type hoser (Gor Muldrak
    # "protection from Salamanders") wants the type-CHANGING toolbox — turn opponents'
    # creatures into the punished type so the hoser blanks them. Genuine changers only
    # ("target/each creature becomes <type>"), NOT the tribal anthems that merely
    # "choose a creature type" then buff your own.
    ("type_change", "you"): _spec(
        "Type change",
        "creature-type changers to force opponents into the punished type",
        {"oracle": _TYPE_CHANGER_ORACLE},
        _TYPE_CHANGER_ORACLE,
    ),
    # ADR-0027 β: color_change migrated to the Card IR via a byte-identical kept-mirror
    # (the lane fires from crosswalk_signals._color_change). This serve spec was
    # always hand-registered with its own curated SEARCH regex (broader than the
    # detector — it also credits color GRANTERS / fixers and color-conditional PAYOFFS),
    # independent of the deleted SWEEP producer, so it survives unchanged.
    ("color_change", "you"): _spec(
        "Color change",
        "effects that add or change colors — fixing plus color-matters enablers",
        {
            "oracle": r"becomes the color of your choice|the chosen color"
            r"|in addition to (?:its|their) (?:other )?colors?"
        },
        r"becomes the color of your choice|becomes? (?:the color|all colors)"
        r"|(?:are|is) the chosen color"
        r"|(?:is|are|becomes?) [^.]*(?:white|blue|black|red|green) "
        r"in addition to (?:its|their)"
        # Color-conditional PAYOFFS a color-CHANGER enables (make everything one color,
        # then "destroy/return all [color]" is a board wipe — CR 105/613, color is
        # continuously checked). Only the 2 color-change commanders see this serve, so
        # the narrow color-hosers stay scoped to the decks that turn them on.
        r"|(?:return|destroy|exile) all (?:white|blue|black|red|green) "
        r"(?:creature|permanent)s?"
        r"|return all permanents of the (?:chosen )?colou?r"
        r"|(?:white|blue|black|red|green) creatures? (?:can't|get [+\-])",
    ),
    # Hand-spec overriding the mined sweep detector so the serve also credits the Domain
    # ENABLERS — "lands you control are every basic land type" (Prismatic Omen, Dryad of
    # the Ilysian Grove) — not just the "domain" / "basic land types among" payoffs. The
    # `... in addition to` tail also credits the additive type-of-choice granter
    # (Navigator's Compass) WITHOUT the replacement color-fixers ("becomes X until
    # end of turn", no "in addition to") or anti-domain hosers (Blood Moon).
    ("domain_matters", "you"): _spec(
        "Domain",
        "basic land types and fixing to grow domain",
        {"oracle": r"\bdomain\b|basic land types?"},
        r"\bdomain\b|number of basic land types?|basic land types? among"
        r"|every basic land type|basic land types?[^.]*in addition to",
    ),
    ("clue_matters", "you"): _spec(
        "Clues / investigate",
        "investigate enablers and artifact/draw payoffs for Clues",
        {"oracle": r"\bclue\b|investigate"},
        r"\bclue\b|investigate",
    ),
    # _matters sweep (ADR-0034): clue split. The make_token MAKER arm (clue_makers,
    # cards that create Clue tokens / investigate) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (clue_matters) both serve the same
    # investigate-and-crack avenue. The union == the old clue_matters; only the role
    # label differs.
    ("clue_makers", "you"): _spec(
        "Clue makers / investigate",
        "Clue makers plus artifact/draw payoffs for Clues",
        {"oracle": r"\bclue\b|investigate"},
        r"\bclue\b|investigate",
    ),
    # _matters sweep (ADR-0034): blood split. The make_token MAKER arm
    # (blood_makers, cards that create Blood tokens) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (blood_matters) both serve the same
    # Blood-rummage-and-sacrifice avenue. The union == the old blood_matters;
    # only the role label differs.
    ("blood_makers", "you"): _spec(
        "Blood tokens",
        "Blood makers plus rummage and sacrifice payoffs",
        {"oracle": r"blood token"},
        r"blood token",
    ),
    ("blood_matters", "you"): _spec(
        "Blood token payoffs",
        "cards that sacrifice or reference Blood tokens",
        {"oracle": r"blood token"},
        r"blood token",
    ),
    # _matters sweep (ADR-0034): Day/Night split. The transition-MAKER arm
    # (daynight_makers — "it becomes day/night" flippers: The Celestus, Vadrik,
    # Brimstone Vandal, Tovolar's upkeep flip) and the daybound/nightbound werewolf
    # PAYOFF arm (daynight_matters — creatures rewarded by the flip) both serve the
    # same Day/Night avenue. The union == the old daynight_matters; only the role
    # label differs.
    ("daynight_makers", "you"): _spec(
        "Day / Night enablers",
        "cards that flip day/night — the transition makers",
        {"oracle": r"\bdaybound\b|\bnightbound\b|\bday\b|\bnight\b"},
        r"daybound|nightbound|becomes night|becomes day",
    ),
    ("daynight_matters", "you"): _spec(
        "Day / Night",
        "daybound/nightbound creatures and day-night transition payoffs",
        {"oracle": r"\bdaybound\b|\bnightbound\b|\bday\b|\bnight\b"},
        r"daybound|nightbound|becomes night|becomes day",
    ),
    # _matters sweep (ADR-0034): voting split. The vote-CREATOR doer arm
    # (voting_makers, will-of-the-council / council's-dilemma cards that run a
    # vote) and the finish-voting PAYOFF arm (voting_matters, triggers off a vote
    # without creating one) both serve the same multiplayer-politics avenue. The
    # union == the old voting_matters; only the role label differs.
    ("voting_makers", "each"): _spec(
        "Voting / council",
        "will-of-the-council and vote effects — multiplayer politics",
        {"oracle": r"\bvote\b|will of the council|council's dilemma"},
        r"\bvote\b|will of the council",
    ),
    ("voting_matters", "each"): _spec(
        "Voting / council payoffs",
        "cards that trigger off a vote — multiplayer politics",
        {"oracle": r"\bvote\b|will of the council|council's dilemma"},
        r"\bvote\b|will of the council",
    ),
    ("coven_matters", "you"): _spec(
        "Coven",
        "creatures with different powers to turn on coven",
        {"oracle": r"\bcoven\b|different powers"},
        r"\bcoven\b",
    ),
    # ADR-0027 β: conjure_makers migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted — detection moved to a byte-identical `\bconjure\b` kept word mirror in
    # signals._IR_KEPT_DETECTORS). The SERVE pool stays oracle-defined (Arena/Alchemy
    # conjure makers and payoffs), so hand-register the spec the sweep auto-register
    # loop used to build (scope "you", the deleted SWEEP row's scope), reusing the EXACT
    # deleted regex so the serve never drifts. SWEEP_LABELS keeps the human label.
    ("conjure_makers", "you"): _spec(
        *SWEEP_LABELS["conjure_makers"],
        {"oracle": r"\bconjure\b"},
        r"\bconjure\b",
    ),
    # Token doubling: a token doubler wants the token MAKERS it multiplies (Hornet
    # Queen), other token doublers to stack (Parallel Lives), and the go-wide / ETB
    # payoffs every doubled token feeds. Distinct from counter doubling.
    ("token_doubling", "you"): _spec(
        "Token doubling",
        "token makers to multiply, plus other token doublers and go-wide payoffs",
        {"oracle": r"create [^.]*creature token|twice that many[^.]*tokens?"},
        r"create [^.]*creature token"
        r"|(?:twice that many|double the number of) [^.]*tokens?",
        extras=(
            _TOKEN_MAKER_EXTRA,
            _TOKEN_DOUBLER_EXTRA,
            _GOWIDE_ANTHEM_EXTRA,
            _ETB_PAYOFF_EXTRA,
        ),
    ),
    # Counter doubling: a +1/+1-counter doubler wants the counter SOURCES it multiplies
    # — things that PUT counters (Hardened Scales fuel), creatures that ENTER WITH them
    # (Master Biomancer, Hangarback), proliferate, and other counter doublers to stack.
    ("counter_doubling", "you"): _spec(
        "Counter doubling",
        "+1/+1 counter sources to multiply, plus other counter doublers",
        {"oracle": r"\+1/\+1 counters?|double the number of [^.]*counters?"},
        r"(?:twice that many|double the number of) [^.]*counters?"
        # Creatures that ENTER WITH +1/+1 counters are counter sources — including the
        # variable "a number of" / "X" forms a digit-keyed regex misses (Master
        # Biomancer, Hangarback Walker).
        r"|enters with (?:a|an|one|two|three|x|\d+|a number of)[^.]*?\+1/\+1 counters?",
        extras=_COUNTERS_PACKAGE,
    ),
    # Serve is precise (the second-spell payoff). The SEARCH carried the same bare
    # "draw a card" FP; narrow it to the payoffs (second/third spell, multi-spell,
    # storm) so the avenue stops crediting every value permanent that draws.
    ("second_spell_matters", "you"): _spec(
        "Second-spell / storm-lite",
        "second-spell, multi-spell, and storm payoffs that reward chaining casts",
        {
            "oracle": (
                r"(?:second|third) spell you cast|cast your (?:second|third) spell"
                r"|cast two or more spells|\bstorm\b"
            )
        },
        r"(?:second|third) spell you cast|cast your (?:second|third) spell",
    ),
}
