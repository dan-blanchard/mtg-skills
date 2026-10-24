# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

**From the Jace, Multiverse Architect precon tune (2026-10-17)**

- **`scryfall-lookup --batch` without `--bulk-data` dies on one Scryfall 503.** A
  name the local pool can't resolve (or every name, when no `--bulk-data` is
  passed) goes to `fetch_card`, and one `HTTPError` aborts the whole batch with a
  traceback instead of landing in the envelope's `missing`. Catch the per-name
  network failure in `lookup_single`'s batch loop and report it as missing; keep
  the hard exit for a bulk that can't be read at all.
- **What the polymorph tune and the 25-precon audit still get wrong** (third
  pass, 2026-10-18 — `docs/plans/precon-audit-2026-10-18.md` has the method,
  the three before / after tables and the per-precon reads; the first two
  passes' fixes are listed there). Fixed in the third pass: a quality read
  inside a lane is "a feeder nobody plays" (measured, below); Spine fills
  rank by play-rate within a mana-value band; player-only damage is not
  `interaction`; Bello's Animation and Yuma's Deserts have lanes
  (`animate_makers|you|<Type>`, `land_type_matters|you|<Type>`); pillowfort
  and fogs are not `superfriends_matters`; a typed token replacement or
  sacrifice trigger carries its token kind (Xorn is `treasure_matters`,
  Academy Manufactor three kinds, Fisher's Talent `tokens_matter|you|Fish`);
  an artifact-TOKEN maker is a maker, never `artifacts_matter`; carers respect
  scope where the specs split it ("Opponents' graveyards" 43 → 4 under
  Teval); two avenues with one carer set are one theme (Polymorph fodder
  absorbs Token generators); an emerging theme needs two carers in
  proportion; the primary lane is a held lane deep enough to show; three pair
  rows for the Enchantment / Artifact / Planeswalker cheat subjects; the CR
  2026-09-25 subtype lists (Heartwood); Syr Konrad's folded zone-change
  trigger reads as `dies` for a dies doubler; a card that merely has an
  activated ability is a payoff target of "Activated-ability engine", not a
  builder (its untap engines are — Abzan Armor read that lane as its main
  over a 42-deep toughness lane; the Jace phantom of the polymorph entry's
  (d) is gone with it). Fixed in the seventh pass (2026-10-19): the upgrade
  slots — an off-lane card past rank 3000 and the deep lane's least-played
  half (never a Granter), traded by a last-ranked `upgrade` issue for a
  better-played card at no higher mana-value band doing the same job (223
  swaps, 104 cuts and 29 adds matching a guide, from 85 / 44 / 8); every theme
  add is the most-played candidate that fits; an Equipment's, Aura's or
  target's shrink and damage to each player are not board wipes; the main
  theme no longer changes with the string-hash seed. Fixed in the eighth pass
  (2026-10-19): the interaction search combined its five presets with AND and
  sourced nothing (no removal fill or upgrade since the fourth pass) — it reads
  any of them now; job reads (`_analysis/job_quality/`, ADR-0060) gate which
  cards may be an upgrade and, for wipes / draw, order them blended with
  play-rate, so a looter is no draw upgrade and Animate Dead no removal; overload spells are
  sweeps (`crosswalk.overload_sweep`, a retirement canary). Left:
  (a) **Inside a lane, the cut read is "a feeder nobody plays" — don't
  re-suggest a function read.** Measured 2026-10-18 on the 25 precons' main
  lanes (906 lane cards, 222 guide cuts, base rate 0.245): no function
  feature moved the rate — one-shot vs repeatable 0.19, body for its cost
  0.27-0.32, in-deck synergy depth (`rank_candidates` over the deck's own
  cards) flat 0.22-0.25 across quartiles, lanes touched 0.14-0.28. Play-rate
  does (least-played quarter 0.35), and "a member that does not itself care
  about the lane" more so (0.32 vs carers 0.20; rank-bottom-quarter feeders
  0.46; a feeder with no template role past rank 8000: 0.67, n=24). The
  `lane_upgrade` tier now orders feeders before carers, then least played
  (top-five precision 0.48; costlier-first within the half was 0.30). The
  guides' stated reasons (one-shot, delirium type, curve) are not what their
  cuts share, and the same holds for the flip-quality read the polymorph tune
  wanted. Script: `docs/plans/precon-audit/lane_quality.py` (rerun recipe in
  `docs/plans/precon-audit-2026-10-18.md`).
  (b) **Lane verdicts — don't re-suggest** (the leftovers closed 2026-10-23).
  The `animate_artifact` regex lane retired for `animate_makers` drops 24
  cards with no replacement by design: 19 Vehicles, 2 artifacts that animate
  only themselves, 2 copy effects (Saheeli, Sublime Artificer; True
  Polymorph). A token maker is a doer — `artifacts_matter|you|token` /
  `enchantments_matter|you|token` (Roles, Glimmers), never the bare payoff;
  an artifact or enchantment card keeps the LOW membership-floor key. In Too
  Deep is no `clue_makers`: the Clue it makes is the enchanted permanent's
  controller's. The superfriends synth arm stands down on a card naming
  planeswalkers only as half of a bare "creature or planeswalker" and never
  their loyalty (`crosswalk.planeswalkers_only_beside_creatures` — Angelic
  Intervention, Kaya's Ghostform, Fey Steed and six more), so Spark Double
  (an extra loyalty counter) and Lae'zel (no typed planeswalker filter) keep
  it.
  (d) **Text-mirror leftovers behind the payoff lanes.** The three `_matters`
  text mirrors (artifacts / enchantments / the cast arm) still run over oracle
  clauses minus what `board_and_ramp._non_animation_clauses` claims: an
  animating static's description, and since 2026-10-23 the whole ability
  holding a one-shot animation of something other than the card itself (Rise
  and Shine, Alloy Animist, Skilled Animator and eight more lost
  `artifacts_matter|you|`; a self-animation keeps its ability's text — Iron
  Man Armor's granted count). Running the mirrors over every description in
  each non-claimed unit (nested ones too: Galvanic Blast's metalcraft rider)
  plus the root's mode text instead is still not sound. Affinity for an
  artifact kind or enchantments and improvise (`card_keyword_types` /
  `card_keywords`) and a tap-artifacts cost (`controller_paid_cost_leaves`,
  which now reaches a spell's additional `TapCreatures`) read off the tree
  since 2026-10-24, so 27 of the cards it lost keep the key, but 10 real
  payoffs still lose it, their only read being text no node carries: Saga chapters (Age of Ultron III's "artifact creatures you control
  gain deathtouch", Origin of Iron Man, Yotia Declares War, Fugitive of the
  Judoon — phase writes "Chapter N" and no chapter text; each needs its own
  typed read), a trigger's bullets (Venser, Corpse Puppet —
  `execute.modal.mode_descriptions`, which the shape would have to read), a
  modal header's condition (Soul Transfer — a root `modal.constraints`
  `ConditionalMaxChoices` no tree field carries), an alternative cost (Zahid —
  `casting_options` keeps only PayLife and has no Spell carrier on a creature),
  "Enchant artifact you control" (Hardlight Containment — `card_keyword_types`
  drops the keyword's controller), a delayed trigger (Rite of Harmony's
  "creature or enchantment you control enters this turn"), and Platinum Angel
  Avatar's condition, which phase drops. (The pair rows read candidates
  without membership idents since the fourth pass, so a card with both a cast and an enters payoff —
  Tuvasa the Sunlit, Sai — fires the typed-cheat rows and Sol Ring / Pacifism
  no longer score as payoffs.)
  (g) **The guide cuts the tuner protects** (2026-10-24, the experiment table in
  `docs/plans/precon-audit-2026-10-18.md`, "The remaining tuner levers"). Shipped:
  popular cards (inside `UPGRADE_RANK`, not premium) off every lane and on none of
  the deck's viable avenues are the last upgrade tier (`focus.popular_upgrade_cards`,
  after the deep lane's half; the guides cut 0.28 of them, 27 of 96; beside the
  fringe tier they spent the lane's theme budget, 51 adds). Left, with no read that
  separates them: 62 popular cuts (Feed the Swarm is premium, rank 93; the rest
  serve a viable avenue) and 55 commander-lane doers, 54 of them carers, whose
  guide-cut rate outside the lane's half is 0.08-0.20 in every carer split by role
  and play-rate holding more than four cards, below the decks' 0.24 — (a) holds,
  don't re-suggest a split of them without a new read; Sliver Swarm's 11 are
  Granters (ADR-0040 §4). Script: `docs/plans/precon-audit/cut_splits.py` (both
  splits; same ROOT as `misses.py`).
  (j) **Job-read leftovers** (ADR-0060 and its 2026-10-24 amendment; each module
  docstring lists its own). The ninth pass measured every read as the order and as
  "better than the cut" and kept neither, so the order is still the blend (wipes,
  draw, protection) or play-rate (removal, ramp), with theme fit breaking a near tie
  for draw and ramp. What is left. The wipe read's cost misreads were fixed
  2026-10-24 (ADR-0060's second amendment that day: a spree mode's cost, an enters
  trigger's X, no flicker / transform-back / event-fired clean sweep), its
  reference line recalibrated to a four-mana clean sweep, and its per-creature
  discount read at a board of eight, generic mana only (ADR-0060's last amendment:
  Blasphemous Act 0.82, Vanquish the Horde 0.80, Toxic Deluge 0.78, Wrath of God and
  Damnation 0.76). The read leading the wipe upgrades then cleared the bar alone
  (58 / 179, a budget-moved Jhoira) and added nothing beside the shipped budget
  rule; one of its picks is Harsh Mercy, whose chosen-type spare phase drops, so
  don't re-suggest leading with it until the read's "left unread" list shrinks.
  Jaya Ballard no longer scores. The removal read's agreement
  with play-rate over every card with a removal effect is weak (it was fitted on
  cards whose main job is removal); Winnow's "if another permanent with the same
  name" condition, which phase drops, is read by name (`removal._CONDITION_DROPPED`,
  retired by its canary). Theme fit as a tie lost for removal (38 adds), wipes
  (39) and protection (no change). Play-rate's picks still recur where nothing else
  decides: the removal adds are Beast Within in 10 precons, Path to Exile, Swords to
  Plowshares and Chaos Warp in 7, the ramp adds Fellwar Stone in 9; Garruk's
  Uprising is the draw add in 7 (10 before the theme tie, backlog "(e)" until
  2026-10-24). Protection goes unsearched in 18 guide adds' decks because ADR-0024
  asks for protection only from a combo or control deck or a voltron plan;
  protection for every shape (a target of 5 or 3) matched fewer adds.
  (m) **Recall** (`precon-audit/misses.py`, at the largest guide's thirty
  swaps and each precon's own guides' budget, `budgets.json`, Spellbook cached):
  195 of 408 cuttable guide cuts, 60 of 610 in-scope guide adds (2026-10-24, after
  the near-tie budget rule; 180 / 57 before it, 169 / 56 at 9e0026ed). Shipped: where
  play-rate orders a page, a near tie that costs less is the add (`swaps._near_tie`:
  play-rates within a factor of two, read scores within 0.1 for an ordering job;
  every width from 0.1 to 0.5 log10 rank cleared the bar and wider kept gaining —
  the budget binds; the table is the audit's "The last tuner levers"). The levers
  by size at the shipped tune: adds a page held but outranked (244), theme adds no
  search reaches (169, (r)), cuts the popularity threshold still shields (62),
  commander-lane cards the guides trim (57), and cuts a budget-bound tune never
  reaches (27, from 43). Measured negative, so don't re-suggest without a new
  read: theme adds serving two viable avenues first (46 adds), and theme adds by
  a synergy / play-rate blend (53).
  Six guide summaries don't tag sources per row (`guide_sizes.py` skips them).
  (r) **Theme reach, what's left** (2026-10-24; the experiment table is in
  `docs/plans/precon-audit-2026-10-18.md`, "Theme reach"). Shipped: a type- or
  preset-searched theme takes up to one add in five from its serve's broader
  page, never the first, with the fit floor read off its own members; the theme's
  adds are shared by depth over the main avenues; and under a creature commander
  the suit-up avenue never folds into another theme. 169 theme guide adds still
  have no search. Measured negative, so don't re-suggest without a new read:
  payoffs first (47 guide adds over the serve's whole match set, 44 over the
  150-card page, against 50: the payoffs cost more and spend small budgets); the
  whole match set as the theme page (no gain, twice the tune time); support at
  one in three or more (generic tribal support takes the members' budget);
  slots shared over every viable avenue (35) or by carers (45), because the
  generic subs' pages hold staples (Murder for Fae Dominion's Spellslinger).
  Left: the guide adds that serve only a lane that isn't viable (Blood Rites'
  sacrifice package) still have no search; only four serve only a sub (Living
  Energy's Arcum Dagsson, Clever Impersonator, Scrap Welder; Deep Clue Sea's
  Displaced Dinosaurs). Measured negative 2026-10-24: a sub with a main's carers
  (6) taking one add that also serves a main (57 adds, 2 guide cuts fewer; neither
  deck moved). At
  a913f172 the 150-card play-rate page (`swaps._PAGE`) hid 71 main-avenue guide
  adds; "the most played that fits" never reaches them, and payoffs first
  didn't either. Virtue and Valor's Auras that pump their creature
  (`voltron_makers|you|pump`) count as Ellivere's lane doers since 2026-10-24
  (`metrics._LANE_DOER_IDENTS`), so they left the off-lane upgrade slots; the deep
  lane's least-played half still trades Daybreak Coronet, Angelic Destiny, Ancestral
  Mask and Snake Umbra (none a guide cut; now for Whispersilk Cloak, Hardened Scales,
  Sram and Heroic Intervention, 20 swaps). Left: no read separates an Aura deck's
  gear from Equipment (Ellivere's lane is enchanted creatures; Equipment makes none),
  and Ancestral Mask's count of enchantments emits no carer ident.
  (n) **Lane follow-up verdicts — don't re-suggest without a card** (2026-10-24:
  a targeted Treasure conversion is no `ramp` — Vraska, Betrayal's Sting's −2,
  Kitesail Larcenist answer the target, whose controller keeps it, CR 110.2 /
  602.2). Checked and empty on the 2026-10-23 corpus: a card with both a creature-type and a card-type Choose firing
  `chosen_type_matters` (none), and a discard or leaves-the-battlefield
  trigger's self-return firing `bounce_tempo` (none; the other trigger
  back-references on cards that fire return an event object — a blocked
  creature, a damage source, a land tapped for mana).
  (o) **Theme matching off the IR, what's left** (2026-10-24). A theme's
  candidate page derives from its serve (``signal_specs.theme_page``: Find's
  ``engine.lane_page``, the tuner's ``swaps._run_search``, ``search_filters``);
  ``SignalSpec.search`` / ``SubAvenue.search`` is only the page's override — a
  tribe's or source type's card type, a preset, a mana-value band — and most
  specs carry none. The 532 pattern searches (346 specs', 186 sub-avenues')
  and 33 ``regex=`` searches on ident-served sweep specs are retired, with the
  32 regex constants that fed only them; the five serve-less sub-avenues
  (Creature-lands' three, Flip fixing, Punish land loss) carry their pattern
  verbatim as their serve, same pages. ``test_a_theme_pages_by_its_serve_not_a_pattern``
  pins it. One pattern search is left: One-sided keep-N's, whose serve admits
  nothing (its pattern as a serve would count the deck's own keep-N wraths as
  the lane's depth). What the retired patterns reached that the serves (the
  pages since ``theme_page``) don't, over the commander pool, is mostly
  reminder-text and stray-word noise (Keyword soup's 7289, Damage to
  opponents' 5574), but two are real gaps: Creature-lands' serve misses the
  manlands themselves (Mutavault, Mishra's Factory, Inkmoth Nexus — 46; the
  lane's ident is its animators' and payoffs'), and Crimes' serve misses the
  crimes (Swords to Plowshares, Path to Exile, Beast Within — the lane's ident
  is the payoffs'). Eleven ``_sweep_detectors`` regexes the retired searches
  used are referenced nowhere now (``ABILITY_COPY_REGEX``,
  ``TOUGHNESS_COMBAT_REGEX``, ``SELF_COUNTER_GROW_SWEEP_REGEX`` and eight
  more); their comment blocks carry the lanes' migration history, so fold
  that into the lanes before deleting them.
  Serves were written to credit a deck's own cards, not to page candidates:
  each OR arm (types,
  keywords, cmc and stat floors) can admit a card on its own, as the
  toughness >= 4 arm admitted Roaming Throne — a guard would pin each arm's
  should / should-not real cards, the ``theme_presets`` way. And an IR hit's
  role is read by lining the emitting unit's text up with an oracle clause,
  then that clause with a compat ability (``ranking._hit_clauses``): reading
  the payoff test off the unit itself would drop both text alignments, and
  would give a role to the hits no single ability emits (a keyword's lifelink,
  Crucible of Worlds' whole-card ident, a modal spell's text-less mode), which
  still score structural. Seven serves a theme pages by still carry an oracle
  arm (``xspell_matters``, ``team_buff``, ``self_etb_payload``,
  ``permanent_etb``, ``target_redirect``, ``spell_redirect``,
  ``land_protection`` — Pass D's list): their page is partly a pattern. Since
  2026-10-24 an IR hit takes its role from its emitting unit where the unit
  decides one (``ranking._unit_role``: a replacement emitting the lane's ident is
  a payoff — Anointed Procession, Parallel Lives, Hardened Scales; a
  ``DOER_SUBJECTS`` ident an enabler), else from the clause test; one guide add
  fewer (Virtue and Valor's Sram for Hardened Scales), shipped as a read fix.
  (l) **Tune speed, what's left** (2026-10-24). The ranking's per-unit ident
  attribution persists in a write-back sidecar beside the signals index
  (`<bulk>.provenance.pkl`, `ident_provenance.attach_provenance_sidecar`; the
  deck-tune CLI and the hub attach it), and the index build reads blink's
  concept arm off its one extraction (`Preset.concept_signals`): the build
  147 → 107 s (payload byte-identical), a warm Blood Rites tune 15.6 → 12.5 s
  (profiled: attribution 9.1 → 0 s). A tune's first sight of a candidate still
  pays its attribution (about 9 ms a card). `card_search.filter_records`
  memoizes each search context's gate (layout, legality, game, color identity:
  `_gated`, per records list), so a tune's 17 pages scan the in-identity slice,
  not the ~100k-printing pool: 5.3 → 1.9 s of a profiled Blood Rites tune
  (18.5 → 14.9 s), warm tunes 13.7–17.1 → 11.2–12.3 s, swaps byte-identical
  on five precons. A per-serve slice memo measured no gain (two serve pages a
  tune). Left, by size: `signals_index.signal_source_files` walks the 214
  modules' ASTs twice a process (2.6 s) to key the sidecar, and the pages' own
  filters (presets, serves) over the slice (1.6 s).

- **Competitive Brawl's "banned as a commander" reads as `restricted`.** The
  2026-10-12 B&R update introduced the category (mtg.wiki "Competitive Brawl"
  §Banned as a commander; Draftsim 2026-10-12): Oko, Thief of Crowns, Ragavan,
  Nimble Pilferer, Nadu, Winged Wisdom and Wrenn and Six are legal in the 99 but
  can't lead a deck; Yuriko, the Tiger's Shadow, Spider-Man 2099 and Light-Paws,
  Emperor's Voice joined them; Lutri is the only outright ban. The 2026-10-17
  AllPrintings encodes the category as `competitivebrawl: "restricted"` (the
  2026-10-14 bulk said `banned`). `Format.legality` therefore reads these as
  playable — right for the 99, wrong for `commander_eligibility` — and six tests
  that pin the old outright bans (`test_formats`, `test_legality_audit`,
  `test_price_check`) fail on a regenerated snapshot. Teach `formats.py`'s
  Competitive Brawl read that `restricted` means legal in the 99 and ineligible
  as commander (a new eligibility reason), re-pin the tests on Lutri for the
  outright ban and Oko for the commander ban, then regen the snapshot. The
  deck-wizard SKILL.md's "bans ten cards, as commander and in the 99" is stale
  the same way. Until then a bare `build-card-snapshot` run drags the drift in —
  the 2026-10-17 regen spliced only its two new cards.

- **Pass D: the serves still on a regex** (2026-10-23;
  `docs/plans/serve-idents-and-avenue-support.md` "Pass D"; each spec's comment
  names its remainder). Regex-only: `self_etb_payload` (a bounce-to-replay engine
  — Whitemane Lion, Kor Skyfisher — has no ident; a your-own subject on
  `bounce_tempo` would serve it), `permanent_etb` (its regex is every "when ~
  enters"; the ident union leaves about a thousand cards, mostly reanimation and
  land puts, a judgement call), `land_protection` (the shield subject alone is
  half the regex; Tomik's static is Unimplemented), `ability_strip_payoff` (the
  crippling-drawback text beside a power floor; no lane reads a drawback a strip
  turns off). Regex beside idents: `xspell_matters` (an "{X} in its cost" payoff
  has no ident; `mana_amplifier` covers the doublers), `team_buff` (the static
  team keyword grants the lane's subjects don't all reach), `target_redirect` /
  `spell_redirect` (redirect wordings beside the lane's ident). Lane
  follow-ups the pass found: a `(key, subject)` role table that
  `DOER_SUBJECTS`, `MEMBERSHIP_SUBJECTS`, the pair reads' wildcards and the presets
  all read (today each reads its own set); an `attack_trigger_side` crosswalk read
  beside `targeting_trigger_side` (the defensive-trigger veto lives in
  `tree_synthesis.combat`, and `stax_and_tempo`'s own `attacks` reads skip it —
  MacCready still reads as an attack payoff); the spell-additional-cost walk keeps
  only allowlisted OTHER leaves (PayLife, Blight) — walk them all;
  `mass_removal` misses one-sided "creatures your opponents control get -N/-N"
  (Massacre Wurm, about forty); `card_draw_engine` misses granted draw triggers
  (Avarice Amulet), aftermath halves and connive X; `opponent_draw_matters` misses
  enchanted-player watchers (Curse of Fool's Wisdom now carries no draw key);
  `ends_the_game` reads a missing player as you (a canary arm in `core_makers`);
  the empower Jace token's scry / surveil (about thirty cards) is not walked; a
  clone that adds a keyword (Auton Soldier) and Mouth // Feed's aftermath count
  are missed; Smothering Tithe and Pyxis of Pandemonium sit in no stax /
  opponent-graveyard lane; `big_hand_matters`' text arm still fires on "reveal
  any number of X cards"; Dan Lewis's AddSubtype Equipment and Equipment
  affinity. Left from the lane pass:
  the resource-maker lanes still count a token another player creates as yours
  (An Offer You Can't Refuse, Overencumbered); every artifact emits a membership
  `artifacts_matter|you|`, so Sol Ring lands on the Artifacts payoff page;
  `etb_value_x_recast_commander` (`pair_reads.py`) weights a scry-1 ETB like
  Shriekmaw now that `self_etb_payload` reads 4,333 cards; the `card-draw` preset
  is key-level, so Master of the Feast (opponents draw) stays in it. Phase gaps
  to report upstream (Dan posts) — from Pass D: Frodo, Sauron's Bane's granted
  trigger; Angel of Destiny and Nicol Bolas, Dragon-God's LoseTheGame player;
  Teferi, Temporal Pilgrim and Devastating Mastery's chooser stamped You; The
  Fall of Kroog and Radiating Lightning's "that player controls" stamped You;
  Canopy Cover's opponent-only hexproof as SelfRef; Phyrexian Unlife and the
  zero-life cards as unconditional CantLoseTheGame; seek has no player and nine
  seeks drop; printed firebending has no trigger; double team as CopyTokenOf;
  conjure-of-choice as DraftFromSpellbook; Ojutai Exemplars' "Return it" as
  TriggeringSource (a canary); Fatespinner's skip (a canary); Leonin Arbiter,
  Shadow of Doubt, Pale Moon, Cephalid Shrine, Hallowed Moonlight, Mistcaller,
  Juxtapose, Cultural Exchange, Legerdemain, Teferi's Time Twist, Desolation,
  Cleanse, Crusade, Artificial Evolution, Tomik; Champion of Stray Souls'
  graveyard zone; Sinister Gnarlbark's blight; Become Brutes' Role; Gemcutter
  Buccaneer's Equipment subtype; Krydle's mill; One Ring to Rule Them All's mill
  reach; where-X scry / surveil (Desmond Miles). Earlier: council's dilemma /
  secret council votes parked as residues (a canary), Brago's Representative, Overlord of the Hauntwoods'
  token, Narset Transcendent's rebound, Ral Izzet Viceroy's emblem, a block
  trigger's "it" as ParentTarget, Go Blank's graveyard owner, Estrid's
  Invocation's copy, Mortarion, fourteen damage clauses left Unimplemented
  (Power Surge, Urborg Stalker …), Curse of the Pierced Heart's controller,
  Masako, Lander / Map token abilities, Collision Course's AnyOf, the optional
  wheel's draw scope (Snort — a canary), Can't Stay Away, Vigor Mortis, Custodi
  Soulcaller, Lich-Knights' Conquest, Balthor, Omen Machine, Blightwing Bandit,
  Abduction's ChangeController, "as though it had flash" dropped (Rootwater
  Shaman, Arlinn), Radagast, Aluren, Jin Sakai, Nether Void's unless-pay, Mana
  Breach's controller, Dimir Keyrune, Hive of the Eye Tyrant, Corpse Cobble,
  snow landwalk, Vectis Gloves, Quicksilver Fountain, Sideswipe. Our own
  projection drops Splice's subtype from `card_keyword_types`.
- **Every held serve spec is converted (2026-10-19); what the lanes still
  miss** (the per-spec censuses are in `docs/plans/serve-idents-and-avenue-support.md`
  §2; the 41 holds of the serve-ident pass and the six of the fourth pass are
  all `serve_idents` now, each with its remainder classified). Phase gaps,
  each bridged 2026-10-19 by the supplemental parser with a `retirement_canary`
  or a self-retiring ledger row (tests/mtg-utils/test_phase_gaps_*.py; report
  upstream all the same, Dan posts): where-X keyword heads (Mask of the
  Schemer's connive X, Thromok's devour X, Fall of Cair Andros's amass X,
  Officious Interrogation's investigate X — the `_where_x_head` recovery,
  scoped to connive / amass / investigate; opening it to every allowlisted verb
  would recover ~40 more where-X clauses across many lanes, a separate
  measured promotion); energy residues (`gain_energy` / `energy_payment`
  tokens: Overclocked Electromancer, Robobrain War Mind, The Motherlode,
  Reiterating Bolt, Salvation Colossus, Izzet Generatorium's condition);
  foretell residues (Ethereal Valkyrie, Karfell Harbinger, Ranar); Osteomancer
  Adept's forage cost (a ledger row); Jetmir's Fixer (a lane arm over the
  recovered counter); the nine "all damage dealt to X is dealt to Y instead"
  replacements (`damage_redirect` token, Treacherous Link and Megatron kept
  out as opponent-side); Prairie Dog and Zabaz (`counter_bonus` token);
  Death's Approach and kin (`debuff` static token — the Sewer Plague ledger row
  retired by it); Attempted Murder; Ian the Reckless and Volcano Hellion ("to
  you and …" burn); Stunning Shot and three more fresh tap targets; ledger rows
  for Cragganwick Cremator / Flames of the Blood Hand / Kaboom! / Unstable
  Footing (a dropped planeswalker target), Insult // Injury, Tetsuo, Mob
  Verdict / Chandra's Flame Wave / Path of Mettle (the creature half), Decimator
  Beetle / Zealous Persecution / Foul Renewal (a dropped shrink), Heir of the
  Ancient Fang / Lethal Exploit / Lethal Throwdown / Lion Umbra (modified),
  Elspeth Resplendent / Undercover Operative (shield counters), Nicanzil,
  Dream Devourer, The Fourth Doctor, You Find a Cursed Idol (Unknown or
  dropped trigger modes); field corrections for the `SelfRef` untap locks
  (Mesmerizing Benthid, Scion of Stygia, Wall of Stolen Identity, Tsabo's Web,
  Code of Constraint), the anaphoric "it gets -N/-0" pumps (the two Jaces,
  Tamiyo, Blood Lust, Six-Sided Die), "that player controls" taps (Delirium,
  Yosei, Mana Web — and 22 self-tap cards such as Jaddi Lifestrider left
  `tapper_engine`), the Hidden / Opal / Veiled / Lurking self-animation cycle,
  Alacrian Armory and Animate Artifact, Athreos's exile, the graveyard owner
  (Skullsnatcher, Zombie Cannibal, Grime Gorger — opponents; Savior of
  Ollenbock — any), `CounterPlayerAddedAll`'s energy kind, Venser's Diffusion;
  the eight protective superfriends cards (a parked-recipient check); and the
  repo-side reads: granted afterlife / mobilize token makers, Worldwalker
  Helm's replacement Map, Dodecapod's enters-with counters, Hamza / Starport
  Security's countered-creature cost reductions, Brimaz's Phyrexian death,
  `walk_effect_chain` descending a coin flip's WIN branch only (+23 idents;
  the lose branch — Volatile Rig's sweep — is deliberately not walked, since
  both branches would serve drawbacks: Scoria Wurm's self-bounce). Still open,
  nothing to read: Commence the Endgame (the amass is folded into the Draw
  node's description with no residue; the keyword-array fallback serves it),
  Izzet Generatorium's energy replacement (a payoff on makers, left), Aether
  Refinery's doubler typed as a CreateToken replacement (no consumer reads it
  wrong), Rain of Riches (already served), the aftermath faces Rags // Riches,
  Reduce // Rubble, Indulge // Excess (phase emits no record for the second
  face — a canary waits on it), Pradesh Gypsies (no record at all), Tomik's
  "affinity for planeswalkers" (the keyword's parameter is not exposed), the
  Attraction Unknown modes (already served by the sweep row); Orcish Captain's
  "it gets -0/-2" (an anaphoric "it" inside an ACTIVATED ability's coin-flip
  branch, stamped `SelfRef`; the `anaphoric_pump` arm covers delayed triggers
  and a spell's own chain, not activated abilities, since a Dragonrage-type
  grant really does mean the card) fires `self_pump|you|`; Desperate Gambit's "choose a source you control" loses
  "you control" (the chooser is `TargetOnly{target: Any}`), so its losing
  branch's prevention reads as `damage_prevention` — a dropped-controller
  misstamp, and once a field correction restores it `is_own_drawback` needs a
  `PreventDamage`-on-your-source arm.
  Lane gaps still open: `creature_recursion` has no destination subject (62
  reanimation spells sit outside damage_for_each; creature_etb carries a
  reanimation extra instead); `cost_reduction` has no spell-type subject (21
  creature-spell reducers); the edict lane misses Incriminate, Malik,
  Gluttonous Hellkite, Killing Wave, Tragic Arrogance and granted edicts;
  keyword token-copy makers
  (embalm, eternalize, myriad, squad, encore) are not read; granted flanking;
  back-reference counter targets scoped you (Retribution, Obelisk Spider);
  partial prevention, granted absorb, Blinding Powder, Torrent of Lava
  (`damage_prevention`); `discard_outlet`
  misses "cast from your graveyard by discarding" (Alien Symbiosis, Demonic
  Embrace, Rona); the lifegain pair lost its 96 Food makers — `lifegain_makers`
  does not read the gain inside a Food token (Bake into a Pie, Bill the Pony);
  "whenever you proliferate" payoffs and granted / X proliferate have no ident
  (Scheming Aspirant, Venser, Tam, Ichormoon Gauntlet); the own-graveyard
  remainder (collect-evidence and forage costs, descend payoffs, the Empower
  Jace token's surveil, granted delve / soulshift X, a craft cost). Lane false
  positives still open: a token another player
  creates serves as a `token_maker|you|*` (Varchild, Goblin Spymaster,
  Skyclave Apparition, Genesis Chamber, March of Souls …); "tap creatures you
  control" cards serve `tapper_engine` (Jaddi Lifestrider — inseparable from
  the `controller: You` misstamp above); ~9 "when an opponent causes you to
  discard this" cards fire `discard_matters` and Balance / Restore Balance
  `discard_outlet`; Oft-Nabbed Goat and Sentinel of Lost Lore fire
  `gain_control`; An Offer You Can't Refuse fires `treasure_makers|you`;
  Investigator's Journal still fires `proliferate_matters` and
  The Book of Exalted Deeds `stax_taxes|opponents`.
  Ranking: `ranking._synergy_score` gives clause clusters only to regex-matched
  hits, so every regex → ident conversion thins clause breadth (Empty the
  Warrens' token clause 8 → 6 lanes); attributing an ident hit to the clause
  its signal came from belongs in the ranking module.

**From the Omnath Competitive Brawl build (2026-10-04)**

- **Phase gaps behind the closer, alternative-cost and mass-land-denial reads**
  (found moving `_tuner/` and `deck_stats` onto the trees, phase v0.94.0; report
  upstream, Dan posts). Each is a card the old regexes read and the trees don't:
  - Reach: `unparsed_quantity` residues park "loses life / deals damage equal to …"
    (Within Range, Soulblast, Final Punishment, Mjölnir; ~28 such residues name
    damage or life loss). Underbridge Warlock's boon reads as a self loss. (The
    `where_x_binding` X effects — Insatiable Hemophage, Zenith Flare — are read by
    `reads.unbound_x_reach`, canary `test_unbound_x_reach_canary`.)
  - Game wins: Frodo, Sauron's Bane's Rogue clause is dropped (its second ability
    parses as the Ring tempting you); Celestial Convergence's win is an
    `unbound_subject` residue.
  - Alternative costs, each corrected where the tree is built with a canary: keyword
    lines with a non-mana cost parked as residues (morph "Reveal a blue card", warp
    / madness with life, Escape Velocity's escape; blitz parses since v0.104.0 —
    `core._dropped_keyword_costs`, `test_dropped_keyword_costs_canary`); suspend X
    read as count 0 and Warbringer's / Catalyst Stone's cost changers read as empty
    keywords (`core._misread_keyword`, `test_misread_keyword_canary`).
  - Mass land denial, each with a canary or a ledger row: Eye of Singularity and
    Herald of Vengeance lose their narrowing clause and read as "all permanents"
    (vetoed by `reads.NARROWED_PERMANENT_SWEEPS`; End Hostilities is an
    `attached_to_qualifier` residue since v0.104.0); Exhaustion's and
    Mana Vapors' one-untap-step effect parses as a lasting static
    (`_lasting_static_defs`); Burning of Xinye's "destroys four lands" is a residue
    and Global Ruin's sacrifice a tracked set (both ledger bridges).
- **Phase gap behind the tuner's ramp sourcing** (found 2026-10-08, phase v0.94.0;
  report upstream, Dan posts). Boxing Ring's "Activate only if you control a
  creature that fought this turn" is an `unparsed_condition` residue, not an
  activation restriction — the only legal card whose mana or Treasure ability is
  gated that way (`reads.UNPARSED_ACTIVATION_GATE`,
  `test_boxing_ring_gate_is_still_a_residue_canary`).
- **Phase misparses behind cut-check reads** (found 2026-10-08; report upstream,
  Dan posts). Each has a canary: Glorfindel, Dauntless Rescuer's "can't be blocked
  by more than one creature each combat" parses as `CantBeBlockedBy` a typeless
  filter (`test_glorfindel_blocking_limit_misparse_canary`); Wyll's Reversal loses
  "with one or more targets", so it reads as a commander-spell copy
  (`test_wylls_reversal_target_constraint_canary`); aftermath halves (Dusk // Dawn),
  Garza's Assassin's recover, Salvation Colossus's unearth and Oscorp Industries'
  mayhem are dropped, so the `self-recurring` preset and the "Self-recurring
  fodder" serve read them by keyword (`theme_presets.SELF_RECURRING_KEYWORD_GAPS`,
  `test_self_recurring_keyword_gap_canary`); Nether Shadow's graveyard return is an
  `unparsed_condition` residue since v0.104.0 (ledger row
  `nether_shadow_graveyard_return_parked`); Bumi's Feast
  Lecture's earthbend return binds to the Food token (`LastCreated`) instead of the
  land (`test_earthbend_last_created_binding_canary`).
- **Phase misparses behind the "Self-recurring fodder" serve** (found 2026-10-09,
  phase v0.104.0; report upstream, Dan posts). The serve reads the card's graveyard
  return routes (`card_advantage.comes_back_from_graveyard`); three legal creatures
  the old regex served stay out because
  phase loses "this card": Sproutback Trudge's and Syrix, Carrier of the Flame's "you
  may cast this card from your graveyard" is a `CastFromZone` with target `Any` in a
  battlefield-zone trigger; Worldheart Phoenix's (and Raffine's Guidance's)
  graveyard alternative cost is a `CastWithAlternativeCost` static whose `affected`
  is your typed permanents, active on the battlefield. Read with a canary: "you may
  cast it from your graveyard" (Skyclave Shade, Hildibrand Manderville, Mosswood
  Dreadknight, Ichor Aberration) is a `PlayFromExile` permission on an empty
  `TrackedSet` (`test_unbound_graveyard_cast_misparse_canary`); Forgeborn Phoenix's
  granted "return this card from your graveyard to battlefield" parses as a
  `Bounce` to hand (`test_perpetual_bounce_misparse_canary`).

**From the twohg-guide skill (2026-09-27)**

- **Phase drops the player behind edicts** (found 2026-10-09, phase v0.104.0;
  report upstream, Dan posts). Each is read with a workaround that retires itself:
  a chained "…, then sacrifices" loses its subject (Undercity Plague, Priest of
  Forgotten Gods, Din of the Fireherd's land half, Nicol Bolas, Planeswalker's −9),
  and Davriel, Soul Broker's +1 hangs "they sacrifice an attacking creature" beside
  its delayed trigger, not in it (`test_chained_sacrifice_actor_dropped_canary`);
  "each opponent [who …] sacrifices" parses with no player at all (Papalymo
  Totolymo, Variable Solutions — ledger row `opponent_sacrifice_actor_dropped`).
- **phase tags "each other player" as `Opponent`.** Grave Pact and Syphon Mind carry
  `player_scope: Opponent`, which only differs from "each opponent" in team formats
  (it includes your teammate). phase doesn't support team formats yet, so this isn't
  reported upstream for now. `twohg_scan` vetoes it with an oracle-text check guarded by
  a `retirement_canary` test; delete the veto when the canary fails.
- **`twohg-scan --shadow`.** Listing IR-vs-text disagreements (information only, never
  merged) would calibrate the text fallback and surface phase misparses. Deferred until
  a set arrives that phase hasn't parsed. Baseline from FRA with the IR stripped: the
  text path misses Tomik, Izzet Sparkmage (a damage *replacement*, not an "each
  opponent" clause), reads Cruel Calculations as target-player (phase drops its player
  target), and differs on removal reach for about 18 cards.

**From walking phase's branch shapes (2026-10-09)**

- **Phase misparses behind the branch-misread registry** (`_card_ir.branches.
  BRANCH_MISREADS`, each row with its `retirement_canary`; report upstream, Dan
  posts). Fraying Line's "that player may pay {2}" is a `PayCost` with `payer:
  Controller`, so its "Otherwise" branch reads as yours (pruned from the certain
  records: LOW); Osseous Sticktwister's "each opponent who didn't sacrifice … or
  discard a card this way" parses as a second choice with a discard branch; Spitting
  Slug's "each creature blocking or blocked by this creature" loses its narrowing
  (both dropped from every tree). Also unreported, no workaround: Worms of the
  Earth's "any player may" choice is `chooser: Controller` (read off the wrapper's
  `optional_for`), and Ensnared by the Mara's villainous branch carries
  `player_scope: All`, so its (LOW) impulse_top_play scopes "each".

**From the phase v0.104.0 bump (2026-10-09)**

- **Phase now fails closed on what it can't represent** (#9392 and kin), parking the
  whole effect as a residue named for its shape (`unparsed_condition` 63 → 216 at
  v0.104.0, `put_counter_tail`, `attached_to_qualifier`, `static_structure`,
  `unparsed_verb_arguments`, `perpetual_modify_pt`, `granter_reference_unreached`).
  Recovery reads the parked verbs (`recovery.ALLOWLIST`), each instruction of a
  compound clause and a granted body's residue (nine rows retired that way,
  2026-10-09); the remaining v0.104.0 ledger rows are parked conditions and verbs the
  grammar doesn't tag. Report upstream by residue class, not per card.
- **Lane-side reads of recovered clause text remain** beside the seam's marks:
  `damage_for_each`'s `_DFE_RECOVERED_RX`, `named_counter_misc`'s
  `_RECOVERED_POWER_TAP_RE`, `_recovered_power_damage`, `creatures_matter`'s
  `_RECOVERED_TEAM_COUNTER_RE` and `target_player_draws`'
  `_RECOVERED_DRAW_REPLACEMENT_RE` (a replacement diagnostic the seam could refuse).
  Move each onto a `read_clause` mark the same way draw, discard, damage reach and
  make_token's kinds moved (2026-10-09), population unchanged.

**From the 2026-09-17 architecture review (worth exploring, not started)**

- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Known lane recall gaps (surfaced by ADR-0051; a lane fix repairs every consumer)**

- Vibranium-mana token makers are suspected not to count as ramp, but no card was
  found to test.

**Discovery ranking:** see ADR-0043's terminal-state amendment for the unclaimed
headroom and parked items.

## Settled: don't re-suggest

- **A spell's casting-cost discard is a discard outlet** (Dan, 2026-10-10). The
  optional keyword costs count: escalate (Collective Brutality, CR 702.120a),
  buyback (Forbid, Demonic Collusion, CR 702.27a), flashback (Conflagrate, Twinned
  Vision, CR 702.34a), as Sabin's blitz does (CR 702.152a). Jump-start (CR
  702.133a) and retrace (CR 702.81a) count too; phase leaves their discard
  untyped, so `discard_outlet` reads them by keyword name behind a
  `retirement_canary`. A mandatory additional-cost discard counts as well
  (Tormenting Voice, Thrill of Possibility, CR 601.2f): you choose the card and
  when to cast. So does a discard that is one choice of an either/or cost (Bitter
  Triumph, Bone Shards, Lightning Axe: "discard a card or pay …"), since you may
  always choose it. `discard_outlet` reads each off the spell's merged `unit.costs`.
- **A random discard isn't a discard outlet, but it still makes discards** (Dan,
  2026-10-10). It can't be aimed (CR 701.9b; Flowstone Flood's buyback, Goblin
  Lore, Amok), so `discard_outlet` skips it in every arm, the kept text mirror
  included (`crosswalk.discard_is_random`). `discard_makers` (loot and rummage)
  keeps it, because a "whenever you discard" payoff (Drake Haven) fires whichever
  card goes (Burning Inquiry). A chosen opponent's discard is not yours either
  (Fervent Mastery, `lanes._shared._choose_opponent_bound_discard`).
- **Upkeep-payment discards aren't discard outlets** (Dan, 2026-10-09): echo's and
  cumulative upkeep's discard (Deepcavern Imp, Rakdos Headliner, Vexing Sphinx) is
  a forced payment to keep the permanent, not a discard you make on demand (CR
  702.30a, 702.24a); `core._UPKEEP_PAYMENT_KEYWORDS` reads only their life costs.

- **Two-arm lanes** (a structural arm OR a `synth_<key>` reference-arm concept, 91 of
  279 lanes): stable by design, not debt (ADR-0038 amendment). Don't tabulate or
  rename them.
- **Judged in good shape by the 2026-09-17 review:** `theme_presets` (a registry over
  signals; removal isn't duplicated), `cut_check`, proxy-printer's layout and Fetcher
  seam, `phase_bump`, `testkit`, `agent_bridge` / `events`, and the tuner's classify,
  shape and bracket modules.
- **Firebending isn't ramp** (Dan, 2026-10-09): not a creature with firebending
  (Uncle Iroh; `firebending_makers` is out of the ramp preset's keys), a maker of
  firebending tokens (Fire Nation Attacks, Firebender Ascension, Cruel
  Administrator, Fire Nation Occupation) nor a grant (Sozin's Comet, Fire Nation
  Turret, Fire Nation Cadets). The mana comes only as the creature attacks and lasts
  until end of combat (CR 702.189a), so it doesn't speed up the curve.
- **Symmetric shields aren't protection** (Dan, 2026-10-08): `roles.protects` is
  protecting YOUR board, so a permanent's shield over every player's objects alike
  (Crumbling Sanctuary, Plated Pegasus, Well-Laid Plans' residue) stays out; a fog
  you cast and an optional shield you aim stay in.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
