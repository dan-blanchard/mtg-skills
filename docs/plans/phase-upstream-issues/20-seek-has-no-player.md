# Variable Solutions: `Seek` carries no player, then an extra `ChangeZone` moves the result

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Variable Solutions** (YSOS):
> If X is 1, seek a basic land card and put it onto the battlefield tapped.
> If X is 2, each opponent sacrifices an artifact of their choice.
> If X is 3, conjure a random creature card with mana value X onto the battlefield.
> If X is 4 or more, you gain 2 life. Then do all of the above.

## Observed at v0.118.0

"seek a basic land card and put it onto the battlefield tapped": `Seek` has `destination: Hand` and no player, then a `ChangeZone` to the battlefield of `ParentTarget`. The conjure clause is `unrecognized_clause_head` and "do all of the above" is a residue:

```json
[{"effect": {"type": "Seek", "filter": {"type": "Typed", "type_filters": ["Land"], "properties": [{"type": "HasSupertype", "value": "Basic"}]}, "count": {"type": "Fixed", "value": 1}, "destination": "Hand"}, "sub_ability": {"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "ParentTarget"}, "enter_tapped": true}, "sub_ability": {"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Artifact"]}, "count": {"type": "Fixed", "value": 1}}}}}, {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "conjure a random creature card with mana value X onto the battlefield"}}, {"effect": {"type": "GainLife", "amount": {"type": "Fixed", "value": 2}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "do all of the above"}}, "condition": {"type": "QuantityCheck", "lhs": {"type": "Ref", "qty": {"type": "CostXPaid"}}, "comparator": "GE", "rhs": {"type": "Fixed", "value": 4}}}]
```

## Expected

`Seek` with a player and a destination of `Battlefield` (tapped).

## Why it matters

The seek puts the card in hand first; no consumer can tell whose library is searched.
