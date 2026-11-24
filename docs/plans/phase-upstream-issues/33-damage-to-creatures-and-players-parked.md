# Disorder, Incite Rebellion, Mob Verdict: damage to a player and the creatures they control, in one clause, parked whole

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Disorder** (7ED):
> Disorder deals 2 damage to each white creature and each player who controls a white creature.

**Incite Rebellion** (C14):
> For each player, Incite Rebellion deals damage to that player and each creature that player controls equal to the number of creatures they control.

**Mob Verdict** (MKC):
> Secret council — Each player secretly votes for another player, then those votes are revealed. For each vote an opponent received, Mob Verdict deals 2 damage to that player and each creature that player controls. For each vote you received, draw a card.

## Observed at v0.131.0

Disorder:

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "deal 2 damage to each white creature and each player who controls a white creature"}}
```

Incite Rebellion (the per-player loop is typed; its body is not):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "deal damage to that player and each creature that player controls equal to the number of creatures they control"}, "player_scope": {"type": "All"}}
```

Mob Verdict, third link of the chain (the votes before it are parked too, as `unrecognized_clause_head`):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_quantity", "description": "For each vote an opponent received, ~ deals 2 damage to that player and each creature that player controls"}}
```

At v0.118.0 each was typed with one half dropped, and Disorder and Incite Rebellion carried a `SwallowedClause` warning (`detector: DamageSubjectConjunction`): Disorder a `DamageAll` over white creatures (no players), Incite Rebellion a `DealDamage` to `ScopedPlayer` only (no creatures), Mob Verdict a `DealDamage` of 2 to `TriggeringPlayer` (no creatures, no per-vote count).

## Expected

Both recipients typed: a `DamageAll` over the creature filter (white creatures; creatures `ScopedPlayer` controls) followed by damage to the players (each player who controls a white creature; `ScopedPlayer`), with Incite Rebellion's amount the `ObjectCount` of creatures that player controls, as v0.118.0 already typed it. For Mob Verdict, the damage repeated for each vote the opponent received (the vote itself is the separate "secret council" gap).

## Why it matters

These are sweepers, and parked they deal no damage at all. At v0.118.0 a consumer saw half of each (Disorder hit only creatures; Incite Rebellion and Mob Verdict only players).
