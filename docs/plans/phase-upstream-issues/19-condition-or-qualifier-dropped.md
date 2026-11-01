# Phyrexian Unlife, Eye of Singularity, Herald of Vengeance: a condition or same-name qualifier dropped from a static or effect

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Phyrexian Unlife** (WOT):
> You don't lose the game for having 0 or less life.
> As long as you have 0 or less life, all damage is dealt to you as though its source had infect. (Damage is dealt to you in the form of poison counters.)

**Eye of Singularity** (VIS):
> When this enchantment enters, destroy each permanent with the same name as another permanent, except for basic lands. They can't be regenerated.
> Whenever a permanent other than a basic land enters, destroy all other permanents with that name. They can't be regenerated.

**Herald of Vengeance** (YSNC):
> Flying
> When Herald of Vengeance enters the battlefield, destroy each permanent you don't control that has the same name as a permanent that dealt damage to you last turn.

## Observed at v0.118.0

Phyrexian Unlife: the first sentence's `CantLoseTheGame` is right (it is unconditional), but the second sentence's static keeps only its condition (`LifeTotal <= 0`) and has no modifications -- the as-though-infect damage effect is gone:

```json
[{"mode": "CantLoseTheGame", "affected": {"type": "Typed", "controller": "You"}}, {"mode": "Continuous", "affected": {"type": "SelfRef"}, "condition": {"type": "QuantityComparison", "lhs": {"type": "Ref", "qty": {"type": "LifeTotal", "player": {"type": "Controller"}}}, "comparator": "LE", "rhs": {"type": "Fixed"}}}]
```

Eye of Singularity, enters trigger ("each permanent with the same name as another permanent, except for basic lands"): an unrestricted `DestroyAll` of `Permanent`:

```json
{"effect": {"type": "DestroyAll", "target": {"type": "Typed", "type_filters": ["Permanent"]}, "cant_regenerate": true}}
```

Herald of Vengeance ("each permanent you don't control that has the same name as a permanent that dealt damage to you last turn"):

```json
{"effect": {"type": "DestroyAll", "target": {"type": "Typed", "type_filters": ["Permanent"], "controller": "Opponent"}}}
```

## Expected

A modification on the second static for "all damage is dealt to you as though its source had infect"; and, on the `DestroyAll` targets, a filter for "same name as another permanent" and an exclusion of basic lands; the grammar has no field for the same-name filter today.

## Why it matters

Eye of Singularity as parsed destroys every permanent, Herald every permanent an opponent controls.
