# Desperate Gambit, Goblin Kites, Fickle Efreet: one "Flip a coin. If you win ... If you lose ..." typed as two flips

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Desperate Gambit** (WTH):
> Choose a source you control and flip a coin. If you win the flip, the next time that source would deal damage this turn, it deals double that damage instead. If you lose the flip, the next time it would deal damage this turn, prevent that damage.

**Goblin Kites** (FEM):
> {R}: Target creature you control with toughness 2 or less gains flying until end of turn. Flip a coin at the beginning of the next end step. If you lose the flip, sacrifice that creature.

**Fickle Efreet** (PCY):
> Whenever this creature attacks or blocks, flip a coin at end of combat. If you lose the flip, an opponent gains control of this creature.

## Observed at v0.118.0

Desperate Gambit: a win-only `FlipCoins` whose `sub_ability` is a second, lose-only one (so two independent flips). The "choose a source you control" is also a bare `TargetOnly {target: Any}`; "you control" is lost:

```json
{"effect": {"type": "TargetOnly", "target": {"type": "Any"}}, "sub_ability": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}, "win_effect": {"effect": {"type": "CreateDamageReplacement", "source_filter": {"type": "ChosenDamageSource"}, "modification": {"type": "Double"}}}}, "sub_ability": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}, "lose_effect": {"effect": {"type": "PreventDamage", "amount": "All", "target": {"type": "Any"}, "recipient_scope": {"type": "Single"}, "scope": "AllDamage", "damage_source_filter": {"type": "ChosenDamageSource"}}}}}}}
```

Goblin Kites, delayed form: an outcome-less `FlipCoins` followed by a nested `FlipCoins` (trimmed):

```json
{"effect": {"type": "CreateDelayedTrigger", "condition": {"type": "AtNextPhase", "phase": "End"}, "effect": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}}, "sub_ability": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}, "lose_effect": {"effect": {"type": "Sacrifice", "target": {"type": "ParentTarget"}, "count": {"type": "Fixed", "value": 1}}}}}}}}
```

Fickle Efreet, same nested form:

```json
{"type": "CreateDelayedTrigger", "condition": {"type": "AtNextPhase", "phase": "EndCombat"}, "effect": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}}, "sub_ability": {"effect": {"type": "FlipCoins", "flips": {"type": "Exactly", "count": {"type": "Fixed", "value": 1}}, "lose_effect": {"effect": {"type": "Choose", "choice_type": "Opponent"}, "sub_ability": {"effect": {"type": "GainControl", "target": {"type": "SelfRef"}}}}}}}}
```

## Expected

One `FlipCoins` carrying both `win_effect` and `lose_effect`.

## Why it matters

As parsed the two outcomes are independent flips, so both can happen or neither.
