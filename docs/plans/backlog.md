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
  (d) **Type payoffs — don't re-suggest** (2026-10-25). A choice of types
  ("creature or artifact you control" — Abuelo, Heliod, Zimone), stax or edicts
  over other players' artifacts (Null Rod, Harsh Mentor, Pick Your Poison), a
  count another player wins (Ward of Bones' lock on each opponent with more
  artifacts than you, `crosswalk.counts_behind_another_player`) and a retype
  that also strips abilities (Sugar Coat, Kitesail Larcenist, Vraska,
  Betrayal's Sting, Soul Sculptor: removal) are no payoff. The type-grant read
  (`crosswalk.granted_card_types`) has no node for Xathrid Gorgon's dropped
  "becomes a colorless artifact" or the Alchemy perpetual grants (Hinterland
  Chef, Resourceful Collector, Woodland Investigation, Glimmer Hoarder,
  Housemeld); none is an artifacts or enchantments payoff a guide plays.
  (g) **The guide cuts the tuner protects** (2026-10-24, the experiment table in
  `docs/plans/precon-audit-2026-10-18.md`, "The remaining tuner levers"). Shipped:
  popular cards (inside `UPGRADE_RANK`, not premium) off every lane and on none of
  the deck's main avenues are the last upgrade tier (`focus.popular_upgrade_cards`,
  after the deep lane's half; the guides cut 0.28 of them, 27 of 96, when any viable
  avenue spared a card; beside the fringe tier they spent the lane's theme budget,
  51 adds). Since 2026-10-25 only a main shields an off-lane card from the upgrade
  tiers (a sub's or an emerging or folded theme's carer is a slot, and a popular
  card on a sub alone; the audit's "The cut pool"); keeping a folded theme's
  carers shielded lost five guide cuts. Since 2026-10-26 (the audit's "The open
  levers, closed") a main shields only its carers (a popular main feeder is the
  last slot), a solid Granter is a slot and may go to a better grant (ADR-0040's
  amendment). Left: 23 popular cuts, all premium (the guides cut 0.10 of premium
  cards, 22 of 210 — premium stays), and 45 commander-lane doers, whose guide-cut
  rate outside the lane's half is 0.08-0.20 in every carer split by role and
  play-rate holding more than four cards, below the decks' 0.24 — (a) holds,
  don't re-suggest a split of them without a new read; most sit in tunes that
  reach the thirty swaps. Combo protection stays whole: only a game-ending combo
  protecting its pieces lost an add, and `proposal-check` gates every infinite.
  Script: `docs/plans/precon-audit/cut_splits.py` (both splits; same ROOT as
  `misses.py`).
  (j) **Job-read verdicts — don't re-suggest without a new read** (ADR-0060 and
  its amendments; the experiment tables are the audit's "The tuner-policy
  leftovers" and "The deck-fit wipe read"). The order is the blend (wipes, draw,
  protection) or play-rate (removal, ramp), theme fit breaking a near tie for draw
  and ramp. The wipe read leading its upgrades was flat twice (547 / 195 / 60): it
  moves picks only in precons whose guides add no wipe. The deck-fit wipe read was
  built and measured 2026-10-25 (the share of the deck's own permanents a sweep
  leaves, off its filter: a chosen type, a power or mana-value bound, one each,
  one-sidedness, damage against toughness): the deck-free read already prices a
  spare and one-sidedness at the average deck's board, so on its own it moves no
  non-tribal deck, and leading the wipe order and fill with it in a tribal deck
  (most creatures share a type: Fae Dominion, Blood Rites, Sliver Swarm,
  VelociRampTor) took Raise the Palisade in Fae Dominion but cost three guide adds
  there on the budget (guide adds 18 → 16 over those four, cuts flat): rejected.
  Expel the Interlopers and Tragic Arrogance under Ellivere, and Chain Reaction
  and Winds of Abandon in Blame Game, need a slot the tune doesn't open (one wipe
  upgrade each, already Vanquish the Horde / Blasphemous Act, both guide adds);
  a lead for every deck trades those away. Rejected for removal: the deck's count
  of instant any-permanent answers deciding flexible vs targeted (59 and 56 adds;
  Beast Within's recurrence moved to Abrade). Rejected for ramp: the read blended
  into the order (56; Mana Vault took Fellwar Stone's 10). The removal read's weak
  agreement with play-rate over every card with a removal effect stands (it was
  fitted on main-job removal and only gates). Theme fit as a tie lost for removal,
  wipes and protection. Protection goes unsearched in 18 guide adds' decks because
  ADR-0024 asks for it only from a combo or control deck or a voltron plan; a
  target of 5 or 3 for every shape matched fewer adds. Left narrow, none a guide
  card: a size off a card the caster takes from a graveyard (Volcanic Vision, Too
  Greedily, Too Deep) or off a random discard (Kindle the Carnage). An on-theme
  draw or ramp card reading within a tie of its cut passing the play-rate gate
  gained none of its targets (Insidious Roots, Faerie Mastermind; 2026-10-26).
  Where the deck holds the most of a job it wants (a row at its max, protection
  at the Shape's target) the job's upgrade moves onto the theme (2026-10-26); a
  looser row read or cost bar spent the budget-bound decks' cuts.
  (k) **Age-adjusted play-rate — don't re-suggest** (2026-10-30; patch and runs in
  `~/mtg/tuner-work/w29/`). A card's rank as a percentile among cards first printed
  within ±6/12/24 months, the better of that and the raw rank, and a recent-only lag
  boost, each through the add order, fills, near-tie, play-rate gate, page sort or
  cut side: no variant raised guide adds on the 25 (best 108 against 109; the
  ordering variants lost 13-19, mostly old staples: Swiftfoot Boots, Counterspell,
  Nature's Lore). The "newer and less played" misses were mostly a dating error
  (MTGO's promo set dates every card 2002-06-24; The List and Secret Lair likewise);
  with reprint-aware dates a ±6-month cohort puts the guide card first in 5 of 151.
  Real rank lag is limited to 2025-26 cards, which mostly postdate the guides. A
  card's first printing is its earliest printing not flagged `reprint`
  (`precon-audit/scoreboard.py`).
  (s) **Deck fit for job upgrades — don't re-suggest** (2026-10-30; patch and runs
  in `~/mtg/tuner-work/w31/`, the audit's "Deck fit for the job upgrades"). Two
  levers, each measured alone, then together; none raised guide adds on the 25.
  (3a) a job upgrade never cuts a card serving the main theme or the commander (a
  main's member or carer, a commander-lane doer, or a card sharing a non-generic
  ident with the commander): 611 / 281 / 97, every split of the set lost (shared
  ident only 672 / 314 / 103, carers and lane doers 684 / 317 / 101, main members
  634 / 292 / 98), because the guides cut those cards at 0.39 (57 of the 146
  protected job-upgrade cuts), above the decks' 0.24. Only two of the five
  motivating trades are theme cards by focus's sets (Vona, Chittering Witch);
  Stalking Leonin, Siege-Gang Lieutenant and Will of the Abzan share no
  non-generic ident with their commander and serve no main. (3b) a job's
  candidates (upgrade, Spine fill) that share a non-generic ident with the
  commander or a main's serve rank first, play-rate or the blend within each
  group: 710 / 324 / 91; per job removal 104, wipes 108, draw 107, ramp 104,
  protection 107 adds (109 base). Unlike (j)'s theme tie (fit breaks a 0.1
  job-read tie over the viable avenues) it reorders the whole match set, and the
  fit read is too loose: `attack_matters`, `combat_damage_to_opp` and
  `target_player_draws` tie Myr Battlesphere, Sword of Fire and Ice and
  Kozilek's Command to Nelly Borca, and the guides add the staples it pushes out
  (Swords and Path in Blame Game, Counterspell, Swiftfoot Boots, Heroic
  Intervention). A 5% pool-share cap on the shared idents (102) or fit only
  within tenfold of the top card's play-rate (102) lost too. The guides' deck-fit
  removal (Wall of Souls, Soul Shatter, Grasp of Fate) is played less than its
  cuts, so no order reaches it. Found on the way, not fixed: Noxious Gearhulk
  emits `toughness_combat|you|` (its life gain is the destroyed creature's
  toughness, per its ruling) and Myr Battlesphere reads as interaction (it hits
  only the player or planeswalker it attacks, by its own text).
  (t) **Card reads leading the theme adds — don't re-suggest** (2026-10-30;
  patch and runs in `~/mtg/tuner-work/w33/`, the audit's "Card reads leading the
  theme adds"). Measured against 715 / 329 / 114 (held-out 297 / 139 / 35, Jace
  29 / 14 / 3). Order A (fit to the commander, a non-generic ident shared with
  it; then `rank_candidates`' synergy; then play-rate) over the whole match set:
  723 / 331 / 82, held-out 30 adds, 2.3× the tune time. Order B (commander fit,
  then how many deck cards emit one of the candidate's non-generic idents, then
  play-rate) over the whole match set: 740 / 335 / 80, held-out 30. Each reaches
  about 22 unpopular guide adds (Gix, Krydle, Djeru, Teferi, Temporal Pilgrim,
  Conduit of Ruin) and loses about 55 popular ones. The 150-card page, the
  synergy rounded to whole points, a log-depth, a 5% pool-share cap and tiered
  forms (fit, then the 0.2 fit floor; fit, then 15+ deck sharers) scored 87-111.
  Blends in log10 play-rate (fit worth 0.1-0.5 decades, a depth doubling up to
  0.2, synergy share 0.47, weights from a logistic fit) scored 109-116 adds. The
  best, fit worth 0.25 decades, scored 725 / 332 / 116 with held-out 38, but Jace
  fell to 1 add (it lost Archfiend of Depravity and Nezahal). No variant passed
  all three bars. Inside a play-rate band, fit (2-3×) and 31+ deck sharers (2-5×)
  do raise the guide-add rate on the whole match sets, but play-rate separates
  more: rank ≤ 1000 runs 5.4% against 0.07% past 15,000. Found on the way, not
  shipped: dropping the theme page's 0.2 synergy fit floor, with play-rate alone
  and no read, scored 720 / 331 / 118, held-out 290 / 139 / 36, Jace 29 / 14 / 3.
  It reads less of the card, which is the opposite of the plan's direction.
  (m) **Recall** (`precon-audit/misses.py`, at the largest guide's thirty
  swaps and each precon's own guides' budget, `budgets.json`, Spellbook cached):
  332 of 505 cuttable guide cuts, 114 of 793 in-scope guide adds, 717 swaps;
  held-out 139 of 216 / 35 of 407, 297 swaps (2026-10-30, the phase v0.118.0 pin
  bump: Planeswalker Party one guide cut more, Sliver Swarm two more swaps and
  two guide cuts more; near-misses 70 / 29, consensus 39 / 121 and 6 / 37, Jace
  29 / 14 / 3, all as before. Before it 329 / 114, 715 swaps; held-out 139 /
  35, 297 swaps (2026-10-30, the signal-gap pass:
  Sundial of the Infinite in all four guide decks, Graveyard Overdrive's Six,
  Tarmogoyf and Terravore; Mardu Surge's Sundial spends the budget its last five
  upgrades had, one guide cut fewer; Jace unchanged. Before it 330 / 109, 721
  swaps; held-out 139 / 34). The scoreboard
  (`precon-audit/scoreboard.py`, the audit's "The scoreboard", 2026-10-30) adds
  two reported numbers, not gates: near-misses (a tuner add standing in for a
  missed guide add by job subtype or shared deck signal; 13 of 20 sampled pairs
  held up by the rules) 70 on the 25 (71 before the signal-gap pass), 29
  held-out, 2 on Jace; consensus guide cards (named by 2+ guides) matched, adds
  39 of 137 / cuts 121 of 169 on the 25 (122 before), 6 of 52 / 37 of 53
  held-out, Jace 0 of 2 / 7 of 10. (The baseline is
  from 2026-10-29, after the guide-row fix: 108 rows that joined cards with commas or misspelled them now name real
  cards, and the audit scripts no longer split "Dusk // Dawn" at its second
  slash; the larger add counts raise 14 precons' budgets. Before it, on the old
  rows: 271 of 408 cuttable guide cuts, 88 of 610 in-scope guide adds,
  713 swaps (2026-10-26, the audit's "The open levers, closed": solid
  Granters and a main's popular feeders are upgrade slots, a Spine fill takes a
  jobless slot before a lane slot, a full job's upgrade moves onto the theme;
  271 / 88, 713 swaps again, every swap of the 25 precons the same, once a
  lifelink body kept the voltron carrier, 2026-10-29: 66 cards gained it, none
  legendary — the held-out ten likewise, 139 / 34, 297 swaps, every swap the
  same; 256 / 76, 680 swaps before the open levers, unchanged by the
  fourth and fifth (o) passes; 252 / 75, 669 swaps before the third (o) pass;
  199 / 67, 562 swaps before the cut pool; 197 / 66, 560 swaps at the even share;
  195 / 59, 543 swaps before it; 180 / 57 before the near-tie budget rule, 169 / 56
  at 9e0026ed.) The levers by size now: adds a page held but outranked
  (235, from 251 by the full-job move; no read separates the rest), theme adds no search reaches (164, (r)), guide cuts in a cut pool
  the tune never reaches (50: seventeen tunes reach thirty swaps, six
  end on their budget, two on their cut pool — Blood Rites, its lane all Vampires,
  and Sliver Swarm), commander-lane cards the guides trim (45, (g)), premium cuts
  (23, (g)) and protected ones (13). 49 guide adds are gated as fewer
  played than their cut and 31 as a band higher: a theme upgrade of a
  main card letting a near tie in play-rate through when it fits better lost two
  adds, and a band more where the curve has room was flat (2026-10-26). Taking
  the popular tier before the lane's carers cut four more guide cards but lost two
  adds: the carers' slots bring the lane's theme adds. The outranked adds, by what beat
  them (`find_add` traced, 2026-10-25, before the even share): theme pages 122 (91
  behind a more-played pick, 17 ahead of it but passed over for a cheaper near
  tie, 8 on a page that picked nothing), removal 37, ramp 26, draw 21, protection
  16, wipes 6. No card read separates them from the picks: a commander pair read
  (ADR-0042's rows) fires on 8.0% of the theme pages' guide adds and 7.3% of the
  rest, a template role on 31% of the outranked guide adds and 28% of the theme
  picks; the top fifth of a page's synergy holds guide adds at twice the rate,
  which the synergy orderings below already lost on. Measured negative, so don't
  re-suggest without a new read: theme adds serving two viable avenues first (46
  adds), theme adds by a synergy / play-rate blend (53), and, against the even
  share's experiments (the audit's "The budget's even share"): a theme page's near
  tie to the better fit where the budget doesn't bind (58), the even share on the
  guarded Spine fills (one add fewer), and the cheapest card in the window, near
  tie or not, past the share (adds flat, one cut more); and, against the cut
  pool's: a lane feeder's theme upgrade to a less-played payoff of the main lane
  (one add fewer), an over-band trim's add shared over the mains (flat).
  Six guide summaries don't tag sources per row (`guide_sizes.py` skips them).
  (r) **Theme reach, what's left** (2026-10-25; the experiment table is in
  `docs/plans/precon-audit-2026-10-18.md`, "Theme reach"; unchanged by the
  2026-10-26 pass, which found no new read for it). 164 theme guide adds
  still have no search. Open:
  - the 150-card play-rate page (`swaps._PAGE`), which hid 71 main-avenue guide
    adds at a913f172 ("the most played that fits" never reaches them, nor did
    payoffs first; 67 serve the commander's main at the cut pool's tune). Blood
    Rites' Lich-Knights' Conquest is this lever: it carries
    `sacrifice_outlets|you|`, which the Aristocrats serve counts, but the page
    doesn't hold it; Pyre of Heroes, Altar of Dementia, Diabolic Intent,
    Razaketh and Dictate of Erebos are on it, outranked;
  - four guide adds serve only a sub (Living Energy's Arcum Dagsson, Clever
    Impersonator, Scrap Welder; Deep Clue Sea's Displaced Dinosaurs). Sharing the
    theme adds over the commander's held subs as well as the mains took Roaming
    Throne and Praetor's Grasp but lost eight guide adds elsewhere (2026-10-25,
    the audit's "The cut pool"), as every sub sharing did.
  The guide adds that serve only a lane that isn't viable — don't re-suggest
  without a new read (2026-10-25): of those no search reaches, 54 serve only a
  fed lane (Spellslinger, Artifacts, Cost reduction: incidental keys, mostly
  staples and protection) and 4 an emerging one; 14 more on an emerging lane are
  outranked. The guides cut the carers of an emerging or folded theme (22 of 52
  past `UPGRADE_RANK`) more than they commit to one, so "commit more" is no
  lever; the tune now trades those carers as upgrade slots.
  An Aura deck's gear apart from Equipment (Ellivere counts enchanted creatures;
  an Aura makes one, CR 303.4b; Equipment an "equipped" one, 301.5a) was
  simulated before building the read: Auras only on Virtue and Valor's suit-up
  page took Sram and lost Swiftfoot Boots and Lightning Greaves, the guide adds
  that page makes (one add fewer) — don't build it without a new read.
  Measured deltas: a granted "When this creature dies, <payoff>" read as
  `death_matters|you` alone moved no swap (543 / 195 / 60); a held lane as deep
  as a main never folding into a held tribe added Blood Rites' Skullclamp (544 /
  196 / 62; 542 / 195 / 61 after the near-miss piece fix); Ancestral Mask's count
  of every player's enchantments read as an enchantments carer keeps it in Virtue
  and Valor, and its slot moves Sram and All That Glitters off the adds (543 /
  196 / 59). Measured negative, so don't re-suggest without a new read: payoffs
  first (47 guide adds over the serve's whole match set, 44 over the 150-card
  page, against 50: the payoffs cost more and spend small budgets); the whole
  match set as the theme page (no gain, twice the tune time); support at one in
  three or more (generic tribal support takes the members' budget); slots shared
  over every viable avenue (35) or by carers (45), because the generic subs'
  pages hold staples (Murder for Fae Dominion's Spellslinger); one swap off the
  serve page for each lane below the viable floor that the commander holds and
  cares about (58 adds; 60 held to the emerging floor, flat); a sub with a
  main's carers taking one add that also serves a main (57 adds, 2 guide cuts
  fewer).
  (n) **Lane follow-up verdicts — don't re-suggest without a card** (2026-10-24:
  a targeted Treasure conversion is no `ramp` — Vraska, Betrayal's Sting's −2,
  Kitesail Larcenist answer the target, whose controller keeps it, CR 110.2 /
  602.2). Checked and empty on the 2026-10-23 corpus: a card with both a creature-type and a card-type Choose firing
  `chosen_type_matters` (none), and a discard or leaves-the-battlefield
  trigger's self-return firing `bounce_tempo` (none; the other trigger
  back-references on cards that fire return an event object — a blocked
  creature, a damage source, a land tapped for mana).
  (o) **Theme matching off the IR, what's left** (2026-10-25, after the third
  pass: the tribe spec and its payoff sub-avenue page off the IR too; the
  fourth and fifth (2026-10-26) took the pattern off every keyword tribe —
  ``text_reads._ABILITY_KEYWORDS``, first and double strike now among them; the
  class of every card the tribe pages lost is in
  ``~/mtg/tuner-work/w16/classification-tribes.tsv``, the keyword pages' in
  ``~/mtg/tuner-work/w18/classification-keywords.tsv`` (flying … hexproof, 445
  cards) and ``~/mtg/tuner-work/w19/classification-keywords2.tsv`` (the rest,
  281 cards), the second pass's in ``~/mtg/tuner-work/w13/classification-final.tsv``).
  A theme pages by its serve (``signal_specs.theme_page``); no search carries an
  oracle pattern (``test_a_theme_pages_by_its_serve_not_a_pattern``). Open:
  - the commander-damage fallback's silencing took the carrier from Jodah's
    Avenger (its restored shadow: ``evasion_self|you|shadow``) and Urza's
    Avenger (``has_banding``), though the floor's own comment says an evasion
    tell must not silence it — ``evasion_self`` is missing from
    ``_VOLTRON_HAS_OTHER_PLAN_COMPAT`` (a lifelink body's own lifegain no longer
    silences it, Dan's call 2026-10-29: Noble Banneret and Vampire Nighthawk
    are lifegain plans and carriers both — ``membership_floor``'s
    ``own_lifelink``);
  - the tribe pages were checked on Goblin, Elf, Zombie, Dragon and Sliver
    (and Angel, Vampire, Merfolk, Wizard, Human): every real member they
    lost has an IR ident or a ledger row (the 21 ``_reference_row`` rows). The
    other tribes weren't, and phase drops ran 0–3 members a tribe;
  - ``type_matters``' token-profile join gains Eye and Hand of Vecna on the
    Zombie page (their Vecna is a Zombie God), no member.
  The page-only keys (``signal_keys.PAGE_ONLY_KEYS``: ``subtype_ref``,
  ``keyword_bodies`` and ``land_return_untap``, the Forest-bounce untap engines
  split off ``permanent_etb``) feed a theme's page and open no avenue or plan
  (``signal_keys.is_page_only``).
  A card phase has no record for carries no ident at all, so it drops off a
  pattern-free page: of the permanents-entering makers, Oko, Lord of the Fae;
  Flourishing Forces; Enter the Eternities; Quintorius, Fate Splitter; Potential
  Horizon; Searing Soloist; Plunderer's Prize; of the token makers and counter
  placers, the same Oko, Flourishing Forces and Quintorius; Rootha, Ardent
  Artisan (sacrifice outlets); Change the Narrative (cost reducers); Nylea's
  Oracle (go-wide anthems); Avoided Stairwurm (Enlist fodder, Ability-strip
  targets). The ledger rows that gate on a node's absence (Estrid's
  Invocation, both rows; Venture Forth; Hide in Plain Sight; the
  typeless reanimations; the dropped return costs; Catastrophe's creature
  branch; the where-X player burns; Commence the Endgame's amass; Widespread
  Brutality's Army bite; Jin Sakai's modes) retire only through
  ``test_bridge_ledger``'s "already served" guard, not their own gap.
  Rules that stand: serves were written to credit a deck's own cards, so each
  OR arm admits a card on its own; ``tests/deck-forge/test_serve_arm_guards.py``
  pins each structured arm on a page serve to a real card and a near miss, and a
  new arm needs a row. An IR hit whose emitting unit decides no role
  (``ranking._unit_role``) is read by lining the unit's text up with an oracle
  clause, then that clause with a compat ability (``ranking._hit_clauses``):
  reading the payoff test off the unit itself would drop both text alignments,
  and would give a role to the hits no single ability emits (a keyword's
  lifelink, Crucible of Worlds' whole-card ident, a modal spell's text-less
  mode), which still score structural.
  What the keyword pages dropped (2026-10-26, each class rules-checked): a card
  naming the keyword to fight it (a removal or block rider, "without", "loses",
  flying's reminder "except by creatures with flying or reach" on the reach page,
  CR 702.9b); "as though it had flash" or "… didn't have defender" adds no
  ability (CR 113.10: an added ability "gains" or "has" it — 74 flash enablers),
  though a static letting other creatures attack as though they didn't have
  defender is a defender payoff (``crosswalk.lets_defenders_attack``, CR
  702.3b — High Alert; a creature letting only itself attack, Backstreet
  Bruiser, is not); shroud or hexproof on a player (CR 702.18a / 702.11c); a
  grant of defender onto another creature, yours or not (Guard Duty, Stasis
  Field; Peregrine Mask, Dormant Sliver) is the drawback ``_DRAWBACK_GRANT_KW``
  names, where a body with defender the card is or makes counts
  (``crosswalk.made_keyword_bodies``: a Wall token, Primal Clay, Guardian
  Zendikon's land); a Vibranium token is a noncreature artifact (no body); a
  keyword-variety payoff (Akroma, Vision of Ixidor; Odric, Blood-Cursed) or a
  keyword-sorting dig (Selective Adaptation) is no one keyword's; a card or
  ability name (Fear Ray, Shadow the Hedgehog, Undying Flames). A keyword tutor
  of your own library pages its keyword (Mystical Teachings, Isperia,
  Mwonvuli Beast Tracker). A token any player may create is no body the card
  makes for you (Basalt Golem's Wall is the blocker's controller's, CR 111.2).
  Don't re-suggest: an enters drawback (Phage, the sacrifice-unless lands), an
  Equipment's auto-attach, a token or search another player gets (the Hunted
  cycle, gift, Path to Exile) and a card putting only itself are no
  permanents-entering member; the Emergence Auras' "that land gains
  indestructible" replacement (CR 614.1a) guards only the land they animate,
  the animator's own payoff like Kamahl's Will, not land protection; an
  untargeted edict ("each opponent sacrifices" — Liliana's Triumph, Grave Pact)
  commits no crime (CR 700.13: a crime targets); a land-creature anthem or
  token maker (Sylvan Advocate, Jyoti) and a land already a creature (Dryad
  Arbor) animate no land, so the land-animation preset leaves them out (13
  cards); a coin-flip-gated self-exile-and-return (Frenetic Sliver) is a blink
  though the effect walk drops it as the card's own drawback, but one returning
  the card transformed (Ral, Monsoon Mage) is the transform vehicle. What the
  second pass dropped from the pages, each class adjudicated: an upkeep "sacrifice
  it unless you pay" is the card's restriction (``self_drawback|you|restriction``),
  not harm a donate deck hands over (76 cards), and a pact, an extra-turn spell
  or another instant or sorcery is no permanent to donate; a self-mill on a card
  that reads its graveyard is fuel (Splinterfright, Sidisi), not harm; a payoff
  for damage dealt to you, a Phyrexian Arena's paid draw and a curse on another
  permanent are no drawback; a creature that untaps only itself, a
  {Q} cost, a threaten's untap and a "doesn't untap" static are no untap effect
  (294 cards); a debuff Aura ("enchanted creature gets -N/-N") is removal, and
  an Equipment payoff or equip-cost reducer is ``voltron_matters``' page, not
  gear; a creature giving itself double strike, and "that much damage" counting
  something other than damage dealt, amplify nothing; a symmetric draw, token,
  tutor or Food is no symmetric mana; a sacrifice-cost drain (Anje, Glass-Cast
  Heart) is the aristocrats outlet, not a token-leaves drain, and a drain on the
  token a card makes is that token's; a curse watching its enchanted player's
  creatures enter punishes them, not a creature-ETB payoff of yours. What the
  third pass dropped from the tribe pages (``/rules-lawyer``, 2026-10-25): a
  protection from the tribe guards its holder (CR 702.16b/e); a targeted
  removal (CR 115.1) that can't hit the tribe spares no board (Victim of
  Night), while an untargeted mass effect (CR 115.10) or an every-player edict
  that leaves the tribe out rewards a board of it — the lane's call (Eyeblight
  Massacre, Kindred Dominance, Call to the Grave) — and pages on both the
  tribe and its payoffs; a Siege's
  "Dragons" is an anchor word with no tie to the type (its ruling, CR 607.2m);
  a party counts one Wizard (CR 700.8); a four-material craft (Throne of the
  Grim Captain, CR 702.167a), a named card (conjured, tutored) and an
  opponent's tokens of the tribe are no tribe's; a token maker of the tribe
  is its main page's, not a payoff. Merging ``creature_etb|you|punish`` into
  ``typed_enters_punish`` doesn't hold: 17 cards carry both, but each keeps
  cards the other rightly lacks (a landfall or artifact-entering burn there; a
  drain or a creature-entering burn here), and the ETB-payoff page reads both.
  (l) **Tune speed, what's left** (2026-10-26, after the third speed pass: a
  warm Blood Rites / Eldrazi Unbound / Sliver Swarm `deck-tune` 2.3-2.6 /
  2.5-2.9 / 3.1-3.5 → 1.7-2.0 / 2.0 / 2.1 s; the 25 precons' warm tunes, each a
  fresh process, 2.04 / 2.49 → 1.66 / 2.02 s median / max; the precon audit 23 s
  warm, 1.25 GB peak, its output identical). Open: the CLI is now Spellbook's:
  it asks at 0.4 s (after the deck's names: `acquire_for_cli` loads the pool
  index, 0.3 s) and the answer lands at 1.1-1.7 s, while the deck reads are done
  by 1.0 s — what's left behind the answer is the swap phase (0.5 s), whose page
  scans read every card of the gated slice once a page (~32k cards x 16 pages
  for a five-colour deck: 0.5 s; Blood Rites 0.2 s), each through one shared
  `CardView`; the per-card cost left is Python's (`_matches_card`, then
  `Serve.matches`' arms). Measured verdicts, don't re-suggest: **a Spellbook
  cache** — a cached answer can't equal a live one: 25 of 25 precon answers
  changed `popularity` / `prices` within 40 h (popularity orders the near-misses
  and is in the output), `find-my-combos` sends no ETag or version, and the bulk
  export's ETag dates the export, not the live database; so the CLI asks before
  it loads anything else (`deck_tune`), which took the wait off the warm CLI.
  **`is_wincon_card`'s trees** — 2-16 ms a warm tune, no builds (the trees store
  serves them). **The mirror classes** (0.28 s) — `mirror/__init__` no longer
  re-exports the loader, so nothing imports them before the first tree is built
  or unpickled: a CLI pays them inside Spellbook's wait, a tune still pays them;
  only a codegen emitting plain classes would cut them, and `dataclasses.fields`
  / `replace` read the nodes. **The crosswalk JSON** — read through a span index
  (`<sidecar>.spans.pkl`), 0.12 → 0.02 s. **The import-closure walks** used
  `find_spec`, which imported every parent (0.45 s, the mirror among them); they
  resolve names off `sys.modules` and the path finder now, once a process. **The
  two-face trees memo** — bulk-face reads have their own memo
  (`trees._BULK_TREES_MEMO`), so neither read depends on the order and
  `card_reads` / the store need no special case; the 25 precon tunes and the
  audit were unchanged by it. Earlier verdicts: the per-card reads in
  `_analysis/card_reads` stay beside the trees store — reading the four light
  ones (mana, gate, has-trees, self-return) live off stored trees cost a warm
  tune 0.1 / 0.5 / 0.4 s (Blood Rites / Eldrazi Unbound / Sliver Swarm); the
  trees store moves a warm tune by nothing measurable but a cold one, with no
  sidecars attached, by ~0.5 s of its ~1 s of builds; a stored tree carries none
  of the memos reads leave on its nodes (`crosswalk.reads.MEMO_ATTR_PREFIX`;
  `_owner_index` is keyed by node ids); a per-serve slice memo (no gain, two
  serve pages a tune); the collector off for the whole tune (a tune may start
  the signals index's whole-pool build, which makes ~50 cyclic objects a card —
  the tune collects at a 100,000 young threshold instead, measured as fast).

- **`legality-audit` never asks whether a commander can be one** (2026-10-29).
  `check_commander_zone` fails only a card `Format.commander_eligibility` calls
  `banned_as_commander` (Competitive Brawl's list); a `not_a_commander` card (a
  nonlegendary creature, a Commander-format planeswalker without "can be your
  commander") in the command zone passes the audit. Failing every ineligible
  reason there (format legality already reports `banned` / `not_legal`) is the
  general fix; check the synthetic commander fixtures first.

- **Pass D: the serves still on a regex** (2026-10-23;
  `docs/plans/serve-idents-and-avenue-support.md` "Pass D"; each spec's comment
  names its remainder). Regex-only, measured over the legal corpus:
  `ability_strip_payoff` (the
  crippling-drawback text beside a power floor; no lane reads a drawback a strip
  turns off). Lane follow-ups the pass found: a `(key, subject)` role table that
  `DOER_SUBJECTS`, `MEMBERSHIP_SUBJECTS`, `PAGE_ONLY_SUBJECTS`, the pair reads'
  wildcards and the presets all read (today each reads its own set:
  `PAGE_ONLY_SUBJECTS` belongs in it as a role, and the voltron `has_other_plan`
  read should ask `avenue_spec_for(s) is not None` instead of keeping its own
  exclusion lists — membership_floor's step-trigger exclusion duplicates
  `STEP_TRIGGER_KEYS` the same way); an `attack_trigger_side` crosswalk read
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
  Juxtapose, Cultural Exchange, Legerdemain, Desolation,
  Cleanse, Crusade, Artificial Evolution, Tomik; Champion of Stray Souls'
  graveyard zone; Sinister Gnarlbark's blight; Become Brutes' Role; Gemcutter
  Buccaneer's Equipment subtype; Krydle's mill; One Ring to Rule Them All's mill
  reach; where-X scry / surveil (Desmond Miles); Platinum Angel Avatar's "If you
  control an artifact, a creature, an enchantment, and a land" condition (a
  Vanguard card, so no bridge). Earlier: council's dilemma /
  secret council votes parked as residues (a canary), Brago's Representative, Overlord of the Hauntwoods'
  token, Narset Transcendent's rebound, Ral Izzet Viceroy's emblem, a block
  trigger's "it" as ParentTarget, Go Blank's graveyard owner, Estrid's
  Invocation's copy, Mortarion, fourteen damage clauses left Unimplemented
  (Power Surge, Urborg Stalker …), Curse of the Pierced Heart's controller,
  Masako, Lander / Map token abilities, Collision Course's AnyOf, the optional
  wheel's draw scope (Snort — a canary), Can't Stay Away, Custodi
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
  (Mesmerizing Benthid, Wall of Stolen Identity, Tsabo's Web; Scion of Stygia and
  Code of Constraint fixed at v0.118.0), the anaphoric "it gets -N/-0" pumps
  (the other Jace, Tamiyo, Blood Lust, Six-Sided Die; Jace, Architect of
  Thought fixed at v0.118.0), "that player controls" taps (Delirium, Mana Web;
  Yosei fixed at v0.118.0 — and 22 self-tap cards such as Jaddi Lifestrider left
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

**From the no-search guide adds' signal gaps (2026-10-30; bucket D of
`~/mtg/tuner-work/w27/nosearch_buckets.tsv`)**

- **What the four gaps' fixes still don't page.** Shipped: `end_step_sacrifice`
  and `end_the_turn|you|instant`, the `commander_keeps` issue (Sundial in all four
  guide decks), tutor subjects (`tutor|you|<card type>`), ability copiers no longer
  read as spell copiers, multipliers seeing a granted cascade, and a paid tribe the
  commander isn't in kept apart from its lane. Still unpaged: Fabricate (Deep Clue
  Sea's Artifacts is a sub), Enlightened Tutor (Lorehold Spirit), Expedition Map
  (Desert Bloom's Deserts is a sub; Eldrazi Unbound has no land page) and Moonsilver
  Key. Call the Gatewatch and Firemind's Foresight are on their theme's serve but
  below the 150-card play-rate page, which is lever (r). Arena Rector, Changeling
  Outcast and Conspiracy are on a page now and get outranked. A subject's serve
  for the land-type and Artifacts avenues was not tried.
- **Measured negative, so don't re-suggest without a new read: a commander
  ability-multiplier page** (2026-10-30). This is a `commander_keeps`-style issue
  for the ability copiers and trigger doublers that `multiplier_reasons` says
  reach the commander. It added the guides' Strionic Resonator (Eldrazi Unbound)
  and Weaver of Harmony (Enduring Enchantments), and cost four held-out guide adds
  (34 → 31 with it, 35 without). Its one swap takes the first upgrade cut, so
  World Shaper's theme upgrades shift down a slot and Tannuk, Valakut Exploration
  and World Shaper fall off the end. Strionic Resonator, Lithoform Engine and
  Illusionist's Bracers stay unpaged, though `commander_multipliers` protects
  them once they're in a deck.
- **Two reads to fold into one (review, 2026-10-30).** (a) Three versions of
  "at instant speed" exist and disagree:
  `crosswalk.instant_end_turn_unit` (an instant or flash spell, or an
  activation without `AsSorcery`), `job_quality/protection._timely`, and
  `job_quality/removal`, which counts every activation as instant speed. One
  unit-level crosswalk read should replace all three, with the job reads
  re-measured. (b) phase's `CopySpell` maps to the `copy_spell` concept for
  ability copies too (`crosswalk/core.py`). `_spell_copy_makers` filters them
  out with `unit_copied_ability_kind`, but the value-engine synthesis
  (`tree_synthesis/value_engines.py`) and the ledger's copy-spell gap check
  (`bridge_ledger.py`) still count Strionic Resonator as a spell copy. The fix
  is to split the concept where it is assigned.

**From the Fynn, the Fangbearer real-deck validation (2026-10-29; `real-deck-validation.md`)**

- **Fynn's candidate fixes 2-6 are open.** These are: poison and toxic as closers;
  a mana-value gate on a trim's add; the fed-only re-bucket exempting lane doers
  (it cuts Venerated Rotpriest on v6); back-face and activated-grant deathtouch
  read as bodies; and a `deck-tune --collection` flag. Fix 1 (the bites as
  deathtouch-lane members) shipped. The doc's "Candidate fixes" section has the
  evidence for each.
- **A held lane that folds takes its doers with it.** Once the bites joined
  Deathtouch matters, Fynn v4's poison lane ("Poison / infect": the members are
  mostly the same cards) folded into it (`metrics.focus`, `same_members`). Its
  doer, Infectious Bite, dropped out of `commander_lane_cards`, which is the cut
  ranking's lane protection. No Fynn run cuts it, but a folded held lane could
  keep its doers (union the doers over every held ident, folded or not).
- **`damage_equal_power|you|creature` still carries cards that aren't bites.**
  Repentance and Solar Blaze (a creature damages itself), Mutiny (an opponent's
  creature deals the damage), and Corpse Explosion and Dead Reckoning (the spell
  deals the damage) all serve the "Power-as-damage payoffs" page. Mage Slayer
  reads as `creature` too, though it hits the player or planeswalker being
  attacked. The new `bite` subject leaves all of these out. The page could read
  `bite` where it means a creature's own power.
- **`is_bite` skips triggering and batch dealers**, by construction:
  "it deals damage equal to its power" off a trigger, or Moonlight Hunt's "each
  creature you control". The read can't say whose creature those are, so they
  aren't deathtouch-lane members.
- **The deathtouch lane serves every fight, whoever fights.** `fight_makers`
  doesn't record whose creatures fight. Dissension in the Ranks (two blocking
  creatures) counts the same as Prey Upon.

**From the Omnath Competitive Brawl build (2026-10-04)**

- **Phase gaps behind the closer, alternative-cost and mass-land-denial reads**
  (found moving `_tuner/` and `deck_stats` onto the trees, phase v0.94.0; report
  upstream, Dan posts). Each is a card the old regexes read and the trees don't:
  - Reach: `unparsed_quantity` residues park "loses life / deals damage equal to …"
    (Within Range, Soulblast, Final Punishment, Mjölnir; ~28 such residues name
    damage or life loss). (Underbridge Warlock's boon, once a self loss, is a
    typed ``CreateBoon`` since v0.118.0.) (The
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
    `attached_to_qualifier` residue since v0.104.0); Burning of Xinye's "destroys
    four lands" is a residue
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
- **Phase misparses behind the granted death-payoff read** (found 2026-10-25,
  phase v0.104.0; report upstream, Dan posts). Mathas, Fiend Seeker's granted "When
  this creature dies, each opponent draws a card and gains 2 life" parses as `Draw`
  with target `Controller` (the dying creature's controller, not each of their
  opponents). No ledger row or canary: `death_matters`' granted arm
  (`core_makers._grants_death_payoff`) drops the card anyway, because the grant goes
  to a creature an opponent controls, whose death pays that opponent's trigger
  (CR 603.3a), so the misparse moves no read.
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
  Forgotten Gods, Din of the Fireherd's land half, Nicol Bolas, Planeswalker's −9 —
  `test_chained_sacrifice_actor_dropped_canary`); "each opponent [who …]
  sacrifices" parses with no player at all (Variable Solutions — ledger row
  `opponent_sacrifice_actor_dropped`). Fixed at v0.118.0: Davriel, Soul Broker's
  sacrifice now sits in its delayed trigger; Papalymo Totolymo's clause is parked
  whole as an `unbound_subject` residue instead.
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
  records: LOW). (Osseous Sticktwister's phantom discard choice and Spitting Slug's
  dropped blocking-or-blocked narrowing are fixed at v0.118.0; their rows retired.)
  Also unreported, no workaround: Worms of the
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

**From the phase v0.118.0 bump (2026-10-30)**

- **Phase misparses new at v0.118.0** (report upstream by shape, Dan posts):
  - *Subject peeled from a parked clause.* "Target player discards a card for each
    creature it devoured" (Tar Fiend) parks as `unparsed_quantity` "discard a card
    for each …"; likewise Whispering Specter, Doom Foretold, Brain Pry, Cabal
    Shrine, Thoughtcutter Agent ("lose 1 life and reveals their hand"). Read back
    by `recovery._peeled_subject`; Thoughtcutter's second verb is ledger row
    `second_verb_reveal_hand_parked`.
  - Geistlight Snare's "It also costs {1} less to cast" parks as its own
    `unbound_subject` residue in the spell's chain (canary
    `test_self_discount_continuation_parked_canary`).
  - "Reveal N cards from their hand and you choose one" (Blackmail, Hollow
    Specter, Cabal Interrogator, Pulse of the Dross) and "pay one or more {E}"
    (Pia Nalaar, Chief Mechanic; Rampaging Aetherhood) park as
    `unparsed_verb_arguments`; recovered by new grammar rows.
  - Mana Clash's and Rakdos, the Showstopper's per-flip outcome park as
    `per_object_coin_flip_outcome` (direct_damage / mass_removal lost).
  - Bestial Fury's "it gets +4/+0 and gains trample" binds `ParentTarget`, not
    the enchanted creature (aura_equip_kw_grant lost).
  - Seasoned Cryomancer's reflexive tap and Summon: Kujata's, Vivien's
    Invocation's and Adaptive Armorer's reflexive effects park as
    `zone_change_reflexive_*`.
  - Parked whole, each an accepted loss with no workaround (one line each to
    report): Legion's Chant (`unenforced_aggregate_resolution_selection`), Rune
    Snag (`unless_payment`), Lich Lord of Unx's loss per Zombie, Helm of
    Obedience's repeat mill, Turtles Forever (`search_zone_list`), Nazahn's
    search (`search_result_condition`), Even the Odds (`casting_restriction`),
    Smogbelcher Chariot (`perpetual_gain_choice`), Divine Purge's perpetual
    grant, Ursine Monstrosity's mill, Soulgorger Orgg's and Glimmer Hoarder's
    life loss, Absolving Lammasu's and Marrow Chomper's life gain, Tar Fiend's
    enters payload, Hateful Eidolon and Stone Haven Outfitter
    (`departure_attachment_relation`), Ludevic (`unparsed_condition`), Consuming
    Tide, Sudden Salvation and Biomantic Mastery (`unparsed_quantity` draws),
    Wheel of Potential's draw count, Pharika's Spawn's escape counters, Dark
    Intimations' +1/+1-counter tail, Brokers' Safeguard's perpetual shield
    counter, Rakdos Augermage's and Impetuous Lootmonger's own discard, Indominus
    Rex's keyword counters, Invasion of Arcavios's search.
- **Our reads still missing a v0.118.0 shape** (open):
  - "Destroy target creature … and all Equipment attached to that creature" is a
    `TargetOnly` + `DestroyAll{Or[ParentTarget, AttachedTo{Host}]}` (Eaten by
    Spiders removal, Silence the Believers and Soul Nova exile_removal, Portal of
    Sanctuary permanent_etb, Word of Undoing bounce_tempo lost); the removal
    lanes would resolve the `ParentTarget` arm to the chain's root target.
  - A recovered `blocked_attacker_damage_source` damage ("it deals 1 damage to
    defending player" — Simian Sling, Tormentor's Helm; "… to each creature
    blocking it" — Ib Halfheart, Trailblazer's Torch) is read by direct_damage
    but not lifeloss_makers / mass_removal.
  - Underbridge Warlock's enters trigger is a `CreateBoon`; no lane reads a boon
    as an enters payload (self_etb_payload lost).
  - Ral, Izzet Viceroy's emblem trigger ("whenever you cast an instant or sorcery
    spell, … you draw two cards") is typed now; card_draw_engine doesn't read an
    emblem's draw.
  - Tasha, Unholy Archmage's "+1: … put a -1/-1 counter on that creature" names
    the attacker as `TriggeringSource`; debuff_makers doesn't take it.
  - King Narfi's Betrayal's "exile a creature or planeswalker card from each
    graveyard" is a `ChooseFromZone` into a `TrackedSet`; graveyard_matters
    doesn't read the pick.
  - Recovery marks that misfire: Biomantic Mastery ("another target player
    controls" sets `OtherPlayer`), Souls of the Faultless ("attacking player
    loses" not another player), Ursine Monstrosity ("choose an opponent" scopes
    your own mill), Val, Marooned Surveyor (a parked trigger condition recovers as
    a clue maker), Ingenious Mastery ("they scry 2" read as yours).
- `mana_and_wipes._chooses_at_most_one` vetoes a sweep whose tracked set the
  controller fills with at most one object (Light of Judgment) without resolving
  which `TrackedSet` the sweep destroys: it holds for any one-object choice in
  the unit. Resolve the set the `DestroyAll` names (open, low priority).
- **Policy questions from the bump's gains** (decide; fixing would drop cards
  v0.104.0 already had): lifegain_matters on "whenever an opponent gains life"
  (Punishing Fire new; Kavu Predator, Wedding Ring already); Cinder Wall /
  Ceremonial Guard gain voltron_matters|carrier from the membership floor once
  blocked_matters left; keyword_bodies|enchant on Aura tokens (Scriv); Word of
  Undoing's color_change payoff; Messenger Jays' self_drawback; Council's
  Deliberation's card_draw_engine (it exiles itself, so fires once); Swarmyard
  Massacre's scaling_pump from a shrink.

**From the keyword tribe's dropped keywords (2026-10-26, phase v0.104.0)**

- **Phase drops a keyword from a body it otherwise types** (report upstream by
  shape, Dan posts). Each is read in our correction layer
  (``_card_ir.dropped_keywords`` before strict load, the recovery stage's
  ``ConceptNode.body_keywords``), with a ``retirement_canary`` in
  ``test_phase_gaps_keywords.py``, or by a ``keyword_bodies`` ledger row:
  - *A static def's grant left out of its modifications.* Chariot of the Sun:
    "{2}, {T}: Until end of turn, target creature you control gains flying and
    has base toughness 1" types a ``Continuous`` def with ``SetToughness`` alone.
    It should add ``AddKeyword(Flying)``. Likewise Valkyrie's Call's "It has
    flying and is an Angel" (``AddSubtype`` alone), the Zendikons' "is a 4/4
    Elemental creature with reach and haste" (the animation's mods have no
    keyword), and Argivian Avenger's "your choice of flying, vigilance,
    deathtouch, or haste" (``AddKeyword`` for vigilance and deathtouch only); 32
    defs on the legal corpus. Also Guardian Zendikon's "is a 2/6 white Wall
    creature with defender", Jodah's Avenger's "your choice of double strike,
    protection from red, vigilance, or shadow" (the list past "protection from
    red" dropped) and Urza's Avenger's banding.
  - *A grant parked in an ``Unrecognized`` condition.* Tek: "~ gets +0/+2 as long
    as you control a Plains, has flying as long as you control an Island, …"
    types ``AddPower 0 / AddToughness 2`` with the rest of the line as the
    condition's ``text``. It should be one def per clause, each with its own
    condition and ``AddKeyword``. Tribal Golem, Altar of the
    Wretched's "The same is true for first strike, …", and Evolved Spinoderm's
    "Otherwise, it has hexproof" are the same.
  - *A copy's keyword dropped from its exceptions.* Irenicus's Vile
    Duplication: "Create a token that's a copy of target creature you control,
    except the token has flying and it isn't legendary" types ``CopyTokenOf``
    whose ``additional_modifications`` hold only ``RemoveSupertype(Legendary)``.
    It should also hold ``AddKeyword(Flying)``. March from Velis Vel's
    "becomes a copy … and gains haste" is the same.
  - *A keyword misread as a subtype.* Will of the Temur: "except it's a 4/4
    Dragon creature with flying" types ``AddSubtype("With")`` and
    ``AddSubtype("Flying")``. It should type ``AddKeyword(Flying)``. Leonardo da
    Vinci, Sauron, the Necromancer, Kaya, Intangible Slayer and Dino DNA are the
    same.
  - *A pump's grant dropped.* Tromp the Domains: "creatures you control gain
    trample and get +1/+1 for each basic land type" types a bare ``PumpAll``. It
    should add a ``GenericEffect`` with ``AddKeyword(Trample)`` (Haldir, Lórien
    Lieutenant likewise; the team-grant lanes read the decoration as the pump's
    own grant, ``crosswalk.pump_keyword_grants``). Stolen Vitality's
    "Otherwise, it gains first strike" drops the else branch. Indominus Rex,
    Alpha's and Priest of Possibility's "The same is true for …" lists keep only
    their first keyword.
  - *A grant, token or keyword counter parked as an ``Unimplemented`` residue.*
    Notorious Throng: "Create X 1/1 black Faerie Rogue creature tokens with
    flying" should be a ``Token`` with ``keywords: [Flying]``. Reaper of Night's
    "it gains flying until end of turn", Inventive Wingsmith's "put a flying
    counter on it" and Genku, Future Shaper's mode "1/2 blue Moonfolk with
    flying" are the same.
  - *Counter kinds swallowing a clause* (Dralnu's Pet, Printlifter Ooze, March
    Toward Perfection's boon): fixed at v0.118.0; the recovery read and the
    ledger row retired.
  - *A Role token's own ability.* Monstrous Rage: "Create a Monster Role token
    attached to it" types the ``Token`` with no static. It should carry the
    Role's "Enchanted creature gets +1/+1 and has trample" (CR 111.10k; Royal's
    "has ward {1}", 111.10m), which known-tokens has: restored before load, 11
    cards. Become Brutes parks the creation itself (a ledger row).
  - *A spell's conditional flash dropped.* Crashing Tide: "This spell has flash
    as long as you control a Merfolk" leaves no node; phase types the same line
    on Supernatural Rescue. Graveyard Shift, Mutual Destruction (whose
    condition is also a flash payoff) and Take for a Ride likewise (one ledger
    row).
  - *A grant swallowed beside the effect phase types.* Woolly Razorback's "it
    has defender" (the prevention kept), Nick Fury, Spymaster's "and gains
    indestructible until end of turn" (a ``SwallowedClause``), Guardian Beast's
    "they have indestructible" (folded into a ``CantBeEnchanted`` static on
    itself), Wakanda Forever!'s "put a permanent card … onto the battlefield
    with an indestructible counter" (a ``Dig`` to the hand alone) — ledger rows.
  - *A cloak dropped or parked* (CR 701.58a: a 2/2 with ward {2}). Hide in Plain
    Sight's "cloak two of them" is a ``Dig`` with no destination; Become
    Anonymous parks "then cloak those cards" as a residue (ledger rows).
  - *A static bound to the Equipment.* Warmonger's Chariot's "As long as
    equipped creature has defender, it can attack as though it didn't have
    defender" types ``CanAttackWithDefender`` with ``affected: SelfRef`` and the
    equipped creature only in its condition; it should affect the equipped
    creature (a ledger row).
  - *A zone's owner dropped.* Soovril, Patient Antiquarian's "nonland card in
    exile that was put there from your graveyard" types
    ``ZoneChangedThisTurn{from: Graveyard}`` with no owner, so its "gains
    suspend" can't be told yours (a ledger row; the typed grants are
    ``crosswalk.suspends_own_card``'s). The Eleventh Doctor's "If it doesn't
    have suspend, it gains suspend" is a ``keyword_anaphor_resolution_time_pick``
    residue (a ledger row).
  - Single cards, as ledger rows (card: phase emits → should emit):
    Furygale Flocking: "create two 3/3 … Elemental creature tokens with flying"
    → a ``SwallowedClause`` warning, no ``Token`` → a ``Token`` with
    ``keywords: [Flying]``; Welcome the Darkness: "Create an X/X black Demon
    creature token with flying" → only a ``CantGainLife`` static carrying the
    whole text → a ``Token``; (Doom Foretold's Knight token and Spry and
    Mighty's trample are fixed at v0.118.0, their rows retired); Case
    of the Stashed Skeleton: "create a 2/1 black Skeleton … and suspect it" →
    ``Token`` alone → plus ``Suspect``; Burn Down the House: "They gain haste
    until end of turn" → ``Token`` alone → plus a haste grant; Yasova
    Dragonclaw: "untap that creature, and it gains haste" → ``GainControl``
    alone → plus untap and haste; Thundermane Dragon: "If you cast a creature
    spell this way, it gains haste" → swallowed → a haste grant on the cast;
    Alaundo the Seer: the same clause in its granted trigger → an
    ``Unimplemented`` residue; Araumi of the Dead Tide: "gains encore" → a
    residue → ``AddKeyword(Encore)``; Salvation Colossus: "Unearth—Pay eight
    {E}" → a residue → the ``Unearth`` keyword with an energy cost; Ginger,
    Queen of Sweets: "create a Gingerbrute token" → a residue → a ``Token``;
    Phyrexian Splicer: "Choose flying, first strike, trample, or shadow: …
    another target creature gains it" → the choice parked as a cost residue → a
    ``Choose`` of a keyword and its grant; Solid Footing: "As long as enchanted
    creature has vigilance" and Ram Through: "If the creature you control has
    trample" → no ``WithKeyword`` condition → one.

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
