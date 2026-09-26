# deck-forge serves every Format family; the template and every tuner floor are the family's

deck-forge, the shared tuner and `deck-tune` served the Commander family only. The
scope lived in code rather than in a decision: `engine.check_format` allowed
`COMMANDER_FORMATS`, `format_options()` defaulted to them, `deck_tune.py` refused
anything else (ADR-0029's "60-card constructed stays agent-driven"), and every band
and floor the tuner measured was a Command Zone number scaled by `deck_size / 100`
— so a 60-card deck, had it got through, would have been held to 0.6 of a Commander
deck's ramp and wipes. Meanwhile the substrate was already format-general:
`formats.py` declared the nine constructed formats, `legality_audit` was
`Format`-driven (4-of, Vintage's restricted list, the 15-card sideboard, Yorion's
companion condition), `mana_audit` already branched Commander vs constructed
(ADR-0041), and the session held a `sideboard` zone the browser never rendered.

**Decision.** The Format answers the family questions, and everything downstream
asks it (ADR-0045).

- **The family is a Format fact.** `Format.family` (`commander` | `constructed`;
  a pool-bounded `limited` follows in ADR-0055) with the facts it implies —
  `has_commander`, `max_copies`, `sideboard_size`, `size_is_minimum`,
  `min_deck_size` (the CR floor, never a build's larger target), `size_cap` (none
  where the family sets only a minimum), `family_size_choices`. The SPA's format
  table serves them; the browser derives `hasCommander` / `maxCopies` /
  `sideboardSize` / `sizeIsMinimum` from the served row and never compares a format
  id. `commander_eligibility` is false where there is no command zone. The media
  say what the formats are: Standard and Pioneer default to paper
  (`primary_medium`), Alchemy / Historic / Timeless are Arena-only.
- **The hub serves every declared Format.** `check_format` accepts the table;
  `set_deck_size` guards by family (a constructed size is any valid floor — an
  80-card Yorion deck; the Commander family keeps its dormant-override choices);
  the size cap fires only for the exact-size family; a constructed build below its
  CR floor is illegal at finalize and no override lifts it. Copy limits are an
  engine rule (`check_copy_add`, from `legality_audit.card_copy_limit` — the ONE
  exemption ladder, spanning every zone), Find strips by `at_copy_limit` (a 2-of
  stays findable; a basic never disappears), and a zone move is one call
  (`move_card`) with every rule run before the session changes.
- **The Commander-only surfaces are gated by `has_commander`, and say so.**
  Commander discovery (a 400, not an empty 200), the partner / Background avenue,
  the staples avenue (`staples.py` is curated for Commander — offered to Legacy it
  names Sol Ring), the bracket pill (WotC's multiplayer-Commander system), commander
  fit, grant coverage, commander suggestions, and edhrec play-rate as a quality
  read (a paper-EDH population) are `None` / skipped outside the family — never a
  silent no-op. A lane search is scoped to `deck_colors`: the commanders' colour
  identity under a command zone (the rule), the castable colours of the cards the
  deck runs otherwise (a description — the Find pips stay unlocked; a splash is the
  builder's call).
- **The template and every floor are the family's.** `_analysis/budgets.py` holds
  a `Template` per family — ordered `BudgetRow`s with a label, a band at the
  family's base size, and ONE membership read: a template role via `roles.role_of`
  (ADR-0051) or a plain type-line / mana-value predicate, honestly labelled and
  `advisory` (a creature count is a fact about the deck, shown beside the verdict,
  never a slot the tuner sources, never a cut pool, never a deviation — "threats"
  is deliberately not a role: ADR-0024's Shape-scaled closer advisory covers it).
  The Command Zone rows are verbatim at base 100; the constructed template (base
  60) is the honest minimum — interaction with sweepers folded in, card draw, an
  advisory creature count, no ramp or wipe row (archetype choices in 60-card); the
  limited template (base 40) is creatures, removal and the curve buckets.
  `_tuner/calibration.py` carries the metrics' floors per family, scaled from the
  template's base size; slots count copies (`CardClass.quantity`); the counted
  deck is commanders + main deck (`HydratedDeck.deck_records`) — a sideboard never
  shapes the avenues, the classes or a budget row. Size is exact only for the
  Commander family; a size-minimum family reports a `shortfall` toward its target.
- **The per-name copy model.** A card stays addable while its copies are under the
  Format's limit (an add carries `copy`; "go to four" is a swap like any other), a
  cut removes one copy, and a limited `pool` bounds both and makes every pool card
  free (the seam ADR-0055 fills).

**Considered and rejected.** Scaling the Command Zone bands to 60 cards (ADR-0029's
own reason for refusing: a 60-card Burn deck at 0.6 × 10 ramp is a misleading read).
A `threats` role from oracle text (ADR-0051: roles are views over the signal path;
a type-line count is a fact, and the closer advisory already exists). Sideboard
proposals from the tuner (needs a matchup model the substrate lacks; the sideboard
is the builder's, with the 15-card cap enforced). String compares on the format id
anywhere a family fact exists.

**Consequences.** ADR-0029's scope clause is revised (the refusal is gone; the
tuner is the deterministic spine for every family). `deck-tune` accepts every
format; `--bracket` on a non-commander deck is noted and ignored. The scorecard's
`size` gains `exact` / `shortfall`, budget rows gain `label` / `advisory`, swaps
carry `copy` / `quantity`, and the finalize report carries `below_minimum` — all
additive. The companion is priced like any other card the deck runs (its wildcard
/ USD cost counts): it is a card the builder must own to play, which is the reading
the cost readouts exist for. Non-goals: sideboard proposals, a matchup or metagame
model, bracket-scaled bands (ADR-0024 stands).

**Amended (the 2026-09-19 whole-change review).** Two departures from the build plan
were reviewed and accepted as shipped. `mtga-import --format` offers every
Arena-playable format (the Format's Arena flag, sealed and draft included), not every
format: a paper-only format is not a choice for an Arena collection. `win_conditions`
keeps a defaulted `game` parameter rather than a required one: the tuner passes the
resolved medium's game, and a direct caller gets the paper reading.
