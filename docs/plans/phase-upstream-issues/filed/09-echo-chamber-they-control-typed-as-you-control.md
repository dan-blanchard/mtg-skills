<!-- Status: FILED 2026-11-26 as https://github.com/phase-rs/phase/issues/11385 (against phase v0.134.0, commit 5d226a5; measured in phase's engine and independently verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Echo Chamber: "An opponent chooses target creature they control" is typed `controller: You`, so the opponent must pick one of the activator's creatures and the activator copies their own

:robot: _AI text below_ :robot:

### Card(s)

Echo Chamber (reported supported by the coverage export)

### Build/version

v0.134.0 5d226a5 (release card-data `card-data-0fd43dd7cf32923f.json`; the same parse is in v0.133.0)

### Game mode

Unknown (found by reading the release card-data; outcome measured with a throwaway integration test at the v0.134.0 tag, see Logs)

### Actual behavior

Oracle text:

> {4}, {T}: An opponent chooses target creature they control. Create a token that's a copy of that creature. That token gains haste until end of turn. Exile the token at the beginning of the next end step. Activate only as a sorcery.

The chooser is typed right (`target_chooser: Opponent`), but "they control" is typed as `controller: You`:

```json
{"effect": {"type": "TargetOnly", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}, "target_chooser": {"type": "Opponent"}}
```

Its follow-up copies that target: `{"type": "CopyTokenOf", "target": {"type": "ParentTarget"}, "owner": {"type": "Controller"}, "count": {"type": "Fixed", "value": 1}}`.

`You` resolves to the activator, so the slot announced by the opponent holds only the activator's creatures.

Measured at v0.134.0 through a real activation (the oracle text above through `parse_oracle_text`). P0 controls Echo Chamber, four Forests and a 2/2 "My Bear". P1 controls a 5/5 "Their Dragon". P0 activates the ability:

- The engine waits on `TargetSelection { player: P1 }` with one slot whose only legal target is My Bear.
- P1 choosing Their Dragon is rejected ("Illegal target selected").
- P1 choosing My Bear is accepted. After resolution P0 controls a token copy of My Bear.

The parser test for this sentence (`oracle_tests.rs`, "Echo Chamber") asserts only `target_chooser == Some(TargetFilter::Opponent)`, not the controller.

`crates/phase-ast/data/confirmed-misparses.toml` already holds two cards with the same `target_chooser: Opponent` + `controller: You` pair unsupported: Evangelize and Preacher (`target_wrong`, on "target creature of an opponent's choice they control"). Echo Chamber's sentence is worded differently and isn't listed there, so it is reported supported.

### Expected behavior

> CR 109.5: The words “you” and “your” on an object refer to the object’s controller, its would-be controller (if a player is attempting to play, cast, or activate it), or its owner (if it has no controller). For a static ability, this is the current controller of the object it’s on. For an activated ability, this is the player who activated the ability. For a triggered ability, this is the controller of the object when the ability triggered, unless it’s a delayed triggered ability. To determine the controller of a delayed triggered ability, see rules 603.7d–f.

> CR 115.1: Some spells and abilities require their controller to choose one or more targets for them. The targets are object(s) and/or player(s) the spell or ability will affect. These targets are declared as part of the process of putting the spell or ability on the stack. The targets can’t be changed except by another spell or ability that explicitly says it can do so.

"They" in "target creature they control" is the opponent who chooses, not the activator ("you", CR 109.5). The opponent targets one of their own creatures, and the activator gets a hasty token copy of it until the next end step.

Expected parse: the target filter's controller is the announcing opponent (the player who announces the slot), not `You`.

### Steps to reproduce

1. Control Echo Chamber and a 2/2 creature. Your opponent controls a 5/5 creature.
2. In your main phase, activate Echo Chamber.
3. The opponent is asked to choose a target, and only your 2/2 is offered. You get a copy of your own 2/2. By the rules, the opponent must choose their 5/5 (their only creature) and you get a 5/5 copy with haste.

### Logs/screenshots/game-state

Parse taken from the v0.134.0 release card-data (identical in v0.133.0). Outcome measured at the v0.134.0 tag with a throwaway test in `crates/engine/tests/`. It used `GameScenario::add_artifact_from_oracle`, `GameAction::ActivateAbility`, then `GameAction::ChooseTarget` for the opponent's slot:

```
PROBE echo activate ok=true err=None
PROBE echo ids: mine(P0)=ObjectId(1) theirs(P1)=ObjectId(2)
PROBE echo chooser=PlayerId(1) slot legal targets=[[Object(ObjectId(1))]]
PROBE echo select P1's own creature: ok=false err=Some(InvalidAction("Illegal target selected"))
PROBE echo select P0's creature: ok=true err=None
PROBE echo waiting_for after choice: Priority
PROBE echo tokens after resolution: ["My Bear (controller PlayerId(0))"]
PROBE echo chamber tapped=true
```
