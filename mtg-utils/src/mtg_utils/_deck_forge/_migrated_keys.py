"""Migrated-key registry for the ADR-0027 regex→Card IR strangler.

Extracted verbatim from ``signals.py`` (behavior-neutral split, 2026-06-21) so
that each migration edits this compact data file instead of scrolling the
multi-thousand-line ``signals.py`` monolith — cuts the per-edit token cost
(input-tokens-per-minute) that was driving API rate limits.

``signals`` re-exports ``MIGRATED_KEYS`` for import compatibility, so existing
``from mtg_utils._deck_forge.signals import MIGRATED_KEYS`` callers are unaffected.
"""

from __future__ import annotations

MIGRATED_KEYS: frozenset[str] = frozenset(
    {
        # ADR-0027 big_hand_matters — migrated to the Card IR. STRUCTURAL ARM: the
        # v23 `no_max_handsize` Effect category (project._project_static_mods emits
        # it for phase's `NoMaximumHandSize` static mode — Reliquary Tower / Thought
        # Vessel / Spellbook / Folio of Fancies, the 25 commander-legal "no maximum
        # hand size" enablers, all scope you, CR 402.2). MIRROR: the byte-identical
        # _BIG_HAND_MATTERS_MIRROR (the OR of the two deleted producers — the
        # _HAND_FLOOR row + the SWEEP row) in _signals_ir._IR_KEPT_DETECTORS recovers
        # the under-structured tail phase leaves textual — the "X = the number of
        # cards in your hand" P/T-scaling payoffs (Maro, Psychosis Crawler, Sturmgeist:
        # phase encodes these as a `characteristic_pt` Effect carrying NO in:hand zone)
        # and the "N or more cards in hand" conditions. The DELETED IR `in:hand`-zone
        # arm was UNUSABLE: phase's _zone_tags surfaces `in:hand` on every discard
        # ("discards their hand" — 116 cards) and hand-scaling draw (16), structurally
        # indistinguishable from a genuine HandSize count operand, so the arm over-fired
        # on hand-as-zone DISCARD/REVEAL references (the distinct lane boundary). The
        # structural arm adds 0 over the mirror (all 25 enablers carry "no maximum hand
        # size" text). VOLTRON: both deleted producers fired HIGH-confidence scope 'you'
        # and fed has_other_plan, so deleting them un-silences the Site-2 commander-
        # damage voltron tell on 9 bodies where big_hand is the sole plan (Akki
        # Underling, Thought Eater/Devourer, …); the byte-identical
        # _BIG_HAND_MATTERS_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS — the IR
        # is the SAME breadth, so the keys set would not broaden but the mirror is
        # the precise idiom) re-supplies has_other_plan. Commander-legal, floor-
        # disabled, by oracle_id: both == 140, ir_only == 0, regex_only == 0; scope
        # parity (all 'you', HIGH). The hand-written serve spec in signal_specs.py is
        # independent of the deleted regexes and survives. CR 402.2.
        "big_hand_matters",
        # Batch 1 — keys whose IR production is genuinely STRUCTURAL (not a
        # re-run of the deleted oracle regex), so deleting the regex cannot
        # regress the IR path. seek (phase `seek` effect category),
        # specialize (Scryfall `specialize` keyword), ki (phase counter-kind
        # projection). See ADR-0027.
        "seek_matters",
        "specialize_matters",
        "ki_counter_matters",
        # Group "bending" — the four bending lanes (airbend CR 701.65, earthbend
        # CR 701.66, waterbend CR 701.67, firebending CR 702.189). phase v0.1.19
        # doesn't structure these recent named mechanics, so the IR path detects
        # them from the kept word-detector mirror (_IR_KEPT_DETECTORS), NOT a
        # re-run of the deleted SWEEP_DETECTORS rows. A-B==0 (commander-legal,
        # floor lanes disabled). See ADR-0027.
        "airbend_matters",
        "earthbend_matters",
        "waterbend_matters",
        "firebending_matters",
        # Group "set-mechanics" — recent-set named mechanics. celebration (WOE
        # ability word), coven (MID ability word), outlaw (creature-type group),
        # snow (supertype), lessons (subtype) detect from the kept word-detector
        # mirror (_IR_KEPT_DETECTORS); enlist + companion detect from the Scryfall
        # keyword array (_IR_KEYWORD_MAP). All NON-floor IR sources; A-B==0
        # (commander-legal, floor lanes disabled). See ADR-0027.
        "celebration_matters",
        "coven_matters",
        "outlaw_matters",
        "snow_matters",
        "lessons_matter",
        "enlist_matters",
        "companion_keyword",
        # Group "structural" — keys backed by a STRUCTURED IR shape (not a re-run
        # of the deleted oracle regex). all_creatures_kw_grant ← GrantKeyword effect
        # on an "all creatures" subject; counter_move ← MoveCounters effect
        # (_DOER_EFFECT_KEYS); facedown_matters ← manifest/cloak/turn_face_up effect
        # categories + kept word mirror; nonhuman_attackers ← attacks trigger w/
        # NotSubtype:Human subject; opponent_draw_matters ← "drawn" trigger scoped
        # opp; token_doubling ← token-doubling replacement effect; voting_matters ←
        # kept word mirror. All NON-floor IR sources; A-B==0 (commander-legal, floor
        # lanes disabled). See ADR-0027.
        "all_creatures_kw_grant",
        "counter_move",
        "facedown_matters",
        "nonhuman_attackers",
        "opponent_draw_matters",
        "token_doubling",
        "voting_matters",
        # Group "restriction-narrow" (ADR-0027 projection deepening) — keys whose
        # tail cards phase folds into a generic carrier (a static restriction, an
        # Animate, a TargetOnly/Choose wrapper, an ismonarch condition) so the
        # mechanic survives only in raw. project._narrow_mechanic_refs appends a
        # precise `monarch`/`saddle`/`soulbond` marker effect (read via
        # _DOER_EFFECT_KEYS), and the ismonarch condition is lifted in
        # extract_signals_ir, so the lane fires from a NON-floor structural IR
        # source — A-B==0 (commander-legal, floor lanes disabled). soulbond also
        # reuses the Scryfall keyword; saddle also reuses the saddle keyword. Their
        # oracle-regex producers are deleted. See ADR-0027.
        "monarch_matters",
        "saddle_matters",
        "soulbond_matters",
        # Group "trigger-other raw-marker" (ADR-0027 projection deepening) — keys
        # whose tail cards are PAYOFF triggers phase flattened to event='other' (the
        # consequence is a typed effect; the trigger condition survives only in the
        # effect raw). project._narrow_trigger_other_refs appends a precise marker
        # effect (coin_flip / ring_tempt / discover / ninjutsu) read via
        # _DOER_EFFECT_KEYS, so the lane fires from a NON-floor structural IR source —
        # A-B==0 (commander-legal, floor lanes disabled). discover/ninjutsu also reuse
        # the Scryfall keyword; ring also raw-scans "Ring-bearer" (Sauron, no tempt
        # trigger). Their oracle-regex producers are deleted. boast/exhaust/explore/
        # scry_surveil got the same markers but a static-grant / delayed-trigger /
        # replacement-drop remainder keeps them on regex (not migrated). See ADR-0027.
        "coin_flip",
        "discover_matters",
        "ninjutsu_matters",
        "ring_matters",
        # Group "conferred-keyword re-parse" (ADR-0027 projection deepening) — keys
        # whose tail cards GRANT a keyword/ability to a CLASS of objects, which phase
        # folds into a grant carrier (cast_with_keyword / grant_spell_ability /
        # grant_keyword) so the granted keyword survives only in raw.
        # project._narrow_conferred_keyword_refs appends a precise marker effect, so
        # the lane fires from a NON-floor structural IR source — A-B==0 (commander-
        # legal, floor lanes disabled). affinity_type ← the Scryfall affinity keyword
        # + an `affinity` marker for "spells you cast have affinity for X" (Tezzeret,
        # …); damage_reflect ← the on-card damage_received+damage co-occurrence + a
        # `damage_reflect` marker for the quoted reflection grant (Spiteful Sliver);
        # evasion_denial ← phase's named-walk evasion_denial effect + an
        # `evasion_denial` marker for the generic-landwalk umbrella (Staff of the
        # Ages). Their oracle-regex SWEEP_DETECTORS rows are deleted (affinity also
        # left _IR_FLOOR_LANES). madness/foretell/devour/connive/counter_control got
        # the same markers (recall improved) but a condition-drop (Anje), a Foretold-
        # predicate (Niko), a token-profile residual, and modal/Aura-host parse-drops
        # keep them on regex pending a later capability. See ADR-0027.
        "affinity_type",
        "damage_reflect",
        "evasion_denial",
        # Group "go-wide count-over-own-board" (ADR-0027 projection deepening) — the
        # headline scaling lane. creatures_matter fires from STRUCTURAL IR alone (it is
        # NOT in _IR_FLOOR_LANES — its broad oracle floor was never floor-mirrored into
        # the IR path): a COUNT/AGGREGATE operand over your generic creature board (a
        # SetDynamicPower / ModifyCost-Reduce / Aggregate-Sum / replacement-counter
        # count, plus phase's named formidable condition and the for-each / X-is-count
        # oracle markers), a TEAM ANTHEM (pump / keyword grant / base-P/T set over the
        # generic set), a MASS keyword/evasion grant (CantBeBlockedBy static + the
        # narrow oracle mass-grant marker), a MASS untap (SetTapState scope=All + the
        # "untap all creatures you control" marker), and the token-maker cross-open.
        # All 14 adjudicated gaps fire structurally; the floor-disabled A-B residual is
        # 100% over-fire (subtype/color lords = type_matters CR 205.3, single-target,
        # attack/combat triggers, cost taps). Its over-broad oracle-regex _DETECTORS
        # producer ("creatures you control"/"for each creature you control" substring)
        # is deleted; the serve spec stays in signal_specs. See ADR-0027.
        "creatures_matter",
        # devour_matters (CR 702.82) — the sacrifice-creatures-for-+1/+1-counters
        # keyword lane. Fires from STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES): the
        # Scryfall `devour` keyword via _IR_KEYWORD_MAP plus phase's `devour` effect
        # category (the `devour N` make-token marker + the supplement keyword value),
        # fanned by the cat=="devour" arm in extract_signals_ir. Floor-mirror-dep==0
        # (commander-legal, floor lanes disabled): the IR set is identical with the
        # floor on or off. Its over-broad "\bdevour\b" SWEEP_DETECTORS regex producer
        # is deleted — it 100% over-fired on the "Devour Intellect" FLAVOR WORD
        # (CR 207.2d, no rules meaning) and the "Devour in Flames" CARD NAME, neither
        # being the Devour keyword; the structural IR correctly excludes both. The
        # serve spec stays in signal_specs. See ADR-0027.
        "devour_matters",
        # blood_matters (CR 111.10g — the Blood token subtype, a discard-a-card-draw
        # artifact-token rummage engine) — the token-subtype synergy lane. REMOVED
        # from _IR_FLOOR_LANES and now fires from the STRUCTURAL IR alone: a
        # Blood-subtype make_token subject (the maker), a Blood SACRIFICE PAYOFF (a
        # `sacrifice` Effect OR a `sacrificed` Trigger whose subject Filter carries
        # the Blood subtype — Wedding Security, Blood Hypnotist; the token-subtype
        # synergy widening reads sacrifice subjects, not just maker subjects), and the
        # CHOOSE-LIST / GRANTED-ABILITY maker recovery (Transmutation Font's "create
        # your choice of a Blood token", Ceremonial Knife's quoted "create a Blood
        # token" grant — project._narrow_token_subtype_makers appends make_token
        # markers for the dropped subtypes). Floor-mirror-dependency == 0 (commander-
        # legal, floor lanes disabled): all 41 cards fire structurally with the floor
        # on or off (the 4 former floor-only gap cards now bind structurally). Its
        # "blood tokens?" _HAND_FLOOR producer is deleted; the serve spec stays in
        # signal_specs. The widening generalizes to clue/food/treasure (genuine
        # recall: +18/+10/+8 structural firings, all real makers/sac-payoffs), which
        # keep their floor for now. See ADR-0027.
        "blood_matters",
        # Group "tail-supplement" (ADR-0027 projection deepening) — the 1-2-card
        # synthesis tail: keys whose last residual is a named-mechanic reference phase
        # DROPS (a static grant, a payoff condition, a replacement clause, a delayed
        # trigger, a count operand), recovered by a NARROW supplement marker so the
        # lane fires from a NON-floor structural IR source. Floor-mirror-dep==0
        # (commander-legal, floor lanes disabled) for each; the boundary over-fires
        # (Bloodboil's "Crown of Madness" / Malanthrope's "Scavenge the Dead" ability
        # words, CR 207.2c, rules-lawyer-verified) are the cards the structural IR
        # correctly drops. Each key's oracle-regex producer is deleted; serve specs
        # stay in signal_specs. See ADR-0027.
        #   boast      ← `boast` keyword + event='other' payoff + "can boast" face
        #                amplifier marker (Birgi).
        #   connive    ← phase's connive effect + the applied/granted marker + the
        #                Scryfall connive keyword granter-lift (Security Bypass).
        #   end_the_turn ← phase's end_the_turn effect (supplement category reconciled
        #                — Obeka).
        #   exhaust    ← `exhaust` keyword + the exhaust payoff marker, now firing on
        #                the delayed-trigger-inside-activated shape (Pit Automaton).
        #   extra_end_step ← phase's extra_end effect + the "additional end step" face
        #                marker (Y'shtola; left _IR_FLOOR_LANES — it was never floored).
        #   madness    ← `madness` keyword + grant marker + "if it has madness" payoff
        #                marker (Anje); left _IR_FLOOR_LANES.
        #   mutate     ← `mutate` keyword + "if it has mutate" keyword-less payoff
        #                marker (Pollywog).
        #   phasing    ← `phasing` keyword + phase-out DOER markers + event='other'
        #                payoff marker (War Doctor); left _IR_FLOOR_LANES.
        #   trigger_doubling ← phase's trigger_doubling effect + the granted/quoted
        #                "triggers an additional time" face marker (The Masamune).
        #   experience ← GivePlayerCounter gainers + the op="experience" scaler
        #                operand (Atreus, Azula).
        #   explore    ← `explore` keyword (authoritative, 53 ⊇ 44 regex) + the
        #                event='other' explore payoff (Topography Tracker, Glowcap).
        #   foretell   ← `foretell` keyword + grant marker + Foretold-predicate payoff
        #                (Niko) + "to foretell" enabler marker (Karfell); left
        #                _IR_FLOOR_LANES.
        #   scavenge_fuel ← `scavenge` keyword + the "has scavenge" graveyard-grant
        #                face marker (Varolz, Young Deathclaws, Cave of Skulls).
        #   scry_surveil ← scried/surveiled triggers + event='other' payoff + the
        #                "if you would scry a number of cards" replacement face marker
        #                (Kenessos, Eligeth); left _IR_FLOOR_LANES.
        "boast_matters",
        "connive_matters",
        "end_the_turn",
        "exhaust_matters",
        "extra_end_step",
        "madness_matters",
        "mutate_matters",
        "phasing_matters",
        "trigger_doubling",
        "experience_matters",
        "explore_matters",
        "foretell_matters",
        "scavenge_fuel",
        "scry_surveil_matters",
        # Group "tail-supplement 2" (ADR-0027 projection deepening) — the next batch
        # of synthesis-tail keys whose residual cards phase DROPS, recovered by NARROW
        # supplement markers so the lane fires from a NON-floor structural IR source.
        # Floor-mirror-dep==0 (none is in _IR_FLOOR_LANES). NO-FLOOD held (only the
        # target keys grew, each by its gap count; no non-target key moved). Each key's
        # oracle-regex producer is deleted; serve specs stay hand-registered. See
        # ADR-0027.
        #   extra_draw_step / extra_upkeep ← phase's extra_draw/extra_upkeep effect
        #                categories + an `_EXTRA_BEGINNING_PHASE_GRANT` face marker
        #                emitting BOTH for "additional beginning phase" (CR 501.1 — a
        #                beginning phase contains untap/upkeep/draw), which phase
        #                mis-routes to extra_combats (Second Sun cycle) or drops
        #                (Cyclonus). extra_draw fired 0 in the IR before this marker.
        #   counter_control ← phase's `counter_spell` effect + a `counter_spell` face
        #                marker for "counter target … spell/ability" phase loses in a
        #                modal body (Fangkeeper, Ertai), an Aura quoted grant (Equinox,
        #                Sunken Field), or a coin_flip carrier (Goblin Artisans).
        #   cant_block_grant ← phase's `cant_block` effect + a `cant_block` face marker
        #                for the modal mode body (Breeches, Retreat to Valakut) and the
        #                granted quoted ability (Hostile Realm, Malicious Intent) phase
        #                drops (CR 509). The structural IR is broader-and-correct recall
        #                (176 vs the regex's 65 — "creatures can't block" etc.), not
        #                over-fire.
        #   land_exchange ← phase's `gain_control` over a Land subject + a raw fallback
        #                for the subject=None "exchange control of … land" shape
        #                (Political Trickery, Vedalken Plotter, Gauntlets). The IR
        #                correctly drops Sharkey (copies/taxes land abilities, never
        #                exchanges control — the regex's lone false positive).
        "extra_draw_step",
        "extra_upkeep",
        "counter_control",
        "cant_block_grant",
        "land_exchange",
        # Group "tail-supplement 3" (ADR-0027 projection deepening) — five more
        # synthesis-tail keys. Three (myriad_grant, convoke_matters, tapped_matters)
        # were REMOVED from _IR_FLOOR_LANES and now fire from the STRUCTURAL IR alone;
        # floor-mirror-dependency == 0 for each (the floor-dependent gap cards now bind
        # structurally). The other two (typed_anthem_multi, life_total_set) were never
        # floored. NO-FLOOD held (only the target keys grew; no non-target key moved —
        # the Masako tapped-grant marker uses category="tap" so it never trips the
        # creatures_matter team-anthem read). Each key's oracle-regex producer is
        # deleted; serve specs stay hand-registered. See ADR-0027.
        #   myriad_grant ← `myriad` keyword (makers) + grant_keyword counter_kind=
        #                'myriad' (granters) + a copy-exception conferred marker
        #                (Muddle). The "\bmyriad\b" floor over-fired on the "The Myriad
        #                Pools" card NAME — the IR correctly drops it.
        #   convoke_matters ← `convoke` keyword (makers) + cast_with_keyword counter_
        #                kind='convoke' granters + grant_spell_ability/cast-trigger
        #                convoke-raw payoff markers.
        #   tapped_matters ← a Tapped(controller='you') Filter predicate read in the
        #                effect subject / amount.subject COUNT / condition.subject
        #                threshold slots, plus a `_TAPPED_GRANT` marker (Masako's
        #                dropped subject + Harvest Season's dropped count predicate).
        #   typed_anthem_multi ← a pump over a creature Filter naming 2+ subtypes (AnyOf
        #                node OR flat subtypes tuple) + a "that's a X … or a Y" raw
        #                fallback. The pump-only gate drops Paladin Danse (a keyword
        #                grant, not a +X/+X anthem), the regex's over-fire.
        #   life_total_set ← phase's set_life effect + the exchange/redistribute
        #                _NAMED_MECHANICS recategorizations + a `_LIFE_TOTAL_SET` marker
        #                for "life total becomes <X>" + "double … life total". The IR
        #                drops Heartless Hidetsugu (a damage effect), the over-fire.
        "myriad_grant",
        "convoke_matters",
        "tapped_matters",
        "typed_anthem_multi",
        "life_total_set",
        # Group "tail-supplement 4" (ADR-0027 projection deepening) — five floored
        # synthesis-tail keys, all REMOVED from _IR_FLOOR_LANES; floor-mirror-dep == 0
        # for each (the floor-dependent gap cards now bind structurally). NO-FLOOD held
        # (only the target keys grew; no non-target key moved). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. See ADR-0027.
        #   energy_matters ← phase's `energy` effect (gainenergy producers) + an
        #                `_ENERGY_REF` ({e}) marker for the sinks / "whenever you get
        #                {E}" payoffs / doublers phase loses. {e} is unambiguous (real
        #                energy cards only).
        #   rad_counter_matters ← phase's `rad_counter` effect / rad place_counter + a
        #                `_RAD_REF` ("rad counter(s)") marker for the clauses phase
        #                mangles (rad kind dropped to '', counter_doubling, dropped).
        #   suspect_matters ← phase's `suspect` effect (leading-verb) + a `_SUSPECT_REF`
        #                marker for the verb mid-clause/granted + the "suspected" state.
        #                The "(?! counter)" drops Investigator's Journal's "suspect
        #                counter" (a same-named counter type, CR 701.60b).
        #   venture_matters ← phase's venture/take-initiative effect + a
        #                completedadungeon/isinitiative condition read + a
        #                trigger_doubling-over-dungeons read + a `_VENTURE_REF`
        #                dropped-clause marker (gated out of a restriction effect so
        #                Keen-Eared Sentry's opponent anti-venture hate stays out).
        #   crimes_matter ← phase's commit_crime trigger event (the trigger form) + a
        #                `crime` condition-form marker ("(if|as long as) you've
        #                committed a crime") for the payoff phase has no kind for.
        "energy_matters",
        "rad_counter_matters",
        "suspect_matters",
        "venture_matters",
        "crimes_matter",
        # group_mana ← phase emits scope='each' for ZERO ramp effects (the recipient
        # field doesn't exist), so the dead each-scope arm is replaced by a
        # non-controller-recipient discriminator (_GROUP_MANA_RAW) on the ramp effect
        # raw — "each/that/the active/chosen player … adds {" — separating symmetric
        # group ramp (Magus of the Vineyard, Yurlok, Valleymaker, Tangleroot) from
        # your-own ramp. NOT in _IR_FLOOR_LANES; its SWEEP row is deleted, serve
        # hand-registered. gap=0, over=0 (all 8 cards bind structurally). See ADR-0027.
        "group_mana",
        # low_power_matters ← a non-dynamic PtComparison:Power:LE/LT predicate on a
        # you-controller Creature Filter (read by _predicate_build_around_lanes). The
        # recursion cards (Alesha, Reveillark, Vesperlark, Shirei — "return a creature
        # with power N or less") carry the predicate natively; phase DROPS it on the
        # buff/etb subject shapes, recovered by a `_LOW_POWER_REF` marker that rebuilds
        # the Power:LE subject (category="tap" so it stays out of the creatures_matter
        # team-anthem read). REMOVED from _IR_FLOOR_LANES; floor-mirror-dep == 0
        # (with_floor 33 == without_floor 33). NO-FLOOD held. See ADR-0027.
        "low_power_matters",
        # power_matters ← the GE/GT twin of low_power_matters. STRUCTURAL: a
        # non-dynamic PtComparison:Power:GE/GT predicate on a you-controller Filter
        # (CR 208), read by _predicate_build_around_lanes off the board_count Effect
        # subject + the amount.subject + the trigger.subject (the v23 projection now
        # fills the operand), plus _condition_power_matters off the Condition.subject.
        # The board_count/amount sites carry the Ferocious "for each / draw a card for
        # each creature you control with power N+" (Become the Avalanche, Crater's
        # Claws); the trigger.subject carries "a creature you control with power N+
        # enters" (Elemental Bond, Kiora, Where Ancients Tread — the regex missed
        # these: it required the literal "enters the battlefield UNDER YOUR CONTROL");
        # the Condition.subject carries the upkeep/etb/attacks gate "if/while you
        # control a creature with power N+" (Colossal Majesty, Heir of the Wilds + the
        # WHILE-phrased Courageous Goblin / Ruby / Picnic Ruiner + the "can't attack
        # unless" Rhonas / Tiger-Dillo the regex's "if you control" anchor dropped).
        # The Condition read is POWER-ONLY (NOT the general
        # _predicate_build_around_lanes, which would drift the colorless / multicolor /
        # legends / low_power siblings off a Condition.subject). MIRROR: the
        # byte-identical _POWER_MATTERS_MIRROR (the EXACT deleted _HAND_FLOOR regex)
        # over the reminder-stripped kept_oracle recovers the under-structured tail
        # phase can't bind — the "total/greatest/combined power of creatures you
        # control" AGGREGATES phase emits as a board_count with an EMPTY-predicate
        # Filter (Ghalta, Rishkar's Expertise, The Great Henge; the Goreclaw-style
        # threshold-dropped cost reducer is the same EMPTY-board_count tail), the
        # "(total|greatest) power AMONG creatures you control" value refs, the "creature
        # spells you cast with power N+" reducer, and the Formidable ability word (CR
        # 207.2c). REMOVED from _IR_FLOOR_LANES; floor-mirror-dep == 0 (arm + mirror
        # read no floor detector).
        # RESIDUAL (commander-legal, floor-disabled, by oracle_id; NEW IR path vs the
        # deleted regex set): both == 102, regex_only == 0 (the mirror recovers every
        # regex firing byte-identically: mirror == regex == 102, 0 miss / 0 over-fire),
        # ir_only == 34 (ALL genuine power-threshold build-arounds the narrow regex
        # missed per "no dismissal without the hook" — "power N+ enters" triggers, "for
        # each power N+" count operands, "power N+ gain", WHILE-phrased + "can't attack
        # unless" Ferocious gates). HYBRID power_matters == 136 (102 + 34). SCOPE
        # PARITY: the deleted producer, the structural arm, and the mirror all fire
        # scope 'you'. VOLTRON: the deleted producer fired HIGH scope 'you' and fed
        # has_other_plan (a power/Ferocious engine is no vanilla beater; not
        # _GENERIC/_VOLTRON_COMPAT); the migrated IR is BROADER (+34), so
        # _VOLTRON_SILENCING_PLAN_KEYS would over-silence — instead the byte-identical
        # _POWER_MATTERS_PLAN_MIRROR re-supplies has_other_plan over the kept oracle,
        # reproducing the exact pre-migration silence set (voltron delta 0). CR 208.1 /
        # 207.2c. See ADR-0027.
        "power_matters",
        # life_payment_insurance ← a repeatable "Pay N life:" ACTIVATION COST
        # ("paylife" in Ability.cost — Selenia, Beledros, the fetchlands; genuine recall
        # the narrow "pay N life:" regex missed) + a `life_payment` marker for the
        # misparsed cost (Arco-Flagellant, Hibernation Sliver) and the conferred quoted
        # "…Pay 1 life: Draw" ability phase drops (Underworld Connections, the volvers).
        # NOT in _IR_FLOOR_LANES; gap=0, over=36 (all genuine paylife-cost recall).
        # NO-FLOOD held (only this key grew, +7). See ADR-0027.
        "life_payment_insurance",
        # sacrifice_matters ← a you-sacrifice EFFECT (scope not opp/each OR a "you"
        # subject controller; a non-land subject; not a forced-opponent edict raw),
        # a "sacrificed" trigger payoff, the Casualty keyword, a subject-less / modal
        # raw fallback, and the project markers (additional-cost incl. Choice/Kicker,
        # granted/quoted outlet, casualty grant, free-spell pitch, keyworded-cost sac,
        # pay-or-die, discard+sac, bullet, cumulative-upkeep). NOT in _IR_FLOOR_LANES;
        # floor-mirror-dep == 0 (floor-ON 1279 == floor-OFF 1279). The deleted broad
        # regex over-fired on land-sac, edicts, "controller may sacrifice",
        # Ward—Sacrifice, and reanimation engines with NO sacrifice; the floor-disabled
        # residual re-adjudicates to all over-fire bar one card (Phyrexian Soulgorger,
        # a cumulative-upkeep cost phase parses as a SelfRef "sacrifice it"). NO-FLOOD
        # held (only sacrifice_matters / edict_matters grew; edict_matters +107 is the
        # recovered-from-mis-scope recall, plus 3 typed-sac-subject recall gains on
        # food/legends/type_matters — all correct). See ADR-0027.
        "sacrifice_matters",
        # lifeloss_matters ← a structured `lose_life` Effect (scope you→you else
        # opponents — the drain / self-loss split), a `life_payment` marker + a paylife
        # ACTIVATION COST buying a non-ramp engine (the self life-as-resource half), a
        # `life_lost` trigger payoff, and the project _lifeloss_markers (pay-life
        # additional cost / pitch / keyworded-cost / cumulative-upkeep / tax / Defiler
        # / granted / modal / dice / choose self-loss + the modal / granted /
        # lost-life-this-turn / dice drain). extort / afflict / spectacle are removed
        # from the regex keyword path (the IR covers them structurally). NOT in
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON 1262 == floor-OFF 1262). The
        # deleted broad regex over-fired on pay-life MANA sources (painlands etc.),
        # Ward—Pay life (the opponent pays), and lifeGAIN-context. The floor-disabled
        # residual re-adjudicates to ~all over-fire bar ~3 deep edge cards (a
        # value-paylife with no "if you do" anchor, a replacement-effect life loss).
        # NO-FLOOD held (only lifeloss_matters grew). See ADR-0027.
        "lifeloss_matters",
        # removal_matters ← phase's `destroy` / `damage` effect with a SINGLE-TARGET
        # permanent SUBJECT (card_types ∩ permanent types OR a permanent subtype, CR
        # 115.1), the quoted-grant-ability recursion (an Aura/Equipment granting "{T}:
        # Destroy/deal damage to target …" — Manriki-Gusari, Lavamancer's Skill), the
        # subtype-only destroy ("destroy target Wall"), the modal destroy/damage bullet
        # (subject recovered via the modal-split recursion), and the
        # removal-target-subject recovery (Combo Attack, Broken Visage). The MASS form
        # ("destroy/deal damage to EACH/ALL …" — DamageAll/DestroyAll, counter_kind ==
        # "all") is a BOARD WIPE (CR 115.10), EXCLUDED here and served by the
        # mass_removal lane; land destruction routes to land_destruction. NOT in
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON 2533 == floor-OFF 2533, the
        # IR removal arm reads no floor detector). The deleted broad regex (the
        # _HAND_FLOOR row + the SWEEP_DETECTORS row) over-fired by folding board wipes
        # ("destroy all/each", "damage divided") and land destruction into removal —
        # the A-B (regex-only) residual re-adjudicates to ~259/275 over-fire (mass /
        # land / divided), the ~16 remaining genuine single-target gaps being niche
        # sub-shapes (coin-flip-wrapped destroy, clone-exception grant, conditional
        # edicts). NO-FLOOD held: the migration DROPS the 470 board-wipe/land over-fires
        # and ADDS ~218 genuine single-target recall the narrow regex missed ("destroy
        # X/two/any-number-of target", fight-style "deals damage equal to its power to
        # target creature", granted Aura/Equipment removal). See ADR-0027.
        "removal_matters",
        # Group "sweep" (ADR-0027 small-residual close) — five low-residual keys closed
        # by the sweep markers (prior commit). Four left _IR_FLOOR_LANES and
        # now fire from the STRUCTURAL IR alone; floor-mirror-dep == 0 for each
        # (extract_signals_ir reproduces production with the floor lanes disabled).
        # NO-FLOOD held (only the target keys grew; no non-target key moved). Each key's
        # oracle-regex producer is deleted; serve specs stay hand-registered. ADR-0027.
        #   oil_counter_matters ← phase's place_counter(counter_kind='oil') placer +
        #                an `_OIL_REF` ("oil counter(s)") payoff marker (Urabrask's
        #                Anointer, Kuldotha Cackler — the count-operand/condition phase
        #                drops). The 'oil' kind never leaks into counters_matter (p1p1).
        #   mass_death_payoff ← a `_MASS_DEATH_REF` ("creatures that died this turn")
        #                count-operand marker (Khabál Ghoul, Gadrak, Spymaster's Vault).
        #   starting_life_matters ← a `_STARTING_LIFE_REF` ("starting life total")
        #                compare marker. The broad regex's "life total is greater/less"
        #                arm over-fired on unrelated thresholds (Elderscale Wurm's
        #                "less than 7", Sigarda's Splendor's "last noted life total"),
        #                which the tight IR marker correctly drops (CR 103.4).
        #   cycling_matters ← phase's `cycled` trigger + a `cycling` marker (the
        #                _narrow_trigger_other_refs arm for the "cycle or discard"
        #                payoff trigger phase flattens to event='other', plus the
        #                _dropped_static_markers arm for the cards phase truncates the
        #                trigger phrase off entirely — Pitiless Vizier, Zenith Seeker).
        #   dice_matters ← phase's native roll_die effect + a `roll_die` marker (the
        #                trigger-other "whenever you roll" payoff + the dropped-static
        #                "Roll two d6 and choose" SPELL / "Roll a d8:" COST / "reroll").
        "oil_counter_matters",
        "mass_death_payoff",
        "starting_life_matters",
        "cycling_matters",
        "dice_matters",
        # Group "sweep 2" (ADR-0027 small-residual close) — five more low-residual keys
        # closed by the conferred/dropped-static markers (prior commit). Four left
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 for cascade/changeling/regenerate
        # (floor-ON == floor-OFF), and undying_persist's +1 floor-dependency is the
        # "Undying Flames" NAME over-fire the structural IR correctly drops (parallel to
        # the madness "Crown of Madness" / devour "Devour Intellect" name/word over-fire
        # precedents). creature_cast_trigger was never floored. NO-FLOOD held (only the
        # target keys grew; no non-target key moved). The migrations are broader-and-
        # correct RECALL, not over-fire: creature_cast_trigger +28 (qualified-subject
        # triggers — "green/Vampire/Eldrazi creature spell", "nonlegendary creature
        # spell with flying" — the bare "casts a creature spell" regex missed). Each
        # key's oracle-regex producer is deleted; serve specs stay hand-spec'd.
        #   cascade_matters ← Scryfall `cascade` keyword + a `_CASCADE_GRANT` marker for
        #                the keyword-less granters/references (Maelstrom Nexus, Yidris,
        #                Averna, The First Doctor's "spell with cascade" payoff).
        #   changeling_matters ← Scryfall `changeling` keyword + a `_CHANGELING_REF`
        #                ("changeling" / "is every creature type") marker (Maskwood
        #                Nexus, Mistform Ultimus, Arachnoform, Omo's everything ctr).
        #   regenerate_matters ← phase's `regenerate` effect + a `_REGENERATE_REF`
        #                marker for the granted/quoted/replacement regenerate (Tribal
        #                Golem, Mossbridge Troll, the Holy Nimbus pair).
        #   undying_persist_matters ← Scryfall undying/persist keywords + a
        #                `_UNDYING_PERSIST_GRANT` marker for the keyword-less granters
        #                (Mikaeus, Cauldron of Souls, the Scarecrows). Drops "Undying
        #                Flames" (the name over-fire).
        #   creature_cast_trigger ← a cast_spell trigger with a Creature subject + an
        #                effect-raw / face-oracle "whenever/when [player] casts a …
        #                creature spell" scan (Wildgrowth Archaic's enters-with
        #                replacement, Glimpse of Nature's delayed trigger, Blink's
        #                token, Garruk's emblem). Anchored past mana-restrictions /
        #                different-trigger may-cast actions (Cavern of Souls, Dragon-
        #                Kami's Egg).
        "cascade_matters",
        "changeling_matters",
        "regenerate_matters",
        "undying_persist_matters",
        "creature_cast_trigger",
        # fight_matters ← phase's `fight` effect + a `_FIGHT_REF` dropped-static marker
        # (granted "it fights" / quoted-token / modal "Fight!" / emblem / symmetric
        # "fight each other") + a `_FIGHT_RAW` face-level fallback (the Aftermath DFC
        # phase doesn't project — Prepare // Fight). NOT in _IR_FLOOR_LANES;
        # floor-mirror-dep == 0 (132 == 132). NO-FLOOD held. The migration is broader-
        # and-correct recall (+5: Grothama, Ezuri's Predation, Time to Feed, Kraul
        # Harpooner, Skophos Maze-Warden — granted/token fights the narrow regex
        # missed). Its SWEEP_DETECTORS row is deleted; serve hand-spec'd. CR 701.12.
        "fight_matters",
        # food_matters / treasure_matters ← the generalized blood_matters token-subtype
        # widening: a Food/Treasure-subtype make_token MAKER (the die-roll/vote/choice
        # branch + the Aftermath-DFC face fallback), a "Sacrifice a Food/Treasure" SAC
        # PAYOFF, and a `token_subtype_ref` "Foods/Treasures you control" / "was a
        # Treasure" / "is a Food" CARES-ABOUT marker (project._narrow_token_subtype_
        # makers + _dropped_static_markers, read via _TOKEN_SUBTYPE_KEYS). REMOVED from
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON == floor-OFF: 157/324).
        # NO-FLOOD held (token_maker/tokens_matter/creatures_matter unchanged — the
        # markers route ONLY through _TOKEN_SUBTYPE_KEYS to the 4 subtype lanes). The
        # migration is broader-and-correct recall (+4 food sac-payoffs / +27 treasure
        # make_token-SUBJECT makers the narrow "create … <Subtype> token" regex missed —
        # Old Gnawbone, Prismari Command, Wanted Scoundrels). CR 111.10 / 701.16.
        "food_matters",
        "treasure_matters",
        # saga_matters ← a `_SAGA_REF` ("lore counter" / "Saga you control") dropped-
        # static face marker (lore-counter manipulation — Keldon Warcaller, Satsuki,
        # Garnet; chapter-scaling payoff Sagas; the Saga-payoff commander Tom Bombadil;
        # non-Saga lore engines — Myth Realized, Mind Unbound). REMOVED from
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (17 == 17). NO-FLOOD held: mapping
        # counter_kind='lore' → saga_matters would have flooded the lane with all 186
        # Sagas (phase synthesizes a lore placement for every Saga's chapter
        # advancement); the reminder-stripped face anchor fires ONLY on the build-around
        # tell (a vanilla Saga's reminder-only lore mention is excluded), exactly
        # mirroring the regex (residual 0, ir_only 0). Its SWEEP_DETECTORS row is
        # deleted; serve hand-spec'd. CR 714.
        "saga_matters",
        # Group "cares-about kept-detector" (ADR-0027) — 7 cares-about lanes phase
        # v0.1.19 doesn't structure as a card-property payoff (rules-lawyer-verified: no
        # reference shape in the parse). MOVED from _IR_FLOOR_LANES (a reused production
        # floor Detector) to _IR_KEPT_DETECTORS (a dedicated IR-path word mirror), which
        # zeroes floor-mirror-dep by construction — the lane no longer toggles with
        # _IR_FLOOR_LANES. Each retains its EXISTING structural bind too (add() dedups):
        # devotion/party ← the amount.op=="devotion"/"party" count operand (the scaling
        # payoffs); multicolor/colorless ← the ColorCount subject-Filter predicates (the
        # "<multicolored|colorless> permanent/card you control" build-arounds — the kept
        # mirror is broader-and-correct: it adds Ancient Stirrings / Obscura Charm /
        # Dragon Arch "card" refs the narrow regex missed); historic ← the "Historic"
        # subject-Filter predicate. initiative (CR 720) / attractions (CR 717) have no
        # structural form — the word IS the build-around tell. Floor-mirror-dep == 0 for
        # all 7; regex-path parity exact (regex_only_resid == 0); NO-FLOOD (0 keys'
        # firing counts changed by the floor->kept move). Their _HAND_FLOOR rows
        # (devotion/historic/party/initiative/multicolor/colorless) + the attractions
        # SWEEP_DETECTORS row are deleted; serve specs survive. CR 700.5/700.6/702.114.
        "devotion_matters",
        "party_matters",
        "historic_matters",
        "multicolor_matters",
        "colorless_matters",
        "initiative_matters",
        "attractions_matter",
        # Group "SWEEP batch" (ADR-0027) — 11 keys whose forms phase scatters across
        # categories it doesn't unify (a count operand it drops, a trigger flattened to
        # event='other', a grant whose subject it folds, a zone-exile with subject=None,
        # a recipient it drops). Each fires from its EXISTING structural bind PLUS a
        # dedicated _IR_KEPT_DETECTORS word mirror (or a raw discriminator), reproducing
        # the deleted regex exactly (regex_only_resid == 0). rules-lawyer-verified.
        #   donate_matters ← a gain_control effect whose raw names an another-player
        #                RECIPIENT (_DONATE_RAW; phase drops the recipient to
        #                scope='any'). Replaces the dead scope=='opp' arm. CR 701.12.
        #   minus_counters_matter ← place_counter(m1m1) maker + a "-1/-1 counter" kept
        #                mirror for the remove/cost/ward/"with a counter" payoffs.
        #   team_evasion_grant ← the generic creatures-you-control grant_keyword +
        #                a kept mirror for subtype/color-scoped grants (Slivers have
        #                flying). +15 pump+grant recall the narrow regex missed.
        #   hand_disruption ← the opp-reveal trigger + a kept mirror for "look at
        #                hand" / "play with hands revealed" / modal reveal-discard.
        #                +6 recall.
        #   commander_matters ← the IsCommander predicate + a kept mirror for Background
        #                grants / "commander damage". Moved floor->kept. +13 recall.
        #   domain_matters ← amount.op=='domain' + a "\bdomain\b|basic land types" kept
        #                mirror. Moved floor->kept (floor-mirror-dep -> 0). CR 700.3.
        #   opponent_exile_matters ← GRAVEYARD HATE alone (CR 406) from a kept mirror;
        #                the old permanent-exile arm mis-fired on Path-to-Exile
        #                removal and is removed (so the 19 ir_only removal cards
        #                correctly leave the lane). phase scatters the forms across
        #                exile / cheat_play / pump.
        #   exalted_lone_attacker ← the `exalted` keyword + an "attacks alone|exalted"
        #                kept mirror. Moved floor->kept. CR 702.83.
        #   speed_matters ← phase's `speed` doer + a "start your engines|max speed|your
        #                speed" kept mirror. Moved floor->kept. CR 702.178/702.179.
        #   tap_untap_matters ← the `taps` (tap-for-mana) trigger + a "becomes tapped/
        #                untapped" kept mirror (Inspired flattens to event='other').
        #                +65 tap-for-mana recall the regex missed.
        #   reanimator ← a creature whose `reanimate` returns CREATURE cards from a
        #                graveyard (incl. a raw fallback for the subject phase drops —
        #                Isareth, Beacon of Unrest). The regex conflated this with
        #                "cast a spell FROM a graveyard" (flashback/escape — CR 702.34
        #                casting ≠ reanimation), which the structural IR correctly
        #                drops; the 38 regex-only residual re-adjudicates to all
        #                over-fire (flashback/escape/unearth/self-recursion). +25
        #                genuine creature-reanimation recall (the raw fallback). CR 603.
        # Floor-mirror-dep == 0 for all 11 (regex-path parity exact). NO-FLOOD: an
        # in-process before/after over the commander-legal corpus changed ZERO
        # non-target key firing counts (the removed opponent_exile permanent-exile arm
        # only dropped
        # that lane's mis-fires; exile_removal — the sibling on the same arm — is
        # unchanged).
        # color_hoser (ADR-0027 MIGRATED) ← the destroy/exile/counter_spell + HasColor-
        # subject structural arm (which carries the +1 ir_only recall, Reign of Chaos —
        # a non-contiguous "destroy … target white creature" the regex's `destroy …
        # {color} creature` could never match) PLUS the byte-identical _COLOR_HOSER_RE
        # kept mirror over kept_oracle. The earlier batch SKIPPED it for a PURE-
        # structural migration (the 18 gaps — color-less counterspell subjects, NotColor
        # pump-debuffs typed cat='pump', destroy-target-color with phase-dropped
        # HasColor, the bounce/restriction forms — would need a _card_ir widening). The
        # SIGNALS-ONLY kept-mirror (the established predicate-DROPPED tail pattern)
        # recovers all 66 regex hits with regex_only==0: byte-mirror parity over the
        # commander-legal corpus (both=66, ir_only=1 genuine, regex_only=0). The regex
        # is BROADER than the byte-mirror (+1 ir_only), so has_other_plan is re-supplied
        # by a byte-identical mirror (the EXACT _COLOR_HOSER_RE over the reminder-
        # stripped `text`), NOT _VOLTRON_SILENCING_PLAN_KEYS (which would over-silence
        # Reign of Chaos). CR 105.2 (colors) / 613.1e (layer 5). See ADR-0027.
        "color_hoser",
        "donate_matters",
        "minus_counters_matter",
        "team_evasion_grant",
        "hand_disruption",
        "commander_matters",
        "domain_matters",
        "opponent_exile_matters",
        "exalted_lone_attacker",
        "speed_matters",
        "tap_untap_matters",
        "reanimator",
        # Group "SWEEP-floor->kept" (ADR-0027 sweep batch) — cares-about lanes phase
        # v0.1.19 leaves TEXTUAL, each with a load-bearing floor mirror so it MOVES
        # from _IR_FLOOR_LANES to a dedicated _IR_KEPT_DETECTORS word mirror while
        # KEEPING its existing structural / keyword IR bind (add() dedups). The move
        # zeroes floor-mirror-dep by construction (floor_ON == floor_OFF for all 4).
        # legends_matter ← HasSupertype:Legendary predicate; lands_matter ←
        # amount.subject=Land operand; poison_matters ← infect/toxic/poisonous
        # keywords; suspend_matters ← `suspend` keyword. Each mirror reproduces the
        # deleted regex exactly (regex_only_resid == 0). NO-FLOOD: floor->kept changed
        # one voltron tell (-1: The Balrog correctly silenced via legends IR recall).
        # See ADR-0027.
        "legends_matter",
        "lands_matter",
        "poison_matters",
        "suspend_matters",
        # stickers_matter (ADR-0027 floor->kept, same shape as the SWEEP batch above) —
        # the Unfinity sticker-sheet archetype: the {TK} (ticket) ability-sticker costs
        # on "Stickers"-type creatures plus the "put a sticker"/"name|art|ability|power
        # and toughness sticker" effects (and Wicker Picker's "sticker kicker").
        # Stickers (CR 123, ticket counters CR 122) are a niche paper-only mechanic
        # phase v0.1.19 doesn't structure — line 191 of _signals_ir notes ticket/unknown
        # player counters stay lane-less, and there is NO structural stickers arm (with
        # _IR_FLOOR_LANES disabled the IR fires it 0 times). So the lane MOVES from
        # _IR_FLOOR_LANES to a dedicated _IR_KEPT_DETECTORS word mirror reusing the
        # deleted SWEEP regex (STICKERS_MATTER_REGEX = `\{tk\}|\bstickers?\b`, scope
        # 'you'). The regex has NO `[^.]*` cross-clause span, so the flat .search over
        # the reminder-stripped kept_oracle == the deleted producer's per-clause firing
        # set byte-identically: floor-disabled IR-vs-deleted-regex residual over the
        # commander-legal corpus, by oracle_id, is both==92 / ir_only==0 / regex_only==0
        # (all 92 genuine sticker cards — BREADTH, not over-fire). The deleted SWEEP
        # producer fed has_other_plan (HIGH conf, forced scope 'you', not in
        # _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), so stickers_matter is added to
        # _VOLTRON_SILENCING_PLAN_KEYS — the byte-identical IR re-supply re-silences the
        # spurious commander-damage voltron tell on a sticker-payoff body (no sticker
        # card has empty oracle_text + card_faces, so the re-supply set == the regex
        # producer set exactly). NO-FLOOD: only stickers_matter's count moves, voltron
        # 3010->3010. CR 123 / 122.1. See ADR-0027.
        "stickers_matter",
        # Group "damage cluster" (ADR-0027 projection deepening) — the damage-doubling
        # half of the direct_damage <-> damage_doubling decoupling. damage_doubling
        # fires from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-
        # dep == 0): phase's `damage_doubling` DamageDone-replacement category, now
        # deepened to cover Triple (Fiery Emancipation, City on Fire) and the nested
        # AddTargetReplacement / CreateDamageReplacement amplifiers (Goblin Goliath,
        # Isengard Unleashed, Desperate Gambit), plus a `damage_doubling` face marker
        # for the modification phase dropped entirely (Neriv's entered-this-turn
        # condition, Jeska's Unimplemented loyalty mode, Borborygmos/Surtland's "deals
        # twice that much" riders). The IR is strictly broader-and-correct ("double all
        # damage … would deal" — Collective Inferno, Raphael, Wolverine — regex
        # missed) and EXCLUDES the regex's "prevent half that damage" HALVING over-fire
        # (Dark Sphere, CR 615 prevention — the opposite of a doubler, the lone regex-
        # only residual the structural IR correctly drops). The projection fix ALSO
        # nets out the coupling's other direction: the doublers (Furnace of Rath,
        # Gratuitous Violence, Neriv, Goblin Goliath) no longer carry the spurious
        # direct_damage the deleted synthesized `damage` effect over-fired in the IR.
        # direct_damage ITSELF stays on regex — its 52 burn gaps (Keranos, Koth,
        # Tibalt — damage buried in a reveal/loyalty/Unimplemented body) need a deeper
        # damage-recovery pass, not a clean over-fire migration. Its SWEEP_DETECTORS
        # row is deleted; the serve spec is hand-registered. See ADR-0027.
        "damage_doubling",
        # Group "combat-forcing" (ADR-0027 projection deepening) — the goad half of
        # the goad_matters <-> forced_attack disentanglement (CR 701.38 goad redirect-
        # payoff vs CR 508.1g self-force). goad_matters fires from the STRUCTURAL IR
        # alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0): the Scryfall `goad`
        # keyword + phase's `goad_all` effect + a `_GOAD_REWARD_REF` face marker (the
        # redirect-reward conditions phase flattens to raw — "attacks one of your
        # opponents", "a player other than you", "whenever a player attacks", Kazuul's
        # defending-player payoff) + the goad-style single-target political force
        # (`_GOAD_STYLE_FORCE` lifting phase's force_attack effect on "target creature
        # … attacks … if able" — Boiling Blood, Incite, Basandra, Alluring Siren). The
        # disentanglement is structural: the self/team "attacks each combat if able"
        # static stays on forced_attack (its own lane); the single-target / redirect-
        # reward forms open goad. regex-only residual 45 -> 2 (Boros Battleshaper's
        # attack-OR-block manipulation → cant_block, Tower Above's "blocks if able" →
        # force_block/lure — both correct IR exclusions). forced_attack ITSELF now
        # migrates too (the sibling below); the coupling's over-fire direction (regex
        # goad over-firing on self-force / blocks) is resolved structurally. The two
        # goad _DETECTORS / _HAND_FLOOR producers are deleted; the serve spec is
        # registered. See ADR-0027.
        "goad_matters",
        # Group "combat-forcing" (ADR-0027) — forced_attack, the sibling of
        # goad_matters above (CR 508.1d "attacks if able" REQUIREMENT vs CR 701.15
        # goad's redirect-payoff). UNION migration shape:
        #   (a) STRUCTURAL arm — phase's `force_attack` Effect category, already wired
        #       in extract_signals_ir (scope "any"). This covers EVERY real 508.1d
        #       force-attack compulsion — the self/team "attacks each combat if able"
        #       static (Public Enemy, Seeker of Slaanesh), the single-target political
        #       force (Boiling Blood, Alluring Siren, Basandra — which ALSO co-open
        #       goad via _GOAD_STYLE_FORCE), and the "creatures that player controls
        #       attack X if able" table-force (Gideon Jura, Rowan Kenrith, War's Toll).
        #       +41 ir_only RECALL the narrow deleted SWEEP regex missed (it only knew
        #       "each/every combat if able" / "that player this combat if able"), all
        #       100% genuine forced-attack effects (verified vs Scryfall). The deleted
        #       SWEEP regex's REAL (reminder-stripped) firings are ALL in this arm —
        #       SWEEP regex_only == 0 over the reminder-stripped corpus.
        #   (b) BYTE-IDENTICAL KEPT MIRROR — the deleted _DETECTORS "didn't attack this
        #       turn|that attacked this turn" PUNISHER-incentive arm (scope "you"),
        #       pinned as _FORCED_ATTACK_DET_MIRROR in _signals_ir._IR_KEPT_DETECTORS.
        #       phase carries NO structural form for the "didn't attack" penalty
        #       subject (Erg Raiders, Kratos, Angel's Trumpet, Season of the Witch) nor
        #       the "untap creatures that attacked" extra-combat rider; the mirror
        #       reproduces all 23 DET regex_only cards byte-identically. The mirror has
        #       no `[^.]*` cross-clause arm and the patterns never appear inside
        #       reminder text (DET full-text == reminder-stripped == 26), so flat over
        #       kept_oracle == per-clause. A few extra-combat-untap over-fires it
        #       reproduces (Relentless Assault, World at War) are KEPT for byte-parity
        #       (the regex matched them pre-migration; not a behavior change). CR
        #       508.1d / 701.15.
        # The 55 goad-reminder SWEEP over-fires the FULL-text SWEEP regex would catch
        # are NOT a residual: the production regex path strips reminder text first, so
        # those goad cards never fired forced_attack pre-migration (they fire
        # goad_matters, the correct lane) — base hybrid forced_attack == 128. LOSE == 0:
        # gained 41 (genuine recall), lost 0; post-mig commander-legal == 169. Voltron:
        # the deleted DET + SWEEP producers fed has_other_plan (HIGH, scope you/any, not
        # generic/voltron-compat). The IR re-supply is BROADER (169 vs 128), so a
        # _VOLTRON_SILENCING_PLAN_KEYS entry would OVER-silence the +41 recall bodies;
        # instead a byte-identical _FORCED_ATTACK_PLAN_MIRROR (the EXACT DET-or-SWEEP
        # over reminder-stripped oracle) is OR'd into has_other_plan in _signals_regex —
        # re-silencing ONLY the old regex's 128-card set (94 load-bearing, all
        # re-silenced; 0 leak). The _DETECTORS / SWEEP producers are deleted; the serve
        # spec is hand-registered with the pinned SWEEP regex. CR 508.1d / 701.15 /
        # 903.10a.
        "forced_attack",
        # Group "spell-copy" (ADR-0027 projection deepening) — spell_copy_matters fires
        # from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0):
        # phase's `spell_copy` effect (CopySpell + CastCopyOfCard) + the storm/replicate
        # /conspire/casualty Scryfall keywords (the HAVERS, _IR_KEYWORD_MAP) + a
        # `_COPY_SPELL_REF` face marker (project._dropped_static_markers) for the
        # granted/quoted/conditional copy phase folds into a modal / coin-flip / storm-
        # reminder carrier (God-Eternal Kefnet, Twinferno, Krark, Pyromancer's Goggles)
        # AND the keyword-less GRANTERS ("…spell you cast has replicate/casualty/storm/
        # demonstrate" — Anhelo, Djinn Illuminatus, Wort, Threefold Signal, The Twelfth
        # Doctor). The structural IR EXCLUDES the deleted regex's `\bstorm\b` card-NAME
        # over-fire — 20 of the 21 regex-only residual are cards merely NAMED "… Storm"
        # (Comet Storm, Arrow Storm, Tropical Storm — burn/effects, not the keyword),
        # which the IR correctly drops; the 21st (Refuse // Cooperate) is an irreducible
        # phase gap (phase has no record for the Aftermath back face that carries "Copy
        # target instant or sorcery spell"). The IR_ONLY (121) are 100% genuine copy
        # cards (all mention copy / a copy-keyword) the narrow regex missed. Both regex
        # producers (the _HAND_FLOOR + the SWEEP row) are deleted; the serve spec is
        # hand-registered. See ADR-0027.
        "spell_copy_matters",
        # Group "counters" (ADR-0027 counters_matter pass 2) — counters_matter fires
        # from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0,
        # floor-ON == floor-OFF). It fires on ANY +1/+1 counter PLACEMENT regardless
        # of recipient (self / on-others / on-attacking / distribute-among — all are
        # sources, CR 122.1 / 122.6) and on a "has/with a +1/+1 counter" PAYOFF
        # reference. Sources: phase's place_counter(p1p1) + counter_move(p1p1) +
        # proliferate + the counter_added trigger + the count-form payoff (the Counters
        # predicate on amount.subject / e.subject) + the amass/fabricate/devour modal
        # fan-out + the counters_have_ref marker (project._narrow_counter_refs /
        # _counter_face_marker — the placement/payoff phase folds into a coin_flip /
        # roll_die / vote / pay-cost / distribute / trimmed-grant / reanimate-rider
        # carrier or drops entirely) + the +1/+1 keyword block (mentor/training/
        # modular/bolster/evolve/outlast/renown/adapt/graft/riot/bloodthirst/
        # fabricate/sunburst/tribute/unleash/ravenous/reinforce/scavenge/undying/
        # dethrone/devour — every one verified to project a place_counter / carry its
        # keyword, 0-miss). LOSE == 0 in production config (floor lanes ON): the IR
        # fires counters_matter on ALL 1895 cards the regex did, plus 1243 the narrow
        # regex missed (genuine recall; IR 3138 vs regex 1895). All regex producers
        # (the count/board-wide _DETECTORS row, the two _HAND_FLOOR rows — "power
        # greater than its base power" twin + the any-counter HAVE form — the +1/+1
        # keyword block in _DIRECT_KEYWORD_SIGNALS, and the two self-/have-counter
        # add() calls) are deleted; the serve spec stays hand-registered. The
        # counter_place_trigger / counter_distribute / self_counter_grow SWEEP rows
        # (their own widen lanes) are independent and stay regex. See ADR-0027.
        "counters_matter",
        # Group "tranche2-B" (ADR-0027) — 5 keys phase v0.1.19 NOW structures, each
        # fires from the STRUCTURAL IR alone (NONE in _IR_FLOOR_LANES; floor-mirror-dep
        # == 0 by construction — no key reads a floor detector). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. NO-FLOOD held (only the
        # target keys' firing counts changed; no non-target key moved). See ADR-0027.
        #   mass_bounce ← a `bounce` Effect with counter_kind=='all' (the mass
        #                discriminator, same convention as the mass-untap arm) on a
        #                generic Creature/Permanent subject (_is_mass_bounce_subject),
        #                excluding graveyard recursion (InZone/Owned predicate or a
        #                graveyard/library zone — Garna, Wrenn, Empty the Catacombs).
        #                Single-target bounce (Cyclonic Rift base, counter_kind=='')
        #                stays out. Kept residual: Cyclonic Rift's overload 'each' mode
        #                (a phase modal-alt-cost parse drop) + artifact/enchantment-only
        #                sweeps (Rebuild, Reduce to Dreams — out of the Creature/
        #                Permanent subject scope). CR 115.10.
        #   permanent_etb ← an `etb` Trigger whose subject Filter carries 'Permanent'
        #                and controller=='you' (Amareth). BROADER-and-correct vs the
        #                narrow word-order regex (+12 generic-permanent-ETB engines:
        #                Cloudstone Curio, Kodama, Yoshimaru). creature_etb (Creature
        #                subject) and an opp-scoped punisher stay out. CR 603.
        #   team_buff ← the `grant_keyword` Effect (one per keyword, keyword in
        #                counter_kind) on a GENERIC "creatures you control" subject
        #                (_is_team_buff_grant tolerates NonToken/Another/Other;
        #                _TEAM_BUFF_GRANT_KW is the evergreen team-keyword set).
        #                Co-fires with team_evasion_grant / protection_grant (subsets;
        #                seen-set dedups). The structural IR drops the regex's tribal /
        #                color / attacking / single-target over-fires (it matched the
        #                "creatures you control have <kw>" mass_grant roll-up text even
        #                when the real grant was narrowed) — 0 genuine generic anthems
        #                lost. The summary ck=='mass_grant' roll-up Effect is ignored.
        #   destroy_legendary ← a `destroy` Effect whose subject Filter carries the
        #                exact HasSupertype:Legendary predicate (Bounty Agent, Tsabo
        #                Tavoc; the mass "destroy each legendary" form — Invasion of
        #                Fiora — rides counter_kind=='all' with the same predicate). The
        #                exact string is the discriminator: a generic "destroy target
        #                creature" lacks it; NotSupertype:Legendary ("nonlegendary" —
        #                Cast Down, One Ring) is the OPPOSITE and stays out. ~0
        #                residual. CR 205.4a. is_widen_of removal_matters preserved.
        #   power_double ← a `pump`/`pump_target` Effect whose raw carries the
        #                "double … power" / "power … doubled" word-mirror
        #                (_POWER_DOUBLE_RAW). phase sets no multiply quantity for P/T
        #                doubling (amount=None), so the category + raw is the
        #                discriminator (NOT the over-firing Scryfall `Double` keyword,
        #                which mostly doubles damage/counters/tokens). Single-target
        #                doublers (Unleash Fury) land in pump_target; mass doublers
        #                (Unnatural Growth) in pump. Kept residual: a Saga chapter
        #                (Roar of Endless Song, phase structures as saga steps).
        "mass_bounce",
        "permanent_etb",
        "team_buff",
        "destroy_legendary",
        "power_double",
        # Group "tranche2-A structural sweeps" (ADR-0027) — four removal/buff lanes
        # phase v0.1.60 now structures cleanly, each migrated from a STRUCTURAL /
        # cost-bearing IR source (NONE are in _IR_FLOOR_LANES; floor-disabled IR ==
        # floor-on IR for all four). The IR is strictly broader-and-cleaner than the
        # deleted regex — it drops the regex's over-fires and adds the typed/predicate
        # cases the narrow regex missed.
        #  • activated_draw ← Ability(kind=='activated') with 'tap' in cost + a draw
        #    Effect (the {T}: gate the cost field now supplies; the loose 'tap' catches
        #    the {N}{T}: draw rocks the literal `{t}: draw a card` regex missed). The
        #    5 regex-only are GRANTED {T}:Draw abilities phase folds into the granter.
        #  • anthem_static ← Ability(kind=='static') pump over a creature GROUP,
        #    factor>=0 (keeps +0/+N toughness anthems), scope!='opp' (drops the debuff
        #    half of a split anthem). kind=='static' drops the 303 EOT/one-shot pump
        #    over-fires the regex caught (Charge, planeswalker minus abilities); a
        #    ~15-card emblem/phase-parse-gap residual is the accepted tail.
        #  • aoe_ping ← a counter_kind=='all' damage Effect over a Creature subject on
        #    a REPEATABLE-FRAME ability (activated tap/mana cost without sacself, or an
        #    upkeep/end_step/cast_spell trigger). Drops the regex's sacself one-shot
        #    pingers (Bloodfire Colossus) and one-shot ETB sweeps (Chaos Maw).
        #  • mass_removal ← a counter_kind=='all' destroy/exile/damage of a battlefield
        #    permanent type, or a negative all-creatures pump (Languish/Toxic Deluge).
        #    Battlefield-type + graveyard-zone gates exclude land destruction
        #    (Armageddon) and mass reanimation/GY-hate (Living Death, Gerrard).
        "activated_draw",
        "anthem_static",
        "aoe_ping",
        "mass_removal",
        # Group "tranche2-C" (ADR-0027) — five combat/engine lanes, each fires from a
        # STRUCTURAL IR arm (none is in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them).
        # NO-FLOOD held (only the target keys' counts moved). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. See ADR-0027.
        #   exert_matters ← a grant_keyword effect with counter_kind=='vigilance' over
        #                a generic-creature-you-control subject (the team-vigilance
        #                enabler that neutralizes exert's "won't untap" downside —
        #                Heliod, Always Watching, Brave the Sands; _is_generic_creature_
        #                filter is predicate-tolerant so Heliod's `Another` / Always
        #                Watching's `NonToken` board counts, but the subtype-scoped
        #                Golem/Sliver/Warrior grants and Kytheon's single-target are
        #                excluded) + a Johan "attacking doesn't cause … to tap" kept
        #                word mirror. Its _HAND_FLOOR producer is deleted.
        #   self_pump ← an ACTIVATED pump_target / place_counter(p1p1) effect on the
        #                SELF (subject=None) — the firebreathing mana-sink (Shivan
        #                Dragon) and the activated +1/+1-counter body (Walking Ballista,
        #                Crystalline Crawler). The ab.kind=='activated' gate excludes
        #                manlands (animate/ramp) and one-shot spell pumps; subject=None
        #                excludes granters ("target creature gets…"). Its SWEEP row is
        #                deleted; its existing serve spec is repointed via regex=.
        #   tapper_engine ← a `tap` Effect with a target subject Filter (the repeatable
        #                tapper — Icy Manipulator, Opposition, Master Decoy; tap-as-cost
        #                lives in Ability.cost and emits no tap Effect, so subject!=None
        #                never leaks cost taps) + a "doesn't untap" restriction-raw
        #                branch (Frost Titan). Scope 'any' (broad target tap; tap_down
        #                may co-fire, OK). Its SWEEP row is deleted; serve hand-spec'd.
        #   recast_etb ← DETECTOR: the Scryfall `sneak` keyword (_IR_KEYWORD_MAP, the
        #                bounce-replay engine; drops the `\bsneak\b`-regex over-fires).
        #                SERVE: an etb Trigger + a discard/lose_life/sacrifice effect
        #                whose raw names "each opponent" (the aggressive enter-bleed the
        #                recast repeats — Liliana's Specter, Skirmish Rhino). Its
        #                _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   count_anthem ← a team +N/+N pump whose amount SCALES with a board count
        #                (_is_scaling_count) over a generic creature Filter you control
        #                (Hold the Gates, Commander's Insignia, Boon of the Spirit
        #                Realm). The team-subject discriminator separates it from
        #                single-target firebreathing scaling_pump and the symmetric
        #                Coat-of-Arms global; it is the team-subject subset of
        #                scaling_pump (both may open — add() dedups). Its SWEEP row is
        #                deleted; serve hand-spec'd.
        "exert_matters",
        "self_pump",
        "tapper_engine",
        "recast_etb",
        "count_anthem",
        # Group "tranche2 (t2b2-A)" — structural grant / bounce / exile IR arms whose
        # original `needs_projection` mappings were STALE (grant_keyword now carries the
        # granted keyword in counter_kind; Ability.condition carries the gate; the
        # `Owned` subject predicate captures "you own"; bounce is a first-class
        # category). All NON-floor (floor-mirror-dep == 0 — none is in _IR_FLOOR_LANES);
        # the floor-disabled IR-vs-regex residual is empty or 100% over-fire (the IR is
        # broader-and-correct). See ADR-0027.
        #   aura_equip_kw_grant ← grant_keyword of an _AURA_EQUIP_GRANT_KW evergreen kw
        #                over a YOUR Aura/Equipment subgroup subject (Rashel + 2 the
        #                literal regex alternation missed). Its SWEEP row is deleted;
        #                serve repointed via regex=.
        #   counter_grants_kw ← grant_keyword over a YOUR-creature subject carrying the
        #                `Counters` predicate (Bramblewood Paragon, Abzan Falconer,
        #                Tuskguard Captain). Broader than the closed-keyword regex
        #                (which named only haste/flying/trample/menace/vigilance/
        #                lifelink). Its SWEEP row is deleted; serve via regex=.
        #   conditional_self_protection ← a STATIC ability with a condition granting
        #                a _SELF_PROTECTION_GRANT_KW keyword to ITSELF (subject None =
        #                SelfRef) — Dragonlord Ojutai, Zurgo, Kaito. Broader-and-correct
        #                (catches every "during your turn has indestructible" the narrow
        #                regex missed). voltron-relevant (_VOLTRON_COMPAT_KEYS). Its
        #                SWEEP row is deleted; serve repointed via regex=.
        #   control_exchange ← an `exile` Effect whose subject carries the `Owned`
        #                predicate, PAIRED with a to:battlefield return in the same
        #                ability (Meneldor, The Neutrinos, Aminatou). The inverse of the
        #                exile_removal Owned-exclusion. Its SWEEP + _HAND_FLOOR
        #                producers are deleted; serve repointed via regex=.
        #   bounce_tempo ← a `bounce` Effect (first-class category) with no graveyard
        #                zone tag and subject not controller='you' (excludes self-bounce
        #                blink/karoo) — Boomerang, Unsummon, Man-o'-War, Cyclonic Rift.
        #                Broader than the narrow regex (mass + flexible bounce);
        #                breadth, not over-fire. Its SWEEP + _DETECTORS producers are
        #                deleted; serve repointed via regex=.
        "aura_equip_kw_grant",
        "counter_grants_kw",
        "conditional_self_protection",
        "control_exchange",
        "bounce_tempo",
        # Group "tranche2-B (counters / O-Ring)" (ADR-0027) — four lanes, each fires
        # from a STRUCTURAL IR arm (NONE in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them).
        # Floor-disabled IR-vs-regex residual on the commander-legal corpus:
        # counter_manipulation / counter_replace_bonus / exile_until_leaves A-B==0;
        # counter_place_trigger A-B==6, all 100% adjudicated (opp-side scope, a
        # CONFERRED trigger phase can't attribute — Danny Pink, Cursed Wombat — a
        # turn-face-up place_counter EFFECT not a counter_added trigger — Experiment
        # Twelve — and a lore-counter manipulation — Sigurd). Each key's oracle-regex
        # SWEEP_DETECTORS producer is deleted; serve specs stay hand-registered.
        # (damage_to_opp_matters — formerly DEFERRED here — is now migrated via the
        # SIDECAR v13 DamageToPlayer recipient projection; see its block below.)
        #   counter_manipulation ← (counter_move|remove_counter) Effect with
        #                counter_kind in {p1p1,m1m1} (the +1/+1-vs-charge/oil
        #                discriminator) + a kept word mirror for the remove-as-COST
        #                tail (Walking Ballista, Quillspike — an Ability.cost phase
        #                leaves in raw). The IR also catches Graft's counter MOVE the
        #                narrow regex missed.
        #   counter_place_trigger ← a counter_added TRIGGER (scope!='opp', non-Saga).
        #                EXCLUDES Saga CHAPTERS (phase types the lore-counter chapter
        #                trigger as the SAME counter_added(scope='you',subj=None) a
        #                +1/+1 payoff carries — 202 Sagas would flood otherwise; the
        #                Saga supertype / lore-counter reminder is the only
        #                discriminator). is_widen_of counters_matter (co-fires).
        #   counter_replace_bonus ← the counter_doubling replacement category (same
        #                population as counter_doubling, is_widen_of it) + a
        #                place_counter(kind='plus') tail for the temporary activated
        #                form (Prairie Dog, 1 card, zero over-fire).
        #   exile_until_leaves ← _is_exile_until_leaves: the inline "exile/blink …
        #                until ~ leaves" raw phrase OR the two-ability linked-return
        #                O-Ring shape (exile to:exile + a dies/leaves trigger whose
        #                reanimate returns to:battlefield — Oblivion Ring, Fiend
        #                Hunter the inline regex missed) + a Saga-chapter mirror
        #                (Trial of a Time Lord collapses its per-effect raw to a
        #                "Chapter N" stub, losing the phrase).
        "counter_manipulation",
        "counter_place_trigger",
        "counter_replace_bonus",
        "exile_until_leaves",
        # ADR-0027 — counter_doubling (CR 122 counters / 614 replacement effects)
        # migrated to the Card IR via a STRUCTURAL arm + a BYTE-IDENTICAL kept mirror
        # (the lane is BROADER than phase's one `counter_doubling` replacement
        # category, so neither source alone suffices):
        #   • structural arm — the `cat == "counter_doubling"` replacement-effect
        #     category (event=='addcounter', qmod in _INCREASE_MODS) fires the static
        #     "if one or more counters would be put … put twice that many instead"
        #     doublers (Doubling Season, Branching Evolution, Primal Vigor, Corpsejack
        #     Menace, The Earth Crystal, Struggle for Project Purity's rad-counter
        #     Enclave mode). These 6 are the CANONICAL replacement doublers the deleted
        #     regex MISSED — "twice that many … counters are put" never matched its
        #     "double the number of …" / "would put … instead … twice" pattern. The
        #     structural arm recovers them (a strict, all-genuine recall WIN).
        #   • _COUNTER_DOUBLING_MIRROR — the OR of the two deleted oracle regexes (the
        #     _HAND_FLOOR producer + the SWEEP_DETECTORS row), pinned as
        #     COUNTER_DOUBLING_REGEX, run FLAT over the reminder-stripped joined-face
        #     kept_oracle. phase v0.1.19 MANGLES the ONE-SHOT / activated / triggered
        #     doublers — "double the number of +1/+1 counters on it" — into a generic
        #     `double` effect (8: Vorel, Gilder Bairn, Deepglow Skate, …) or, worse,
        #     loses the doubling semantics entirely to a plain `place_counter` /
        #     `counter_distribute` (38: Kalonian Hydra, Primordial Hydra, Voracious
        #     Hydra, Growth Curve, Study the Classics, Fractal Harness, …). No clean
        #     structural arm reaches all 46, so the byte-mirror recovers them. It is
        #     byte-identical to the deleted regex (commander-legal: mirror == regex ==
        #     69 exactly, 0 over-fire, 0 miss). add() dedups the 23 the structural arm
        #     already supplies.
        # Floor-mirror-dep == 0 (NOT in _IR_FLOOR_LANES). Hybrid fires 75 (the regex's
        # 69 via mirror + the 6 replacement doublers via the structural arm) — the
        # ONLY no-flood move, all 6 genuine (verified vs Scryfall). Token- and
        # counter-doubling stay SEPARATE lanes (a token doubler wants token MAKERS, a
        # counter doubler wants counter SOURCES — feedback_split_too_broad_lanes). The
        # _HAND_FLOOR producer + the SWEEP row are deleted; the serve spec
        # (signal_specs.py) is hand-registered and survives. See ADR-0027.
        "counter_doubling",
        # ADR-0027 tranche2-C (batch C) — three structural migrations:
        #   extra_land_drop ← cheat_play / topdeck_select with a Land subject (put a
        #     land from hand/library onto the battlefield) + a YOUR-anchored kept word
        #     mirror for the empty-raw modal / cascade / phase-mis-zoned tail. The
        #     deleted regex's broad arm over-matched into graveyard sources (Wreck and
        #     Rebuild / Soul of Windgrace), which phase correctly routes to reanimate
        #     (a graveyard-lands engine, a different shape) — residual 2, both o/fire.
        #     Floor-mirror-dep == 0; IR is a recall-gaining superset (+19). SWEEP row
        #     deleted; serve hand-spec'd.
        #   free_creature_payoff ← an ETB trigger whose condition tree carries a
        #     manaspentcondition (Satoru the Infiltrator). The etb-trigger gate excludes
        #     the 4 cast_spell-triggered manaspentcondition anti-free-spell punishers
        #     (Lavinia / Boromir / Roiling Vortex / Vexing Bauble); the deleted regex
        #     100% over-fired on those + self-punish/self-bonus forms (Primeval Spawn,
        #     Freestrider Commando). Floor-mirror-dep == 0; residual 7, all over-fire.
        #     Its _DETECTORS regex producer is deleted; the serve spec stays.
        #   keyword_counter ← a place_counter / remove_counter whose counter_kind is in
        #     the closed CR-122.1b keyword set (_KEYWORD_COUNTER_KINDS) + a kept word
        #     mirror (KEYWORD_COUNTER_REGEX) for the choice/multi/quoted-grant tail
        #     phase drops counter_kind on ("your choice of a flying OR hexproof").
        #     Floor-mirror-dep == 0; IR is a strict superset of the regex (regex_only 0,
        #     +6 recall). SWEEP row deleted; serve reuses the shared regex constant.
        # (keyword_grant_target — formerly DEFERRED here — is now migrated via the
        # SIDECAR v14 single_target_grant marker projection; see its block below.)
        # (gain_control was deferred for the cross-open shape; NOW MIGRATED below via
        # the IR arm + a narrowed kept-mirror + a facade cross-open reconciliation — see
        # the gain_control entry near the end.)
        "extra_land_drop",
        "free_creature_payoff",
        "keyword_counter",
        # ADR-0027 tranche2-batch-3-A — land-animation + keyword-soup lanes.
        #   land_denial          ← phasing Effect, Land subject, controller=='you'
        #     (Taniwha). Pure-structural; regex==IR==1, residual 0; floor-mirror-dep 0.
        #   keyword_soup         ← >=5 distinct evergreen grant_keyword counter_kinds in
        #     one ability (Odric class) + a kept oracle mirror for the "same is true
        #     for …" idiom phase under-parses (Indominus Rex). Combined residual 0;
        #     +8 genuine keyword-stackers the regex missed. Floor-mirror-dep 0.
        #   land_creatures_matter / land_protection ← the SHARED land-animator predicate
        #     (animate/base_pt_set/type_set over a Land subject, you- vs you/any-gated)
        #     + Land+Creature anthem/maker subjects + a kept oracle mirror for the
        #     self-animate manlands phase drops. Combined residual 0; +127 / +97
        #     manlands the regex missed. Floor-mirror-dep 0; the co-fire on one
        #     land-animator is correct (the deck wants both lanes).
        # legend_rule_off MIGRATED (ADR-0027 β kept-mirror) — phase's legend_exempt is a
        # strict SUBSET of the regex (2 of 8; the bounded-scope variant is dropped), so
        # it rides a byte-identical _IR_KEPT_DETECTORS mirror of the deleted regex (all
        # 8; see the entry above). It is NO LONGER on the regex path.
        "land_denial",
        "keyword_soup",
        "land_creatures_matter",
        "land_protection",
        # Group "tranche2-B-3" (ADR-0027) — 2 of 5 batch keys migrated structurally;
        # timing_control later migrated via an ADR-0027 β kept-mirror (phase emits
        # nothing structural for the cast-timing statics — see the entry above), and
        # token_copy_matters via an ADR-0027 β kept-mirror too (the structural
        # CopyTokenOf/Populate effect 100%-over-fires the lane with reminder-text
        # SELF-copies — Embalm/Eternalize/Offspring/Double-team — that the
        # reminder-stripped regex deliberately excludes; see the entry below). The
        # remaining 1 (self_counter_grow) stays DEFERRED for a genuine floor-disabled
        # IR-vs-regex recall gap (NOT 100% over-fire), see the deferral comment at its
        # arm / producer.
        #   spell_keyword_grant ← the WHOLE `cast_with_keyword` effect category (the
        #     umbrella over flash_grant / convoke_matters — it co-fires with them on
        #     those subsets, e.g. Chief Engineer). Floor-mirror-dep == 0. The floor-
        #     disabled regex-only residual is 1 card (Wicker Picker, a "sticker kicker"
        #     non-keyword grant phase routes to grant_keyword) — 100% over-fire of the
        #     deleted regex's bare "creature spells you cast have" arm. The IR adds 52
        #     genuine granters the narrow keyword-list regex missed ("cast spells as
        #     though they had flash" enablers — Vedalken Orrery, Leyline, Yeva; ripple/
        #     cascade granters). Its SWEEP_DETECTORS row is deleted; serve reuses the
        #     shared SPELL_KEYWORD_GRANT_REGEX. CR 702 / 601.3e.
        #   target_player_draws ← a `draw` effect with scope=='any' (the directed /
        #     forced draw; a self-cantrip parses scope=='you', "each player draws"
        #     scope=='each' → group_hug_draw, so the gate isolates the directed draw).
        #     Floor-mirror-dep == 0. The floor-disabled regex-only residual is 1 card
        #     (Arcane Artisan, whose "Target player draws … then exiles" draw phase
        #     scopes 'opp' for the downstream forced discard — the card stays covered by
        #     activated_draw + token_copy_matters, no coverage loss). The IR adds 233
        #     genuine directed/forced draws the narrow "draws a card|target opponent
        #     draws" regex missed ("Target player draws seven cards", "that player
        #     draws", Edric's "its controller may draw"). Its SWEEP_DETECTORS row is
        #     deleted; serve reuses the shared TARGET_PLAYER_DRAWS_REGEX. CR 120.2.
        "spell_keyword_grant",
        "target_player_draws",
        # ADR-0027 — group_hug_draw (the symmetric group-hug card-advantage lane:
        # a card that draws for EVERY player — Howling Mine, Wheel of Fortune,
        # Timetwister, Windfall, Prosperity, Font of Mythos, Dictate of Kruphix).
        # STRUCTURAL ARM (signals._signals_ir, the `draw` Effect scope=='each' —
        # the v22 projection's structural tell for "each player draws"). DISJOINT
        # from the YOU-draw payoff (draw_matters reads the `drawn` trigger scope
        # 'you'), the directed/forced OPP-draw (target_player_draws reads the
        # `draw` effect scope=='any'), and the scaling X-draw (draw_for_each reads
        # a `draw` effect with a board-count amount). The SWEEP_DETECTORS row is
        # deleted; the serve spec stays hand-registered (signal_specs.py).
        # FLOOR. group_hug_draw is NOT an _IR_FLOOR_LANE (it was a SWEEP_DETECTORS
        # producer, like draw_for_each / symmetric_damage_each), so floor-mirror-dep
        # == 0.
        # RESIDUAL (commander-legal, floor-disabled, by oracle_id).
        #   both=42, ir_only=37, regex_only=4 — scope parity PERFECT (every firing,
        #   regex and IR, is scope 'each').
        #   ir_only (+37, ALL genuine): the WHEEL / mass-draw cards the narrow regex
        #     `each player (?:may )?draws?\b` MISSED on word-adjacency — the wheel
        #     text reads "each player discards their hand, THEN draws seven cards",
        #     so "each player" is not immediately followed by "draws" and the regex
        #     never fires; the structural `draw` Effect carries scope=='each'
        #     regardless of the intervening discard/shuffle clause. Wheel of
        #     Fortune, Timetwister, Windfall, Day's Undoing, Memory Jar, Reforge the
        #     Soul, Wheel of Fate, Jace's Archivist, Molten Psyche, Time Spiral,
        #     Whispering Madness, Magus of the Jar/Wheel, Step Between Worlds,
        #     Sensation Gorger, Wheel of Misfortune, Rankle (modal "each player …
        #     draws"), Tales of the Ancestors ("each player with fewer cards …
        #     draws"), etc. — all verified vs ACTUAL Scryfall oracle to draw for
        #     every player. A strict structural WIN over the regex's adjacency gap.
        #   regex_only (4): Grothama, All-Devouring / Mathise, Surge Channeler /
        #     Vault 11: Voter's Dilemma / Winter Sky — all literally say "each player
        #     draws", but phase UNDER-STRUCTURES them: the variable-amount /
        #     d20-outcome / Saga-chapter draws fold to a `draw` Effect scope=='any'
        #     (the directed-draw bucket → target_player_draws), and Winter Sky's
        #     coin-flip branch emits NO draw Effect at all. The narrow structural
        #     arm can't reach these, so the lane keeps a BYTE-IDENTICAL kept WORD
        #     MIRROR (GROUP_HUG_DRAW_REGEX, the EXACT deleted SWEEP regex, in
        #     _IR_KEPT_DETECTORS, scope 'each'). Mirror set == the deleted regex's
        #     46 commander-legal cards EXACTLY (mirror does NOT broaden: mirror==46,
        #     struct adds the 37 wheels on top), so union(struct|mirror) loses 0 and
        #     over-fires 0 — the extra_combats precedent (structural arm + tail
        #     mirror). CR 120.2 (draw is a player action).
        "group_hug_draw",
        # ADR-0027 tranche2-B (t2b3-B) — four structural migrations. NONE is in
        # _IR_FLOOR_LANES (floor-mirror-dep == 0 — each fires from a NON-floor
        # structural IR source with the floor disabled). Floor-disabled IR-vs-regex
        # residual on the commander-legal corpus, all adjudicated:
        #   lose_unless_hand       ← an etb trigger scope=you + a lose_game effect
        #     (Phage the Untouchable). A-B==0 — single-card archetype, structurally
        #     unique. Its _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   opponent_cast_matters  ← the structural cast_spell scope=opp arm + an
        #     _IR_KEPT_DETECTORS mirror (the deleted regex MINUS its bare "whenever a
        #     player casts" arm — the symmetric-punisher's "that player" anchor excludes
        #     the scope='any' spellslinger over-fire phase can't separate). regex_only
        #     is 100% over-fire (symmetric-benefit / self-drawback
        #     cards the bare arm wrongly opened — Forgotten Ancient, Chalice, Ebon
        #     Drake — plus emblem-buried Jace / odd-parse); the IR is MORE precise. Its
        #     _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   opponent_counter_grant ← a place_counter of a DETRIMENTAL counter (CR
        #     122.1d) on an opponent's permanent — direct opp subject (bounty/stun/m1m1/
        #     slime/bribery/rejection) or a co-tap-opp recovery for the "tap … and stun
        #     it" pronoun shape; beneficial p1p1/shield/keyword counters excluded.
        #     regex_only==0 (the bribery recall gap — Gwafa Hazid — is closed); ir_only
        #     is legitimate breadth (all real opponent-detrimental-counter cards). Its
        #     SWEEP_DETECTORS row is deleted; serve hand-spec'd.
        #   power_tap_engine       ← an ACTIVATED ability cost~'tap' + a power-scaling
        #     effect raw (Marwyn, Selvala, Staff of Domination) + an _IR_KEPT_DETECTORS
        #     mirror for the granted/quoted "{T}: … equal to its power" form phase folds
        #     into a grant carrier (Predatory Urge,
        #     Dragon Throne, Arlinn back face). regex_only==0; ir_only is breadth (the
        #     structured ab.cost catches "{T}, Sacrifice …" engines the contiguous
        #     "{t}:" regex missed — Brion Stoutarm, Ghitu Fire-Eater). Its _HAND_FLOOR
        #     producer is deleted; serve hand-spec'd.
        # pump_matters (a POSITIVE single-target combat-trick buff) migrated below as a
        # byte-identical kept-mirror — it is genuinely UNSTRUCTURABLE as a positive
        # discriminator (see its entry near the end of this set). See ADR-0027.
        "lose_unless_hand",
        "opponent_cast_matters",
        "opponent_counter_grant",
        "power_tap_engine",
        # ADR-0027 tranche2-batch-4 (t2b4-C) — 5 kept_detector keys phase v0.1.60
        # CANNOT structure (the discriminant is DROPPED in the parse), so each fires
        # from a dedicated IR-path WORD MIRROR (the EXACT deleted regex) in
        # extract_signals_ir — the sanctioned home for mechanics with no structural IR
        # form. Each mirror reads the joined-face oracle, so it is byte-identical to the
        # deleted regex (NO-FLOOD via file-swap baseline: each key's count UNCHANGED,
        # A-B==0). floor-mirror-dep == 0 by construction (none is a floor detector).
        # Voltron: each fired high-confidence in the regex path, so all 5 are added to
        # _VOLTRON_SILENCING_PLAN_KEYS to preserve the commander-damage tell silencing
        # the IR re-supply now carries (0 voltron leaked). See ADR-0027.
        #   damage_to_you_punish ← phase keeps deals_damage but drops the opp-source
        #     filter AND the "to you" recipient. SWEEP row deleted; serve hand-spec'd.
        #   excess_damage ← clean payoffs bind structurally (Trigger event), but the
        #     intervening-condition / spell-text refs ride Effect.raw — recovered by a
        #     `\bexcess damage\b` mirror. SWEEP row deleted; serve hand-spec'd.
        #   self_blink ← no clean IR form (the `~`-substituted exile raw is ambiguous);
        #     reproduce BOTH regex producers byte-identically (the name-aware fulltext
        #     detector + the per-clause _SELF_BLINK_SWEEP_RE). SWEEP row + the regex-
        #     path emission deleted; serve hand-spec'd.
        #   tap_down_blockers ← the "can't be blocked unless all … block it" clause is
        #     100% dropped by phase. _HAND_FLOOR row deleted; serve hand-spec'd.
        #   type_change ← phase drops the protection subtype argument; mirror the
        #     _type_hoser_clause subtype-gated detector. _DETECTORS row deleted; serve
        #     hand-spec'd.
        "damage_to_you_punish",
        "excess_damage",
        "self_blink",
        "tap_down_blockers",
        "type_change",
        # ADR-0027 tranche2-batch-4 (t2b4a-A) — 3 of 5 keys migrated; each fires from a
        # STRUCTURAL IR arm (NONE in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them, and
        # the floor-ON firing set is byte-identical to the floor-OFF one). NO-FLOOD held
        # via the file-swap baseline (only the target keys' counts moved; voltron
        # membership unchanged — none of the 3 fed has_other_plan). Each migrated key's
        # oracle-regex producer is deleted; serve specs stay hand-registered.
        #   tribal_etb_multi ← an `etb` Trigger whose subject Filter names a creature
        #     SUBTYPE (vocab-gated _kindred_subjects — "this or another <Tribe> you
        #     control enters"). The broad structural read is the lane's intent (every
        #     tribal-ETB chain — Miirym, Lathliss, Righteous Valkyrie, Hada Freeblade),
        #     far wider than the artificially-narrow multi-tribe self-inclusion regex.
        #     The vocab gate drops the deleted regex's non-tribal over-fires (Serum
        #     Tank's Artifact ETB, River Kelpie / Flayer's graveyard-permanent ETB — no
        #     creature subtype). regex-only residual 3, 100% over-fire. CR 603.
        #   typed_enters_punish ← an `etb` Trigger on a YOUR-controlled creature/typed-
        #     thing whose consequence is a `damage` Effect with an OPPONENT recipient
        #     (subject controller=='opp', scope in opp/each, OR an "each/target
        #     opponent" / "any target" raw — _TYPED_ENTERS_OPP_RAW recovers Purphoros
        #     / Witty Roastmaster, whose damage phase scopes 'any'). The damage-to-
        #     opponent payoff is the discriminator vs plain creature_etb value.
        #     regex-only residual 0; ir_only is broader-and-correct recall (Dread
        #     Presence, Terror of the Peaks, Impact Tremors, landfall burn). CR 603.
        #   vanilla_matters ← the HasNoAbilities subject-Filter predicate (read in
        #     _predicate_build_around_lanes, gate controller in {'you','any'}). The
        #     predicate is its own discriminator (a card merely BEING vanilla never
        #     carries it). The IR drops the regex's lone over-fire (Rise from the Wreck,
        #     a multi-target Mount/Vehicle recursion spell enumerating "creature card
        #     with no abilities" — incidental mention, not a vanilla build-around) and
        #     ADDS the "Creatures you control with no abilities" anthem the contiguous
        #     regex missed (Jasmine Boreal). regex-only residual 1, over-fire. CR 113.3.
        # DEFERRED (needs-projection — genuine recall gap, NOT clean over-fire):
        #   untap_engine ← the IR arm (already wired) misses 11 genuine untap engines
        #     the regex catches (modal "tap or untap target" — Captain of the Mists,
        #     Tideforce Elemental; "tap-all OR untap-all" choose — Turnabout, Faces of
        #     the Past; mass-untap-of-own-board — All-Out Assault, Ohabi Caleria; the
        #     creatures-are-lands synergy — Ashaya). phase routes their untap text into
        #     `choose` / `bounce` / cost / SelfRef shapes, not a `cat=='untap'` effect.
        #     Its two _HAND_FLOOR producers stay on the regex path.
        "tribal_etb_multi",
        "typed_enters_punish",
        "vanilla_matters",
        # ADR-0027 tranche2-batch-4a (t2b4a-B) — two structural IR keys + three
        # field-lookup keyword-array keys:
        #   win_lose_game  ← Effect.category in {win_game, lose_game} (the broad
        #     terminal-outcome pool) + a kept regex mirror (scope 'any') for the
        #     conferred/quoted-ability tail (Vraska tokens, Frodo). SWEEP row deleted.
        #   xspell_matters ← the HasXInManaCost predicate on a cast_spell trigger
        #     subject (Zaxara …) + a kept effect-raw hook mirror (minus the hoser veto)
        #     for the predicate-dropped tail (Unbound Flourishing, Rosheen). _DETECTORS
        #     row deleted.
        #   alt_cost_keyword ← Scryfall web-slinging / sneak / mayhem keyword array
        #     (_IR_KEYWORD_MAP). SWEEP row deleted; drops the regex's flavor/grant
        #     over-fires.
        #   curse_matters ← a trigger/effect subject Filter subtypes=='Curse' +
        #     a kept regex mirror (the deleted cares-about regex) for the under-parsed
        #     "search for a Curse card …" tail. _HAND_FLOOR row deleted. Membership
        #     stays REGEX-ONLY at A4.
        #   partner_background ← Scryfall partner-family keyword array (_IR_KEYWORD_MAP;
        #     partner / partner with / choose a background / doctor's companion /
        #     friends). SWEEP row deleted; drops the regex's name-comma over-fires,
        #     recovers Friends-forever partners. Feeds the ADR-0019 color-widening
        #     avenue (production cards carry the keyword). companion NOT mapped.
        "win_lose_game",
        "xspell_matters",
        "alt_cost_keyword",
        "curse_matters",
        "partner_background",
        # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector keys phase v0.1.60
        # CANNOT structure, each fires from a dedicated IR-path WORD MIRROR (the EXACT
        # deleted regex) in extract_signals_ir, the sanctioned home for mechanics with
        # no structural IR form. Each mirror reads the joined-face oracle, so it is
        # byte-identical to the deleted regex (NO-FLOOD via file-swap baseline: each
        # key's count UNCHANGED, A-B==0). floor-mirror-dep == 0 by construction (none
        # is a floor detector). Voltron: each fired high-confidence in the regex path,
        # so all 5 are added to _VOLTRON_SILENCING_PLAN_KEYS to preserve the commander-
        # damage tell silencing the IR re-supply now carries (0 voltron leaked — the
        # kept mirror is byte-identical, so the IR re-supply is the same set). ADR-0027.
        #   draft_spellbook ← Arena/Alchemy digital mechanics (draft-a-card / spellbook)
        #     not in the CR, no phase effect category. SWEEP row deleted; serve hand-
        #     spec'd.
        #   each_mode_player ← phase captures the modal head but has no field for the
        #     spread-the-modes constraint. SWEEP row deleted; serve hand-spec'd.
        #   flip_self ← phase parses the Kamigawa flip inconsistently; "flip this
        #     creature" is the tell. SWEEP row deleted; serve hand-spec'd.
        #   free_plot ← no IR structure for the Plot alt-cost rewrite; the phrase is
        #     unique to Fblthp. _HAND_FLOOR row deleted; serve stays hand-spec'd.
        #   miracle_grant ← phase folds the grant into a carrier; the granting-direction
        #     phrase is the tell. SWEEP row deleted; serve hand-spec'd.
        "draft_spellbook",
        "each_mode_player",
        "flip_self",
        "free_plot",
        "miracle_grant",
        # ADR-0027 tranche2-batch-5 (t2b5-B) — five kept_detector lanes phase v0.1.60
        # CANNOT structure (the discriminant is DROPPED in the parse), each firing from
        # a dedicated IR-path word mirror (_IR_KEPT_DETECTORS) reproducing the deleted
        # _HAND_FLOOR / SWEEP regex. All NON-floor IR sources; floor-mirror-dep == 0;
        # A-B == 0 by construction (the secret_writedown mirror is INTENTIONALLY
        # narrower — it drops the deleted regex's companion-reminder "your sideboard"
        # arm, owned by companion_keyword). Their oracle-regex producers are deleted;
        # the serve specs stay hand-registered in signal_specs.py. See ADR-0027.
        #   per_target_payoff    ← Hinata's per-target cost-reduction arm (no IR
        #     mana-cost / target-count operand; CR 601 / 118).
        #   sacrifice_protection ← protective-vs-stax restriction split + the
        #     quoted/granted forms phase drops (CR 701.16).
        #   secret_writedown     ← out-of-game zone + pre-game secret name (CR 408.1).
        #   target_own_payoff    ← Monk Gyatso's becomes-target may-reaction (the
        #     trigger flattens to event='other'; CR 603).
        #   target_redirect      ← Rayne's becomes-target-of-opponent → draw (same
        #     event='other' flattening; CR 603).
        "per_target_payoff",
        "sacrifice_protection",
        "secret_writedown",
        "target_own_payoff",
        "target_redirect",
        # ADR-0027 tranche2-batch-5 (t2b5-C) — four kept_detector keys + one
        # field-lookup keyword-array key:
        #   targeting_matters ← a kept regex mirror (the exact deleted SWEEP regex:
        #     heroic + becomes-target + cast-that-targets; phase structures the heroic /
        #     cast-that-targets half but flattens the becomes-target trigger to
        #     event='other'). SWEEP row deleted; clause-safe (A-B==0).
        #   theft_protection ← a kept regex mirror ("for the first time each turn,
        #     counter"; phase parses Kira's grant as a carrier + counter_spell but drops
        #     the once-per-turn becomes-target gate). _HAND_FLOOR row deleted.
        #   villainous_choice ← a kept regex mirror (the "villainous choice" literal;
        #     phase routes the keyword action to a generic 'choose' Effect). _HAND_FLOOR
        #     row deleted.
        #   named_counter_misc ← a kept regex mirror (the closed named-counter set).
        #     phase's structured counter_kind covers 32/34, but a place/remove-as-cost
        #     or replacement form (Mazemind Tome, Pursuit of Knowledge) drops
        #     counter_kind — a 2-card recall gap — so the byte-identical word mirror is
        #     the migratable home, not the partial structural field. SWEEP row deleted.
        #   powerup_matters ← the Scryfall Power-up keyword array (_IR_KEYWORD_MAP[
        #     'power-up'], a field lookup, 37 keyword carriers == 37 regex hits, 0
        #     residual). SWEEP row deleted. (Rides _IR_KEYWORD_KEYS in IR_SLICE_KEYS.)
        "targeting_matters",
        "theft_protection",
        "villainous_choice",
        "named_counter_misc",
        "powerup_matters",
        # ADR-0027 cmdzone_ability — an Eminence / command-zone-gated ability. The
        # triggered+activated halves (Oloro, Edgar, Arahbo, Inalla, Sidar Jabari)
        # fire from a STRUCTURAL arm in extract_signals_ir: 'command' in the ability
        # zones OR in the recursive Condition zone tree (phase models the command-
        # zone gate as Condition(kind='sourceinzone', zones=('command',)), nested
        # under an 'or' for the on-battlefield-OR-command form). The STATIC-Eminence
        # half (The Ur-Dragon's cost-reducer) drops the condition in phase's parse,
        # so it rides a byte-identical _IR_KEPT_DETECTORS word mirror (the exact
        # deleted SWEEP regex). struct plus mirror == the regex set on the commander-
        # legal corpus (0 gap, 0 over-fire); floor-mirror-dep == 0 (not a floor
        # lane). Its SWEEP_DETECTORS row is deleted; the serve is hand-registered in
        # signal_specs (reusing the deleted regex). CR 702.107 / 903.6.
        "cmdzone_ability",
        # ADR-0027 q2-D2 — opp_top_exile: the structural extract_signals_ir arm (exile
        # scope=='opp' + cast_from_zone scope=='opp', OR exile scope=='opp' carrying
        # 'in:library') plus an _IR_KEPT_DETECTORS word mirror (the exact deleted regex)
        # for the name-lock / peek subset phase under-parses. Net recall ≥ regex (the
        # mirror recovers the 6 residuals byte-identically; the structural arm adds 50
        # steal-and-cast cards the regex never reached). _HAND_FLOOR producer deleted.
        "opp_top_exile",
        # ADR-0027 (q2-D3) — two half-migrations (clean IR arm + kept word mirror):
        #   flash_matters ← the GRANT half binds via cast_with_keyword{flash} (the same
        #     node flash_grant reads; Leyline, Vivien). The FULL deleted _HAND_FLOOR
        #     regex is kept byte-identically as an _IR_KEPT mirror to recover the
        #     ACTIVATED flash-grant (phase folds to grant_keyword with empty ck —
        #     Winding Canyons, Teferi Time Raveler) + the opponent-turn cast payoff
        #     (textual). Broader-and-correct (+1: Teferi Mage of Zhalfir). floor-mirror-
        #     dep == 0 (not a floor lane). NO-FLOOD held (voltron 0 leaked). CR 702.8.
        #   noncreature_cast_punish ← the OPPONENT-punisher half binds via a cast_spell
        #     trigger scope=='opp' over a noncreature subject (NotType:Creature or a
        #     noncreature card-type set; Kambal, Mystic Remora, Esper Sentinel — +13
        #     genuine recall the regex missed, 0 over-fire on scope=='opp'). The
        #     SYMMETRIC "a player casts a noncreature spell" half collapses to
        #     scope=='any' (indistinguishable from prowess in phase v0.1.19), so its
        #     deleted SWEEP branch rides an _IR_KEPT mirror anchored on "a player"/"an
        #     opponent". floor-mirror-dep == 0. NO-FLOOD held (the _OPP_CAST / new
        #     mirror re-supply keeps voltron byte-identical). CR 603.2.
        "flash_matters",
        "noncreature_cast_punish",
        # ADR-0027 — flash_grant: the GRANT-to-OTHERS flash ENABLER lane (a card that
        # lets you cast a CLASS of OTHER spells "as though they had flash" — Vedalken
        # Orrery, Leyline of Anticipation, Teferi, Yeva, Emergence Zone; CR 702.8).
        # Binds via the SAME cast_with_keyword{flash} structural arm as flash_matters
        # (the 29 cards phase parses as a cast-permission static), plus the FULL deleted
        # SWEEP regex kept BYTE-IDENTICALLY as an _IR_KEPT mirror (FLASH_GRANT_REGEX) to
        # recover the activated/conditional grant phase folds into an empty counter_kind
        # (Winding Canyons, Aluren) AND the "cast THIS spell as though it had flash"
        # self-flash tail (Rout, Necromancy). union == the deleted producer's 81
        # commander-legal fires EXACTLY (regex_only 0, ir_only 0, scope parity 'you').
        # The producer fired HIGH-confidence scope 'you' and fed has_other_plan, so
        # flash_grant is added to _VOLTRON_SILENCING_PLAN_KEYS — the IR re-supply is
        # byte-identical, so the hybrid re-silences the spurious commander-damage
        # voltron tell EXACTLY (NO-FLOOD: voltron delta 0). SWEEP_DETECTORS row deleted;
        # serve hand-registered. CR 702.8.
        "flash_grant",
        # ADR-0027 — dies_recursion: the SELF-recursion-on-death lane ("when this dies,
        # return it to the battlefield/your hand" — Bloodghast / Reassembling Skeleton /
        # Gravecrawler / Feign Death style; undying/persist-adjacent; CR 700.4 dies =
        # put into a graveyard from the battlefield, CR 603.6c leaves-the-battlefield
        # trigger). The BROAD superset of undying_persist_matters: undying (CR 702.93a,
        # +1/+1) and persist (CR 702.79a, -1/-1) ARE dies-recursion that also place a
        # counter. The undying/persist keyword BEARERS already open the lane via the IR
        # keyword map (_IR_KEYWORD_MAP['undying'/'persist'] — the floor-disabled "both"
        # set, 49 cards). phase v0.1.19 carries NO structural "returns itself on death"
        # form (the dies trigger flattens to event='other' with the return buried in the
        # effect raw), so the bare dies-return GRANTS (Feign Death / Supernatural
        # Stamina) and keyword-LESS GRANTERS (Mikaeus / Cauldron of Souls / Endling)
        # ride the FULL deleted SWEEP regex kept BYTE-IDENTICALLY as an _IR_KEPT mirror
        # (DIES_RECURSION_REGEX, scope 'you'). The `[^.]*` arms never cross a clause
        # boundary, so flat-over-kept_oracle == per-clause: floor-disabled IR-vs-regex
        # residual, commander-legal, by oracle_id, is both==98 / ir_only==0 / regex_only
        # ==0. NOT an _IR_FLOOR_LANE (floor-mirror-dep == 0). The producer fired HIGH-
        # confidence scope 'you' and fed has_other_plan (a SELF-recurring beater is a
        # real plan — Bloodghast, a recurring aristocrats sac body, is no vanilla
        # voltron body), so dies_recursion is added to _VOLTRON_SILENCING_PLAN_KEYS —
        # the IR re-supply is byte-identical, so the hybrid re-silences the commander-
        # damage voltron tell EXACTLY (NO-FLOOD: voltron delta 0). PRESERVED over-fire
        # (byte-identical, not introduced): "Undying Flames" (keywords=['Epic'], no
        # undying mechanic) self-matches `\bundying\b` on its CARD NAME embedded in its
        # oracle text — the exact regex artifact the deleted producer carried, mirrored
        # unchanged for parity. SWEEP_DETECTORS row deleted; serve reuses the pinned
        # constant. CR 700.4 / 603.6c.
        "dies_recursion",
        # ADR-0027 β — impulse_top_play: the structural arm (a NON-static cast_from_zone
        # Effect carrying the recovered 'from:library' zone) plus a per-clause
        # _IMPULSE_TOP_PLAY_SWEEP_RE mirror (the EXACT deleted SWEEP regex). The
        # structural arm adds 105 real impulse engines the regex never reached
        # (legitimate breadth, verified vs oracle text); the mirror recovers the
        # follow-through tail phase folds into a categoryless effect (recall ≥ regex).
        # floor-mirror-dep == 0 (neither source reads _IR_FLOOR_LANES). The ab.kind!=
        # 'static' gate prevents double-firing the SIBLING play_from_top (now MIGRATED
        # via
        # a dedicated kind='static' marker — phase's TopOfLibraryCastPermission mode —
        # so
        # the two lanes are disjoint by construction). The deleted SWEEP producer fired
        # high-confidence scope 'you', so an _IMPULSE_TOP_PLAY_PLAN_MIRROR re-supplies
        # has_other_plan (NO-FLOOD: voltron byte-identical). CR 601.3b.
        "impulse_top_play",
        # ADR-0027 β — play_from_top: the ONGOING permission to play/cast cards from the
        # top of YOUR library (Future Sight, Bolas's Citadel, Mystic Forge, Vizier of
        # the
        # Menagerie, Experimental Frenzy, Magus of the Future, Garruk's Horde, Oracle of
        # Mul Daya, Courser of Kruphix). The structural arm reads a STATIC
        # cast_from_zone
        # Effect carrying 'from:library' — project._top_play_permission_marker's
        # re-surface of phase's dropped TopOfLibraryCastPermission static mode (SIDECAR
        # v16), structured through supplement's grammar (recover_effect_from_text) as
        # the
        # precision gate. The ab.kind=='static' gate + the `"exile" not in raw` gate
        # make
        # it the clean 45-card spine (the 2 granted-impulse statics phase's
        # _recover_library_zones also tags — Capricious Sliver, Tavern Brawler — say
        # "exile the top card" and are excluded). The boundary vs the sibling
        # impulse_top_play (ab.kind != 'static') is disjoint BY CONSTRUCTION: a
        # continuous
        # permission is static, a one-shot impulse-draw is not.
        #
        # The migration does NOT fully structuralize — phase models a 25-card tail as a
        # NON-cast-permission shape: REVEAL-only ("Play with the top card revealed" —
        # Goblin Spy, Crown of Convergence, Mul Daya Channelers, Skill Borrower, Vampire
        # Nocturnus; "look at the top card any time" — Sphinx of Jwar Isle, Vesuvan
        # Drifter, Glowcap Lantern), ONCE-EACH-TURN restricted casts (Johann, Cemetery
        # Illuminator, Assemble the Players, The Fourth Doctor), and TRIGGERED/temporary
        # permissions (Gwenom, The Belligerent, The Lunar Whale, Xanathar, Ziatora's
        # Envoy, Temporal Aperture, Fblthp, Radha). Those ride a per-clause
        # _PLAY_FROM_TOP_MIRROR + _PLAY_FROM_TOP_FLOOR_MIRROR (the EXACT deleted SWEEP +
        # _HAND_FLOOR regexes) so net recall == regex (no-flood).
        #
        # Floor-disabled residual vs the deleted regexes (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 41, ir_only == 0 (the structural arm is
        # a
        # clean subset of the union regex — no recall the regex misses, the value is the
        # structured spine + documented mirror tail), regex_only == 25 — the tail above,
        # ALL recovered by the byte-identical mirror so production behavior is
        # preserved.
        # The deleted FLOOR's broad `(?:play|cast)…from the top` arm pre-existingly
        # over-fires on 4 dig-until impulse engines (Amped Raptor, Codie, Jodah, Old
        # Stickfingers — "exile/reveal cards from the top … until you exile/reveal"):
        # this
        # is REPRODUCED byte-identically (no-flood), not a new over-fire.
        # SWEEP_DETECTORS
        # row + _HAND_FLOOR producer deleted (SWEEP_LABELS kept); the serve is
        # hand-registered in signal_specs.py reusing the pinned PLAY_FROM_TOP_REGEX.
        # floor-mirror-dep == 0 (play_from_top is not an _IR_FLOOR_LANE). CR 116 /
        # 601.3b.
        "play_from_top",
        # ADR-0027 — cast_from_exile: the CAST/PLAY-FROM-EXILE build-around axis —
        # payoffs and enablers that cast or play cards FROM EXILE. The "whenever you
        # cast a spell from exile" / "from anywhere other than your hand" Paradox
        # triggers (Vega, Iraxxa, Quintorius Kand, Nalfeshnee, Keeper of Secrets),
        # self-cast-from-exile creatures (Eternal Scourge, Misthollow Griffin, Squee),
        # exile-and-cast engines (Court of Locthwain, Tinybones, Norin), the "exile this
        # card from your hand … cast it for as long as it remains exiled" cycle (Masked
        # Bandits, Rakish Revelers, Spara's Adjudicators), and Plot from the top
        # (Fblthp). Served by a BYTE-IDENTICAL kept WORD MIRROR (the CAST_FROM_EXILE_
        # REGEX row in _IR_KEPT_DETECTORS, scope 'you', HIGH conf — its EXACT pattern
        # pinned in _sweep_detectors), NOT a structural arm: phase carries NO usable
        # structural form (it drops the "from exile" zone off the cast_spell trigger AND
        # the self-cast cast_from_zone Effect; the only exile cast-zone it projects —
        # castable_zones=('exile',) — is the 51-card foretell-spell SERVE pool, DISJOINT
        # from the 77 detector firings, overlap 0). Over the commander-legal corpus
        # (floor-disabled) the structural IR emits this lane on ZERO cards, so the
        # mirror run FLAT over the reminder-stripped kept_oracle is the whole lane
        # (flat==per-clause==77, 0 gain/loss). The _HAND_FLOOR producer is deleted; the
        # hand-written serve spec (signal_specs.py) is independent and survives. The
        # deleted producer fed has_other_plan (HIGH, scope 'you'), so the hybrid re-
        # silences voltron via _VOLTRON_SILENCING_PLAN_KEYS — byte-identical re-supply,
        # no over-silence.
        # Distinct from impulse_top_play / play_from_top (the top-of-LIBRARY lanes — a
        # different zone). cast_from_exile was NEVER a SWEEP key (floor count stays 33).
        # CR 207.2c / 601.3b / 903.10a.
        "cast_from_exile",
        # ADR-0027 — exile_matters: the EXILE-ZONE-AS-RESOURCE cares-about axis — a
        # card caring about cards STANDING in exile. The "cards you own in exile" /
        # "card in exile with <kind> counter" P/T scalers + cast-from-the-exile-pile
        # engines (Cosmogoyf, Crackling Drake, Mairsil, Grolnok, Tasha, Kianne,
        # Ketramose, Ulamog), the wishboard fetch (Karn, Coax), the
        # own-a-card-in-exile gates (Dreadlight Monstrosity, Howling Galefang, Warden
        # of the Beyond), the "exiled with <this>" persistent-pile payoffs (Gorex, The
        # Kenriths' Royal Funeral, Lumbering Battlement), and the "for each card
        # exiled this way" one-shot scalers the prefix branch also reaches (the March
        # cycle, Mizzix's Mastery, Haunting Echoes — pre-existing breadth). Served by
        # a BYTE-IDENTICAL kept WORD MIRROR (the EXILE_MATTERS_REGEX row in
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf — its EXACT pattern pinned in
        # _sweep_detectors), NOT a structural arm: phase carries NO usable structural
        # form (it scatters the exile-zone reference across a `zones=('in:exile',)`
        # count operand (Ulamog), a `Condition(zones=('exile',))` (Ketramose), and a
        # `characteristic_pt` Effect whose count operand drops the zone (Cosmogoyf,
        # Crackling Drake), with no single category meaning "references cards standing
        # in exile"). Over the commander-legal corpus (floor-disabled) the structural
        # IR emits this lane on ZERO cards, so the mirror run FLAT over the
        # reminder-stripped kept_oracle is the whole lane (flat==per-clause==63, 0
        # gain/loss — neither branch carries a `[^.]*` cross-clause span). FLOOR→KEPT:
        # exile_matters was an _IR_FLOOR_LANE, now removed (floor-mirror-dep -> 0).
        # The _HAND_FLOOR producer is deleted; the hand-written serve spec
        # (signal_specs.py) is independent and survives. The deleted producer fed
        # has_other_plan (HIGH, scope 'you'), so the hybrid re-silences voltron via
        # _VOLTRON_SILENCING_PLAN_KEYS — byte-identical re-supply, no over-silence.
        # Distinct from exile_removal (EXILE a permanent as REMOVAL), cast_from_exile
        # above (CAST/PLAY a card FROM exile), and opponent_exile_matters (GRAVEYARD
        # HATE). exile_matters was NEVER a SWEEP key (floor count stays 32). CR 406.
        "exile_matters",
        # ADR-0027 — superfriends_matters (the PLANESWALKER-as-a-group cares-about lane:
        # the "planeswalkers you control" anthem (Doubling Season-adjacent walkers
        # decks), the "loyalty counter" payoffs (proliferate / Carth / Atraxa shells),
        # the "activate a loyalty ability" engines (The Chain Veil, Teferi's ultimate),
        # the "planeswalker type" group ref (Leori, Shape Shifter Sovereign), and the
        # "abilities of a planeswalker" copiers (Oath of Teferi, The Chain Veil)).
        # Served by a UNION: (1) the EXISTING structural arm in extract_signals_ir — a
        # Condition gated on a Planeswalker subject you control ("as long as you control
        # a <Name> planeswalker, this creature …", "if you control a Chandra
        # planeswalker, …"),
        # which fires on 26 commander-legal cards the deleted regex's narrow word
        # patterns MISSED (the singular "control a <Name> planeswalker" gate — Charging
        # War Boar, Court Cleric, Renegade Firebrand, Oath of Chandra/Liliana, the
        # planeswalker-deck "uncommon partner" creatures); PLUS (2) a byte-identical
        # SUPERFRIENDS_MATTERS_REGEX kept WORD MIRROR (its EXACT pattern pinned in
        # _sweep_detectors, scope 'you', HIGH conf) for the BROADER textual refs phase
        # leaves unstructured (the anthem / loyalty-counter / activate-loyalty / walker-
        # ability-copy clauses scatter into pump_target / counter / activated-ability
        # shapes with no "references planeswalkers-as-a-group" tag). The mirror run FLAT
        # over the reminder-stripped kept_oracle reproduces the deleted per-clause
        # producer BYTE-IDENTICALLY (flat==per-clause==149, 0 gain/loss — no branch
        # carries a `[^.]*` cross-clause span); add() dedups it against the structural
        # arm. FLOOR→KEPT: superfriends_matters was an _IR_FLOOR_LANE, now removed
        # (floor-mirror-dep -> 0). The _HAND_FLOOR producer is deleted; the hand-written
        # serve spec (signal_specs.py) is independent and survives. The deleted producer
        # fed has_other_plan (HIGH, scope 'you', not generic/voltron-compat); because
        # the IR re-supply is BROADER (+26 ir_only), the hybrid re-silences voltron via
        # byte-identical _SUPERFRIENDS_MATTERS_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_
        # KEYS, which would over-silence the 26). Floor-disabled residual (IR-vs-regex,
        # by oracle_id): both==0, regex_only==149 (all recovered by the kept mirror),
        # ir_only==26 (all genuine "control a <Name> planeswalker" payoffs).
        # superfriends_matters was NEVER a SWEEP key (floor count unchanged). CR 306 /
        # 606 / 903.10a.
        "superfriends_matters",
        # ADR-0027 β — free_spell_storm: a per-spell SCALING self-discount whose
        # cost drops for each spell CAST THIS TURN, so the deck wants FREE (0-cost)
        # spells to chain and keep cutting it (Thrasta, Tempest's Roar; Demilich;
        # A-Demilich). The structural arm reads a dedicated `free_spell_storm` STATIC
        # marker — project._free_spell_storm_marker's re-surface of phase's SelfRef
        # ModifyCost{Reduce} static (SIDECAR v20), which _project_static_mods DROPS
        # as a self-discount (the SelfRef cost-reducer is NOT the build-around
        # cost_reduction lane — it cheapens no OTHER spell, CR 601.2f/118.7). The
        # marker is gated to the "spells cast this turn" dynamic_count shape phase
        # carries two corpus-unique ways: SpellsCastThisTurn{scope=Controller}
        # (Demilich) or an ObjectCount whose filter has an `Another` property
        # (Thrasta). The dedicated category is read by NO other lane, so it never
        # drifts cost_reduction. FULLY STRUCTURAL — no mirror: the deleted
        # _HAND_FLOOR regex (`less to cast for each (?:other )?spell[^.]*cast this
        # turn`) matched only 2 cards and the marker improves on it both ways:
        # +Demilich/A-Demilich RECALL (the "for each instant and sorcery spell"
        # wording defeats the regex's `for each spell` anchor) and drops Delightful
        # Discovery OVER-FIRE (an opponent-spell tax, props=[] no `Another`,
        # correctly excluded). Floor-disabled residual vs the deleted regex
        # (commander-legal): both == 1 (Thrasta), ir_only == 1 (Demilich — recall
        # gain; A-Demilich is Alchemy-only, out of the commander-legal corpus),
        # regex_only == 1 (Delightful Discovery — 100% over-fire, "for each spell
        # your opponents have cast this turn", correctly dropped). Voltron file-swap
        # delta == 0 (the at-risk Thrasta keeps its has_other_plan silence via the
        # pre-existing _COST_REDUCTION_PLAN_MIRROR; Demilich via its own engine
        # plans; Delightful Discovery is power-0, no voltron candidate). floor-
        # mirror-dep == 0 (free_spell_storm is not an _IR_FLOOR_LANE). The
        # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered in
        # signal_specs.py. CR 601.2f / 118.7.
        "free_spell_storm",
        # ADR-0027 β — edict_matters: the structural opp/each `sacrifice` arm (gated by
        # _ir_effect_is_edict against 6 leaked-scope self/you-sac over-fires) plus a
        # flat _IR_KEPT_DETECTORS mirror (the EXACT deleted SWEEP regex over the joined-
        # face oracle, scope 'each'). struct + mirror reproduces the regex firing set
        # byte-identically (regex_only == 0) and adds 28 real edicts the regex missed
        # (verified vs oracle text: Annihilator reminder-only sacs, modal "those
        # players sacrifice", empty-raw modes). floor-mirror-dep == 0. The deleted SWEEP
        # producer fired high-confidence scope 'each', so _EDICT_PLAN_MIRROR re-supplies
        # has_other_plan (the IR is +28 broader, so a mirror — not
        # _VOLTRON_SILENCING_PLAN_KEYS — keeps an Annihilator voltron beater from over-
        # silencing; NO-FLOOD: voltron 0 leaked). CR 701.16.
        "edict_matters",
        # ADR-0027 β — tribe_damage_trigger: a byte-identical KEPT MIRROR (the EXACT
        # deleted SWEEP regex via _IR_KEPT_DETECTORS over the joined-face oracle, scope
        # 'you'). phase leaves the combat_damage trigger subject = None, so there is no
        # structure to read — the old `tsub_kinds` arm in extract_signals_ir was DEAD
        # CODE (never fired) and is removed. Under re.IGNORECASE the regex's
        # `[A-Z][a-z]+` also matches a generic "creature", so the lane is "your
        # creatures connect for combat damage → reward" (Toski, Reconnaissance Mission,
        # Coastal Piracy, Bident of Thassa), not strictly tribal — a kept mirror, NOT a
        # projection. The mirror reproduces the regex firing set byte-identically
        # (regex_only == 0, A-B == 0).
        # floor-mirror-dep == 0 (the mirror never reads _IR_FLOOR_LANES). NO-FLOOD held:
        # voltron 0 leaked (the kept mirror re-supplies has_other_plan via
        # _VOLTRON_SILENCING_PLAN_KEYS — byte-identical re-supply is safe). CR 510.1c.
        "tribe_damage_trigger",
        # ADR-0027 β — combat_damage_to_creature + combat_damage_to_opp (both
        # is_widen_of combat_damage_matters). The RECIPIENT-TYPE split phase
        # can't make structurally: phase carries the damage recipient on the
        # combat_damage trigger's `valid_target` (Ohran Viper's two DamageDone
        # triggers differ — Typed[Creature] vs Player), but project.py uses
        # valid_target only for its `controller` (scope), dropping its TYPE, so
        # both project to scope='any', subject=None (byte-identical). The
        # recipient discriminator survives byte-identically in the joined-face
        # oracle ("to a creature" vs "to a player/an opponent/each opponent"),
        # so each lane rides a byte-identical _IR_KEPT_DETECTORS mirror of its
        # EXACT deleted SWEEP regex — a kept mirror, NOT a projection (no
        # SIDECAR_VERSION bump). The deleted regexes only ever matched single
        # clauses, so the flat mirror reproduces the per-clause regex firing set
        # EXACTLY (commander-legal corpus: creature 33==33, opp 760==760 incl. 3
        # low-confidence double-strike-grant; the 2 cards with BOTH recipients —
        # Ohran Viper, Phage the Untouchable — fire both lanes; regex_only == 0,
        # ir_only == 0; 0 over-fire — every creature-hit deals to a creature,
        # every opp-hit to a player). Also REMOVED the dead unconditional
        # combat_damage→combat_damage_to_opp row from _PAYOFF_TRIGGER_KEYS (it
        # fired the opp lane on EVERY combat_damage trigger incl. creature-
        # recipients — an over-fire the regex never had; the mirror is now the
        # sole, recipient-correct producer). The double-strike-grant tail
        # (Raphael, Blade Historian, Berserkers' Onslaught) is a dedicated
        # LOW-confidence inline mirror so it never feeds has_other_plan (those
        # power-2 voltron bodies keep their tell). floor-mirror-dep == 0 (neither
        # reads _IR_FLOOR_LANES). NO-FLOOD: both deleted HIGH-confidence regex
        # producers silenced voltron — creature on 6 connect-with-creatures bodies
        # (Serpentine Basilisk, Toxin Sliver, Voracious Cobra, Creepy Doll,
        # Charging Tuskodon, Dripping Dead), opp on 1 more (Charging Tuskodon's
        # "would deal combat damage to a player … double" replacement, which the
        # combat_damage_matters regex misses, so opp is its only HIGH plan). Both
        # are re-supplied by the byte-identical _COMBAT_DAMAGE_CONNECT_PLAN_MIRROR
        # (the OR of the two deleted regexes). FILE-SWAP base-hybrid(188) vs
        # edits(190): drift_cards == 0, voltron 0 gained / 0 lost. CR 510.1c.
        "combat_damage_to_creature",
        "combat_damage_to_opp",
        # ADR-0027 β — damage_to_opp_matters (is_widen_of combat_damage_matters): the
        # GENERAL (any-source, ANY damage — NOT the literal "combat damage" the combat_*
        # keys require) "deals damage to a PLAYER / opponent" connect-payoff (Hypnotic
        # Specter, Curiosity, Goblin Lackey, Fungal Shambler). Boundary vs the already-
        # migrated combat_damage_to_opp (42f6d81): that lane is the LITERAL "deals
        # COMBAT damage to a player" recipient; this lane is the broader any-damage
        # connect-trigger (the regex's `deals (?:noncombat )?damage` never matches
        # "deals combat damage", so the two firing sets are DISJOINT by construction).
        # PROJECTION (SIDECAR v12→v13). phase keeps the player recipient on the
        # DamageDone trigger's valid_target ({type:Player} or {type:Typed,controller:
        # Opponent}) but _project_trigger reads only valid_card (the SOURCE — null on
        # all 69 such trigs) for the subject and _trigger_scope reads valid_target only
        # for its CONTROLLER, so a {type:Player,controller:null} recipient collapsed to
        # scope='any', subject=None — BYTE-IDENTICAL to a generic "deals damage to any
        # target" trigger (the 771-flood this lane was DEFERRED on: 733 player-typed
        # DamageDone trigs, 704 of them combat-only = combat_damage_to_opp). project's
        # _DAMAGE_TO_PLAYER_MARKER re-surfaces the recipient as a Filter predicate
        # ("DamageToPlayer") on the deals_damage trigger subject. combat-ONLY recipients
        # are EXCLUDED (event=='combat_damage', not 'deals_damage'). BEHAVIOR-NEUTRAL
        # until wired: two-sidecar global no-flood (v12 vs v13, same UNWIRED signals.py,
        # 30969 commander-legal): drift_cards == 0. parse_confidence unchanged (98.7%
        # full both sides: 34118/34562).
        # STRUCTURAL ARM (recall-GAINING). A deals_damage trigger carrying the
        # DamageToPlayer marker fires damage_to_opp_matters scope 'opponents'. The old
        # arm fired only on trig.scope=='opp' (Typed/Opponent recipients), MISSING every
        # {type:Player,controller:null} recipient (Hypnotic Specter, Goblin Lackey,
        # Abyssal Specter). +recall over the deleted word-order regex: structural
        # placement catches "deals 6 or more damage to an opponent" (Deus of Calamity),
        # "deal damage to a player" plural (Francisco, Dragonborn Champion, The Thing),
        # "deals damage to another player" (Night Dealings) — the regex's `deals damage
        # to (a player|...)` missed the count-qualifier / plural-verb / "another" forms.
        # BYTE-IDENTICAL KEPT MIRROR (_IR_KEPT_DETECTORS row reusing the pinned
        # DAMAGE_TO_OPP_MATTERS_REGEX). The structural arm only sees DamageDone
        # TRIGGERS; phase can't structure the trigger when it's QUOTED inside a
        # GrantAbility ("…gain 'whenever this creature deals damage to an opponent,
        # draw' " — Snake Umbra, Helm of the Ghastlord, Serpent Generator, Arm with
        # Aether, the Vraska / Sorcerer-Class grants) or when it's an ETB /
        # set-in-motion BURST ("when ~ enters, it deals
        # damage to each opponent" — Fanatic of Mogis, Meria's Outrider, Gruesome
        # Scourger, Sycorax) or another-event consequence (Magebane Lizard). The mirror
        # recovers all of those byte-identically (the `[^.]*?` arm never crosses a
        # sentence, so flat-over-kept_oracle == per-clause). add() dedups vs the arm.
        # GATES. Floor-disabled residual (commander-legal, _IR_FLOOR_LANES=frozenset(),
        # arm + mirror vs the deleted regex): regex_only == 0 (the byte-identical mirror
        # reproduces every regex firing), ir_only is pure recall gain (the structural
        # count-qualifier/plural/another-player triggers, all verified real vs Scryfall
        # oracle — Deus of Calamity, Dragonborn Champion, Francisco, Night Dealings). 0
        # over-fire: every regex hit names a player/opponent damage recipient. floor-
        # mirror-dep == 0 (NOT an _IR_FLOOR_LANE — it was a HAND_FLOOR regex). FILE-SWAP
        # NO-FLOOD (base 49a17a2 v12 vs edits v13, commander-legal): only damage_to_opp_
        # matters moves (+recall, 0 lost), combat_damage_to_opp UNCHANGED, voltron delta
        # 0. The deleted HAND_FLOOR producer fired HIGH-confidence (forced scope
        # 'opponents') and counted toward has_other_plan, so a byte-identical
        # _DAMAGE_TO_OPP_MATTERS_PLAN_MIRROR re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER. CR 119.3 / 903.10a.
        "damage_to_opp_matters",
        # ADR-0027 — combat_damage_matters (the BASE lane all the combat_* siblings
        # above are is_widen_of): a payoff for dealing COMBAT damage TO A PLAYER/OPP
        # ("whenever ~ deals combat damage to a player/an opponent/each opponent" —
        # Edric, Dragonlord Ojutai, Wrexial; or the passive "player who was dealt combat
        # damage by ~"). CR 510. BYTE-IDENTICAL KEPT MIRROR — NOT the structural arm.
        # phase structures the combat_damage trigger EVENT but drops the RECIPIENT TYPE
        # onto a lossy scope (project.py reads valid_target only for its controller —
        # same loss documented on the combat_* siblings above), so the unconditional
        # `add("combat_damage_matters", "opponents")` arm fired on EVERY combat_damage
        # AND deals_damage trigger regardless of recipient — a 3-way OVER-FIRE the
        # regex never had: (1) 131 NON-combat `deals_damage` bodies (Hypnotic Specter,
        # Curiosity, Chandra's Incinerator — these are damage_to_opp_matters /
        # noncombat_damage_payoff, NOT CR-510 combat damage); (2) 29 combat-damage-to-a-
        # CREATURE bodies (Serpentine Basilisk — that recipient is the already-migrated
        # combat_damage_to_creature); (3) "deals combat damage TO YOU" defensive
        # punishers (Witch-king, Teysa Envoy, Norn's Decree — the regex scoped to "to a
        # player/an opponent" excluded them). So the unconditional structural
        # `add(combat_damage_matters)` line is DELETED from extract_signals_ir (the
        # nested damage_to_opp_matters add on the SAME trigger event is kept), and the
        # lane rides a byte-identical _IR_KEPT_DETECTORS mirror of the EXACT deleted
        # _DETECTORS regex (anchored on "deals combat damage to a player/an opponent/…",
        # scope 'opponents', re.IGNORECASE over the reminder-stripped joined-face
        # kept_oracle). The deleted
        # regex's `[^.]*?` arm never crosses a sentence, so flat-over-kept_oracle ==
        # per-clause: the mirror reproduces the regex producer EXACTLY. Floor-disabled
        # residual (commander-legal, _IR_FLOOR_LANES=frozenset(), the byte-mirror vs the
        # deleted regex producer, by oracle_id): both==763, regex_only==0, ir_only==0 —
        # a perfectly clean byte-mirror. floor-mirror-dep == 0 (the mirror reads no
        # _IR_FLOOR_LANES; NOT a floor lane). The deleted _DETECTORS producer fired
        # HIGH-confidence (forced scope 'opponents') and counted toward has_other_plan,
        # so it is added to signals._VOLTRON_SILENCING_PLAN_KEYS — the byte-identical IR
        # re-supply re-silences the spurious commander-damage voltron tell on a connect-
        # payoff engine that is no vanilla beater (Edric, Dragonlord Ojutai). NO-FLOOD:
        # only combat_damage_matters moves, voltron 3010→3010, siblings 0. CR 510 /
        # 903.10a.
        "combat_damage_matters",
        # ADR-0027 β kept-mirror — legend_rule_off + timing_control: phase emits
        # NOTHING structural for either (legend_exempt covers only 2 of 8; the
        # cast-timing statics are dropped wholesale), so each rides a byte-identical
        # _IR_KEPT_DETECTORS mirror of the EXACT deleted regex. The mirror reproduces
        # the regex firing set byte-identically (commander-legal corpus: regex==mirror,
        # 0 lost, 0 over-fire — legend_rule_off 8==8, timing_control 5==5). floor-
        # mirror-dep == 0 (neither reads _IR_FLOOR_LANES). NO-FLOOD: voltron 0 leaked
        # on the FILE-SWAP even without a _VOLTRON_SILENCING_PLAN_KEYS entry (their
        # creature bodies already carry another plan), so neither is added there.
        # CR 704.5j / 117.1a.
        "legend_rule_off",
        "timing_control",
        # ADR-0027 β — power-as-damage cluster (creature_ping + damage_equal_power).
        # The projection unlock (d6620ac: op="power" recovery in project._quantity)
        # made the power-scaling damage effect a STRUCTURAL anchor: every power-as-
        # damage card now carries a cat=="damage" Effect with amount.op=="power".
        # Each key fires from a STRUCTURAL arm in extract_signals_ir PLUS a byte-
        # identical _IR_KEPT_DETECTORS mirror of its EXACT deleted SWEEP regex (the
        # mirror reproduces the regex firing set byte-identically over the commander-
        # legal corpus — regex_only == 0 for both — recovering the projection-gap tail
        # phase can't reach: emblem-quoted grants, dungeon-room rows, "Chapter 3" /
        # empty-raw effects, cards with no op="power" projected at all). The structural
        # arm adds genuine recall the narrow regexes missed (creature_ping +84,
        # damage_equal_power +17 — all verified vs Scryfall oracle text as real power-
        # as-damage cards). floor-mirror-dep == 0 for both (the structural arm + the
        # unconditional _IR_KEPT_DETECTORS mirror never read _IR_FLOOR_LANES).
        #
        # The empirical Effect.subject↔recipient mapping (verified on Fling / Soul's
        # Fire / Rabid Bite and 250 power-damage effect rows): the damage Effect's
        # subject IS the RECIPIENT — a Creature Filter for a creature recipient (Rabid
        # Bite: c=opp), None for "any target" / a player (Fling, Soul's Fire). The DOER
        # ("target creature you control deals …") is a SEPARATE target_only Effect with
        # a you-controller Creature subject. The structural split:
        #   creature_ping ← a creature is the doer of ITS OWN power: recipient is a
        #     creature (subject has 'Creature'), OR a self-ping ("to itself"), OR a
        #     creature-doer sibling target_only/fight, OR raw "<actor> deals damage
        #     equal to its power" (its OWN power, NOT a fling source's). Soul's Fire
        #     (your creature → any target) fires BOTH keys, matching the regex overlap.
        #   damage_equal_power ← the recipient reaches a PLAYER / any target (subject is
        #     a Player Filter, OR raw player-reach: "to any target", "to (target)
        #     player", "to each opponent", "to its controller", "to you", "any other
        #     target", "player or planeswalker"). Fling-style sac-to-power ("the
        #     sacrificed creature's power to any target") fires this, NOT creature_ping
        #     (the spell/sacrificed creature is the source, not a controlled-creature
        #     doer).
        # Each deleted SWEEP producer fired high-confidence scope 'you' and counted
        # toward has_other_plan, so a byte-identical PLAN_MIRROR re-supplies it (the
        # structural arms are broader than the regex, so _VOLTRON_SILENCING_PLAN_KEYS
        # would over-silence — a mirror restores only the old regex's silence set;
        # NO-FLOOD: voltron 0 leaked on the FILE-SWAP). The two SWEEP_DETECTORS rows are
        # deleted (SWEEP_LABELS kept); the serve specs survive via pinned regex
        # constants in signal_specs. CR 119.3 / 120.6.
        "creature_ping",
        "damage_equal_power",
        # ADR-0027 β — cost_reduction (a BUILD-AROUND reducer: an effect that makes a
        # CLASS of OTHER spells/abilities you cast cheaper — Goblin Electromancer, Ruby
        # Medallion, Helm of Awakening, Urza's Incubator; a SELF-discount "this spell
        # costs {X} less" is NOT in the lane, CR 601.2f/118.7). project.py's d45df65/
        # 6747de2 projection carries two cat=="cost_reduction" Effect forms: the static
        # ModifyCost{Reduce} (subject = the spell_filter, direction-correct + SelfRef-
        # gated) and the named `reducenextspellcost` effect (subject None), which is NOT
        # direction- or SelfRef-gated — phase mis-routes BOTH cost-INCREASE text and
        # "this spell costs ... less" self-discounts into it. The structural arm in
        # extract_signals_ir trusts a non-None subject and screens the named effects
        # (genuine "cost ... less", not a self-discount, not a cost-increase), firing
        # scope 'you'. A NARROWED _IR_KEPT_DETECTORS mirror (_COST_REDUCER_MIRROR — NOT
        # byte-identical, since the deleted regex over-fired) recovers the genuine
        # build-around reducers the projection drops (ability-cost reducers, the Defiler
        # conditional cycle, granted/donor reducers, named special-cost reducers, the
        # Chapter-3 / empty-raw tail). floor-mirror-dep == 0 (the arm + mirror never
        # read _IR_FLOOR_LANES).
        #
        # The deleted regex was DIRECTION-AGNOSTIC and SELF-BLIND. The floor-disabled
        # IR-vs-regex residual over the commander-legal corpus: regex_only == 92 = 100%
        # "this spell costs ... less" self-discount over-fire (SelfRef, rules-excluded —
        # correctly dropped, 0 genuine miss); ir_only == 7 genuine recall GAIN (ability-
        # cost + foretell/flashback special-cost reducers — Professor Hojo, Tezzeret,
        # Ghostfire Blade, Agatha, Cosmos Charger, Catalyst Stone, Momo). Net hybrid
        # firing 331 → 246 (≈85 self-discount over-fires removed, 7 recall gained).
        #
        # The deleted producer fired high-confidence scope 'you' and counted toward
        # has_other_plan; the IR arm+mirror are NARROWER than the deleted regex (it
        # caught the 92 self-discounts the lane drops), so re-supplying voltron silence
        # via _VOLTRON_SILENCING_PLAN_KEYS is SOUND only because every card the IR fires
        # also fired the regex (no NEW voltron silence is added — NO-FLOOD held: voltron
        # membership byte-identical, 0 gained / 0 lost on the FILE-SWAP). The two
        # cost_reduction regex producers (_HAND_FLOOR row + SWEEP_DETECTORS row) are
        # deleted; the serve survives via a pinned regex constant in signal_specs
        # (SWEEP_LABELS kept). CR 601.2f / 118.7.
        "cost_reduction",
        # ADR-0027 β — mana_amplifier (a mana DOUBLER: a permanent that, when you tap
        # something for mana, makes it produce MORE — Mirari's Wake, Crypt Ghast,
        # Vorinclex, Mana Reflection, Nyxbloom, Zendikar Resurgent, Doubling Cube —
        # plus the DORK-SUPPORT payoff "creatures with a mana ability" — Raggadragga).
        # The deleted regex had TWO arms (a doubler arm + a dork-support arm), and the
        # doublers were NOT structurally isolable: phase types most as a triggered
        # `ramp` Mana effect (shared with thousands of dorks/rocks), one as the
        # mana_filter passthrough (Mana Reflection — which ALSO conflates the any-color
        # SPEND permission — Celestial Dawn, Vizier — those are NOT amplifiers), and
        # Doubling Cube as `double`.
        #
        # PROJECTION + SPLIT (SIDECAR v16→v17). supplement._recover_static_pattern
        # carries a new _MANA_AMPLIFY rule (checked BEFORE _MANA_PRODUCE) that splits
        # the amount-MULTIPLIER doublers ("produces twice/three times as much" — Mana
        # Reflection, Virtue of Strength) OUT of the generic mana_filter passthrough
        # into a dedicated cat=="mana_amplifier" category (card_ir.CATEGORIES). The
        # color-CHANGE filters ("produces {C} instead" — Damping Sphere, Pale Moon,
        # Deep Water, Harvest Mage, Pulse of Llanowar, Quarum Trench Gnomes, Mirri)
        # and the any-color SPEND permission (_MANA_FILTER — Celestial Dawn, Vizier)
        # stay mana_filter, which NO lane reads — so the split is drift-FREE. Two-
        # sidecar global no-flood (v16 vs v17, SAME unwired signals.py, 30969
        # commander-legal): drift_cards == 0. parse_confidence unchanged (full 34118 /
        # partial 444 both sides — the clause still recovers, only its category moved).
        #
        # STRUCTURAL ARM (recall-GAINING). extract_signals_ir fires mana_amplifier on
        # (a) the new mana_amplifier category alone (Mana Reflection, Virtue), and (b)
        # a triggered `ramp` / `double` effect whose raw matches _MANA_AMPLIFY_RAW (the
        # AMOUNT-INCREASE discriminator — "add an additional/twice/that much/one mana
        # of any", "produces twice/three times", "double the amount of … mana"), read
        # ADDITIVELY: the doubler ALREADY fired ramp_matters in the same loop and KEEPS
        # firing it (the category is NOT moved out of `ramp` — that would drift
        # ramp_matters / group_mana / activated_ability / lifeloss_matters, which all
        # read `ramp`; instead only an EXTRA mana_amplifier signal is added). The DORK-
        # SUPPORT arm ("creatures with a mana ability" — Raggadragga) has NO structural
        # form (phase drops the "with a mana ability" subject), so it rides a byte-
        # identical _MANA_DORK_SUPPORT_MIRROR (the EXACT deleted _HAND_FLOOR regex).
        # floor-mirror-dep == 0 (mana_amplifier is NOT an _IR_FLOOR_LANE).
        #
        # Floor-disabled IR-vs-regex residual (commander-legal, _IR_FLOOR_LANES=
        # frozenset()): IR 17, regex 15, regex_only == 0 (clean superset — no recall
        # the regex caught is lost), ir_only == 2 genuine recall GAIN verified vs
        # Scryfall oracle (Doubling Cube "Double the amount of each type of unspent
        # mana"; Virtue of Strength "produces three times as much"). The any-color
        # cards Celestial Dawn / Vizier do NOT fire mana_amplifier. NO over-fire.
        #
        # VOLTRON. The deleted doubler _HAND_FLOOR producer fired high-confidence scope
        # 'you' and counted toward has_other_plan; a mana-doubler engine IS a plan, so
        # a byte-identical _MANA_AMPLIFIER_PLAN_MIRROR re-supplies the silence on the
        # regex side (the IR arm is BROADER by +2, so _VOLTRON_SILENCING_PLAN_KEYS
        # would over-silence the 2 ir_only bodies — Doubling Cube, Virtue; the mirror
        # keeps the silence set byte-identical to pre-migration). FILE-SWAP no-flood:
        # ONLY mana_amplifier moves; ramp_matters / group_mana / activated_ability /
        # lifeloss_matters / mana_filter-reading lanes drift 0; voltron delta 0. The
        # two _HAND_FLOOR doubler/dork producers are deleted; the serve spec in
        # signal_specs.py is a standalone _spec (never read a SWEEP regex), so no serve
        # re-home. CR 106.4 / 605 / 903.10a.
        "mana_amplifier",
        # ADR-0027 - ramp_matters (the ACCELERATION doer lane: a mana rock / dork /
        # ritual / "tap-a-land-add-more" engine / land-aura that produces mana to
        # accelerate into your payoffs - Sol Ring, Llanowar Elves, Crypt Ghast, Mirari's
        # Wake, Wild Growth, Magus of the Vineyard). The lane reads phase's `ramp` Mana
        # effect, the SAME category mana_amplifier / group_mana / activated_ability read
        # (NO sidecar bump - the projection already emits `ramp`).
        #
        # THE OVER-FIRE GATE (card_is_land). A naive `cat=='ramp'` arm fires on EVERY
        # land that taps for mana - but a basic Forest / dual / shock / triome is the
        # deck's MANA BASE, not ramp (acceleration). The deleted regex deliberately
        # excluded those: a basic's mana ability is REMINDER text "({T}: Add {G}.)",
        # stripped before matching, so the regex never fired on it. The IR arm is gated
        # `not card_is_land` to reproduce that exclusion (drops 106 reminder-formatted
        # mana-base lands - basics, Taiga/Underground Sea duals, Temple Garden/Steam
        # Vents shocks, Raugrin Triome, the bicycle/battle lands). The 1005 NONBASIC
        # lands the regex DID fire on (Orzhov Guildgate, Eldrazi Temple - a non-reminder
        # "{T}: Add {W} or {B}." on its own line) are KEPT byte-identically via the
        # _RAMP_MATTERS_REGEX mirror, so no land recall is lost.
        #
        # STRUCTURAL ARM + BYTE-IDENTICAL KEPT-MIRROR. extract_signals_ir fires
        # ramp_matters on (a) the structural `ramp` category for NON-LAND cards (the
        # recall-GAINING arm) and (b) a byte-identical _RAMP_MATTERS_REGEX mirror of the
        # deleted _HAND_FLOOR producer (the "{T}: add {" / "add N mana" / "add {WUBRGC}"
        # anchors) PLUS a _MANA_DORK_SUPPORT_RAMP_MIRROR of the deleted dork-support
        # producer ("creatures with a mana ability" - Raggadragga, Tazri, Katilda, which
        # phase drops the subject of). The mirror reproduces
        # the regex's 2003 firings EXACTLY (incl. the token-embedded "create a token
        # with '{T}: Add'" makers phase attributes to the TOKEN, not the maker); the
        # structural arm ADDS the 96 nonland ramp doers the brittle "add {" anchor
        # missed ("add an amount of {R} equal to..." - Karametra's Acolyte, Vhal; the
        # "whenever a player taps a land, add an additional" doublers - Wild Growth,
        # Caged Sun, Mana Flare; Magus of the Vineyard's "adds {G}{G}").
        #
        # Floor-disabled IR-vs-regex residual (commander-legal, _IR_FLOOR_LANES=
        # frozenset()): migrated 2099, regex 2003, regex_only == 0 (clean superset - no
        # regex firing lost, 0 land recall lost), ir_only == 96 genuine recall GAIN
        # verified vs Scryfall oracle (all 96 carry a real mana-production clause; 41
        # dorks, 28 land-auras, 15 rocks, 10 ritual spells, 2 DFC mana-lands). The 106
        # reminder-formatted mana-base lands do NOT fire (over-fire dropped). NO over-
        # fire added. floor-mirror-dep == 0 (ramp_matters is NOT an _IR_FLOOR_LANE).
        #
        # VOLTRON. The deleted _HAND_FLOOR producer fired high-confidence scope 'you'
        # and counted toward has_other_plan (a ramp engine is a plan, silencing the
        # spurious commander-damage voltron tell on a non-vanilla-beater). The migrated
        # IR arm is BROADER (+96 ir_only), so re-supplying via _VOLTRON_SILENCING_PLAN_
        # KEYS would OVER-silence those 96 bodies; instead a byte-identical
        # _RAMP_MATTERS_PLAN_MIRROR (the EXACT deleted regex, run on the joined-face
        # oracle) restores the old regex's silence set without over-silencing. FILE-SWAP
        # no-flood: ONLY ramp_matters moves (+96); mana_amplifier / group_mana drift 0;
        # voltron delta 0. The two _HAND_FLOOR producers are deleted; the serve spec in
        # signal_specs.py stays hand-registered. CR 106.4 / 605 / 903.10a.
        "ramp_matters",
        # ADR-0027 β — global_ability_grant (a card that grants a QUOTED activated /
        # triggered / static ability to YOUR whole creature board OR to an
        # ALL-permanents set: "Creatures you control have '{T}: …'" — Cryptolith Rite,
        # Phenax; "All artifacts have '…'" — Energy Flux, Kataki; "All creatures have
        # '…'" — The Tabernacle). The QUOTE is the tell — a bare keyword anthem
        # ("creatures you control have flying") is grant_keyword, a DIFFERENT lane, so
        # the IR cleanly separates them (no keyword-anthem flood). The v9 projection
        # emits a board_grant + counter_kind="grant_ability" marker from a
        # GrantAbility / GrantTrigger / GrantStaticAbility static over a creature board
        # (controller you, incl. subtyped/owned) or a bare all-permanents set
        # (controller any, no subtype/predicate); opponent-only and single-permanent
        # Aura/Equipment grants are excluded. extract_signals_ir reads the marker →
        # Signal("global_ability_grant","any",…) — scope "any" matches the deleted
        # SWEEP detector's firing identity (it hard-fired scope "any" for ALL matches).
        #
        # Floor-disabled IR-vs-regex residual over the commander-legal corpus:
        # regex_only == 6 = 100% over-fire (the regex matched the quote around a
        # KEYWORD — bands x5 + Ward x1: Cathedral of Serra / Mountain Stronghold /
        # Adventurers' Guildhouse / Unholy Citadel / Seafarer's Quay / Hexing
        # Squelcher — which is grant_keyword's lane, not a quoted activated/triggered/
        # static ability; 0 genuine miss). ir_only == 33 genuine recall GAIN the
        # brittle regex anchor missed: "Each creature you control has '…'" (Tazri,
        # Tyvar the Bellicose, Endless Whispers), "Creatures you control have <kw> and
        # '…'" (Inga, Tocasia), tribal/typed grants ("Elves you control have '…'" —
        # Joraga, Dionus; "Squirrels you control have '…'"), token grants ("Tokens you
        # control have '…'" — Jaheira, Insidious Roots), nested static-ability grants
        # ("…have 'Creature tokens you control get +2/+2'" — Inspiring Leader; "…have
        # 'The first Dragon spell … costs {2} less'" — Acolyte of Bahamut), and
        # "Permanents you control have '…'" (Cursed Wombat); the lone borderline
        # over-fire is Essence Leak (a conditional Aura whose Enchant relationship
        # phase folded into a condition, projecting a bare-Permanent affected).
        #
        # The deleted SWEEP producer fired high-confidence scope "any" and counted
        # toward has_other_plan (a quoted-ability granter is NOT a vanilla voltron
        # beater), so a byte-identical _GLOBAL_ABILITY_GRANT_PLAN_MIRROR (the OR of the
        # deleted regex over the joined-face oracle) re-supplies that voltron silence in
        # the regex path — NOT _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is
        # NARROWER on the 6 keyword over-fires (it would UNDER-silence the bands/Ward
        # bodies the IR drops). The SWEEP_DETECTORS row is deleted (SWEEP_LABELS kept);
        # the serve spec is hand-registered in signal_specs.py reusing the EXACT deleted
        # regex (pinned as GLOBAL_ABILITY_GRANT_REGEX). CR 113.3 / 604.3.
        "global_ability_grant",
        # ADR-0027 β — keyword_grant_target (formerly DEFERRED, needs-projection): a
        # SPELL/ability that grants a keyword to a SINGLE TARGET creature ("target
        # creature gains menace until end of turn" — Accelerate, Adamant Will, Run Amok;
        # the combat-trick / evasion enablers). phase collapsed the single-target grant
        # to grant_keyword(subject=None) with a TRUNCATED raw (affected==ParentTarget →
        # _filter is None), erasing the "target creature" anchor — INDISTINGUISHABLE
        # from a self-grant ("~ gains haste") and a subject-dropped team/anthem grant —
        # firing on subject=None FLOODED +2236. The BOUNDARY: this lane is the
        # SINGLE-TARGET grant, distinct from (a) TEAM grants over your whole creature
        # board (the grant_keyword team_evasion_grant / protection_grant / team_buff
        # lanes + global_ability_grant for QUOTED-ability board grants) and (b) the
        # aura/equipment suit-up grant (aura_equip_kw_grant — EnchantedBy/EquippedBy).
        #
        # PROJECTION (SIDECAR v13→v14). phase keeps the real target — a Typed creature —
        # on the GenericEffect's `target` (or an EARLIER effect's target for the "It
        # gains X" idiom: "Untap target creature. It gains reach" — Aim High) but
        # _project_static_mods reads only `affected` (==ParentTarget) for the
        # grant_keyword subject. project._single_target_keyword_grant_markers walks the
        # effect+sub_ability chain, tracks the resolved Typed-creature target, and emits
        # a dedicated `single_target_grant` Effect whose subject is that target Filter
        # PLUS a "SingleTarget" predicate (the predicate guards it out of EVERY team
        # /anthem grant_keyword gate, all of which require controller=="you" with
        # no/limited predicates). BEHAVIOR-NEUTRAL until wired: two-sidecar global
        # no-flood (v13 vs v14, same UNWIRED signals.py, 30969 commander-legal):
        # drift_cards == 0. parse_confidence unchanged (98.7% full both sides:
        # 34118/34562).
        # STRUCTURAL ARM. The single_target_grant marker fires keyword_grant_target
        # scope "you" (the deleted SWEEP detector's firing identity — it hard-fired
        # scope "you" for ALL matches). +recall over the deleted word-order regex: the
        # "It gains X" idiom (Aim High, Act of Treason) and PARAMETERIZED protection
        # /ward grants ("target creature gains protection from the color of your choice"
        # — Benevolent Bodyguard, Blessed Breath, Eldritch Immunity) the regex's
        # enumerated keyword list included but the word-order/pronoun anchor missed.
        # BYTE-IDENTICAL KEPT MIRROR (_IR_KEPT_DETECTORS row reusing the pinned
        # KEYWORD_GRANT_TARGET_REGEX). The structural arm only sees a grant phase
        # structured as a spell/ability GenericEffect static; phase can't structure the
        # grant when it's QUOTED inside a GrantAbility on an Aura/land/planeswalker
        # ("Enchanted land has '{T}: Target creature gains haste'" — Racecourse Fury,
        # Skygames, Footfall Crater; Rowan's Talent), a MODAL/choose grant ("• Target
        # creature gains flying" — Balloon Stand, Adaptive Sporesinger, Retreat to
        # Hagra, Ferocification, Appa), or a compound grant carrying a quoted ability
        # (Infuse with Vitality). The deleted regex is clause-local (no `[^.]` spans a
        # sentence), so the flat mirror over reminder-stripped kept_oracle reproduces
        # the per-clause regex firing set exactly. add() dedups vs the arm.
        # GATES. Floor-disabled residual (commander-legal, _IR_FLOOR_LANES=frozenset(),
        # arm + mirror vs the deleted regex): both == 532, ir_only == 488 (pure recall
        # gain, verified real vs Scryfall — the "It gains X" idiom; color/power-
        # qualified targets — Might Weaver "target red or white creature gains trample",
        # Mosstodon "power 5 or greater"; subtype-creature targets — Lowland Oaf "target
        # Goblin creature"; named-mechanic keyword grants the regex's evergreen list
        # omitted — Shadow Rift's shadow, Unseen Walker's forestwalk, Amoeboid
        # Changeling's all creature types; Backup's keyword-grant-to-the-counter-target
        # — Doomskar Warrior, Death-Greeter's Champion; protection/ward grants — Alseid,
        # Eldritch Immunity), regex_only == 0 (the kept mirror reproduces every regex
        # firing).
        # 0 over-fire: every marker carries the SingleTarget guard + a Creature target
        # (1006 marker cards, 0 missing-guard, 0 team-grant-only firing the lane — the
        # +2236 flood is structurally impossible). floor-mirror-dep == 0 (NOT an
        # _IR_FLOOR_LANE — it was a SWEEP detector, firing identical floor ON/OFF). The
        # SUBTYPE-ONLY single-target grant ("target Dinosaur gains haste" — Otepec) is
        # deliberately EXCLUDED (the regex never matched a tribal grant either — a
        # separate tribal care; the marker pass gates on the Creature card type — a
        # subtype-creature target like Lowland Oaf's "target Goblin creature" still has
        # the Creature card_type, so it stays IN). FILE-SWAP
        # NO-FLOOD (base 7582a15 v13 vs edits v14, commander-legal): ONLY kgt
        # moves (488 gained / 0 lost); global_ability_grant + the keyword anthem lanes
        # (team_evasion_grant / protection_grant / team_buff / all_creatures_kw_grant /
        # aura_equip_kw_grant) + keyword_soup + exert_matters UNCHANGED (0/0);
        # voltron_matters delta 0; the +2236 flood is AVOIDED.
        # The deleted SWEEP producer fired HIGH-confidence (scope "you") and counted
        # toward has_other_plan, so a byte-identical _KEYWORD_GRANT_TARGET_PLAN_MIRROR
        # re-supplies the voltron silence in the regex path — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (the "It gains X" /
        # protection ir_only gains) and would over-silence those bodies. The
        # SWEEP_DETECTORS row is deleted (SWEEP_LABELS kept); the serve spec is hand-
        # registered in signal_specs.py reusing the EXACT deleted regex (pinned as
        # KEYWORD_GRANT_TARGET_REGEX). CR 700.2 / 903.10a (voltron).
        "keyword_grant_target",
        # ADR-0027 β — activated_ability (formerly a bare-cost-shape _DETECTORS
        # regex): a card whose ENGINE is a MEANINGFUL activated ability — the
        # {T}:/{Q}: or generic-mana-cost ability ({2}{U}{B}: …, {8}:, {X}: …) a
        # tap-engine commander deck supports with cost reducers (Training Grounds),
        # untappers + haste-for-abilities (Thousand-Year Elixir), and ability
        # copiers (Rings of Brighthearth). The deleted _DETECTORS regex
        # (`\{t\}…|\{q\}…|\{(?:\d+|x)\}…:`) fired on the COST SHAPE alone,
        # which FLOODED on EVERY land/rock/dork's "{T}: Add {mana}" mana ability —
        # Forest, Sol Ring, Llanowar Elves, Birds, Gilded Lotus, Arcane Signet all
        # matched `{t}:` (6474 commander-legal regex firings, ~half the mana flood).
        # The lane wants MEANINGFUL activated-ability engines, NOT mana abilities.
        #
        # TWO STRUCTURAL DISCRIMINATORS (no recall loss):
        #   1. is_mana_ability — phase's Mana effect projects to Effect.category
        #      'ramp', so a mana ability has ONLY ramp/attach effects; the arm
        #      gates on >=1 NON-ramp, NON-attach effect, dropping the mana flood
        #      (and equip — an Attach the cost-shape regex never matched, no `:`
        #      after "Equip {2}"). CR 605.1a.
        #   2. genericmana (SIDECAR v14→v15) — _cost_string previously collapsed
        #      every mana cost to one coarse 'mana' token, erasing the
        #      generic-vs-colored distinction the regex's generic branch
        #      ({(?:\d+|x)\}) relied on. v15 adds a 'genericmana' token (additive
        #      — every 'mana'-substring check is unaffected; two-sidecar drift==0)
        #      iff the cost carries a GENERIC numeral / {0} / {X}; the arm's mana
        #      branch fires only on it, never on colored-/hybrid-/snow-ONLY
        #      firebreathing ({R}: +1/+0, {G/W}:, {S}:), which the regex excluded
        #      (firebreathing has its own pump lane). An additional
        #      sac/discard/exile cost on the mana branch is excluded (the regex's
        #      18-char window dropped those one-shots — "{3}{B}, Sacrifice this:
        #      …"); a 'tap'/'untap' anchor overrides (the regex's {T}:/{Q}: branch
        #      fired regardless of an extra cost). CR 602.1a.
        # Lands are excluded (card_is_land) — the lane is the creature/permanent
        # engine the support package suits up, not a manland's animate ability.
        #
        # STRUCTURAL ARM (extract_signals_ir), scope "you" — the deleted _DETECTORS
        # row hard-forced scope "you" for ALL matches (its firing identity). NO
        # sidecar marker category: the arm reads the EXISTING projected Ability
        # (kind=='activated', cost tap/untap/genericmana, effect categories) — the
        # v15 change is only the additive genericmana cost token. NO kept mirror: a
        # byte-identical mirror re-floods on dorks (their "{T}: Add" is OUTSIDE
        # parens, so reminder-stripping doesn't remove it), and a narrowed
        # quoted-grant mirror leaks granted-mana via the comma-form ("{T},
        # Sacrifice: Add mana") while adding 0 to ir_only — the quoted-board-grant
        # tail (Magma Sliver, Sliver lords, Ghired) is the sibling
        # global_ability_grant lane's concern (most already fire it), so the arm's
        # "card's OWN engine ability" boundary legitimately leaves them there.
        #
        # GATES. Floor-disabled residual (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), arm vs deleted regex): both==4024,
        # ir_only==43 (pure recall gain, verified real vs Scryfall — the Moonfolk
        # land-bounce cycle Meloku/Soratami/Oboro/Uyo; the Eldrazi processors Oracle
        # of Dust/Void Attendant; tap-untapped-creatures value Sigil
        # Tracer/Volrath's Gardens/Symbiotic Deployment; Tenth District Hero,
        # Rootha, Zareth San — all generic-mana engines past the 18-char window),
        # 0 over-fire (no ir_only card lacks a real meaningful activated ability).
        # regex_only==2450 is 100% over-fire/out-of-lane: reminder-text token-makers
        # (642), lands incl. manlands (1043), and the mana/colored/sac-for-mana
        # flood (756 — the regex fired on the MANA ability `{T}: Add`, e.g.
        # keyrunes/Devoted Druid/Heart Warden) + the tribal/land QUOTED-board-grant
        # tail (9, the sibling global_ability_grant lane's concern). FLOOD
        # SPOT-CHECK: Forest / Island / Swamp / Mountain / Plains / Sol Ring /
        # Llanowar Elves / Birds of Paradise / Arcane Signet / Gilded Lotus / Mana
        # Vault all fire NEITHER the arm NOR a mirror — the flood is structurally
        # impossible. floor-mirror-dep == 0 (NOT an _IR_FLOOR_LANE — it was a
        # _DETECTORS row, firing identical floor ON/OFF). parse_confidence unchanged
        # (98.7% full both sides, 34118/34562).
        # The deleted _DETECTORS producer fired HIGH-confidence scope "you" feeding
        # has_other_plan, so a byte-identical _ACTIVATED_ABILITY_PLAN_MIRROR (over
        # the reminder-STRIPPED text) re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is both broader (the recall
        # gains) and narrower (the dropped flood). FILE-SWAP NO-FLOOD (base ff4cc29
        # v14 vs edits v15, commander-legal): ONLY activated_ability moves;
        # voltron_matters delta 0. The _DETECTORS row is deleted; the EXACT regex is
        # pinned as ACTIVATED_ABILITY_REGEX (_sweep_detectors) for the PLAN mirror;
        # the serve spec stays its OWN hand-registered curated search pool
        # (signal_specs), independent of this regex (like gain_control).
        # CR 602.1a / 605.1a / 903.10a (voltron).
        "activated_ability",
        # ADR-0027 β — debuff_matters (a -1/-1 / toughness-shrink removal-and-payoff
        # lane). The v9 projection carries the debuff structure directly: a -N/-N giver
        # is a `pump` Effect with amount.factor < 0 (Dead Weight / Weakness → factor=-2;
        # the NEGATIVE factor IS the signal), and a -1/-1-counter giver is a
        # `place_counter` Effect with counter_kind=="m1m1". The structural arm in
        # extract_signals_ir fires scope "any" on a pump factor<0 OR a non-self m1m1
        # placement — gating OUT the 62-card self-enter-with drawback tail (persist/
        # undying riders + "~ enters with N -1/-1 counters", which project scope=="you")
        # and a mixed-sign combat trick (Nameless Inversion's +3/-3 projects factor=+3,
        # the POWER side, so factor<0 leaves it out — it's a trick, not a pure debuff).
        #
        # The structural arm is recall GAIN (+94 ir_only, all Scryfall-verified: static
        # auras "Enchanted creature gets -2/-2", self-shrinkers "This creature gets
        # -1/-1 for each card in your hand", and put-N-counters-on-target the narrow
        # regex missed), but the big "gets -N/-N until end of turn" / "-X/-X" tail
        # projects as a pump / pump_target Effect with amount==None (the value lives
        # only in the raw), so there is NO structural number to read. That tail is
        # recovered by a byte-identical _IR_KEPT_DETECTORS mirror of BOTH deleted
        # regexes (the SWEEP scope-"any" pattern + the Maha opponent-shrink scope-"you"
        # _DETECTORS row): as a full-text .search over the reminder-stripped joined-face
        # oracle the mirror fires on the IDENTICAL 613-card commander-legal set the
        # deleted per-clause regex path did (0 drift both directions → regex_only == 0
        # after the mirror).
        #
        # Both deleted producers fired high-confidence and counted toward has_other_plan
        # (a -1/-1 / shrink body is NOT a vanilla voltron beater), so a byte-identical
        # _DEBUFF_MATTERS_PLAN_MIRROR (the OR of the two deleted regexes over the
        # reminder-stripped joined-face oracle) re-supplies that voltron silence in the
        # regex path — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (+94 ir_only) and
        # would OVER-silence those recall-gain bodies. SWEEP_DETECTORS row deleted
        # (SWEEP_LABELS kept); the serve is hand-registered in signal_specs.py reusing
        # the EXACT deleted regex (pinned as DEBUFF_SWEEP_REGEX). CR 122.1b / CR 613.
        "debuff_matters",
        # ADR-0027 β — variable_pt (a */* characteristic-defining P/T creature whose
        # power and/or toughness is "equal to <something>": Nightmare = */* equal to
        # Swamps; Pack Rat; Serra Avatar = */* equal to your life; Cultivator Colossus;
        # Tarmogoyf; Lhurgoyf). The IR arm in extract_signals_ir reads a
        # `characteristic_pt` Effect (scope 'any', matching the sweep). phase carries
        # the clause two ways: an oracle-text CDA it left as `other` (Tarmogoyf —
        # supplement._CDA_PT promotes it) AND a fully-structured SetDynamicPower/
        # Toughness self-CDA static it then DROPPED (Nightmare — the base_pt_set arm
        # excludes the characteristic_defining flag + SelfRef). The PROJECTION fix
        # (SIDECAR v10) re-surfaces the dropped static as a `characteristic_pt` marker
        # via project._self_cda_marker, structured through supplement's _CDA_PT (the
        # gamma structuring layer); +168 characteristic_pt cards over the corpus. Plus
        # a NARROWED kept
        # mirror (_VARIABLE_PT_MIRROR in _signals_ir) for the */* tail phase can't
        # structure as a self-CDA — the TOKEN-borne */* ("This token's power and
        # toughness are each equal to" — Seize the Storm, Ajani Goldmane's Avatar) and
        # the triggered "change <Name>'s base power and toughness" self-set (Halfdane,
        # Eldrazi Mimic, Shape Stealer).
        #
        # Floor-disabled residual vs the deleted SWEEP regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 222, ir_only == 22 (broader-and-correct
        # recall — Tymaret/Daxos/Renata "toughness is equal to your devotion", An-Havva
        # Constable "toughness is equal to 1 plus …", Nighthawk Scavenger — true */*
        # CDAs the regex's narrow "number of" phrasing missed), regex_only == 26 — ALL
        # over-fire: the deleted regex's "equal to … number of cards in … hand|library"
        # arm caught draw/damage/destroy effects that scale with hand size but have NO
        # */* body (Spiraling Embers, Enter the Infinite, Sword of War and Peace, Castle
        # Locthwain, The Royal Scions), and its "change … base power and toughness OF
        # all/each/other … creatures" arm caught mass-debuffs (Brine Hag, Exuberant
        # Wolfbear). Both are correctly DROPPED (the mirror vetoes them). The lone
        # near-miss is Tarmogoyf Nest (the token CDA lives in REMINDER text the IR
        # strips) — its synergy rides the Tarmogoyf TOKEN card, which carries the real
        # characteristic_pt itself. SWEEP_DETECTORS row deleted (SWEEP_LABELS kept);
        # the serve is hand-registered in signal_specs.py reusing the EXACT deleted
        # regex (pinned as VARIABLE_PT_SWEEP_REGEX). A */* CDA is not a voltron plan,
        # so NOT in _VOLTRON_SILENCING_PLAN_KEYS (voltron delta 0). floor-mirror-dep
        # == 0 (variable_pt is not an _IR_FLOOR_LANE). CR 604.3.
        "variable_pt",
        # ADR-0027 β — token_copy_matters (a card that makes TOKEN COPIES / populates:
        # "create a token that's a copy of …" — Helm of the Host, Rite of Replication;
        # populate — Trostani, Ghired; token DOUBLERS — Doubling Season, Adrix and Nev,
        # Mondrak, Parallel Lives, Primal Vigor; the modal/Unimplemented copy spells —
        # Mirror March, Esix, Fractured Identity). MIGRATED VIA A KEPT-MIRROR (signals-
        # only, NO sidecar bump), NOT a structural CopyTokenOf/Populate arm.
        #
        # DISCRIMINATOR FOUND (structured, but UNUSABLE): phase DOES carry a structured
        # copy/populate signal the projection drops — `CopyTokenOf` (394 cards) and
        # `Populate` (27) effect types both collapse to a plain `make_token` Effect in
        # project._copy_token_effect / _EFFECT_CATEGORY['populate'], indistinguishable
        # from a vanilla token maker. A structural arm reading those was REJECTED: the
        # structural set is 421 cards vs the deleted reminder-STRIPPED regex's 375, and
        # the 80-card struct_only delta is 100% OVER-FIRE — every one is a reminder-text
        # SELF-copy the regex deliberately excludes by running reminder-stripped:
        # Embalm/Eternalize (41 — "(…Create a token that's a copy of it…)" in the
        # keyword's reminder, a graveyard self-recursion, NOT a copy payoff), Offspring
        # (~25 — "(…create a 1/1 token copy of it.)"), and Double-team (~14 — phase
        # MIS-structures "conjure a duplicate into your hand" as CopyTokenOf, not even a
        # token at all). None is a genuine token-copy payoff. So the structural marker
        # would 100%-over-fire the lane.
        #
        # CHOSEN PATH 2 (kept-mirror). The lane fires from a NARROWED
        # _IR_KEPT_DETECTORS-style mirror — _TOKEN_COPY_MATTERS_MIRROR in _signals_ir —
        # that runs the EXACT deleted _HAND_FLOOR regex over the reminder-STRIPPED
        # kept_oracle, byte-identical to the deleted floor Detector. No structural arm
        # is wired (cat=='make_token' is the vanilla-token lane; reading CopyTokenOf
        # would over-fire as above). The serve spec stays hand-registered in
        # signal_specs.py reusing the EXACT regex (pinned as TOKEN_COPY_MATTERS_REGEX).
        #
        # Floor-disabled residual vs the deleted _HAND_FLOOR regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 306, ir_only == 0, regex_only == 0 — the
        # mirror is byte-identical to the deleted regex over the same reminder-stripped
        # input, so the served set is UNCHANGED (a true behavior-neutral re-home, no
        # recall gain, no over-fire). floor-mirror-dep == 0 (token_copy_matters is NOT
        # an _IR_FLOOR_LANE). The deleted producer fired HIGH-confidence (forced scope
        # 'you') and counted toward has_other_plan (a token-copy ENGINE is a real plan,
        # not a vanilla voltron beater), so a byte-identical _TOKEN_COPY_MATTERS_PLAN_
        # MIRROR in _signals_regex re-supplies that voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, matching the variable_pt/cost_reduction byte-
        # identical-mirror pattern (restores has_other_plan for ALL cards regardless of
        # IR/regex mode). CR 702.95 (populate) / 707 (copies).
        "token_copy_matters",
        # ADR-0027 — tokens_matter (the GO-WIDE token lane: a payoff/reference that
        # CARES about tokens — token DOUBLERS (Doubling Season, Parallel Lives,
        # Mondrak, Divine Visitation), "tokens you control" anthems/refs (Intangible
        # Virtue, Mirror Box, Brudiclad), token-enters triggers (Woodland Champion,
        # Junk Winder), and the GO-WIDE creature-count-scaler whose own/granted P/T
        # scales with the board (Adeline, Leonardo, Bravado, Might of the Masses).
        # DISTINCT from token_maker (the subject-bearing MAKER lane, NOT migrated) and
        # token_copy_matters (the token-COPY/populate lane, migrated). MIGRATED VIA A
        # KEPT-MIRROR (signals-only, NO sidecar bump), NOT a structural arm.
        #
        # WHY KEPT-MIRROR, NOT STRUCTURAL: phase carries NO structural shape for the
        # "tokens you control" / "for each creature you control" payoffs — they survive
        # only in raw oracle text, never as an Effect/Trigger/predicate the projection
        # exposes. A structural-only migration would LOSE 161 commander-legal cards
        # (regex_only == 161, ir_only == 0 over the floor-disabled corpus) — a massive
        # recall loss, the polar opposite of a 100%-over-fire. So the clean
        # signals-only path is a byte-identical kept-mirror of the deleted regex ("no
        # dismissal without the hook": each of the 161 is a genuine token/go-wide
        # payoff with a detectable oracle hook the regex already matched).
        #
        # CHOSEN PATH 2 (kept-mirror). The lane fires from _TOKENS_MATTER_MIRROR in
        # _signals_ir — the UNION of the two EXACT deleted _HAND_FLOOR regexes (the
        # go-wide count-scaler + the broad token payoff, pinned as TOKENS_MATTER_REGEX)
        # over the reminder-STRIPPED kept_oracle, byte-identical to the deleted floor
        # Detectors. PLUS the existing structural amass / fabricate effect-category arm
        # (extract_signals_ir's cat=='amass'/'fabricate' fan-out) already fires
        # tokens_matter for those keyword cards; the regex amass / mobilize entries
        # MOVED from _DIRECT_KEYWORD_SIGNALS to _IR_KEYWORD_MAP (the IR-only keyword
        # path), so mobilize-keyword bodies whose token-making lives in stripped
        # reminder text keep firing from the keyword array (the saddle-style move).
        # The serve spec stays hand-registered in signal_specs.py (its curated search
        # regex was always independent of the producers).
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): the structural IR path (amass/fabricate only)
        # gives both == 69, ir_only == 0, regex_only == 161 — the 161 regex-only cards
        # are exactly the broad-payoff bodies phase can't structure. The mirror OR the
        # IR-structural arm reproduces the full regex firing EXACTLY: regex == hybrid
        # == 230, 0 miss, 0 over-fire (a true behavior-neutral re-home). floor-mirror-
        # dep == 0 (tokens_matter is NOT an _IR_FLOOR_LANE). The three deleted
        # producers (2 _HAND_FLOOR + the amass/mobilize keyword map) fired HIGH-
        # confidence (forced scope 'you') and counted toward has_other_plan (a go-wide
        # token ENGINE is a real plan, not a vanilla voltron beater), so the voltron
        # silence is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — NOT a
        # byte-identical oracle PLAN mirror, which would go blind on the 3 vanilla
        # mobilize-KEYWORD bodies (token-making in stripped reminder text). The IR
        # re-supply is byte-identical (230 == 230), so no over-silence. CR 111.1 /
        # 701.47 (amass) / 702.123 (fabricate).
        "tokens_matter",
        # ADR-0027 — island_matters (the islandwalk / island-attack-restriction lane:
        # islandwalk BEARERS — Thada Adel, Wrexial; islandwalk GRANTERS / token-makers /
        # references — Lord of Atlantis & Master of the Pearl Trident (Merfolk anthem),
        # Fishliver Oil (Aura grant), Chasm Skulker / Coral Barrier / The Sea Devils
        # (make islandwalk tokens), Shore Snapper / Deeptread Merrow / Piracy Charm /
        # War Barge / Part Water / Sandals of Abdallah / Streambed Aquitects (grant
        # islandwalk), Island Sanctuary (cares about islandwalk), Mystic Decree / Gosta
        # Dirk / Undertow (neutralize islandwalk), Merfolk Assassin (destroys islandwalk
        # creatures); plus the Zhou Yu "can't attack unless defending player controls an
        # Island" attack restriction). MIGRATED VIA A BYTE-IDENTICAL KEPT-MIRROR
        # (signals-only, NO sidecar bump), NOT the Scryfall `islandwalk` keyword-array
        # path.
        #
        # WHY KEPT-MIRROR, NOT THE KEYWORD ARM: the IR keyword route
        # (_IR_KEYWORD_MAP['islandwalk'], a card['keywords'] lookup) covers only the
        # islandwalk BEARERS (the keyword the card itself HAS). It MISSES every
        # islandwalk GRANTER / token-maker / reference — Scryfall's keyword array lists
        # conferred keywords nowhere (the conferred-keyword gap), so Lord of Atlantis
        # ("Other Merfolk … have islandwalk"), Fishliver Oil, Chasm Skulker's tokens,
        # and the neutralizers / destroyers all carry keywords=[]. The deleted regex
        # `\bislandwalk\b` over the oracle catches all of them; the keyword route can't.
        # So the keyword entry is REMOVED (it is a strict subset — every
        # islandwalk-keyword bearer also has the bare word in its reminder-stripped
        # oracle, verified 0 keyword-only cards) and the lane fires from a
        # byte-identical kept mirror of the EXACT deleted producer.
        #
        # CHOSEN PATH (kept-mirror). The lane fires from _ISLAND_MATTERS_MIRROR in
        # _signals_ir (pinned as ISLAND_MATTERS_REGEX in _sweep_detectors): the EXACT
        # deleted _HAND_FLOOR regex (`\bislandwalk\b` OR the Zhou Yu attack restriction)
        # run FLAT over the reminder-STRIPPED kept_oracle. The regex has NO `[^.]*`
        # span, so it cannot cross a clause boundary → flat == per-clause (verified: 0
        # mismatches over the commander-legal corpus). The serve spec stays
        # hand-registered in signal_specs.py (its curated "lands become Islands" search
        # regex was always independent of this producer).
        #
        # Floor-disabled residual vs the deleted _HAND_FLOOR regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), by oracle_id): both == 79, ir_only == 0,
        # regex_only == 0 — the mirror is byte-identical to the deleted regex over the
        # same reminder-stripped input, so the served set is UNCHANGED (a true behavior-
        # neutral re-home, no recall gain, no over-fire). floor-mirror-dep -> 0
        # (island_matters REMOVED from _IR_FLOOR_LANES). The deleted producer fired
        # HIGH-confidence (forced scope 'you') and counted toward has_other_plan (24
        # commander-legal island creatures — Sea Serpent, Marjhan, Zhou Yu, Island Fish
        # Jasconius … — carry island_matters as their SOLE high-confidence plan, so the
        # floor silenced the spurious commander-damage voltron membership tell). The IR
        # re-supply is byte-identical (79 == 79), so the voltron silence is re-supplied
        # via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — the tokens_matter / t2b4-t2b5
        # kept-mirror precedent (byte-identical → no over-silence, voltron 3010 ->
        # 3010). CR 702.14c (islandwalk = "can't be blocked as long as the defending
        # player controls at least one land with the specified land type") / 702.14b
        # (landwalk is an evasion ability) / 903.10a (commander damage).
        "island_matters",
        # ADR-0027 β — creature_etb (the ETB-VALUE lane: a payoff that triggers
        # "whenever a creature you control enters" — Cathars' Crusade, Impact Tremors,
        # Soul Warden; the ETB-trigger DOUBLERS — Panharmonicon, Yarok, Elesh Norn,
        # Naban; the delayed ETB payoff — Ephara, Saddled Rimestag; plus the
        # 'opponents' PUNISHER scope — "a creature an opponent controls enters" —
        # Lictor, Theoretical Duplication). MIGRATED VIA A BYTE-IDENTICAL KEPT-MIRROR
        # (signals-only, NO sidecar bump), NOT the pre-existing structural etb-trigger
        # arm.
        #
        # STRUCTURAL ARM EXISTS but is a NON-byte-identical MIX (so NEUTRALIZED). The IR
        # arm (an `etb` trigger w/ a Creature subject, scoped by the trigger-subject
        # controller) fires 344 commander-legal vs the deleted regex's 367: it GAINS 39
        # Graft/Soulbond bodies ("Whenever another creature enters" from the Graft
        # reminder / Soulbond "when either enters") — genuine ETB triggers — but MISSES
        # 62 the regex caught. The recall gap is GENUINE, not over-fire: 8 ETB-trigger
        # DOUBLERS (Panharmonicon, Yarok, Elesh Norn, Ancient Greenwarden, Naban,
        # Starfield Vocalist — phase models "entering … triggers an additional time" as
        # a static REPLACEMENT effect, no `etb` event), 4 delayed payoffs (Ephara,
        # Saddled Rimestag, Zhalfirin Decoy, Bellowing Elk — phase models "if you had a
        # creature enter … this/last turn" as an upkeep/static trigger, no `etb` event),
        # 3 opp-punishers (Lictor, Theoretical Duplication, Crafty Cutpurse), plus the
        # broad "whenever a creature you control enters → reward" tail (First Day of
        # Class, Kindred Discovery, Thunder of Unity, the Huatli/Kiora/Mila emblems).
        # Because the structural set is a MIX (recall gain on one axis, recall gap on
        # another), a structural migration is NOT behavior-neutral — it would re-home
        # creature_etb with a ±non-zero drift, NOT a clean re-home.
        #
        # CHOSEN PATH 2 (byte-identical kept-mirror). The structural etb-trigger arm is
        # NEUTRALIZED; the lane fires from _creature_etb_clauses in _signals_regex (the
        # EXACT per-clause logic of the two deleted _DETECTORS rows) invoked in the
        # extract_signals_ir kept-detector pass over the reminder-STRIPPED kept_oracle.
        # Both scopes emit. The serve specs (both ("creature_etb","you") and
        # ("creature_etb","opponents")) were always hand-registered in signal_specs.py,
        # independent of the deleted producer (creature_etb is intentionally EXCLUDED
        # from SWEEP_DETECTORS), so they survive unchanged.
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 367 (key,scope), ir_only == 0,
        # regex_only == 0 — the mirror is byte-identical to the deleted regex over the
        # same reminder-stripped per-clause input, so the served set is UNCHANGED (a
        # true behavior-neutral re-home, no recall gain, no over-fire). floor-mirror-dep
        # == 0 (creature_etb is NOT an _IR_FLOOR_LANE). Both deleted producers fired
        # HIGH-confidence (scope 'you'/'opponents') and counted toward has_other_plan
        # (an ETB-value/doubler/punisher engine is a real plan, not a vanilla beater),
        # so _creature_etb_has_plan in _signals_regex re-supplies that voltron silence —
        # NOT _VOLTRON_SILENCING_PLAN_KEYS, matching the token_copy_matters/variable_pt
        # byte-identical-mirror pattern (restores has_other_plan for ALL cards
        # regardless of IR/regex mode). CR 603.6.
        "creature_etb",
        # ADR-0027 — attack_matters (the COMBAT-trigger / attacked-this-turn payoff
        # axis: a card that CARES when a creature attacks — "whenever ~ attacks"
        # triggers (Hellrider, Adeline), the Raid / "attacked this turn" combat-count
        # condition (Relentless Assault, Bloodsoaked Champion), the "attacking causes"
        # Isshin form, and the team combat-keyword anthems). MIGRATED VIA A STRUCTURAL
        # ARM + A BYTE- IDENTICAL KEPT-MIRROR (signals-only, NO sidecar bump).
        #
        # STRUCTURAL ARM (recall GAIN). phase DOES carry the `attacks` TRIGGER event
        # (_PAYOFF_TRIGGER_KEYS → attack_matters) and the `Attacking` filter PREDICATE
        # (the e.subject / amount.subject Attacking read), and the structural arm fires
        # them. That arm ADDS +135 ir_only recall the bare substring regex MISSED: the
        # reminder-only attack triggers (Training / Mentor / Exalted / Mobilize
        # creatures, whose "whenever ~ attacks" lives ONLY in the stripped reminder text
        # — Noble Hierarch, Tajic, Voice of Victory) and the "Attacking creatures you
        # control get …" anthems (Gruul War Chant, Goblin Oriflamme, Nobilis of War) —
        # all genuine attack payoffs. So this is NOT a structural-only NOR a mirror-only
        # migration.
        #
        # WHY THE MIRROR (recall the structural arm cannot reach). phase carries NO
        # clean `attacks` shape for the DOMINANT family: the DISJUNCTIVE "enters or
        # attacks" / "attacks or blocks" trigger collapses to event='other' (Elder
        # Gargaroth, Sun Titan, Grave Titan, Frost Titan, Doran), the Raid "if you
        # attacked this turn" is a CONDITION with no trigger (Searslicer Goblin,
        # Bloodsoaked Champion), the `AttackedThisTurn` shows only on an EFFECT
        # predicate the lane doesn't read as a payoff ("untap all creatures that
        # attacked this turn" — Relentless Assault, World at War), and "attacking
        # causes" (Isshin) is a static. A structural-only migration would LOSE 394
        # genuine cards, so the lane ALSO rides _ATTACK_MATTERS_MIRROR in _signals_ir —
        # the EXACT deleted _DETECTORS lambda (the two regex-expressible branches pinned
        # as ATTACK_MATTERS_REGEX in _sweep_detectors: "attacking causes" / "attacked
        # this turn", PLUS the "whenever"&"attack" SUBSTRING-AND checked inline, which
        # no single regex expresses) run PER-CLAUSE over the reminder-stripped
        # kept_oracle, add()-deduped with the structural arm.
        #
        # The 10 combat KEYWORDS the deleted _DIRECT_KEYWORD_SIGNALS rows mapped (battle
        # cry / battalion / melee / boast / exert / myriad / bushido / annihilator /
        # flanking / frenzy) MOVED to the IR-only _IR_KEYWORD_MAP (the saddle/lifelink-
        # style move): their attack condition lives in stripped reminder text, so
        # neither the mirror nor the structural arm fires for a vanilla-keyword body —
        # the keyword array is the only structured anchor. boast / myriad keep their OWN
        # lanes (boast_matters / myriad_grant) too — attack_matters is merged in, not
        # replaced. The deleted _DETECTORS producer + the 10 keyword rows are gone; the
        # serve spec stays hand-registered in signal_specs.py (its curated search regex
        # was always independent of the producer).
        #
        # Floor-disabled residual vs the deleted producers (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): the STRUCTURAL-ONLY arm vs the deleted regex was
        # both==1598, ir_only==135, regex_only==394 — the 394 regex_only are ALL genuine
        # (the disjunctive-trigger / Raid-condition / attacked-this-turn family phase
        # has no shape for), so the mirror recovers them. Post-migration IR (structural
        # + mirror + 10 keywords) ⊇ original-regex over the corpus: 0 lost, +135 gained.
        # floor- mirror-dep == 0 (attack_matters is NOT an _IR_FLOOR_LANE — floor-ON ==
        # floor-OFF).
        #
        # VOLTRON: NOT a plan that silences the commander-damage tell — an ATTACKER is
        # the commander-damage plan, so attack_matters never fed has_other_plan in a
        # silencing role and is NOT in _VOLTRON_SILENCING_PLAN_KEYS (no
        # _ATTACK_MATTERS_PLAN_MIRROR; voltron delta 0, verified over the full
        # commander-legal corpus). The class-tribe go-wide GATE (which read regex
        # attack_matters) keeps parity via the _attack_go_wide oracle mirror in
        # _signals_regex (the IR gate sees the real signal). CR 508 (declare attackers)
        # / 702.10 (battle cry et al.).
        "attack_matters",
        # ADR-0027 β — entered_attacker (the freshly-entered-attacker payoff: a
        # creature that ENTERED this turn paired with attacks / deals combat damage —
        # Samut "if that creature entered this turn, draw a card" on combat damage;
        # Redoubled Stormsinger forks creature TOKENS that entered this turn on attack;
        # Hixus rewards ITSELF having entered this turn when it blocks). Only ~3
        # commander-legal cards. MIGRATED VIA A BYTE-IDENTICAL KEPT-MIRROR (signals-
        # only, NO sidecar bump), NOT a structural arm.
        #
        # NO STRUCTURAL FORM: phase does NOT project the "entered (the battlefield)
        # this turn" temporal predicate — it survives only in raw — so there is nothing
        # structural to read for the lane (no etb-this-turn marker, no attack-
        # conditioned-on-entry shape). For ~3 cards a projection change would not be
        # worth it, and is FORBIDDEN in this parallel batch; the clean SIGNALS-ONLY
        # path is a byte-identical mirror of the exact deleted regex.
        #
        # CHOSEN PATH (kept-mirror). The lane fires from _ENTERED_ATTACKER_MIRROR in
        # _signals_ir — the EXACT deleted _HAND_FLOOR regex (pinned as
        # ENTERED_ATTACKER_REGEX in _sweep_detectors) run PER-CLAUSE over the reminder-
        # stripped oracle, byte-identical to the deleted floor Detector (which ran
        # per-clause over reminder-stripped clauses). The serve spec ("Haste + ETB
        # pump") stays hand-registered in signal_specs.py with its OWN curated search
        # regex, independent of the deleted producer.
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 3 (Hixus, Redoubled Stormsinger,
        # Samut), ir_only == 0, regex_only == 0 — a true behavior-neutral re-home.
        # floor-mirror-dep == 0 (entered_attacker is NOT an _IR_FLOOR_LANE). The
        # deleted producer fired HIGH-confidence (forced scope 'you') and fed
        # has_other_plan, BUT each of the 3
        # cards keeps has_other_plan via OTHER high-confidence non-generic signals
        # (combat_damage_matters / creature_etb / attack_matters / tokens_matter), so
        # deleting it leaks NO voltron tell (voltron delta 0, verified over the full
        # commander-legal corpus) — hence NO _ENTERED_ATTACKER_PLAN_MIRROR and NOT in
        # _VOLTRON_SILENCING_PLAN_KEYS. CR 603.10a (entered this turn) / 506.4 / 509.
        "entered_attacker",
        # ADR-0027 β — color_change (a card that CHANGES a permanent's/spell's COLOR:
        # "becomes the color of your choice" — Prismatic Lace, Tidal Visionary, Blind
        # Seer; "becomes the color" / "becomes all colors" — Scrapbasket, Tam; the
        # Painter-style color-fixer Scuttlemutt). MIGRATED VIA A BYTE-IDENTICAL KEPT-
        # MIRROR (signals-only, NO sidecar bump), NOT a structural arm.
        #
        # INCONSISTENT PARSE (structured, but UNUSABLE): phase parses the 24 color-
        # changers three different ways — 20 carry a deeply-nested `AddChosenColor`
        # modification (under a Choose sub_ability → GenericEffect → static_abilities),
        # and 4 are a bare `Unimplemented` "become" (Mondo Gecko "become the color of
        # your choice and gains hexproof", Scrapbasket / Tam "become all colors", Wild
        # Mongrel). The projection then re-categorizes them INCONSISTENTLY: 17 land as
        # cat=='animate', but Dream Coat → restriction (the "Activate only once" clause
        # won), Mondo Gecko / Shyft → grant_keyword (the "gains hexproof" clause won),
        # Sisay's Ingenuity → only choose (AddChosenColor is inside a GrantAbility). A
        # STRUCTURAL arm reading the one shared category, cat=='animate', was REJECTED:
        # it fires on 256 commander-legal cards (every man-land, animate-land anthem,
        # "becomes a 4/4") vs the 24 genuine color-changers — a ~90% OVER-FIRE.
        #
        # CHOSEN PATH 2 (kept-mirror). The lane fires from _COLOR_CHANGE_MIRROR in
        # _signals_ir — the EXACT deleted SWEEP regex (pinned as COLOR_CHANGE_REGEX in
        # _sweep_detectors) over the reminder-stripped kept_oracle, byte-identical to
        # the deleted SWEEP Detector. No structural arm is wired (reading cat=='animate'
        # would over-fire as above). The serve spec stays hand-registered in
        # signal_specs.py with its own (broader) curated search regex, independent of
        # the deleted producer.
        #
        # Floor-disabled residual vs the deleted SWEEP regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 24, ir_only == 0, regex_only == 0 — the
        # mirror is byte-identical to the deleted regex over the same reminder-stripped
        # input, so the served set is UNCHANGED (a true behavior-neutral re-home, no
        # recall gain, no over-fire). All 24 are genuine color-changers (no over-fire to
        # drop). floor-mirror-dep == 0 (color_change is NOT an _IR_FLOOR_LANE). The
        # deleted producer fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a byte-identical _COLOR_CHANGE_PLAN_MIRROR in
        # _signals_regex re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, matching
        # the token_copy_matters/variable_pt byte-identical-mirror pattern (a color-
        # change body is rarely a vanilla beater; FILE-SWAP voltron delta == 0). CR 105
        # / 613 (color is a continuously-checked layer-5 characteristic, verified via
        # rules-lawyer).
        "color_change",
        # ADR-0027 β — damage_redirect (a card that PROTECTS by preventing/redirecting
        # damage: the Pariah/Cho-Manno unkillable carrier + the en-Kor/Reflect-Damage
        # redirectors). MIGRATED VIA TWO BYTE-IDENTICAL KEPT MIRRORS (signals-only, NO
        # sidecar bump), NOT a structural arm. The lane has two DISJOINT arms (corpus
        # overlap == 0 over commander-legal):
        #
        # ARM A — name-aware self-PREVENTION/self-redirect ("prevent all damage that
        #   would be dealt to <self>", "if damage would be dealt to <self>": Cho-Manno,
        #   Phyrexian Vindicator, the Phantom +1/+1-shield cycle, Gideon Blackblade — 44
        #   commander-legal, 44/44 genuine). phase's cat=='damage_prevention' fires on
        #   396 commander-legal cards (every fog / Circle of Protection / Samite Healer)
        #   vs the 44 self-prevent tells — a ~90% OVER-FIRE with no recipient/self
        #   filter; a structural arm was REJECTED. ARM A is NAME-AWARE (self-only — it's
        #   the unkillable equipment carrier), so it rides the EXACT production helper
        #   signals._detect_self_damage_prevention inline in extract_signals_ir (the
        #   self_blink name-aware precedent), NOT a static SWEEP regex.
        # ARM B — the REDIRECT clause ("the next N damage … would be dealt … dealt to
        #   <X> instead", "that damage is dealt to ~ instead", "deal that damage to ~
        #   instead": Pariah/en-Kor redirectors, Reflect Damage, Nova Pentacle,
        #   Captain's Maneuver — 25 commander-legal, 25/25 genuine). phase types these
        #   INCONSISTENTLY (redirect / damage_replace / damage_replacement) and the
        #   union of those three categories fires on 224 commander-legal cards vs the 25
        #   genuine redirectors — a ~90% OVER-FIRE (every burn spell loosely typed
        #   damage_replacement: Lava Coil, Anger of the Gods); a structural arm was
        #   REJECTED. ARM B rides _DAMAGE_REDIRECT_MIRROR (_signals_ir) — the EXACT
        #   deleted SWEEP regex (pinned as DAMAGE_REDIRECT_REGEX in _sweep_detectors)
        #   over the reminder-stripped kept_oracle, byte-identical to the deleted
        #   Detector.
        #
        # Floor-disabled residual vs the deleted producers (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): ir_only == 0, regex_only == 0 — both arms are
        # byte-identical to their deleted regexes over the same reminder-stripped input,
        # so the served set is UNCHANGED (a behavior-neutral re-home, no recall gain, no
        # over-fire). All 69 (44 ARM A + 25 ARM B) are genuine (no over-fire to drop).
        # floor-mirror-dep == 0 (damage_redirect is NOT an _IR_FLOOR_LANE). The deleted
        # ARM A producer ALSO added voltron_matters (membership, low conf — the
        # unkillable body is the ideal Equipment/Aura carrier); that add is re-homed to
        # extract_signals_ir alongside ARM A. The deleted producers fired HIGH-
        # confidence (scope 'you') and counted toward has_other_plan, so a
        # _DAMAGE_REDIRECT_PLAN_MIRROR (ARM B regex) + the self-prevent helper in
        # _signals_regex re-supply the voltron silence — NOT the SILENCING_PLAN_KEYS set
        # (FILE-SWAP voltron delta == 0). CR 614.9 (redirection replacement) / 615
        # (prevention).
        "damage_redirect",
        # ADR-0027 — damage_prevention (a card that PREVENTS damage: the fog /
        # Circle-of-Protection / "prevent the next N damage" / "if a source would deal
        # damage … prevent it" family — CR 615 prevention, distinct from the CR 614.9
        # damage_redirect lane above and from damage_reflect). MIGRATED VIA the broad
        # `damage_prevention` effect-category arm (the PRIMARY producer) PLUS a
        # BYTE-IDENTICAL KEPT MIRROR (signals-only, NO sidecar bump).
        #
        # TWO IR producers in extract_signals_ir, unioned (add() dedups, both scope
        # 'you' to match the deleted SWEEP producer):
        #   ARM 1 (PRIMARY, structural) — phase's `damage_prevention` effect category
        #     via _DOER_EFFECT_KEYS, scope 'you'. This is the BROADER arm: it catches
        #     the 18 "prevent N of that damage" / "prevent half that damage" forms the
        #     deleted SWEEP regex MISSED (it required `prevent the next N` / `prevent
        #     all` / `prevent … damage that would be dealt`, none of which match
        #     "prevent 1 of that damage" — Urza's Armor, the Sphere of
        #     Law/Grace/Duty cycle, Daunting Defender, Hedron-Field Purists,
        #     Valkmira, Gisela's "prevent half that damage", Dark Sphere). All 18
        #     ir_only verified genuine CR 615 prevention vs Scryfall.
        #   ARM 2 (kept mirror) — _DAMAGE_PREVENTION_MIRROR (_signals_ir), the EXACT
        #     deleted SWEEP regex (pinned as DAMAGE_PREVENTION_REGEX in
        #     _sweep_detectors) over the reminder-stripped kept_oracle. phase's
        #     effect category MISSES 88 commander-legal genuine preventers (Fog Bank,
        #     Gaseous Form, Glacial Chasm, the Phantom/+1-counter prevention-shield
        #     cycle — Phantom Centaur, Vigor, Polukranos, Sekki, Ugin's Conjurant;
        #     Iroas, Energy Field, Solitary Confinement, Nine Lives, Immortal Coil,
        #     the Aura/Equipment "prevent all damage dealt to/by enchanted/equipped
        #     creature" wards). The regex's `[^.]*` arms never cross a sentence, so a
        #     FLAT scan over kept_oracle == the deleted per-clause SWEEP firing set
        #     BYTE-IDENTICALLY (466==466, 0 mismatch over all commander-legal —
        #     verified), recovering every regex_only card.
        #
        # Floor-disabled residual vs the deleted producer (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): regex_only == 0 (the kept mirror is byte-
        # identical), ir_only == 18 (the broader structural arm, all genuine).
        # Union == 484, all 484 genuine CR 615 prevention (no over-fire to drop).
        # floor-mirror-dep == 0 (damage_prevention is NOT an _IR_FLOOR_LANE). The
        # deleted SWEEP producer fired HIGH-confidence (scope 'you') and counted
        # toward has_other_plan (a prevention engine — a fog/CoP body — is no vanilla
        # beater), so a byte-identical _DAMAGE_PREVENTION_PLAN_MIRROR in
        # _signals_regex re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, which would OVER-silence the 18 ir_only bodies
        # the regex never fired on (the broader-IR → plan-mirror rule). CR 615
        # (prevention; verified via rules-lawyer).
        "damage_prevention",
        # ADR-0027 β — animate_artifact (a card that makes ARTIFACTS BECOME CREATURES:
        # Karn Silver Golem, March of the Machines, Ensoul Artifact, Tezzeret the
        # Seeker, Sydri, every Vehicle-crew "becomes an artifact creature"). MIGRATED
        # VIA A BYTE-IDENTICAL KEPT-MIRROR (signals-only, NO sidecar bump), NOT a
        # structural arm.
        #
        # INCONSISTENT PARSE (structured, but UNUSABLE): phase parses the animation
        # three different ways — base_pt_set + board_grant over an Artifact subject
        # (March of the Machines, Ensoul Artifact, Tezzeret the Seeker), a
        # becomes_type{Artifact} grant ("grant: becomes a artifact" — Karn Silver Golem,
        # Karn's Touch static half), or a base_pt_set with subject=None (Karn's Touch's
        # spell clause + every "target artifact becomes a N/N artifact creature" whose
        # target phase drops). The PRE-EXISTING structural arm (cat=='animate' &
        # 'Artifact'-subject) fires on ZERO commander-legal cards — phase never tags
        # artifact-animation `animate` — so it was DEAD CODE (now removed from
        # extract_signals_ir). A base_pt_set / board_grant / becomes_type-over-Artifact
        # arm was REJECTED two ways: the broad form 90%-OVER-FIRES (95 ir, 47 ir_only —
        # "becomes an artifact" type-conferral like Liquimetal Coating / Memnarch /
        # Argent Mutation; artifact-creature ANTHEMS like Galazeth / Food Fight /
        # Fountain Watch; "Artifacts are Foods/Clues/Equipment" like Ragost / Senator
        # Peacock / Dan Lewis — all verified non-animation vs Scryfall), and the narrow
        # form (excl already-Creature subjects, require the creature word in the raw)
        # LOSES 48 core animators (every Vehicle-crew "becomes an artifact creature" +
        # the subject=None spells — Alloy Animist, Fleetwheel Cruiser, Tezzeret the
        # Seeker, Karn's Touch, Xenic Poltergeist). The artifact-animation is NOT
        # structurally separable from generic become / type-conferral (rules-lawyer:
        # animating an artifact is a CR 613 layer-4 type addition — the SAME machinery
        # as making it an artifact or an Equipment, no separate IR category), so a
        # structural arm cannot cleanly hit the gate.
        #
        # CHOSEN PATH 2 (kept-mirror). The lane fires from _ANIMATE_ARTIFACT_MIRROR in
        # _signals_ir — the EXACT deleted SWEEP regex (pinned as ANIMATE_ARTIFACT_REGEX
        # in _sweep_detectors) over the reminder-stripped kept_oracle, byte-identical to
        # the deleted SWEEP Detector. The serve spec is hand-registered in signal_specs
        # reusing the pinned constant (SWEEP_LABELS keeps the label), so the served pool
        # is unchanged.
        #
        # Floor-disabled residual vs the deleted SWEEP regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 67, ir_only == 0, regex_only == 0 — the
        # mirror is byte-identical to the deleted regex over the same reminder-stripped
        # input, so the served set is UNCHANGED (a true behavior-neutral re-home, no
        # recall gain, no over-fire). All 67 are genuine animators (Vehicles are
        # artifacts — CR 301.7 — so "this Vehicle becomes an artifact creature" IS the
        # lane; the copy / Elk / Angel forms — True Polymorph, Oko, Majestic
        # Metamorphosis — all turn an artifact into a creature; 0 over-fire to drop).
        # floor-mirror-dep == 0 (animate_artifact is NOT an _IR_FLOOR_LANE — it was a
        # SWEEP_DETECTORS key).
        # The deleted producer fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a byte-identical _ANIMATE_ARTIFACT_PLAN_MIRROR in
        # _signals_regex re-supplies the voltron silence — NOT _VOLTRON_SILENCING_PLAN_
        # KEYS, matching the color_change / token_copy_matters / variable_pt byte-
        # identical-mirror pattern (FILE-SWAP voltron delta == 0). CR 110.1 / 305.7 /
        # 613 (animating an artifact is a layer-4 type addition; Vehicles / noncreature
        # artifacts gain the creature type — verified via rules-lawyer).
        "animate_artifact",
        # ADR-0027 β — free_cast (cast spells WITHOUT paying their mana cost — Beseech
        # the Mirror, Baral's Expertise, As Foretold). The IR carries cast_from_zone/
        # alt_cost but no 'free' discriminator (a structural arm can't separate a real
        # free-cast from a flash-grant/Bargain/Prototype alt-cost without a project.py
        # flag), so the lane rides a BYTE-IDENTICAL _FREE_CAST_MIRROR of the exact
        # deleted SWEEP regex (pinned FREE_CAST_REGEX) over the reminder-stripped
        # kept_oracle. The "without paying its mana cost" phrase is specific +
        # clause-local; both=314 (300 single-face + 14 DFC back-face recall via the
        # joined oracle), regex_only=0, over-fire=0 (of 39 "as though it had flash"
        # cards only Qasali Ambusher fires, genuine). floor-mirror-dep==0; voltron 0
        # via byte-identical _FREE_CAST_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS).
        # Serve hand-registered in signal_specs (SWEEP auto-spec gone). CR 601.2b/118.9.
        "free_cast",
        # ADR-0027 β — untap_engine (a DELIBERATE repeatable/mass untap engine —
        # Seedborn Muse, Murkfiend Liege, Kiora, Candelabra). The IR arm in
        # extract_signals_ir reads `cat=='untap'` Effects on three engine shapes: a mass
        # untap (counter_kind=='all' — Early Harvest, Sands of Time, Godo), a raw "untap
        # target/all/each/two/up to" (the deleted regex's anchor), and a multi/X-target
        # untap of a permanent TYPE you can control (Candelabra "Untap X target lands",
        # Synod Artificer, Reality Spasm — phase drops the "X target" engine raw). The
        # arm is gated against three over-fires the previous broad subject branch
        # leaked: (1) an opponent-untap (subject controller=='opp' OR a "you don't
        # control" raw — Provoke the card, Spinal Embrace, the provoke combat keyword
        # untap an ENEMY permanent for combat/theft, anti-synergy with an untap engine);
        # (2) a PROVOKE keyword (a `force_block` sibling effect rides the de-reminded
        # raw); (3) the single-permanent "untap enchanted/equipped <thing>" rider (Crab
        # Umbra, Pemmin's Aura).
        #
        # phase routes ~11 genuine engines into a choose / target_only / cost / type_set
        # carrier with NO cat=='untap' Effect (Captain of the Mists & Tideforce
        # Elemental — modal "tap or untap target"; Turnabout & Faces of the Past —
        # "tap-all OR untap-all" choose; All-Out Assault — mass-untap-own-board folded
        # into extra_combat; Teferi Who Slows the Sunset & Zariel — emblem untap in an
        # effect raw; Crackleburr & Halo Fountain — "untap two tapped … you control" as
        # a COST; Ohabi Caleria — "untap all Archers you control"; Ashaya — the
        # creatures-are-lands synergy). A NARROWED _IR_KEPT_DETECTORS-style mirror
        # recovers them with the EXACT two deleted _HAND_FLOOR regexes over the
        # reminder-stripped kept_oracle, vetoed by the opp-untap anti-pattern so it
        # drops the same incidental enemy-untap over-fires the structural arm does.
        #
        # Net residual vs the deleted regex (commander-legal, floor lanes disabled):
        # both == 339, ir_only == 12 (broader-and-correct recall — Candelabra, Synod
        # Artificer, Sands of Time, all Scryfall-verified engines), regex_only ==
        # {Provoke, Spinal Embrace} == 100% over-fire (both "Untap target creature you
        # don't control" — untap an ENEMY permanent for combat/theft, not a deliberate
        # engine — which the deleted regex over-fired on because it ran reminder-
        # stripped and couldn't read "you don't control"; the IR correctly drops both).
        # floor-mirror-dep == 0 (untap_engine is NOT in _IR_FLOOR_LANES; neither source
        # reads it). Both deleted producers fired high-confidence scope 'you', counting
        # toward has_other_plan, so an _UNTAP_ENGINE_PLAN_MIRROR (the byte-identical OR
        # of both deleted regexes over the reminder-stripped joined-face `text`) re-
        # supplies that voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, since the IR
        # arm is broader and would over-silence the ir_only bodies (NO-FLOOD: voltron 0
        # leaked). Both _HAND_FLOOR producers deleted; the standalone _spec serve in
        # signal_specs.py survives. CR 701.16 / 903.10a.
        "untap_engine",
        # ADR-0027 β — toughness_combat (TOUGHNESS matters for combat / as a value):
        # the Doran / Assault Formation / High Alert / Belligerent Brontodon / Huatli /
        # Arcades combat-redirect ("each creature assigns combat damage equal to its
        # TOUGHNESS rather than its power") PLUS the broader toughness-as-VALUE payoff
        # half (gain life / deal damage / draw / make an X/X / lose life "equal to …
        # toughness", "X is … toughness" — Geralf, Last March of the Ents, Death's
        # Caress, Angelic Chorus, Phthisis). MIGRATED VIA A BYTE-IDENTICAL KEPT-MIRROR
        # (signals-only, NO sidecar bump), NOT a structural arm.
        #
        # TWO deleted regex producers feed this key (BOTH dropped from the hybrid when
        # the key migrates, so BOTH must be reproduced): (1) the SWEEP detector
        # "assigns combat damage equal to its toughness/mana value rather than its
        # power | deals damage equal to its toughness" (the Doran combat-redirect half,
        # 22 commander-legal), and (2) an inline _signals_regex _DETECTORS producer
        # "\bx (is|equals) …toughness | equal to …toughness(?! are each)" (the value-
        # payoff half, a SUPERSET — the lane's true firing set is 133 commander-legal,
        # of which 111 are value-only).
        #
        # STRUCTURAL ARM REJECTED. phase parses the Doran clause cleanly as an
        # `AssignDamageFromToughness` modification on a Continuous static, but
        # project.py's _project_static_mods has NO arm for it: on a SINGLE-static body
        # (Doran, Belligerent Brontodon) the face falls through to supplement, which
        # text-recovers a `combat_damage_mod` Effect; on a MULTI-ability body the static
        # is silently DROPPED (Assault Formation / High Alert / Huatli / Arcades all
        # lose it). So the structural `combat_damage_mod` category fires on only 21
        # commander-legal cards while MISSING 129 of the 133-card lane (it can't reach
        # the 111 value-payoffs at all — they're a Ref/Aggregate `toughness` quantity
        # spread across gain_life/damage/draw/make_token/lose_life, no single category),
        # AND it OVER-FIRES on 17 of its 21 (= 81%): supplement's _ASSIGN_DAMAGE also
        # catches "deal damage equal to its POWER" combat redirects / punches
        # (Laccolith *, Farrel's *, Master of Cruelties, Defensive Formation, Pygmy
        # Hippo) — NOT toughness-as-power. 81% over-fire + 97% recall-miss → rejected
        # (cf. color_change's animate arm 256-vs-24).
        #
        # CHOSEN PATH 2 (kept-mirror). The lane rides a byte-identical
        # _TOUGHNESS_COMBAT_MIRROR in _signals_ir — the EXACT OR of the two deleted
        # producers (pinned as TOUGHNESS_COMBAT_REGEX in _sweep_detectors) over the
        # reminder-stripped kept_oracle. Both producers' arms are clause-local (no
        # `[^.]` crossing a sentence), so a full-text scan == the per-clause union.
        # The inline _DETECTORS producer was compiled WITHOUT re.IGNORECASE and matched
        # against the LOWERCASED clause; the mirror compiles with re.IGNORECASE over the
        # mixed-case kept_oracle, reproducing it exactly.
        #
        # Floor-disabled residual vs the two deleted regexes (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 133, ir_only == 0, regex_only == 0 — a
        # true behavior-neutral re-home (no recall gain, no over-fire; all 133 are
        # genuine toughness-matters). floor-mirror-dep == 0 (toughness_combat is NOT an
        # _IR_FLOOR_LANE — it was a SWEEP / _DETECTORS key, never a floor lane). Both
        # deleted producers fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a byte-identical _TOUGHNESS_COMBAT_PLAN_MIRROR in
        # _signals_regex re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, matching the color_change / token_copy_matters /
        # variable_pt byte-identical-mirror pattern (FILE-SWAP voltron delta == 0). The
        # serve spec stays hand-registered in signal_specs.py (_sweep_spec_with_extras
        # over the pinned regex, crediting high-toughness/Defender bodies), independent
        # of the deleted producers. CR 510.1c (combat-damage assignment) / 122 / 604.3.
        "toughness_combat",
        # ADR-0027 β — ability_copy (the "Ability copy" build-around): a card that
        # COPIES an activated/triggered ability (Strionic Resonator, Lithoform Engine,
        # Rings of Brighthearth, Illusionist's/Battlemage's Bracers, Kurkesh, the Riku-
        # ability arm) OR a "you may copy it" spell/adventure self-copy (Chancellor of
        # Tales, Tawnos the Toymaker, Donal), PLUS the ability-GRANTERS that import
        # another permanent's whole activated-ability suite ("has all/the activated
        # abilities of …" — Necrotic Ooze, Experiment Kraj, Mairsil, Myr Welder, Marvin,
        # Skill Borrower, Conspicuous Snoop). MIGRATED VIA A BYTE-IDENTICAL KEPT-MIRROR
        # (signals-only, NO sidecar bump), NOT a structural arm. 51 commander-legal.
        #
        # ONE deleted regex producer feeds this key (the SWEEP detector "copy
        # that/this/the/target …ability | you may copy it/that ability | has all/the
        # activated abilities of"). Migrating the key drops it from the hybrid, so it is
        # reproduced byte-for-byte as the pinned ABILITY_COPY_REGEX (_sweep_detectors).
        #
        # STRUCTURAL ARM REJECTED — needs a phase projection this parallel batch is
        # FORBIDDEN to make. phase parses every copy effect to ONE undifferentiated
        # `spell_copy` Effect category: Strionic's "Copy target triggered ability",
        # Lithoform's "Copy target instant or sorcery spell", and Twincast's "Copy
        # target spell" all flatten to `spell_copy` with NO spell-vs-ability
        # discriminator (the copy TARGET is dropped). So a `category == "spell_copy"`
        # arm fires on 303 commander-legal — OVER-FIRING 272 (90%) on the spell-copy
        # half NOT in this lane (Twincast, Reverberate, Fork, Reiterate, Dual Casting,
        # the Casualty/Conspire/ Replicate keyword cards, Kalamax-spell) — AND it STILL
        # MISSES the 20 ability- GRANTERS (Necrotic Ooze / Experiment Kraj / Mairsil:
        # phase parses "has all activated abilities of" as grant_keyword/board_grant,
        # NOT spell_copy). Splitting the lane structurally requires a projection that
        # tags the copy target (spell vs ability) — DEFERRED (FORBIDDEN to touch
        # _card_ir/ in this parallel batch). Re-reading e.raw to discriminate is
        # regex-by-another-name, not a structural arm, and it stays leaky (27 regex-miss
        # + 11 spurious). 90% over-fire + a hard projection blocker → rejected (cf.
        # color_change's animate arm 256-vs-24).
        #
        # CHOSEN PATH 2 (kept-mirror). The lane rides a byte-identical _ABILITY_COPY_
        # MIRROR in _signals_ir — the EXACT deleted SWEEP regex (pinned
        # ABILITY_COPY_REGEX in _sweep_detectors) over the reminder-stripped
        # kept_oracle. Every arm is clause-local (no `[^.]` crossing a sentence), so a
        # full-text scan == the deleted per-clause SWEEP union; the deleted SWEEP
        # detector compiled with re.IGNORECASE over reminder-stripped clauses, so the
        # mirror compiles the same way, reproducing it exactly.
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): both == 51, ir_only == 0, regex_only == 0 — a
        # true behavior-neutral re-home (no recall gain, no over-fire; all 51 are
        # genuine ability-copy / ability-import bodies). floor-mirror-dep == 0
        # (ability_copy is NOT an _IR_FLOOR_LANE — it was a SWEEP key, never a floor
        # lane). The deleted producer fired HIGH-confidence (scope 'you') and counted
        # toward has_other_plan, so a byte-identical _ABILITY_COPY_PLAN_MIRROR in
        # _signals_regex re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, matching the color_change / token_copy_matters /
        # toughness_combat byte-identical-mirror pattern (FILE-SWAP voltron delta == 0).
        # The serve spec stays hand-registered in signal_specs.py
        # (_sweep_spec_with_extras over the pinned regex), independent of the deleted
        # producer. CR 706.10 (copying an ability) / 113.2 (granted abilities) / 706.2.
        "ability_copy",
        # ADR-0027 β — pump_matters (a POSITIVE single-target combat-trick buff:
        # "target creature gets +N/+N", the instant-speed pump that wins combat). Unlike
        # its sign-discriminated sibling debuff_matters (a `pump` Effect with
        # amount.factor < 0), pump_matters is genuinely UNSTRUCTURABLE as a positive
        # discriminator: the v9 projection drops the value of EVERY target-creature pump
        # to amount==None (the +N/+N lives only in the raw — Giant Growth, Titanic
        # Growth, Brute Force all project pump_target / subj=Creature / amt=None) and
        # carries no temporal marker, so a +3/+3 combat trick is structurally
        # indistinguishable from Festering Goblin's -1/-1 (identical shape) and from a
        # permanent buff. The ONLY clean positive-single-target structural form phase
        # DOES carry — a positive-factor `pump` on an EnchantedBy/EquippedBy subject
        # (auras/equipment, factor>0: Serra's Embrace, Rancor, Vulshok Gauntlets) — is
        # the SEPARATE voltron/suit-up lane (signal_specs' "equipment/auras … suit
        # up and buff your attackers" avenue), so a structural arm firing on those
        # 409+ aura/equipment bodies would be SCOPE CREEP, not pump_matters recall.
        #
        # So the migration is a byte-identical _IR_KEPT_DETECTORS mirror of the EXACT
        # deleted regex (pinned as PUMP_MATTERS_REGEX): the regex itself IS the
        # positive-single-target discriminator. As a full-text .search over the
        # reminder-stripped joined-face `text` the mirror fires on the IDENTICAL
        # commander-legal set the deleted per-clause SWEEP path did (the regex arms are
        # all clause-local, so full-text == per-clause; 0 drift both directions →
        # ir_only == 0, regex_only == 0). No structural arm is added (it would be 100%
        # over-fire on the aura/equipment superset). floor-mirror-dep == 0 (pump_matters
        # was a SWEEP key, never an _IR_FLOOR_LANE).
        #
        # The deleted SWEEP producer fired HIGH-confidence (scope 'you') and counted
        # toward has_other_plan (a combat-trick body is NOT a vanilla beater), so a
        # byte-identical _PUMP_MATTERS_PLAN_MIRROR in _signals_regex re-supplies the
        # voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS (which the mirror equals
        # here since the IR set == the regex set exactly, but the byte-identical-mirror
        # pattern also covers the ir-is-None regex-path computation, matching the
        # toughness_combat / debuff_matters / variable_pt siblings). The serve spec is
        # hand-registered in signal_specs.py reusing PUMP_MATTERS_REGEX (the sweep
        # auto-register loop no longer builds it); the _PUMP_EXTRA combat-support
        # SubAvenue reuses the same pinned regex. CR 122.1b / 903.10a.
        "pump_matters",
        # ADR-0027 β — gain_control (THEFT: you take control of an opponent's / any
        # permanent — Control Magic, Mind Control, Confiscate, Treachery; temp-steal —
        # Act of Treason, Threaten, Mark of Mutiny, Zealous Conscripts). MIGRATED VIA A
        # STRUCTURAL IR ARM (already present pre-migration) + a NARROWED kept-mirror +
        # a facade cross-open reconciliation. NO sidecar bump (the v10 projection
        # already emits the gain_control category).
        #
        # STRUCTURAL ARM (recall-GAINING superset). project._project_static_mods emits
        # a `cat=='gain_control'` Effect for a ChangeController static, and phase also
        # emits it for the temp-steal "gain control … until end of turn" effects. The
        # GATED arm in extract_signals_ir (cat=='gain_control', EXCLUDING donate /
        # Owned-subject return / give-away) fires on 314 commander-legal cards vs the
        # deleted regex's 256 — a +85 recall gain (Control Magic / Mind Control /
        # Confiscate / Enslave / Treachery "you control enchanted creature", Mindslaver
        # / Worst Fears "control target player", Political Trickery / Juxtapose
        # "exchange control" — genuine theft the bare `gain control of` regex MISSED).
        # It drops
        # 4 regex over-fires the bare regex caught: Gruul Charm / Brand "gain control of
        # all permanents you OWN" (a reset-to-self, NOT theft), Guardian Beast "others
        # can't gain control" (a protection), Coveted Falcon "you own but don't control"
        # (own-recovery). All 4 verified non-theft against Scryfall oracle.
        #
        # NARROWED KEPT-MIRROR (_GAIN_CONTROL_MIRROR in _signals_ir). phase does NOT
        # emit a gain_control category for 9 genuine theft cards (Seize the Spotlight,
        # Power of Persuasion, Invert Polarity steal-a-spell, Wake the Dragon token,
        # Expropriate, Midnight Crusader Shuttle, Captivating Glance, Herald of Leshrac,
        # Risky Move). Recover them with `gain control of` over the reminder-stripped
        # kept_oracle PER-CLAUSE, vetoed PER-CLAUSE by the give-away/reset/protection
        # over-fires (you-own reset, "<player> gains control" give-away, "can't gain
        # control" protection) so the 4 dropped over-fires stay dropped. (Byte-identical
        # full-text would re-introduce them and a flat scan would let one clause's veto
        # kill another's genuine theft — Captivating Glance / Herald.)
        #
        # CROSS-OPEN RECONCILIATION (facade). The regex include_membership cross-open
        # fired a LOW-confidence gain_control on 13 "you control but DON'T OWN" theft-
        # payoff commanders with NO structural form (Gonti Canny, Tasha, Vaan, Don
        # Andres, Arvinox, Nita, Laughing Jasper Flint, Nathan Drake, Thieving Amalgam,
        # Thieving Varmint, Tinybones Bauble Burglar, Sentinel of Lost Lore, Staff of
        # Eden). The hybrid drops ALL regex gain_control (migrated), so signals.py re-
        # supplies the LOW `dont_own` cross-open AND re-opens the theft_matters sibling
        # against the MERGED key set (the structural-theft commanders — Memnarch,
        # Dragonlord Silumgar, Nihiloor, Empress Galina — that opened theft_matters via
        # gain_control-in-regex-keys now open it from the IR set). Matches the
        # spell_copy cross-open reconciliation pattern already in the facade.
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), IR arm + mirror vs regex base+cross-open):
        # ir_only == 85 (all genuine theft recall gain), regex_only == 4 (all genuine
        # over-fire dropped: Gruul Charm/Brand reset, Guardian Beast protection, Coveted
        # Falcon own-recovery) — NO genuine theft lost (the 9 phase-misses ride the
        # mirror; the 13 cross-opens ride the facade). floor-mirror-dep == 0
        # (gain_control is NOT an _IR_FLOOR_LANE — it was a _DETECTORS key). The deleted
        # producer fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a
        # _GAIN_CONTROL_PLAN_MIRROR in _signals_regex re-supplies the voltron silence —
        # NOT _VOLTRON_SILENCING_PLAN_KEYS, because the IR arm is BROADER (+85) and the
        # silencing-keys path would over-silence the recall-gain bodies. CR 800.4a /
        # 720.1 (one player controls a permanent at a time) / 903.10a (voltron).
        "gain_control",
        # ADR-0027 β — ltb_matters (LEAVES THE BATTLEFIELD: sac / blink / bounce fodder
        # to trigger a permanent leaving — broader than DYING, CR 603.6e/700.4: any
        # battlefield→elsewhere movement, where `dies` is the battlefield→graveyard
        # subset). MIGRATED VIA A PROJECTION (SIDECAR v10→v11) + a STRUCTURAL IR ARM + a
        # NARROWED kept-mirror.
        #
        # PROJECTION. phase's `LeavesBattlefield` trigger mode was projected to
        # event=='dies' — WRONG (leaves ≠ dies). project._trigger_event now maps it to
        # event=='leaves' (the `ChangesZone` arm already split leaves vs dies on the
        # explicit origin/destination zones; this fixes the zone-less LeavesBattlefield
        # mode). `Destroyed` stays `dies` (CR 701.7 — destroy IS battlefield→graveyard).
        # This touches NO migrated lane (death_matters is REGEX-served, keyed on the
        # word "dies", not the trigger event; the two-sidecar global no-flood is
        # drift==0). parse_confidence unchanged (98.7% full both sides).
        #
        # STRUCTURAL ARM (recall-GAINING). A `leaves` trigger with a real OTHER-
        # permanent subject + a BATTLEFIELD-leave (from:battlefield, or no directional
        # zone — the bare LeavesBattlefield mode) fires ltb_matters. Excludes the
        # graveyard-arrival "put into a graveyard from anywhere" ChangesZone triggers
        # the projection also tags `leaves` (to:graveyard with no from:battlefield —
        # Compost / Countryside Crusher; those are graveyard_matters). +12 recall over
        # the deleted regex: DFC back faces (Luminous Phantom, Aang at the Crossroads,
        # Zenos / Shinryu) the front-face-only regex missed, and bounce payoffs (Azorius
        # Aethermage, Warped Devotion, Tameshi — "a permanent is returned to hand", a
        # battlefield→hand leave).
        #
        # NARROWED KEPT-MIRROR (_LTB_MATTERS_MIRROR in _signals_ir). phase leaves the
        # bulk of the lane textual — the Revolt "a permanent left the battlefield this
        # turn" condition is a static check (no trigger), and the self-LTB payoff ("when
        # ~ leaves the battlefield, …" — Walker of the Grove, Sengir Autocrat, Skyclave
        # Apparition) is a SelfRef trigger (subject=None, gated out of the structural
        # arm, mirroring the death_matters / self_death_payoff split). Recover them with
        # the deleted producer's EXACT regex (pinned LTB_MATTERS_SWEEP_REGEX) over the
        # reminder-stripped kept_oracle PER-CLAUSE, VETOED per-clause by the O-Ring
        # self-LTB-EXILE form ("exile … until ~ leaves the battlefield" — Banishing
        # Light / Static Prison / Assimilation Aegis): that "until ~ leaves" is the END
        # of a removal LOCK, NOT a leaves-MATTERS payoff (it already routes to
        # exile_until_leaves). PER-CLAUSE so the veto can't kill a co-printed genuine
        # leave payoff (Skyclave keeps its "when ~ leaves … create a token").
        #
        # Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), structural arm + mirror vs the regex): both==252,
        # ir_only==12 (all genuine recall: DFC back faces + bounce payoffs),
        # regex_only==93 — ALL O-Ring self-LTB-exile over-fires the deleted regex's
        # "when ~ enters … until ~ leaves" span caught (100% over-fire vs Scryfall,
        # already routed to exile_until_leaves, 0 genuine payoff lost). floor-mirror-dep
        # == 0 (ltb_matters is NOT an _IR_FLOOR_LANE — it was a SWEEP_DETECTORS key).
        # The deleted producer fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a byte-identical _LTB_MATTERS_PLAN_MIRROR in _signals_regex
        # re-supplies the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, because
        # the IR arm is BROADER (+12) and the silencing-keys path would under-silence
        # the recall-gain bodies. FILE-SWAP no-flood (base 3525463 v10 vs edits v11,
        # 30969 commander-legal): drift==110, ONLY ltb_matters moves (gained 15 / lost
        # 95 by (key,scope); 7 cards gained, 95 dropped O-Ring), voltron delta 0, 0
        # other lane drift, 0 death_matters change. CR 603.6e / 700.4 (leaves ⊃ dies) /
        # 903.10a (voltron).
        "ltb_matters",
        # ADR-0027 — death_matters (the ARISTOCRATS payoff: OTHER creatures dying as a
        # resource, CR 700.4 "dies" = battlefield→GRAVEYARD, the DISJOINT complement of
        # the broader `leaves` event ltb_matters reads — dies = to-graveyard, leaves =
        # any zone). MIGRATED VIA A STRUCTURAL IR ARM + a BYTE-IDENTICAL kept-mirror (NO
        # sidecar bump — the v11 projection already emits the `dies` trigger event).
        #
        # STRUCTURAL ARM. extract_signals_ir fires on a `dies`-trigger with a real
        # subject (trig.event=='dies' and trig.subject is not None) — phase's
        # battlefield→graveyard trigger, the precise complement of the `leaves` event.
        #
        # WHY NOT STRUCTURAL-ONLY. The `dies`-TRIGGER arm covers only the literal
        # "whenever a creature dies" form. The dominant family is the MORBID "if a
        # creature died this turn" CONDITION (104 cards — Bone Picker, Reaper from the
        # Abyss, Bontu the Glorified), which is NO trigger at all; plus the conferred /
        # "until end of turn" / quoted dies triggers phase leaves textual
        # (Necrosynthesis, Relic Vial, Massacre Girl) and the death-trigger DOUBLERS
        # (Teysa Karlov, Drivnod). Phase carries no structural shape for these, so a
        # structural-only migration would LOSE 223 cards (208 genuine). Hence a kept-
        # mirror, NOT structural-only.
        #
        # BYTE-IDENTICAL KEPT-MIRROR. _DEATH_MATTERS_MIRROR (pinned DEATH_MATTERS_REGEX)
        # plus the two substring-AND branches ("whenever"&"dies", "dying"&"trigger") the
        # deleted lambda ran, over the reminder-stripped clauses — the EXACT union of
        # the two deleted producers (the clause-scoped _DETECTORS lambda + the "died
        # this turn" _HAND_FLOOR regex). Floor-disabled residual (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), structural arm + mirror vs the deleted regex):
        # both==558, ir_only==0, regex_only==0 — the mirror is byte-identical (verified
        # 558==558, 0 miss, 0 over). The STRUCTURAL arm ALONE adds +90 ir_only recall
        # (the verbose "is put into a graveyard from the battlefield" payoffs — Field of
        # Souls, Dingus Egg, Sarulf, Shirei — the literal-"dies" regex MISSED), add()-
        # deduped with the mirror. floor-mirror-dep == 0 (death_matters is NOT an
        # _IR_FLOOR_LANE — it was a clause-scoped baseline widen, never floored).
        #
        # VOLTRON. The deleted _HAND_FLOOR producer fired HIGH-confidence (scope 'any')
        # and the _DETECTORS lambda fired at the _resolve_scope confidence, both feeding
        # has_other_plan; a byte-identical _DEATH_MATTERS_PLAN_MIRROR in _signals_regex
        # re-supplies the regex-path voltron silence directly (the mirror is byte-
        # identical, so _VOLTRON_SILENCING_PLAN_KEYS would also work, but the pure-regex
        # has_other_plan needs the direct restore). FILE-SWAP no-flood (base 1611621 vs
        # edits, 30969 commander-legal): ONLY death_matters moves (+90 recall gain), 0
        # ltb_matters / dies_recursion / self_death_payoff drift, voltron delta 0, 0
        # other lane drift. CR 700.4 / 603.6e (dies ⊂ leaves) / 903.10a (voltron).
        "death_matters",
        # ADR-0027 — self_death_payoff (the SELF-death Aristocrats piece: the card
        # rewards ITS OWN death — Kokusho, Solemn, Wurmcoil, Doomed Dissenter — wanting
        # sac outlets to re-fire / loop the death, dies-recursion to bring it back,
        # reanimation to recast). DISTINCT from death_matters (OTHER creatures dying, CR
        # 700.4: "dies" = battlefield→graveyard, gated on a real trigger SUBJECT) — this
        # lane keys on the card ITSELF dying (SelfRef → scope "you"). MIGRATED VIA THE
        # STRUCTURAL IR ARM (already present, IR_SLICE_KEYS) + a name-aware kept mirror
        # (NO sidecar bump — the v11 projection already emits the `dies` trigger with
        # the SelfRef self-anchor that drops the subject Filter).
        #
        # STRUCTURAL ARM. extract_signals_ir fires on a `dies`-trigger that is SELF
        # (trig.event=='dies' and trig.scope=='you' — phase's SelfRef self-death, the
        # complement of death_matters' real-subject other-creature trigger) carrying at
        # least one RECOGNIZED payoff (any e.category != 'other'). The SelfRef gate
        # excludes "equipped creature dies" (Skullclamp, AttachedTo → scope "any"); the
        # recognized-effect gate drops unparsed "other"-only death triggers.
        #
        # WHY NOT STRUCTURAL-ONLY. The structural arm covers the 207 both + 591 ir_only
        # recall GAIN (the verbose "is put into a graveyard from the battlefield" self
        # forms — Zodiac Dragon, Enigma Sphinx — and the keyword-expanded self-deaths —
        # Modular / Persist / Undying / Afterlife / Soulshift — the literal-"dies" regex
        # MISSED, every one a CR-700.4 SELF dies trigger with a payoff). But it MISSES
        # 22 CONFERRED / GRANTED dies triggers — a spell or ability that GRANTS "When
        # this creature dies, …" to ANOTHER (target) creature (Feign Death, Supernatural
        # Stamina, Undying Malice, Showstopper, the granted-quote cycle), which phase
        # parses as a quoted ability on the target, NOT the card's own SelfRef trigger.
        # So a structural-only migration would LOSE those 22 (recall loss). Hence a kept
        # mirror, NOT structural-only.
        #
        # NAME-AWARE KEPT MIRROR. _detect_self_death_payoff(kept_oracle, name) — the
        # EXACT deleted producer, reused byte-identically (its `kept_oracle` == the
        # regex path's `text`: both `re.sub(r"\([^)]*\)", " ", get_oracle_text(card))`).
        # Name-aware is load-bearing (45 cards key on the card's own NAME — "When
        # Kokusho … dies" — not "this creature"; the structural arm catches those, the
        # mirror recovers the 22 "this creature"-quoted grants). With structural arm +
        # mirror, floor-disabled residual (commander-legal,
        # _IR_FLOOR_LANES=frozenset()):
        # both==229, ir_only==591 (all genuine SELF-death payoffs), regex_only==0 (no
        # recall lost). scope_mismatch==0 (both paths scope "you"). self_death_payoff is
        # NOT an _IR_FLOOR_LANE (floor-mirror-dep == 0 — it rode the name-aware fulltext
        # detector, never a floor Detector).
        #
        # VOLTRON. The deleted producer fired HIGH-confidence (scope 'you') and counted
        # toward has_other_plan, silencing the spurious commander-damage voltron tell on
        # a body that is an aristocrats engine, not a vanilla beater (Kokusho, Lord
        # Xander, Wurmcoil). The migrated lane rides a BROADER structural arm (+591
        # ir_only), so re-supplying via _VOLTRON_SILENCING_PLAN_KEYS would OVER-silence
        # those 591 bodies; instead the pure-regex `has_other_plan` calls
        # _detect_self_death_payoff(text, name) directly — byte-identical to the deleted
        # producer, restoring the EXACT old silence set. FILE-SWAP no-flood (base
        # 59b8e79 vs edits, commander-legal): ONLY self_death_payoff moves (229 → 820,
        # +591 recall gain), 0 death_matters / reanimator / sacrifice_matters /
        # aristocrats drift, voltron delta 0, 0 other lane drift. CR 700.4 / 603.6e /
        # 903.10a.
        "self_death_payoff",
        # ADR-0027 β — self_counter_grow (a creature that puts +1/+1 counters on ITSELF
        # to GROW: adapt CR 701.43 / monstrosity 701.13 / renown 702.111, Saga chapter
        # "put N +1/+1 on ~", "enters with / put a +1/+1 counter on this creature",
        # multi-
        # pay self-pump). MIGRATED VIA A PROJECTION (SIDECAR v11→v12) + a STRUCTURAL IR
        # ARM + a NARROWED kept-mirror.
        #
        # PROJECTION. phase emits a place_counter with target=={type:SelfRef} (the
        # self-anchor — "on ~ / this creature / it" / SelfRef), or implies it for the
        # keyworded adapt/monstrosity/renown nodes, but _effect_subject DROPPED the bare
        # SelfRef (it has no type/controller/predicates, so _filter → None) — leaving
        # the
        # placement subject=None, indistinguishable from "put a +1/+1 counter on TARGET
        # /
        # another creature" (the exact ambiguity that DEFERRED this lane). project.py
        # re-surfaces the anchor as a SelfRef-predicate Filter marker (_SELF_COUNTER_
        # MARKER). The enters-with REPLACEMENT form re-checks the replacement's
        # valid_card
        # (SelfRef = self enters → marked; Typed/Another = "each other creature enters
        # with …" → NOT marked: Master Biomancer, Giada). The projection is BEHAVIOR-
        # NEUTRAL until the lane is wired — self_pump treats the marker as the self
        # shape
        # it already fired on, and adapt/monstrosity keep counter_kind='' so they don't
        # newly open counters_matter (two-sidecar global no-flood v11 vs v12: drift==0).
        # parse_confidence unchanged (98.7% full both sides).
        #
        # STRUCTURAL ARM (recall-GAINING). A place_counter carrying the SelfRef marker
        # fires self_counter_grow scope 'you'. +503 recall over the deleted regex (which
        # matched only the PRONOUNS "on him/her/it/this"): it catches every body that
        # names ITSELF — "put a +1/+1 counter on Lazav / Garza Zol / Kyler" — the
        # pronoun-
        # only regex missed.
        #
        # NARROWED KEPT-MIRROR (_SELF_COUNTER_GROW_MIRROR in _signals_ir). phase drops
        # the
        # self-anchor on a structural tail (the Adversary multi-pay "put that many +1/+1
        # counters on this creature", Stormwild Capridor's damage-prevention static,
        # Scarlet Spider's ParentTarget branch — 14 self-growers). Recover them with the
        # deleted regex's SELF-ANCHORED arms only (MINUS the loose "on it" arm, which
        # 100%-over-fired onto OTHER-creature placements — Ordeal of Purphoros, Defy
        # Death, the counter anthems The Great Henge / Railway Brawler, combat payoffs
        # Necropolis Regent / Stensia Masquerade: 103 over-fires, the SelfRef IR gate
        # correctly excludes them). PLUS the self-power-scaling commander cross-open ("X
        # is ~'s power" → wants +1/+1 sources — Esper Sentinel, Velomachus), re-homed
        # from
        # the deleted low-confidence _DETECTORS add.
        #
        # GATES. Floor-disabled residual vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), structural arm + mirror vs the regex): both==898,
        # ir_only==503 (genuine recall: by-name self-grow + adapt/monstrosity/enters-
        # with
        # the pronoun regex missed), regex_only==103 — ALL the loose-"on it" OTHER-
        # creature
        # placements (100% over-fire vs Scryfall oracle, the SelfRef gate's exclusion is
        # correct). floor-mirror-dep == 0 (self_counter_grow is NOT an _IR_FLOOR_LANE —
        # it
        # was a SWEEP_DETECTORS key). The deleted SWEEP producer fired HIGH-confidence
        # (scope 'you') and counted toward has_other_plan, so a byte-identical
        # _SELF_COUNTER_GROW_PLAN_MIRROR re-supplies the voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, because the IR arm is BROADER (+503). CR 122.1 /
        # 614.12 / 701.43 / 701.13 / 702.111.
        "self_counter_grow",
        # ADR-0027 β — unspent_mana (the "you KEEP unspent mana across steps/phases"
        # payoff: the pure statics Kruphix / Leyline Tyrant / Horizon Stone / Omnath
        # Locus of Mana+All / Ashling / Electro / Fangorn / Upwelling / Ozai, AND the
        # mana-burst riders Savage Ventmaw / Avatar Roku / Birgi / Brazen Collector /
        # Sakiko / Rousing Refrain / Shizuko / …). MIGRATED VIA A KEPT-MIRROR, NO
        # SIDECAR BUMP.
        #
        # PATH (kept-mirror, no structural arm). phase DOES carry a structured
        # `StepEndUnspentMana` static-ability mode for the 11 pure statics (action
        # Retain — "you don't lose unspent <color> mana"; or Transform:<color> —
        # "becomes colorless/black/red instead"), but the v17 projection DROPS that mode
        # entirely (no Effect category models it), AND every one of those 11 cards
        # already matches the deleted regex's "don't lose unspent" / "\bunspent mana\b"
        # arms — so a NEW retain_mana category + a structural arm would gain ZERO
        # recall. The mana-burst riders have NO structural form: phase buries "you don't
        # lose this mana as steps end" in an Unimplemented(name="lose") sub-ability of a
        # `ramp` trigger, so they MUST ride a regex mirror regardless. The cheapest
        # correct path is therefore a byte-identical _IR_KEPT_DETECTORS mirror of the
        # EXACT deleted SWEEP regex (pinned as UNSPENT_MANA_REGEX) — no category, no
        # sidecar bump, drift-free by construction.
        #
        # GATES. floor-mirror-dep == 0 (unspent_mana is NOT an _IR_FLOOR_LANE — it was a
        # SWEEP_DETECTORS key). Floor-disabled IR-vs-regex residual (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), the kept mirror vs the EXACT deleted SWEEP
        # regex): both == 43, ir_only == 0, regex_only == 0 — the mirror is byte-
        # identical (no
        # arm spans a sentence, so the flat .search over reminder-stripped kept_oracle
        # reproduces the deleted per-clause SWEEP firing set exactly; 0 drift both
        # directions). FILE-SWAP no-flood (base 40e7ddf vs edits, commander-legal): ONLY
        # unspent_mana moves (0 cards — byte-identical), voltron gain 0 / lose 0. The
        # deleted SWEEP producer fired HIGH-confidence (scope 'you') and counted toward
        # has_other_plan, so a byte-identical _UNSPENT_MANA_PLAN_MIRROR re-supplies the
        # voltron silence on a mana-retention engine (Leyline Tyrant, Savage Ventmaw — a
        # mana-banking body is NOT a vanilla beater) — NOT _VOLTRON_SILENCING_PLAN_KEYS
        # (which would equal it here since the IR set == the regex set, but the gate
        # mirror also covers the ir-is-None regex-path computation). The serve spec in
        # signal_specs.py reuses UNSPENT_MANA_REGEX via the ``regex=`` arg (the sweep
        # auto-register loop no longer builds it; SWEEP_LABELS keeps the human label).
        # CR 500.4 / 106.4 / 903.10a.
        "unspent_mana",
        # ADR-0027 β — counter_distribute (a BOARD-WIDE +1/+1 counter spread — "put a
        # +1/+1 counter on each creature you control" / "distribute N +1/+1 counters
        # among target creatures" / "each of [up to N] target creatures" / "creatures …
        # enter with N additional +1/+1 counters"). MIGRATED VIA PROJECTION (SIDECAR
        # v17→v18) + a NARROWED kept-mirror.
        #
        # PROJECTION (v17→v18). phase carries the MASS distinction in the effect TYPE
        # itself — `PutCounterAll` ("on each …") vs the single-target `PutCounter` — but
        # _EFFECT_CATEGORY folds both to category `place_counter`, dropping the "All"
        # distinction; project._with_mass_marker re-surfaces it as the `MassEach`
        # subject predicate. The marker is the discriminator: a generic place_counter
        # (p1p1) on a Creature/you subject would conflate board-spread with "put a +1/+1
        # counter on TARGET creature you control" (New Horizons, Snakeskin Veil —
        # single-target, NOT board-wide; phase emits the SAME subject for both).
        # counter_kind stays p1p1 (additive — nothing else reads MassEach), so
        # counters_matter / self_counter_grow / debuff_matters / type_matters are byte-
        # identical. Two-sidecar behavior-neutral no-flood (v17 vs v18, SAME unwired
        # signals.py, 30969 commander-legal): drift_cards == 0. parse_confidence
        # unchanged (34118 full / 444 partial both sides).
        #
        # STRUCTURAL ARM (recall-GAINING). A place_counter carrying the MassEach marker
        # fires counter_distribute scope 'you'. +84 recall over a mirror-only path: it
        # catches every TRIBAL/restricted mass — "put a +1/+1 counter on each Vampire /
        # Cleric / legendary creature / attacking creature you control" (Krenko Baron of
        # Tin Street, Cordial Vampire, Minwu, Ardbert, Fangren Firstborn) — the deleted
        # regex's literal "each creature you control" arm missed. counters_matter still
        # co-fires on the p1p1 placement (counter_distribute is the NARROWER go-wide
        # build-around — is_widen_of counters_matter).
        #
        # NARROWED KEPT-MIRROR (_COUNTER_DISTRIBUTE_MIRROR in _signals_ir). Two board-
        # wide forms have NO PutCounterAll: the DISTRIBUTE-AMONG / "each of [up to N]
        # target creatures" form (Verdurous Gearhulk, Thrive, Ajani Mentor, support —
        # phase types these as a single-target PutCounter, structurally identical to "on
        # target creature you control") and the ENTERS-WITH-ADDITIONAL group buff ("each
        # other X you control enters with an additional +1/+1 counter" — Bramblewood
        # Paragon, Giada, Oona's Blackguard — phase drops the replacement subject to
        # None). Recover them with the deleted regex's mass/distribute/each-of arms PLUS
        # an enters-with-ADDITIONAL arm, MINUS the loose plain "enters with N +1/+1
        # counters on it" arm — that arm 100%-over-fired onto SELF-enters-with creatures
        # (Triskelion / Endless One / Modular / Graft / Bloodthirst — the source grows
        # ITSELF, which is self_counter_grow, NOT board spread; 329 over-fires, the lane
        # is board-wide-only per test_counter_distribute_is_board_wide_only). The
        # "distribute" arm is also fixed for the modern "distribute four +1/+1 counters"
        # templating the deleted regex's number-less arm missed. Run PER-CLAUSE over
        # reminder-stripped kept_oracle.
        #
        # GATES. floor-mirror-dep == 0 (counter_distribute is NOT an _IR_FLOOR_LANE — it
        # was a SWEEP_DETECTORS key; 380 firings floor-ON == 380 floor-OFF). Floor-
        # disabled IR-vs-regex residual (commander-legal, _IR_FLOOR_LANES=frozenset(),
        # structural arm + mirror vs the EXACT deleted SWEEP regex over the REMINDER-
        # STRIPPED oracle, the real producer's input): both == 229, ir_only == 151
        # (genuine recall: distribute-N the broken number-less arm missed + tribal mass
        # the literal-creature arm missed + support N the reminder-strip dropped + the
        # enters-with-additional form; 0 of 151 lack a +1/+1 mention, 0 single-target
        # over-fire — verified vs Scryfall oracle), regex_only == 258 — ALL plain self-
        # enters-with / keyword-self-grow placements (100% over-fire vs the board-wide
        # intent: the source grows itself, not the board; routed to self_counter_grow).
        # FILE-SWAP no-flood (base a96a28a + v17 vs edits + v18, commander-legal): drift
        # == 409, ONLY counter_distribute moves (gain 151 / lose 258); counters_matter /
        # self_counter_grow / debuff_matters / type_matters / creatures_matter drift 0,
        # voltron gain 0. The deleted SWEEP producer fired HIGH-confidence (scope 'you')
        # and counted toward has_other_plan, so a byte-identical
        # _COUNTER_DISTRIBUTE_PLAN_MIRROR re-supplies the voltron silence on a board
        # engine, NOT _VOLTRON_SILENCING_PLAN_KEYS (the IR arm is broader, +151).
        # The serve spec in signal_specs.py reuses COUNTER_DISTRIBUTE_SERVE_REGEX (a
        # board-wide regex via the ``regex=`` arg; SWEEP_LABELS keeps the human label).
        # CR 122.1 / 122.6 / 903.10a.
        "counter_distribute",
        # ADR-0027 β — opponent_search_matters (PUNISH opponents' tutors / library
        # manipulation — "whenever an opponent searches / shuffles their library /
        # scries / surveils": Ob Nixilis Unshackled, Psychic Surgery, River Song, Wan
        # Shi Tong, Cosi's Trickster, Archivist of Oghma). MIGRATED VIA PROJECTION
        # RE-TYPE (SIDECAR v18→v19).
        #
        # PROJECTION (v18→v19). phase carries the PRECISE trigger MODE —
        # `SearchedLibrary` (Ob Nixilis, Archivist, Wan Shi Tong), `Shuffled`
        # (Psychic Surgery, Cosi's Trickster), and the `PlayerPerformedAction`
        # scry-surveil-search composite (River Song, player_actions ==
        # ["Scry","Surveil","SearchedLibrary"]) — each with valid_target.controller
        # == "Opponent". But _trigger_event FOLDED all of them to the generic `other`
        # event, where they are indistinguishable from SIX OTHER opp-scoped `other`
        # modes (LandPlayed -> Burgeoning, AbilityActivated -> Runic Armasaur,
        # BecomeMonarch -> Garland, LosesGame -> Share the Spoils — a naive
        # `ev=='other' and scope=='opp'` arm would over-fire all of them).
        # project._trigger_event re-types the three library-manipulation modes to a
        # dedicated `lib_search` event (the same "phase carries a marker the
        # projection drops -> recover it" shape as the scry/surveil modes above it).
        # The PlayerPerformedAction gate (_player_actions_are_lib_search) requires
        # `SearchedLibrary` in the player_actions, so the Proliferate composites
        # (Ezuri, Scheming Aspirant) AND the scry/surveil-ONLY YOU-payoffs (Matoya,
        # Planetarium — which keep their event='other' _narrow_trigger_other_refs
        # scry_surveil marker) stay on `other`, making the re-type DRIFT-FREE on
        # scry_surveil_matters. The event is scope-neutral; nothing read `lib_search`
        # before, so every other lane is byte-identical. Two-sidecar behavior-neutral
        # no-flood (v18 vs v19, SAME unwired signals.py, 30969 commander-legal):
        # drift_cards == 0. parse_confidence unchanged (34118 full / 444 partial both
        # sides). Default sidecar rebuilt to v19.
        #
        # STRUCTURAL ARM. An opp-scoped `lib_search` trigger fires
        # opponent_search_matters scope 'opponents'. The scope=='opp' gate (recovered
        # from valid_target.controller by _trigger_scope) is the EXACT discriminator
        # the deleted producer regex required ("whenever an opponent|a player|each
        # opponent … searches/shuffles their library / scries / surveils") — it
        # excludes the YOU-scoped "whenever you search your library / scry / surveil"
        # payoffs (Search Elemental — scope 'any').
        #
        # GATES. floor-mirror-dep == 0 (NOT an _IR_FLOOR_LANE — it was a _HAND_FLOOR
        # regex, like the sibling opponent_draw_matters / opponent_cast_matters).
        # FILE-SWAP residual (base a626384 + v18 vs edits + v19, commander-legal,
        # include_membership): only opponent_search_matters moves, 6 -> 6
        # BYTE-IDENTICAL (gain 6 / lose 0 — the exact 6 commander-legal cards the
        # deleted regex hit over the reminder-stripped oracle: Archivist of Oghma,
        # Cosi's Trickster, Ob Nixilis Unshackled, Psychic Surgery, River Song, Wan Shi
        # Tong; 0 ir_only, 0 regex_only). No NEW recall (the regex's producer arms —
        # scries/surveils/searches/shuffles — all have a phase trigger mode, so the
        # structural arm is an exact reproduction, not a widening) and no over-fire.
        # voltron delta 0 with NO _PLAN_MIRROR: the two power<2 punishers never reach
        # the voltron gate, and every power>=2 punisher carries another high-confidence
        # plan keeping has_other_plan True. The _HAND_FLOOR producer is deleted; the
        # serve spec (signal_specs.py) is independent and survives.
        # CR 701.19 (search) / 701.23 (shuffle) / 701.39 (scry) / 701.47 (surveil) /
        # 903.10a (voltron).
        "opponent_search_matters",
        # ADR-0027 β — conjure_matters (CONJURE: the Arena/Alchemy "create a real
        # CARD onto the battlefield / into a zone, NOT a token" mechanic — Key to the
        # Archive-style spellbooks, Agent of Raffine, Drover of the Swine, the Collector
        # cycle, the Viconia personas). MIGRATED VIA A KEPT-MIRROR (signals-only, NO
        # sidecar bump), NOT a structural Conjure-effect arm.
        #
        # DISCRIMINATOR FOUND (structured, but UNUSABLE for a clean migration): phase
        # DOES carry a structural `Conjure` EFFECT type (101 cards: `{"type":"Conjure",
        # "cards":[…],"destination":…}`) that the projection FOLDS to make_token
        # (project._EFFECT_CATEGORY['conjure'] == 'make_token'), indistinguishable from
        # a vanilla token maker. A STRUCTURAL arm reading the un-folded Conjure effect
        # was REJECTED: that set is INCOMPLETE. Over the Historic-Brawl corpus (Scryfall
        # `brawl` key, where conjure actually lives — it is digital-only) the structural
        # set is 93 cards, a STRICT SUBSET of the deleted regex's 158 — the 65-card
        # regex_only delta is 100% RECALL LOSS (genuine conjure phase fails to
        # structure: conjure on an ACTIVATED ability — Agent of Raffine; a TRIGGERED
        # ability phase nests past — Anina, Blood Age Muster, Cosmic Sovereign; a MODE —
        # Drover of the Swine), and struct_only == 0 (no over-fire to gain). So the
        # structural marker would LOSE 65 cards with no benefit.
        #
        # CHOSEN PATH 2 (kept-mirror). The lane fires from a byte-identical
        # `\bconjure\b` row in signals._IR_KEPT_DETECTORS (scope 'you', matching the
        # deleted SWEEP scope), run over the reminder-STRIPPED kept_oracle — byte-
        # identical to the deleted SWEEP Detector (which ran per-clause over the same
        # `re.sub(r"\([^)]*\)", " ", …)`-stripped joined-face text; `\bconjure\b` has no
        # `[^.]` span, so full-text == per-clause). The keyword is near-EXACT: 166 of
        # 167 stripped hits are genuine conjure; the single false positive is Silvanus's
        # Invoker's "Conjure Elemental —" ability-WORD name — and it is the ONLY
        # commander-legal hit, so commander served-set is empty either way. The serve
        # spec stays hand-registered in signal_specs.py (the sweep auto-register loop no
        # longer reaches it once the SWEEP_DETECTORS row is deleted).
        #
        # GATES. floor-mirror-dep == 0 (conjure_matters is NOT an _IR_FLOOR_LANE — it
        # was a SWEEP key, like the sibling celebration/coven/outlaw kept mirrors).
        # Floor-disabled residual vs the deleted SWEEP regex over get_oracle_text
        # (joined faces, HB-legal — the corpus where conjure lives —
        # _IR_FLOOR_LANES=frozenset()): both == 164, ir_only == 0, regex_only == 0 (the
        # mirror is byte-identical to the deleted regex over the same reminder-stripped
        # input; commander-legal: both == 1, the Silvanus false positive). FILE-SWAP
        # no-flood (base 813d507 vs edits, commander+HB, 31868 cards): drift_cards == 0
        # — only conjure_matters re-homes, byte-identical, no other lane drifts.
        #
        # VOLTRON. The deleted SWEEP producer fired HIGH-confidence (scope 'you') and
        # fed has_other_plan (a conjure ENGINE is a real value plan), so a
        # byte-identical _CONJURE_MATTERS_PLAN_MIRROR in _signals_regex re-supplies the
        # commander-damage voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS (matching
        # the token_copy_matters / variable_pt byte-identical-mirror pattern: restores
        # has_other_plan for ALL cards regardless of IR/regex mode). NEEDED: 23 HB-legal
        # conjure creatures power>=2 carry conjure_matters as their ONLY high-confidence
        # plan (Cosmic Sovereign, Darigaaz Shivan Champion, Roalesk, …), so without the
        # mirror they would flip to a spurious voltron tell. CR 701.66a / 903.10a.
        "conjure_matters",
        # ADR-0027 β — draw_matters (the YOU-draw payoff: a "whenever you draw" engine
        # — Niv-Mizzet Parun, Chasm Skulker, The Locust God, Psychosis Crawler — and
        # the past-tense draw-COUNT payoff "for each card you've drawn this turn" —
        # Proft's Eidetic Memory, Kydele, Thundering Djinn). MIGRATED VIA A
        # SCOPE-GATED STRUCTURAL ARM + a byte-identical kept-mirror + a voltron
        # _PLAN_MIRROR. NO sidecar bump (the v20 projection already emits the `drawn`
        # trigger event the structural arm reads).
        #
        # STRUCTURAL ARM (scope-gated). extract_signals_ir fires draw_matters scope
        # "you" on a `drawn` trigger with trig.scope != "opp". The gate is the
        # discriminator: phase parses a literal "Whenever you draw a card" as scope
        # 'any' (NOT 'you'), so 'any' is the YOU-draw payoff (Niv-Mizzet et al.) and
        # is KEPT; an OPP-scoped drawn trigger is the SEPARATE opponent_draw_matters
        # punisher lane (Underworld Dreams, Smothering Tithe, Nekusar, Orcish
        # Bowmasters) the deleted regex deliberately excluded — "whenever you draw"
        # never matched "whenever an opponent draws". The un-gated arm (the
        # pre-migration code, which fired draw_matters on EVERY drawn trigger) OVER-
        # fired on 20 commander-legal opp-draw punishers; the gate drops all 20 while
        # KEEPING 8 genuine you/any-scoped recall gains the regex missed (Sneaky
        # Snacker "your third card", Tamiyo "your second card", and the symmetric
        # "whenever a player draws" payoffs — Phyrexian Tyranny, Spiteful Visions,
        # Ian Malcolm, The Council of Four, Krang, Fasting).
        #
        # KEPT-MIRROR (recall recovery, NO sidecar bump). The past-tense draw-COUNT
        # payoff ("for each card you've drawn this turn") is a static / CDA /
        # count-operand reference with NO `drawn` trigger, and a granted/quoted
        # "whenever you draw" (Diviner's Wand, Teferi's emblem, Lady Octopus) nests
        # below a top-level trigger phase doesn't surface — 28 commander-legal cards
        # the structural arm alone misses. A byte-identical draw_matters row in
        # signals._IR_KEPT_DETECTORS reproduces the EXACT deleted _DETECTORS producer
        # (both arms: "whenever you draw" OR "(?:you've|you have) drawn (?:this turn|
        # your|\d|two|three)"), run over the reminder-STRIPPED kept_oracle — byte-
        # identical to the deleted Detector (which ran per-clause over the same
        # `re.sub(r"\([^)]*\)", " ", …)`-stripped lowercased text; neither arm has a
        # `[^.]` cross-sentence span, so full-text == per-clause). The mirror's
        # "whenever you draw" never matches an opp-draw punisher, so it re-introduces
        # ZERO over-fire. The serve spec stays hand-registered in signal_specs.py
        # (line 1891, ("draw_matters","you")).
        #
        # GATES. floor-mirror-dep == 0 (draw_matters is NOT an _IR_FLOOR_LANE — it
        # was a _DETECTORS producer, like the sibling opponent_draw_matters). FLOOR-
        # DISABLED residual vs the deleted regex (commander-legal, dedupe oracle_id,
        # _IR_FLOOR_LANES=frozenset()): COMBINED struct + mirror gives both ==
        # 105,
        # regex_only == 0 (NO recall lost), ir_only == 8 (all genuine you/any draw
        # payoffs the "whenever you draw" literal-regex missed). The three sibling
        # draw lanes (draw_for_each = a draw that SCALES with a board count;
        # card_draw_engine = a recurring bulk-advantage engine; group_hug_draw = a
        # symmetric "each player draws" gift) key on `Effect`/scaling, NOT the `drawn`
        # trigger, so they are DISJOINT and DO NOT drift (a card with both a draw
        # payoff and a draw engine legitimately carries draw_matters + the sibling —
        # that is co-occurrence, not over-fire).
        #
        # VOLTRON. The deleted _DETECTORS producer fired HIGH-confidence (scope 'you')
        # and fed has_other_plan (draw_matters is not in _GENERIC_KEYS /
        # _VOLTRON_COMPAT_KEYS; a draw-engine commander is no vanilla beater), so a
        # byte-identical _DRAW_MATTERS_PLAN_MIRROR in _signals_regex re-supplies the
        # commander-damage voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS (the
        # combined IR arm is BROADER (+8 ir_only); the silencing-keys path would
        # over-silence those recall-gain bodies). Restores has_other_plan for ALL
        # cards regardless of IR/regex mode (FILE-SWAP voltron delta 0). CR 120.1 /
        # 903.10a.
        "draw_matters",
        # ADR-0027 β — lifegain_matters (a lifegain PAYOFF — "whenever you gain life",
        # "if you gained life this turn" — Aerith, Celestine, Lathiel, Bilbo; a lifegain
        # SOURCE — "you gain N life", "gain life equal to"; PLUS a self-bleed engine
        # that WANTS lifegain to sustain — Deadpool / Gallowbraid upkeep loss, Greven
        # "lose life equal to", Necropotence draw-and-bleed). MIGRATED VIA A STRUCTURAL
        # IR ARM (recall-gaining, already present pre-migration) + a BYTE-IDENTICAL
        # kept-mirror. NO sidecar bump (the v20 projection already emits the gain_life
        # category and the life_gained trigger).
        #
        # STRUCTURAL ARM (recall-GAINING). extract_signals_ir already fires
        # lifegain_matters from a `gain_life` Effect scope you/any (the gain SOURCE) and
        # a `life_gained` Trigger (the gain PAYOFF), plus the lifelink keyword (moved
        # from _DIRECT_KEYWORD_SIGNALS to the IR-only _IR_KEYWORD_MAP). Floor-disabled
        # (commander-legal, _IR_FLOOR_LANES=frozenset()) it fires on +77 cards the
        # deleted bare-"you gain" regex MISSED — the DIRECTED "target player gains N
        # life" (Skystreamer, Tonic Peddler, Rest for the Weary, Soothing Balm) and
        # "each opponent gains 1 life" (Grove of the Burnwillows) gains phase structures
        # as a gain_life Effect. All 77 verified genuine lifegain sources/payoffs (every
        # one carries a gain/life clause), zero noise.
        #
        # BYTE-IDENTICAL KEPT-MIRROR (_LIFEGAIN_MATTERS_MIRROR in _signals_ir). phase
        # has no structural form for the deleted producers' broader intent: (A) the
        # registry-280 detector — "whenever you gain life" / "gained life this turn"
        # gate / "gain X life" variable source / "if you would gain life" amplifier; and
        # (B) the inline self-bleed-wants-sustain block — a SIGNIFICANT repeated self-
        # life-LOSS engine (upkeep lose >=2, cumulative upkeep, "lose life equal to",
        # Necropotence draw-and-bleed, symmetric "each player loses [2-9]"). These are
        # the `_matters` "cares-about" reading (a self-bleed engine wants lifegain to
        # stay alive — Infernal Darkness, Stinging Study, Imp's Mischief), which phase
        # carries no signal for. So the lane rides the EXACT deleted producers (pinned
        # as LIFEGAIN_MATTERS_REGEX) over the reminder-stripped kept_oracle. Run FULL-
        # TEXT (not per-clause): the registry-280 arms are `[^.]`-bounded clause-local
        # AND the deleted sustain block was an inline full-`text` `re.search`, so over
        # the same reminder-stripped input full-text == the union of both producers.
        #
        # Floor-disabled residual vs the deleted regex producers (commander-legal,
        # _IR_FLOOR_LANES=frozenset(): IR-arm-only vs regex base): ir_only == 77
        # (genuine directed-gain recall the IR gained), regex_only == 247 (the broader
        # payoff / sustain intent the structural arm has no form for) — ALL 247
        # recovered byte-identically by the mirror (247 fixed, 0 still-regex-only, 0 NEW
        # over-fire) — NO genuine lifegain lost. floor-mirror-dep == 0 (lifegain_matters
        # is NOT an _IR_FLOOR_LANE — it was a _DETECTORS key + an inline block).
        #
        # VOLTRON. Two HIGH-confidence regex sources fed has_other_plan and are re-
        # supplied as byte-identical gate mirrors in _signals_regex (NOT the silencing-
        # keys set, matching the token_copy_matters / conjure_matters pattern): (1) the
        # registry-280 _DETECTORS producer (ARM A, forced scope 'you') →
        # _LIFEGAIN_MATTERS_PLAN_MIRROR, the ARM-A-only regex (NOT the A|B union — the
        # ARM-B sustain block fired LOW confidence and never fed has_other_plan, so
        # silencing sustain-only bodies would CHANGE behavior); and (2) the lifelink
        # keyword map entry (HIGH-confidence, the default add() confidence) → a
        # `lifelink in card.keywords` term, since a vanilla-lifelink beater's gain lives
        # only in the stripped keyword reminder the PLAN mirror can't see (69 commander-
        # legal lifelink creatures power>=2 — Divinity of Pride, Blood Baron — would
        # otherwise flip to a spurious voltron tell). FILE-SWAP voltron delta == 0.
        # CR 119 / 118 / 702.15 / 903.10a.
        "lifegain_matters",
        # ADR-0027 proliferate_matters — the counter-SYNERGY hub (cards that want
        # MORE counters of an existing kind): proliferate itself (CR 701.27 — "add
        # another counter of each kind already there"), station (CR 702.184 —
        # charge accrual), the divinity/indestructible enters-with cycle (Myojin,
        # Arwen), beneficial charge/experience-counter references (Ezuri, Mizzix,
        # Meren), and the "remove a counter as a cost" counter-spend engines (Tayam,
        # Fain). FIVE producers, re-homed by source:
        #   • proliferate KEYWORD + station KEYWORD → _IR_KEYWORD_MAP (IR-only
        #     keyword path, byte-identical to the deleted preset; the native
        #     `proliferate` EFFECT category in _DOER_EFFECT_KEYS additionally opens
        #     the lane for keyword-LESS proliferators — Maulfist Revolutionary,
        #     Skyship Plunderer — recall the keyword regex MISSED).
        #   • divinity/indestructible-counter + charge/experience-counter
        #     _HAND_FLOOR producers → HIGH-confidence _IR_KEPT_DETECTORS mirrors
        #     (phase carries no structural form: an enters-replacement /
        #     charge-counter reference projects with a blank counter_kind the
        #     structural edge routes to counters_matter, not proliferate_matters).
        #   • the "remove a counter from X:" inline producer (fired LOW) →
        #     _PROLIFERATE_REMOVE_COST_RE LOW-confidence mirror arm in
        #     extract_signals_ir (kept LOW so the 55 commander-legal
        #     countdown-resource cards with no other plan — Gemstone Mine, Serrated
        #     Arrows — keep their voltron tell; a HIGH firing would wrongly silence
        #     it).
        #
        # FLOOR-DISABLED RESIDUAL vs the deleted regex (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), IR-arm-only vs regex base): both == 404,
        # ir_only == 2 (genuine recall GAIN — Maulfist Revolutionary, Skyship
        # Plunderer, the keyword-LESS "give another counter of each kind"
        # proliferators), regex_only == 0 (the four oracle-text producers are
        # reproduced byte-identically by the kept mirrors). floor-mirror-dep == 0
        # (proliferate_matters is NOT an _IR_FLOOR_LANE — it was a _HAND_FLOOR /
        # keyword / inline set, never floored).
        #
        # VOLTRON. The deleted HIGH-confidence producers (proliferate keyword +
        # station keyword + divinity-enter + charge/experience floors) fed
        # has_other_plan; a byte-identical _PROLIFERATE_MATTERS_PLAN_MIRROR in
        # _signals_regex re-supplies the commander-damage voltron silence — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (+2 ir_only) and
        # that would over-silence the two recall-gain bodies. The LOW remove-cost
        # producer never fed has_other_plan, so its term is intentionally absent.
        # FILE-SWAP no-flood (base ee50c00 vs edits, commander-legal hybrid): ONLY
        # proliferate_matters moves (404 → 406, +2 recall gain), counters_matter /
        # counter_distribute / counter_manipulation / minus_counters_matter drift 0,
        # voltron_matters delta 0 (gained 0 / lost 0). CR 701.27 / 702.184 / 903.10a.
        "proliferate_matters",
        # ADR-0027 — artifacts_matter (the ARTIFACTS go-wide / matters axis: a card
        # that cares about your artifact population — "artifacts you control" anthems,
        # "for each artifact you control" count payoffs, affinity / metalcraft /
        # improvise, artifact ETB / cast triggers, artifact tutors / recursion /
        # sac-outlets / token-makers — affinity CR 702.41, metalcraft CR 207.2c,
        # artifact tokens CR 205.3g). MIGRATED VIA the STRUCTURAL IR arms + a NARROWED
        # kept-mirror (NO sidecar bump — the v20 projection already structures the
        # artifact filters / triggers / token subtypes the arms read).
        #
        # STRUCTURAL ARMS (already present in extract_signals_ir, the recall-GAINING
        # half): the `_TYPE_MATTERS_LANE` count/grant/trigger DOERs ("for each artifact
        # you control" / "artifacts you control have …" / "whenever an artifact
        # enters"), the `_ARTIFACT_TOKEN_SUBTYPES` maker/sac arm (Treasure/Clue/Food/…
        # are artifact tokens per CR 205.3g — a maker or "sacrifice a Food" payoff feeds
        # the lane), the type-gate condition arm ("if you control three or more
        # artifacts" = metalcraft), and the type_line membership arm ("if 'artifact' in
        # type_line" — byte-identical to the deleted line-4349 regex membership
        # producer). These ADD +325 ir_only recall the brittle oracle regex MISSED — the
        # subtype sac payoffs (Cauldron Familiar, Wicked Wolf, Bog Naughty) + the DFC
        # back-face artifact-recursion (Open the Vaults variants, Crystal Dragon // Rob
        # the Hoard) — every one a real artifact-population care.
        #
        # NARROWED KEPT-MIRROR. phase carries NO clean shape for the oracle-idiom family
        # the deleted _HAND_FLOOR regex read (artifact tutors / recursion-from-graveyard
        # / "abilities of artifacts" / "becomes an artifact" / improvise / metalcraft /
        # investigate / "artifact, instant, and sorcery spells"), so a structural-only
        # migration would LOSE 109 genuine artifact-deck cards (Retract, Meria, Vedalken
        # Certarch, Goblin Welder, Drafna, Urza Lord Protector).
        # _ARTIFACTS_MATTER_MIRROR
        # (the deleted _HAND_FLOOR producer UNIONed with the KEPT "if you control an
        # artifact" SWEEP row — NOT deleted, len(SWEEP_DETECTORS) stays >=36) runs
        # PER-CLAUSE over the reminder-stripped kept_oracle, the EXACT union of the
        # regex-path producers, recovering all 109 byte-identically. add() dedups vs the
        # structural arm.
        #
        # NARROWED (signals-only over-fire fix, "no dismissal without the hook"): the
        # deleted producer's bare `\baffinity\b` branch over-fired on EVERY
        # affinity-for-NON-artifact card — the hook is the keyword "affinity" without
        # its object, so the mirror requires `affinity for artifacts`. This drops 22
        # commander-legal over-fires (Icebreaker Kraken's snow affinity, Argivian
        # Phalanx's creature affinity, Bartz and Boko's bird affinity, Thrumming
        # Hivepool's sliver affinity — verified vs Scryfall oracle, NONE an artifacts
        # deck). The real affinity-matters bodies survive: conferred "spells you cast
        # have affinity for artifacts" (Sami), and the artifact-typed Golems keep the
        # lane via the membership arm.
        #
        # FLOOR-DISABLED RESIDUAL (commander-legal, _IR_FLOOR_LANES=frozenset(), the
        # structural arms + the narrowed mirror vs the deleted regex base): both==4554,
        # ir_only==325 (pure recall GAIN, all genuine), regex_only==22 (ALL the
        # affinity-for-other over-fire — 100% over-fire, 0 genuine recall lost). SCOPE
        # PARITY holds — IR and regex both fire scope 'you' ONLY (no scope regression).
        # floor-mirror-dep == 0 (artifacts_matter is NOT an _IR_FLOOR_LANE — a
        # structural type-matters lane).
        #
        # VOLTRON. The two deleted HIGH-confidence producers (the _HAND_FLOOR oracle
        # regex + the kept SWEEP row, both scope 'you') counted toward `has_other_plan`,
        # silencing the spurious commander-damage voltron tell on an artifacts body that
        # is NOT a vanilla beater (Sai, Emry, Urza, Slobad). The migrated IR arm is BOTH
        # broader (+325) and narrower (the 22 affinity over-fires dropped), so a
        # BYTE-IDENTICAL _ARTIFACTS_MATTER_PLAN_MIRROR in _signals_regex (keeping the
        # bare `\baffinity\b` branch the lane mirror dropped) re-supplies the regex-path
        # voltron silence EXACTLY. FILE-SWAP voltron delta == 0.
        #
        # FILE-SWAP no-flood (base ee50c00 vs edits, commander-legal): ONLY
        # artifacts_matter moves (4576 → 4879, +303 net = +325 recall gain / -22
        # over-fire drop), 0 type_matters / clue_matters / vehicles_matter drift,
        # voltron delta 0. SWEEP_DETECTORS stays at 36 (the "if you control an
        # artifact" row is KEPT). artifacts_matter added to MIGRATED_KEYS; both regex
        # producers deleted (the _HAND_FLOOR oracle regex + the line-4349 type_line
        # membership, the latter reproduced by the IR membership arm); the serve spec
        # stays hand-registered. CR 702.41 / 207.2c / 205.3g / 903.10a.
        "artifacts_matter",
        # ADR-0027 — enchantments_matter (the ENCHANTMENTS go-wide / matters axis: a
        # card that cares about your enchantment population — "enchantments you control"
        # anthems, "for each enchantment you control" count payoffs, constellation
        # ("whenever an enchantment you control enters" — CR 207.2c), enchantress cast
        # triggers, enchantment tutors / recursion / sac-outlets / token-makers, and
        # Role-token makers — Roles ARE Aura enchantments per CR 303.7 / 111.10j, Auras
        # are enchantments per CR 205.2 / 303). MIGRATED VIA the STRUCTURAL IR arms
        # (shared with artifacts_matter) + a BYTE-IDENTICAL kept-mirror (NO sidecar bump
        # — the v20 projection already structures the enchantment filters / triggers /
        # token subtypes the arms read).
        #
        # STRUCTURAL ARMS (already present in extract_signals_ir, the recall-GAINING
        # half): the `_TYPE_MATTERS_LANE` Enchantment count/grant/trigger DOERs ("for
        # each enchantment you control" / "enchantments you control have …" / "whenever
        # an enchantment enters"), the Enchantment make_token / sac-payoff DOER
        # (Bargain- gated by `'Permanent' not in card_types` — the shared sac arm, CR
        # 702.166a), the type-gate condition arm ("if you control an enchantment"), the
        # becomes- Enchantment / type-recursion / type-tutor arms, the Aura-subtype
        # "loose enchantments member" arm (Auras are enchantments), and the type_line
        # membership arm ("if 'enchantment' in type_line" — byte-identical to the
        # deleted membership producer). These ADD +95 ir_only recall the brittle oracle
        # regex MISSED — the Licids that "become an Aura enchantment"
        # (Gliding/Nurturing/Calming Licid), the enchantment-creature / Aura / Glimmer
        # token makers (Aerie Worshippers, Fated Intervention, Tunnel Surveyor), Aura
        # recursion (Nomad Mythmaker, Retether, Storm Herald), enchantment tutors /
        # recursion (Plea for Guidance, Triumphant Reckoning), affinity-for-enchantments
        # (Brine Giant), single-type "sacrifice an enchantment" outlets (Faith Healer,
        # Auratog, Phantatog), and "if you control an enchantment" conditions
        # (Flutterfox, Blood-Cursed Knight, Lagonna-Band Elder) — every one a real
        # enchantment-population care. The Bargain symmetric-sac gate keeps the lane
        # shut for the ~20 "sacrifice an artifact, ENCHANTMENT, or token" alt-cost cards
        # (Torch the Tower, Beseech the Mirror) — GONE on this base, not over-fires.
        #
        # BYTE-IDENTICAL KEPT-MIRROR. phase carries NO clean shape for the oracle-idiom
        # family the deleted _HAND_FLOOR regex read (enchantment tutors /
        # recursion-from- graveyard / "enchantment card in your hand" miracle-grant /
        # Role-token makers), so a structural-only migration would LOSE 15 genuine
        # enchantment-deck cards (the Role-token makers Royal Treatment / Become Brutes
        # — Roles ARE Aura enchantments; Yenna; Rite of Harmony's constellation;
        # Aminatou's "enchantment card in your hand"; enchantment recursion Relive the
        # Past / Reconstruct History). _ENCHANTMENTS_MATTER_MIRROR (the deleted
        # _HAND_FLOOR producer ALONE — there is NO dedicated enchantment SWEEP_DETECTORS
        # row, unlike artifacts' "if you control an artifact" row, so
        # len(SWEEP_DETECTORS) stays 36) runs PER-CLAUSE over the reminder-stripped
        # kept_oracle, recovering all 15 byte-identically. add() dedups vs the
        # structural arm.
        #
        # FLOOR-DISABLED RESIDUAL (commander-legal, _IR_FLOOR_LANES=frozenset(), the new
        # IR arms + the byte-identical mirror vs the deleted-regex base — floor +
        # type_line membership): both==3718, ir_only==105 (pure recall GAIN, all genuine
        # — the +95 payoff recall plus the membership-arm overlap), regex_only==0 (the
        # 15-card tail recovered byte-identically). SCOPE PARITY holds — IR and regex
        # both fire scope 'you' ONLY (no scope regression). floor-mirror-dep == 0
        # (enchantments_matter is NOT an _IR_FLOOR_LANE — a structural type-matters
        # lane).
        #
        # VOLTRON. The deleted HIGH-confidence _HAND_FLOOR producer (scope 'you')
        # counted toward `has_other_plan`, silencing the spurious commander-damage
        # voltron tell on an enchantments body that is NOT a vanilla beater (Yenna,
        # Sythis, Calix). The migrated IR arm is BROADER (+95), so a BYTE-IDENTICAL
        # _ENCHANTMENTS_MATTER_PLAN_MIRROR in _signals_regex (the same
        # ENCHANTMENTS_MATTER_REGEX — the lane mirror was NOT narrowed, unlike
        # artifacts' affinity branch) re-supplies the regex-path voltron silence
        # EXACTLY. FILE-SWAP voltron delta == 0.
        #
        # FILE-SWAP no-flood (base 333f2a6 vs edits, commander-legal hybrid): ONLY
        # enchantments_matter moves (3728 → 3823, +95 net = the ir_only recall GAIN; the
        # 15-card tail was already regex-served in base, now mirror-served), 0
        # artifacts_matter / type_matters / clue_matters / vehicles_matter / treasure /
        # food / constellation drift, voltron 2342 → 2342 (delta 0). SWEEP_DETECTORS
        # stays at 36 (no enchantment row existed to keep or delete).
        # enchantments_matter added to MIGRATED_KEYS; both regex producers deleted (the
        # _HAND_FLOOR oracle regex + the type_line membership, the latter reproduced by
        # the IR membership arm); the serve spec stays hand-registered. CR 205.2 / 303 /
        # 303.7 / 207.2c.
        "enchantments_matter",
        # ADR-0027 — landfall (the LAND-ETB payoff axis: a card that CARES when a land
        # enters — the "Landfall —" ability word (CR 207.2c), the keyword-LESS
        # "whenever a land you control enters" trigger, the extra-land STATIC ("play N
        # additional lands" — Azusa, Dryad of the Ilysian Grove), and land RECURSION
        # from the graveyard (Crucible of Worlds, Splendid Reclamation, Titania) that
        # replays lands for repeat landfall). MIGRATED VIA A STRUCTURAL ARM + A
        # BYTE-IDENTICAL KEPT-MIRROR (signals-only, NO sidecar bump).
        #
        # STRUCTURAL ARM (recall GAIN). phase DOES carry the land-ETB trigger (a
        # Trigger whose subject is a Land — the "Batch 14 — landfall" arm fires
        # `ev == "etb" and "Land" in tsubs`). That arm ADDS +5 ir_only recall the bare
        # substring regex MISSED: the DISJUNCTIVE / qualified land-ETB triggers —
        # "this land or another land you control enters" (Field of the Dead), "a land
        # you control enters from exile" (Faldorn), "a nonbasic land an opponent
        # controls enters" (Spectrum Sentinel), "one or more lands enter under an
        # opponent's control" (Deep Gnome Terramancer), and the transform-on-land-ETB
        # (Twists and Turns) — all genuine land-ETB payoffs. So this is NOT a
        # structural-only NOR a mirror-only migration.
        #
        # WHY THE MIRROR (recall the structural arm cannot reach). phase carries NO
        # structural shape for the OTHER three branches of the deleted producer: the
        # "Landfall —" ability word as a CONDITION ("if you had a land enter this
        # turn" — Searing Blaze, Groundswell, Quarry Beetle), the extra-land STATIC
        # ("play N additional lands" — 30 cards), and land RECURSION ("play lands from
        # your graveyard" / "return … lands … from your graveyard to the battlefield"
        # — 32 cards). A structural-only migration would LOSE 78 genuine cards, so the
        # lane ALSO rides _LANDFALL_MIRROR in _signals_ir — the EXACT deleted lambda
        # (the three regex-expressible branches pinned as LANDFALL_REGEX in
        # _sweep_detectors: the "landfall" ability word, "play N additional lands", and
        # the two land-recursion forms, PLUS the "whenever a land" & "enter"
        # SUBSTRING-AND checked inline, which no single regex expresses) run PER-CLAUSE
        # over the reminder-stripped kept_oracle, add()-deduped with the structural arm.
        #
        # Floor-disabled residual vs the deleted producer (commander-legal,
        # _IR_FLOOR_LANES=frozenset()): the STRUCTURAL-ONLY arm vs the deleted regex was
        # both==179, ir_only==5, regex_only==78 — the 78 regex_only are ALL genuine (the
        # ability-word-condition / extra-land / land-recursion families phase has no
        # shape for), so the mirror recovers them byte-identically (257-card producer
        # set reproduced EXACTLY: 0 miss, 0 extra). Post-migration IR (structural +
        # mirror) ⊇ original-regex over the corpus: 0 lost, +5 gained (every ir_only
        # sample verified vs ACTUAL Scryfall oracle). floor-mirror-dep == 0 (landfall is
        # NOT an _IR_FLOOR_LANE).
        #
        # VOLTRON: the deleted producer FORCED scope 'you' (so every firing was HIGH-
        # confidence), feeding has_other_plan — a landfall / extra-land / land-recursion
        # ENGINE is a plan, not a vanilla beater. Because the producer was
        # unconditionally HIGH, a flat byte-identical reproduction (_landfall_is_plan in
        # _signals_regex — the LANDFALL_REGEX branches + the substring-AND, per-clause
        # over the reminder-STRIPPED text) restores the exact silence set — NOT
        # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (+5) and that route
        # would over-silence the recall-gain bodies. FILE-SWAP voltron delta == 0,
        # verified over the full commander-legal corpus. CR 207.2c / 305 / 903.10a.
        "landfall",
        # ADR-0027 — mill_matters (the self-mill / mill-payoff axis: a card with the
        # Mill keyword action — CR 701.13, "put the top N cards of a library into its
        # owner's graveyard". scope "any": SELF-mill — you mill yourself to fuel a
        # graveyard-value engine — OR an OPPONENT mill — a wincon / disruption).
        # MIGRATED VIA THE KEYWORD ROUTE ONLY (signals-only, NO sidecar bump) — NOT a
        # structural arm, NOT a kept-mirror.
        #
        # THE REGEX PRODUCER WAS THE Mill-KEYWORD PRESET ALONE. mill_matters was
        # produced regex-side SOLELY by _PRESET_KEYWORD_SIGNALS['mill'] — the Scryfall
        # `Mill`-keyword preset (get_preset("mill").keywords == ("Mill",)). Verified
        # over the commander-legal corpus: ALL 555 regex fires carry the `Mill` keyword,
        # 0 keyword-less. So the producer is a pure keyword-array lookup, with no oracle
        # regex.
        #
        # WHY KEYWORD-ROUTE, NOT THE EFFECT-CATEGORY DOER. mill_matters was ALSO emitted
        # IR-side by the _DOER_EFFECT_KEYS['mill'] doer arm (phase's `mill` effect
        # category). But that arm OVER-FIRES: floor-disabled residual (commander-legal,
        # _IR_FLOOR_LANES=frozenset(), the DOER arm vs the deleted regex) is both==555,
        # regex_only==0, ir_only==3 — and ALL 3 ir_only are phase MISLABELS, not mill:
        # Bone Dancer ("put the top creature card of defending player's graveyard onto
        # the battlefield" — opp-GY→battlefield reanimation, no library→graveyard),
        # Scroll Rack ("Exile … from your hand … Put that many cards from the top of
        # your library into your hand …" — library↔hand swap + reorder), and Soldevi
        # Digger ("Put the top card of your graveyard on the bottom of your library" —
        # GY→library, the INVERSE of mill). None carries the `Mill` keyword; none is a
        # CR-701.13 mill. And there is NO keyword-LESS GENUINE mill in the corpus
        # (Scryfall tags every real mill with the keyword — 0 keyword-less mill-text
        # cards). So the doer arm adds ONLY over-fires and zero genuine recall. The
        # _DOER_EFFECT_KEYS['mill'] entry is therefore DELETED (the `mill` effect
        # category STILL opens graveyard_matters via the separate broader arm), and the
        # lane rides _IR_KEYWORD_MAP['mill'] — the SAME Scryfall `Mill` keyword array
        # the deleted preset read. The IR keyword route is BYTE-IDENTICAL to the deleted
        # regex producer (commander-legal: both==555, ir_only==0, regex_only==0), so NO
        # mirror is needed.
        #
        # SCOPE PARITY. The deleted preset forced scope "any"; the keyword route fires
        # scope "any"; the doer fired scope "any" — 0 scope mismatches over the 555
        # both-fire cards (self vs opponent mill both ride the single "any" scope, as
        # the regex producer did).
        #
        # VOLTRON. The deleted preset fired HIGH-confidence (the default add()
        # confidence) and counted toward has_other_plan — a mill engine is a plan, not a
        # vanilla beater, and a mill creature's library→graveyard action lives only in
        # its `Mill` keyword reminder (stripped from `text`, so no PLAN-mirror can see
        # it). A byte-identical `"mill" in card.keywords` gate term in _signals_regex
        # re-supplies the regex-path commander-damage voltron silence directly (the
        # lifelink/proliferate keyword-array precedent) — NOT _VOLTRON_SILENCING_PLAN_
        # KEYS. FILE-SWAP no-flood (base 333f2a6 vs edits, baked sidecar over 30969
        # commander-legal, hybrid path): mill_matters is BYTE-IDENTICAL (555 → 555 —
        # the keyword route reproduces the regex preset exactly; the pre-migration
        # hybrid already took mill_matters from the regex path, so leaving the doer arm
        # in would have ADDED the 3 over-fires — dropping it prevents that);
        # graveyard_matters
        # (4063), reanimator (135), creature_recursion (304) drift 0; voltron_matters
        # delta 0 (3010 → 3010); 0 other-key drift across all 298 keys. CR 701.13 /
        # 903.10a.
        "mill_matters",
        # ADR-0027 magecraft_matters — migrated to the Card IR via a BYTE-IDENTICAL
        # keyword-array route (the saddle / lifelink / mill / proliferate precedent),
        # signals-only, NO sidecar bump. STRUCTURAL ANCHOR: the Scryfall `Magecraft`
        # keyword array via _IR_KEYWORD_MAP['magecraft'] — the SAME field the deleted
        # _PRESET_KEYWORD_SIGNALS['magecraft'] preset read (get_preset("magecraft").
        # keywords == ("Magecraft",), so the IR keyword predicate `"magecraft" in
        # card.keywords` is byte-identical to the preset's `card_kws & {"magecraft"}`).
        # Magecraft is an ability word (CR 207.2c — "whenever you cast or copy an
        # instant or sorcery spell"); its trigger lives in stripped reminder text, so a
        # vanilla-keyword body fires NO structural cast Effect — the keyword array is
        # the only clean anchor (no mirror, no doer arm needed). NO RESIDUAL: commander-
        # legal, floor-disabled, by oracle_id — both == 29, ir_only == 0, regex_only ==
        # 0 (every magecraft card carries the keyword; 0 keyword-less). All 29 are
        # genuine Strixhaven spellslinger payoffs (Archmage Emeritus, Storm-Kiln Artist,
        # Veyran, the Apprentice/Pledgemage cycles, the two MDFC commanders Extus and
        # Jadzi whose front face carries the keyword). SCOPE PARITY: deleted preset
        # forced scope "you"; the keyword route fires scope "you" — 0 mismatches.
        #
        # VOLTRON. The deleted preset fired HIGH-confidence (the default add()
        # confidence) and so counted toward has_other_plan. But the commander-damage
        # voltron membership tell already stays silenced WITHOUT compensation: every
        # magecraft creature carries another high-confidence plan (notably the
        # co-firing spellcast_matters — magecraft IS "whenever you cast a spell", so the
        # spellcast detector matches the same bodies). Verified: removing magecraft_
        # matters from the regex set flips has_other_plan for 0 of the 29 cards, and 0
        # magecraft creatures have magecraft_matters as their sole plan. Added to
        # signals._VOLTRON_SILENCING_PLAN_KEYS for the byte-identical keyword-move
        # convention (inert here — 0 leaks — but future-proofs a hypothetical
        # plan-less vanilla magecraft creature). File-swap: voltron_matters 3010 → 3010,
        # only magecraft_matters moves (29 → 29), all 297 sibling keys drift 0. The
        # spellslinger serve spec in signal_specs.py (the _SPELLSLINGER_SPEC bound to
        # ("magecraft_matters","you")) is independent of the deleted preset and
        # survives. CR 207.2c / 903.10a.
        "magecraft_matters",
        # ADR-0027 — land_destruction (the LD-support build-around axis: the Armageddon/
        # Numot stax-LD plan — own-land recursion to survive symmetric LD, land-loss
        # punishers; CR 305.6). MIGRATED VIA A BYTE-IDENTICAL MEMBERSHIP-GATED KEPT-
        # MIRROR (signals-only, NO sidecar bump) — NOT the broad `destroy`/Land
        # structural arm.
        #
        # THE REGEX PRODUCER WAS A CREATURE-COMMANDER CROSS-OPEN, NOT A PER-CARD
        # DETECTOR. land_destruction was produced regex-side SOLELY by the
        # `extract_signals` include_membership block: a creature whose own oracle says
        # "destroy [up to N] target land(s)" (Numot, Goblin Settler, Demonic Hordes — a
        # repeatable LD ENGINE) opens the LD support lane, scope 'you', LOW confidence.
        # It was gated creature + include_membership SO A ONE-SHOT LD SPELL among the 99
        # (Stone Rain, Armageddon) is NOT mistaken for the deck's plan (the canonical
        # test_numot_repeatable_land_destruction_opens_lane: Numot opens it, Stone Rain
        # does NOT). 23 commander-legal cards, all creatures.
        #
        # WHY THE MEMBERSHIP MIRROR, NOT THE STRUCTURAL ARM. phase DOES carry a
        # structural shape — a `destroy` Effect whose target Filter is Land-typed (the
        # `if "Land" in ftypes` arm in extract_signals_ir). But that broad per-card arm
        # fires HIGH on EVERY destroy-Land card — every Stone Rain / Wasteland / Strip
        # Mine / Armageddon (+143 over commander-legal, floor-disabled by oracle_id) —
        # flooding the DECK-PLAN lane with one-shot LD spells and utility lands the
        # cross-open intentionally excluded, AND flipping LOW→HIGH confidence. All 143
        # are GENUINE land destruction, but the lane's ROLE is the LD-support
        # build-around cross-open (open the lane when the COMMANDER is an LD engine),
        # not a per-card "this destroys a land" label — so the broad arm is the WRONG
        # producer for this lane. The broad structural `land_destruction` add is REMOVED
        # (it was DEAD pre-migration — the hybrid dropped the unmigrated IR
        # land_destruction, so it never reached production; nothing else reads it, and
        # removal_matters' own land-subtype exclusion — Land ∉ _PERMANENT_TYPES — is
        # independent of it). The lane rides the membership-gated _LAND_DESTRUCTION_
        # MIRROR arm (LAND_DESTRUCTION_REGEX over the reminder-stripped kept_oracle,
        # creature + include_membership gated, LOW conf — the deleted _LAND_DESTRUCTION_
        # RE pattern, pinned in _sweep_detectors), reproducing the deleted cross-open
        # BYTE-IDENTICALLY (commander-legal, floor-disabled by oracle_id: regex==mirror,
        # both==23, regex_only==0, ir_only==0). NO mirror is needed beyond it.
        #
        # SCOPE PARITY. The deleted cross-open forced scope 'you' / LOW conf; the mirror
        # fires scope 'you' / LOW conf — 0 scope/confidence mismatches over the 23
        # both-fire cards.
        #
        # VOLTRON. The deleted cross-open fired LOW confidence and NEVER fed
        # has_other_plan (which requires confidence=='high'), so it silenced NO
        # commander-damage voltron tell. Dropping it leaks nothing — NO
        # _LAND_DESTRUCTION_PLAN_MIRROR, NOT _VOLTRON_SILENCING_PLAN_KEYS. FILE-SWAP
        # no-flood (base b723a76 vs edits, baked sidecar over commander-legal, hybrid
        # path): land_destruction is BYTE-IDENTICAL (23 → 23 — the membership mirror
        # reproduces the cross-open exactly); voltron_matters delta 0 (3010 → 3010);
        # siblings land_sacrifice_matters / land_exchange / removal_matters / stax_taxes
        # drift 0; 0 other-key drift across all 298 keys. CR 305.6 / 903.10a.
        "land_destruction",
        # ADR-0027 — discard_matters (the SELF-discard payoff / discard-as-enabler
        # avenue: a loot/rummage outlet — "draw N cards, then discard" (Careful
        # Study, Merfolk Looter, Faithless Looting, Alpharael) — PLUS the discard
        # PAYOFF — Madness (CR 702.35 discard-to-cast: Basking Rootwalla, Fiery
        # Temper), "whenever YOU / a player discards" (Asylum Visitor, Confessor,
        # Spirit Cairn), and "when an opponent causes YOU to discard this card"
        # (Sand Golem, Psychic Purge, Orvar). scope "you"). MIGRATED VIA A
        # SCOPE-GATED STRUCTURAL ARM + a byte-identical LOOT kept-mirror + a voltron
        # _PLAN_MIRROR. NO sidecar bump (the v20 projection already emits the
        # `discarded` trigger event the structural arm reads).
        #
        # STRUCTURAL ARM (scope-gated). extract_signals_ir fires discard_matters
        # scope "you" on a `discarded` trigger with trig.scope != "opp". The gate is
        # the discriminator: phase parses a self-discard payoff ("whenever you
        # discard", Madness's discard-this-card-into-exile, "when an opponent causes
        # you to discard this card") as scope 'you' and a symmetric "whenever a
        # player discards" as scope 'any' — both KEPT; a "whenever an OPPONENT
        # discards" punisher is scope 'opp' and is the SEPARATE opponent_discard lane
        # (Megrim, Liliana's Caress, Waste Not, Tinybones Bauble Burglar, Nath,
        # Sangromancer) the deleted regex deliberately excluded — the loot regex never
        # matched "whenever an opponent discards". The PRE-migration un-gated arm
        # (fired discard_matters on EVERY discarded trigger) OVER-fired on those opp-
        # discard punishers; the gate drops them while KEEPING the 74 genuine
        # you/any-scoped self-discard payoffs the loot-only regex missed.
        #
        # LOOT KEPT-MIRROR (recall recovery, NO sidecar bump). The deleted regex
        # producer was the _LOOT_FULLTEXT_RE full-text loot/rummage detector ("draw N
        # cards[.,] then/you/may discard" — Careful Study, Merfolk Looter), a
        # draw-Effect-then-discard-Effect co-occurrence with NO `discarded` trigger.
        # A byte-identical discard_matters row in signals._IR_KEPT_DETECTORS
        # reproduces the EXACT deleted producer (the same _LOOT_FULLTEXT_RE) over the
        # reminder-STRIPPED kept_oracle — byte-identical to the deleted producer's
        # `re.sub(r"\([^)]*\)", " ", …)`-stripped input (and joining DFC faces via
        # get_oracle_text, so the back-face loot lives — Careful Study on Spellbook
        # Seeker's back). The loot regex never matches an opp-discard punisher, so it
        # re-introduces ZERO over-fire. The serve spec stays hand-registered in
        # signal_specs.py (("discard_matters","you")).
        #
        # GATES. floor-mirror-dep == 0 (discard_matters is NOT an _IR_FLOOR_LANE — it
        # was a hand-written _LITERAL_ADD producer, like the sibling draw_matters /
        # opponent_discard). FLOOR-DISABLED residual vs the deleted regex (commander-
        # legal, dedupe oracle_id, _IR_FLOOR_LANES=frozenset()): COMBINED struct +
        # loot mirror gives both == 277, regex_only == 0 (NO recall lost), ir_only ==
        # 74 (all genuine you/any-scoped self-discard payoffs the loot-only literal-
        # regex missed: 59 Madness, 4 symmetric "whenever a player discards", 9 "opp
        # causes you to discard this card", 2 "when you discard"). SCOPE PARITY: 0
        # mismatch on the 277 both-fire (both "you"). opponent_discard (the forced-
        # OPPONENT-discard EFFECT lane) is DISJOINT — it keys on the `discard` EFFECT
        # scope 'opp', not the `discarded` TRIGGER — so it does NOT drift.
        #
        # VOLTRON. The deleted regex producer fired HIGH-confidence (scope 'you') and
        # fed has_other_plan (discard_matters is not in _GENERIC_KEYS /
        # _VOLTRON_COMPAT_KEYS; a loot/discard engine is no vanilla beater), so a
        # byte-identical _DISCARD_MATTERS_PLAN_MIRROR in _signals_regex re-supplies the
        # commander-damage voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, since
        # the combined IR arm is BROADER (+74 ir_only) and the silencing-keys path
        # would over-silence those payoff bodies. Restores has_other_plan for ALL
        # cards regardless of IR/regex mode (FILE-SWAP voltron delta 0). CR 702.35
        # (madness) / 120.1 (draw) / 903.10a (voltron).
        "discard_matters",
        # ADR-0027 — second_spell_matters (the SPECIFIC "whenever you cast your
        # second spell each turn" payoff — Saruman of Many Colors, Aria-of-Flame-
        # adjacent Storm-lite; the Dualcast "second spell ... costs {2} less"
        # discount; the "third/fourth spell of a turn" Erayo-family count trigger,
        # CR 601 cast events) now fires from the Card IR instead of its oracle-regex
        # producer. NO sidecar bump (the kept-mirror reads the Scryfall oracle the
        # sidecar already carries; no new projection field).
        #
        # KEPT-MIRROR, NOT A STRUCTURAL ARM. This is a SPECIFIC trigger — the
        # "second spell EACH turn" counter — distinct from the broad
        # spellcast_matters (the magecraft / "whenever you cast a spell" lane, which
        # is DEFERRED, NOT conflated). phase v0.1.19 parses "Whenever you cast your
        # second spell each turn" as a bare `cast_spell` trigger (event=cast_spell,
        # scope=you, raw='') — IDENTICAL to a plain magecraft trigger, with NO
        # "second spell" qualifier in the structure (verified on Saruman: the
        # ability's Trigger.event=='cast_spell', no count). So a structural
        # cast_spell arm CANNOT tell the second-spell payoff from the broad
        # spellcast payoff — it would either flood spellcast bodies into this narrow
        # lane or vice-versa. The qualifier lives ONLY in the oracle text phase
        # under-structures, so the lane fires from a byte-identical
        # _SECOND_SPELL_MIRROR in signals._IR_KEPT_DETECTORS reproducing the EXACT
        # deleted _FLOOR_DETECTORS regex ("second spell you cast (each|this) turn" |
        # "cast your second spell" | "(second|third|fourth|fifth) spell (you cast|of
        # (a|each|that) turn)" | "cast two or more spells") over the reminder-
        # STRIPPED kept_oracle (byte-identical to the deleted floor producer's
        # per-clause reminder-stripped input — no `[^.]` cross-sentence span, so
        # full-text == per-clause). The serve spec stays hand-registered in
        # signal_specs.py (("second_spell_matters","you")).
        #
        # FLOOR→KEPT. second_spell_matters WAS an _IR_FLOOR_LANE (the IR path reused
        # the production floor Detector); it is REMOVED from _IR_FLOOR_LANES and the
        # _FLOOR_DETECTORS source tuple is deleted — floor-mirror-dep -> 0. FLOOR-
        # DISABLED residual vs the deleted regex (commander-legal, dedupe oracle_id,
        # _IR_FLOOR_LANES=frozenset()): both == 92, regex_only == 0, ir_only == 0 —
        # BYTE-IDENTICAL, no recall lost, no over-fire. SCOPE PARITY: all 92 fire
        # scope "you" (the floor producer's forced scope), 0 mismatch. The sibling
        # lanes (spellcast_matters / magecraft_matters / typed_spellcast /
        # storm_matters) are DISJOINT — they key on different producers (the
        # cast_spell payoff trigger / typed_spellcast subject detector / a separate
        # storm regex) — so they do NOT drift.
        #
        # VOLTRON. The deleted floor producer fired HIGH-confidence (scope 'you') and
        # fed has_other_plan (second_spell_matters is not in _GENERIC_KEYS /
        # _VOLTRON_COMPAT_KEYS; a second-spell Storm-lite engine is no vanilla
        # beater). Because the kept-mirror is BYTE-IDENTICAL (IR == regex == 92, no
        # broadening), second_spell_matters is added to _VOLTRON_SILENCING_PLAN_KEYS
        # so the hybrid re-silences the spurious commander-damage membership tell
        # from the IR re-supply — restoring pre-migration behavior. FILE-SWAP voltron
        # delta 0. CR 601 (cast) / 903.10a (voltron).
        "second_spell_matters",
        # ADR-0027 — land_sacrifice_matters (the land-SACRIFICE archetype axis: a card
        # paying an ongoing land-sac cost ("sacrifice [this] unless you sacrifice a
        # land" — Gitrog, Mana Vortex), drawing/growing when lands hit the graveyard
        # ("whenever one or more land cards are put into your graveyard" — Gitrog,
        # Titania, Slogurk, Crawling Sensation), or offering a repeatable "Sacrifice a
        # land:" OUTLET — Zuran Orb, Sylvan Safekeeper, Squandered Resources; CR
        # 701.16). MIGRATED VIA A BYTE-IDENTICAL kept WORD MIRROR (signals-only, NO
        # sidecar bump) — NOT a structural arm.
        #
        # phase carries NO STRUCTURAL FORM for this lane. FLOOR-DISABLED residual over
        # the commander-legal corpus (by oracle_id, _IR_FLOOR_LANES=frozenset()): the
        # structural IR emits land_sacrifice_matters on ZERO cards. There is no
        # `add("land_sacrifice_matters", ...)` anywhere in extract_signals_ir — the
        # you-sacrifice arm at ~line 5560 deliberately routes a land-ONLY sac SUBJECT
        # AWAY from sacrifice_matters (`e.subject.card_types != ("Land",)`) but never
        # re-homes it to land_sacrifice, and phase scatters the payoff/cost forms
        # across categories it never unifies. So the lane fired SOLELY from the deleted
        # _HAND_FLOOR regex producer (66 commander-legal cards, ALL scope 'you', HIGH
        # confidence). It was a _IR_FLOOR_LANE (the production floor re-ran the regex on
        # the IR path); both the floor membership and the _HAND_FLOOR producer are
        # removed.
        #
        # BYTE-IDENTICAL KEPT WORD MIRROR. The deleted producer was a per-card
        # Detector run PER-CLAUSE over the reminder-stripped, DFC-joined oracle. The
        # EXACT pattern (LAND_SACRIFICE_REGEX, pinned in _sweep_detectors) run FLAT over
        # the same reminder-stripped kept_oracle in extract_signals_ir's
        # _IR_KEPT_DETECTORS loop (scope 'you', HIGH conf) reproduces the deleted
        # producer BYTE-IDENTICALLY: the four arms' `[^.]*` anchors never cross a clause
        # boundary and no card's match is split by a `;`/`\n` only (commander-legal:
        # flat==per-clause==66, 0 gain, 0 loss; floor-disabled residual: both==66,
        # regex_only==0, ir_only==0). Distinct from land_destruction (DESTROY a land —
        # CR 305.6) and land_exchange (swap CONTROL of a land). land_sacrifice_matters
        # was NEVER a SWEEP key, so no SWEEP row is touched (len stays 36). The serve
        # spec stays hand-registered (("land_sacrifice_matters","you") in signal_specs)
        # and is independent of the producer.
        #
        # SCOPE PARITY. The deleted producer forced scope 'you' / HIGH conf; the mirror
        # fires scope 'you' / HIGH conf — 0 scope/confidence mismatches over the 66
        # both-fire cards.
        #
        # VOLTRON. The deleted producer fed has_other_plan (HIGH, scope 'you', NOT in
        # _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious commander-damage
        # voltron tell on a land-sac creature commander (Slogurk, Titania, Uurg, The
        # Gitrog Monster — no vanilla beater). Because the IR re-supply IS this byte-
        # identical mirror (IR==regex==66), the hybrid re-silences via
        # _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — no broadening, no over-silence —
        # matching the lands_matter / draw_matters kept-mirror precedent; NO
        # _LAND_SACRIFICE_PLAN_MIRROR. FILE-SWAP no-flood (base 6f84483 vs edits, baked
        # sidecar over commander-legal, hybrid path): land_sacrifice_matters is BYTE-
        # IDENTICAL (66 → 66); voltron_matters delta 0 (3010 → 3010); siblings
        # land_destruction / land_exchange / sacrifice_matters / ramp_matters drift 0; 0
        # other-key drift across all 298 keys. CR 701.16 / 903.10a.
        "land_sacrifice_matters",
        # ADR-0027 — opponent_discard (the forced-OPPONENT-discard / hand-attack
        # avenue — "target/each player discards" hand-attack (Mind Rot, Hymn to
        # Tourach, Mind Twist, Stupor), the symmetric upkeep-discard forcers
        # (Bottomless Pit, Oppression, Necrogen Mists), AND the discard-MATTERS
        # PAYOFFS that trigger on an opponent HAVING discarded ("whenever an opponent
        # discards" — Megrim, Liliana's Caress, Waste Not, Nath, Sangromancer; "if an
        # opponent discarded a card this turn" — Tinybones, Bauble Burglar). scope
        # "opponents"). This is the DISJOINT SIBLING of discard_matters: opponent_
        # discard keys on the forced-discard EFFECT scope 'opp' (or the opp-discard
        # PAYOFF), NOT the `discarded` self-discard TRIGGER (scope != 'opp') the
        # discard_matters lane reads. MIGRATED VIA A STRUCTURAL ARM + a byte-identical
        # word mirror. NO sidecar bump (the v20 projection already emits the
        # `discard` effect scope 'opp' the structural arm reads).
        #
        # STRUCTURAL ARM. extract_signals_ir fires opponent_discard scope "opponents"
        # on a `discard` EFFECT with scope == "opp" (Leshrac's Sigil, Thought-Stalker
        # Warlock, Robber Fly, Doomsday Specter, Laquatus's Creativity — the 7 genuine
        # forced-opp-discards the loot-only literal-regex missed, each verified vs
        # actual Scryfall oracle). But phase UNDER-STRUCTURES the lane three ways: a
        # directed "target player discards" parses the discard effect scope 'any' (the
        # affected player carries no controller — Mind Rot, Hymn to Tourach, Mind
        # Twist), a symmetric "each player discards" parses scope 'you'/'any'
        # (Bottomless Pit), and a "whenever an opponent discards" PAYOFF parses a
        # `discarded` TRIGGER (scope opp) with NO discard effect at all (Megrim, Waste
        # Not, Tinybones). The structural-arm-alone catches only 76 of 433; the rest
        # need a kept word mirror.
        #
        # KEPT WORD MIRROR (recall recovery, NO sidecar bump). A byte-identical
        # _OPPONENT_DISCARD_MIRROR row in signals._IR_KEPT_DETECTORS reproduces the
        # EXACT deleted _HAND_FLOOR regex (the "(each|target|that) player/opponent
        # discards" forcer OR the "opponent discarded a card this turn" / "whenever an
        # opponent/a player discards" payoff) over the reminder-STRIPPED kept_oracle —
        # byte-identical to the deleted producer's `re.sub(r"\([^)]*\)", " ",
        # …)`-stripped input (and joining DFC faces via get_oracle_text). The regex's
        # `[^.]{0,20}` arm never crosses a sentence, so the flat .search == the floor
        # detector's per-clause path. Combined (struct OR mirror) reproduces the
        # deleted regex with regex_only==0 (NO recall lost) + 7 genuine scope-'opp'
        # effect recall gains (the directed/forced opp-discards phase structures as a
        # `discard` effect but the literal regex's word list missed). 0 over-fire (the
        # mirror IS the regex). SCOPE PARITY: 0 mismatch on the 433 both-fire (all
        # "opponents").
        #
        # GATES. floor-mirror-dep == 0 (opponent_discard is NOT an _IR_FLOOR_LANE — it
        # was a hand-written _HAND_FLOOR producer; it lives in IR_SLICE_KEYS, the
        # structural-arm slice). FLOOR-DISABLED residual vs the deleted regex
        # (commander-legal, dedupe oracle_id, _IR_FLOOR_LANES=frozenset()): both ==
        # 433, regex_only == 0, ir_only == 7. discard_matters (the SELF-discard lane)
        # is DISJOINT — it reads the `discarded` TRIGGER scope != 'opp', not the
        # `discard` EFFECT scope 'opp' — so it does NOT drift.
        #
        # VOLTRON. The deleted _HAND_FLOOR producer fired HIGH-confidence (scope
        # 'opponents') and fed has_other_plan (a hand-attack engine is no vanilla
        # beater: Nath, Tinybones, Davriel), so a byte-identical
        # _OPPONENT_DISCARD_PLAN_MIRROR in _signals_regex re-supplies the commander-
        # damage voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, since the combined
        # IR arm is BROADER (+7 ir_only) and the silencing-keys path would over-silence
        # those 7 payoff bodies. Restores has_other_plan for ALL cards regardless of
        # IR/regex mode (FILE-SWAP voltron delta 0). CR 701.8a (discard) / 903.10a
        # (voltron).
        "opponent_discard",
        # ADR-0027 — kicked_spell_matters (the Kicker build-around — CR 702.33: the
        # "whenever you cast a kicked spell" PAYOFF that rewards casting a paid-kicker
        # spell — Verazol, Hallar, Rumbling Aftershocks, Roost of Drakes — PLUS the
        # "if (that|it) (spell) was kicked" CONDITION on kicker spells whose ETB effect
        # depends on the kicked state — Goblin Bushwhacker, Gatekeeper of Malakir,
        # Verix Bladewing, Bubble Snare). Now fires from the Card IR instead of its
        # oracle-regex producer. NO sidecar bump (the kept-mirror reads the Scryfall
        # oracle the sidecar already carries; no new projection field).
        #
        # KEPT-MIRROR, NOT A STRUCTURAL ARM, NOT THE KEYWORD ROUTE. Kicker is a KEYWORD
        # (CR 702.33), but this lane is the PAYOFF/CONDITION, not Kicker presence. The
        # bare `\bkicker\b`/`\bkicked\b` keyword route OVER-FIRES +171: it matches EVERY
        # card that merely HAS kicker, not the cards that care about a spell being
        # PAID-kicked (the DEFERRED note in extract_signals_ir warned exactly this). And
        # phase v0.1.19 under-structures the payoff: the "if it was kicked" trigger
        # condition has no structured tag, and the "whenever you cast a kicked spell"
        # trigger does not carry a "kicked" qualifier in the IR — so there is NO
        # structural arm that can discriminate the kicker-payoff from a plain
        # spell-cast. The qualifier survives ONLY in the oracle text, so the lane fires
        # from a byte-identical _KICKED_SPELL_MIRROR in _IR_KEPT_DETECTORS reproducing
        # the EXACT deleted _HAND_FLOOR regex ("whenever you cast a kicked spell" | "if
        # (that|it) (spell) was kicked") over the reminder-STRIPPED kept_oracle (no
        # `[^.]` cross-sentence span, so full-text == per-clause). The serve spec stays
        # hand-registered in signal_specs.py (("kicked_spell_matters","you")).
        #
        # FLOOR→KEPT. kicked_spell_matters WAS an _IR_FLOOR_LANE (the IR path reused the
        # production floor Detector); it is REMOVED from _IR_FLOOR_LANES and the
        # _HAND_FLOOR source row is deleted — floor-mirror-dep -> 0. FLOOR-DISABLED
        # residual vs the deleted regex (commander-legal, dedupe oracle_id,
        # _IR_FLOOR_LANES=frozenset()): both == 85, regex_only == 0, ir_only == 0 —
        # BYTE-IDENTICAL, no recall lost, no over-fire. All 85 fires are genuine kicker
        # payoffs/conditions (verified vs ACTUAL Scryfall oracle: 14 "whenever you cast
        # a kicked spell" payoffs incl. Verazol/Hallar/Rumbling Aftershocks/Roost of
        # Drakes; the rest "if (it|that spell) was kicked" ETB conditions on kicker
        # spells incl. the full Battlemage / Emissary / Gatekeeper cycles). SCOPE
        # PARITY: all 85 fire scope "you" (the floor producer's forced scope), 0
        # mismatch. The sibling lanes (spellcast_matters / typed_spellcast /
        # storm_matters) key on different producers and do NOT drift.
        #
        # VOLTRON. The deleted floor producer fired HIGH-confidence (scope 'you') and
        # fed has_other_plan (kicked_spell_matters is not in _GENERIC_KEYS /
        # _VOLTRON_COMPAT_KEYS; a kicker build-around is no vanilla beater). Because the
        # kept-mirror is BYTE-IDENTICAL (IR == regex == 85, no broadening),
        # kicked_spell_matters is added to _VOLTRON_SILENCING_PLAN_KEYS so the hybrid
        # re-silences the spurious commander-damage membership tell from the IR
        # re-supply — restoring pre-migration behavior (matching the
        # second_spell_matters byte-identical kept-mirror precedent). FILE-SWAP voltron
        # delta 0. CR 702.33 (kicker) / 903.10a (voltron).
        "kicked_spell_matters",
        # ADR-0027 — extra_combats (the ADDITIONAL-COMBAT-PHASE archetype axis: a card
        # granting "after this [main] phase, there is an additional combat phase" —
        # Aggravated Assault, Combat Celebrant, Seize the Day, Moraug, Aurelia, Scourge
        # of the Throne, World at War, Najeela, Illusionist's Gambit; CR 505.1a / 720)
        # now fires from the Card IR instead of its oracle-regex producer. NO sidecar
        # bump (signals-only; the supplement word mirror reads the reminder-stripped,
        # DFC-joined oracle the record already carries).
        #
        # STRUCTURAL ARM + a SUPPLEMENT BYTE-IDENTICAL kept WORD MIRROR. phase carries
        # an ACCURATE structural form: the `extra_combat` effect category fires
        # extra_combats through the _DOER_EFFECT_KEYS doer loop (scope 'you', HIGH).
        # FLOOR-DISABLED residual over the commander-legal corpus (by oracle_id,
        # _IR_FLOOR_LANES=frozenset()): the structural arm emits extra_combats on 42 of
        # the 43 commander-legal regex fires with ZERO over-fire (both==42, ir_only==0,
        # 0 scope/conf mismatch). The ONE under-structured gap is Illusionist's Gambit
        # ("After this phase, there is an additional combat phase") — phase folds the
        # whole card into a single `restriction` effect and never emits the
        # `extra_combat` category (regex_only==1). Unlike land_destruction's broad
        # structural arm (which FLOODED with one-shot LD spells), this structural arm
        # over-fires on NOTHING, so it is KEPT as the IR-native producer where phase has
        # it; the gap is recovered by a SUPPLEMENT word mirror.
        #
        # BYTE-IDENTICAL SUPPLEMENT MIRROR. The deleted producer was the `extra-combats`
        # theme PRESET (pattern `additional combat phase`) run per-clause via
        # _PRESET_REGEX_SIGNALS. The EXACT pattern (EXTRA_COMBATS_REGEX, pinned in
        # _sweep_detectors) run FLAT over the reminder-stripped kept_oracle in
        # extract_signals_ir's _IR_KEPT_DETECTORS loop (scope 'you', HIGH conf)
        # reproduces the deleted producer BYTE-IDENTICALLY: the substring carries no
        # parens and crosses no clause boundary, so flat==per-clause (commander-legal:
        # flat-mirror==per-clause-regex==43, 0 gain, 0 loss). The structural arm (42)
        # union the word mirror (43, a strict SUPERSET) == 43 == the deleted regex
        # producer EXACTLY. The `extra-combats` PRESET ITSELF survives (deck-wizard /
        # cube-wizard archetype detection use it); only the _PRESET_REGEX_SIGNALS
        # producer entry is removed. Distinct from extra_turns (CR 716), extra_upkeep /
        # extra_draw_step (CR 501.1 "additional beginning phase" — Shadow/Sphinx of the
        # Second Sun say "beginning phase", NOT "combat phase", so the substring
        # correctly skips them). extra_combats was NEVER a SWEEP key, so no SWEEP row
        # is touched (len stays 36); only the CONSTANT is pinned there. The serve spec
        # stays hand-registered (("extra_combats","you") in signal_specs) and is
        # independent of the producer.
        #
        # SCOPE PARITY. The deleted producer forced scope 'you' / HIGH conf; the
        # structural arm and the mirror BOTH fire scope 'you' / HIGH — 0 scope/conf
        # mismatches over the 43 both-fire cards.
        #
        # VOLTRON. The deleted producer fed has_other_plan (HIGH, scope 'you', NOT in
        # _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious commander-damage
        # voltron tell on an extra-combat creature commander that is NOT a vanilla
        # beater (Aurelia, Moraug, Najeela, Anzrag, Karlach). Because the IR re-supply
        # IS this byte-identical union (IR==regex==43), the hybrid re-silences via
        # _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — no broadening, no over-silence —
        # matching the land_sacrifice / draw_matters kept-mirror precedent; NO
        # _EXTRA_COMBATS_PLAN_MIRROR. FILE-SWAP no-flood (base fc02a23 vs edits, baked
        # sidecar over commander-legal, hybrid path): extra_combats is BYTE-IDENTICAL
        # (43 → 43); voltron_matters delta 0; siblings extra_turns / attack_matters /
        # untap_engine drift 0; 0 other-key drift across all 298 keys. CR 505.1a /
        # 903.10a.
        "extra_combats",
        # ADR-0027 — extra_turns (the TIME-WALK build-around axis: take-another-turn
        # payoffs and enablers — Time Warp, Temporal Manipulation, Nexus of Fate,
        # Magosi, Obeka, plus the per-extra-turn payoffs Wanderwine Prophets / Sage of
        # Hours / Medomai; CR 500.7) now fires from the Card IR instead of its oracle-
        # regex producer. NO sidecar bump (signals-only; the structural arm + kept word
        # mirror read the reminder-stripped, DFC-joined oracle the record already
        # carries). MIGRATED VIA THE STRUCTURAL `extra_turn` EFFECT ARM (already
        # wired: _DOER_EFFECT_KEYS["extra_turn"] → add("extra_turns","you") in
        # extract_signals_ir, scope 'you', HIGH conf) PLUS a byte-identical kept WORD
        # MIRROR (EXTRA_TURNS_REGEX in _IR_KEPT_DETECTORS) for the under-structured
        # tail.
        #
        # THE DELETED PRODUCER was the `extra-turns` theme PRESET (_PRESET_REGEX_SIGNALS
        # in _signals_regex) — a per-clause re.search of "take an (?:extra|additional)
        # turn" over the reminder-stripped oracle, scope 'you', HIGH conf, on 42
        # commander-legal cards.
        #
        # SCOPE PARITY. The deleted preset forced scope 'you' / HIGH; both IR producers
        # fire scope 'you' / HIGH — 0 scope/confidence mismatches over the 36 both-fire
        # cards (floor-disabled, by oracle_id).
        #
        # MIGRATE-WHEN-CLEAN. Floor-disabled residual over the commander-legal corpus
        # (by oracle_id, pure-regex vs pure-IR): both=36, ir_only=8, regex_only=6.
        #   ir_only (8, a RECALL GAIN — all genuine extra-turn cards the buggy preset
        #   MISSED): the 3rd-person "takes an extra turn" — Time Warp, Walk the Aeons,
        #   Beacon of Tomorrows, Karn's Temporal Sundering, Eon Frolicker, Timesifter —
        #   and "take TWO extra turns" — Time Stretch, Teferi Master of Time. phase
        #   structures every one as an `extra_turn` effect; the preset pattern only
        #   matched the IMPERATIVE "Take an extra turn".
        #   regex_only (6, recovered BYTE-IDENTICALLY by the EXTRA_TURNS_REGEX
        #   _IR_KEPT_DETECTORS mirror): the 6 cards where phase FOLDS "take an extra
        #   turn" into a SIBLING category, emitting no `extra_turn` effect — Chance for
        #   Glory (grant_keyword carrier), Expropriate (vote), Ichormoon Gauntlet (a
        #   CONFERRED planeswalker ability), Ral Zarek / Stitch in Time (coin_flip),
        #   Ugin's Nexus (an exile replacement). The mirror's pattern has no `[^.]*`, so
        #   flat==per-clause, and reminder-stripping keeps Perch Protection's Gift-
        #   reminder "take an extra turn" OUT. So the hybrid serves the UNION (50 = 36
        #   both + 8 structural recall-gain + 6 under-structured mirror).
        #
        # VOLTRON. The deleted preset fired HIGH conf scope 'you' and so counted toward
        # has_other_plan (extra_turns is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS),
        # silencing the spurious commander-damage voltron tell on a time-walk CREATURE
        # commander whose ONLY high plan tell is extra_turns (Timestream Navigator,
        # Lighthouse Chronologist, Wormfang Manta). Because the structural arm is
        # BROADER
        # (+8 ir_only, incl. the creature Eon Frolicker), _VOLTRON_SILENCING_PLAN_KEYS
        # would OVER-SILENCE the recall-gain bodies — so the regex path keeps a BYTE-
        # IDENTICAL _EXTRA_TURNS_PLAN_MIRROR over the reminder-stripped `text` (NOT
        # _VOLTRON_SILENCING_PLAN_KEYS), matching the landfall / ramp_matters broader-IR
        # precedent (42-card silence set, 0 Perch over-fire; FILE-SWAP voltron delta 0).
        #
        # FILE-SWAP no-flood (base fc02a23 vs edits, baked sidecar over commander-legal,
        # hybrid path): ONLY extra_turns moves (42 → 50, +8 recall gain);
        # voltron_matters delta 0; siblings extra_combats / untap_engine / time_matters
        # drift 0; 0 other-key drift across all 298 keys. The serve spec stays
        # hand-registered
        # (("extra_turns","you") in signal_specs, independent of the producer). CR 500.7
        # / 903.10a.
        "extra_turns",
        # ADR-0027 — daynight_matters (the Day/Night mechanic — CR 726, Innistrad:
        # Midnight Hunt: daybound/nightbound creatures that transform on the day↔night
        # flip, PLUS the transition payoffs — "it becomes day/night", "as long as it's
        # day/night" — Tovolar, Brimstone Vandal, The Celestus, Vadrik). Now fires from
        # the Card IR instead of its oracle-regex floor producer. NO sidecar bump (the
        # keyword arm reads the Scryfall keyword array, the doer arm reads phase's
        # `day_night` effect — both the sidecar already carries; no new projection
        # field).
        #
        # TWO STRUCTURAL ARMS, NO MIRROR. The lane splits cleanly across phase's own
        # structure: (1) the daybound / nightbound Scryfall KEYWORD via _IR_KEYWORD_MAP
        # (the 35 transforming creatures — every daybound/nightbound card carries the
        # word in its kept_oracle, 0 keyword-less keyword card); (2) the `day_night`
        # EFFECT-category doer via _DOER_EFFECT_KEYS (phase v0.1.19 structures the
        # transition — "it becomes day/night", "as long as it's day/night" — as a clean
        # `day_night` effect; 12 keyword-LESS payoffs fire this arm, plus Tovolar fires
        # BOTH). Because phase structures BOTH halves, NO kept-mirror is needed — the
        # two arms reproduce the deleted _HAND_FLOOR regex EXACTLY.
        #
        # FLOOR→KEPT. daynight_matters WAS an _IR_FLOOR_LANE (the IR path reused the
        # production floor Detector); it is REMOVED from _IR_FLOOR_LANES and the
        # _HAND_FLOOR source row is deleted — floor-mirror-dep -> 0. FLOOR-DISABLED
        # residual vs the deleted regex (commander-legal, dedupe oracle_id,
        # _IR_FLOOR_LANES=frozenset()): both == 47, regex_only == 0, ir_only == 0 —
        # BYTE-IDENTICAL, no recall lost, no over-fire (no ir_only sample to adjudicate;
        # the day_night effect-category arm fires on EXACTLY the regex set — 34 keyword-
        # only werewolves, 12 effect-only payoffs, 1 both — Tovolar). SCOPE PARITY: all
        # 47 fire scope "you" (the floor producer's forced scope; both arms emit "you"),
        # 0 mismatch. The siblings key on different producers and drift 0.
        #
        # VOLTRON. The deleted floor producer fired HIGH-confidence (scope 'you') and
        # fed has_other_plan (a daynight build-around — Tovolar — is no vanilla beater,
        # not in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS). Because the two IR arms are
        # BYTE-IDENTICAL (IR == regex == 47, no broadening), daynight_matters is added
        # to _VOLTRON_SILENCING_PLAN_KEYS so the hybrid re-silences the spurious
        # commander-damage membership tell from the IR re-supply, restoring
        # pre-migration behavior (matching the kicked_spell / second_spell precedent).
        # FILE-SWAP voltron delta 0. CR 726 (Day/Night) / 903.10a (voltron).
        "daynight_matters",
        # ADR-0027 — creature_recursion (return a CREATURE card from a graveyard, to
        # HAND or BATTLEFIELD: Raise Dead, Gravedigger, Reanimate, Hua Tuo, Meren). The
        # build-around axis for "loop a single creature" engines — they want self-
        # sacrificing creatures (Spore Frog) and ETB-value bodies. MIGRATED VIA A
        # STRUCTURAL ARM (recall GAIN) + A BYTE-IDENTICAL KEPT-MIRROR (the regex tail
        # phase doesn't structure); signals-only, NO sidecar bump.
        #
        # THE BOUNDARY vs reanimator / graveyard_matters. creature_recursion is the
        # BROAD "return a creature card from a graveyard" (GY→hand OR GY→library OR
        # GY→battlefield). It is DISTINCT from the already-migrated reanimator
        # (GY→BATTLEFIELD specifically) and from graveyard_matters (any self-graveyard
        # care). The deleted regex producer was a `_DETECTORS` row,
        # `(?:return|put|choose) (?:target|a|another)? creature card [^.]*? (in|from)
        # your graveyard`, forced scope 'you', HIGH confidence, run PER-CLAUSE over the
        # reminder-stripped oracle — 304 commander-legal cards.
        #
        # STRUCTURAL ARM (the recall GAIN). phase structures reanimation as a
        # `reanimate` Effect; the existing `cat=='reanimate' and 'Creature' in ftypes`
        # arm in extract_signals_ir fires creature_recursion scope 'you' on every
        # GY->battlefield creature reanimator. This ADDS +160 ir_only cards the brittle
        # "your graveyard" regex MISSED — the reanimation spells that say "from A
        # graveyard" / "that player's graveyard" (Reanimate, Beacon of Unrest, Exhume,
        # Sepulchral Primordial, Living Death, Twilight's Call, Storm of Souls,
        # Patriarch's Bidding) and the split/DFC reanimation halves whose top-level
        # oracle is empty (Push // Pull, Crime // Punishment, Breaking // Entering). ALL
        # +160 verified genuine creature recursion (return a creature card from a
        # graveyard to the battlefield), 0 over-fire.
        #
        # WHY ALSO A BYTE-IDENTICAL MIRROR. phase carries NO clean structural shape for
        # GY->HAND / GY->LIBRARY creature recursion (graveyard_recursion /
        # topdeck_stack, NOT reanimate) — so a structural-only migration would LOSE 132
        # genuine cards (Raise Dead, Gravedigger, Disentomb, Hua Tuo's GY->library,
        # Meren, Kolaghan's Command's GY->hand mode, Liliana the Last Hope's -2).
        # _CREATURE_RECURSION_MIRROR (the EXACT deleted regex run PER-CLAUSE over the
        # reminder-stripped kept_oracle in extract_signals_ir) recovers all 132 byte-
        # identically (commander-legal, floor-disabled by oracle_id: mirror == regex ==
        # 304, flat == per-clause, 0 miss, 0 extra). add() dedups vs the structural arm.
        #
        # SCOPE PARITY. The deleted producer forced scope 'you'; the structural arm
        # fires scope 'you'; the mirror fires scope 'you' — uniform. Reanimating from an
        # opponent's graveyard is still YOUR creature_recursion plan (you control the
        # returned creature), so 'you' is correct — 0 scope mismatches over the 172
        # both-fire cards (no _gy_scope regression, unlike graveyard_matters).
        #
        # VOLTRON. The deleted producer fired HIGH-confidence scope 'you' and so counted
        # toward has_other_plan (creature_recursion ∉ _GENERIC_KEYS / _VOLTRON_COMPAT_
        # KEYS) — a recursion ENGINE is a plan, not a vanilla beater. Because the
        # migrated IR path is BROADER (464 = 172 both + 132 mirror + 160 structural),
        # _VOLTRON_SILENCING_PLAN_KEYS would OVER-SILENCE the +160 recall-gain bodies —
        # so the regex path keeps a BYTE-IDENTICAL _CREATURE_RECURSION_PLAN_MIRROR over
        # the reminder-stripped `text` (matching the enchantments_matter / extra_turns
        # broader-IR precedent), reproducing the deleted producer's exact silence set.
        # (Empirically 0 commander-legal cards have creature_recursion as their SOLE
        # high-conf plan key, so voltron delta is 0 either way; the mirror is the
        # defensive faithful re-supply.)
        #
        # FILE-SWAP no-flood (base 59b8e79 vs edits, baked sidecar over commander-legal,
        # hybrid path): ONLY creature_recursion moves (304 → 464, +160 recall gain; the
        # 132 GY→hand/library tail was already regex-served in base, now mirror-served);
        # voltron_matters delta 0 (3010 → 3010); siblings reanimator / graveyard_matters
        # / dies_recursion / self_death_payoff drift 0; 0 other-key drift across all 298
        # keys. The serve spec stays hand-registered (("creature_recursion","you") in
        # signal_specs, independent of the producer). CR 700.4 / 903.10a.
        "creature_recursion",
        # ADR-0027 (stax pair) — stax_taxes + symmetric_stax migrated regex→Card IR.
        # Both lanes read the SAME `restriction` Effect scope (the v22 projection,
        # SIDECAR_VERSION 22): a static restriction/tax with scope=='opp' (an OPPONENT
        # static — Drannith Magistrate, Lavinia, Ghostly Prison) opens stax_taxes; one
        # with scope=='each' (a controller-NEUTRAL permanent-CLASS lock — Back to
        # Basics, Static Orb, Sphere of Resistance) opens symmetric_stax.
        # extract_signals_ir already gates the restriction arm on e.scope, so the lanes
        # never cross. The force_attack/cant_block arms also feed the pair on their
        # opp/each scope (a symmetric "all creatures attack each combat" / "creatures
        # can't block" is a table-warp lock).
        #
        # WHY A BYTE-MIRROR, NOT PURE STRUCTURAL. The structural restriction-scope arm
        # is ADJUDICATED-CORRECT but BROADER than the deleted regex (commander-legal,
        # floor-disabled by oracle_id): symmetric_stax +145 ir_only (Collector Ouphe /
        # Cursed Totem / Stony Silence ability-shutoffs; Defense Grid / Chill / Gloom /
        # Feroz's Ban symmetric cost taxes; Bedlam / Falter / Awe for the Guilds can't-
        # block table effects; Blazing Archon / Ensnaring Bridge / Moat can't-attack
        # locks; Arrest / Faith's Fetters / Ice Cage Aura lockdowns — all GENUINE
        # each-scope symmetric locks rules-lawyer-verified); stax_taxes +10 ir_only
        # (Angelic Arbiter "each opponent who cast can't attack"; Gnat Miser / Locust
        # Miser / Jin-Gitaxias hand-size taxes; Ashiok search-denial — all GENUINE
        # opponent restrictions). It also DROPS the regex over-fire: the _HAND_FLOOR
        # `creatures your opponents control` branch matched every -X/-X DEBUFF anthem
        # (Elesh Norn, Massacre Wurm, Cower in Fear), which is removal, not a
        # restriction static. CR 604.1: a static ability is "simply true", so an
        # UNQUALIFIED "Spells cost {1} more to cast" (Sphere of Resistance, Thalia)
        # taxes ALL players including the controller — phase's scope=='each' correctly
        # re-buckets these symmetric taxes the old regex wrongly forced into
        # stax_taxes(opponents). rules-lawyer-confirmed vs the actual Scryfall oracle
        # (no "your opponents").
        #
        # Because the arm is BROADER, the deleted regex is reproduced BYTE-IDENTICALLY
        # by a per-clause kept-mirror (_signals_ir, over the reminder-stripped
        # kept_oracle, the same input the deleted detectors scanned):
        # _STAX_TAXES_MIRROR from STAX_TAXES_REGEX (the union of the deleted
        # _signals_regex _DETECTORS pacify row + _HAND_FLOOR `opponents can't` /
        # `creatures your opponents control` row + the kept SWEEP row) and
        # _SYMMETRIC_STAX_MIRROR from SYMMETRIC_STAX_REGEX (the kept SWEEP row;
        # symmetric_stax had no _signals_regex producer). Both SWEEP rows stay in
        # SWEEP_DETECTORS (len 36) as the pinned source — the artifacts_matter /
        # edict_matters kept-row precedent.
        #
        # SCOPE PARITY. The deleted producers forced scope 'opponents' (stax_taxes) /
        # 'each' (symmetric_stax); the structural arm fires the same scopes off
        # e.scope=='opp'/'each'; the mirrors fire 'opponents'/'each'. 0 cross-lane scope
        # mismatches over the both-fire cards. The 53 symmetric-tax cards the old regex
        # forced into stax_taxes now ALSO carry symmetric_stax from the structural arm
        # (the serve specs treat the two lanes as one stax-piece pool, so the
        # recommendation is unchanged); the byte-mirror keeps their old stax_taxes
        # firing too (no recall lost).
        #
        # VOLTRON. Both deleted stax_taxes producers fired HIGH (forced scope
        # 'opponents') and counted toward has_other_plan (stax_taxes ∉ _GENERIC_KEYS /
        # _VOLTRON_COMPAT_KEYS). The IR is BROADER, so re-supplying via
        # _VOLTRON_SILENCING_PLAN_KEYS would over-silence the +10 recall bodies; instead
        # a byte-identical _STAX_TAXES_PLAN_MIRROR (STAX_TAXES_REGEX over reminder-
        # stripped `text`) restores the exact silence set. symmetric_stax needs NO plan
        # entry: its sole producer is the kept SWEEP row, which extract_signals still
        # fires, so its regex-path has_other_plan is intact. Neither key is added to
        # _VOLTRON_SILENCING_PLAN_KEYS. FILE-SWAP no-flood (base 77f1cc3, baked sidecar
        # v22 over commander-legal, hybrid path): ONLY stax_taxes (339 → 349) and
        # symmetric_stax (292 → 437) move; voltron_matters delta 0 (3010 → 3010);
        # siblings tapper_engine / cant_block_grant / group_hug_draw / mana_denial drift
        # 0; 0 other-key drift across all 298 keys. CR 604.1 / 118.9 / 903.10a.
        "stax_taxes",
        "symmetric_stax",
        # ADR-0027 — direct_damage + symmetric_damage_each (the two sibling lanes that
        # SHARE the v22 damage Effect, migrated atomically). The v22 projection scopes
        # the damage recipient — 'opp' ("deals N to each/target opponent" — Sizzle),
        # 'each' ("deals N to each player" — Pestilence), 'any' for creature-only bite
        # (subject=Filter(Creature) — Flame Slash) AND "any target"/player burn
        # (subject=None — Lightning Bolt) — so the shared `damage` arm can now route
        # player-reachable / each-player / creature-only THREE ways (CR 120.1 / 115.4 /
        # 102.2; rules-lawyer-verified). The old shared IR arm over-fired direct_damage
        # on ALL non-'you' damage (ir_only 1196, all creature-bite); the v22 scope gate
        # fixes it.
        #
        # direct_damage = a source that CAN deal damage to a PLAYER (a burn-them-out
        # deck). STRUCTURAL: scope 'opp'/'each' always reaches a player; scope 'any'
        # fires ONLY when the recipient is NOT creature/permanent-restricted AND the raw
        # names a player (or an "any target") — so creature-only removal (Flame Slash,
        # Pyroclasm, Star of Extinction) and the modal "deals N instead" recipient-
        # dropped clause (Fiery Impulse) and the bare "to you" drawback (Erg Raiders)
        # stay OUT. MIRROR: the byte-identical _DIRECT_DAMAGE_MIRROR (the OR of the two
        # deleted _HAND_FLOOR producers) recovers the under-structured player-reaching
        # tail phase can't read as a `damage` Effect — the damage DOUBLERS (replacement
        # effects — Furnace of Rath, Torbran), the damage-MATTERS payoffs ("whenever a
        # source you control deals damage" — The Red Terror, Tamanoa), the controller-
        # rider (Searing Blood), and the DFC/coin-flip burst burn. Commander-legal,
        # floor-disabled, by oracle_id: both == 1497 (== the exact regex total, 0 regex
        # firing lost), ir_only == 139 (ALL verified player-reachable per "no dismissal
        # without the hook" — each-player sweepers, each-opponent burn, any-target/
        # controller/them recipients, empty-Filter "to target opponent"), regex_only ==
        # 0. The flat mirror == the per-clause regex byte-identically (0 over-fire).
        # SCOPE PARITY: the deleted producers + the structural arm + the mirror all fire
        # scope 'you' (you control the source) — uniform.
        #
        # symmetric_damage_each = damage dealt to EACH player (the Pestilence / Star of
        # Extinction / Sulfurous Blast symmetric-board family). STRUCTURAL: the
        # scope=='each' arm (strictly broader-and-correct vs the deleted regex, which
        # required a literal \d+ amount — the IR catches the X-/equal-to forms it
        # missed: Earthquake, Price of Progress, Heartless Hidetsugu). MIRROR: the byte-
        # identical _SYMMETRIC_DAMAGE_EACH_MIRROR (the each-PLAYER subset of the deleted
        # SWEEP regex) recovers the coin-flip-branch tail phase drops (Volatile Rig,
        # Winter Sky). The deleted SWEEP lane's "each opponent" arm is INTENTIONALLY
        # dropped — one-sided damage is NOT symmetric (CR 102.2 — an opponent is not
        # you), so the ADR-0027 split routes those 168 each-opponent cards to
        # direct_damage (scope 'opp') instead, where their synergy is correctly re-homed
        # (verified: all 168 fire direct_damage; 0 genuine each-player card lost —
        # each_player_leak == 0). Commander-legal, floor-disabled, by oracle_id: both ==
        # 46, ir_only == 40 (ALL have "each player" text — genuine symmetric the regex's
        # \d+ gate missed), regex_only == 183 (ALL "each opponent", the intentional
        # split, re-homed to direct_damage). The flat mirror == per-clause byte-
        # identically (0 over-fire). SCOPE PARITY: deleted producer + structural arm +
        # mirror all fire scope 'each'.
        #
        # VOLTRON. Both deleted producers fired HIGH-confidence (scope 'you' / 'each')
        # and fed has_other_plan (neither is _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS — a
        # burn / symmetric-board engine is no vanilla beater). The migrated IR paths are
        # BROADER (direct +139; symmetric +40 each-player but -168 each-opponent), so
        # _VOLTRON_SILENCING_PLAN_KEYS would mis-silence — instead the byte-identical
        # _DIRECT_DAMAGE_PLAN_MIRROR (the OR of the two deleted direct producers) and
        # _SYMMETRIC_DAMAGE_EACH_PLAN_MIRROR (the FULL deleted SWEEP regex, incl. each-
        # opponent) re-supply has_other_plan over the reminder-stripped joined-face
        # `text`, reproducing the exact pre-migration silence set. The serve specs stay
        # hand-registered in signal_specs.py (direct_damage's was already independent;
        # symmetric_damage_each's keeps the old regex via _sweep_spec_with_extras(
        # regex=) since its SWEEP row was deleted). CR 120.1 / 115.4 / 102.2 / 903.10a.
        "direct_damage",
        "symmetric_damage_each",
        # ADR-0027 big-mana (v23 mana-amount projection). big_mana opens the
        # X-spell-sink avenue for a COMMANDER that makes a LOT of mana (Sol Ring,
        # rituals, big rocks, scaling dorks/lands — Selvala, Gaea's Cradle, Nykthos).
        # The deleted regex (`add {X}{Y}` | `add … for each` | `add an additional`) was
        # an include_membership, scope-'you', LOW-conf cross-open; the migrated lane
        # reads the v23 structural tell directly — a `ramp` Effect whose amount is
        # amount.factor>1 (Sol Ring 2, Dark Ritual 3, Gilded Lotus 3) OR op=="variable"
        # (Selvala / Gaea's Cradle / Nykthos devotion / Cabal Coffers count). A
        # factor==1 dork (Llanowar — "Add {G}") is one mana and is correctly EXCLUDED
        # (the v23 magnitude makes them distinguishable; the pre-v23 projection
        # collapsed every producer to amount==None). The structural arm runs in the
        # include_membership block; a byte-identical _BIG_MANA_REGEX kept mirror over
        # kept_oracle re-supplies the under-structured tail (Neheb, the Eternal's "add
        # {R} for each …" projects amount==None). Floor-disabled residual
        # (commander-legal, _IR_FLOOR_LANES=frozenset(), by oracle_id): both==362,
        # regex_only==0 (the byte-mirror reproduces the deleted regex EXACTLY —
        # kept_oracle == the regex `text`), ir_only==169 (broader-and-correct: every
        # card produces >1 mana — filter rocks/lands "add two", rituals,
        # power/devotion/count scalers — that the `{X}{Y}`/"for each"/"an additional"
        # regex never matched; all 169 verified vs Scryfall oracle, 0 over-fire). SCOPE
        # PARITY: deleted producer + structural arm + mirror all fire scope 'you', LOW
        # conf. NO VOLTRON entry: big_mana fired LOW confidence and so never fed
        # has_other_plan (the silence gate is confidence=='high') — matching the
        # land_destruction precedent, no _PLAN_MIRROR needed. The serve spec stays
        # hand-registered in signal_specs.py. CR 106.4.
        "big_mana",
        # ADR-0027 cheat_from_top — a COMMANDER that REVEALS the top card of a library
        # and CHEATS the SAME revealed card onto the battlefield (Vaevictis, Hans
        # Eriksson, Lurking Predators) wants to STACK its top with a bomb (graveyard-
        # to-top recursion, put-on-top effects). DISTINCT from the sibling top-of-
        # library lanes: cheat_into_play (cheat creatures from library/HAND — Collected
        # Company, Polymorph, See the Unwritten), topdeck_selection (surveil/scry/look-
        # at-top SELECTION — Mayael), impulse_top_play / play_from_top (CAST from top).
        # MIRROR-ONLY migration (the land_destruction / big_mana precedent): the v24
        # from:top/to:battlefield zone projection is too COARSE to carry this lane's
        # narrow scope — a structural `from:top` + `to:battlefield` arm over-fires +156
        # commander-legal (177 vs the regex's 24), 87 of which already fire
        # cheat_into_play and 100 topdeck_selection: it MERGES three deliberately-
        # separate lanes (it cannot distinguish "reveal THE TOP CARD, put IT onto bf"
        # from "look at top N, put A creature card onto bf"). And Vaevictis's reveal
        # folds into a scope-'opp' `choose` clause carrying NO from:top, so the
        # structural arm both over-fires AND misses the canonical card. So the WHOLE
        # lane is under-structured relative to the regex's phrasing precision: the
        # migrated lane is the BYTE-IDENTICAL _CHEAT_FROM_TOP_MIRROR in
        # extract_signals_ir (include_membership-gated; the OR of the EXACT deleted
        # _CHEAT_TOP_REVEAL_RE + _CHEAT_TOP_ONTO_RE over the reminder-stripped
        # kept_oracle == the regex path's `text`). Commander-legal, floor-disabled, by
        # oracle_id: both==24, regex_only==0, ir_only==0 (perfect parity, incl. the
        # DFCs Esper Origins / Jadzi / Nissa — get_oracle_text joins faces on both
        # sides). SCOPE PARITY: deleted producer + mirror both fire scope 'you', LOW
        # conf. NO VOLTRON entry: cheat_from_top fired LOW confidence and so never fed
        # has_other_plan (the silence gate is confidence=='high') — matching the
        # land_destruction / big_mana precedent, no _PLAN_MIRROR needed. NOT a
        # SWEEP_DETECTORS row (a hand-written add() / _LITERAL_ADD_KEYS key), so the
        # detector floor stays at 33. The serve spec stays hand-registered in
        # signal_specs.py. CR 401 / 701.20a.
        "cheat_from_top",
        # ADR-0027 arcane_matters — the Kamigawa Arcane / Splice-onto-Arcane /
        # Spiritcraft archetype (a commander caring about ARCANE spells: "cast a Spirit
        # or Arcane spell" — Tallowisp; "Splice onto Arcane" — the Kamigawa I/S spells;
        # CR 205.3k spell type, CR 702.47 Splice). phase v0.1.19 does NOT structure
        # Arcane as a synergy subject — Arcane is a SPELL TYPE on Instants/Sorceries (CR
        # 304.3 / 307.3), not a creature subtype or a structured keyword, and a "cast a
        # Spirit or Arcane spell" trigger folds to a bare cast_spell event with the
        # Arcane qualifier dropped. So the WHOLE lane is under-structured relative to
        # the regex's word match: the migrated lane is the BYTE-IDENTICAL `\barcane\b`
        # kept WORD MIRROR in _IR_KEPT_DETECTORS (scope 'you', run FLAT over the
        # reminder-stripped kept_oracle — same input as the deleted _HAND_FLOOR
        # producer). The producer's `\barcane\b` has no `[^.]*` cross-clause span, so
        # flat-over-full-text == per-clause and the mirror set == the deleted regex's
        # firing set EXACTLY. Commander-legal, floor-disabled, by oracle_id: both==92,
        # regex_only==0, ir_only==0 (perfect parity); SCOPE PARITY (all 'you', '' HIGH).
        # VOLTRON: the deleted producer fired HIGH-confidence scope 'you' and is NOT in
        # _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS, so it fed has_other_plan. But it is NOT
        # added to _VOLTRON_SILENCING_PLAN_KEYS: the FILE-SWAP showed 0 voltron leaked
        # without an entry (every one of the 92 Arcane bodies — Spiritcraft Spirits with
        # abilities, the Splice I/S spells, the Baku/Kami/Onna — already carries another
        # high-confidence plan signal; none is a vanilla beater whose ONLY plan is the
        # Arcane engine). Adding it would be dead over-silencing, so it stays out —
        # matching the legend_rule_off / timing_control / keyword_soup precedent. NOT a
        # SWEEP_DETECTORS row (a _HAND_FLOOR producer), so the detector floor stays at
        # 33. The serve spec (signal_specs.py — splice-onto-arcane + serve_types
        # ('arcane',)) is independent of this regex and survives. CR 205.3k / 702.47.
        "arcane_matters",
        # modified_matters ← the UNION kept WORD MIRROR (the `\bmodified\b` direct word
        # OR "power greater than its base power" indirect anchor, _signals_ir.
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf) for the Kamigawa Neon Dynasty
        # "modified" creature archetype (CR 700.9 — a permanent is modified if it has a
        # counter, is equipped, or is enchanted by an Aura its controller controls;
        # payoffs reference "modified" — Kappa Tech-Wrecker, Mirror-Style Master, Ondu
        # Knotmaster). phase v0.1.19 doesn't structure "modified" (a DERIVED
        # counter/Equipment/Aura union per CR 700.9, not a parsed predicate/effect), so
        # there's no structural arm — the mirror reads the reminder-stripped joined-
        # face kept_oracle (get_oracle_text sentence-terminates each face; neither
        # pattern has a `[^.]*` cross-clause span, so flat == per-clause == per-face).
        # FLOOR→KEPT: removed from _IR_FLOOR_LANES; floor-mirror-dep -> 0. RESIDUAL
        # (commander-legal, floor-disabled, by oracle_id): both == 47, regex_only == 0
        # (the mirror recovers every regex firing byte-identically incl. the 2 DFCs —
        # Jugan Defends the Temple, Ondu Knotmaster — whose face text get_oracle_text
        # joins), ir_only == 0; all scope 'you', HIGH. SCOPE PARITY: both deleted
        # producers and the mirror all fire scope 'you'. VOLTRON: both producers fired
        # HIGH scope 'you' and fed has_other_plan (a "modified" counters/Aura/Equip
        # engine is no vanilla beater); the IR re-supply is the SAME breadth (residual
        # 0), so modified_matters is added to _VOLTRON_SILENCING_PLAN_KEYS — re-supplies
        # the exact pre-migration commander-damage voltron silence (file-swap voltron
        # delta 0). Both _HAND_FLOOR producers are deleted; NOT a SWEEP_DETECTORS row,
        # so the detector floor stays at 32. The serve spec (signal_specs.py) is
        # independent of these regexes and survives. CR 700.9 / 122 / 301.5 / 303.4 /
        # 613.4c / 903.10a.
        "modified_matters",
        # ADR-0027 — theft_matters (STEAL an OPPONENT's cards and CAST/PLAY them: the
        # impulse-from-opponent steal-and-cast engines (Stolen Goods, Etali, Nicol
        # Bolas God-Pharaoh, Sen Triplets — "exiles cards from the top of their
        # library … you may cast that card"), the heist Arena keyword action (CR DD9),
        # and the name-strip three-zone rifles (Slaughter Games, Lobotomy, Unmoored
        # Ego — "search target opponent's graveyard, hand, and library … exile them").
        # MIGRATED VIA A BYTE-IDENTICAL kept WORD MIRROR (signals-only, NO sidecar
        # bump) — NOT a structural arm.
        #
        # phase carries NO STRUCTURAL FORM for this lane. FLOOR-DISABLED residual over
        # the commander-legal corpus (by oracle_id, _IR_FLOOR_LANES=frozenset()): the
        # structural IR emits theft_matters on ZERO cards. There is no
        # `add("theft_matters", ...)` structural arm anywhere in extract_signals_ir —
        # the lane fired SOLELY from the deleted SWEEP producer (33 commander-legal
        # cards, ALL scope 'opponents', HIGH confidence). It was an _IR_FLOOR_LANE (the
        # production floor re-ran the SWEEP regex on the IR path); both the floor
        # membership and the SWEEP_DETECTORS row are removed.
        #
        # BYTE-IDENTICAL KEPT WORD MIRROR. The deleted producer was a per-card Detector
        # run PER-CLAUSE over the reminder-stripped, DFC-joined oracle. The EXACT
        # pattern (THEFT_MATTERS_REGEX, pinned in _sweep_detectors) run FLAT over the
        # same reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS
        # loop (scope 'opponents', HIGH conf) reproduces the deleted producer BYTE-
        # IDENTICALLY: the seven arms' `[^.]*` anchors never cross a clause boundary
        # (commander-legal: flat==per-clause==33, 0 gain, 0 loss; floor-disabled
        # residual: both==33, regex_only==0, ir_only==0). The SWEEP row is deleted
        # (detector floor 32→31); SWEEP_LABELS["theft_matters"] and the hand-registered
        # serve spec (signal_specs.py — _THEFT_SWEEP_REGEX, pinned verbatim) are
        # independent of the producer and survive.
        #
        # CROSS-OPEN RECONCILIATION (facade). The 337 LOW-conf theft_matters firings in
        # the hybrid are NOT this lane's producer — they ride the gain_control sibling
        # cross-open (signals.py reconciliation: when the migrated IR supplies
        # gain_control, open a LOW theft_matters) plus the regex `dont_own` membership
        # path. Both are independent of the SWEEP producer and untouched here, so the
        # 337 LOW survive byte-for-byte. Only the 33 HIGH steal-and-cast firings move
        # from the SWEEP floor to the kept mirror.
        #
        # SCOPE PARITY. The deleted producer forced scope 'opponents' / HIGH conf; the
        # mirror fires scope 'opponents' / HIGH conf — 0 scope/confidence mismatches
        # over the 33 both-fire cards.
        #
        # VOLTRON. The deleted producer fired HIGH (scope 'opponents', NOT in
        # _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), so it fed has_other_plan, silencing the
        # spurious commander-damage voltron tell on a steal commander (Etali, Sen
        # Triplets, Nicol Bolas, Plargg and Nassari — a steal-and-cast engine is no
        # vanilla beater). Because the IR re-supply IS this byte-identical mirror
        # (IR==regex==33), the hybrid re-silences via _VOLTRON_SILENCING_PLAN_KEYS
        # (signals.py) — no broadening, no over-silence — matching the
        # second_spell_matters / land_sacrifice_matters kept-mirror precedent. FILE-SWAP
        # no-flood (base 24c8eb1 vs edits, baked sidecar, commander-legal, hybrid path):
        # theft_matters BYTE-IDENTICAL (370 → 370); voltron_matters delta 0
        # (3010 → 3010); siblings gain_control / donate_matters / clone_matters /
        # removal_matters drift 0. CR DD9 (heist) / 613.1b (control-changing) / 903.10a.
        "theft_matters",
        # ADR-0027 — evasion_self. The self-evasion lane ("This creature can't be
        # blocked" / unblockable / landwalk / the menace-family keyword words) rides a
        # BYTE-IDENTICAL kept WORD MIRROR (_EVASION_SELF_REGEX, the EXACT deleted
        # _HAND_FLOOR producer) in _signals_ir._IR_KEPT_DETECTORS, flat over the
        # reminder-stripped kept_oracle (no `[^.]*` arm → flat == per-clause). phase
        # only carries the self "can't be blocked" as a generic `restriction` Effect
        # (too broad) or a mass CantBeBlockedBy as `grant_keyword`(unblockable), so a
        # structural arm would be unclean. The IR is BROADER (+36):
        # _IR_KEYWORD_MAP['shadow'] credits the Shadow tribes (Dauthi/Soltari/Thalakos)
        # the regex excluded for name-collision safety — genuine hard evasion (CR
        # 702.28), recall not over-fire. Commander-legal, floor-disabled, by oracle_id:
        # both==1426, ir_only==36, regex_only==0. The deleted producer fired HIGH scope
        # 'you' and fed has_other_plan; the IR re-supply is BROADER, so a byte-identical
        # _EVASION_SELF_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS) restores the
        # voltron silence. Serve spec survives. CR 509.1b / 702.14 / 702.28.
        "evasion_self",
    }
)
"""Signal keys served from the IR path in production; grows as the ADR-0027
regex→IR strangler deletes each key's regex detector. Empty = pure regex
(today)."""
