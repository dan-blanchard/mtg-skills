# Arena's game logs check phase's parse

Phase's parse is the repo's only structured card source, and its misparses show up only
when a read happens to trip on one. MTG Arena runs its rules engine on Wizards' servers
and, with Detailed Logs on, writes every message it sends the client to `Player.log`:
for each spell and ability that resolves, the zone moves, damage, life, counters and
tokens it caused, and the object that caused them; for each triggered ability it puts on
the stack, the events just before. The client ships no rules engine (its IL2CPP metadata
holds only message translators and a state mirror), so the log is the engine's own
record of what each card did. Compared by hand on nine games (2026-11-09), every effect
Arena logged was one phase's parse predicts; the one structural difference, "exile it
instead" typed as a move out of the graveyard (Dissipate), became a `misparsed_shapes`
row and upstream issue 25.

**Decision.** `arena-crosscheck` (mtg-utils, a developer audit like
`deck-forge-phase-crosscheck`, never run in CI) reads the logs and scores each
resolution and fired trigger against phase's parse of the same ability.

- **Arena is evidence, not the referee.** It has rules bugs and Arena-only rulings. A
  disagreement is a lead, checked with `/rules-lawyer` before it is called a misparse.
  Phase wrong: a correction row with its `retirement_canary`, an upstream issue file, a
  backlog entry. Arena wrong: a row in `data/arena_crosscheck_ignore.toml` with its
  reason.
- **Only an ability's own effects count.** An annotation whose source is another object
  (a replacement another permanent applies, a graveyard-hate exile) is set aside.
- **Kinds, then strict checks** (`_arena_crosscheck.effects`). Arena's annotations and
  phase's effects in one vocabulary; then each fact phase states as fixed (an amount; who
  drew, gained life, controls the tokens; a token's, counter's, damaged or moved object's
  type; whose object moved) against what Arena logged. A count Arena exceeded passes when
  a permanent on that side has a replacement phase types for that event (Elspeth, Storm
  Slayer's doubler). Whether an effect may not happen is read per effect off the tree,
  never the text: optional (`effect_owner_optional`), conditional (`effect_conditional`:
  its wrapper's or its ability's condition, "When you do", "unless it escaped"), in a
  branch its controller doesn't decide (`in_uncertain_branch`), one of two alternatives
  (`effects_exclusive`), with no target required (`effect_targets_optional`), of a
  scaling amount, or after one of these in its chain. Such an effect not happening is
  `conditional`, and its count is a ceiling; a generic effect that changes only a rule (a
  permission, "can't block") is one Arena logs nothing for. Every tree read goes through
  `crosswalk`; a concept's `scope` is not "whose object"
  (`filter_controller_side(effect_filter(...))` is), and `effect_player_reach`'s `None`
  is "you" for a draw but unrestricted for damage.
- **Triggers** (`check.shown_by`). Each trigger Arena fired is checked one way against
  `crosswalk.trigger_def_event`: the events of the object Arena names as having set it
  off (its `TriggeringObject`, under any id it had), over its message and the three
  before (a cast, its targets and its mana arrive in separate messages); a trigger naming
  no object (a step's) reads its messages whole. A trigger phase predicts that Arena never
  fired is not checked yet. A reflexive "When you do" or delayed trigger, which Arena's
  card database links to its parent (`HiddenByAbilityIds`), is not scored.
- **Confident pairings only** (`_arena_crosscheck.align`). An Arena ability pairs with
  phase's at near-identical text (0.9, after reading Arena's mana symbols, `CARDNAME` and
  "this permanent" as phase's), by containment, by a keyword rule (an instance of an Arena
  keyword, its `BaseId`: Fading, Evoke, paired with phase's own ability for it), by a grant ("~ gains "…"" is the granting ability), or as
  one ability phase writes as two triggers (Ivora, Insatiable Heir). Anything weaker is
  listed as unsure and never scored: a wrong pairing is a false finding, or worse, a false
  pass. A static ability never resolves (CR 405.6b) and is never a candidate.
- **Rebalanced cards** are compared against the paper card's parse with a warning (Arena
  no longer plays them as rebalanced); a digital-only card only when phase parses it.
- **The logs are kept.** Arena overwrites `Player-prev.log` each launch, so each account
  on the Mac runs a LaunchAgent (machine setup, not in the repo) that gzips it into
  `/Users/Shared/mtg-arena-logs/<user>/` and keeps Detailed Logs on.
- **Per-pin reports.** Each run keeps `<archive>/reports/<PHASE_TAG>.json` (unless `--no-save-report`); rows
  are keyed by game and order, so `report.diff_reports` lists what a new pin's parse
  changed against the same games.

**Consequences.** A phase misparse that changes what a card does in play can now be found
from games already played, at the cost of a fuzzy text pairing, kept honest by scoring
only confident pairs. The check sees only cards that were played, only effects Arena
logs (no permissions, no library searches), and only the triggers that fired.
