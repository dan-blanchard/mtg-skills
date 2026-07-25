"""The card-type / cares-about membership floor and its tables.

Extracted 2026-07-25 from the retired regex/IR signal engines; every symbol
here is production-serving (imported by signals.py, structural lanes,
bridges, or the membership floor)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import (
    CLASS_TRIBES,
    CREATURE_SUBTYPES,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import (
    EXILE_MATTERS_REGEX,
    LAND_DESTRUCTION_REGEX,
    LAND_SACRIFICE_REGEX,
    SWEEP_DETECTORS,
)
from mtg_utils._deck_forge.signal_base import _GENERIC_KEYS, Signal, _clauses
from mtg_utils._deck_forge.text_reads import (
    _EVERGREEN_KW_WORDS,
    _VOLTRON_EQUIP_RE,
    _detect_self_damage_prevention,
    _detect_token_maker,
    _self_dies_value,
    _self_etb_value,
    _voltron_double_strike_beater,
    _voltron_land_scaler,
    _voltron_self_heroic,
    _voltron_self_pump,
    _voltron_self_recurs,
    _voltron_self_unblockable,
)
from mtg_utils.card_classify import card_pt_int

_EVERGREEN_KW_RE = tuple(
    re.compile(r"\b" + kw + r"\b", re.IGNORECASE) for kw in _EVERGREEN_KW_WORDS
)


_KEYWORD_SOUP_CONTEXT_RE = re.compile(
    r"creatures you control (?:gain|have)|each other creature you control"
    r"|if it has",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Detector:
    """A compiled floor/sweep detector: a regex over a clause → a scoped signal key.
    The single record type the extractor's Tier-3 loop consumes, whether the source
    is a curated hand-written rule or a row of the exhaustively-mined sweep table."""

    key: str
    scope: str  # forced scope ("you" | "opponents" | "each" | "any")
    pattern: re.Pattern[str]


_HAND_FLOOR: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # ADR-0027: goad_makers migrated to the Card IR — this second goad producer (the
    # force-OTHER-creatures-to-attack form + the "whenever a player attacks" / Kazuul
    # defending-player reward) is deleted. The IR recovers all three structurally: the
    # single-target political force via _GOAD_STYLE_FORCE over phase's force_attack
    # effect; the reward conditions via the _GOAD_REWARD_REF face marker
    # (project._dropped_static_markers). Floor-mirror-dep == 0 (goad_makers is NOT in
    # _IR_FLOOR_LANES). The hand-written serve spec (signal_specs.py) survives.
    # ADR-0027: modified_matters migrated to the Card IR — this FIRST of the two
    # _HAND_FLOOR producers (the indirect "power greater than its base power" anchor:
    # Kutzil, Baird — the only way a creature's power exceeds its BASE power is a
    # counter or a pump, CR 613.4c layer 7c, the modified-via-counter/Aura/Equip side)
    # is deleted. phase v0.1.19 doesn't structure "modified" (CR 700.9 — a derived
    # counter/Equipment/Aura union, not a parsed predicate), so the IR recovers it via
    # the UNION kept WORD MIRROR (`\bmodified\b` OR "power greater than its base power")
    # in _signals_ir._IR_KEPT_DETECTORS, run flat over the reminder-stripped joined-face
    # kept_oracle (byte-identical: both==47, regex_only==0, ir_only==0; scope 'you',
    # HIGH). The deleted producers fired HIGH-confidence scope 'you' and fed
    # has_other_plan; since the IR re-supply is the SAME breadth (residual 0),
    # modified_matters is added to _VOLTRON_SILENCING_PLAN_KEYS (signals.py) to
    # re-supply the pre-migration commander-damage voltron silence (file-swap voltron
    # delta 0). The SECOND producer (the `\bmodified\b` word) is deleted below. The
    # hand-written serve spec (signal_specs.py) survives. CR 700.9 / 301.5 / 303.4.
    # (plus_one_matters — formerly the "power greater than its base power" twin of this
    # producer — is independently migrated to the Card IR via project._P1P1_HAVE_FACE /
    # signals._P1P1_HAVE_REF → counters_have_ref; that producer is deleted too.)
    # ADR-0027: low_power_matters migrated to the Card IR — a non-dynamic
    # PtComparison:Power:LE/LT predicate on a you-controller Creature Filter, read by
    # _predicate_build_around_lanes (the recursion cards — Alesha, Reveillark — carry it
    # natively; phase DROPS it on the buff/etb subject shapes, recovered by a
    # `_LOW_POWER_REF` marker that rebuilds the Power:LE subject from "creatures you
    # control with power N or less" — Subira, Underfoot Underdogs). Removed from
    # _IR_FLOOR_LANES; serve stays hand-registered.
    # ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror. Both deleted
    # _HAND_FLOOR producers (this GO-WIDE count-scaler — "gets +N/+N for each creature
    # you control" / "power … equal to the number of creatures you control": Leonardo,
    # Adeline, Suki, Bravado — and the broad token PAYOFF producer below) are unioned
    # into TOKENS_MATTER_REGEX (_sweep_detectors) and re-fired byte-identically by
    # _TOKENS_MATTER_MIRROR in _signals_ir. Both fired HIGH-confidence (forced scope
    # 'you') and fed has_other_plan (a go-wide token engine is a real plan, not a
    # vanilla beater), so the voltron silence is re-supplied via
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py). The serve spec stays hand-registered in
    # signal_specs.py (its curated search regex was always independent of these
    # producers). CR 111.1 / 701.47.
    # ADR-0027 spellcast_matters (signals-only, SIDECAR 50): this recaster/copier
    # _HAND_FLOOR producer (Mavinda recasts from the yard, Velomachus casts off the
    # top, Naru Meha copies — enabler/copier forms with no "whenever you cast" trigger)
    # is deleted with the migration. Its pattern is pinned as _SPELLCAST_RECASTER_RE and
    # rides the byte-identical kept mirror _detect_spellcast_matters (re-run PER-CLAUSE
    # over the reminder-stripped kept_oracle in extract_signals_ir) — the `[^.]*` arm
    # never crosses a sentence, so flat == per-clause. CR 601.2.
    # Enchantment-TOKEN maker (Scriv "create a white Aura enchantment token", The Rani,
    # Preston Garvey) — makes enchantments, so it's an enchantment deck wanting
    # enchantment payoffs (Eriette, Sphere of Safety).
    (
        "enchantments_matter",
        re.compile(r"create [^.]*\benchantment token", re.IGNORECASE),
        "you",
    ),
    # Celebration (WOE ability word, CR 702.x reminder): every Celebration card carries
    # the exact phrase "two or more nonland permanents entered the battlefield under
    # your control this turn". Only 11 cards share it, so the phrase is its own precise
    # archetype lane — a Celebration commander (Ash) wants the other Celebration
    # payoffs (Grand Ball Guest, Raging Battle Mouse), which the bare attack trigger
    # never surfaced. Same phrase opens (commander) and serves (card).
    # ADR-0027: celebration_matters migrated to the Card IR — detected from the
    # kept word-detector mirror (signals._IR_KEPT_DETECTORS: \bcelebration\b, the
    # WOE ability word CR 207.2c phase doesn't structure). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py) is
    # independent of this regex and survives.
    # ADR-0027: land_sacrifice_matters (Gitrog, Titania, Slogurk, Zuran Orb, Sylvan
    # Safekeeper — a card paying an ongoing land-sac cost, drawing/growing when lands
    # hit the graveyard, or offering a repeatable "Sacrifice a land:" outlet) migrated
    # to the Card IR. phase carries NO structural form (the structural sacrifice arm
    # emits this lane on 0 commander-legal cards — a land-ONLY sac subject is routed
    # AWAY from sacrifice_outlets but never re-homed), so this _HAND_FLOOR producer is
    # deleted and survives BYTE-IDENTICALLY as the LAND_SACRIFICE_REGEX row in
    # _IR_KEPT_DETECTORS (scope 'you', HIGH conf — the EXACT pattern run flat over the
    # reminder-stripped kept_oracle; commander-legal: flat==per-clause==66, 0
    # gain/loss).
    # A distinct archetype from sacrifice_outlets (which EXCLUDES "sacrifice a land" —
    # the fetchland guard), land_destruction (DESTROY a land), land_exchange (swap land
    # CONTROL).
    # The hand-written serve spec (signal_specs.py) is independent and survives. The
    # deleted producer fed has_other_plan (HIGH, scope 'you', not generic/voltron-
    # compat); the hybrid re-silences voltron via _VOLTRON_SILENCING_PLAN_KEYS — the IR
    # re-supply IS this byte-identical mirror (IR==regex==66), so no over-silence and NO
    # _LAND_SACRIFICE_PLAN_MIRROR. CR 701.16 / 903.10a.
    # ADR-0027: proliferate_matters migrated to the Card IR. This divinity /
    # indestructible-counter _HAND_FLOOR producer (Myojin cycle, Arwen — enter
    # with one beneficial counter that proliferate multiplies) is DELETED; it
    # survives byte-identically as a HIGH-confidence _IR_KEPT_DETECTORS mirror in
    # _signals_ir (phase carries no structural form — the enters-replacement
    # place_counter projects with a blank kind the structural edge routes to
    # plus_one_matters, not proliferate_matters). The keyword/charge/remove-cost
    # producers are likewise re-homed; the serve spec stays hand-registered.
    # ADR-0027: tapped_matters migrated to the Card IR — the Tapped(controller='you')
    # Filter predicate read in three slots: the effect subject (Saryth's grant), the
    # amount.subject COUNT (Throne of the God-Pharaoh / Dragonscale General), and the
    # threshold-gate condition.subject (Vaultguard Trooper, Sami Ship's Engineer), plus
    # a `_TAPPED_GRANT` dropped-static face marker for the subject phase strips (Masako
    # "tapped creatures you control can block") and the count predicate phase drops
    # (Harvest Season). Removed from _IR_FLOOR_LANES; serve stays hand-registered in
    # signal_specs.
    # Legends-matter: a commander that TUTORS legends (Captain Sisay "search your
    # library for a legendary card"), BUFFS them (Dihada "target legendary creature
    # gains"), counts/cost-reduces them, or triggers off them (Yomiji "whenever a
    # legendary permanent ... is put into a graveyard"). All want legendary bombs.
    # ADR-0027: legends_matter migrated to the Card IR — served from the
    # HasSupertype:Legendary subject-Filter predicate + a kept word mirror
    # (_IR_KEPT_DETECTORS) merging both _HAND_FLOOR rows for the cost-reduction /
    # target-legendary / cast-legendary / library-search refs phase leaves textual.
    # Moved floor->kept (floor-mirror-dep -> 0); both _HAND_FLOOR producers deleted.
    # ADR-0027: the "sac-and-return-this-turn engine" floor (Garna, Gerrard, Moira)
    # is DELETED with the sacrifice_outlets migration — it over-fired on reanimation
    # engines that name no sacrifice at all (the IR path correctly drops them).
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR. The warp-GRANTING
    # membership cross-open (Tannuk: "cards in your hand have warp" — warp casts a hand
    # card for its warp cost and exiles it at end of turn, a temporary cheat-into-play;
    # a
    # commander handing out warp is a cheat deck wanting fat creatures + cheat enablers)
    # is DELETED; it survives BYTE-IDENTICALLY in the narrow _CHEAT_INTO_PLAY_RESIDUE_RE
    # mirror (the `have warp`/`gains warp` alt) in _signals_ir — phase emits no
    # structural
    # shape for a hand-wide warp grant. CR 702.184a.
    # ADR-0027: death_matters migrated to the Card IR. This "creature DIED this turn"
    # _HAND_FLOOR producer (scope "any", high-confidence — it fed has_other_plan) is
    # deleted along with the clause-scoped _DETECTORS producer above; both survive
    # byte-identically as the _DEATH_MATTERS_MIRROR in _signals_ir (the union pinned as
    # DEATH_MATTERS_REGEX), and the morbid-condition family feeds the regex-path
    # has_other_plan via _DEATH_MATTERS_PLAN_MIRROR below. The serve spec stays hand-
    # registered in signal_specs.py. CR 700.4.
    # ADR-0027 β: debuff_makers migrated to the Card IR. This Maha opponent-SHRINK
    # _DETECTORS row (scope "you") is deleted; it survives byte-identically as the
    # _DEBUFF_MAHA_REGEX _IR_KEPT_DETECTORS mirror, and feeds the regex-path
    # has_other_plan gate via _DEBUFF_MATTERS_PLAN_MIRROR below (it fired high-
    # confidence forced scope, silencing the spurious commander-damage voltron tell).
    # ADR-0027: direct_damage migrated to the Card IR. BOTH _HAND_FLOOR producers (this
    # player-BURN source — Syr Konrad, Mogis, Anathemancer, Fanatic of Mogis — and the
    # any-target/tap-ping/doubler/source-deals-damage producer below) are deleted. The
    # lane fires from the v22 damage Effect SCOPE arm in _signals_ir (scope 'opp'/'each'
    # always reaches a player; scope 'any' fires ONLY when the recipient is NOT
    # creature/permanent-restricted AND the raw names a player — so creature-only bite
    # stays removal) PLUS the byte-identical _DIRECT_DAMAGE_MIRROR (the OR of
    # these two deleted producers) for the under-structured player-reaching tail
    # (doublers, damage-matters payoffs, controller-riders, DFC/coin-flip burst). The
    # serve spec stays hand-registered in signal_specs.py. The deleted producers fired
    # HIGH-confidence scope 'you' and fed has_other_plan; the migrated IR is BROADER
    # (+139 ir_only), so the byte-identical _DIRECT_DAMAGE_PLAN_MIRROR below — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — re-supplies the exact pre-migration voltron silence
    # set. CR 120.1 / 115.4 / 903.10a.
    # ADR-0027 tranche2-C: free_creature_payoff migrated to the Card IR — an ETB
    # trigger whose condition tree carries a manaspentcondition (Satoru the
    # Infiltrator), read structurally in extract_signals_ir. The deleted "no mana …
    # spent to cast" regex 100% over-fired on anti-free-spell PUNISHERS (Nix, Roiling
    # Vortex, Vexing Bauble, Lavinia, Boromir — counter/tax opponents' free spells) and
    # self-punish/self-bonus forms (Primeval Spawn, Freestrider Commando); the
    # etb-trigger gate correctly excludes all of them. The serve spec stays in
    # signal_specs (all_of(creature, mana_cost ^{0}$), independent of this regex).
    # ADR-0027: mass_death_payoff migrated to the Card IR — a `_MASS_DEATH_REF`
    # ("for each|number of … creature … died this turn") count-operand marker
    # (project._dropped_static_markers), keyed on the AGGREGATE board-wipe shape and
    # EXCLUDING the single-death conditional ("if a creature died this turn", morbid —
    # plain death_matters). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027 (t2b5-B): per_target_payoff migrated to the Card IR (kept_detector).
    # Hinata's YOUR-arm ("Spells you cast cost {1} less to cast for each target") has no
    # IR shape — the IR has no mana_cost / cost-reduction model and no per-spell target-
    # count operand, so the arm is DROPPED from the parse entirely. The IR path detects
    # it from a byte-identical _IR_KEPT_DETECTORS word mirror; this _HAND_FLOOR producer
    # is deleted; the hand-written serve spec (signal_specs.py, X-/multi-target spells)
    # is independent of this regex and survives.
    # ADR-0027: arcane_matters migrated to the Card IR via a BYTE-IDENTICAL kept WORD
    # MIRROR (the `\barcane\b` row in _signals_ir._IR_KEPT_DETECTORS, scope 'you'). The
    # Kamigawa Arcane / Splice-onto-Arcane / Spiritcraft archetype — "cast a Spirit or
    # Arcane spell" (Tallowisp), "Splice onto Arcane" (the Kamigawa I/S spells); CR
    # 205.3k spell type, CR 702.47 Splice. phase v0.1.19 doesn't structure Arcane (a
    # SPELL TYPE on Instants/Sorceries, not a creature subtype or keyword), so the IR
    # rides the EXACT deleted pattern over the reminder-stripped kept_oracle (no `[^.]*`
    # span → flat == per-clause → byte-identical, both==92, regex_only==0, ir_only==0).
    # This _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py
    # — splice-onto-arcane + serve_types ('arcane',)) is independent and survives. The
    # deleted producer fed has_other_plan (HIGH, scope 'you'), but is NOT added to
    # _VOLTRON_SILENCING_PLAN_KEYS — the file-swap leaked 0 voltron (all 92 Arcane
    # bodies already carry another plan), so an entry would be dead over-silencing.
    # ADR-0027: has_enlist migrated to the Card IR — detected from the Scryfall
    # `enlist` keyword (signals._IR_KEYWORD_MAP, a structured-field lookup). This
    # _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_keywords=("enlist",)) is independent of this regex and survives.
    # ADR-0027: power_tap_engine migrated to the Card IR — an ACTIVATED ability whose
    # cost contains 'tap' plus a power-scaling effect raw (the structural arm in
    # extract_signals_ir's ability loop), plus an _IR_KEPT_DETECTORS mirror (byte-
    # identical to this deleted regex) for the conferred/quoted "{T}: … equal to its
    # power" grant phase folds into a grant carrier. This _HAND_FLOOR producer is
    # deleted; the hand-written serve spec (signal_specs.py, untap effects) survives.
    # ADR-0027: recast_etb migrated to the Card IR. DETECTOR (the bounce-replay
    # engine): the Scryfall `Sneak` keyword (_IR_KEYWORD_MAP, 28 cards — the TMNT/
    # Marvel ninjutsu-on-a-spell variant) drops the four `\bsneak\b`-regex over-fires
    # (Cheatyface "you may sneak", Lightfoot Rogue "Sneak Attack" ability word,
    # Fraternal Exaltation, empty-keyword Ninja Teen). Ninjutsu proper / "return an
    # unblocked attacker" is ALREADY has_ninjutsu, so recast_etb keys on Sneak
    # specifically. SERVE (the aggressive-ETB payoff): an etb Trigger plus a
    # discard/lose_life/sacrifice effect whose raw names "each opponent" (the
    # aggressive enter-bleed the recast repeats — Liliana's Specter, Skirmish Rhino),
    # wired in the trigger loop of extract_signals_ir. This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: exert_matters migrated to the Card IR. The team-VIGILANCE enabler
    # (Heliod, Always Watching, Brave the Sands — team vigilance neutralizes exert's
    # only downside, "won't untap next turn") is served STRUCTURALLY from a
    # grant_keyword effect with counter_kind=='vigilance' over a generic-creature-you-
    # control subject (the exert arm in the grant_keyword block of extract_signals_ir;
    # _is_generic_creature_filter admits Heliod's `Another` / Always Watching's
    # `NonToken` predicate but excludes the subtype-scoped Golem/Sliver/Warrior grants
    # and the single-target Kytheon's Tactics). The Johan namesake — "attacking
    # doesn't cause creatures you control to tap" — projects to a restriction whose
    # clause survives only in raw, so it is served by a kept word mirror
    # (_IR_KEPT_DETECTORS). This _HAND_FLOOR producer is deleted; the serve spec
    # (signal_specs.py, serve_keywords=("exert",)) stays hand-registered.
    # ADR-0027 t2b4-C: tap_down_blockers ("Can't be blocked unless ALL block" —
    # Tromokratis) migrated to the Card IR (kept_detector). phase DROPS the conditional-
    # evasion clause entirely (only the hexproof grant survives), so there is no
    # structural shape to read — the literal phrase is the only signal. It fires from an
    # _IR_KEPT_DETECTORS word mirror (the exact regex). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: island_matters migrated to the Card IR (the islandwalk / island-
    # attack-restriction lane: islandwalk bearers Thada Adel / Wrexial; GRANTERS /
    # token-makers / references Lord of Atlantis / Fishliver Oil / Chasm Skulker /
    # Mystic Decree; the Zhou Yu "can't attack unless defending player controls an
    # Island" restriction). The lane fires from a BYTE-IDENTICAL kept WORD MIRROR
    # (_ISLAND_MATTERS_MIRROR in _signals_ir, pinned as ISLAND_MATTERS_REGEX) — NOT the
    # Scryfall keyword array, which misses every GRANTER (the conferred-keyword gap).
    # This _HAND_FLOOR producer is deleted; the serve spec (signal_specs.py, "lands
    # become Islands") survives. The deleted producer fired HIGH-confidence (forced
    # scope 'you') and fed has_other_plan (24 island creatures — Sea Serpent, Marjhan,
    # Zhou Yu — carry island_matters as their SOLE plan), so island_matters is added to
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py) for the byte-identical re-supply
    # (79 == 79, voltron 3010 -> 3010).
    # ADR-0027 β: entered_attacker (the freshly-entered-attacker payoff — Samut
    # "if that creature entered this turn, draw a card" on combat damage;
    # Redoubled Stormsinger forks tokens that entered this turn on attack; Hixus
    # rewards itself having entered this turn) migrated to the Card IR via a
    # BYTE-IDENTICAL kept mirror. The "entered (the battlefield) this turn"
    # predicate is NOT projected (it survives only in raw), so there is no
    # structural IR shape to read — for ~3 commander-legal cards the clean
    # SIGNALS-ONLY path is a byte-identical _ENTERED_ATTACKER_MIRROR of the exact
    # deleted regex (pinned as ENTERED_ATTACKER_REGEX in _sweep_detectors), run
    # per-clause over the reminder-stripped oracle in _signals_ir, byte-identical
    # to this deleted floor Detector. NO voltron PLAN mirror is needed: each of
    # the 3 cards keeps has_other_plan via OTHER high-confidence non-generic
    # signals (combat_damage_matters / creature_etb / attack_matters /
    # tokens_matter), so deleting this producer leaks no voltron tell (voltron
    # delta 0, verified). The serve spec (signal_specs.py, "Haste + ETB pump") is
    # independent of this regex and survives. This _HAND_FLOOR producer is deleted.
    # ADR-0027: land_protection migrated to the Card IR — fired from the shared
    # land-animator predicate (animate/base_pt_set/type_set over a you/any Land subject)
    # + a kept oracle mirror (signals._IR_KEPT_DETECTORS) for the self-animate manlands
    # phase drops. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: lose_unless_hand migrated to the Card IR — an ETB trigger scoped to YOU
    # whose consequence is a lose_game effect (Phage the Untouchable; the etb +
    # scope=you + lose_game shape is structurally unique, in extract_signals_ir's
    # trigger loop). This _HAND_FLOOR producer is deleted; the hand-written serve spec
    # (signal_specs.py, drawback negation) survives.
    # ADR-0027: land_denial migrated to the Card IR — fired structurally from a
    # `phasing` Effect on a Land subject with controller=='you' (Taniwha). This
    # _HAND_FLOOR producer is deleted; the serve spec (the LD-punisher serve) stays
    # hand-registered in signal_specs.py and is unaffected.
    # ADR-0027: aoe_ping migrated to the Card IR — a REPEATABLE "damage to each
    # creature" board ping (Tibor, Pestilence, Pyrohemia) is structurally an Effect
    # (category=='damage', counter_kind=='all', Creature subject) carried by a
    # REPEATABLE-FRAME ability: an activated ability whose cost has 'tap'/'mana' but
    # NOT 'sacself'/'sacrifice' (the {T}: gate the cost field now supplies), OR a
    # triggered ability on upkeep/end_step/cast_spell (extract_signals_ir, per-ability
    # loop). A one-shot ETB sweep (Chaos Maw, event='etb') or sac-self pinger
    # (Bloodfire Colossus, cost='mana,sacself') can't be suited up before it fires, so
    # both are excluded. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py (deathtouch on the source so each ping kills).
    # ADR-0027: nonhuman_attackers migrated to the Card IR — detected structurally
    # from an attacks-trigger whose subject Filter carries NotSubtype:Human and a
    # "you"-controller (the dedicated branch in extract_signals_ir). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py, fliers that
    # connect) is independent of this regex and survives.
    # ADR-0027 (t2b2-A): control_exchange migrated to the Card IR — an `exile` Effect
    # whose subject carries the `Owned` predicate ("creature/permanent you OWN"), PAIRED
    # with a to:battlefield return in the same ability (Meneldor, The Neutrinos,
    # Aminatou). The inverse of the exile_removal Owned-exclusion. This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py, "Control
    # swaps") is independent of this regex and survives.
    # ADR-0027 t2b5-C: theft_protection migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact "for the first
    # time each turn, counter" regex). phase parses Kira's granted shield as a grant
    # carrier + a counter_spell effect but does NOT structure the once-per-turn becomes-
    # target gate, so the phrasing survives only on the oracle. This _HAND_FLOOR
    # producer is deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027 q2-D2: opp_top_exile migrated to the Card IR — a name-lock /
    # impulse-cast engine that exiles from an opponent's zone AND lets a card be
    # PLAYED from there (Circu, Ragavan, Gonti, Villainous Wealth). Fires from the
    # structural extract_signals_ir arm (exile scope=='opp' + cast_from_zone
    # scope=='opp', OR exile scope=='opp' carrying 'in:library') — which adds 50
    # steal-and-cast cards this regex never reached — plus an _IR_KEPT_DETECTORS word
    # mirror reproducing this exact regex for the name-lock / peek subset phase
    # under-parses (Circu's exile scope=='any'; Scrib Nibblers; granted "exile the top
    # card" on Predators' Hour). This _HAND_FLOOR producer is deleted; the serve spec
    # stays hand-registered in signal_specs.py.
    # ADR-0027 t2b5-A: free_plot migrated to the Card IR — Fblthp makes the top card's
    # plot cost = its mana cost (the cEDH artifact-combo / storm engine), but no IR
    # structure exists for the Plot alt-cost rewrite (phase routes the clause to a
    # subjectless topdeck_select). The lane fires from a signals._IR_KEPT_DETECTORS word
    # mirror (the exact "plot cost is equal to its mana cost" phrase — literally unique
    # to one card, zero over-fire). This _HAND_FLOOR producer is deleted; the serve spec
    # (the 0-cost-cards serve) stays hand-registered in signal_specs.py.
    # ADR-0027: multicolor_matters migrated to the Card IR — served from the
    # multicolor ColorCount subject-Filter predicate (the "multicolored <permanent> you
    # control" / "multicolored card" build-arounds — Niv-Mizzet Reborn, Rienne) + a
    # _IR_KEPT_DETECTORS word mirror for the "cast a multicolored spell" trigger / "for
    # each color pair" refs that aren't a structured subject. This _HAND_FLOOR producer
    # is deleted; the serve spec stays hand-registered.
    # ADR-0027 (t2b5-B → SIDECAR v40): target_own_payoff migrated to the Card IR via a
    # STRUCTURAL trigger read. phase HAS a `BecomesTarget` mode (CR 702.21a), so the
    # lane reads event=='becomes_target' + scope in (you,any) + NOT the project
    # `src:opp` zone tag (the you-can-self-target half — Heartfire Hero / Nadu / Brine
    # Comber / Monk Gyatso). The narrow "creature you control … you may" regex caught
    # only 2 cards; the structural event reaches all the own-target payoffs. This
    # _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py,
    # en-Kor / {0}-equip enablers) is independent of this regex and survives.
    # ADR-0027: life_payment_insurance migrated to the Card IR — a repeatable "Pay N
    # life:" ACTIVATION COST ("paylife" in Ability.cost; Selenia, Beledros, the
    # fetchlands — genuine recall the narrow regex missed) + a `life_payment` marker for
    # the misparsed cost (Arco-Flagellant, Hibernation Sliver) and the conferred quoted
    # "…Pay 1 life: Draw" ability phase drops (Underworld Connections, the volvers).
    # NOT in _IR_FLOOR_LANES; serve stays hand-registered. (CR 118.)
    # ADR-0027: land_exchange migrated to the Card IR — phase's `gain_control` effect
    # over a Land subject, plus a raw fallback (_LAND_EXCHANGE_RAW) for the "exchange
    # control of target X and target Y" shape phase parses with subject=None (Political
    # Trickery, Vedalken Plotter, Gauntlets of Chaos). NOT in _IR_FLOOR_LANES; the
    # serve spec stays hand-registered in signal_specs. The deleted regex's other
    # alternation ("activated abilities of lands … opponents control") only over-fired
    # on Sharkey (copies/taxes land abilities, never exchanges control — it emits NO
    # gain_control effect, so the structural IR correctly drops it).
    # ADR-0027: scavenge_fuel migrated to the Card IR — the Scryfall `scavenge`
    # keyword (_IR_KEYWORD_MAP, the intrinsic scavengers) plus a `scavenge`
    # dropped-static face marker for the graveyard-wide GRANTERS phase drops ("Each
    # creature card in your graveyard has scavenge" — Varolz, Young Deathclaws, The
    # Cave of Skulls, project._dropped_static_markers, read via _DOER_EFFECT_KEYS).
    # The "\bscavenge\b" floor over-fired on the "Scavenge the Dead" ability WORD
    # (CR 207.2c — Malanthrope), which the structural IR correctly excludes. This
    # _HAND_FLOOR producer is deleted; the serve spec stays in signal_specs.
    # ADR-0027 β: free_spell_storm migrated to the Card IR. A per-spell SCALING
    # self-discount whose cost drops for each spell cast THIS TURN (Thrasta "for each
    # other spell cast this turn"; Demilich / A-Demilich "for each instant and
    # sorcery spell you've cast this turn") — the deck wants FREE (0-cost) spells to
    # chain and keep cutting it (Ornithopter, Memnite, Lotus Petal, Mishra's Bauble).
    # phase models the discount as a SelfRef ModifyCost{Reduce} static (DROPPED by
    # project._project_static_mods — a self-discount is rules-excluded from the
    # build-around cost_reduction lane, CR 601.2f); project._free_spell_storm_marker
    # re-surfaces it as a dedicated `free_spell_storm` STATIC Effect (the migrated
    # lane reads it in _signals_ir), gated to the cast-this-turn dynamic_count shape
    # so an opponent-spell tax (Delightful Discovery) never fires. FULLY STRUCTURAL —
    # no _PLAN_MIRROR needed (the deleted regex matched only 2 cards; the marker
    # drops its lone over-fire and adds recall). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py. NOT in
    # _IR_FLOOR_LANES (floor-mirror-dep == 0).
    # ADR-0027 (t2b5-B → SIDECAR v40): target_redirect migrated to the Card IR via a
    # STRUCTURAL trigger read. phase HAS a `BecomesTarget` mode (CR 702.21a), and
    # `_project_trigger` surfaces the targeting spell's controller as the `src:opp` zone
    # tag, so the lane reads event=='becomes_target' + scope in (you,any) + src:opp (the
    # opponent-targets-your-stuff punisher — Rayne / Shapers' Sanctuary / Diffusion
    # Sliver / Tectonic Giant). The narrow "an opponent controls … draw" regex caught
    # only 11 cards and double-fired Shapers' Sanctuary into target_own_payoff too; the
    # structural src:opp split is clean. This _HAND_FLOOR producer is deleted. The
    # hand-written serve spec (signal_specs.py, redirect spells) is independent of this
    # regex and survives — the redirect SERVE pool is itself structural via
    # category=='redirect' should anyone tighten it later.
    # ADR-0027: ramp migrated to the Card IR. Its TWO _HAND_FLOOR producers are
    # deleted — this dork-support arm (Raggadragga: "Each creature you control with a
    # mana ability gets +2/+2 … untap it when it attacks") and the main mana-production
    # arm below. The dork-support arm has no structural form (phase drops the "with a
    # mana ability" subject), so it rides _MANA_DORK_SUPPORT_MIRROR in
    # _signals_ir (already present for the mana_amplifier dork arm — same regex); the
    # main arm rides _RAMP_MATTERS_REGEX + the structural `not card_is_land` ramp arm.
    # The has_other_plan voltron silence is re-supplied by _RAMP_MATTERS_PLAN_MIRROR
    # (the migrated IR arm is BROADER, so _VOLTRON_SILENCING_PLAN_KEYS would over-
    # silence). The serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: proliferate_matters migrated to the Card IR. This beneficial-
    # resource-counter _HAND_FLOOR producer (charge — Immard; experience — Ezuri,
    # Mizzix, Meren — counters that accumulate for upside, so the commander wants
    # PROLIFERATE) is DELETED; it survives byte-identically as a HIGH-confidence
    # _IR_KEPT_DETECTORS mirror in _signals_ir (phase carries no structural form
    # for a charge/experience-counter reference). The serve spec stays hand-
    # registered in signal_specs.py.
    # ADR-0027: treasure_matters migrated to the Card IR — detected structurally like
    # blood_matters: a Treasure-subtype make_token maker (incl. the die-roll/vote/choice
    # branch + Aftermath-DFC recovery), a "Sacrifice a Treasure" SAC PAYOFF, and a
    # `token_subtype_ref` "Treasures you control" / "was a Treasure" cares-about marker
    # (project._narrow_token_subtype_makers + _dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; floor-mirror-dep == 0. The structural IR is broader-and-correct
    # recall (the make_token-SUBJECT Treasure makers the "create … treasure token" regex
    # missed — Old Gnawbone, Prismari Command, Wanted Scoundrels). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec survives.
    # ADR-0027: artifacts_matter migrated to the Card IR — the ARTIFACTS go-wide /
    # matters axis (artifact-population anthems / counts, affinity / metalcraft /
    # improvise, artifact ETB / cast triggers, tutors / recursion / sac-outlets / token-
    # makers). The lane fires from the STRUCTURAL arms in extract_signals_ir (the
    # `_TYPE_MATTERS_LANE` count/grant/trigger DOERs, the `_ARTIFACT_TOKEN_SUBTYPES`
    # maker/sac arm, the type-gate condition arm, and the type_line membership arm —
    # +325 ir_only recall the brittle oracle regex missed: Food/Clue/Treasure subtype
    # sac payoffs + DFC back-face recursion) PLUS the NARROWED _ARTIFACTS_MATTER_MIRROR
    # (the deleted _HAND_FLOOR producer UNIONed with the kept "if you control an
    # artifact" SWEEP row) run per-clause for the oracle-idiom family no structural
    # shape covers.
    # NARROWED: the bare `\baffinity\b` branch became `affinity for artifacts`,
    # dropping the 22 affinity-for-non-artifact over-fires (Icebreaker Kraken's snow
    # affinity, Argivian Phalanx's creature affinity — none an artifacts deck). BOTH
    # this clause-
    # scoped _HAND_FLOOR producer AND the line-4349 type_line membership producer are
    # deleted (the IR membership arm reproduces the latter byte-identically); the kept
    # SWEEP row stays (len(SWEEP_DETECTORS) >=36). The serve spec stays hand-registered;
    # _ARTIFACTS_MATTER_PLAN_MIRROR re-supplies the has_other_plan voltron silence.
    # (CR 702.41 / 207.2c / 205.3g.)
    # ADR-0027: enchantments_matter migrated to the Card IR — the ENCHANTMENTS go-wide
    # / matters axis (enchantment-population anthems / counts, constellation,
    # enchantress cast triggers, enchantment tutors / recursion / sac-outlets /
    # token-makers, Role-token makers — Roles ARE Aura enchantments per CR 303.7 /
    # 111.10j). The lane fires from the STRUCTURAL arms in extract_signals_ir (the
    # `_TYPE_MATTERS_LANE` Enchantment count/grant/trigger DOERs, the Enchantment
    # make_token / Bargain-gated sac-payoff DOER, the type-gate condition arm, the
    # becomes-Enchantment / type-recursion / type-tutor arms, the Aura-subtype "loose
    # enchantments member" arm, and the type_line membership arm — shared with
    # artifacts_matter; +95 ir_only recall the brittle oracle regex missed: Licids that
    # become Auras, Aura / Glimmer / enchantment-creature token makers, Aura recursion,
    # single-type sac-an-enchantment outlets, "if you control an enchantment"
    # conditions) PLUS the BYTE-IDENTICAL _ENCHANTMENTS_MATTER_MIRROR (the deleted
    # _HAND_FLOOR producer ALONE — there is NO dedicated enchantment SWEEP row, unlike
    # artifacts' "if you control an artifact" row, so SWEEP_DETECTORS stays 36) run
    # per-clause for the oracle-idiom family no structural shape covers (enchantment
    # tutors / recursion-from-graveyard /
    # "enchantment card in your hand" miracle-grant / Role-token makers). BOTH this
    # clause-scoped _HAND_FLOOR producer AND the type_line membership producer below are
    # deleted (the IR membership arm reproduces the latter byte-identically). The serve
    # spec stays hand-registered; _ENCHANTMENTS_MATTER_PLAN_MIRROR re-supplies the
    # has_other_plan voltron silence. (CR 205.2 / 303 / 303.7.)
    # ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror — this broad
    # token PAYOFF producer ("tokens you control" anthems/refs — Intangible Virtue,
    # Mirror Box, Brudiclad; a "whenever a/one or more/another … token … enters" trigger
    # — Woodland Champion, Junk Winder; and the token DOUBLER replacement "tokens would
    # be created/put" / "create twice that many … token" / "twice that many … tokens" —
    # Doubling Season, Parallel Lives, Mondrak, Divine Visitation) is deleted, unioned
    # with the GO-WIDE count-scaler above into TOKENS_MATTER_REGEX and re-fired by
    # _TOKENS_MATTER_MIRROR in _signals_ir. Voltron silence re-supplied via
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py). CR 111.1 / 701.47.
    # ADR-0027: stax_taxes migrated regex→Card IR. This _HAND_FLOOR producer
    # (`opponents can't` / `spells your opponents cast cost` / `creatures your opponents
    # control`) is DELETED with the _DETECTORS pacify row above. Its broad `creatures
    # your opponents control` branch over-fired on every -X/-X debuff anthem (Elesh
    # Norn, Massacre Wurm, Cower in Fear — NOT restriction/tax statics), which the
    # structural `restriction` IR arm correctly drops. The genuine firings are
    # reproduced byte-identically by _STAX_TAXES_MIRROR (_signals_ir) from
    # STAX_TAXES_REGEX (the union of this row + the deleted _DETECTORS row + the kept
    # SWEEP row). The deleted producer fired HIGH (forced scope 'opponents') and fed
    # has_other_plan, so the byte-identical _STAX_TAXES_PLAN_MIRROR (below) re-supplies
    # the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS (the IR is broader). The
    # serve spec stays hand-registered. CR 604.1 / 903.10a.
    # ADR-0027 β: cost_reduction migrated to the Card IR — this _HAND_FLOOR producer
    # (and the SWEEP_DETECTORS row) are deleted. The lane fires from the IR arm +
    # _COST_REDUCER_MIRROR in _signals_ir; the deleted regex's voltron silence is
    # restored by _COST_REDUCTION_PLAN_MIRROR above (its high-confidence producer fed
    # has_other_plan). The serve survives via the pinned COST_REDUCTION_REGEX constant.
    # ADR-0027: cast_from_exile migrated to the Card IR — this _HAND_FLOOR producer
    # (the CAST/PLAY-FROM-EXILE build-around: payoffs/enablers that cast or play cards
    # FROM EXILE — plot, the "from exile" / "from anywhere other than your hand" Paradox
    # triggers, self-cast-from-exile creatures, exile-and-cast engines, the Adventure-
    # style exile-from-hand cycle) is DELETED. phase carries NO usable structural form
    # (it drops the "from exile" zone off the cast_spell trigger AND the self-cast
    # cast_from_zone Effect; the only exile cast-zone it projects — castable_zones=
    # ('exile',) — is the 51-card foretell-spell SERVE pool, DISJOINT from these 77
    # detector firings), so the lane fires SOLELY from the byte-identical kept word
    # mirror — CAST_FROM_EXILE_REGEX (pinned in _sweep_detectors) run FLAT over the
    # reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS loop
    # (commander-legal: flat==per-clause==77, 0 gain/loss). Distinct from impulse_top_
    # play (exile the TOP of YOUR library then temporary-play — its own avenue) and
    # play_from_top below (the ONGOING permission to play off the top of the LIBRARY — a
    # different zone, not exile). The deleted producer fired HIGH (scope 'you') and fed
    # has_other_plan, so the hybrid re-silences the spurious commander-damage voltron
    # tell via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — byte-identical re-supply, no
    # over-silence. The serve survives via the standalone _spec in signal_specs.py
    # (never reads this regex). cast_from_exile was NEVER a SWEEP key, so no SWEEP row /
    # floor count moves (len stays 33). CR 207.2c / 601.3b / 903.10a.
    # ADR-0027 β: play_from_top migrated to the Card IR — this _HAND_FLOOR producer
    # (and the SWEEP_DETECTORS row) are deleted. The lane fires from the IR structural
    # arm (a STATIC cast_from_zone+from:library Effect over phase's
    # TopOfLibraryCastPermission mode) + the per-clause _PLAY_FROM_TOP_MIRROR /
    # _PLAY_FROM_TOP_FLOOR_MIRROR (the EXACT deleted SWEEP + this FLOOR regex). The
    # deleted regex's voltron silence is restored by _PLAY_FROM_TOP_PLAN_MIRROR below
    # (its high-confidence producer fed has_other_plan). The serve survives via the
    # pinned PLAY_FROM_TOP_REGEX constant in signal_specs.py. CR 116 / 601.3b.
    # ADR-0027: lands_matter migrated to the Card IR — served from the
    # amount.subject=Land count operand (the structured scalers) + a kept word mirror
    # (_IR_KEPT_DETECTORS) for the "P/T equal to the number of lands you control" and
    # "for each land you control" forms phase emits as characteristic_pt/pump_target
    # but DROPS the count operand. Moved floor->kept (floor-mirror-dep -> 0); this
    # _HAND_FLOOR producer is deleted.
    # ADR-0027: direct_damage migrated to the Card IR — this second _HAND_FLOOR producer
    # (any-target burn / {T}-ping / damage doubler / "source you control deals damage"
    # payoff) is deleted along with the player-burn producer above. It survives byte-
    # identically inside the _DIRECT_DAMAGE_MIRROR (_signals_ir), whose tail-arms ARE
    # these exact branches; the doublers + damage-matters payoffs phase emits as
    # replacement / trigger effects (not a `damage` Effect), so they ride the mirror
    # while the structural scope arm handles the player-reaching `damage` Effects. See
    # the migration note on the deleted player-burn producer above.
    # ADR-0027 β: mana_amplifier (the DOUBLER arm) migrated to the Card IR — this
    # _HAND_FLOOR producer is deleted. The lane fires from the IR structural arm (the
    # supplement-split `mana_amplifier` category + a _MANA_AMPLIFY_RAW discriminator
    # over the triggered `ramp` / `double` doublers, read additively) + the per-card
    # dork-support _MANA_DORK_SUPPORT_MIRROR, all in _signals_ir. The deleted regex's
    # voltron silence is restored by _MANA_AMPLIFIER_PLAN_MIRROR below (its high-
    # confidence producer fed has_other_plan — a mana-doubler engine IS a plan). The
    # serve survives via the standalone _spec in signal_specs.py (never read this
    # regex). CR 106.4 / 605.
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    # ADR-0027 (voltron migration — the LAST key): the Equipment/Aura PAYOFF producer
    # is DELETED from the regex path. Its regex lives on as VOLTRON_PAYOFF_REGEX above;
    # the IR path (extract_signals_ir) runs the SAME regex per-clause UNIONed with the
    # structural _detect_voltron_payoff_ir. extract_signals no longer emits voltron.
    # ADR-0027: vehicles_matter migrated to the Card IR. This broad _HAND_FLOOR
    # producer (the "Vehicles you control" anthem / crew payoff / Vehicle GRANTER form)
    # is deleted; its EXACT regex is pinned as VEHICLES_MATTER_REGEX in _sweep_detectors
    # and rides the byte-identical VEHICLES_MATTER_MIRROR kept WORD MIRROR in
    # _signals_ir._IR_KEPT_DETECTORS (scope 'you', flat over the reminder-stripped
    # kept_oracle == this floor Detector's per-clause scan, both==41). The SEPARATE
    # typed-graveyard-recursion Vehicle arm (_detect_typed_gy_recursion's "vehicle" row
    # — Greasefang: "return target Vehicle card from your graveyard to the battlefield",
    # which this floor regex never anchored) is re-supplied PER-CLAUSE in the IR path
    # too. After both, IR == the deleted regex producers EXACTLY (both==42, ir_only==0,
    # regex_only==0). FLOOR→KEPT: removed from _IR_FLOOR_LANES (floor-mirror-dep -> 0).
    # The deleted producer fired HIGH-confidence scope 'you' and fed has_other_plan, and
    # the IR re-supply is the SAME breadth (residual 0), so vehicles_matter is added to
    # signals._VOLTRON_SILENCING_PLAN_KEYS (byte-identical re-silence). The hand-written
    # serve spec in signal_specs.py is independent of this regex and survives. CR 301.7
    # (Vehicle artifact subtype) / 702.122 (Crew) / 305.7.
    # ADR-0027: scry_surveil_matters migrated to the Card IR — the scried/surveiled
    # trigger events (_PAYOFF_TRIGGER_KEYS) + phase's `scry_surveil` effect category
    # (the event='other' "whenever you scry/surveil" payoff trigger,
    # _narrow_trigger_other_refs) plus a `scry_surveil` dropped-static face marker
    # for the "if you would scry a number of cards … instead" REPLACEMENT phase drops
    # entirely (Kenessos, Eligeth — project._dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; this _HAND_FLOOR producer is deleted; the serve spec stays.
    # ── Named-mechanic long tail (precise named anchors → novel build-arounds) ───
    # ADR-0027: monarch_matters migrated to the Card IR — served structurally from
    # phase's `monarch` effect category (_DOER_EFFECT_KEYS, "you become the monarch"
    # grants narrowed in project._narrow_mechanic_refs) AND the Condition(ismonarch)
    # gate lifted in extract_signals_ir. Its oracle-regex floor detector is deleted;
    # the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: initiative_matters migrated to the Card IR — served from a
    # "\bthe initiative\b" _IR_KEPT_DETECTORS word mirror (phase v0.1.19 doesn't
    # structure the CR 720 initiative designation). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: ring_matters migrated to the Card IR — served structurally from
    # phase's `ring_tempt` effect category (_DOER_EFFECT_KEYS). A "Whenever the Ring
    # tempts you" trigger (CR 701.54) phase flattened to event='other', and a
    # "Ring-bearer" reference buried in any effect raw (Sauron — no tempt trigger),
    # are appended as `ring_tempt` marker effects by
    # project._narrow_trigger_other_refs. Its oracle-regex floor detector is deleted
    # and it is removed from _IR_FLOOR_LANES; the serve spec stays hand-registered.
    # ADR-0027: venture_matters migrated to the Card IR — phase's venture/take-the-
    # initiative effect category (_DOER_EFFECT_KEYS) + a condition-kind read
    # (completedadungeon / isinitiative — Gloom Stalker, Imoen, Safana) + a
    # trigger_doubling-over-dungeons read (Hama Pashar, Dungeon Delver) + a
    # `_VENTURE_REF` dropped-clause marker (You Find a Cursed Idol, Fly, Dungeon
    # Crawler). Removed from _IR_FLOOR_LANES; serve stays hand-registered. (CR 701.46.)
    # ADR-0027: energy_matters migrated to the Card IR — phase's `energy` effect
    # category (_DOER_EFFECT_KEYS, the gainenergy producers) + an `_ENERGY_REF` ({e})
    # marker for the SINKS / "whenever you get {E}" payoffs / doublers phase loses.
    # Removed from _IR_FLOOR_LANES; serve stays hand-registered. (CR 122.1.)
    # ADR-0027: devotion_matters migrated to the Card IR — served from the
    # amount.op=="devotion" count operand (the scaling payoffs) + a "devotion to
    # <color>" _IR_KEPT_DETECTORS word mirror for the cost-reduction / counterspell-tax
    # / mana forms phase doesn't make a count operand. This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: superfriends_matters migrated to the Card IR — served from the EXISTING
    # structural arm (a Condition gated on a Planeswalker subject you control: "as long
    # as you control a <Name> planeswalker, …", +26 commander-legal ir_only the regex
    # missed) PLUS a byte-identical SUPERFRIENDS_MATTERS_REGEX _IR_KEPT_DETECTORS word
    # mirror for the "planeswalkers you control" anthem / "loyalty counter" payoffs /
    # "activate a loyalty ability" engines / "abilities of a planeswalker" copiers phase
    # leaves textual. This _HAND_FLOOR producer is deleted and superfriends_matters is
    # removed from _IR_FLOOR_LANES; the serve spec stays hand-registered in
    # signal_specs.py. The BROADER IR re-supply means the has_other_plan voltron silence
    # is restored by the byte-identical _SUPERFRIENDS_MATTERS_PLAN_MIRROR below (NOT
    # _VOLTRON_SILENCING_PLAN_KEYS, which would over-silence the 26 structural bodies).
    # ADR-0027: historic_matters migrated to the Card IR — served from the "Historic"
    # subject-Filter predicate + a "\bhistoric\b" _IR_KEPT_DETECTORS word mirror for the
    # cost-reduction / "play a historic" / type-group refs phase leaves textual
    # (artifacts, legendaries, and Sagas are historic). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: legends_matter migrated to the Card IR (see the merged
    # _IR_KEPT_DETECTORS mirror). This second _HAND_FLOOR producer is deleted too.
    # ADR-0027: big_hand_matters migrated to the Card IR — served from the v23
    # `no_max_handsize` Effect structural arm + the byte-identical
    # _BIG_HAND_MATTERS_MIRROR _IR_KEPT_DETECTORS word mirror for the "X = cards in your
    # hand" P/T-scaling payoffs (Maro, Psychosis Crawler — a `characteristic_pt` Effect
    # with NO in:hand zone) and the "N or more cards in hand" conditions. BOTH its
    # oracle-regex producers (this _HAND_FLOOR row + the SWEEP row) are deleted; the
    # _BIG_HAND_MATTERS_PLAN_MIRROR re-supplies the has_other_plan voltron silence (the
    # producers fired HIGH-confidence scope 'you'). The hand-written serve spec
    # (signal_specs.py) is independent of these regexes and survives. CR 402.2.
    # ADR-0027: party_matters migrated to the Card IR — served from the
    # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
    # "full party" CONDITION + "creatures in your party" non-count refs. This
    # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered.
    # ADR-0027: exile_matters migrated to the Card IR — the EXILE-ZONE-AS-RESOURCE
    # cares-about lane (cards STANDING in exile — "cards you own in exile" / "card in
    # exile with <kind> counter" payoffs + "exiled with <this>" persistent-pile
    # scalers + the "for each card exiled this way" one-shot scalers the prefix branch
    # also reaches). phase carries NO usable structural form (it scatters the
    # exile-zone reference across a `zones=('in:exile',)` count operand, a
    # `Condition(zones= ('exile',))`, and a `characteristic_pt` Effect whose count
    # operand drops the zone), so the lane fires from a BYTE-IDENTICAL kept WORD
    # MIRROR — EXILE_MATTERS_REGEX (pinned in _sweep_detectors) run FLAT over the
    # reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS loop
    # (commander-legal: flat==per- clause==63, 0 gain/loss — neither branch carries a
    # `[^.]*` cross-clause span). This was a regex FLOOR lane (in _IR_FLOOR_LANES);
    # FLOOR→KEPT, floor-mirror-dep -> 0. Distinct from exile_removal (EXILE a
    # permanent as REMOVAL), cast_from_exile (CAST/PLAY a card FROM exile), and
    # opponent_exile_matters (GRAVEYARD HATE). The deleted producer fired HIGH (scope
    # 'you') and fed has_other_plan, so the hybrid re-silences the spurious
    # commander-damage voltron tell via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) —
    # byte-identical re-supply, no over- silence. The serve survives via the
    # standalone _spec in signal_specs.py (never reads this regex). exile_matters was
    # NEVER a SWEEP key, so no SWEEP row / floor count moves (len stays 32). CR 406.
    # ADR-0027: experience_matters migrated to the Card IR — the GivePlayerCounter
    # ->experience_counter gainers (_DOER_EFFECT_KEYS) plus the experience SCALER
    # operand (op="experience" from a Ref->PlayerCounter{Experience}, project
    # ._quantity) for Atreus/Azula. This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec stays in signal_specs.
    # ADR-0027: poison_matters migrated to the Card IR — served from the
    # infect/toxic/poisonous Scryfall keywords (the bearers, _IR_KEYWORD_MAP) + a kept
    # word mirror (_IR_KEPT_DETECTORS) for the GRANTERS ("gains infect", "has
    # poisonous 1") and "poison counter" / "has toxic" references phase folds into a
    # grant carrier's raw. Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
    # ADR-0027: modified_matters migrated to the Card IR — this SECOND _HAND_FLOOR
    # producer (the direct `\bmodified\b` word: the Kamigawa Neon Dynasty "modified"
    # archetype, CR 700.9) is deleted. The IR recovers it (and the indirect "power
    # greater than its base power" anchor deleted above) via the UNION kept WORD MIRROR
    # in _signals_ir._IR_KEPT_DETECTORS (byte-identical, residual 0). The voltron
    # silence is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS. See the FIRST producer.
    # ADR-0027: has_mutate migrated to the Card IR — the Scryfall `mutate`
    # keyword (_IR_KEYWORD_MAP, the 34 mutate creatures) plus a `mutate` payoff
    # marker for the keyword-less cast-payoff ("if it has mutate" —
    # project._narrow_payoff_condition_refs, read via _DOER_EFFECT_KEYS; Pollywog
    # Symbiote). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: food_matters migrated to the Card IR — detected structurally like
    # blood_matters: a Food-subtype make_token maker (incl. the die-roll/vote/choice
    # branch + Aftermath-DFC recovery), a "Sacrifice a Food" SAC PAYOFF, and a
    # `token_subtype_ref` "Foods you control" / "is a Food" cares-about marker
    # (project._narrow_token_subtype_makers + _dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; floor-mirror-dep == 0. This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec survives.
    # ADR-0027: clue_matters migrated to the Card IR — STRUCTURAL ARM (the artifact-
    # token-subtype maker / sac payoff / token_subtype_ref marker shared with food/
    # treasure/blood) UNIONed with a byte-identical kept WORD MIRROR
    # (_CLUE_MATTERS_MIRROR in _signals_ir._IR_KEPT_DETECTORS, the EXACT deleted
    # `\bclue\b|\binvestigate\b` pinned as CLUE_MATTERS_REGEX). The mirror is REQUIRED:
    # the structural arm fires only 52 of the 163 commander-legal lane cards (phase tags
    # the Investigate keyword -> artifacts_matter but DROPS the Clue subtype off the
    # make_token subject — Deduce, Bygone Bishop, Thraben Inspector parse with
    # subject=None), so the 112 pure-investigate / Clue-payoff cards survive only
    # textually (regex_only == 0 after the mirror). The structural arm is BROADER (+1
    # ir_only: Tangletrove Kelp, whose "other Clues you control" the singular-only
    # `\bclue\b` missed — a genuine recall gain), so voltron is re-silenced by the byte-
    # identical _CLUE_MATTERS_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS, which would
    # over-silence Tangletrove Kelp). Removed from _IR_FLOOR_LANES. This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec survives. CR 701.16 / 111.10f.
    # ADR-0027: blood_matters migrated to the Card IR — detected structurally from a
    # Blood-subtype maker (make_token subject), a Blood SACRIFICE PAYOFF (a sacrifice
    # Effect/Trigger whose subject Filter carries the Blood subtype — Wedding
    # Security, Blood Hypnotist), and the choose-list / granted-ability maker
    # recovery (Transmutation Font, Ceremonial Knife — project._narrow_token_subtype_
    # makers). It is removed from _IR_FLOOR_LANES (no floor mirror; floor-mirror-
    # dependency == 0). This _HAND_FLOOR producer is deleted; the hand-written serve
    # spec (signal_specs.py) survives. (clue/food/treasure all now migrated too.)
    # ADR-0027 / ADR-0034: the Day/Night lane migrated to the Card IR and SPLITS at
    # the emission arm (NO mirror needed; CR 726 Day/Night): the daybound/nightbound
    # Scryfall KEYWORD via signals._IR_KEYWORD_MAP (the 35 transforming werewolves —
    # Tovolar, the werewolf cycles, Arlinn) is the PAYOFF arm and KEEPS
    # `daynight_matters`; the `day_night` EFFECT category via _DOER_EFFECT_KEYS (the 12
    # keyword-LESS "it becomes day/night" / "as long as it's day/night" transition
    # makers — Brimstone Vandal, The Celestus, Vadrik — and Tovolar's both-arm upkeep
    # flip) is the MAKER arm and emits `daynight_makers`. phase v0.1.19 structures the
    # transition cleanly, so the two arms reproduce this deleted _HAND_FLOOR producer
    # BYTE-IDENTICALLY (commander-legal: union==47, ir_only==0, regex_only==0).
    # This producer (formerly an _IR_FLOOR_LANE; moved floor->kept, floor-mirror-dep ->
    # 0) is deleted; the hand-written serve specs (signal_specs.py) survive. Both arms
    # fire high-confidence scope 'you' and feed has_other_plan; voltron self-derives in
    # extract_signals_ir (the old _VOLTRON_SILENCING_PLAN_KEYS cross-check is retired),
    # neither key is in any voltron-exclusion set, so voltron delta is 0.
    # ADR-0027: voting_matters migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: a broader vote regex that
    # also catches the plural + "each player votes"; voting CR 701.38 is a real
    # mechanic phase only partially structures). This _HAND_FLOOR producer is
    # deleted; the hand-written serve spec (signal_specs.py) survives.
    # ADR-0027: token_doubling migrated to the Card IR — detected structurally from
    # the token-doubling replacement effect (the `cat == "token_doubling"` branch in
    # extract_signals_ir). This _HAND_FLOOR producer is deleted; the hand-written
    # serve spec (signal_specs.py) survives. Token- and counter-doubling stay
    # separate lanes (a token doubler wants token makers; a counter doubler wants
    # counter sources).
    # ADR-0027: counter_doubling migrated to the Card IR — a structural
    # `cat == "counter_doubling"` replacement-effect arm (recovering the 6 canonical
    # replacement doublers this regex MISSED — Doubling Season, Branching Evolution,
    # Primal Vigor, Corpsejack Menace, The Earth Crystal, Struggle for Project Purity)
    # + a byte-identical COUNTER_DOUBLING_REGEX kept word mirror in _signals_ir (the 46
    # one-shot/activated/triggered "double the number of … counters" doublers phase
    # v0.1.19 mangles to a generic `double` effect or a plain
    # `place_counter`/`counter_distribute`). This _HAND_FLOOR producer (the UNION'd into
    # COUNTER_DOUBLING_REGEX) is deleted; the hand-written serve spec (signal_specs.py)
    # survives. The producer fired HIGH-confidence scope 'you' and fed has_other_plan,
    # so a byte-identical _COUNTER_DOUBLING_PLAN_MIRROR (below) re-supplies the
    # commander-damage voltron silence (the IR re-supply is BROADER — +6 — so NOT
    # _VOLTRON_SILENCING_PLAN_KEYS). CR 122 / 614 / 903.10a.
    # ADR-0027: second_spell_matters migrated to the Card IR — detected from a
    # byte-identical _SECOND_SPELL_MIRROR in signals._IR_KEPT_DETECTORS (the "second
    # spell each turn" / Dualcast-discount / Erayo-count payoff phase
    # under-structures: a bare `cast_spell` trigger drops the "second spell"
    # qualifier, identical to plain magecraft — so no structural arm can tell the
    # narrow second-spell payoff from the broad spellcast_matters lane). This
    # _HAND_FLOOR producer (formerly an _IR_FLOOR_LANE; moved floor->kept,
    # floor-mirror-dep -> 0) is deleted; the hand-written serve spec
    # (signal_specs.py) survives. The producer fired high-confidence scope 'you' and
    # fed has_other_plan, so second_spell_matters is added to
    # _VOLTRON_SILENCING_PLAN_KEYS (the IR re-supply is byte-identical, IR == regex
    # == 92, so the silencing-keys path re-silences exactly without over-silence).
    # ADR-0027: opponent_cast_matters migrated to the Card IR — the structural
    # cast_spell-trigger scope=opp arm (Lavinia, Nekusar) plus an _IR_KEPT_DETECTORS
    # mirror that DROPS this regex's over-broad bare "whenever a player casts a spell"
    # arm (the IR is more precise — symmetric-benefit / self-drawback over-fires are
    # excluded) and keeps only the explicit-opponent + symmetric-PUNISH ("that player"
    # anchor) branches. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: opponent_draw_matters migrated to the Card IR — detected
    # structurally from a "drawn" trigger event whose subject scope is an opponent
    # (the `ev == "drawn"` + `trig.scope == "opp"` branch in extract_signals_ir).
    # This _HAND_FLOOR producer is deleted; the hand-written serve spec
    # (signal_specs.py) is independent of this regex and survives.
    # ADR-0027 β: opponent_search_matters migrated to the Card IR — an opp-scoped
    # `lib_search` trigger (project._trigger_event re-types phase's SearchedLibrary /
    # Shuffled / scry-surveil-search PlayerPerformedAction modes off the generic
    # `other`; the scope=='opp' gate in extract_signals_ir is the discriminator vs the
    # YOU-scoped scry/surveil payoffs). This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec (signal_specs.py) is independent of this regex and
    # survives. NO voltron _PLAN_MIRROR is needed: although the producer fired
    # high-confidence (scope 'opponents') and fed has_other_plan, the FILE-SWAP shows
    # voltron delta 0 even with the lane absent — the two power<2 punishers (Wan Shi
    # Tong, Cosi's Trickster) never reach the voltron gate (power>=2 / voltron-keyword),
    # and every power>=2 punisher (River Song, Ob Nixilis, Archivist of Oghma) carries
    # ANOTHER high-confidence plan (direct_damage / death_matters / lifegain_matters)
    # that keeps has_other_plan True. So no body leaks the commander-damage tell.
    # ── Mechanics recovered from the "rejected" families (still-zero commanders) ──
    # ADR-0027 β: token_copy_makers migrated to the Card IR via a kept-mirror — the
    # lane fires from _TOKEN_COPY_MATTERS_MIRROR in _signals_ir (the EXACT deleted
    # regex, pinned as TOKEN_COPY_MATTERS_REGEX, over the reminder-stripped oracle),
    # NOT a structural CopyTokenOf/Populate arm (phase structures those but the 80-card
    # struct-only delta is 100% reminder-text SELF-copies — Embalm/Eternalize/Offspring/
    # Double-team — the regex excludes). This _HAND_FLOOR producer fired HIGH-confidence
    # (scope 'you') and fed has_other_plan, so a byte-identical
    # _TOKEN_COPY_MATTERS_PLAN_MIRROR below re-supplies the commander-damage voltron
    # silence. The serve spec stays hand-registered in signal_specs.py reusing
    # TOKEN_COPY_MATTERS_REGEX. CR 702.95 / 707.
    # ADR-0027: specialize_matters migrated to the Card IR (served structurally
    # from the Scryfall `specialize` keyword — _IR_KEYWORD_MAP['specialize']
    # below); both its oracle-regex sources (this _HAND_FLOOR detector and the
    # SWEEP_DETECTORS row) are deleted. The keyword survivor is the IR backing.
    # ADR-0027 t2b5-C: villainous_choice migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact "villainous
    # choice" literal). phase routes the keyword action to a GENERIC 'choose' Effect
    # (too broad to key on), so the literal phrase is the only clean discriminator. The
    # Valeyard doubles them; Davros/Missy/Dr. Eggman present them. This _HAND_FLOOR
    # producer is deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027 t2b4a-B: curse_matters (Aura — Curse cares-about) migrated to the Card
    # IR — a trigger/effect subject Filter with subtypes=='Curse' (Lynde, Bitterheart
    # Witch, Witchbane Orb) + a kept word mirror (_IR_KEPT_DETECTORS, byte-identical to
    # this deleted regex) for the under-parsed "search for a Curse card …" tail (Curse
    # of Misfortunes). The membership half (a card that IS a Curse) stays REGEX-ONLY at
    # A4 like TYPE_MATTERS membership. This _HAND_FLOOR producer is deleted; the serve
    # spec stays hand-registered. CR 205.3 / 702.39.
    # ADR-0027: dice_matters migrated to the Card IR — phase's native `roll_die` effect
    # + a `roll_die` marker (project._narrow_trigger_other_refs for the "whenever you
    # roll" payoff trigger + _dropped_static_markers for the "Roll two d6 and choose"
    # spell / "Roll a d8:" cost / "reroll" forms phase keeps only in raw). The
    # structural IR is broader-and-correct recall ("rolls a d20", "Roll X dice", "Roll
    # the planar die", "20-sided die" — Chaos Dragon, Clown Car, Fractured Powerstone,
    # "Name Sticker" Goblin), not over-fire. This _HAND_FLOOR producer is deleted (the
    # SWEEP_DETECTORS row too); the serve spec stays. (CR 706.)
    # ADR-0027: crimes_matter migrated to the Card IR — phase's commit_crime trigger
    # event (_PAYOFF_TRIGGER_KEYS, the "Whenever you commit a crime" trigger form) + a
    # `_CRIME_REF`/`crime` marker for the condition-form payoff phase has no condition
    # kind for ("(if|as long as) you've committed a crime this turn" — Oko, Nimble
    # Brigand, Slickshot Vault-Buster, the Outlaws cost-reducers). Removed from
    # _IR_FLOOR_LANES; serve stays hand-registered. (CR 701.49.)
    # ADR-0027: connive_makers migrated to the Card IR — phase's `connive` effect
    # category (self-conniving cards, _DOER_EFFECT_KEYS) + the `_CONNIVE_REF`
    # applied/granted marker, plus the Scryfall `connive` keyword (_IR_KEYWORD_MAP)
    # which lifts the keyword-less GRANTER phase swallows into an Enchant parse
    # (Security Bypass). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: spell_copy_makers migrated to the Card IR — phase's `spell_copy`
    # effect (CopySpell + CastCopyOfCard) + the storm/replicate/conspire/casualty
    # Scryfall keywords (the HAVERS, _IR_KEYWORD_MAP) + a `_COPY_SPELL_REF` marker for
    # the granted/quoted/conditional copy phase folds into a modal / coin-flip / storm-
    # reminder carrier and the keyword-less GRANTERS ("…spell you cast has replicate/
    # casualty/storm/demonstrate"). The IR EXCLUDES the deleted regex's `\bstorm\b`
    # card-NAME over-fire (Comet Storm, Arrow Storm — burn, not the keyword). Both
    # regex producers (this _HAND_FLOOR + the SWEEP row) are deleted; the serve spec
    # stays hand-registered.
    # ── Effect-axis detectors: every ability is a direction to build around ──────
    # ADR-0027: ramp main mana-production arm migrated to the Card IR. The
    # deleted regex ("{T}: add {" / "add N mana" / "add {WUBRGC}") is now the
    # byte-identical _RAMP_MATTERS_REGEX kept mirror in _signals_ir, paired with a
    # structural `ramp`-category arm gated `not card_is_land` (the recall-GAINING half:
    # +96 nonland ramp doers the brittle anchor missed). See the dork-support note above
    # and _migrated_keys.py for the full residual.
    # ADR-0027: removal migrated to the Card IR — phase's `destroy` / `damage`
    # effect categories with a single-target permanent SUBJECT (CR 115.1), plus the
    # quoted-grant-ability recursion (an Aura/Equipment granting "{T}: Destroy/deal
    # damage to target …" — Manriki-Gusari, Lavamancer's Skill) and the
    # removal-target-subject recovery (Combo Attack, Broken Visage). The mass form
    # ("destroy/deal damage to EACH/ALL …" — DamageAll/DestroyAll, counter_kind=="all")
    # is a BOARD WIPE (CR 115.10), correctly EXCLUDED here and served by mass_removal;
    # the regex over-fired by folding board wipes / land destruction into removal. NOT
    # in _IR_FLOOR_LANES (floor-mirror-dep == 0); this _HAND_FLOOR producer is deleted
    # and the SWEEP_DETECTORS removal row with it; serve stays hand-registered.
    # ADR-0027 exile_removal (SIDECAR v30) migrated to the Card IR — phase's `exile`
    # effect category with a single-target permanent SUBJECT (CR 406.1 one-way exile /
    # 115.1 target), the v30 supplement RETAINING cat=exile + a permanent subject on the
    # rider-swallow / dropped-subject cases (Soul Partition, "Exile", Unexplained
    # Absence). This _HAND_FLOOR producer is deleted (its `exile target … nonland` arm
    # over-fired on GY-hate / recursion — "exile target nonland CARD from a graveyard",
    # Moratorium Stone / Secret Salvage / Shiko — which is NOT battlefield removal; the
    # structural arm excludes a graveyard zone, correctly dropping them). The SWEEP
    # row's broader regex survives as EXILE_REMOVAL_REGEX (the byte-identical kept
    # mirror); the serve spec stays hand-registered. CR 406.1 / 115.1.
    # ADR-0027: counter_control migrated to the Card IR — phase's `counter_spell`
    # effect category plus a `counter_spell` dropped-static face marker for the
    # "counter target … spell/ability" phase loses in a modal mode body (Fangkeeper's
    # Familiar, Ertai Resurrected), a granted/quoted Aura ability (Equinox, Sunken
    # Field), or a non-grant carrier (Goblin Artisans). NOT in _IR_FLOOR_LANES; the
    # serve spec stays hand-registered in signal_specs (FP-free at this breadth).
    # ADR-0027: team_buff migrated to the Card IR — phase's `grant_keyword` Effect (one
    # per granted keyword, the keyword in counter_kind) on a GENERIC "creatures you
    # control" subject (_is_team_buff_grant + _TEAM_BUFF_GRANT_KW). The structural IR
    # drops the regex's tribal / color / attacking / single-target over-fires (it
    # matched the "creatures you control have <kw>" mass_grant roll-up text even when
    # the real grant was tribal/color-scoped); 0 genuine generic anthems lost. NOT in
    # _IR_FLOOR_LANES; this _HAND_FLOOR producer + the SWEEP_DETECTORS team_buff row
    # are deleted; the serve spec stays hand-registered.
    # ADR-0027 reveal/dig-v2: tutor migrated to the Card IR via a BYTE-IDENTICAL
    # kept mirror (_TUTOR_MATTERS_MIRROR in _signals_ir._IR_KEPT_DETECTORS == the
    # deleted
    # TUTOR_MATTERS_REGEX, over reminder-stripped kept_oracle). This _HAND_FLOOR
    # producer
    # is DELETED; the pattern survives as TUTOR_MATTERS_REGEX (below) for the mirror +
    # the
    # has_other_plan voltron silence reuse. The producer fired HIGH-confidence scope
    # 'you' and fed has_other_plan (a tutor engine is a card-advantage plan), so
    # tutor joins _VOLTRON_SILENCING_PLAN_KEYS (the IR re-supply is
    # byte-identical
    # — same 773 cards — so the strict-subset facade is valid). CR 701.23 / 401.
    # ADR-0027 β: untap_engine migrated to the Card IR — this _HAND_FLOOR producer (the
    # "untap target/all/each/two/up to" engine anchor) and the creatures-are-lands
    # producer below are deleted. The lane fires from a refined structural arm in
    # extract_signals_ir (mass untap counter_kind=='all' + raw "untap target/.." + a
    # multi/X-target untap of a permanent type you can control, all gated against the
    # opponent-untap / provoke / single-attach over-fires) PLUS a NARROWED
    # _IR_KEPT_DETECTORS-style mirror for the ~11 engines phase routes into a choose /
    # target_only / cost / type_set carrier. The two producers fired HIGH-confidence
    # (forced scope 'you') and counted toward has_other_plan, so an
    # _UNTAP_ENGINE_PLAN_MIRROR (the byte-identical OR of both deleted regexes over the
    # reminder-stripped joined-face `text`) re-supplies that voltron silence — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (+12 ir_only) and would
    # over-silence those recall-gain bodies. The serve spec (signal_specs.py, a
    # standalone _spec on untap effects) survives. CR 701.16 / 903.10a. ADR-0027 β:
    # gain_control migrated to the Card IR — this _DETECTORS producer (the bare `gain
    # control of` literal, pinned now as GAIN_CONTROL_REGEX in _sweep_detectors) is
    # deleted. The lane fires from a GATED structural arm in extract_signals_ir
    # (cat=='gain_control' excl donate / Owned-return / give-away — a +85 recall-gaining
    # superset that catches the "you control enchanted creature" / "control target
    # player" / "exchange control" theft the bare regex MISSED and drops the
    # you-own-reset / can't-gain-protection / own-recovery over-fires it caught) PLUS a
    # NARROWED _GAIN_CONTROL_MIRROR (the 9 genuine theft phase emits no category for,
    # vetoed per-clause). The deleted producer fired HIGH-confidence (scope 'you') and
    # counted toward has_other_plan, so a _GAIN_CONTROL_PLAN_MIRROR (below) re- supplies
    # the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is
    # BROADER (+85) and the silencing-keys path would over-silence those recall-gain
    # bodies. The LOW-conf `dont_own` cross-open below + the theft_matters sibling are
    # reconciled in signals.py against the MERGED key set. The serve spec (signal_specs)
    # survives. CR 800.4a / 720.1 / 903.10a. ADR-0027: opponent_discard migrated to the
    # Card IR — this _HAND_FLOOR producer (the "(each|target|that) player/opponent
    # discards" hand-attack forcer OR the "opponent discarded a card this turn" /
    # "whenever an opponent discards" payoff) is DELETED. It fires from a structural arm
    # (a `discard` EFFECT scope == "opp", +7 genuine recall) PLUS a byte-identical
    # _OPPONENT_DISCARD_MIRROR kept-mirror in signals._IR_KEPT_DETECTORS (the EXACT
    # deleted regex) for the directed/symmetric forcers phase scopes 'any'/'you' and the
    # "whenever an opponent discards" payoffs phase emits a `discarded` TRIGGER for. The
    # serve spec stays hand-registered in signal_specs.py; the deleted producer fed
    # has_other_plan (HIGH-confidence, scope 'opponents'), so its voltron silence is
    # restored by _OPPONENT_DISCARD_PLAN_MIRROR below. DISJOINT from discard_matters
    # (the SELF-discard `discarded`-TRIGGER scope != 'opp' lane). CR 701.8a / 903.10a.
    # ADR-0027 β: damage_to_opp_matters migrated to the Card IR. This HAND_FLOOR
    # producer (a "whenever ~ deals (noncombat) damage to a PLAYER / opponent"
    # connect-payoff — ANY damage, not the literal "combat damage" the combat_* keys
    # require) is deleted. The lane now fires from a STRUCTURAL IR arm reading project's
    # DamageToPlayer recipient marker (SIDECAR v13 — the player recipient phase keeps on
    # the DamageDone trigger's valid_target but the projected Trigger drops) PLUS a
    # byte-identical kept mirror (_signals_ir) for the granted-ability / ETB-burst /
    # "another player" textual tail phase can't structure as a DamageDone trigger. The
    # IR path is BROADER (+recall: "deals 6 or more damage to an opponent", plural "deal
    # damage to a player", "deals damage to another player" the word-order regex
    # missed), so a byte-identical _DAMAGE_TO_OPP_MATTERS_PLAN_MIRROR below re-supplies
    # the deleted high-confidence producer's voltron silence — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS (that would over-silence the ir_only recall-gain
    # bodies). The exact regex is pinned as DAMAGE_TO_OPP_MATTERS_REGEX
    # (_sweep_detectors), shared by the mirror, the plan-mirror, and the hand-registered
    # serve. Distinct from combat_damage_to_opp (already migrated 42f6d81 — the literal
    # "combat damage to a player" recipient). CR 119.3. ADR-0027: permanent_etb migrated
    # to the Card IR — an `etb` Trigger whose subject Filter carries the 'Permanent'
    # card_type and controller=='you' (Amareth, the canonical card). The structural IR
    # is BROADER-and-correct: it catches the "a/another permanent you control enters"
    # variants the narrow word-order regex missed (Cloudstone Curio, Kodama, Yoshimaru,
    # Builder's Talent). NOT in _IR_FLOOR_LANES; this _HAND_FLOOR producer is deleted;
    # the serve spec stays. ADR-0027: evasion_self migrated to the Card IR. Evasion is a
    # blocking RESTRICTION (CR 509.1b); landwalk (CR 702.14) is conditional
    # unblockable-by-that-land-type evasion, and the keyword-only evasion words
    # (horsemanship 702.31, menace 702.111, fear 702.36, intimidate 702.13, skulk
    # 702.118) carry their "can't be blocked …" only in reminder text (stripped here),
    # so the bare keyword survived (Guan Yu's horsemanship). phase v0.1.19 structures
    # "This creature can't be blocked" only as a GENERIC `restriction` Effect (Slither
    # Blade — shared with stax/"can't block"/tax, too broad to key the lane off), and a
    # true mass CantBeBlockedBy grant becomes a `grant_keyword`(counter_kind
    # "unblockable") — neither is a clean SELF-evasion arm. So the lane rides a
    # BYTE-IDENTICAL kept WORD MIRROR of this EXACT deleted producer
    # (_EVASION_SELF_REGEX, pinned below) run FLAT over the reminder-stripped
    # kept_oracle in _signals_ir._IR_KEPT_DETECTORS — no `[^.]*` arm, so flat ==
    # per-clause. The IR re-supply is BROADER (+36): _IR_KEYWORD_MAP['shadow'] (CR
    # 702.28) credits the Shadow tribes (Dauthi/Soltari/Thalakos) via the precise
    # Scryfall keyword[] array, which the regex deliberately EXCLUDED (shadow collides
    # with card-name self-refs: "Whenever Shadow the Hedgehog…"). Shadow is genuine hard
    # evasion — recall, not over-fire. Commander-legal, floor-disabled, by oracle_id:
    # both==1426, ir_only==36 (all genuine Shadow keyword carriers), regex_only==0.
    # Because the deleted producer fired HIGH-confidence scope 'you' and fed
    # has_other_plan, and the IR re-supply is BROADER, a byte-identical
    # _EVASION_SELF_PLAN_MIRROR (the EXACT deleted regex) restores the voltron silence —
    # NOT _VOLTRON_SILENCING_PLAN_KEYS, which would over-silence the 36 Shadow bodies.
    # The hand-written serve spec (signal_specs.py) survives. CR 509.1b / 702.14 /
    # 702.28. ADR-0027 clone copied-type subject (SIDECAR v30): clone_makers migrated
    # to the Card IR. The supplement now populates the copied-type subject
    # (_copied_type_from_ text on the _CLONE_STATIC / _BECOMES re-tag), so a
    # cat=='clone' STRUCTURAL arm in extract_signals_ir fires clone_makers for the
    # broad "becomes a copy of target creature" family (triggered/activated/sorcery
    # clones — Cytoshape, Oko, Lazav, Sunfrill Imitator's Dinosaur) the narrow ETB-only
    # patterns missed, UNION a byte- identical _CLONE_MATTERS_MIRROR (the COMBINED
    # deleted regex — this _DETECTORS entry plus the SWEEP widen, pinned as
    # CLONE_MATTERS_REGEX) over the reminder-stripped kept_oracle for the 54 cards phase
    # under-structures (Spark Double / Stunt Double / Mockingbird — no clone effect) or
    # that copy a non-creature (Copy Artifact — the regex fired clone_makers regardless
    # of copied type). A token-copy clone ("create a token that's a copy" — Mirror
    # Match) is vetoed in the structural arm (the separate token_copy_makers lane). The
    # two membership cross-opens (the legendary recurring- value engine + the high-CMC
    # ETB/dies clone-TARGET tells) are reproduced in extract_signals_ir's
    # include_membership block (LOW conf, byte-identical). This _DETECTORS entry is
    # deleted; the deleted producer fired HIGH-confidence scope 'you' and fed
    # has_other_plan, so a byte-identical _CLONE_MATTERS_PLAN_MIRROR (below) — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — restores the voltron silence (the IR re-supply is
    # BROADER: +1 Metamorphic Alteration the regex's "card"/"becomes" arms missed). CR
    # 707.1 / 707.2.
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR. This _DETECTORS
    # producer ("put … creature card … onto the battlefield" / "put … onto the
    # battlefield from your hand/library") is DELETED — it OVER-fired on graveyard
    # reanimation ("put target creature card from a graveyard onto the battlefield" —
    # Reanimate, Beacon of Unrest: the source zone the structural arm routes OUT) and
    # MISSED the reveal-until-creature Polymorph family the IR arm recovers. The lane
    # now
    # fires from the STRUCTURAL cat=='cheat_play'+to:battlefield+non-gy-source arm
    # (reading the project._recover_cheat_into_play_source marker, SIDECAR v37) UNION
    # the
    # narrow _CHEAT_INTO_PLAY_RESIDUE_RE mirror in _signals_ir. CR 110.2a / 400.7.
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR — a first-class `bounce`
    # Effect with no graveyard zone tag and a subject not controlled by you (excludes
    # GY-recursion and self-bounce blink). This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec (signal_specs.py, "Bounce / tempo") is independent of this
    # regex and survives.
    # ADR-0027: cascade_matters migrated to the Card IR — the Scryfall `cascade`
    # keyword (_IR_KEYWORD_MAP, the intrinsic cascaders) + a `_CASCADE_GRANT` marker for
    # the keyword-less granters/references ("spells you cast have cascade", "as you
    # cascade", "spell with cascade"). Removed from _IR_FLOOR_LANES; serve hand-spec'd.
    # ADR-0027: regenerate_makers migrated to the Card IR — phase's `regenerate` effect
    # (_DOER_EFFECT_KEYS) + a `_REGENERATE_REF` marker for the granted/quoted/replace
    # regenerate phase drops (Tribal Golem, Mossbridge Troll). Removed from
    # _IR_FLOOR_LANES; serve hand-spec'd.
    # ── Keyword-coverage audit (CR 702/701) keyword[]-anchored avenues ──────────
    # Each fires on a commander/card that bears or cares about the keyword; the matching
    # SPECS entry serves the keyword[] bearers (authoritative) plus the payoff phrasing.
    # Madness (CR 702.35): discard to cast — discard_matters covers only 1/61.
    # ADR-0027: madness_matters migrated to the Card IR — the Scryfall `madness`
    # keyword (_IR_KEYWORD_MAP) + the `_MADNESS_GRANT` "has madness" conferral
    # marker, plus a `madness` payoff marker for the "if it has madness" condition
    # (project._narrow_payoff_condition_refs; Anje Falkenrath's untap loop). Removed
    # from _IR_FLOOR_LANES. The "\bmadness\b" floor over-fired on the "Crown of
    # Madness" ability WORD (CR 207.2c — Bloodboil Sorcerer), which the structural IR
    # correctly excludes. This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: speed_matters migrated to the Card IR — phase's `speed` doer +
    # a "start your engines|max speed|your speed" _IR_KEPT_DETECTORS word mirror (phase
    # v0.1.19 doesn't structure the CR 702.178/702.179 Speed designation; Aetherdrift).
    # Moved floor->kept (floor-mirror-dep -> 0); this _HAND_FLOOR producer is deleted;
    # the serve spec stays hand-registered. ADR-0034 _matters sweep split this by role:
    # the MAKER arms (the `speed` doer + the "Start your engines!" keyword that PERFORM/
    # advance speed) now fire speed_makers; the "Max speed" PAYOFF keeps speed_matters.
    # ADR-0027: discover_makers migrated to the Card IR — served structurally from
    # the Scryfall `discover` keyword (_IR_KEYWORD_MAP, the discover SOURCES) plus a
    # `discover` effect category for the keyword-less re-trigger payoff (Curator of
    # Sun's Creation: "Whenever you discover, discover again" — a trigger phase
    # flattened to event='other', appended by project._narrow_trigger_other_refs and
    # read via _DOER_EFFECT_KEYS). Its oracle-regex floor detector is deleted; the
    # serve spec stays hand-registered in signal_specs.py.
    # Foretell (CR 702.143): the foretold-card payoff/engine axis (Alrund, Ranar).
    # ADR-0027: foretell_matters migrated to the Card IR — the Scryfall `foretell`
    # keyword (_IR_KEYWORD_MAP) + the `_FORETELL_REF` "has foretell"/"you foretell"
    # marker, plus the Foretold-predicate payoff bind (Niko Defies Destiny — a
    # counted subject Filter carrying the Foretold predicate) and a `foretell`
    # marker for the "to foretell" mana ENABLER (Karfell Harbinger,
    # project._narrow_payoff_condition_refs). Removed from _IR_FLOOR_LANES. This
    # _HAND_FLOOR producer is deleted; the serve spec stays in signal_specs.
    # ADR-0027: has_undying_persist migrated to the Card IR — the Scryfall
    # `undying`/`persist` keywords (_IR_KEYWORD_MAP, the intrinsic bearers) + a
    # `_UNDYING_PERSIST_GRANT` marker for the keyword-less GRANTERS ("creatures you
    # control have undying" — Mikaeus, "gains persist until end of turn" — the persist-
    # granters). Removed from _IR_FLOOR_LANES; the "\bundying\b" floor over-fired on the
    # "Undying Flames" card NAME (Epic damage, no undying mechanic), which the
    # structural IR correctly drops. This _HAND_FLOOR producer is deleted; the serve
    # hand-spec stays. (dies_recursion still includes the undying/persist keywords.)
    # ADR-0027: minus_counters_matter migrated to the Card IR — phase's place_counter
    # (counter_kind='m1m1') is the maker (via _COUNTER_KIND_KEYS); the "-1/-1 counter"
    # references (remove / cost / ward / "with a -1/-1 counter on it" / prevention) are
    # the cares-about payoffs phase leaves textual, served from a "-1/-1 counter"
    # _IR_KEPT_DETECTORS word mirror (CR 122 / 702.80 Wither / 702.90 Infect). This
    # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered.
    # ADR-0027: the any-counter HAVE form of plus_one_matters ("permanents/creatures
    # you control with a counter on it" — Xolatoyac, Hidden Hideout, Michelangelo —
    # and "for each <permanent/creature> you control with a counter") migrated to the
    # Card IR: the counters_have_ref marker (project._narrow_counter_refs /
    # _counter_face_marker, "with a counter(s) on it/them" + "+1/+1 counter on
    # creatures you control" anchors) and the count-form payoff (amount.subject with
    # the Counters predicate). This _HAND_FLOOR producer is deleted; the serve spec
    # stays hand-registered.
    # ADR-0027 β: the untap_engine creatures-are-lands producer (Ashaya — "nontoken
    # creatures you control are Forest lands", whose creature-lands untap for mana via a
    # Seedborn/Quirion Ranger engine) is deleted alongside the engine-anchor producer
    # above. It survives byte-identically as _UNTAP_ENGINE_MIRROR_LANDS in the IR kept
    # mirror and in the _UNTAP_ENGINE_PLAN_MIRROR voltron re-supply below. CR 701.16.
    # ADR-0027: cycling_matters migrated to the Card IR — phase's `cycled` trigger +
    # a `cycling_payoff` marker (project._narrow_trigger_other_refs for the "cycle or
    # discard" payoff phase flattens to event='other', + _dropped_static_markers for
    # the cards phase truncates the trigger phrase off entirely). The `cycling_payoff`
    # category is DISTINCT from phase's native `cycling` landcycling doer, so the lane
    # stays payoff-only. This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: kicked_spell_matters migrated to the Card IR — detected from a
    # byte-identical _KICKED_SPELL_MIRROR in signals._IR_KEPT_DETECTORS (the narrow
    # "whenever you cast a kicked spell" payoff / "if (that|it) (spell) was kicked"
    # condition, CR 702.33 Kicker). NOT the bare `\bkicked\b` keyword route — that
    # over-fires +171 on every "if kicked" card; the lane is the PAYOFF/CONDITION, not
    # Kicker presence. This _HAND_FLOOR producer (formerly an _IR_FLOOR_LANE; moved
    # floor->kept, floor-mirror-dep -> 0) is deleted; the hand-written serve spec
    # (signal_specs.py) survives. The producer fired high-confidence scope 'you' and fed
    # has_other_plan, so kicked_spell_matters is added to _VOLTRON_SILENCING_PLAN_KEYS
    # (the IR re-supply is byte-identical, IR == regex == 85, so the silencing-keys path
    # re-silences exactly without over-silence).
    # ADR-0027: colorless_matters migrated to the Card IR — served from the
    # ColorCount:EQ:0 subject-Filter predicate (the "colorless <permanent> you
    # control" / "colorless card" build-arounds — Ancient Stirrings, Vile Aggregate) + a
    # "colorless (creature|spell|permanent)" _IR_KEPT_DETECTORS word mirror for the
    # cost-reduction / cast-restriction refs that aren't a structured subject (CR
    # 702.114). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: exalted_lone_attacker migrated to the Card IR — the Scryfall `exalted`
    # keyword (_IR_KEYWORD_MAP, the bearers) + an "attacks alone|\bexalted\b"
    # _IR_KEPT_DETECTORS word mirror for the attacks-alone payoff triggers + "X have
    # exalted" grants phase leaves textual (CR 702.83). Moved floor->kept (floor-mirror-
    # dep -> 0); this _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027 (q2-D3): flash_matters migrated to the Card IR — the GRANT half binds
    # structurally (extract_signals_ir: an Effect category=='cast_with_keyword' with
    # counter_kind=='flash' — the same node flash_grant reads; Leyline of Anticipation,
    # Vivien Champion of the Wilds, Teferi Mage of Zhalfir). phase folds the ACTIVATED
    # flash-grant (Winding Canyons {2}{T}, Teferi Time Raveler +1) into grant_keyword
    # with an EMPTY counter_kind, and leaves the opponent-turn cast payoff ("whenever
    # you cast a spell during an opponent's turn") textual — so the FULL deleted regex
    # is kept byte-identically as the _IR_KEPT_DETECTORS mirror to recover both forms.
    # The structural arm is broader-and-correct (adds Teferi Mage of Zhalfir, whose
    # "have flash" grant the regex's phrasing missed). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered. CR 702.8.
    # ADR-0027: team_evasion_grant migrated to the Card IR — phase's grant_keyword on a
    # generic creatures-you-control subject (the structural team grant) + a kept word
    # mirror for the subtype/color-scoped grants ("Sliver creatures you control have
    # flying", "Blue creatures you control can't be blocked") the narrow generic gate
    # excludes (CR 702.13/702.14/509). This _HAND_FLOOR producer is deleted; the serve
    # spec stays hand-registered.
    # ADR-0027: lessons_matter migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: \blessons?\b; Lesson is a
    # subtype CR 702.x phase doesn't surface as a payoff tag). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_types=("lesson",)) is independent of this regex and survives.
    # ADR-0027: suspend_matters migrated to the Card IR — served from the Scryfall
    # `suspend` keyword (the bearers, _IR_KEYWORD_MAP) + a kept word mirror
    # (_IR_KEPT_DETECTORS) folding in the SWEEP \bsuspend\b and widening to the whole
    # time-counter superstructure (CR 701.56 time travel, 702.63 Vanishing, Impending,
    # and the cross-pool enablers/payoffs As Foretold, Jhoira, Dust of Moments that
    # manipulate time counters without bearing Suspend). Moved floor->kept (floor-
    # mirror-dep -> 0); this _HAND_FLOOR producer + the SWEEP \bsuspend\b row deleted.
    # ADR-0027: the Casualty (CR 702.153) sacrifice_outlets regex is DELETED with the
    # migration — the printed Casualty keyword now routes via _IR_KEYWORD_MAP and the
    # keyword-LESS granter (Anhelo "has casualty N") via a project grant marker.
    # ADR-0027: saddle_matters migrated to the Card IR — served structurally from
    # phase's `saddle` effect category (_DOER_EFFECT_KEYS; a "becomes saddled" /
    # "you saddle" grant phase folds into an animate/restriction/target_only carrier
    # is appended as a `saddle` marker in project._narrow_mechanic_refs) and the
    # Scryfall `saddle` keyword (_DIRECT_KEYWORD_SIGNALS, a structured field that
    # survives). Its oracle-regex floor detector is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: suspect_matters migrated to the Card IR — phase's `suspect` effect
    # category (_DOER_EFFECT_KEYS, the leading-imperative suspect verb) + a
    # `_SUSPECT_REF` marker for the verb buried mid-clause / in a granted ability and
    # the "suspected" adjective form phase loses (the marker's "(?! counter)" excludes
    # Investigator's Journal's "suspect counter" — a same-named COUNTER type, not the
    # designation, CR 701.60b). Removed from _IR_FLOOR_LANES; serve hand-registered.
    # Power matters (CR 208): a commander whose engine keys on creature POWER — cost
    # reduction by total/greatest power (Ghalta), a power-N-or-greater spell threshold
    # (Goreclaw), or a Ferocious-style "if you control a creature with power N or
    # greater" payoff (Colossal Majesty, Crater's Claws).
    # ADR-0027: power_matters migrated to the Card IR — served from the structural
    # PtComparison:Power:GE/GT predicate read off the board_count / trigger / Condition
    # / amount subject (_predicate_build_around_lanes + _condition_power_matters; the
    # v23 projection fills the operand) PLUS the byte-identical _POWER_MATTERS_MIRROR
    # (the exact deleted regex) over the reminder-stripped kept_oracle for the aggregate
    # "total/greatest power of creatures you control" tail phase folds into an empty-
    # predicate board_count. REMOVED from _IR_FLOOR_LANES; serve stays hand-registered
    # in signal_specs. The deleted producer fed has_other_plan (HIGH, scope 'you'), so
    # the byte-identical _POWER_MATTERS_PLAN_MIRROR (below) re-supplies the voltron
    # silence — the migrated IR is BROADER (+34), so _VOLTRON_SILENCING_PLAN_KEYS would
    # over-silence.
)


_FLOOR_DETECTORS: tuple[Detector, ...] = tuple(
    Detector(key, scope, pattern) for key, pattern, scope in _HAND_FLOOR
) + tuple(
    Detector(d["key"], d["scope"], re.compile(d["regex"], re.IGNORECASE))
    for d in SWEEP_DETECTORS
)


_PER_TURN_ENGINE_RE = re.compile(
    r"at the beginning of (?:your|each)[^.]*"
    r"(?:upkeep|end step|draw step|combat|main phase)"
    r"|(?:once )?(?:each|every) turn"
    # Extra-turn / extra-phase generators (Obeka Splitter of Seconds: "additional upkeep
    # steps"; Najeela / Aurelia / Moraug: "additional combat phase"; "take an extra
    # turn") are PREMIUM recurring-value engines — cloning multiplies the extra phases.
    r"|(?:additional|extra|another) (?:upkeep|combat|main)[^.]{0,8}(?:step|phase)"
    r"|take (?:an? )?(?:extra|additional) turn|an additional turn",
    re.IGNORECASE,
)


_TAP_ABILITY_RE = re.compile(r"\{t\}[^:]*:", re.IGNORECASE)


_MANA_TAP_RE = re.compile(r"\{t\}: add\b", re.IGNORECASE)


_CHEAT_TOP_REVEAL_RE = re.compile(r"reveals? the top card", re.IGNORECASE)


_CHEAT_TOP_ONTO_RE = re.compile(
    r"puts? (?:it|that card|them) onto the battlefield", re.IGNORECASE
)


_REPEATABLE_KILL_RE = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*destroy target creature"
    r"|(?:whenever|at the beginning of)[^.]*destroy target creature",
    re.IGNORECASE,
)


_VOLTRON_KEYWORDS = frozenset(
    {
        "flying",
        "menace",
        "fear",
        "intimidate",
        "shadow",
        "horsemanship",
        "skulk",
        "trample",
        "double strike",
        # Resilience / aggression keywords that make a themeless legend a real
        # commander-damage threat worth suiting up (Konda: indestructible+vigilance).
        "indestructible",
        "hexproof",
        "vigilance",
        "first strike",
        "lifelink",
        "deathtouch",
        "haste",
    }
)


_VOLTRON_COMPAT_KEYS = frozenset({"partner_background", "conditional_self_protection"})


_VOLTRON_HAS_OTHER_PLAN_COMPAT: frozenset[str] = frozenset(
    {
        "regenerate_makers",
        "has_changeling",
        "facedown_makers",
        "self_pump",
        "pump_makers",
        "cant_block_grant",
        # _matters sweep (ADR-0034): the voltron MAKER arm. Attaching/fetching gear
        # IS the voltron plan (load one creature with Equipment/Auras), NOT another
        # plan, so a voltron_makers HIGH must not silence the bare commander-damage
        # fallback. (The old combined arm emitted voltron_matters HIGH here, which
        # equally never silenced its own lane — keeping this compat preserves that.)
        "voltron_makers",
    }
)


_VOLTRON_PLAN_BROADENED: frozenset[str] = frozenset(
    # _matters sweep (ADR-0034): the land-sac population split into the MAKER arm
    # (land_sacrifice_makers — the over-silencers Oblivion Sower / Serendib Djinn /
    # Shivan Wumpus / Argothian Wurm / Foul Spirit all SAC a land, so they emit
    # land_sacrifice_makers now) and the PAYOFF trigger (land_sacrifice_matters).
    # BOTH stay excluded from the generic has_other_plan scan; the byte-identical
    # _BROADENED_PLAN_MIRROR over kept_oracle re-supplies their narrow silence set.
    {"exile_matters", "land_sacrifice_makers", "land_sacrifice_matters"}
)


_BROADENED_PLAN_MIRROR: re.Pattern[str] = re.compile(
    rf"(?:{EXILE_MATTERS_REGEX})|(?:{LAND_SACRIFICE_REGEX})", re.IGNORECASE
)


_IR_FLOOR_LANES: frozenset[str] = frozenset(
    {
        # token-type synergy
        # clue_matters / food_matters / treasure_matters removed — ADR-0027 migrated
        # them to the Card IR (the generalized blood_matters widening: Clue/Food/
        # Treasure-subtype make_token makers incl. the die-roll/vote/choice branch +
        # Aftermath-DFC recovery, a "Sacrifice a Food/Treasure" SAC PAYOFF, and a
        # `token_subtype_ref` "Foods/Treasures you control" cares-about marker). Removed
        # from _IR_FLOOR_LANES; floor-mirror-dep == 0. Their _HAND_FLOOR detectors are
        # deleted; serve specs survive. clue_matters additionally rides the byte-
        # identical _CLUE_MATTERS_MIRROR kept WORD detector (CLUE_MATTERS_REGEX
        # `\bclue\b|\binvestigate\b`) because phase tags the Investigate keyword (->
        # artifacts_matter) but DROPS the Clue subtype off the make_token subject, so
        # the 112 pure-investigate / Clue-payoff cards have no structural form — they
        # survive only on the mirror.
        # blood_matters removed — ADR-0027 migrated it to the Card IR (Blood-subtype
        # makers + the sacrifice-Effect/Trigger subject widening + the choose-list /
        # granted-ability maker recovery), so it fires from the STRUCTURAL IR alone
        # and no longer needs the floor mirror. Its _HAND_FLOOR detector is deleted.
        # counter-type synergy (distinct from the +1/+1 plus_one_matters doer lane)
        # poison_makers / poison_matters removed — ADR-0027 migrated poison to the Card
        # IR (the infect/toxic/poisonous Scryfall keywords + a kept word mirror, split
        # by role under ADR-0034: the GRANTERS / "has toxic" -> poison_makers, the
        # "poison counter" refs -> poison_matters). Moved floor->kept (floor-mirror-dep
        # -> 0); _HAND_FLOOR gone.
        # oil_counter_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # place_counter(counter_kind='oil') placer + an `_OIL_REF` payoff marker for the
        # count-operand/condition phase drops). Its SWEEP_DETECTORS row is deleted.
        "shield_counter_makers",
        # rad_counter_makers removed — ADR-0027 migrated it to the Card IR (the
        # `rad_counter` effect / rad place_counter + a "rad counter(s)" face marker).
        # resource / devotion
        # energy_makers / energy_matters removed — ADR-0027 migrated to the Card IR
        # (phase's `energy` effect = makers + a {e} face marker = matters payoff for
        # the sinks/payoffs/doublers phase loses; ADR-0034 _matters split).
        # devotion_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="devotion" count operand + a "devotion to <color>" kept word
        # mirror for the cost-reduction / counterspell-tax forms phase doesn't make a
        # count operand). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
        # type / tribe / permanent-shape synergy
        # vehicles_matter removed — ADR-0027 migrated it to the Card IR. The broad
        # "Vehicles you control" anthem / crew payoff / Vehicle-GRANTER _HAND_FLOOR
        # producer rides the byte-identical VEHICLES_MATTER_MIRROR kept WORD MIRROR
        # (_IR_KEPT_DETECTORS, the EXACT deleted regex pinned as VEHICLES_MATTER_REGEX
        # in _sweep_detectors); the SEPARATE typed-graveyard-recursion Vehicle arm
        # (Greasefang) is re-supplied PER-CLAUSE via _detect_typed_gy_recursion below.
        # Moved floor->kept (floor-mirror-dep -> 0); voltron re-silenced via
        # _VOLTRON_SILENCING_PLAN_KEYS (byte-identical IR re-supply).
        # CR 301.7 / 702.122.
        # island_matters removed — ADR-0027 migrated it to the Card IR via a byte-
        # identical kept WORD MIRROR (_ISLAND_MATTERS_MIRROR in _IR_KEPT_DETECTORS, the
        # exact deleted `\bislandwalk\b` OR Zhou Yu attack-restriction regex). NOT the
        # Scryfall keyword array: that misses every islandwalk GRANTER / token-maker /
        # reference (the conferred-keyword gap). Moved floor->kept (floor-mirror-dep ->
        # 0); the _HAND_FLOOR producer + the _IR_KEYWORD_MAP['islandwalk'] entry both
        # deleted.
        # legends_matter removed — ADR-0027 migrated it to the Card IR (the
        # HasSupertype:Legendary subject-Filter predicate + a kept word mirror merging
        # both _HAND_FLOOR rows for the cost-reduction / target-legendary / cast-
        # legendary / search refs phase leaves textual). Moved floor->kept (floor-
        # mirror-dep -> 0); both _HAND_FLOOR producers deleted.
        # has_changeling removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # changeling keyword + a "changeling" / "is every creature type" marker). Its
        # SWEEP_DETECTORS row is deleted.
        # colorless_matters / multicolor_matters removed — ADR-0027 migrated them to the
        # Card IR (the ColorCount subject-Filter predicate build-arounds). multicolor
        # keeps an _IR_KEPT_DETECTORS word mirror for the "cast a multicolored spell"
        # trigger; colorless's mirror is DELETED (#24g SIDECAR v56 —
        # supplement._recover_colorless_subject synthesizes a ColorCount:EQ:0 subject
        # Filter for the "colorless spell/creature" cost-reduction / cast-restriction /
        # counter-target refs phase leaves color-blind, so the predicate arm fires
        # structurally). CR 105.2c.
        # lands_matter removed — ADR-0027 migrated it to the Card IR (the
        # amount.subject=Land count operand + a kept word mirror for the "P/T equal to
        # the number of lands you control" / "for each land you control" forms phase
        # emits as characteristic_pt/pump_target but DROPS the count operand). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # superfriends_matters removed — ADR-0027 migrated it to the Card IR (the
        # EXISTING structural arm: a Condition gated on a Planeswalker subject you
        # control — "as long as you control a <Name> planeswalker, …" — that fires on 26
        # commander-legal cards the deleted regex MISSED; PLUS a SUPERFRIENDS_MATTERS_
        # REGEX kept word mirror for the "planeswalkers you control" anthem / "loyalty
        # counter" payoffs / "activate a loyalty ability" engines / "abilities of a
        # planeswalker" copiers phase leaves textual). Moved floor->kept (floor-mirror-
        # dep -> 0; floor-disabled IR-vs-regex residual: both==0, regex_only==149 [all
        # recovered byte-identically by the kept mirror], ir_only==26 [all genuine
        # "control a <Name> planeswalker" payoffs]). _HAND_FLOOR producer deleted;
        # voltron
        # re-silenced via the byte-identical _SUPERFRIENDS_MATTERS_PLAN_MIRROR (BROADER
        # IR re-supply). CR 306 / 606.
        # modified_matters removed — ADR-0027 migrated it to the Card IR via the UNION
        # kept WORD MIRROR (the `\bmodified\b` direct word OR the "power greater than
        # its base power" indirect anchor in _IR_KEPT_DETECTORS, scope 'you', HIGH).
        # phase v0.1.19 doesn't structure "modified" (CR 700.9 — a derived
        # counter/Equipment/Aura union, not a parsed predicate), so the lane rides the
        # EXACT union of the two deleted _HAND_FLOOR producers run FLAT over the
        # reminder-stripped, joined-face kept_oracle. Moved floor->kept (floor-mirror-
        # dep -> 0; floor-disabled IR-vs-regex residual: both==47, regex_only==0,
        # ir_only==0). Both _HAND_FLOOR producers deleted.
        # low_power_matters removed — ADR-0027 migrated it to the Card IR (the
        # Power:LE/LT predicate read + a `_LOW_POWER_REF` marker rebuilding the dropped
        # subject from "creatures you control with power N or less").
        # power_matters removed — ADR-0027 migrated it to the Card IR (the GE/GT twin:
        # the non-dynamic PtComparison:Power:GE/GT predicate read off the board_count /
        # trigger / Condition subject + the amount.subject, plus a byte-identical
        # _POWER_MATTERS_MIRROR for the aggregate "total/greatest power of creatures you
        # control" tail phase emits as an empty-predicate board_count). REMOVED from
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (arm + mirror read no floor).
        # historic_matters removed — ADR-0027 migrated it to the Card IR (the
        # "Historic" subject-Filter predicate). The "\bhistoric\b" word mirror is
        # DELETED (#24g SIDECAR v56 — supplement._recover_historic_subject synthesizes a
        # Historic subject Filter for the historic cast-restriction / cost-reduction /
        # discard-cost refs phase leaves without the qualifier, so the predicate arm
        # fires structurally). CR 700.6 (legendary OR artifact OR Saga).
        # domain_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="domain" count operand + a "\bdomain\b|basic land types" kept word
        # mirror for the cost-reduction / condition / ability-word refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # party_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
        # "full party" CONDITION + "creatures in your party" non-count refs). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # commander_matters removed — ADR-0027 migrated it to the Card IR (the
        # IsCommander subject-Filter predicate + a kept word mirror for the Background
        # grants / "commander damage" / "your commander costs less" refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # mechanic / keyword synergy
        # arcane_matters removed — ADR-0027 migrated it to the Card IR via a BYTE-
        # IDENTICAL kept WORD MIRROR (the `\barcane\b` row in _IR_KEPT_DETECTORS, scope
        # 'you', HIGH conf). phase v0.1.19 doesn't structure Arcane (a SPELL TYPE on
        # Instants/Sorceries — CR 205.3k/304.3/307.3 — not a creature subtype or
        # keyword; the "Spirit or Arcane spell" trigger drops the Arcane qualifier), so
        # the lane rides the EXACT deleted _HAND_FLOOR pattern over the reminder-
        # stripped kept_oracle. Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR
        # row deleted. CR 205.3k / 702.47.
        # Day/Night regex floor removed — ADR-0027 migrated it to the Card IR and
        # ADR-0034 SPLIT it at the emission arm: the daybound/nightbound Scryfall
        # KEYWORD via _IR_KEYWORD_MAP for the 35 transforming werewolves is the PAYOFF
        # arm (keeps daynight_matters), and the `day_night` EFFECT category via
        # _DOER_EFFECT_KEYS for the 12 keyword-less "becomes day/night" / "as long as
        # it's day/night" transition MAKERS + Tovolar's both-arm flip is the MAKER arm
        # (emits daynight_makers; CR 726 Day/Night).
        # phase v0.1.19 structures the transition cleanly, so NO mirror is needed — the
        # two arms reproduce the deleted _HAND_FLOOR regex byte-identically (commander-
        # legal: both==47, ir_only==0, regex_only==0). Moved floor->kept (floor-mirror-
        # dep -> 0); the _HAND_FLOOR producer is deleted. The hand-written serve spec
        # (signal_specs.py) survives.
        # saga_matters removed — ADR-0027 migrated it to the Card IR (a `_SAGA_REF`
        # "lore counter" / "Saga you control" dropped-static face marker; the reminder-
        # stripped anchor excludes a vanilla Saga's intrinsic advancement, mirroring the
        # deleted SWEEP regex). Its SWEEP_DETECTORS row is deleted.
        # initiative_matters removed — ADR-0027 migrated it to the Card IR (a
        # "\bthe initiative\b" _IR_KEPT_DETECTORS word mirror; phase v0.1.19 doesn't
        # structure the CR 720 initiative designation). Moved floor->kept
        # (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # cycling_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `cycled` trigger + a `cycling_payoff` marker for the "cycle or discard" payoff
        # phase flattens to event='other' or truncates the trigger off entirely). Its
        # _HAND_FLOOR detector is deleted.
        # station_matters removed — ADR-0027 migrated it to the Card IR via a BYTE-
        # IDENTICAL kept WORD MIRROR (STATION_MATTERS_REGEX in _IR_KEPT_DETECTORS, scope
        # 'you'; the EOE Station keyword action, CR 702.184). phase v0.1.19 doesn't
        # structure Station for the carriers (bare "Station" + charge-counter accrual in
        # reminder/level text), and the floor-disabled structural `station` effect arm
        # caught only 1 card while missing all 44 regex producers — so the `station`
        # doer entry was REMOVED and the lane rides the byte mirror over reminder-
        # stripped kept_oracle (both==44, regex_only==0, ir_only==0). Moved floor->kept
        # (floor-mirror-dep -> 0); its SWEEP_DETECTORS row is deleted (serve hand-
        # registered).
        # void_warp_matters removed — ADR-0027 migrated it to the Card IR via a
        # byte-identical VOID_WARP_MATTERS_REGEX kept word mirror in _IR_KEPT_DETECTORS
        # (scope 'you'); Void is a CR 207.2c ability word (0 sidecar keywords) and the
        # baked sidecar drops the CR 702.185 Warp keyword on 2 genuine warp cards, so no
        # clean structural arm exists. Moved floor->kept (floor-mirror-dep -> 0); its
        # SWEEP_DETECTORS row is deleted.
        # speed_matters removed — ADR-0027 migrated it to the Card IR (phase's `speed`
        # doer arm + the "Start your engines!"/"Max speed" Scryfall keywords via
        # _IR_KEYWORD_MAP; #24 KW-WAVE-1 retired the "your speed" kept word mirror).
        # Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # stickers_matter removed — ADR-0027 migrated it to the Card IR (a
        # byte-identical STICKERS_MATTER_REGEX `\{tk\}|\bstickers?\b` kept word mirror;
        # phase v0.1.19 doesn't structure the CR 123 sticker / CR 122 ticket-counter
        # mechanic — no structural arm, floor-disabled the IR fires it 0 times). Moved
        # floor->kept
        # (floor-mirror-dep -> 0); its SWEEP_DETECTORS row is deleted (serve stays).
        # attractions_matter removed — ADR-0027 migrated it to the Card IR (a
        # "\battraction\b|open an attraction" kept word mirror; phase v0.1.19 doesn't
        # structure the CR 717 Attraction designation). Moved floor->kept
        # (floor-mirror-dep -> 0); its SWEEP_DETECTORS row is deleted (serve stays).
        # suspect_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `suspect` effect + a verb/"suspected" face marker; the marker's "(?! counter)"
        # excludes Investigator's Journal's "suspect counter" same-named counter type).
        # venture_matters removed — ADR-0027 migrated it to the Card IR (the venture/
        # take-initiative effect + a completedadungeon/isinitiative condition read +
        # a trigger_doubling-over-dungeons read + a venture/complete-a-dungeon marker).
        # foretell_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # foretell keyword + the "has foretell"/"you foretell" marker, plus the
        # Foretold-predicate payoff bind (Niko) and the "to foretell" enabler marker
        # (Karfell)), so it no longer needs the regex floor (its _HAND_FLOOR detector
        # is deleted).
        # phasing_makers removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # phasing keyword + the phase-out/in DOER markers, plus the event='other'
        # "permanents phase out" payoff-trigger marker (The War Doctor)), so it no
        # longer needs the regex floor (its SWEEP_DETECTORS row is deleted).
        # ring_matters removed — ADR-0027 migrated it to the Card IR (structural
        # ring_tempt effect, including the event='other' tempt trigger + the
        # Ring-bearer raw-scan), so it no longer needs the regex floor (its
        # _HAND_FLOOR detector is deleted).
        # convoke_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # convoke keyword + cast_with_keyword counter_kind='convoke' granters +
        # grant_spell_ability/cast-trigger convoke-raw markers), so it no longer needs
        # the regex floor (its SWEEP_DETECTORS row is deleted).
        # affinity_type removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # affinity keyword + an `affinity` marker effect for the conferred "spells you
        # cast have affinity for X" granters), so it no longer needs the regex floor
        # (its SWEEP_DETECTORS row is deleted).
        # cascade_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # cascade keyword + a `_CASCADE_GRANT` conferral/reference marker). Its
        # _HAND_FLOOR detector is deleted.
        # has_undying_persist removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall undying/persist keywords + a `_UNDYING_PERSIST_GRANT` grant marker);
        # the "\bundying\b" floor over-fired on the "Undying Flames" card NAME, which
        # the structural IR correctly drops. Its _HAND_FLOOR detector is deleted.
        # myriad_grant removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # myriad keyword + grant_keyword counter_kind='myriad' granters + a copy-
        # exception conferred marker), so it no longer needs the regex floor (its
        # SWEEP_DETECTORS row is deleted; the "\bmyriad\b" floor over-fired on the
        # "The Myriad Pools" card NAME, which the IR correctly drops).
        # suspend_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # `suspend` keyword + a kept word mirror folding in the SWEEP \bsuspend\b and
        # widening to the time-counter superstructure — time travel / Vanishing /
        # Impending — phase doesn't structure). Moved floor->kept (floor-mirror-dep
        # -> 0); _HAND_FLOOR row + SWEEP_DETECTORS \bsuspend\b row deleted.
        # monarch_matters removed — ADR-0027 migrated it to the Card IR (structural
        # monarch effect + ismonarch condition), so it no longer needs the regex
        # floor (its _HAND_FLOOR detector is deleted).
        # madness_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # madness keyword + the "has madness" grant marker + the "if it has madness"
        # payoff marker (Anje)); the "\bmadness\b" floor over-fired on the "Crown of
        # Madness" ability word (CR 207.2c — Bloodboil Sorcerer), which the structural
        # IR correctly excludes. Its _HAND_FLOOR detector is deleted.
        # dice_matters removed — ADR-0027 migrated it to the Card IR (phase's native
        # roll_die effect + a `roll_die` marker for the "whenever you roll" payoff
        # trigger / "Roll two d6 and choose" spell / "Roll a d8:" cost / "reroll" phase
        # keeps only in raw). Its _HAND_FLOOR + SWEEP_DETECTORS rows are deleted.
        # exalted_lone_attacker removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall `exalted` keyword + an "attacks alone|\bexalted\b" kept word mirror
        # for the attacks-alone payoff triggers + "X have exalted" grants phase leaves
        # textual; CR 702.83). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR
        # row deleted.
        # crimes_matter removed — ADR-0027 migrated it to the Card IR (phase's
        # commit_crime trigger event + a `crime` condition-form marker for the
        # "(if|as long as) you've committed a crime" payoff phase has no kind for).
        # scry_surveil_matters removed — ADR-0027 migrated it to the Card IR (the
        # scried/surveiled trigger events + the event='other' scry/surveil payoff
        # marker, plus the "if you would scry a number of cards" replacement marker
        # (Kenessos, Eligeth)), so it no longer needs the regex floor (its _HAND_FLOOR
        # detector is deleted).
        # regenerate_makers removed — ADR-0027 migrated it to the Card IR (phase's
        # `regenerate` effect + a `_REGENERATE_REF` granted/quoted/replacement marker).
        # Its _HAND_FLOOR detector is deleted.
        # spell-pattern / count payoffs
        # second_spell_matters removed — ADR-0027 migrated it to the Card IR (a
        # byte-identical _SECOND_SPELL_MIRROR in _IR_KEPT_DETECTORS for the "second
        # spell each turn" / Dualcast-discount / Erayo-count trigger phase
        # under-structures — a bare `cast_spell` trigger drops the "second spell"
        # qualifier). Moved floor->kept (floor-mirror-dep -> 0); the _FLOOR_DETECTORS
        # source row is deleted. The hand-written serve spec (signal_specs.py)
        # survives.
        # kicked_spell_matters removed — ADR-0027 migrated it to the Card IR (a
        # byte-identical _KICKED_SPELL_MIRROR in _IR_KEPT_DETECTORS for the "whenever
        # you cast a kicked spell" payoff / "if (that|it) (spell) was kicked"
        # condition, CR 702.33 Kicker). NOT the bare `\bkicked\b` keyword route — that
        # over-fires +171 on every "if kicked" card (the DEFERRED note below); the lane
        # is the PAYOFF/CONDITION, not Kicker presence. Moved floor->kept (floor-mirror-
        # dep -> 0); the _HAND_FLOOR source row is deleted. The hand-written serve spec
        # (signal_specs.py) survives.
        # big_hand_matters removed — ADR-0027 migrated it to the Card IR (the v23
        # `no_max_handsize` Effect structural arm + the byte-identical
        # _BIG_HAND_MATTERS_MIRROR kept word mirror for the "X = cards in your hand"
        # P/T-scaling payoffs / "N or more cards in hand" conditions phase leaves
        # textual — a characteristic_pt Effect carries no in:hand zone). Moved
        # floor->kept (floor-mirror-dep -> 0); both _HAND_FLOOR + SWEEP producers are
        # deleted; the hand-written serve spec (signal_specs.py) survives. CR 402.2.
        # cast_from_exile removed — ADR-0027 migrated it to the Card IR via a
        # BYTE-IDENTICAL kept WORD MIRROR (the CAST_FROM_EXILE_REGEX row in
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf). phase carries NO structural form
        # (it drops the "from exile" zone off the cast_spell trigger AND the self-cast
        # cast_from_zone Effect; the only exile cast-zone it projects —
        # castable_zones=('exile',) — is the foretell-spell serve pool, disjoint from
        # the detector firings), so the lane fires SOLELY from the kept mirror — it no
        # longer needs the regex floor. Its _HAND_FLOOR detector is deleted; the hand-
        # written serve spec (signal_specs.py) is independent and survives. CR 207.2c.
        # exile_matters removed — ADR-0027 migrated it to the Card IR via a
        # BYTE-IDENTICAL kept WORD MIRROR (the EXILE_MATTERS_REGEX row in
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf). phase carries NO structural form
        # (it scatters the exile-zone reference across a `zones=('in:exile',)` count
        # operand, a `Condition(zones=('exile',))`, and a `characteristic_pt` Effect
        # whose count operand drops the zone, with no single category meaning
        # "references cards standing in exile"), so the lane fires SOLELY from the kept
        # mirror — it no longer needs the regex floor (FLOOR→KEPT, floor-mirror-dep ->
        # 0). Its _HAND_FLOOR detector is deleted; the hand-written serve spec
        # (signal_specs.py) is independent and survives. Distinct from exile_removal /
        # cast_from_exile / opponent_exile_matters. CR 406.
        # starting_life_matters removed — ADR-0027 migrated it to the Card IR (a
        # `_STARTING_LIFE_REF` "starting life total" compare marker, CR 103.4). The
        # broad regex over-fired on unrelated life thresholds (Elderscale Wurm,
        # Sigarda's Splendor), which the tight IR marker drops. Its SWEEP row is gone.
        # theft_matters removed — ADR-0027 migrated it to the Card IR via a BYTE-
        # IDENTICAL kept WORD MIRROR (THEFT_MATTERS_REGEX in _IR_KEPT_DETECTORS, scope
        # 'opponents', HIGH conf). phase carries NO structural steal-and-cast form, so
        # the lane fires SOLELY from the kept mirror — it no longer needs the regex
        # floor (its SWEEP_DETECTORS row is deleted; floor 32→31). The 337 LOW-conf
        # cross-opens ride the gain_control sibling facade (signals.py), independent of
        # this producer. CR DD9 (heist) / 613.1b.
        # mass_death_payoff removed — ADR-0027 migrated it to the Card IR (a
        # `_MASS_DEATH_REF` "creatures that died this turn" count-operand marker). Its
        # _HAND_FLOOR detector is deleted.
        # noncombat_damage_payoff removed — ADR-0027 migrated it to the Card IR via a
        # BYTE-IDENTICAL kept WORD MIRROR (the NONCOMBAT_DAMAGE_PAYOFF_REGEX row in
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf). phase v0.1.19 carries NO
        # structural form (no single category flags the CR-702.19a noncombat/combat
        # damage distinction, and the MV-scaling burn arms fold their amount into raw),
        # so the lane fires SOLELY from the kept mirror — it no longer needs the regex
        # floor. FLOOR→KEPT (floor-mirror-dep -> 0): both==92, regex_only==0,
        # ir_only==0. Its SWEEP_DETECTORS row is deleted (floor 20→19); voltron
        # re-silenced via
        # _VOLTRON_SILENCING_PLAN_KEYS (byte-identical IR re-supply). CR 120.1 / 510 /
        # 702.19a.
        # land_sacrifice_matters removed — ADR-0027 migrated it to the Card IR via a
        # BYTE-IDENTICAL kept WORD MIRROR (the LAND_SACRIFICE_REGEX row in
        # _IR_KEPT_DETECTORS, scope 'you', HIGH conf). phase carries NO structural form
        # (the structural sacrifice arm emits this lane on 0 commander-legal cards), so
        # the lane fires SOLELY from the kept mirror — it no longer needs the regex
        # floor. Its _HAND_FLOOR detector is deleted; the hand-written serve spec
        # (signal_specs.py) is independent and survives.
    }
)


_BIG_MANA_REGEX = re.compile(
    r"add \{[^}]*\}\{[^}]*\}|add [^.]*for each|add an additional", re.IGNORECASE
)


_LAND_DESTRUCTION_MIRROR = re.compile(LAND_DESTRUCTION_REGEX, re.IGNORECASE)


_REPEATABLE_KILL_MIRROR = _REPEATABLE_KILL_RE


def _apply_membership_floor(
    card: dict,
    name: str,
    vocab: frozenset[str],
    kept_oracle: str,
    out: list[Signal],
    add: Callable[..., None],
    *,
    is_big_mana: bool,
    is_kill_engine: bool,
    token_maker_subjects: frozenset[str],
) -> None:
    """The card-type / own-subtype MEMBERSHIP floor (what the card IS).

    Extracted from ``extract_signals_ir`` so the ADR-0035 crosswalk can reproduce
    it BYTE-IDENTICALLY (ADR-0035 Stage-3a floor port): one source, zero drift.
    Fires the LOW-confidence "commander cares about X" lanes derived from the own
    card-type (Artifact -> artifacts_matter, Enchantment -> enchantments_matter),
    the own-subtype tribal membership, the token-profile tribal cross-open, and
    the voltron / big-body / kill-engine / clone-target cross-opens. ``add`` /
    ``out`` are the caller's dedup surface (first HIGH structural firing wins the
    ``(key, scope, subject)`` ident); the caller gates the call on
    ``include_membership``.

    ADR-0039 task #80 step 3 (deletion phase): the three structural facts that
    used to be read directly off the OLD projected ``Card`` (``_is_big_mana_ir`` /
    ``_is_kill_engine_ir`` / the ``ir.all_abilities()`` make_token walk) are now
    parameters — each caller computes them off ITS OWN substrate (the legacy
    caller off the old ``Card``, the crosswalk caller off the ``ConceptTree``),
    so this shared function never touches ``old_ir_for`` / the old ``Card`` type
    at all. Keeps the floor's SEMANTICS identical (a re-plumbing, not a
    redesign) — only the read SOURCE moves.
    """
    type_line = (card.get("type_line") or "").lower()
    if "artifact" in type_line:
        add("artifacts_matter", "you", "", "", "low")
    if "enchantment" in type_line:
        add("enchantments_matter", "you", "", "", "low")
    # ADR-0027 — land_destruction BYTE-IDENTICAL membership-gated kept mirror. A
    # CREATURE COMMANDER whose own oracle says "destroy [up to N] target land(s)"
    # (Numot, Goblin Settler, Demonic Hordes — a repeatable LD ENGINE) opens the LD
    # support lane (more LD, own-land recursion to survive symmetric LD, land-loss
    # punishers). Creature + include_membership gated so a one-shot LD SPELL among
    # the 99 (Stone Rain, Armageddon) is NOT read as the deck's plan. This
    # reproduces the deleted extract_signals cross-open EXACTLY (LAND_DESTRUCTION_
    # REGEX over the reminder-stripped kept_oracle — same input as the regex path's
    # reminder-stripped `text`; commander-legal: regex==mirror, 23→23, 0 miss/
    # extra), NOT the broad `destroy`/Land structural arm (removed above — it floods
    # +143 one-shot spells / utility lands HIGH). scope 'you', LOW confidence (the
    # deleted producer's scope/conf — it never fed has_other_plan, so no voltron
    # mirror is needed). CR 305.6.
    if "creature" in type_line and _LAND_DESTRUCTION_MIRROR.search(kept_oracle):
        add("land_destruction", "you", "", "repeatable land destruction", "low")
    # ADR-0027 — big_mana (a COMMANDER that makes a LOT of mana wants X-spell
    # sinks). STRUCTURAL arm: a `ramp` Effect whose v23 amount is amount.factor>1
    # (Sol Ring {C}{C}, Gilded Lotus "three mana", Dark Ritual {B}{B}{B}) OR
    # op=="variable" (a dynamic scaler — Selvala / Gaea's Cradle / Nykthos devotion
    # / Cabal Coffers count). A factor==1 dork (Llanowar — "Add {G}") is exactly ONE
    # mana and is NOT big mana (the v23 magnitude makes them distinguishable; the
    # pre-v23 projection had amount==None). Plus a BYTE-IDENTICAL _BIG_MANA_REGEX
    # kept mirror over kept_oracle for the under-structured "add … for each" tail
    # (Neheb, the Eternal → amount==None). include_membership-gated, scope 'you',
    # LOW conf — reproducing the deleted extract_signals cross-open (which fired LOW
    # and never fed has_other_plan, so no voltron mirror is needed). CR 106.4.
    if is_big_mana or _BIG_MANA_REGEX.search(kept_oracle):
        add("big_mana", "you", "", "big-mana generator", "low")
    # ADR-0027 — cheat_from_top BYTE-IDENTICAL membership-gated kept mirror. A
    # COMMANDER that REVEALS the top card of a library AND cheats the SAME revealed
    # card onto the battlefield (Vaevictis, Hans Eriksson, Lurking Predators) wants
    # to STACK its top with a bomb (graveyard-to-top recursion, put-on-top effects).
    # MIRROR-ONLY: the v24 from:top/to:battlefield zone projection is too COARSE to
    # carry this lane's narrow scope — a structural `from:top` + `to:battlefield`
    # arm over-fires +156 commander-legal (177 vs 24), MERGING the deliberately-
    # separate sibling lanes (87 of the flood already fire cheat_into_play — cheat
    # from library/HAND; 100 fire topdeck_selection — look-at-top SELECTION), AND it
    # MISSES Vaevictis (his reveal folds into a scope-'opp' `choose` carrying no
    # from:top). The whole lane is under-structured relative to the regex phrasing,
    # so it rides the OR-AND of the EXACT deleted _CHEAT_TOP_REVEAL_RE +
    # _CHEAT_TOP_ONTO_RE over the reminder-stripped kept_oracle — same input as the
    # deleted producer's `text` (commander-legal: regex==mirror, 24->24, 0 miss/
    # extra, incl. the DFCs Esper Origins / Jadzi / Nissa — get_oracle_text joins
    # faces). scope 'you', LOW conf (the deleted producer's scope/conf — it never
    # fed has_other_plan, so no voltron mirror is needed, matching the
    # land_destruction / big_mana precedent). CR 401 / 701.20a.
    if _CHEAT_TOP_REVEAL_RE.search(kept_oracle) and _CHEAT_TOP_ONTO_RE.search(
        kept_oracle
    ):
        add("cheat_from_top", "you", "", "reveal-top cheat into play", "low")
    # ADR-0027 — kill_engine (STRUCTURAL repeatable-frame arm + Evil-Twin mirror,
    # membership cross-open). A creature COMMANDER that REPEATABLY destroys a
    # creature (Visara, Diaochan, Royal Assassin, Western Paladin) is a death-
    # engine: each kill fires on-death payoffs. _is_kill_engine_ir READS the frame
    # phase already structures (an activated destroy-creature ability, or a
    # recurring-trigger one — excluding board wipes [counter_kind=='all'] and a one-
    # shot ETB / morph-flip / monstrosity / transform trigger per CR 701.37 / 707 /
    # 701.27), RECOVERING the +48 qualified-creature kills the narrow regex missed
    # (its literal "destroy target creature" skipped "destroy target TAPPED/WHITE/
    # non-Demon creature"). Evil Twin rides the byte-identical
    # _REPEATABLE_KILL_MIRROR over kept_oracle — phase folds its quoted granted
    # ability ("{U}{B}, {T}: Destroy …") into a `clone` Effect with no destroy
    # ability for the arm to read.
    # creature + include_membership gated so a one-shot removal spell in the 99
    # isn't read as the deck's plan. scope 'you', LOW confidence (the deleted
    # producer's identity — it fired LOW and never fed has_other_plan, so NO voltron
    # mirror is needed, matching the land_destruction / cheat_from_top precedent).
    # CR 305.6.
    if "creature" in type_line and (
        is_kill_engine or _REPEATABLE_KILL_MIRROR.search(kept_oracle)
    ):
        add("kill_engine", "you", "", "repeatable creature destruction", "low")
    # ADR-0027 — one_punch (STRUCTURAL ARM, membership audit). An extreme power-
    # for-cost beater (power >= 8 AND power >= 2x its mana value: Lord of
    # Tresserhorn 10/4, Yargle 18/6, The Ancient One 8/8 for 2, Death's Shadow
    # 13/13, Phyrexian Dreadnought 12/12) wins by connecting ONCE for lethal, so it
    # wants damage amplification — grant infect (power -> poison) or double strike
    # (2x). The ratio gate excludes expensive fatties (Emrakul 15/15 for 15) that
    # win by size, not amplification. NOT a regex at all in the deleted producer —
    # a pure numeric gate over the SAME Scryfall fields the IR path already reads
    # (card_pt_int(card) + card['cmc'] + type_line), so this arm reproduces the
    # deleted extract_signals producer BYTE-IDENTICALLY (commander-legal, floor-
    # disabled, by oracle_id: both==23, ir_only==0, regex_only==0; all 23 genuine
    # extreme beaters). include_membership-gated (the huge body is the COMMANDER's
    # plan, not every fatty in the 99). scope 'you', LOW confidence — the deleted
    # producer's identity. It fired AFTER has_other_plan and never fed it (LOW conf,
    # added post-gate), so voltron needs NO mirror / NO _VOLTRON_SILENCING_PLAN_KEYS
    # entry (voltron_matters set unchanged, 3010 -> 3010). NOT in _IR_FLOOR_LANES
    # (floor-mirror-dep == 0: a structural numeric gate, not an oracle floor). CR
    # 903.10a / 702.90 (infect) / 702.4 (double strike).
    if "creature" in type_line:
        power = card_pt_int(card)
        cmc = card.get("cmc") or 0
        if power >= 8 and power >= 2 * cmc:
            add("one_punch", "you", "", "extreme power-for-cost beater", "low")
    # ADR-0027 — keyword_soup_makers BYTE-IDENTICAL membership-gated kept mirror.
    # A keyword-soup commander (Odric Lunarch Marshal, Akroma Vision, Akroma's
    # Memorial/Will, Concerted Effort, Bleeding Effect) GRANTS/SHARES many evergreen
    # keywords across the team, so it wants creatures STACKED with keywords.
    # MIRROR-ONLY: the structural grant_keyword-counter_kind arm (the sibling
    # `keyword_soup` lane's shape) LOSES Akroma's Will — phase splits its modal
    # "Choose one" grants across abilities so neither ability alone reaches >=5 cks
    # — and over-fires onto 11 single-creature keyword-ABSORBERS (Cairn Wanderer,
    # Rayami, Soulflayer, …) that belong to `keyword_soup`, a different archetype.
    # So the lane rides the EXACT deleted producer (the team-grant
    # _KEYWORD_SOUP_CONTEXT_RE AND >=5 distinct evergreen keyword WORDS) flat over
    # the reminder-stripped kept_oracle — same input as the deleted `text`, and with
    # no per-clause `[^.]` span the whole-text count is byte-identical
    # (commander-legal: regex == mirror, 6 -> 6, 0 miss / 0 extra). scope 'you', LOW
    # conf (the deleted producer's identity — it never fed has_other_plan, so no
    # voltron mirror is needed, matching the land_destruction / big_mana /
    # cheat_from_top precedent). NOT in _IR_FLOOR_LANES (floor-mirror-dep == 0).
    # CR 702.
    if (
        _KEYWORD_SOUP_CONTEXT_RE.search(kept_oracle)
        and sum(1 for rx in _EVERGREEN_KW_RE if rx.search(kept_oracle)) >= 5
    ):
        add("keyword_soup_makers", "you", "", kept_oracle[:160], "low")
    # _matters sweep (wants_cloning): the two clone-TARGET membership cross-opens.
    # These are NOT clone DOERS (the structural cat=='clone' arm = clone_makers) —
    # they fire because the COMMANDER itself is a worth-copying target, so a clone
    # deck WANTS to copy it. Strict membership (ADR-0031) keeps them out of
    # clone_makers; this is the separate `wants_cloning` benefit/payoff lane (LOW
    # conf, scope 'you'). include_membership-gated — a property of the commander,
    # not every creature in the 99 (the deck-aggregate path passes False).
    # (1) A LEGENDARY creature whose value is a REPEATABLE engine (a
    # per-turn triggered ability or a non-mana tap-activated ability) is a clone
    # target — copying it forks the engine and the copy dodges the legend rule
    # (Obeka, Koma, Linessa). "legendary" + "creature" (not contiguous) so a
    # Legendary ENCHANTMENT/ARTIFACT/SNOW Creature (Go-Shintai, the gods) qualifies.
    # Matched against `kept_oracle` (the regex path's reminder-stripped `text`,
    # byte-identical). CR 704.5j / 707.1.
    if "legendary" in type_line and "creature" in type_line:
        is_engine = bool(_PER_TURN_ENGINE_RE.search(kept_oracle)) or (
            bool(_TAP_ABILITY_RE.search(kept_oracle))
            and not (_MANA_TAP_RE.search(kept_oracle) and kept_oracle.count("{T}") == 1)
        )
        if is_engine:
            add("wants_cloning", "you", "", kept_oracle[:160], "low")
    # (2) A HIGH-CMC commander (mana value >= 5) with a strong ETB or DEATH trigger
    # is worth COPYING — a clone re-fires the expensive ETB on a cheap body (Gyruda)
    # or the death trigger when the copy dies (Keiga, Kokusho — sac-loop). Reuse the
    # self-ETB / self-dies clauses (the SHORT name Scryfall prints). CR 603.6 /
    # 707.1.
    if (card.get("cmc") or 0) >= 5:
        clone_clause = _self_etb_value(kept_oracle, name) or _self_dies_value(
            kept_oracle, name
        )
        if clone_clause is not None:
            add("wants_cloning", "you", "", clone_clause, "low")
    # ADR-0027 returns_to dimension (SIDECAR v34): blink_flicker migrated. Reproduce
    # the deleted self-ETB-value membership cross-open — a commander with a strong
    # own ETB value (Ephemerate/Cloudshift/Conjurer's Closet fodder) opens the
    # flicker/blink support avenue to RE-USE its own ETB (CR 603.6). Reuses the SAME
    # `_self_etb_value` helper over kept_oracle (the deleted producer's reminder-
    # stripped `text`, byte-identical), LOW conf, scope 'you' — a flicker package is
    # a suggestion, not a detected on-board synergy. It fired LOW and never fed
    # has_other_plan, so it needs no voltron mirror.
    etb_clause = _self_etb_value(kept_oracle, name)
    if etb_clause is not None:
        add("blink_flicker", "you", "", etb_clause, "low")
    # Own-subtype tribal membership (a creature's own race) + named-token
    # tribes — a clean type_line / all_parts field-lookup. Class tribes
    # (Soldier/Cleric) open only behind a go-wide signal; race tribes open
    # unconditionally (CR 205.3).
    keys_now = {s.key for s in out}
    go_wide = bool(keys_now & {"creatures_matter", "attack_matters", "anthem_static"})
    if "creature" in type_line and "—" in type_line:
        for tok in type_line.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in TRIBAL_SUBTYPES or (sub in CLASS_TRIBES and go_wide):
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
    for part in card.get("all_parts") or []:
        if part.get("component") != "token":
            continue
        tl = (part.get("type_line") or "").lower()
        if "creature" not in tl or "—" not in tl:
            continue
        for tok in tl.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in CREATURE_SUBTYPES and sub != "human":
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
    # ADR-0027 — token_maker → type_matters cross-open (the regex
    # `for _sub in _token_maker_subjects: add(TYPE_MATTERS, …)` at
    # _signals_regex.py, now migrated). A commander that MAKES tribe-X creature
    # tokens (a captured make_token kindred subject — Krenko makes Goblins, Darien
    # Soldiers, a "create a 1/1 Human creature token" engine) wants tribe-X
    # lords/support: its token board IS that kindred. UNION: (a) the IR make_token
    # effects via _token_kindred_subject (the per-effect read the token_maker arm
    # uses); (b) a BYTE-IDENTICAL kept mirror — the deleted _detect_token_maker
    # producer per-clause over kept_oracle (the same derivation the regex
    # `_token_maker_subjects` used) — recovers the makers phase folds into a
    # coin_flip / transform / place_counter Effect with no token subject (Bottle
    # of Suleiman → Djinn, Wirefly Hive → Insect, Wedding Announcement → Human).
    # scope 'you', LOW conf. Non-creature token makers (Treasure/Clue) yield no
    # subject and stay out. CR 111.2 / 205.3.
    token_subjects: set[str] = set(token_maker_subjects)
    for clause in _clauses(kept_oracle):
        for _key, sub in _detect_token_maker(clause, vocab):
            if sub:
                token_subjects.add(sub)
    for sub in token_subjects:
        add(signal_keys.TYPE_MATTERS, "you", sub, "", "low")

    # ── Voltron membership (ADR-0027 — the LAST migrated key) ──────────────
    # voltron_matters is a COMMANDER that wants to win via commander damage
    # (CR 903.10a: 21 combat damage from one commander) by loading ONE creature
    # (itself) with Equipment/Auras. It is a COMPOSITION OF STRUCTURAL MECHANICS,
    # all of which now live in the IR — so it migrates here off the regex
    # composite. The ONE sanctioned re-baseline: has_other_plan is now derived
    # from THIS function's own `out` (every plan lane is migrated, so the IR set
    # carries them all high-confidence) instead of the regex path's ~40
    # byte-identical *_PLAN_MIRROR re-supplies. Where the IR lane is BROADER than
    # the deleted regex producer (a self-death / combat-buff / cheat-into-play
    # engine the word-list missed), the broader has_other_plan correctly SILENCES
    # the spurious commander-damage tell on that engine — a more-correct set than
    # the old regex's 3007. The unconditional tells (payoff, self-growth,
    # evasion/resilience, self-protection) fire regardless; only the bare
    # commander-damage fallback is gated on `not has_other_plan`.
    power = card_pt_int(card)
    kws = {k.lower() for k in (card.get("keywords") or [])}
    # (4) self-protection (Power/Evasion/Protection triad; removal is the
    # weakness): an unkillable body that prevents all damage to ITSELF is the
    # ideal Equipment/Aura carrier (Cho-Manno, Gideon Blackblade). Not creature-
    # gated, matching the deleted regex producer. CR 614.9 / 615 / 903.10a.
    if _detect_self_damage_prevention(kept_oracle, name):
        add("voltron_matters", "you", "", kept_oracle[:160], "low")
    if "creature" in type_line:
        # (4) hexproof/indestructible/shroud beater — a removal-resistant body
        # you safely suit up (Sigarda, Uril, Geist of Saint Traft). The single
        # most-distinguishing voltron tell (60% want the package vs 21.6% base).
        # CR 702.11 / 702.12 / 702.18.
        if power >= 2 and kws & {"hexproof", "indestructible", "shroud"}:
            add(
                "voltron_matters",
                "you",
                "",
                "hexproof/indestructible beater",
                "low",
            )
        # (2) the narrower _VOLTRON_EQUIP_RE word tell ("enchanted creature" /
        # "equipped creature" singular / reconfigure / equip {} — the singular
        # payload forms the broad ungated payoff detector above stays off). (1/7)
        # self combat-damage growth loop (_voltron_self_pump — Mirri) and self-
        # targeting heroic suit-up (_voltron_self_heroic — Brigone, Feather; CR
        # 702.83). (3) self-unblockable evasion (Tromokratis). (7) land-scaling
        # threat (Sima Yi), self-recurring threat (Akuta), and double-strike beater
        # (Sabin — doubles every equip/aura bonus, CR 702.4).
        if (
            _VOLTRON_EQUIP_RE.search(kept_oracle)
            or (power >= 2 and _voltron_self_pump(kept_oracle, name))
            or (power >= 4 and _voltron_self_unblockable(kept_oracle, name))
            or _voltron_self_heroic(kept_oracle, name)
            or _voltron_land_scaler(kept_oracle, name)
            or _voltron_self_recurs(kept_oracle, name)
            or _voltron_double_strike_beater(card, kept_oracle)
        ):
            add("voltron_matters", "you", "", "likely voltron commander", "low")
    # has_other_plan (ADR-0027 re-baseline): a high-confidence signal in THIS
    # function's IR `out` for a NON-COMBAT RESOURCE/BOARD ENGINE (card-draw / ramp /
    # tokens / aristocrats / graveyard / tribal-lord / removal-control …) IS another
    # plan — a commander whose primary identity is such an engine is NOT a vanilla
    # voltron beater, so its commander-damage tell is silenced. EXCLUDED are the
    # voltron-COMPATIBLE lanes (_VOLTRON_HAS_OTHER_PLAN_COMPAT): a high-conf signal
    # that is itself a Power/Evasion/Protection tell or a vanilla-body trait does
    # NOT redirect the deck away from the single-big-threat plan, so it must not
    # silence the fallback. Per CR: regeneration (701.19) is removal-resistance — a
    # resilient beater is the IDEAL Equipment carrier; changeling (702.73a) is a
    # vanilla all-creature-type body; morph/facedown (702.37a / 708) is a casting
    # option, not an engine; self power-growth (self_pump / pump_makers) and the
    # evasion-enabling cant_block_grant push the carrier's own damage through (the
    # Power/Evasion legs of the triad). The voltron LOW adds above are LOW (so are
    # skipped); an exalted body's voltron HIGH from the keyword map counts but fired
    # voltron (moot). Background / conditional self-protection stay compat.
    has_other_plan = any(
        s.confidence == "high"
        and s.key not in _GENERIC_KEYS
        and s.key not in _VOLTRON_COMPAT_KEYS
        and s.key not in _VOLTRON_HAS_OTHER_PLAN_COMPAT
        and s.key not in _VOLTRON_PLAN_BROADENED
        for s in out
    ) or bool(_BROADENED_PLAN_MIRROR.search(kept_oracle))
    # (base) commander-damage fallback (CR 903.10a): only when nothing else gave a
    # strong direction and the creature is a real commander-damage threat (an
    # evasion/resilience keyword, or power >= 2 — Isamaru is a 2/2). A 0/1
    # themeless wall is excluded by the power floor.
    if (
        not has_other_plan
        and "creature" in type_line
        and (kws & _VOLTRON_KEYWORDS or power >= 2)
    ):
        add(
            "voltron_matters",
            "you",
            "",
            "commander damage (CR 903.10a)",
            "low",
        )
