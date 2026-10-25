"""Swept detector set — mined exhaustively from real Scryfall oracle text.

Each entry is one ability-axis detector: a structural-anchor regex (validated
against bulk, never authored from memory — ADR-0009), a scope, and is_widen_of
(the existing key it extends, or "" for a brand-new axis). The extractor compiles
these into Detector records (_FLOOR_DETECTORS) and signal_specs auto-registers an
avenue per key.
Regenerate via the exhaustive-residual-sweep workflow. Two clause-scoped baseline
widens (creature_etb, death_matters) are intentionally excluded here — their
originals keep clause scope.
"""

# ruff: noqa: E501 — generated data module of long, bulk-validated regex literals
from __future__ import annotations

# ADR-0027 big_mana migrated to the Card IR (v23 mana-amount projection). big_mana was a
# hand-written include_membership add() in extract_signals (a _LITERAL_ADD_KEYS key), NOT
# a SWEEP_DETECTORS row, so this floor is UNTOUCHED — SWEEP_DETECTORS stays at 34. The
# deleted _BIG_MANA_RE producer survives as the _BIG_MANA_REGEX kept mirror in
# _signals_ir, paired with the v23 structural `ramp`-amount arm (_is_big_mana_ir).
#
# ADR-0027 cheat_from_top migrated to the Card IR (the byte-identical _CHEAT_FROM_TOP_
# MIRROR — the v24 from:top zone is too coarse for a structural arm). cheat_from_top was
# also a hand-written include_membership add() in extract_signals (a _LITERAL_ADD_KEYS
# key), NOT a SWEEP_DETECTORS row, so this floor is UNTOUCHED — SWEEP_DETECTORS stays at
# 33. The deleted producer's _CHEAT_TOP_REVEAL_RE + _CHEAT_TOP_ONTO_RE survive in
# _signals_regex and are reused byte-identically by the membership-gated mirror arm.
#
# ADR-0027 tranche2-C — keyword_counter migrated to the Card IR. Its SWEEP_DETECTORS
# row is deleted (the structural read is place_counter/remove_counter with a CR-122.1b
# keyword counter_kind, in signals.extract_signals_ir). This mined regex survives as a
# shared constant: signals._IR_KEPT_DETECTORS reuses it for the choice/multi/quoted-
# grant tail phase drops counter_kind on ("your choice of a flying or hexproof
# counter"), and signal_specs reuses it for the serve pool — so the two never drift.
KEYWORD_COUNTER_REGEX = "(?:put|with|of an?)[^.]{0,60}?(?:flying|menace|trample|reach|haste|deathtouch|hexproof|indestructible|lifelink|vigilance) counter|enters with (?:a|an|one|two|\\d+)[^.]*?(?:flying|menace|trample|reach|haste|deathtouch|hexproof|indestructible|lifelink|vigilance) counter"

# ADR-0027 — group_hug_draw migrated to the Card IR (the symmetric group-hug draw lane:
# a card that draws for EVERY player — Howling Mine, Wheel of Fortune, Prosperity). Its
# SWEEP_DETECTORS row is deleted; detection moved to a STRUCTURAL arm (a `draw` Effect
# scope=='each', signals.extract_signals_ir) UNION a BYTE-IDENTICAL kept WORD MIRROR
# (this exact regex in signals._IR_KEPT_DETECTORS, scope 'each') for the 4 cards phase
# under-structures (Grothama / Mathise / Vault 11 / Winter Sky fold "each player draws"
# to scope 'any' or emit no draw Effect). This mined regex survives as a shared
# constant.
GROUP_HUG_DRAW_REGEX = "each player (?:may )?draws?\\b|each player who drew"
# ADR-0027 — dies_recursion migrated to the Card IR (SELF-recursion-on-death; CR 700.4
# / 603.6c). Its SWEEP_DETECTORS row is deleted; detection moved to a BYTE-IDENTICAL
# kept WORD MIRROR (this exact regex in signals._IR_KEPT_DETECTORS, scope 'you') — phase
# v0.1.19 carries no structural "returns itself on death" form (the dies trigger
# flattens to event='other' with the return buried in the effect raw). The undying /
# persist keyword BEARERS already open the lane via _IR_KEYWORD_MAP; this mirror recovers
# the bare dies-return grants (Feign Death / Supernatural Stamina) and the keyword-LESS
# GRANTERS (Mikaeus / Cauldron of Souls / Endling). This mined regex survives as a shared
# constant; signal_specs' Dies-recursion sub-avenue serves by it. See the deleted-row
# comment below for the full residual / over-fire adjudication.
DIES_RECURSION_REGEX = "if [^.]* would die, instead exile it with [^.]*counters?|when [^.]* dies, return (?:it|her|him|them) to the battlefield|\\b(?:undying|persist)\\b"
# ADR-0027 — station_matters migrated to the Card IR (the EOE Station keyword action;
# CR 702.184). Its SWEEP_DETECTORS row is deleted; detection moved to a BYTE-IDENTICAL
# kept WORD MIRROR (this exact regex in _signals_ir._IR_KEPT_DETECTORS, scope 'you') —
# phase v0.1.19 doesn't structure Station for the carriers (the bare "Station" keyword +
# its charge-counter accrual live in reminder/level text), so the floor-disabled
# structural `station` effect arm caught only 1 card and missed all 44 regex producers.
# This mined regex survives as a shared constant. See the deleted-row comment below for
# the full residual / over-fire adjudication.
STATION_MATTERS_REGEX = "\\bstation\\b|\\bspacecraft\\b"
# ADR-0027 — flash_grant migrated to the Card IR. The GRANT-to-OTHERS structural form
# binds in extract_signals_ir (a cast_with_keyword{flash} static — "cast <a class of>
# spells as though they had flash"; Vedalken Orrery, Leyline of Anticipation, Teferi,
# Yeva — the 29 commander-legal cards phase parses structurally). phase folds the
# ACTIVATED / conditional flash-grant (Winding Canyons {2}{T}, Emergence Zone, Teferi
# Time Raveler +1) and leaves the "cast this spell as though it had flash" self-flash
# textual, so the FULL deleted SWEEP regex is kept BYTE-IDENTICALLY as the
# _IR_KEPT_DETECTORS mirror (signals._IR_KEPT_DETECTORS) — the union reproduces the
# deleted producer's 81 commander-legal fires EXACTLY (regex_only 0, ir_only 0, scope
# parity 'you'). This mined regex survives as a shared constant so the kept mirror
# reuses it — mirror / (now-deleted) detector never drift. SWEEP_LABELS still carries
# the human label. CR 702.8 (flash).
FLASH_GRANT_REGEX = "as though (?:it|they) (?:had|have) flash|have flash\\b"
# ADR-0027 — stickers_matter migrated to the Card IR (the Unfinity sticker-sheet
# archetype — CR 123 stickers / CR 122 ticket counters: the {TK} ability-sticker costs
# on "Stickers"-type creatures plus the "put a sticker"/"name|art|ability sticker"
# effects and Wicker Picker's "sticker kicker"). Stickers are a niche paper-only
# mechanic phase v0.1.19 doesn't structure (no structural arm — floor-disabled the IR
# fires it 0 times), so the lane MOVES from _IR_FLOOR_LANES to a byte-identical kept
# WORD MIRROR (this exact regex in signals._IR_KEPT_DETECTORS, scope 'you'). The two
# bare alternatives have NO `[^.]*` cross-clause span, so flat-over-kept_oracle ==
# per-clause == the deleted producer's 92 commander-legal fires EXACTLY (both==92,
# ir_only==0, regex_only==0; all 92 genuine sticker cards). This mined regex survives as
# a shared constant so the kept mirror reuses it — mirror / (now-deleted) detector never
# drift. SWEEP_LABELS still carries the human label. CR 123 / 122.1.
STICKERS_MATTER_REGEX = "\\{tk\\}|\\bstickers?\\b"
# ADR-0027 — theft_matters migrated to the Card IR (STEAL an OPPONENT's cards and
# CAST/PLAY them: the impulse-from-opponent steal-and-cast engines, the heist Arena
# keyword action, and the name-strip three-zone rifles). Its SWEEP_DETECTORS row is
# deleted; phase carries NO structural form, so the lane rides a BYTE-IDENTICAL kept
# WORD MIRROR (this exact regex in signals._IR_KEPT_DETECTORS, scope 'opponents') —
# the seven arms' `[^.]*` spans never cross a clause, so flat-over-kept_oracle ==
# per-clause == the deleted producer's 33 commander-legal fires EXACTLY. This mined
# regex survives as a shared constant so the kept mirror reuses it — mirror /
# (now-deleted) detector never drift. SWEEP_LABELS still carries the human label. CR
# DD9 (heist) / 613.1b
# (control-changing effects).
THEFT_MATTERS_REGEX = "conjure a duplicate of[^.]*from an opponent's library|you may (?:play|cast)[^.]*from that player's hand|cast (?:spells )?from (?:that|target) (?:player|opponent)'s hand|play (?:with )?(?:lands and )?(?:spells )?from (?:that|target) (?:player|opponent)'s hand|(?:each player|each opponent|target opponent|that player)[^.]*exiles? cards from the top of their library|search (?:that player|target opponent|an opponent|each opponent)'?s? graveyard, hand,? and library|\\bheist\\b"
# ADR-0027 discard-discarder scope (SIDECAR v26): discard_outlet migrated to the Card IR
# (cost arm + scope in ('you','each') structural arm + a byte-identical PER-CLAUSE
# mirror of this regex). The regex survives as a shared constant so the kept mirror
# (_DISCARD_OUTLET_SWEEP_RE in _signals_regex) reuses it — mirror / (now-deleted)
# detector never drift.
# Its `[^.]*\.?\s*` arms span a sentence over the WHOLE oracle, so the mirror MUST run
# per-clause (matching the deleted SWEEP path), NOT flat. CR 701.8a.
DISCARD_OUTLET_REGEX = "discard (?:a|an|another|two|three|your hand|x|\\d+) [^:.]{0,40}?:|, discard (?:a|an|another|two|three|x|\\d+) cards?:|discard (?:two|three|four|five|x|\\d+) cards? at random|discard all the cards in your hand|discard your hand|discard three cards at random|draw (?:two|three|\\w+|\\d+) cards?[^.]*\\.?\\s*then discard|draw [^.]*cards?,? then discard"
# The named_synergy lane (key SPLIT off the old named_permanent in Task #19): a card
# whose ability references a specific permanent BY NAME for synergy (Festering Newt →
# Bogbrew Witch, Brothers Yamazaki → itself). Detection reads phase's typed ``Named``
# reference to a permanent (``lanes._named_synergy`` over
# ``reads.named_permanent_refs``); this regex is the
# ``named_synergy_parked_reference`` ledger row's match for the clauses phase parks.
# DISTINCT from the COPY_LIMIT lane below: "an ability refers to a named permanent",
# NOT the deck-construction copy-limit relaxation (a copy-limit swarm naming itself
# is copy_limit's alone). The constant keeps its NAMED_PERMANENT name (it matches
# the "permanent named X" shape).
NAMED_PERMANENT_REGEX = "(?:permanent|creature|another permanent) named [A-Z]|a permanent you control named|control a (?:permanent|creature)[^.]*named"
# ADR-0027 dig library-owner scope (SIDECAR v27): dig_until migrated to the Card IR (a
# `dig_until` EFFECT scope=='you' structural arm — the own-library digs project.py now
# scopes from the digger's `player` — UNION a byte-identical PER-CLAUSE mirror of this
# regex for the 44 your-library digs phase re-categorizes to cheat_play/reveal/
# topdeck_stack). The regex survives as a shared constant so the kept mirror
# (_DIG_UNTIL_SWEEP_RE in _signals_regex) reuses it — mirror / (now-deleted) detector
# never drift. Its `[^.]*` arm never
# crosses a clause boundary, but the deleted SWEEP ran PER-CLAUSE over the reminder-
# stripped oracle, so the mirror runs per-clause too. The regex is YOUR-library-anchored
# ("your library" / "you exile"), so it never matched the opponent-library mills the
# structural arm also excludes (scope!='you'). CR 701.23 (search/dig) / 401.
DIG_UNTIL_REGEX = "exile cards? from the top of your library until|exile (?:the )?top[^.]*until you exile|reveal cards from the top of your library until"
# ADR-0027 topdeck library-owner scope (SIDECAR v28): topdeck_selection migrated to the
# Card IR. Detection moves to a `topdeck_select` EFFECT scope=='you' STRUCTURAL arm
# (supplement._topdeck_select_owner_scope scopes the look/reveal + scry/surveil selection
# from the library OWNER — own-library → 'you', opponent peek → 'opp', Morph reveal →
# re-categorized out) UNION a byte-identical PER-CLAUSE mirror of this regex for the 148
# your-library reveals phase re-categorizes to reveal / cast_play (Fact or Fiction, the
# pile cards, cascade/dig bodies). The regex survives as a shared constant so the kept
# mirror (_TOPDECK_SELECTION_SWEEP_RE in _signals_regex) reuses it — mirror /
# (now-deleted) detector never drift. The
# deleted SWEEP ran PER-CLAUSE over the reminder-stripped oracle, so the mirror runs
# per-clause too. The regex is YOUR-library-anchored ("of your library", "from the top of
# your library", "from among them"), so it never matched the opponent-library / opponent-
# hand peeks the structural arm also excludes (scope!='you'). CR 116 / 701.18 / 701.42.
TOPDECK_SELECTION_REGEX = "look at the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal cards from the top of your library until|put [^.]*from among them onto the battlefield"
# ADR-0027 exile_removal (SIDECAR v30): migrated to the Card IR. Detection moves to a
# `cat=="exile"` single-target permanent-removal STRUCTURAL arm (the v30 supplement
# retains cat=exile + a permanent subject on the rider-swallow / dropped-subject cases)
# UNION a byte-identical PER-CLAUSE mirror of this regex (_EXILE_REMOVAL_SWEEP_RE in
# _signals_regex) for the blink/GY-hate over-fires the regex matched + the Drach'Nyen
# ETB-exile-dropped tail (phase carries no structural form — its ETB exile trigger is
# lost entirely). The regex survives as a shared constant so the kept mirror reuses it
# — mirror / (now-deleted) detector never drift. The deleted SWEEP ran PER-CLAUSE over
# the reminder-
# stripped oracle, so the mirror runs per-clause too. CR 406.1 (one-way exile = removal)
# / 115.1 (single target).
EXILE_REMOVAL_REGEX = "exile (?:up to (?:one|two|three|\\w+|x) )?(?:other )?target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)|exile [^.]*and target (?:permanent|creature)"
# ADR-0027 per-clause draw raw (SIDECAR v32): draw_for_each migrated to the Card IR.
# Detection moves to a `draw` EFFECT scaling-count STRUCTURAL arm gated by the draw's
# PER-CLAUSE raw (project.py carries the draw-local clause on `Effect.clause_raw`; the
# arm runs _is_scaling_count over clause_raw, so a fixed draw sharing an ability with a
# for-each cost / damage / life / token rider — Tamiyo's Logbook, Castle Locthwain, the
# Parley draws — no longer fires) UNION a byte-identical PER-CLAUSE mirror of this regex
# (_DRAW_FOR_EACH_SWEEP_RE in _signals_regex) for the cards phase RE-CATEGORIZES off the
# draw effect or leaves textual (Borrowed Knowledge, Curse of Surveillance, Sea Gate
# Restoration — 12 commander-legal regex-only). The regex survives as a shared constant
# so the kept mirror reuses it — mirror / (now-deleted) detector never drift. Its arms
# ("draw … for each"
# / "draw cards equal to the number of") never cross a clause boundary, so the mirror
# runs PER-CLAUSE over the reminder-stripped oracle == the deleted SWEEP path byte-
# identically. The structural arm adds +48 genuine scaling draws the regex missed (a
# counted SUBJECT — "draw cards equal to the greatest power among creatures"; a "where
# X is the number of <type>" count) and drops the ~40 fixed-draw + sibling-rider over-
# fires. CR 107.3.
DRAW_FOR_EACH_REGEX = "draw a card for each|draw cards equal to the number of|draws? (?:a card |cards )?for each"
# ADR-0027: tap_down migrated to the Card IR (the tap-down control lane — tap an
# OPPONENT's permanent / "skips its next untap step" / detain; CR 701.21 detain, CR
# 502.x untap step). Its SWEEP_DETECTORS row is deleted; detection moves to a
# BYTE-IDENTICAL kept WORD MIRROR (this exact regex in signals._IR_KEPT_DETECTORS, scope
# 'opponents'). phase carries a structural `tap` Effect, but only the scope='opp'
# subset — and that subset infers opponent-scope from the COST CONTEXT, not the tap
# TARGET, so it fires on a bare "Tap target creature" whose cost names an opponent
# (Cryptic Cruiser) while MISSING the 89 cards whose tap target IS "an opponent
# controls" but whose phase parse drops the controller predicate (Frost Lynx, Icefall
# Regent, Dungeon Geists, Time of Ice, Kor Hookmaster …). So the structural `tap`/opp
# arm AND the _IR_KEYWORD_MAP['detain'] entry are BOTH removed for this key and replaced
# by this mirror, making the IR re-supply == the deleted producer (the broad
# any-controller target tap stays on the SEPARATE tapper_engine lane, scope 'any', which
# is untouched). The four arms' `[^.]*` span never crosses a clause boundary (the
# splitter cuts on [.;\n]; `[^.]*` excludes `.`, and no `;`/`\n` lands inside a span on
# the corpus), so flat-over-kept_oracle == the deleted per-clause SWEEP firing EXACTLY
# (commander-legal, by oracle_id: both 101, ir_only 0, regex_only 0; scope parity
# 'opponents' on all 101). This mined regex survives as a shared constant so the kept
# mirror reuses it — mirror / (now-deleted) detector never drift. SWEEP_LABELS still
# carries the human label. The
# deleted producer fired HIGH-confidence scope 'opponents' and fed has_other_plan, so the
# byte-identical re-supply adds tap_down to signals._VOLTRON_SILENCING_PLAN_KEYS. CR
# 701.21 / 502.
TAP_DOWN_REGEX = "(?<!un)tap target (?:permanent|creature|land|nonland permanent)[^.]*(?:an opponent|that player) controls|skips? (?:their|his or her|its) next untap step|tap (?:up to )?\\w+ target permanents? (?:an opponent|that player) controls|\\bdetain\\b"
# ADR-0027: topdeck_stack migrated to the Card IR. Its SWEEP_DETECTORS row is deleted;
# detection moves to a STRUCTURAL arm (extract_signals_ir — phase's `topdeck_stack`
# put-into-library Effect, gated counter_kind in {top, topbottom} so the removal-tuck
# `nthfromtop` position and the cleanup `bottom` position both stay out, subject
# controller == "you" so it's YOUR library) PLUS a BYTE-IDENTICAL kept WORD MIRROR (this
# exact regex in signals._IR_KEPT_DETECTORS, scope 'you') for the look-then-stack /
# put-from-hand forms phase doesn't structure (Brainstorm-style "on top in any order",
# Scroll Rack, Diabolic Vision, Munda, Leashling). The two arms never share a `[^.]*`
# span that crosses a clause, so flat-over-kept_oracle == the deleted per-clause SWEEP
# firing EXACTLY (commander-legal, floor-disabled, by oracle_id: mirror == regex == 23).
# This mined regex survives as a shared constant so the kept mirror AND the
# has_other_plan voltron mirror reuse it — mirror / plan-mirror / (now-deleted) detector
# never drift. SWEEP_LABELS still carries the human label. CR 401.4 (library ordering).
TOPDECK_STACK_SWEEP_REGEX = "put (?:two|three|\\w+) cards? from your hand on top of your library|on top of your library in any order"
# The NARROW second producer of combat_damage_to_opp the regex path carried alongside
# the SWEEP row (it lived in _signals_regex, not a SWEEP_DETECTORS row): a double-strike
# grant to your ATTACKING team (Raphael, Blade Historian, Berserkers' Onslaught) makes
# attackers connect with players TWICE — a combat-damage-to-player payoff whose oracle
# never says "deals combat damage to a player". It fired LOW confidence (it does NOT feed
# has_other_plan), and its 3 cards are disjoint from the COMBAT_DAMAGE_TO_OPP_REGEX set,
# so the kept mirror reproduces it as a third byte-identical _IR_KEPT_DETECTORS row (same
# low confidence) to keep the migration loss-free. Pinned here so the mirror reuses it.
COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX = (
    "attacking creatures you control have[^.]*double strike"
)
# ADR-0027 — noncombat_damage_payoff migrated to the Card IR via a BYTE-IDENTICAL kept
# WORD MIRROR (the _IR_KEPT_DETECTORS row, scope 'you', HIGH conf). The lane was an
# _IR_FLOOR_LANES floor reuse (phase v0.1.19 carries no single category for "burn
# outside combat" — its damage Effects don't flag the CR-702.19a noncombat/combat
# distinction, and the MV-scaling burn arms fold their amount into raw), so the lane
# rides this mirror, NOT a structural arm. The lone `[^.]*` arm ("whenever a source
# you control deals [^.]* damage") never crosses a period, so flat over the reminder-
# stripped kept_oracle == the deleted floor Detector's per-clause scan EXACTLY
# (commander-legal, floor-disabled, by oracle_id: both==92, regex_only==0, ir_only==0).
# This mined regex survives as a shared constant so the kept mirror reuses it — mirror
# / (now-deleted) detector never drift. SWEEP_LABELS still carries the human label. CR
# 120.1 / 510 / 702.19a.
NONCOMBAT_DAMAGE_PAYOFF_REGEX = "noncombat damage|deals that much damage to (?:each opponent|any target|that creature)|deals exactly \\d+ damage|whenever (?:a|another) source you control deals [^.]*damage|deals damage equal to (?:that spell's|the exiled card's|that card's|that creature's) mana value"
# ADR-0027 β — cost_reduction migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here (SWEEP_LABELS keeps the human label).
# The lane's firing now comes from the IR arm + _COST_REDUCER_MIRROR (in _signals_ir),
# not this regex.
COST_REDUCTION_REGEX = "spells?[^.]*cost \\{[wubrg]\\}[^.]*less to cast|cost \\{w\\}, \\{u\\}, \\{b\\}, \\{r\\}, or \\{g\\} less|cost \\{[wubrgc\\d]\\}+ less to cast|cost \\{?\\d+\\}? less to activate|(?:cards you drew this turn|abilities you activate)[^.]{0,40}?cost \\{?\\d|costs? \\{?\\d+\\}? less to cast for each|cost \\{?\\d+\\}? less for each"
# ADR-0027 β — keyword_grant_target migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here so the voltron PLAN mirror in
# _signals_regex reuses it (SWEEP_LABELS keeps the human label). The lane's firing now
# comes from the IR arm (the single_target_grant marker in _signals_ir — project._single_target_keyword_
# grant_markers), not this regex.
KEYWORD_GRANT_TARGET_REGEX = "target creature (?:you control )?(?:gains?|gets [+\\-][0-9x]/[+\\-][0-9x] and gains?) (?:deathtouch|trample|flying|menace|vigilance|double strike|first strike|lifelink|haste|hexproof|indestructible|protection|reach|ward|shroud)"
# ADR-0027 β / #24 — pump_makers migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here as a shared constant. The lane (a
# POSITIVE single-target combat-trick buff: "target creature gets +N/+N") now has a
# STRUCTURAL arm — a FIXED positive `pump_target` over a real target-Creature subject
# (the pump-MAGNITUDE field, SIDECAR v42), disjoint from the self_pump firebreather
# (subject None/SelfRef) and the aura/equipment voltron lane (a positive `pump` on an
# EnchantedBy/EquippedBy subject is NOT a `pump_target`). But two classes stay
# un-structurable and ride the RETAINED tail-mirror of this regex: the X-VARIABLE
# "gets +X/+X" (phase drops the dynamic magnitude → amount==None) and the "+N/+N and
# gains <kw>" trick (phase folds it into a subject-None `pump` — indistinguishable
# from a firebreather without phase's per-ability `duration`, a fast-follow). The
# regex (the mirror, the voltron PLAN mirror, and the _PUMP_EXTRA SubAvenue in
# signal_specs all reuse it) is the tail discriminator; add() dedups
# its overlap with the structural arm. SWEEP_LABELS keeps the label. CR 122.1b/613.4c.
PUMP_MATTERS_REGEX = "target (?:[a-z]+ )*creature(?: you control)? gets \\+[0-9x]/\\+[0-9x]|target [A-Z][a-z]+ you control gets \\+|target creature(?: you control)? gets \\+[\\dxX]"

# ADR-0027 Cluster C — base_pt_set migrated to the Card IR. The deleted SWEEP_DETECTORS
# regex was a 4-MECHANIC UMBRELLA: fixed base-P/T set (base_pt_set, CR 613.4b layer 7b) +
# switch P/T (CR 613.4d layer 7d) + "in addition to its types" type-conferral (CR 205.1b)
# + dynamic "equal to X" (variable_pt's CDA territory, CR 613.4a). The migration carves
# out ONLY the fixed base-P/T-set mechanic. Two pins:
#   • BASE_PT_SET_FULL_REGEX — the EXACT deleted umbrella, kept ONLY for the voltron
#     has_other_plan re-supply (the deleted SWEEP detector fired HIGH on all four arms, so
#     a faithful voltron silence must reproduce its full firing set — _base_pt_set_has_plan
#     in _signals_regex; voltron stays 3010 by set equality).
#   • BASE_PT_SET_REGEX — the CARVED base-P/T-set-ONLY arms (drop the two switch arms and
#     narrow the type-conferral arm to require a literal N/N): the SIGNALS kept WORD MIRROR
#     (_BASE_PT_SET_MIRROR in signals._IR_KEPT_DETECTORS, scope 'any') so switch_pt / pure
#     type-conferral are NOT swept into base_pt_set. The
#     structural arm (the SIDECAR v32 SelfBasePt self-transform + the supplement static-
#     parser-failed recovery) supplies the cards phase DROPS the clause for (Bogardan
#     Dragonheart, Answered Prayers, Curse of Conformity); this mirror recovers the dynamic
#     "base power … equal to X" tail phase routes elsewhere (Trench Gorger, Fractalize —
#     variable_pt stays silent on them, so the mirror prevents a recall loss). The carved
#     arms span an `[^.]*` (the type-conferral arm), so the mirror runs PER-CLAUSE over the
#     reminder-stripped kept_oracle == the deleted per-clause SWEEP firing. CR 613.4b.
BASE_PT_SET_FULL_REGEX = "base power (?:and toughness )?\\d|has base power|base toughness \\d|becomes a [^.]*with base power and toughness|becomes a [^.]* in addition to its other types|switch (?:each |target )?creature'?s'? power and toughness|switch [^.]{0,40}power and toughness|base power and toughness of each [^.]*become"
BASE_PT_SET_REGEX = "base power (?:and toughness )?\\d|has base power|base toughness \\d|becomes a [^.]*with base power and toughness|becomes a [^.]*?\\b\\d+/\\d+\\b[^.]* in addition to its other types|base power and toughness of each [^.]*become"

# ADR-0027 Cluster D — protection_grant migrated to the Card IR. The EXACT deleted
# SWEEP_DETECTORS regex, pinned so the byte-identical kept WORD MIRROR
# (PROTECTION_GRANT_REGEX in signals._IR_KEPT_DETECTORS, scope 'you') reuses it. The
# deleted SWEEP ran
# PER-CLAUSE over the reminder-stripped oracle; the two `[^.]*` arms never cross a
# sentence boundary, so a FLAT search over the reminder-stripped joined-face
# kept_oracle == the per-clause SWEEP firing byte-identically (verified 0 flat-only
# / 0 clause-only over the commander-legal corpus). The structural arm is BROADER —
# it adds the single-target indestructible/ward grants, the suit-up auras, and the
# parameterized protection-from-color team grants the word-order regex missed — so the
# mirror is NOT _VOLTRON_SILENCING_PLAN_KEYS; a byte _PROTECTION_GRANT_PLAN_MIRROR
# re-supplies the voltron silence (see signals). CR 702.11/16/12/18/21.
PROTECTION_GRANT_REGEX = "gains? protection from|gains? (?:hexproof|shroud)\\b|target [^.]*gains? protection|can't be the target of (?:spells?|abilities)[^.]*your opponents control"

# ADR-0027 Cluster D — combat_buff_engine migrated to the Card IR (SIGNALS-ONLY). The
# EXACT deleted SWEEP_DETECTORS regex (the per-clause attacks/blocks/begin-combat
# "gets +/-" arms), pinned so the byte-identical kept mirror (run per-clause over
# kept_oracle in extract_signals_ir) and the _combat_buff_engine_has_plan voltron
# re-supply (_signals_regex) both reuse it. The SWEEP ran PER-CLAUSE over the reminder-stripped oracle; the
# `[^.]*` arms never cross a sentence boundary, so the mirror runs per-clause to match
# byte-identically. The structural arm (a triggered ability with Trigger.event in
# {attacks, blocks, begin_combat} + a pump/pump_target/place_counter effect) is BROADER
# — it adds the keyword combat-pumps (Battle cry / Mentor / Exalted / Bushido / Rampage
# / Melee) and "attacks → +1/+1 counter" engines the literal "gets +" regex missed
# (+588 ir_only) — so the mirror is NOT _VOLTRON_SILENCING_PLAN_KEYS; the byte
# _combat_buff_engine_has_plan re-supplies the voltron silence (see signals). CR 508.
COMBAT_BUFF_ENGINE_SWEEP_REGEX = (
    r"at the beginning of combat on your turn[^.]*creature[^.]*\.?\s*"
    r"(?:until end of turn,? )?that creature gets \+"
    r"|whenever (?:this creature|[A-Z][a-z]+) attacks[^.]*(?:creature|it) gets "
    r"\+\d/"
    r"|whenever [\w ]+ blocks(?: or becomes blocked)?[^.]*gets [+\-]"
    r"|whenever [\w ]+ attacks[^.]*,? (?:it|[\w ]+?) gets [+\-]"
)
# ADR-0027 Cluster D (SIDECAR v36) — blocked_matters migrated to the Card IR. The
# EXACT deleted SWEEP_DETECTORS regex, pinned as a shared constant so the byte-
# identical kept WORD MIRROR (signals._IR_KEPT_DETECTORS, scope 'you') reuses it. Two arms: the
# ATTACKER-side textual "whenever … becomes blocked" (CR 509.3c) and the BLOCKER-side
# "whenever <creature> blocks" (CR 509.3a) — the lane historically covered both halves
# of the declare-blockers combat-trigger archetype. The STRUCTURAL becomes_blocked arm
# (_PAYOFF_TRIGGER_KEYS, extract_signals_ir) covers ONLY the attacker payoff (and adds
# the Rampage/Bushido/Flanking/Afflict/Infect keyword reminder triggers this regex
# missed); this mirror recovers the blocker-side "whenever X blocks" half the arm
# deliberately doesn't fold in. The two `[^.]*` arms never cross a sentence boundary,
# so a FLAT search over the reminder-stripped joined-face kept_oracle == the per-clause
# SWEEP firing byte-identically (verified 0 flat-only / 0 clause-only over the
# commander-legal corpus). The structural arm is BROADER (the keyword tail), so the
# mirror is NOT _VOLTRON_SILENCING_PLAN_KEYS; a byte _BLOCKED_MATTERS_PLAN_MIRROR
# re-supplies the voltron silence. CR 509.3c/d / 702.45a / 702.25a / 702.131.
BLOCKED_MATTERS_REGEX = "whenever [^.]*becomes blocked|\\bwhenever \\w[^.]*\\bblocks\\b"

# ADR-0027 — scaling_pump migrated to the Card IR. The EXACT deleted SWEEP_DETECTORS
# regex, pinned as a shared constant so the byte-identical kept WORD MIRROR
# (_SCALING_PUMP_SWEEP_MIRROR in signals._IR_KEPT_DETECTORS, scope 'you') and the voltron
# _SCALING_PUMP_PLAN_MIRROR (_signals_regex) reuse ONE source so they never drift from
# the deleted detector. The
# single arm has no `[^.]*` span, so a flat .search over the reminder-stripped joined-
# face kept_oracle == the deleted per-clause SWEEP firing (commander-legal: flat ==
# per-clause == 223, identical sets). The structural _is_scaling_count arm supplies the
# broader "+X/+X where X is the number/greatest of" + counter-op set the narrow regex
# missed; this mirror recovers the token-/equipment-granted + pump_target-amount-dropped
# tail. CR 613 / 107.3.
SCALING_PUMP_SWEEP_REGEX = "gets [+\\-][0-9x]/[+\\-][0-9x] for (?:each|every)"

# ADR-0027 β — unspent_mana migrated to the Card IR via a kept-mirror; its
# SWEEP_DETECTORS row is deleted but the EXACT mined regex survives here as a shared
# constant. The lane is the "you KEEP unspent mana across steps/phases" payoff — a
# continuous mana-RULE static (CR 500.4 / 106.4). phase DOES carry a structured form
# for the pure statics (a `StepEndUnspentMana` static-ability mode, action `Retain`
# for the "you don't lose unspent <color> mana" cards — Leyline Tyrant, Omnath Locus
# of Mana, Ashling, Electro, Fangorn, Upwelling — or `Transform: <color>` for the
# convert-instead-of-lose cards — Kruphix, Horizon Stone, Omnath Locus of All, Ozai),
# BUT the v17 projection DROPS that static mode entirely (no Effect category exists for
# it), AND every one of those 11 structural cards already matches this regex's "don't
# lose unspent" / "\bunspent mana\b" arms — so a structural arm (a new category + a
# SIDECAR bump) would gain ZERO recall over this mirror. The mana-BURST riders ("Until
# end of turn, you don't lose this mana as steps and phases end" — Savage Ventmaw,
# Avatar Roku, Birgi, Brazen Collector, Sakiko, Rousing Refrain, …) have NO structural
# form: phase buries the retention clause in an Unimplemented(name="lose") sub-ability
# of a `ramp` trigger, so they MUST ride a regex mirror regardless. The regex IS the
# cheapest correct path. The mirror and the voltron PLAN mirror reuse this one constant,
# so detector / silence never drift. SWEEP_LABELS keeps the human label. No arm
# spans a sentence (`.;\n`), so a flat full-text scan over the reminder-stripped oracle
# (the _IR_KEPT_DETECTORS path) reproduces the deleted per-clause SWEEP firing set
# byte-identically. CR 500.4 / 106.4.
UNSPENT_MANA_REGEX = (
    "\\bunspent mana\\b|don't lose unspent|lose unspent mana|\\bmana burn\\b"
    "|loses? (?:one or more )?unspent mana|don't lose (?:this |unspent )?"
    "(?:\\w+ )?mana as (?:steps|phases|those steps)"
)

# ADR-0027 — stax_taxes + symmetric_stax pinned regexes (see the SWEEP_DETECTORS
# stax rows below for the full rationale). STAX_TAXES_REGEX is the byte-exact UNION of
# the three deleted/kept stax_taxes producers — the _signals_regex _DETECTORS pacify
# row (`creatures … can't attack` / `can't attack you`), the _HAND_FLOOR row
# (`opponents can't` / `spells your opponents cast cost` / `creatures your opponents
# control`), and the kept SWEEP row (the long opponent-tax / restriction pattern) —
# so the _STAX_TAXES_MIRROR kept detector (_signals_ir) and the _STAX_TAXES_PLAN_MIRROR
# voltron gate (_signals_regex) share ONE source. SYMMETRIC_STAX_REGEX is the kept
# SWEEP row alone (symmetric_stax had no _signals_regex producer). Run per-clause over
# the reminder-stripped kept_oracle, these reproduce the deleted regex BYTE-IDENTICALLY
# (commander-legal, floor-disabled: stax_taxes mirror==regex==339, symmetric mirror==
# regex==292); the broader structural restriction arm then ADDS the genuine ir_only
# recall. CR 604.1 / 118.9.
STAX_TAXES_REGEX = (
    # _DETECTORS pacify row
    r"creatures? (?:with|you don't control|an opponent controls)[^.]*can't attack"
    r"|can't attack you\b"
    # _HAND_FLOOR row
    r"|\bopponents? can't\b|spells your opponents cast cost"
    r"|creatures your opponents control"
    # kept SWEEP row
    r"|(?:target player|that player|each player|a player|that opponent)"
    r"[^.]{0,90}?can't (?:cast|activate|attack|block|search|untap|draw)"
    r"|must pay \{?\d?\}?[^.]*additional"
    r"|spells?[^.]*cost \{?\d+\}? more to (?:cast|activate)"
    r"|noncreature spells?[^.]*cost(?:s)? \{?\d"
    r"|noncreature spells?[^.]*can't be cast"
    r"|spells? with mana value \d[^.]*can't be cast"
    r"|players? can't cast|that player can't cast spells|spells can't be cast"
    r"|can cast spells only|your opponents control enter(?:s)? tapped"
    r"|nonbasic lands enter(?:s)? tapped|costs? players \{?\d+\}? more"
    r"|doing the chosen action costs"
    r"|players? can't pay life or sacrifice nonland permanents"
)
SYMMETRIC_STAX_REGEX = (
    r"players? can't (?:cast|untap|attack|gain|search their|draw|play|activate)"
    r"|other permanents enter (?:the battlefield )?tapped"
    r"|(?:doesn't|don't|does not) untap during (?:its|their|the)"
)

# ADR-0027 β: token_copy_makers migrated to the Card IR via a kept-mirror — the
# deleted _HAND_FLOOR producer is pinned here byte-identically so the
# _TOKEN_COPY_MATTERS_MIRROR kept detector (_signals_ir) and the
# _TOKEN_COPY_MATTERS_PLAN_MIRROR voltron gate (_signals_regex) share ONE source.
# Matched reminder-STRIPPED: a token-COPY maker / populate / token-DOUBLER payoff.
# The `\bpopulate\b` arm covers CR 702.95 (populate IS a token copy); the "twice that
# many … tokens" arm credits token DOUBLERS (Adrix and Nev, Mondrak — they fork
# token-copy spells). NOT a structural CopyTokenOf/Populate arm: phase structures those
# (421 cards) but the 80-card struct-only delta is 100% reminder-text SELF-copies
# (Embalm/Eternalize/Offspring/Double-team) the reminder-stripped regex excludes.
# CR 702.95 / 707.
TOKEN_COPY_MATTERS_REGEX = "tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|create a token that's a copy|\\bpopulate\\b|twice that many[^.]*tokens?"
# ADR-0027 clone copied-type subject (SIDECAR v30): clone_makers migrated to the Card
# IR. This is the COMBINED deleted regex — the _DETECTORS "becomes a copy" entry UNION
# the deleted SWEEP widen above — pinned byte-identically so the _CLONE_MATTERS_MIRROR
# kept detector (_signals_ir) and the _CLONE_MATTERS_PLAN_MIRROR voltron gate
# (_signals_regex) share ONE source. Matched reminder-STRIPPED: a
# permanent that itself becomes / enters as a copy (CR 707.1) — the structural arm
# (cat=='clone') supplies the broad "becomes a copy of target creature" recall on top,
# this mirror recovers the 54 cards phase under-structures / mis-categorizes / copies a
# non-creature. The two `[^.]*` arms never cross a clause on the commander-legal corpus,
# so flat-over-kept_oracle == the deleted per-clause firing EXACTLY (137 → 137, 0 miss /
# 0 extra). The token-copy phrase ("create a token that's a copy") is deliberately
# EXCLUDED — that's the separate token_copy_makers lane (Dan's clone-vs-token-copy
# boundary). CR 707.1 / 707.2.
CLONE_MATTERS_REGEX = "becomes? a copy of|enters [^.]*as a copy of|enter (?:the battlefield )?as a copy of|may have [^.]*enter as a copy|create a copy of the card|is a copy of (?:that|the chosen) card"

# ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror — the UNION of the
# two deleted _HAND_FLOOR producers is pinned here byte-identically so the
# _TOKENS_MATTER_MIRROR kept detector (_signals_ir) and the _TOKENS_MATTER_PLAN_MIRROR
# voltron gate (_signals_regex) share ONE source.
# Matched reminder-STRIPPED, PER-CLAUSE. Two deleted producers, unioned:
#   (1) the GO-WIDE count-scaler — a creature whose own/granted P/T scales with the
#       creature board ("gets +N/+N for each creature you control"; "power … equal to
#       the number of creatures you control" — Adeline, Leonardo, Bravado, Might of the
#       Masses). Kind-agnostic on purpose (it counts ANY creature, so any creature-token
#       maker pumps it).
#   (2) the broad token PAYOFF — "tokens you control" anthems/refs (Intangible Virtue,
#       Mirror Box, Brudiclad), a "whenever a/one or more/another … token … enters"
#       trigger (Woodland Champion, Junk Winder), and the token DOUBLER replacement
#       ("tokens would be created/put", "create twice that many … token", "twice that
#       many … tokens" — Doubling Season, Parallel Lives, Mondrak, Divine Visitation).
# NOT a structural arm: phase carries NO shape for "tokens you control" / "for each
# creature you control" payoffs (they survive only in raw), and a structural-only
# migration would LOSE 161 commander-legal cards. The amass / fabricate keyword cards
# (59) already fire tokens_matter STRUCTURALLY from the IR (the amass / fabricate
# effect-category fan-out + the moved _IR_KEYWORD_MAP keyword route), so the mirror
# covers ONLY the two _HAND_FLOOR producers; mirror OR IR-structural reproduces the full
# regex firing EXACTLY (commander-legal: regex==hybrid==230, 0 miss, 0 over-fire).
# CR 111.1 / 701.47 (amass) / 702.123 (fabricate).
TOKENS_MATTER_REGEX = "(?:gets? \\+\\d+/\\+\\d+|power (?:and toughness )?(?:is|are) equal to)[^.]*(?:for each (?:other )?creature you control|number of creatures you control)|\\btokens? you control\\b|whenever (?:a|one or more|another)[^.]*?\\btokens?\\b[^.]*?\\benters?\\b|tokens? would be (?:created|put)|create twice that many[^.]*token|twice that many[^.]*tokens?"

# ADR-0027 β: entered_attacker migrated to the Card IR via a byte-identical kept-mirror.
# The deleted _HAND_FLOOR producer is pinned here so the _ENTERED_ATTACKER_MIRROR kept
# detector (_signals_ir) shares ONE source. The lane is the freshly-entered-attacker
# payoff (Samut "if that creature entered this turn, draw a card" on combat damage;
# Redoubled Stormsinger forks tokens that entered this turn on attack; Hixus rewards
# itself having entered this turn when it blocks). The "entered (the battlefield) this
# turn" predicate is NOT projected — it survives only in raw — so there is no structural
# IR shape to read; for ~3 commander-legal cards a byte-identical mirror is the clean
# SIGNALS-ONLY path (regex==mirror, 0 lost, 0 over-fire). The serve spec stays hand-
# registered in signal_specs.py, independent of this regex.
# CR 603.10a (entered this turn) / 506.4 / 509 (attacking creatures).
ENTERED_ATTACKER_REGEX = "(?:deals combat damage|attacks)[^.]*entered (?:the battlefield )?this turn|entered (?:the battlefield )?this turn[^.]*(?:attacks|deals combat damage)"

# ADR-0027: migrated to the Card IR via byte-identical kept-mirrors. The deleted
# _HAND_FLOOR producer is pinned here so the kept detectors (_signals_ir) share ONE
# source. ADR-0034 _matters sweep — SPLIT by role: the original lane fused two
# populations under one regex's two alternations.
#  * ISLAND_MAKERS_REGEX (`\bislandwalk\b`) — the islandwalk DOER/HAS side: islandwalk
#    BEARERS (Thada Adel, Wrexial), GRANTERS / token-makers (Lord of Atlantis,
#    Master of the Pearl Trident, Fishliver Oil, Chasm Skulker), and islandwalk
#    references (Mystic Decree, Merfolk Assassin). Emits `island_makers`.
#  * ISLAND_MATTERS_REGEX (the Zhou Yu "can't attack unless defending player controls
#    an Island" restriction) — the cares-about-Islands PAYOFF side: a card that wants
#    the defender to control an Island. Emits `island_matters`.
# Splitting at the alternation IS the maker/payoff split (each old member matched
# exactly one alternation → union is set-equal; gate: both==79, makers>0, keep>0).
# NOT the Scryfall `islandwalk` keyword array: that lists only the keyword the card HAS,
# missing every GRANTER (the conferred-keyword gap). Neither pattern carries a `[^.]*`
# span, so a flat scan over the reminder-stripped oracle == the deleted floor Detector's
# per-clause scan. The serve specs stay hand-registered in signal_specs.py. CR 702.14c
# (islandwalk evasion) / 702.14b (landwalk is an evasion ability).
ISLAND_MAKERS_REGEX = "\\bislandwalk\\b"
ISLAND_MATTERS_REGEX = "can'?t attack unless defending player controls an island"

# ADR-0027: vehicles_matter migrated to the Card IR via a byte-identical kept WORD
# MIRROR (the EXACT deleted _HAND_FLOOR producer, scope 'you', pinned here so the
# VEHICLES_MATTER_MIRROR kept detector in _signals_ir and the
# _VEHICLES_MATTER_PLAN_MIRROR voltron gate share ONE source). phase v0.1.19 carries
# NO clean structural shape for "Vehicles you control" anthems / crew payoffs / the
# Vehicle GRANTER ("becomes a Vehicle … gains crew") — Crew (CR 702.122) and the
# Vehicle artifact subtype (CR 301.7) are not parsed predicates — so the lane rides
# the deleted regex. The `whenever[^.]*crews?` and `create [^.]*vehicle artifact
# token` arms are `[^.]`-bounded inside a clause, so a flat scan over the reminder-
# stripped joined-face kept_oracle == the deleted floor Detector's per-clause scan
# (verified: both==41, ir_only==0, regex_only==0 over the commander-legal corpus).
# The serve spec stays hand-registered in signal_specs.py, independent of this regex.
VEHICLES_MATTER_REGEX = (
    r"\bvehicles you control\b|\bmounts? and vehicles?\b"
    r"|\bvehicle you control enters\b|\bcrews a vehicle\b"
    r"|\bwhenever[^.]*\bcrews?\b"
    r"|\b(?:mount|equipment) or vehicle (?:card|spell)\b"
    r"|\bvehicle or artifact (?:creature )?(?:card|spell)\b"
    r"|create [^.]*\bvehicle artifact (?:creature )?token\b"
    r"|\bbecomes? a vehicle\b|\bgains? crew\b"
)

# ADR-0027 β: color_change migrated to the Card IR via a byte-identical kept-mirror —
# the deleted SWEEP producer is pinned here so the _COLOR_CHANGE_MIRROR kept detector
# (_signals_ir) and the _COLOR_CHANGE_PLAN_MIRROR voltron gate (_signals_regex) share
# ONE source. NOT a structural arm: phase parses the clause INCONSISTENTLY (20 cards as
# a deeply-nested AddChosenColor modification under a Choose sub_ability/GenericEffect,
# 4 as a bare Unimplemented "become" — Mondo Gecko/Scrapbasket/Tam/Wild Mongrel), and
# the projection re-categorizes them inconsistently as animate/restriction/grant_keyword
# /choose. The only structural anchor — cat=='animate' — fires on 256 commander-legal
# cards (man-lands, animate-land anthems) vs the 24 genuine color-changers, a ~90%
# over-fire. The deleted oracle regex is precise (24/24 genuine, 0 over-fire), so the
# lane rides it byte-identically. CR 105 / 613 (color is a continuously-checked layer-5
# characteristic). The serve spec stays hand-registered in signal_specs.py, independent
# of this detector.
COLOR_CHANGE_REGEX = (
    "becomes the color of your choice|becomes? (?:the color|all colors)"
)


# ADR-0027 β: gain_control migrated to the Card IR. The deleted _DETECTORS producer (an
# inline `gain control of` literal in _signals_regex, NOT a SWEEP row) is pinned here so
# the NARROWED _GAIN_CONTROL_MIRROR kept detector (_signals_ir) and the
# _GAIN_CONTROL_PLAN_MIRROR voltron gate (_signals_regex) share ONE source. UNLIKE the
# byte-identical color_change/toughness_combat re-homes, gain_control rides a recall-
# GAINING structural arm (cat=='gain_control' excl donate / Owned-return / give-away):
# +85 commander-legal theft cards the bare regex MISSED ("you control enchanted creature"
# Auras — Control Magic / Mind Control / Confiscate / Enslave / Treachery; "control
# target player" — Mindslaver / Worst Fears; "exchange control" — Political Trickery /
# Juxtapose), while DROPPING 4 the bare regex over-fired (a you-own reset — Gruul Charm /
# Brand; a can't-gain protection — Guardian Beast; an own-recovery — Coveted Falcon). The
# 9 genuine theft cards phase emits NO gain_control category for (Seize the Spotlight,
# Power of Persuasion, Invert Polarity, Wake the Dragon, Expropriate, Midnight Crusader
# Shuttle, Captivating Glance, Herald of Leshrac, Risky Move) ride the narrowed mirror
# (this regex run PER-CLAUSE, vetoed per-clause by those same 3 over-fire forms). CR
# 800.4a / 720.1 (one player controls a permanent at a time). The serve spec stays
# hand-registered in signal_specs.py, independent of this detector.
GAIN_CONTROL_REGEX = "gain control of"

# ADR-0027 C14 — the NARROWED toughness-as-VALUE residue mirror. The combat-REDIRECT
# alternative ("assigns combat damage equal to its toughness rather than its power") is
# now read STRUCTURALLY (phase's AssignDamageFromToughness modification → combat_damage_
# mod / counter_kind=='from_toughness'), and the clean value cards phase routes through a
# {type:Toughness} Ref / Aggregate operand fire structurally via Quantity op=='toughness'
# (Angelic Chorus gain_life, Last March draw). This mirror covers ONLY the measured
# residue: the toughness-as-value cards phase routes through OTHER projection paths it
# folds to a fixed/None operand — a token's P/T (Geralf, Kin-Tree Invocation, Soul
# Separator, Sutured Ghoul), a -X/-X or +X/+X pump-X (Tip the Scales, Freelance Muscle,
# Snowblind), mana = toughness (Vhal, Arbor Adherent), cost = total toughness (The Pride
# of Hull Clade), discover/discover-X (Pantlaza). The dedicated combat-redirect + the
# vestigial mana-value alternatives are dropped; the `equal to … toughness` arm still
# incidentally matches the redirect phrase, but those fire structurally and the mirror is
# a harmless dedup backstop. Both value arms are clause-local. CR 119.3 / 604.3.
# A base-P/T COPY ("base power and toughness become equal to that creature's power
# and toughness" — Shape Stealer, Halfdane; the v0.94.0 Oracle wording) is a layer-7b
# set (CR 613.4b), not toughness read as a value, so "become(s) equal to … toughness"
# is excluded whole. A lone "base toughness becomes equal to …" is the same 7b set
# (Ambassador Blorpityblorpboop, the only such card at v0.94.0), so no
# "becomes equal to" form stays.
TOUGHNESS_VALUE_REGEX = (
    r"deals damage equal to its toughness"
    r"|\bx (?:is|equals?) [^.]{0,40}\btoughness\b"
    r"|(?<!\bbecome )(?<!\bbecomes )equal to [^.]{0,40}\btoughness\b(?! are each)"
)

# ADR-0027 β — damage_to_opp_matters migrated to the Card IR. The exact deleted
# _DETECTORS regex (a "whenever ~ deals (noncombat) damage to a PLAYER / opponent"
# connect-payoff — ANY damage, NOT the literal "combat damage" the combat_* keys
# require, per the rules-lawyer audit: the connect-trigger axis for self-source
# pingers / evasion the tribe/combat keys miss). Pinned here as a shared constant so
# signals._IR_KEPT_DETECTORS reuses it for the kept mirror (the granted-ability / ETB-
# burst tail phase can't structure as a DamageDone trigger) and the voltron PLAN mirror
# in _signals_regex reuses it — so mirror / silence never drift. The structural projection (SIDECAR v13's
# DamageToPlayer recipient marker) fires the lane on the phase-typed DamageDone
# triggers; this regex covers the textual tail. CR 119.3 / 510.1c.
DAMAGE_TO_OPP_MATTERS_REGEX = (
    r"\bwhen(?:ever)?\b[^.]*?\bdeals (?:noncombat )?damage to "
    r"(?:a player|an opponent|one of your opponents|each opponent"
    r"|target opponent|that player|a player or planeswalker)\b"
)

# ADR-0027 β — damage_redirect migrated to the Card IR via two byte-identical kept
# mirrors (signals-only, NO sidecar bump). The lane has two DISJOINT arms (corpus
# overlap == 0):
#   ARM B (this regex) — a REDIRECT clause ("the next N damage … would be dealt …
#     dealt to <X> instead", "that damage is dealt to ~ instead", "deal that damage to
#     ~ instead": Pariah/en-Kor redirectors, Reflect Damage, Nova Pentacle, Captain's
#     Maneuver — 25 commander-legal, 25/25 genuine). phase DOES carry a category, but
#     INCONSISTENTLY (redirect / damage_replace / damage_replacement), and the union of
#     those three categories fires on 224 commander-legal cards vs the 25 genuine
#     redirectors — a ~90% OVER-FIRE (every burn spell phase loosely types as
#     damage_replacement: Lava Coil, Anger of the Gods). So the lane rides this exact
#     deleted SWEEP regex byte-identically (_DAMAGE_REDIRECT_MIRROR in _signals_ir).
#   ARM A (signals._detect_self_damage_prevention, NAME-AWARE) — a self-PREVENTION /
#     self-redirect tell ("prevent all damage that would be dealt to <self>", "if
#     damage would be dealt to <self>": Cho-Manno, Phyrexian Vindicator, Phantom cycle,
#     Gideon Blackblade — 44 commander-legal, 44/44 genuine). phase's
#     cat=='damage_prevention' fires on 396 cards (every fog / Circle of Protection /
#     Samite Healer) vs the 44 self-prevent tells — a ~90% OVER-FIRE with no recipient
#     / self filter. ARM A is name-aware (self-only, the unkillable Pariah carrier), so
#     it rides the EXACT production helper inline in extract_signals_ir (the self_blink
#     name-aware precedent), NOT a static SWEEP regex.
# This SWEEP_DETECTORS row is deleted; the EXACT ARM B regex is pinned here so the
# _DAMAGE_REDIRECT_MIRROR kept detector (_signals_ir) and the _DAMAGE_REDIRECT_PLAN_
# MIRROR voltron gate (_signals_regex) share ONE source; SWEEP_LABELS keeps the human
# label; the serve stays hand-registered in signal_specs.py. CR 614.9 (redirection
# replacement) / 615 (prevention).
DAMAGE_REDIRECT_REGEX = (
    "the next (?:\\d+|x) damage [^.]*would be dealt[^.]*(?:is )?dealt to [^.]*instead"
    "|that damage is dealt to [^.]*instead|deal that damage to [^.]*instead"
)

# ADR-0027: damage_prevention's EXACT deleted SWEEP regex, pinned so ONE source feeds
# the _DAMAGE_PREVENTION_MIRROR kept detector (_signals_ir, recovering the 88 cards
# phase's effect category doesn't structure) AND the _DAMAGE_PREVENTION_PLAN_MIRROR
# voltron gate (_signals_regex). Every arm uses `[^.]*` (never crosses a period), so a
# flat scan over the reminder-stripped kept_oracle == the deleted per-clause SWEEP
# firing set BYTE-IDENTICALLY (466==466, 0 mismatch over commander-legal). CR 615.
DAMAGE_PREVENTION_REGEX = (
    "prevent the next (?:\\d+|x) damage"
    "|prevent (?:all|the next \\d+|x|all combat|all but \\d+|that) [^.]*damage"
    "|prevent that damage|prevent all damage"
    "|prevent [^.]*damage that would be dealt"
)

# ADR-0027 β: free_cast migrated to the Card IR via a byte-identical kept-mirror
# (_FREE_CAST_MIRROR in _signals_ir). The SWEEP_DETECTORS row is deleted; the EXACT
# regex is pinned here, reused by the IR mirror and the has_other_plan plan-mirror.
# SWEEP_LABELS keeps the label.
FREE_CAST_REGEX = "rather than pay (?:its|their|the) mana cost|without paying (?:its|their) mana cost|may cast (?:it|that (?:card|spell)|those cards)[^.]*without paying"

# ADR-0027: death_matters (the ARISTOCRATS payoff — OTHER creatures dying as a
# resource, CR 700.4: "dies" = battlefield→graveyard) migrated to the Card IR via a
# BYTE-IDENTICAL kept-mirror (_DEATH_MATTERS_MIRROR + the two substring-AND branches in
# _signals_ir). The two deleted producers (the clause-scoped _DETECTORS lambda and the
# "died this turn" _HAND_FLOOR regex) had no single structural shape: phase's `dies`
# TRIGGER (project @ SIDECAR v11 — battlefield→graveyard, the disjoint complement of the
# broader `leaves` event ltb_matters reads) covers only the "whenever a creature dies"
# TRIGGER form, but the dominant family is the MORBID "if a creature died this turn"
# CONDITION (104 cards — Bone Picker, Reaper from the Abyss, Bontu), which is NO trigger
# at all, plus conferred / "until end of turn" / quoted dies triggers phase leaves
# textual (Necrosynthesis, Relic Vial, Massacre Girl) and the death-trigger DOUBLERS
# (Teysa Karlov, Drivnod). So the lane rides this byte-identical regex (commander-legal
# corpus: regex==mirror, 0 lost, 0 over-fire) run PER-CLAUSE. The STRUCTURAL `dies`-
# trigger arm in extract_signals_ir adds +90 ir_only recall (the verbose "is put into a
# graveyard from the battlefield" payoffs — Field of Souls, Dingus Egg, Sarulf — the
# literal-"dies" regex MISSED), add()-deduped with the mirror. The regex-expressible
# branches are pinned here (reused by the IR mirror and the has_other_plan
# _DEATH_MATTERS_PLAN_MIRROR); the mirror ALSO runs
# the two substring-AND branches ("whenever"&"dies", "dying"&"trigger") the deleted
# lambda did, which no single regex expresses. NO SWEEP row (death_matters was a clause-
# scoped baseline widen, never swept). NO sidecar bump (the v11 projection already emits
# the `dies` trigger event). CR 700.4 / 603.6e (dies ⊂ leaves the battlefield).
DEATH_MATTERS_REGEX = (
    r"whenever [^.]*(?:creatures?|permanents?|tokens?|they|control) die\b"
    r"|creatures? (?:that )?died this turn"
    r"|creature[^.]*\bdied\b[^.]*this turn"
)
# ADR-0027 — artifacts_matter / enchantments_matter migrated to the Card IR; the
# per-clause text mirrors that rode beside the structural arms (the deleted oracle
# producers' ARTIFACTS_MATTER_REGEX / ENCHANTMENTS_MATTER_REGEX / the enchantment-cast
# idiom) were retired 2026-10-24 for typed reads of every population filter over your
# artifacts / enchantments (``lanes.board_and_ramp._artifacts_enchantments_matter``).
# ADR-0027 — landfall (the LAND-ETB payoff axis: a card that CARES when a land
# enters — the "Landfall —" ability word (CR 207.2c), the keyword-LESS "whenever a
# land you control enters" trigger, the extra-land STATIC ("play N additional
# lands" — Azusa, Dryad of the Ilysian Grove), and land RECURSION from the graveyard
# (Crucible of Worlds, Splendid Reclamation, Titania) that replays lands for repeat
# landfall) migrated to the Card IR via a STRUCTURAL arm + a BYTE-IDENTICAL
# kept-mirror. The structural `etb`-trigger arm (a Trigger whose subject is a Land)
# in extract_signals_ir ADDS +5 ir_only recall: the DISJUNCTIVE / qualified
# land-ETB triggers the bare "whenever a land" substring MISSED — "this land or
# another land you control enters" (Field of the Dead), "a land you control enters
# from exile" (Faldorn), "a nonbasic land an opponent controls enters" (Spectrum
# Sentinel), "one or more lands enter under an opponent's control" (Deep Gnome
# Terramancer), and the transform-on-land-ETB (Twists and Turns) — all genuine
# land-ETB payoffs. But phase carries NO structural shape for the OTHER three
# branches of the deleted producer: the "Landfall —" ability word as a CONDITION
# ("if you had a land enter the battlefield this turn" — Searing Blaze, Groundswell,
# Quarry Beetle), the extra-land STATIC ("play N additional lands" — 30 cards), and
# land RECURSION ("play lands from your graveyard" / "return … lands … from your
# graveyard to the battlefield" — 32 cards). A structural-only migration would LOSE
# 78 genuine cards, so the lane ALSO rides this byte-identical regex (commander-legal
# corpus: post-IR ⊇ original-regex, 0 lost, +5 gained) run PER-CLAUSE over the
# reminder-stripped kept_oracle, PLUS the one SUBSTRING-AND branch the deleted lambda
# ran on the lower-cased clause ("whenever a land" & "enter" — no single regex
# expresses a substring-AND), checked inline in extract_signals_ir. The three
# regex-expressible branches (the "landfall" ability word, "play N additional lands",
# and the two land-recursion forms) are pinned here. landfall was NEVER a SWEEP key,
# so no SWEEP row is touched (len stays >=36). NO sidecar bump (the v20 projection
# already emits the land-ETB trigger). NOT a voltron-key add (the deleted producer
# fed has_other_plan when it fired — forced scope 'you' → always HIGH — so a faithful
# byte-identical reproduction, NOT _VOLTRON_SILENCING_PLAN_KEYS, restores the voltron
# silence in _signals_regex without over-silencing the +5 ir_only recall-gain
# bodies). CR 207.2c / 305 / 903.10a.
LANDFALL_REGEX = (
    r"landfall"
    r"|play (?:an|one|two|three|\d+) additional lands?"
    r"|play lands? from your graveyard"
    r"|return [^.]*\blands?\b[^.]*from your graveyard to the battlefield"
)
# ADR-0027 — land_destruction (the LD-support build-around axis: a card whose OWN
# ability repeatedly destroys lands — the Armageddon/Numot stax-LD plan, CR 701.8a)
# migrated to the Card IR via a BYTE-IDENTICAL membership-gated kept-mirror. The
# deleted regex producer (the `extract_signals` include_membership block) was NOT a
# per-card detector: it was a CREATURE-COMMANDER cross-open — a creature whose own
# oracle says "destroy [up to N] target land(s)" (Numot, Goblin Settler, Demonic
# Hordes — a repeatable LD ENGINE) opens the LD support lane, scope 'you', LOW
# confidence. It was deliberately membership + creature gated so a one-shot LD SPELL
# among the 99 (Stone Rain, Armageddon) is NOT mistaken for the deck's plan. phase
# DOES carry a structural shape (a `destroy` Effect whose target Filter is Land-typed)
# — but that broad per-card arm fires HIGH on every Stone Rain / Wasteland / Strip Mine
# (+143 over commander-legal), flooding the deck-plan lane with one-shot spells and
# utility lands the cross-open producer intentionally excluded. So the lane rides a
# BYTE-IDENTICAL regex mirror (this pattern, run over the reminder-stripped kept_oracle
# in extract_signals_ir's membership block, creature + include_membership gated, LOW
# confidence) — reproducing the deleted cross-open's firing set EXACTLY (commander-
# legal: regex==mirror, 23→23, 0 miss, 0 extra), NOT the broad structural arm. The
# broad `destroy`/Land structural `add` is removed (it was DEAD — the hybrid dropped
# the unmigrated IR land_destruction, so it never reached production; removal'
# own land-subtype exclusion is independent of it). land_destruction was NEVER a SWEEP
# key, so no SWEEP row is touched (len stays >=36). NO sidecar bump. NOT a voltron plan
# key: the deleted cross-open fired LOW confidence and NEVER fed has_other_plan (which
# requires confidence=='high'), so dropping it leaks no commander-damage voltron tell
# (voltron delta 0) and NO _LAND_DESTRUCTION_PLAN_MIRROR is needed. CR 701.8a / 903.10a.
LAND_DESTRUCTION_REGEX = (
    r"destroy (?:up to (?:one|two|three|four|\w+) )?target lands?\b"
)
# ADR-0027 — land_sacrifice_matters (the land-SACRIFICE archetype axis: a card that
# pays an ongoing land-sac cost, draws/grows when lands hit the graveyard, or offers a
# repeatable "Sacrifice a land:" OUTLET — Gitrog, Titania, Slogurk, Zuran Orb, Sylvan
# Safekeeper, Squandered Resources; CR 701.16) migrated to the Card IR via a BYTE-
# IDENTICAL kept WORD MIRROR. phase carries NO structural form for this lane — over the
# commander-legal corpus (floor-disabled, by oracle_id) the structural sacrifice arm
# emits land_sacrifice_matters on ZERO cards (the you-sac arm at line ~5560 deliberately
# routes a land-ONLY sac subject AWAY from sacrifice_outlets but never re-homes it to
# land_sacrifice — there is no `add("land_sacrifice_matters", ...)` anywhere in the
# structural IR), so the lane fired ONLY from this regex (66 commander-legal cards, all
# scope 'you', HIGH conf). The deleted producer was a per-card `_HAND_FLOOR` Detector run
# per-clause over the reminder-stripped, DFC-joined oracle; this constant, run FLAT over
# the same reminder-stripped `kept_oracle` in extract_signals_ir's _IR_KEPT_DETECTORS
# loop, is BYTE-IDENTICAL — the four arms' `[^.]*` anchors never cross a clause boundary
# and no card's match is split by a `;`/`\n` only (commander-legal: flat==per-clause==66,
# 0 gain, 0 loss). Distinct from land_destruction (DESTROY a land — CR 701.8a) and
# land_exchange (swap CONTROL of a land). land_sacrifice_matters was NEVER a SWEEP key, so
# no SWEEP row is touched (len stays 36). NO sidecar bump. The deleted producer fired HIGH
# conf scope 'you' and so counted toward has_other_plan (it is NOT in _GENERIC_KEYS /
# _VOLTRON_COMPAT_KEYS), silencing the spurious commander-damage voltron tell on a
# land-sac creature commander (Slogurk, Titania, Uurg, The Gitrog Monster — NOT a vanilla
# beater). Because the IR re-supply IS this byte-identical mirror (IR==regex==66), the
# hybrid re-silences via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — no broadening, no
# over-silence — matching the lands_matter / draw_matters kept-mirror precedent; NO
# _LAND_SACRIFICE_PLAN_MIRROR is needed. CR 701.16 / 903.10a.
LAND_SACRIFICE_REGEX = (
    r"sacrifice a land(?: card)?:"
    r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
    r"put into[^.]*graveyard"
    r"|whenever you sacrifice (?:a|one or more|another) lands?"
    r"|unless you sacrifice a land"
)
# ADR-0027 — cast_from_exile (the CAST/PLAY-FROM-EXILE build-around axis: payoffs and
# enablers that cast or play cards FROM EXILE — "whenever you cast a spell from exile"
# / "from anywhere other than your hand" Paradox triggers (Vega, Iraxxa, Quintorius
# Kand, Nalfeshnee, Keeper of Secrets), self-cast-from-exile creatures (Eternal Scourge,
# Misthollow Griffin, Squee), exile-and-cast engines (Court of Locthwain, Tinybones,
# Norin), the Adventure-style "exile this card from your hand … cast it for as long as
# it remains exiled" cycle (Masked Bandits, Rakish Revelers, Spara's Adjudicators), Plot
# from the top of the library (Fblthp); CR 207.2c / 601.3b / 702.143 / 702.170)
# migrated to the Card IR. phase carries NO usable STRUCTURAL form for this lane: it
# DROPS the "from exile" zone qualifier off both the `cast_spell` trigger (no zone) AND
# the self-cast `cast_from_zone` Effect (zones=() on Eternal Scourge / Misthollow), and
# the only exile cast-zone phase DOES project — `castable_zones=('exile',)` — is the
# 51-card FORETELL-SPELL serve pool, DISJOINT from the 77 detector firings (overlap 0),
# so reading it as a detector would over-fire 51 keyword-having spells. Over the
# commander-legal corpus (floor-disabled, by oracle_id) the structural IR emits this
# lane on ZERO cards — the lane fired ONLY from the deleted regex (77 commander-legal,
# all scope 'you' HIGH). This CAST_FROM_EXILE_REGEX (the EXACT deleted _HAND_FLOOR
# pattern) run FLAT over the reminder-stripped kept_oracle in extract_signals_ir's
# _IR_KEPT_DETECTORS loop reproduces the deleted per-clause producer BYTE-IDENTICALLY:
# every `[^.]*?` arm anchors within a single clause and no card's match is split by a
# `;`/`\n` only (commander-legal: flat==per-clause==77, 0 gain, 0 loss). Distinct from
# impulse_top_play (exile the TOP of YOUR library then temporary-play — its own avenue)
# and play_from_top (the ONGOING permission to play off the top of the LIBRARY — a
# different zone, not exile). cast_from_exile was NEVER a SWEEP key, so no SWEEP row is
# touched (len stays 33); only this CONSTANT is pinned here. NO sidecar bump. The
# deleted producer fired HIGH conf scope 'you' and so counted toward has_other_plan (it
# is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious commander-
# damage voltron tell on a cast-from-exile creature commander that is NOT a vanilla
# beater (Vega, Iraxxa, Quintorius Kand, Norin, Tinybones). Because the IR re-supply IS
# this byte-identical mirror (IR==regex==77), the hybrid re-silences via
# _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — no broadening, no over-silence — matching
# the land_sacrifice / extra_combats kept-mirror precedent; NO _CAST_FROM_EXILE_PLAN_
# MIRROR is needed. CR 207.2c / 601.3b / 903.10a.
CAST_FROM_EXILE_REGEX = (
    r"top card of your library has plot"
    r"|(?:whenever|each time) you (?:cast a spell|play a (?:card|land)"
    r"|play a land or cast a spell)[^.]*?from exile"
    r"|spells? you cast from exile"
    r"|you may (?:play|cast) (?:it|that card|this card|those cards?|them)"
    r"[^.]*?(?:for as long as it remains exiled|from exile)"
    r"|you may play (?:a |that )?card[^.]*?from exile"
    # Paradox (CR 207.2c): zone-agnostic "from anywhere other than your hand"
    # payoffs (Vega, Iraxxa) — the literal-"from exile" branches miss 16/17.
    r"|(?:cast a spell|play a land|play a card)[^.]*?"
    r"from anywhere other than your hand"
)
# ADR-0027 — exile_matters (the EXILE-ZONE-AS-RESOURCE archetype axis: a card that
# cares about the EXILE zone as a standing resource — "cards you own in exile" /
# "card in exile with <kind> counter on it" payoffs (Cosmogoyf / Crackling Drake P/T
# scalers, Mairsil / Grolnok / Tasha / Kianne cast-from-the-exile-pile engines,
# Ketramose "seven or more cards in exile", Ulamog "greatest mana value among cards in
# exile", Karn / Coax wishboard fetch, Dreadlight Monstrosity / Howling Galefang / Warden
# of the Beyond own-a-card-in-exile gates) plus the "exiled with <this>" persistent-pile
# payoffs (Gorex, The Kenriths' Royal Funeral, Lumbering Battlement) and the
# "for each card exiled this way" one-shot scalers the prefix branch also reaches
# (the March pump/cost cycle, Mizzix's Mastery, Haunting Echoes — pre-existing breadth;
# CR 406 exile zone) migrated to the Card IR. phase carries NO usable STRUCTURAL form:
# it scatters the exile-zone reference across a `zones=('in:exile',)` count operand
# (Ulamog), a `Condition(zones=('exile',))` (Ketramose), and a `characteristic_pt` Effect
# whose count operand drops the zone (Cosmogoyf / Crackling Drake), with no single
# category that means "this card references cards standing in exile". Over the
# commander-legal corpus (floor-disabled, by oracle_id) the structural IR emits this lane
# on ZERO cards — the lane fired ONLY from the deleted regex (63 commander-legal, all
# scope 'you' HIGH). This EXILE_MATTERS_REGEX (the EXACT deleted _HAND_FLOOR pattern) run
# FLAT over the reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS
# loop reproduces the deleted per-clause producer BYTE-IDENTICALLY: neither branch carries
# a `[^.]*` cross-clause span, so flat==per-clause (commander-legal: flat-mirror==per-
# clause-regex==63, 0 gain, 0 loss). Distinct from exile_removal (EXILE a permanent as
# REMOVAL — the deleted producer's "in exile" anchor never reaches it), cast_from_exile
# (CAST/PLAY a card FROM exile — the build-around above, no "in exile" standing-zone ref),
# and opponent_exile_matters (GRAVEYARD HATE — exiling an OPPONENT's graveyard). The lane
# was a regex FLOOR lane (in _IR_FLOOR_LANES, so the IR path re-ran the deleted producer);
# the byte-identical kept mirror replaces that floor re-run — exile_matters is removed
# from _IR_FLOOR_LANES (floor-mirror-dep -> 0). exile_matters was NEVER a SWEEP key, so no
# SWEEP row is touched (len stays 32); only this CONSTANT is pinned here. NO sidecar bump.
# The deleted producer fired HIGH conf scope 'you' and so counted toward has_other_plan
# (it is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious commander-
# damage voltron tell on an exile-zone engine commander that is NOT a vanilla beater
# (Mairsil, Grolnok, Tasha, Kianne, Ketramose). Because the IR re-supply IS this byte-
# identical mirror (IR==regex==63), the hybrid re-silences via _VOLTRON_SILENCING_PLAN_
# KEYS (signals.py) — no broadening, no over-silence — matching the cast_from_exile /
# land_sacrifice kept-mirror precedent; NO _EXILE_MATTERS_PLAN_MIRROR is needed. CR 406.
EXILE_MATTERS_REGEX = (
    r"cards? (?:you own )?(?:that are )?in exile"
    r"|for each card (?:you own )?(?:in )?exile"
)
# ADR-0027 — superfriends_matters (the PLANESWALKER-as-a-group cares-about lane:
# "planeswalkers you control" anthems / loyalty-counter payoffs / "activate a loyalty
# ability" engines / "planeswalker type" group refs (Leori) / "abilities of a
# planeswalker" copiers (The Chain Veil, Oath of Teferi)) migrated to the Card IR. The
# lane keeps its EXISTING structural arm in extract_signals_ir (a Condition gated on a
# Planeswalker subject you control — "as long as you control a <Name> planeswalker, …",
# "if you control a Chandra planeswalker, …"), which fires on 26 commander-legal cards
# the deleted regex's narrow word patterns MISS (the singular "control a <Name>
# planeswalker" gate: Charging War Boar, Court Cleric, Renegade Firebrand, Oath of
# Chandra/Liliana). phase v0.1.19 carries NO structural form for the BROADER textual
# refs (the "planeswalkers you control" anthem, the "loyalty counter" payoffs, the
# "activate a loyalty ability" engines, the "abilities of a planeswalker" copiers —
# these scatter into pump_target / counter / activated-ability shapes with no
# "this references planeswalkers-as-a-group" tag), so those ride this
# SUPERFRIENDS_MATTERS_REGEX (the EXACT deleted _HAND_FLOOR pattern) run FLAT over the
# reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS loop. No
# branch carries a `[^.]*` cross-clause span, so flat==per-clause (commander-legal:
# flat-mirror==per-clause-regex==149, 0 gain, 0 loss). The lane was a regex FLOOR lane
# (in _IR_FLOOR_LANES, so the IR path re-ran the deleted producer); the kept mirror
# replaces that floor re-run — superfriends_matters is removed from _IR_FLOOR_LANES
# (floor-mirror-dep -> 0). superfriends_matters was NEVER a SWEEP key, so no SWEEP row
# is touched (len unchanged); only this CONSTANT is pinned here. NO sidecar bump. The
# deleted producer fired HIGH conf scope 'you' and so counted toward has_other_plan (it
# is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious commander-
# damage voltron tell on a superfriends engine that is NOT a vanilla beater. Because the
# IR re-supply (structural arm + kept mirror) is BROADER than the deleted regex (+26
# ir_only), _VOLTRON_SILENCING_PLAN_KEYS would OVER-silence those 26 structural bodies;
# instead a byte-identical _SUPERFRIENDS_MATTERS_PLAN_MIRROR (== this regex over the
# reminder-STRIPPED `text`) OR'd into has_other_plan restores ONLY the old regex's
# silence set (voltron 3010 -> 3010, file-swap delta 0). CR 306 / 606 / 903.10a.
SUPERFRIENDS_MATTERS_REGEX = (
    r"planeswalkers? you control|loyalty counters?"
    r"|activate (?:a |one )?loyalty|one or more loyalty"
    r"|planeswalker type"
    r"|abilit(?:y|ies) of (?:a |target |another |each )?planeswalker"
)

# ADR-0027: counter_doubling migrated to the Card IR. This is the byte-identical UNION
# of the two deleted oracle regexes — the _HAND_FLOOR producer (the first three arms)
# and this SWEEP_DETECTORS row (the last four arms) — pinned here so the
# _COUNTER_DOUBLING_MIRROR kept detector (_signals_ir) and the _COUNTER_DOUBLING_PLAN_MIRROR
# voltron gate (_signals_regex) share ONE source.
# phase v0.1.19 MANGLES the one-shot / activated / triggered "double the number of …
# counters" forms (Vorel, Gilder Bairn, Kalonian Hydra, Primordial Hydra, Voracious
# Hydra, …) — to a generic `double` effect or a plain `place_counter`/`counter_distribute`
# that loses the doubling semantics — so no clean structural arm reaches the 46; the
# mirror recovers them. The structural `cat == "counter_doubling"` replacement arm adds
# the 6 canonical replacement doublers the regex MISSED (Doubling Season, Branching
# Evolution, Primal Vigor, Corpsejack Menace, The Earth Crystal, Struggle for Project
# Purity). Commander-legal: mirror == old regex == 69 exactly, 0 over-fire. CR 122 / 614.
COUNTER_DOUBLING_REGEX = (
    r"double the number of [^.]*counters?"
    r"|would put[^.]*counters?[^.]*\binstead\b[^.]*(?:twice|double|that many plus)"
    r"|that many plus one[^.]*counters?"
    r"|one or more counters? would be put on"
    r"|(?:put|placed?) (?:twice that many|that many plus (?:one|\d+))[^.]*counters?"
)
# ADR-0027 — void_warp_matters migrated to the Card IR. Its SWEEP_DETECTORS row is
# deleted; detection moves to a BYTE-IDENTICAL kept WORD MIRROR (this exact regex in
# signals._IR_KEPT_DETECTORS, scope 'you'). Void (CR 207.2c ability word) and Warp (the
# Edge of Eternities alt-cast keyword) are recent mechanics phase v0.1.19 carries NO
# usable structural form for: the baked sidecar surfaces `Void` as a keyword on ZERO
# cards (it's an ability word) and DROPS the `Warp` keyword on 2 genuine warp cards
# (Timeline Culler folds it into a `cast_from_zone` Effect keeping only Haste; Tannuk —
# a warp GRANTER — has empty keywords), so a structural keyword arm would under-fire by
# 14+2 of the 49. This mined regex survives as a shared constant so the kept mirror
# reuses it — mirror / (now-deleted) detector never drift. SWEEP_LABELS still carries
# the human label. CR 207.2c (Void ability word) / 702.185 (Warp).
#
# _matters sweep (ADR-0034): split by emission ARM. VOID_WARP_MAKERS_REGEX = the three
# MAKER branches — the card PERFORMS/GRANTS the Warp alt-cast: the Warp keyword bearer
# ("Warp {1}{U}", Starfield Vocalist) and granter ("have warp {2}{R}", Tannuk) via
# `warp \{`, the em-dash non-mana warp-cost keyword form via `warp—`, and the warp-from-
# graveyard self-cast (Timeline Culler, "using its warp ability") via that branch.
# VOID_WARP_MATTERS_REGEX keeps the five PAYOFF branches — the Void ability word that
# CARES whether "a spell was warped this turn" (CR 207.2c — Alpharael, Susurian
# Voidborn) and the warp REFERENCES ("for its warp cost" Full Bore, "cast … for its
# warp", "target exiled card with warp" Blade of the Swarm, bare "warp cost"). Both run
# as separate kept WORD MIRRORS (scope 'you', HIGH); their union over the reminder-
# stripped oracle == the old single regex (each branch lives in exactly one arm), so
# membership is gate-verified set-equal (49 = makers + matters). CR 207.2c / 702.185.
VOID_WARP_MAKERS_REGEX = "warp \\{|warp—|using its warp ability"
VOID_WARP_MATTERS_REGEX = "void —|warp cost|for its warp cost|cast (?:a |this )?(?:spell|card)[^.]*for its warp|target exiled card with warp"

# ADR-0027 — lure_makers (force-a-block, CR 509.1c). Pinned as a shared constant so the
# kept WORD MIRROR (_LURE_MATTERS_MIRROR, _signals_ir — recovers the Aftermath-DFC back
# face phase never projects, Destined // Lead) and the voltron _LURE_MATTERS_PLAN_MIRROR
# (_signals_regex) reuse ONE source so they never drift from the deleted SWEEP
# detector. Every arm is clause-local — the only
# span "all creatures able to block [^.]*do so" can't cross a period — so a flat scan
# over the reminder-stripped kept_oracle == the deleted per-clause SWEEP firing
# (commander-legal: 69==69, no divergence). CR 509.1c.
LURE_MATTERS_REGEX = (
    "all creatures able to block [^.]*do so|must be blocked if able"
    "|all creatures (?:that could|able to) block|must be blocked(?: (?:by|if))?"
)

SWEEP_DETECTORS: tuple[dict, ...] = (
    # ADR-0027 — stax_taxes + symmetric_stax migrated regex→Card IR. Both lanes now
    # fire from the structural `restriction` Effect arm in extract_signals_ir, scope-
    # discriminated by the v22 projection (SIDECAR_VERSION 22): a restriction with
    # scope=='opp' (an OPPONENT static — Drannith Magistrate, Lavinia, Ghostly Prison)
    # opens stax_taxes; scope=='each' (a controller-NEUTRAL permanent-CLASS lock — Back
    # to Basics, Static Orb, Sphere of Resistance, Thalia's symmetric noncreature tax)
    # opens symmetric_stax. The arm is BROADER than the deleted regex on the each-scope
    # side (+145 ir_only symmetric locks the brittle regex missed — Collector Ouphe /
    # Cursed Totem ability-shutoffs, Defense Grid / Chill / Gloom symmetric cost taxes,
    # Bedlam / Falter can't-block table effects, Arrest / Faith's Fetters Aura
    # lockdowns) and on the opp side (+10: Angelic Arbiter, Gnat Miser / Jin-Gitaxias
    # hand-size taxes, Ashiok search-denial — all genuine opponent restrictions); it
    # also DROPS the regex over-fire (every "creatures your opponents control get -X/-X"
    # debuff anthem the HAND_FLOOR `creatures your opponents control` branch matched).
    # Because the arm is broader, the deleted regex is reproduced BYTE-IDENTICALLY by a
    # per-clause kept-mirror (signals._signals_ir, run over the reminder-stripped
    # kept_oracle, the same input the deleted detectors scanned) of these EXACT pinned
    # regexes: STAX_TAXES_REGEX (the union of the THREE deleted producers — the
    # _signals_regex _DETECTORS pacify row + the _HAND_FLOOR `opponents can't` /
    # `creatures your opponents control` row + this SWEEP row) and SYMMETRIC_STAX_REGEX
    # (this SWEEP row — symmetric_stax had no _signals_regex producer). The two SWEEP
    # rows are KEPT in this list (len stays 36; they ARE the pinned regex source and,
    # since extract_signals still runs them, they re-supply the regex-path has_other_plan
    # voltron silence for the cards they cover — symmetric_stax is fully SWEEP-covered, so
    # it needs no plan mirror; stax_taxes' DETECTORS+HAND_FLOOR-only cards are re-silenced
    # by a byte-identical _STAX_TAXES_PLAN_MIRROR in _signals_regex). Mirrors the
    # artifacts_matter / edict_makers kept-row precedent. CR 604.1 (static abilities are
    # simply true → an unqualified "Spells cost {1} more" taxes all players symmetrically)
    # / 118.9. The serve specs stay hand-registered in signal_specs.py.
    {
        "key": "stax_taxes",
        "scope": "opponents",
        "is_widen_of": "stax_taxes",
        "regex": "(?:target player|that player|each player|a player|that opponent)[^.]{0,90}?can't (?:cast|activate|attack|block|search|untap|draw)|must pay \\{?\\d?\\}?[^.]*additional|spells?[^.]*cost \\{?\\d+\\}? more to (?:cast|activate)|noncreature spells?[^.]*cost(?:s)? \\{?\\d|noncreature spells?[^.]*can't be cast|spells? with mana value \\d[^.]*can't be cast|players? can't cast|that player can't cast spells|spells can't be cast|can cast spells only|your opponents control enter(?:s)? tapped|nonbasic lands enter(?:s)? tapped|costs? players \\{?\\d+\\}? more|doing the chosen action costs|players? can't pay life or sacrifice nonland permanents",
    },
    {
        "key": "symmetric_stax",
        "scope": "each",
        "is_widen_of": "stax_taxes",
        "regex": "players? can't (?:cast|untap|attack|gain|search their|draw|play|activate)|other permanents enter (?:the battlefield )?tapped|(?:doesn't|don't|does not) untap during (?:its|their|the)",
    },
    {
        "key": "voltron_matters",
        "scope": "you",
        "is_widen_of": "voltron_matters",
        "regex": "create [^.]*\\bequipment\\b[^.]* token|create [^.]*\\bequipment\\b artifact",
    },
    {
        "key": "artifacts_matter",
        "scope": "you",
        "is_widen_of": "artifacts_matter",
        "regex": "if you control an artifact|if you control (?:a|an|one or more) artifacts?",
    },
)


# Curated (label, avenue) prose per mined sweep axis. Data, not logic.
SWEEP_LABELS: dict[str, tuple[str, str]] = {
    "ability_copy": (
        "Ability copy",
        "ability-copy effects plus permanents with strong activated/triggered abilities to copy",
    ),
    "activated_draw": (
        "Repeatable draw",
        "repeatable activated card draw and ways to untap the source",
    ),
    "affinity_type": (
        "Affinity",
        "cheap artifacts/creatures of the affinity type to slash costs",
    ),
    "all_creatures_kw_grant": (
        "Global keyword grant",
        "symmetric keyword grants — pair with your own evasive board",
    ),
    "alt_cost_keyword": (
        "Alternative-cost keyword",
        "cards sharing the alternative-cost mechanic",
    ),
    "anthem_static": ("Static anthem", "go-wide creatures to ride the anthem"),
    "attractions_matter": ("Attractions", "attraction openers and visit payoffs"),
    "aura_equip_kw_grant": (
        "Aura/Equipment keyword grant",
        "Auras and Equipment that gain keywords to suit up",
    ),
    "base_pt_set": (
        "Set base power/toughness",
        "set-P/T effects and creatures that exploit them",
    ),
    "airbend_makers": (
        "Airbend",
        "airbend exile-and-recast tempo and payoffs for airbending",
    ),
    # _matters sweep (ADR-0034): earthbend split into the keyword-bearer DOER arm
    # (cards carrying the Earthbend keyword — land-animation + +1/+1 counters) and
    # the cross-bend PAYOFF arm (Avatar Aang's "whenever you …earthbend…" reference).
    "earthbend_makers": (
        "Earthbend",
        "earthbend land-animation and +1/+1 counter cards (Earthbend keyword)",
    ),
    "earthbend_matters": (
        "Earthbend payoffs",
        "payoffs that trigger when you earthbend",
    ),
    # _matters sweep (ADR-0034): waterbend split into the keyword-bearer DOER arm
    # (cards that pay/perform a waterbend cost) and the cross-bend PAYOFF arm
    # (Avatar Aang's "whenever you waterbend…" reference).
    "waterbend_makers": (
        "Waterbend",
        "waterbend alternate-cost (tap artifacts/creatures) cards",
    ),
    "waterbend_matters": (
        "Waterbend payoffs",
        "payoffs that trigger when you waterbend",
    ),
    # _matters sweep (ADR-0034): firebending split into the keyword-bearer MAKER arm
    # (cards carrying the Firebending keyword — attack-trigger red mana) and the
    # keyword-LESS Fire-Nation reference/payoff arm.
    "firebending_makers": (
        "Firebending",
        "firebending attack-trigger red mana (Firebending keyword bearers)",
    ),
    "firebending_matters": (
        "Firebending payoffs",
        "Fire Nation references and payoffs for firebending",
    ),
    "blocked_matters": (
        "Blocks matter",
        "combat triggers when creatures block or become blocked",
    ),
    # _matters sweep (ADR-0034): boast split into the MAKER arm (creatures with a
    # Boast ability — this label fits them) and the PAYOFF arm (boast triggers /
    # amplifiers — Birgi's 'can boast twice').
    "boast_makers": ("Boast", "boast creatures and ways to attack safely"),
    "boast_matters": ("Boast payoffs", "boast triggers and amplifiers"),
    "cant_block_grant": ("Can't-block", "force blockers off to clear a path to attack"),
    # ADR-0027 A4: cast_as_named_card label deleted with its SWEEP_DETECTORS row.
    "has_changeling": (
        "Changeling / all types",
        "all-creature-type cards for tribal overlap",
    ),
    "cmdzone_ability": (
        "Command-zone ability",
        "command-zone activations and commander recursion",
    ),
    "coin_flip": ("Coin flips", "coin-flip payoffs plus flip-fixing"),
    "color_change": (
        "Color change",
        "color-changing effects for protection and devotion",
    ),
    "combat_buff_engine": ("Beginning-of-combat buff", "attackers to grow each combat"),
    "combat_damage_to_creature": (
        "Combat damage to creatures",
        "evasive/first-strike/deathtouch attackers that connect with creatures",
    ),
    "combat_damage_to_opp": (
        "Combat damage to opponents",
        "evasive attackers and extra combats to connect",
    ),
    "commander_matters": (
        "Commander matters",
        "cast-from-command-zone payoffs and commander protection",
    ),
    "conditional_self_protection": (
        "Conditional protection",
        "ways to satisfy the commander's protection condition",
    ),
    "conjure_makers": ("Conjure", "conjure effects (Alchemy)"),
    "convoke_makers": (
        "Convoke",
        "wide, cheap creatures to convoke out your convoke spells",
    ),
    "convoke_matters": ("Convoke", "wide, cheap creatures to convoke out big spells"),
    "count_anthem": ("Count anthem", "go-wide creatures to scale the count-based pump"),
    "counter_distribute": (
        "Counter distribution",
        "spread +1/+1 counters across your whole board",
    ),
    "counter_grants_kw": (
        "Counters grant keywords",
        "+1/+1 counter sources to turn on the keyword grant",
    ),
    "counter_manipulation": (
        "Counter manipulation",
        "remove or relocate counters for value",
    ),
    "counter_move": ("Counter movement", "move counters between permanents"),
    "counter_place_trigger": (
        "Counter-placement triggers",
        "ways to put +1/+1 counters to fire the trigger",
    ),
    "counter_replace_bonus": (
        "Counter doubling",
        "counter-placement sources to double up",
    ),
    "token_doubling": (
        "Token doubling",
        "token MAKERS to multiply plus other token doublers and go-wide payoffs",
    ),
    "counter_doubling": (
        "Counter doubling",
        "+1/+1 counter SOURCES to multiply plus other counter doublers",
    ),
    "creature_cast_trigger": (
        "Creature-cast triggers",
        "cheap creatures to chain the cast trigger",
    ),
    "creature_ping": ("Power-based ping", "high-power creatures to ping with"),
    "damage_doubling": ("Damage doubling", "burn and big hits to double"),
    "damage_equal_power": (
        "Power-as-damage",
        "high-power creatures to fling as damage",
    ),
    "damage_prevention": (
        "Damage prevention / fog",
        "fogs and prevention to blank attacks and burn",
    ),
    "damage_redirect": ("Damage redirection", "redirect effects to protect and punish"),
    "damage_to_you_punish": (
        "Punish damage to you",
        "take damage and punish the source",
    ),
    "debuff_makers": (
        "-1/-1 / shrink",
        "minus-counter and toughness-shrink removal plus payoffs",
    ),
    "destroy_legendary": ("Legend removal", "targeted destruction of legends"),
    "has_devour": ("Devour", "token fodder to devour"),
    "dies_recursion": (
        "Dies-recursion",
        (
            "anything that makes creatures recur when they die — with or without counters "
            "(undying/persist plus bare dies-return like Feign Death)"
        ),
    ),
    "dig_until": ("Dig-until", "deep top-of-library digging effects"),
    "discard_outlet": (
        "Discard outlets",
        "loot/rummage outlets to fuel discard and graveyard payoffs",
    ),
    "domain_matters": ("Domain", "basic land types and fixing to grow domain"),
    "donate_makers": ("Donate", "give away downside permanents for advantage"),
    "draft_spellbook": (
        "Draft / spellbook",
        "draft-a-card and spellbook effects (Alchemy)",
    ),
    "draw_for_each": ("Scaling card draw", "grow the count your draw scales with"),
    "each_mode_player": ("Spread-the-modes", "modal effects that hit each player"),
    "edict_makers": (
        "Edicts / forced sacrifice",
        "edicts to make opponents sacrifice",
    ),
    "evasion_denial": (
        "Anti-landwalk defense",
        "strip an opponent's landwalk so you can block (CR 702.14)",
    ),
    "excess_damage": ("Excess damage", "trample and big hits to exploit excess damage"),
    # _matters sweep (ADR-0034): exhaust split into the MAKER arm (cards with an
    # Exhaust ability — this label fits them) and the PAYOFF arm (exhaust-activation
    # triggers — Pit Automaton).
    "exhaust_makers": ("Exhaust", "exhaust abilities (once per game)"),
    "exhaust_matters": ("Exhaust payoffs", "exhaust-activation triggers and payoffs"),
    "exile_until_leaves": ("O-Ring removal", "exile-until-leaves removal effects"),
    "explore_makers": ("Explore", "creatures that explore"),
    "explore_matters": ("Explore payoffs", "triggers when your creatures explore"),
    "extra_land_drop": (
        "Put lands into play",
        "lands to drop straight onto the battlefield",
    ),
    "facedown_matters": (
        "Face-down / morph",
        "morph/manifest/disguise creatures and flip payoffs",
    ),
    "fight_makers": ("Fight", "big creatures to fight with as removal"),
    "flash_grant": ("Flash", "flash enablers and instant-speed threats"),
    "flip_self": (
        "Flip creature",
        "a self-contained flip creature (Kamigawa) — meets its own flip condition",
    ),
    "forced_attack": ("Forced attacks / politics", "goad-style forced-attack effects"),
    "free_cast": ("Free / alternative cost", "expensive bombs to cast for free"),
    "global_ability_grant": (
        "Global ability grant",
        "a board that exploits the granted ability",
    ),
    "group_hug_draw": ("Group draw", "symmetric draw plus punisher payoffs"),
    "group_mana": ("Group ramp", "shared-mana effects and big payoffs to spend it"),
    "hand_disruption": ("Hand disruption", "peek-and-strip effects against opponents"),
    "impulse_top_play": ("Impulse draw (top)", "top-of-library exile-and-play engines"),
    "keyword_counter": (
        "Keyword counters",
        "keyword-ability counter sources and payoffs (CR 122.1b)",
    ),
    "keyword_grant_target": (
        "Targeted keyword grant",
        "creatures worth granting evasion/protection",
    ),
    "keyword_soup": ("Keyword soup", "many-keyword threats to buff together"),
    "legend_rule_off": (
        "Legend-rule off",
        "duplicate legends to abuse without the legend rule",
    ),
    "life_total_set": ("Life-total swing", "set/exchange-life effects and payoffs"),
    "ltb_matters": (
        "Leaves-the-battlefield",
        "sacrifice and blink fodder to trigger LTB",
    ),
    "lure_makers": ("Lure", "lure effects plus deathtouch/trample to punish blocks"),
    "mass_bounce": ("Mass bounce", "board-wide bounce and ETB re-use"),
    "mass_removal": ("Board wipes", "sweepers plus resilience to rebuild"),
    "miracle_grant": ("Miracle", "miracle support and top-deck setup"),
    "myriad_grant": ("Myriad", "attackers worth copying to each opponent"),
    "rad_counter_makers": (
        "Rad counters",
        "rad-counter sources and payoffs (Fallout — each player mills + loses life per rad)",
    ),
    "oil_counter_makers": (
        "Oil counters",
        "oil-counter sources (Phyrexia — cards that place oil counters)",
    ),
    "oil_counter_matters": (
        "Oil counters",
        "oil-counter sources and payoffs (Phyrexia — charge-style depletion counters)",
    ),
    "ki_counter_makers": (
        "Ki counters",
        "ki-counter sources (Kamigawa Spirit/Arcane triggers place ki counters)",
    ),
    "ki_counter_matters": (
        "Ki counters",
        "ki-counter sources and payoffs (Kamigawa Spirit/Arcane triggers)",
    ),
    "shield_counter_makers": (
        "Shield counters",
        (
            "shield-counter sources and payoffs (Brokers — a counter that absorbs the next "
            "destroy/damage)"
        ),
    ),
    "named_counter_misc": (
        "Other named counters",
        "enablers and payoffs for a niche named-counter mechanic",
    ),
    "named_synergy": (
        "Named-card synergy",
        "the specific named cards this references",
    ),
    "copy_limit": (
        "Copy-limit swarm",
        "more cards sharing this name + go-wide-on-one-name payoffs (CR 100.2a)",
    ),
    "has_ninjutsu": (
        "Ninjutsu",
        "cheap unblockable creatures to ninja in value bombs",
    ),
    "noncombat_damage_payoff": (
        "Noncombat damage",
        "burn and mana-value-scaling damage outside combat",
    ),
    "noncreature_cast_punish": (
        "Punish noncreature spells",
        "stax and punishers for noncreature casts",
    ),
    "opponent_counter_grant": (
        "Mark opponents",
        "bounty/stun counters on opponents plus payoffs",
    ),
    "opponent_exile_makers": (
        "Graveyard hate",
        "exile opponents' graveyards (graveyard-hate doers)",
    ),
    "opponent_exile_matters": (
        "Opponents' exile",
        "exile opponents' cards and play them",
    ),
    "partner_background": (
        "Partner / Background",
        "a Partner or Background to pair as a second commander",
    ),
    "companion_keyword": (
        "Companion",
        "a companion whose deckbuilding restriction your deck already meets",
    ),
    "phasing_makers": ("Phasing", "phase-out effects for protection and resets"),
    "play_from_top": ("Play from the top", "top-of-library access plus reveal payoffs"),
    # ADR-0027 A4: playtest_matters label deleted with its SWEEP_DETECTORS row.
    "power_double": ("Power doubling", "big creatures to double in power"),
    "powerup_matters": ("Power-up", "power-up counters and payoffs"),
    "protection_grant": (
        "Grant protection",
        "creatures worth protecting with hexproof/protection",
    ),
    "pump_makers": (
        "Combat tricks / pump",
        "instant-speed pump to win combat and push damage",
    ),
    "sacrifice_protection": (
        "Sacrifice protection",
        "key permanents to shield from sacrifice",
    ),
    "saga_matters": ("Sagas", "Sagas plus lore-counter manipulation"),
    "scaling_pump": ("Scaling pump", "go-wide/go-tall payoffs that scale a creature"),
    "secret_writedown": (
        "Wish / outside the game",
        "wishboard and name-a-card effects",
    ),
    "seek_matters": ("Seek", "seek effects (Alchemy tutoring)"),
    "self_blink": (
        "Blink / flicker",
        "your own ETB creatures to flicker for value",
    ),
    "self_counter_grow": (
        "Self +1/+1 growth",
        "counter doublers and ways to grow the commander",
    ),
    "self_pump": ("Firebreathing", "mana sinks to pump and close games"),
    "has_soulbond": ("Soulbond", "creatures to pair via soulbond"),
    "spell_keyword_grant": (
        "Grant spells keywords",
        "instants/sorceries to give cascade/flashback/etc.",
    ),
    "starting_life_matters": (
        "Starting-life threshold",
        "lifegain/loss to cross the threshold",
    ),
    "station_matters": (
        "Station / Spacecraft",
        "ways to charge and station Spacecraft",
    ),
    "stickers_matter": ("Stickers", "name/ability/art sticker effects"),
    "suspend_matters": (
        "Suspend / time counters",
        "suspend cards plus time-counter manipulation",
    ),
    "symmetric_damage_each": (
        "Symmetric damage",
        "sweepers and pingers that hit everyone",
    ),
    "symmetric_stax": ("Symmetric stax", "asymmetry-breakers to dodge the lock"),
    "tap_down": (
        "Tap-down control",
        "repeatable tappers to lock opponents' permanents",
    ),
    "tap_untap_matters": (
        "Tap/untap triggers",
        "tap and untap effects to fire the trigger",
    ),
    "tapper_engine": ("Tappers / pacifism", "repeatable tappers to neutralize threats"),
    "target_player_draws": (
        "Targeted draw",
        "give-draw effects and the payoffs around them",
    ),
    "targeting_matters": (
        "Targeting / heroic",
        "cheap targeted spells to trigger target-matters",
    ),
    "theft_makers": ("Theft", "steal opponents' cards and cast them"),
    "wants_theft": (
        "Wants theft",
        "theft enablers — your commander rewards casting what you don't own",
    ),
    "timing_control": (
        "Timing restriction",
        (
            "effects that restrict WHEN spells can be cast (Teferi, City of Solitude, "
            "Fires of Invention)"
        ),
    ),
    "end_the_turn": (
        "End the turn",
        (
            "end-the-turn effects to lock in your turn's value and fizzle end-step "
            "downsides (Sundial of the Infinite, Glorious End, Obeka)"
        ),
    ),
    "topdeck_selection": (
        "Top-deck selection",
        "scry and look-at-top to set up your draws (surveil also fills the graveyard)",
    ),
    "topdeck_stack": (
        "Top-deck stacking",
        "put-on-top effects plus play-from-top payoffs",
    ),
    "toughness_combat": (
        "Toughness as power",
        "high-toughness defenders to deal combat damage",
    ),
    "tribal_etb_multi": (
        "Multi-tribe ETB",
        "creatures of the relevant types to chain ETBs",
    ),
    "tribe_damage_trigger": (
        "Tribal combat damage",
        "evasive tribe members to connect",
    ),
    "trigger_doubling": (
        "Trigger doubling",
        "high-value triggered abilities to double",
    ),
    "typed_anthem_multi": ("Multi-type anthem", "creatures of the named types"),
    "typed_enters_punish": (
        "Typed-ETB punisher",
        "creatures of the type to chain the punish trigger",
    ),
    "unspent_mana": ("Unspent mana", "ways to use leftover mana each turn"),
    "variable_pt": (
        "Variable power/toughness",
        "fill the resource your */* scales with",
    ),
    "void_warp_makers": (
        "Void / warp makers",
        "warp bearer/granter cards (Edge of Eternities)",
    ),
    "void_warp_matters": ("Void / warp", "void and warp cards (Edge of Eternities)"),
    "win_lose_game": (
        "Alternate win/lose",
        "alternate win conditions and ways to enable them",
    ),
}
