# Battle-Scarred Goblin, Fire Juggler: "deals N damage to each creature blocking it" typed as damage to every creature

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Battle-Scarred Goblin** (LTR):
> Whenever this creature becomes blocked, it deals 1 damage to each creature blocking it.

**Fire Juggler** (MOR):
> Whenever this creature becomes blocked, clash with an opponent. If you win, this creature deals 4 damage to each creature blocking it. (Each clashing player reveals the top card of their library, then puts that card on their choice of the top or bottom. A player wins if their card had a greater mana value.)

## Observed at v0.118.0

Battle-Scarred Goblin:

```json
{"effect": {"type": "DamageAll", "amount": {"type": "Fixed", "value": 1}, "target": {"type": "Typed", "type_filters": ["Creature"]}}}
```

Fire Juggler (after the clash):

```json
{"effect": {"type": "DamageAll", "amount": {"type": "Fixed", "value": 4}, "target": {"type": "Typed", "type_filters": ["Creature"]}}, "condition": {"type": "EventOutcomeWon"}}
```

## Expected

The `DamageAll` target filter restricted to creatures blocking the source, so only the blockers are hit; the grammar has no filter property for "blocking this creature" that I could confirm in the card-data.

## Why it matters

As parsed, a becomes-blocked trigger is a symmetric board sweep.
