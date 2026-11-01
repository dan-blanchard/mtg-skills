# Cleansing Meditation, Skyclave Shade, Ichor Aberration: tracked set lost or unbound ("destroyed this way", "cast it from your graveyard")

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Cleansing Meditation** (TOR):
> Destroy all enchantments.
> Threshold — If there are seven or more cards in your graveyard, instead destroy all enchantments, then return all cards in your graveyard destroyed this way to the battlefield.

**Skyclave Shade** (PZNR):
> Kicker {2}{B}
> This creature can't block.
> If this creature was kicked, it enters with two +1/+1 counters on it.
> Landfall — Whenever a land you control enters, if this card is in your graveyard and it's your turn, you may cast it from your graveyard this turn.

**Ichor Aberration** (YONE):
> Flying, Defender
> As long as Ichor Aberration's power is 7 or greater, it can attack as though it didn't have defender.
> Whenever you proliferate, if Ichor Aberration is in your graveyard or on the battlefield, Ichor Aberration perpetually gets +1/+1. You may cast it from your graveyard this turn.

## Observed at v0.118.0

Cleansing Meditation, threshold branch: "return all cards in your graveyard destroyed this way" is a `ChangeZoneAll` over every card in your graveyard; the set the preceding `DestroyAll` produced is not carried:

```json
{"effect": {"type": "ChangeZoneAll", "origin": "Graveyard", "destination": "Battlefield", "target": {"type": "Typed", "type_filters": ["Card"], "controller": "You", "properties": [{"type": "InZone", "zone": "Graveyard"}]}}}
```

Skyclave Shade: "you may cast it from your graveyard" is a `GrantCastingPermission` on a `TrackedSet` nothing filled (the object is the card itself, in the graveyard):

```json
{"effect": {"type": "GrantCastingPermission", "permission": {"type": "PlayFromExile", "duration": "UntilEndOfTurn", "mode": "Cast"}, "target": {"type": "TrackedSet"}}, "optional": true}
```

Ichor Aberration, same shape after the perpetual pump:

```json
{"effect": {"type": "GrantCastingPermission", "permission": {"type": "PlayFromExile", "duration": "UntilEndOfTurn", "mode": "Cast"}, "target": {"type": "TrackedSet"}}}
```

## Expected

Cleansing Meditation: the `ChangeZoneAll` targets the tracked set of the preceding destroy (`TrackedSet`, as `GrantCastingPermission` already uses). Skyclave Shade / Ichor Aberration: a graveyard-cast permission whose target is `SelfRef` (permission type `PlayFromExile` is also the wrong name for a graveyard source).

## Why it matters

As parsed, Cleansing Meditation reanimates the whole graveyard (not just the enchantments), and the Shade/Aberration permissions grant nothing.
