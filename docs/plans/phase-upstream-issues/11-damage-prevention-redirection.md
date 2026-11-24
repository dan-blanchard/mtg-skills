# Treacherous Link, Prairie Dog, Well-Laid Plans and others: damage prevention and redirection parked

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Treacherous Link** (ULG):
> Enchant creature
> All damage that would be dealt to enchanted creature is dealt to its controller instead.

**Prairie Dog** (OTJ):
> Lifelink
> At the beginning of your end step, if you haven't cast a spell from your hand this turn, put a +1/+1 counter on this creature.
> {4}{W}: Until end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead.

**Light of Sanction** (RAV), typed at v0.131.0, for comparison:
> Prevent all damage that would be dealt to creatures you control by sources you control.

## Observed at v0.131.0

Treacherous Link ("is dealt to its controller instead"):

```json
{"effect": {"type": "Unimplemented", "name": "replacement_structure", "description": "Replacement pattern matched but line failed replacement parser: All damage that would be dealt to enchanted creature is dealt to its controller instead."}}
```

Prairie Dog (the activated ability's "if you would put ... counters, put that many plus one instead"):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_replacement", "description": "if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead"}, "cost": {"type": "Mana", "cost": {"type": "Cost", "shards": ["White"], "generic": 4}}, "duration": "UntilEndOfTurn"}
```

Light of Sanction, the typed form (a `replacement_structure` residue at v0.94.0 through v0.118.0, typed again at v0.131.0):

```json
{"event": "DamageDone", "mode": {"type": "Mandatory"}, "valid_card": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}, "damage_source_filter": {"type": "Typed", "controller": "You"}, "shield_kind": {"Prevention": {"amount": "All"}}}
```

Same family, each a residue in its `abilities` (all re-checked at v0.131.0):

- **Well-Laid Plans** (`prevention_source_scope`; `replacement_structure` at v0.118.0): "Prevent all damage that would be dealt to a creature by another creature if they share a color."
- **Camel** (`as_long_as_gate`): "As long as this creature is attacking, prevent all damage Deserts would deal to this creature and to creatures banded with this creature."
- **Forcefield** (`unrecognized_clause_head`): "The next time an unblocked creature of your choice would deal combat damage to you this turn, prevent all but 1 of that damage."

Light of Sanction and Ironscale Hydra, drafted here at v0.118.0, are fixed at v0.131.0.

## Expected

`DamageDone` replacements with a prevention/redirect modification and the source/recipient filters spelled out, as Light of Sanction now has (for Treacherous Link, a redirect to the enchanted creature's controller; for Well-Laid Plans, a source filter relating the two creatures' colors). For Prairie Dog, a replacement on counter placement.

## Why it matters

Census at v0.131.0 (commander-legal, by the records' own `legalities`): `replacement_structure` 27 cards, `unparsed_replacement` 46, `prevent_damage_recipient_target_role` 15, `prevention_source_scope` 2. A prevention parked as a residue is a card that prevents nothing.
