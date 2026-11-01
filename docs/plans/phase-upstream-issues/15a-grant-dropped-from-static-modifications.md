# Chariot of the Sun, Valkyrie's Call: a keyword grant is left out of the effect's modifications

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Chariot of the Sun** (MIR):
> {2}, {T}: Until end of turn, target creature you control gains flying and has base toughness 1.

**Valkyrie's Call** (FDN):
> Whenever a nontoken, non-Angel creature you control dies, return that card to the battlefield under its owner's control with a +1/+1 counter on it. It has flying and is an Angel in addition to its other types.

## Observed at v0.118.0

Chariot of the Sun ("gains flying and has base toughness 1"): only `SetToughness` survives; the description keeps the whole phrase:

```json
{"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "ParentTarget"}, "modifications": [{"type": "SetToughness", "value": 1}]}], "duration": "UntilEndOfTurn", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}, "cost": {"type": "Composite", "costs": [{"type": "Mana", "cost": {"type": "Cost", "generic": 2}}, {"type": "Tap"}]}, "duration": "UntilEndOfTurn", "entry_onset": "WithEntry"}
```

Valkyrie's Call ("It has flying and is an Angel in addition to its other types"): only `AddSubtype Angel`:

```json
{"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "TriggeringSource"}, "enter_with_counters": [["P1P1", {"type": "Fixed", "value": 1}]]}, "sub_ability": {"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "TriggeringSource"}, "modifications": [{"type": "AddSubtype", "subtype": "Angel"}]}], "duration": "Permanent"}, "duration": "Permanent", "entry_onset": "WithEntry"}}
```

## Expected

`AddKeyword Flying` beside `SetToughness` / `AddSubtype`.

## Why it matters

The same shape appears on these cards, not re-quoted here: the Zendikons ("is a 4/4 Elemental creature with reach and haste"), Argivian Avenger, Guardian Zendikon, Jodah's Avenger, Urza's Avenger. The keyword is silently absent from every consumer.
