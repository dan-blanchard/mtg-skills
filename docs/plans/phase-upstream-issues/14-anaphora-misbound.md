# Bestial Fury, Blood Lust, Stunning Shot and others: anaphora ("it", "that creature") bound to the wrong object

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Bestial Fury** (ALL):
> Enchant creature
> When this Aura enters, draw a card at the beginning of the next turn's upkeep.
> Whenever enchanted creature becomes blocked, it gets +4/+0 and gains trample until end of turn.

**Blood Lust** (5ED):
> If target creature has toughness 5 or greater, it gets +4/-4 until end of turn. Otherwise, it gets +4/-X until end of turn, where X is its toughness minus 1.

**Stunning Shot** (MSC):
> Put two +1/+1 counters on up to one target creature you control. Tap up to one target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)

## Observed at v0.118.0

Bestial Fury ("it gets +4/+0" -- `it` is the enchanted creature; `ParentTarget` names nothing in this trigger):

```json
{"mode": "BecomesBlocked", "execute": {"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "ParentTarget"}, "modifications": [{"type": "AddPower", "value": 4}, {"type": "AddToughness"}, {"type": "AddKeyword", "keyword": "Trample"}]}], "duration": "UntilEndOfTurn"}, "duration": "UntilEndOfTurn"}, "valid_card": {"type": "AttachedTo"}}
```

Blood Lust ("If target creature has toughness 5 or greater, it gets +4/-4": `target` is `SelfRef`; the else branch is an `otherwise` residue):

```json
{"effect": {"type": "Pump", "power": {"type": "Fixed", "value": 4}, "toughness": {"type": "Fixed", "value": -4}, "target": {"type": "SelfRef"}}, "sub_ability": "…", "duration": "UntilEndOfTurn"}
```

Stunning Shot ("Tap up to one target creature an opponent controls" is a fresh target, but `SetTapState` binds `ParentTarget`, the creature that got the counters):

```json
{"type": "SetTapState", "target": {"type": "ParentTarget"}, "scope": {"type": "Single"}, "state": {"type": "Tap"}}
```

Same family (re-checked at v0.118.0):

- **Six-Sided Die**: "4 -- It gets -4/-4 until end of turn." is `Pump {-4/-4, target: SelfRef}` instead of the chosen creature (likewise the other results).
- **Ojutai Exemplars**, third mode: "Exile this creature, then return it to the battlefield tapped" returns `TriggeringSource`, which is the cast spell.
- **Fatespinner**: "The player skips each instance of the chosen step or phase this turn" is an `unbound_subject` residue after a typed `Choose`.

## Expected

An anaphoric reference to the clause's own subject (the trigger's object, `SelfRef` for "this creature"), `ParentTarget` only when an earlier clause chose the target, or a fresh target when the clause picks its own.

## Why it matters

The pump or tap lands on the wrong creature (or on nothing): Bestial Fury never pumps the enchanted creature, and Blood Lust pumps itself.
