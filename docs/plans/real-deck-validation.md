# Real-deck validation: the tuner against hand-tuned decks

The 25-precon audit (`precon-audit-2026-10-18.md`) compares the deterministic
tuner (`deck-tune`) with published upgrade guides. This doc compares it with
decks Dan tuned himself and played, where the verdicts are his own and settled.
It records measurements only. No tuner code changed. A finding marked (a) below
is a candidate fix for Dan to choose, not a decision.

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

## Fynn

*Placeholder: another agent adds this section (Competitive Brawl, Fynn v6).*
