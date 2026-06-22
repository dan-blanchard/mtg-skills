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

# ADR-0027 tranche2-B-3: spell_keyword_grant / target_player_draws migrated to the
# Card IR (detection moved to signals.extract_signals_ir). Their SWEEP_DETECTORS rows
# are deleted; these mined regexes survive as shared constants so signal_specs reuses
# them for the serve pool — keeping serve and the (now-deleted) detector from drifting.
SPELL_KEYWORD_GRANT_REGEX = "spells you cast have (?:convoke|affinity|cascade|flash|trample|deathtouch|delve|undaunted|haste|lifelink|menace|ward|improvise|demonstrate|casualty|flashback)|(?:noncreature spells|creature spells|spells) you cast have (?:improvise|demonstrate|casualty|convoke|affinity|cascade|flashback)|spell you cast(?: each turn)? has casualty|creature spells you cast have"
TARGET_PLAYER_DRAWS_REGEX = "target player draws a card|target opponent draws"
# ADR-0027 — group_hug_draw migrated to the Card IR (the symmetric group-hug draw lane:
# a card that draws for EVERY player — Howling Mine, Wheel of Fortune, Prosperity). Its
# SWEEP_DETECTORS row is deleted; detection moved to a STRUCTURAL arm (a `draw` Effect
# scope=='each', signals.extract_signals_ir) UNION a BYTE-IDENTICAL kept WORD MIRROR
# (this exact regex in signals._IR_KEPT_DETECTORS, scope 'each') for the 4 cards phase
# under-structures (Grothama / Mathise / Vault 11 / Winter Sky fold "each player draws"
# to scope 'any' or emit no draw Effect). This mined regex survives as a shared constant
# so signal_specs hand-registers the serve pool reusing it — keeping serve and the
# (now-deleted) detector from drifting.
GROUP_HUG_DRAW_REGEX = "each player (?:may )?draws?\\b|each player who drew"
# ADR-0027 — flash_grant migrated to the Card IR. The GRANT-to-OTHERS structural form
# binds in extract_signals_ir (a cast_with_keyword{flash} static — "cast <a class of>
# spells as though they had flash"; Vedalken Orrery, Leyline of Anticipation, Teferi,
# Yeva — the 29 commander-legal cards phase parses structurally). phase folds the
# ACTIVATED / conditional flash-grant (Winding Canyons {2}{T}, Emergence Zone, Teferi
# Time Raveler +1) and leaves the "cast this spell as though it had flash" self-flash
# textual, so the FULL deleted SWEEP regex is kept BYTE-IDENTICALLY as the
# _IR_KEPT_DETECTORS mirror (signals._IR_KEPT_DETECTORS) — the union reproduces the
# deleted producer's 81 commander-legal fires EXACTLY (regex_only 0, ir_only 0, scope
# parity 'you'). This mined regex survives as a shared constant so signal_specs
# hand-registers the serve pool reusing it and the kept mirror reuses it — serve /
# mirror / (now-deleted) detector never drift. SWEEP_LABELS still carries the human
# label. CR 702.8 (flash).
FLASH_GRANT_REGEX = "as though (?:it|they) (?:had|have) flash|have flash\\b"
# ADR-0027 — theft_matters migrated to the Card IR (STEAL an OPPONENT's cards and
# CAST/PLAY them: the impulse-from-opponent steal-and-cast engines, the heist Arena
# keyword action, and the name-strip three-zone rifles). Its SWEEP_DETECTORS row is
# deleted; phase carries NO structural form, so the lane rides a BYTE-IDENTICAL kept
# WORD MIRROR (this exact regex in signals._IR_KEPT_DETECTORS, scope 'opponents') —
# the seven arms' `[^.]*` spans never cross a clause, so flat-over-kept_oracle ==
# per-clause == the deleted producer's 33 commander-legal fires EXACTLY. This mined
# regex survives as a shared constant so signal_specs hand-registers the serve pool
# reusing it AND the kept mirror reuses it — serve / mirror / (now-deleted) detector
# never drift. SWEEP_LABELS still carries the human label. CR DD9 (heist) / 613.1b
# (control-changing effects).
THEFT_MATTERS_REGEX = "conjure a duplicate of[^.]*from an opponent's library|you may (?:play|cast)[^.]*from that player's hand|cast (?:spells )?from (?:that|target) (?:player|opponent)'s hand|play (?:with )?(?:lands and )?(?:spells )?from (?:that|target) (?:player|opponent)'s hand|(?:each player|each opponent|target opponent|that player)[^.]*exiles? cards from the top of their library|search (?:that player|target opponent|an opponent|each opponent)'?s? graveyard, hand,? and library|\\bheist\\b"
# ADR-0027 tranche2-B (t2b3-B) — opponent_counter_grant migrated to the Card IR. Its
# SWEEP_DETECTORS row is deleted (structural read: a detrimental bounty/stun counter on
# an opponent's permanent). This mined regex survives as a shared constant so
# signal_specs hand-registers the serve pool reusing it — DETRIMENTAL marks only
# (bounty/stun); the open `[a-z]+` that caught beneficial +1/+1 grants to opponents was
# removed.
OPPONENT_COUNTER_GRANT_REGEX = "put a (?:bounty|stun) counter on target (?:creature|permanent) (?:an opponent controls|that opponent controls)|target creature an opponent controls[^.]*it has \\\"|creatures with [^.]*counters on them can't attack"
# ADR-0027 (q2-D3) — noncreature_cast_punish migrated to the Card IR. Its
# SWEEP_DETECTORS row is deleted (the OPPONENT-punisher half binds structurally; the
# symmetric "a player casts" half rides signals._IR_KEPT_DETECTORS). This mined regex
# survives as a shared constant so signal_specs hand-registers the serve pool reusing
# it, and signals reuses it for both the kept word mirror and the voltron PLAN mirror —
# so serve / detector / silence never drift.
NONCREATURE_CAST_PUNISH_REGEX = "whenever a player casts a noncreature spell|whenever an opponent casts a noncreature|whenever a player casts an (?:artifact|instant|sorcery)"
# ADR-0027 β — tribe_damage_trigger migrated to the Card IR via the KEPT-DETECTOR
# pattern. Its SWEEP_DETECTORS row is deleted: phase leaves the combat_damage trigger
# subject = None (no structure to read), so this is a byte-identical kept mirror, not a
# projection. Compiled with re.IGNORECASE, `[A-Z][a-z]+` also matches a generic
# "creature", so the lane is really "your creatures connect for combat damage → reward"
# (Toski, Reconnaissance Mission, Coastal Piracy, Bident of Thassa), not strictly
# tribal. This mined regex survives as a shared constant so signals._IR_KEPT_DETECTORS
# reuses it for the kept mirror and signal_specs hand-registers the serve reusing it —
# so serve / mirror never drift. SWEEP_LABELS still carries the human label.
TRIBE_DAMAGE_TRIGGER_REGEX = "whenever (?:one or more|a|another) [A-Z][a-z]+s? you control deal[s]? (?:combat )?damage to (?:a player|an opponent|one of your opponents|each opponent)"
# ADR-0027 β — combat_damage_to_creature + combat_damage_to_opp (both is_widen_of
# combat_damage_matters) migrated to the Card IR via the KEPT-DETECTOR pattern. Their
# SWEEP_DETECTORS rows are deleted: phase DOES carry the damage RECIPIENT class on the
# combat_damage trigger (Ohran Viper's two DamageDone triggers differ structurally —
# valid_target Typed[Creature] vs Player), but project.py drops valid_target's TYPE
# onto the Trigger today, so the two recipients are indistinguishable in the projected
# IR (both scope='any', subject=None). The recipient discriminator survives byte-
# identically in the joined-face oracle ("to a creature" vs "to a player/an opponent/
# each opponent"), and the deleted regexes only ever matched single clauses (no `.`/`;`/
# `\n` inside the connect phrase), so a FLAT-text mirror reproduces the per-clause regex
# firing set exactly (commander-legal corpus: regex==mirror, 0 lost, 0 over-fire). These
# mined regexes survive as shared constants so signals._IR_KEPT_DETECTORS reuses each for
# the kept mirror, signal_specs hand-registers the serve reusing it, and the voltron PLAN
# mirror in _signals_regex reuses the OR of both — so serve / mirror / silence never
# drift. SWEEP_LABELS still carries the human label rows. CR 510.1c / 510.2.
COMBAT_DAMAGE_TO_CREATURE_REGEX = r"deals combat damage to (?:a|another|one or more) creatures?\b|whenever [^.]*deals combat damage to (?:a|another) creature"
COMBAT_DAMAGE_TO_OPP_REGEX = (
    "deals? combat damage to (?:a player|each opponent|an opponent|that player)"
)
# The NARROW second producer of combat_damage_to_opp the regex path carried alongside
# the SWEEP row (it lived in _signals_regex, not a SWEEP_DETECTORS row): a double-strike
# grant to your ATTACKING team (Raphael, Blade Historian, Berserkers' Onslaught) makes
# attackers connect with players TWICE — a combat-damage-to-player payoff whose oracle
# never says "deals combat damage to a player". It fired LOW confidence (it does NOT feed
# has_other_plan), and its 3 cards are disjoint from the COMBAT_DAMAGE_TO_OPP_REGEX set,
# so the kept mirror reproduces it as a third byte-identical _IR_KEPT_DETECTORS row (same
# low confidence) to keep the migration loss-free. Pinned here so mirror / serve reuse it.
COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX = (
    "attacking creatures you control have[^.]*double strike"
)
# ADR-0027 β — the power-as-damage cluster (creature_ping + damage_equal_power)
# migrated to the Card IR. Both SWEEP_DETECTORS rows are deleted: every power-scaling
# damage card now carries a cat=="damage" Effect with amount.op=="power" (the d6620ac
# projection unlock), so each key fires from a STRUCTURAL recipient/doer arm in
# extract_signals_ir PLUS a byte-identical _IR_KEPT_DETECTORS mirror of its exact
# deleted regex (the mirror recovers the projection-gap tail phase can't reach). These
# mined regexes survive as shared constants so signals reuses each for BOTH the kept
# word mirror and the voltron PLAN mirror, and signal_specs hand-registers the serve
# pool reusing it — so serve / detector / silence never drift. SWEEP_LABELS still
# carries the human label rows.
CREATURE_PING_REGEX = "(?:target |another target )?[A-Z][a-z]+ you control deals damage equal to its power to|deals damage equal to its power to (?:another )?target|deals damage to itself equal to its power|target creature deals damage [^.]*equal to its power"
DAMAGE_EQUAL_POWER_REGEX = "deals? damage[^.]*equal to (?:its|that creature.s|[^.]*) power[^.]*to (?:any target|target|each opponent|that player|target player)"
# ADR-0027 β — cost_reduction migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here so signal_specs hand-registers the
# serve pool reusing it (SWEEP_LABELS keeps the human label). The serve only needs a
# discount-EXPLOITING search anchor; the lane's firing now comes from the IR arm +
# _COST_REDUCER_MIRROR (in _signals_ir), not this regex.
COST_REDUCTION_REGEX = "spells?[^.]*cost \\{[wubrg]\\}[^.]*less to cast|cost \\{w\\}, \\{u\\}, \\{b\\}, \\{r\\}, or \\{g\\} less|cost \\{[wubrgc\\d]\\}+ less to cast|cost \\{?\\d+\\}? less to activate|(?:cards you drew this turn|abilities you activate)[^.]{0,40}?cost \\{?\\d|costs? \\{?\\d+\\}? less to cast for each|cost \\{?\\d+\\}? less for each"
# ADR-0027 β — global_ability_grant migrated to the Card IR; its SWEEP_DETECTORS row
# is deleted but the EXACT mined regex survives here so signal_specs hand-registers the
# serve pool reusing it (SWEEP_LABELS keeps the human label). The serve only needs a
# grant-EXPLOITING search anchor; the lane's firing now comes from the IR arm (the
# board_grant + counter_kind="grant_ability" marker in _signals_ir), not this regex.
GLOBAL_ABILITY_GRANT_REGEX = 'all (?:artifacts|creatures|lands|permanents) have \\"|creatures? you (?:own|control) have \\"'
# ADR-0027 β — keyword_grant_target migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here so signal_specs hand-registers the
# serve pool reusing it (SWEEP_LABELS keeps the human label) and the voltron PLAN mirror
# in _signals_regex reuses it. The serve only needs a grant-EXPLOITING search anchor (the
# creatures worth granting evasion/protection to); the lane's firing now comes from the
# IR arm (the single_target_grant marker in _signals_ir — project._single_target_keyword_
# grant_markers), not this regex.
KEYWORD_GRANT_TARGET_REGEX = "target creature (?:you control )?(?:gains?|gets [+\\-][0-9x]/[+\\-][0-9x] and gains?) (?:deathtouch|trample|flying|menace|vigilance|double strike|first strike|lifelink|haste|hexproof|indestructible|protection|reach|ward|shroud)"
# ADR-0027 β — activated_ability migrated regex→Card IR. The lane is a card whose ENGINE
# is a MEANINGFUL activated ability (the {T}:/{Q}: or generic-mana-cost ability a tap-
# engine commander deck supports with cost reducers / untappers / ability copiers). The
# EXACT deleted _DETECTORS regex survives here as the byte-identical voltron PLAN mirror
# (it fired high-confidence scope 'you', feeding has_other_plan) — see
# _ACTIVATED_ABILITY_PLAN_MIRROR in _signals_regex. The lane's FIRING now comes from the
# structural arm in extract_signals_ir (an Ability kind=='activated', cost shape tap/
# untap/genericmana, >=1 NON-ramp/attach effect — the is_mana_ability + SIDECAR-v15
# genericmana discriminators kill the land/rock/dork flood the bare cost-shape regex
# matched). The serve spec is its OWN hand-registered curated search pool (signal_specs)
# — independent of this regex, like gain_control. CR 602.1a / 903.10a.
ACTIVATED_ABILITY_REGEX = (
    "\\{t\\}\\s*[,:]|\\{q\\}\\s*[,:]|\\{(?:\\d+|x)\\}[^.\\n]{0,18}:"
)
# ADR-0027 β — debuff_matters migrated to the Card IR; both deleted regex producers
# (the SWEEP row + the Maha opponent-shrink _DETECTORS row) survive here as shared
# constants. The structural arm fires from the projection's negative-pump (factor<0) /
# non-self m1m1 Effects; these regexes back the byte-identical _IR_KEPT_DETECTORS
# mirror (the "gets -N/-N until end of turn" / "-X/-X" tail that projects amount==None),
# the voltron PLAN mirror, and the hand-registered serve in signal_specs — so serve /
# detector / silence never drift. SWEEP_LABELS keeps the human label.
DEBUFF_SWEEP_REGEX = "(?:other [a-z]+ creatures|nonblack creatures|all creatures|creatures) get -\\d/-\\d|gets? -\\d/-\\d until end of turn|gets -0/-x|gets -x/-x|creatures? (?:[^.]{0,40})?get -[0-9x]/-[0-9x]|put a -1/-1 counter on target|put (?:a|one|two|x|\\d+) -1/-1 counters? on|creatures? (?:target player|an opponent|your opponents|each opponent)[^.]*controls?[^.]*base power and toughness [0-2]/[0-2]"
DEBUFF_MAHA_REGEX = (
    "creatures your opponents control (?:have base (?:power|toughness)|get -)"
)
# ADR-0027 β — pump_matters migrated to the Card IR; its SWEEP_DETECTORS row is
# deleted but the EXACT mined regex survives here as a shared constant. This is a
# DISCRIMINATOR lane (a POSITIVE single-target combat-trick buff: "target creature
# gets +N/+N"), but the v9 projection cannot structure it: phase drops the value of
# every target-creature pump to amount==None (the +N/+N lives only in the raw), and
# it carries no temporal marker, so a combat trick (Giant Growth's "+3/+3 until end
# of turn") is structurally indistinguishable from a -1/-1 debuff (Festering Goblin,
# same pump_target/subj=Creature/amt=None shape) and from a permanent buff. The only
# clean positive-single-target structural form phase DOES carry — a positive-factor
# pump on an EnchantedBy/EquippedBy subject (auras/equipment, factor>0) — is the
# SEPARATE voltron/suit-up lane (signal_specs' "equipment/auras … suit up and buff
# your attackers" avenue), so firing it here would be scope creep, not recall. So
# this lane is genuinely UNSTRUCTURABLE as a positive discriminator: the regex itself
# IS the discriminator, and the lane rides a byte-identical _IR_KEPT_DETECTORS mirror
# of this exact regex (the mirror, the voltron PLAN mirror, and the hand-registered
# serve / _PUMP_EXTRA SubAvenue in signal_specs all reuse it — so serve / detector /
# silence never drift). SWEEP_LABELS keeps the human label. CR 122.1b / 903.10a.
PUMP_MATTERS_REGEX = "target (?:[a-z]+ )*creature(?: you control)? gets \\+[0-9x]/\\+[0-9x]|target [A-Z][a-z]+ you control gets \\+|target creature(?: you control)? gets \\+[\\dxX]"
# ADR-0027 β — variable_pt migrated to the Card IR; its SWEEP_DETECTORS row is deleted
# but the EXACT mined regex survives here so signal_specs hand-registers the serve pool
# reusing it (SWEEP_LABELS keeps the human label). The lane's firing now comes from the
# IR arm (a `characteristic_pt` Effect — phase's dropped self-CDA static re-surfaced by
# project._self_cda_marker, SIDECAR v10, PLUS the oracle-text CDAs supplement._CDA_PT
# already caught) and the NARROWED _VARIABLE_PT_MIRROR (the token-borne */* + change-
# base-self tail phase can't structure as a self-CDA), NOT this full regex. The serve
# only needs a build-around search anchor (cards that FILL the resource a */* scales
# with). CR 604.3.
VARIABLE_PT_SWEEP_REGEX = "power and toughness are each equal to(?: the (?:total )?number of)?|power(?: and toughness)? (?:is|are)(?: each)? equal to (?:twice )?the (?:total )?number of|equal to (?:twice )?the (?:total )?number of cards in (?:your|their|the|all) [^.]*hand|change [^.]*base power and toughness"

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
# cheapest correct path. The mirror, the voltron PLAN mirror, and the hand-registered
# serve / _MANA_AMP_EXTRA-bearing spec in signal_specs all reuse this one constant, so
# serve / detector / silence never drift. SWEEP_LABELS keeps the human label. No arm
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

# ADR-0027 β: token_copy_matters migrated to the Card IR via a kept-mirror — the
# deleted _HAND_FLOOR producer is pinned here byte-identically so the serve spec, the
# _TOKEN_COPY_MATTERS_MIRROR kept detector (_signals_ir), and the
# _TOKEN_COPY_MATTERS_PLAN_MIRROR voltron gate (_signals_regex) all share ONE source.
# Matched reminder-STRIPPED: a token-COPY maker / populate / token-DOUBLER payoff.
# The `\bpopulate\b` arm covers CR 702.95 (populate IS a token copy); the "twice that
# many … tokens" arm credits token DOUBLERS (Adrix and Nev, Mondrak — they fork
# token-copy spells). NOT a structural CopyTokenOf/Populate arm: phase structures those
# (421 cards) but the 80-card struct-only delta is 100% reminder-text SELF-copies
# (Embalm/Eternalize/Offspring/Double-team) the reminder-stripped regex excludes.
# CR 702.95 / 707.
TOKEN_COPY_MATTERS_REGEX = "tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|create a token that's a copy|\\bpopulate\\b|twice that many[^.]*tokens?"

# ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror — the UNION of the
# two deleted _HAND_FLOOR producers is pinned here byte-identically so the
# _TOKENS_MATTER_MIRROR kept detector (_signals_ir), the _TOKENS_MATTER_PLAN_MIRROR
# voltron gate (_signals_regex), and the serve spec (signal_specs) all share ONE source.
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
# registered in signal_specs.py with its own (independent) curated search regex.
# CR 603.10a (entered this turn) / 506.4 / 509 (attacking creatures).
ENTERED_ATTACKER_REGEX = "(?:deals combat damage|attacks)[^.]*entered (?:the battlefield )?this turn|entered (?:the battlefield )?this turn[^.]*(?:attacks|deals combat damage)"

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
# characteristic). The serve spec stays hand-registered in signal_specs.py with its own
# (broader) curated search regex, independent of this detector.
COLOR_CHANGE_REGEX = (
    "becomes the color of your choice|becomes? (?:the color|all colors)"
)

# ADR-0027 β: animate_artifact migrated to the Card IR via a byte-identical kept-mirror —
# the deleted SWEEP producer is pinned here so the _ANIMATE_ARTIFACT_MIRROR kept detector
# (_signals_ir), the _ANIMATE_ARTIFACT_PLAN_MIRROR voltron gate (_signals_regex), and the
# hand-registered serve (signal_specs) share ONE source. NOT a structural arm: the lane
# is "artifacts become creatures" (Karn Silver Golem, March of the Machines, Ensoul
# Artifact, Tezzeret the Seeker, Vehicle-crew animation), and phase parses it three
# INCONSISTENT ways — base_pt_set/board_grant over an Artifact subject (March/Ensoul/
# Tezzeret the Seeker), a becomes_type{Artifact} grant (Karn Silver Golem/Karn's Touch),
# or a base_pt_set with subject=None (Karn's Touch's spell clause, every "target artifact
# becomes a N/N artifact creature" whose subject phase drops). The pre-existing
# cat=='animate' & 'Artifact'-subject arm fires on ZERO commander-legal cards (phase
# never tags artifact-animation `animate`); a base_pt_set/board_grant/becomes_type-over-
# Artifact arm either 90%-OVER-FIRES (47 ir_only: "becomes an artifact" type-conferral —
# Liquimetal Coating/Memnarch/Argent Mutation; artifact-creature ANTHEMS — Galazeth/Food
# Fight/Fountain Watch; "Artifacts are Foods/Clues/Equipment" — Ragost/Senator Peacock/
# Dan Lewis) or, narrowed to drop those, LOSES 48 core animators (every Vehicle-crew
# "becomes an artifact creature" + the subject=None spells). The artifact-animation is
# NOT structurally separable from generic become / type-conferral, so the lane rides a
# byte-identical mirror of this exact regex (commander-legal corpus: regex==mirror, 67/67
# genuine vs Scryfall oracle, 0 over-fire). CR 110.1 / 305.7 (Vehicles / noncreature
# artifacts gaining the creature type) / 613 (layer-4 type-changing). The lane's `[^.]*`
# arms never cross a sentence, so the flat-text mirror == the per-clause SWEEP firing set.
# SWEEP_LABELS keeps the human label; the serve stays hand-registered in signal_specs
# reusing this constant.
ANIMATE_ARTIFACT_REGEX = "(?:target |each )?(?:noncreature )?artifact(?:s)? (?:you control )?(?:becomes?|are|become) (?:an? )?(?:artifact )?creature|becomes? an artifact creature|(?:artifact or land|target artifact|noncreature artifact|artifact you control)[^.]*becomes? a[^.]*creature"

# ADR-0027 β: ability_copy migrated to the Card IR via a byte-identical kept-mirror.
# ONE pinned source the _ABILITY_COPY_MIRROR kept detector (_signals_ir), the
# _ABILITY_COPY_PLAN_MIRROR voltron gate (_signals_regex), and the serve spec
# (signal_specs) all reuse — the EXACT deleted SWEEP_DETECTORS regex. The lane is the
# "Ability copy" build-around: a card that COPIES an activated/triggered ability
# (Strionic Resonator, Lithoform Engine, Rings of Brighthearth, Illusionist's/
# Battlemage's Bracers, Kurkesh, Riku-ability arm) OR a "you may copy it" spell/
# adventure self-copy (Chancellor of Tales, Tawnos the Toymaker, Donal), PLUS the
# ability-GRANTERS that import another permanent's whole activated-ability suite
# ("has all/the activated abilities of …" — Necrotic Ooze, Experiment Kraj, Mairsil,
# Myr Welder, Marvin, Skill Borrower, Conspicuous Snoop). 51 commander-legal.
#
# STRUCTURAL ARM REJECTED — needs a projection change this batch is forbidden to make.
# phase parses every copy effect to ONE undifferentiated `spell_copy` Effect category:
# Strionic's "Copy target triggered ability", Lithoform's "Copy target instant or
# sorcery spell", and Twincast's "Copy target spell" all flatten to `spell_copy` with
# no spell-vs-ability discriminator in the Effect (the copy TARGET is dropped). So a
# `category == "spell_copy"` arm fires on 303 commander-legal — OVER-FIRING 272 (90%)
# on the spell-copy half NOT in this lane (Twincast, Reverberate, Fork, Reiterate,
# Dual Casting, the Casualty/Conspire/Replicate keyword cards, Kalamax-spell) — and it
# STILL MISSES the 20 ability-GRANTERS (Necrotic Ooze / Experiment Kraj / Mairsil:
# phase parses "has all activated abilities of" as grant_keyword/board_grant, NOT
# spell_copy). The only way to split the lane structurally is a phase projection that
# tags the copy target (spell vs ability) — DEFERRED (FORBIDDEN to touch _card_ir/ in
# this parallel batch; re-reading e.raw to discriminate is regex-by-another-name, not a
# structural arm: it stays leaky, 27 regex-miss + 11 spurious). 90% over-fire + a hard
# projection blocker → rejected (cf. color_change's animate arm 256-vs-24).
#
# CHOSEN PATH 2 (kept-mirror). The deleted regex is precise (51/51 genuine, 0
# over-fire), so the lane rides it byte-identically via _ABILITY_COPY_MIRROR
# (_signals_ir) over the reminder-stripped kept_oracle. Every arm is clause-local (no
# `[^.]` crossing a sentence), so the full-text mirror == the deleted per-clause SWEEP
# union (commander-legal: regex==mirror, 51==51, 0 lost, 0 over-fire — a behavior-
# neutral re-home). The serve stays hand-registered in signal_specs.py reusing this
# pinned regex (SWEEP_LABELS keeps the human label). CR 706.10 (copying an ability) /
# 113.2 (granted abilities) / 706.2.
ABILITY_COPY_REGEX = (
    "copy (?:that|this|the|target) "
    "(?:activated |triggered |activated or triggered )?ability"
    "|you may copy (?:it|that ability)"
    "|has all activated abilities of|has the activated abilities of"
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
# hand-registered in signal_specs.py with its own curated search regex, independent of
# this detector.
GAIN_CONTROL_REGEX = "gain control of"

# ADR-0027 β: toughness_combat migrated to the Card IR via a byte-identical kept-mirror.
# TWO deleted producers feed the key, joined here into ONE pinned source the
# _TOUGHNESS_COMBAT_MIRROR kept detector (_signals_ir), the
# _TOUGHNESS_COMBAT_PLAN_MIRROR voltron gate (_signals_regex), and the serve spec
# (signal_specs) all reuse: (1) the deleted SWEEP detector — the Doran / Assault
# Formation / High Alert / Huatli combat-redirect "assigns combat damage equal to its
# toughness/mana value rather than its power | deals damage equal to its toughness"
# (22 commander-legal); (2) the deleted inline _signals_regex _DETECTORS producer — the
# broader toughness-as-VALUE payoff "X is/equals … toughness | equal to … toughness"
# (gain life / deal damage / draw / X/X token / lose life keyed on a creature's
# toughness — Geralf, Last March of the Ents, Angelic Chorus; a SUPERSET, lane == 133
# commander-legal). NOT a structural arm: phase parses the Doran clause as an
# AssignDamageFromToughness modification but project._project_static_mods has no arm,
# so it DROPS the static on every multi-ability face (Assault Formation / High Alert /
# Huatli / Arcades) — the structural `combat_damage_mod` category fires on only 21,
# MISSES 129/133 of the lane (no structural form for the 111 value-payoffs), AND
# OVER-FIRES 17/21 (81%) on "deal damage equal to its POWER" combat redirects /
# punches (Laccolith *, Farrel's *, Master of Cruelties). The deleted regexes are
# precise (133/133 genuine, 0 over-fire), so the lane rides their OR byte-identically.
# Both arms are clause-local (no `[^.]` crossing a sentence), so the full-text mirror ==
# the deleted per-clause union (commander-legal: regex==mirror, 0 lost, 0 over-fire).
# The serve stays hand-registered in signal_specs.py (high-toughness / Defender bodies).
# CR 510.1c / 122 / 604.3.
TOUGHNESS_COMBAT_REGEX = (
    r"assigns? combat damage equal to its (?:toughness|mana value) "
    r"rather than its power|deals damage equal to its toughness"
    r"|\bx (?:is|equals?) [^.]{0,40}\btoughness\b"
    r"|equal to [^.]{0,40}\btoughness\b(?! are each)"
)
# ADR-0027 β: ltb_matters (leaves-the-battlefield payoffs — sacrifice/blink/bounce
# fodder to trigger a permanent leaving) migrated to the Card IR. The deleted
# SWEEP_DETECTORS row's EXACT regex is pinned here so the migrated lane's narrowed
# kept-mirror (_LTB_MATTERS_MIRROR in _signals_ir), the has-other-plan voltron gate
# (_LTB_MATTERS_PLAN_MIRROR in _signals_regex), and the serve spec all share ONE
# source. The lane fires from a STRUCTURAL arm (a `leaves` trigger — phase's
# `LeavesBattlefield` mode, projected event=='leaves' @ SIDECAR v11 — with a real
# OTHER-permanent subject leaving the battlefield, a +9 recall gain over this regex:
# DFC back faces Luminous Phantom / Aang at the Crossroads, bounce payoffs Azorius
# Aethermage / Warped Devotion / Tameshi the front-face-only regex missed) PLUS this
# regex run PER-CLAUSE as the narrowed mirror for the Revolt "a permanent left the
# battlefield this turn" conditions + the self-LTB payoffs phase leaves as a SelfRef
# trigger / static condition. The mirror is VETOED per-clause by the O-Ring self-LTB-
# EXILE form ("exile … until ~ leaves the battlefield" — Banishing Light / Static
# Prison / Assimilation Aegis): that "until ~ leaves" is the END of a removal LOCK, not
# a leaves-MATTERS payoff (it already routes to exile_until_leaves), so the 93 O-Ring
# over-fires this regex caught are DROPPED (100% over-fire vs Scryfall oracle, 0 genuine
# payoff lost). SWEEP_LABELS keeps the human label; the serve is hand-registered in
# signal_specs.py reusing this constant (with its own O-Ring serve_not veto). CR
# 603.6e / 700.4 (leaves the battlefield ⊃ dies).
LTB_MATTERS_SWEEP_REGEX = (
    "a permanent (?:you controlled )?left the battlefield "
    "(?:under your control )?this turn"
    "|whenever [^.]*(?:leaves the battlefield|leave the battlefield)"
    "|when [^.]* leaves the battlefield"
)
# ADR-0027 β: self_counter_grow (a creature that puts +1/+1 counters on ITSELF to grow
# — adapt/monstrosity/renown, Saga chapter "put N +1/+1 on ~", "enters with / put a
# +1/+1 counter on this creature", multi-pay self-pump) migrated to the Card IR. The
# deleted SWEEP_DETECTORS row's EXACT regex is pinned here so the migrated lane's
# narrowed kept-mirror (_SELF_COUNTER_GROW_MIRROR in _signals_ir) and the has-other-plan
# voltron gate (_SELF_COUNTER_GROW_PLAN_MIRROR in _signals_regex) share ONE source. The
# lane fires from a STRUCTURAL arm (a place_counter carrying the SelfRef self-anchor
# marker project.py recovers @ SIDECAR v12 — phase carries the anchor as the PutCounter
# target=={type:SelfRef}, or implies it for adapt/monstrosity/renown — a +503 ir_only
# recall gain over this regex: the regex only matched the pronouns "on him/her/it/this",
# so it MISSED every body that names itself ("put a +1/+1 counter on Lazav / Garza Zol /
# Kyler", the by-name self-grow). The regex's loose "on it" arm 100%-over-fires onto
# OTHER-creature counter placements ("enchanted creature attacks, put a +1/+1 on it" —
# Ordeal of Purphoros; "if it's an Angel, put two +1/+1 on it" — Defy Death; the go-wide
# counter anthems The Great Henge / Railway Brawler; combat payoffs Necropolis Regent /
# Stensia Masquerade), the doer the IR's SelfRef gate correctly excludes — so the mirror
# is NARROWED to the SELF-ANCHORED arms only (`on (?:him|her|itself|this creature)` +
# multi-pay "put that many on this creature"), recovering the 14 phase-parse-gap self-
# growers (the Adversary multi-pay cycle Spectral/Primal/Bloodthirsty, Stormwild
# Capridor's damage-prevention static, Scarlet Spider's ParentTarget branch) while
# DROPPING the 103 "on it" over-fires. The self-power-scaling commander cross-open ("X
# is ~'s power" → a self-power-scaler wants +1/+1 sources, Esper Sentinel / Velomachus)
# rode a low-confidence _DETECTORS add, also re-homed to the narrowed mirror. SWEEP_LABELS
# keeps the human label; the serve is hand-registered in signal_specs.py. CR 122.1 /
# 614.12 / 701.43 (adapt) / 701.13 (monstrosity) / 702.111 (renown).
SELF_COUNTER_GROW_SWEEP_REGEX = (
    "enters with (?:x|\\d+|a|an|one|two|three) \\+1/\\+1 counters? on "
    "(?:him|her|it|itself|this)"
    "|put (?:a|one|two|three|x|\\d+) \\+1/\\+1 counters? on "
    "(?:him|her|it|itself|this creature)\\b"
    "|put that many \\+1/\\+1 counters? on (?:him|her|it|itself|this creature)"
)
# ADR-0027 β: counter_distribute (a BOARD-WIDE +1/+1 counter spread — "put a +1/+1
# counter on each creature you control", "distribute N +1/+1 counters among target
# creatures", "each of [up to N] target creatures", "creatures … enter with N additional
# +1/+1 counters") migrated to the Card IR. The deleted SWEEP_DETECTORS row's EXACT
# regex is pinned here so the has-other-plan voltron gate (_COUNTER_DISTRIBUTE_PLAN_MIRROR
# in _signals_regex) re-supplies the silence byte-identically. The lane fires from a
# STRUCTURAL arm (a place_counter carrying the MassEach marker project.py recovers @
# SIDECAR v18 — phase carries the mass distinction in the effect TYPE PutCounterAll, which
# _EFFECT_CATEGORY folds to place_counter; +84 recall over this regex's literal "each
# creature you control" arm: it catches every tribal/restricted mass — "each Vampire /
# Cleric / legendary creature you control" — the regex missed) + the NARROWED
# _COUNTER_DISTRIBUTE_MIRROR (this regex's mass/distribute/each-of arms PLUS enters-with-
# ADDITIONAL, MINUS the loose plain "enters with N +1/+1 counters on it" arm — 329 over-
# fires onto SELF-grow creatures Triskelion / Endless One / Modular / Graft, which are
# self_counter_grow, not board spread; the lane is board-wide-only). The serve is hand-
# registered in signal_specs.py (a board-wide serve regex that, like the IR, catches
# tribal mass while excluding single-target). SWEEP_LABELS keeps the human label.
# CR 122.1 / 122.6.
COUNTER_DISTRIBUTE_SWEEP_REGEX = (
    "put (?:a|one|two|\\d+|x) \\+1/\\+1 counters? on each (?:other )?creature you control"
    "|distribute \\+1/\\+1 counters"
    "|put (?:a |one or more |the same number[^.]*?)\\+1/\\+1 counters? on each of"
    "|enters with (?:a|an|one|two|three|x|\\d+)(?: additional)? \\+1/\\+1 counters? on"
    "|enters with that many additional"
)
# The board-wide SERVE regex: like the deleted detection regex but with the loose plain
# self-enters arm DROPPED (a self-grower doesn't spread counters) and the "each <tribe>
# you control" tribal-mass form added (the structural arm catches it via PutCounterAll;
# the regex serve mirrors that breadth). Excludes single-target "on target creature you
# control" (New Horizons), keeping the lane board-wide-only (test_signal_specs
# .test_counter_distribute_is_board_wide_only).
COUNTER_DISTRIBUTE_SERVE_REGEX = (
    "put (?:a|one|two|\\d+|x) \\+1/\\+1 counters? on each "
    "(?:other )?(?:[a-z]+ )*creatures? (?:you|each|that opponent|an opponent) control"
    "|put (?:a|one|two|\\d+|x) \\+1/\\+1 counters? on each (?:attacking|legendary) creature"
    "|distribute [^.]{0,30}?\\+1/\\+1 counters"
    "|put (?:a |one or more |the same number[^.]*?)\\+1/\\+1 counters? on each of"
    "|(?:enters?|enter) with (?:a|an|one|two|three|x|\\d+) additional \\+1/\\+1 counters? on"
    "|enters with that many additional"
    "|support (?:x|\\d+)"
)

# ADR-0027 β — damage_to_opp_matters migrated to the Card IR. The exact deleted
# _DETECTORS regex (a "whenever ~ deals (noncombat) damage to a PLAYER / opponent"
# connect-payoff — ANY damage, NOT the literal "combat damage" the combat_* keys
# require, per the rules-lawyer audit: the connect-trigger axis for self-source
# pingers / evasion the tribe/combat keys miss). Pinned here as a shared constant so
# signals._IR_KEPT_DETECTORS reuses it for the kept mirror (the granted-ability / ETB-
# burst tail phase can't structure as a DamageDone trigger), the voltron PLAN mirror in
# _signals_regex reuses it, and signal_specs hand-registers the serve reusing it — so
# serve / mirror / silence never drift. The structural projection (SIDECAR v13's
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
# label; the serve stays hand-registered in signal_specs.py (its own curated search
# regex). CR 614.9 (redirection replacement) / 615 (prevention).
DAMAGE_REDIRECT_REGEX = (
    "the next (?:\\d+|x) damage [^.]*would be dealt[^.]*(?:is )?dealt to [^.]*instead"
    "|that damage is dealt to [^.]*instead|deal that damage to [^.]*instead"
)

# ADR-0027 β: free_cast migrated to the Card IR via a byte-identical kept-mirror
# (_FREE_CAST_MIRROR in _signals_ir). The SWEEP_DETECTORS row is deleted; the EXACT
# regex is pinned here, reused by the IR mirror, the has_other_plan plan-mirror, and the
# hand-registered serve spec (signal_specs). SWEEP_LABELS keeps the label.
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
# branches are pinned here (reused by the IR mirror, the has_other_plan
# _DEATH_MATTERS_PLAN_MIRROR, and the hand-registered serve spec); the mirror ALSO runs
# the two substring-AND branches ("whenever"&"dies", "dying"&"trigger") the deleted
# lambda did, which no single regex expresses. NO SWEEP row (death_matters was a clause-
# scoped baseline widen, never swept). NO sidecar bump (the v11 projection already emits
# the `dies` trigger event). CR 700.4 / 603.6e (dies ⊂ leaves the battlefield).
DEATH_MATTERS_REGEX = (
    r"whenever [^.]*(?:creatures?|permanents?|tokens?|they|control) die\b"
    r"|creatures? (?:that )?died this turn"
    r"|creature[^.]*\bdied\b[^.]*this turn"
)
# ADR-0027 — artifacts_matter (the ARTIFACTS go-wide / matters axis: a card that cares
# about your artifact population — "artifacts you control" anthems, "for each artifact
# you control" count payoffs, affinity / metalcraft / improvise, artifact ETB / cast
# triggers, artifact tutors / recursion / sac-outlets / token-makers — affinity per
# CR 702.41, metalcraft CR 207.2c, artifact tokens CR 205.3g). MIGRATED to the Card IR
# via the STRUCTURAL arms (the `_TYPE_MATTERS_LANE` count/grant/trigger DOERs, the
# `_ARTIFACT_TOKEN_SUBTYPES` maker/sac arm, the type-gate condition arm, and the
# type_line membership arm — all already present in extract_signals_ir) PLUS a NARROWED
# kept-mirror of the deleted oracle-regex producer. NO sidecar bump (the v20 projection
# already structures the artifact filters / triggers / token subtypes these arms read).
#
# NARROWED (signals-only over-fire fix): the deleted producer's bare `\baffinity\b`
# branch over-fired on EVERY affinity-for-NON-artifact card ("Affinity for snow lands"
# Icebreaker Kraken, "Affinity for creatures" Argivian Phalanx, "Affinity for Birds"
# Bartz and Boko, "Affinity for Slivers" Thrumming Hivepool — 22 commander-legal
# over-fires verified vs Scryfall oracle, NONE an artifacts deck). The narrowed branch
# `affinity for artifacts` keeps the real affinity-matters bodies (conferred "spells you
# cast have affinity for artifacts" — Sami; the Golems whose Artifact type_line still
# opens the lane via membership) while dropping the 22. The structural IR arm
# add()-dedups its +325 ir_only recall GAIN (the Food/Clue/Treasure-subtype sac payoffs
# and DFC back-face artifact-recursion the brittle oracle regex MISSED).
#
# Floor-disabled residual after the swap (commander-legal, _IR_FLOOR_LANES=frozenset()):
# regex_only==22 (ALL the affinity-for-other over-fire, 0 genuine recall lost),
# ir_only==325 (genuine gain). SCOPE PARITY holds (both fire scope 'you' only). The
# SWEEP_DETECTORS "if you control an artifact" row is KEPT (len stays >=36); the mirror
# UNIONs it (the deleted _HAND_FLOOR producer + the kept SWEEP regex run together
# per-clause). artifacts_matter is NOT in _IR_FLOOR_LANES (floor-mirror-dep == 0).
ARTIFACTS_MATTER_REGEX = (
    r"\bartifacts? you control\b"
    r"|artifact creatures? you control"
    r"|for each artifact you control"
    r"|whenever an? artifact (?:you control )?enters"
    r"|whenever you cast an artifact|affinity for artifacts"
    r"|artifact (?:card|spell)[^.]*(?:from|in)[^.]*graveyard"
    r"|search [^.]*\bfor [^.]*artifact[^.]*card|noncreature artifact card"
    r"|put (?:an?|that|up to \w+) artifact cards?[^.]*"
    r"(?:into your hand|onto the battlefield)"
    r"|\bimprovise\b"
    r"|sacrifices? (?:an?|another|two|three|x|\d+) artifacts?\b"
    r"(?!,? (?:or )?(?:an? )?(?:creature|enchantment|land|permanent))"
    r"|abilit(?:y|ies) of (?:an? )?artifacts?\b"
    r"|becomes? an? artifact\b"
    r"|create[^.]*\b(?:treasure|food|clue|blood|gold|map|powerstone"
    r"|junk|incubator|lander|mutagen)\b[^.]*token"
    r"|\binvestigate\b"
    r"|\bmetalcraft\b"
    r"|search (?:your library )?for an?[^.]*artifact card"
    r"|reveal an artifact card"
    r"|if an artifact entered the battlefield under your control"
    r"|artifact,? instant,? and sorcery spells"
)
# ADR-0027 — enchantments_matter (the ENCHANTMENTS go-wide / matters axis: a card that
# cares about your enchantment population — "enchantments you control" anthems, "for each
# enchantment you control" count payoffs, constellation ("whenever an enchantment you
# control enters"), enchantress cast triggers, enchantment tutors / recursion-from-
# graveyard / hand-matters, and Role-token makers — Roles ARE Aura enchantments per
# CR 303.7 / 111.10j, Auras are enchantments per CR 205.2 / 303). MIGRATED to the Card IR
# via the STRUCTURAL arms (the `_TYPE_MATTERS_LANE` Enchantment count/grant/trigger DOERs,
# the Enchantment make_token / sac-payoff DOER, the type-gate condition arm, the becomes-
# Enchantment / type-recursion / type-tutor arms, the Aura-subtype "loose enchantments
# member" arm, and the type_line membership arm — all already present in
# extract_signals_ir, shared with artifacts_matter) PLUS a BYTE-IDENTICAL kept-mirror of
# the deleted oracle-regex producer. NO sidecar bump (the v20 projection already structures
# the enchantment filters / triggers / token subtypes these arms read).
#
# The structural arms ADD +95 ir_only recall the brittle oracle regex MISSED — the Licids
# that "become an Aura enchantment" (Gliding/Nurturing/Calming Licid …), the enchantment-
# creature / Aura / Glimmer token makers (Aerie Worshippers, Fated Intervention, Tunnel
# Surveyor), Aura recursion (Nomad Mythmaker, Retether, Storm Herald), enchantment tutors
# / recursion (Plea for Guidance, Triumphant Reckoning, Crystal Dragon // Rob the Hoard),
# affinity-for-enchantments (Brine Giant), single-type "sacrifice an enchantment" outlets
# (Faith Healer, Auratog, Phantatog), and "if you control an enchantment" conditions
# (Flutterfox, Blood-Cursed Knight, Lagonna-Band Elder) — every one a real enchantment-
# population care. The Bargain symmetric-sac gate (CR 702.166a, the shared arm landed by
# the artifacts pass) keeps the lane shut for the ~20 "sacrifice an artifact, ENCHANTMENT,
# or token" alt-cost cards (Torch the Tower, Beseech the Mirror) — those are GONE on this
# base, not over-fires. phase carries NO clean shape for the oracle-idiom family the
# deleted regex read (enchantment tutors / recursion-from-graveyard / "enchantment card in
# your hand" miracle-grant / Role-token makers), so the kept-mirror runs PER-CLAUSE over
# the reminder-stripped oracle, recovering all 15 byte-identically (Role-token makers
# Royal Treatment / Become Brutes — Roles ARE Aura enchantments; Yenna, Rite of Harmony's
# constellation, Aminatou's "enchantment card in your hand"). add() dedups vs the
# structural arm. There is NO dedicated enchantment SWEEP_DETECTORS row (unlike artifacts'
# "if you control an artifact" row), so the mirror is the deleted producer alone and
# SWEEP_DETECTORS stays at 36. enchantments_matter is NOT in _IR_FLOOR_LANES
# (floor-mirror-dep == 0 — a structural type-matters lane).
ENCHANTMENTS_MATTER_REGEX = (
    r"\benchantments? you control\b"
    r"|for each enchantment you control"
    r"|whenever an? enchantment (?:you control )?enters"
    r"|cast (?:an?|your (?:first|second)) enchantment"
    r"|search (?:your library )?for an?[^.]*enchantment card"
    r"|return [^.]*enchantment cards?[^.]*(?:graveyard|hand)"
    r"|enchantment cards? in your hand"
    r"|reveal[^.]*enchantment cards?[^.]*hand|put all enchantment cards"
    r"|create [^.]*\bRole token"
)
# ADR-0027 — attack_matters (the COMBAT-trigger / attacked-this-turn payoff axis: a
# card that CARES when a creature attacks — "whenever ~ attacks" triggers, the Raid /
# "attacked this turn" combat-count condition, the "attacking causes" Isshin form, and
# the team combat-keyword anthems) migrated to the Card IR via a STRUCTURAL arm + a
# BYTE-IDENTICAL kept-mirror. The structural `attacks`-TRIGGER arm + the `Attacking`
# filter-predicate arm in extract_signals_ir ADD +135 ir_only recall: the reminder-only
# attack triggers (Training / Mentor / Exalted / Mobilize creatures, whose "whenever ~
# attacks" lives ONLY in stripped reminder text) and the "Attacking creatures you
# control get …" anthems (Gruul War Chant, Goblin Oriflamme, Nobilis of War) the bare
# substring regex MISSED — all genuine attack payoffs. But phase carries NO clean
# `attacks` shape for the DOMINANT family: the DISJUNCTIVE "enters or attacks" /
# "attacks or blocks" trigger (Elder Gargaroth, Sun Titan, Grave Titan, Doran — phase
# collapses these to event='other'), the Raid "if you attacked this turn" CONDITION
# (Searslicer Goblin, Bloodsoaked Champion — no trigger at all), the `AttackedThisTurn`
# effect predicate ("untap all creatures that attacked this turn" — Relentless Assault,
# World at War), and "attacking causes" (Isshin). A structural-only migration would LOSE
# 394 genuine cards, so the lane ALSO rides this byte-identical regex (commander-legal
# corpus: post-IR ⊇ original-regex, 0 lost, +135 gained) run PER-CLAUSE, PLUS the one
# SUBSTRING-AND branch the deleted lambda ran on the lower-cased clause ("whenever" &
# "attack" — no single regex expresses a substring-AND), checked inline in
# extract_signals_ir. The two regex-expressible substring branches ("attacking causes",
# "attacked this turn") are pinned here. The 10 combat KEYWORDS the deleted
# _DIRECT_KEYWORD_SIGNALS rows mapped (battle cry / battalion / melee / boast / exert /
# myriad / bushido / annihilator / flanking / frenzy — whose attack condition lives in
# stripped reminder text, so neither the mirror nor the structural arm fires) move to
# the IR-only _IR_KEYWORD_MAP so the IR path still opens the lane for them. attack_matters
# was NEVER a SWEEP key, so no SWEEP row is touched (len stays >=36). NO sidecar bump
# (the v20 projection already emits the `attacks` trigger event + the Attacking filter
# predicate). NOT a voltron plan (an attacker IS the commander-damage plan), but the
# deleted producer fed has_other_plan when it fired HIGH, so a faithful reproduction (not
# a key add) restores the voltron silence in _signals_regex. CR 508 / 702.10.
ATTACK_MATTERS_REGEX = r"attacking causes|attacked this turn"
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
# ability repeatedly destroys lands — the Armageddon/Numot stax-LD plan, CR 305.6)
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
# the unmigrated IR land_destruction, so it never reached production; removal_matters'
# own land-subtype exclusion is independent of it). land_destruction was NEVER a SWEEP
# key, so no SWEEP row is touched (len stays >=36). NO sidecar bump. NOT a voltron plan
# key: the deleted cross-open fired LOW confidence and NEVER fed has_other_plan (which
# requires confidence=='high'), so dropping it leaks no commander-damage voltron tell
# (voltron delta 0) and NO _LAND_DESTRUCTION_PLAN_MIRROR is needed. CR 305.6 / 903.10a.
LAND_DESTRUCTION_REGEX = (
    r"destroy (?:up to (?:one|two|three|four|\w+) )?target lands?\b"
)
# ADR-0027 — creature_recursion (return a CREATURE card from a graveyard, to HAND or
# BATTLEFIELD: Raise Dead, Gravedigger, Reanimate, Hua Tuo, Meren — the "loop a single
# creature" build-around) migrated to the Card IR via a STRUCTURAL `reanimate` arm
# (recall GAIN) PLUS this BYTE-IDENTICAL kept regex. The deleted `_DETECTORS` producer
# fired forced scope 'you', HIGH conf, run PER-CLAUSE over the reminder-stripped oracle
# (304 commander-legal cards). The structural arm (`cat=='reanimate' and 'Creature' in
# ftypes` in extract_signals_ir) GAINS +160 cards the brittle "your graveyard" regex
# missed — the "from A graveyard" / "that player's graveyard" reanimation spells
# (Reanimate, Beacon of Unrest, Exhume) and the empty-top-level split/DFC halves — but
# phase carries NO clean structural shape for GY→HAND / GY→LIBRARY creature recursion
# (graveyard_recursion / topdeck_stack, NOT reanimate), so a structural-only migration
# would LOSE 132 genuine cards (Raise Dead, Gravedigger, Hua Tuo's GY→library, Meren,
# Kolaghan's Command's GY→hand mode). This constant, run PER-CLAUSE over the reminder-
# stripped `kept_oracle` in extract_signals_ir, recovers all 132 BYTE-IDENTICALLY
# (commander-legal, floor-disabled: mirror==regex==304, flat==per-clause, 0 miss, 0
# extra; the lone `[^.]*?` never crosses a clause). add() dedups vs the structural arm.
# DISTINCT from reanimator (GY→BATTLEFIELD only) and graveyard_matters (any self-GY
# care). creature_recursion was NEVER a SWEEP key, so no SWEEP row is touched (len stays
# 36). NO sidecar bump. The deleted producer fired HIGH conf scope 'you' and counted
# toward has_other_plan; because the migrated IR path is BROADER (464), the regex path
# keeps a byte-identical _CREATURE_RECURSION_PLAN_MIRROR over the reminder-stripped
# `text` (NOT _VOLTRON_SILENCING_PLAN_KEYS, which would over-silence the +160 recall-
# gain bodies) — voltron delta 0. CR 700.4 / 903.10a.
CREATURE_RECURSION_REGEX = (
    r"(?:return|put|choose) (?:target |a |another )?creature card"
    r"[^.]*?\b(?:in|from) your graveyard"
)
# ADR-0027 — land_sacrifice_matters (the land-SACRIFICE archetype axis: a card that
# pays an ongoing land-sac cost, draws/grows when lands hit the graveyard, or offers a
# repeatable "Sacrifice a land:" OUTLET — Gitrog, Titania, Slogurk, Zuran Orb, Sylvan
# Safekeeper, Squandered Resources; CR 701.16) migrated to the Card IR via a BYTE-
# IDENTICAL kept WORD MIRROR. phase carries NO structural form for this lane — over the
# commander-legal corpus (floor-disabled, by oracle_id) the structural sacrifice arm
# emits land_sacrifice_matters on ZERO cards (the you-sac arm at line ~5560 deliberately
# routes a land-ONLY sac subject AWAY from sacrifice_matters but never re-homes it to
# land_sacrifice — there is no `add("land_sacrifice_matters", ...)` anywhere in the
# structural IR), so the lane fired ONLY from this regex (66 commander-legal cards, all
# scope 'you', HIGH conf). The deleted producer was a per-card `_HAND_FLOOR` Detector run
# per-clause over the reminder-stripped, DFC-joined oracle; this constant, run FLAT over
# the same reminder-stripped `kept_oracle` in extract_signals_ir's _IR_KEPT_DETECTORS
# loop, is BYTE-IDENTICAL — the four arms' `[^.]*` anchors never cross a clause boundary
# and no card's match is split by a `;`/`\n` only (commander-legal: flat==per-clause==66,
# 0 gain, 0 loss). Distinct from land_destruction (DESTROY a land — CR 305.6) and
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
# ADR-0027 — extra_combats (the ADDITIONAL-COMBAT-PHASE archetype axis: a card that
# grants "after this [main] phase, there is an additional combat phase" — Aggravated
# Assault, Combat Celebrant, Seize the Day, Moraug, Aurelia, Scourge of the Throne,
# World at War, Najeela, Illusionist's Gambit; CR 505.1a / 720) migrated to the Card
# IR. phase DOES carry an accurate STRUCTURAL form: the `extra_combat` effect category
# fires extra_combats through the _DOER_EFFECT_KEYS doer loop (scope 'you', HIGH conf),
# covering 42 of the 43 commander-legal regex fires with ZERO over-fire (floor-disabled
# residual by oracle_id: both==42, regex_only==1, ir_only==0, 0 scope/conf mismatch).
# The single under-structured gap is Illusionist's Gambit ("After this phase, there is
# an additional combat phase") — phase folds the whole card into one `restriction`
# effect and never emits the `extra_combat` category, so the structural arm misses it.
# This EXTRA_COMBATS_REGEX (the EXACT deleted `extra-combats` theme PRESET pattern,
# `additional combat phase`) run FLAT over the reminder-stripped kept_oracle in
# extract_signals_ir's _IR_KEPT_DETECTORS loop (scope 'you', HIGH conf) recovers that
# gap byte-identically: the substring carries no parens and crosses no clause boundary,
# so flat==per-clause (commander-legal: flat-mirror==per-clause-regex==43, 0 gain/loss).
# The structural arm union the word mirror == 43 == the deleted regex producer EXACTLY.
# Distinct from extra_turns (CR 716 — take another turn), extra_upkeep / extra_draw_step
# (CR 501.1 — an additional BEGINNING phase; Shadow/Sphinx of the Second Sun say
# "additional beginning phase", NOT "combat phase", so the substring correctly skips
# them). extra_combats was NEVER a SWEEP key, so no SWEEP row is touched (len stays 36);
# only this CONSTANT is pinned here. NO sidecar bump. The deleted producer fired HIGH
# conf scope 'you' and so counted toward has_other_plan (it is NOT in _GENERIC_KEYS /
# _VOLTRON_COMPAT_KEYS), silencing the spurious commander-damage voltron tell on an
# extra-combat creature commander that is NOT a vanilla beater (Aurelia, Moraug,
# Najeela, Anzrag, Karlach). Because the IR re-supply IS this byte-identical union
# (IR==regex==43), the hybrid re-silences via _VOLTRON_SILENCING_PLAN_KEYS (signals.py)
# — no broadening, no over-silence — matching the land_sacrifice / draw_matters kept-
# mirror precedent; NO _EXTRA_COMBATS_PLAN_MIRROR is needed. CR 505.1a / 903.10a.
EXTRA_COMBATS_REGEX = r"additional combat phase"
# ADR-0027 — extra_turns (the TIME-WALK build-around axis: take-another-turn payoffs
# and enablers — Time Warp, Temporal Manipulation, Nexus of Fate, Magosi, Obeka, plus
# the per-extra-turn payoffs Wanderwine Prophets / Sage of Hours / Medomai; CR 500.7)
# migrated to the Card IR. The lane fires from the STRUCTURAL `extra_turn` effect-
# category arm (_DOER_EFFECT_KEYS, scope 'you', HIGH conf — already wired) PLUS this
# BYTE-IDENTICAL kept WORD MIRROR for the under-structured tail phase folds into another
# category. The deleted regex producer was the `extra-turns` theme PRESET
# (_PRESET_REGEX_SIGNALS) — a per-clause `re.search` of "take an (?:extra|additional)
# turn" over the reminder-stripped oracle, scope 'you', HIGH conf. The structural arm is
# BROADER (+8 ir_only: the buggy preset matches only the IMPERATIVE "Take an extra turn"
# and MISSES the 3rd-person "takes an extra turn" — Time Warp / Walk the Aeons / Beacon
# of Tomorrows / Karn's Temporal Sundering — and the "take TWO extra turns" form — Time
# Stretch / Teferi; all 8 ir_only are genuine extra-turn cards phase structures as an
# `extra_turn` effect, a recall GAIN). It is also NARROWER for 6 under-structured cards
# (regex_only) where phase folds "take an extra turn" into a SIBLING category and emits
# no `extra_turn` effect: Chance for Glory (grant_keyword carrier), Expropriate (vote),
# Ichormoon Gauntlet (a CONFERRED planeswalker ability), Ral Zarek / Stitch in Time
# (coin_flip), Ugin's Nexus (an exile replacement). This constant, run FLAT over the
# reminder-stripped `kept_oracle` in extract_signals_ir's _IR_KEPT_DETECTORS loop (scope
# 'you', HIGH conf), recovers those 6 BYTE-IDENTICALLY — the pattern has no `[^.]*`, so
# flat==per-clause, and reminder-stripping matches the producer (Perch Protection, whose
# "take an extra turn" lives ONLY in Gift reminder text, is correctly EXCLUDED). add()
# dedups the mirror vs the structural arm; the hybrid serves the UNION (50 = 36 both + 8
# structural recall-gain + 6 under-structured mirror). extra_turns was NEVER a SWEEP key,
# so no SWEEP row is touched (len stays 36); only this CONSTANT is pinned here. NO sidecar
# bump. VOLTRON: the deleted preset fired HIGH conf scope 'you' and so counted toward
# has_other_plan (it is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the
# spurious commander-damage voltron tell on a time-walk CREATURE commander whose ONLY
# high plan tell is extra_turns (Timestream Navigator, Lighthouse Chronologist, Wormfang
# Manta). Because the structural arm is BROADER (+8), _VOLTRON_SILENCING_PLAN_KEYS would
# OVER-SILENCE the recall-gain bodies (e.g. Eon Frolicker), so the regex path keeps a
# BYTE-IDENTICAL _EXTRA_TURNS_PLAN_MIRROR over the reminder-stripped `text` (NOT
# _VOLTRON_SILENCING_PLAN_KEYS) — matching the landfall / ramp_matters broader-IR
# precedent. CR 500.7 / 903.10a.
EXTRA_TURNS_REGEX = r"take an (?:extra|additional) turn"
# ADR-0027 β: lifegain_matters migrated to the Card IR via a byte-identical kept-
# mirror (_LIFEGAIN_MATTERS_MIRROR in _signals_ir). The deleted regex producers — the
# `_DETECTORS` registry row (the "whenever you gain life" payoff / "gain N life" source
# detector) AND the inline `extract_signals` self-bleed-wants-sustain block — are pinned
# here byte-identically so the IR kept mirror, the _LIFEGAIN_MATTERS_PLAN_MIRROR voltron
# gate (_signals_regex), and the hand-registered serve spec (signal_specs) all share ONE
# source. lifegain_matters was NEVER a SWEEP key, so no SWEEP row is touched (len stays
# 36). The structural IR arm (a `gain_life` Effect scope you/any + a `life_gained`
# trigger + the shared lifelink keyword map) is a recall-GAINING addition that already
# fires on +77 commander-legal cards the bare "you gain" regex MISSED (the directed
# "target player gains N life" / "each opponent gains 1 life" gains phase structures);
# this mirror restores the 247 regex-only cards (153 reg280 payoffs / 93 self-bleed-
# sustain / 1 both) byte-identically with 0 new over-fires. ARM (A) is the payoff /
# source detector; ARM (B) credits a SIGNIFICANT repeated self-life-LOSS engine (upkeep
# lose >=2, cumulative upkeep, "lose life equal to", Necropotence-style draw-and-bleed,
# symmetric "each player loses [2-9]") that WANTS lifegain to sustain. CR 119 / 118.
LIFEGAIN_MATTERS_REGEX = (
    # ARM (A) — lifegain payoff ("whenever you gain life") / the act of gaining life /
    # a payoff that gates on HAVING gained life ("if you gained life this turn", "the
    # amount of life you gained" — Aerith / Celestine / Lathiel) / variable self-gain
    # ("gain X life", "gain life equal to", "you gain that much life") / amplifiers
    # ("if you would gain life" — Bilbo, Boon Reflection, Rhox Faithmender).
    r"whenever[^.]*gain[^.]*life|you gain \d+ life|gain \d+ life"
    r"|(?:you|your team)(?:'ve| have)? gained[^.]*life|life you gained"
    r"|gains? x life|gains? life equal to|you gain that much life"
    r"|if you would gain life"
    # ARM (B) — significant, repeated, unavoidable self-life-loss that wants lifegain
    # sustain: MEANINGFUL fixed/scaling bleed (upkeep lose >=2 — Deadpool; cumulative
    # upkeep — Gallowbraid/Morinfen; "you lose life equal to" sac engines — Greven),
    # the Necropotence-style "draw X / lose X" engines (Be'lakor, Imskir, Corpse Augur)
    # and "you lose that much life" (Asmodeus), and the symmetric significant drain
    # ("each player loses [2-9] life" hits YOU too). The negligible controlled "lose 1
    # life" rider and the optional "may pay X life" stay OUT (the over-broad trap).
    r"|at the beginning of (?:your|each)[^.]*upkeep[^.]*you lose (?:[2-9]|\d\d) "
    r"life|cumulative upkeep[^.]*life|you lose life equal to"
    r"|you lose x life|you lose that much life"
    r"|whenever[^.]*(?:put into (?:a|their|your) graveyard|dies"
    r"|leaves the battlefield)[^.]*you draw[^.]*you lose \d+ life"
    r"|each player loses (?:[2-9]|\d\d) life"
)

# ADR-0027: counter_doubling migrated to the Card IR. This is the byte-identical UNION
# of the two deleted oracle regexes — the _HAND_FLOOR producer (the first three arms)
# and this SWEEP_DETECTORS row (the last four arms) — pinned here so the
# _COUNTER_DOUBLING_MIRROR kept detector (_signals_ir), the _COUNTER_DOUBLING_PLAN_MIRROR
# voltron gate (_signals_regex), and the serve spec (signal_specs) all share ONE source.
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

SWEEP_DETECTORS: tuple[dict, ...] = (
    # ADR-0027: commander_matters migrated to the Card IR — the IsCommander subject-
    # Filter predicate + a kept word mirror (signals._IR_KEPT_DETECTORS) for the
    # Background grants / "commander damage" / "your commander costs less" refs phase
    # leaves textual. Its SWEEP_DETECTORS row is deleted; the serve is hand-registered
    # in signal_specs.py reusing the deleted regex (SWEEP_LABELS still carries the
    # human label).
    # ADR-0027 β: variable_pt migrated to the Card IR — a */* characteristic-defining
    # P/T fires from a `characteristic_pt` Effect (phase's dropped self-CDA static
    # re-surfaced by project._self_cda_marker @ SIDECAR v10, plus the oracle-text CDAs
    # supplement._CDA_PT already caught) + the NARROWED _VARIABLE_PT_MIRROR (the token-
    # borne */* / change-base-self tail phase can't structure as a self-CDA). Its
    # SWEEP_DETECTORS row is deleted; the EXACT regex is pinned as VARIABLE_PT_SWEEP_REGEX
    # above and the serve is hand-registered in signal_specs.py reusing it (SWEEP_LABELS
    # keeps the human label). CR 604.3.
    {
        "key": "scaling_pump",
        "scope": "you",
        "is_widen_of": "",
        "regex": "gets [+\\-][0-9x]/[+\\-][0-9x] for (?:each|every)",
    },
    # ADR-0027: count_anthem migrated to the Card IR — served from a team +N/+N pump
    # whose amount SCALES with a board count (_is_scaling_count) over a generic
    # creature Filter you control (Hold the Gates, Commander's Insignia, Boon of the
    # Spirit Realm). Its SWEEP_DETECTORS row is deleted; the serve spec is
    # hand-registered in signal_specs.py reusing this deleted regex.
    # ADR-0027: tapper_engine migrated to the Card IR — served from a `tap` Effect
    # carrying a target subject Filter + a "doesn't untap" restriction-raw branch
    # (Icy Manipulator, Opposition, Master Decoy, Frost Titan). Its SWEEP_DETECTORS
    # row is deleted; the serve spec is hand-registered in signal_specs.py reusing
    # this deleted regex.
    {
        "key": "tap_down",
        "scope": "opponents",
        "is_widen_of": "",
        "regex": "(?<!un)tap target (?:permanent|creature|land|nonland permanent)[^.]*(?:an opponent|that player) controls|skips? (?:their|his or her|its) next untap step|tap (?:up to )?\\w+ target permanents? (?:an opponent|that player) controls|\\bdetain\\b",
    },
    # ADR-0027: tap_untap_matters migrated to the Card IR — phase's `taps` (tap-for-
    # mana) trigger + a "whenever … becomes tapped/untapped" kept word mirror
    # (signals._IR_KEPT_DETECTORS) for the Inspired trigger phase flattens to
    # event='other'. Its SWEEP_DETECTORS row is deleted; the serve is hand-registered in
    # signal_specs.py reusing the deleted regex.
    # ADR-0027 β: ability_copy migrated to the Card IR via a byte-identical kept-mirror.
    # This SWEEP_DETECTORS row is deleted; its regex is pinned as ABILITY_COPY_REGEX
    # above. The lane's firing now comes from the _ABILITY_COPY_MIRROR (_signals_ir)
    # full-text scan of that regex over the reminder-stripped kept_oracle (commander-
    # legal: regex==mirror, 51==51, 0 lost, 0 over-fire), NOT a structural `spell_copy`
    # arm — phase emits ONE undifferentiated `spell_copy` category for spell-copy AND
    # ability-copy alike, so the arm OVER-FIRES 90% on the spell-copy half (Twincast/
    # Reverberate) and still MISSES the "has all activated abilities of" granters
    # (grant_keyword); splitting needs a phase projection this batch can't make (see the
    # _migrated_keys.py rationale). SWEEP_LABELS keeps the human label; the serve is
    # hand-registered in signal_specs.py reusing the pinned regex. CR 706.10 / 113.2.
    # ADR-0027: affinity_type migrated to the Card IR — served structurally from the
    # Scryfall `affinity` keyword (_IR_KEYWORD_MAP) plus an `affinity` marker effect
    # for the keyword-less CONFERRED granters ("spells you cast have affinity for X" /
    # "the next spell you cast has affinity for X" — Tezzeret, Saheeli, Sami, Don &
    # Raph, Pearl-Ear), appended by project._narrow_conferred_keyword_refs. Its
    # oracle-regex SWEEP_DETECTORS row is deleted; the serve spec stays hand-registered
    # in signal_specs.py (SWEEP_LABELS still carries the human label).
    # ADR-0027: flash_grant migrated to the Card IR — served structurally from a
    # cast_with_keyword{flash} static (the GRANT-to-OTHERS enabler) plus a
    # byte-identical FLASH_GRANT_REGEX kept word mirror (signals._IR_KEPT_DETECTORS)
    # for the activated/conditional grant + the self-flash tail phase leaves textual.
    # Its SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human label, and the
    # serve spec is hand-registered in signal_specs.py reusing FLASH_GRANT_REGEX. CR
    # 702.8.
    {
        "key": "noncombat_damage_payoff",
        "scope": "you",
        # MV/card-value-SCALING burn engines ("deals damage equal to that spell's /
        # the exiled card's / that card's mana value" — Kaervek, Vial Smasher,
        # Hidetsugu) are the genuine noncombat payoffs here. The "deals double/triple
        # that damage" branch was removed: those are ALL-damage replacement effects
        # (Furnace of Rath, Fiery Emancipation) — combat damage too (CR 510 vs the
        # noncombat damage of 702.19a) — so they belong on damage_doubling, not a
        # "burn outside combat" lane.
        "is_widen_of": "",
        "regex": "noncombat damage|deals that much damage to (?:each opponent|any target|that creature)|deals exactly \\d+ damage|whenever (?:a|another) source you control deals [^.]*damage|deals damage equal to (?:that spell's|the exiled card's|that card's|that creature's) mana value",
    },
    # ADR-0027: mass_removal migrated to the Card IR — a BOARD WIPE (CR 115.10) is the
    # counter_kind=='all' "each/all" discriminator on a destroy/exile/damage of a
    # battlefield permanent type, or the negative all-creatures pump (Languish/Toxic
    # Deluge). The structural gate is STRICTLY broader-and-cleaner than this regex: it
    # drops the regex's EOT-modal debuff / exile-your-own-board / mass-reanimation
    # over-fires and adds the typed/predicate sweeps the regex missed (Maelstrom Pulse,
    # Earthquake, Breath Weapon). Land destruction (Armageddon) and graveyard exile
    # (Living Death) are excluded by the battlefield-type + graveyard-zone gates. This
    # SWEEP_DETECTORS row is deleted; the serve spec stays hand-registered in
    # signal_specs.py (the rebuild-after-wrath package + indestructible serve keyword).
    # ADR-0027 β: debuff_matters migrated to the Card IR — a -1/-1 / toughness-shrink
    # removal-and-payoff lane. The structural arm in extract_signals_ir fires from the
    # projection's negative-pump (amount.factor<0) and non-self -1/-1-counter (m1m1)
    # Effects (recall GAIN over this narrow regex). The big "gets -N/-N until end of
    # turn" / "-X/-X" tail projects with amount==None (the value only in raw), so it is
    # recovered by a byte-identical _IR_KEPT_DETECTORS mirror of this exact regex (plus
    # the Maha opponent-shrink _DETECTORS row). This SWEEP_DETECTORS row is deleted
    # (SWEEP_LABELS kept); the serve spec is hand-registered in signal_specs.py reusing
    # the pinned _DEBUFF_SWEEP_REGEX (the sweep auto-register loop no longer builds it).
    # CR 122.1b / CR 613.
    # ADR-0027: coin_flip migrated to the Card IR — the doers land in phase's
    # coin_flip EFFECT category (_DOER_EFFECT_KEYS), and the "Whenever you win/lose
    # a coin flip" PAYOFF trigger phase flattened to event='other' is appended as a
    # coin_flip marker effect (project._narrow_trigger_other_refs). Its oracle-regex
    # SWEEP_DETECTORS row is deleted; the serve spec stays hand-registered in
    # signal_specs.py (SWEEP_LABELS still carries the human label).
    {
        "key": "topdeck_selection",
        "scope": "you",
        "is_widen_of": "",
        "regex": "look at the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal the top (?:two|three|four|five|six|seven|eight|nine|ten|\\w+|x|\\d+) cards? of your library|reveal cards from the top of your library until|put [^.]*from among them onto the battlefield",
    },
    # ADR-0027 β: play_from_top migrated to the Card IR — the structural arm (a STATIC
    # cast_from_zone+from:library Effect, project._top_play_permission_marker over phase's
    # TopOfLibraryCastPermission static mode, gated `"exile" not in raw` to split granted
    # impulse) plus a per-clause _PLAY_FROM_TOP_MIRROR + _PLAY_FROM_TOP_FLOOR_MIRROR (the
    # EXACT deleted SWEEP + _HAND_FLOOR regexes) for the reveal-only / once-each-turn /
    # triggered tail phase doesn't model as a cast-permission static. Its SWEEP_DETECTORS
    # row + _HAND_FLOOR producer are deleted; the serve is hand-registered in
    # signal_specs.py reusing the deleted regex (SWEEP_LABELS still carries the human
    # label). The ab.kind=='static' gate keeps it disjoint from the sibling
    # impulse_top_play arm (ab.kind!='static'). CR 116 / 601.3b.
    {
        "key": "dig_until",
        "scope": "you",
        "is_widen_of": "",
        "regex": "exile cards? from the top of your library until|exile (?:the )?top[^.]*until you exile|reveal cards from the top of your library until",
    },
    # ADR-0027: hand_disruption migrated to the Card IR — phase's opp-reveal trigger +
    # a kept word mirror (signals._IR_KEPT_DETECTORS) for the "look at … hand" / "play
    # with hands revealed" / modal reveal-and-discard forms phase leaves textual. Its
    # SWEEP_DETECTORS row is deleted; the serve is hand-registered in signal_specs.py
    # reusing the deleted regex.
    # ADR-0027: group_mana migrated to the Card IR — phase emits scope='each' for ZERO
    # ramp effects (the recipient field doesn't exist), so detection moved to a
    # non-controller-recipient discriminator (_GROUP_MANA_RAW) on the ramp effect's raw
    # ("each/that/the active/chosen player … adds {"), which separates symmetric group
    # ramp from your-own ramp. NOT in _IR_FLOOR_LANES; serve hand-registered in
    # signal_specs reusing the deleted regex + the symmetric-mana extra.
    # ADR-0027 (t2b5-B): secret_writedown migrated to the Card IR (kept_detector) — the
    # out-of-game zone (CR 408.1 Wish: "from outside the game") + pre-game secret
    # name/choose has no IR shape (phase's in-game battlefield IR models neither). The
    # IR path detects it from an _IR_KEPT_DETECTORS word mirror that INTENTIONALLY drops
    # this regex's "|your sideboard" arm — companion reminder text (Lurrus, Yorion, …)
    # owned by companion_keyword, NOT a wishboard build-around. SWEEP_LABELS keeps the
    # human label; the serve is hand-registered in signal_specs.py reusing the narrowed
    # regex.
    # ADR-0027: fight_matters migrated to the Card IR — phase's `fight` effect + a
    # `_FIGHT_REF` dropped-static marker (granted/quoted/modal/symmetric fights) and a
    # `_FIGHT_RAW` face-level fallback (the Aftermath DFC phase doesn't project, Prepare
    # // Fight). This SWEEP_DETECTORS row is deleted; the serve hand-spec keeps its regex.
    # ADR-0027: life_total_set migrated to the Card IR — phase's `set_life` effect
    # category (_DOER_EFFECT_KEYS), the exchange/redistribute-life recategorizations in
    # supplement._NAMED_MECHANICS, plus a `_LIFE_TOTAL_SET` dropped-static face marker
    # for "life total becomes <X>" (phase mis-tags as animate/shuffle/lose_game or
    # drops on a modal bullet/replacement — Touch of the Eternal, Lich's Mirror,
    # Captive Audience, Exquisite Archangel) and life DOUBLING ("double … life total" —
    # Beacon, Enduring Angel). NOT in _IR_FLOOR_LANES; serve hand-registered in
    # signal_specs. The IR correctly drops Heartless Hidetsugu ("damage equal to half …
    # life total" is a damage effect, not a set/exchange), the regex's lone over-fire.
    # ADR-0027 β: animate_artifact migrated to the Card IR via a byte-identical kept-
    # mirror — phase parses "artifacts become creatures" three INCONSISTENT ways
    # (base_pt_set/board_grant over an Artifact subject, a becomes_type{Artifact} grant,
    # or a base_pt_set with subject=None), and no structural arm is clean: the dead
    # cat=='animate' arm fires 0 cards, while a base_pt_set/board_grant-over-Artifact arm
    # 90%-over-fires (type-conferral + artifact-creature anthems) or, narrowed, loses the
    # 48 Vehicle-crew + subject=None animators. So the lane rides a _ANIMATE_ARTIFACT_
    # MIRROR (_signals_ir) of the exact deleted regex over the reminder-stripped oracle
    # (commander-legal: regex==mirror, 67/67 genuine, 0 over-fire). Its SWEEP_DETECTORS
    # row is deleted; the EXACT regex is pinned as ANIMATE_ARTIFACT_REGEX above,
    # SWEEP_LABELS keeps the human label, and the serve is hand-registered in
    # signal_specs.py reusing the pinned constant. CR 110.1 / 305.7 / 613.
    # ADR-0027 β: creature_ping + damage_equal_power (the power-as-damage cluster)
    # migrated to the Card IR. Both SWEEP rows are deleted — each key fires from a
    # STRUCTURAL recipient/doer arm in extract_signals_ir (the op="power" damage anchor)
    # PLUS a byte-identical _IR_KEPT_DETECTORS mirror of its exact deleted regex
    # (CREATURE_PING_REGEX / DAMAGE_EQUAL_POWER_REGEX, pinned above). SWEEP_LABELS keeps
    # both human label rows; the serve specs are hand-registered in signal_specs reusing
    # the pinned constants.
    # ADR-0027: power_double migrated to the Card IR — a pump/pump_target Effect whose
    # raw carries the "double … power" / "power … doubled" word-mirror (phase sets no
    # multiply quantity for P/T doubling, so the category + raw is the discriminator).
    # This SWEEP_DETECTORS row is deleted; the hand-spec serve in signal_specs reuses
    # the deleted regex.
    # ADR-0027 (q2-D3): noncreature_cast_punish migrated to the Card IR — the
    # OPPONENT-punisher half binds structurally (extract_signals_ir: a cast_spell
    # trigger scope=='opp' over a noncreature subject — Kambal, Mystic Remora, Esper
    # Sentinel). The SYMMETRIC "a player casts a noncreature spell" half (Niv-Mizzet
    # Parun, Mirrorwing) collapses to scope=='any' (indistinguishable from prowess in
    # phase v0.1.19), so it rides an _IR_KEPT_DETECTORS word mirror anchored on "a
    # player"/"an opponent". This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the
    # label and the serve spec stays hand-registered in signal_specs.py.
    {
        "key": "combat_buff_engine",
        "scope": "you",
        "is_widen_of": "",
        "regex": "at the beginning of combat on your turn[^.]*creature[^.]*\\.?\\s*(?:until end of turn,? )?that creature gets \\+|whenever (?:this creature|[A-Z][a-z]+) attacks[^.]*(?:creature|it) gets \\+\\d/|whenever [\\w ]+ blocks(?: or becomes blocked)?[^.]*gets [+\\-]|whenever [\\w ]+ attacks[^.]*,? (?:it|[\\w ]+?) gets [+\\-]",
    },
    # ADR-0027: opponent_exile_matters migrated to the Card IR — GRAVEYARD HATE (CR
    # 406), served from a kept word mirror (signals._IR_KEPT_DETECTORS) because phase
    # scatters its forms across categories it doesn't unify (graveyard-zone exile →
    # cat='exile' subject=None; Leyline replacement → cat='cheat_play'; Umbris payoff →
    # cat='pump'). The old permanent-exile structural arm mis-fired on Path-to-Exile
    # removal and is removed. Its SWEEP_DETECTORS row is deleted; the serve is hand-
    # registered in signal_specs.py reusing the deleted regex.
    # ADR-0027 tranche2-B (t2b3-B): opponent_counter_grant migrated to the Card IR — a
    # place_counter of a DETRIMENTAL counter (CR 122.1d) on an opponent's permanent
    # (direct opp subject or a co-tap-opp recovery for the "tap … and stun it" pronoun
    # shape; beneficial p1p1/shield/keyword counters excluded), in extract_signals_ir's
    # ability loop. Its SWEEP_DETECTORS row is deleted (the structural read replaces it);
    # this mined regex survives as the shared OPPONENT_COUNTER_GRANT_REGEX constant so
    # signal_specs hand-registers the serve pool reusing it (the two never drift).
    # ADR-0027 tranche2-B: counter_place_trigger migrated to the Card IR — detected
    # from the counter_added TRIGGER event (scope!='opp', Saga-excluded). SWEEP_LABELS
    # keeps the label; the serve spec is re-homed in signal_specs.py.
    # ADR-0027 β: counter_distribute migrated to the Card IR — a BOARD-WIDE +1/+1 counter
    # spread fires from a STRUCTURAL arm (a place_counter carrying the MassEach marker
    # project.py recovers @ SIDECAR v18 from phase's PutCounterAll, +84 recall over this
    # regex's literal "each creature you control" arm — it catches every tribal mass) +
    # the NARROWED _COUNTER_DISTRIBUTE_MIRROR (this regex's mass/distribute/each-of arms
    # PLUS enters-with-ADDITIONAL, MINUS the loose plain "enters with N +1/+1 counters on
    # it" arm — 329 over-fires onto SELF-grow creatures, which are self_counter_grow). Its
    # SWEEP_DETECTORS row is deleted; the EXACT regex is pinned as
    # COUNTER_DISTRIBUTE_SWEEP_REGEX above (shared by the voltron plan-mirror) and the
    # board-wide serve is hand-registered in signal_specs.py (SWEEP_LABELS keeps the
    # label). CR 122.1 / 122.6.
    # ADR-0027 tranche2-C: keyword_counter migrated to the Card IR — detected
    # structurally from a place_counter/remove_counter whose counter_kind is in the
    # closed CR-122.1b keyword set (signals._KEYWORD_COUNTER_KINDS), PLUS a kept word
    # mirror (signals._IR_KEPT_DETECTORS reusing KEYWORD_COUNTER_REGEX above) for the
    # choice/multi/quoted-grant tail phase drops counter_kind on. This SWEEP_DETECTORS
    # row is deleted; SWEEP_LABELS keeps the human label, and the serve spec in
    # signal_specs.py reuses KEYWORD_COUNTER_REGEX (the auto-register loop no longer
    # reaches it).
    # ADR-0027 tranche2-B: counter_replace_bonus migrated to the Card IR — detected
    # from the counter_doubling replacement category (+ a place_counter(plus) tail).
    # SWEEP_LABELS keeps the label; the serve spec is re-homed in signal_specs.py.
    # ADR-0027: counter_move migrated to the Card IR — detected structurally from
    # the MoveCounters effect (phase's `counter_move` effect category,
    # _DOER_EFFECT_KEYS). Its oracle-regex sweep row is deleted; SWEEP_LABELS keeps
    # the label, and the serve spec (which fanned out the counter-doubler package
    # via _sweep_spec_with_extras) is re-homed in signal_specs.py to a literal spec
    # reusing this regex, since the sweep row it read is gone.
    # ADR-0027 tranche2-B: counter_manipulation migrated to the Card IR — detected
    # from (counter_move|remove_counter) effects with counter_kind in {p1p1,m1m1} +
    # a kept cost-clause word mirror (signals._IR_KEPT_DETECTORS). SWEEP_LABELS keeps
    # the label; the serve spec is re-homed in signal_specs.py.
    # ADR-0027 β: self_counter_grow migrated to the Card IR — a creature that puts +1/+1
    # counters on ITSELF fires from a STRUCTURAL arm (a place_counter carrying the SelfRef
    # self-anchor marker project.py recovers @ SIDECAR v12, +503 ir_only over this regex's
    # pronoun-only "on him/her/it/this" — it catches by-name self-grow the regex missed)
    # + the NARROWED _SELF_COUNTER_GROW_MIRROR (the self-anchored arms of this regex, run
    # per-clause, recovering the 14 phase-parse-gap self-growers; the loose "on it" arm is
    # DROPPED — 103 over-fires onto OTHER-creature counter placements). Its SWEEP_DETECTORS
    # row is deleted; the EXACT regex is pinned as SELF_COUNTER_GROW_SWEEP_REGEX above and
    # the serve is hand-registered in signal_specs.py (SWEEP_LABELS keeps the human label).
    # CR 122.1 / 614.12.
    # ADR-0027: facedown_matters migrated to the Card IR — detected from the
    # manifest/cloak/turn_face_up effect categories (_DOER_EFFECT_KEYS) PLUS the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the morph/disguise/
    # face-down-payoff text phase doesn't structure). Its oracle-regex sweep row is
    # deleted; SWEEP_LABELS keeps the label, and the serve spec is hand-registered
    # in signal_specs.py.
    # ADR-0027 t2b5-C: targeting_matters migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact deleted regex;
    # phase structures the heroic / cast-that-targets half as a Targets predicate but
    # flattens the becomes-target trigger to event='other'). Its oracle-regex sweep row
    # is deleted; SWEEP_LABELS keeps the label, and the serve spec is hand-registered in
    # signal_specs.py.
    {
        "key": "protection_grant",
        "scope": "you",
        "is_widen_of": "",
        "regex": "gains? protection from|gains? (?:hexproof|shroud)\\b|target [^.]*gains? protection|can't be the target of (?:spells?|abilities)[^.]*your opponents control",
    },
    # ADR-0027 (t2b2-A): conditional_self_protection migrated to the Card IR — a STATIC
    # Ability with a condition granting a protective keyword to ITSELF (grant_keyword,
    # subject None, counter_kind in _SELF_PROTECTION_GRANT_KW). Its SWEEP row is deleted;
    # the serve spec is hand-registered in signal_specs.py reusing the deleted regex.
    # ADR-0027 β: keyword_grant_target migrated to the Card IR — the structural arm in
    # _signals_ir.extract_signals_ir reads the v14 single_target_grant marker (a keyword
    # grant whose resolved target is a SingleTarget-marked creature — project._single_
    # target_keyword_grant_markers; the ParentTarget affected on a spell/ability
    # GenericEffect is the single-target tell). Its SWEEP_DETECTORS row is deleted;
    # SWEEP_LABELS keeps the human label; the serve spec is hand-registered in
    # signal_specs.py reusing the EXACT deleted regex (pinned above as
    # KEYWORD_GRANT_TARGET_REGEX). The deleted high-confidence scope-"you" producer fed
    # has_other_plan, so a byte-identical _KEYWORD_GRANT_TARGET_PLAN_MIRROR re-supplies
    # the voltron silence in the regex path (the IR arm is BROADER — it gains the "It
    # gains X" idiom + protection/ward grants the word-order regex missed — so
    # _VOLTRON_SILENCING_PLAN_KEYS would over-silence those ir_only gains).
    # ADR-0027 tranche2-B-3: spell_keyword_grant migrated to the Card IR — detected
    # from the whole `cast_with_keyword` effect category (the umbrella over
    # flash_grant / convoke_matters) in signals.extract_signals_ir. Its SWEEP_DETECTORS
    # row is deleted; SWEEP_LABELS keeps the label, and the serve spec is hand-registered
    # in signal_specs.py reusing SPELL_KEYWORD_GRANT_REGEX.
    # ADR-0027: exhaust_matters migrated to the Card IR — served structurally from
    # the Scryfall `exhaust` keyword (_IR_KEYWORD_MAP) plus an `exhaust` effect
    # marker for the keyword-less payoff ("activate an exhaust ability", including
    # Pit Automaton's delayed-trigger-inside-activated-ability shape). The serve spec
    # is hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027 t2b4a-B: partner_background migrated to the Card IR — the Scryfall
    # keyword array (partner / partner with / choose a background / doctor's companion
    # / friends [Scryfall truncates "Friends forever" to "Friends"], via
    # signals._IR_KEYWORD_MAP). The keyword array is MORE precise than this regex,
    # which over-fired on card-name self-references with a comma ("Lava, Axe", "Gather,
    # the Townsfolk") via its \bpartner\b / friend arms, and on cards that merely
    # REFERENCE the keyword ("a card with doctor's companion" — An Unearthly Child); it
    # also recovers real Friends-forever partners the regex missed (Astarion). The
    # partner-commander COLOR-WIDENING avenue (ADR-0019, engine.py) consumes this key:
    # in production every partner card carries the keyword, so the avenue still flags
    # `widening` and the find ranker sorts by color widening. `companion` (Lutri) is
    # the SEPARATE companion_keyword lane and is deliberately NOT mapped. This
    # SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the label, and the serve spec
    # is hand-registered in signal_specs.py. CR 702.124 / 702.123.
    # ADR-0027: companion_keyword migrated to the Card IR — detected from the
    # Scryfall `companion` keyword (signals._IR_KEYWORD_MAP, a structured-field
    # lookup). Its oracle-regex sweep row is deleted; SWEEP_LABELS keeps the human
    # label, and the serve spec is hand-registered in signal_specs.py (the sweep
    # auto-register loop no longer reaches it).
    {
        "key": "lure_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "all creatures able to block [^.]*do so|must be blocked if able|all creatures (?:that could|able to) block|must be blocked(?: (?:by|if))?",
    },
    # ADR-0027: the four bending lanes (airbend CR 701.65, earthbend CR 701.66,
    # waterbend CR 701.67, firebending CR 702.189) migrated to the Card IR — they
    # are detected from the kept word-detector mirror in signals._IR_KEPT_DETECTORS
    # (phase v0.1.19 doesn't structure these recent named mechanics, so they stay
    # narrow oracle-word detectors INSIDE the IR path). Their oracle-regex sweep
    # rows are deleted; SWEEP_LABELS still carries each human label, and the serve
    # specs are hand-registered in signal_specs.py (the sweep auto-register loop no
    # longer reaches them).
    # ADR-0027: domain_matters migrated to the Card IR — the amount.op=='domain' count
    # operand + a "\\bdomain\\b|basic land types" kept word mirror
    # (signals._IR_KEPT_DETECTORS) for the cost-reduction / condition / "Domain —"
    # ability-word refs phase leaves textual (CR 700.3). Its SWEEP_DETECTORS row is
    # deleted; the serve is its own hand-written _spec in signal_specs.py (independent
    # of this regex).
    # ADR-0027 β: conjure_matters migrated to the Card IR — a byte-identical
    # `\\bconjure\\b` kept word mirror (signals._IR_KEPT_DETECTORS, scope 'you').
    # CONJURE is digital-only (Arena/Alchemy): phase DOES carry a structural `Conjure`
    # effect type (101 cards) but the projection folds it to make_token, AND that
    # structural set is INCOMPLETE — it misses conjure-via-activated/triggered/modal
    # ability (Agent of Raffine, Anina, Drover of the Swine: 65 HB-legal regex_only
    # cards), so a structural arm would LOSE 65 cards of recall vs this exact-keyword
    # regex with no over-fire benefit (struct_only == 0). The regex is near-exact (166
    # of 167 stripped hits genuine conjure; the single false positive — Silvanus's
    # Invoker "Conjure Elemental —" ability word — is the ONLY commander-legal hit), so
    # the kept word mirror is the clean migration. Its SWEEP_DETECTORS row is deleted;
    # the serve is its own hand-written _spec in signal_specs.py (the sweep auto-
    # register loop no longer reaches it). CR 701.66a (conjure).
    # ADR-0027: saga_matters migrated to the Card IR — a `_SAGA_REF` ("lore counter" /
    # "Saga you control") dropped-static face marker (the lore-counter manipulation /
    # payoff, anchored on the stripped oracle so a vanilla Saga's reminder-only lore
    # mention doesn't fire — exactly mirroring this regex). This SWEEP_DETECTORS row is
    # deleted; the serve hand-spec survives.
    # ADR-0027 t2b4a-B: win_lose_game migrated to the Card IR — the win_game / lose_game
    # Effect categories (the broad terminal-outcome pool, 54+43 cards — Thassa's Oracle,
    # Lab Maniac, the Pacts, Lich, Phyrexian Unlife, Felidar Sovereign, Door to
    # Nothingness, Triskaidekaphobia), far past this narrow regex. A kept word mirror
    # (_IR_KEPT_DETECTORS, byte-identical to this deleted regex, scope 'any') recovers
    # the conferred/quoted-ability tail phase folds into a grant carrier (Vraska's
    # token "that player loses the game"; Frodo's granted loss). Scope stays 'any' (the
    # behavior-neutral choice — the row matched both self-wins and player-losses). This
    # SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the label, and the serve spec
    # is hand-registered in signal_specs.py. CR 104.2.
    # ADR-0027 tranche2-B-3: target_player_draws migrated to the Card IR — detected
    # from a `draw` effect with scope=='any' (a directed/forced draw; a self-cantrip
    # parses scope=='you', "each player draws" scope=='each' → group_hug_draw) in
    # signals.extract_signals_ir. Its SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps
    # the label, and the serve spec is hand-registered in signal_specs.py reusing
    # TARGET_PLAYER_DRAWS_REGEX.
    # ADR-0027 β: ltb_matters migrated to the Card IR — a leaves-the-battlefield payoff
    # fires from a STRUCTURAL `leaves`-trigger arm (phase's LeavesBattlefield mode,
    # event=='leaves' @ SIDECAR v11, OTHER-permanent subject) + the NARROWED
    # _LTB_MATTERS_MIRROR (this regex run per-clause, vetoed against the O-Ring self-LTB-
    # exile over-fire). Its SWEEP_DETECTORS row is deleted; the EXACT regex is pinned as
    # LTB_MATTERS_SWEEP_REGEX above and the serve is hand-registered in signal_specs.py
    # reusing it (SWEEP_LABELS keeps the human label). CR 603.6e / 700.4.
    # ADR-0027 t2b5-A: each_mode_player migrated to the Card IR — phase captures the
    # modal head (Effect.category=='choose') but has NO field for the spread-the-modes
    # CONSTRAINT, so the lane fires from a signals._IR_KEPT_DETECTORS word mirror (the
    # exact regex). This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human
    # label, and the serve is hand-registered in signal_specs.py reusing the regex.
    # ADR-0027 β: toughness_combat migrated to the Card IR via a byte-identical kept-
    # mirror. This SWEEP_DETECTORS row (the Doran combat-redirect half) is deleted; it
    # is joined with the deleted inline _signals_regex _DETECTORS value-payoff producer
    # into the pinned TOUGHNESS_COMBAT_REGEX above. The lane's firing now comes from the
    # _TOUGHNESS_COMBAT_MIRROR (_signals_ir) full-text scan of that OR over the reminder-
    # stripped kept_oracle (commander-legal: regex==mirror, 0 lost, 0 over-fire), NOT a
    # structural `combat_damage_mod` arm (it MISSES 129/133 and over-fires 81% — see the
    # _migrated_keys.py rationale). SWEEP_LABELS keeps the human label; the serve is
    # hand-registered in signal_specs.py reusing the pinned regex. CR 510.1c / 122.
    # ADR-0027: donate_matters migrated to the Card IR — a `gain_control` effect whose
    # raw names another-player RECIPIENT (you GIVE a permanent you control away; phase
    # drops the recipient to scope='any', so the lane reads the effect raw — the
    # _DONATE_RAW discriminator in signals.py, the lane's own deleted serve regex
    # minus its "[^.]*you control" arm, reproducing it exactly). CR 701.12. Its
    # SWEEP_DETECTORS row is deleted; the serve is hand-registered in signal_specs.py
    # reusing the deleted regex.
    # ADR-0027: attractions_matter migrated to the Card IR — served from a
    # "\battraction\b|open an attraction" _IR_KEPT_DETECTORS word mirror (phase v0.1.19
    # doesn't structure the CR 717 Attraction designation). This SWEEP_DETECTORS row is
    # deleted; the serve label below survives.
    # ADR-0027 tranche2-C: extra_land_drop migrated to the Card IR — detected
    # structurally from a cheat_play / topdeck_select with a Land subject (put a land
    # from hand/library onto the battlefield), plus a YOUR-anchored kept word mirror
    # (signals._IR_KEPT_DETECTORS) for the empty-raw modal / cascade / phase-mis-zoned
    # tail. This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human label, and
    # the serve spec is hand-registered in signal_specs.py reusing the deleted regex
    # (the auto-register loop no longer reaches it).
    {
        "key": "blocked_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "whenever [^.]*becomes blocked|\\bwhenever \\w[^.]*\\bblocks\\b",
    },
    # ADR-0027 tranche2-B: exile_until_leaves migrated to the Card IR — detected from
    # signals._is_exile_until_leaves (inline raw phrase OR the two-ability linked-
    # return O-Ring shape) + a kept Saga-chapter word mirror. SWEEP_LABELS keeps the
    # label; the serve spec is re-homed in signal_specs.py.
    {
        "key": "damage_prevention",
        "scope": "you",
        "is_widen_of": "",
        "regex": "prevent the next (?:\\d+|x) damage|prevent (?:all|the next \\d+|x|all combat|all but \\d+|that) [^.]*damage|prevent that damage|prevent all damage|prevent [^.]*damage that would be dealt",
    },
    # ADR-0027 β: damage_redirect migrated to the Card IR via two byte-identical kept
    # mirrors. phase types both arms INCONSISTENTLY and ~90%-over-fires either structural
    # category (redirect/damage_replace(ment) = 224 vs 25; damage_prevention = 396 vs
    # 44), so the lane rides the deleted regexes byte-identically: ARM B (the redirect
    # clause) via _DAMAGE_REDIRECT_MIRROR over the reminder-stripped oracle, ARM A (the
    # name-aware self-prevention) via the EXACT _detect_self_damage_prevention helper
    # inline in extract_signals_ir. This SWEEP_DETECTORS row is deleted; the EXACT ARM B
    # regex is pinned as DAMAGE_REDIRECT_REGEX above, SWEEP_LABELS keeps the human
    # label, and the serve stays hand-registered in signal_specs.py (its own curated
    # search regex). CR 614.9 / 615.
    # ADR-0027: damage_doubling migrated to the Card IR — detected structurally from
    # phase's `damage_doubling` DamageDone-replacement category (now covering Double,
    # Triple, Plus, and the nested AddTargetReplacement / CreateDamageReplacement
    # amplifiers), plus a `damage_doubling` face marker for the modification phase
    # dropped (Neriv/Jeska/Borborygmos). The structural IR is strictly broader-and-
    # correct ("double all damage … would deal" — Collective Inferno, Raphael,
    # Wolverine) and EXCLUDES the regex's "prevent half that damage" halving over-fire
    # (Dark Sphere). Its SWEEP_DETECTORS row is deleted; the serve spec is hand-
    # registered in signal_specs.py (SWEEP_LABELS still carries the human label).
    # ADR-0027: symmetric_damage_each migrated to the Card IR. The lane = damage dealt
    # to EACH player (the Pestilence / Star of Extinction / Sulfurous Blast symmetric-
    # board family). It fires from the v22 damage Effect scope=='each' structural arm
    # (strictly broader-and-correct vs this regex, which required a literal \d+ amount —
    # the IR catches the X-/equal-to forms it missed: Earthquake, Price of Progress,
    # Heartless Hidetsugu) PLUS the byte-identical _SYMMETRIC_DAMAGE_EACH_MIRROR for the
    # coin-flip-branch tail (Volatile Rig, Winter Sky). The deleted regex's "each
    # opponent" arm is INTENTIONALLY dropped — one-sided damage is NOT symmetric (CR
    # 102.2 — an opponent is not you), so those cards route to direct_damage (scope
    # 'opp') instead (the ADR-0027 split; 0 genuine each-player card lost). This
    # SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human label and the serve
    # spec stays hand-registered in signal_specs.py. The deleted producer fired HIGH-
    # confidence scope 'each', feeding has_other_plan; the full-regex
    # _SYMMETRIC_DAMAGE_EACH_PLAN_MIRROR re-supplies the exact pre-migration voltron
    # silence set (the each-opponent cards are independently re-silenced by the
    # direct_damage plan mirror, so no leak). CR 102.2 / 903.10a.
    # ADR-0027 t2b4-C: damage_to_you_punish migrated to the Card IR (kept_detector) —
    # phase captures the deals_damage event but DROPS both discriminants (the opponent-
    # controlled source filter and the "to you" recipient), so it fires from an
    # _IR_KEPT_DETECTORS word mirror (the exact regex below). This SWEEP_DETECTORS row is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: damage_reflect migrated to the Card IR — served structurally from the
    # on-card co-occurrence (a damage_received trigger + a damage effect, in
    # extract_signals_ir) plus a `damage_reflect` marker effect for the GRANTED/QUOTED
    # reflection ability ('Slivers you control have "Whenever ~ is dealt damage, ~
    # deals that much damage to ..."' — Spiteful Sliver), appended by
    # project._narrow_conferred_keyword_refs. Its oracle-regex SWEEP_DETECTORS row is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027 t2b4-C: excess_damage migrated to the Card IR (kept_detector) — the clean
    # "is dealt excess damage" payoffs bind structurally (Trigger event=='excess_damage'),
    # but the 29/33 intervening-condition / spell-text references ride Effect.raw (phase
    # inlines the condition, not a structured node), so they fire from an
    # _IR_KEPT_DETECTORS `\bexcess damage\b` word mirror. This SWEEP_DETECTORS row is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: destroy_legendary migrated to the Card IR — a `destroy` Effect whose
    # subject Filter carries the exact HasSupertype:Legendary predicate (the mass
    # "destroy each legendary" form rides counter_kind=='all' with the same predicate).
    # This SWEEP_DETECTORS row is deleted; the hand-spec serve in signal_specs reuses
    # the deleted regex. (is_widen_of removal_matters is preserved structurally — the
    # destroy effect still opens removal_matters where it qualifies.)
    # ADR-0027: anthem_static migrated to the Card IR — a STATIC +N/+N over a creature
    # GROUP (extract_signals_ir: ab.kind=='static', pump Effect, amount.factor>=0,
    # scope!='opp', subject a creature group). The structural gate is strictly cleaner
    # than this regex: ab.kind=='static' drops the regex's one-shot / until-end-of-turn
    # pump over-fires (Charge, Overcome, Steadfast Unicorn, planeswalker minus
    # abilities) and factor>=0/scope!='opp' drops the debuff half of a split anthem
    # (Elesh Norn's -2/-2). It also adds the typed/subtype/predicate anthems the
    # narrow regex subject-phrase list missed. is_widen_of='team_buff' is preserved by
    # the serve spec. This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the label
    # and the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: all_creatures_kw_grant migrated to the Card IR — detected
    # structurally from the GrantKeyword effect whose subject is "all creatures"
    # (extract_signals_ir's grant_keyword branch + _is_all_creatures_grant). Its
    # oracle-regex sweep row is deleted; SWEEP_LABELS keeps the label, and the serve
    # spec is hand-registered in signal_specs.py.
    # ADR-0027 β: global_ability_grant migrated to the Card IR — the structural arm in
    # _signals_ir.extract_signals_ir reads the v9 board_grant + counter_kind=
    # "grant_ability" marker (a GrantAbility/GrantTrigger/GrantStaticAbility static over
    # a creature board or a bare all-permanents set — project._global_ability_grant_
    # markers; the QUOTE is the tell vs a bare keyword anthem). Its SWEEP_DETECTORS row
    # is deleted; SWEEP_LABELS keeps the human label; the serve spec is hand-registered
    # in signal_specs.py reusing the EXACT deleted regex (pinned above as
    # GLOBAL_ABILITY_GRANT_REGEX). The deleted high-confidence scope-"any" producer fed
    # has_other_plan, so a byte-identical _GLOBAL_ABILITY_GRANT_PLAN_MIRROR re-supplies
    # the voltron silence in the regex path (the IR arm is narrower on the 6 bands/Ward
    # keyword over-fires, so _VOLTRON_SILENCING_PLAN_KEYS would under-silence).
    # ADR-0027 (t2b2-A): aura_equip_kw_grant migrated to the Card IR — a grant_keyword
    # of an evergreen keyword (counter_kind in _AURA_EQUIP_GRANT_KW) over a YOUR
    # Aura/Equipment subgroup subject (_is_aura_equip_grant). Its SWEEP row is deleted;
    # the serve spec is hand-registered in signal_specs.py reusing the deleted regex.
    # ADR-0027 (t2b2-A): counter_grants_kw migrated to the Card IR — a grant_keyword over
    # a YOUR-creature subject carrying the `Counters` predicate (Bramblewood Paragon).
    # Its SWEEP row is deleted; the serve spec is hand-registered in signal_specs.py
    # reusing the deleted regex.
    # ADR-0027: typed_anthem_multi migrated to the Card IR — a pump effect over a
    # creature Filter naming 2+ subtypes (an AnyOf-of-subtypes node OR a flat
    # subtypes tuple of length >=2 — Brenard, Howlpack Resurgence, Auriok Steelshaper),
    # plus a raw fallback for the disjunction phase drops the subject on ("that's a X …
    # or a Y" — Kaheera, Immerwolf, Lovisa, Sporecrown). NOT in _IR_FLOOR_LANES; serve
    # hand-registered in signal_specs. The structural pump-only gate excludes Paladin
    # Danse (a one-shot keyword GRANT via grant_keyword, not a +X/+X anthem), the
    # regex's lone over-fire.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a kept-mirror — this
    # SWEEP_DETECTORS row is deleted. The EXACT regex is pinned above as
    # UNSPENT_MANA_REGEX; the lane fires from the byte-identical _UNSPENT_MANA_MIRROR
    # in signals._IR_KEPT_DETECTORS, the voltron _UNSPENT_MANA_PLAN_MIRROR
    # (_signals_regex) re-supplies the deleted producer's has_other_plan silence, and
    # the serve spec in signal_specs reuses the pinned regex. SWEEP_LABELS still
    # carries the human label.
    # ADR-0027: keyword_soup migrated to the Card IR — fired structurally from >=5
    # distinct evergreen grant_keyword counter_kinds in one ability (Odric class) plus
    # a kept oracle mirror (signals._IR_KEPT_DETECTORS) for the "the same is true for …"
    # keyword-absorb idiom phase under-parses on a few cards. This SWEEP_DETECTORS row
    # is deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: trigger_doubling migrated to the Card IR — served structurally from
    # phase's `trigger_doubling` effect category (Panharmonicon/Yarok class) plus a
    # `trigger_doubling` dropped-static face marker for the granted/quoted form
    # phase drops entirely (The Masamune's equipped-creature "triggers an additional
    # time"). The serve spec is hand-registered in signal_specs reusing the regex.
    # ADR-0027: ninjutsu_matters migrated to the Card IR — served structurally from
    # the Scryfall `ninjutsu`/`commander ninjutsu` keyword (_IR_KEYWORD_MAP) plus a
    # `ninjutsu` marker effect for the keyword-less payoff commander (Satoru: "Whenever
    # you activate a ninjutsu ability" — a trigger phase flattened to event='other',
    # appended by project._narrow_trigger_other_refs). Its oracle-regex SWEEP_DETECTORS
    # row is deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: suspend_matters migrated to the Card IR — served from the Scryfall
    # `suspend` keyword (_IR_KEYWORD_MAP) + a kept word mirror (signals._IR_KEPT_
    # DETECTORS) folding this \bsuspend\b in and widening to the time-counter
    # superstructure (Vanishing / Impending / time travel) phase doesn't structure.
    # This SWEEP_DETECTORS row is deleted; the serve spec stays hand-registered.
    # ADR-0027: boast_matters migrated to the Card IR — served structurally from the
    # Scryfall `boast` keyword (_IR_KEYWORD_MAP) + phase's `boast` effect category
    # (the event='other' boast-payoff trigger) plus a `boast` dropped-static face
    # marker for the "can boast twice" static amplifier phase drops (Birgi). The
    # serve spec is hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027: soulbond_matters migrated to the Card IR — served structurally from
    # the Scryfall `soulbond` keyword (_IR_KEYWORD_MAP) plus a `soulbond` effect
    # marker for non-keyword references ("paired with a creature with soulbond" —
    # Flowering Lumberknot — narrowed in project._narrow_mechanic_refs into the
    # `soulbond` effect category, read via _DOER_EFFECT_KEYS). Its oracle-regex
    # detector row is deleted; the serve spec is hand-registered in signal_specs.py
    # (SWEEP_LABELS still carries the human label).
    # ADR-0027 β: pump_matters migrated to the Card IR — a POSITIVE single-target
    # combat-trick buff ("target creature gets +N/+N"). The lane is UNSTRUCTURABLE as a
    # positive discriminator: phase drops the value of every target-creature pump to
    # amount==None (the +N/+N lives only in the raw) and carries no temporal marker, so
    # a combat trick is structurally indistinguishable from a -1/-1 debuff (same
    # pump_target/subj=Creature/amt=None shape) or a permanent buff. The one clean
    # positive-single-target structural form phase carries (a positive-factor pump on an
    # EnchantedBy/EquippedBy subject — auras/equipment) is the SEPARATE voltron/suit-up
    # lane, so a structural arm would be scope creep, not recall. So this row is deleted
    # and the lane rides a byte-identical _IR_KEPT_DETECTORS mirror of the exact deleted
    # regex (pinned as PUMP_MATTERS_REGEX above; full-text over reminder-stripped text ==
    # the deleted per-clause SWEEP path, 0 drift both directions). The serve spec is
    # hand-registered in signal_specs.py reusing PUMP_MATTERS_REGEX (the sweep
    # auto-register loop no longer builds it; SWEEP_LABELS keeps the human label).
    # CR 122.1b / 903.10a.
    # ADR-0027: self_pump migrated to the Card IR — served from an ACTIVATED
    # pump_target / place_counter(p1p1) effect on the SELF (subject=None) — the
    # firebreathing mana-sink (Shivan Dragon) and the activated +1/+1-counter body
    # (Walking Ballista, Crystalline Crawler). Its SWEEP_DETECTORS row is deleted; the
    # existing _sweep_spec_with_extras("self_pump", …) serve spec in signal_specs.py
    # is repointed to this deleted regex via the `regex=` arg.
    {
        "key": "base_pt_set",
        "scope": "any",
        "is_widen_of": "",
        "regex": "base power (?:and toughness )?\\d|has base power|base toughness \\d|becomes a [^.]*with base power and toughness|becomes a [^.]* in addition to its other types|switch (?:each |target )?creature'?s'? power and toughness|switch [^.]{0,40}power and toughness|base power and toughness of each [^.]*become",
    },
    {
        "key": "playtest_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bplaytest cards?\\b",
    },
    {
        "key": "stickers_matter",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\{tk\\}|\\bstickers?\\b",
    },
    # ADR-0027: starting_life_matters migrated to the Card IR — a `_STARTING_LIFE_REF`
    # ("starting life total") dropped-static compare marker (CR 103.4). The broad
    # regex's second arm ("life total is greater/less") over-fired on unrelated
    # thresholds (Elderscale Wurm's "less than 7", Sigarda's "last noted life total"),
    # which the tight IR marker drops; the marker is also broader-and-correct recall
    # ("N life more than your starting life total", "becomes half your starting life
    # total" — Righteous Valkyrie, Torgaar). Removed from _IR_FLOOR_LANES; serve
    # hand-registered reusing the deleted regex.
    # ADR-0027 t2b5-A: miracle_grant migrated to the Card IR — a card that GRANTS
    # miracle to OTHER cards in hand; phase folds the grant into a carrier (category
    # grant_keyword/other), so the lane fires from a signals._IR_KEPT_DETECTORS word
    # mirror (the exact regex — the granting DIRECTION, excluding intrinsic-miracle
    # makers). This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human label,
    # and the serve is hand-registered in signal_specs.py reusing the regex.
    # ADR-0027: convoke_matters migrated to the Card IR — the MAKERS ride the Scryfall
    # `convoke` keyword (_IR_KEYWORD_MAP); the keyword-less GRANTERS + PAYOFFS read
    # structurally: cast_with_keyword counter_kind='convoke' (static "<type> spells you
    # cast have convoke" — Fallaji Wayfarer, Chief Engineer), grant_spell_ability with
    # convoke in raw (Wand of the Worldsoul), and the "spell that has convoke" cast
    # trigger payoff (Saint Traft, Joyful Stormsculptor). Removed from _IR_FLOOR_LANES;
    # serve hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027: explore_matters migrated to the Card IR — served structurally from
    # the Scryfall `explore` keyword (_IR_KEYWORD_MAP, the authoritative path: 53 ⊇
    # the 44 regex hits, covering Map-token grants / granted-ability / replacement-
    # clause explore cards that emit no explore Effect node) + phase's `explore`
    # effect category (the event='other' explore payoff). The serve spec is hand-
    # registered in signal_specs reusing the deleted regex.
    # ADR-0027: changeling_matters migrated to the Card IR — the Scryfall `changeling`
    # keyword (_IR_KEYWORD_MAP, the intrinsic changelings) + a `_CHANGELING_REF`
    # ("changeling" / "is every creature type") dropped-static marker for the keyword-
    # less makers/anthems (Maskwood Nexus, Mistform Ultimus, Arachnoform). Removed from
    # _IR_FLOOR_LANES; serve hand-registered reusing the deleted regex.
    # ADR-0027 t2b4a-B: alt_cost_keyword migrated to the Card IR — the Scryfall
    # keyword array (web-slinging / sneak / mayhem via signals._IR_KEYWORD_MAP, a
    # structured-field lookup). The keyword-array membership is exact (no over-fire,
    # vs this regex which over-fired on flavor "Sneak Attack" and keyword-GRANTING
    # text — "cards have mayhem/sneak/web-slinging"). This SWEEP_DETECTORS row is
    # deleted; SWEEP_LABELS keeps the human label, and the serve spec is hand-
    # registered in signal_specs.py. CR 118.9.
    # ADR-0027 t2b5-A: flip_self migrated to the Card IR — the Kamigawa flip (CR 710) is
    # a single card that self-transforms in place on its own condition (self-contained,
    # no cross-card payoff; split from meld, the two-card subject-bearing meld_pair
    # detector). phase parses the flip INCONSISTENTLY (transform / reanimate / buried in
    # raw), so no single structured category is reliable; the lane fires from a
    # signals._IR_KEPT_DETECTORS word mirror (the exact "flip this creature" regex, a
    # coined term on exactly the 7 flip creatures). This SWEEP_DETECTORS row is deleted;
    # SWEEP_LABELS keeps the human label, and the serve is hand-registered in
    # signal_specs.py reusing the regex.
    # ADR-0027 β (kept-mirror): legend_rule_off migrated to the Card IR. phase's
    # `legend_exempt` Effect is a strict SUBSET of the regex (2 of 8: only the
    # unbounded "the legend rule doesn't apply" — Mirror Gallery, Brothers
    # Yamazaki). The bounded-scope variant ("doesn't apply to
    # permanents/tokens/<Subtype> you control" — Mirror Box, Cadric, Sliver
    # Gravemother, Spider-Verse, The Master, Sakashima) is DROPPED by phase, so
    # a byte-identical _IR_KEPT_DETECTORS word mirror (the exact regex below)
    # recovers all 8 — the only honest resolution while phase emits no structural
    # form for the bounded variant. This SWEEP_DETECTORS row is deleted;
    # SWEEP_LABELS keeps the human label, and the serve is hand-registered in
    # signal_specs.py reusing the regex. CR 704.5j.
    # ADR-0027: cmdzone_ability migrated to the Card IR — an Eminence / command-zone-
    # gated ability fires from a STRUCTURAL arm (extract_signals_ir): 'command' in the
    # ability zones OR in the recursive Condition zone tree (phase models the gate as
    # Condition(kind='sourceinzone', zones=('command',))). The STATIC-Eminence half
    # (The Ur-Dragon) drops the condition, so it rides a byte-identical
    # _IR_KEPT_DETECTORS word mirror (the exact regex below). This SWEEP_DETECTORS row
    # is deleted; the serve is hand-registered in signal_specs (reusing the regex).
    # ADR-0027: mass_bounce migrated to the Card IR — a `bounce` Effect with
    # counter_kind=='all' (the mass discriminator) on a generic Creature/Permanent
    # subject (_is_mass_bounce_subject), excluding graveyard recursion. This
    # SWEEP_DETECTORS row is deleted; the hand-spec serve in signal_specs reuses the
    # deleted regex.
    # ADR-0027: activated_draw migrated to the Card IR — a TAP-to-DRAW activated engine
    # is an Ability(kind=='activated') whose cost contains 'tap' (the {T}: gate the
    # cost field now carries) and an Effect(category=='draw') (extract_signals_ir,
    # cost-based lanes). The looser 'tap' in cost catches the {N}{T}: draw rocks/lands
    # (Arch of Orazca, Bonders' Enclave) the literal `{t}: draw a card` regex missed,
    # while sacself/discardself/paylife-cost draws (Forgotten Cave, Erebos) lack 'tap'
    # and stay out. This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the label
    # and the serve spec stays hand-registered in signal_specs.py.
    {
        "key": "forced_attack",
        "scope": "any",
        "is_widen_of": "",
        "regex": "may attack only the nearest opponent|attacks? that player this combat if able|attacks? (?:each|every) combat if able",
    },
    # ADR-0027: tribal_etb_multi + typed_enters_punish migrated to the Card IR (their
    # SWEEP_DETECTORS rows deleted). tribal_etb_multi detects an `etb` trigger whose
    # subject Filter names a creature subtype (vocab-gated _kindred_subjects); the
    # broad structural read is the lane's intent (every tribal-ETB chain), far wider
    # than the artificially-narrow "this or another <Tribe>" multi-tribe regex.
    # typed_enters_punish detects an `etb` trigger on a YOUR creature/typed-thing whose
    # consequence is a damage Effect with an opponent recipient (the burn payoff).
    # Their serve pools stay oracle-defined — the deleted regexes are pinned in
    # signal_specs.py and the specs hand-registered (the auto-sweep loop no longer
    # builds them). SWEEP_LABELS keeps each human label.
    {
        "key": "topdeck_stack",
        "scope": "you",
        "is_widen_of": "",
        "regex": "put (?:two|three|\\w+) cards? from your hand on top of your library|on top of your library in any order",
    },
    # ADR-0027: theft_matters migrated to the Card IR (its SWEEP_DETECTORS row deleted).
    # The lane fires from a BYTE-IDENTICAL kept WORD MIRROR (THEFT_MATTERS_REGEX above,
    # in signals._IR_KEPT_DETECTORS, scope 'opponents', HIGH) — phase carries no
    # structural steal-and-cast form. SWEEP_LABELS keeps the human label; the serve spec
    # stays hand-registered in signal_specs.py reusing THEFT_MATTERS_REGEX.
    {
        "key": "cast_as_named_card",
        "scope": "you",
        "is_widen_of": "",
        "regex": "cast (?:creature )?cards? from your hand as though they were the card",
    },
    # ADR-0027: evasion_denial migrated to the Card IR — served structurally from
    # phase's `evasion_denial` (IgnoreLandwalkForBlocking) effect category for the
    # specific named-walk shapes (Great Wall, Crevasse, …) plus an `evasion_denial`
    # marker effect for the GENERIC umbrella phrasing ("Creatures with landwalk
    # abilities can be blocked as though they didn't have those abilities" — Staff of
    # the Ages), appended by project._narrow_conferred_keyword_refs. Its oracle-regex
    # SWEEP_DETECTORS row is deleted; the serve spec stays hand-registered.
    {
        "key": "named_permanent",
        "scope": "you",
        "is_widen_of": "",
        "regex": "(?:permanent|creature|another permanent) named [A-Z]|a permanent you control named|control a (?:permanent|creature)[^.]*named",
    },
    {
        "key": "discard_outlet",
        "scope": "you",
        "is_widen_of": "discard_matters",
        "regex": "discard (?:a|an|another|two|three|your hand|x|\\d+) [^:.]{0,40}?:|, discard (?:a|an|another|two|three|x|\\d+) cards?:|discard (?:two|three|four|five|x|\\d+) cards? at random|discard all the cards in your hand|discard your hand|discard three cards at random|draw (?:two|three|\\w+|\\d+) cards?[^.]*\\.?\\s*then discard|draw [^.]*cards?,? then discard",
    },
    {
        # dies_recursion is the BROAD "creatures recur when they die" category — with
        # OR without counters. It is the SUPERSET of undying_persist_matters: undying
        # (CR 702.93a, +1/+1) and persist (CR 702.79a, -1/-1) ARE dies-recursion that
        # also place a counter, so the keywords are members here too; bare dies-return
        # grants (Feign Death / Supernatural Stamina) are dies_recursion only. The
        # keyword word survives reminder-text stripping (same as undying_persist_matters).
        "key": "dies_recursion",
        "scope": "you",
        "is_widen_of": "",
        "regex": "if [^.]* would die, instead exile it with [^.]*counters?|when [^.]* dies, return (?:it|her|him|them) to the battlefield|\\b(?:undying|persist)\\b",
    },
    # ADR-0027: devour_matters' oracle-regex SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the Scryfall `devour` keyword via
    # _IR_KEYWORD_MAP + phase's `devour` effect category, fanned via the
    # cat=="devour" arm in extract_signals_ir). The bare "\bdevour\b" regex
    # over-fired on the "Devour Intellect" FLAVOR WORD (CR 207.2d — no rules
    # meaning) and the "Devour in Flames" CARD NAME, neither of which is the
    # Devour keyword (CR 702.82a). The serve pool stays oracle-defined, so the
    # spec is hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027: cant_block_grant migrated to the Card IR — phase's `cant_block` effect
    # category (the force-a-block-off statics/grants) plus a dropped-static face marker
    # for the MODAL mode body ("• Target creature can't block this turn" — Breeches,
    # Retreat to Valakut) and the GRANTED QUOTED ability ("Enchanted land has '{T}:
    # Target creature can't block…'" — Hostile Realm, Malicious Intent) phase drops
    # (CR 509). NOT in _IR_FLOOR_LANES; the serve spec is hand-registered in
    # signal_specs reusing the deleted "target creature can't block" regex.
    {
        "key": "station_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bstation\\b|\\bspacecraft\\b",
    },
    {
        "key": "void_warp_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "void —|warp \\{|warp cost|warp—|for its warp cost|using its warp ability|cast (?:a |this )?(?:spell|card)[^.]*for its warp|target exiled card with warp",
    },
    # Named counters are NOT interchangeable (CR 122.1: only same-name counters are),
    # so a rad payoff wants nothing from an oil/ki/shield deck. The old single lane
    # served every branch together — split into the populous, mechanically-distinct
    # types (each auto-served from its own regex) plus a misc residual for singletons.
    # "fade" is dropped: fade counters are the Fading keyword's sacrifice clock
    # (CR 702.32), not a build-around payoff axis. The cross-type axis (proliferate)
    # already lives in proliferate_matters.
    # ADR-0027: rad_counter_matters migrated to the Card IR — phase's `rad_counter`
    # effect category + a rad place_counter (counter_kind='rad') plus a `_RAD_REF`
    # ("rad counter(s)") dropped-static face marker for the clauses phase mangles (the
    # rad kind dropped to '', a counter_doubling, or a dropped clause). Removed from
    # _IR_FLOOR_LANES; serve hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027: oil_counter_matters migrated to the Card IR — phase's place_counter
    # (counter_kind='oil') placer + an `_OIL_REF` ("oil counter(s)") dropped-static
    # marker for the count-operand/condition payoff phase drops. Removed from
    # _IR_FLOOR_LANES; serve hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027: ki_counter_matters migrated to the Card IR (served structurally
    # from phase's counter-kind projection — _COUNTER_KIND_KEYS['ki'] in
    # signals.py); its oracle-regex detector row is deleted. The SWEEP_LABELS
    # entry survives to feed the serve spec (signal_specs.py hand-registers it).
    {
        # Shield counters (CR 122.1c) — a real UW/Brokers archetype (Falco Spara,
        # Perrie, Kros) deliberately excluded from keyword_counter; this is its home.
        "key": "shield_counter_matters",
        "scope": "you",
        "is_widen_of": "",
        "regex": "\\bshield counters?\\b",
    },
    # ADR-0027 t2b5-C: named_counter_misc migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact deleted regex).
    # phase's structured counter_kind field covers 32 of 34 cards, but a place/remove-as-
    # COST or replacement form (Mazemind Tome, Pursuit of Knowledge) drops counter_kind,
    # a 2-card recall gap — so the byte-identical word mirror is the migratable home, not
    # the partial structural field. Its oracle-regex sweep row is deleted; SWEEP_LABELS
    # keeps the label, and the serve spec is hand-registered in signal_specs.py.
    # ADR-0027: seek_matters migrated to the Card IR (served structurally from
    # phase's `seek` effect category — _DOER_EFFECT_KEYS['seek'] in signals.py);
    # its oracle-regex detector row is deleted. The SWEEP_LABELS entry survives to
    # feed the serve spec (signal_specs.py hand-registers it).
    # ADR-0027 t2b5-C: powerup_matters migrated to the Card IR — detected from the
    # Scryfall `Power-up` keyword array (_IR_KEYWORD_MAP['power-up'], a structured-field
    # lookup, exact 1:1 with the deleted `power-up —` regex: 37 keyword carriers == 37
    # regex hits, 0 residual). Its oracle-regex sweep row is deleted; SWEEP_LABELS keeps
    # the label, and the serve spec is hand-registered in signal_specs.py.
    # ADR-0027: myriad_grant migrated to the Card IR — phase stamps counter_kind=
    # 'myriad' on the grant_keyword effect of the GRANTERS ("<class> have myriad" —
    # Blade of Selves, Legion Loyalty, Duke Ulder, Corporeal Projection) plus a
    # copy-exception conferred-keyword marker (Muddle), and the MAKERS ride the
    # Scryfall `myriad` keyword (_IR_KEYWORD_MAP). Removed from _IR_FLOOR_LANES; serve
    # hand-registered in signal_specs. The bare "\bmyriad\b" over-fired on the card
    # NAME "The Myriad Pools" (The Everflowing Well // The Myriad Pools), which the
    # structural IR correctly drops (no myriad effect or keyword).
    # ADR-0027: phasing_matters migrated to the Card IR — served structurally from
    # the Scryfall `phasing` keyword (_IR_KEYWORD_MAP) + phase's `phasing` effect
    # category (the phase-out/in DOER markers, _narrow_mechanic_refs) plus a
    # `phasing` payoff-trigger marker for the event='other' "permanents phase out"
    # payoff phase keeps only in a place_counter raw (The War Doctor). It is removed
    # from _IR_FLOOR_LANES; the serve spec is hand-registered in signal_specs.
    # ADR-0027 β: color_change migrated to the Card IR via a byte-identical kept-mirror —
    # phase parses the "becomes the color of your choice / all colors" clause
    # INCONSISTENTLY (20 AddChosenColor mods + 4 Unimplemented "become"s) and the only
    # structural anchor (cat=='animate') 90%-over-fires (256 vs 24), so the lane rides a
    # _COLOR_CHANGE_MIRROR (_signals_ir) of the exact deleted regex over the reminder-
    # stripped oracle. Its SWEEP_DETECTORS row is deleted; the EXACT regex is pinned as
    # COLOR_CHANGE_REGEX above, SWEEP_LABELS keeps the human label, and the serve stays
    # hand-registered in signal_specs.py (its own curated search regex). CR 105 / 613.
    # ADR-0027 β (kept-mirror): timing_control migrated to the Card IR. phase drops
    # the cast-timing statics entirely (it keeps only the flash-grant), so there is
    # no structural form — a byte-identical _IR_KEPT_DETECTORS word mirror (the exact
    # regex below, scope "any") is the only honest resolution. The restriction arms
    # span opponents-only (Teferi), symmetric (City of Solitude), and self (Fires of
    # Invention) — no single side is right, so scope "any" reads honestly as
    # "restricts WHEN spells can be cast", not a punish. This SWEEP_DETECTORS row is
    # deleted; SWEEP_LABELS keeps the human label, and the serve is hand-registered
    # in signal_specs.py reusing the regex. CR 117.1a / 307.1.
    # ADR-0027: end_the_turn migrated to the Card IR — served structurally from
    # phase's `end_the_turn` effect category (CR 724; the EndTheTurn effect + the
    # failed-parse "end the turn" supplement recovery, now reconciled to the same
    # category string the _DOER_EFFECT_KEYS key reads — Obeka). The serve spec is
    # hand-registered in signal_specs reusing the deleted regex.
    # ADR-0027 t2b5-A: draft_spellbook migrated to the Card IR — Arena/Alchemy digital
    # mechanics (draft-a-card / spellbook) NOT in the CR with NO phase effect category
    # (phase leaves them category='other'), so the lane fires from a
    # signals._IR_KEPT_DETECTORS word mirror (the exact regex; the literal phrasing is
    # the only signal). This SWEEP_DETECTORS row is deleted; SWEEP_LABELS keeps the human
    # label, and the serve is hand-registered in signal_specs.py reusing the regex.
    # ADR-0027 (t2b5-B): sacrifice_protection migrated to the Card IR (kept_detector).
    # phase parses only ~21/39 hits as a generic restriction (subject=None), which it
    # cannot tell from a STAX restriction (Ghostly Prison is also restriction) — the
    # protective-vs-taxing split lives only in the raw — and drops ~18/39 buried in a
    # quoted/granted ability (Assault Suit) or a make_token/sacrifice carrier (Zurgo).
    # The two literal protective phrases ("can't be sacrificed" / "can't cause you to
    # sacrifice") are the only full-coverage tell, so the IR path detects it from a
    # byte-identical _IR_KEPT_DETECTORS word mirror (CR 701.16). SWEEP_LABELS keeps the
    # human label; the serve is hand-registered in signal_specs.py reusing the regex.
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
    # artifacts_matter / edict_matters kept-row precedent. CR 604.1 (static abilities are
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
        "key": "cheat_into_play",
        "scope": "you",
        "is_widen_of": "cheat_into_play",
        "regex": "put (?:a|that|those|up to (?:two|one|\\d+))[^.]*(?:permanent|creature|land|nonland)[^.]*cards?[^.]*onto the battlefield|put a permanent card[^.]*onto the battlefield|put [^.]*land cards?[^.]*onto the battlefield|put (?:an? )?artifact,? (?:creature,? )?(?:or land |and/or land )?card[^.]*from (?:your|their) hand onto the battlefield|put an? [^.]*card[^.]*(?:from your (?:hand|library)|from among them) onto the battlefield",
    },
    {
        "key": "draw_for_each",
        "scope": "you",
        "is_widen_of": "card_draw_engine",
        "regex": "draw a card for each|draw cards equal to the number of|draws? (?:a card |cards )?for each",
    },
    {
        "key": "clone_matters",
        "scope": "you",
        "is_widen_of": "clone_matters",
        "regex": "enter (?:the battlefield )?as a copy of|may have [^.]*enter as a copy|create a copy of the card|is a copy of (?:that|the chosen) card",
    },
    # ADR-0027 β: cost_reduction migrated to the Card IR — the structural arm in
    # _signals_ir.extract_signals_ir (the projection's static ModifyCost{Reduce} +
    # screened named `reducenextspellcost` Effects) plus a NARROWED _COST_REDUCER_MIRROR
    # _IR_KEPT_DETECTORS row (recovering the genuine reducers the projection drops).
    # Its SWEEP_DETECTORS row is deleted; the serve is hand-registered in signal_specs.py
    # reusing the EXACT deleted regex (pinned above as COST_REDUCTION_REGEX). SWEEP_LABELS
    # still carries the human label. The deleted high-confidence producer fed
    # has_other_plan, but the IR arm+mirror are NARROWER (they drop the 92 self-discounts
    # the regex over-caught), so _VOLTRON_SILENCING_PLAN_KEYS re-supplies the silence
    # soundly — NO-FLOOD held (voltron membership byte-identical on the FILE-SWAP).
    # ADR-0027 β: impulse_top_play migrated to the Card IR — the structural arm (a
    # NON-static cast_from_zone Effect carrying the recovered 'from:library' zone, gated
    # ab.kind!='static' to split it from the sibling play_from_top) plus a per-clause
    # _IMPULSE_TOP_PLAY_SWEEP_RE mirror (the EXACT regex this row carried). Its
    # SWEEP_DETECTORS row is deleted; the serve is hand-registered in signal_specs.py
    # reusing the deleted regex (SWEEP_LABELS still carries the human label). The
    # high-confidence producer fed has_other_plan, so an _IMPULSE_TOP_PLAY_PLAN_MIRROR
    # in signals.py re-supplies the voltron silence byte-identically (NO-FLOOD).
    # ADR-0027: extra_upkeep + extra_draw_step migrated to the Card IR — phase's
    # `extra_upkeep`/`extra_draw` effect categories (Obeka, Paradox Haze, The Ninth
    # Doctor) plus an `_EXTRA_BEGINNING_PHASE_GRANT` dropped-static face marker that
    # emits BOTH categories for "an additional beginning phase after this phase"
    # (CR 501.1 — a beginning phase contains the untap, UPKEEP, and DRAW steps), which
    # phase mis-routes to extra_combats (Shadow/Sphinx of the Second Sun) or drops
    # entirely (Cyclonus). Neither is in _IR_FLOOR_LANES; their serve specs are
    # hand-registered in signal_specs (reusing the deleted "additional beginning
    # phase" regex). extra_end_step (CR 513) migrated earlier the same way.
    # ADR-0027 β — tribe_damage_trigger's SWEEP_DETECTORS row is deleted (migrated to
    # the Card IR via the KEPT-DETECTOR pattern: signals._IR_KEPT_DETECTORS reuses the
    # shared TRIBE_DAMAGE_TRIGGER_REGEX above, byte-identically). SWEEP_LABELS still
    # carries the human label; signal_specs hand-registers the serve.
    # ADR-0027 β — combat_damage_to_creature + combat_damage_to_opp's SWEEP_DETECTORS
    # rows are deleted (migrated to the Card IR via the KEPT-DETECTOR pattern:
    # signals._IR_KEPT_DETECTORS reuses the shared COMBAT_DAMAGE_TO_CREATURE_REGEX /
    # COMBAT_DAMAGE_TO_OPP_REGEX above, byte-identically). SWEEP_LABELS still carries the
    # human labels; signal_specs hand-registers each serve.
    # ADR-0027: creature_cast_trigger migrated to the Card IR — a cast_spell trigger with
    # a Creature subject + an effect-raw / face-oracle "whenever/when [player] casts a …
    # creature spell" scan (recovers the qualified-subject triggers the bare regex
    # missed). This SWEEP_DETECTORS row is deleted; the serve hand-spec keeps its regex.
    # ADR-0027: spell_copy_matters migrated to the Card IR — phase's `spell_copy` effect
    # (CopySpell + CastCopyOfCard) + storm/replicate/conspire/casualty Scryfall keywords
    # + a `_COPY_SPELL_REF` granted/quoted/conditional marker (project). The structural
    # IR EXCLUDES this row's `\bstorm\b` over-fire on the "… Storm" card NAME (Comet
    # Storm, Arrow Storm). This SWEEP_DETECTORS row is deleted; the hand-spec serve in
    # signal_specs.py is independent and survives.
    # ADR-0027: removal_matters migrated to the Card IR (single-target destroy/damage
    # SUBJECT + quoted-grant recursion); this SWEEP_DETECTORS row is deleted. Its regex
    # over-fired by folding board wipes ("destroy all/each", "damage divided") and land
    # destruction into removal — the IR excludes those (mass_removal / land_destruction
    # carry them). destroy_legendary (also ADR-0027-migrated, the HasSupertype:Legendary
    # destroy subject) is a DIFFERENT key.
    {
        "key": "exile_removal",
        "scope": "you",
        "is_widen_of": "exile_removal",
        "regex": "exile (?:up to (?:one|two|three|\\w+|x) )?(?:other )?target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)|exile [^.]*and target (?:permanent|creature)",
    },
    # ADR-0027: team_buff migrated to the Card IR — the grant_keyword Effect on a
    # generic "creatures you control" subject (_is_team_buff_grant + _TEAM_BUFF_GRANT_KW).
    # This SWEEP_DETECTORS row + the _HAND_FLOOR team_buff row are deleted; the hand-spec
    # serve in signal_specs reuses the deleted regex. (anthem_static, the separate
    # +N/+N stat-anthem lane that documents is_widen_of team_buff, is a DIFFERENT key
    # and stays on regex.)
    # ADR-0027: venture_matters migrated to the Card IR — its SWEEP_DETECTORS widen row
    # (dungeon / room-abilities oracle text) is deleted; the hand-registered serve spec
    # in signal_specs carries the lane (the structural IR — venture effect + condition
    # kind + trigger_doubling-over-dungeons + dropped-clause marker — does detection).
    # ADR-0027: big_hand_matters migrated to the Card IR — served from the v23
    # `no_max_handsize` Effect structural arm + the byte-identical _BIG_HAND_MATTERS_MIRROR
    # _IR_KEPT_DETECTORS word mirror (the OR of this SWEEP regex + the deleted _HAND_FLOOR
    # row) for the "X = cards in your hand" P/T-scaling payoffs + "N or more cards in
    # hand" conditions. This SWEEP_DETECTORS widen row is deleted; the hand-registered
    # serve spec in signal_specs carries the lane. CR 402.2.
    # ADR-0027: lifeloss_matters migrated to the Card IR — served from the structural
    # `lose_life` Effect (the drain / self-loss split), a `life_payment` marker + a
    # paylife engine cost, a `life_lost` trigger payoff, and the project
    # _lifeloss_markers. This sweep row + the two _DETECTORS regexes are deleted; the
    # hand-written serve specs in signal_specs.py survive (independent of the regex).
    # ADR-0027: token_doubling migrated to the Card IR — detected structurally from
    # the token-doubling replacement effect (phase v0.1.60 `replacements`, the
    # `cat == "token_doubling"` branch in extract_signals_ir). Both its oracle-regex
    # sources (this sweep row + the _HAND_FLOOR row) are deleted; the hand-written
    # serve spec in signal_specs.py is independent of these regexes and survives.
    # (Token-doubling and counter-doubling stay separate lanes — a token doubler
    # wants token MAKERS, a counter doubler wants counter SOURCES.)
    # ADR-0027: counter_doubling migrated to the Card IR — a structural
    # `cat == "counter_doubling"` replacement-effect arm (Doubling Season, Branching
    # Evolution, Primal Vigor, Corpsejack Menace, The Earth Crystal, Struggle for
    # Project Purity — the 6 the regex MISSED) + a byte-identical COUNTER_DOUBLING_REGEX
    # kept mirror in _signals_ir (the 46 one-shot/activated/triggered doublers phase
    # mangles to `double`/`place_counter`/`counter_distribute`). Both this sweep row and
    # the _HAND_FLOOR row are deleted; the hand-written serve spec in signal_specs.py is
    # independent of these regexes and survives. (Sweep floor 32→31.)
    # ADR-0027: dice_matters migrated to the Card IR — phase's native roll_die effect
    # + a `roll_die` marker (project._narrow_trigger_other_refs for the "whenever you
    # roll" payoff trigger + _dropped_static_markers for the spell/cost/reroll forms).
    # Both its oracle-regex sources (this self-widen SWEEP row + the _HAND_FLOOR
    # detector) are deleted; serve hand-registered reusing the deleted regex.
    # ADR-0027: specialize_matters migrated to the Card IR (served from the
    # Scryfall `specialize` keyword — _IR_KEYWORD_MAP in signals.py); both its
    # oracle-regex sources (this row + the _HAND_FLOOR detector) are deleted. Its
    # serve spec is hand-registered in signal_specs.py.
    {
        "key": "voltron_matters",
        "scope": "you",
        "is_widen_of": "voltron_matters",
        "regex": "create [^.]*\\bequipment\\b[^.]* token|create [^.]*\\bequipment\\b artifact",
    },
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR — a first-class `bounce`
    # Effect with no graveyard zone tag and a subject not controlled by you (excludes
    # GY-recursion and self-bounce blink). Its SWEEP row (an is_widen_of base) is
    # deleted; the serve spec is hand-registered in signal_specs.py reusing the deleted
    # regex.
    # ADR-0027 β: edict_matters migrated to the Card IR — the structural opp/each
    # `sacrifice` Effect arm (gated by signals._ir_effect_is_edict to drop leaked-scope
    # self/you-sac over-fires) plus a byte-identical signals._IR_KEPT_DETECTORS mirror of
    # this exact regex (the tail phase folds into a categoryless / mis-scoped effect).
    # This SWEEP row is deleted; the serve spec is hand-registered in signal_specs.py
    # reusing the deleted regex (inlined as _EDICT_SWEEP_REGEX there). CR 701.16.
    {
        "key": "artifacts_matter",
        "scope": "you",
        "is_widen_of": "artifacts_matter",
        "regex": "if you control an artifact|if you control (?:a|an|one or more) artifacts?",
    },
    # ADR-0027 t2b4-C: self_blink migrated to the Card IR (kept_detector) — the
    # `~`-substituted exile raw can't be told from cost-exile / other-target exile, so
    # there is no clean structural IR form. The regex path produced it from two disjoint
    # sources; both are reproduced byte-identically in extract_signals_ir (the name-aware
    # _detect_self_blink_fulltext + the _SELF_BLINK_SWEEP_RE single-target regex run
    # per-clause). This SWEEP_DETECTORS row is deleted (its regex now lives as the
    # _SELF_BLINK_SWEEP_RE constant in signals.py); the serve spec stays hand-registered.
    # type_matters_anthem deleted: its `\b(\w+?) creatures get [+]` was subject-LESS and
    # redundant — real typed anthems ("Goblins you control get +1/+1") are produced as
    # subject-bearing type_matters by the parametric detector, and its junk captures
    # ("all/attacking/color creatures get +") belong to anthem_static.
    # ADR-0027: group_hug_draw migrated to the Card IR (the symmetric group-hug draw
    # lane: a card that draws for EVERY player — Howling Mine, Wheel of Fortune,
    # Prosperity, Timetwister, Windfall). Detected from a `draw` Effect scope=='each'
    # (the v22 structural tell for "each player draws") in signals.extract_signals_ir,
    # UNION a BYTE-IDENTICAL kept WORD MIRROR (GROUP_HUG_DRAW_REGEX in
    # signals._IR_KEPT_DETECTORS, scope 'each') for the 4 cards phase under-structures
    # (Grothama / Mathise / Vault 11 fold "each player draws" to a scope-'any' draw →
    # target_player_draws; Winter Sky's coin-flip branch emits no draw Effect). The
    # structural arm ALSO adds 37 wheel/mass-draw cards the narrow regex missed on
    # word-adjacency ("each player discards their hand, THEN draws"). This
    # SWEEP_DETECTORS row is deleted (its regex now lives as the GROUP_HUG_DRAW_REGEX
    # constant above); SWEEP_LABELS keeps the human label and the serve spec is
    # hand-registered in signal_specs.py reusing it. CR 120.2.
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
    "animate_artifact": (
        "Animate artifacts",
        "artifacts to animate plus artifact-creature payoffs",
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
    "airbend_matters": (
        "Airbend",
        "airbend exile-and-recast tempo and payoffs for airbending",
    ),
    "earthbend_matters": (
        "Earthbend",
        "earthbend land-animation, +1/+1 counters, and payoffs for earthbending",
    ),
    "waterbend_matters": (
        "Waterbend",
        "waterbend alternate-cost (tap artifacts/creatures) cards and payoffs",
    ),
    "firebending_matters": (
        "Firebending",
        "firebending attack-trigger red mana and payoffs for firebending",
    ),
    "blocked_matters": (
        "Blocks matter",
        "combat triggers when creatures block or become blocked",
    ),
    "boast_matters": ("Boast", "boast creatures and ways to attack safely"),
    "cant_block_grant": ("Can't-block", "force blockers off to clear a path to attack"),
    "cast_as_named_card": ("Cast-as", "play cards as though they were another card"),
    "changeling_matters": (
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
    "conjure_matters": ("Conjure", "conjure effects (Alchemy)"),
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
    "damage_reflect": ("Damage reflection", "high-toughness bodies to reflect damage"),
    "damage_to_you_punish": (
        "Punish damage to you",
        "take damage and punish the source",
    ),
    "debuff_matters": (
        "-1/-1 / shrink",
        "minus-counter and toughness-shrink removal plus payoffs",
    ),
    "destroy_legendary": ("Legend removal", "targeted destruction of legends"),
    "devour_matters": ("Devour", "token fodder to devour"),
    "dies_recursion": (
        "Dies-recursion",
        "anything that makes creatures recur when they die — with or without counters "
        "(undying/persist plus bare dies-return like Feign Death)",
    ),
    "dig_until": ("Dig-until", "deep top-of-library digging effects"),
    "discard_outlet": (
        "Discard outlets",
        "loot/rummage outlets to fuel discard and graveyard payoffs",
    ),
    "domain_matters": ("Domain", "basic land types and fixing to grow domain"),
    "donate_matters": ("Donate", "give away downside permanents for advantage"),
    "draft_spellbook": (
        "Draft / spellbook",
        "draft-a-card and spellbook effects (Alchemy)",
    ),
    "draw_for_each": ("Scaling card draw", "grow the count your draw scales with"),
    "each_mode_player": ("Spread-the-modes", "modal effects that hit each player"),
    "edict_matters": (
        "Edicts / forced sacrifice",
        "edicts to make opponents sacrifice",
    ),
    "evasion_denial": (
        "Anti-landwalk defense",
        "strip an opponent's landwalk so you can block (CR 702.14)",
    ),
    "excess_damage": ("Excess damage", "trample and big hits to exploit excess damage"),
    "exhaust_matters": ("Exhaust", "exhaust abilities (once per game)"),
    "exile_until_leaves": ("O-Ring removal", "exile-until-leaves removal effects"),
    "explore_matters": ("Explore", "explore creatures plus counter/graveyard payoffs"),
    "extra_land_drop": (
        "Put lands into play",
        "lands to drop straight onto the battlefield",
    ),
    "facedown_matters": (
        "Face-down / morph",
        "morph/manifest/disguise creatures and flip payoffs",
    ),
    "fight_matters": ("Fight", "big creatures to fight with as removal"),
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
    "lure_matters": ("Lure", "lure effects plus deathtouch/trample to punish blocks"),
    "mass_bounce": ("Mass bounce", "board-wide bounce and ETB re-use"),
    "mass_removal": ("Board wipes", "sweepers plus resilience to rebuild"),
    "miracle_grant": ("Miracle", "miracle support and top-deck setup"),
    "myriad_grant": ("Myriad", "attackers worth copying to each opponent"),
    "rad_counter_matters": (
        "Rad counters",
        "rad-counter sources and payoffs (Fallout — each player mills + loses life per rad)",
    ),
    "oil_counter_matters": (
        "Oil counters",
        "oil-counter sources and payoffs (Phyrexia — charge-style depletion counters)",
    ),
    "ki_counter_matters": (
        "Ki counters",
        "ki-counter sources and payoffs (Kamigawa Spirit/Arcane triggers)",
    ),
    "shield_counter_matters": (
        "Shield counters",
        "shield-counter sources and payoffs (Brokers — a counter that absorbs the next "
        "destroy/damage)",
    ),
    "named_counter_misc": (
        "Other named counters",
        "enablers and payoffs for a niche named-counter mechanic",
    ),
    "named_permanent": (
        "Named-card synergy",
        "the specific named cards this references",
    ),
    "ninjutsu_matters": (
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
    "phasing_matters": ("Phasing", "phase-out effects for protection and resets"),
    "play_from_top": ("Play from the top", "top-of-library access plus reveal payoffs"),
    "playtest_matters": ("Playtest cards", "Mystery Booster playtest-card effects"),
    "power_double": ("Power doubling", "big creatures to double in power"),
    "powerup_matters": ("Power-up", "power-up counters and payoffs"),
    "protection_grant": (
        "Grant protection",
        "creatures worth protecting with hexproof/protection",
    ),
    "pump_matters": (
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
    "soulbond_matters": ("Soulbond", "creatures to pair via soulbond"),
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
    "theft_matters": ("Theft", "steal opponents' cards and cast them"),
    "timing_control": (
        "Timing restriction",
        "effects that restrict WHEN spells can be cast (Teferi, City of Solitude, "
        "Fires of Invention)",
    ),
    "end_the_turn": (
        "End the turn",
        "end-the-turn effects to lock in your turn's value and fizzle end-step "
        "downsides (Sundial of the Infinite, Glorious End, Obeka)",
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
    "void_warp_matters": ("Void / warp", "void and warp cards (Edge of Eternities)"),
    "win_lose_game": (
        "Alternate win/lose",
        "alternate win conditions and ways to enable them",
    ),
}
