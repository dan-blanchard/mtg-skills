# Mirrormind Crown: the token-copy replacement is parked as an `as_long_as_gate` residue

Phase tag: v0.118.0 (`card-data-v0.118.0.json`).

## Card

**Mirrormind Crown** (ECL), Artifact — Equipment, {4}:
> As long as this Equipment is attached to a creature, the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of equipped creature.
> Equip {2}

## Observed at v0.118.0

The first ability is emitted as a Spell ability whose effect is a residue:

```json
{"kind": "Spell", "effect": {"type": "Unimplemented", "name": "as_long_as_gate", "description": "As long as ~ is attached to a creature, the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of equipped creature."}}
```

The equip ability is typed.

## Expected

A conditional `CreateToken` replacement, the shape Anointed Procession's "If an effect would create one or more tokens under your control, it creates twice that many instead" already has (`token_owner_scope: You`), with the condition "this Equipment is attached to a creature", a once-each-turn limit, and the created tokens being copies of the equipped creature (an optional replacement: "you may instead").

## Why it matters

The card is a token-copy engine for any token-making deck (it is in Prismari Artistry's upgrade guides as a copy-your-best-creature piece); parked, it reads as an Equipment with no ability, so a tokens-matter or copy-matters read sees nothing.
