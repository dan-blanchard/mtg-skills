<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11363 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Blood Lust: "If target creature has toughness 5 or greater, it gets …" declares no target, and both pumps land on the spell (SelfRef)

:robot: _AI text below_ :robot:

### Card(s)

Blood Lust

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`)

### Game mode

Unknown (found by reading the release card-data)

### Actual behavior

Oracle text:

> If target creature has toughness 5 or greater, it gets +4/-4 until end of turn. Otherwise, it gets +4/-X until end of turn, where X is its toughness minus 1.

The spell declares no target, and there is no condition on toughness 5 or greater. Both `Pump` nodes target `SelfRef`, the instant itself. The "Otherwise" between them is a residue, and that residue is the card's only coverage gap:

```json
{"effect": {"type": "Pump", "power": {"type": "Fixed", "value": 4}, "toughness": {"type": "Fixed", "value": -4}, "target": {"type": "SelfRef"}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "otherwise"}, "sub_ability": {"effect": {"type": "Pump", "power": {"type": "Fixed", "value": 4}, "toughness": {"type": "Quantity", "value": {"type": "Multiply", "factor": -1, "inner": {"type": "ClampMin", "inner": {"type": "Offset", "inner": {"type": "Ref", "qty": {"type": "Toughness", "scope": {"type": "Source"}}}, "offset": -1}, "minimum": 0}}}, "target": {"type": "SelfRef"}}, "duration": "UntilEndOfTurn"}}, "duration": "UntilEndOfTurn"}
```

The same `SelfRef` targets are in every release card-data checked, from v0.66.0 to v0.133.0.

### Expected behavior

> CR 115.1: Some spells and abilities require their controller to choose one or more targets for them. The targets are object(s) and/or player(s) the spell or ability will affect. These targets are declared as part of the process of putting the spell or ability on the stack. The targets can’t be changed except by another spell or ability that explicitly says it can do so.

Blood Lust targets a creature as it is cast. "It" is that creature in both branches, and X reads that creature's toughness. By the parse, Blood Lust declares no target, and both pumps land on the spell itself, so no creature is pumped. The `Toughness` of `Source` in the second branch also reads the spell, not the creature.

Expected parse: a targeted creature, then one branch gated on the target's toughness and an `else_ability` for "Otherwise", with both `Pump` nodes on `ParentTarget` and X as the target's toughness minus 1. Gore Vassal, which the coverage export reports as supported, already types the gate this card needs. Its "Then if that creature's toughness is 1 or greater, regenerate it" is:

```json
{"effect": {"type": "Regenerate", "target": {"type": "ParentTarget"}}, "condition": {"type": "TargetMatchesFilter", "filter": {"type": "Typed", "properties": [{"type": "PtComparison", "stat": "Toughness", "scope": "Current", "comparator": "GE", "value": {"type": "Fixed", "value": 1}}]}}}
```

For Blood Lust the same condition, with `value: 5`, gates the +4/-4 branch.

### Steps to reproduce

1. Control a 2/2 creature. Cast Blood Lust targeting it.
2. The creature should become 6/1 until end of turn. By the parse, the spell has no target and its pumps land on the spell itself, so the creature stays 2/2.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data.

Outcome read from the v0.133.0 engine source, not played.
