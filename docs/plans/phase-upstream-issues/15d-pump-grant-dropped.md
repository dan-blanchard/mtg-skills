# Tromp the Domains: "gain trample and get +1/+1 for each ..." keeps the pump and drops the keyword

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Tromp the Domains** (TSR):
> Domain — Until end of turn, creatures you control gain trample and get +1/+1 for each basic land type among lands you control.

## Observed at v0.118.0

A bare `PumpAll`; no `AddKeyword Trample` anywhere in the record:

```json
{"effect": {"type": "PumpAll", "power": {"type": "Quantity", "value": {"type": "Ref", "qty": {"type": "BasicLandTypeCount", "controller": "You"}}}, "toughness": {"type": "Quantity", "value": {"type": "Ref", "qty": {"type": "BasicLandTypeCount", "controller": "You"}}}, "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}, "duration": "UntilEndOfTurn"}
```

## Expected

A `PumpAll` plus a `GenericEffect` granting `AddKeyword Trample` to the same population for the same duration (or one effect carrying both).

## Why it matters

The same shape appears on these cards, not re-quoted here: Haldir, Lorien Lieutenant; Stolen Vitality ("Otherwise, it gains first strike"); Indominus Rex, Alpha and Priest of Possibility ("The same is true for ..." keeps only the first keyword).
