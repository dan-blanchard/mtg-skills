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
    never stuck in hand, since it can be played as that land (CR 712.12). It sets the
    top at its spell's cost (Emeria's Call, 7).
  - Cards whose printed cost nobody pays are left out of the top: an unpriced
    "costs less" clause (Octavia, Living Thesis; Nyxborn Behemoth;
    Ancient Stone Idol), and morph, megamorph and disguise cards. Those are cast
    face down "by paying {3} rather than paying its mana cost" (CR 702.37a,
    702.168a), which is the cheapest a candidate is checked at. Leaving morph cards
    out of the top is arguable, since their unmorph costs are real mana. It moves
    Deadly Disguise's top from 10 to 6 (cap 8).
  - Undaunted ("costs {1} less to cast for each opponent you have", CR 702.125a)
    counts at printed less three on both sides, a four-player pod.
- **Convoke, delve, improvise, affinity and emerge** (first left uncapped as
  candidates; replaced by Dan's decision below). They pay "rather than pay" mana
  (convoke 702.51a, delve 702.66a, improvise 702.126a), cost less for what you
  control (affinity 702.41a), or are an alternative cost reduced by a sacrificed
  creature (emerge 702.119a).

*Dan's decision (2026-11-27): a self-paying card is capped at what the deck pays
for it* (`costs.self_paid_cost`). A deck that feeds it nothing pays its printed
cost.

*The coordinator's call (2026-11-27), on the deck-top side:* a self-paying card
the deck feeds counts in the top at what the deck pays. One it can't feed is left
out of the top, as an unpriced "costs less" card is, because a deck that can't
feed it doesn't plan on casting it. Counting it at printed would loosen the cap:
Organic Extinction beside thirty one-drops would raise the top from 1 to 10.

*The builder's choices, for how "what the deck pays" is read:*

- **Convoke, improvise and affinity** are priced by the ADR-0044 estimator
  (`commander_cost.affordable_turn`) for this deck. The population is the deck's
  own creature cards (convoke), artifact cards (improvise, affinity for
  artifacts) or cards of the affinity's quality (`ConceptTree.card_keyword_types`).
  Each pays one generic mana and none goes below the colored pips. For affinity
  and improvise that is the rule (affinity takes off generic mana only, CR 702.41a
  and 118.7a; improvise pays generic mana only, CR 702.126a). A convoke creature
  can pay a pip of its own color (CR 702.51a), so for convoke the floor is the
  builder's cautious choice.
  No threshold is needed: the estimator's affordable turn is the cost the deck
  pays, and the cap reads it. The card itself, on the stack, is not counted.
  Hoarding Broodlord (eight) is an eight, out of the top, in a deck with no
  creatures, and a five beside thirty one-drops in 99.
- **Tokens** count one payer per card that makes a token of the kind
  (`costs._payers`; its `make_token` concepts under your control). It is cast at
  its own mana value like any other card; a creature making creature tokens is
  two bodies. One token per maker is low for a token deck, and investigate's
  Clues (a keyword action, no `make_token`) are not read. Autochthon Wurm
  (twelve) costs 10 → 9 in Tyranid Swarm (cap 9: in), 11 → 9 in Squirreled Away
  (cap 10: in), 12 → 11 in Quick Draw (cap 8: out), and 9 either way in Call for
  Backup (cap 9).
- **Delve** has no battlefield population to price. Two deck cards that fill
  your own graveyard (`costs.GRAVEYARD_FILL_FLOOR`, R2's cheat floor) make it
  one that fills. A filler is a mill that can hit you (`reads.mill_reaches_you`:
  a self-mill, each player's, or a target player's, which can be you) or a
  discard outlet, loots included (`discard_outlet|you`). The `mill_makers`
  signals can't tell these apart: `opponents` marks any mill that can reach an
  opponent, Millstone included. A commander filling it counts at once. A delve
  card fed this way counts at its colored pips, since a filled graveyard pays
  every generic mana. Unfed, it counts at printed. A dig that puts the rest into
  the graveyard (Satyr Wayfinder) is no mill and is not read.
- **Emerge** counts at its emerge cost less the mana value of the deck's
  cheapest creature card, never below its colored pips. It is cast on the
  earliest turn the estimator expects a creature on the battlefield to
  sacrifice. The estimator casts cheapest-first, so the cheapest creature is the
  one it expects out first. The card itself is no sacrifice for its own emerge.
  Elder Deep-Fiend ({8}; emerge {5}{U}{U}) counts at 5 in Eldrazi Incursion
  (cap 12).
- What is conservative here is the candidate side: fewer payers make a dearer
  candidate. On the top side, fewer payers can leave a card out of the top or
  count it higher. Emerge's cheapest sacrifice is the same trade: the smallest
  discount makes an emerge candidate as dear as the deck can make it, and it
  counts a fed emerge card already in the deck higher, which raises that deck's
  top and loosens its cap.
- **Census over N28's adds** (55 precons). No tuner add and no guide add is
  refused. All 22 self-paying adds and guide adds are within their deck's cap.
  Deep Clue Sea's cap rises from 9 to 10: Organic Extinction ({8}{W}{W},
  improvise) is fed by its 17 artifact cards. The estimator expects two
  artifacts out by turn eight, which pays the last two generic mana, so the deck
  can cast it on turn eight, and its top becomes 8.

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
  every permanent card under them. It stays unbounded under Dan's 2026-11-27 decision: the
  signal's identity is `(key, scope, subject)`, and its subject is the card type,
  so there is nowhere in it to carry a bound. Bounding it would mean reading each
  emitter's own trees, as the reanimation read does.
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
  `effective_mana_value`.
- **The named-combo-piece guard stays stricter than the cap** (measured
  2026-11-27). The older guard from 2026-11-01 (`swaps.deck_top_mv`, every
  family) holds a combo's missing piece to the deck's top at printed mana value,
  with no room and no cheat waiver. Over the 55 precons' near-miss pieces, the
  cap would admit ten pieces the guard holds out. None of them is a guide's add,
  and six are Tidespout Tyrant on a value line, the add the 2026-10-18 audit
  found no upgrade article agreeing with. Sliver Swarm's other three are
  Approach of the Second Sun, Morophon and Star of Extinction, plus Secret
  Arcade in Virtue and Valor. The cap's own reading at no room would move eleven
  pieces the other way. No named piece is reached only by a cheat plan, so a
  cheat waiver would change nothing.
  (`test_a_named_combo_piece_stays_within_the_decks_printed_top_under_the_cap`)
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
  - Since 2026-11-27 the cheaper window (`swaps._CHEAPER_WINDOW`) counts only
    the cards that pass every gate the pick must pass, the cap among them. A card
    the cap refuses no longer pushes a near tie out of the window
    (`test_the_cheaper_window_counts_only_cards_the_pick_could_be`). The window
    also ends twenty positions past the first pick (`_WINDOW_REACH`, twice its
    count; eighty under a tight purse's forty-card window). On the 55 precons,
    with no bound, a take past the share stood a median 7 positions down, p90 25
    and up to 393. Measured alone against N28 (N34): 236 swap pairs in 35 decks
    move; guide adds 128 → 123 / 110 → 112 / 51 → 46 on the 25, the held-out 20
    and the fresh 10, plan 505 → 497 / 415 → 412 / 167 → 169, both floors held;
    a reading of twenty changed pairs was 6 better, 7 worse, 7 sideways. It
    misses the gate's primary; Dan landed it on the floors (2026-11-27), since
    the old window let a card the pick could never be push the pick out.

**Consequences.** A low-curve Commander deck is capped by design: a deck topping at
four is offered nothing past six outside its thin top-end page
(`test_a_low_curve_commander_deck_is_capped`). The census of N20's adds against the
final rule is in the commit message.
