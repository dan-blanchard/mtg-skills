# Irenicus's Vile Duplication, Will of the Temur: a copy's "except ... has flying" exception is dropped or misread as a subtype

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Irenicus's Vile Duplication** (CLB):
> Create a token that's a copy of target creature you control, except the token has flying and it isn't legendary.

**Will of the Temur** (TDC):
> Choose one. If you control a commander as you cast this spell, you may choose both instead.
> • Create a token that's a copy of target permanent, except it's a 4/4 Dragon creature with flying in addition to its other types.
> • Target player draws cards equal to the greatest mana value among permanents you control.

## Observed at v0.118.0

Irenicus's Vile Duplication ("except the token has flying and it isn't legendary"): only the legendary removal survives:

```json
{"type": "CopyTokenOf", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}, "owner": {"type": "Controller"}, "count": {"type": "Fixed", "value": 1}, "additional_modifications": [{"type": "RemoveSupertype", "supertype": "Legendary"}]}
```

Will of the Temur ("a 4/4 Dragon creature with flying"): the keyword becomes subtypes `With` and `Flying`:

```json
{"type": "CopyTokenOf", "target": {"type": "Typed", "type_filters": ["Permanent"]}, "owner": {"type": "Controller"}, "count": {"type": "Fixed", "value": 1}, "additional_modifications": [{"type": "SetPower", "value": 4}, {"type": "SetToughness", "value": 4}, {"type": "AddSubtype", "subtype": "Dragon"}, {"type": "AddType", "core_type": "Creature"}, {"type": "AddSubtype", "subtype": "With"}, {"type": "AddSubtype", "subtype": "Flying"}]}
```

## Expected

`additional_modifications` containing `AddKeyword Flying` (and no `AddSubtype With` / `AddSubtype Flying`).

## Why it matters

The copy token loses flying (Irenicus) or gains two nonsense creature types (Will). The same shape appears on these cards, not re-quoted here: Leonardo da Vinci, Sauron the Necromancer, Kaya Intangible Slayer, Dino DNA.
