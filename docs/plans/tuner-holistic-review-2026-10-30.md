# The deterministic tuner, reviewed against the precon guides (2026-10-30)

A holistic look at `deck-tune` after the 2026-10-18 → 10-30 audit cycle: what the
guides are, what they know that the tuner doesn't, where the misses come from
(ranking, reach, parse, theme definition), and the algorithmic changes that would
move the add side. Numbers are from the current baseline runs
(`~/mtg/tuner-work/precons/misses-r-fodder.json`, `heldout/misses-r-fodder.json`,
commit 514d63d5 + 8e56f394) unless stated. Card claims were checked with
`scryfall-lookup` / `rulings-lookup` / `rules-lookup` (CR 2026-09-25).

## Summary

1. **The guides are a usable gold standard, in aggregate.** Their adds are spread
   over 1,007 distinct cards for 1,200 adds (only 6% of adds are cards named in 4+
   decks); the tuner's 1,029 adds use 580 cards and 36% are cards it puts in 4+
   decks. The guides keep the precon's plan and cut mostly off-lane cards (only
   14-19% of their cuts are cards the tuner reads as lane doers or main carers).
   The staple-swapper in this comparison is the tuner, not the guides.
   (Per-source verdicts: §1.)
2. **The cut side is in reasonable shape; the add side is the problem.** Cuts:
   66% of the guides' cuttable cuts are made (335/505; held-out 64%). Adds: 15%
   on the 25 (121/793), **9% on the held-out ten** (37/407), 0-3% on three
   held-out decks (Revenant Recon 0/32, Silverquill 1/54, Prismari 1/37).
3. **What the guide writers use that the tuner has no read for is the
   commander's own text.** Winter's delirium reads "four or more card types
   among cards in your graveyard"; Mirko triggers "whenever you surveil"; Killian
   draws when "creatures enchanted by an Aura you control attack". The guides'
   adds satisfy the commander's condition 44-83% of the time; the tuner's adds
   0-10% (§2). The Card IR already carries these conditions (Winter's delirium
   is `QuantityComparison(GE, DistinctCardTypes(Zone(Controller, Graveyard)), 4)`),
   so this is a missing *read*, not a missing *parse*.
4. **Ranking vs reach splits by kind of add.** The guides' job adds (ramp /
   draw / removal / wipes / protection — about half of all guide adds) are
   mostly on a page the tuner built and outranked (458 of 594 in scope, both
   sets): a ranking and budget-policy problem. Their theme adds are mostly
   never searched (315 of 605) or outside the 150-card play-rate page: a
   reach / theme-definition problem (§3, §5).
5. **The theme page is the broad avenue's most-played cards.** Since the fit
   floor was dropped, nothing the Card IR reads orders a theme add; the
   synergy score decides only ties, and the 27-row commander-anchored pair
   ledger (`pair_reads`) is not passed to the tuner's ranker at all. Deck
   after deck the main theme is a 7-10%-of-the-pool umbrella ("Your graveyard",
   "Combat", "Enchantments") while the commander's distinctive ident is a
   0.1-0.7% one (surveil, goad, Auras, mill, Warrior tokens) — §5, §7.
6. **The evaluation has been over-fitted to the 25.** 210 measured policy
   variants and 86 tuner/analysis commits since 2026-10-18, gated on ±1-2 add
   deltas, took the 25 from 8 to 121 guide adds while the held-out ten went
   from 24 to 37. Swap cascades make ±2 noise. §7.8 proposes a page-level
   metric that doesn't depend on the swap budget.
7. **Phase parses are 1-3% of the misses** (§4): four cards, each fixable in
   our correction layers, each worth one card. Theme definition is ~38% of
   the unreached theme adds, page depth under umbrella lanes ~20%, and about a
   fifth are raw-power picks no theme read should chase.

## The numbers that frame everything

| | the 25 | held-out 10 |
|---|---|---|
| swaps | 732 | 297 |
| swaps that are the `upgrade` issue (play-rate drain) | 572 (78%) | 246 (83%) |
| guide cuts matched | 335 / 505 (66%) | 139 / 216 (64%) |
| guide adds matched | 121 / 793 (15%) | 37 / 407 (9%) |
| guide adds on a page but outranked | 372 + 63 gated | 185 + 37 gated |
| guide adds no search reached (theme) | 191 | 124 |
| guide adds no search reached (a job) | 27 + 16 not on page | 12 + 11 |

Add concentration (both sets, 35 decks): the tuner adds Fellwar Stone, Feed the
Swarm and Beast Within to 13 decks each, Chaos Warp 12, Mangara / Vanquish the
Horde / Garruk's Uprising / Swiftfoot Boots / Path to Exile / Blasphemous Act 11
each, Generous Gift 10 — 60 cards go into 4+ decks. The guides' most repeated adds
are Heroic Intervention (8), Swiftfoot Boots / Smothering Tithe / Skullclamp /
Anointed Procession / Parallel Lives (6), Doubling Season / Lightning Greaves (5)
— 13 cards in 4+ decks.

Prices (USD, listed): tuner adds median $1.36, 5% over $25; guide adds median
$1.85, 9% over $25. Of the 557 outranked guide adds, 160 cost more than the
tune's even share of the budget (budget / 30 swaps).

## 1. Are the guides a good gold standard?

A research agent classified every source in the 35 guide summaries (98 sources,
92 with six or more adds) by the share of its adds that are generic staples
(rocks, generic removal / wipes / draw / protection, lands) versus cards tied
to the deck's plan; full tables in `~/mtg/tuner-work/w40/guides-quality.md`
(per-source, by site, by author, play data, Game Changer counts).

- **74 of 92 guides keep the theme**, 8 are mixed, 9 are staple-swaps, 1 is a
  rebuild (Quick Draw's Card Kingdom untap-combo list). 23% of all added cards
  are generic (28-30% allowing for the name list's misses; a 50-row hand sample
  put the error at 5-10%, all toward undercounting staples).
- **Consensus rows lean further to the theme:** of the 205 cards two or more
  guides name for the same precon, 83% are plan cards. Where guides drop a
  subtheme it is a secondary one (the alternate commander's, the Food
  package, Betor's lifegain, Killian's politics), never the main commander's
  engine.
- **By site:** Card Kingdom is the most theme-keeping (median guide 11%
  generic; 25 of 27 keep the theme), then EDHREC / Andy Zupke (20%; 22 of 25).
  Draftsim (23%) and Card Game Base (25%) lean to staples — especially A.L.
  Walser's "N easy changes" lists (40%); Hipsters (one guide, 61%) and MTG
  Rocks (two) are the staple-swappers. No TCGplayer source is in the set.
- **Bracket:** no guide states a bracket for its main list; they set price
  tiers ($50; under $5 a card). 63 of 92 predate the bracket system. 59 Game
  Changer adds across 26 guides (0.6 per guide), 32 of them pre-bracket; the
  2025-26 guides offer GCs as an optional "three for bracket 3" layer (counted
  against WotC's 53-card list of 2026-02-09).
- **Play data: there is none for upgraded precons.** Playgroup.gg (26k logged
  stock-precon games) says its data "does not show a clear win-rate gain from
  modifying a precon while keeping its core" and publishes no numbers for
  modified decks. Its proxies are observational: win rate by GC count (0 GCs
  −4.6%, 1-3 +2.8%, 4+ +10.3% vs the pod), and a commander-matched per-card
  lift — a commander-specific statistic the tuner's rules keep out. EDHREC
  precon-upgrade pages are popularity. WotC stopped pegging precons to
  bracket 2 on 2025-10-21. So the guides are expert opinion with no outcome
  validation, and agreement between independent guides is the best stand-in
  for "this card performs here".

**Verdict on Q1:** the guides are the right target for a theme-keeping
upgrade; they are budget upgrades, not optimized bracket-3 lists, and the
tuner should be read the same way. Scoring changes the agent recommends and I
agree with: keep every theme row at full weight; add a consensus line (the
scoreboard already reports it — 38 of 137 consensus adds matched on the 25);
score generic rows at the job level ("a 2-mana rock", "an untapped dual")
rather than by name, with lands and rocks on a separate mana-base line (124 of
the 314 generic rows); halve the generic rows that come only from the 18
mixed / staple / rebuild sources; leave GC rows out of recall unless the run
targets bracket 3 with a GC allowance. Drop no site.

What the tuner's own reads say about the guides as a set:

- Guide cuts are off-lane cards: on the 25, 56 of 505 guide cuts are commander-lane
  doers and 13 are main-theme carers (14%); held-out 41 + 1 of 216 (19%). The
  rest are filler, low-value, off-lane cards and the lane's least-played half.
- Guide adds are not a staple list (the concentration numbers above). Within
  the job adds the guides prefer permanents: of 406 outranked job adds, 288 are
  permanents (Smothering Tithe, Esper Sentinel, Terror of the Peaks, Professional
  Face-Breaker, Birds of Paradise) and 118 are spells; the tuner's job adds are
  overwhelmingly the most-played instant or sorcery of the job.
- Guides swap commanders occasionally (World Shaper's EDHREC guide builds
  Szarel; Death Toll's guides keep Winter over Rendmaw) and do not throw the
  plan out: every consensus line in `docs/plans/precon-audit/*.md` is "cut the
  off-plan / weak cards, add on-plan cards and fix the mana".

## 2. What the guide writers know that the tuner doesn't

**The commander's own conditions and resources.** Three decks, read against
the commander's text:

| deck / commander condition | guide adds satisfying it | tuner adds satisfying it |
|---|---|---|
| Death Toll — Winter: "four or more card types among cards in your graveyard" (delirium); mills on attack. Test: the add has 2+ card types or mills/surveils | 21 / 38 (55%) | 3 / 30 (10%) |
| Revenant Recon — Mirko: "Whenever you surveil, put a +1/+1 counter on Mirko"; returns a creature with lesser power at end step. Test: the add surveils | 14 / 32 (44%) | 0 / 30 (0%) |
| Silverquill Influence — Killian: enchantment enters → tap and goad; "creatures that are enchanted by an Aura you control attack" → draw. Test: the add is an Aura or names Auras/enchant | 45 / 54 (83%) | 2 / 30 (7%) |

The tuner's Death Toll adds are the most-played `graveyard_matters|you|` cards
in Golgari (Ramunap Excavator, Aftermath Analyst, Conduit of Worlds, Splendid
Reclamation — a lands-in-graveyard package Winter never reads) plus the
interaction staples. Its Revenant Recon adds are the most-played graveyard cards
in Dimir and it cuts eight of the precon's surveil outlets (Curate, Notion Rain,
Discovery // Dispersal, Dream Eater, Nightveil Sprite, Thoughtbound Phantasm,
Dimir Spybug, Otherworldly Gaze) — the guides cut several of those too, but
replace them with better surveil outlets (Snarling Gorehound, Cruel Witness,
Laser Screwdriver, Eloise, Dimir Strandcatcher); the tuner replaces them with
Gravecrawler and Myr Retriever. Its Silverquill adds are the Combat page
(Adeline, Bastion of Remembrance, Marionette Apprentice, Bitterblossom) because
"Combat" (`attack_matters|you|`, 6.3% of the pool, 15 carers) beat "Voltron /
equipment & auras" (`voltron_matters|you|`, 0.7%, 10 carers) and "Goad"
(`goad_makers|opponents|`, 0.4%, 9 emitters) for the primary lane.

The commander's condition is already in the Card IR. Winter's second trigger is
`condition=QuantityComparison(comparator='GE', lhs=DistinctCardTypes(source=Zone(
scope='Controller', zone='Graveyard')), rhs=Fixed(4))`; Mirko's first trigger has
`mode='Surveil'`; Killian's has `destination='Battlefield'` on an enchantment
filter and a second trigger on attackers enchanted by an Aura you control.
Nothing in `_tuner/` or `_analysis/` reads a commander's trigger `mode` or
`condition` to decide what to add. The nearest things are: `commander_idents`
(the lane keys the commander emits — a coarse projection of the same text),
`multipliers.Commander` (end-step sacrifices, grants), the token-doubler lever
(`Sourcing.multiplier_avenue`, which is exactly a "what the commander produces →
what consumes it" read, for one resource), and `pair_reads` (27 curated
commander-anchored rows the tuner doesn't call).

**The deck's plan as a sentence.** Every guide states the plan in one line
("Dimir surveil/recursion", "W/B Aura/enchantress", "Golgari self-mill and
reanimation with delirium"). The tuner's plan is the top viable avenue's label,
chosen by carer count among the commander's held lanes. Where the commander's
distinctive mechanic is a rare ident, the broad lane wins: 5 of the 35 decks
read "Your graveyard" (10.3% of the pool carry it) as the main; Mardu Surge and
Silverquill read "Combat". The table in §5 lists each commander's idents
rarest-first beside the tuner's mains and the guide's plan line.

**Two-purpose cards.** The guides' job adds double as plan cards (Millikin:
ramp that mills; Hedge Shredder: ramp when milling; Drag to the Roots: removal
with a delirium payoff; Smothering Tithe in a Treasure deck). The tuner's job
page is the job's whole match set ordered by play-rate (or the read blended
with it); theme fit breaks a near tie (`_THEME_TIE`, draw and ramp only). The
audit measured "fit first over the whole match set" (3b) and lost the staples
the guides also add — because fit was "shares any non-generic ident with the
commander", which is too loose. A fit read that is the commander's *condition*
(§2 above) is a different, much narrower test, and it has not been measured.

**Budget allocation.** The guides spend on two or three marquee cards and fill
the rest cheaply; the tune spreads an even share (budget / open swaps, with a
near-tie fallback to the cheaper card). Smothering Tithe is a guide add in five
decks and the tuner's add in none; Fellwar Stone is the tuner's ramp add in 13.
160 of the 557 outranked guide adds cost more than the even share.

**Cut reasons the guides give that the tuner has no read for.** "Limited-level
card", "clunky at that cost", "one-shot where a repeatable effect exists",
"doesn't add a card type", "needs fodder the deck doesn't make". The audit
measured several function reads inside a lane (one-shot vs repeatable, body
for cost, lanes touched) and none beat play-rate for predicting a guide cut
(backlog (a)); on the cut side the play-rate tiers are good enough. The
same reasons on the *add* side are plan-conditional ("adds a card type" only
matters under Winter), which is the commander-need read again.

## 3. Ranking or reach?

By the tuner's own `upgrade_job` read of each guide add (both sets):

| kind of guide add | added | on a page, outranked or gated | never searched / not on any page | out of scope |
|---|---|---|---|---|
| theme card (no template job) | 87 | 203 | 315 | 89 |
| ramp | 13 | 118 | 9 | 4 |
| card draw | 28 | 121 | 26 | 20 |
| interaction | 15 | 124 | 5 | 2 |
| protection | 10 | 60 | 25 | 4 |
| board wipe | 5 | 35 | 0 | 1 |

So: **job adds are a ranking problem** (458 outranked against 71 added and 65
unreached) and **theme adds are mostly a reach problem** (315 unreached, 203
outranked, 87 added). Two caveats on "outranked":

- A job upgrade reads the job's *whole match set* (`_JOB_READ_PAGE`), so "on a
  page" for a job means "somewhere among thousands of removal spells"; the
  guide card is usually hundreds of places down a play-rate order (the w38
  count: a median of 307 better-played job cards ahead of the outranked ones).
- For a theme card, "no search for its kind" also covers "not in the top 150
  by play-rate of a searched theme page" (misses.py checks the page, and only a
  job kind is checked for "a page of its job was searched"). So the theme
  reach gap is partly page depth, partly no page.

What outranked guide job adds have in common is in §2: they are permanents that
also serve the plan. What the unreached theme adds have in common, measured by
ident against the commander (342 rows, both sets):

| the missed theme card… | rows |
|---|---|
| shares one of the commander's three rarest idents | 37 (11%) |
| is a maker of a thing the commander cares about (`_cares_keys` inverse) | 23 (7%) |
| shares another non-generic (<5% of pool) commander ident | 46 (13%) |
| shares only a generic (≥5% of pool) ident — on the broad lane, past its page | 106 (31%) |
| shares no ident with the commander | 130 (38%) |

The last row is the condition-reading problem: Giant Ox, Shield Sphere and
Meekstone under Felothar (toughness and low-power bodies: a stat, not an
ident), Invasion battles and Destined // Lead under Winter (a card type), Spirit
Link under Killian (an Aura). No ident vocabulary will ever name "has toughness
greater than power" or "adds a second card type to the graveyard"; a predicate
over the record derived from the commander's condition will.

## 4. Phase parses

A taxonomy agent sorted every missed guide add that no search reached (381
rows: 234 on the 25, 147 held-out) into buckets, programmatically and then by
hand on 128 rows (`~/mtg/tuner-work/w40/miss-taxonomy.md`, `missed-adds.tsv`;
a patched copy of `misses.py` reproduced the baseline exactly first):

| bucket | programmatic | hand-judged (128) | weighted estimate of 381 |
|---|---|---|---|
| PARSE — phase drops the clause the guide values | 9 | 4 | ~6 (1-3%) |
| LANE — parsed, no ident captures it | 81 | 9 | ~24 |
| THEME-DEF — ident exists, the deck's mains don't reach it | 94 | 49 | ~143 (38%) |
| PAGE-DEPTH — in a main's search, past the 150-card play-rate page | 121 | 17 | ~75 |
| JOB — a template-job card, not a theme card | 66 | 16 | ~50 |
| POWER — a finisher / raw power / personal pick | 10 | 33 | ~84 |

**Phase parses are 1-3% of the misses.** Phase flags a punt (`parse_warnings`)
on 30 of the missed adds, but in only three does the punt drop the clause the
guide wants (Sower of Discord, Serra Paragon, Helm of Obedience), and one silent
misparse turned up: Solar Blaze, read as damage with no target, so the
board-wipe read never fires. Each is fixable in our layers — Solar Blaze in
`field_corrections` (the one general shape), Sower as a ledger row, Serra
Paragon in `recovery`, Helm in `dropped_clauses` — and each recovers one card.
The programmatic LANE bucket over-counts: of 31 hand-checked LANE rows, 6 are
real lane gaps, 12 are theme-definition misses, 11 are power adds.

One data point from this review: the three commanders' conditions above parse
completely (Winter's delirium condition, Mirko's surveil mode, Killian's
enchantment-ETB filter and Aura-attack filter), so none of the §2 misses is a
parse gap.

## 5. Theme definitions

**Theme definition is the largest addressable cause (~38% of the unreached
theme adds).** The lanes themselves mostly hold up; what fails is which lane
the deck is read as being about, and which side of a maker/payoff pair gets a
page. The taxonomy agent's reach counts (guide adds across both sets):

- Killian's Aura plan (17): an Aura-attach payoff ident that counts any
  creature's controller — Killian draws for creatures enchanted by an Aura you
  control, and goaded opponents' creatures attack (his rulings; CR 701.15a) —
  plus a main rule that lets a commander-held lane at main depth be a main
  when it fails only the carer-share bar (Enchantments 39 deep and Voltron 31
  deep lost to Combat's 15 attack-trigger carers).
- Token makers beside a token-payoff commander (16): Mardu Surge's "Token
  generators" is 28 deep and only fed (3 carers against a floor of 4).
- Counter movers / keepers beside +1/+1 counter makers (11: The Ozolith ×2,
  Host of the Hereafter, Envoy, Byrke); surveil makers beside Mirko (9);
  evasion and double strike beside a combat-damage commander (8); "whenever an
  artifact / enchantment you control enters" payoffs, which phase parses but no
  ident serves (7); role reads — Clue engines as card draw, a conditional
  exile as removal, theme cards currently read as job cards staying theme
  (6-9); artifact-token makers on Gimbal's page (4); land tokens as landfall
  makers and land tutors in landfall decks (3).

All of these are instances of §7.4's maker↔payoff pairing read off the
commander. **Page depth** is the second cause (~75): 92 of the 121 such rows
sit in mains with more than 1,500 matches (Your graveyard 41, Spellslinger
23, Combat 16) — the umbrella-lane problem again, since a specific page would
hold them near the top.

**Cut side** (40 sampled protected guide cuts): 28 are on-theme for the deck
and the guides cut them for quality, consistent with backlog (a); 6 are
popular staples the premium shield keeps; 2 are lane doers through a loose
ident (Sylvan Ranger via a low-confidence `blink_flicker` on Ellivere, TARDIS
via `attack_matters`) — across all 96 lane-doer cuts, 8 are doers through
`attack_matters` alone, the same generic-lane weakness as the primary choice.

**A labeling caveat on "outranked":** in a 60-row sample, 18 guide cards sat
*above* the tuner's pick on the same page and still lost — to the cut's
mana-value band, the even budget share, or an earlier issue taking the slot.
`misses.py`'s "outranked" overstates pure ordering by about 30%.

The commander's idents, rarest in the pool first, beside the tuner's mains and
the guide's plan (all 35 decks; pool base rate over 38,753 indexed cards):

| deck | tuner mains | commander's rarest idents (pool share, deck emitters) | guide plan |
|---|---|---|---|
| Silverquill Influence | Combat | goad_makers\|opponents (0.4%, 9); voltron_matters\|you (0.7%, 10); … attack_matters\|you (6.3%, 15); enchantments_matter (10.6%, 8) | W/B Aura/enchantress + goad |
| Revenant Recon | Your graveyard | scry_surveil_matters\|you (0.1%, 6); reanimator (0.4%, 1); creature_recursion\|battlefield (1.0%, 8) … graveyard_matters (10.3%, 23) | Dimir surveil / recursion |
| Death Toll | Your graveyard | permanent_recast (1.0%, 4); mill_makers\|any (1.6%, 15) … graveyard_makers (7.6%, 20); graveyard_matters (10.3%, 30) | self-mill, reanimation, delirium |
| Mardu Surge | Combat | tokens_matter\|you\|drain (0.0%, 1); tokens_matter (0.3%, 4); token_maker\|Warrior (0.4%, 4); ltb_matters (0.6%, 1) | Warrior tokens, mobilize, drain |
| Grand Larceny | Combat damage | wants_theft (0.0%, 1); opp_top_exile (0.2%, 8); theft_makers (0.4%, 15); cast_from_exile (0.5%, 9) | Sultai theft off combat damage |
| Graveyard Overdrive | Your graveyard | type_matters\|Lhurgoyf (0.0%, 3); tribe_damage_trigger (0.5%, 1) … graveyard_matters (10.3%, 27) | Jund Lhurgoyfs from the graveyard |
| Desert Bloom | Your graveyard | token_maker\|Plant (0.0%, 4); land_type_matters\|Desert (0.0%, 3); land_sacrifice_makers (0.3%, 3) | Naya landfall / lands-matter, Deserts |
| Sultai Arisen | Your graveyard | token_maker\|Druid (0.0%, 4); permanent_recast\|land (0.2%, 6); token_maker\|Zombie (0.6%, 5); landfall (0.8%, 7) | cards leaving the graveyard, recursion, tokens |
| Creative Energy | Energy, Combat | energy_matters (0.3%, 29); energy_makers (0.4%, 32); end_step_sacrifice (0.7%, 1); token_copy_makers (0.9%, 2) | energy / token copies |
| Peace Offering | +1/+1 counters (makers) | target_player_draws\|any (0.6%, 8); keyword_grant_target\|flying (0.5%, 1) | Bant group hug + counters |

Where the commander is a tribe or a one-word mechanic (Slivers, Dinosaurs,
Energy, Landfall, Superfriends, Suspend, Goad under Nelly, Clues under Morska)
the main is right. Where the commander's mechanic is a rare ident beside a
common one, the common one wins the primary (carer count, then depth —
`metrics.focus`'s `primary`), and even when the rare lane survives as a sub it
takes no theme add (only mains and commander tribes share the theme adds —
`Sourcing.theme_avenues`). The audit's 4c experiment ("the commander's every
non-generic ident whose lane isn't viable, its exact-ident page") is the closest
thing tried and was rejected because a commander holds five to eight such
idents and each took an add; "one per deck, the deepest" passed the 25 and
lost one held-out add. The rarest-ident rule is a different selector (pool
specificity, not depth), and the page it wants is the *maker* side of the
commander's payoff ident (surveil outlets for Mirko, Auras for Killian), which
is not the exact-ident page 4c built (other "whenever you surveil" payoffs).

## 6. Deckbuilding frameworks worth encoding

The agent's framework survey (`~/mtg/tuner-work/w40/frameworks.md`, 18
sources with URLs: Command Zone #658, Burgess, Karsten, Tomer's "50 mana"
checklist, EDHREC's Gottfried / Cain guides, Draftsim's precon method, Card
Kingdom, Mythras, Cardsphere, SCG, WotC brackets) distilled 20 checkable rules.
Against what the tuner has: 3 already, 13 partial, 4 missing. The ones that
bear on the misses:

| rule | kind | status in the tuner |
|---|---|---|
| Tapped lands → untapped on-colour duals at the same land count (the guides' single largest generic add class, 71 land rows) | cuts/adds | missing — the tune never touches lands; `balance-lands` is a separate tool |
| Ramp MV discipline: ramp MV ≤ commander MV − 2; a 3-4 MV rock making one mana is the first ramp cut; ramp 10, or 12 when the commander costs 4+ | cuts/adds/ranking | partial — ramp row and play-rate upgrades; no MV-vs-commander rule |
| Single-target removal at MV ≥ 5 is a cut, MV ≥ 4 an upgrade target for an instant at 1-3; rank by MV, speed, permanence | cuts/ranking | partial — the removal job read exists, no explicit thresholds |
| Multiplayer scaling: a one-shot, one-target, non-repeating effect ranks below one hitting each opponent | cuts/ranking | missing |
| Interaction coverage by permanent type (creature / artifact / enchantment) plus a counterspell in blue | adds | missing |
| At least one graveyard-hate piece; ~2 recursion; 1-2 tutors for the plan's key piece | adds | missing as template rows |
| Every nonland card has a role; a card with two or more roles ranks higher | cuts/ranking | cut side already (filler); multi-role ranking bonus missing |
| Plan density 22-30 and ≥ 7 cards that push or win with the plan | adds | partial — closer count, no plan-density band |
| Redundancy of the commander's key effect (~8 cards); **the on-plan version of a role beats the generic one** (enchantment ramp over Farseek under an enchantress — Card Kingdom's stated method) | adds/ranking | partial — no redundancy target; theme fit breaks only a near tie for draw and ramp |
| A payoff with too few enablers is a cut (Ripjaw Raptor with few enrage triggers); so is an enabler whose payoff left | cuts | partial — fed-only read |
| Cut the secondary theme, double down on the primary | cuts | partial |
| A nonland card at MV ≥ 6 that is neither finisher nor plan card is a cut | cuts | missing |
| Symmetric creature wipes in a creature-heavy deck are cuts; one-sided preferred | cuts/adds | partial — the deck-fit wipe read was built and rejected on the 25 |

"Cut win-more" is not a hard rule in the sources (SCG: "win-more pieces
aren't bad"); "Limited-level filler" is the role rule plus the vanilla-body
rule. Two of these rules fall straight out of the §7.4 read: "redundancy of
the commander's key effect" is the commander-need page with a target, and "the
on-plan version of a role" is the job page preferring a card the commander's
condition admits.

## 7. Algorithmic shortcomings

### 7.1 The upgrade drain is a staple-swapper

78-83% of swaps are the `upgrade` issue: an off-lane card past EDHREC rank 1500
(or the deep lane's least-played half, or a popular off-main card) traded for a
better-played card doing the same job. Both ends are play-rate; the IR decides
only membership (does the candidate do the job) and the mana-value band. The
cut end is good (48% of off-lane cards past rank 3000 are guide cuts). The add
end is where the staples come from: the most-played removal spell in the colours
is the add for every interaction cut, in every deck. The guides make the same
cuts and add two-purpose permanents instead (§2, §3).

### 7.2 Nothing the IR reads orders a theme add

`_ranked_pool` under `synergy_first and ctx.playrate` sorts by `_quality`
(EDHREC rank) then price — the fit floor was dropped on 2026-10-30 because it
cost four adds. `rank_candidates`' synergy score is computed but used only to
break ties in `_job_order` and for `_viable_served_names`; `pair_score` is 0
because the tuner never builds a `PairContext` (only `deck_rank` does). The
"card reads leading" experiments (orders A/B) lost because the reads were
coarse (shares an ident with the commander; deck depth); the audit concluded
"reorders lose to play-rate, reach-adding changes win". That conclusion is about
*those* reads, not about reading cards.

### 7.3 The primary lane is chosen by carer count, not specificity

`metrics.focus`: the primary is the held lane the most cards care about, then
the deepest. Generic lanes (Combat 6.3% of the pool, Enchantments 10.6%, Your
graveyard 10.3%, permanent_etb 15.4%) accumulate carers in any deck. A
specificity term — pool base rate of the ident, the same lift the scoreboard's
near-miss rule already uses — would pick Auras/Goad for Killian, surveil for
Mirko, Warrior tokens for Zurgo, theft for Gonti (§5 table).

### 7.4 No commander-need model

The single biggest gap (§2). Concretely, from the commander's trees:

- **Events it triggers on** (`S_triggers.mode`: Surveil, Attacks, an
  enchantment entering, a token leaving) → the add page is the *makers* of
  that event (`_cares_keys` has the makers→payoff direction for carers; the
  inverse is missing except for the token-doubler lever).
- **Conditions it reads** (`condition=QuantityComparison(...)` over
  `DistinctCardTypes`, `power`, `toughness`, counters, a zone count) → a
  predicate over the candidate record: does this card raise the quantity
  (adds a card type to the graveyard, has toughness > power, has power less
  than Mirko's expected size)?
- **Resources it produces** (tokens of kind X, energy, counters, Treasure) → the
  payoffs that consume them (the 4b lever, generalised; measured per
  resource — the audit found counter doublers cost held-out adds through the
  budget, not through wrong cards).

This is a reach change (new pages) with a narrow, deterministic fit test, which
is the shape of change the audit found wins. It should be measured first as
page-level recall (§7.8), then as a tune.

### 7.5 One job per card

`upgrade_job` returns a single job in `UPGRADE_ROLE_ORDER` (wipe > interaction
> draw > ramp), else protection, else none. A creature with an incidental
removal clause (Terror of the Peaks, Rise of the Witch-king, Lord Windgrace,
Surly Badgersaur — all outranked guide adds) is "interaction" and can only be
sourced from the interaction page, where it loses to Path to Exile. The guides
add them as plan cards. A theme page should admit a card whatever job it also
does; a job page should prefer a card that also serves the plan (3b's idea,
with the §2 condition read as the fit).

### 7.6 The even share

`find_add` takes the first affordable candidate at or under budget / open
swaps, else the first of the next ten that fits the share, else the cheapest
near tie. With 30 swaps and a $57-$600 budget the share is $2-$20, so a $30
guide add loses to a $1 card of the same job unless it is first and within
`_PURSE_CAP`. The guides front-load: Tithe, Doubling Season, Parallel Lives,
Teferi's Protection, The One Ring. A two-tier purse (a marquee allowance of
~40% for the best-fit card of the plan, the rest even) is the human policy.

### 7.7 The lane cut tier removes the plan's feeders without putting the plan back

Silverquill's `lane_upgrade_cards` are 14 Aura-plan cards (Hateful Eidolon,
Eidolon of Countless Battles, Ajani's Chosen, Martial Impetus …); the guides
cut several of them too, so the tier's precision is fine. The add that replaces
each is "the main theme" — the Combat page. Cutting a weak Aura for a better
Aura is an upgrade; cutting it for Adeline is a plan change. The replacement
for a lane slot should come from the lane the cut was on (the cut's own
rarest-ident lane), not the primary's page.

### 7.8 The evaluation over-fits the 25 and can't see ±2

- 210 measured variants, 86 commits, gates of "adds rise, cuts fall ≤2 on the
  25; adds don't fall, cuts fall ≤1 held-out". One deck's swap cascade moves
  2-5 adds (the audit records several). The held-out ten were never used to
  design a rule, and show 9% adds against the 25's 15%.
- Proposal: a **page-level metric** independent of the swap cascade and the
  budget — for each deck, each guide add's rank on the page the tuner *would*
  ask for it (or "no page"), reported as recall@10 / @30 per kind (theme, each
  job). The w33 probe did this once by hand (82 guide adds in the pages' top
  ten vs 71). It isolates ranking from reach, costs seconds per deck after one
  tune, and a change that raises it without raising the tune's count points at
  the cut/budget machinery rather than the read.
- A **plan-consistency metric**: the share of a tune's adds that satisfy the
  commander's own condition (§2's test, generalised by the §7.4 read). It
  scores the tune on what it is for, even where a guide names a different
  card doing the same thing, and it is the metric the held-out zeros fail.
- Grow the held-out set before the next policy round (ten more precons is an
  afternoon of guide summaries), and stop gating on single-digit deltas.

## 8. What I would do first

1. **Build the commander-need read** (§7.4) as a pure function over the
   commander's trees: events (trigger modes) → maker pages; conditions →
   record predicates; resources → consumer pages. Measure it with the
   page-level metric on all 35 decks before wiring it into a tune.
2. **Pick the primary lane by specificity** (§7.3): rank the commander's held
   lanes by pool base rate (lift) with the carer floor as a gate, not the
   score. Check the §5 table flips Silverquill, Mardu Surge, Grand Larceny
   and the five graveyard decks to their guide plan.
3. **Give lane cuts a lane add** (§7.7): a `lane_upgrade` slot's replacement
   comes from that card's own rarest-ident lane page, then the primary.
4. **A marquee purse** (§7.6) and a job page that prefers a plan-fitting
   permanent when the §1 read says the card fits (3b with the narrow fit).
5. **Fix the evaluation** (§7.8) so 1-4 can be measured honestly.

Beside those, the taxonomy agent's reach list (§5) is the concrete backlog
for lanes and idents: the Aura-attach payoff ident and the main rule (17), the
maker lane a payoff commander cares about as commander-held (16, measured
against (r) / 4c's bar), counter movers beside counter makers (11), surveil
makers beside Mirko (9), evasion / double strike beside combat-damage
commanders (8), the artifact / enchantment ETB payoff idents (7), the three
role-read fixes (6-9), and the four one-card parse corrections (Solar Blaze,
Sower of Discord, Serra Paragon, Helm of Obedience).

Already rejected and not re-proposed here: reordering the theme page by card
reads or reaching past 150 under the current reads (orders A/B, 4c, (s));
protection searches for every shape (j); trigger copiers and counter doublers
as a shared page (w34); every sub sharing the theme adds; alternate-commander
plans.
