"""Signal specs data slice 3/4: SPECS dict entries (lines 4563-5823 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

import re

from mtg_utils._analysis._sweep_detectors import (
    SWEEP_LABELS,
)

from ._shared import (
    _AMASS_SERVE_IDENTS,
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
    _IC,
    _PLUS_ONE_PLACERS,
    _SELF_BOUNCE_EXTRA,
    _SELF_BOUNCE_RECAST_EXTRA,
    _TOKEN_DOUBLER_EXTRA,
    _TOKEN_MAKER_EXTRA,
    _UNTAP_EXTRA,
    _VOLTRON_PROTECT_EXTRA,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
    _sweep_spec_with_extras,
)

_CONNIVE_SERVE_IDENTS = frozenset({"connive_makers|you|", "connive_matters|you|"})

# The explore serve (explore_makers / explore_matters): both lanes.
_EXPLORE_SERVE_IDENTS = frozenset({"explore_makers|you|", "explore_matters|you|"})

# The activated-ability engine's enablers: haste grants (Thousand-Year Elixir's
# "as though it had haste" by pattern, the grant lanes' haste by ident) and
# activated-ability cost reducers (Training Grounds). The untaps of one creature
# (Freed from the Real) are the main serve's ``untap_engine`` ident. Find and the
# tuner page the extra by its serve (``pages_by_serve``), so the pattern below is
# only the serve's arm.
_ABILITY_HASTE_COST_ORACLE = (
    r"activated abilities[^.]*\bcost\b"
    r"|activate (?:its |their )?abilit(?:y|ies)[^.]*as though"
    r"|as though (?:those creatures|it|they) (?:had|have) haste"
)
_ABILITY_HASTE_COST_EXTRA = SubAvenue(
    "Untap, haste and cheaper activations",
    "untap the tapper again, give it haste, or cut its activation cost "
    "(Freed from the Real, Thousand-Year Elixir, Training Grounds)",
    serve=Serve(
        oracle=re.compile(_ABILITY_HASTE_COST_ORACLE, _IC),
        signal_idents=frozenset(
            {
                "keyword_grant_target|you|haste",
                "team_buff|you|haste",
                "aura_equip_kw_grant|you|haste",
                "all_creatures_kw_grant|any|haste",
            }
        ),
    ),
)

# The dash avenue's Equipment movers (Brass Squire, Armory Automaton): the
# "attach … Equipment" arm of the old serve regex, moved here verbatim — the
# Equipment themselves serve through the type arm.
_EQUIPMENT_MOVER_ORACLE = r"attach [^.]*equipment"
_EQUIPMENT_MOVER_EXTRA = SubAvenue(
    "Equipment movers",
    "cards that attach your Equipment for free (Brass Squire, Armory Automaton)",
    serve=Serve(oracle=re.compile(_EQUIPMENT_MOVER_ORACLE, _IC)),
)

# clone_makers / copy_permanent / wants_cloning share one serve: every copy lane.
_CLONE_SERVE_IDENTS = frozenset(
    {"clone_makers|you|", "copy_permanent|you|", "token_copy_makers|you|"}
)

SPECS_3: dict[tuple[str, str], SignalSpec] = {
    # ── Mechanics recovered from the "rejected" families ────────────────────────
    # ADR-0027 β: token_copy_makers migrated to the Card IR via a byte-identical kept-
    # mirror (the lane fires structurally from crosswalk_signals.py). This serve
    # spec was always hand-registered and independent of the deleted _HAND_FLOOR
    # producer, so it survives unchanged; the "twice that many … tokens" doubler arm is
    # the _TOKEN_DOUBLER_EXTRA below, a separate avenue.
    ("token_copy_makers", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        # Serve idents: the token-copy lane. The self-copy keywords the lane excludes
        # by design (embalm, eternalize, squad, myriad) still serve by keyword.
        None,
        serve_idents=frozenset({"token_copy_makers|you|"}),
        serve_keywords=("embalm", "eternalize", "squad", "myriad"),
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
        # Serve idents: the clone, permanent-copy and token-copy lanes. The leftover
        # is spell-copy reminder text; Estrid's Invocation is a phase gap.
        None,
        serve_idents=_CLONE_SERVE_IDENTS,
    ),
    # Serve on the lanes' idents: the +1/+1 counter package
    # (plus_one_makers reads the amass / incubate actions themselves) and, for
    # amass, the Army payoffs.
    ("amass_makers", "you"): _spec(
        "Amass",
        "amass sources plus Army / +1/+1-counter payoffs",
        None,
        serve_idents=_AMASS_SERVE_IDENTS,
    ),
    ("incubate_makers", "you"): _spec(
        "Incubate",
        "incubate sources plus artifact-token / +1/+1-counter payoffs",
        None,
        serve_idents=_PLUS_ONE_PLACERS,
    ),
    ("specialize_matters", "you"): _spec(
        "Specialize",
        "specialize payoffs to swap a creature's stat/ability line "
        "(Backgrounds are a separate axis — see Partner / Background)",
        # The lane reads exactly the regex's cards.
        None,
        serve_idents=frozenset({"specialize_matters|you|"}),
    ),
    # ADR-0027: ki_counter_matters + seek_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — phase's
    # counter-kind / effect-category projection), so hand-register the spec the
    # sweep auto-register loop used to build. (SWEEP_LABELS still carries the human
    # label.)
    ("ki_counter_makers", "you"): _spec(
        *SWEEP_LABELS["ki_counter_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"ki_counter_makers|you|", "ki_counter_matters|you|"}),
    ),
    ("ki_counter_matters", "you"): _spec(
        *SWEEP_LABELS["ki_counter_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"ki_counter_makers|you|", "ki_counter_matters|you|"}),
    ),
    ("seek_matters", "you"): _spec(
        *SWEEP_LABELS["seek_matters"],
        # Serve idents: every seek the lane reads, including the opponent-side "its
        # owner seeks" cards. Seeks phase drops (a Rat card, a Merfolk card) leave.
        None,
        serve_idents=frozenset({"seek_matters|you|"}),
    ),
    # ADR-0027: mass_bounce + destroy_legendary had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — the bounce/destroy effect shape).
    # Each is hand-registered; the serve is the lane's idents. (SWEEP_LABELS still
    # carries the human label.)
    ("mass_bounce", "any"): _spec(
        *SWEEP_LABELS["mass_bounce"],
        # The lane reads an overloaded Cyclonic Rift, Aetherize and Engulf the Shore;
        # graveyard returns (Infernal Caretaker) drop out. Artifact / enchantment sweeps
        # (Rebuild) and Soulquake are lane gaps.
        None,
        serve_idents=frozenset({"mass_bounce|any|", "mass_land_denial|each|bounce"}),
    ),
    # The population shrink (2026-10-24): the board-wipe preset's third key, beside
    # mass_removal and mass_bounce. Its avenue pages the preset.
    ("population_shrink", "any"): _spec(
        "Shrink sweeps",
        "toughness shrinks over a board of creatures, one-sided or continuous",
        None,
        serve_idents=frozenset({"population_shrink|any|"}),
        search={"preset_names": ("board-wipe",)},
    ),
    ("destroy_legendary", "any"): _spec(
        *SWEEP_LABELS["destroy_legendary"],
        # Serve idents (2026-10-18): the regex missed 'destroy all legendary creatures'
        # (Invasion of Fiora).
        None,
        serve_idents=frozenset({"destroy_legendary|any|"}),
    ),
    # ADR-0027: the four bending lanes had their oracle-regex SWEEP_DETECTORS rows
    # deleted (detection moved to the Card IR — the kept word-detector mirror in
    # signals._IR_KEPT_DETECTORS), so hand-register the spec the sweep
    # auto-register loop used to build. (SWEEP_LABELS still carries the human
    # label.)
    ("airbend_makers", "you"): _spec(
        *SWEEP_LABELS["airbend_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"airbend_makers|you|"}),
    ),
    # _matters sweep (ADR-0034): earthbend split. The DOER arm (earthbend_makers,
    # keyword bearers) and the PAYOFF arm (earthbend_matters, keyword-less cross-bend
    # references) both serve the same pool — clone-pilot precedent: the serve
    # avenue legitimately offers makers + payoffs together; only membership splits by
    # role.
    ("earthbend_makers", "you"): _spec(
        *SWEEP_LABELS["earthbend_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"earthbend_makers|you|", "earthbend_matters|you|"}),
    ),
    ("earthbend_matters", "you"): _spec(
        *SWEEP_LABELS["earthbend_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"earthbend_makers|you|", "earthbend_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): waterbend split. The DOER arm (waterbend_makers,
    # keyword bearers) and the PAYOFF arm (waterbend_matters) both serve the same
    # pool — clone-pilot precedent: the serve avenue legitimately offers
    # makers + payoffs together; only membership splits by role.
    ("waterbend_makers", "you"): _spec(
        *SWEEP_LABELS["waterbend_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"waterbend_makers|you|", "waterbend_matters|you|"}),
    ),
    ("waterbend_matters", "you"): _spec(
        *SWEEP_LABELS["waterbend_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"waterbend_makers|you|", "waterbend_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): firebending split. The MAKER arm (firebending_makers,
    # Firebending-keyword bearers) and the PAYOFF arm (firebending_matters, keyword-less
    # Fire-Nation references) both serve the same pool — clone-pilot precedent:
    # the serve avenue legitimately offers makers + payoffs together; only membership
    # splits by role.
    ("firebending_makers", "you"): _spec(
        *SWEEP_LABELS["firebending_makers"],
        # Serve idents (2026-10-18): the regex served the name of a plain burn spell
        # (Firebending Lesson).
        None,
        serve_idents=frozenset({"firebending_makers|you|", "firebending_matters|you|"}),
    ),
    ("firebending_matters", "you"): _spec(
        *SWEEP_LABELS["firebending_matters"],
        # Serve idents (2026-10-18): the regex served the name of a plain burn spell
        # (Firebending Lesson).
        None,
        serve_idents=frozenset({"firebending_makers|you|", "firebending_matters|you|"}),
    ),
    # ADR-0027 (t2b2-A): aura_equip_kw_grant / counter_grants_kw /
    # conditional_self_protection had their oracle-regex SWEEP_DETECTORS rows deleted
    # (detection moved to the Card IR — the grant_keyword effect shape gated on the
    # subject Filter + the granted keyword). Each is hand-registered; the serve is the
    # lane's ident. (SWEEP_LABELS still carries each human label.)
    ("aura_equip_kw_grant", "you"): _spec(
        *SWEEP_LABELS["aura_equip_kw_grant"],
        # The lane also reads a one-shot grant (Hemlock Vial, Silkguard). Every
        # keyword an Aura or Equipment grants (the lane's subject) is the theme's:
        # Lightning Greaves' haste and shroud.
        None,
        serve_idents=frozenset({"aura_equip_kw_grant|you|*"}),
    ),
    ("counter_grants_kw", "you"): _spec(
        *SWEEP_LABELS["counter_grants_kw"],
        # The lane also reads "creatures you control with counters on them" and keywords
        # the regex list left out (Bushmaster, Cathedral Acolyte, Longshot Squad).
        None,
        serve_idents=frozenset({"counter_grants_kw|you|"}),
    ),
    ("conditional_self_protection", "you"): _spec(
        *SWEEP_LABELS["conditional_self_protection"],
        # The lane reads every "as long as" self-grant (Angelic Overseer, Fleecemane
        # Lion); granted shapes (Bilbo's Ring, Giant's Amulet) and Bello are lane gaps.
        None,
        serve_idents=frozenset({"conditional_self_protection|you|"}),
    ),
    # ADR-0027: attractions_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to an _IR_KEPT_DETECTORS word mirror), so hand-register the spec
    # the sweep auto-register loop used to build.
    # Serve on the lane's ident: the lane reads phase's typed open / roll-to-visit
    # nodes beside its word row (Step Right Up, Line Cutter).
    ("attractions_matter", "you"): _spec(
        *SWEEP_LABELS["attractions_matter"],
        None,
        serve_idents=frozenset({"attractions_matter|you|"}),
    ),
    # ADR-0027: stickers_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to a byte-identical STICKERS_MATTER_REGEX _IR_KEPT_DETECTORS word
    # mirror), so hand-register the spec the sweep auto-register loop used to build.
    ("stickers_matter", "you"): _spec(
        *SWEEP_LABELS["stickers_matter"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"stickers_matter|you|"}),
    ),
    # ADR-0027 tranche2-C: extra_land_drop had its oracle-regex SWEEP_DETECTORS row
    # deleted (detection moved to the Card IR — cheat_play / topdeck_select with a Land
    # subject + a kept word mirror), so hand-register the spec the sweep auto-register
    # loop used to build.
    ("extra_land_drop", "you"): _spec(
        *SWEEP_LABELS["extra_land_drop"],
        # Serve idents (2026-10-18): the regex missed library-to-battlefield land puts
        # (Kamahl's Druidic Vow).
        None,
        serve_idents=frozenset({"extra_land_drop|you|"}),
    ),
    # ADR-0027: companion_keyword had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Scryfall `companion` keyword), so hand-register the spec
    # the sweep auto-register loop used to build.
    ("companion_keyword", "you"): _spec(
        *SWEEP_LABELS["companion_keyword"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"companion_keyword|you|"}),
    ),
    # ADR-0027: has_soulbond had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `soulbond` keyword + a
    # `soulbond` effect marker for non-keyword references), so hand-register the spec
    # the sweep auto-register loop used to build.
    ("has_soulbond", "you"): _spec(
        *SWEEP_LABELS["has_soulbond"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"has_soulbond|you|"}),
    ),
    # ADR-0027: has_devour had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `devour` keyword + phase's
    # `devour` effect category), so hand-register the spec the sweep auto-register
    # loop used to build. (SWEEP_LABELS still carries the human label.)
    ("has_devour", "you"): _spec(
        *SWEEP_LABELS["has_devour"],
        # Serve idents (2026-10-18): the regex served 'Devour' in card names (Devour in
        # Flames, Intellect Devourer).
        None,
        serve_idents=frozenset({"has_devour|you|"}),
    ),
    # ADR-0027 tail-supplement: boast/exhaust/explore/phasing/end_the_turn/
    # trigger_doubling each had their oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — keyword array + effect-category + supplement
    # markers), so hand-register the spec the sweep auto-register loop used to build.
    # _matters sweep (ADR-0034): the MAKER arm of the boast split — boast creatures
    # (cards carrying the Boast ability). Same serve pool as the payoff arm.
    ("boast_makers", "you"): _spec(
        *SWEEP_LABELS["boast_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"boast_makers|you|", "boast_matters|you|"}),
    ),
    ("boast_matters", "you"): _spec(
        *SWEEP_LABELS["boast_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"boast_makers|you|", "boast_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the exhaust split — cards carrying
    # an Exhaust ability. Same serve pool as the payoff arm.
    ("exhaust_makers", "you"): _spec(
        *SWEEP_LABELS["exhaust_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"exhaust_makers|you|", "exhaust_matters|you|"}),
    ),
    ("exhaust_matters", "you"): _spec(
        *SWEEP_LABELS["exhaust_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"exhaust_makers|you|", "exhaust_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): the MAKER arm of the explore split — creatures that
    # explore. One serve pool for both arms, on the lanes' idents: explore_makers
    # reads a granted explore (Glowcap Lantern) and Map tokens. Not served:
    # Nicanzil's "explores a land card" payoff (phase: an Unknown trigger mode) and
    # Worldwalker Helm's replacement-made Map.
    ("explore_makers", "you"): _spec(
        *SWEEP_LABELS["explore_makers"],
        None,
        serve_idents=_EXPLORE_SERVE_IDENTS,
    ),
    ("explore_matters", "you"): _spec(
        *SWEEP_LABELS["explore_matters"],
        None,
        serve_idents=_EXPLORE_SERVE_IDENTS,
    ),
    ("phasing_makers", "you"): _spec(
        *SWEEP_LABELS["phasing_makers"],
        # Serve idents (2026-10-18): the regex served phasing's reminder text on a lock
        # aura (Cloak of Invisibility).
        None,
        serve_idents=frozenset({"phasing_makers|you|"}),
    ),
    # ADR-0027 / _matters sweep (ADR-0034): the Station/Spacecraft lane migrated to the
    # Card IR and then SPLIT into station_makers (the Spacecraft/Planet bodies + the
    # chargers that PERFORM Station) and station_matters (the Spacecraft-ref payoffs).
    # Both serve the SAME Station/Spacecraft pool (the avenue composes maker + payoff).
    ("station_makers", "you"): _spec(
        "Station / Spacecraft",
        "Spacecraft/Planet to station plus ways to charge them",
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"station_makers|you|", "station_matters|you|"}),
    ),
    ("station_matters", "you"): _spec(
        *SWEEP_LABELS["station_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"station_makers|you|", "station_matters|you|"}),
    ),
    # ADR-0027: tap_down migrated to the Card IR (its SWEEP_DETECTORS row is deleted, so
    # the auto-register loop no longer builds this spec). Hand-register it. Scope
    # 'opponents' (the deleted SWEEP row's forced scope). SWEEP_LABELS still carries
    # the human label.
    ("tap_down", "opponents"): _spec(
        *SWEEP_LABELS["tap_down"],
        # Serve idents (2026-10-18): the regex missed tappers that don't say 'an
        # opponent controls' (Blustersquall).
        None,
        serve_idents=frozenset({"tap_down|opponents|"}),
    ),
    ("end_the_turn", "you"): _spec(
        *SWEEP_LABELS["end_the_turn"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"end_the_turn|you|"}),
    ),
    ("trigger_doubling", "you"): _spec(
        *SWEEP_LABELS["trigger_doubling"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"trigger_doubling|you|"}),
    ),
    # ADR-0027: cant_block_grant had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `cant_block` effect category + a
    # modal/granted-quoted dropped-static face marker). Hand-registered; the serve is
    # the lane's ident.
    ("cant_block_grant", "you"): _spec(
        *SWEEP_LABELS["cant_block_grant"],
        # The lane holds every regex card plus the mass and Aura forms (Bedlam,
        # Demotion).
        None,
        serve_idents=frozenset({"cant_block_grant|you|"}),
    ),
    # ADR-0027: convoke_matters / myriad_grant / typed_anthem_multi / life_total_set
    # each had their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the
    # Card IR — keyword array + effect-category + supplement markers), so hand-register
    # the spec the sweep auto-register loop used to build.
    ("convoke_matters", "you"): _spec(
        *SWEEP_LABELS["convoke_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"convoke_makers|you|", "convoke_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): the DOER/ENABLER side of the convoke split (the
    # `convoke` keyword bearers + the "<type> spells you cast have convoke" granters).
    # Same serve pool as the payoff — both want wide, cheap creatures to tap.
    ("convoke_makers", "you"): _spec(
        *SWEEP_LABELS["convoke_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"convoke_makers|you|", "convoke_matters|you|"}),
    ),
    # ADR-0027 t2b4a-B: win_lose_game / alt_cost_keyword / partner_background each had
    # their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the Card IR —
    # win/lose Effect categories; the alt-cost & partner-family Scryfall keyword
    # arrays), so hand-register the spec the sweep auto-register loop used to build.
    # (SWEEP_LABELS still carries each human label.)
    ("win_lose_game", "any"): _spec(
        *SWEEP_LABELS["win_lose_game"],
        # Serve idents: the lane's win/lose-the-game cards, which reach a flip- or
        # clause-gated "you win/lose" the regex missed. Frodo is a phase gap.
        None,
        serve_idents=frozenset({"win_lose_game|any|"}),
    ),
    ("alt_cost_keyword", "you"): _spec(
        *SWEEP_LABELS["alt_cost_keyword"],
        # Serve on the lane's ident: the lane reads a granted sneak /
        # mayhem / web-slinging too (Ninja Teen, Green Goblin, Amazing
        # Spider-Man); the regex also matched Lightfoot Rogue's "Sneak Attack"
        # flavor word.
        None,
        serve_idents=frozenset({"alt_cost_keyword|you|"}),
        serve_keywords=("web-slinging", "sneak", "mayhem"),
    ),
    # partner_background's avenue REPLACES this serve with a partner-legality search
    # (engine.partner_search + the ADR-0019 color-widening flag); this spec is the
    # fallback pool — the cards that carry a partner-family keyword.
    ("partner_background", "you"): _spec(
        *SWEEP_LABELS["partner_background"],
        # Serve idents (2026-10-18): the regex served a 'doctor's companion' search (An
        # Unearthly Child).
        None,
        serve_idents=frozenset({"partner_background|you|"}),
        # No bare "friends": that keyword is Astarion, the Decadent's "Friends —"
        # flavor word (CR 207.2d); "Partner—Friends forever" carries 'Partner'.
        serve_keywords=(
            "partner",
            "partner with",
            "choose a background",
            "doctor's companion",
        ),
    ),
    # ADR-0027 t2b5-C: named_counter_misc / powerup_matters each had their oracle-regex
    # SWEEP_DETECTORS row deleted (detection moved to the Card IR — named_counter_misc
    # to the kept word mirror; powerup_matters to the Scryfall Power-up keyword array).
    # Each had no hand spec, so the sweep auto-register loop built its serve; reproduce
    # that spec here, reusing SWEEP_LABELS.
    ("named_counter_misc", "you"): _spec(
        *SWEEP_LABELS["named_counter_misc"],
        # Serve idents (2026-10-18): the regex listed a dozen counter names and missed
        # the rest (Bomb Squad's fuse counters).
        None,
        serve_idents=frozenset({"named_counter_misc|you|"}),
    ),
    ("powerup_matters", "you"): _spec(
        *SWEEP_LABELS["powerup_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"powerup_matters|you|"}),
        serve_keywords=("power-up",),
    ),
    # ADR-0027: rad_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `rad_counter` effect / rad place_counter
    # + a "rad counter(s)" face marker). The IR fires scope "opponents" (rad counters go
    # on players as a kill clock). Serve hand-registered.
    ("rad_counter_makers", "opponents"): _spec(
        *SWEEP_LABELS["rad_counter_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"rad_counter_makers|opponents|"}),
    ),
    # ADR-0027: oil_counter_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter(counter_kind='oil') placer
    # + an "oil counter(s)" payoff marker). Serve hand-registered so the lane still
    # surfaces oil sources and payoffs.
    # _matters sweep (ADR-0034): the MAKER side of the oil split (cards that
    # PLACE oil counters). Same serve pool as the payoff lane — the avenue
    # legitimately offers oil sources + payoffs together (ADR-0034: only
    # membership splits by role, the serve avenue composes both).
    ("oil_counter_makers", "you"): _spec(
        *SWEEP_LABELS["oil_counter_makers"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"oil_counter_makers|you|", "oil_counter_matters|you|"}),
    ),
    ("oil_counter_matters", "you"): _spec(
        *SWEEP_LABELS["oil_counter_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"oil_counter_makers|you|", "oil_counter_matters|you|"}),
    ),
    # ADR-0027: shield_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter / hascounters
    # counter_kind='shield' structural arm + a byte-identical kept word mirror), so
    # hand-register the spec the sweep auto-register loop used to build. CR 122.1c.
    ("shield_counter_makers", "you"): _spec(
        *SWEEP_LABELS["shield_counter_makers"],
        # Serve on the lane's ident. Not served: Call In a Professional's "Shield
        # counters don't prevent this damage" reminder, and two shield counters
        # phase drops — Elspeth
        # Resplendent's dig "onto the battlefield with a shield counter" and
        # Undercover Operative's copy "except it enters with a shield counter".
        None,
        serve_idents=frozenset({"shield_counter_makers|you|"}),
    ),
    # ADR-0027: fight_makers had its oracle-regex SWEEP_DETECTORS row deleted (moved to
    # the Card IR — phase's fight effect + a granted/quoted/modal fight marker). Serve
    # hand-registered (the lane wants big creatures to fight with — surface fatties via
    # power_min).
    ("fight_makers", "you"): _sweep_spec_with_extras(
        "fight_makers",
        serve_power_min=4,
        # Serve idents (2026-10-18): the regex missed mass and granted fights (Grothama,
        # All-Devouring).
        serve_idents=frozenset({"fight_makers|you|"}),
    ),
    # ADR-0027: has_changeling had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall changeling keyword + a "changeling"
    # / "is every creature type" all-tribes marker). Serve hand-registered (plus the
    # changeling keyword dimension for the bearers).
    ("has_changeling", "you"): _spec(
        *SWEEP_LABELS["has_changeling"],
        # Serve idents (2026-10-18): the regex missed 'all creature types' lands and
        # grants (Mutavault).
        None,
        serve_idents=frozenset({"has_changeling|you|"}),
        serve_keywords=("changeling",),
    ),
    # ADR-0027: starting_life_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a "starting life total" compare marker). Serve
    # hand-registered.
    ("starting_life_matters", "you"): _spec(
        *SWEEP_LABELS["starting_life_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"starting_life_matters|you|"}),
    ),
    ("myriad_grant", "you"): _spec(
        *SWEEP_LABELS["myriad_grant"],
        # Serve idents (2026-10-18): the regex served a card name (The Everflowing Well
        # // The Myriad Pools).
        None,
        serve_idents=frozenset({"myriad_grant|you|"}),
    ),
    ("typed_anthem_multi", "you"): _spec(
        *SWEEP_LABELS["typed_anthem_multi"],
        # The lane reads the "Skeletons and Zombies you control" form (Death Baron,
        # Gisa) the "that's a" template missed.
        None,
        serve_idents=frozenset({"typed_anthem_multi|you|"}),
    ),
    ("life_total_set", "any"): _spec(
        *SWEEP_LABELS["life_total_set"],
        # The lane reads "your life total becomes" (Loxodon Lifechanter) and a doubled
        # life total (Celestial Mantle); Heartless Hidetsugu's half-life damage drops
        # out.
        None,
        serve_idents=frozenset({"life_total_set|any|"}),
    ),
    # ADR-0027: all_creatures_kw_grant + facedown_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # GrantKeyword effect / the manifest-cloak-morph effect categories + kept word
    # mirror). Each is hand-registered; the serve is the lane's ident.
    ("all_creatures_kw_grant", "any"): _spec(
        *SWEEP_LABELS["all_creatures_kw_grant"],
        # The lane also reads one-shot "all creatures gain" spells and protection grants
        # (Demoralize, Absolute Grace), whatever the keyword (its subject).
        None,
        serve_idents=frozenset({"all_creatures_kw_grant|any|*"}),
    ),
    ("facedown_matters", "you"): _spec(
        *SWEEP_LABELS["facedown_matters"],
        # Serve idents (2026-10-18): the regex missed turned-face-up payoffs (Bonethorn
        # Valesk) and served 'cloak' in card names (Cloak and Dagger, Entwined).
        None,
        serve_idents=frozenset({"facedown_makers|you|", "facedown_matters|you|"}),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the facedown split. facedown_makers
    # fires on the morph/megamorph/disguise/manifest/cloak/manifest-dread bodies that
    # PUT a face-down 2/2 on the battlefield (CR 708). The avenue serves more of those
    # face-down 2/2 makers plus the turn-face-up payoffs the deck wants alongside them
    # (the avenue composes makers + payoffs per ADR-0034).
    ("facedown_makers", "you"): _spec(
        "Face-down makers",
        "morph/manifest/disguise/cloak creatures that enter face down",
        # Serve idents (2026-10-18): the regex missed turned-face-up payoffs (Bonethorn
        # Valesk) and served 'cloak' in card names (Cloak and Dagger, Entwined).
        None,
        serve_idents=frozenset({"facedown_makers|you|", "facedown_matters|you|"}),
    ),
    # ADR-0027: affinity_type + evasion_denial had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — affinity ← the Scryfall keyword +
    # an `affinity` conferred-grant marker; evasion_denial ← phase's named-walk
    # evasion_denial effect + a generic-landwalk-umbrella marker). The auto-register
    # sweep loop used to build their serve specs from the now-gone rows, so hand-
    # register them.
    ("affinity_type", "you"): _spec(
        *SWEEP_LABELS["affinity_type"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"affinity_type|you|"}),
    ),
    ("evasion_denial", "opponents"): _spec(
        *SWEEP_LABELS["evasion_denial"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"evasion_denial|opponents|"}),
    ),
    # ADR-0027: lure_makers had its oracle-regex SWEEP_DETECTORS row deleted (detection
    # moved to the Card IR — a structural `lure` arm + a byte-identical kept mirror for
    # the Aftermath-DFC back face phase drops), so hand-register the spec the sweep
    # auto-register loop used to build (scope 'you'). CR 509.1c.
    ("lure_makers", "you"): _spec(
        *SWEEP_LABELS["lure_makers"],
        # Serve idents (2026-10-18): the regex missed subtype lures (Talruum Piper's
        # 'creatures with flying').
        None,
        serve_idents=frozenset({"lure_makers|you|"}),
    ),
    # ADR-0027: damage_doubling had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the damage_doubling DamageDone-replacement category, now
    # covering triple + the nested AddTargetReplacement / CreateDamageReplacement
    # amplifiers, plus a face marker for the dropped modification). The auto-register
    # sweep loop used to build its serve spec from the now-gone row, so hand-register
    # it (the serve wants double/triple doublers, not Dark Sphere's prevention).
    ("damage_doubling", "you"): _spec(
        *SWEEP_LABELS["damage_doubling"],
        # Serve idents: the lane's damage-replacement read (doublers and triplers).
        None,
        serve_idents=frozenset({"damage_doubling|you|"}),
    ),
    # ADR-0027: commander_matters / hand_disruption / opponent_exile_matters had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # predicate/trigger bind + a kept word mirror per key). The auto-register sweep loop
    # used to build their serve specs from the now-gone rows, so hand-register them.
    ("commander_matters", "you"): _spec(
        *SWEEP_LABELS["commander_matters"],
        # Serve idents (2026-10-18): the regex missed command-zone tools (Command
        # Beacon, Hellkite Courser) and served 'If ~ is your commander' colour rules.
        None,
        serve_idents=frozenset({"commander_matters|you|"}),
    ),
    ("hand_disruption", "opponents"): _spec(
        *SWEEP_LABELS["hand_disruption"],
        # Serve idents (2026-10-18): the regex missed reveal-and-choose and look-at-hand
        # riders (Lay Bare).
        None,
        serve_idents=frozenset({"hand_disruption|opponents|"}),
    ),
    # _matters sweep (ADR-0034): the opponent_exile lane SPLIT by role. ADR-0034 lets
    # the avenue still serve makers + payoffs together; only MEMBERSHIP splits.
    ("opponent_exile_makers", "opponents"): _spec(
        *SWEEP_LABELS["opponent_exile_makers"],
        # Serve idents: the lane's own read of exiling an opponent's graveyard or
        # replacing a card headed there; nothing classified is left over.
        None,
        serve_idents=frozenset({"opponent_exile_makers|opponents|"}),
    ),
    ("opponent_exile_matters", "opponents"): _spec(
        *SWEEP_LABELS["opponent_exile_matters"],
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"opponent_exile_matters|opponents|"}),
    ),
    ("villainous_choice", "you"): _spec(
        "Villainous choice",
        "villainous-choice cards (the punisher pool a villainous-choice commander — "
        "The Valeyard, Davros, Missy — is built to present and double)",
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"villainous_choice|you|"}),
    ),
    ("curse_matters", "you"): _spec(
        "Curses",
        "Curse cards to recur, attach, and pile onto opponents (Lynde, Cheerful "
        "Tormentor) — served by the Curse subtype, not oracle prose",
        None,
        serve_types=("curse",),
        search={"card_type": "Curse"},
    ),
    # _matters sweep (ADR-0034): dice split. dice_makers = the ENABLER/doer side (cards
    # that roll dice — "roll a d20", "roll a six-sided die"); dice_matters below = the
    # PAYOFF side (cards rewarded by / triggering off a roll). The avenue serves both
    # together (enablers to roll + payoffs that reward rolling).
    ("dice_makers", "you"): _spec(
        "Dice rolling",
        "dice-rolling enablers plus roll-result payoffs",
        # Serve idents (2026-10-18): the regex missed 'roll three six-sided dice'
        # rollers (Circuits Act).
        None,
        serve_idents=frozenset({"dice_makers|you|", "dice_matters|you|"}),
    ),
    ("dice_matters", "you"): _spec(
        "Dice payoffs",
        "cards rewarded by rolling dice, plus the rollers to feed them",
        # Serve idents (2026-10-18): the regex missed 'roll three six-sided dice'
        # rollers (Circuits Act).
        None,
        serve_idents=frozenset({"dice_makers|you|", "dice_matters|you|"}),
    ),
    # A crime (CR 700.13) targets opponents / their permanents / spells they control —
    # i.e. targeted removal + explicit-opponent-target.
    ("crimes_matter", "you"): _spec(
        "Crimes",
        "targeted removal and abilities that count as committing a crime",
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"crimes_matter|you|"}),
    ),
    # Serve idents: the connive doers and the connive payoffs ("whenever a
    # creature you control connives" — connive_matters). The regex's remainder:
    # Mask of the Schemer's "connives X", an unimplemented ``where_x_binding`` in
    # phase.
    ("connive_makers", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        None,
        serve_idents=_CONNIVE_SERVE_IDENTS,
    ),
    ("connive_matters", "you"): _spec(
        "Connive payoffs",
        "creatures that connive to trigger your connive payoffs",
        None,
        serve_idents=_CONNIVE_SERVE_IDENTS,
    ),
    ("spell_copy_makers", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        # The lane reads "copy it" engines, replicate and casualty (Chandra, Hope's
        # Beacon). The lane does not read storm (copies its own spell, CR 702.40a), so
        # the keyword arm keeps the storm cards; card names (Storm's Wrath) drop out.
        None,
        serve_idents=frozenset({"spell_copy_makers|you|"}),
        serve_keywords=("storm",),
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp", "you"): _spec(
        "Ramp / big mana",
        "mana rocks, dorks, and land ramp to accelerate into your payoffs",
        # The ramp role's keys (ADR-0051), mana amplifiers, extra land drops, Treasure
        # makers and big mana. Gains rituals and land puts (Gilded Lotus, Burgeoning);
        # lands' own mana abilities, land-to-hand searches and firebending (never ramp)
        # drop out.
        None,
        serve_idents=frozenset(
            {
                "ramp|you|",
                "mana_amplifier|you|",
                "extra_land_drop|you|",
                "treasure_makers|you|",
                "big_mana|you|",
            }
        ),
        # Deliver on "accelerate into your payoffs": the big bombs (Ghalta) and creature
        # cost reducers (Goreclaw). Only ~3% of commanders open this big-mana lane, so
        # crediting power-6+ fatties is on-theme, not noise.
        serve_power_min=6,
        extras=(_CREATURE_COST_EXTRA,),
    ),
    # The `deals .* damage to target creature` branch missed every burn spell pointed at
    # ANY target (Lightning Bolt, Shock — "deals N damage to any target"). The serve is
    # the lane's ident.
    ("removal", "you"): _spec(
        "Removal / interaction",
        "destroy and burn removal — note indestructible/regeneration blank it",
        # The lane reads "destroy target nonblack creature" (Hand of Death), divided
        # damage and fight-style removal; one-shot land destruction (Stone Rain) is not
        # removal.
        None,
        serve_idents=frozenset({"removal|you|"}),
    ),
    # task #87: pacify_makers — an Aura that neutralizes (not removes) what
    # it enchants (Pacifism, Arrest, Faith's Fetters, Prison Term). A
    # pacify-aura deck wants more of the same PLUS the removal/interaction
    # a pacify-only build still needs (a Pacifism-only pile can't answer an
    # already-attacking evasive threat or a nonpermanent spell).
    ("pacify_makers", "you"): _spec(
        "Pacify auras",
        "Auras that shut down attacking/blocking without removing the threat",
        # The lane vetoes the Vow cycle (a compensated Aura) and reads can't-block locks
        # (Demotion).
        None,
        serve_idents=frozenset({"pacify_makers|you|"}),
        serve_types=("Enchantment",),
        search={"preset_names": ("pacify-aura",)},
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
        # Serve idents (2026-10-18): the regex missed Cursed Role makers (Cursed
        # Courtier) and served a pump aura (Awakened Awareness).
        None,
        serve_idents=frozenset({"single_target_neutralize|you|"}),
    ),
    # Exile removal: a card that exiles a creature then returns it is a flicker
    # engine, not removal (Ephemerate, Cloudshift — the lane's call); the serve is
    # the lane's ident, which leaves those out.
    ("exile_removal", "you"): _spec(
        "Exile removal",
        "exile-based removal that bypasses indestructible and stops recursion",
        # The lane reads Oblivion Ring, Solitude and airbend; graveyard-card exile (Vile
        # Rebirth) and your own permanents stay out, with no blink veto needed.
        None,
        serve_idents=frozenset({"exile_removal|you|"}),
    ),
    # ADR-0027 tranche2-B: exile_until_leaves's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — _is_exile_until_leaves). It used to be
    # auto-registered from that row (the SWEEP→SPECS fallback below), so hand-register
    # it now, keeping the old regex as the serve pattern.
    ("exile_until_leaves", "you"): _spec(
        *SWEEP_LABELS["exile_until_leaves"],
        # Serve idents (2026-10-18): the regex missed the two-trigger O-Ring template
        # (Oblivion Ring).
        None,
        serve_idents=frozenset({"exile_until_leaves|you|"}),
    ),
    ("counter_control", "you"): _spec(
        "Counterspells / control",
        "counterspells and stack interaction",
        # Serve idents (2026-10-18): the regex missed 'counter that spell' triggers
        # (Boromir, Glyph Keeper).
        None,
        serve_idents=frozenset({"counter_control|you|"}),
    ),
    # The bare `… (gain|have)` tail matched any "creatures you control gain/have X". Tie
    # it to the actual keyword-grant list or a static (+N/+N, not "until end of turn")
    # anthem, so a one-shot pump or a non-keyword clause doesn't read as a team grant.
    ("team_buff", "you"): _spec(
        "Team keyword grants",
        "keyword grants and anthems for your board",
        r"creatures? you control (?:gain|gains|have|has) (?:flying|trample|menace"
        r"|hexproof|indestructible|protection|deathtouch|lifelink|double strike"
        r"|first strike|vigilance|haste|ward|reach)"
        r"|creatures you control get \+\d+/\+\d+",
        # The lane's team grants, whatever the keyword (its subject): the grants
        # the regex's list or wording misses (Rafiq's double strike to a lone
        # attacker, Akroma's Will's modes).
        serve_idents=frozenset({"team_buff|you|*"}),
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
        # The lane reads "library and/or graveyard" tutors (Chandra's Outburst) and
        # skips landcycling. It fires on fetch lands too, so the land-to-battlefield
        # veto stays.
        None,
        serve_idents=frozenset({"tutor|you|"}),
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
        # Serve idents: every untap shape the lane reads.
        None,
        serve_idents=frozenset({"untap_engine|you|*"}),
    ),
    # own_target_spell (iteration-4): served by the cards that pay off a spell
    # targeting your own permanents — heroic and valiant bodies, and the engines
    # that rebate or copy one (Feather-class, Zada).
    ("own_target_spell", "you"): _spec(
        "Own-target spell",
        "heroic payoffs and the recursion and copy engines that reward spells "
        "targeting your own permanents",
        # Serve idents: the targeting-matters cards (heroic, valiant, cast-a-spell-
        # that-targets payoffs); Repartee and spell-copy engines are not in the lane.
        None,
        serve_idents=frozenset({"targeting_matters|any|you"}),
    ),
    # permanent_recast (iteration-3): a repeatable re-delivery engine — served
    # by the one-shot ETB/self-sac value permanents it re-delivers.
    ("permanent_recast", "you"): _spec(
        "Permanent recast engine",
        "one-shot ETB value permanents this engine re-delivers every turn",
        # Serve idents: the one-shot self-ETB payloads this engine re-delivers.
        None,
        serve_idents=frozenset({"self_etb_payload|you|"}),
    ),
    # self_etb_payload (iteration-3): a self-ETB value trigger — served by the
    # engines that re-deliver it (blink/flicker, recursion, bounce-to-replay);
    # CR 603.6a: enters triggers fire on every entry.
    ("self_etb_payload", "you"): _spec(
        "ETB value to re-deliver",
        "blink, recursion, and bounce engines that re-fire this card's "
        "enters-the-battlefield value",
        r"exile [^.]*return[^.]*battlefield|return [^.]*from your graveyard "
        r"to the battlefield",
    ),
    # Tap/untap commander (Tui and La) wants the untap effects that retrigger it.
    # ADR-0027: tap_untap_matters had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the `taps` trigger + a "becomes tapped/untapped" kept mirror).
    # The serve rides the lane once it reads granted "becomes tapped" triggers
    # (Dionus, Elvish Archdruid).
    ("tap_untap_matters", "you"): _sweep_spec_with_extras(
        "tap_untap_matters",
        (_UNTAP_EXTRA,),
        serve_idents=frozenset({"tap_untap_matters|you|"}),
    ),
    # Activated-ability engine: the support package for a {T}: commander — activated-
    # ability cost reducers (Training Grounds), untappers + haste-for-abilities
    # (Thousand-Year Elixir, Ioreth), and ability copiers (Rings of Brighthearth,
    # Illusionist's Bracers). The serve is the lanes' idents plus an extra for the
    # haste, cost-reducer and one-creature untap shapes no lane names.
    ("activated_ability", "you"): _spec(
        "Activated-ability engine",
        "cost reducers, untappers, haste-for-abilities, and copiers that power your "
        "commander's activated abilities",
        # The {T}/generic-cost engines, untappers and ability copiers; the haste,
        # cost-reducer and one-creature untap shapes are the extra. Cycling, equip and
        # token reminder text drops out.
        None,
        serve_idents=frozenset(
            {"activated_ability|you|", "untap_engine|you|", "ability_copy|you|"}
        ),
        extras=(_ABILITY_HASTE_COST_EXTRA,),
    ),
    # YOU must be the one gaining control: the lane (lanes.counters_voltron.
    # _gain_control) vetoes the donate shapes where an OPPONENT gains control of your
    # stuff (Sky Swallower) and the control resets.
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        # Serve rides the lane, which vetoes the give-aways and
        # control resets (Brand) and now reads granted theft (Chamber of
        # Manipulation) and Bribery / Acquire: seize a card out of an OPPONENT's
        # library onto the battlefield UNDER YOUR CONTROL (you control a
        # permanent you don't own, CR 110.2). The borrow-and-cast engines (Gonti,
        # Wrexial, Sen Triplets) exile or reach a card and let you CAST it —
        # playing what you don't own, never a battlefield control change — so
        # they serve theft_makers / wants_theft, not this lane.
        None,
        serve_idents=frozenset({"gain_control|you|"}),
    ),
    # Align the serve with the extraction regex so the wheel-punishers and "each
    # opponent/player discards" forms (Bottomless Pit, Hymn) are recovered.
    ("opponent_discard", "opponents"): _spec(
        "Hand attack",
        "forced discard and hand disruption aimed at opponents",
        # Serve idents (2026-10-18): the regex missed combat / ETB discard triggers
        # (Alley Grifters, Blightning) and served self-loot and ward costs (Compulsive
        # Research, Reality Smasher).
        None,
        serve_idents=frozenset(
            {"opponent_discard|each|", "opponent_discard|opponents|"}
        ),
        extras=(_DISCARD_PUNISH_EXTRA, _HELLBENT_PUNISH_EXTRA),
    ),
    # Bare `can't be blocked` matched the menace/flying REMINDER "can't be blocked
    # except by …" on vanilla evasive creatures (~673). Exclude the "except" form (a
    # conditional restriction, CR 509.1b, not true unblockable) and add landwalk.
    ("evasion_self", "you"): _spec(
        "Evasion / unblockable",
        "unblockable and evasion to keep connecting — strong for voltron",
        # Serve idents: unblockable and every hard-evasion shape the lane reads.
        None,
        serve_idents=frozenset(
            f"evasion_self|you|{k}"
            for k in (
                "unblockable",
                "landwalk",
                "menace",
                "fear",
                "intimidate",
                "skulk",
                "horsemanship",
                "shadow",
            )
        ),
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
        # Serve idents: unblockable and landwalk carriers plus team evasion grants.
        None,
        serve_idents=frozenset(
            {
                "evasion_self|you|unblockable",
                "evasion_self|you|landwalk",
                "team_evasion_grant|you|*",
            }
        ),
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
        # Serve idents: the clone, permanent-copy and token-copy lanes. The leftover
        # is spell-copy reminder text; Estrid's Invocation is a phase gap.
        None,
        serve_idents=_CLONE_SERVE_IDENTS,
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
    # token-copy gear (Helm of the Host, Rite of Replication). Same clone serve
    # as clone_makers, minus the power-6 bomb floor (here we want the copiers, not more
    # bodies to copy).
    ("wants_cloning", "you"): _spec(
        "Wants cloning",
        "clone enablers — your commander/creatures are worth copying",
        # Serve idents: the clone, permanent-copy and token-copy lanes. The leftover
        # is spell-copy reminder text; Estrid's Invocation is a phase gap.
        None,
        serve_idents=_CLONE_SERVE_IDENTS,
        extras=(_COPY_EXTRA,),
    ),
    # The SUBJECT-LESS cheat (signal_keys.CHEAT_INTO_PLAY): a put that names no
    # single card type — a named tutor (Angel's Herald), "a permanent card"
    # (Jhoira, Weatherlight Corsair). A typed cheat builds its own per-type spec
    # (``core._cheat_subject_spec``, same label) whose payoff arm is the type it
    # cheats; this one has no type to pay off, so it serves the cheats alone.
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put cards onto the battlefield from hand or library without "
        "casting them",
        # The enabler arm is the lane's own structural read (``_cheat_into_play`` in
        # ``lanes.mana_and_wipes``: a Hand/Library→Battlefield put, the reveal-until
        # engine, the dig-and-put — with its land / graveyard carve-outs). The
        # oracle regex it replaced (2026-10-17) missed the "creature OR planeswalker
        # card" reveal-until idiom (Identity Echo, Jace, Multiverse Architect's -3)
        # and credited old-template reanimation (Reanimate's "Put target creature
        # card from a graveyard onto the battlefield"), which the lane keeps out.
        # Every subject: an untyped cheat sits beside cheats of any type.
        None,
        serve_idents=frozenset({"cheat_into_play|you|*"}),
    ),
    # Polymorph fodder (wants_fodder): a cheat that turns a body you control into a
    # fresh card off the library (Jace, Multiverse Architect's -3, Mass Polymorph,
    # Proteus Staff — ``lanes.mana_and_wipes._polymorph_fodder``) wants cheap,
    # expendable bodies to transform: a token is the best one to lose (CR 111.7 —
    # a token in a zone other than the battlefield ceases to exist). The serve is
    # the token lane's own idents, capped at mana value 3 so it stays the cheap end.
    ("wants_fodder", "you"): SignalSpec(
        label="Polymorph fodder",
        avenue="cheap creature-token makers and expendable bodies to transform",
        search={"cmc_max": 3},
        serve=Serve(
            all_of=(
                Serve(signal_idents=frozenset({"token_maker|you|*"})),
                Serve(cmc_max=3),
            )
        ),
    ),
    # Greedy `return target .*owner's hand` matched "return target spell" (Reprieve →
    # counterspell space) and spanned clauses. Constrain the object + the dot.
    ("bounce_tempo", "you"): _spec(
        "Bounce / tempo",
        "bounce effects for tempo and ETB re-use",
        # Serve idents: the lane's bounce effects (mass, X-target, delayed). Graveyard
        # returns drop out; own-permanent rescues serve only through the self-bounce
        # extra (ETB / upkeep recast engines).
        None,
        serve_idents=frozenset({"bounce_tempo|you|"}),
        extras=(_SELF_BOUNCE_EXTRA,),
    ),
    # _matters sweep (ADR-0034): the cascade build-around is driven by an
    # intrinsic-cascader commander (The First Sliver, Apex Devastator) — a
    # cascade_makers card — so the "Cascade" avenue attaches to cascade_makers.
    # The serve regex \bcascade\b serves makers + granters + payoffs alike.
    ("cascade_makers", "you"): _spec(
        "Cascade",
        "high-value spells to hit off cascade plus more cascade enablers",
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"cascade_makers|you|", "cascade_matters|you|"}),
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
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"cascade_makers|you|", "cascade_matters|you|"}),
        serve_power_min=6,
    ),
    ("regenerate_makers", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        # Serve idents (2026-10-18): the regex matched exactly the lane's own cards; the
        # lane is the source of truth.
        None,
        serve_idents=frozenset({"regenerate_makers|you|"}),
        # A regenerating/resilient beater is a voltron plan — surface the gear, buff
        # Auras (Rancor, Bear Umbra), and protection (Alpha Authority) you suit it with.
        extras=(_COMBAT_SUPPORT_EXTRA, _VOLTRON_PROTECT_EXTRA),
    ),
    # Drop the bare `opponents? cast` — only the TRIGGER/tax forms are punishers.
    ("opponent_cast_matters", "opponents"): _spec(
        "Punish opponents' spells",
        "taxes and punishers that trigger when opponents cast",
        # Serve idents: the lane's own read of opponent-cast triggers and taxes.
        None,
        serve_idents=frozenset({"opponent_cast_matters|opponents|"}),
    ),
    # Drop the bare `opponents? draws?` — it matched group-hug GIFT effects (Master of
    # the Feast) that HAND opponents cards rather than punishing the draw.
    ("opponent_draw_matters", "opponents"): _spec(
        "Punish opponents' draw",
        "wheels and draw-denial punishers that trigger on opponents drawing",
        # Serve idents: the punishers plus the enablers that make opponents draw
        # (group draw, wheels, forced draw, Inspiration); your own cantrip (Opt) is out.
        None,
        serve_idents=frozenset(
            {
                "opponent_draw_matters|opponents|",
                "card_draw_engine|opponents|",
                "card_draw_engine|each|",
                "group_hug_draw|each|",
                "target_player_draws|any|",
            }
        ),
    ),
    # Drop the bare `search their library` — your OWN tutor reads "search their
    # library" too (Path to Exile). Require an opponent/player subject.
    ("opponent_search_matters", "opponents"): _spec(
        "Punish opponents' tutors / selection",
        "stax and punishers for opponents who search, scry, or surveil",
        # Serve idents: punishers that watch opponents search or shuffle (Stranglehold,
        # Psychic Surgery); symmetric each-player tutors drop out.
        None,
        serve_idents=frozenset({"opponent_search_matters|opponents|"}),
    ),
    ("damage_to_opp_matters", "opponents"): _spec(
        "Damage to opponents",
        "evasion, pingers, and extra combats to keep connecting and fire these "
        "damage-to-opponent triggers (any damage, not just combat)",
        # Serve idents: the damage-to-opponent payoffs plus unblockable and landwalk
        # carriers; bare menace stays out.
        None,
        serve_idents=frozenset(
            {
                "damage_to_opp_matters|opponents|",
                "evasion_self|you|unblockable",
                "evasion_self|you|landwalk",
            }
        ),
    ),
    # `enters the battlefield` is a DEAD branch — Scryfall templated the phrase down to
    # bare "enters" years ago (CR glossary), so it matched ~1 card and the serve missed
    # every Panharmonicon/Yarok ETB-engine. Key on the ETB-trigger / flicker clauses.
    ("permanent_etb", "you"): _spec(
        "Permanents entering",
        "cheap permanents, token makers, and flicker to repeatedly trigger your "
        "permanent enters-the-battlefield value engine",
        r"create [^.]*token|put [^.]*onto the battlefield"
        r"|when (?:this|[A-Z][\w']+)[^.]*enters"
        r"|(?:a|an|another|one or more)[^.]*permanents? you control enters"
        r"|(?:artifact or creature|creature or artifact)[^.]*enter",
        extras=(_FLICKER_EXTRA, _DIES_RECURSION_EXTRA, _SELF_BOUNCE_EXTRA),
    ),
    # The avenue is Equipment-for-a-dasher: the serve gates on the dash ident, the
    # Equipment TYPE (CR 301.5 — the persistent buff) and the dash / reconfigure KEYWORD
    # (CR 702.109/702.151), plus an extra for cards that move/cheat Equipment without
    # the subtype.
    ("has_dash", "you"): _spec(
        "Dash / hit-and-run Equipment",
        "Equipment — it stays on the battlefield when Dash returns the creature to "
        "your hand at end of turn (Auras and counters don't), so it's the resilient "
        "buff for a recurring haste attacker; plus haste enablers and cheap recursion",
        # The dash cards themselves; Equipment serves through the type arm and the
        # "attach … Equipment" movers are an extra.
        None,
        serve_idents=frozenset({"has_dash|you|"}),
        serve_types=("equipment",),
        serve_keywords=("dash", "reconfigure"),
        extras=(_EQUIPMENT_MOVER_EXTRA,),
        search={"preset_names": ("equip",)},
    ),
}
