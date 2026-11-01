# Boxing Ring: "Activate only if ..." parsed as a residue sub-ability instead of an activation restriction

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Boxing Ring** (NCC):
> Whenever a creature you control enters, it fights up to one target creature you don't control with the same mana value.
> {T}: Create a Treasure token. Activate only if you control a creature that fought this turn.

**Grim Reminder** (MRD):
> Search your library for a nonland card and reveal it. Each opponent who cast a spell this turn with the same name as that card loses 6 life. Then shuffle.
> {B}{B}: Return this card from your graveyard to your hand. Activate only during your upkeep.

## Observed at v0.118.0

Boxing Ring: the restriction becomes a `sub_ability` of the ability (and is truncated: "this turn" is lost):

```json
{"effect": {"type": "Token", "name": "Treasure", "power": {"type": "Fixed"}, "toughness": {"type": "Fixed"}, "types": ["Artifact", "Treasure"], "count": {"type": "Fixed", "value": 1}, "owner": {"type": "Controller"}}, "cost": {"type": "Tap"}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "Activate only if you control a creature that fought"}, "duration": "UntilEndOfTurn"}}
```

Phase types other restrictions on `activation_restrictions` (Grim Reminder's graveyard ability):

```json
{"effect": {"type": "ChangeZone", "origin": "Graveyard", "destination": "Hand", "target": {"type": "SelfRef"}}, "cost": {"type": "Mana", "cost": {"type": "Cost", "shards": ["Black", "Black"]}}, "activation_restrictions": [{"type": "DuringYourUpkeep"}], "activation_zone": "Graveyard"}
```

## Expected

An `activation_restrictions` entry with a state condition (a `QuantityCheck`/`ObjectCount` over creatures you control that fought this turn).

## Why it matters

The Treasure ability is typed as unconditional, so a ramp/mana-source read counts it as always available.
