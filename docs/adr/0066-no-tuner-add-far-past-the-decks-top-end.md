# No tuner add far past the deck's top end

The tuner keeps an upgrade's or a trim's add within its cut's mana-value band
(`upgrade_gates.over_band`), but the last band (over five) has no top. An add the
tuner finds before it picks the cut (a dead-weight fill, a Spine fill, a closer, a
fill into an open slot) has no band check at all. Only the even share
(`find_add`, `_Purse.share`) held Blight Curse's dead-weight drain back from
Blightsteel Colossus, twelve mana, in a deck whose costliest card is seven. A
settle-up pass, which spent the money no later swap needed, exposed it. That pass
is held as a patch (Dan's decision, 2026-11-26: it failed the scoreboard's gate;
`~/mtg/tuner-work/w-2026-11-26/settle-up/`). Blight Curse's reanimation
(Aberrant Return) cannot return Blightsteel either: it shuffles itself into its
library whenever it would be put into a graveyard. The cap guards any budget
generous enough to reach an off-curve card, and must change nothing where the
tuner was already right: the scoreboard run of the cap's first form (N21) was swap
for swap identical to the parent (N18) on the 55 precons.

**Decision.** In a family whose calibration carries `curve_room`, no add costs more
than the deck's own top end plus that room (`_tuner/curve_cap.py`, `CurveCap`). The
deck's top end is its costliest nonland card, the commander included, each card at
the cost of its big mode. A candidate is checked at its cheapest mode
(`_analysis.costs.cast_costs`).

The lines come from three places, and each item says which: **Dan's rulings**
(2026-11-26), **the coordinator's calls** (2026-11-26, after review), and **the
builder's choices** where both were silent.

*Dan's rulings (2026-11-26):*

- **R1. The room is two mana.** A deck topping at 7 is offered up to 9. The Eldrazi
  precon, topping at 10, keeps It That Betrays (12). Blightsteel Colossus (12
  against 7) stays out, whatever the budget.
- **R2. A deck that cheats cards into play is not capped for the cards its plan
  reaches,** through the tuner's existing reads: the reanimation signal
  (`creature_recursion`, the read behind `metrics.efficiency`'s
  `cost_cheat_waiver`) and the `cheat_into_play` signal. Two or more deck cards
  must hold it, the waiver's own floor; the commander holding it counts at once.
- **R3. The Commander family only** (`Calibration.curve_room`: 2.0 for Commander,
  None for constructed and limited). A 60-card or limited deck has no thin top-end
  path, so a ceiling there would be a wall: a sealed deck topping at five must still
  be offered the seven in its pool.

*The coordinator's calls (2026-11-26):*

- **The waiver's scope.** Only a plan that puts the card onto the battlefield
  counts: `creature_recursion|you|battlefield`. A return to hand does not (Order of
  Midnight's Alter Fate, Haven of the Spirit Dragon). Each reanimator is read
  against the candidate itself: its graveyard-to-battlefield move's target filter
  (an Aura's at its Enchant filter: Animate Dead) must admit the card from your own
  graveyard (`reads.filter_admits`, with the owner and controller). A tribe-bound
  one counts for its tribe only (Knights' Charge: Knights). A mana-value bound
  counts where it is fixed (Unearth's "3 or less" doesn't reach a 12). The owner
  must include you: "each player" does (Exhume, Twilight's Call: a
  `ScopedPlayer` owner under an `All` player scope); a defending player's or
  "each other player"'s does not (Rakshasa Debaser, Enslaved Horror). A
  reanimator counts toward the two only when it admits the candidate. A creature that leaves the graveyard by its own trigger (the
  shuffle-trigger Eldrazi: Kozilek, Butcher of Truth; Ulamog, the Infinite Gyre;
  Emrakul, the Aeons Torn) is capped under a reanimation plan, as the replacement
  ones are. This is the simple and conservative line.
- **The deck's top end takes each card's big mode, and a candidate is checked at
  its cheapest.**
  - A split card or an adventurer card tops at its costlier half. A deck that casts
    Finality tops at 6, not 2; Realm-Cloaked Giant at 7. A candidate is castable if
    any mode is.
  - A modal double-faced card with a land face is never capped as a candidate: it is
    never stuck in hand, since it can be played as that land (CR 712.9). It sets the
    top at its spell's cost (Emeria's Call, 7).
  - Cards whose printed cost nobody pays are left out of the top, as convoke cards
    are: an unpriced "costs less" clause (Octavia, Living Thesis; Nyxborn Behemoth;
    Ancient Stone Idol), and morph, megamorph and disguise cards. Those are cast
    face down "by paying {3} rather than paying its mana cost" (CR 702.37a,
    702.168a), which is the cheapest a candidate is checked at. Leaving morph cards
    out of the top is arguable, since their unmorph costs are real mana. It moves
    Deadly Disguise's top from 10 to 6 (cap 8).
  - Undaunted ("costs {1} less to cast for each opponent you have", CR 702.125a)
    counts at printed less three on both sides, a four-player pod.
- **Convoke, delve, improvise, affinity and emerge stay uncapped as candidates.**
  They pay "rather than pay" mana (convoke 702.51a, delve 702.66a, improvise
  702.126a), cost less for what you control (affinity 702.41a), or are an
  alternative cost reduced by a sacrificed creature (emerge 702.119a). The cap is a
  guard, not a ranking. Known limit: such a card meets no ceiling even where the
  deck can't feed it. Autochthon Wurm in a token-less deck, Blinkmoth Infusion with
  no artifacts, Icebreaker Kraken with no snow lands; Organic Extinction is the
  likeliest to be picked. The fix it would need: count them at printed cost unless
  the deck supplies what they feed on. Recorded in the backlog.

*The builder's choices:*

- **A card no reanimation returns** (`curve_cap.cant_be_reanimated`, an addition to
  R2's existing reads). It is read off the card's front face:
  - a mandatory replacement of its own move to a graveyard from anywhere, active in
    its hand and library too, so a discard or a mill is replaced as well as a death
    (CR 614.1a: Blightsteel Colossus, Darksteel Colossus, Progenitus);
  - or a trigger on its own move to a graveyard from anywhere that shuffles the
    graveyard, or the card itself, into the library (the Eldrazi above; Worldspine
    Wurm and the Lorwyn Incarnations, Dread among them).

  A "would die … instead" (Possessed Skaab, Gravebane Zombie) is not one, and
  neither is a back face's replacement (Spectral Binding).
- **An untyped cheat (`cheat_into_play|you|`) reaches permanent cards only.**
  Instants and sorceries can't enter the battlefield (CR 304.4, 307.4). Known
  limit: three of the four untyped emitters in the precons cheat only up to a bound
  (Genesis Hydra: mana value X or less; Emergent Woodwurm: its power; Broodcaller
  Scourge: the damage dealt). The signal carries no bound, so the cap lifts for
  every permanent card under them.
- **The other modes `cast_costs` reads:** an X counted at three
  (`costs.X_COST_VALUE`, the value the mana-value bands already used; CR 202.3e
  counts X as 0 off the stack); a split card's halves (each cast on its own, CR
  709.3; its mana value combines them, 709.4); an adventurer card's Adventure (CR
  716.3: played "normally or as an Adventure"); a curve alternative cost (warp,
  evoke and the others `effective_mana_value` reads); and a "this spell costs less"
  clause of its own, at the ADR-0044 estimator's affordable turn in this deck where
  it can price it.
- **What the reanimation read can't hold a card to, and so doesn't count.**
  - A bound the filter doesn't carry as a fixed number: a power bound (Reveillark's
    "power 2 or less"), a mana value the game decides (Betor's "less than or equal
    to the life you lost").
  - A move whose target is another reference or a tracked set (Technomancer;
    Victimize's sacrifice-then-return; Living Death's exile-then-return).
  - A move whose origin phase leaves unset (Puppeteer Clique's return from an
    opponent's graveyard), and a card with no graveyard-to-battlefield move in its
    trees (Necromancy).

  Known limit: a bound phase drops from the tree entirely is read as no bound.
  Reunion of the House's "total power 10 or less" is absent from its typed target,
  so it counts as returning any creature card.
- **What is untouched.** The tuner's curve, shape and efficiency reads keep
  `effective_mana_value`. A known inconsistency: the older named-combo-piece guard
  from 2026-11-01 (`swaps.deck_top_mv`, every family) still reads printed mana
  value (`CardClass.cmc`, `effective_mana_value`), with no room and no cheat
  waiver. Routing it through the cap would loosen it in the Commander family
  (two mana of room) and change the scoreboard where the cap refuses nothing.
  Recorded in the backlog.
- **An empty top is no cap.** A deck whose every nonland card is left out of the
  top (or that has none) has no ceiling, not a cap of two.
- **The thin top-end search is exempt.** A search that asks for the top end itself
  (a thin top-end's six-and-up page, `issues._EFFICIENCY_BANDS`) is uncapped.
- **The cap is the last gate a candidate meets** (`swaps.find_on_page`, just
  before its price), so it changes a pick only by refusing one. The page and its
  order are the parent's, including the job reads' percentile blend over the whole
  match set. A page the cap empties is searched again four times deeper
  (`swaps.find_add`), so the swap is not lost.
  - A filter after the search lost Abzan Armor one of its thirty swaps.
  - A filter on the search itself took the over-cap cards out of the match set the
    blend ranks over, which moved Quick Draw's interaction upgrades though nothing
    the cap refused was picked (N23, 2026-11-26).

**Consequences.** A low-curve Commander deck is capped by design: a deck topping at
four is offered nothing past six outside its thin top-end page
(`test_a_low_curve_commander_deck_is_capped`). The census of N20's adds against the
final rule is in the commit message.
