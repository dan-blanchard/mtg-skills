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
resolution and fired trigger against phase's parse of the same ability, and each
trigger phase's parse expects on an object's own event against the ability instances
Arena created.

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
  spell's own "Exile ~" has its type checked against the spell's other movers. Life
  a damaged player loses and the counters damage removes are the damage's, no effect
  of their own: loyalty counters from a damaged planeswalker (CR 120.3c, 306.8) and
  defense counters from a damaged battle (CR 120.3h, 310.6), read off the logged
  object's type and the counter's kind, at most the damage dealt to it (a
  planeswalker with one loyalty counter dealt 3 damage loses one). A damaged
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
- **Counted amounts** (`_arena_crosscheck.amounts`; added 2026-11-27). An amount
  phase writes as a count is evaluated on the board the log shows and checked like
  a fixed one, under the same check name with " (counted)" (its `checks` row,
  pass or fail; `explain_excess` passes an excess a token, damage, draw, life or
  counter replacement on its controller's side explains, as for fixed amounts).
  The answer is determined once, when the effect is applied (CR 608.2h), so the
  board is the one the resolution's message began with (a message's objects and
  zones are as it leaves them: the reader keeps each object's and zone's state
  from before the message, `Resolution.permanents`), and the count is left out
  (`board-changed`) when that message changed the battlefield, a power, a
  counter, or an object's controller, types or colors (`log.BOARD_ANNOTATIONS`)
  before the resolution began, or the resolution did before the amount's
  first annotation ("gets +1/+0 until end of turn. It deals damage equal to its
  power"). What it evaluates: a fixed number and the X Arena logged (the own X,
  or the X paid for a permanent's spell its enters ability reads), with an
  offset, a factor, or divided and rounded the way the card says (CR 107.1a:
  "X plus 2", "twice X", "half X, rounded down"); permanents a filter matches
  (`ObjectCount`), every filter part decidable from the log (`crosswalk.
  filter_admits` with a `LoggedObject`, sides relative to the resolution's
  controller, "another" not its own permanent); the distinct colors among them;
  the power or toughness of the ability's own permanent or of its one target, as
  last logged (its last known information if it left, CR 608.2h); the number of
  opponents or players. An evaluated count is no ceiling for being a count (its
  value is known); an effect that may not happen for another reason still is.
  Everything else is listed on the row (`count_unchecked`, by reason): another
  quantity (cards in a zone, a mana value, mana spent, counters, an event's
  amount, a tracked group), an object it can't place (`that creature`, a
  triggering object), a filter property the log can't show (`filter`: counters,
  power, a name). An amount locked in before the resolution is an X (CR 601.2b:
  announced as the spell is cast), which the X check reads with the logged X.
  Damage another object deals for the resolution (a bite) is that object's in the
  log, set aside by the own-effects rule, so it is not checked. Measured on
  2026-11-27: archive and live logs (47 games) 9 resolutions gained a count check,
  9 checks passed, 0 failed, 8 rows left unchecked; the corpus (95 games) 13
  resolutions, 21 checks passed, 0 failed, 20 rows unchecked. The tool's faults
  before it settled were its own: the board read after the message (Ouroboroid's
  power after its counters), and an evaluated count kept as a ceiling. No
  resolution, trigger, own-event or watched status moved, and no existing check.
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
  text with a parse of one half. A
  reflexive "When you do" or delayed trigger, which Arena's card database links to its
  parent (`HiddenByAbilityIds`), is not scored; an emblem's ability, which the database
  links to the ability that made the emblem, is its source card's (CR 114.1), compared
  with phase's emblem. A game rule's own ability with no card behind it (speed's
  trigger, CR 702.179d; earthbend's return, CR 701.66a) is a `rules-object`, scored
  where `check.RULES_OBJECTS` / `HOLDER_ABILITIES` give its kinds.
- **The reverse check: a trigger phase expects that Arena never fired**
  (`check.Checker.expected`, the report's `expected` rows; added 2026-11-27). The
  log reader records each event of one object itself (`log.ObjectEvent`): it entered
  the battlefield (a move there, or a created token, CR 111.2), left it (a leave to a
  graveyard is a death, CR 700.4), was cast, attacked (its attack state went from
  declared to attacking: a creature unselected before the attack is locked in goes
  back from declared to none, and an attack trigger won't trigger for one put onto
  the battlefield attacking, CR 508.3a, which never "attacked", CR 508.4), blocked
  (likewise), or became blocked (a declared blocker names it; two blockers are one
  event, CR 509.1h). With it go the abilities Arena lists on the object
  (`uniqueAbilities`, which Arena keeps current: a granted haste appears and goes; a
  leave reads the battlefield object's, CR 603.10a), the cards on the battlefield
  (for a leave, with those that left it in the same message), and every instance
  Arena created from it (its source or parent, under any id it had) from the event's
  message until the turn ended (a dies trigger's instance is logged ahead of its
  move, and ordering and target choices can put an instance several messages
  later). An instance whose `TriggeringObject` names another object is not offered.
  An annotation a full resync (`GameStateType_Full`) repeats, the same id with the
  same content, opens no second event (16 events were opened twice over both log
  sets); an id a later message reuses for another annotation is a rollback, and an
  event from an annotation numbered from it on is `rolled-back` (10 events, all
  cancelled casts: Phlage, Titan of Fire's Fury's escape undone, the same object id
  then cast as another card). The forward check reads each repeat once too: that
  removed 6 resolution rows over both sets, each a resync's second copy (Blessed
  Ghoul, Teferi, Time Raveler, Urza's Saga; Mistmeadow Council, Kaito, Bane of
  Nightmares, Wilt in the Heat), and no other row; the 3 repeated trigger records
  were mana abilities, which make no trigger row. Those games' later resolution
  rows shift one key against a baseline saved before, so the baseline is saved
  again once this lands.

  Each trigger of the card's face (a double-faced card's other face is not on the
  battlefield, CR 712.8) that watches that event of the card alone
  (`crosswalk.watches_itself`, not "~ or another"; enters, dies, leaves, a zone
  change, cast, attacks, blocks, becomes blocked; a zone change's zones against the
  move's; not `taps`, which an attack shows only without vigilance, nor damage,
  counters or targeting) is one row, keyed by its event's place in the game and its
  trigger's text, so a parse that adds or drops a trigger moves no other row's key.
  A pin that only rewords a trigger's phase text gives its rows new keys, so the
  step-10 diff drops them (no change listed for them, never a wrong one). An
  instance answers at most one row: of the events offered it with a row whose
  trigger it pairs with (the same `align.pair` as the forward check), the last,
  and none when that row is answered already. Arena's `TriggeringObject` names the
  object, never which of its events (an enter and an attack name the same id, a
  leave the id the enter had), so the order decides, and a row left unanswered
  though an instance offered it pairs with its trigger is `unfired-unsure`: the
  log can't tell which event that instance was for. With two events of one object
  and the instances logged after both, the later row is `fired` and the earlier
  `unfired-unsure`, whether one instance came or two: a haste creature's attack
  instance, a doubled attack trigger (Isshin, Two Heavens as One), a doubled leave,
  or both triggers of an "enters or leaves the battlefield" ability put on the
  stack after the leave (a second Bilbo, Retired Burglar put into the graveyard by
  the legend rule). The later row's `fired` assumes an instance logged after both
  events is the later one's. An instance that pairs with one row only answers it:
  an enter instance logged after the creature died at once (Woodfall Primus,
  beside its persist) is the enter's. `fired`: an instance answers it. `unfired`, the finding:
  none did, though Arena lists a triggered ability on the object that pairs with
  it, and none of these explains it. Each of the rest is counted, never a finding,
  in the order decided: `face-down` (Arena's `isFacedown`: no abilities, CR 708.2,
  no enters triggers, CR 708.3); `copy` (Arena's `isCopy`, or a token of a card's
  printing: a copy effect may make exceptions, CR 707.9, and a spell's copy, which
  Arena logs with a cast move, isn't cast, CR 707.10); `rolled-back`; `game-over`
  (the game or the log ended before the turn did); `suppressed` (a card on the
  battlefield whose static stops the event from triggering abilities, phase's
  `SuppressTriggers` mode, `crosswalk.trigger_suppressions`: Hushbringer's
  "Creatures entering the battlefield or dying don't cause abilities to trigger",
  which its ruling says holds for a creature dying at the same time. Entering
  silences the triggers expected on an enter; dying silences dies and leaves
  triggers and a zone change whose every move starts on the battlefield, never a
  "whenever you sacrifice" trigger nor a dying card's own "put into a graveyard
  from anywhere", which Hushbringer's rulings say still trigger. A suppressor of
  opponents' triggers, Elesh Norn, Mother of Machines, spares its controller's;
  one of creatures, a noncreature's. An event name this reader doesn't map
  silences every trigger); `rebalanced` (an A- card, scored against the paper card's parse);
  `unfired-unsure` (an instance from the object pairs with no phase trigger
  confidently: it could be this one); `no-abilities` (Arena lists none: it lost
  them); `unfired-unpaired` (no ability Arena lists pairs with it);
  `arena-not-triggered` (Arena files the ability that pairs as no triggered
  ability: evoke's and offspring's are not); `unfired-conditional`
  (`crosswalk.trigger_gates`: an intervening "if", CR 603.4, a limit, any trigger
  field beyond the event it watches, a condition at the head of its effect, or a
  clause phase parked anywhere in it; a "may" or an "unless" is no gate, since such
  a trigger goes on the stack regardless, CR 603.5: 31 of 32 "may" triggers fired,
  the 32nd had no legal target); `unfired-targeted` (Arena's ability says "target",
  CR 115.10a, or is a keyword, by its `BaseId` or a pairing by the keyword, whose
  rule targets: Backup's, CR 702.165a, Mentor's, CR 702.134a, which Arena may file
  bare; with no legal target Arena creates no instance at all, CR 603.3d, as
  Affectionate Indrik showed entering onto a board with no opposing creature;
  `crosswalk.effect_targets` alone also counts scry's controller); `ignored`. An
  object the log shows no card for, a token's own printing, and a card phase
  doesn't parse get no rows. Measured on 2026-11-27 (phase v0.133.0): the owner's
  40 archived games 194 `fired`, 4 `unfired-conditional` (Emeritus of Abundance's
  eight lands not met), 5 `arena-not-triggered` (evoke); the corpus's 95 games 342
  `fired`, 11 `unfired-conditional`, 5 `arena-not-triggered` (evoke, offspring), 1
  `unfired-targeted`; 0 `unfired` on either. Its tool faults were pairings: Brigid,
  Clachan's Heart's "enters or transforms into ~" paired with the transform trigger
  alone until a split's second event could be more than a word, and Brinebound
  Gift's split then paired half with Brine Comber's trigger until a split's halves
  had to be on one face. No resolution or trigger row of either set changed.
- **The watched check: a trigger watching other objects** (`check.Checker.watched`,
  the report's `watched` rows; added 2026-11-27). Each object event also records
  every permanent on the battlefield at it (`log.BoardObject`: its id, card, seat,
  listed abilities, copy and face-down marks, and whether it entered or left the
  battlefield in that message), and the log keeps every ability instance Arena
  created (`log.InstanceLog`) with the objects it came from and the object Arena
  says set it off (`TriggeringObject`). For an enter the board is the battlefield
  after the move, newcomers included (CR 603.6a: "all permanents on the
  battlefield (including the newcomers) are checked"); for a leave, with what left
  in the same message (CR 603.10a: leaves-the-battlefield abilities look back in
  time). Each trigger of a watcher's card's face (`check.watches_other`) that
  watches that kind of event (enters, dies, leaves, attacks, blocks, becomes
  blocked, cast; working on the battlefield, its `trigger_zones`; zones against the
  move's) with an object filter that is not the card alone (Blood Artist's "~ or
  another creature" included) and matches the event's object is one row on the
  watcher. Matching is `crosswalk.filter_admits` given a `crosswalk.LoggedObject`,
  strict: the logged types, subtypes, supertypes and colors, the filter's
  controller and `Owned` side relative to the watcher's controller, token or not,
  "another" (not the watcher), mana value from the card's record only when the
  record is surely the object's (not a copy or a token, CR 707.2; not face down;
  not a card with faces, CR 712.8, 715.4, 709.3; not one with a prototype, whose
  prototyped spell and permanent have only the prototype's mana cost, CR 718.3b:
  Phyrexian Fleshgorger's record is 7; no X); for a cast, the caster (`valid_target`: you, an opponent, any) and
  any spell when phase writes no spell filter ("Whenever you cast a spell"). A
  filter that rules the object out yields no row; one that asks what the log
  can't show (power, a keyword, "attacking", what it is attached to) is
  `filter-unknown`, never a guess. A trigger on "one or more" objects (phase's
  `batched`) is one row for that message's objects.

  An instance answers a row only when Arena names the object that set it off and
  the row's event is that object's, earlier in the same turn; of such rows the
  latest, and nothing when it is answered already, so a doubled trigger's extra
  instance (Elesh Norn, Mother of Machines) answers no earlier event. Every
  instance that answered a row over both log sets had that link; one without it
  answers nothing and leaves the row it pairs with `unfired-unsure`, as does one
  answering another of the object's events. An instance Arena files under another
  ability (`HiddenByAbilityIds`) pairs here: Arena files there not only a "When
  you do" but an ability it shares with a token another card makes (Sazh's
  Chocobo's landfall under the ability that makes Zabu), and a "When you do" pairs
  with no watcher trigger. In the own-event check such an instance answers no
  row but leaves the row it pairs with `unfired-unsure`, never `unfired` (no
  landed own-event row moved).
  Statuses (`check.WATCHED_STATUSES`, in the order decided): `face-down` or `copy`
  (the watcher; a copy of a spell, which isn't cast, CR 707.10), `rolled-back`,
  `filter-unknown`, `fired`, `game-over`, `watcher-moved` (the watcher entered or
  left in the event's message, other than its own event: whether at the same time
  the log can't tell), `watcher-left` (a cast, the watcher leaving the battlefield
  later that turn: it may have been sacrificed as a cost, and cast triggers trigger
  only once the costs are paid, CR 601.2i; deliberately broad, any leave that
  turn, since a cost's payment is logged in messages of its own after the cast
  move and this read doesn't follow them, so it only loses findings), `suppressed` (by the watcher's
  controller: Elesh Norn silences its opponents' permanents' triggers), then the
  own-event check's `rebalanced`, `unfired-unsure`, `no-abilities`,
  `unfired-unpaired`, `arena-not-triggered`, `unfired-conditional` (a cast
  trigger's caster is no gate here), `unfired-targeted`, `ignored`, `unfired`.
  Rows are keyed by the event's place in the game, the watcher's log id and the
  trigger's text. Out of this piece: triggers in other zones (a graveyard's, a
  hand's, an emblem's, the command zone's), `changes_zone` watchers (the log
  records no move between other zones), "whenever you sacrifice", a player's
  event with no object filter ("Whenever you attack", "attacks or blocks"),
  damage, counters and targeting, and tokens as watchers (no card behind them).
  An open limit: a phased-out permanent is treated as though it doesn't exist (CR
  702.26b), but no log over both sets shows phasing (no annotation or object key
  naming it beyond the step changes, and no card that phases anything out among
  the logged objects), so a phased-out watcher or object would be read as
  present.
  Measured on 2026-11-27 (phase v0.133.0), archive and live logs, 47 games: 90
  `fired`, 34 `filter-unknown`, 11 `unfired-conditional`, 5 `copy`, 1
  `game-over`, 1 `watcher-left`; the corpus, 95 games: 287 `fired`, 49
  `filter-unknown`, 9 `unfired-conditional`, 4 `game-over`, 3 `copy`, 3
  `rolled-back`, 2 `watcher-left`; 0 `unfired` on either. Its tool fault was the
  `HiddenByAbilityIds` exclusion above (Sazh's Chocobo's landfall read
  `unfired` three times, Glacierwood Siege's cast trigger ten times
  `arena-not-triggered` or `game-over`). No resolution, trigger or own-event
  row moved.
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
  `--no-save-report`); rows are keyed by game and order within their section
  (`resolutions`, `triggers`, `expected`), so `report.diff_reports` lists
  what a new pin's parse changed against the same games. `bump-phase-pin`'s step 10 (step 9 until the tree-coverage step was added) reruns
  the crosscheck under the new pin over the archive alone (`--no-live`) and puts that
  diff in its triage report, advisory only: it never fails the bump. A report saved
  before the reverse check has no `expected` rows, so they diff only once the
  baseline is saved again.

**Consequences.** A phase misparse that changes what a card does in play can now be found
from games already played, at the cost of a fuzzy text pairing, kept honest by scoring
only confident pairs. The check sees only cards that were played, only effects Arena
logs (no permissions, no library searches), and of the triggers Arena never fired only
those phase expects on an object's own event, unconditional and untargeted.
