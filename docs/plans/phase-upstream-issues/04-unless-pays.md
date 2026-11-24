# Rhystic Tutor: "unless any player pays" sits on a placeholder effect

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Rhystic Tutor** (PCY):
> Unless any player pays {2}, search your library for a card, put that card into your hand, then shuffle.

**Geistlight Snare** (VOW):
> This spell costs {1} less to cast if you control a Spirit. It also costs {1} less to cast if you control an enchantment.
> Counter target spell unless its controller pays {3}.

## Observed at v0.131.0

Rhystic Tutor: the head effect is `Unimplemented "empty"` carrying `unless_pay`; the search chain hangs beneath it and the search itself carries no `unless_pay`:

```json
{"effect": {"type": "Unimplemented", "name": "empty"}, "sub_ability": {"effect": {"type": "SearchLibrary", "filter": {"type": "Typed", "type_filters": ["Card"]}, "count": {"type": "Fixed", "value": 1}}, "sub_ability": {"effect": {"type": "ChangeZone", "origin": "Library", "destination": "Hand", "target": {"type": "Any"}}, "sub_ability": {"effect": {"type": "Shuffle", "target": {"type": "Controller"}}}}}, "unless_pay": {"cost": {"type": "Mana", "cost": {"type": "Cost", "generic": 2}}, "payer": {"type": "AllPlayers"}}}
```

The typed form, for comparison (Geistlight Snare's `Counter`):

```json
{"effect": {"type": "Counter", "target": {"type": "StackSpell"}}, "unless_pay": {"cost": {"type": "Mana", "cost": {"type": "Cost", "generic": 3}}, "payer": {"type": "ParentTargetController"}}}
```

Rune Snag, drafted here at v0.118.0, is fixed at v0.131.0: its `Counter` carries `unless_pay` with a `ManaDynamic` cost (`Sum` of `Fixed 2` and `2 x ObjectCount` of cards named Rune Snag in graveyards).

## Expected

Question: is a head `Unimplemented "empty"` with `unless_pay` meant to gate its `sub_ability` chain at runtime? If so the record is as designed and only the placeholder name misleads; if not, `unless_pay` belongs on the `SearchLibrary`, as it is on `Counter`.

## Why it matters

Consumers reading the tree see an unimplemented head and cannot tell the payment is a gate on the search. 33 commander-legal cards (by the records' own `legalities`) carry `Unsupported unless clause` at v0.131.0, a related residue (see the census issue).
