# Guardian of the Ages: "it loses defender and gains trample" parked as `unparsed_condition`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Guardian of the Ages** (M14):
> Defender (This creature can't attack.)
> When a creature attacks you or a planeswalker you control, if this creature has defender, it loses defender and gains trample.

## Observed at v0.118.0

The attack-watcher is typed (`Attacks` on a creature attacking you or a planeswalker you control); its body is a residue:

```json
{"mode": "Attacks", "execute": {"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "if ~ has defender, it loses defender and gains trample"}}, "valid_card": {"type": "Typed", "type_filters": ["Creature"]}, "valid_target": {"type": "Controller"}, "attack_target_filter": "PlayerOrPlaneswalker"}
```

## Expected

The intervening-if (`has defender`) typed as a condition, with a `RemoveKeyword Defender` and `AddKeyword Trample` effect (for comparison, Torpid Moloch's "loses defender until end of turn" is typed that way: `GenericEffect` / `RemoveKeyword Defender`).

## Why it matters

A read looking for defenders that can attack cannot see this card.
