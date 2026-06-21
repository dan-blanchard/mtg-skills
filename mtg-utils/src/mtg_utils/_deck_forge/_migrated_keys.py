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
        # unchanged). color_hoser was the 12th batch key — SKIPPED: 18 genuine gaps
        # (colored counterspells with subject=None, NotColor anthems on cat='pump',
        # destroy-target-color with dropped predicates, mass-bounce/restriction
        # categories the bind doesn't cover) need a deeper IR-bind widening, not a clean
        # over-fire migration. See ADR-0027.
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
        # force_block/lure — both correct IR exclusions). forced_attack ITSELF stays on
        # regex — its 23 "didn't attack this turn" PUNISHER-incentive gaps (Erg
        # Raiders, Kratos, Angel's Trumpet) are a distinct sub-concept the IR doesn't
        # bind, not a clean over-fire migration; the coupling's over-fire direction
        # (regex goad over-firing on self-force / blocks) is resolved structurally. The
        # two goad _DETECTORS / _HAND_FLOOR producers are deleted; the serve spec is
        # registered. See ADR-0027.
        "goad_matters",
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
        # damage_to_opp_matters is DEFERRED (needs_projection — phase types the
        # "deals damage to a player" trigger as scope='any' indistinguishable from a
        # generic combat-damage connect trigger; widening to scope='any' floods 771
        # over-fires, a genuine recall gap). See ADR-0027.
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
        # NOT migrated (deferred, needs-projection): gain_control (a low-confidence
        # include_membership theft-archetype cross-open fires on 13 "you control but
        # don't own" commanders — Gonti, Tasha, Vaan, … — with no structural IR form;
        # migrating would silently drop them) and keyword_grant_target (phase collapses
        # the single-target "target creature gains menace" spell grant to subject=None
        # with a TRUNCATED raw, erasing the anchor — indistinguishable from self/go-wide
        # grants; firing on subject=None floods +2236). See the deferral comments at the
        # respective arms / producers.
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
        # nothing structural for the cast-timing statics — see the entry above). The
        # remaining 2 (self_counter_grow / token_copy_matters) stay DEFERRED for a
        # genuine floor-disabled IR-vs-regex recall gap (NOT 100% over-fire), see the
        # deferral comments at their arms / producers.
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
        # pump_matters is DEFERRED (needs-projection): the IR pump/pump_target
        # categories flood ~1600 floor-disabled residual with -1/-1 DEBUFFS, activated
        # SELF firebreathing, and conditional self-buffs the narrow positive-single-
        # target regex never caught — not adjudicable as clean over-fire. It stays on
        # its SWEEP_DETECTORS regex. See ADR-0027.
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
        #   variable_pt ← the IR arm misses ~154 genuine */* CDAs (Nightmare, Pack Rat,
        #     Consuming Aberration, Serra Avatar, Cultivator Colossus): phase DROPS the
        #     "power and toughness equal to …" clause entirely on most CDA bodies (the
        #     IR carries only the keyword/other abilities). A deep supplement parse-gap,
        #     not an over-fire migration. Its SWEEP_DETECTORS row stays on regex.
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
        # ADR-0027 β — impulse_top_play: the structural arm (a NON-static cast_from_zone
        # Effect carrying the recovered 'from:library' zone) plus a per-clause
        # _IMPULSE_TOP_PLAY_SWEEP_RE mirror (the EXACT deleted SWEEP regex). The
        # structural arm adds 105 real impulse engines the regex never reached
        # (legitimate breadth, verified vs oracle text); the mirror recovers the
        # follow-through tail phase folds into a categoryless effect (recall ≥ regex).
        # floor-mirror-dep == 0 (neither source reads _IR_FLOOR_LANES). The ab.kind!=
        # 'static' gate prevents double-firing the SIBLING play_from_top (DEFERRED — its
        # static cast_from_zone never carries from:library under the current supplement
        # ordering, so the structural arm reproduces 0/66 of its regex set). The deleted
        # SWEEP producer fired high-confidence scope 'you', so an
        # _IMPULSE_TOP_PLAY_PLAN_MIRROR re-supplies has_other_plan (NO-FLOOD: voltron
        # byte-identical). CR 601.3b.
        "impulse_top_play",
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
    }
)
"""Signal keys served from the IR path in production; grows as the ADR-0027
regex→IR strangler deletes each key's regex detector. Empty = pure regex
(today)."""
