# Karfell Harbinger, Ethereal Valkyrie: "Spend this mana only to ..." and foretell clauses parked

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Karfell Harbinger** (KHM):
> {T}: Add {U}. Spend this mana only to foretell a card from your hand or cast an instant or sorcery spell.

**Ethereal Valkyrie** (KHC):
> Flying
> Whenever this creature enters or attacks, draw a card, then exile a card from your hand face down. It becomes foretold. Its foretell cost is its mana cost reduced by {2}. (On a later turn, you may cast it for its foretell cost, even if this creature has left the battlefield.)

## Observed at v0.118.0

Karfell Harbinger: the mana is typed; the spending restriction is a residue `sub_ability` of the mana ability:

```json
{"effect": {"type": "Mana", "produced": {"type": "Fixed", "colors": ["Blue"]}}, "cost": {"type": "Tap"}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "Spend this mana only to foretell a card from your hand or cast an instant or sorcery spell"}}, "is_mana_ability": true}
```

Ethereal Valkyrie: the draw and the face-down exile are typed; "It becomes foretold" has no node and the foretell-cost sentence is a residue:

```json
{"effect": {"type": "Draw", "count": {"type": "Fixed", "value": 1}, "target": {"type": "Controller"}}, "sub_ability": {"effect": {"type": "ChangeZone", "origin": "Hand", "destination": "Exile", "target": {"type": "Typed", "type_filters": ["Card"], "controller": "You", "properties": [{"type": "InZone", "zone": "Hand"}]}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "Its foretell cost is its mana cost reduced by {2}"}}}}
```

## Expected

A mana spend restriction typed with its spell / ability filter, including "foretell a card" as an action; a foretold status on the exiled card and a foretell cost expressed with `SelfManaCostReduced {reduction: 2}`, which Dream Devourer's static already carries.

## Why it matters

Without the restriction the Harbinger's mana reads as unrestricted blue.
