"""Signal specs data slice 2/4: SPECS dict entries (lines 3417-4562 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

from mtg_utils._analysis._sweep_detectors import (
    SWEEP_LABELS,
)

from ._shared import (
    _CAST_FROM_EXILE_EXTRA,
    _COMBAT_SUPPORT_EXTRA,
    _COST_REDUCER_EXTRA,
    _COUNTERS_PACKAGE,
    _DAMAGE_AMPLIFIER_EXTRA,
    _DEATHTOUCH_GEAR_EXTRA,
    _ETB_PAYOFF_EXTRA,
    _EXTRA_COMBAT_EXTRA,
    _GOWIDE_ANTHEM_EXTRA,
    _LANDS_FROM_GRAVE_EXTRA,
    _LOYALTY_DOUBLER_EXTRA,
    _MANA_AMP_EXTRA,
    _PARADOX_PAYOFF_EXTRA,
    _PILLOWFORT_EXTRA,
    _PLUS_ONE_SERVE_IDENTS,
    _PUMP_EXTRA,
    _SYM_MANA_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_EXTRA,
    _TOKEN_MAKER_IDENTS,
    _VOLTRON_PROTECT_EXTRA,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
    _sweep_spec_with_extras,
)

# The voltron serve (voltron_matters / voltron_makers, you): the suit-up payoffs and
# the gear-attachers and tutors.
_VOLTRON_IDENTS = frozenset({"voltron_matters|you|", "voltron_makers|you|*"})

# The discard serve (discard_makers / discard_matters / discard_outlet, you): the
# outlets, the discard makers, the "whenever you discard" payoffs and the Blood
# makers whose tokens rummage.
_DISCARD_SERVE_IDENTS = frozenset(
    {
        "discard_makers|you|",
        "discard_matters|you|",
        "discard_outlet|you|",
        "blood_makers|you|",
    }
)

# The energy and venture serves (both lanes of each pair): makers and payoffs
# share one avenue.
_ENERGY_SERVE_IDENTS = frozenset({"energy_makers|you|", "energy_matters|you|"})
_VENTURE_SERVE_IDENTS = frozenset({"venture_makers|you|", "venture_matters|you|"})

# The self life-loss serve (lifeloss_matters / lifeloss_makers, you): the life
# payers and losers, the "whenever you lose life" payoffs, the pay-life insurance
# and the life-total swaps and resets. The lane reads the "life you lost this turn"
# amounts too (Children of Korlis). Lane gaps: "whenever you gain or lose life"
# (Moonstone Harbinger) and Channel's payments (Sylvan Library).
_SELF_LIFELOSS_SERVE_IDENTS = frozenset(
    {
        "lifeloss_makers|you|",
        "lifeloss_matters|you|",
        "life_payment_insurance|you|",
        "life_total_set|any|",
    }
)

# The land-sacrifice serve (land_sacrifice_matters / _makers, you): both lanes. They
# also read a land sacrificed as a kicker / additional cost (Harrow, Scapeshift) and
# symmetric land wraths, which sit on the each scope (Tremble, Wildfire, Smallpox).
# Lane gap: lands put into a graveyard
# without a sacrifice (Akki Raider, Hedge Shredder).
_LAND_SAC_SERVE_IDENTS = frozenset(
    {
        "land_sacrifice_matters|you|",
        "land_sacrifice_makers|you|",
        "land_sacrifice_makers|each|",
    }
)

# Flying granters: nonhuman_attackers' sub-avenue. The serve reads the grant lanes'
# flying idents.
_FLYING_GRANT_IDENTS = frozenset(
    {
        "keyword_grant_target|you|flying",
        "team_buff|you|flying",
        "aura_equip_kw_grant|you|flying",
        "all_creatures_kw_grant|any|flying",
        "team_evasion_grant|you|flying",
    }
)

_BIG_HAND_IDENTS = frozenset({"big_hand_makers|you|", "big_hand_matters|you|"})


SPECS_2: dict[tuple[str, str], SignalSpec] = {
    # ── Rules mined from the zero-signal commander tail ─────────────────────────
    # Serve the payoff trigger (CR 510 combat damage) + true-unblockable enablers. The
    # bare `\bmenace\b` matched every menace creature AND the menace/flying REMINDER
    # "can't be blocked except by …" — surfacing vanilla evasive bodies, not connect
    # payoffs. Drop it; gate `can't be blocked` against the "except" reminder.
    ("combat_damage_matters", "opponents"): _spec(
        "Combat damage",
        "evasive attackers and extra-combat enablers to keep connecting",
        # Serve on the lanes' idents: the combat-damage payoffs and the unblockable /
        # landwalk bodies that connect (menace and fear bodies stay out).
        None,
        serve_idents=frozenset(
            {
                "combat_damage_matters|opponents|",
                "combat_damage_to_opp|opponents|",
                "evasion_self|you|unblockable",
                "evasion_self|you|landwalk",
            }
        ),
        # A combat-damage-trigger commander needs to CONNECT and survive: gear to suit
        # up (Ojutai), instant pump to push through / survive blocks (Benton), and extra
        # combats to multiply the trigger (Neheb -> Relentless Assault, Seize the Day).
        extras=(_COMBAT_SUPPORT_EXTRA, _PUMP_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted, so the serve is hand-registered.
    ("combat_damage_to_opp", "opponents"): _sweep_spec_with_extras(
        "combat_damage_to_opp",
        (
            _COMBAT_SUPPORT_EXTRA,
            _PUMP_EXTRA,
            _DAMAGE_AMPLIFIER_EXTRA,
            _EXTRA_COMBAT_EXTRA,
        ),
        # Serve on the lanes' idents, not the regex (2026-10-18): the regex read
        # only the literal phrase, so it missed the "combat damage to one of your
        # opponents" payoffs (Edric, Spymaster of Trest; Gonti, Night Minister) and
        # the double-strike granters. Cipher grants the same trigger (CR 702.99a),
        # which the regex reached only through reminder text: the keyword dim keeps it.
        serve_idents=frozenset(
            {"combat_damage_to_opp|opponents|", "combat_damage_matters|opponents|"}
        ),
        serve_keywords=("cipher",),
    ),
    # ADR-0027 β: combat_damage_to_creature migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted (the auto-loop used to register a plain spec,
    # no extras). Hand-register the plain spec so the avenue still resolves
    # (connect-with-creatures payoffs — Ohran Viper, the basilisks, Toxin Sliver).
    ("combat_damage_to_creature", "any"): _spec(
        *SWEEP_LABELS["combat_damage_to_creature"],
        # Serve on the lane's ident, not the regex (2026-10-18): the two agree on
        # every printed trigger; the regex's only extras were the same trigger
        # granted in quotes (Kaldra Compleat), a granted-ability lane gap.
        None,
        serve_idents=frozenset({"combat_damage_to_creature|any|"}),
    ),
    # Group-mana commanders (Shizuko, Yurlok) want symmetric mana-doublers / punishers +
    # join-forces ramp beyond the bare "each player adds {" the sweep regex credits.
    # Unspent-mana commander (Omnath, Kruphix) keeps mana between steps -> wants mana
    # amplification (untap-all-lands + doublers) to bank more. The sweep's bare "unspent
    # mana" serve credited none; promote it to a hand-spec with the amp extra.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a kept-mirror — its
    # SWEEP_DETECTORS row is deleted, so hand-register the spec.
    ("unspent_mana", "you"): _sweep_spec_with_extras(
        "unspent_mana",
        (_MANA_AMP_EXTRA,),
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        serve_idents=frozenset({"unspent_mana|you|"}),
    ),
    # ADR-0027: group_mana migrated to the Card IR — its SWEEP_DETECTORS row is deleted
    # (detection moved to a non-controller-recipient discriminator on phase's ramp
    # effect raw), so hand-register the spec the sweep loop used to build; the serve is
    # the lane's ident, with the symmetric-mana extra.
    ("group_mana", "each"): _spec(
        *SWEEP_LABELS["group_mana"],
        # The lane reads the symmetric doublers the regex missed (Mana Flare, High
        # Tide). Lane gaps: Yurlok of Scorch Thrash's activated "each player adds",
        # Valleymaker.
        None,
        serve_idents=frozenset({"group_mana|each|"}),
        extras=(_SYM_MANA_EXTRA,),
    ),
    # The discount-exploiting target set is defined by high cmc (structured) + X-spells
    # — not the generic words "mana value", which matched 453 cards (Disdainful Stroke,
    # Abrupt Decay). The serve drops that branch: the lane's ident plus cmc (expensive
    # bombs) and an {X} mana cost, with a Storm payoffs extra.
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount, plus more cost "
        "reducers to stack the discount",
        # The cost reducers the avenue names (Etherium Sculptor, Dragonspeaker Shaman).
        # Storm payoffs a discount chains into are the Storm payoffs extra, read off the
        # keyword (CR 702.40a); the old \bstorm\b served cards named Storm.
        None,
        serve_idents=frozenset({"cost_reduction|you|*"}),
        serve_cmc_min=7,
        # X-spells by their printed MANA COST, as xspell_matters reads them: the old
        # oracle "{x}" arm caught 32 of 567 X-cost spells (Torment of Hailfire's text
        # says "X times", never "{X}") and credited 318 cards whose {X} is an
        # activated-ability cost a spell-cost reducer never discounts.
        serve_mana_cost=r"\{X\}",
        extras=(
            _COST_REDUCER_EXTRA,
            SubAvenue(
                "Storm payoffs",
                "storm spells that a cheap, chained turn of discounted spells "
                "copies many times (Grapeshot, Tendrils of Agony, Mind's Desire)",
                serve=Serve(keywords=frozenset({"storm"})),
            ),
        ),
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
        # Serve on the lane's ident; the keyword dims below cast from exile too.
        None,
        # Suspend (CR 702.62a), Foretell (702.143), Rebound (702.88a), and Plot all CAST
        # the card from exile — authoritative Scryfall keywords, not regex-from-prose.
        serve_keywords=("plot", "suspend", "foretell", "rebound", "warp"),
        serve_idents=frozenset({"cast_from_exile|you|"}),
        extras=(_PARADOX_PAYOFF_EXTRA,),
    ),
    # Impulse: serves the impulse lane's idents plus the impulse-style cast-from-exile
    # engines. Remainder: impulse draws the lanes don't read (look, exile one, play
    # it) and theft-side exiles, which the theft lanes own.
    ("impulse_top_play", "you"): _spec(
        *SWEEP_LABELS["impulse_top_play"],
        None,
        serve_idents=frozenset(
            {"impulse_top_play|you|", "cast_from_exile|you|impulse"}
        ),
        # Paradox payoffs (Keeper of Secrets) — casting from exile IS from-anywhere-
        # other-than-hand, so an impulse deck triggers them too.
        extras=(
            _PARADOX_PAYOFF_EXTRA,
            _CAST_FROM_EXILE_EXTRA,
        ),
    ),
    # X-spells matter (CR 107.3 / 202.1): an X-matters commander (Zaxara, Rosheen,
    # Zimone) is built from spells whose printed mana cost contains {X} and wants the
    # X-doublers / copy-the-X-spell payoffs (Unbound Flourishing). The serve credits
    # {X}-cost cards via the structured mana_cost dimension (the X-spells themselves)
    # PLUS the X-payoffs (xspell_matters). A broad but genuinely on-theme pool — an X
    # deck wants the universe of X-spells, so breadth here is coverage, not noise.
    ("xspell_matters", "you"): _spec(
        "X spells",
        "X-spells (cards with {X} in their cost) plus the X-doublers and "
        "copy-the-X-spell payoffs an X-matters deck is built around",
        # The X payoffs are the lane's own ident (a cast watcher or a card filter
        # on {X} costs, mana spent only on them; the phase drops bridged): the
        # old "{X} in its cost" pattern also took the X hosers (Gaddock Teeg,
        # Frontline Medic, Titans' Nest).
        None,
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
        serve_idents=frozenset({"xspell_matters|you|", "mana_amplifier|you|"}),
    ),
    # Theft (steal an OPPONENT's cards and cast them): serve credits the opponent-
    # library dig (Gonti, Black Cat, Thief of Sanity) and the steal-and-cast engines
    # (Hostage Taker). Opponent-anchored / "remains exiled"-anchored so a self-impulse
    # engine (Valakut Exploration — your own library, "until end of next turn") stays
    # out. Detector regex unchanged.
    ("theft_makers", "opponents"): _spec(
        *SWEEP_LABELS["theft_makers"],
        # Serve on the theft lane's ident (steal and steal-and-cast engines).
        None,
        serve_idents=frozenset({"theft_makers|opponents|"}),
    ),
    # _matters sweep (ADR-0034): the WANTS side of the theft split. wants_theft fires
    # (LOW) when the commander itself rewards casting what you don't own (a don't-own
    # payoff — Don Andres, Vaan, Gonti Canny) or steals battlefield permanents
    # (gain_control). The avenue it OPENS is the theft ENABLERS that feed that payoff —
    # the same steal-and-cast pool as theft_makers (Gonti, Hostage Taker, the impulse-
    # from-opponent engines). Same opponent-anchored serve; the maker/payoff split
    # is in MEMBERSHIP, the avenue legitimately offers the doers to a wants commander.
    ("wants_theft", "opponents"): _spec(
        *SWEEP_LABELS["wants_theft"],
        # Serve on the theft lane's ident (steal and steal-and-cast engines).
        None,
        serve_idents=frozenset({"theft_makers|opponents|"}),
    ),
    # ADR-0027: void_warp_matters migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds this spec).
    ("void_warp_matters", "you"): _spec(
        *SWEEP_LABELS["void_warp_matters"],
        # Serve on the lanes' idents (2026-10-18): the regex missed warp cards whose
        # warp cost line it didn't phrase-match (Astelli Reclaimer, Quantum Riddler).
        None,
        serve_idents=frozenset({"void_warp_makers|you|", "void_warp_matters|you|"}),
    ),
    # _matters sweep (ADR-0034) — the MAKER arm of the void_warp split: cards that
    # PERFORM/GRANT the Warp alt-cast (the keyword bearer/granter, the em-dash warp-cost
    # form, the graveyard self-cast).
    ("void_warp_makers", "you"): _spec(
        *SWEEP_LABELS["void_warp_makers"],
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        None,
        serve_idents=frozenset({"void_warp_makers|you|"}),
    ),
    # Play from the TOP OF YOUR LIBRARY — Future Sight / Bolas's Citadel / Oracle of Mul
    # Daya. Casts from the LIBRARY zone (not exile), so it's its own avenue, distinct
    # from cast-from-exile and impulse. ADR-0027 β: detection moved to the Card IR (a
    # STATIC cast_from_zone+from: library Effect over phase's TopOfLibraryCastPermission
    # mode + a per-clause mirror); the serve is the lane's ident (the sweep
    # auto-register no longer builds this spec — its SWEEP_DETECTORS row is deleted).
    ("play_from_top", "you"): _spec(
        "Play from the top of your library",
        "engines that let you play or cast off the top of your library (Future Sight, "
        "Bolas's Citadel) — top-of-library control and extra-land effects amplify them",
        # The lane serves library-cast permissions. Cascade's reminder text is cascade's
        # own avenue; lane gaps: temporary or conditional permissions (Gwenom, The
        # Belligerent) and lands-only ones (Radha).
        None,
        serve_idents=frozenset({"play_from_top|you|"}),
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the discard split. discard_makers
    # fires on a loot/rummage/connive OUTLET (a draw+discard co-occurrence — Faithless
    # Looting, Merfolk Looter, Windfall). The avenue it OPENS is the discard PAYOFFS
    # those outlets power ("whenever you discard …" — Containment Construct, Rielle)
    # plus more outlets (the same self-discard pool as discard_matters), so an outlet
    # engine finds its payoffs. The maker/payoff split is in MEMBERSHIP; the avenue
    # legitimately offers both.
    # Serve idents: the three discard lanes plus Blood makers (a Blood token is
    # "{1}, {T}, Discard a card, Sacrifice this token: Draw a card.", CR 111.10g).
    # discard_makers reads a discard cost you choose to pay (random included) and
    # connive (CR 701.50a), granted connive too. The regex's remainder: opponent
    # discards (Skull Rend, Court of Ambition) and an opponent's Blood token
    # (Bloodvial Purveyor), a tax (Avatar of Discord's "sacrifice it unless you
    # discard two cards"), and Mask of the Schemer's "connives X", which phase
    # leaves an unimplemented ``where_x_binding``.
    ("discard_makers", "you"): _spec(
        "Loot / discard outlets",
        "loot/connive/rummage outlets plus the discard payoffs they power",
        None,
        serve_idents=_DISCARD_SERVE_IDENTS,
    ),
    ("discard_matters", "you"): _spec(
        "Discard",
        "discard payoffs and the self-discard outlets that feed them",
        None,
        serve_idents=_DISCARD_SERVE_IDENTS,
    ),
    # Discard OUTLET commander (a loot/rummage engine): hand-written so the serve adds
    # the discard PAYOFFS it powers ("whenever you discard …" — Containment Construct,
    # Rielle, Glint-Horn Buccaneer) alongside the outlets the sweep regex already
    # credits. Detector regex unchanged (same key → auto-register skips it).
    # Serve idents: the same discard idents.
    ("discard_outlet", "you"): _spec(
        *SWEEP_LABELS["discard_outlet"],
        None,
        serve_idents=_DISCARD_SERVE_IDENTS,
    ),
    # ADR-0027 dig library-owner scope (SIDECAR v27): dig_until migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label /
    # avenue.
    ("dig_until", "you"): _spec(
        *SWEEP_LABELS["dig_until"],
        # Serve on the dig-until, cascade and discover idents (2026-10-18): the regex
        # reached cascade only through its reminder text, so it missed the bare-keyword
        # cascaders (Sweet-Gum Recluse) and the discover cards printed without it
        # (Curator of Sun's Creation). Cascade and discover ARE exile-until digs.
        None,
        serve_idents=frozenset(
            {
                "dig_until|you|",
                "cascade_makers|you|",
                "cascade_matters|you|",
                "discover_makers|you|",
            }
        ),
    ),
    # ADR-0027 per-clause draw raw (SIDECAR v32): draw_for_each migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label /
    # avenue.
    ("draw_for_each", "you"): _spec(
        *SWEEP_LABELS["draw_for_each"],
        # Serve on the lane's ident (2026-10-18): the regex missed the "draw X cards,
        # where X is" form (Champion of Dusk, Be'lakor) and credited an opponent's
        # draw (Deadly Cover-Up).
        None,
        serve_idents=frozenset({"draw_for_each|you|"}),
    ),
    # ADR-0027 topdeck library-owner scope (SIDECAR v28): topdeck_selection migrated to
    # the Card IR (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer
    # builds this spec). Hand-registered with the same label / avenue; the serve is the
    # lane's ident.
    ("topdeck_selection", "you"): _spec(
        *SWEEP_LABELS["topdeck_selection"],
        # Reads scry and surveil, which the avenue names (Dissolve, Fated Retribution).
        # Manifest dread (a look-at-two selection) is a lane gap; ripple is not
        # selection.
        None,
        serve_idents=frozenset({"topdeck_selection|you|"}),
    ),
    # Drain. The serve required "opponent" adjacent to "loses", so it MISSED the
    # keystone aristocrats drains worded "target/that player loses N life" (Blood
    # Artist, Falkenrath Noble). Add the player-loses branch; "each player" is excluded
    # to keep symmetric self-damage out of the opponents-drain avenue.
    # Serve widened with the past-tense "lost life this turn" THRESHOLD wording
    # (Spectacle / Rakdos payoffs — Stromkirk Bloodthief, Rakdos Lord of Riots) the
    # continuous "loses life" branches missed. Opponent-anchored so a self "you lost
    # life this turn" payoff (Ludevic) never matches.
    ("lifeloss_matters", "opponents"): _spec(
        "Drain",
        "repeatable life-drain and aristocrats payoffs",
        # Serve on the lanes' idents: life-loss doers and payoffs share one avenue.
        None,
        serve_idents=frozenset(
            {"lifeloss_makers|opponents|", "lifeloss_matters|opponents|"}
        ),
    ),
    # The bare `pay \d+ life` matched 39 painlands/fetchlands (Blood Crypt, Sacred
    # Foundry) that are mana fixing, not a life-as-resource engine. VETO lands; keep the
    # lose-life payoff/enabler clauses.
    ("lifeloss_matters", "you"): _spec(
        "Self life-loss",
        "ways to pay or lose life on demand to fuel your payoffs, plus the life-total "
        "swaps/resets and recovery that turn a low life total into an advantage",
        # The life payers and losers, "whenever you lose life" payoffs, pay-life
        # insurance and life-total swaps / resets (Selenia's package); see
        # _SELF_LIFELOSS_SERVE_IDENTS.
        None,
        serve_idents=_SELF_LIFELOSS_SERVE_IDENTS,
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
        # Serve on the lanes' idents: life-loss doers and payoffs share one avenue.
        None,
        serve_idents=frozenset(
            {"lifeloss_makers|opponents|", "lifeloss_matters|opponents|"}
        ),
    ),
    ("lifeloss_makers", "you"): _spec(
        "Self life-loss (makers)",
        "ways to pay or lose life on demand to fuel your payoffs, plus the life-total "
        "swaps/resets and recovery that turn a low life total into an advantage",
        None,
        serve_idents=_SELF_LIFELOSS_SERVE_IDENTS,
        serve_not=r"\bas this land enters\b|enters tapped",
    ),
    # Celebration (WOE): all 11 cards carry the exact phrase, so serve == open. A
    # Celebration commander floods nonland permanents each turn to switch the payoffs
    # on; the lane surfaces the other Celebration cards (Grand Ball Guest, Raging
    # Battle Mouse). Niche by design — the phrase appears nowhere else.
    ("celebration_matters", "you"): _spec(
        "Celebration",
        "ways to deploy two or more nonland permanents a turn, plus the payoffs",
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        None,
        serve_idents=frozenset({"celebration_matters|you|"}),
    ),
    # Tapped-creatures-matter: tap your team freely, then cash in the count (Throne of
    # the God-Pharaoh, Dragonscale General, Harvest Season) — backed by the grants that
    # make tapping safe (Masako: block while tapped; Saryth: deathtouch; Oak Street
    # Innkeeper: hexproof). \btapped excludes convoke's "untapped creatures".
    ("tapped_matters", "you"): _spec(
        "Tapped creatures matter",
        "payoffs that scale with tapped creatures, plus grants that make tapping safe",
        # Serve on the lane's ident.
        None,
        serve_idents=frozenset({"tapped_matters|you|"}),
    ),
    # Land sacrifice (Gitrog, Titania, Slogurk): lands hitting the graveyard is the
    # payoff, so repeatable "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb)
    # are the engine. Distinct from sacrifice_outlets (which excludes "sacrifice a land"
    # — the fetchland guard) and from landfall (lands ENTERING).
    ("land_sacrifice_matters", "you"): _spec(
        "Land sacrifice",
        "repeatable sac-a-land outlets and the payoffs for lands hitting the graveyard",
        # Serve on the lanes' idents; see _LAND_SAC_SERVE_IDENTS.
        None,
        serve_idents=_LAND_SAC_SERVE_IDENTS,
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
        # Serve on the lanes' idents; see _LAND_SAC_SERVE_IDENTS.
        None,
        serve_idents=_LAND_SAC_SERVE_IDENTS,
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
        None,
        serve_keyword_count_min=3,
    ),
    ("lands_matter", "you"): _spec(
        "Lands matter",
        "ramp, extra land drops, and recursion to maximize your land count",
        # The land-count payoffs plus the land ramp, extra land drops and landfall
        # that grow the count (same archetype as landfall); the recursion is the extra.
        None,
        serve_idents=frozenset(
            {
                "lands_matter|you|",
                "landfall|you|",
                "extra_land_drop|you|",
                "ramp|you|land",
            }
        ),
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # An ENGINE is recurring or bulk draw — NOT a one-shot cantrip. The serve's
    # `draw \w+ cards?` let \w+ eat the article in "draw a card", mislabeling ~753
    # one-shot cantrips (Remand, Cryptic Command) as engines — contradicting the
    # extractor's own _CARD_DRAW_RE. Mirror that: a recurring "at the beginning of …
    # draw" OR a bulk 2+ / additional draw. (The lane also reads a repeating
    # trigger's single draw — Rhystic Study, Kindred Discovery.)
    ("card_draw_engine", "you"): _spec(
        "Card-advantage engine",
        "protection, recursion, and payoffs for a repeatable draw engine",
        # Serve on the lane's ident: the repeatable draw engines. ETB bulk draw stays
        # the self_etb_payload lane's; granted-trigger draws are a lane gap.
        None,
        serve_idents=frozenset({"card_draw_engine|you|"}),
        search={"preset_names": ("card-draw",)},
    ),
    # Drop the self-only `draws? an additional card` (it belongs to the YOU engine); the
    # EACH avenue is symmetric/group draw only.
    ("card_draw_engine", "each"): _spec(
        "Group draw / wheel",
        "symmetric draw with punisher payoffs (Nekusar-style)",
        # Serve on the lanes' idents: symmetric draw and its punisher payoffs.
        None,
        serve_idents=frozenset({"card_draw_engine|each|", "group_hug_draw|each|"}),
    ),
    # task #83 (theme-preset structural views): cantrip — a bounded single-draw
    # rider (Preordain/Opt-shaped), the crosswalk_signals._cantrip lane's key. A
    # cantrip deck wants more of the same (low-opportunity-cost card selection)
    # plus spellslinger payoffs (prowess/magecraft) that reward casting a dense
    # instant/sorcery base.
    ("cantrip", "you"): _spec(
        "Cantrips",
        "more low-opportunity-cost card selection and spellslinger payoffs",
        # A cantrip is an instant or sorcery (the type dim). Permanents that draw a card
        # (Mulldrifter) are left to blink_flicker / self_etb_payload by design.
        None,
        serve_idents=frozenset({"cantrip|you|"}),
        serve_types=("Instant", "Sorcery"),
    ),
    # The serve names the damage DOUBLERS the blurb already promises — replacement
    # effects (CR 701.10g) worded "deals double/twice that much damage" / "deals that
    # much damage plus" / "if a source … would deal damage … instead" (Furnace of Rath,
    # Gratuitous Violence, Torbran) — through the damage_doubling ident.
    ("direct_damage", "you"): _spec(
        "Burn / pingers",
        "repeatable direct damage — pingers, burn, and damage doublers",
        # Burn, each-creature pingers, damage reflectors (Repercussion) and doublers;
        # gains X and divided burn (Banefire, Fireball). Damage to creatures only is
        # removal's; one-shot or granted doublers (Isengard Unleashed) are a
        # damage_doubling lane gap.
        None,
        serve_idents=frozenset(
            {
                "direct_damage|you|",
                "aoe_ping|you|",
                "damage_reflect|you|",
                "damage_doubling|you|",
            }
        ),
        extras=(_DEATHTOUCH_GEAR_EXTRA,),
        search={"preset_names": ("burn",)},
    ),
    # `add .* mana of any` captured fixing (Birds, City of Brass), not amplification.
    # The serve is the doublers/triplers (a "tap … for mana" trigger that adds/produces
    # extra), through the lane's ident, plus the {x} X-spend payoffs by printed cost.
    ("mana_amplifier", "you"): _spec(
        "Big mana",
        "mana doublers plus the X-spells and expensive bombs to spend it on",
        # The lane plus X-spells by printed mana cost; gains the symmetric and land-type
        # doublers (Mana Flare, Vernal Bloom). The old {X} arm served every X ability
        # and tax; lane gap: Groundchuck & Dirtbag.
        None,
        serve_idents=frozenset({"mana_amplifier|you|"}),
        serve_mana_cost=r"\{X\}",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    # Voltron suits up one creature with Equipment (CR 301.5) and BUFF Auras (CR 303).
    # Gate on the Equipment/Aura subtype, but VETO pure-control Auras (Pacifism /
    # Faith's Fetters — ~167 of them) that pacify rather than buff. Keep the oracle as a
    # residual for equip-cost reducers / tutors that aren't themselves Equipment.
    ("voltron_matters", "you"): _spec(
        "Voltron / equipment & auras",
        "equipment, auras, equip-cost reducers, and tutors to suit up one creature",
        # Serve on the lanes' idents plus the Equipment / Aura type gate. Remainder:
        # the equip-cost reducers and suit-up tutors the lanes read are the idents'.
        None,
        serve_idents=_VOLTRON_IDENTS,
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
        search={"preset_names": ("equip",)},
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
        None,
        serve_idents=_VOLTRON_IDENTS,
        serve_types=("equipment", "aura"),
        serve_keywords=("reconfigure",),
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls"
        r"|enchant (?:player|land|forest|island|swamp|mountain|plains)",
        extras=(_VOLTRON_PROTECT_EXTRA, _EXTRA_COMBAT_EXTRA),
        search={"preset_names": ("equip",)},
    ),
    # An extreme power-for-cost beater (Lord of Tresserhorn 10/4, Yargle 18/6) wins by
    # connecting ONCE for lethal — serve the damage amplifiers that convert raw power
    # into a kill: grant infect (power -> poison) and grant double strike (2x). Distinct
    # from voltron (equipment/auras): these are the combat tricks/auras that close.
    ("one_punch", "you"): _spec(
        "One-punch finishers",
        "amplify your huge body into a one-shot kill — grant infect or double strike "
        "(Tainted Strike, Temur Battle Rage, Grafted Exoskeleton)",
        # Serve on the grant lanes' idents for infect / double strike granted to
        # another creature; a creature's own keyword is out by design.
        None,
        serve_idents=frozenset(
            f"{lane}|{scope}|{kw}"
            for kw in ("double strike", "infect")
            for lane, scope in (
                ("keyword_grant_target", "you"),
                ("team_buff", "you"),
                ("aura_equip_kw_grant", "you"),
                ("all_creatures_kw_grant", "any"),
            )
        ),
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
        # The fliers are the avenue (the keyword dim); the flying GRANTERS are the
        # Flying granters sub-avenue, served on the grant lanes' flying idents.
        None,
        serve_keywords=("flying",),
        extras=(
            SubAvenue(
                "Flying granters",
                "effects that give your attackers flying so they connect",
                serve=Serve(signal_idents=_FLYING_GRANT_IDENTS),
            ),
        ),
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
        # Serve on the lane's swap ident. Remainder: exchanges between two other
        # permanents or players (Legerdemain, Juxtapose) are a lane gap.
        None,
        serve_idents=frozenset({"control_exchange|you|swap"}),
    ),
    # Kira shields your creatures from removal, so PERMANENT theft sticks: a contingent
    # steal (Sower, Roil — lost if the thief dies) can't be undone, and a theft engine
    # (Empress Galina) survives. Serve the non-temporary theft; the `until end of turn`
    # veto drops Threaten-style steals, which gain nothing from protection.
    ("theft_protection", "you"): _spec(
        "Protected theft",
        "theft creatures whose steal sticks because you shield them from removal — "
        "Sower of Temptation, Roil Elemental, Empress Galina",
        # The theft lane's ident (veto unchanged) reads control Auras (Control Magic),
        # group theft (Mass Manipulation) and stealing a spell (Commandeer), which a
        # shield never protects. Regaining your own card (Coveted Falcon) is noise.
        None,
        serve_idents=frozenset({"gain_control|you|"}),
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
        # Serve the X-spells by printed mana cost, as xspell_matters reads them: the
        # sink is the {X} you pay (Torment of Hailfire, Hangarback Walker). Count-set X
        # (The Rack) is out; activated X sinks (Crypt Rats) are a lane gap.
        None,
        serve_mana_cost=r"\{X\}",
    ),
    # A commander that exiles/takes opponents' library TOPS (Circu, Ragavan, Grenzo)
    # wants to SEE those tops — play-with-top-revealed shows what it will exile/steal.
    # A shuffle-peek (Psychic Surgery) isn't a continuous top-reveal and stays out.
    ("opp_top_exile", "you"): _spec(
        "See opponents' tops",
        "reveal opponents' library tops so you exile/steal the best card — Field of "
        "Dreams, Wizened Snitches, Lantern of Insight",
        # Serve on the peek ident (seeing opponents' tops). The bare exile-from-top
        # ident is theft, which the theft lanes serve, so it stays out.
        None,
        serve_idents=frozenset({"opp_top_exile|you|peek"}),
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
        None,
        serve_mana_cost=r"^\{0\}$",
        search={"card_type": "Artifact", "cmc_max": 0},
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, support, and creatures to crew them",
        # Also credit vehicle SUPPORT: cheat a Vehicle into play, ramp/cost-reduction
        # for Vehicle spells (Oviya, Intrepid Stablemaster), not just core text.
        None,
        serve_types=("vehicle",),
        serve_idents=frozenset({"vehicles_matter|you|"}),
        search={"preset_names": ("crew",)},
    ),
    ("low_power_matters", "you"): _spec(
        "Small creatures matter",
        "payoffs and anthems that reward your low-power creatures attacking and going "
        "wide (Raid Bombardment, Reconnaissance Mission)",
        # Serve on the lane's ident: it reads Assemble the Players' cast-from-the-top
        # permission and the low-power reanimators (Reveillark, Smile at Death). NO
        # power_max serve (it would flood the lane with vanilla small bodies).
        None,
        serve_idents=frozenset({"low_power_matters|you|"}),
    ),
    ("scry_surveil_matters", "you"): _spec(
        "Scry / surveil matters",
        "scry and surveil to fire these payoffs — note surveil also fills your "
        "graveyard (see Your graveyard), while scry is pure top-of-library selection",
        # Serve on the lanes' idents: scry / surveil payoffs and the scry and surveil
        # makers. Remainder: Empower Jace (a token's surveil) is a lane gap.
        None,
        serve_idents=frozenset(
            {
                "scry_surveil_matters|you|",
                "topdeck_selection|you|scry",
                "topdeck_selection|you|surveil",
            }
        ),
    ),
    # ── Named-mechanic long tail ────────────────────────────────────────────────
    # _matters sweep (ADR-0034): monarch split. The MAKER side — cards that GRANT
    # the monarch ("you become the monarch", CR 725). The avenue it opens is the
    # full monarch package (the grant + the evasion/combat-damage payoffs that
    # defend it), so the serve stays broad; only the lane KEY encodes the doer role.
    ("monarch_makers", "you"): _spec(
        "Monarch (become)",
        "become the monarch — plus the evasion and combat triggers that defend it",
        # Serve on the lanes' idents (2026-10-18): the regex's one extra was Regal
        # Sliver's quoted, granted monarch trigger (a granted-ability gap).
        None,
        serve_idents=frozenset({"monarch_makers|you|", "monarch_matters|you|"}),
        extras=(_PILLOWFORT_EXTRA,),
    ),
    ("monarch_matters", "you"): _spec(
        "Monarch",
        "defend the monarch — evasion and combat-damage triggers",
        # Serve on the lanes' idents (2026-10-18): the regex's one extra was Regal
        # Sliver's quoted, granted monarch trigger (a granted-ability gap).
        None,
        serve_idents=frozenset({"monarch_makers|you|", "monarch_matters|you|"}),
        extras=(_PILLOWFORT_EXTRA,),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the initiative split — cards that
    # TAKE the initiative (CR 720). The avenue it opens is the full initiative package
    # (takers + the "have the initiative" payoffs + Undercity venture), so the serve
    # stays broad; only the lane KEY encodes the doer role.
    ("initiative_makers", "you"): _spec(
        "Initiative (take)",
        "take the initiative; venture through the Undercity",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"initiative_makers|you|", "initiative_matters|you|"}),
    ),
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "hold the initiative payoffs; venture through the Undercity",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"initiative_makers|you|", "initiative_matters|you|"}),
    ),
    ("ring_matters", "you"): _spec(
        "The Ring",
        "Ring-bearer payoffs — cards rewarded by the Ring tempting you",
        # Serve on the lanes' idents (2026-10-18): the regex served the payoffs but not
        # the tempters that fuel them (Claim the Precious, Boromir), and credited Lord
        # of the Nazgûl for naming Ring-bearers in a protection clause.
        None,
        serve_idents=frozenset({"ring_matters|you|", "ring_tempters|you|"}),
    ),
    # _matters sweep (ADR-0034): the maker side of the ring split. ring_tempters
    # fires on a NATIVE tempt action (the card itself does "the Ring tempts you" —
    # Boromir). The avenue it OPENS is the Ring-bearer payoffs to reward the tempting
    # (the ring_matters serve) plus more ways to tempt yourself.
    ("ring_tempters", "you"): _spec(
        "Tempt the Ring",
        "ways to tempt yourself with the Ring (advance the Ring-bearer)",
        # Serve on the lanes' idents (2026-10-18): the regex missed the Ring-bearer
        # payoffs a tempter feeds (Sauron, the Necromancer).
        None,
        serve_idents=frozenset({"ring_tempters|you|", "ring_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the venture split — cards that
    # venture / take the initiative (CR 701.49a; CR 726.2: taking the initiative
    # ventures into Undercity). The avenue it opens is the venture enablers
    # package; only the lane KEY encodes the doer role.
    # Serve on the lanes' idents (reads.keyword_resource_events): the regex
    # missed the take-the-initiative cards and room-trigger doubling (Hama
    # Pashar). It also served a phase gap (You Find a Cursed Idol's venture mode
    # is dropped) and an opponent hoser (Keen-Eared Sentry).
    ("venture_makers", "you"): _spec(
        "Venture (enablers)",
        "venture enablers — cards that venture into the dungeon",
        None,
        serve_idents=_VENTURE_SERVE_IDENTS,
    ),
    ("venture_matters", "you"): _spec(
        "Venture / dungeons",
        "dungeon-completion payoffs and dungeon-trigger doublers",
        None,
        serve_idents=_VENTURE_SERVE_IDENTS,
    ),
    # _matters sweep (ADR-0034): the energy split. energy_makers fires on cards
    # that PRODUCE energy (a real `energy` Effect — "you get {E}"); its avenue
    # serves the rest of the energy engine (more producers + the sinks that spend
    # it).
    # Serve on the lanes' idents (reads.keyword_resource_events). What the regex
    # also served is phase gaps: Izzet Generatorium's energy replacement, a
    # replicate / unearth cost paid in {E}.
    ("energy_makers", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        None,
        serve_idents=_ENERGY_SERVE_IDENTS,
    ),
    # The PAYOFF side of the energy split: a card that SPENDS energy (a
    # "Pay {E}{E}:" sink, a "you may pay {E}" trigger) or rewards getting it (a
    # "whenever you get {E}" trigger). It wants the producers that fuel it.
    ("energy_matters", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        None,
        serve_idents=_ENERGY_SERVE_IDENTS,
    ),
    # Devotion (CR 700.5) counts single-color mana SYMBOLS among permanents you control,
    # so the enablers are structurally heavy-pip permanents — a dimension oracle text
    # can't express. Keep `devotion to` for the payoffs; add the pip gate (≥2 of one
    # color, nonland permanent) for the enablers the old serve was blind to.
    ("devotion_matters", "you"): _spec(
        "Devotion",
        "heavy colored pips to grow devotion and devotion payoffs",
        # Serve on the lane's ident (2026-10-18): the regex missed the chroma counts
        # of colored pips (Primalcrux, Heartlash Cinder); its one extra, Altar of the
        # Pantheon's devotion boost, is a lane gap the lane should close.
        None,
        serve_idents=frozenset({"devotion_matters|you|"}),
        serve_min_devotion=2,
    ),
    # The central body of the archetype IS the planeswalkers (type) and the proliferate
    # payoffs (keyword) — both authoritative Scryfall fields the oracle-only serve named
    # none of.
    ("superfriends_matters", "you"): _spec(
        "Superfriends",
        "planeswalkers plus proliferate and loyalty payoffs to protect them",
        # The lane reads "if you control a <name> planeswalker" payoffs (Jace's
        # Sentinel). Pillowfort "attacks you or planeswalkers" clauses are noise; lane
        # gaps: empower Jace (Hexhaven Battalion), "put loyalty counters" (Inspired
        # Tethermage).
        None,
        serve_idents=frozenset({"superfriends_matters|you|"}),
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
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        None,
        serve_idents=frozenset({"historic_matters|you|"}),
        serve_types=("legendary", "artifact", "saga"),
    ),
    ("legends_matter", "you"): _spec(
        "Legends matter",
        "legendary creatures and the payoffs that reward a board of legends",
        # The lane reads the legend payoffs the regex missed (Arwen's Gift, Esquire of
        # the King); "nonlegendary" text is out. It also reads legend hate (Hero's
        # Demise), a lane false positive.
        None,
        serve_idents=frozenset({"legends_matter|you|"}),
        serve_types=("legendary",),
    ),
    # The big-hand lane splits by role at emission (ADR-0034: makers = no-max-hand-
    # size enablers, matters = cards-in-hand payoffs); both specs share one serve.
    ("big_hand_makers", "you"): _spec(
        "No maximum hand size",
        "no-max-hand-size enablers and the payoffs that reward a full grip",
        # Serves the no-max-hand-size enablers and the payoffs that scale with or
        # check your own hand; the remainder is drawbacks and taxes on a full hand,
        # end-the-turn discards, and stax hand-size checks (Ensnaring Bridge).
        None,
        serve_idents=_BIG_HAND_IDENTS,
    ),
    ("big_hand_matters", "you"): _spec(
        "Big hand payoffs",
        "card draw and no-max-hand-size payoffs that reward a full grip",
        # Serves the no-max-hand-size enablers and the payoffs that scale with or
        # check your own hand; the remainder is drawbacks and taxes on a full hand,
        # end-the-turn discards, and stax hand-size checks (Ensnaring Bridge).
        None,
        serve_idents=_BIG_HAND_IDENTS,
    ),
    # A party (CR 700.x) is one each of Cleric/Rogue/Warrior/Wizard — those creature
    # SUBTYPES are the members. The bare `\bparty\b` caught 3 flavor FPs; gate the
    # members on the subtype field, keep the party-phrase oracle for the payoffs.
    ("party_matters", "you"): _spec(
        "Party",
        "Clerics, Rogues, Warriors, and Wizards to assemble a full party",
        # Serve on the lane's ident (2026-10-18): the regex's one extra was Champions
        # from Beyond, whose "Light Party" / "Full Party" ability words aren't a party.
        None,
        serve_idents=frozenset({"party_matters|you|"}),
        serve_types=("cleric", "rogue", "warrior", "wizard"),
    ),
    ("exile_matters", "you"): _spec(
        "Exile pile matters",
        "impulse/foretell exile enablers and payoffs for cards in exile",
        # The lane reads the exile payoffs the regex missed (Rakshasa Vizier, Kaya,
        # Spirits' Justice); "exiled this way" riders are noise. It also reads removal
        # riders that count exiled creatures (Curse of the Swine), a lane false
        # positive.
        None,
        serve_idents=frozenset({"exile_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): split the conflated experience lane by role.
    # experience_makers = the MAKER arm (cards that GAIN experience counters —
    # Ezuri, Mizzix, Kalemne); experience_matters = the PAYOFF arm (cards that
    # SCALE off your experience count — Atreus draw-X, Azula pump-X). Both share
    # one serve (the two lanes' idents).
    ("experience_makers", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"experience_makers|you|", "experience_matters|you|"}),
    ),
    ("experience_matters", "you"): _spec(
        "Experience payoffs",
        "payoffs that scale with experience counters",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"experience_makers|you|", "experience_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): poison split by role. poison_makers = the MAKER arm
    # (infect/toxic threats + poison-counter givers that DEAL the poison);
    # poison_matters = the PAYOFF arm (cards that REWARD a high poison count —
    # Corrupted, proliferate-to-finish). Both share one serve: the avenue
    # legitimately composes infect/toxic threats AND the poison payoffs
    # together (ADR-0034: only membership splits by role, the avenue offers both).
    ("poison_makers", "opponents"): _spec(
        "Poison / infect",
        "infect and toxic threats to stack poison counters on opponents",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset(
            {"poison_makers|opponents|", "poison_matters|opponents|"}
        ),
    ),
    ("poison_matters", "opponents"): _spec(
        "Poison payoffs",
        "payoffs that reward a high poison count plus proliferate to finish",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset(
            {"poison_makers|opponents|", "poison_matters|opponents|"}
        ),
    ),
    # "Modified" (CR 122) = a creature with a +1/+1 counter, Aura, OR Equipment. The
    # serve named only the literal word (the payoffs); the ENABLERS are structurally
    # Equipment/Aura permanents and counter-placers. Add those dimensions.
    ("modified_matters", "you"): _spec(
        "Modified",
        "counters, Auras, and Equipment to keep creatures modified",
        # Serve on the lanes' idents: the modified payoffs plus the
        # +1/+1 counter package (makers, payoffs, doublers, proliferate — every
        # counter is a modification). The losses are the +1/+1 package's own
        # (blink-and-return-with-a-counter, tribute) and five "modified" cards
        # whose predicate phase drops (Ian the Reckless, Lethal Exploit, Lethal
        # Throwdown; Heir of the Ancient Fang and Lion Umbra still serve).
        None,
        serve_idents=_PLUS_ONE_SERVE_IDENTS | {"modified_matters|you|"},
        serve_types=("equipment", "aura"),
    ),
    ("has_mutate", "you"): _spec(
        "Mutate",
        "mutate creatures and mutate-trigger payoffs",
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        None,
        serve_idents=frozenset({"has_mutate|you|"}),
    ),
    # _matters sweep (ADR-0034): food split. The make_token MAKER arm
    # (food_makers, cards that create Food tokens) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (food_matters) both serve the same Food
    # makers-plus-sacrifice-and-lifegain avenue. The union == the old
    # food_matters; only the role label differs.
    #
    # Serve on the lanes' idents: food_makers read granted / nested Food
    # creation, a token replacement that adds a Food (Tippy-Toe, Peregrin Took)
    # and the "artifacts you control are Foods" granters (Gourmand's Talent,
    # Ragost); food_matters reads a forage (CR 701.61a) and a spell's additional
    # Food sacrifice (Feed the Cycle). The regex's remainder is gift Foods only an
    # opponent creates (CR 111.2) and two phase gaps (Osteomancer Adept's
    # forage cast permission, The Fourth Doctor's reflexive Food).
    ("food_makers", "you"): _spec(
        "Food tokens",
        "Food makers plus sacrifice outlets and lifegain payoffs",
        None,
        serve_idents=frozenset({"food_makers|you|", "food_matters|you|"}),
    ),
    ("food_matters", "you"): _spec(
        "Food token payoffs",
        "cards that sacrifice or reference Food tokens, plus lifegain payoffs",
        None,
        serve_idents=frozenset({"food_makers|you|", "food_matters|you|"}),
    ),
    # Type change (the TYPE analog of color_change): a creature-type hoser (Gor Muldrak
    # "protection from Salamanders") wants the type-CHANGING toolbox — turn opponents'
    # creatures into the punished type so the hoser blanks them. Genuine changers only
    # ("target/each creature becomes <type>"), NOT the tribal anthems that merely
    # "choose a creature type" then buff your own.
    ("type_change", "you"): _spec(
        "Type change",
        "creature-type changers to force opponents into the punished type",
        # Serve on the type-changer lane's idents (any / each / you scopes). Remainder:
        # a text-changing word swap (Artificial Evolution) is a lane gap.
        None,
        serve_idents=frozenset(
            {
                "type_changers|any|*",
                "type_changers|each|*",
                "type_changers|you|",
                "type_changers|you|all",
            }
        ),
    ),
    # Color change: serves the color_change lane's makers and its color-conditional
    # payoffs. Remainder: "chosen color" self-colourings (commander-only text) and
    # a few color-word text swaps.
    ("color_change", "you"): _spec(
        "Color change",
        "effects that add or change colors — fixing plus color-matters enablers",
        None,
        serve_idents=frozenset({"color_change|you|", "color_change|you|payoff"}),
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
        # Serve on the lane's ident: the payoffs and the land-type granters.
        None,
        serve_idents=frozenset({"domain_matters|you|"}),
    ),
    ("clue_matters", "you"): _spec(
        "Clues / investigate",
        "investigate enablers and artifact/draw payoffs for Clues",
        # Serve on the lanes' idents (2026-10-18): the regex missed a Clue payoff that
        # names Clues only in the plural (Tangletrove Kelp).
        None,
        serve_idents=frozenset({"clue_matters|you|", "clue_makers|you|"}),
    ),
    # _matters sweep (ADR-0034): clue split. The make_token MAKER arm (clue_makers,
    # cards that create Clue tokens / investigate) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (clue_matters) both serve the same
    # investigate-and-crack avenue. The union == the old clue_matters; only the role
    # label differs.
    ("clue_makers", "you"): _spec(
        "Clue makers / investigate",
        "Clue makers plus artifact/draw payoffs for Clues",
        # Serve on the lanes' idents (2026-10-18): the regex missed a Clue payoff that
        # names Clues only in the plural (Tangletrove Kelp).
        None,
        serve_idents=frozenset({"clue_makers|you|", "clue_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): blood split. The make_token MAKER arm
    # (blood_makers, cards that create Blood tokens) and the sacrifice/ref/
    # sacrificed-trigger PAYOFF arm (blood_matters) both serve the same
    # Blood-rummage-and-sacrifice avenue. The union == the old blood_matters;
    # only the role label differs.
    ("blood_makers", "you"): _spec(
        "Blood tokens",
        "Blood makers plus rummage and sacrifice payoffs",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"blood_makers|you|", "blood_matters|you|"}),
    ),
    ("blood_matters", "you"): _spec(
        "Blood token payoffs",
        "cards that sacrifice or reference Blood tokens",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"blood_makers|you|", "blood_matters|you|"}),
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
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"daynight_makers|you|", "daynight_matters|you|"}),
    ),
    ("daynight_matters", "you"): _spec(
        "Day / Night",
        "daybound/nightbound creatures and day-night transition payoffs",
        # Serve on the lanes' idents (2026-10-18): they reproduce the regex exactly.
        None,
        serve_idents=frozenset({"daynight_makers|you|", "daynight_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): voting split. The vote-CREATOR doer arm
    # (voting_makers, will-of-the-council / council's-dilemma cards that run a
    # vote) and the finish-voting PAYOFF arm (voting_matters, triggers off a vote
    # without creating one) both serve the same multiplayer-politics avenue. The
    # union == the old voting_matters; only the role label differs.
    ("voting_makers", "each"): _spec(
        "Voting / council",
        "will-of-the-council and vote effects — multiplayer politics",
        # Serve on the lanes' idents: vote makers and vote payoffs share one avenue.
        None,
        serve_idents=frozenset({"voting_makers|each|", "voting_matters|each|"}),
    ),
    ("voting_matters", "each"): _spec(
        "Voting / council payoffs",
        "cards that trigger off a vote — multiplayer politics",
        # Serve on the lanes' idents: vote makers and vote payoffs share one avenue.
        None,
        serve_idents=frozenset({"voting_makers|each|", "voting_matters|each|"}),
    ),
    ("coven_matters", "you"): _spec(
        "Coven",
        "creatures with different powers to turn on coven",
        # Serve on the lane's ident (2026-10-18): it reproduces the regex exactly.
        None,
        serve_idents=frozenset({"coven_matters|you|"}),
    ),
    # Conjure (Alchemy): serves the conjure lane's idents. Remainder: conjures the
    # lane misses (an emblem, a Saga chapter, "conjure a card named" ETBs).
    ("conjure_makers", "you"): _spec(
        *SWEEP_LABELS["conjure_makers"],
        None,
        serve_idents=frozenset({"conjure_makers|you|"}),
    ),
    # Token doubling: a token doubler wants the token MAKERS it multiplies (Hornet
    # Queen), other token doublers to stack (Parallel Lives), and the go-wide / ETB
    # payoffs every doubled token feeds. Distinct from counter doubling.
    ("token_doubling", "you"): _spec(
        "Token doubling",
        "token makers to multiply, plus other token doublers and go-wide payoffs",
        # Serve rides the lanes: the creature-token makers (amass, endure and
        # populate included) and the other token doublers.
        None,
        serve_idents=_TOKEN_MAKER_IDENTS | {"token_doubling|you|"},
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
        # Serve on the +1/+1 package's idents: the cards that PUT counters, proliferate,
        # or replace "that many plus one" (Hardened Scales). Gaps: sunburst grants (Lux
        # Artillery) are the package's documented exclusion.
        None,
        serve_idents=_PLUS_ONE_SERVE_IDENTS,
        extras=_COUNTERS_PACKAGE,
    ),
    # Serve is precise (the second-spell payoff), so the avenue stops crediting every
    # value permanent that draws.
    ("second_spell_matters", "you"): _spec(
        "Second-spell / storm-lite",
        "second-spell, multi-spell, and storm payoffs that reward chaining casts",
        # Serve on the lane's ident (2026-10-18): the regex missed the "cast two or
        # more spells this turn" and "a player casts their second spell" payoffs
        # (Ledger Shredder, Vengevine, Brightspear Zealot).
        None,
        serve_idents=frozenset({"second_spell_matters|you|"}),
    ),
}
