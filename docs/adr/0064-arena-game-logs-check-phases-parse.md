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
  phase's effects in one vocabulary; then each fact phase states as fixed (an amount; a
  pump's power and toughness change; who drew, gained life, controls the tokens; a
  token's, counter's, damaged or moved object's type; whose object moved) against what
  Arena logged. An amount that is the X the spell or ability was cast with is fixed
  too: Arena logs the chosen X (a persistent `CastingTimeOption` of type 2) on the
  object, and a permanent keeps its spell's id as it resolves, so an enters ability
  reads its permanent's (CR 107.3m; only an amount phase writes as the X paid, and
  never after the permanent left and came back under a new id). An effect of a
  delayed trigger the ability sets up (`effect_is_delayed`) belongs to that
  trigger's own resolution and is left out. A count Arena exceeded passes when
  a permanent on that side has a replacement phase types for that event (Elspeth, Storm
  Slayer's doubler). Whether an effect may not happen is read per effect off the tree,
  never the text: optional (`effect_owner_optional`), conditional (`effect_conditional`:
  its wrapper's or its ability's condition, "When you do", "unless it escaped"), in a
  branch its controller doesn't decide (`in_uncertain_branch`), one of two alternatives
  (`effects_exclusive`), with no target required (`effect_targets_optional`), of a
  scaling amount, or after one of these in its chain. Such an effect not happening is
  `conditional`, and its count is a ceiling; a generic effect that changes only a rule (a
  permission, "can't block") is one Arena logs nothing for. So is a group effect over
  the permanents of one name when Arena's board held none ("each other creature you
  control named Baloth Packhunter"), and a Class's new level, which shows only through a
  static it gives. Arena's conjure is a move out of `Limbo`, a poison counter a counter
  on a player, an ability the resolution targets leaving the stack a counter (CR 701.6a,
  though Arena files it under that ability's source), and ending the turn an exile of
  everything on the stack, the resolving spell included (CR 724.1b): neither that nor a
  spell's own "Exile ~" has its type checked against the spell's other movers. A damaged
  player passes a "target player or planeswalker" (`crosswalk.effect_reaches_player`).
  A player's counter goes to the side phase names (Fynn's "that player": the player
  an attacking creature of yours hit, an opponent, CR 510.1b, 506.2), and an object
  whose control changed ends up under the side the effect names (gaining control:
  you; giving it: `crosswalk.control_recipient_scope`). A Case's solve is the
  designation Arena marks the Case with during the resolution (CR 719.3b), a
  persistent annotation numbered inside it. Every tree read goes through
  `crosswalk`; a concept's `scope` is not "whose object"
  (`filter_controller_side(effect_filter(...))` is), and `effect_player_reach`'s `None`
  is "you" for a draw but unrestricted for damage. It is "you" only when the effect
  names no other player: "its controller draws a card" (a recipient read through
  another object) can be either side. An object's type is not checked when one of
  the effects that could have moved or damaged it takes an object of any type.
- **Triggers** (`check.shown_by`). Each trigger Arena fired is checked one way against
  `crosswalk.trigger_def_event`: the events of the object Arena names as having set it
  off (its `TriggeringObject`, under any id it had), over its message and the three
  before, and the spell's cast for as long as the spell is on the stack (each mana tap
  and target choice is a message of its own); a trigger naming no object (a step's)
  reads its message whole, since Arena can log it ahead of its event, and the three
  before. A created token entered the battlefield (CR 111.2), though Arena logs no zone
  move for it; a creature put onto the battlefield attacking never "attacked" (CR
  508.4), so its attack state isn't an attack. Two known limits: a cause-less trigger
  reads events logged after it in its message, so any such event satisfies it; and a
  combined "enters or dies" ability with a long effect can still pair by its whole
  text with a parse of one half. A trigger phase predicts that Arena never fired is
  not checked yet. A
  reflexive "When you do" or delayed trigger, which Arena's card database links to its
  parent (`HiddenByAbilityIds`), is not scored; an emblem's ability, which the database
  links to the ability that made the emblem, is its source card's (CR 114.1), compared
  with phase's emblem. A game rule's own ability with no card behind it (speed's
  trigger, CR 702.179d; earthbend's return, CR 701.66a) is a `rules-object`, scored
  where `check.RULES_OBJECTS` / `HOLDER_ABILITIES` give its kinds.
- **Confident pairings only** (`_arena_crosscheck.align`). An Arena ability pairs with
  phase's at near-identical text (0.9, after reading Arena's mana symbols, `CARDNAME`,
  "this permanent" and a leading ability word, which has no rules meaning, CR 207.2c,
  as phase's; difflib's autojunk off, which scored any long text near 0), by
  containment, by a keyword rule (an instance of an Arena
  keyword, its `BaseId`: Fading, Evoke, Mobilize, Offspring, paired with phase's own
  ability for it; a Case's "To solve" with the trigger whose effect is `SolveCase`), by a
  Saga chapter's number (Arena files a chapter under `SagaChapter` with its
  `BaseIdNumeral`; phase calls the trigger "Chapter N"), by a grant ("~ gains "…"" is the
  granting ability), by a modal trigger's condition (phase describes "When ~ enters,
  choose one — …" as "When ~ enters"), or as one ability phase writes as two triggers
  ("… and whenever …", "… and at the beginning of …", "enters or dies": Ivora,
  Insatiable Heir; Gathering Stone; Stitcher's Supplier), each half pairing with a
  different trigger. Anything weaker is
  listed as unsure and never scored: a wrong pairing is a false finding, or worse, a false
  pass. An instance of a keyword phase lists on the card, or the card's own ability
  grants it (`crosswalk.own_keyword_bodies`: Bloodbraid Marauder's cascade), with no
  ability to compare it to (prowess, ward, warp's delayed exile, ninjutsu's untexted
  activation) is `keyword-only`. That is the last resort: only once nothing else
  pairs, and only on a card with no keyword ability phase wrote out ("CR 702.…: …")
  that the instance could be. One of a keyword the card neither lists, grants itself,
  nor prints in its record is `granted-keyword`: another object gave it (a decayed
  counter, an Alchemy "perpetually gains"). A static ability never resolves (CR 405.6b)
  and is never a candidate.
- **Rebalanced cards** are compared against the paper card's parse with a warning (Arena
  no longer plays them as rebalanced); a digital-only card only when phase parses it.
- **The logs are kept.** Arena overwrites `Player-prev.log` each launch, so each account
  on the Mac runs a LaunchAgent (machine setup, not in the repo) that gzips it into
  `/Users/Shared/mtg-arena-logs/<user>/` and keeps Detailed Logs on.
- **Per-pin reports.** Each run keeps `<archive>/reports/<PHASE_TAG>.json` (unless
  `--no-save-report`); rows are keyed by game and order, so `report.diff_reports` lists
  what a new pin's parse changed against the same games. `bump-phase-pin`'s step 10 (step 9 until the tree-coverage step was added) reruns
  the crosscheck under the new pin over the archive alone (`--no-live`) and puts that
  diff in its triage report, advisory only: it never fails the bump.

**Consequences.** A phase misparse that changes what a card does in play can now be found
from games already played, at the cost of a fuzzy text pairing, kept honest by scoring
only confident pairs. The check sees only cards that were played, only effects Arena
logs (no permissions, no library searches), and only the triggers that fired.
