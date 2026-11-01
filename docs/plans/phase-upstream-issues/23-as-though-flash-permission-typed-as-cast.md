# Rootwater Shaman, Aluren: "as though it had flash" permissions typed as a one-shot cast, or parked

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Rootwater Shaman** (TMP):
> You may cast Aura spells with enchant creature as though they had flash.

**Aluren** (TMP):
> Any player may cast creature spells with mana value 3 or less without paying their mana costs and as though they had flash.

## Observed at v0.118.0

Rootwater Shaman ("You may cast Aura spells with enchant creature as though they had flash"): an `optional` `CastFromZone` ability of `Typed[Subtype Aura]`, with no static permission and no `casting_options`:

```json
{"effect": {"type": "CastFromZone", "target": {"type": "Typed", "type_filters": [{"Subtype": "Aura"}]}, "mode": "Cast"}, "optional": true}
```

Aluren ("as though they had flash" plus "without paying their mana costs", for any player):

```json
{"effect": {"type": "Unimplemented", "name": "static_structure", "description": "Static pattern matched but line failed static parser: Any player may cast creature spells with mana value 3 or less without paying their mana costs and as though they had flash."}}
```

## Expected

A static casting permission scoped to the spell filter (as the own-spell `casting_options: [{kind: AsThoughHadFlash}]` and `AddKeyword Flash` forms are typed elsewhere in the same card-data), with the Aura's `enchant creature` restriction and, for Aluren, a free-cast permission for every player.

## Why it matters

As parsed Rootwater Shaman reads as an activated cast of an Aura; the continuous permission it grants is not represented.
