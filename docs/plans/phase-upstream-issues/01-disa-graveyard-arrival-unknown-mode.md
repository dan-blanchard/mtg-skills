# Disa the Restless: "put into your graveyard from anywhere other than the battlefield" parsed as an `Unknown` trigger mode

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Disa the Restless** (M3C):
> Whenever a Lhurgoyf permanent card is put into your graveyard from anywhere other than the battlefield, put it onto the battlefield.
> Whenever one or more creatures you control deal combat damage to a player, create a Tarmogoyf token.

**Countryside Crusher** (MMA):
> At the beginning of your upkeep, reveal the top card of your library. If it's a land card, put it into your graveyard and repeat this process.
> Whenever a land card is put into your graveyard from anywhere, put a +1/+1 counter on this creature.

## Observed at v0.118.0

Disa's first trigger keeps the whole trigger line as `mode.Unknown`; `origin`, `destination` and `valid_card` are absent, while the body is typed:

```json
{"mode": {"Unknown": "Whenever a Lhurgoyf permanent card is put into your graveyard from anywhere other than the battlefield"}, "execute": {"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "ParentTarget"}}}}
```

For comparison, the plain "from anywhere" form is typed (Countryside Crusher, second trigger):

```json
{"mode": "ChangesZone", "execute": {"effect": {"type": "PutCounter", "counter_type": "P1P1", "count": {"type": "Fixed", "value": 1}, "target": {"type": "SelfRef"}}}, "valid_card": {"type": "Typed", "type_filters": ["Land"], "properties": [{"type": "Owned", "controller": "You"}]}, "destination": "Graveyard", "valid_target": {"type": "Typed", "controller": "You"}}
```

Aside, same card: the second trigger's body ("create a Tarmogoyf token") is parked.

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "create a Tarmogoyf token"}}
```

## Expected

`mode: ChangesZone`, `destination: Graveyard`, `valid_card: Typed[Permanent, Subtype Lhurgoyf] + Owned{You}`, and a way to say the origin is "anywhere except the battlefield" (today `origin: null` means "from anywhere", so the grammar has no field for the exclusion; the grammar has no field for this today). The body (`ChangeZone` of `ParentTarget` to `Battlefield`) is already right.

## Why it matters

A trigger with `Unknown` mode has no event for any consumer to read: deck analysis cannot tell this is a graveyard-arrival payoff, and the engine has nothing to match against.
