# Furygale Flocking, Case of the Stashed Skeleton, Soovril: token keyword, suspect and zone owner dropped

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Furygale Flocking** (SOC):
> This spell costs {1} less to cast for each instant and sorcery card in your graveyard.
> For each opponent, create two 3/3 blue and red Elemental creature tokens with flying that attack that opponent this turn if able. They gain haste until end of turn.

**Case of the Stashed Skeleton** (MKM):
> When this Case enters, create a 2/1 black Skeleton creature token and suspect it. (It has menace and can't block.)
> To solve — You control no suspected Skeletons. (If unsolved, solve at the beginning of your end step.)
> Solved — {1}{B}, Sacrifice this Case: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.

**Soovril, Patient Antiquarian** (YSOS):
> Vigilance
> {T}: Put two time counters on target nonland card in exile that was put there from your graveyard this turn. If it doesn't have suspend, it gains suspend.

## Observed at v0.118.0

Furygale Flocking ("two 3/3 ... Elemental creature tokens with flying that attack that opponent"): `Token` has no `keywords`, and the record carries a `SwallowedClause` warning:

```json
{"type": "Token", "name": "Elemental", "power": {"type": "Fixed", "value": 3}, "toughness": {"type": "Fixed", "value": 3}, "types": ["Creature", "Elemental"], "colors": ["Blue", "Red"], "count": {"type": "Fixed", "value": 2}, "owner": {"type": "Controller"}}
```

```json
[{"type": "SwallowedClause", "detector": "Condition_If", "line_index": 1, "unit_span": {"first_line": 1, "last_line": 1, "start_byte": 87, "end_byte": 251, "precision": "Exact"}, "items": [1]}]
```

Case of the Stashed Skeleton ("create a 2/1 black Skeleton creature token and suspect it"): the `Token` alone, no `Suspect`:

```json
{"effect": {"type": "Token", "name": "Skeleton", "power": {"type": "Fixed", "value": 2}, "toughness": {"type": "Fixed", "value": 1}, "types": ["Creature", "Skeleton"], "colors": ["Black"], "count": {"type": "Fixed", "value": 1}, "owner": {"type": "Controller"}}}
```

Soovril ("nonland card in exile that was put there from your graveyard"): `ZoneChangedThisTurn` has `from`/`to` but no owner:

```json
{"type": "Typed", "type_filters": ["Card", {"Non": "Land"}], "properties": [{"type": "InZone", "zone": "Exile"}, {"type": "ZoneChangedThisTurn", "from": "Graveyard", "to": "Exile"}]}
```

## Expected

Tokens with `keywords: [Flying]`; a `Suspect` effect bound to the created token; an `Owned{You}` on the `ZoneChangedThisTurn` property.

## Why it matters

Each loses a single word that changes what the card does (a flying attacker, a suspected token, whose graveyard).
