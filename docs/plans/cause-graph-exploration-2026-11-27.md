# Is the tuner's data model wrong? Findings of the cause-graph exploration (2026-11-27)

The experiments ran on the local branch `explore/cause-graph` and changed nothing in the
shipping tuner. The plan and Dan's eleven decisions are in the plan file named at the end;
per-experiment result files sit in `~/mtg/tuner-work/cause-graph/`. What follows from it is
under "Next steps".

## The question

The tuner describes cards with hand-written signals and lanes, and is tuned toward upgrade
guides written by people. Dan's suspicion: both are the wrong foundation. Could card fit be
derived from the rules and the cards, and could deck quality be measured against something
other than opinion?

## Short answer

Three hand-made things were tested, and they got three different answers.

| Hand-made thing today | Proposed replacement | Verdict | Evidence |
|---|---|---|---|
| Lane membership and the "wants" tables | A graph of what each card causes and what each card waits for, joined by rules steps | **Works. Extend.** | E1, E2 |
| Template numbers (lands first) | A simulation of the deck's own flow of mana and cards | **Works for lands, with one measured input. Extend.** | E5 |
| The guides as the yardstick | Phase's engine comparing different decks | **Does not work.** A score fitted on measured results does, partly | E3 |
| | Phase's engine comparing versions of one deck | **Works for like-for-like swaps** (added after Dan's question; limited only) | E7 |
| | Card vectors learned from results | **Not as tested.** Card-level gain is small; pairs show nothing; deck-level gain is real | E6, E3 |

In one paragraph: the suspicion about membership is right and fixable, but membership is not
where the tuner loses. A derived graph says which cards connect and cannot say which
connections matter. That needs a score. The engine cannot score one deck against a different
deck with its current AI; a model fitted on real results can, where real results exist. The
engine can score a deck against its own variants: with the style held fixed, it ranked better
and worse builds of 16 decks in the right order, and a real 3-point difference shows in
minutes. That is the tuner's own question (is the tuned deck better than the one it started
from), so the next test is the same design on Brawl. For casual Commander no measured results
exist, and that stays the open problem.

## What was run

| | Question | Result |
|---|---|---|
| Step 0 | Rebuild the shared phase install at the pin | **Failed and was rolled back.** The repo's `ai-duel` patch no longer fits v0.133.0. Ported (on main since `b02fa9eb`); an isolated v0.133.0 build was used instead |
| E2 | Does phase's own analysis already hold the graph? | No. It is a loop finder: 45 of 241 effect types, no object filters, no "whose", nothing exported. Ours is built over the corrected trees |
| E1 | Can membership be derived for "a creature dies"? | Pass with caveats. 29 hand rows, no card names, about 97% of the lanes' true members |
| E5 | Can land count fall out of a simulation? | Within one land of the measured best in three curve bands, equal in two |
| E6 | Do mechanics-built card vectors predict results in a set never seen? | Not passed. Small edge on cards, nothing on pairs |
| E3 | Does the engine rank decks the way real results do? | **Not passed.** Order wrong; 2.2 ± 3.5 engine points for 12.5 real points |
| E3, fallback | Does a fitted model rank the same decks? | Yes: 7.7 points between its bottom and top tenth, against a ceiling of 12.5 |
| E7 | Does the engine rank better and worse builds of one deck? | **Passed.** Right order over five builds; best minus worst 19.5 ± 1.5 engine points, the right way in 16 of 16 decks |

## Layer 1: the cause graph (E2, E1)

**What it is.** Each card gets two lists read off its trees: what it can cause and what it
waits for. A short table of rules steps joins them (destroy, sacrifice, lethal damage, fight,
toughness 0 and a direct move all end in "dies"). Fit is a link between one card's cause and
another's wait. A link carries facts (route, whose creature, one or all, certain or not, how
it is delivered, repeatable or not) and no verdict.

**What happened.**

- For the dies family the whole read is 29 hand-written rows: six rules steps, fifteen phase
  effect names, four keywords whose own rule sacrifices a creature, four fallbacks for nodes
  phase could not parse. Every rule number came from `rules-lookup`. No card is named.
- Against today's lanes, over 32,573 Commander-legal cards: derived 5,263 cards, lanes 6,086,
  both 4,465.
  - Lanes only, 1,621: about 1,350 are the lanes being wider than "dies" (exile, bounce,
    noncreature targets). About 110 to 150 are real misses from four generic gaps (a sacrifice
    paid as an alternative cost, "its controller sacrifices it", emblems, unparsed nodes).
  - Derived only, 798: 404 kill only the card itself, 419 are toughness reductions. True by
    the rules; the lanes dropped them as relevance calls. In a sample of 22 others, 4 were
    false, all from a filter phase left empty or a node it did not parse.
- No disagreement sampled was a definition dispute. Each was a rules-true link the lanes chose
  to drop, a lane wider than the event, or a parse gap.
- It widens today's need read a great deal: 4,160 cards can kill one of your own creatures and
  the need read admits 1,313 of them. Of the 943 that do it for certain and repeatably, it
  admits 721.
- Phase's own graph cannot stand in: it never reads a trigger's object filter, so "a creature
  you control dies" and "any creature dies" are the same thing to it, and damage never leads
  to a death.

**Caveats.**

- The read took six rounds of fixes in an afternoon (composite costs, who sacrifices, land
  subtypes read as creatures, granted abilities, static changes, keywords). Each was a generic
  shape fixed once. There will be more.
- 2,623 of today's 4,371 death feeders are token makers: bodies to kill, not causes. That is a
  second kind of link (a card that makes objects another card's cost or filter needs) and it
  is not built.
- Waits cover triggers only. Conditions and counts ("if a creature died this turn") are the
  lanes' extra 279 demand cards.
- The held-out precons could not grade this family: 3 of the 20 commanders wait for a
  sacrifice and none for a death.
- 4,160 feeders is not a shortlist. The graph is the easy half.

**Verdict: extend.** Membership is derivable, and a boundary dispute becomes a question about
one rule, settled once. Start with the need read's supply side, one event family at a time,
each with a census against the keys it replaces. Lanes stay as named views. Draft ADR:
`cause-graph-drafts/adr-draft-cause-graph.md`.

## Layer 2: the flow model (E5)

**What it is.** A deck simulated alone over many shuffles, scored by what it gets to do. If
that works, numbers the template sets by hand become outputs.

**What happened** (FDN draft, 742k games, the repo's own solo model extended to record mana
spent each turn):

| curve | simulated best, plain "mana spent" | simulated best, mana weighted by its measured worth per turn | measured best |
|---|---|---|---|
| low  | 14 | 15 | 15 to 16 |
| mid  | 15 | 16 | 16 (17 equal) |
| high | 16 | 17 | 16 (17 close) |

- The plain objective gets the slope right and sits one land low.
- The weights are measured, not chosen: a fit of who won on mana spent each turn, from
  17Lands' per-turn replay data. Mana on turn 1 is worth 0.48, turns 2 and 3 0.29, turn 4
  0.23, turn 5 0.17, later turns about 0.14. Early mana is worth two to three times late mana.
- Real players in every band mostly run 17. Low-curve decks do 1.7 points better at 16.
- Where the solo model is wrong, turn by turn: it overspends by 10 to 15% on turns 1 to 6 (it
  never holds a card back) and underspends by 15 to 30% from turn 8 (no abilities, no card
  draw, nothing to sink mana into).

**Verdict: extend.** One template number fell out of a simulation plus one measured input.
The two named gaps are what a model of cards as converters would close, and 17Lands' replay
data is a turn-by-turn record to check it against. Ramp, draw and interaction counts were not
attempted; interaction needs an opponent.

## Layer 3: the yardstick (E3, E6)

### The engine as judge: not passed

72 real FDN draft decks in three groups (bottom tenth, middle, top tenth by the measured
strength of their cards), each played 160 games by phase's AI against a fixed field of eight.

| group | real win rate | engine win rate |
|---|---|---|
| low  | 50.7% | 42.6% ± 2.3 |
| mid  | 57.2% | 46.9% ± 2.0 |
| high | 63.2% | 44.8% ± 2.6 |

- Dan's bar: right order, and two decks a real 3 points apart separable in about an hour. The
  order is wrong, and the separation would take about eleven hours.
- The engine's ranking is not noise. Two halves of the field agree on it (0.79). It follows
  the number of creatures in the deck (+0.49) and runs against the deck's real record (-0.34).
  Its worst deck is a top-tenth blue-black deck with nine instants, three of them
  counterspells.
- So the rules engine is fine and the pilot is the limit. An engine result says how well this
  AI plays the deck.
- The first design of this test was wrong and was dropped: it grouped decks by their own draft
  record, which is mostly luck (those groups were about 1 point apart in true strength).

### The engine on versions of one deck (E7): passed

Dan's question after E3: the realistic test is versions of the deck being tuned against a
fixed field. Run as asked, on 16 middling FDN decks. Each got two worse builds and two better
builds by like-for-like swaps (same colour, creature for creature, mana value within one; a
card is better only if both its win rate when seen and its lift are higher), and each build
played 240 games against a fixed field of twelve with the same seeds. 23,040 games, two hours.

| build | engine win rate | change from the drafted deck | estimated real change (index / lift) |
|---|---|---|---|
| 6 points worse | 43.6% | -8.1 ± 1.0 | -6.1 / -10.9 |
| 3 points worse | 47.6% | -4.1 ± 1.2 | -3.1 / -5.7 |
| as drafted | 51.7% | | |
| 3 points better | 56.9% | +5.2 ± 1.4 | +3.0 / +6.9 |
| 6 points better | 63.2% | +11.4 ± 1.4 | +6.1 / +14.2 |

- The order is right, and best minus worst is the right way in every one of the 16 decks.
- Dan's bar: two builds a real 3 points apart take 7 minutes of compute to separate by one
  estimate of the real change and 29 by the other. The bar was an hour; E3's figure for
  different decks was eleven hours.
- It is card quality the engine is following, not size: it rewards better noncreature spells
  as much as better creatures (1.8 ± 0.3 against 1.4 ± 0.2 engine points per real point), and
  the swaps' change in mana value and creature power adds nothing.
- A sixth build tested the pilot's taste: three noncreature spells out, three no-better
  creatures in. No steady tilt (eight decks up, seven down, +3.1 ± 1.6 on average), but two
  decks gained 17 and 18 points, more than their best-cards build gained. The pilot's blind
  spots are real, large where they occur, and specific to the deck.
- Why this passes where E3 failed: with the deck's style fixed, the pilot's handicap for that
  style is on both sides of the comparison and cancels. E3's strongest group also had the
  fewest creatures. The engine prices a card against a like card well and a style against
  another style badly (a reading, not a measurement).
- The real change is an estimate from card results; nobody played these builds. Detail:
  `~/mtg/tuner-work/cause-graph/e7-deck-versions.md`.

### The fallback: a score fitted on measured results

Dan's decision 3 named this in advance. The outcome model from E6, trained on five other sets
and never shown an FDN result, scores a deck from its card list. All 53,912 FDN decks in the
skill band, cut into tenths by score:

| score | bottom tenth wins | top tenth wins | spread |
|---|---|---|---|
| cost, rarity, type and size only | 55.0% | 60.3% | 5.3 |
| plus parsed mechanics and amounts | 53.5% | 61.2% | 7.7 |
| measured on FDN itself (the ceiling) | 51.1% | 63.6% | 12.5 |

- A score that has never seen the set recovers about 60% of what the set's own data gives, and
  costs nothing to run.
- One held-out set, one run. It is a lead until repeated on the other five sets.

### Card vectors (E6): not passed as tested

- Card level: with mechanics the model beats plain features (cost, rarity, type, size) on a
  never-seen set in 6 of 6 sets, by margins too small to matter (AUC 0.6237 against 0.6227 on
  FDN). Most of what predicts a limited card is its cost, rarity and size.
- Pair level: the learned vectors do not predict which pairs do better together in an unseen
  set (rank correlation from -0.13 to +0.06). The measured pair effects are themselves noisy,
  so this test had little power.
- Deck level (from E3's fallback): mechanics widen the spread by 45%. Mechanics seem to matter
  more summed over a deck than card by card. Unconfirmed.
- Five training sets is thin, and limited is where synergy matters least. 17Lands has about
  thirty sets.

**Verdict: replace the engine with a fitted score; keep the engine for other jobs.** It can
still check that a line works by the rules and count what a deck does (the E4 idea: commander
triggers per turn). "Improve the pilot" is a backlog draft.

## What this means for the three goals

Dan's order: a deck score that needs no guide, then derived fit judged by it, then an
optimizer.

1. **The score.** Two partial ones exist for limited. Between different decks: a fitted model
   (60% of the ceiling). Between versions of one deck: the engine (E7), which is the
   comparison a tuner needs. Neither exists for Commander. Dan's bridge was Arena Brawl through
   the engine; it is open again in E7's form: builds of a Brawl deck made from cards with
   better and worse measured results under that commander, ranked by the engine. Untapped's
   Brawl rows are aggregates per list and per card, far thinner than 17Lands. And casual
   Commander (four players, a social power level) has no measured results anywhere, so
   whatever score is built reaches it by assumption.
2. **Derived fit.** Buildable now, and it is a correctness and upkeep gain on its own. Until a
   score exists it can only be graded by census and by the guides, the yardstick this work
   set out to leave.
3. **The optimizer.** Waits on the score. Searching against a weak judge returns decks that
   exploit the judge. E7 measured the size of that risk: two decks in sixteen where a swap
   with no real value gained more than the best real upgrade. The engine is safer as a check
   on a finished proposal than as the thing searched against.

## Next steps (grilled with Dan, 2026-11-28)

**End state.** Lane membership moves to links derived from the rules and the parsed cards, one
event family at a time. Lane names stay, as labels computed from link facts. Dan's past
rulings become conditions on a link's facts ("repeatable only"), never card names; one that
will not fit goes back to him.

**Four tracks, in priority order for the machine and for attention.**

1. **The fitted score.** Every one of the six sets held out in turn, three training seeds a
   fold, error ranges. Its job is comparing different decks, which the engine failed. Then
   Brawl, where Untapped gives totals and no game rows: a sum of card results checked against
   the lists' records.
2. **The engine test on Competitive Brawl.** Untapped serves per-card results per commander
   (2.04 million games in three months, 18 commanders with 20,000 or more; Dan pointed it out
   on 2026-11-28, and it replaces the "far thinner" remark above). About ten of the most-played
   commanders, one real list each, like-for-like builds from that commander's own card
   results, plus builds whose swaps cross card types, to measure how often the engine is
   fooled. First step: recompute E7's truth from Untapped's limited card results. Pass bar:
   E7's. If it passes, "tuned deck against its starting deck" is reported beside the guide
   scores on the 20 held-out precons for a trial, and Dan then decides whether it replaces the
   guide gate. It is never a search target.
3. **Derived links, shipped to main.** "A creature dies" first: the commander feed table, with
   a stated strength order (repeatable before one-shot, more events before fewer, cheaper
   before dearer, today's blend breaking ties); then that family's lanes become labels and
   their hand code is deleted in the same commit. Later families in order of how many
   commanders wait on them with nothing offered today.
4. **The plan measure** (E4): per game and per turn, how often each thing the commander's text
   waits for happened, mana spent, the turn the commander was first cast. Checked on the Brawl
   builds before it runs on Commander precons in four-player games. Reported, never a gate.

**Bars.** A link ships when the rules say it is true and every difference from today's lane is
explained; guide scores are reported and never block. A family stops, and comes back to Dan,
if more than about 5% of its members need an exception over the definition (not a parse
fault) or it needs more hand-written rows than it deletes.

**A new yardstick.** Do the tuner's adds have better measured results under that commander
than its cuts, on the most-played list of each of the 20 most-played Competitive Brawl
commanders, with Dan's own decks on a separate line. The tuner never reads these results.

**Parked** (backlog): land counts from the solo simulation, an optimizer, card vectors built
from mechanics. Still not recommended: engine comparisons between different decks before the
pilot changes, and any search that optimises against the engine.

## Limits

- Phase is not a near-perfect model: about 14% of Commander-legal cards are knowingly
  unsupported and 2,772 faces are on its misparse list. A derived graph inherits each one.
- Every measured result here is limited (40 cards, two players, one set at a time). Nothing
  was measured for Commander.
- The fitted score reflects decks people chose to build and how people play them.
- E6's second run and E3's fallback were designed after seeing earlier results. Small gains
  from them are leads.
- E7's "real" change is estimated from card results, and its two estimates differ by a factor
  of two. Its swaps were like for like; a tuner's are not always.
- E3 used eight field decks whose own engine results ran from 25% to 70%. A larger field would
  tighten the numbers and would not change the verdict.

## Housekeeping found along the way

- `playtest-install-phase` failed at the pin; fixed in `b02fa9eb`, and the shared install was
  rebuilt at v0.133.0 on 2026-11-28. A failed run still leaves the install unusable (backlog).
- 17 of E3's 1,152 jobs hit the 20-minute limit; 16 were in decks holding Krenko, Mob Boss.
- The playtest coverage gate counts a card as supported when its name exists in card-data.
- The rest is in the backlog's cause-graph group.

## Where things are

- Plan and decisions: `~/.claude/plans/i-have-been-thinking-sleepy-lightning-of-29002e84-99e7-402e-8340-3866a5170457.md`
- Result files: `~/mtg/tuner-work/cause-graph/` (`e1-dies-family.md`, `e2-phase-analysis.md`,
  `e3-engine-as-judge.md`, `e5-land-count.md`, `e6-card-vectors.md`, `e7-deck-versions.md`, and
  the data beside them)
- Code: `experiments/cause_graph/` on the local branch `explore/cause-graph` (worktree
  `../mtg-skills-cause-graph`; `cause_graph.py` is the dies-family read)
- Isolated phase v0.133.0 build: `~/mtg/tuner-work/cause-graph/cache/phase`
- The ADR draft: `docs/plans/cause-graph-drafts/` on that branch; it lands with the first
  shipped family
