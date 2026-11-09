# Forger's Foundry: a mana ability's "when you spend this mana … exile that spell instead" parked as `Unimplemented`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Forger's Foundry** (OTC):
> {T}: Add {U}. When you spend this mana to cast an instant or sorcery spell with mana value 3 or less, you may exile that spell instead of putting it into its owner's graveyard as it resolves.
> {3}{U}{U}, {T}: You may cast any number of spells from among cards exiled with this artifact without paying their mana costs. Activate only as a sorcery.

**Primal Amulet // Primal Wellspring** (XLN), the back face for comparison:
> {T}: Add one mana of any color. When that mana is spent to cast an instant or sorcery spell, copy that spell and you may choose new targets for the copy.

## Observed at v0.118.0

The rider is a residue on the mana ability:

```json
{"effect": {"type": "Mana", "produced": {"type": "Fixed", "colors": ["Blue"]}}, "cost": {"type": "Tap"}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "When you spend this mana to cast an instant or sorcery spell with mana value 3 or less, you may exile that spell instead of putting it into its owner's graveyard as it resolves"}}}
```

Primal Wellspring's rider (the back face's record) is typed as a grant on the `Mana` effect:

```json
{"effect": {"type": "Mana", "produced": {"type": "AnyOneColor", "count": {"type": "Fixed", "value": 1}, "color_options": ["White", "Blue", "Black", "Red", "Green"]}, "grants": [{"TriggerOnSpend": {"filter": {"type": "Or", "filters": [{"type": "Typed", "type_filters": ["Instant"]}, {"type": "Typed", "type_filters": ["Sorcery"]}]}, "ability": {"effect": {"type": "CopySpell", "target": {"type": "TriggeringSource"}, "retarget": {"type": "MayChooseNewTargets"}}}}}]}}
```

## Expected

A `TriggerOnSpend` grant whose filter is instants and sorceries with `Cmc LE 3` and whose ability is an optional `ExileResolvingSpellInsteadOfGraveyard` (the form phase types for Rod of Absorption's "exile it instead of putting it into a graveyard as it resolves").

## Why it matters

The card's engine (exile cheap spells, then cast them from exile with its second ability) is invisible: nothing exiles cards "with Forger's Foundry", so the second ability has nothing to cast.
