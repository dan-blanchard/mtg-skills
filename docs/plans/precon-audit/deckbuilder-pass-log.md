# The 25-precon deckbuilder pass: batches and re-reads (2026-11-01 to 2026-11-03)

Every shipped batch of the precon deckbuilder pass (batches 15c through 17d),
with its numbered fixes, the measurement on the 25 / held-out 20 / fresh 10,
and the verdicts each re-read settled; then the full 55-deck re-read record.
Moved here from `docs/plans/backlog.md`'s "Settled" section (its header: an
entry is deleted when it ships). The verdicts a re-read's reviewers apply are
in `reread-brief.md` beside this file; `verify_symptoms.py` holds the
regression checks each batch claims.

- **Shipped, keyed on commander structure, measured on the 25 (734 / 339 / 120
  → 733 / 341 / 121 swaps / guide cuts / guide adds) and the held-out 20 (579
  / 253 / 83 → 578 / 252 / 101).** (1) *The commander's needs outrank
  play-rate on its theme pages* (`swaps._ranked_pool`'s need lead,
  `_upgrades`' need gate; the needs the deck builds toward —
  `_NEED_BUILT_FLOOR` — that are a role in the plan, not more of what the
  commander already does (`kind == "redundancy"`: Ms. Bumbleflower's page
  filled with wheels) nor a property of the card (`Need.leads`: "cheap
  spells", "instants and sorceries")): Felothar's walls (Abzan Armor 2 → 6
  guide adds), Morska's Clue makers (Deep Clue Sea 5 → 8), Ellivere's Auras.
  Need reads fixed on the way: a keyword lord's bodies read off the card's
  keywords (`defender bodies` matched nothing); an artifact-TOKEN payoff asks
  for the token makers, not every artifact (Gimbal); a toughness-reading
  commander wants HIGH toughness (`commander_need.HIGH_TOUGHNESS`), not a butt
  — "toughness over power" put Snubhorn Sentry over Ghalta on Pantlaza's page;
  a voltron commander whose own suit is Auras asks for Auras, never Equipment
  (Ellivere; `Sourcing.aura_commander` filters her voltron pages the same
  way). (2) *Near-miss combos*: at
  most two adds completing a line on one deck card (`swaps._COMBO_PIECE_ADDS`;
  Blood Rites took five Exquisite Blood partners), and never a named add
  costing more than anything the deck runs (Mardu Surge's Blightsteel
  Colossus). (3) *A trim takes the card serving the fewest of the deck's
  themes first*, then the least played (`cut_candidates`). (4) *A tribe
  member's slot stays the tribe's*, members and changelings only, unless the
  commander makes that tribe's tokens itself (`Sourcing.tribe_spec`; Disa's
  Lhurgoyfs went to the graveyard page, Herald's Horn took a Dinosaur's slot,
  Quintorius's weak Spirits became other Spirits). (5) *Under a commander
  whose plan is its top end* (a need with `Need.mana_floor` ≥
  `tune.TOP_END_FLOOR`) the ramp and card-draw rows are the plan's fuel, never
  a trim (`plan_fuel`; Eldrazi Unbound trimmed four rocks and three draw
  engines). Guide-score losses taken knowingly: Tinker Time 3 → 2, Graveyard
  Overdrive 6 → 4 (its Lhurgoyfs are no longer cut at all), Eldrazi Unbound 1
  → 0 (its one hit was a draw trim's add).
- **Batch 2 (same day; the 25 733 / 341 / 121 → 729 / 340 / 121, held-out 578
  / 252 / 101 → 578 / 252 / 99).** (7) *A life-loss trigger gated to
  opponents' turns* (Valgavoth's `OncePerOpponentPerTurn`) asks for makers
  that fire on their turns — a trigger watching what opponents do
  (`opponent_*` watcher keys, a tax, a payoff lane scoped past "you":
  `commander_need._drains_on_opponents_turns`), never your own spells'
  riders; the payoff read's generic "lifeloss makers" stands down beside it.
  Endless Punishment's page is Painful Quandary, Underworld Dreams, Razorkin
  Needlehead, Sheoldred where it was Guttersnipe and Reckless Fireweaver. A
  need read off the commander's own trigger or condition leads its page
  whatever the deck holds yet (the `_NEED_BUILT_FLOOR` is for resource and
  payoff needs). (8) *Izzet Generatorium is an energy maker* through the
  ledger row `energy_gain_replacement_parked` (ADR-0048: its "you get that
  many plus one {E} instead" is a phase `replacement_structure` residue);
  Living Energy takes it and Aether Refinery again.
- **Batch 3 (same day; the 25 729 / 340 / 121 → 723 / 339 / 118, held-out 578
  / 252 / 99 → 573 / 256 / 100 — the held-out gate's floors cleared, the 25's
  three adds taken knowingly).** (9) *A graveyard-to-battlefield effect wants
  its payload*: a permanent card of the filter's types at
  `commander_need.REANIMATION_MV` (7) or more — the top end a deck cheats in,
  where Death Toll's guides' adds sit (Overlord of the Balemurk, Hoarding
  Broodlord); not a land (Teval), not a tribe's card (Sidar Jabari's Knights,
  Admiral Brass's Pirates, which come back as 4/4s), not a unit that sizes
  the card itself (Meren's experience, Alesha's power). Hornet Queen goes to
  Myr Battlesphere and Vile Mutilator to Meteor Golem where they went to
  Buried Alive and Beast Within. (10) *A commander that takes a typed card
  from its graveyard wants that type put there* (Anikthea's enchantments: the
  self-mill and discard outlets its guides add; the one graveyard-fill need
  the "put into your graveyard" trigger read and this share,
  `_graveyard_fill_need`). (11) *A token effect that favours one kind of
  token asks for makers of that kind* (Hazel's "if that token is a Squirrel,
  instead create two": `token_maker|you|Squirrel`). (12) *A land-sacrificing
  commander's consumers include the repeatable extra land drops*
  (`card_reads.plays_extra_lands` — Exploration, Azusa, Oracle of Mul Daya,
  not Explore's one turn; the landfall lane folds the read into its umbrella
  key, so the need reads it as a predicate). (13) *An ident-derived
  mana-value need stands down for the tree-read one* (Bello's
  `animate_makers|you|Artifact>=4` dropped his "non-Equipment": Hammer of
  Nazahn and Leyline Axe led his page), and *a mana-value-floor need is never
  broad* (`is_broad`; his need is 10.5% of a Gruul pool and had no page at
  all). (14) *An upgrade keeps what the cut gives the commander, whatever the
  job* (`_upgrades`: Living Death stays under Teval, Squirrel Nest and Deep
  Forest Hermit under Hazel — Assassin's Trophy and Fanatic of Rhonas supply
  none of their needs); and (15) *a trim takes a card supplying a built need
  last, ahead even of the fixing shield* (Oracle of Mul Daya over Harrow under
  Yuma). Swap counts fell where a gated upgrade found no replacement
  (Veloci-Ramp-Tor 30 → 27, Sultai Arisen 30 → 28): a card the commander
  asks for and nothing better for it is no swap.
- **Batch 4 (same day, the recursive pass over batch 3's own proposals; the
  25 723 / 339 / 118 → 719 / 338 / 117, held-out 573 / 256 / 100 → 574 / 256
  / 101).** (16) *A led page's deep suppliers join its play-rate head*
  (`swaps._ranked_pool`): a card the lead ranks ahead of every addable card
  in the head (Hazel's Squirrel makers, two needs to the head's one) is on
  the page though play-rate never reached it — Squirreled Away takes Drey
  Keeper, Scurry Oak, Camellia, Cloakwood Hermit, Squirrel Sanctuary where
  Fanatic of Rhonas and Oketra's Monument took Squirrel Nest's and Deep
  Forest Hermit's slots. Measured and held back on the way: the whole page
  sorted and cut to the lead's top — a thousand obscure one-need cards, and
  the tune spent its budget on them before its job upgrades (held-out
  Counter Intelligence 30 → 21 swaps; Enduring Enchantments took eight
  self-mill enchantments). (17) *A need-count admission never trades down a
  card that already served the commander* (`_upgrades`, the card-quality
  read as the guard): Zetalpa, Primal Dawn went to Shield-Wall Sentinel for
  ticking two of Felothar's boxes to its one. (18) *Valgavoth's
  opponents'-turn read covers the watchers no lane key names*
  (`_drains_on_opponents_turns`: a trigger on a player action by opponents
  or every player — Harsh Mentor's "an opponent activates", Kaervek's "an
  opponent casts" — or on a permanent an opponent controls, Blood Seeker;
  not the card's own attack or cast, nor a sweeper's "any": Myr
  Battlesphere, Crypt Ghast and Toxic Deluge, which the first widening
  admitted). Blood Seeker, Harsh Mentor and Stormfist Crusader are kept
  where they went to Guttersnipe and Reckless Fireweaver; Endless
  Punishment proposes 20 swaps on its $126 (30 on an unlimited budget): the
  right replacements are the pricier drainers. (19) *A `graveyard_leave_matters`
  lane* ("Cards leaving your graveyard": Teval, Desecrated Tomb, Chalk
  Outline, Tormod, Syr Konrad's second trigger — read off the trigger's
  graveyard origin through the shared `trigger_zone_changes`), and *a payoff
  with no maker lane behind it is its own redundancy*
  (`commander_need._PAYOFF_REDUNDANCY_KEYS`: "graveyard leave payoffs like
  the commander" under Teval). (20) *Mirko's dropped "power less than"
  clause* is read off the ability's description behind a `retirement_canary`
  (`_desc_sizes_the_card`; phase v0.118.0 keeps no residue), so his return
  states its own line and opens no payload page.
- **Batch 5 (2026-11-02, the pass over batch 4's proposals and the held-out
  decks' own; the 25 719 / 338 / 117 → 729 / 340 / 120, held-out 574 / 256 /
  101 → 577 / 259 / 104).** (21) *A payoff for what the deck doesn't do is no
  add* (`swaps.dead_payoff` over `metrics.payoff_feeders`, the inverse of
  `_cares_keys` plus the multipliers' feeders): every mechanic the card cares
  about has fewer than `_FEEDER_FLOOR` (5) doers in the deck and the card
  feeds none itself — a choose-a-creature-type payoff with no tribe of ten,
  a counter doubler where nothing places counters. Banner of Kinship, Door
  of Destinies and Coat of Arms leave Bello's page; Etali (its own poison),
  Myr Battlesphere (its own Myr) and every card caring about nothing the read
  names stay. (22) *A trim's add takes at most the purse cap past the share*,
  as an upgrade's does (`_PURSE_CAP`): Sheoldred, the Apocalypse took half of
  Endless Punishment's $126 and the tune ran dry at 20 swaps; 30 again, with
  Razorkin Needlehead. (23) *A tribe member with a job keeps the tribe's slot
  while its row is in band or over*, as a flip does (`upgrade_spec`: Aryel,
  Knight of Windgrace's removal went to An Offer You Can't Refuse and
  Cavalry Charge lost a Knight). (24) *A tribe member and every need's
  supplier, the redundancy needs' included, trim last from an over-band row*
  (`cut_candidates`: Cavalier of Thorns went as surplus ramp under an
  Elemental commander whose guides add Cavaliers; Kwain, Itinerant Meddler
  as surplus draw under Ms. Bumbleflower). Dance of the Elements takes
  Cavalier of Night, Solitude and Animar; Animated Army takes Fiery
  Emancipation and Guardian Project again.
- **Batch 6 (2026-11-02; the 25 729 / 340 / 120 → 730 / 340 / 120, held-out
  577 / 259 / 104 unchanged).** The dead-payoff read tightened on its own
  misfires: (25) *a `subtype_ref` is a care only for a creature type among
  YOUR permanents* — Farseek's Plains, Scourge of Fleets' Islands and Sram's
  Auras are no tribe the deck fields; (26) *a life payment and an untapper are
  not what the card is for* (`metrics.NO_FEEDER_READ`: Black Market
  Connections' `wants_lifegain`, Teferi, Hero of Dominaria's `untap_engine`);
  (27) *a card with an independent doer is never dead* (`metrics.NEUTRAL_KEYS`
  names what a card IS rather than does; a multiplier's own feeder tag —
  Hardened Scales' extra counter — and the umbrella payoffs don't count):
  Birgi's boast unfed, her mana a doer; (28) *a choose-a-creature-type card
  is tribal through and through* (`chooses_a_type_without_tribe`): no tribe of
  ten, dead on every page — Vanquisher's Banner drew nothing for Bello's deck
  as a card-draw upgrade. Measured and held back on the way: the whole
  dead-payoff read on job pages (the 25 120 → 116 guide adds: Farseek,
  Scourge of Fleets, Black Market Connections, Teferi all vetoed, and the
  banner still through on its draw key).
- **Batch 7 (2026-11-02; the 25 730 / 340 / 120 unchanged, held-out 577 /
  259 / 104 unchanged).** (29) *A trigger gated on a creature type the deck
  lacks is a dead payoff too*, read off phase's trees (now `swaps._unit_gates`,
  batch 12: each trigger's `valid_card` subtypes, the field
  `ranking._ir_gate_subtypes` reads on the compat Card — whose sidecar CI has
  no copy of, which the CI-style run caught): when most of the card's
  triggers are so gated and it has nothing to activate, whatever they do
  waits on a tribe that never comes. The gate rule (`gated_without_feed`:
  this and the choose-a-type read) applies on every page, a job page's
  included — Dragon Tempest left
  Endless Punishment's and Creative Energy's interaction upgrades. The CR's
  creature types only (`_card_ir.creature_types`): Ygra, Eater of All's Food
  is an artifact type the deck makes, and the bulk-harvested
  `CREATURE_SUBTYPES` list holds it.
- **Batch 8 (2026-11-02).** (30) *A commander whose static makes its
  permanents creatures and sends them into combat wants support for those
  attackers* (`commander_need._static_needs` → `_animates_attackers`: an
  `AddType` of Creature beside a granted combat-damage trigger or haste; the
  need `support for the attackers the commander makes`, keys
  `_ATTACKER_SUPPORT_KEYS` — team pumps and anthems, team protection, evasion
  grants). Bello's page now leads with Asceticism, Glorious Sunrise, Sight of
  the Scalelords and Akroma's Memorial (two of his needs) over Panharmonicon
  and Mystic Forge (one), the guides' adds where play-rate gave idle
  artifacts; 6.8% of a Gruul pool, specific. Within the page's play-rate
  head: Asceticism, Eldrazi Monument, Enduring Courage and The Fire Crystal
  lead; Glorious Sunrise and Sight of the Scalelords sit past it. Measured
  and held back first: an other-lanes lead scoped to floor-plan commanders,
  which traded his idle artifacts for obscure artifact creatures (Big Mother
  Mouser, Lux Artillery); and deep ties with the head's best tier admitted
  while that tier is thin, which flooded the page with obscure artifacts
  (Gruul War Plow, Horn of Deafening) and took Counter Intelligence back to
  21 swaps.
- **Batch 9 (2026-11-02; both sets unchanged).** (31) *A doubler is for what
  the deck does a lot*: a multiplier's feeders (`swaps._MULTIPLIER_FEEDER_FLOOR`,
  twice the dead-payoff floor, ten) — Anikthea's five incidental counter
  cards (constellation) kept Hardened Scales and Branching Evolution alive on
  her enchantments page; now dead there, while Hazel's eighteen token makers
  keep Doubling Season and Parallel Lives.
- **Batch 10 (2026-11-02; the 25 730 / 340 / 120 → 732 / 341 / 121,
  held-out 577 / 259 / 104 → 571 / 255 / 103, fresh 10 — pre-pass baseline
  295 / 130 / 38 → 291 / 126 / 37).** The pass re-read against the fresh
  set and a card-by-card check of every earlier flaw. (32) *A counter
  commander's consumers include the doublers, replacement bonuses and
  proliferators* (`commander_need._EXTRA_CONSUMER_KEYS["plus_one_makers"]`):
  Call for Backup had lost Doubling Season, Evolution Sage, Ozolith and
  Hardened Scales to two-need obscurities (Sphere Grid, Lion Sash) — 8 → 3 →
  7 guide adds. (33) *A jobless cut is never traded down* (`_upgrades`:
  both play-rate-free admissions, off-theme and need-count, stop at a
  candidate the card-quality read rates below a cut with no template job or
  protection): Zetalpa, Primal Dawn stays in Abzan Armor (his toughness need
  is too broad to page, so neither earlier guard reached him). (34) *A tribe
  slot falls back to the main theme when the tribe's page holds nothing
  better* (never a flip's). (35) *The attacker-support need excludes
  Equipment* (gear helps one creature; Hammer of Nazahn led Bello's page as
  support), and (36) *a card's own combat damage is not an opponents'-turn
  drain* (`_OWN_COMBAT_KEYS`: Sword of Fire and Ice, Rankle). Verified on
  the latest run: Bello's page holds Asceticism and none of the banners,
  Coat of Arms or gear; Endless Punishment has 30 swaps with no Guttersnipe,
  Dragon Tempest or own-combat gear and keeps Blood Seeker, Harsh Mentor and
  Stormfist Crusader; Living Death, Squirrel Nest, Deep Forest Hermit,
  Oracle of Mul Daya and Zetalpa are kept; Squirrel makers are added;
  Anikthea's page has no counter doublers; Aryel stays a Knight; Cavalier of
  Thorns and Kwain are no trims; Mirko opens no payload page; Bright-Palm's
  counters staples are back.
- **Batch 11 (2026-11-02; the 25 732 / 341 / 121 → 732 / 340 / 121,
  held-out 571 / 255 / 103 → 578 / 259 / 103, fresh 291 / 126 / 37 → 295 /
  130 / 37).** The last two residues fixed. (37) *A tribe slot whose page
  holds nothing better is routed as any theme cut's is*: the main theme, then
  the pages of the needs the cut supplies (`propose_swaps`' upgrade loop;
  Explorers of the Deep's weak Merfolk feed Hakbal's counters — Benthic
  Biomancer goes to Ozolith, and the deck has its 30 swaps and 13 guide cuts
  again). (38) *Under a tight purse — an even share under `_TIGHT_SHARE`
  ($2) a swap, below a played staple's price — a theme page's near tie looks
  `_CHEAPER_WINDOW_THEME` (40) candidates deep* for the cheaper card of the
  same popularity: Counter Intelligence's $40, half of it on Aetherflux
  Reservoir (a combo piece), ran dry at 24 swaps with the cheap counters
  cards past the tenth candidate; 30 again. Measured and held back: the
  wider window for every purse (Pantlaza's Etali went to Tyrranax Rex on a
  $286 budget, three guide adds), and a near tie by equal need count
  whatever the popularity gap (not needed once the window was tight-purse
  only). Verified on the run: all of batch 10's checks, plus Etali kept
  under Pantlaza, Counter Intelligence at 30 swaps, Explorers at 30 with its
  weak Merfolk cut.
- **Batch 12 (2026-11-02; the 25 732 / 340 / 121 → 733 / 339 / 119,
  held-out 578 / 259 / 103 → 576 / 259 / 104, fresh 295 / 130 / 37 → 295 /
  133 / 39).** The fresh ten re-read deck by deck after batch 11. (39) *A
  unit gated on a card type or a gear type the deck lacks is as dead as one
  gated on a tribe* (`swaps._unit_gates` replaces `_tribe_gates`: a trigger's
  `valid_card` and a static's `affected` give their creature types, the card
  types in `_GATE_TYPE_WORDS` — instant, sorcery, artifact, enchantment,
  planeswalker, legendary — and their other subtypes; a card type is fed by
  `_TYPE_GATE_FLOOR` (15) cards of it, a creature or gear type by the
  feeder floor; a type a static grants feeds its gate (Ygra's Food); the
  card's own type and tokens feed a trigger's gate, never a static's — a lord
  for other Zombies; `deck_profile` now counts the deck's type words too).
  Docent of Perfection (two Wizard tokens a turn in an Eldrazi deck with
  thirteen spells), Puresteel Paladin (two Equipment), Death Baron, Kor
  Spiritdancer, Starfield Mystic (Party Time's Cleric and Wizard pages),
  Rising of the Day (seven legends) and Cyberdrive Awakener are gone from
  the pages; Sai, Master Thopterist (an activated draw) and Danitha (phase
  types only her cost reduction) stay admissible by design. (40) *The ramp
  band rises with the deck's top end* (`budgets.top_end_ramp_shift`: one
  slot per two nonland cards at effective mana value five or more beyond
  fourteen per hundred, on both ends of the band, reported as the row's
  `top_end_shift`): the guides keep sixteen to twenty-two ramp in the decks
  with twenty-five or more five-drops and trim none; a flat band cut Eldrazi
  Incursion's three Talismans, Awakening Zone and Forsaken Monument for
  "ramp over by 9" (now the two Hedrons, the guide's cuts, over by 2 at
  17-19), Necron Dynasties' Illuminor Szeras — a guide add — for over by 1,
  and Temur Roar's and Prismari Artistry's ramp the guides added to. Cost:
  Animated Army's trim list is four shorter (Rain of Riches, a guide cut,
  no longer reached), Temur Roar proposes 24 swaps for 27. (41) *A sacrifice
  a mandatory trigger forces at a time you don't pick is the card's drawback,
  not an outlet* (`board_and_ramp._forced_sacrifice_unit`, before the
  sacrifice-outlet lane's effect arm: a phase trigger — Rust Elemental's,
  Lord of the Pit's, Braids' upkeep — or a trigger any player's action fires,
  Desecration Elemental's "whenever a player casts a spell"; an enters,
  attack or your-own-cast trigger stays one): Ashling's "creatures that
  sacrificed" need had put Rust Elemental and Desecration Elemental on Dance
  of the Elements' page as two-need suppliers. Verdict, not a fix: Omo's
  primary lane is Combat (her attack trigger is how her counters land, and
  the deck holds no everything-counter lane), so Tricky Terrain's theme page
  serves combat support for Omo where the guides build land-type payoffs;
  the tuner's read is a defensible plan, the guides' needs a lane the deck
  doesn't hold — superseded by batch 13's need read. Verified with
  `docs/plans/precon-audit/verify_symptoms.py` (31 / 31 on this run; 20 / 31
  on the previous — every batch-12 check bit).
- **Batch 13 (2026-11-02; the 25 733 / 339 / 119 → 733 / 340 / 121,
  held-out 576 / 259 / 104 unchanged, fresh 295 / 133 / 39 → 294 / 132 /
  40).** Batch 12's proposals re-read on all three sets. (42) *A
  commander whose static makes permanents every creature type wants the
  payoffs those types unlock* (`commander_need._static_needs` →
  `_grants_all_creature_types_node`, an `AddAllCreatureTypes` modification,
  read before the controller gate since Omo's counters land on any player's
  permanents; the need `payoffs for the creature types the commander grants`,
  predicate `_typal_payoff`: a typed anthem, a tribal reference to a creature
  type or a shared one, a choose-a-type card) — and under such a commander
  every tribe is one the deck fields (`commander_need.grants_all_creature_types`,
  which `swaps.deck_profile` reads off the commander classes: every CR
  creature type at twice the feeder floor), so Roaming Throne and Coat of
  Arms are no longer dead there. Tricky Terrain's page turns from combat
  support for Omo (Talrand, Aqueous Form, Crashing Drawbridge, Blade of
  Selves) to the guides' direction (Herald's Horn, Vanquisher's Banner,
  Kindred Discovery, Imperious Perfect, Elvish Warmaster): 2 → 4 guide adds.
  (43) *A rock whose colors are another player's lands' fixes on their terms*
  (`job_quality.ramp`: `borrowed_colors` off the `OpponentLandColors` mana
  node halves `fixes`; Fellwar Stone 0.700 → 0.685, below a Signet). (44)
  *A job upgrade at the same or a higher mana value never reads worse at the
  job than the card it replaces* (`swaps._reads_worse_at_the_job`, before
  the needs gate; a cheaper card is a tempo upgrade whatever the read says —
  Duplicant for Meteor Golem — where "cheaper" is the job read's own deploy
  cost when it has one, `_job_cost`: Wayfarer's Bauble costs three to the
  ramp read, not its printed one, so it undercuts no Signet — Jeskai Striker
  had taken it for Azorius Signet). The read still decides membership and
  play-rate still orders (ADR-0060); this is the floor under a swap for its
  own sake: Golgari Signet for Fellwar Stone (Death Toll), Simic Signet for
  Cultivate and Ripples of Potential for Innkeeper's Talent (Explorers, now
  29 swaps), Infernal Grasp for Withering Torment and Casualties of War for
  Feed the Swarm (Witherbloom), Chain Reaction for Aetherize (Counter
  Intelligence) all stop, while Damn still goes to Toxic Deluge (three to
  the wipe read against Damn's overloaded four: cheaper); Squirreled Away
  gains Drey Keeper and Bitterblossom. Verdicts: Temur
  Roar's 24 swaps are the settled lane rule — its unreached guide cuts are
  carers and lane doers of the Dragon lane, which verdict (a) below keeps
  ("a feeder nobody plays", never a function read); Animated Army's four
  fewer ramp trims are the curve-aware band's reading of a 26-ramp deck whose
  guides keep 25. Verified with `verify_symptoms.py` (35 / 35 on this run,
  the four batch-13 checks failing on the previous).
- **Batch 14 (2026-11-02; the 25 733 / 340 / 121 → 735 / 337 / 114, held-out 576 / 259 /
  104 → 571 / 262 / 105, fresh 294 / 132 / 40 → 294 / 126 / 49).** Two Sonnet deckbuilder reviews of
  every proposal on the three sets (the first a read of the 25, the second of
  the held-out 20 and the fresh 10), each flag checked against the cards and
  the code. Fixed: (45) *A colorless commander's identity is ``"C"``, never
  the empty string* (`tune._deck_identity`, `engine.deck_color_identity`; the
  search read "" as no restriction and Zhulodok's deck took Swords to
  Plowshares, Deadly Dispute and Etali — eleven colored adds; `misses.py`
  now records `identity_violations` and the symptom script pins them at
  zero). (46) *The gate read reaches abilities, spells, counters, creature
  tokens and colors* (`swaps._ability_gate_words`: a sacrifice in an
  activated ability's cost and every typed filter its effects reach over
  your permanents — Skirk Prospector's Goblin, Grinding Station's and Sai's
  artifacts, Brass Squire's Equipment; a spell's filters — Inspiring Call's
  creatures with +1/+1 counters, fed by the deck's counter makers; a static
  over your creature tokens — Intangible Virtue, fed by creature-token
  makers, Clues none; a cost reduction's spell filter and its color —
  Oketra's Monument's white creature spells, fed by fifteen cards of the
  color; a self-only activated ability — Scourge of Valkas's firebreathing —
  is nothing to activate; and a card's own type feeds no gate, so Scourge's
  one Dragon is itself). Inspiring Call and Intangible Virtue were flagged
  dead in Animated Army, Tinker Time and Deep Clue Sea; each holds six or
  more makers, so they stay. (47) *A tribal commander wants its tribe's
  payoffs and keeps them* (`commander_need._tribe_payoff_needs` off
  `subtype_ref|you|<Type>`; `typal_payoff_for`: a lord, a typed anthem, a
  reference beside any key but a rider's (`_RIDER_KEYS`: the body, a mana
  ability, a graveyard side effect) — never Drover of the Mighty's Dinosaur
  rider on a mana dork, which held Veloci-Ramp-Tor's ramp to Dinosaur cards;
  an allow-list of payoff keys dropped The First Sliver and Sliver Overlord
  and cost Sliver Swarm four guide adds, measured — or a choose-a-type card; `Sourcing.tribe_kinds`; `cut_candidates` sorts need
  suppliers last in every upgrade tier, trims a tribe payoff last
  (`tribe_member`), and the low-value tier skips a need supplier; keeping
  the payoffs out of the off-lane tiers altogether was measured and
  reverted — Sliver Swarm's, Fae Dominion's and Eternal Might's fringe
  choose-a-type cards are their upgrade pool, the 25 734 / 337 → 722 / 332
  with it). Riders of Rohan's page gains Thalia's Lieutenant,
  Champion of the Parish, Riders of Gavony and Coppercoat Vanguard. (48) *A
  main the commander doesn't hold is the deep lane where the commander's own
  lanes hold too few doers for a half* (`metrics.focus`: Temur Roar's 42
  Dragons under Eshki's eleven pingers; 24 → 30 swaps, 8 → 13 guide cuts;
  with every main's members in the pool instead the off-lane upgrades that
  found adds were displaced — held-out 576 / 259 → 542 / 250, measured; with
  the fallback off, 564 / 251 against 572 / 261 — measured the same day, so
  it stays). (49) *A theme slot upgraded on play-rate alone stays within a
  band of its cost downward* (`_upgrades`: Garruk, Cursed Huntsman's six is
  not Chatter of the Squirrel's one); the card-quality read decides nothing
  here, it rates Garruk below the cantrip. (50) *A job card on the theme
  page keeps its job read, the cheaper exemption within one band*
  (`_reads_worse_at_the_job` with `upgrade_job(cut)`; `_cost_band`:
  Niv-Mizzet, Parun's draw is not Thrill of Possibility's; Duplicant's six
  for Meteor Golem's seven stands; an off-theme slot leaves its role by
  design). (51) *A multi-role card, a mana doubler and a theme-serving piece trim
  last from an over-band row, ahead of the fixing shield* (Wrenn and Seven's
  ramp beside its draw; Forsaken Monument and Mana Reflection,
  `_MANA_DOUBLER_KEYS`; Awakening Zone's Spawn under Ulalek). A second
  pair of reviews over the final proposals found four more, fixed: (52) *a
  library effect's filter is yours with no controller on it* (`_LIBRARY_EFFECTS`:
  Heroes' Podium's legendary creature from the top in Animated Army's
  ten-legend deck, Open the Armory's gear in Jeskai Striker); (53) *an
  opponent's discard is the gate on a trigger watching it*
  (`_OPP_DISCARD_GATE`, fed by the deck's discard makers: Waste Not under
  Jace); (54) *a one-shot mana source never upgrades a repeatable one*
  (`_one_shot_for_repeatable`: Lotus Petal for Wild Growth, Dark Ritual for
  Azorius Signet, Simian Spirit Guide for Millikin); (55) *the cut in another
  coat is no upgrade* (`_lateral_at_the_job`: the same read, deploy cost and
  color count — Talisman of Creativity for Talisman of Curiosity, Pongify
  for Rapid Hybridization; Arcane Signet's any color is more colors than a
  Signet's two). Verdicts, not fixes (the
  reviewers' remaining flags): a popular bomb traded on its theme page for a
  better-played theme card of the same band (Hero of Bladehold for Krenko,
  Hydroid Krasis for Nature's Rhythm, Admiral Beckett Brass for Corsairs of
  Umbar) is the play-rate order ADR-0060 settled; an engine cut for its
  template role's staple (Calix, Starfield of Nyx, God-Eternal Bontu) is the
  role read's; Merfolk Mistbinder for Pyre of Heroes and Juniper Order
  Ranger for a combo piece keep the need the cut supplied; Howling Mine,
  Rhystic Study at Bracket 2, Blasphemous Act in a go-wide deck and Silent
  Arbiter are bracket or symmetry calls the reads don't make; the identity
  flags on Kaito, Will of the Sultai, Akroma's Memorial and Eldrazi
  Conscription were wrong (the pool's identities), as were Will of the
  Sultai's and Will of the Abzan's (mono-colored); Intangible Virtue and
  Inspiring Call are fed by six or more makers in the decks they were flagged
  in; Herald's Horn and Vanquisher's Banner under Omo are the guides' own
  direction (batch 13); Inverter of Truth as a closer, Traxos under eighteen
  historic cards, Coastal Piracy (phase drops its creature filter), Anger,
  Impact Tremors and Blood Artist against the Most Wanted plan are judgment
  calls the reads don't make. Measured and reverted
  on the way, each a route to a flaw the shipped reads cover: a ceiling on a
  built need (met at twelve suppliers, leads no more — it switched off
  Bello's big-artifact need and Éowyn's Human need, the 25 lost ten guide
  adds); a cap of two choose-a-type cards a deck (the guides add Herald's
  Horn, Vanquisher's Banner and Kindred Discovery side by side — Cavalry
  Charge lost three adds, held-out 105 → 99); keeping the tribe's
  payoffs out of the off-lane tiers (above); and keeping the need lead off
  the tribe pages for Veloci-Ramp-Tor, whose Dinosaur page trades Bonehoard
  Dracosaur and Ghalta and Mavren for Dinosaur payoffs under Pantlaza (its
  guides want bodies) — the lever brought neither back and cost Dance of the
  Elements and Party Time seven guide adds (held-out 105 → 100), so
  Veloci's four fewer adds are the tribe need's one cost against Riders',
  Explorers', Party Time's and Cavalry Charge's gains. Verified with
  `verify_symptoms.py` (53 checks, all passing on the final run, 37 of the
  first 46 on the batch-13 run).
- **Batch 15 (2026-11-02; the 25 735 / 337 / 114 → 734 / 338 / 115, held-out 571 / 262 /
  105 → 571 / 262 / 104, fresh 294 / 126 / 49 unchanged).** The closing reviews over the
  committed batch-14 tree, each flag checked against the pool and the code.
  Fixed: (56) *a symmetric "a player casts an instant or sorcery" trigger
  whose payoff is your draw is a Spellslinger build-around*
  (`tree_synthesis.has_structural_spellcast`: Niv-Mizzet, Parun — Quick
  Draw's own payoff read as serving none of its themes and went as a popular
  off-lane card for Rapid Hybridization; a punisher's damage to the caster
  (Eidolon of the Great Revel) and an opponents-only hoser (Mystic Remora)
  stay out). (57) *A body held back by its own text is no closer*
  (`metrics.is_wincon_card` on `self_drawbacks`' restriction; the harm read
  gains the whole-library exile — Inverter of Truth, Leveler — and Eldrazi
  Incursion's closer slot no longer takes a 6/6 that decks you; Phage's
  self-loss rides a card that still wins). (58) *Your own discard is a gate
  too* (`_YOU_DISCARD_GATE`, fed by discard outlets: Monument to Endurance in
  Most Wanted's no-outlet deck). (59) *A wipe that sweeps no creatures
  neither fills the board-wipe row nor upgrades a creature sweeper*
  (`_sweeps_no_creatures` / `_sweeps_fewer_kinds` off the wipe read's
  `creatures` feature: Vandalblast scored above Winds of Rath, Massacre Girl
  and Descend upon the Sinful in Blame Game, Desert Bloom, Endless Punishment
  and Timey-Wimey). Checked and not flaws: Rev, Tithe Extractor and Summon:
  Bahamut are inside their identities (mono-black; {9}); Warping Wail and
  Kozilek's Command have eight colorless sources each in Mardu Surge and
  Peace Offering; Dauthi Voidwalker is a Rogue; Metalwork Colossus costs
  nothing under Death Toll's eleven noncreature artifacts; Inspiring Call
  under Deadly Disguise's ten counter makers is fed. A last pair of reviews
  over that tree found two more, fixed: (60) *a one-shot mana source fills
  no ramp slot either* (`_one_shot_mana` in the fill path: Dark Ritual for
  Fae Dominion, Jeska's Will for Quick Draw, Cabal Ritual for Revenant Recon
  — the last a guide add, so the held-out set gives one up), and (61) *a
  proliferate spell adds to counters the deck must already place*
  (`_COUNTERS_GATE` off a `Proliferate` effect: Ripples of Potential under
  Family Matters' four counter makers), with the spell gate now holding only
  when every effect standing on its own is gated — Tezzeret's Gambit draws
  whatever its proliferate finds, Open the Armory's found card follows its
  search. Its remaining flags are verdicts: Abzan Armor's one-sided
  sweepers for symmetric ones (the wipe read scores Damn and Massacre Girl
  above Slaughter the Strong and Expel the Interlopers, whose sparing lives
  in a chosen power threshold it cannot see); Village Rites for Esper
  Sentinel (the outlet supplies Clavileño's token-consumer need, which the
  pool share reads as broad, so it leads no page and gates no upgrade);
  Gonti's evasive bodies for evasion grants (36 creatures to carry them);
  Mana Reflection for Farseek, the Ulamog Titans under Ulalek, and the
  popular-for-popular theme trades (Barrowgoyf, Angel of Invention,
  Lingering Souls) are the play-rate order ADR-0060 settled. Verified with
  `verify_symptoms.py` (64 checks, all passing on the final run). Across
  batches 14 and 15 the 25's guide adds fall six — the gates and the
  no-downgrade rule on the design set — while the held-out gate holds and
  the fresh set gains nine.
- **Batch 15c (2026-11-02; the 25 734 / 338 / 115 → 736 / 338 / 116, held-out
  571 / 262 / 104 → 571 / 261 / 104, fresh 294 / 126 / 49 unchanged).** Two
  verdicts of batch 15 turned into fixes, each read back on all 55 decks.
  (62) *A token-making commander whose own text spends or counts deaths
  wants sacrifice outlets as a need of their own*
  (`commander_need._resource_needs`, gated on `_DEATH_KEYS` in the
  commander's idents: Clavileño's death trigger, Ghave's sacrifice cost) —
  the bundled token-consumer need reads as broad in most pools and so led no
  page and gated no upgrade; Village Rites is kept over Esper Sentinel and
  Blood Rites gains Pyre of Heroes. Read for EVERY token maker it was
  measured and narrowed: Anikthea's enchantment copies and Teval's Druids
  want no outlet, and the 25 lost Parallel Lives, Rootborn Defenses and
  Ramunap Excavator (736 / 338 / 113). (63) *An upgrade keeps the card type
  the commander's text pays off, broad or not* (`swaps._upgrades`'
  `needs_kept` over `SwapContext.needs` — every need, the ones `need_avenues`
  skips as over `BROAD_SHARE` included, kept to the `payoff` needs with
  `types`): Cast Out, an enchantment Anikthea returns, went to Assassin's
  Trophy on the interaction page; it now moves onto the theme (Greater Good,
  the full job's designed move). Inspirit's Mindless Automaton (an artifact
  draw) stays for the same reason — the one held-out guide cut given up.
  Holding every broad leading need was measured and narrowed: Eshki's
  "whenever you cast a creature spell" kept Gadrak and Steel Hellkite from
  Impact Tremors and Rhythm of the Wild, Olivia's evasion event kept Massacre
  Girl from Damn — the held-out 20 lost three guide cuts (571 / 259 / 105).
  Measured and reverted: *a candidate the job read scores nothing is worse
  at the job* (so a job card's slot never leaves the job on a theme page) —
  the 25 728 / 335 / 122, held-out 564 / 260 / 104, fresh 293 / 126 / 45; the
  reads' coverage is partial (Dark Confidant scores nothing at card draw and
  was blocked as a Wizard's upgrade), and a full job's slot moving onto the
  theme is the designed path (``moved_source``), so the rule took guide
  adds with the misfires. Verdicts, with the reason: Starfield of Nyx for
  Blind Obedience (the play-rate order of the enchantment page; the
  "does what the commander does" redundancy need deliberately leads and
  gates nothing — measured 2026-11-01 under Ms. Bumbleflower); Garruk,
  Cursed Huntsman for Drey Keeper (a theme upgrade may step one band down).
  A Sonnet re-read of the other 30 proposals found no new flags.
  `verify_symptoms.py` gains the Village Rites keep and a `no_pair` kind
  (Cast Out -> Assassin's Trophy); 66 checks, all passing.
- **Batch 15d (2026-11-02; the 25 736 / 338 / 116 → 735 / 338 / 116, held-out
  571 / 261 / 104 and fresh 294 / 126 / 49 unchanged).** The re-read of the
  three decks batch 15c changed. Fixed: (64) *a "shares a creature type"
  filter that only picks what a mass effect destroys, damages, or exiles is a
  tribe's hoser, not its payoff* (`crosswalk._subtype_refs`' `shares_type`
  skips the filter under a `DestroyAll` / `DamageAll` / `ChangeZoneAll` to
  exile or a graveyard): Endemic Plague — "destroy all creatures that share
  a creature type with the sacrificed creature" — went onto Blood Rites'
  Vampire page as a Coat of Arms, for New Blood. Excluding EVERY mass
  effect's filter was measured and narrowed: Resplendent Marshal's counters
  on each creature sharing a type are a payoff, and Party Time lost it as a
  guide add (fresh 48). Checked and not flaws: Sanguine Bond under Anikthea
  (nine lifegain makers, and it completes Exquisite Blood); Seize the Spoils
  is card draw; Cemetery Tampering is on-plan self-mill; Viral Drake for
  Deepglow Skate supplies the counters need and proliferate besides, as a
  closer. Verdicts: Cast Out for Greater Good and Font of Fertility for
  Ghostly Prison (a full job's slot moving onto the theme — `moved_source`,
  the designed path — keeping the enchantment type); Lux Cannon for Meteor
  Golem (the one-band-up job rule under the kept artifact type); Pentad
  Prism for Serum Snare and Hangarback Walker for Metastatic Evangel (the
  play-rate order; the guides' Prism combo is their knowledge, not the
  card's text). `verify_symptoms.py`: Endemic Plague never joins Blood
  Rites; 67 checks, all passing.
- **Batch 15e (2026-11-02; every set's score unchanged: the 25 735 / 338 /
  116, held-out 571 / 261 / 104, fresh 294 / 126 / 49).** The re-read of
  batch 15d's Blood Rites. Fixed: (65) *a planeswalker's ultimate is not its
  job* (`crosswalk.is_ultimate`: a loyalty ability whose cost takes more
  loyalty than the card's printed starting loyalty, `ConceptTree.card_loyalty`
  — CR 306.5b, a loyalty cost removes counters, CR 606.4, and a cost needs
  the resources to pay it, CR 118.3; the removal, removal-answer and sweep
  walks skip it). Sorin, Lord of Innistrad (three loyalty, a −6 destroy) was
  an interaction card traded for Feed the Swarm; Liliana, Death's Majesty
  (five, a −7 sweep) was the board-wipe upgrade in five decks (Death Toll,
  Enduring Enchantments, Squirreled Away, Multiverse Reforged, Necron
  Dynasties) and counted as Graveyard Overdrive's own fifth sweeper, which
  trimmed Final Act. Karn Liberated's −3 on six stays his job. Card text and
  rulings checked with `scryfall-lookup` / `rulings-lookup` for every card
  this batch and 15c–15d rest on; every CR number the goal's commits added
  (ten) checked with `rules-lookup`. One earlier verdict did not survive the
  card text and is open below (Viral Drake for Deepglow Skate). Verdicts:
  Patron of the Vein for Braids, Arisen Nightmare (Braids is an end-step
  sacrifice outlet and edict on Clavileño's plan); Legion Lieutenant for
  Cover of Darkness (a Vampire payoff for a better-played one, the theme
  page's play-rate order). `verify_symptoms.py`: Sorin is never traded as
  interaction; 68 checks, all passing.
- **Batch 15f (2026-11-02; the 25 735 / 338 / 116 unchanged, held-out 571 /
  261 / 104 → 571 / 262 / 104, fresh 294 / 126 / 49 unchanged).** The open
  verdict of 15e, checked against the card text. Fixed: (66) *a poison giver
  closes only in a deck that poisons* (`metrics.is_wincon_card`: the same
  rule proliferate already had; ten poison counters lose, CR 704.5c, and
  infect gives a counter per point of damage, CR 702.90b). Viral Drake, a
  1/4 infect flier, was Counter Intelligence's closer add for Deepglow Skate
  in a deck with no other poison; lone toxic cards (Skrelv's Hive, Skrelv,
  Defector Mite) stop being sourced as closers in Virtue and Valor and Call
  for Backup, and Counter Intelligence regains Mindless Automaton as a guide
  cut. Outside a poison deck a poison giver is judged as any card is:
  Triumph of the Hordes still closes as a team pump. Verdicts, with the
  check: Blood Rites' Vampire count falling from 35 to 23 (the guides add 33
  cards, four of them Vampires — they trade bodies for outlets, removal and
  payoffs as the tuner does); a cut that doubles what its commander makes
  (five across the 55: Tanazir Quandrix and Kinetic Ooze go to other
  doublers, Kaya, Geist Hunter is a guide cut, and Deepglow Skate and The
  First Tyrannic War double counters once — on entering, on a chapter — so
  no engine, neither named by its guides; no static doubler is cut anywhere,
  so a multiplier arm for them would change nothing). `verify_symptoms.py`:
  Viral Drake never joins Counter Intelligence; 69 checks, all passing.
- **Batch 16 (2026-11-02; the 25 735 / 338 / 116 unchanged, held-out 571 /
  262 / 104 → 570 / 262 / 105, fresh 294 / 126 / 49 → 294 / 126 / 48).** A
  re-read of the 18 proposals batches 15c–15f changed, by two Sonnet
  reviewers told to look every card up (`scryfall-lookup`) before flagging;
  each flag then checked against the text, rulings and the deck. Fixed:
  (67) *kinship pays off the card's own types* (`crosswalk._subtype_refs`:
  a `SharesQuality` / `ObjectsShareQuality` against `SelfRef` names the
  card's own creature types, not "shares a type" for any tribe; Coat of Arms
  and Shared Animosity compare against another object; `swaps._unit_gates`
  gates the kinship trigger on those types, fed only by the deck's cards of
  them): Wolf-Skull Shaman, an Elf Shaman, was a Squirrel deck's theme add
  (five Elves or Shamans), and Waterspout Weavers, a Merfolk Wizard, a
  Pirate deck's. (68) *a cost of more life than a player starts with is not
  the card's job* (`crosswalk.out_of_reach` = `is_ultimate` or
  `pays_beyond_starting_life`: CR 119.4, a player pays life only up to their
  total; CR 903.7, Commander's 40 is the most anyone starts with; the
  removal lane skips such units in every arm now, not only its destroy
  arm): Aetherflux Reservoir's "Pay 50 life: 50 damage" upgraded Living
  Energy's Duplicant as interaction. (69) *a sweep sparing the deck's own
  attachments is one-sided there* (`board_wipe._spared_attachment`, read in
  the deck when it holds `_ATTACHMENT_DECK` (10) of the kind): Winds of Rath
  ("creatures that aren't enchanted") went to Martial Coup under Ellivere's
  twenty Auras; it now goes to Wrath of God. (70) *a commander that puts
  counters of another kind on other permanents wants the cards that spend
  them* (`commander_need._counter_kind_needs`, CR 122.1; +1/+1, -1/-1 and
  loyalty excluded): Inspirit's "two charge counters on up to one other
  target artifact" makes Titan Forge and Golem Foundry need suppliers, and
  each now goes to another charge spender (Transmogrifying Wand, Spawning
  Pit), not a mana rock. Checked and not flaws: Cloakwood Hermit under Hazel
  (a Background in the 99 grants its ability to "commander creatures you
  own", which Hazel is — its rulings agree); Camellia, the Seedmiser (forage
  exiles three graveyard cards or sacrifices a Food, CR 701.61a); Glaring
  Fleshraker in Mardu Surge (twelve colorless spells); Technomancer in Death
  Toll (six artifact creatures and a mill of three — thin, not dead); The
  Eternal Wanderer for Sunfall (you choose what each player keeps, so the
  read's call stands); Vanquisher's Banner for And They Shall Know No Fear
  (a full draw slot moving onto the theme — the "nothing at the job is
  worse" rule that would hold it was measured and reverted in 15c). The
  fresh set's one lost add is a reshuffle: the kinship Wizards leaving the
  any-tribe read reorder Party Time's Wizard page, and Dark Confidant loses
  its slot; Counter Intelligence's Fumigate goes to Aetherize instead of
  Wrath of God because the purse ($40.69, $40.67 spent) no longer reaches
  Wrath ($3.49) — both pass the gate (an in-process spy on `_upgrades`;
  `misses.py`'s workers are spawned, so a patch in the parent never reaches
  them, and a bisect by patching proves nothing).
  `verify_symptoms.py`: four checks; 73, all passing.
- **Batch 16b (2026-11-02; the 25 735 / 338 / 116 → 735 / 338 / 118, held-out
  570 / 262 / 105 → 569 / 262 / 105, fresh 294 / 126 / 48 unchanged).** The
  re-read of the ten proposals batch 16 changed. Fixed: (71) *a narrow sweep
  never replaces a sweep of the whole board* (`swaps._sweeps_fewer_kinds`,
  the wipe read's `narrow` feature): Aetherize ("return all attacking
  creatures") took Fumigate's and Massacre Wurm's slots as the cheaper card
  though the read scores it below; Fumigate now goes to Vanquish the Horde.
  (72) *a listed type choice is fed only by a listed tribe*
  (`swaps._choosable_types`): Dawn-Blessed Pennant names Elemental, Elf,
  Faerie, Giant, Goblin, Kithkin, Merfolk or Treefolk, and Most Wanted's
  twelve Humans fed it. (73) *tokens of a type are fed by their makers*
  (`_gate_words` turns a `Token` filter's creature type into "<type>
  tokens", `deck_profile` counts each token kind's makers): Gleaming
  Overseer's "Zombie tokens you control have hexproof" was fed by Cavalry
  Charge's seven Zombie cards. (74) *a trigger's effects can be its gate*
  (`_trigger_effect_gate_words`): opening an Attraction, which a player does
  only with an Attraction deck (CR 701.51a — Squirrel Squatters), and the
  filter of a static every effect grants for the turn (Chocobo Knights'
  "creatures you control with counters on them gain double strike" over
  three counter makers). Verdicts, with the check: Summon: Titan as a closer
  (a 7/7 reach-and-trample body whose third chapter gives another creature
  +X/+X and trample, X its lands); Hangarback Walker for Lulu, Stern
  Guardian (a theme card for a theme card, each supplying two of Inspirit's
  needs); Eldrazi Monument under Bello (six creature-token makers feed its
  upkeep sacrifice). Open, measured next: Pentad Prism for Volt Charge (the
  need gate counts needs, and each supplies two — Pentad Prism the charge
  spender, Volt Charge proliferate).
  `verify_symptoms.py`: four checks; 77, all passing.
- **Batch 16c (2026-11-02; held-out 569 / 262 / 105 → 569 / 262 / 107; the 25
  and fresh unchanged).** Fixed: (75) *a commander whose only lifegain is
  its own lifelink asks for no lifegain payoffs*
  (`commander_need._lifelink_only`: the keyword and no `GainLife` effect of
  its own — CR 702.15b, a gain per hit of one body): Olivia, Opulent
  Outlaw's lifelink drew Sanguine Bond and Vito, Thorn of the Dusk Rose for
  Witch of the Moors and Veinwitch Coven where her guides say lifegain "only
  works with Olivia's lifelink" and cut it; Most Wanted now takes Path to
  Exile and Bitterblossom, both guide adds. Olivia is the only such
  commander in the 55. Its aristocrat adds (Zulaport Cutthroat) remain: the
  deck's death lane is its own, not a reading of Olivia's text — a verdict.
  Measured and reverted: *an upgrade keeps the same needs, not only as
  many* (a set test on the built needs beside the count) — Pentad Prism
  stays as Inspirit's charge spender, but the rule holds back the guides'
  own one-need-for-another trades (Harrow for Ramunap Excavator, Progenitor's
  Icon for Hulking Raptor, Raging Swordtooth for Forerunner of the Empire)
  and sends Village Rites to Deadly Dispute: the 25 735 / 338 / 118 → 728 /
  334 / 115, held-out 569 / 262 / 107 → 568 / 264 / 110, fresh 294 / 126 / 48
  → 293 / 127 / 47, and two symptom checks fail. Pentad Prism for Volt
  Charge is the count test's call — a verdict.
- **The re-read of batches 16b–16c (2026-11-02): no new flaw.** A Sonnet
  reviewer read the six proposals they changed, card text looked up. Its
  three flags: Cloakwood Hermit under Hazel (settled in batch 16 — a
  Background in the 99 grants its ability to "commander creatures you own";
  its rulings agree); Esper Sentinel as card draw ("draw a card unless that
  player pays {X}" is a draw tax the way Rhystic Study is — the deck's
  choice to count it is the read's call); Rampaging Ferocidon for Kinjalli's
  Sunwing in Velocirampor (a Dinosaur for a better-played Dinosaur, the
  tribe page's play-rate order; its ping on every creature entering is
  symmetric, so the opponents' creatures pay too — weighed, not a cut
  reason). Fixed on the way: (76) *a ping on whoever's creature entered
  hurts you too* (`crosswalk.self_drawbacks` / `_harms_you`: a trigger
  watching every player's creatures that deals damage to "that creature's
  controller" is a harm, where another object entering is otherwise an
  engine's cost — Rampaging Ferocidon now reads `harm`; Suture Priest, which
  pings only for an opponent's creature, does not). No proposal in the 55
  changes (run 68: the 25 735 / 338 / 118, held-out 569 / 262 / 107, fresh
  294 / 126 / 48; 78 checks). With it every flaw this pass's re-reads found
  is fixed or recorded above as a verdict with the check behind it.
- **Batch 16d (2026-11-02; the 25 735 / 338 / 118 → 735 / 338 / 119, held-out
  569 / 262 / 107 → 569 / 262 / 106, fresh 294 / 126 / 48 → 294 / 126 / 49).**
  A last check of every item left as a verdict. Fixed: (77) *a lane-ok
  fill takes a card that is none of the commander's tribe or its payoffs,
  across both fallback pools, before one that is* (`swaps.take_lane_ok_cut`,
  `tribal_cut`): pool by pool, Descendants' Path — a payoff for Pantlaza's
  Dinosaurs ("cast it without paying its mana cost" when it shares a type
  with a creature you control) — was the last jobless slot and went as a
  card-draw fill's cut while Drover of the Mighty and four other guide cuts
  waited in the lane pool; it now goes to Regal Imperiosaur. Holding back
  every need supplier that way was measured and narrowed (held-out 569 /
  262 / 107 → 564 / 260 / 104). Not flaws, with the evidence: Pentad Prism
  for Volt Charge — the loop the guides finish (Aura of Dominion with Kilo
  and Pentad Prism, infinite proliferate) is one of Counter Intelligence's
  forty one-card-away Spellbook combos, below the top five by popularity
  the tuner completes, and 181 of the 55 proposals' cuts are a piece of such
  a combo (Faeburrow Elder with Freed from the Real…), so a rule protecting
  them would freeze the tuner; nothing in the cards marks this loop as the
  deck's plan. Esper Sentinel as card draw — the card-draw read scores it
  0.98 beside Rhystic Study's 0.96 (both read "opponents fuel the draw"),
  and its play rank is 80. Most Wanted's "aristocrat" adds — Zulaport
  Cutthroat (Human Rogue) and Vengeful Bloodwitch (Vampire Warlock) are
  outlaws replacing outlaws (Veinwitch Coven, Humble Defector) on the
  Outlaws page, Olivia's own lane. Blood Rites' Vampires falling from 35 to
  23 — its guides add 33 cards, four of them Vampires.
  `verify_symptoms.py`: Descendants' Path never goes to Esper Sentinel; 79.
- **Batch 16e (2026-11-02; the 25 735 / 338 / 119 → 734 / 337 / 118, held-out
  569 / 262 / 106 → 570 / 263 / 107, fresh unchanged).** The re-read of
  batch 16d's six proposals, each flag checked against the card text.
  Fixed: (78) *a sacrifice the player may decline for a penalty is no edict*
  (`lanes._shared._punisher_choice`, read by `sacrifice_actor_scope`, so the
  edict lane and the removal walk both see it): Braids, Arisen Nightmare's
  "each opponent may sacrifice … For each opponent who doesn't, that player
  loses 2 life" was interaction and upgraded Blood Rites' Patron of the
  Vein (a Vampire whose enters trigger destroys a creature); it now goes to
  Eaten Alive. The `creature-edict` preset already excluded punishers
  (Prowling Pangolin) and listed Braids as a match against its own rule —
  moved to should-not-match. (79) *a one-shot spell is no upgrade of a
  permanent that does the job* (`swaps._one_shot_for_an_engine`: an instant
  or sorcery the job's read sees nothing of, for a permanent it scores):
  Vanquisher's Banner's draw went to And They Shall Know No Fear's one turn
  of +1/+0 in Cavalry Charge and Sliver Swarm; it now goes to Kindred Boon.
  Verdicts, with the check: Cast Out for Accursed Marauder (the removal read
  scores the Marauder 0.77 to Cast Out's 0.75, and it is a Zombie under
  Temmet). The 25's loss is Sultai Arisen's Harrow-for-Ramunap pair, gone
  in a reshuffle of its theme page. `verify_symptoms.py`: 81.
- **Batch 16f (2026-11-02; the 25 734 / 337 / 118 → 733 / 339 / 120; held-out
  and fresh unchanged).** Fixed: (80) *an upgrade keeps a broad commander
  resource need the deck builds toward* (`swaps` kept needs: the `resource`
  needs beside the payoff card types, at `_NEED_BUILT_FLOOR` suppliers) —
  Sultai Arisen gets Harrow for Ramunap Excavator back and Mardu Surge,
  Enduring Enchantments gain a guide cut or add each. Archfiend of Ifnir for
  Counterspell in Eternal Might is untouched: Temmet's "discard consumers"
  has three suppliers in the deck, under the floor.
- **Batch 16g (2026-11-02; held-out 570 / 263 / 107 → 570 / 263 / 106; the 25
  and fresh unchanged).** Fixed: (81) *a commander resource need is kept
  however few suppliers the deck holds, and a page need under the built
  floor is kept too* (`swaps` kept needs: every leading need outside the
  built ones — a `resource` need at any count, a payoff card type at the
  floor). Temmet loots on every attack and Archfiend of Ifnir is one of
  Eternal Might's three discard payoffs; its "discard consumers" need has a
  page but sat under the built floor, so neither gate held it and it went
  to Counterspell, which supplies nothing Temmet asks for. It now goes to
  Arcane Denial, whose draw feeds Temmet's "whenever you draw a card" — one
  need for another, the count test's call. The cost is King T'Challa in
  Avengers Assemble, now ranked behind Araña for Black Widow's slot.
  Dropping only the floor (run 74) changed nothing: the need had a page.
- **Batch 16h (2026-11-02; every set's score unchanged: the 25 733 / 339 /
  120, held-out 570 / 263 / 106, fresh 294 / 126 / 49).** The re-read of the
  20 proposals batches 16e–16g changed, by two Sonnet reviewers with every
  card looked up. Fixed: (82) *a chosen card type read as a creature type*
  (`misparsed_shapes`, a new row, `test_chosen_card_type_sweep_canary`):
  Season of Gathering's "Choose artifact or enchantment. Destroy all
  permanents of the chosen type" is phase's `Choose` among `Labeled`
  card-type options, then a `DestroyAll` over `Permanent` filtered by
  `IsChosenCreatureType` — creatures included. The filter is rewritten to the
  listed card types, so the wipe read sees an artifact-or-enchantment sweep
  and the creature-less veto keeps it out of Tinker Time's board-wipe fill
  (Faerie Slumber Party now). Verdicts, with the check: Glaring Fleshraker for Hero of
  Bladehold (twelve colorless spells feed it, batch 16; a better-played
  theme card); Coretapper for Talisman of Creativity (Coretapper makes
  charge counters, as Inspirit does — a "like the commander" need, which
  the gate deliberately doesn't hold — and both are artifacts); The Rise of
  Sozin for Silhana Ledgewalker (its chapter I wipes, then Fire Lord Sozin
  returns creature cards from every graveyard under your control — a theft
  card on Grand Larceny's plan); Gonti's evasive bodies for evasion grants
  (batch 15's verdict). `verify_symptoms.py`: 83.
- **Batch 16i (2026-11-02; held-out 570 / 263 / 106 → 565 / 262 / 106 — within
  the gate's floors; the 25 and fresh unchanged).** Fixed: (83) *"remove a
  counter" of any kind spends a commander's charge counters too*
  (`commander_need._spends_counters`: a `RemoveCounter` of the kind or of
  `ANY`): Gavel of the Righteous ("Equip—Pay {3} or remove a counter from
  this Equipment") went to Serum Snare; it now goes to Umezawa's Jitte,
  which spends charge counters as well. The deck now keeps Pentad Prism,
  Long-Range Sensor and Moxite Refinery, all spenders of what Inspirit puts
  out — which also settles the Pentad Prism for Volt Charge flag — so 30
  swaps become 25 at the same spend ($40.49 of $40.69), and Soul-Guide
  Lantern, a guide cut, goes unmade for want of purse. First reverted on the
  swap count alone; the gate (guide adds ≥ −5, cuts ≥ −1) holds, and the
  dropped swaps are the deck keeping its plan. Batch 11's `swaps=30` check
  (a purse that ran dry with cheap cards unreached) becomes `swaps>=25`.
- **Batch 16j (2026-11-02; held-out 565 / 262 / 106 → 565 / 261 / 107; the 25
  and fresh unchanged).** Fixed: (84) *a commander that puts counters of a
  kind on other permanents wants the cards that put more of them out*
  (`commander_need._counter_kind_needs`' second need, `_places_counters`:
  a `PutCounter` of the kind on a target other than the card itself):
  Coretapper ("Put a charge counter on target artifact") went to Talisman
  of Creativity under Inspirit; it now goes to Surge Node, which charges
  another artifact too, and Long-Range Sensor to Reckoner Bankbuster, a
  charge spender for a charge spender. Counter Intelligence gains Cayth as a
  guide add and Soul-Guide Lantern back as a guide cut, and gives up Chain
  Reaction and Angel of the Ruins as cuts.
- **Batch 16k (2026-11-02; the 25 733 / 339 / 120 → 733 / 339 / 119, held-out
  565 / 261 / 107 → 566 / 262 / 108, fresh 294 / 126 / 49 → 294 / 126 / 52).**
  A full re-read of all 55 proposals (four Sonnet reviewers, every card
  looked up), each flag checked against the text and the deck. Fixed:
  (85) *-1/-1 counters on each creature are a sweep*
  (`lanes.mana_and_wipes._mass_shrink`, the wipe read's mode and amount:
  CR 122.1a, 704.5f) — Black Sun's Zenith read as no wipe, so Revenant
  Recon upgraded it to Negate while its wipe row was short; it now goes to
  Cyclonic Rift. (86) *a card's own tokens feed only their own type's gate*
  (`_UnitGates.fed`: only tokens of a kind the read can't name feed any
  creature-type gate) and *a creature-type gate the deck can't feed is dead
  whatever else the card cares about* (`dead_payoff`): Invisible Woman's
  only trigger waits on "other Heroes", and her Wall tokens and the +1/+1
  counters Abzan Armor makes never reach it; Tower Defense now goes to Wall
  Off. The early verdict for every gate was measured and narrowed to
  creature types: a token-made type like Food is counted off the type line,
  and it cost Food and Fellowship's Trail of Crumbs (the 25 −2 adds, fresh
  −3). (87) *a draw only off an attacking token is combat's*
  (`job_quality.card_draw._draws_only_if_attacking`): Zurgo Stormrender's
  mobilized token is sacrificed after combat (CR 511.3, 702.181a), so it is
  no self-fueled engine. (88) *a redirect that copies copies no creature
  commander's spell* (`multipliers._copy_reason`, beside phase's dropped
  "with one or more targets"; `test_wylls_reversal_target_constraint_canary`
  now guards the workaround): Wyll's Reversal reads as copying Nelly
  Borca's targeted trigger, not her spell. (89) *one completion per set of
  combo pieces the deck holds* (`issues`' near-miss loop): Necron Dynasties
  took Vito and Sanguine Bond for the same Shard of the Nightbringer line;
  it now takes Vito. Verdicts, with the check: Metalwork Colossus in Death
  Toll (11 noncreature artifacts, 19 mana value — 17 with Golgari Signet
  cut); Intangible Virtue in Deep Clue Sea and Jaheira in Enduring
  Enchantments (12 creature-token makers each); Etched Oracle in Peace
  Offering (12 +1/+1-counter makers beside its sunburst); Thief of
  Existence (eight colorless sources, batch 15); Curiosity in Quick Draw (it
  holds Niv-Mizzet, Parun); Archfiend of Ifnir for Arcane Denial, Field
  Historian for Pyre of Heroes, Rite of the Raging Storm for Sephara (each
  add supplies another of the commander's needs — the count test);
  Killian, Ink Duelist for Flawless Maneuver (neither supplies Killian,
  Decisive Mentor's needs; a free protection spell is the better-played
  theme card); Cut Your Losses (a casualty sorcery on Rootha's spells
  theme); Glaring Fleshraker, The Rise of Sozin, Gonti's evasion grants,
  Eldrazi Monument (earlier batches); the soft flags — Chandra's Ignition as
  a closer or wipe, Doctor Strange's +2/+2 at 50 life, Sephara's fliers,
  Coastal Piracy (the draw read scales a combat engine by the deck's
  creatures), Aetherflux Conduit's 50-energy draw (an energy deck's own
  payoff), Faerie Slumber Party (a symmetric bounce filling a real wipe
  shortfall). `verify_symptoms.py`: 90.
- **Batch 16l (2026-11-02; the 25 733 / 339 / 119 → 733 / 339 / 120, held-out
  566 / 262 / 108 unchanged, fresh 294 / 126 / 52 → 294 / 126 / 53).** The
  re-read of batch 16k's 18 proposals. Fixed: (90) *cards leaving your
  graveyard are their own draw fuel* (`job_quality.card_draw._fuel`:
  "graveyard_leave", fed by the deck's recursion — `creature_recursion`,
  `permanent_recast`, `reanimator` — at an eighth of its nonland cards):
  Teval's Judgment read as an "enters" engine every deck fuels and replaced
  Staff of the Storyteller in Multiverse Reforged, which moves nothing out
  of its graveyard; it scores 0 there now and keeps 0.45 in Sultai Arisen.
  (91) *a commander's "if a creature of a type entered this turn" is a
  need* (`commander_need._condition_need`, `BattlefieldEntriesThisTurn`: the
  type's cards and its token makers), *held by the upgrade gate however
  broad* (`swaps` kept needs take `condition` needs beside `resource`):
  Éowyn, Shieldmaiden's "if another Human entered the battlefield under
  your control this turn" — Increasing Devotion went to Burnished Hart and
  Riders of Rohan to Skullclamp; they now go to Captain Lannery Storm and
  Professional Face-Breaker, both Humans. Verdicts, with the check: Dawn of
  Hope in Multiverse Reforged (nine lifegain makers, and it makes lifelink
  Soldiers); Bitter Triumph for Anger in Mardu Surge (the interaction row
  had reached its top after the fills — `job_room` is max minus current —
  so the slot moved onto the theme inside the band); Blame Game's Take the
  Bait for Avacyn and Vow of Duty for Wyll's Reversal (protection for
  better-played protection); Hero of Bladehold for Maskwood Nexus (theme
  for theme); Pashalik Mons (it makes its own Goblins). `verify_symptoms.py`:
  92.
- **The re-read of batch 16l (2026-11-02): no new flaw.** A Sonnet reviewer
  read the three proposals it changed, every card looked up. Its two flags,
  checked: Polluted Cistern // Dim Oubliette for Eldrazi Conscription in
  Death Toll (Eldrazi Conscription is a Kindred Enchantment — two card types
  for Winter's "card types in your graveyard", a need for a need); Overlord
  of the Mistmoors for Ancient Stone Idol in Multiverse Reforged (a flip's
  slot stays a flip under the Jace polymorph commander — the 2026-11-01
  call). This closes the loop that began with the full 55-deck re-read of
  batch 16k: every flag each pass raised is fixed above or recorded as a
  verdict with the card text, deck count or measurement behind it.
- **Batch 16m (2026-11-02; every set's score and every swap unchanged).** The
  two oldest verdicts re-read against the card text. Fixed: (92) *a draw on
  the first such spell each turn fires less than one on every spell*
  (`job_quality.card_draw._rate`: a `NthSpellThisTurn` constraint halves
  the rate) — Esper Sentinel's "first noncreature spell each turn" had
  Rhystic Study's flow and read above it (0.98 to 0.96); it now reads
  0.946. It is still Veloci-Ramp-Tor's card-draw fill, the draw tax it is
  (rank 80). Re-checked: Blood Rites keeps 26 Vampire creatures and eight
  Vampire-token makers after the proposal, and Clavileño's "target attacking
  Vampire that isn't a Demon" needs one an attack — the drop from 35 is the
  guides' own direction (four Vampires among their 33 adds).
- **Batch 16n (2026-11-02; the 25 733 / 339 / 120 → 733 / 339 / 119, held-out
  566 / 262 / 108 → 565 / 262 / 106, fresh 294 / 126 / 53 → 293 / 125 / 53).**
  The second full 55-deck re-read (four Sonnet reviewers, every card looked
  up). Fixed: (93) *a sweep that spares most of this deck's creatures is
  one-sided here* (`job_quality.board_wipe`: `_Sweep.spared_power` — Dusk's
  "power 3 or greater", Slaughter the Strong's "total power 4 or less" —
  against the deck, at 40% of its creatures, a face-down creature a 2/2 per
  CR 708.2a), and *an upgrade never trades a sweep one-sided in this deck
  for one that isn't* (`swaps._spares_less_of_the_deck`): Winds of Rath and
  Dusk // Dawn no longer go to Wrath of God, nor Slaughter the Strong to
  Damn. (94) *a small sweep is no upgrade into a lethal one*
  (`_sweeps_fewer_kinds`): Starstorm for Contagion Engine. (95) *the -1/-1
  counter event need counts wither, infect and the counter's own placers*
  (`commander_need`, CR 702.80a / 702.90c): Kulrath Knight supplies Auntie
  Ool. (96) *a split card's mana value for a commander's "mana value 5 or
  greater" is its larger half* (CR 709.3b, hybrid per 202.3f). (97) *a
  "{type} token makers" payoff need is met only by cards making that token
  type* (`_makes_tokens_of`): Feldon of the Third Path for Skullclamp in
  Tinker Time. (98) *a static's own condition is its gate*
  (`swaps.dead_payoff`, `IsPresent` you control): Gravecrawler's "as long as
  you control a Zombie" off the Necron page. (99) *a counter only of spells cast
  with no mana spent is a hoser, not a counterspell*
  (`lanes.triggers_damage._counter_control` skips a `ManaSpentCondition`):
  Boromir, Warden of the Tower no longer fills Creative Energy's
  interaction row for Silverquill Lecturer. (100) *a
  protection-job flip keeps a flip's slot while protection is in band*
  (`Sourcing(protection_low=…)`). Verdicts, with the card text or count:
  Serra's Emissary for Rootborn Defenses under Jace (protection 3 of ~5:
  a flip whose job row is short keeps its job page, as card draw's does);
  Kulrath Knight for Ashnod's Altar in Blight Curse (34 deck cards supply
  the -1/-1 need, the fill took the last non-tribal jobless slot;
  opening the jobless popular slots ahead of it was measured and reverted —
  held-out 565 / 262 / 106 → 565 / 265 / 101, Pentad Prism cut again);
  Horn of Gondor (Omo grants every type); Wonder (it dies on its own);
  Primal Vigor (12 feeders); Eldrazi Unbound's X-spells (a play note, the
  size-anti-synergy rule); Thunderherd Migration for Wrath of God (wipe row
  short, ramp over band); Bitter Triumph (job row full); Commit // Memory
  (Memory's half is MV 6). `verify_symptoms.py`: 99.
- **Batch 16o (2026-11-02; the 25 733 / 339 / 119 → 732 / 339 / 120, held-out
  565 / 262 / 106 → 564 / 261 / 107, fresh unchanged at 293 / 125 / 53).** The
  re-read of batch 16n's ten proposals (a Sonnet reviewer, every card looked
  up). Fixed: (101) *a power line the caster sets spares a small deck*
  (`job_quality.board_wipe._caster_picked`: Expel the Interlopers' "the
  chosen number", Fell the Mighty's "target creature's power", read at Dusk's
  line of 3): Expel no longer goes to White Sun's Twilight under Felothar's
  0-power walls, nor Fell the Mighty to Martial Coup in Food and Fellowship
  or Deadly Disguise. (102) *a power line that kills the commander is no
  one-sided sweep* (`board_wipe.power_bound_hits`, `SwapContext.commanders`):
  Dusk spares most of Virtue and Valor by printed power but kills Ellivere
  of the Wild Court (power 4), so Winds of Rath no longer goes to it. (103)
  *a "tap N creatures of a type" cost gates the ability on that type*
  (`swaps._ability_gate_words`; a cost's words now stand alone, since it has
  to be paid): High Perfect Morcant's proliferate taps three Elves and its
  trigger waits on another Elf; Blight Curse holds three, so it is dead
  there and Village Pillagers goes to Murderous Redcap. Verdict: Whisperwood
  Elemental for Hauntwoods Shrieker in Deadly Disguise (Kaust turns
  face-down *attackers* face up, so an attack trigger is on the plan, at two
  less mana). `verify_symptoms.py`: 103.
- **The re-read of batch 16o (2026-11-02): no new flaw.** A Sonnet reviewer
  read the seven proposals it changed, every card looked up. Its one flag,
  checked: The Reaper, King No More for Woodfall Primus in Blight Curse.
  Both supply Auntie Ool's -1/-1 counter need — Woodfall Primus's persist
  returns it "with a -1/-1 counter on it" (CR 702.79a), and a counter given
  as a permanent enters is "put on" it (CR 122.6) — and on the interaction
  page "destroy target noncreature permanent" reads above two -1/-1
  counters, so it is an interaction upgrade that keeps the commander's need.
- **Batch 16p (2026-11-02; the 25 732 / 339 / 120 → 732 / 340 / 116, held-out
  564 / 261 / 107 → 563 / 262 / 105, fresh 293 / 125 / 53 → 294 / 126 / 50).**
  The third full 55-deck re-read (five Sonnet reviewers, every card looked
  up; 27 flags). Fixed: (104) *a tax costs more* — the residue pattern read
  Artist's Talent's "Noncreature spells you cast cost {1} less" as an
  opponent tax and so as a drain on opponents' turns under Valgavoth.
  (105) *a sweep leaving out a type spares a deck of it, and a commander
  of it* (`board_wipe._spares_a_type` / `type_bound_hits`): Extinguish All
  Hope and Cacophony Unleashed under Enduring Enchantments' enchantment
  creatures, Their Name Is Death under Necron Dynasties' artifacts, no
  longer go to The One Ring to Rule Them All or Massacre Girl. (106) *a
  board-wipe role the wipe read sees sweep no creatures is an interaction
  job* (`issues.upgrade_job`): Maelstrom Pulse, Dismantling Wave. (107) *an
  evasion need takes only evasive keyword grants*: Zack Fair's
  indestructible. (108) *a count of your permanents with counters of a kind
  wants their makers* (`commander_need._counted_counter_needs`; vanishing
  per CR 702.63a): The Moment under Rose Tyler. (109) *a -1/-1 counter is a
  shrink of its count* (`job_quality.removal`, CR 122.1a): Contagion Clasp
  is small removal, no upgrade of Spine of Ish Sah. (110) *a draw counting
  countered creatures runs on counter placers; one on a chosen type, on the
  biggest printed tribe* (`card_draw` fuels `countered`, `chosen_type`):
  Inspiring Call, Vanquisher's Banner. (111) *a tribe slot's members are
  creatures* (CR 700.8): Diviner's Wand under Nalia. (112) *a "non-<type>"
  gate is fed by the deck's other creatures*: Winota in Riders of Rohan.
  (113) *a grant of every creature type reaches the battlefield only*
  (`swaps._chosen_type_on_battlefield`): Herald's Horn under Omo. (114) *an
  artifact sacrifice spends Food* (CR 111.10b): Trading Post under Sam.
  (115) *an effect moving a card out of your graveyard feeds "cards leaving
  your graveyard"*: Quintorius, Loremaster. (116) *a first-X-spell trigger
  wants X spells* (CR 107.3): Stonecoil Serpent under Zimone. (117) *a
  sacrifice of any permanent can sacrifice a land*: God-Eternal Bontu under
  Hearthhull. (118) *a trim's add is no member of the row it trims*: Wizard
  Class to Deep Analysis for "card draw over by 9". (119) *a power line
  spares nothing in a deck built on Auras or Equipment*: Dusk under Killian.
  (120) *a paid activation for a mana token makes no mana* (`ramp._granted`):
  Idol of False Gods. The batch-15 Vandalblast checks now guard the wipe row
  only (`never_wipe`): it arrives as an interaction upgrade, its job.
  Verdicts, with the card text: Hour of Reckoning for Damn in Mardu Surge
  (it kills Zurgo, and mobilize tokens are sacrificed at end step anyway);
  Fiery Confluence for Chain Reaction (its "1 damage to each creature" is
  symmetric too); Ukkima for Spectral Deluge, Kaya's Wrath for Laurine and
  Summon: Leviathan for Brudiclad (fills of a short wipe row); Deathrite
  Shaman ("from a graveyard": every opponent's too); Whisperwood Elemental
  for Hauntwoods Shrieker. Open: The Day of the Doctor for The Battle of
  Bywater in Timey Wimey — chapter IV keeps up to three chosen Doctors (a
  tracked set the read can't resolve), and the Battle kills the Tenth
  Doctor. `verify_symptoms.py`: 122.
- **Batch 16q (2026-11-02; the 25 732 / 340 / 116 → 733 / 341 / 116, held-out
  563 / 262 / 105 → 562 / 262 / 105, fresh unchanged at 294 / 126 / 50).**
  The re-read of batch 16p's 26 changed proposals (three Sonnet reviewers,
  every card looked up; 15 flags). Fixed: (121) *a wipe the commander
  survives is never traded for one that kills it*
  (`board_wipe.keeps_commander` / `kills_commander`; a chosen set kept out
  of the sweep — `ChooseObjectsIntoTrackedSet` before `Not InTrackedSet` —
  is read): The Day of the Doctor keeps the Tenth Doctor and went to The
  Battle of Bywater, then Martial Coup ("all other creatures" spares its own
  Soldiers, never the commander); it now goes to Mizzium Mortars, closing
  16p's open item. (122) *an Equipment on any face is Equipment*: Harvest
  Hand's Scrounged Scythe off Ellivere's Aura page. (123) *a trigger sized
  only by a count of creature types is gated on them*: Valley Rotcaller in
  Most Wanted. (124) *a draw on creatures past their base power runs on the
  deck's pumps* (`card_draw` fuel `pumped`): Kutzil (Deadly Disguise has
  twenty, so it stays). (125) *a sweep that gives you a token for each of
  your creatures it destroyed is one-sided* (`board_wipe._replaces_yours`):
  Ceaseless Conflict no longer goes to Waltz of Rage. Measured and reverted:
  holding a theme add out of every row over its band (Peace Offering, whose
  plan is draw, lost eight swaps and seven guide cuts: held-out → 554 / 255
  / 105), and holding a trim's add so (two guide cuts: → 562 / 260 / 105);
  16p's narrower rule — a trim's add is no member of the row it trims —
  stays. Verdicts, with the card text or count: Tempt with Discovery and
  Managorger Hydra to Deep Analysis and Ancestral Vision (draw is Peace
  Offering's plan, above); Horde of Notions to the main theme (the tribe
  page held no better Elemental; the fallback is measured); Flamebraider on
  the Elemental page (a tribe member keeps its slot while its ramp row is
  in band); Mechanized Production (it completes Ant-Man's win); Veiled
  Ascension, Persistent Constrictor and Tenuous Truce (theme for theme; the
  Truce's Aura still fires Killian's enchantment trigger); Calix for Swords
  to Plowshares (interaction staple); Afterlife from the Loam (a fill cut
  from need suppliers, as Kulrath Knight); Gallifrey Falls // No More (one-
  sided only cast as two halves); Sylvan Scrying (lower confidence);
  Vanquisher's Banner for Painful Truths in Most Wanted (it names Human, of
  which the deck holds twelve: 0.44 against 0.16 on the draw read).
  `verify_symptoms.py`: 126.
- **The re-read of batch 16q (2026-11-02): no new flaw.** A Sonnet reviewer
  read the four proposals it changed, every added card looked up: Mizzium
  Mortars' overload is one-sided where The Day of the Doctor exiles your own
  non-Doctors; Virtue and Valor's adds are enchantments Ellivere counts;
  Most Wanted's are outlaws and a guide add (Port Razer).
- **Batch 16r (2026-11-02; the 25 733 / 341 / 116 → 729 / 339 / 116, held-out
  562 / 262 / 105 → 562 / 263 / 106, fresh 294 / 126 / 50 → 294 / 126 / 51).**
  The fourth full 55-deck re-read (five Sonnet reviewers; 24 flags).
  Fixed: (126) *a permanent's mana value floor reads X as 0* (CR 202.3e):
  Walking Ballista is no artifact at 4+ for Bello. (127) *a trigger on any
  token made or sacrificed waits on token makers* (`swaps._TOKENS_GATE`):
  Mirkwood Bats in Endless Punishment. (128) *removal that answers
  creatures is no upgrade to removal that can't*
  (`removal.answers_creatures`; a counterspell is outside it): Lethal Scheme
  to Return to Nature. (129) *a cheaper ramp card makes at least half the
  cut's mana a turn*: Exploration Broodship's station-gated land drop for
  Careful Cultivation. (130) *the lane-ok fallback never cuts a card in a
  short row*: Titan of Littjara's draw for Sundial of the Infinite while
  draw was two short. (131) *a cost reducer for your spells trims last*,
  as a mana doubler does: Ugin, the Ineffable. (132) *blight puts the
  -1/-1 counters* (CR 701.68a). (133) *a need supplier is no do-nothing
  filler*: Evolution Sage and Everlasting Torment as Blight Curse's dead
  weight. (134) *life above the starting total waits on lifegain, and a
  card gated only so is dead* (`swaps._LIFE_GATE`): Doctor Strange,
  Surgeon as Avengers Assemble's closer. (135) *a draw on creatures of a
  power entering runs on the deck's creatures that big, face up*
  (`card_draw` fuel `power_ge_<n>`): Garruk's Uprising in Deadly Disguise.
  Open, upstream: phase leaves Sinister Gnarlbark's "draw a card and
  blight 1" (and three other blight compounds) `Unimplemented`, and drops
  Everlasting Torment's "as though its source had wither"; the theft lane
  counts Tasha's Hideous Laughter's opponent exile as theft by design
  (Grand Larceny under Gonti wants cards it may cast). Verdicts, with the
  rulings or counts: Akroan Horse (its ruling: you get the Soldiers);
  Sanguine Bond and Ral, Storm Conduit (theme for theme); Necromantic
  Selection; Exemplar of Light (a counters deck feeds it); Bolt Bend (a
  redirect is no removal); Vito (it completes Shard of the Nightbringer);
  The Indomitable (it supplies Omo's granted-type need); Goblin Bombardment
  ("1 damage to any target" is interaction); Contaminant Grafter (toxic 1
  itself); Reconnaissance Mission (18 creatures); Kozilek's Command (eight
  colorless sources, settled in batch 15). `verify_symptoms.py`: 135.
- **Batch 16s (2026-11-02; the 25 729 / 339 / 116 → 728 / 339 / 115, held-out
  562 / 263 / 106 → 561 / 263 / 103, fresh unchanged at 294 / 126 / 51).**
  The re-read of batch 16r's 28 changed proposals (four Sonnet reviewers,
  every card looked up; 27 flags). Fixed: (136) *a cheaper card is a tempo
  upgrade only while it keeps 0.4 of the cut's read*
  (`swaps._TEMPO_FLOOR`): Key to the City (0.22) for Smuggler's Share
  (0.57); Duplicant keeps 0.49 of Meteor Golem and stays. (137) *an add
  asking {C} pips wants four colorless sources a pip*
  (`_C_SOURCES_PER_PIP`, counted off `produced_mana`, which names a
  painland's {C}): Echoes of Eternity's {C}{C}{C} in Animated Army's eight;
  batch 15's {C}{C} verdicts stand. (138) *a mana grant to creature tokens
  alone runs on the deck's token makers* (`ramp.deck_fit`): Insidious Roots
  no longer reads above Timeless Lotus in Dance of the Elements. (139) *a
  commander's "whenever you sacrifice a land" is an event need*, kept by the
  upgrade gate, and a sacrifice of "another nonland permanent" feeds none:
  Sprouting Goblin no longer goes to Shadow, Mysterious Assassin under
  Hearthhull. Open, upstream (phase): Umbra Mystic's umbra-armor grant is
  `Unimplemented`; Akiri, Fearless Voyager's "with one or more equipped
  creatures" is dropped (a bare `YouAttack`); Unwanted Remake's "Its
  controller manifests dread" loses its player (a bare `ManifestDread`).
  Verdicts, with the card text or count: Vanquisher's Banner in Living
  Energy (nine Artificers: fit 0.6); Will of the Sultai for Trading Post
  (both move a card out of the graveyard for Teval); Rite of the Raging
  Storm for Iroas (protection for protection; both feed Nelly's evasion
  need); Promise of Aclazotz and March of the Canonized (fill cuts from
  need suppliers, as Kulrath Knight); Valakut Exploration; Nicanzil for
  Glistening Sphere (a need for a need: its proliferate feeds Hakbal's
  counters); Captain Marvel, Shooting Star (a big flier is the read's
  closer); Blight Curse's infect adds (infect damage is -1/-1 counters, CR
  702.90c, and poison); Dreamscape Artist (it nets a land each activation);
  Cavalier of Thorns (its ramp row is short, so it keeps its job page);
  Ribtruss Roaster for Inspiring Call (its fuel read now applies).
  `verify_symptoms.py`: 139.
- **Batch 16t (2026-11-02; every set's score unchanged; three swaps moved).**
  The re-read of batch 16s's 15 changed proposals (two Sonnet reviewers,
  every card looked up; 8 flags). Fixed: (140) *a bonus on tapping lands of
  a type runs on the deck's lands of it* (`ramp.deck_fit`, against half its
  lands): Nissa, Who Shakes the World reads at half in Dance of the
  Elements' eight Forests of 38 — still above Timeless Lotus, since her +1
  untaps a land each turn. (141) *a deck that plays extra lands or pays off
  landfall takes no add that stops it playing lands*
  (`swaps._stops_land_plays`): Aggressive Mining under Hearthhull now goes
  to Hew the Entwood. Open: the removal read sizes Fling's "damage equal to
  the sacrificed creature's power" as a scaling amount whatever the deck's
  creatures (Palace Jailer to Fling in Riders of Rohan's small Humans) — a
  deck-sized amount for removal, as `board_wipe` has. Verdicts, with the
  card text or count: Eldrazi Monument (its upkeep sacrifice is the
  protection read's `upkeep_cost`); Putrefy for An Offer You Can't Refuse
  (counterspells are outside the creature-reach rule by design); Magmatic
  Insight for Mask of Memory (both bin a Desert for Yuma); The Scorpion God
  for Sword of Truth and Justice (its proliferate feeds Auntie Ool; the
  +1/+1 clash is a play note); Fire Covenant for Chaos Warp (interaction
  staple); Insidious Roots in Food and Fellowship (eight creature-token
  makers — Field-Tested Frying Pan makes Halflings — fit 0.52). The three
  moved swaps were read too: There and Back Again (a Mountain and a 6/6
  Dragon in a deck with Mountains), Hew the Entwood (it sacrifices lands for
  Hearthhull), Rishkar, Peema Renegade (Hakbal's countered creatures tap for
  mana). `verify_symptoms.py`: 140.
- **Batch 16u (2026-11-02; the 25 728 / 339 / 115 → 728 / 339 / 117, held-out
  and fresh unchanged at 561 / 263 / 103 and 294 / 126 / 51).** Closes 16t's
  open Fling item, then what reading the moved swaps found, three times
  over. Fixed: (142) *a spell whose cost sacrifices a creature pays as an
  activation's sacrifice does* (`removal._spell_sacrifices` →
  `activated_sac`): Fling 0.69 → 0.32, Bone Splinters 0.41 → 0.04, so
  Fling no longer replaces Palace Jailer (Riders of Rohan), Spine of Ish Sah
  (Tinker Time) or Unholy Heat (Desert Bloom). (143) *a card that pays a
  creature the cut doesn't is no cheaper* (`swaps._pays_a_sacrifice_more`
  denies the tempo exemption): Fling for Fiend Hunter. (144) *an
  Equipment's granted removal costs its equip* (`removal._equip_cost`, and
  `_job_cost` reads the removal's deploy cost): Thornbite Staff's ping
  behind "Equip {4}" costs six and scores 0.15, no upgrade of Fiend Hunter
  or Root Out. The moved swaps read: Aether Channeler (it bounces a
  nonland permanent), Chainsaw ("3 damage to up to one target creature"),
  Rose Room Treasurer (X damage from the third creature a turn, which
  Tinker Time's token makers reach). `verify_symptoms.py`: 141.
- **Batch 16v (2026-11-02; the 25 728 / 339 / 117 → 728 / 339 / 116, held-out
  and fresh unchanged at 561 / 263 / 103 and 294 / 126 / 51).** The fifth
  full 55-deck re-read (five Sonnet reviewers; 16 flags, the fewest yet).
  Fixed: (145) *no keep page for a commander paid by its tokens leaving*
  (`issues._pays_off_tokens_leaving`): Zurgo Stormrender's "Whenever a
  creature token you control leaves the battlefield" is paid by its
  mobilize tokens' end-step sacrifice, and Sundial of the Infinite had
  taken Gix, Yawgmoth Praetor's slot in Mardu Surge; Saheeli and Sliver
  Gravemother keep theirs. (146) *a shrink sized by the sacrificed
  creature's toughness spares the deck's tougher creatures*
  (`board_wipe` spared kind `tough_chosen`, read at the chosen line's 3):
  Tip the Scales under Felothar's walls now goes to The Battle of Bywater,
  not White Sun's Twilight. (147) *a fill never cuts a card of a row the
  deck is short of* (`take_cut(filling=…)`, as the lane-ok fallback since
  16r) — no proposal changed. Verdicts, with the card text, rulings or
  needs: Aetherflux Reservoir in Animated Army (Bello animates it); Haliya
  in Deep Clue Sea (each Clue entering gains a life); Norn's Decree for
  Hot Pursuit (goad for goad); Dune Chanter for Icetill Explorer and
  Hangarback Walker for Lulu, Nissa, Steward of Elements for Brotherhood
  Regalia (a need for a need); Heartless Hidetsugu with Angrath's Marauders
  (Spellbook's own prerequisite: "You have an odd life total", so you
  survive at 1); Massacre Girl, Known Killer as draw (its wither feeds its
  own toughness-below-1 draw); Gix for Black Market Connections (card draw
  is in band in Mardu Surge: a strong body for a real ramp fill); Viscera
  Seer for Inkshield (both supply Zurgo's token-leaves need).
  `verify_symptoms.py`: 143.
- **Batch 16w (2026-11-02; the 25 728 / 339 / 116 → 728 / 340 / 115, held-out
  561 / 263 / 103 → 561 / 264 / 102, fresh unchanged at 294 / 126 / 51).**
  The parse gaps the earlier batches recorded as upstream-only, closed
  in-repo through the correction layer (each row retires with its canary):
  (148) `misparsed_shapes` writes Sinister Gnarlbark's unparsed "draw a card
  and blight 1" as a `Draw` and a `BlightEffect` (CR 701.68a); (149)
  Unwanted Remake's bare `ManifestDread` gets Fateful Absence's
  `player_scope: ParentObjectTargetController`, and
  `crosswalk.acts_for_answered_target` now reads that scope — Fateful
  Absence's and Beast Within's "Its controller …" had been read as yours
  too; (150) Akiri, Fearless Voyager's dropped "with one or more equipped
  creatures" is written back as a `HasAttachment{Equipment}` attacker
  filter, and `card_draw` reads an `attached_<kind>` fuel off the deck's
  Equipment (Desert Bloom: 0.03); (151) Umbra Mystic's unparsed grant is
  written as a `TotemArmor` static over your Auras, umbra armor joins
  `PROTECTIVE_KEYWORDS` and the protection read's wipe-proof set (CR
  702.89a: it reads 0.44 at protection; the `protective_grant_parse_failure`
  bridge graduates its pin); (152) Everlasting Torment's "as though its
  source had wither", a parser residue, is the
  `wither_grant_unparsed` bridge row emitting `minus_counters_matter`, so
  Auntie Ool's -1/-1 need sees it — it is no longer cut as dead weight.
  (153) *a dig steals only what you may play*
  (`tree_synthesis.value_engines._theft_dig_effect` needs a `CastFromZone` /
  `FreeCastFromZones` / unparsed clause beside the opponent's
  `ExileFromTopUntil`, and the bucket-B theft arm stands down on a typed
  dig): Tasha's Hideous Laughter and Umbris leave `theft_makers`; Chaos
  Wand, Dream Harvest, Plargg and Nassari and Wand of Wonder stay. Verdict:
  Unexplained Absence for Unwanted Remake (interaction for interaction).
  `verify_symptoms.py`: 148.
- **Batch 16x (2026-11-02; the 25 728 / 340 / 115 → 728 / 340 / 113, held-out
  561 / 264 / 102 → 561 / 264 / 103, fresh unchanged at 294 / 126 / 51).** The
  sixth full 55-deck re-read (five Sonnet reviewers; 15 flags, one
  structural). Fixed: (154) *a mode chosen again and again is its size
  times the choices* (`board_wipe._repeat_choices`, off the face's
  `modal.allow_repeat_modes` / `max_choices`): Fiery Confluence's "1 damage
  to each creature" is 3; and (155) *a damage or shrink sweep under
  `KILL_SIZE` spares the creatures tougher than it* (`tough_above`), read
  by the upgrade gate only (`board_wipe.toughness_spares`): Fiery
  Confluence under Pantlaza's 4-toughness Dinosaurs no longer goes to
  Martial Coup but to Delayed Blast Fireball. Read into the sweep's own
  `one_sided` score it was measured and narrowed — a 1-damage sweep
  "spares" most decks, and Golgari Charm rose above Deluge of Doom in Death
  Toll. Verdicts, with the card text, counts or measurement: Jeska, Thrice
  Reborn under Commodore Guff (at least one loyalty once Guff is cast);
  Vanquisher's Banner for Kindred Boon, Kotis for Perpetual Timepiece,
  Essence Anchor for Llanowar Mentor, Frontier Warmonger for Shadowspear
  (theme for theme, a need for a need); Timely Ward for Gaea's Gift
  (protection for protection); All Will Be One (Bello animates it; six
  counter sources); Wheel of Misfortune (you choose your number); Deepglow
  Skate for Fellwar Stone (a fill cut from need suppliers, as Kulrath
  Knight); Anger in Creative Energy (a creature: it reaches the graveyard
  by dying); Welcoming Vampire for Sylvan Library (the draw read prefers
  the Library); Abzan Falconer (it outlasts itself; Olivia places
  counters); Thought-Knot Seer and Thief of Existence in Peace Offering
  (eight colorless sources, four per pip); Storm's Wrath for Season of
  Weaving (symmetric for symmetric); Immoral Bargain for Feed the Swarm
  (Dina's sacrifice event is broad, and holding broad event needs was
  measured and reverted in batch 15c). `verify_symptoms.py`: 149.
- **Batch 16y (2026-11-02; the 25 728 / 340 / 113 → 728 / 339 / 113, held-out
  561 / 264 / 103 → 559 / 264 / 103, fresh unchanged at 294 / 126 / 51).** The
  seventh full 55-deck re-read (five Sonnet reviewers; 19 flags, eight
  structural), each fix read back on all 55 decks. Fixed: (156) *a short
  row keeps a rider job's page* (`issues`: a plan card whose job is a
  trigger rider goes to its job page when that row is short — Synapse
  Sliver's draw no longer goes to Roaming Throne with Sliver Swarm two
  draws short); (157) *a delirium deck reads its graveyard's card types at
  four* (`board_wipe._delirium_deck`, six cards counting
  `DistinctCardTypes`): Death Toll's Deluge of Doom is a -4/-4, no longer
  traded for Phyresis Outbreak's -1/-1, and a small sweep's spared
  toughness follows its deck-read size; (158) *own combat damage drains on
  your turn* (`commander_need._drains_only_on_own_combat`, CR 510.1b /
  506.2): Rankle feeds no Valgavoth and no longer takes Spiteful Visions'
  slot; (159) *an add the commander already grants is dead*
  (`swaps._commander_already_grants`): Rolling Stones and Animate Wall
  under Felothar; (160) *life a target's controller gains is not yours*
  (`core_makers`, `ParentTargetController` beside `ParentTargetOwner`):
  Nature's Claim no longer supplies Dina's lifegain need; (161) *a sweep
  that keeps your own pick keeps the commander* (`board_wipe.keeps_own_pick`):
  Promise of Loyalty no longer goes to Damn under Killian. Verdicts, with
  the card text or counts: Behind the Scenes for Woolly Razorback (theme
  for theme); Find // Finality for One Ring to Rule Them All (both kill most
  of Graveyard Overdrive: Finality spares about 11 of 32, the Ring 7);
  Nightshade Harvester for Agent of the Iron Throne (your creatures die on
  their turns too); Starfield of Nyx for Sanguine Bond (the same proposal
  adds three lifegain cards, back to eight); Ferrafor as a protection-fill
  cut (as Kulrath Knight); the Curses under Killian (an enchantment
  entering goads); Traxos under Eshki (a 7-power creature spell); Idol of
  Oblivion in Party Time (Jadar's end-step Zombie); Skullclamp in Tyranid
  Swarm (its token makers); Magus of the Wheel for Increasing Devotion and
  Pest Infestation for Withering Torment (Dina's sacrifice event is broad,
  as batch 16x). Village Rites's batch-15 keep becomes a `no_pair` against
  Esper Sentinel: it now goes to Invasion of New Capenna, an outlet too
  ("you may sacrifice an artifact or creature"). `verify_symptoms.py`: 155.
- **Batch 16z (2026-11-02; the 25 728 / 339 / 113 → 725 / 337 / 114, held-out
  559 / 264 / 103 → 557 / 264 / 104, fresh 294 / 126 / 51 → 294 / 126 / 50).** The
  eighth full 55-deck re-read (five Sonnet reviewers; 13 flags, five
  structural), each fix read back on all 55 decks. Fixed: (162) *a land put
  on a later sacrifice is not early ramp* (`ramp._land_only_later`, the
  self-`sacrificed` trigger beside `_LEAVES`), nor a tempo upgrade: Ordeal
  of Nylea's lands wait on three attacks and no longer take Careful
  Cultivation's slot; (163) *a narrower draw trigger is no upgrade at the
  same job* (`card_draw.narrower_engine`): Kutzil's pumped-creature combat
  draw for Ohran Frostfang's any-creature one; (164) *an artifact-creature
  draw runs on artifact creatures* (`card_draw` fuel `artifact_creatures`,
  artifact-token makers included; an engine making its own fuels itself —
  Thopter Shop); (165) *a narrow team grant protects the creatures it
  names* (`protection.deck_fit`, creature grants only — Nissa's lands and
  Darksteel Forge's artifacts are not read against creatures); (166) *the
  proposal is read whole* (`swaps._unfueled_adds`): an add whose draw fuel
  or narrow protection the deck the whole proposal leaves can't feed is
  dropped and refunded — Losheel in Deep Clue Sea, Skullclamp in Prismari
  Artistry, Garruk's Uprising in two decks — except a battlefield
  chosen-type draw under Omo (Kindred Discovery). Its cost: a dropped add's
  cut stays in the deck, so four guide cuts fall with their bad adds; *a
  dropped swap could take its cut's next-best add* is open. Verdicts:
  Admiral Beckett Brass for Edward Kenway, Aligned Heart for Unbreakable
  Formation (an instant for flurry), Anger in Family Matters, Fumigate for
  Damn under Frodo (the lifegain need is broad, batch 15c), Wave of
  Reckoning for Contagion Engine (proliferate twice grows its counters),
  Sephara in Silverquill Influence (8 of 17 creatures fly after the whole
  proposal), Inspiring Call under Dina (Dina places +1/+1 counters).
  `verify_symptoms.py`: 160.
- **Batch 17a (2026-11-02; the 25 unchanged at 725 / 337 / 114, held-out
  557 / 264 / 104 → 557 / 264 / 105, fresh 294 / 126 / 50 → 294 / 126 / 49).**
  The ninth full 55-deck re-read (five Sonnet reviewers; 8 flags, two
  structural — parts 1-3, 35 decks, found none). Fixed: (167) *a self-mill
  deck takes no card that only mills opponents* (`swaps._self_mill_deck`,
  `_mills_only_opponents`: `mill_makers|opponents|` without
  `graveyard_makers|you|`): Szarekh's Necron Dynasties no longer adds
  Mindcrank and Altar of the Brood, but Perpetual Timepiece and Grinding
  Station; (168) *a typed combat-damage trigger wants those types to
  connect* (`commander_need._evasion_for`): Olivia, Opulent Outlaw's
  outlaws (CR 700.12) — an evasive body outside them supplies nothing (a
  changeling is every type, CR 702.73a; a grant still feeds it), so
  Tenured Inkcaster goes to Vadmir, New Blood, not Hangarback Walker.
  Verdicts: Chandra's Ignition for Blasphemous Act (a guide cut); Redemption
  Arc for Lightning Bolt (15 other goaders; a redundancy need); Dusk //
  Dawn under Nalia (a 3/3 whose full-party counters push the small
  creatures to 3 power); Hofri for Daretti, Scrap Savant (its -2 returns a
  card from the graveyard for Quintorius). `verify_symptoms.py`: 162.
- **Batch 17b (2026-11-02; the 25 unchanged at 725 / 337 / 114, held-out
  557 / 264 / 105 → 557 / 264 / 103, fresh unchanged at 294 / 126 / 49).**
  The tenth full 55-deck re-read (five Sonnet reviewers; 13 flags, two
  structural). Fixed: (169) *a land a spell sacrifices as its effect is a
  land paid* (`ramp._lands`, costs and effects alike): Cycle of Renewal's
  "Sacrifice a land. Search ... tapped" netted a land more than Harrow's
  additional cost and replaced it — Harrow now goes to Edge of Autumn
  (World Shaper); (170) *an entering creature has only its printed types*
  (`swaps._Gate.entering`): under Omo, whose everything counters are on
  creatures already out, a trigger on a tribe entering waits on the deck's
  printed members — Dragon Tempest is dead under Omo (an old test said
  alive; Omo's text says otherwise), Elvish Warmaster keeps its slot on its
  Elf pump, which the countered creatures do get. The held-out's two lost
  guide adds are World Shaper's Sakura-Tribe Elder and Elvish Reclaimer,
  their slots reordered by Cycle of Renewal's lower read (theme-page order,
  not a gate). Verdicts: Camellia, the Seedmiser (a Squirrel lord);
  Lathliss, Dragon Queen as a closer (a 6/6 flier pumping itself);
  Inspiring Statuary for Mirrorworks (17 nontoken artifacts); Voracious
  Bibliophile for Kraum (each opponent's second spell); Eight-and-a-Half-
  Tails for Duty Beyond Death (protection for protection); Advanced
  Reconstruction for Soul Separator and Hammer of Purphoros for Entish
  Restoration (theme for theme, the same need). `verify_symptoms.py`: 163.
- **Batch 17c (2026-11-02; the 25 725 / 337 / 114 → 723 / 335 / 114, held-out
  557 / 264 / 103 → 558 / 264 / 108, fresh 294 / 126 / 49 → 294 / 126 / 48).**
  The eleventh full 55-deck re-read (five Sonnet reviewers; 9 flags, three
  structural), and the re-read of the swaps its fixes moved (two more).
  Fixed: (171) *in a deck of three colours or more a source that fixes less is
  no upgrade to a fixer* (one colour for many, two for five) (`swaps._FIXING_COLORS`, the ramp read's `fixes`):
  Ignoble Hierarch for Llanowar Elves (Graveyard Overdrive), Solar Array
  for Thought Vessel (Counter Intelligence — now Chromatic Lantern); (172)
  *a kicked sweep costs its kicker* (`board_wipe._kicker_mana`); (173) *what
  a sweep leaves standing spares the deck only if the deck holds it*
  (`board_wipe` deck-read `spares`: a fixed type list by the deck's
  creatures, +1/+1 counters and tokens by a card in eight making them,
  historic by `_DECK_SPARED_SHARE`): Slinn Voda's Merfolk-and-Krakens for
  Quandrix's Fractals, Wave Goodbye's countered creatures for Revenant
  Recon's three counter cards; (174) *a bounce is no upgrade to a kill
  unless it spares more* (`swaps._bounces_for_a_kill`): Slinn Voda for
  Oversimplify, Wave Goodbye for Black Sun's Zenith — Cyclonic Rift's
  one-sided overload and Raise the Palisade's chosen type still pass. The
  batch-14 `never Talisman of Creativity` check narrows to its lateral pair
  (Cultivator's Caravan's five mana for the Talisman's two is a tempo
  trade). Verdicts: Shadowmage Infiltrator for Dead Man's Chest (a
  different Gonti need); Fell the Mighty for In Garruk's Wake (one-sided
  for one-sided). `verify_symptoms.py`: 168.
- **Twelfth full re-read (2026-11-02, over batch 17c's proposals): no
  structural flaw.** Five Sonnet reviewers over all 55 decks raised 7 flags,
  each settled on card text: Garruk, Cursed Huntsman for Orcish Bowmasters
  (removal for removal; Bowmasters amasses an Army token for Hazel);
  Warping Wail for Null Elemental Blast (both narrow answers); Expressive
  Iteration for Negate (an instant on Prismari's spells theme); Faerie
  Mastermind for Brainstorm and Revenant Recon's Village Rites / Deadly
  Dispute (draw for draw); Nils, Discipline Enforcer for Windborn Muse
  (both attack taxes); Scriv, the Obligator for Cathar's Call (an Aura:
  its entering goads for Killian, its enchanted attacker draws). Structural
  flaws per full pass since batch 16n: 17, 10, 3, 1, 8, 5, 2, 2, 3 (+2 in
  the moved swaps), 0.
- **Batch 17d (2026-11-03; the code review of 2971ce9b..HEAD; the 25
  723 / 335 / 114 → 726 / 337 / 114, held-out 558 / 264 / 108 → 560 / 264 /
  109, fresh unchanged at 294 / 126 / 48).** (175) *a rider keeps its job page
  only when its own row is short* (`issues.upgrade_job`'s `short_rows`; fix
  156 read any short row); (176) *a self-mill deck is one whose mill is at
  least three quarters its own* (`swaps._SELF_MILL_SHARE`; fix 167 required
  none); (177) *a dropped add's cut takes its next fuelled add*
  (`swaps._next_fueled_add`, the add's own search re-run, `unfueled` never
  re-picked): Thought Monitor → Deduce, Narci → Phyrexian Arena, Snake
  Umbra → Sphere Grid, Dirgur Focusmage → Thoughtcast, Ribtruss Roaster →
  Doubling Season; (178) *Mirko's dropped power bound is written back in
  the correction layer* (`misparsed_shapes._relative_power_return`, its
  canary `test_relative_power_return_canary`; `commander_need`'s
  description regex deleted); (179) *a self-entering return of a card of
  yours gates on its type, and an unparsed ability holds no gate*
  (`swaps._unit_gates`): Forge Anew is dead without Equipment. Fixes 148 and
  149 keep their description regex, the census now in their docstrings
  (4,060 `Unimplemented` bodies, four of them a blight; five scopeless
  `ManifestDread` subs, four of them yours). Fix 165's non-creature
  exclusion has its test. `verify_symptoms.py`: 170.
