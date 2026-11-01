# Canopy Cover, Hidden Guerrillas, Warmonger's Chariot and others: `affected` stamped `SelfRef` / `TriggeringSource` when it names another object

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Canopy Cover** (WWK):
> Enchant creature
> Enchanted creature can't be blocked except by creatures with flying or reach.
> Enchanted creature can't be the target of spells or abilities your opponents control.

**Hidden Guerrillas** (USG):
> When an opponent casts an artifact spell, if this permanent is an enchantment, it becomes a 5/3 Soldier creature with trample.

**Warmonger's Chariot** (CNS):
> Equipped creature gets +2/+2.
> As long as equipped creature has defender, it can attack as though it didn't have defender.
> Equip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)

## Observed at v0.118.0

Canopy Cover ("Enchanted creature can't be the target of spells or abilities your opponents control"): the grant lands on the Aura and "your opponents control" is dropped (the first line is typed correctly):

```json
{"mode": "Continuous", "affected": {"type": "SelfRef"}, "modifications": [{"type": "AddKeyword", "keyword": "Hexproof"}]}
```

Hidden Guerrillas ("it becomes a 5/3 ..." -- `it` is this permanent, not the cast spell):

```json
{"mode": "Continuous", "affected": {"type": "TriggeringSource"}, "modifications": [{"type": "SetPower", "value": 5}, {"type": "SetToughness", "value": 3}, {"type": "AddKeyword", "keyword": "Trample"}, {"type": "AddType", "core_type": "Creature"}, {"type": "RemoveAllSubtypes", "set": "Creature"}, {"type": "AddSubtype", "subtype": "Soldier"}]}
```

Warmonger's Chariot (second static; should affect the equipped creature):

```json
{"mode": "CanAttackWithDefender", "affected": {"type": "SelfRef"}, "condition": {"type": "IsPresent", "filter": {"type": "Typed", "type_filters": ["Creature"], "properties": [{"type": "EquippedBy"}, {"type": "WithKeyword", "value": "Defender"}]}}}
```

Same stamp on these cards (all re-checked at v0.118.0):

- **Mesmerizing Benthid**: the Illusion token's "that creature doesn't untap during its controller's next untap step" is `CantUntap {affected: SelfRef}` on the token.
- **Tsabo's Web**: "Each land with an activated ability that isn't a mana ability doesn't untap" is `CantUntap {affected: SelfRef}`.
- **Alacrian Armory**: "that permanent ... becomes saddled / becomes an artifact creature" is `BecomeSaddled {target: TriggeringSource}` plus an animation with `affected: SelfRef`.
- **Animate Artifact**: "As long as enchanted artifact isn't a creature, it's an artifact creature" is a `Continuous` static with `affected: SelfRef` (the Aura) while its condition reads the enchanted artifact.

## Expected

`affected` is the enchanted / equipped / chosen object, or the named population (all lands with ...; the targeted permanent; the permanent itself for Hidden Guerrillas).

## Why it matters

The effect lands on the wrong object: an Aura gives itself hexproof, the Equipment itself can attack, a spell is animated instead of the permanent.
