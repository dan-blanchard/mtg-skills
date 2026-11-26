# Limited is a pool-bounded Format family: sealed / draft build from an opened pool

A sealed or draft deck is built from the cards a player opened, plus basic lands
(CR 100.2b). Nothing in the toolchain modelled that: a 40-card pool had to borrow a
constructed format (`--format timeless --deck-size 40`), so `legality-audit` applied
the 4-copy limit and the 15-card sideboard cap to a deck whose rules have neither,
nothing checked that the deck was drawn from the pool, `mana-audit` read the
universal 17-land default as over-landed (the constructed formula scaled down), and
deck-forge's Find and Tune searched the whole card database for a build that may
only run what was opened. `docs/plans/limited-sealed-support.md` recorded the gaps
from a live Sealed session; ADR-0054 gave every format family its own template and
left `limited` as the family to follow.

**Decision.** Limited is the third Format family, and what bounds it is the pool.

- **Two formats, one family.** `sealed` and `draft` are Formats with `family ==
  "limited"`: a 40-card minimum (`min_deck_size`), no copy limit (`max_copies`
  None — as many duplicates as the product included), no sideboard cap
  (`sideboard_size` None — the sideboard IS the unused pool, CR 100.4b), and no
  legality key (`pool_bounded`). Their `legality` is "legal" for any record because a
  limited deck's legality is pool MEMBERSHIP, which `legality_audit.check_pool_
  containment` audits instead (every copy in the main deck and sideboard is in the
  pool at that quantity; basics excepted, by record or by name).
- **The pool is the fifth zone.** `pool` joins `ZONES` (hydrated by the one seam,
  ADR-0046; the sidecar version bumps), counted by none of the deck analyses — every
  reader of "the deck" walks the zones it means (`HydratedDeck.deck_records`, the
  counted deck), never the all-zones bookkeeping list. `parse-deck --format sealed`
  pools every card a list holds across its Deck and Sideboard sections, keeping the
  split where the list has headers; a bare list or `--pool-only` is all pool.
- **The sideboard is derived.** In the hub a pool-bounded build's sideboard is the
  pool less the main deck (`DeckSession.derived_sideboard`) — emitted, never stored,
  never written to. "The sideboard is the unused pool" holds by construction; a cut is
  just leaving the deck; a card played from the pool or the sideboard is an add the
  pool bounds; the pool itself never shrinks or grows by a move. Entering a
  pool-bounded format pools everything the build holds; leaving one stores the
  derived sideboard and empties the pool.
- **The pool is the copy limit.** `engine.copy_limit` reads the pool's count for a
  pool-bounded build (basics unlimited), so the ONE add rule (`check_copy_add`) is
  also containment, Find strips by it, and the tuner's per-name copy model takes the
  pool as `available` and owns all of it (an opened pool is never crafted or bought:
  no wildcard or USD readout).
- **Find and Tune search the pool and nothing else.** `engine.search_for` is the
  bulk-backed `search_fn` for a format whose pool is the database, and
  `card_search.filter_records` — the ONE filter implementation `search_cards` itself
  runs after its bulk scan — over the opened pool's records otherwise, with the game
  gate off (the records are the pool, whatever game they were opened in). The
  deterministic core still names every card; it just cannot name one the builder did
  not open.
- **The mana band is the limited norm.** `mana_audit.limited_land_target`: 17 per 40,
  a 16–18 band (one fewer for a low curve or real ramp, one more for a top-heavy
  pool), never the constructed formula scaled down. The FAIL floor is one below the
  target but never below the band's own minimum (16 per 40): a 16-land target does
  not make 15 lands merely a warning.
- **Two read-only readouts, agent-free.** `set-scan --set CODE` (what a set holds:
  removal by rarity, sweepers, evasion, the biggest bodies, the curve — over
  `CardPool.set_records`, the index a set filter needs) and `pool-colors` /
  the snapshot's pool panel (every mono colour and colour pair the pool supports —
  playables, creatures, removal, evasion, power-4-plus bodies, rares — on equal
  footing, before any opinion). Removal and sweepers are the template roles
  (ADR-0051); evasion is the record's keywords. A one-click seed fills a first 40 in
  chosen colours from the pool's own cards plus basics — a starting point, never a
  finished deck. The SPA reads `pool_bounded` / `family` from the served row like every
  other family fact (ADR-0054).

**Considered and rejected.** Borrowing a constructed format at 40 cards (the
status quo: wrong copy limit, wrong sideboard cap, no containment, a wrong land
band, and a database-wide Find). A `--pool <file>` flag on `legality-audit` (the
pool rides inside the deck JSON as a zone, so the audit reads it like any other).
A stored sideboard plus a "cards + sideboard ⊆ pool" rule (double bookkeeping;
every UI move becomes remove-then-add; the derived sideboard makes the invariant
structural). A faked legality key for limited (membership is the question, and a
set's legality status is not). A size floor in `is_valid_deck_size` (a build's
size is its target; the 40-card floor is `deck_minimum`'s, as for constructed).

**Consequences.** `Family` gains `limited`; `Format.max_copies`, `sideboard_size` and
`legality_key` are Optional and every reader is None-safe (an unlimited copy count
reads as unlimited in the SPA, which takes every copy limit from the served row and
derives none). `filter_records` is the seam a second record-bounded search (a cube,
a collection) can reuse. The seed replaces the main deck and keeps
what it replaced for one undo (a first draft, never a finished deck); a paper sealed pool's printings are what was opened, so
`card-search --format sealed` is never Arena-gated. Non-goals: pack generation and
draft simulation (cube-wizard's), a matchup model, ranking the colour pairs
(enumerated on equal footing; the choice is the builder's).

**Amendment (2026-11-25): a cube's pool, and no play rate.** A powered-cube draft
deck (40 cards from a 54-card pool, 2026-11-02) got advice built for a retail set:
ten creatures and fourteen answers read as off-template, its lane's "least played"
half was traded away on EDHREC's Commander play rate, and its top issue named a
combo piece nobody had opened.

- **A pool has a kind.** `HydratedDeck.pool_kind` is `"set"` or `"cube"` (`None`
  with no pool): a cube's when no one booster set prints at least half of the
  pool's nonbasic cards. A retail pool is one set plus its bonus sheet, so its set
  prints nearly all of it (95% or more of 45 cards sampled from each of 17
  sets); a cube's best set prints a fraction (6 of the powered cube pool's 45;
  over 20,000 random 45-card pools from a 312-card Commander cube, 22% at the
  median and 47% at most). Each record lists the booster sets its card is
  printed in (`draft_sets`, built with the bulk): a set MTGJSON types
  `expansion`, `core`, `masters`, `draft_innovation`, `alchemy` or `funny` AND
  lists booster contents for. The type alone is not enough: The List, a reprint
  sheet of five thousand cards with no booster of its own, is typed `masters`
  and prints 56% of that Commander cube; a promo set prints 21 of the powered
  pool's 45. The deck JSON's own `pool_kind` key overrides the cards
  (`parse-deck --cube` / `--no-cube`), and `deck-tune --cube` / `--no-cube`
  overrides both for one run.
- **A cube deck has its own template.** `budgets.template_of(hd)` is the one
  template choice the tuner, `slot-budgets` and deck-forge's rows all make. The
  cube template keeps the lands and curve rows, reports the creature count as
  advisory (the retail band as its reference) and gives interaction no ceiling
  (the row's ceiling is the deck's size, so the hub's bar reads "14/40").
- **No play rate where it means nothing.** EDHREC counts Commander decks, and
  `Calibration.playrate_meaningful` was already off for the limited and
  constructed families. Two reads went around it: the deep lane's "least
  played" half (`metrics.focus`) and the least-played tiebreak of a band trim
  (`cuts.cut_candidates`). Both ask the switch now, and order by the deck's
  meta archetype's shares where it has one (ADR-0059). The fix reaches 60-card
  decks too.
- **A near-miss stays inside the pool.** `combo_search` keeps a pool-bounded
  deck's near-miss only when the pool holds its missing card (or a card that
  can be its missing generic piece), asked before the popularity cut, so the tuner, `combo-search`, `proposal-check` and the hub
  see the same ones.

The hub only detects: a deck-forge session carries no `pool_kind`, and no
switch sets one.

Rejected: an explicit flag alone (a deck JSON says nothing about where its pool
came from, and the cards do); an advisory creature count for every limited deck
(a retail sealed deck short on creatures is short); archetype shape bands for a
cube (no source for the bands).

**Amendment (2026-11-25, Dan's rulings): a limited closer is a threat that's hard
to block or hard to answer.** With the cube template, no play rate and pool-scoped
near-misses, the same powered-cube deck got one swap: True-Name Nemesis out for
Screaming Nemesis, under "≈1 closers — usually wants 2-3". The closer count was
the Commander finisher read at 20 life (a card that wins, an extra combat, a team
pump, closing reach, a big evasive body), which never counts protection; and
True-Name Nemesis, a Rogue feeding only an unbuilt Rogue lane, had been re-bucketed
as filler ("feeds only avenues nobody built toward"), the first cut.

- **The read.** `Calibration.closers` is `"threat"` for the limited family, and
  `metrics.closer_read` hands both the closer count and the closer search
  `metrics.limited_closer_reason`:
  - a finisher that makes sense in a 40-card deck — an extra combat, a one-shot
    team pump, reach that closes, poison in a poison deck. Not an alternative win
    or loss (`reads.ends_the_game`): Thassa's Oracle, Laboratory Maniac and
    Felidar Sovereign win on a library or life total a limited deck doesn't reach,
    so such a card is judged as any other;
  - a noncreature card with a repeatable source (`crosswalk.unit_repeats`): a
    creature token of power 1 or more (`card_reads.repeating_creature_tokens`:
    Bitterblossom) or 2 or more damage to an opponent, or a scaling amount
    (`crosswalk.reach_amount`: Chandra, Torch of Defiance's +1);
  - a creature of power 3 or more that's hard to block — an evasion keyword
    (`card_classify.EVASION_KEYWORDS`, printed or given to itself,
    `crosswalk.own_keyword_bodies`), a blocking restriction on itself
    (`crosswalk.is_evasive_body`, CR 509.1b, now with "can't be blocked by
    creatures with power 2 or less" — Rust-Shield Rampager), trample from power 4
    (CR 702.19b; `budgets.LIMITED_BIG_POWER`, set-scan's big body) — or hard to
    answer: protection (CR 702.16b, 702.16f; from a player, 702.16k — True-Name
    Nemesis), hexproof, shroud, ward or indestructible
    (`crosswalk.PROTECTIVE_KEYWORDS`), or a body that comes back to the battlefield
    by itself (`lanes.card_advantage.self_return_routes`: persist, undying,
    Bloodghast, embalm). A return to hand or a cast from the graveyard (Furious
    Forebear, Gravecrawler) costs its mana again, so the removal still buys a
    turn: not resilience here.
  - Power is the printed number (a double-faced card's front face — the one read
    the finisher read now takes too) plus the +1/+1 counters the card enters with
    by its own text, a fixed number (Spike Feeder, riot — CR 702.136a, endure —
    CR 701.63a: Sandskitter Outrider is a 4/3 menace). A power that counts other
    cards (Adeline), level up (Hexdrinker) or growth on attack is not read.
  - None for a body that can't close: defender (CR 702.3b), decayed (CR 702.147a:
    it can't block and is sacrificed the turn it attacks), a "can't attack" of its
    own, or a standing restriction (`SelfDrawbacks.standing`: Sea Serpent's
    Island clause, an upkeep you may fail). A one-time cost of its own enters
    trigger does not hold it back (Carnage Interpreter's "discard your hand";
    Inverter of Truth's exiled library), where the finisher read still does.
  Never play rate, never a quality score.
- **Dan's rulings.** The floor is 1, for cube and retail alike: only a deck with no
  closer is short. The power line is 3 for evasive and resilient bodies alike (the
  finisher read's own floor at 20 life, about seven swings). A creature that makes
  tokens or pings is judged by its body: creature removal answers it. A repeatable
  one-damage ping is not a closer (`LIMITED_REPEAT_REACH = 2`).
- **The coordinator's choices** (where Dan did not rule). Evasion or resilience a
  creature pays for each turn, or that lasts only a turn it buys, does not count:
  a self-grant behind a payment trigger (expend) or a cost of its own
  (Bark-Knuckle Boxer's indestructible); one that is simply on when its condition
  holds does (Waterspout Warden's flying, Ursine Monstrosity's indestructible each
  combat). A planeswalker counts only by a loyalty ability that costs no loyalty
  (CR 606.4: a plus or zero ability), making a creature of power 1 or more or
  dealing 2 or more to an opponent or any target: Gideon, Ally of Zendikar's 0
  counts, Chandra, Torch of Defiance's +1 counts; The Wandering Emperor's −1
  Samurai, Ajani, Adversary of Tyrants' −7 emblem, Karn, Scion of Urza's −2
  Construct and Nissa, Voice of Zendikar's +1 0/1 Plant do not.
- **The floor and the measurement.** `calibration.LIMITED_CLOSER_FLOOR = 1`, stated
  at the limited game itself and never life-scaled; the band's top
  (`LIMITED_CLOSER_TOP`, 3) is the message's only. Over 733 simulated 40-card
  draft decks (`_draft_ai` + `_gauntlet_build`, the `playtest-draft` pipeline: the
  MTGO Vintage Cube, Bloomburrow and Tarkir: Dragonstorm) the read's median is 3
  for the cube and 2 for each set, and 6% of the decks hold none; the retail
  counts are a lower bound (the pack model has no wildcard or foil slot, so it
  undercounts rares). The powered-cube deck holds four (Quantum Riddler,
  True-Name Nemesis, Emeritus of Ideation, Chandra) and is proposed nothing.
- **No fed-only filler in limited.** `Calibration.fed_only_is_filler` is off for
  the family: in a deck drawn from an opened pool a card is played for what it
  does alone, and the avenue it nominally feeds says nothing about it. The fed
  avenues are still reported.
- **What reaches the other families.** Two fixes are shared: `is_evasive_body`
  reads "can't be blocked by creatures with power 2 or less" (CR 509.1b; "can't be
  blocked by more than one creature" stays out, the `evasion_self` lane's verdict:
  it limits how many block, not what can), and the finisher read takes a
  double-faced card's front-face power. Together they add 27 cards to the
  Commander finisher read at 40 life (Etali, Primal Conqueror, Vorinclex, Dread
  Linnorm …) and 184 at 20 life; no signal moves (the whole corpus, diffed
  against main). `deck-tune` on two Commander decks, a Competitive Brawl deck and
  a 60-card deck is byte-identical before and after.
