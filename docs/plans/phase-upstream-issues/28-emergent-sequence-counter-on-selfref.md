# Emergent Sequence: "Put a +1/+1 counter on it" binds the counter to the sorcery (`SelfRef`) instead of the fetched land

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Emergent Sequence** (STX):
> Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. That land becomes a 0/0 green and blue Fractal creature that's still a land. Put a +1/+1 counter on it for each land you had enter the battlefield under your control this turn.

## Observed at v0.131.0

The animation correctly names the fetched land (`affected: ParentTarget`), but the counter that follows it targets `SelfRef`, the sorcery itself. The record is marked `confirmed_misparse: "wrong_object"`. (At v0.118.0 the last sentence was a `put_counter_tail` residue; v0.131.0 types it with the wrong object.) Trimmed to the last two links:

```json
{"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "ParentTarget"}, "modifications": [{"type": "SetPower", "value": 0}, {"type": "SetToughness", "value": 0}, {"type": "SetColor", "colors": ["Green", "Blue"]}, {"type": "AddType", "core_type": "Creature"}, {"type": "RemoveAllSubtypes", "set": "Creature"}, {"type": "AddSubtype", "subtype": "Fractal"}]}], "duration": "Permanent"}, "sub_ability": {"effect": {"type": "PutCounter", "counter_type": "P1P1", "count": {"type": "Ref", "qty": {"type": "BattlefieldEntriesThisTurn", "player": {"type": "Controller"}, "filter": {"type": "Typed", "type_filters": ["Land"]}}}, "target": {"type": "SelfRef"}}}, "duration": "Permanent"}
```

## Expected

The `PutCounter` target is the same object the animation affects (`ParentTarget`, the land put onto the battlefield); the count is already right.

## Why it matters

As parsed, the counters go on a sorcery that is leaving the stack, and the land enters as a 0/0 creature that dies at once.
