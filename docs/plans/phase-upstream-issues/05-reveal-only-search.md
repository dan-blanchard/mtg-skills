# Grim Reminder, Chaos Mutation: a reveal-only search is typed as a move to hand

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Grim Reminder** (MRD):
> Search your library for a nonland card and reveal it. Each opponent who cast a spell this turn with the same name as that card loses 6 life. Then shuffle.
> {B}{B}: Return this card from your graveyard to your hand. Activate only during your upkeep.

**Chaos Mutation** (40K):
> Exile any number of target creatures controlled by different players. For each creature exiled this way, its controller reveals cards from the top of their library until they reveal a creature card, puts that card onto the battlefield, then puts the rest on the bottom of their library in a random order.

## Observed at v0.118.0

Grim Reminder: `SearchLibrary {reveal: true}` is followed by a `ChangeZone` Library->Hand (the card is only revealed), and the per-opponent life loss is parked as `unbound_subject`:

```json
{"effect": {"type": "SearchLibrary", "filter": {"type": "Typed", "type_filters": ["Card", {"Non": "Land"}]}, "count": {"type": "Fixed", "value": 1}, "reveal": true}, "sub_ability": {"effect": {"type": "ChangeZone", "origin": "Library", "destination": "Hand", "target": {"type": "Any"}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unbound_subject", "description": "who cast a spell this turn with the same name as that card loses 6 life"}, "sub_ability": {"effect": {"type": "Shuffle", "target": {"type": "Controller"}}}, "player_scope": {"type": "Opponent"}}}}
```

Chaos Mutation: "its controller reveals ... until they reveal a creature card, puts that card onto the battlefield" -- `kept_destination` is `Hand`:

```json
{"effect": {"type": "RevealUntil", "player": {"type": "ParentTargetController"}, "filter": {"type": "Typed", "type_filters": ["Creature"]}, "count": {"type": "Fixed", "value": 1}, "kept_destination": "Hand", "rest_destination": "Library", "rest_order": "random"}, "repeat_for": {"type": "Ref", "qty": {"type": "FilteredTrackedSetSize", "filter": {"type": "Typed", "type_filters": ["Creature"]}, "caused_by": "Exiled"}}}
```

## Expected

Grim Reminder: `SearchLibrary` with `reveal: true` and no destination move; the clause as `LoseLife 6` for each opponent matching a "cast a spell this turn with the same name" filter. Chaos Mutation: `kept_destination: Battlefield`.

## Why it matters

The tutor looks like it gets a card into hand; the Chaos Mutation reveal puts creatures into hand instead of onto the battlefield.
