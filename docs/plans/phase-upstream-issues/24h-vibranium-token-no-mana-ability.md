# Vibranium tokens (Shuri's Fabricator and others): the `Token` node has no mana ability

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Shuri's Fabricator** (MSC):
> When this artifact enters, create two tapped Vibranium tokens. (They're artifacts with indestructible and "{T}: Add {C}. This mana can't be spent to cast a nonartifact spell.")
> {6}, {T}: Return target artifact card from your graveyard to the battlefield with a finality counter on it. Activate only as a sorcery. (If a permanent with a finality counter on it would be put into a graveyard, exile it instead.)

## Observed at v0.118.0

The maker's `Token` node is `types: [Artifact, Vibranium]` with `keywords: [Indestructible]` and no ability:

```json
{"effect": {"type": "Token", "name": "Vibranium", "power": {"type": "Fixed"}, "toughness": {"type": "Fixed"}, "types": ["Artifact", "Vibranium"], "keywords": ["Indestructible"], "tapped": true, "count": {"type": "Fixed", "value": 2}, "owner": {"type": "Controller"}}}
```

`known-tokens-v0.118.0.toml` has the rules text ("{T}: Add {C}. This mana can't be spent to cast a nonartifact spell.") but the token body carries only `keywords = ["Indestructible"]`, with no ability field.

## Expected

A mana ability on the token (as Treasure / Powerstone carry theirs), or a note that the engine special-cases the Vibranium subtype. Question: does the engine tap a Vibranium token for mana at all? Also affects T'Challa, the Black Panther; Dora Milaje Elite; Vibranium Mining Mech; The Great Mound (not re-quoted).

## Why it matters

A token that cannot make mana changes what the five makers do.
