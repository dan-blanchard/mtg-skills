# Card fit is derived from causes and waits, one event family at a time

A lane says "these cards do X" and a serve table says "this lane wants cards from that
set". Both are hand-written per key (393 served keys, 305 lane functions), and 75 of
182 recent fixes moved a card across one of those boundaries. The commander-need read
(ADR-0061) derives what a commander waits for and hand-wrote what supplies it, for
about 20 of phase's 115 trigger kinds. A commander that waits for a creature dying was
fed `sacrifice_outlets`, `edict_makers` and the token makers, whoever's creature it
watched: Toxrill, the Corrosive, which watches creatures you don't control, was offered
your own sacrifice outlets and tokens.

The 2026-11-27 exploration (`docs/plans/cause-graph-exploration-2026-11-27.md`) built
the supply side for one family, "a creature dies", from the trees: a table of rules
steps and phase effect names, no card names. It reached about 97% of the lanes' true
members, and what it added were rules-true links the lanes had dropped as relevance
calls.

**Decision** (Dan, grilled 2026-11-28):

1. **A card's fit with another card is a link.** One card's instruction causes an
   event another card's trigger waits for. Links are read from the trees by shared
   reads and a table of rules steps, each row one rule checked with `rules-lookup`.
   `mtg_utils/_analysis/links/` holds them, one module per event family.
2. **A link carries facts, never a verdict**: the route and its rule, certain or
   needing a big enough number, whose object, one or all, cost or effect, how it is
   delivered, repeatable. No card is ruled in or out of a family. Phase's effect
   vocabulary is closed, so a family's tables are gated on it: every effect is a route,
   is known to make the event by a route not yet read, or is known not to. A new phase
   effect fails the test until someone classifies it.
3. **Relevance is a condition on facts.** Where a consumer needs fewer cards than the
   family holds, it says so as a condition on a link's facts ("repeatable", "certain"),
   never as a card name. Dan's past rulings on a lane become such conditions when the
   lane moves; one that will not fit goes back to him.
4. **The end state is lanes as labels.** Membership moves to links one family at a
   time. A lane's name stays, as a label computed from link facts, and its hand-written
   code is deleted in the commit that moves it.
5. **A family ships on correctness.** A link ships when the rules say it is true and
   every difference from what it replaces is explained. The upgrade guides' scores are
   reported with it and never block. A family stops and comes back to Dan if more than
   about 5% of its members need an exception over the definition (not a parse fault),
   or if it needs more hand-written rows than it deletes.
6. **Order among links is stated, not fitted**: a repeatable link before a one-shot
   one, a link that reaches every creature before one that reaches one, a cheaper card
   before a dearer one, with today's play-rate and card-quality blend inside a tier.

## The first family: a creature dies (CR 700.4)

`links/deaths.py`. Six routes, each ending in "is put into a graveyard from the
battlefield": destroy (CR 701.8a), sacrifice (CR 701.21a), a direct move, lethal damage
(CR 704.5g), a fight (CR 701.14a) and toughness 0 or less (CR 704.5f). The first three
are certain; the last three need a big enough number. Fifteen phase effects map to a
route; four keywords carry a sacrifice in their own rule (exploit CR 702.110a, devour
CR 702.82a, casualty CR 702.153a, bargain CR 702.166a); 22 effects can kill by a route
not read yet and are listed as such; 204 cannot. A wait is a trigger watching a death
or a sacrifice, with whose creature it watches. `feeds(link, wait)` is the one test: a
destroyed creature was not sacrificed; a creature of yours has to die for a wait that
watches yours.

**Step 1, shipped here: the commander's death need.** `commander_need` builds a "dies",
"sacrificed" or "exploited" need from the trigger's own waits:

- A card **supplies** the need when one of its links feeds the wait for certain and
  repeatably. Three conditions on facts narrow that, each the read's own line:
  a link that kills only when a number is big enough, or when another player chooses,
  is no supplier; where a creature of yours has to die, a link you would have to aim
  at your own creature is none either (a sacrifice and a link that reaches every
  creature are); and a card that kills itself for certain counts as a body that needs
  no outlet, where the wait could be watching that card (not a token-only wait, CR
  111.1; not another creature type).
- A need is named for whose creature it watches ("creatures that dies", "opponents'
  creatures dying", "the commander dying"), so a commander with two death triggers has
  two needs.
- Any other feeding link makes the card a **weak supplier** (`Need.weak`): on the
  need's page after the suppliers, counted nowhere else (not in the broad line, not in
  what the deck has, not by `satisfies`).
- The page leads with the stated order (`Need.strength`, the tuner's `_lead`).
- Bodies to kill, the token makers, are still read off their keys, and only where the
  wait watches creatures of yours and not only nontoken ones (any token, whatever its
  creature type). A card that makes the objects another card's cost
  or filter needs is a second kind of link, not built.

Step 2, not in this commit: the family's lanes (sacrifice outlets, edicts, removal,
board wipes) become labels over the links.

## Measured

- **The read against its prototype** (32,573 Commander-legal cards): the same links and
  waits on 31,485 cards. The other 1,088 fall into eight classes, and in each the
  shipped read is the rules-true one: an ability whose own cost sacrifices its card
  does not repeat (368; CR 701.21a, CR 113.6); a destroy or damage that names no
  controller can hit either side (332); who sacrifices is read per player, so "target
  opponent sacrifices" is an opponent's creature (109; CR 701.21a); a counted "-1/-1
  for each Swamp" is a toughness reduction (64); creature types come from CR 205.3m
  (78); a Saga chapter does not repeat (66; CR 715.2b); a sacrifice another player
  decides is not certain (15); an Equipment's creature is yours and an Aura's follows
  its enchant restriction (87; CR 702.6a, CR 303.4a).
- **The need against the table it replaces** (34,858 Commander-legal nonland cards):

  | commander's wait | old table | suppliers now | in both | weak now |
  |---|---|---|---|---|
  | another creature you control dies (Meren of Clan Nel Toth) | 4,774 | 4,365 | 3,936 | 3,633 |
  | a creature token dies (Grismold, the Dreadsower) | 4,774 | 3,768 | 3,560 | 3,883 |
  | a creature you don't control dies (Toxrill, the Corrosive) | 4,774 | 323 | 144 | 3,816 |
  | the commander itself dies (Kokusho, the Evening Star) | 4,774 | 725 | 656 | 3,820 |
  | an opponent sacrifices a creature (Legate Lanius, Caesar's Ace) | 4,774 | 111 | 108 | 206 |

  The old table was one set for every wait. For Meren, the 838 cards only the old table
  held: 385 feed it once and are weak now; 182 never sacrifice a creature (the lane is
  wider than this event: artifacts, lands, payoffs); 120 make only opponents sacrifice;
  31 kill only when a number is big enough or another player decides; 117 mention a
  creature sacrifice with no link, mostly cards that only reward a sacrifice, with
  about fifteen real gaps (alternative costs and back-references, each a one-shot).
  The 429 cards only the links supply: 360 sacrifice or destroy themselves by a
  trigger or a cost, the same kind of card as the self-sacrificers the old table held;
  the rest reach every creature or sacrifice a creature of yours by a trigger. No
  difference was a dispute over the definition.
- **The upgrade guides** (reported, not a gate; baseline N36, run N39): 53 of 55 precon
  tunes are identical.
  - Dance of the Elements (Ashling, the Limitless: "Whenever you sacrifice a nontoken
    Elemental") went from 6 guide adds to 10. Its page now offers the Elementals that
    sacrifice themselves (evoke, CR 702.74a): Grief, Solitude and Subtlety were won,
    with Ashling's Command, Roaming Throne and Ygra, Eater of All; Cavalier of Night
    and Rottenmouth Viper were lost.
  - Fae Dominion (Tegwyll, Duke of Splendor) went from 7 guide adds to 6 (Kindred
    Discovery lost) and its plan line from 17 to 14. Its death need used to be
    broad (over a tenth of its pool under the old table) and opened no page; the
    suppliers alone are under the line, so the page opens and takes four adds
    (Viscera Seer among them).
  - Totals: the 25, 727 swaps / 342 guide cuts / 120 guide adds (121 before), plan
    496 (499); held-out 20, 562 / 264 / 115 (111), plan 412 unchanged; the fresh ten
    unchanged.

## Consequences

- A dispute over this family becomes "is this what the rule says", settled once per
  row.
- Every parse gap still reaches the read; the correction layers and their canaries
  stay.
- Known gaps, each a generic shape and none a card: a sacrifice paid as an alternative
  cost ("rather than pay"), "its controller sacrifices it" back-references, emblems,
  and nodes phase leaves unparsed. A wait read from one clause of a multi-clause
  trigger (Syr Konrad, the Grim) opens no need yet, as before. "Sacrifice an artifact"
  is read as killing no creature, though an artifact creature would die. A wait for a
  noncreature permanent ("sacrifice an enchantment") keeps the old table.
- A "leaves the battlefield" wait keeps its hand table: leaving is a wider family.
- The links do not rank. Relevance past the stated order waits on a score
  (the findings document's yardsticks).
