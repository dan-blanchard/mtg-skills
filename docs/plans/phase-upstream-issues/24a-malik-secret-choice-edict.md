# Malik, Grim Manipulator: "you and target opponent each secretly choose a creature that player controls" parked, leaving the sacrifice

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Malik, Grim Manipulator** (SLX):
> When Malik, Grim Manipulator enters, you and target opponent each secretly choose a creature that player controls. Then those choices are revealed, and that player sacrifices those creatures.
> Whenever an opponent sacrifices a creature, you create a Treasure token.

## Observed at v0.118.0

Both choice sentences are `unrecognized_clause_head`; the `Sacrifice` of a `TrackedSet` that nothing filled survives with no player:

```json
{"mode": "ChangesZone", "execute": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "you and target opponent each secretly choose a creature that player controls"}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "those choices are revealed"}, "sub_ability": {"effect": {"type": "Sacrifice", "target": {"type": "TrackedSet"}, "count": {"type": "Fixed", "value": 1}}}}}, "valid_card": {"type": "SelfRef"}, "destination": "Battlefield", "valid_target": {"type": "Player"}}
```

## Expected

A two-player simultaneous secret choice, then a `Sacrifice` by the targeted opponent of the chosen creatures.

## Why it matters

The ETB edict is not recognizable as one.
