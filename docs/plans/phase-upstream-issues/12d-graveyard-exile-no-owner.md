# Rooting Moloch, Grime Gorger, Skullsnatcher: a graveyard exile with no owner on the filter

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Rooting Moloch** (J22):
> When this creature enters, exile target card with a cycling ability from your graveyard. Until the end of your next turn, you may play that card.
> Cycling {2} ({2}, Discard this card: Draw a card.)

**Grime Gorger** (NCC):
> Menace
> Whenever this creature attacks, exile up to one card of each card type from defending player's graveyard. Put a +1/+1 counter on this creature for each card exiled this way.

**Skullsnatcher** (PLST):
> Ninjutsu {B} ({B}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)
> Whenever this creature deals combat damage to a player, exile up to two target cards from that player's graveyard.

## Observed at v0.118.0

Rooting Moloch ("from your graveyard"); the permission that follows is on a `TrackedSet`:

```json
{"effect": {"type": "ChangeZone", "origin": "Graveyard", "destination": "Exile", "target": {"type": "Typed", "type_filters": ["Card"]}}, "sub_ability": {"effect": {"type": "GrantCastingPermission", "permission": {"type": "PlayFromExile", "duration": {"UntilEndOfNextTurnOf": {"player": {"type": "Controller"}}}}, "target": {"type": "TrackedSet"}}, "duration": {"UntilEndOfNextTurnOf": {"player": {"type": "Controller"}}}}}
```

Grime Gorger ("from defending player's graveyard"):

```json
{"type": "ChangeZone", "origin": "Graveyard", "destination": "Exile", "target": {"type": "Typed", "type_filters": ["Card"]}}
```

Skullsnatcher ("from that player's graveyard"):

```json
{"type": "ChangeZone", "origin": "Graveyard", "destination": "Exile", "target": {"type": "Typed", "type_filters": ["Card"], "properties": [{"type": "InZone", "zone": "Graveyard"}]}}
```

## Expected

`Owned` / `InZone` carrying the controller the clause names ("your", "defending player's", "that player's"). Rooting Moloch also lacks the "with a cycling ability" qualifier on the card filter.

## Why it matters

Without an owner the exile reads as any graveyard, so a read of "exiles from opponents' graveyards" cannot distinguish these.
