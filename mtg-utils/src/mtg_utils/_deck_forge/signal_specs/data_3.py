"""Signal specs data slice 3/4: SPECS dict entries (lines 4563-5823 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

from mtg_utils._deck_forge._sweep_detectors import (
    LURE_MATTERS_REGEX,
    STATION_MATTERS_REGEX,
    STICKERS_MATTER_REGEX,
    SWEEP_LABELS,
    TAP_DOWN_REGEX,
)

from ._shared import (
    _BASIC_LAND_FETCH,
    _CLONE_DIES_VALUE_EXTRA,
    _COMBAT_SUPPORT_EXTRA,
    _COPY_EXTRA,
    _CREATURE_COST_EXTRA,
    _DIES_RECURSION_EXTRA,
    _DISCARD_PUNISH_EXTRA,
    _ETB_DOUBLER_EXTRA,
    _ETB_PAYOFF_EXTRA,
    _FLICKER_EXTRA,
    _HELLBENT_PUNISH_EXTRA,
    _SELF_BOUNCE_EXTRA,
    _SELF_BOUNCE_RECAST_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_EXTRA,
    _UNTAP_EXTRA,
    _UNTAP_ORACLE,
    _VOLTRON_PROTECT_EXTRA,
    SignalSpec,
    _spec,
    _sweep_spec_with_extras,
)

SPECS_3: dict[tuple[str, str], SignalSpec] = {
    # ── Mechanics recovered from the "rejected" families ────────────────────────
    # ADR-0027 β: token_copy_makers migrated to the Card IR via a byte-identical kept-
    # mirror (the lane fires structurally from crosswalk_signals.py). This serve
    # spec was always hand-registered and independent of the deleted _HAND_FLOOR
    # producer, so it survives unchanged — its curated SEARCH regex is intentionally
    # narrower than the detector (it omits the "twice that many … tokens" doubler arm,
    # which the _TOKEN_DOUBLER_EXTRA below already supplies as a separate avenue).
    ("token_copy_makers", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        {"oracle": r"token that's a copy|tokens? that are copies|\bpopulate\b"},
        r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|\bpopulate\b",
        # Deliver on "strong creatures to copy": a token-copy deck wants big bombs to
        # copy (Etali). power_min=6 keeps it to genuine bombs, mirroring clone_makers.
        serve_power_min=6,
        # A token-copy commander (Esix) turns each token it would create into a copy —
        # so it also wants raw token MAKERS (more tokens → more copies) and token
        # DOUBLERS (double the copies).
        # A token-copy deck floods the board with creatures that ENTER — so it's an ETB
        # deck too: ETB payoffs (Impact Tremors) and doublers (Panharmonicon) fire on
        # every copy.
        extras=(
            _TOKEN_MAKER_EXTRA,
            _TOKEN_DOUBLER_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _ETB_DOUBLER_EXTRA,
        ),
    ),
    # ADR-0035 Stage-3a: three served maker lanes (in ``SERVED_SIGNAL_KEYS``)
    # that
    # the legacy regex path never produced, so their specs were never registered.
    # Added so the key-agreement gate resolves them; since the ADR-0039 cutover
    # (crosswalk-only serving, flag retired) they serve unconditionally like every
    # other spec.
    ("copy_permanent", "you"): _spec(
        "Permanent copies",
        "generic clone effects plus strong permanents worth copying",
        {"oracle": r"becomes a copy|copy of (?:target|another|any|a|that)\b"},
        r"becomes a copy|copy of (?:target|another|any|a|that)\b|as a copy of",
    ),
    ("amass_makers", "you"): _spec(
        "Amass",
        "amass sources plus Army / +1/+1-counter payoffs",
        {"oracle": r"\bamass\b"},
        r"\bamass\b|\bArmy\b|\+1/\+1 counter",
    ),
    ("incubate_makers", "you"): _spec(
        "Incubate",
        "incubate sources plus artifact-token / +1/+1-counter payoffs",
        {"oracle": r"\bincubate\b"},
        r"\bincubate\b|\bIncubator\b|\+1/\+1 counter",
    ),
    ("specialize_matters", "you"): _spec(
        "Specialize",
        "specialize payoffs to swap a creature's stat/ability line "
        "(Backgrounds are a separate axis — see Partner / Background)",
        {"oracle": r"\bspecialize\b"},
        r"\bspecialize\b",
    ),
    # ADR-0027: ki_counter_matters + seek_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — phase's
    # counter-kind / effect-category projection). The SERVE pool (the cards that
    # ARE the thing) is still oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build — reusing the deleted regex as the
    # serve pattern. (SWEEP_LABELS still carries the human label.)
    ("ki_counter_makers", "you"): _spec(
        *SWEEP_LABELS["ki_counter_makers"],
        {"oracle": r"\bki counters?\b"},
        r"\bki counters?\b",
    ),
    ("ki_counter_matters", "you"): _spec(
        *SWEEP_LABELS["ki_counter_matters"],
        {"oracle": r"\bki counters?\b"},
        r"\bki counters?\b",
    ),
    ("seek_matters", "you"): _spec(
        *SWEEP_LABELS["seek_matters"],
        {"oracle": r"\bseek\b"},
        r"\bseek\b",
    ),
    # ADR-0027: mass_bounce + destroy_legendary had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — the bounce/destroy effect shape).
    # The SERVE pool (the cards that ARE the thing) is still oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex as the serve pattern. (SWEEP_LABELS still carries the human label.)
    ("mass_bounce", "any"): _spec(
        *SWEEP_LABELS["mass_bounce"],
        {
            "oracle": (
                r"return each (?:other )?(?:nonland )?permanent[^.]*to (?:its|their) "
                r"owner's hand|return each (?:other )?[^.]*?creatures?[^.]*?to "
                r"(?:its|their) owner's hand|return all[^.]*to (?:its|their) "
                r"owners' hands"
            )
        },
        (
            r"return each (?:other )?(?:nonland )?permanent[^.]*to (?:its|their) "
            r"owner's hand|return each (?:other )?[^.]*?creatures?[^.]*?to "
            r"(?:its|their) owner's hand|return all[^.]*to (?:its|their) owners' hands"
        ),
    ),
    ("destroy_legendary", "any"): _spec(
        *SWEEP_LABELS["destroy_legendary"],
        {"oracle": r"destroy (?:up to one )?target legendary (?:permanent|creature)"},
        r"destroy (?:up to one )?target legendary (?:permanent|creature)",
    ),
    # ADR-0027: the four bending lanes had their oracle-regex SWEEP_DETECTORS rows
    # deleted (detection moved to the Card IR — the kept word-detector mirror in
    # signals._IR_KEPT_DETECTORS). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing
    # each deleted regex as the serve pattern. (SWEEP_LABELS still carries the
    # human label.)
    ("airbend_makers", "you"): _spec(
        *SWEEP_LABELS["airbend_makers"],
        {"oracle": r"\bairbend(?:ing|s)?\b"},
        r"\bairbend(?:ing|s)?\b",
    ),
    # _matters sweep (ADR-0034): earthbend split. The DOER arm (earthbend_makers,
    # keyword bearers) and the PAYOFF arm (earthbend_matters, keyword-less cross-bend
    # references) both serve the same oracle pool — clone-pilot precedent: the serve
    # avenue legitimately offers makers + payoffs together; only membership splits by
    # role.
    ("earthbend_makers", "you"): _spec(
        *SWEEP_LABELS["earthbend_makers"],
        {"oracle": r"\bearthbend(?:ing|s)?\b"},
        r"\bearthbend(?:ing|s)?\b",
    ),
    ("earthbend_matters", "you"): _spec(
        *SWEEP_LABELS["earthbend_matters"],
        {"oracle": r"\bearthbend(?:ing|s)?\b"},
        r"\bearthbend(?:ing|s)?\b",
    ),
    # _matters sweep (ADR-0034): waterbend split. The DOER arm (waterbend_makers,
    # keyword bearers) and the PAYOFF arm (waterbend_matters) both serve the same
    # oracle pool — clone-pilot precedent: the serve avenue legitimately offers
    # makers + payoffs together; only membership splits by role.
    ("waterbend_makers", "you"): _spec(
        *SWEEP_LABELS["waterbend_makers"],
        {"oracle": r"\bwaterbend(?:ing|s)?\b"},
        r"\bwaterbend(?:ing|s)?\b",
    ),
    ("waterbend_matters", "you"): _spec(
        *SWEEP_LABELS["waterbend_matters"],
        {"oracle": r"\bwaterbend(?:ing|s)?\b"},
        r"\bwaterbend(?:ing|s)?\b",
    ),
    # _matters sweep (ADR-0034): firebending split. The MAKER arm (firebending_makers,
    # Firebending-keyword bearers) and the PAYOFF arm (firebending_matters, keyword-less
    # Fire-Nation references) both serve the same oracle pool — clone-pilot precedent:
    # the serve avenue legitimately offers makers + payoffs together; only membership
    # splits by role.
    ("firebending_makers", "you"): _spec(
        *SWEEP_LABELS["firebending_makers"],
        {"oracle": r"\bfirebend(?:ing|s)?\b"},
        r"\bfirebend(?:ing|s)?\b",
    ),
    ("firebending_matters", "you"): _spec(
        *SWEEP_LABELS["firebending_matters"],
        {"oracle": r"\bfirebend(?:ing|s)?\b"},
        r"\bfirebend(?:ing|s)?\b",
    ),
    # ADR-0027 (t2b2-A): aura_equip_kw_grant / counter_grants_kw /
    # conditional_self_protection had their oracle-regex SWEEP_DETECTORS rows deleted
    # (detection moved to the Card IR — the grant_keyword effect shape gated on the
    # subject Filter + the granted keyword). The SERVE pool (the cards that ARE the
    # thing) stays oracle-defined, so hand-register the spec the sweep auto-register
    # loop used to build, reusing each deleted regex as the serve pattern.
    # (SWEEP_LABELS still carries each human label.)
    ("aura_equip_kw_grant", "you"): _spec(
        *SWEEP_LABELS["aura_equip_kw_grant"],
        {
            "oracle": (
                r"(?:auras?|equipment) you control have (?:exalted|flying|trample"
                r"|deathtouch|lifelink|vigilance|haste|first strike|double strike"
                r"|hexproof|ward|menace|reach|indestructible)"
            )
        },
        (
            r"(?:auras?|equipment) you control have (?:exalted|flying|trample"
            r"|deathtouch|lifelink|vigilance|haste|first strike|double strike"
            r"|hexproof|ward|menace|reach|indestructible)"
        ),
    ),
    ("counter_grants_kw", "you"): _spec(
        *SWEEP_LABELS["counter_grants_kw"],
        {
            "oracle": (
                r"creature you control with a \+1/\+1 counter on it (?:has|have) "
                r"(?:haste|flying|trample|menace|vigilance|lifelink)"
            )
        },
        (
            r"creature you control with a \+1/\+1 counter on it (?:has|have) "
            r"(?:haste|flying|trample|menace|vigilance|lifelink)"
        ),
    ),
    ("conditional_self_protection", "you"): _spec(
        *SWEEP_LABELS["conditional_self_protection"],
        {
            "oracle": (
                r"has hexproof (?:if|while|as long as|during)"
                r"|during your turn,[^.]*has (?:hexproof|indestructible|protection)"
                r"|has (?:hexproof|indestructible) if"
            )
        },
        (
            r"has hexproof (?:if|while|as long as|during)"
            r"|during your turn,[^.]*has (?:hexproof|indestructible|protection)"
            r"|has (?:hexproof|indestructible) if"
        ),
    ),
    # ADR-0027: attractions_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to an _IR_KEPT_DETECTORS word mirror). The SERVE pool stays
    # oracle-defined (Attraction openers / visit payoffs), so hand-register the spec
    # the sweep auto-register loop used to build, reusing the deleted regex.
    ("attractions_matter", "you"): _spec(
        *SWEEP_LABELS["attractions_matter"],
        {"oracle": r"\battraction\b|open an attraction"},
        r"\battraction\b|open an attraction",
    ),
    # ADR-0027: stickers_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to a byte-identical STICKERS_MATTER_REGEX _IR_KEPT_DETECTORS word
    # mirror). The SERVE pool stays oracle-defined (the {TK}/sticker effects), so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex (now the shared STICKERS_MATTER_REGEX constant) so serve / mirror /
    # detector never drift.
    ("stickers_matter", "you"): _spec(
        *SWEEP_LABELS["stickers_matter"],
        {"oracle": STICKERS_MATTER_REGEX},
        STICKERS_MATTER_REGEX,
    ),
    # ADR-0027 tranche2-C: extra_land_drop had its oracle-regex SWEEP_DETECTORS row
    # deleted (detection moved to the Card IR — cheat_play / topdeck_select with a Land
    # subject + a kept word mirror). The SERVE pool (the put-a-land-into-play effects)
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing the deleted regex.
    ("extra_land_drop", "you"): _spec(
        *SWEEP_LABELS["extra_land_drop"],
        {
            "oracle": (
                r"put a land(?: card)? from your hand onto the battlefield"
                r"|you may put a land [^.]*onto the battlefield"
            )
        },
        r"put a land(?: card)? from your hand onto the battlefield"
        r"|you may put a land [^.]*onto the battlefield",
    ),
    # ADR-0027: companion_keyword had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Scryfall `companion` keyword). The SERVE pool stays
    # oracle-defined (a companion's starting-deck restriction text), so
    # hand-register the spec the sweep auto-register loop used to build, reusing
    # the deleted regex as the serve pattern.
    ("companion_keyword", "you"): _spec(
        *SWEEP_LABELS["companion_keyword"],
        {
            "oracle": (
                r"companion —|each (?:creature |permanent )?card in your "
                r"starting deck|your starting deck contains"
            )
        },
        r"companion —|each (?:creature |permanent )?card in your starting deck"
        r"|your starting deck contains",
    ),
    # ADR-0027: has_soulbond had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `soulbond` keyword + a
    # `soulbond` effect marker for non-keyword references). The SERVE pool (the
    # creatures that ARE the thing — they carry the soulbond keyword) stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex as the serve pattern.
    ("has_soulbond", "you"): _spec(
        *SWEEP_LABELS["has_soulbond"],
        {"oracle": r"\bsoulbond\b"},
        r"\bsoulbond\b",
    ),
    # ADR-0027: has_devour had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `devour` keyword + phase's
    # `devour` effect category). The SERVE pool (the cards that ARE devourers /
    # token fodder to devour) stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing the deleted regex as the
    # serve pattern. (SWEEP_LABELS still carries the human label.)
    ("has_devour", "you"): _spec(
        *SWEEP_LABELS["has_devour"],
        {"oracle": r"\bdevour\b"},
        r"\bdevour\b",
    ),
    # ADR-0027 tail-supplement: boast/exhaust/explore/phasing/end_the_turn/
    # trigger_doubling each had their oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — keyword array + effect-category + supplement
    # markers). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing each deleted regex.
    # _matters sweep (ADR-0034): the MAKER arm of the boast split — boast creatures
    # (cards carrying the Boast ability). Same \bboast\b serve pool as the payoff arm.
    ("boast_makers", "you"): _spec(
        *SWEEP_LABELS["boast_makers"],
        {"oracle": r"\bboast\b"},
        r"\bboast\b",
    ),
    ("boast_matters", "you"): _spec(
        *SWEEP_LABELS["boast_matters"],
        {"oracle": r"\bboast\b"},
        r"\bboast\b",
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the exhaust split — cards carrying
    # an Exhaust ability. Same \bexhaust\b serve pool as the payoff arm.
    ("exhaust_makers", "you"): _spec(
        *SWEEP_LABELS["exhaust_makers"],
        {"oracle": r"\bexhaust\b"},
        r"\bexhaust\b",
    ),
    ("exhaust_matters", "you"): _spec(
        *SWEEP_LABELS["exhaust_matters"],
        {"oracle": r"\bexhaust\b"},
        r"\bexhaust\b",
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the explore split — creatures that
    # explore. Same \bexplores?\b serve pool as the payoff arm.
    ("explore_makers", "you"): _spec(
        *SWEEP_LABELS["explore_makers"],
        {"oracle": r"\bexplores?\b"},
        r"\bexplores?\b",
    ),
    ("explore_matters", "you"): _spec(
        *SWEEP_LABELS["explore_matters"],
        {"oracle": r"\bexplores?\b"},
        r"\bexplores?\b",
    ),
    ("phasing_makers", "you"): _spec(
        *SWEEP_LABELS["phasing_makers"],
        {"oracle": r"phase out|phases out|phased out"},
        r"phase out|phases out|phased out",
    ),
    # ADR-0027 / _matters sweep (ADR-0034): the Station/Spacecraft lane migrated to the
    # Card IR and then SPLIT into station_makers (the Spacecraft/Planet bodies + the
    # chargers that PERFORM Station) and station_matters (the Spacecraft-ref payoffs).
    # Both serve the SAME Station/Spacecraft pool (the avenue composes maker + payoff),
    # so both reuse the pinned STATION_MATTERS_REGEX — the serve pool never drifts from
    # the (now-deleted) detector.
    ("station_makers", "you"): _spec(
        "Station / Spacecraft",
        "Spacecraft/Planet to station plus ways to charge them",
        {"oracle": STATION_MATTERS_REGEX},
        STATION_MATTERS_REGEX,
    ),
    ("station_matters", "you"): _spec(
        *SWEEP_LABELS["station_matters"],
        {"oracle": STATION_MATTERS_REGEX},
        STATION_MATTERS_REGEX,
    ),
    # ADR-0027: tap_down migrated to the Card IR (its SWEEP_DETECTORS row is deleted, so
    # the auto-register loop no longer builds this spec). Hand-register it reusing the
    # pinned TAP_DOWN_REGEX so the serve pool never drifts from the (now-deleted)
    # detector. Scope 'opponents' (the deleted SWEEP row's forced scope). SWEEP_LABELS
    # still carries the human label.
    ("tap_down", "opponents"): _spec(
        *SWEEP_LABELS["tap_down"],
        {"oracle": TAP_DOWN_REGEX},
        TAP_DOWN_REGEX,
    ),
    ("end_the_turn", "you"): _spec(
        *SWEEP_LABELS["end_the_turn"],
        {"oracle": r"\bend the turn\b"},
        r"\bend the turn\b",
    ),
    ("trigger_doubling", "you"): _spec(
        *SWEEP_LABELS["trigger_doubling"],
        {"oracle": r"triggers? an additional time|trigger an additional time"},
        r"triggers? an additional time|trigger an additional time",
    ),
    # ADR-0027: cant_block_grant had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `cant_block` effect category + a
    # modal/granted-quoted dropped-static face marker). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex.
    ("cant_block_grant", "you"): _spec(
        *SWEEP_LABELS["cant_block_grant"],
        {"oracle": r"target creature can't block"},
        r"target creature can't block",
    ),
    # ADR-0027: convoke_matters / myriad_grant / typed_anthem_multi / life_total_set
    # each had their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the
    # Card IR — keyword array + effect-category + supplement markers). The SERVE pool
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing each deleted regex.
    ("convoke_matters", "you"): _spec(
        *SWEEP_LABELS["convoke_matters"],
        {"oracle": r"\bconvoke\b"},
        r"\bconvoke\b",
    ),
    # _matters sweep (ADR-0034): the DOER/ENABLER side of the convoke split (the
    # `convoke` keyword bearers + the "<type> spells you cast have convoke" granters).
    # Same serve pool as the payoff — both want wide, cheap creatures to tap.
    ("convoke_makers", "you"): _spec(
        *SWEEP_LABELS["convoke_makers"],
        {"oracle": r"\bconvoke\b"},
        r"\bconvoke\b",
    ),
    # ADR-0027 t2b4a-B: win_lose_game / alt_cost_keyword / partner_background each had
    # their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the Card IR —
    # win/lose Effect categories; the alt-cost & partner-family Scryfall keyword
    # arrays). The SERVE pool stays oracle-defined, so hand-register the spec the sweep
    # auto-register loop used to build, reusing each deleted regex. (SWEEP_LABELS still
    # carries each human label.)
    ("win_lose_game", "any"): _spec(
        *SWEEP_LABELS["win_lose_game"],
        {
            "oracle": (
                r"you win the game|(?:that player|each opponent"
                r"|target (?:player|opponent)) loses the game"
            )
        },
        r"you win the game|(?:that player|each opponent"
        r"|target (?:player|opponent)) loses the game",
    ),
    ("alt_cost_keyword", "you"): _spec(
        *SWEEP_LABELS["alt_cost_keyword"],
        {"oracle": r"\bweb-slinging\b|\bsneak\b|\bmayhem\b"},
        r"\bweb-slinging\b|\bsneak\b|\bmayhem\b",
        serve_keywords=("web-slinging", "sneak", "mayhem"),
    ),
    # partner_background's avenue REPLACES this serve with a partner-legality search
    # (engine.partner_search + the ADR-0019 color-widening flag); this spec is the
    # fallback pool — the cards that carry a partner-family keyword.
    ("partner_background", "you"): _spec(
        *SWEEP_LABELS["partner_background"],
        {
            "oracle": (
                r"choose a background|partner with|\bpartner\b(?! with)"
                r"|\bfriends forever\b|\bdoctor's companion\b"
            )
        },
        r"choose a background|partner with|\bpartner\b(?! with)"
        r"|\bfriends forever\b|\bdoctor's companion\b",
        serve_keywords=(
            "partner",
            "partner with",
            "choose a background",
            "doctor's companion",
            "friends",
        ),
    ),
    # ADR-0027 t2b5-C: named_counter_misc / powerup_matters each had their oracle-regex
    # SWEEP_DETECTORS row deleted (detection moved to the Card IR — named_counter_misc
    # to the kept word mirror; powerup_matters to the Scryfall Power-up keyword array).
    # Each had no hand spec, so the sweep auto-register loop built its serve; reproduce
    # that spec here, reusing SWEEP_LABELS + the deleted regex (byte-identical pool).
    ("named_counter_misc", "you"): _spec(
        *SWEEP_LABELS["named_counter_misc"],
        {
            "oracle": (
                r"\b(?:egg|divinity|prey|bounty|bribery|page|study|knowledge"
                r"|silver|gold|fate|incubation) counters?\b"
            )
        },
        r"\b(?:egg|divinity|prey|bounty|bribery|page|study|knowledge"
        r"|silver|gold|fate|incubation) counters?\b",
    ),
    ("powerup_matters", "you"): _spec(
        *SWEEP_LABELS["powerup_matters"],
        {"oracle": r"power-up —"},
        r"power-up —",
        serve_keywords=("power-up",),
    ),
    # ADR-0027: rad_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `rad_counter` effect / rad place_counter
    # + a "rad counter(s)" face marker). The IR fires scope "opponents" (rad counters go
    # on players as a kill clock). Serve hand-registered reusing the deleted regex.
    ("rad_counter_makers", "opponents"): _spec(
        *SWEEP_LABELS["rad_counter_makers"],
        {"oracle": r"\brad counters?\b"},
        r"\brad counters?\b",
    ),
    # ADR-0027: oil_counter_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter(counter_kind='oil') placer
    # + an "oil counter(s)" payoff marker). Serve hand-registered reusing the deleted
    # regex so the lane still surfaces oil sources and payoffs.
    # _matters sweep (ADR-0034): the MAKER side of the oil split (cards that
    # PLACE oil counters). Same serve pool as the payoff lane — the avenue
    # legitimately offers oil sources + payoffs together (ADR-0034: only
    # membership splits by role, the serve avenue composes both).
    ("oil_counter_makers", "you"): _spec(
        *SWEEP_LABELS["oil_counter_makers"],
        {"oracle": r"\boil counters?\b"},
        r"\boil counters?\b",
    ),
    ("oil_counter_matters", "you"): _spec(
        *SWEEP_LABELS["oil_counter_matters"],
        {"oracle": r"\boil counters?\b"},
        r"\boil counters?\b",
    ),
    # ADR-0027: shield_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter / hascounters
    # counter_kind='shield' structural arm + a byte-identical kept word mirror). The
    # SERVE pool (the cards that ARE the thing — shield-counter sources and payoffs) is
    # still oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing the deleted regex as the serve pattern. CR 122.1c.
    ("shield_counter_makers", "you"): _spec(
        *SWEEP_LABELS["shield_counter_makers"],
        {"oracle": r"\bshield counters?\b"},
        r"\bshield counters?\b",
    ),
    # ADR-0027: fight_makers had its oracle-regex SWEEP_DETECTORS row deleted (moved to
    # the Card IR — phase's fight effect + a granted/quoted/modal fight marker). Serve
    # hand-registered reusing the deleted regex (the lane wants big creatures to fight
    # with — surface fatties via power_min, plus the gear/buffs that suit them up).
    ("fight_makers", "you"): _sweep_spec_with_extras(
        "fight_makers",
        serve_power_min=4,
        regex=(
            r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
            r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature|\bfight each "
            r"other\b|\bfights? it\b|\bfights? (?:another|each)"
        ),
    ),
    # ADR-0027: has_changeling had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall changeling keyword + a "changeling"
    # / "is every creature type" all-tribes marker). Serve hand-registered reusing the
    # deleted regex (plus the changeling keyword dimension for the bearers).
    ("has_changeling", "you"): _spec(
        *SWEEP_LABELS["has_changeling"],
        {"oracle": r"is every creature type|\bchangeling\b"},
        r"is every creature type|\bchangeling\b",
        serve_keywords=("changeling",),
    ),
    # ADR-0027: starting_life_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a "starting life total" compare marker). Serve
    # hand-registered reusing the deleted regex.
    ("starting_life_matters", "you"): _spec(
        *SWEEP_LABELS["starting_life_matters"],
        {
            "oracle": (
                r"(?:greater than|less than|above|below|equal to|more than) your "
                r"starting life total|starting life total"
            )
        },
        (
            r"(?:greater than|less than|above|below|equal to|more than) your "
            r"starting life total|starting life total"
        ),
    ),
    ("myriad_grant", "you"): _spec(
        *SWEEP_LABELS["myriad_grant"],
        {"oracle": r"gains? myriad|\bmyriad\b"},
        r"gains? myriad|\bmyriad\b",
    ),
    ("typed_anthem_multi", "you"): _spec(
        *SWEEP_LABELS["typed_anthem_multi"],
        {
            "oracle": (
                r"each (?:other )?creature (?:you control )?that's (?:a |an )\w+"
                r"[^.]*(?:gets?|have|has|gains?)"
            )
        },
        (
            r"each (?:other )?creature (?:you control )?that's (?:a |an )\w+"
            r"[^.]*(?:gets?|have|has|gains?)"
        ),
    ),
    ("life_total_set", "any"): _spec(
        *SWEEP_LABELS["life_total_set"],
        {
            "oracle": (
                r"life total (?:becomes|equal to)|equal to half (?:that|your|a) "
                r"(?:player'?s? )?life|exchange (?:your )?life total"
                r"|exchange life totals?|set your life total to"
                r"|double target player's life total"
            )
        },
        (
            r"life total (?:becomes|equal to)|equal to half (?:that|your|a) "
            r"(?:player'?s? )?life|exchange (?:your )?life total"
            r"|exchange life totals?|set your life total to"
            r"|double target player's life total"
        ),
    ),
    # ADR-0027: all_creatures_kw_grant + facedown_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # GrantKeyword effect / the manifest-cloak-morph effect categories + kept word
    # mirror). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing each deleted regex.
    ("all_creatures_kw_grant", "any"): _spec(
        *SWEEP_LABELS["all_creatures_kw_grant"],
        {
            "oracle": (
                r"all creatures have (?:haste|flying|trample|vigilance|menace"
                r"|hexproof|deathtouch|first strike|double strike|reach|lifelink)"
            )
        },
        r"all creatures have (?:haste|flying|trample|vigilance|menace|hexproof"
        r"|deathtouch|first strike|double strike|reach|lifelink)",
    ),
    ("facedown_matters", "you"): _spec(
        *SWEEP_LABELS["facedown_matters"],
        {
            "oracle": (
                r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
                r"|face-?down creatures?|as a 2/2 face-?down"
                r"|turn (?:it|that creature|this creature|them"
                r"|a permanent you control) face up|turn target [^.]*?face up"
                r"|turned face up this turn"
            )
        },
        r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
        r"|face-?down creatures?|as a 2/2 face-?down"
        r"|turn (?:it|that creature|this creature|them|a permanent you control) "
        r"face up|turn target [^.]*?face up|turned face up this turn",
    ),
    # _matters sweep (ADR-0034): the MAKER side of the facedown split. facedown_makers
    # fires on the morph/megamorph/disguise/manifest/cloak/manifest-dread bodies that
    # PUT a face-down 2/2 on the battlefield (CR 708). The avenue serves more of those
    # face-down 2/2 makers plus the turn-face-up payoffs the deck wants alongside them
    # (the avenue composes makers + payoffs per ADR-0034).
    ("facedown_makers", "you"): _spec(
        "Face-down makers",
        "morph/manifest/disguise/cloak creatures that enter face down",
        {
            "oracle": (
                r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
                r"|face-?down creatures?|as a 2/2 face-?down"
                r"|turn (?:it|that creature|this creature|them"
                r"|a permanent you control) face up|turn target [^.]*?face up"
                r"|turned face up this turn"
            )
        },
        r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
        r"|face-?down creatures?|as a 2/2 face-?down"
        r"|turn (?:it|that creature|this creature|them|a permanent you control) "
        r"face up|turn target [^.]*?face up|turned face up this turn",
    ),
    # ADR-0027: affinity_type + evasion_denial had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — affinity ← the Scryfall keyword +
    # an `affinity` conferred-grant marker; evasion_denial ← phase's named-walk
    # evasion_denial effect + a generic-landwalk-umbrella marker). The auto-register
    # sweep loop used to build their serve specs from the now-gone rows, so hand-
    # register them reusing each deleted regex as the serve pattern.
    ("affinity_type", "you"): _spec(
        *SWEEP_LABELS["affinity_type"],
        {"oracle": r"\baffinity\b|spells you cast have affinity"},
        r"\baffinity\b|spells you cast have affinity",
    ),
    ("evasion_denial", "opponents"): _spec(
        *SWEEP_LABELS["evasion_denial"],
        {"oracle": r"can be blocked as though (?:it|they) didn't have"},
        r"can be blocked as though (?:it|they) didn't have",
    ),
    # ADR-0027: lure_makers had its oracle-regex SWEEP_DETECTORS row deleted (detection
    # moved to the Card IR — a structural `lure` arm + a byte-identical kept mirror for
    # the Aftermath-DFC back face phase drops). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build (scope 'you'),
    # reusing the pinned LURE_MATTERS_REGEX so the serve never drifts from the deleted
    # detector. CR 509.1c.
    ("lure_makers", "you"): _spec(
        *SWEEP_LABELS["lure_makers"],
        {"oracle": LURE_MATTERS_REGEX},
        LURE_MATTERS_REGEX,
    ),
    # ADR-0027: damage_doubling had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the damage_doubling DamageDone-replacement category, now
    # covering triple + the nested AddTargetReplacement / CreateDamageReplacement
    # amplifiers, plus a face marker for the dropped modification). The auto-register
    # sweep loop used to build its serve spec from the now-gone row, so hand-register
    # it reusing the deleted regex as the serve pattern (minus the halving over-fire —
    # the serve still wants double/triple doublers, not Dark Sphere's prevention).
    ("damage_doubling", "you"): _spec(
        *SWEEP_LABELS["damage_doubling"],
        {
            "oracle": (
                r"deals? (?:double|triple) that damage"
                r"|deals? twice that (?:much|damage)"
                r"|double (?:all damage|the (?:next )?damage)"
                r"|deals that much damage plus"
            )
        },
        r"deals? (?:double|triple) that damage"
        r"|deals? twice that (?:much|damage)"
        r"|double (?:all damage|the (?:next )?damage)"
        r"|deals that much damage plus",
    ),
    # ADR-0027: commander_matters / hand_disruption / opponent_exile_matters had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # predicate/trigger bind + a kept word mirror per key). The auto-register sweep loop
    # used to build their serve specs from the now-gone rows, so hand-register them
    # reusing each deleted regex as the serve pattern.
    ("commander_matters", "you"): _spec(
        *SWEEP_LABELS["commander_matters"],
        {
            "oracle": (
                r"commanders? you (?:control|own) "
                r"(?:have|has|get|gets|gain|gains)"
                r"|commander creatures? you (?:own|control)"
                r"|whenever your commander\b|whenever a commander\b"
                r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
                r"|is your commander|it'?s your commander"
                r"|while [^.]*your commander|it's a copy of your other commander"
                r"|copy of any of your commanders|each commander you (?:control|own)"
                r"|for each commander|commander damage"
            )
        },
        r"commanders? you (?:control|own) (?:have|has|get|gets|gain|gains)"
        r"|commander creatures? you (?:own|control)"
        r"|whenever your commander\b|whenever a commander\b"
        r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
        r"|is your commander|it'?s your commander|while [^.]*your commander"
        r"|it's a copy of your other commander|copy of any of your commanders"
        r"|each commander you (?:control|own)|for each commander|commander damage",
    ),
    ("hand_disruption", "opponents"): _spec(
        *SWEEP_LABELS["hand_disruption"],
        {
            "oracle": (
                r"look at (?:target player|that player|an opponent|each opponent"
                r"|target opponent)'?s?'? hands?"
                r"|plays? with (?:their|his or her) hands? revealed"
                r"|reveals? (?:their|his or her) hands?"
                r"|reveals? (?:\w+ )?cards? (?:at random )?from "
                r"(?:their|his or her|that player's) hand"
                r"|reveals?[^.]*until you say stop"
            )
        },
        r"look at (?:target player|that player|an opponent|each opponent"
        r"|target opponent)'?s?'? hands?"
        r"|plays? with (?:their|his or her) hands? revealed"
        r"|reveals? (?:their|his or her) hands?"
        r"|reveals? (?:\w+ )?cards? (?:at random )?from "
        r"(?:their|his or her|that player's) hand"
        r"|reveals?[^.]*until you say stop",
    ),
    # _matters sweep (ADR-0034): the opponent_exile lane SPLIT by role. ADR-0034 lets
    # the avenue still serve makers + payoffs together; only MEMBERSHIP splits.
    ("opponent_exile_makers", "opponents"): _spec(
        *SWEEP_LABELS["opponent_exile_makers"],
        {
            "oracle": (
                r"exile (?:target player's|target opponent's|each opponent's"
                r"|that player's) graveyard"
                r"|if a card would be put into an opponent's graveyard"
            )
        },
        r"exile (?:target player's|target opponent's|each opponent's"
        r"|that player's) graveyard"
        r"|if a card would be put into an opponent's graveyard",
    ),
    ("opponent_exile_matters", "opponents"): _spec(
        *SWEEP_LABELS["opponent_exile_matters"],
        {
            "oracle": (
                r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
                r"|for each card your opponents own in exile"
                r"|opponents own in exile"
            )
        },
        r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
        r"|for each card your opponents own in exile|opponents own in exile",
    ),
    ("villainous_choice", "you"): _spec(
        "Villainous choice",
        "villainous-choice cards (the punisher pool a villainous-choice commander — "
        "The Valeyard, Davros, Missy — is built to present and double)",
        {"oracle": r"villainous choice"},
        r"villainous choice",
    ),
    ("curse_matters", "you"): _spec(
        "Curses",
        "Curse cards to recur, attach, and pile onto opponents (Lynde, Cheerful "
        "Tormentor) — served by the Curse subtype, not oracle prose",
        {"card_type": "Curse"},
        None,
        serve_types=("curse",),
    ),
    # _matters sweep (ADR-0034): dice split. dice_makers = the ENABLER/doer side (cards
    # that roll dice — "roll a d20", "roll a six-sided die"); dice_matters below = the
    # PAYOFF side (cards rewarded by / triggering off a roll). The avenue serves both
    # together (enablers to roll + payoffs that reward rolling).
    ("dice_makers", "you"): _spec(
        "Dice rolling",
        "dice-rolling enablers plus roll-result payoffs",
        {"oracle": r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|\bd20\b"},
        r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|whenever you roll",
    ),
    ("dice_matters", "you"): _spec(
        "Dice payoffs",
        "cards rewarded by rolling dice, plus the rollers to feed them",
        {
            "oracle": r"whenever you roll"
            r"|roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)"
        },
        r"whenever you roll|roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)",
    ),
    # A crime (CR 700.13) targets opponents / their permanents / spells they control —
    # i.e. targeted removal + explicit-opponent-target. The SEARCH's bare
    # `target.*spell` credited every counterspell; drop it for concrete removal shapes.
    ("crimes_matter", "you"): _spec(
        "Crimes",
        "targeted removal and abilities that count as committing a crime",
        {
            "oracle": (
                r"commit(?:s|ted)? a crime|whenever you commit"
                r"|target (?:opponent|player|opponents)"
                r"|destroy target|exile target (?:creature|permanent|nonland)"
                r"|deals? (?:\d+|x) damage to target (?:creature|player|opponent)"
            )
        },
        r"commit(?:s|ted)? a crime|whenever you commit",
    ),
    ("connive_makers", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        {"oracle": r"\bconnives?\b|draw a card, then discard"},
        r"\bconnives?\b",
    ),
    ("spell_copy_makers", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        {"oracle": r"copy (?:target|that)|instant or sorcery|\bstorm\b"},
        r"copy target (?:instant|sorcery|spell)|\bcopy that spell\b|\bstorm\b",
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp", "you"): _spec(
        "Ramp / big mana",
        "mana rocks, dorks, and land ramp to accelerate into your payoffs",
        {"oracle": r"add \{|search your library for .*\bland\b|" + _BASIC_LAND_FETCH},
        r"\{t\}[^.]*:\s*add|add .* mana|search your library for .*\bland\b|"
        + _BASIC_LAND_FETCH,
        # Deliver on "accelerate into your payoffs": the big bombs (Ghalta) and creature
        # cost reducers (Goreclaw). Only ~3% of commanders open this big-mana lane, so
        # crediting power-6+ fatties is on-theme, not noise.
        serve_power_min=6,
        extras=(_CREATURE_COST_EXTRA,),
    ),
    # The `deals .* damage to target creature` branch missed every burn spell pointed at
    # ANY target (Lightning Bolt, Shock — "deals N damage to any target"). Broaden the
    # damage clause to any-target / player burn; constrain `.*` to a single clause.
    ("removal", "you"): _spec(
        "Removal / interaction",
        "destroy and burn removal — note indestructible/regeneration blank it",
        {"oracle": r"destroy target|deals .* damage to target"},
        r"destroy target (?:creature|permanent|artifact|enchantment|planeswalker|land"
        r"|nonland)"
        r"|deals? (?:\d+|x|that much) [^.\n]*damage to "
        r"(?:target (?:creature|permanent|planeswalker)|any target)",
    ),
    # task #87: pacify_makers — an Aura that neutralizes (not removes) what
    # it enchants (Pacifism, Arrest, Faith's Fetters, Prison Term). A
    # pacify-aura deck wants more of the same PLUS the removal/interaction
    # a pacify-only build still needs (a Pacifism-only pile can't answer an
    # already-attacking evasive threat or a nonpermanent spell).
    ("pacify_makers", "you"): _spec(
        "Pacify auras",
        "Auras that shut down attacking/blocking without removing the threat",
        {"preset_names": ("pacify-aura",)},
        r"enchanted (?:creature|permanent|artifact|land|planeswalker|battle)"
        r"[^.]*can'?t attack",
        serve_types=("Enchantment",),
    ),
    # task #np_roles: single_target_neutralize — the Darksteel Mutation /
    # Lignify / Frogify class: overwrite a threat's base power down to 0-1
    # (CR 613.4b layer 7b), usually stripping abilities too — the
    # commander answer that beats indestructible and dodges death
    # triggers. The pacify-adjacent neutralize shape (CR 611.2 — the
    # permanent stays on the battlefield, so it is deliberately NOT part
    # of `removal`); no theme_presets entry, matching `counter_hate`'s
    # narrow-lane precedent.
    ("single_target_neutralize", "you"): _spec(
        "Neutralize auras",
        "Auras that overwrite a threat's base power/toughness to ~1/1 "
        "(beats indestructible, dodges death triggers)",
        {
            "oracle": r"enchanted (?:creature|permanent)[^.]*"
            r"base power and toughness [01]/\d+"
        },
        r"enchanted (?:creature|permanent)[^.]*base power and toughness [01]/\d+",
    ),
    # VETO exile-and-return (blink): a card that exiles a creature then returns it is a
    # flicker engine, not removal (Ephemerate, Cloudshift) — CR 603.6e.
    ("exile_removal", "you"): _spec(
        "Exile removal",
        "exile-based removal that bypasses indestructible and stops recursion",
        {"oracle": r"exile target (?:creature|permanent|artifact|enchantment)"},
        r"exile target (?:creature|permanent|artifact|enchantment|nonland)",
        serve_not=r"return (?:it|them|that card|those cards|that permanent)"
        r"[^.]*battlefield",
    ),
    # ADR-0027 tranche2-B: exile_until_leaves's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — _is_exile_until_leaves). It used to be
    # auto-registered from that row (the SWEEP→SPECS fallback below), so hand-register
    # it now, keeping the old regex as the serve pattern.
    ("exile_until_leaves", "you"): _spec(
        *SWEEP_LABELS["exile_until_leaves"],
        {"oracle": r"exile [^.]*until [^.]*leaves the battlefield"},
        r"exile [^.]*until [^.]*leaves the battlefield",
    ),
    ("counter_control", "you"): _spec(
        "Counterspells / control",
        "counterspells and stack interaction",
        {"oracle": r"counter target"},
        r"counter target",
    ),
    # The bare `… (gain|have)` tail matched any "creatures you control gain/have X". Tie
    # it to the actual keyword-grant list or a static (+N/+N, not "until end of turn")
    # anthem, so a one-shot pump or a non-keyword clause doesn't read as a team grant.
    ("team_buff", "you"): _spec(
        "Team keyword grants",
        "keyword grants and anthems for your board",
        {"oracle": r"creatures you control (?:gain|have)"},
        r"creatures? you control (?:gain|gains|have|has) (?:flying|trample|menace"
        r"|hexproof|indestructible|protection|deathtouch|lifelink|double strike"
        r"|first strike|vigilance|haste|ward|reach)"
        r"|creatures you control get \+\d+/\+\d+",
        serve_not=r"creatures you control get \+\d+/\+\d+ until end of turn",
    ),
    # lf_ramp (2026-07-13): land-fetch-to-battlefield is RAMP, not tutor —
    # the serve side must not surface Rampant Growth / Cultivate / Nature's
    # Lore under the Tutors avenue (the ramp spec's serve already includes
    # land fetch). serve_not vetoes the fetch idiom only when the land word
    # directly follows the count words, so a mixed-mode search ("a creature
    # or land card" — Archdruid's Charm) still serves as a tutor.
    ("tutor", "you"): _spec(
        "Tutors",
        "tutors to assemble your key pieces and combos",
        {"oracle": r"search your library for"},
        r"search your library for",
        serve_not=(
            r"search your librar(?:y|ies) for (?:up to )?"
            r"(?:a |an |one |two |three |four |five |x |that many )?"
            r"(?:basic )?(?:cave|desert|forest|gate|island|lair|locus|mine"
            r"|mountain|plains|planet|power-plant|sphere|swamp|tower|town"
            r"|urza's|land)\b[^.]*onto the battlefield"
        ),
    ),
    ("untap_engine", "you"): _spec(
        "Untap engine",
        "untap effects to reuse tap abilities and generate value",
        {"oracle": _UNTAP_ORACLE},
        _UNTAP_ORACLE,
    ),
    # own_target_spell (iteration-4): served by the recursion engines that
    # rebate own-targeting spells (Feather-class) and copy engines (Zada).
    ("own_target_spell", "you"): _spec(
        "Own-target spell",
        "spell-recursion and copy engines that rebate spells targeting your "
        "own permanents",
        {"oracle": r"instant or sorcery spell that targets"},
        r"instant or sorcery spell that targets",
    ),
    # permanent_recast (iteration-3): a repeatable re-delivery engine — served
    # by the one-shot ETB/self-sac value permanents it re-delivers.
    ("permanent_recast", "you"): _spec(
        "Permanent recast engine",
        "one-shot ETB value permanents this engine re-delivers every turn",
        {"oracle": r"when(?:ever)? [^.]*enters(?: the battlefield)?, "},
        r"when(?:ever)? [^.]*enters(?: the battlefield)?, ",
    ),
    # self_etb_payload (iteration-3): a self-ETB value trigger — served by the
    # engines that re-deliver it (blink/flicker, recursion, bounce-to-replay);
    # CR 603.6a: enters triggers fire on every entry.
    ("self_etb_payload", "you"): _spec(
        "ETB value to re-deliver",
        "blink, recursion, and bounce engines that re-fire this card's "
        "enters-the-battlefield value",
        {
            "oracle": r"exile [^.]*return[^.]*battlefield|return [^.]*from your "
            r"graveyard to the battlefield|return [^.]*to (?:your|its "
            r"owner's) hand"
        },
        r"exile [^.]*return[^.]*battlefield|return [^.]*from your graveyard "
        r"to the battlefield",
    ),
    # Tap/untap commander (Tui and La) wants the untap effects that retrigger it.
    # ADR-0027: tap_untap_matters had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the `taps` trigger + a "becomes tapped/untapped" kept mirror).
    # The serve pool stays oracle-defined, so pass the deleted regex explicitly.
    ("tap_untap_matters", "you"): _sweep_spec_with_extras(
        "tap_untap_matters",
        (_UNTAP_EXTRA,),
        regex=(r"whenever [^.]*becomes? (?:tapped|untapped)|becomes? untapped, put"),
    ),
    # Activated-ability engine: the support package for a {T}: commander — activated-
    # ability cost reducers (Training Grounds), untappers + haste-for-abilities
    # (Thousand-Year Elixir, Ioreth), and ability copiers (Rings of Brighthearth,
    # Illusionist's Bracers — keyed on "isn't a mana ability", their shared marker).
    ("activated_ability", "you"): _spec(
        "Activated-ability engine",
        "cost reducers, untappers, haste-for-abilities, and copiers that power your "
        "commander's activated abilities",
        {"oracle": r"activated abilit|untap (?:target|another)"},
        r"activated abilities[^.]*\bcost\b"
        r"|untap (?:target|all|another|each)"
        # Untap-enablers re-tap a {T}: commander for extra activations (CR 302.6). The
        # bare clause above misses the aura/equipment forms that untap a single creature
        # — Freed from the Real / Pemmin's Aura "untap enchanted creature", Sting "untap
        # equipped creature" — and the "buff your creature, untap it" tricks (Shore Up).
        # Both are anchored to a CREATURE so land-untap ramp (Rude Awakening, "untap two
        # lands") stays out.
        r"|untap (?:enchanted|equipped) creature"
        r"|target creature you control[\s\S]{0,120}?untap it"
        r"|activate (?:its |their )?abilit(?:y|ies)[^.]*as though"
        r"|as though (?:those creatures|it|they) (?:had|have) haste"
        # Haste-GRANTERS lift summoning sickness (CR 302.6 / 702.10) so a {T}: commander
        # activates the turn it enters or re-enters (blink/reanimate). Anchored to a
        # grant clause ("<your/equipped/enchanted/target creature> ... gains/has haste")
        # so a vanilla creature with innate haste (just "Haste") does NOT match.
        r"|(?:creatures? you control|equipped creature|enchanted creature"
        r"|target creature)[^.]*(?:gains?|have|has) haste"
        r"|isn't a mana ability"
        # The PAYOFF targets: creatures with an expensive mana-cost activated ability
        # ("{8}:", "{3}{R}:", "{X}, {T}:") the cost-reducer/untapper exploits. Requires
        # a mana symbol in the cost (a {T}-only dork gains nothing from a discount).
        r"|\{(?:\d+|x)\}[^.:\n]{0,25}:",
    ),
    # YOU must be the one gaining control — VETO the donate shapes where an OPPONENT
    # gains control of your stuff (Sky Swallower). Add the exile-and-cast theft form.
    # ADR-0027 β: gain_control migrated to the Card IR (the lane fires from a gated
    # structural arm in crosswalk_signals._gain_control + a facade cross-open
    # reconciliation). This serve spec was always hand-registered with its
    # own curated SEARCH regex (broader than the deleted `gain control of` detector — it
    # also
    # credits "you control enchanted permanent" Auras and Bribery/Acquire library-
    # seizes), independent of the deleted producer, so it survives unchanged.
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        {"oracle": r"gain control of"},
        r"you (?:gain|may gain) control of"
        r"|gain control of (?:target|all|each|another|that|them|those)"
        r"|you control enchanted (?:creature|permanent)"
        r"|you may (?:play|cast)[^.]*from (?:that|target) (?:player|opponent)"
        # Bribery / Acquire: seize a card out of an OPPONENT's library and seat it
        # onto the battlefield UNDER YOUR CONTROL — you now control a permanent you
        # don't own (genuine gain-control), just sourced from a library. Anchored to
        # "opponent's library" so a graveyard reanimator is excluded. NOT the same as
        # the borrow-and-cast engines (Gonti / Hostage Taker / Thief): those exile a
        # card and let you CAST it — playing what you don't own (theft_matters), never
        # a battlefield control change — so they stay out of this lane.
        r"|opponent's library for [^.]*onto the battlefield under your control",
        serve_not=r"(?:opponent|another player|target player|that player) "
        r"gains control of",
    ),
    # Align the serve with the extraction regex so the wheel-punishers and "each
    # opponent/player discards" forms (Bottomless Pit, Hymn) are recovered.
    ("opponent_discard", "opponents"): _spec(
        "Hand attack",
        "forced discard and hand disruption aimed at opponents",
        {"oracle": r"opponent discards|each player discards|target player discards"},
        r"(?:each opponent|target opponent|an opponent|that opponent|each player"
        r"|target player|that player) discards|opponent[^.]*discards",
        extras=(_DISCARD_PUNISH_EXTRA, _HELLBENT_PUNISH_EXTRA),
    ),
    # Bare `can't be blocked` matched the menace/flying REMINDER "can't be blocked
    # except by …" on vanilla evasive creatures (~673). Exclude the "except" form (a
    # conditional restriction, CR 509.1b, not true unblockable) and add landwalk.
    ("evasion_self", "you"): _spec(
        "Evasion / unblockable",
        "unblockable and evasion to keep connecting — strong for voltron",
        {"oracle": r"can't be blocked|\bunblockable\b"},
        r"can't be blocked(?! except)|\bunblockable\b"
        r"|\b(?:forest|island|mountain|plains|swamp)walk\b",
        # Keyword-only evasion (horsemanship/menace/fear/intimidate/shadow/skulk) trips
        # the "can't be blocked except" lookahead, so credit it by Scryfall keyword[].
        serve_keywords=(
            "horsemanship",
            "menace",
            "fear",
            "intimidate",
            "shadow",
            "skulk",
        ),
        extras=(_COMBAT_SUPPORT_EXTRA,),
    ),
    # Ninjutsu (CR 702.49) returns an UNBLOCKED attacker to hand and puts the ninja in,
    # so a ninjutsu commander (Satoru Umezawa, Yuriko) wants cheap unblockable/evasive
    # creatures to reliably connect (Slither Blade, Mist-Cloaked Herald, Tormented Soul,
    # Ornithopter). Reuses the evasion_self classifier — unconditional unblockable +
    # hard-evasion keywords; flying is excluded (soft/blockable).
    ("has_ninjutsu", "you"): _spec(
        "Ninjutsu",
        "ninja creatures plus the cheap unblockable/evasive creatures to carry them in",
        {"oracle": r"can't be blocked|\bunblockable\b|\bninjutsu\b"},
        r"can't be blocked(?! except)|\bunblockable\b"
        r"|\b(?:forest|island|mountain|plains|swamp)walk\b",
        # The NINJA creatures themselves are the payoff (swapped in via ninjutsu off an
        # unblocked attacker), not just the evasion carriers. "Commander ninjutsu" is a
        # ninjutsu variant (CR 702.49d) — Yuriko/Satoru carry only that keyword, so the
        # lane must credit it or the canonical ninjutsu commander reads as a misfit.
        serve_keywords=(
            "ninjutsu",
            "commander ninjutsu",
            "horsemanship",
            "menace",
            "fear",
            "intimidate",
            "shadow",
            "skulk",
        ),
    ),
    ("clone_makers", "you"): _spec(
        "Clones / copies",
        "clone effects plus strong creatures worth copying",
        {
            "oracle": r"becomes a copy|copy of (?:target|another|any|a|that)\b"
            r"|as a copy of"
        },
        r"becomes a copy|copy of (?:target|another|any|a|that)\b|as a copy of",
        # Deliver on "strong creatures worth copying": a clone/token-copy deck wants big
        # bombs to copy (Etali, power 6). power_min=6 keeps it to genuine bombs.
        serve_power_min=6,
        # The token-copy GEAR is the same archetype: Helm of the Host ("a token that's
        # a copy of equipped creature"), Blade of Selves (myriad), Rite of Replication —
        # forms the bare "copy of target/that" serve missed (equipped/it/myriad). A copy
        # also ENTERS, so ETB payoffs (Impact Tremors) and doublers (Panharmonicon) hit.
        # The dies-value extra adds the smaller high-VALUE death dragons (cmc>=5, power
        # 4-5 — Kokusho/Keiga/Junji) the power-6 body floor missed.
        extras=(
            _COPY_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _CLONE_DIES_VALUE_EXTRA,
            _SELF_BOUNCE_RECAST_EXTRA,
        ),
    ),
    # _matters sweep: the benefit side of the clone split. wants_cloning fires when the
    # commander/deck is itself a worth-copying target (a repeatable engine or a big
    # ETB/dies bomb — the include_membership cross-open). The avenue it OPENS is the
    # clone ENABLERS to copy that target (Clone, Spark Double, Sakashima) plus the
    # token-copy gear (Helm of the Host, Rite of Replication). Same clone-effect search
    # as clone_makers, minus the power-6 bomb floor (here we want the copiers, not more
    # bodies to copy).
    ("wants_cloning", "you"): _spec(
        "Wants cloning",
        "clone enablers — your commander/creatures are worth copying",
        {
            "oracle": r"becomes a copy|copy of (?:target|another|any|a|that)\b"
            r"|as a copy of"
        },
        r"becomes a copy|copy of (?:target|another|any|a|that)\b|as a copy of",
        extras=(_COPY_EXTRA,),
    ),
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put big creatures onto the battlefield from hand or library",
        {"oracle": r"onto the battlefield"},
        r"onto the battlefield from your (?:hand|library)"
        r"|put .*creature card.*onto the battlefield",
        # The PAYOFF of a cheat-into-play deck is the fat creatures it cheats in
        # (Craterhoof, Worldspine Wurm, Eldrazi) — credit big bodies as on-theme.
        serve_power_min=5,
    ),
    # Greedy `return target .*owner's hand` matched "return target spell" (Reprieve →
    # counterspell space) and spanned clauses. Constrain the object + the dot.
    ("bounce_tempo", "you"): _spec(
        "Bounce / tempo",
        "bounce effects for tempo and ETB re-use",
        {"oracle": r"return target .*to (?:its|their) owner's hand"},
        r"return (?:up to \w+ )?target (?:creature|permanent|nonland permanent)"
        r"[^.\n]*to (?:its|their) owner's hand",
    ),
    # _matters sweep (ADR-0034): the cascade build-around is driven by an
    # intrinsic-cascader commander (The First Sliver, Apex Devastator) — a
    # cascade_makers card — so the "Cascade" avenue attaches to cascade_makers.
    # The serve regex \bcascade\b serves makers + granters + payoffs alike.
    ("cascade_makers", "you"): _spec(
        "Cascade",
        "high-value spells to hit off cascade plus more cascade enablers",
        {"oracle": r"\bcascade\b"},
        r"\bcascade\b",
        # Cascade cheats big nonland bombs into play for free — credit genuine fatties
        # (Ghalta, Etali) as the payoff, not just more cascade sources.
        serve_power_min=6,
    ),
    # _matters sweep (ADR-0034): the PAYOFF side — a keyword-less cascade granter
    # / cares-about reference (Maelstrom Nexus, Yidris, Averna). Same cascade
    # build-around: surface the high-value spell pool to hit off cascade plus
    # more cascade sources to thread through the granter.
    ("cascade_matters", "you"): _spec(
        "Cascade payoffs",
        "high-value spells to hit off cascade plus more cascade enablers",
        {"oracle": r"\bcascade\b"},
        r"\bcascade\b",
        serve_power_min=6,
    ),
    ("regenerate_makers", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        {"oracle": r"\bregenerate\b"},
        r"\bregenerate\b",
        # A regenerating/resilient beater is a voltron plan — surface the gear, buff
        # Auras (Rancor, Bear Umbra), and protection (Alpha Authority) you suit it with.
        extras=(_COMBAT_SUPPORT_EXTRA, _VOLTRON_PROTECT_EXTRA),
    ),
    # Drop the bare `opponents? cast` — only the TRIGGER/tax forms are punishers.
    ("opponent_cast_matters", "opponents"): _spec(
        "Punish opponents' spells",
        "taxes and punishers that trigger when opponents cast",
        {"oracle": r"whenever an opponent casts|spells? your opponents cast"},
        r"whenever an opponent casts|whenever a player casts"
        r"|spells? your opponents cast",
    ),
    # Drop the bare `opponents? draws?` — it matched group-hug GIFT effects (Master of
    # the Feast) that HAND opponents cards rather than punishing the draw.
    ("opponent_draw_matters", "opponents"): _spec(
        "Punish opponents' draw",
        "wheels and draw-denial punishers that trigger on opponents drawing",
        {"oracle": r"whenever an opponent draws|each opponent draws|each player draws"},
        r"whenever an opponent draws|whenever each opponent draws"
        r"|whenever a player (?:other than you )?draws"
        r"|whenever a player draws a card (?:except|other than)"
        # The ENABLERS that make opponents draw extra (so the punish fires): symmetric
        # group-draw (Temple Bell, Howling Mine, Dictate of Kruphix), forced opponent
        # draw (Forced Fruition), and wheels (Windfall). NOT "target player draws" or
        # your own cantrip — those needn't benefit opponents.
        r"|each player draws|all players draw|each opponent draws"
        r"|target (?:player|opponent) draws|that player draws"
        r"|each player's draw step"
        r"|discards? (?:their|his or her) hand[^.]*draws?",
    ),
    # Drop the bare `search their library` — your OWN tutor reads "search their
    # library" too (Path to Exile). Require an opponent/player subject.
    ("opponent_search_matters", "opponents"): _spec(
        "Punish opponents' tutors / selection",
        "stax and punishers for opponents who search, scry, or surveil",
        {"oracle": r"opponent[^.]*(?:search|scry|surveil)|search(?:es)? their library"},
        r"(?:opponent|each player|a player)[^.]*(?:scries|surveils|searches "
        r"(?:their|a) library)"
        r"|whenever (?:an opponent|each opponent|a player)[^.]*search"
        r"|if an opponent would search",
    ),
    ("damage_to_opp_matters", "opponents"): _spec(
        "Damage to opponents",
        "evasion, pingers, and extra combats to keep connecting and fire these "
        "damage-to-opponent triggers (any damage, not just combat)",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals (?:noncombat )?damage to (?:a player|an opponent|one of your opponents"
        r"|that player|each opponent)|can't be blocked(?! except)|\bunblockable\b",
    ),
    # `enters the battlefield` is a DEAD branch — Scryfall templated the phrase down to
    # bare "enters" years ago (CR glossary), so it matched ~1 card and the serve missed
    # every Panharmonicon/Yarok ETB-engine. Key on the ETB-trigger / flicker clauses.
    ("permanent_etb", "you"): _spec(
        "Permanents entering",
        "cheap permanents, token makers, and flicker to repeatedly trigger your "
        "permanent enters-the-battlefield value engine",
        {"oracle": r"create [^.]*token|enters the battlefield"},
        r"create [^.]*token|put [^.]*onto the battlefield"
        r"|when (?:this|[A-Z][\w']+)[^.]*enters"
        r"|(?:a|an|another|one or more)[^.]*permanents? you control enters"
        r"|(?:artifact or creature|creature or artifact)[^.]*enter",
        extras=(_FLICKER_EXTRA, _DIES_RECURSION_EXTRA, _SELF_BOUNCE_EXTRA),
    ),
    # Serve was `…|\bequipment\b|whenever[^.]*attacks`, which matched any creature
    # that merely mentions equipment or attacks (~1104). The avenue is Equipment-for-a-
    # dasher: gate on the Equipment TYPE (CR 301.5 — the persistent buff) and the dash /
    # reconfigure KEYWORD (CR 702.109/702.151), plus a small oracle branch for cards
    # that move/cheat Equipment without the subtype.
    ("has_dash", "you"): _spec(
        "Dash / hit-and-run Equipment",
        "Equipment — it stays on the battlefield when Dash returns the creature to "
        "your hand at end of turn (Auras and counters don't), so it's the resilient "
        "buff for a recurring haste attacker; plus haste enablers and cheap recursion",
        {"preset_names": ("equip",)},
        r"equip \{|attach [^.]*equipment",
        serve_types=("equipment",),
        serve_keywords=("dash", "reconfigure"),
    ),
}
