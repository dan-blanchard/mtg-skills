# Real-deck validation: the tuner against hand-tuned decks

The 25-precon audit (`precon-audit-2026-10-18.md`) compares the deterministic
tuner (`deck-tune`) with published upgrade guides. This doc compares it with
decks Dan tuned himself and played, where the verdicts are his own and settled.
It records measurements. A finding marked (a) below is a candidate fix for Dan
to choose, not a decision. One has shipped since: Fynn's bites count as
deathtouch-lane members ("After the bite fix").

Each disagreement gets one of three classes:

- **(a)**: the tuner is wrong. The likely cause in the code is given.
- **(b)**: the hand tune was arguable, and the tuner's pick is defensible.
- **(c)**: the tuner contradicts one of Dan's settled verdicts.

## Jace, Multiverse Architect

The Multiverse Reforged precon (WUBR, paper Commander, bracket 4, a 4-player
pod) is a polymorph deck. Cheap token makers supply bodies ("fodder"). Jace's −3,
Mass Polymorph, Synthetic Destiny and Proteus Staff exile them and reveal cards
until a creature, which goes onto the battlefield. The deck runs about 18 bombs
it never means to cast. The v2 tune (2026-10-17) made 8 swaps for $19.58 of a
$40 budget:

- **Out:** Omnath, Locus of the Void; Ginger, Queen of Sweets; Dack Fayden, Helping Hand; Niv-Mizzet, Ghost Counsel; Teferi's Reproach; Fact or Fiction; Chromatic Lantern; Rakdos Signet.
- **In:** Hullbreaker Horror; Galactus, Devourer of Worlds; Tidespout Tyrant; Agent of Treachery; Dovin's Veto; Divergent Transformations; Identity Echo; Reality Scramble.

Dan's settled verdicts (memory note `jace-polymorph-commander`):

- Dack was cut on purpose, which gives up the Dack + Venser + Brainstorm infinite.
- Plan for All Outcomes, Whirlwind of Thought and Cursed Mirror stay.
- Dovin's Veto beats Deification.
- Agent of Treachery beats Elesh Norn, for now.

### Method

1. The stock list (`~/mtg/jace-commander/deck.json`) was copied to
   `~/mtg/tuner-work/w22/jace/deck.json` with `owned_cards` removed, so the
   tune ran with no collection, as in the precon recipe.
2. The tunes followed the precon audit's recipe at v2's budget, one at a time:
   - `deck-tune deck.json --medium paper --budget 40 --max-swaps 30` → `tune-30.json`
   - `deck-tune deck.json --medium paper --budget 40 --max-swaps 8` → `tune-8.json`, v2's size, for a like-for-like comparison
   - `--max-swaps 30` on a copy of v2 itself → `v2/tune-v2.json`, to see how the tuner reads v2's adds once they are in the deck
3. Scoring followed `precon-audit/compare.py`, with v2 in place of a guide:
   - the tuner's cuts and adds that match v2's;
   - v2's cuts the tuner misses;
   - v2's cuts the tuner *protects*, meaning a carer of its main avenue or a card on the commander's lane.

   Script: `~/mtg/tuner-work/w22/jace/score.py`.
4. Card text came from `scryfall-lookup --batch` against the local MTGJSON bulk.
   Interaction claims were checked with `rulings-lookup` and `rules-lookup`
   (CR 2026-09-25).
5. The per-card table is in `~/mtg/tuner-work/w22/jace/report.json`, for a
   shareable page.

### Score

| run | swaps | spent | cuts matching v2 | adds matching v2 | v2 cuts the tuner protects |
|---|---|---|---|---|---|
| max-swaps 30 | 19 (stops early: no actionable issue, safe cut or affordable add left) | $39.98 | 4 / 19 (Omnath, Teferi's Reproach, Ginger, Niv-Mizzet) | 0 / 19 | Dack (combo piece and lane carer) |
| max-swaps 8 | 8 | $29.59 | 3 / 8 (Omnath, Teferi's Reproach, Ginger) | 0 / 8 | Dack |
| old tune, 2026-10-17 (`tune.json`) | 6 of 8 | $10.92 | 2 / 6 (Omnath, Teferi's Reproach) | 0 / 6 | none |

Misses:

- **v2 cuts the tuner keeps (30 swaps):** Dack, Fact or Fiction, Chromatic Lantern and Rakdos Signet. At 8 swaps, Niv-Mizzet as well.
- **v2 adds the tuner never proposes:** all eight.

Both new runs read the deck as FOCUSED. The main avenue is Cheat into play, with
Polymorph fodder as a sub. The commander's lane is Jace, Mass Polymorph,
Synthetic Destiny, Proteus Staff, Nissa and Dack.

### Disagreements

These come from the 30-swap tune unless marked "(8)", meaning the 8-swap tune
only. The 8-swap tune makes the same first eight cuts. Its last four adds
differ (Thassa, The Mindskinner, Sneak Attack and Bruenor instead of Heliod,
Rakdos, Bruenor and Sunspine Lynx) because each add gets a bigger share of the
budget.

**Cuts**

| card | tuner says | v2 says | class | reason |
|---|---|---|---|---|
| Dack Fayden, Helping Hand | protected: a combo piece (Dack + Venser + Brainstorm) and a commander-lane carer | cut | (c) | Dan chose to give up the infinite. The lane read is also wrong: Dack puts creatures onto the battlefield, but each one goes to an opponent ("each opponent gains control"), so it cheats nothing in for you. |
| Cursed Mirror | cut: "ramp over template band" (ramp 15 against a band of 10-12) | keep | (c) | Settled keep. It copies an ETB bomb, and the copied creature's ETB triggers (Cursed Mirror ruling, 2021-04-16). The ramp trim reads only its `{T}: Add {R}`. It sorts non-fixing ramp first (`swaps.cut_candidates` tier 2, `_is_fixing` first), and nothing reads the clone mode. The tuner's own near-miss list has Astral Dragon + Cursed Mirror as an infinite, which is on Dan's next-pass list. |
| Plan for All Outcomes | cut: "interaction over template band" (13 against 8-12) | keep | (c) | Settled keep. Empower Jace creates a Jace planeswalker token with no legendary supertype (CR 701.71a). Jace's −3 exiles "another target planeswalker or creature you control", so Plan supplies a fresh body every turn. The Polymorph fodder lane does not count a planeswalker-token maker as fodder. Plan sits only in the unbuilt Spellslinger avenue, so it is an upgrade slot. The old tune cut it too. |
| Currency Converter | cut: "ramp over template band" | keep | (a) | It is a Polymorph fodder member (it makes 2/2 Rogue tokens) and makes a Treasure only from a discarded land. In the ramp trim, being in a sub-avenue gives no shield: the shield (`focus.commander_cards`) covers the lane's doers, not its fodder. |
| Occult Epiphany | cut: "upgrade card draw" (→ Harvester of Souls) | keep | (a) | A fodder maker (Spirit tokens). The upgrade checks only the template job (card draw), so the swap quietly drops a fodder maker. The reason it is an upgrade slot at all: a card in only a sub avenue is "off the deck's lanes" (`metrics.py`, `elsewhere = … carers_of(mains)`), a rule the precon audit measured on guides. |
| Staff of the Storyteller | cut: "upgrade card draw" (→ Tormenting Voice) | keep | (a) | Same cause as Occult Epiphany. A token maker and repeatable draw engine becomes a one-shot rummage, called "reads better at the job". |
| Ob Nixilis, the Ascended | cut: "upgrade board wipe" (→ Vanquish the Horde) | keep | (a) | The card is in the main avenue as a bomb to flip into, and its wipe destroys only the opponents' tapped creatures. The add is a symmetric sweeper that kills the deck's own fodder and bombs. The upgrade compares the wipe job only, never the main-avenue membership it gives up. |
| Avacyn, Angel of Horror | cut: "off the deck's lanes and few decks play it" (rank 6494, → Hellkite Tyrant) | keep | (a) | The reason is false: Avacyn is listed in the main avenue's cards. Bombs are members of that avenue but not carers, so the upgrade tier condemns them on play rate alone. No guide cuts Avacyn. Caveat: backlog (a) measured a flip-quality read as flat on the 25 precons, so this is one deck's data point. |
| Tamiyo, Upriser Crowned | cut: fed-only, makes room for the Unstoppable Slasher combo | keep | (b) | Two guides cut it. v2 kept it only because it stopped at 8 swaps. |
| The Ur-Sphinx, Memnarch, Darksteel Angel, Akroma | cut as upgrades (→ Sun Titan, Etali, Syr Konrad, Moraug) | keep | (b) | Guides cut each one. The replacements are better-played bombs to flip into. |
| Fatehold Charm | cut: "upgrade interaction" (→ Chaos Warp) | keep | (b) | Chaos Warp is the better answer. The charm's draw mode empowers Jace 2, the same unread fodder as Plan. |
| Lingering Souls, Overlord of the Mistmoors | cut as upgrades (→ Junji, Grave Titan) | keep | (b) | A guide cuts Lingering Souls ("prefers repeatable tokens"). Overlord for Grave Titan trades one token-making flip for another. |
| Fact or Fiction | kept (the last "popular upgrade" tier, rank 703) | cut | (b) | A well-played draw spell. v2's cut was a slot choice. |
| Chromatic Lantern, Rakdos Signet | kept: the ramp trim cuts fixing last | cut | (b) | Both trim three ramp cards (v2: Omnath plus two rocks). The tuner keeps the fixing in a 4-color deck and trims Omnath, Currency Converter and Cursed Mirror instead; those two cuts are rows above. |

**Adds**

| card | tuner says | v2 says | class | reason |
|---|---|---|---|---|
| Identity Echo, Reality Scramble, Divergent Transformations | never proposed | add | (a) | The tuner knows they are polymorph doers: tuned on v2, all three are in `commander_lane_cards` and among the main avenue's carers. But no issue ever sources a lane-doer add. Theme adds are the most-played candidates that pass the fit floor (`swaps._ranked_pool`, `fit_key`), and these rank 15934 / 9488 / 8424. Identity Echo is a 2-guide consensus add. Backlog (m) measured a synergy/play-rate blend on theme pages as negative, so the fix would need a new read: a doer add while the lane is thin, not a reordered page. |
| Agent of Treachery | never proposed; tuned on v2, an upgrade slot (→ Harvester of Souls) | add | (a) | ETB abilities trigger when a polymorph puts the card onto the battlefield (CR 603.6a; Mass Polymorph ruling 2010-08-15), so an ETB steal is the best kind of card to flip into. The tuner reads it on play rate alone (rank 2132). Same caveat as Avacyn. |
| Galactus, Devourer of Worlds | never proposed; tuned on v2, cut for "interaction over" | add | (a) | Its ETB exile counts as an interaction card in the band, so the trim would take v2's bomb back out. The commander-lane shield covers doers, not the bombs they flip into. |
| Hullbreaker Horror | never proposed | add | (a) | More played (rank 278, mana value 7) than bombs the tuner did pick in the same band (Sun Titan 315, Hellkite Tyrant 737). The cause is not isolated: it may miss the fit floor or the theme page. |
| Tidespout Tyrant | listed only as a near-miss with Sol Ring (infinite mana, severity 2) | add | (b) | Infinite mana doesn't end the game, so the near-miss rule rightly ranks it low. Tuned on v2, it becomes an upgrade slot (rank 3930). |
| Dovin's Veto | not proposed; the protection add is Swiftfoot Boots | add | (b) | Boots is a guide add. No settled verdict ranks Veto against Boots. |
| Heliod, Sun-Crowned | add for the ramp trim, $19.16 | not added | (a) | Heliod is not a creature while your devotion to white is under five, so flipping into it misses. It spends half the budget on a lifegain payoff. Likely cause: an add for a band trim goes to the first viable avenue (Cheat into play), whose membership doesn't check that the card is a creature once on the battlefield. |
| Thassa, God of the Sea (8) | add for the ramp trim | not added | (a) | Same as Heliod, with devotion to blue. |
| The Mindskinner (8) | add for the ramp trim | not added | (a) | It prevents the damage your sources would deal to opponents. Prevented damage is not dealt (CR 615.1a), so Unstoppable Slasher, the tune's own first add, never triggers, and the combo it was added for dies. Adds are picked per issue, with no check of the whole set of adds for anti-synergy. |
| Sunspine Lynx | add for the interaction trim | not added | (a) | "Players can't gain life" works against Heliod, which the same tune adds. Same cause as The Mindskinner. |
| Dreamtide Whale | add for dead weight ("stronger on-theme card") | not added | (a) | Vanishing 2 means it enters with time counters however it arrives (CR 702.63a), so it is sacrificed two upkeeps after a flip. |
| Bruenor Battlehammer | add for a band trim | not added | (a) | An Equipment payoff in a deck whose only Equipment is the Boots the tuner adds. A 5/3 is a weak card to flip into. |
| Tormenting Voice, Vanquish the Horde | upgrades | not added | (a) | See Staff of the Storyteller and Ob Nixilis above. |
| Unstoppable Slasher | add: completes Archfiend of Despair, a game-ender | not added | (b) | A real two-card game-ender, but a 3-mana 2/3 is a weak card to flip into. The old tune proposed it too. |
| Swiftfoot Boots | add: protection short (3 of ~5) | not added | (b) | A guide add. |
| Rakdos, Lord of Riots, Sun Titan, Etali, Grave Titan, Junji, Moraug, Hellkite Tyrant, Harvester of Souls, Syr Konrad, High-Society Hunter, Chaos Warp, Sneak Attack (8) | upgrades and band-trim adds | not added | (b) | Defensible bombs or answers. A polymorph never casts Rakdos, so its "can't cast" restriction doesn't apply (Rakdos ruling, 2020-11-10). Sneak Attack cheats from hand while the plan wants bombs left in the library. |

Count, one card at a time as in `report.json`: 4 matches, then 19 (a), 27 (b) and 3 (c) disagreements. None of the (c) rows is new: the
memory note's verdicts already named all three, and the tuner has no read that
would honour them.

### What the tuner would do to v2

Tuned on v2 (30 swaps, $39.95), the tuner would undo part of Dan's tune:

- It cuts Galactus ("interaction over") and Agent of Treachery (upgrade slot).
- It lists Tidespout Tyrant as an upgrade slot.
- It cuts Plan for All Outcomes again, and Whirlwind of Thought too, both settled keeps.
- It cuts ten of the eleven Polymorph fodder members (all but Grand Crescendo)
  for creatures and spells.

It does count v2's three polymorph adds as commander-lane doers, which shields
them.

### Then and now

**Then (2026-10-17):** the tuner read the deck as SPREAD-THIN over Historic,
Cantrips, Combat, Big creatures, Cost reduction and Lifegain. It made 6 of 8
swaps for $10.92. Two of its cuts matched v2's and none of its adds. Its adds
were cheap aggro: Kari Zev, Lost Jitte, Patchwork Crawler, Deepchannel Duelist,
Hidden Strings and Unstoppable Slasher.

**Now:** it reads the deck as FOCUSED on Cheat into play, with Polymorph fodder
as a sub and the polymorph pieces as the commander's lane. At 8 swaps it spends
$29.59 and matches 3 of v2's 8 cuts. At 30 it spends $39.98 and matches 4 of 19.
Its adds are now bombs to flip into (Sun Titan, Grave Titan, Etali, Hellkite
Tyrant, Junji) rather than 2-drops, but still none of v2's.

**What hasn't moved:** Plan for All Outcomes is still cut, Unstoppable Slasher
is still the first add, and the lane's own doers (Identity Echo, Reality
Scramble, Divergent Transformations) are still never proposed.

### Candidate fixes, for Dan to choose

These are evidence only; no code changed.

1. **Fodder is unshielded.** A token maker in the commander's own sub avenue is
   an upgrade or trim slot, and the job-only upgrade drops its fodder. Four of
   the 30-swap cuts are fodder makers.
2. **No add path for lane doers.** The tuner recognises Identity Echo and the
   other v2 polymorphs as doers but never adds one.
3. **Two misreads of what a card is.**
   - A flip into a God (Heliod, Thassa) misses, because the God is not a creature on the battlefield.
   - Dack's cheated creatures go to the opponents, yet it reads as a lane carer.
4. **Adds are never checked against each other.** The Mindskinner sits beside
   Unstoppable Slasher, and Sunspine Lynx beside Heliod.
5. **Two template reads miss what the card is for.** Galactus's ETB counts as
   band interaction; Plan's and Fatehold Charm's empower Jace is not read as
   fodder.

### Against the guides (2026-10-29, the reference from now on)

Dan's correction: v2 is not a gold standard. It came from an older version of
this tuner plus AI agents, not from play-testing, and the three "settled
verdicts" above (Dack cut on purpose, Plan for All Outcomes and Cursed Mirror
kept) were agent suggestions too. The reference is the precon's published
upgrade guides (`precon-audit/MultiverseReforged_FRC.md`: two Flipside Gaming,
one Draftsim). Scored by the precon audit after the guide-row fix, at the guides'
budget ($111.70) and 30 swaps (29 made):

| | matching the guides |
|---|---|
| cuts | 14 of 22 |
| adds | 3 of 30 (Swiftfoot Boots, Archfiend of Depravity, Nezahal, Primal Tide) |

What the guides show the tuner missing, by cause:

1. **No search for polymorph fodder** (10 adds): Raise the Alarm, Search for
   Glory, Shadow Summoning, Loyal Apprentice, Felidar Guardian and others.
2. **The mana-value gate blocks flip targets** (7): Austere Command, Rune-Scarred
   Demon, Toxrill, Brainstealer Dragon, Marang River Regent, Summon: Bahamut. A
   polymorph deck never casts its flip targets, so their cost shouldn't gate them.
3. **Ranked too low** (7): Identity Echo, Deification, Agent of Treachery, Terror
   of the Peaks, Sanctuary Warden, Tempt with Bunnies, Fable.
4. **Combo protection over the guides**: Dack, Venser and Brainstorm are
   protected as an infinite; the guides cut all three.

The card-read errors in the tuner's own picks stand whatever the reference:
Heliod, Thassa (Deep-Dwelling) and Purphoros are flip targets that aren't
creatures without devotion 5; Dreamtide Whale's vanishing; fodder makers
(Currency Converter, Occult Epiphany, Staff of the Storyteller) traded by
job-only upgrades. The review page's Jace tab shows this view.

## Fynn, the Fangbearer

A mono-green Competitive Brawl deck on Arena: 100-card singleton, 1v1, 25 life,
no free mulligan. Fynn wins by poison. Each time a creature with deathtouch
deals combat damage to a player, that player gets two poison counters, and ten
poison counters lose the game (CR 704.5c). The deck runs about 30 cheap
deathtouch bodies plus pump and hexproof instants. v4 (2026-08-27) is the start
list, and v6 is Dan's live list after two rounds of play-testing. The diff, from
`lists/RECOMMENDED-fynn-v{4,6}.txt`, is 13 swaps:

- **Out:** Toxic Scorpion, Thornweald Archer, Venomsac Lagac, Underdark Basilisk, Heir of the Wilds; Ranger's Guile, Saved by the Shell, Bombadil's Song, Swiftfoot Boots; Tenderize, Warg Tactics; Heritage Reclamation, Glimpse of Nature.
- **In:** Super-Adaptoid, Allosaurus Shepherd, Venerated Rotpriest; Piercing Exhale, Horrific Assault, Meltstrider's Resolve, Natural State; Audacity, Lightning Greaves, Vexing Bauble, Chrome Mox; Inkmoth Nexus and a Forest (36 lands).

The brief summarised v5 slightly differently from the files: Frog Butler is
already in v4, and Escape Tunnel is in neither list. The files were taken as
ground truth.

Dan's settled verdicts (memory notes `fynn-deck-philosophy`, `competitive-brawl-project`):

- Judge every card as "a cheap printed-deathtouch body, or a protection or pump instant of mana value 2 or less".
- Dead weight is any creature without deathtouch, any spell that grants deathtouch, and anything at mana value 3 or more.
- The ~10 bites are the deck's removal, so keep them all. A creature dealt damage by a deathtouch source is destroyed (CR 702.2b, 704.5h), so a bite from a 1/1 deathtouch body kills anything.
- Cavern of Souls and Key to the Side-Door are untouchable. Super-Adaptoid is not a vanilla body.

### Method

1. `parse-deck --format competitive_brawl` on v4 (it has no section headers),
   then `set-commander`. `mark-owned --bulk-data` marked ownership against
   `~/mtg/radagast-brawl/collection2.json` (mtga-import, 2026-08-24): 47 of 69
   cards owned. Files are in `~/mtg/tuner-work/w24/fynn/`.
2. The 16:46 commit (the Competitive Brawl legality fix) touched
   `membership_floor.py`, `lanes/` and `crosswalk/reads.py`, which are inside the
   signals index's hash. So the 16:34 sidecar was stale, and the tunes ran
   against a private `MTG_SKILLS_CACHE_DIR` (`w24/cache`), where the index
   rebuilt once. The real cache was left alone.
3. Tunes, one at a time, with the wildcards Dan had when he built v5 (2 M / 0 R / 33 U / 27 C):
   - `deck-tune deck.json --medium digital --wildcards mythic=2,rare=0,uncommon=33,common=27 --max-swaps 13` → `tune-13.json` (v4→v6's swap count)
   - the same at `--max-swaps 30` → `tune-30.json`
   - `deck-tune` has no collection flag (below), so a third run, `tune_owned.py`, wraps the CLI's `tune` with the whole collection as `owned=`, which is deck-forge's path → `tune-owned-30.json`
   - `--max-swaps 30` on v6 itself → `v6/tune-v6.json`
4. Scoring followed `precon-audit/compare.py`, with v6 in place of a guide
   (`w24/fynn/score.py`).
5. Card text came from `scryfall-lookup --batch`. Legality and Arena rarity came
   from `Format` and `CardPool.rarity_index(arena_only=True)` (`cbcheck.py`).
   Rulings came from `rulings-lookup` and rules from `rules-lookup` (CR 2026-09-25).
6. The per-card table is `~/mtg/tuner-work/w24/fynn/report.json`.

### Score

| run | swaps | wildcards spent | cuts matching v6 | adds matching v6 | v6 cuts the tuner protects |
|---|---|---|---|---|---|
| max-swaps 13 | 6 (stops early: out of safe cuts) | 2 M / 1 U / 3 C | 2 / 6 (Tenderize, Warg Tactics) | 0 / 6 | none |
| max-swaps 30 | the same 6 | 2 M / 1 U / 3 C | 2 / 6 | 0 / 6 | none |
| max-swaps 30, collection passed | the same 6 | 2 M / 1 U / 1 C | 2 / 6 | 0 / 6 | none |

- **v6 cuts the tuner keeps:** all 11 others. Five are printed-deathtouch bodies, four are protection, and two are cantrips.
- **v6 adds the tuner never proposes:** all 13.

The tuner reads the deck as FOCUSED. The main avenue is Deathtouch matters (32
cards, with Fynn its one carer). The subs are Grant protection, Targeted keyword
grant and Cantrips. All six swaps answer a single issue, "interaction over by 6
(16/8-10)", and each one cuts a bite.

The two matches are the right cards for the wrong reason. v5 swapped Tenderize
for another bite (Piercing Exhale), and v6 swapped Warg Tactics for another
answer (Natural State). The tuner trims both as excess interaction.

### Disagreements

**Cuts**

| card | tuner says | v6 says | class | reason |
|---|---|---|---|---|
| Sylvan Smite, Hard-Hitting Question, Master's Rebuke, Rocky Rebuke | cut: "interaction over template band" (16 against 8-10) | keep | (c) | The bites are the deck's removal, a settled verdict. The Deathtouch matters lane counts only the bodies, so the 16-card interaction row isn't read as the lane: `lane_row` (`tune.py`) needs half the row's members in the lane, and only Kappa Tech-Wrecker is. The band is the Commander family's 8-10 for a 1v1 aggro deck. |
| Toxic Scorpion, Thornweald Archer, Venomsac Lagac, Underdark Basilisk, Heir of the Wilds | kept: printed-deathtouch lane members | cut | (b) | These are the bodies the philosophy wants, and v6 cut the weakest of them to make room. The tuner can't rank one body against another. In a 1v1 game play rate never condemns (`calibration.playrate_condemns`), and the lane-upgrade pool holds only the lane's doers (Fynn, Infectious Bite, Kappa Tech-Wrecker). |
| Ranger's Guile, Saved by the Shell, Bombadil's Song | kept: Grant protection carers | cut | (b) | Dan trimmed redundancy among about 18 protection cards. The tuner has no protection-over row (its protection target is 0 here). |
| Swiftfoot Boots | kept | cut | (b) | A like-for-like swap for Lightning Greaves, which Dan owns. |
| Heritage Reclamation, Glimpse of Nature | kept: Cantrips carers | cut | (b) | Slot choices for Chrome Mox and Venerated Rotpriest. |

**Adds**

| card | tuner says | v6 says | class | reason |
|---|---|---|---|---|
| Wurmcoil Engine, Hornet Queen | add for the interaction trim, a mythic wildcard each | not added | (c) | Mana value 6 and 7, against Dan's rule of under 3. A trim's add deepens the commander's lane (`issues.py`, `role_over`) and is ranked by fit, then play rate. Nothing gates mana value for an aggro deck at average 1.56. The scorecard even raises "curve: thin top-end" as an issue. |
| Gift of the Viper, Horrid Vigor | add for the interaction trim | not added | (c) | Spells that grant deathtouch, which the philosophy calls dead weight. Gift (a deathtouch counter, CR 122.1b) was a v3 add that v4's play-testing removed. |
| Poison Dart Frog | add for the interaction trim | not added | (c) | A creature without printed deathtouch: it pays {2} to gain it. |
| Cryptolith Fragment // Aurora of Emrakul | add for the interaction trim | not added | (a) | Read as a deathtouch body, but the deathtouch is on the back face. That face transforms only if each player is at 10 or less life at upkeep (ruling 2025-01-24), which a poison deck rarely arranges. The front is a mana value 3 rock that enters tapped. Lane membership counts a back-face keyword as if the card had it. |
| Piercing Exhale, Horrific Assault, Meltstrider's Resolve | never proposed | add | (c) | Bites, or a fight Aura. While the row reads as over, the trim never adds the role it trims, so a bite can never come in. Same cause as the cuts. |
| Natural State | never proposed | add | (c) | It destroys an enchantment of mana value 3 or less: the answer to the ability-stripping Auras (Unable to Scream, Witness Protection) that Dan names as his real pain. The band reads it as one more removal spell over the row. |
| Super-Adaptoid | never proposed | add | (b) | Not a printed-deathtouch body: it copies keywords as counters off a target creature. Dan values it from play, and the tuner has no read for it. |
| Audacity | never proposed | add | (b) | The scorecard flags "Combat tricks / pump (9) under-supported — commit more", which points the right way. But no cut pool pays for it (no filler, no low-value cards, no upgrade slots). |
| Lightning Greaves | never proposed | add | (b) | The Boots swap above. |
| Allosaurus Shepherd, Vexing Bauble | never proposed | add | (b) | Meta calls (no counterspells; no free spells). The meta read is skipped: Untapped has 4 Fynn lists and 121 matches, under the 250-match floor. |
| Inkmoth Nexus, Forest | never proposed | add | (b) | Tune adds no lands by design (the land tooling's job). 34 lands passes the band (34-41). Dan found 35 light for the four-mana recast. |
| Chrome Mox, Venerated Rotpriest | never proposed | add | (b) | Both rare, and the v5-time budget has 0 rare wildcards. v6's last three swaps used September's budget (3 M / 3 R). |

Count, one card at a time as in `report.json`: 2 matches, then 1 (a), 20 (b) and
13 (c) disagreements. Every (c) row comes from one read: the deck's ~10 bites,
and the answers beside them, count as generic interaction against a Commander
band of 8-10.

### What the tuner would do to v6

Tuned on v6 (30 swaps, 10 made, 2 M / 3 U / 5 C), it reads interaction as
"over by 8 (18/8-10)" and trims eight cards. Four are v6's own adds: Piercing
Exhale, Horrific Assault, Meltstrider's Resolve and Natural State. Four are bites
v6 kept. Their replacements are Wurmcoil Engine, Hornet Queen, Gift of the Viper,
Poison Dart Frog, Cryptolith Fragment, Horrid Vigor, Oakhame Adversary (mana
value 4) and Hunter's Blowgun (an Equipment that grants deathtouch).

It also cuts two more cards as "feeds only avenues nobody built toward":

- Allosaurus Shepherd, for Arcane Signet (ramp short).
- Venerated Rotpriest, for Inspiring Call (card draw short, mana value 3).

The Rotpriest cut is a bug (class (a)). The same scorecard lists Rotpriest in
`commander_lane_cards` and `commander_lane_carers`, and also in `fed_only_cards`
and `filler_cards`. It poisons an opponent whenever one of the deck's ~18
targeted instants targets a creature, so the lane read is right. The filler
re-bucket is what's wrong. In `metrics.py`, the low-value tier exempts
`lane_doers`, but `fed_only_classes` does not. So a commander-lane carer whose
only avenue is fed (Proliferate) is turned into filler and cut first, before any
lane protection applies.

### Then and now

**Then (2026-09-22, on v5, `2026-09/fynn/tune.json`):** the tuner read the deck
as SPREAD-THIN and made 3 swaps:

- Attercop → Marketback Walker
- Sylvan Smite → Lost Jitte ("interaction over by 8")
- Serpent Specialist → Spider-Slayer ("≈0 closers")

The August runs in `wizard-v5/` made none.

**Now:** it reads FOCUSED on Deathtouch matters, the commander's own lane. The
Commander lane correctly holds Fynn, Infectious Bite and Kappa Tech-Wrecker (and
Rotpriest on v6). Its adds are now deathtouch cards rather than off-plan
equipment.

**What hasn't moved:** the bites are still trimmed as excess interaction, and
the deck still counts zero closers.

### What's specific to Competitive Brawl

- **Legality is right.** No proposed add is banned or illegal (`Format.legality`
  is "legal" for all of them). Probes show the 2026-10-12 list working:
  - Lutri is banned outright.
  - Oko, Spider-Man 2099 and Nadu are `banned_as_commander`: legal in the 99, refused as commander.
  - Fynn is an eligible commander.
- **Rarity costs are right.** Each add was charged its Arena rarity, which can
  differ from paper:
  - Hornet Queen and Wurmcoil Engine charge mythic (paper's lowest printings are uncommon and rare).
  - On v6's side, Inkmoth Nexus is mythic on Arena (Dan spent a mythic on it), and Natural State is uncommon on Arena but common on paper. That matches v6's recorded "1 R / 1 U / 1 C".
- **Owned cards are free only when the tuner is told about them.**
  - `deck-tune` has no `--collection` flag, and `deck_tune.py` calls `tune()` without `owned=`. `mark-owned` writes `owned_cards` for the deck's own cards, which the swap purse never reads.
  - So the CLI charged a common wildcard each for Gift of the Viper and Poison Dart Frog, both of which Dan owns.
  - With the collection passed as `owned=` (deck-forge's `engine.owned_collection`), both read `covered_by: owned` at cost 0, and commons spent fell from 3 to 1.
- **The game is read right; the template isn't.**
  - The life total (25) and 1v1 come through (`wincons.life`, `multiplayer: false`), and play rate rightly never condemns a card in a 1v1 game.
  - But the bands are the Commander family's (interaction 8-10, ramp 8-10, card draw 10-12, board wipes 1-2), built for 4-player paper.
  - A 1v1 aggro deck with average mana value 1.56 reads as short on ramp, card draw and board wipes, and over on interaction.
- **No meta read.** The Untapped Brawl ladder cache (2026-10-14) has too few Fynn
  matches, so `--meta auto` skipped it. Nothing stood in for Dan's meta-driven
  adds (Shepherd, Bauble, Natural State).
- **The swaps note is misleading.** It reads "set a wildcard budget to allow
  crafting" even when one is set and mostly unspent (`swaps.py`, `allow_buys`
  keys only on the mode).

### After the bite fix (2026-10-29)

Fix 1 below shipped. A bite now carries its own ident,
`damage_equal_power|you|bite` (`crosswalk.is_bite`: a creature of yours deals
damage equal to its own power to another creature). A keyword lane on deathtouch
counts it as a member, and counts every fight (`fight_makers|you|`) too
(`signal_specs/core.py`, `_KEYWORD_LANE_IDENTS`). The rules behind it: a
creature dealt damage by a source with deathtouch is destroyed (CR 702.2b,
704.5h), and in a fight each creature deals damage equal to its power to the
other (CR 701.14a). The bite's dealer is the creature, not the spell (Bite
Down's and Rabid Bite's rulings: "the creature you control won't deal
damage"). Repentance (the creature hits itself), Mutiny (an opponent's creature
deals the damage), and Corpse Explosion and Dead Reckoning (the spell deals the
damage) are not bites.

Deathtouch matters went from 32 deep to 41 on v4. Interaction is still "over by 6
(16/8-10)", but the row is now the lane's (`lane_row`). The issue reads "mostly
the commander's own lane, not a trim" and is advisory, so nothing trims it.

| run | before: swaps | after: swaps | after: cuts / adds matching v6 |
|---|---|---|---|
| v4, max-swaps 13 | 6, all bites or Warg Tactics for the interaction trim | 0 | 0 / 0 |
| v4, max-swaps 30 | the same 6 | 0 | 0 / 0 |
| v6, max-swaps 30 | 10: 8 interaction trims (four of them v6's own adds) and 2 fed-only cuts | 2: Allosaurus Shepherd → Kura, the Boundless Sky and Venerated Rotpriest → Sword of Feast and Famine (fed-only cuts, fix 4) | 0 / 0 |

No bite is cut on any run, and no Wurmcoil Engine, Hornet Queen, Gift of the
Viper or Cryptolith Fragment is added. With the trim gone, v4 has no cut pool
left (no filler, no low-value or upgrade slots in a 1v1 game), so the tuner now
leaves the deck alone. The two "matches" in the Score table were Tenderize and
Warg Tactics trimmed as surplus interaction (right card, wrong reason), so losing
them is the fix working.

Side effect on v4: Infectious Bite drops out of `commander_lane_cards`. It is a
bite now, so the poison lane's members are almost all Deathtouch matters
members, and the poison lane folds into Deathtouch matters (`metrics.focus`,
`same_members`). Its doers then stop counting as the lane's. Nothing on these
runs cuts it (v6 keeps it as a doer, because Rotpriest keeps the poison lane
apart). See the backlog.

Both precon sets are unchanged. The 25 precons give 721 swaps, 330 guide cuts
and 109 guide adds; the held-out ten give 297 / 139 / 34. `cmp.py` shows no
difference against either `misses-r-guidefix.json`, because none of those
commanders holds a deathtouch lane.

### Candidate fixes, for Dan to choose

These are evidence only; no code changed, except fix 1 (above).

1. **Shipped 2026-10-29: the bites aren't part of the deathtouch lane.** A "target creature you
   control deals damage equal to its power" spell is removal only because the
   lane's bodies have deathtouch (CR 702.2b). If the lane counted them as members,
   `lane_row` would make the interaction row a fact to report rather than a trim.
   This one read accounts for all 13 (c) rows.
2. **The closer read has no poison.** `is_wincon_card` (`metrics.py`) checks for
   game-ending effects, extra combats, team pumps, reach and big evasive bodies.
   It never reads Fynn's two poison counters (CR 704.5c; Fynn's ruling: Fynn
   needn't be on the battlefield for the tenth), toxic (CR 702.164c) or infect.
   So the deck has "≈0 closers" at severity 5.
3. **A trim's add has no mana-value gate.** An aggro deck at average 1.56 gets
   mana value 6 and 7 bombs, and "thin top-end" is raised as an issue.
4. **The fed-only re-bucket ignores lane doers.** `fed_only_classes`
   (`metrics.py`) should exempt `lane_doers`, as the low-value tier does. On v6
   it cuts Venerated Rotpriest, a lane carer.
5. **Lane membership reads a back face** (Cryptolith Fragment's Aurora) and an
   activated grant (Poison Dart Frog) as deathtouch bodies.
6. **The CLI can't see a collection.** A `--collection` flag passing `owned=`
   would make the CLI price adds the way deck-forge does.
