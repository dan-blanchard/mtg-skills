# Orcish Captain: the losing flip's "it gets -0/-2" is stamped `SelfRef` instead of the chosen Orc

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Orcish Captain** (FEM):
> {1}: Flip a coin. If you win the flip, target Orc creature gets +2/+0 until end of turn. If you lose the flip, it gets -0/-2 until end of turn.

## Observed at v0.118.0

The win outcome targets an Orc; the lose outcome's "it" is `SelfRef` (the Captain):

```json
{"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}, "win_effect": {"effect": {"type": "Pump", "power": {"type": "Fixed", "value": 2}, "toughness": {"type": "Fixed"}, "target": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Orc"}]}}, "duration": "UntilEndOfTurn"}, "lose_effect": {"effect": {"type": "Pump", "power": {"type": "Fixed"}, "toughness": {"type": "Fixed", "value": -2}, "target": {"type": "SelfRef"}}, "duration": "UntilEndOfTurn"}}
```

## Expected

The lose effect targets `ParentTarget`, the activated ability's target.

## Why it matters

The Captain shrinks itself on a lost flip.
