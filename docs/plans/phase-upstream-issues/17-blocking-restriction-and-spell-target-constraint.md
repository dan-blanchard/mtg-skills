# Glorfindel Dauntless Rescuer, Wyll's Reversal: "can't be blocked by more than one creature" typed as a typeless filter; "with one or more targets" dropped

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Glorfindel, Dauntless Rescuer** (LTR):
> Whenever you scry, choose one and Glorfindel gets +1/+1 until end of turn.
> • Glorfindel must be blocked this turn if able.
> • Glorfindel can't be blocked by more than one creature each combat this turn.

**Wyll's Reversal** (CLB):
> Choose target spell or ability with one or more targets. Roll a d20 and add the greatest power among creatures you control.
> 1—14 | You may choose new targets for that spell or ability.
> 15+ | You may choose new targets for that spell or ability. Then copy it. You may choose new targets for the copy.

## Observed at v0.118.0

Glorfindel, mode 2: `CantBeBlockedBy` with a typeless `Typed` filter, which reads as "can't be blocked by any creature":

```json
{"effect": {"type": "GenericEffect", "static_abilities": [{"mode": {"CantBeBlockedBy": {"filter": {"type": "Typed"}}}, "affected": {"type": "SelfRef"}, "modifications": [{"type": "AddStaticMode", "mode": {"CantBeBlockedBy": {"filter": {"type": "Typed"}}}}]}], "duration": "UntilEndOfTurn"}, "duration": "UntilEndOfTurn"}
```

Wyll's Reversal ("target spell or ability with one or more targets"): `TargetOnly` is a bare `StackSpell` (and `ChangeTargets` an `Or[StackSpell, StackAbility]`); the constraint is not carried:

```json
{"effect": {"type": "TargetOnly", "target": {"type": "StackSpell"}}, "sub_ability": {"effect": {"type": "RollDie", "count": {"type": "Fixed", "value": 1}, "sides": 20, "results": [{"min": 1, "max": 14, "effect": {"effect": {"type": "ChangeTargets", "target": {"type": "Or", "filters": [{"type": "StackSpell"}, {"type": "StackAbility"}]}, "scope": {"type": "All"}}, "optional": true}}, {"min": 15, "max": 255, "effect": {"effect": {"type": "ChangeTargets", "target": {"type": "Or", "filters": [{"type": "StackSpell"}, {"type": "StackAbility"}]}, "scope": {"type": "All"}}, "sub_ability": {"effect": {"type": "CopySpell", "target": {"type": "ParentTarget"}, "retarget": {"type": "MayChooseNewTargets"}}}, "optional": true}}], "modifier": {"type": "Add", "value": {"type": "Ref", "qty": {"type": "PropertyAggregate", "function": "Max", "property": "Power", "source": {"type": "Objects", "filter": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}}}}}}}
```

## Expected

A restriction meaning "can't be blocked by more than one creature" and a stack-object filter meaning "has one or more targets"; the grammar has no field for either today (`CantBeBlockedBy` takes a creature filter, and the stack filters `StackSpell` / `StackAbility` carry no target-count property).

## Why it matters

Glorfindel reads as unblockable; Wyll's Reversal can pick a spell with no targets, and its d20 15+ branch copies the `ParentTarget` spell regardless.
