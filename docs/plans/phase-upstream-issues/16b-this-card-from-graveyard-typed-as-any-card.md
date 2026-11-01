# Sproutback Trudge, Syrix, Worldheart Phoenix, Nether Shadow: "cast/return this card from your graveyard" typed as any card, or on the wrong zone

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Sproutback Trudge** (C21):
> This spell costs {X} less to cast, where X is the amount of life you gained this turn.
> Trample
> At the beginning of your end step, if you gained life this turn, you may cast this creature from your graveyard.

**Syrix, Carrier of the Flame** (NCC):
> Flying, haste
> At the beginning of each end step, if a creature card left your graveyard this turn, target Phoenix you control deals damage equal to its power to any target.
> Whenever another Phoenix you control dies, you may cast this card from your graveyard.

**Worldheart Phoenix** (CON):
> Flying
> You may cast this card from your graveyard by paying {W}{U}{B}{R}{G} rather than paying its mana cost. If you do, it enters with two +1/+1 counters on it.

**Nether Shadow** (4ED):
> Haste
> At the beginning of your upkeep, if this card is in your graveyard with three or more creature cards above it, you may put this card onto the battlefield.

## Observed at v0.118.0

Sproutback Trudge ("you may cast this creature from your graveyard"): `CastFromZone` with `target: Any`:

```json
{"effect": {"type": "CastFromZone", "target": {"type": "Any"}, "mode": "Cast"}, "optional": true}
```

Syrix ("you may cast this card from your graveyard"): same:

```json
{"effect": {"type": "CastFromZone", "target": {"type": "Any"}, "mode": "Cast"}, "optional": true}
```

Worldheart Phoenix: a static on your typed permanents, active on the battlefield (the card is in the graveyard); two `SwallowedClause` warnings:

```json
{"mode": {"CastWithAlternativeCost": {"cost": {"type": "Mana", "cost": {"type": "Cost", "shards": ["White", "Blue", "Black", "Red", "Green"]}}}}, "affected": {"type": "Typed", "controller": "You"}, "active_zones": ["Battlefield"]}
```

```json
[{"type": "SwallowedClause", "detector": "Replacement", "line_index": 1, "unit_span": {"last_line": 1, "end_byte": 161, "precision": "Exact"}, "items": [0]}, {"type": "SwallowedClause", "detector": "Condition_If", "line_index": 1, "unit_span": {"last_line": 1, "end_byte": 161, "precision": "Exact"}, "items": [0], "gap": {"guard": "you do"}}]
```

Nether Shadow ("if this card is in your graveyard with three or more creature cards above it, you may put this card onto the battlefield"):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "if this card is in your graveyard with three or more creature cards above it, you may put this card onto the battlefield"}, "optional": true}
```

## Expected

`target: SelfRef` / `affected: SelfRef` with `active_zones: [Graveyard]` for the cast permission; for Nether Shadow a typed condition (creature cards above it in your graveyard) with a `ChangeZone` of `SelfRef` from the graveyard.

## Why it matters

Read as written, Trudge casts any card and Worldheart Phoenix gives your battlefield permanents an alternative cost.
