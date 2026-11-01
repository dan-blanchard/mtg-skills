# Fraying Line, Worms of the Earth: a payment or choice made by another player is stamped `Controller`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Fraying Line** (CLB):
> When this artifact enters, put a rope counter on target creature you control.
> At the beginning of each player's upkeep, that player may pay {2}. If they do, they put a rope counter on a creature they control. Otherwise, exile this artifact and each creature without a rope counter on it, then remove all rope counters from all creatures.

**Worms of the Earth** (DRK):
> Players can't play lands.
> Lands can't enter the battlefield.
> At the beginning of each upkeep, any player may sacrifice two lands of their choice or have this enchantment deal 5 damage to that player. If a player does either, destroy this enchantment.

## Observed at v0.118.0

Fraying Line ("that player may pay {2}"): `PayCost.payer` is `Controller`; the counter placed is correctly `ScopedPlayer`:

```json
{"effect": {"type": "PayCost", "cost": {"type": "Mana", "cost": {"type": "Cost", "generic": 2}}, "payer": {"type": "Controller"}}, "sub_ability": {"effect": {"type": "PutCounter", "counter_type": "rope", "count": {"type": "Fixed", "value": 1}, "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "ScopedPlayer"}}, "else_ability": "…", "condition": {"type": "EffectOutcome", "signal": "OptionalEffectPerformed"}}, "optional": true}
```

Worms of the Earth ("any player may sacrifice two lands ... or have this enchantment deal 5 damage to that player"): `chooser` is `Controller`, with `optional_for: AnyPlayer` on the wrapper:

```json
{"effect": {"type": "ChooseOneOf", "chooser": {"type": "Controller"}, "branches": [{"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Land"]}, "count": {"type": "Fixed", "value": 2}}}, {"effect": {"type": "DealDamage", "amount": {"type": "Fixed", "value": 5}, "target": {"type": "TriggeringPlayer"}}}]}, "sub_ability": {"effect": {"type": "Destroy", "target": {"type": "SelfRef"}}}, "optional": true, "optional_for": "AnyPlayer"}
```

## Expected

`payer` / `chooser` is the scoped or triggering player (`ScopedPlayer` / `TriggeringPlayer`).

## Why it matters

The else-branch ("Otherwise, exile ...") then reads as the controller's own choice.
