"""Signal specs data slice 4/4: SPECS dict entries (lines 5824-6510 of the
original ``signal_specs.py``), verbatim, in original order.
"""

from __future__ import annotations

import re

from mtg_utils._analysis._sweep_detectors import (
    SWEEP_LABELS,
)
from mtg_utils._card_ir.crosswalk import LAND_DENIAL_KINDS

from ._shared import (
    _CHEAP_EVASION_EXTRA,
    _CRIPPLING_DRAWBACK_ORACLE,
    _DIES_RECURSION_EXTRA,
    _ENLIST_FODDER_EXTRA,
    _FLICKER_EXTRA,
    _IC,
    _LANDS_FROM_GRAVE_EXTRA,
    _PILLOWFORT_IDENTS,
    Serve,
    SignalSpec,
    SubAvenue,
    _spec,
)

# The foretell serve (both lanes): bearers, granters and foretold-card payoffs.
_FORETELL_SERVE_IDENTS = frozenset({"foretell_makers|you|", "foretell_matters|you|"})

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
        # 2026-10-18: the serve regex read trample's reminder text (Charging War Boar).
        None,
        serve_idents=frozenset({"excess_damage|you|"}),
        serve_keywords=("trample",),
    ),
    # anthem_static: a STATIC anthem, not a one-shot pump — VETO "until end of turn"
    # (those are pump_makers). Oracle-with-temporal-guard (no structured 'is-static').
    ("anthem_static", "you"): _spec(
        "Static anthem",
        "go-wide creatures to ride the anthem",
        # Serves the lane's static anthems (all-creature, subtype and chosen-type);
        # the remainder is one-turn pumps and cost reducers the old pattern read.
        None,
        serve_idents=frozenset(
            {
                "anthem_static|you|*",
            }
        ),
        serve_not=r"get \+\d/\+\d[^.]*until end of turn",
    ),
    # Serves the lane's repeatable activated draws (tap-cost and other costs alike);
    # one-shot self-sacrifice draws are out by the lane. The one remainder is a
    # planeswalker whose draw the lane does not see.
    ("activated_draw", "you"): _spec(
        *SWEEP_LABELS["activated_draw"],
        None,
        serve_idents=frozenset({"activated_draw|you|"}),
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
        # Serves mass removal of creatures and mass creature recursion; the remainder is
        # mass exile and mass return of non-creature cards.
        None,
        serve_idents=frozenset(
            {
                "mass_removal|you|creature",
                "creature_recursion|you|mass",
            }
        ),
    ),
    # Per-target payoff (Hinata): the discount scales with target count, so serve spells
    # whose target count is VARIABLE — "any number of targets" (Aurelia's Fury) and
    # "X target" spells (Distorting Wake). A single fixed-target removal (Doom Blade) is
    # only a {1} discount, not the payoff, so it isn't credited.
    ("per_target_payoff", "you"): _spec(
        "Multi-target spells",
        "variable / X-target spells whose per-target discount compounds (any number of "
        "targets, X target permanents)",
        # Serves spells with a variable target count; fixed counts and permanents'
        # abilities are out by design.
        None,
        serve_idents=frozenset(
            {
                "per_target_payoff|you|variable",
            }
        ),
    ),
    # Ability-strip targets (Abigale): big creatures with a crippling drawback she
    # strips then buffs. ANDs the drawback clause with power >= 5 (Serve.all_of), so a
    # big vanilla beater (no drawback) and a small drawback creature are both excluded.
    ("ability_strip_payoff", "you"): SignalSpec(
        label="Ability-strip targets",
        avenue="big creatures whose crippling drawback gets stripped, then buffed into "
        "a beater",
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
        # The lane reads splice onto Arcane, the Spirit-or-Arcane cast triggers
        # (Petalmane Baku, Bounteous Kirin) and Arcane recursion (The Unspeakable).
        None,
        serve_idents=frozenset({"arcane_matters|you|"}),
        serve_types=("arcane",),
        search={"card_type": "Arcane"},
    ),
    # Enlist (Aradesh): other enlist creatures (the keyword bearers) plus the big
    # stay-back fodder to tap for their power.
    ("has_enlist", "you"): _spec(
        "Enlist",
        "enlist creatures plus big stay-back fodder to tap for their power",
        # The lane reproduces the serve regex; the keyword dim stays.
        None,
        serve_keywords=("enlist",),
        serve_idents=frozenset({"has_enlist|you|"}),
        extras=(_ENLIST_FODDER_EXTRA,),
    ),
    # Power-scaling tap engine (Mona Lisa, Marwyn, Selvala, Alena): UNTAP effects re-tap
    # the engine for another payoff; ranking surfaces the repeatable untappers first.
    ("power_tap_engine", "you"): _spec(
        "Untap effects",
        "untap effects that re-tap the power-scaling ability for another activation",
        # Serves the untap-engine lane; a card that only untaps itself is out by the
        # lane's decision (it re-taps nothing else).
        None,
        serve_idents=frozenset({"untap_engine|you|"}),
    ),
    # Recastable ETB aggressors (Oroku Saki + the TMNT Sneak legends): cheap creatures
    # whose ENTER trigger bleeds opponents (each opponent discards / loses life), so
    # bouncing and recasting them repeats the bleed. The aggressive-ETB subset is the
    # precise recast payoff (color identity filters it per commander) — NOT every ETB
    # creature, which would be goodstuff.
    ("recast_etb", "you"): _spec(
        "Recastable ETB aggressors",
        "cheap creatures whose enter-trigger bleeds opponents, to bounce and recast",
        # 2026-10-18: the serve regex missed the Sneak bodies and conditional bleeds
        # (Dream Seizer, Diregraf Scavenger) and read a Saga chapter (Thunder of Unity).
        None,
        serve_idents=frozenset({"recast_etb|you|"}),
    ),
    # Exert (Johan, Heliod God of the Sun): when your team has vigilance / never taps to
    # attack, an exert creature's only downside (won't untap) vanishes, so serve the
    # exert creatures (the Scryfall keyword is the precise gate).
    ("exert_matters", "you"): _spec(
        "Exert",
        "exert creatures — their 'won't untap' cost is free when your team doesn't tap",
        # No ident arm: the lane's key fires on the vigilance enablers (Intangible
        # Virtue, Serra's Blessing), the commander side this avenue opens from, not the
        # exert bodies it serves; the keyword arm covers those.
        None,
        serve_keywords=("exert",),
    ),
    # Target redirect (Rayne draws when an opponent targets your stuff): shunt the
    # opponent's spell onto a cheap permanent so you still draw but the real target is
    # safe (Spellskite, Misdirection, Bolt Bend).
    ("target_redirect", "you"): _spec(
        "Target redirection",
        "redirect an opponent's spell onto a cheap permanent (still triggers, stays "
        "safe)",
        # The redirect instruments the spell_redirect lane reads (a ChangeTargets
        # of a stack object, CR 115.7; a spell thief), the residues phase parks
        # bridged (``spell_redirect_parse_failure``). Fork's retarget of its copy
        # is spell_copy_makers' (CR 707.10c).
        None,
        serve_idents=frozenset({"spell_redirect|you|"}),
    ),
    # task B-4: the DOER side (split from the payoff key above per the
    # counter_control precedent) — deck-side key when the deck already runs
    # redirect instruments.
    ("spell_redirect", "you"): _spec(
        "Spell redirection",
        "redirect effects that turn opponents' targeted spells into blowouts "
        "or protection (Wild Ricochet, Bolt Bend)",
        # The lane's own ident, as target_redirect above.
        None,
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
        None,
        serve_power_min=7,
        search={"card_type": "Creature"},
    ),
    # Land control / exchange (Sharkey): a land-control commander wants land-EXCHANGE
    # effects to swap a weak land for an opponent's best while it taxes the rest.
    ("land_exchange", "you"): _spec(
        "Land exchange",
        "swap control of lands to steal opponents' best while you tax the rest",
        # The lane reads land steals and exchanges the regex missed ("two target lands"
        # — Shifting Borders; Annex, Herald of Leshrac).
        None,
        serve_idents=frozenset({"land_exchange|you|"}),
    ),
    # Self-life-payment insurance (Selenia, Beledros, Vilis): a commander that pays its
    # own life repeatedly wants life-loss insurance so the payments don't kill it
    # (Phyrexian Unlife, Angel's Grace, Platinum Angel).
    ("life_payment_insurance", "you"): _spec(
        "Life-loss insurance",
        "cards that stop you losing the game from heavy self-life-payment",
        # Serves the can't-lose-the-game lane; the remainder is the life-total-can't-
        # change cards and Abyssal Persecutor, which the lane does not read.
        None,
        serve_idents=frozenset(
            {
                "life_payment_insurance|you|cant_lose",
            }
        ),
    ),
    # Target-your-own payoff (Monk Gyatso): free ways to target your own creatures so a
    # "when targeted" payoff fires on demand (en-Kor cycle, {0}-equip like Shuko).
    ("target_own_payoff", "you"): _spec(
        "Target-your-own enablers",
        "free/cheap ways to target your own creatures (en-Kor, {0}-equip)",
        # Serves the free-to-target lane, which also reaches {0} untap/equip grants.
        None,
        serve_idents=frozenset(
            {
                "target_own_payoff|you|free_target",
            }
        ),
    ),
    # Multicolor matters (Niv-Mizzet Reborn + the gold-cards commanders): the multicolor
    # PAYOFFS — "whenever you cast a multicolored spell", converge, "multicolored
    # creatures you control" — not every gold card (which would be the whole deck).
    ("multicolor_matters", "you"): _spec(
        "Multicolor payoffs",
        "cards that reward casting multicolored spells, plus converge",
        # The lane reads the multicolored payoffs the regex missed (Niv-Mizzet Reborn,
        # Zenith Chronicler); converge, an ability word (CR 207.2c) the lane does not
        # read, rides the keyword field.
        None,
        serve_idents=frozenset({"multicolor_matters|you|"}),
        serve_keywords=("converge",),
    ),
    # A repeatable land-destruction commander (Numot) wants the LD support package:
    # more land destruction (main), own-land recursion to survive symmetric LD (reuse
    # the lands-from-graveyard extra), and land-loss PUNISHERS that turn each destroyed
    # land into damage/value (Dingus Egg, Price of Glory).
    ("land_destruction", "you"): _spec(
        "Land destruction",
        "blow up lands repeatedly — the Armageddon/Numot stax-LD plan",
        # Serves every land-destruction kind (destroy, sacrifice, exile, bounce); the
        # remainder is two symmetric sacrifice-on-tap and damage cards.
        None,
        serve_idents=frozenset(
            {
                "land_destruction|you|*",
            }
        ),
        extras=(
            SubAvenue(
                "Punish land loss",
                "turn every destroyed land into damage or value (Dingus Egg, "
                "Price of Glory)",
                serve=Serve(
                    oracle=re.compile(
                        r"whenever a land(?: card)? is put into a graveyard"
                        r"|whenever a player taps a land[^.]*destroy",
                        _IC,
                    )
                ),
            ),
            _LANDS_FROM_GRAVE_EXTRA,
        ),
    ),
    # Mass land denial (ADR-0030: the Commander Brackets' definition — destroy,
    # exile or bounce lands, keep them tapped, or change their mana, four or more
    # per player). A deck already running Armageddon effects, untap locks or Blood
    # Moon wants the rest of the lock. Search and serve both ride the key (the
    # ``mass-land-denial`` preset; every shape the lane names as its subject).
    ("mass_land_denial", "each"): _spec(
        "Mass land denial",
        "Armageddon effects, untap locks and Blood Moon — four or more lands per "
        "player",
        None,
        serve_idents=frozenset(
            f"mass_land_denial|each|{kind}" for kind in LAND_DENIAL_KINDS
        ),
        search={"preset_names": ("mass-land-denial",)},
    ),
    # Board protection (ADR-0051: two of ``roles.protects``'s keys). A commander
    # that already shields your board (Avacyn, Shalai, Sterling Grove) wants more
    # of it; one that locks out attackers (Ghostly Prison) wants the rest of the
    # pillowfort. Each spec searches and serves its own key's preset.
    ("board_protection", "you"): _spec(
        "Board protection",
        "protection for the rest of your board — Heroic Intervention, Darksteel "
        "Forge, Mother of Runes, Teferi's Protection",
        None,
        serve_idents=frozenset({"board_protection|you|"}),
        search={"preset_names": ("board-protection",)},
    ),
    ("pillowfort", "you"): _spec(
        "Pillowfort",
        "taxes and limits that make attacking you costly — Ghostly Prison, "
        "Propaganda, Sphere of Safety, Crawlspace",
        None,
        serve_idents=_PILLOWFORT_IDENTS,
        search={"preset_names": ("pillowfort",)},
    ),
    # A cheat-from-top commander (Vaevictis, Hans Eriksson) reveals its top card and
    # puts a permanent into play, so it wants to STACK its top with a bomb: graveyard-
    # to-top recursion and deliberate put-on-top effects choose what gets cheated in.
    ("cheat_from_top", "you"): _spec(
        "Stack your top",
        "put a bomb on top of your library to be cheated in — graveyard-to-top "
        "recursion and put-on-top effects",
        # Serves put-on-top from graveyard, hand, library and exile; the remainder is
        # surveil, whose reminder text the old pattern read.
        None,
        serve_idents=frozenset(
            {
                "topdeck_stack|you|graveyard",
                "topdeck_stack|you|hand",
                "topdeck_stack|you|library",
                "topdeck_stack|you|exile",
            }
        ),
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
        # Serves the lane's death payoffs; the remainder is draw-on-your-creature-dies
        # and combat-damage death triggers the lane does not count.
        None,
        serve_idents=frozenset(
            {
                "kill_engine|you|payoff",
            }
        ),
    ),
    # Phasing-lands (Taniwha): your lands phase back each turn, so symmetric land-denial
    # stax (Mana Breach / Overburden — every player bounces/sacs a land) hits opponents
    # permanently while you recover. Asymmetric land denial.
    ("land_denial", "you"): _spec(
        "Land denial",
        "symmetric land-bounce/sac stax that hits opponents while your lands phase",
        # Serves the sacrifice and bounce land-denial lanes; "that player returns a
        # land" (Mana Breach, Overburden) is the remainder no lane reads.
        None,
        serve_idents=frozenset(
            {
                "land_sacrifice_makers|each|",
                "mass_land_denial|each|sacrifice",
                "mass_land_denial|each|bounce",
                "land_denial|you|",
            }
        ),
    ),
    # Cast-from-hand-or-lose (Phage): negate the drawback — command-zone-to-hand so it's
    # cast normally, "can't lose the game" backstops, and "ETBs don't trigger" silences
    # the lose-trigger when the commander is cheated into play.
    ("lose_unless_hand", "you"): _spec(
        "Drawback negation",
        "command-zone-to-hand, can't-lose, and ETB-silencers for a cast-from-hand-or-"
        "lose commander",
        # Serves can't-lose backstops, command-zone-to-hand and ETB silencers; the
        # remainder is Abyssal Persecutor (a phase gap on the unscoped can't-lose).
        None,
        serve_idents=frozenset(
            {
                "life_payment_insurance|you|cant_lose",
                "lose_unless_hand|you|command_to_hand",
                "lose_unless_hand|you|etb_silencer",
            }
        ),
    ),
    # Land protection (Noyan Dar, Kamahl, the Tophs): a land-animation commander's
    # creature-lands die to creature removal / wraths / land destruction, so it wants
    # indestructible-lands, untargetable-lands, and land recursion to keep them.
    ("land_protection", "you"): _spec(
        "Land protection",
        "keep your animated lands alive: indestructible, untargetable, land recursion",
        # Serve idents: indestructible / hexproof / shroud grants to lands (Terra
        # Eternal, an emblem's — the shield subject) and land recursion (Life
        # from the Loam, Crucible of Worlds — permanent_recast's land doer). An
        # animator that protects only what it animates (Kamahl's Will, Lumbering
        # Falls) is the payoff, not its protection.
        None,
        serve_idents=frozenset(
            {"land_protection|you|shield", "permanent_recast|you|land"}
        ),
    ),
    # Newly-entered attacker payoff (Samut): wants HASTE + ETB-pump anthems so a
    # creature that entered this turn can attack at once for value. Ogre Battledriver /
    # Primal Forcemage pump entering creatures; mass-haste lets them swing.
    ("entered_attacker", "you"): _spec(
        "Haste + ETB pump",
        "haste and enter-trigger pump so freshly-entered creatures attack at once",
        # Serves enter-trigger pump and team haste grants; the remainder is self-pumps
        # on a creature entering, which are not freshly-entered attackers.
        None,
        serve_idents=frozenset(
            {
                "entered_attacker|you|etb_pump",
                "team_buff|you|haste",
            }
        ),
    ),
    # ADR-0034 _matters sweep — island lane split by role.
    # island_makers (the islandwalk DOER side — islandwalk bearers / granters /
    # token-makers): wants more islandwalk granters plus effects that turn opponents'
    # lands into Islands (so islandwalk connects), and island-count payoffs.
    ("island_makers", "you"): _spec(
        "Islandwalk makers",
        "islandwalk granters plus make opponents' lands Islands so it connects",
        # Serves islandwalk bearers and granters, lands-become-Islands effects and the
        # Island-attack-restriction bodies. Counts of your own Islands are out by design
        # (flood noise); Quicksilver Fountain is a phase parse gap.
        None,
        serve_idents=frozenset(
            {
                "island_makers|you|",
                "island_makers|you|lands_become_islands",
                "island_matters|you|",
            }
        ),
    ),
    # island_matters (the Zhou Yu cares-about-Islands PAYOFF side): effects that turn
    # opponents' lands into Islands so the attack restriction is met, plus island-count
    # payoffs. Quicksilver Fountain (flood counters → Islands) and Stormtide Leviathan
    # ("All lands are Islands") feed it; a mana dork does not.
    ("island_matters", "you"): _spec(
        "Island matters",
        "make opponents' lands Islands so the attack restriction is met",
        # Serves lands-become-Islands effects and the Island-matters lane; counts of
        # your own Islands are out by design, Quicksilver Fountain is a phase gap.
        None,
        serve_idents=frozenset(
            {"island_makers|you|lands_become_islands", "island_matters|you|"}
        ),
    ),
    # Tap down blockers (Tromokratis): effects that tap OPPONENTS' creatures (Sleep,
    # Blustersquall) so the defender can't field enough blockers, letting the
    # "unblockable unless all block" commander through.
    ("tap_down_blockers", "you"): _spec(
        "Tap down blockers",
        "effects that tap opponents' creatures so they can't all block",
        # Serves the tap-down lane (tap, detain, freeze) and its blocker-specific mass
        # taps; the remainder is untap-an-opponent cards the old pattern misread.
        None,
        serve_idents=frozenset(
            {
                "tap_down|opponents|",
                "tap_down_blockers|you|",
            }
        ),
    ),
    # ltb_matters: the O-Ring exile-until-leaves removal (Banishing Light) routes to
    # exile_until_leaves, not here. ADR-0027 β: ltb_matters migrated to the Card IR (a
    # structural `leaves`-trigger arm + a narrowed _LTB_MATTERS_MIRROR, SIDECAR v11).
    # This spec is hand-registered, independent of the deleted SWEEP detector; its
    # serve reads the lane (leaves-the-battlefield
    # triggers, CR 603.6c).
    ("ltb_matters", "you"): _spec(
        "Leaves-the-battlefield",
        "sacrifice and blink fodder to trigger LTB",
        # The lane's leaves trigger (CR 603.6c) drops the "when this leaves, sacrifice
        # that creature" tethers (Animate Dead) and gains bounce and "left the
        # battlefield this turn" payoffs (Azorius Aethermage); it already leaves out
        # O-Ring exile.
        None,
        serve_idents=frozenset({"ltb_matters|you|", "ltb_matters|any|"}),
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
        # 2026-10-18: the serve regex read ability-word names (Bloodboil Sorcerer's
        # "Crown of Madness").
        None,
        serve_idents=frozenset({"madness_matters|you|"}),
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
        # 2026-10-18: the serve regex missed speed-reducers (Spikeshell Harrier).
        None,
        serve_idents=frozenset({"speed_makers|you|"}),
        serve_keywords=("start your engines!",),
        extras=(_CHEAP_EVASION_EXTRA,),
    ),
    # ADR-0034 _matters sweep: the PAYOFF side. speed_matters keeps the Max-speed
    # abilities, which only function at speed 4 (they care-about having reached
    # max speed and advance nothing).
    ("speed_matters", "you"): _spec(
        "Max speed",
        "Max-speed payoffs that reward reaching speed 4",
        # 2026-10-18: the serve regex reached the engines only through Start your
        # engines!'s reminder text ("Max speed is 4"); the makers sibling serves them.
        None,
        serve_idents=frozenset({"speed_matters|you|", "speed_makers|you|"}),
        serve_keywords=("max speed",),
    ),
    ("discover_makers", "you"): _spec(
        "Discover",
        "discover sources to dig for free, plus low-mana-value nonland spells worth "
        "flipping into",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"discover_makers|you|"}),
        serve_keywords=("discover",),
    ),
    # ADR-0027 / _matters sweep (ADR-0034): the Foretell lane migrated to the Card IR
    # and then SPLIT into foretell_makers (the `foretell` keyword bearers + grant /
    # "to foretell" enabler markers that PERFORM the mechanic) and foretell_matters
    # (the Foretold-card payoffs — Niko Defies Destiny). Both serve the SAME foretell
    # pool (the avenue composes maker + payoff).
    # Serve on the lanes' idents (reads.keyword_resource_events reads the foretell
    # grants — Bohn, Dream Devourer). What the regex also served is phase gaps:
    # Ranar's foretell cost reducer, Karfell Harbinger's foretell-only mana and
    # Ethereal Valkyrie's "it becomes foretold".
    ("foretell_makers", "you"): _spec(
        "Foretell",
        "foretell cards to bank in exile plus enablers that let you foretell",
        None,
        serve_idents=_FORETELL_SERVE_IDENTS,
        serve_keywords=("foretell",),
    ),
    ("foretell_matters", "you"): _spec(
        "Foretell",
        "foretell cards to bank in exile plus the payoffs that reward foretold cards",
        None,
        serve_idents=_FORETELL_SERVE_IDENTS,
        serve_keywords=("foretell",),
    ),
    ("has_undying_persist", "you"): _spec(
        "Undying / Persist",
        "Undying and Persist bodies (free, repeatable death-return fodder) plus the "
        "anthems and grants that hand out the keyword",
        # 2026-10-18: the serve regex read ability-word / card names (Shadow of the
        # Goblin's "Undying Vengeance", Undying Flames).
        None,
        serve_idents=frozenset({"has_undying_persist|you|"}),
        serve_keywords=("undying", "persist"),
    ),
    # ── Enabler-and-payoff avenues ──────────────────────────────────────────────
    ("minus_counters_matter", "you"): _spec(
        "-1/-1 counters",
        "Wither/Infect bearers and -1/-1 placers plus the payoffs that reward a board "
        "shrinking under -1/-1 counters (Hapatra, Necroskitter, Nest of Scarabs)",
        # Serves -1/-1 placers and payoffs; wither and infect bearers come in by
        # keyword, and the old pattern's reminder-text hits are gone.
        None,
        serve_idents=frozenset(
            {
                "minus_counters_matter|you|",
            }
        ),
        serve_keywords=("wither", "infect"),
    ),
    ("cycling_matters", "you"): _spec(
        "Cycling",
        "cycling cards to churn through your deck plus the payoffs that reward each "
        "cycle (Astral Slide, Drake Haven, Faith of the Devoted)",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"cycling_matters|you|"}),
        serve_keywords=("cycling",),
        search={"preset_names": ("cycling",)},
    ),
    ("kicked_spell_matters", "you"): _spec(
        "Kicked spells",
        "kicker/multikicker spells plus the payoffs that trigger on casting a kicked "
        "spell (Verazol, Hallar, Rumbling Aftershocks)",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"kicked_spell_matters|you|"}),
        serve_keywords=("kicker", "multikicker"),
    ),
    # colorless-hate counterspells ("Counter target colorless spell" — Ceremonious
    # Rejection, Consign to Memory) match the oracle arm but are NOT payoffs: veto them.
    ("colorless_matters", "you"): _spec(
        "Colorless / Eldrazi",
        "Devoid and Eldrazi colorless bodies plus the anthems, cost reducers, and "
        "cast-triggers that reward casting colorless creatures and spells",
        # 2026-10-18: the serve regex missed "colorless card" payoffs (Ancient
        # Stirrings, Ugin's Labyrinth).
        None,
        serve_idents=frozenset({"colorless_matters|you|"}),
        serve_keywords=("devoid",),
        serve_types=("eldrazi",),
        serve_not=r"counter target colorless",
    ),
    # ADR-0027 #24n G1 — base_power_matters (NEW niche lane). The payoffs that REWARD /
    # SCALE WITH / SELECT creatures by their BASE power or toughness (CR 613.4b refer,
    # not set): Bess Soul Nourisher's 1/1 ETB count, Zinnia's base-power-1 go-wide
    # scale, Duskana's draw-per base-2/2, Primo's base-0 combat trigger, Rapid
    # Augmenter's base-1 haste grant, Sword of the Squeak's equip scale. SERVE on
    # the base-reference grammar (a base-power/toughness count/condition); the kept
    # word mirror retired in favor of the structural `BasePtRef` read.
    ("base_power_matters", "you"): _spec(
        "Base power/toughness",
        "the small base-P/T tribe — anthems and triggers that reward creatures by "
        "their base power or toughness (Bess, Zinnia, Duskana, Primo, Rapid Augmenter, "
        "Sword of the Squeak)",
        # The regex served the base-P/T SETTERS (Turn to Frog, Figure of Destiny — layer
        # 7b, CR 613.4b), not the payoffs that count creatures by base P/T; the lane
        # reads only the payoffs.
        None,
        serve_idents=frozenset({"base_power_matters|you|"}),
    ),
    ("exalted_lone_attacker", "you"): _spec(
        "Exalted / lone attacker",
        "Exalted enablers plus the payoffs that reward a single attacker connecting "
        "(Rafiq, Sublime Archangel, Angelic Exaltation)",
        # 2026-10-18: the lane reproduces the serve regex; the IR wins.
        None,
        serve_idents=frozenset({"exalted_lone_attacker|you|"}),
        serve_keywords=("exalted",),
    ),
    # ADR-0034 _matters sweep SPLIT: the MAKER side of the old flash_matters — the
    # flash-GRANTERS (cast your spells as though they had flash — Leyline of
    # Anticipation, Vedalken Orrery, Yeva) plus flash creatures to ambush-cast.
    ("flash_makers", "you"): _spec(
        "Flash",
        "flash creatures to ambush-cast plus the flash-granters that build the deck "
        "around instant-speed play",
        # Serves the flash-granter lane beside the flash keyword; granters whose
        # grant is conditional or typed (Arlinn, Rootwater Shaman) are the remainder.
        None,
        serve_idents=frozenset({"flash_makers|you|"}),
        serve_keywords=("flash",),
        search={"preset_names": ("flash",)},
    ),
    # ADR-0034 _matters sweep SPLIT: the PAYOFF side — the opponent-turn cast triggers
    # that reward instant-speed play (Alela). Same flash serve pool as flash_makers.
    ("flash_matters", "you"): _spec(
        "Flash",
        "opponent-turn cast payoffs plus flash creatures and granters that build the "
        "deck around instant-speed play",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"flash_matters|you|"}),
        serve_keywords=("flash",),
        search={"preset_names": ("flash",)},
    ),
    ("team_evasion_grant", "you"): _spec(
        "Team evasion grant",
        "effects that hand an evasion keyword (menace / fear / flying / can't be "
        "blocked) to your whole board for a go-wide alpha strike",
        # 2026-10-18: the serve regex missed a pump between "control" and the grant
        # ("get +1/+0 and gain fear" — Dance of Shadows, Eldrazi Monument).
        None,
        serve_idents=frozenset({"team_evasion_grant|you|*"}),
    ),
    # Override the auto-registered saga_matters sweep spec: surface the FULL Saga pool
    # via a subtype search (the sweep spec only found lore-counter cards), and serve the
    # Sagas (serve_types) plus the lore-counter/chapter payoffs (Tom Bombadil, Narci).
    ("saga_matters", "you"): _spec(
        "Sagas",
        "Sagas to chain chapter abilities, plus the lore-counter and chapter-retrigger "
        "payoffs that reward them",
        # The lane's lore-counter reads plus the Saga-reference tribe ident (the
        # final-chapter payoffs — Tom Bombadil, Narci); Ian Chesterton's Saga replicate
        # is a gain.
        None,
        serve_idents=frozenset({"saga_matters|you|", "type_matters|you|Saga"}),
        serve_types=("saga",),
        search={"card_type": "Saga"},
    ),
    ("lessons_matter", "you"): _spec(
        "Lessons",
        "Lesson spells (your wishboard payload) plus the Learn enablers and Lesson "
        "payoffs that reward casting them",
        # The lane reads the Lesson payoffs; the Learn enablers (a keyword action the
        # lane does not read) ride the keyword field.
        None,
        serve_idents=frozenset({"lessons_matter|you|"}),
        serve_types=("lesson",),
        serve_keywords=("learn",),
        search={"card_type": "Lesson"},
    ),
    # Override the auto-registered suspend_matters sweep spec (serve was `\bsuspend\b`
    # only): widen to the whole time-counter superstructure — Suspend (702.62),
    # Vanishing (702.63), Impending, and time-counter/time-travel manipulation (701.56).
    ("suspend_matters", "you"): _spec(
        "Suspend / time counters",
        "suspend, vanishing, and impending cards plus the time-counter manipulators "
        "and payoffs (As Foretold, Jhoira, Dust of Moments) that exploit them",
        # Serve on the lanes' idents, shared with suspend_makers: the
        # suspend lane reads time-counter placements and references (a suspended
        # card is in exile with suspend and a time counter, CR 702.62b —
        # Clockspinning), extra_upkeep the extra upkeeps and beginning phases that
        # tick suspend down (Paradox Haze). Not served: Impending Flux, which only
        # names itself, and Venser's Diffusion, whose "or suspended card" phase
        # drops from the bounce target.
        None,
        serve_idents=frozenset(
            {"suspend_makers|you|", "suspend_matters|you|", "extra_upkeep|you|"}
        ),
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
        # 2026-10-18: the serve regex missed vanishing bodies (Idris, Soul of the
        # TARDIS); the suspend lane plus extra upkeeps (Paradox Haze) reproduce it.
        None,
        serve_idents=frozenset(
            {"suspend_makers|you|", "suspend_matters|you|", "extra_upkeep|you|"}
        ),
        serve_keywords=("suspend",),
    ),
    ("saddle_matters", "you"): _spec(
        "Saddle / Mounts",
        "Mounts to ride plus the cheap wide creatures that pay the Saddle cost and the "
        "attacks-while-saddled payoffs (Calamity, Gitrog Ravenous Ride)",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"saddle_matters|you|"}),
        serve_keywords=("saddle",),
    ),
    ("suspect_makers", "you"): _spec(
        "Suspect makers",
        "cards that suspect creatures (menace + can't block) to fuel your "
        "suspected-creature payoffs",
        # 2026-10-18: the lane reproduces the serve regex card for card; the IR wins.
        None,
        serve_idents=frozenset({"suspect_makers|you|"}),
    ),
    ("suspect_matters", "you"): _spec(
        "Suspect payoffs",
        "payoffs that reward having suspected creatures",
        # 2026-10-18: the serve regex missed the suspect-it makers that feed the
        # payoffs (Barbed Servitor, Caught Red-Handed); the makers sibling serves them.
        None,
        serve_idents=frozenset({"suspect_matters|you|", "suspect_makers|you|"}),
    ),
    # ADR-0027: cmdzone_ability had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a 'command' ability-zone / condition-zone
    # structural arm + a kept word mirror for the static-Eminence cost-reducer).
    # Hand-registered (the sweep auto-register loop used to build it); the serve reads
    # the lane's ident.
    ("cmdzone_ability", "you"): _spec(
        *SWEEP_LABELS["cmdzone_ability"],
        # 2026-10-18: the Card IR's command-zone read reproduces the serve regex.
        None,
        serve_idents=frozenset({"cmdzone_ability|you|"}),
    ),
}
