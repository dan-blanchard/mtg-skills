# Dark Sphere, Torrent of Lava, Blinding Powder: damage-prevention clauses parked

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Dark Sphere** (DRK):
> {T}, Sacrifice this artifact: The next time a source of your choice would deal damage to you this turn, prevent half that damage, rounded down.

**Torrent of Lava** (MIR):
> Torrent of Lava deals X damage to each creature without flying.
> As long as Torrent of Lava is on the stack, each creature has "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn."

**Blinding Powder** (BOK):
> Equipped creature has "Unattach Blinding Powder: Prevent all combat damage that would be dealt to this creature this turn."
> Equip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)

## Observed at v0.118.0

Dark Sphere ("prevent half that damage, rounded down"):

```json
{"effect": {"type": "Unimplemented", "name": "prevent", "description": "prevent half that damage, rounded down"}, "cost": {"type": "Composite", "costs": [{"type": "Tap"}, {"type": "Sacrifice", "target": {"type": "SelfRef"}, "count": 1}]}}
```

Torrent of Lava (the granted "{T}: Prevent the next 1 damage ..." is `granter_reference_unreached`):

```json
{"effect": {"type": "Unimplemented", "name": "granter_reference_unreached", "description": "As long as ~ is on the stack, each creature has \"{T}: Prevent the next 1 damage that would be dealt to ~ by ~ this turn.\""}}
```

Blinding Powder (the granted "Unattach ~: Prevent all combat damage ..."):

```json
{"effect": {"type": "Unimplemented", "name": "granter_reference_unreached", "description": "Equipped creature has \"Unattach ~: Prevent all combat damage that would be dealt to ~ this turn.\""}}
```

## Expected

A prevention effect with a halving amount (Dark Sphere); a granted activated ability with a prevention effect (Torrent of Lava, Blinding Powder).

## Why it matters

Related to the damage-prevention issue (11).
