# Danse Macabre: the non-targeting "return up to two creature cards" carries a `multi_target`, and both d20 returns are parked

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Danse Macabre** (AFC):
> Each player sacrifices a nontoken creature of their choice. Roll a d20 and add the toughness of the creature you sacrificed this way.
> 1—14 | Return a creature card put into a graveyard this way to the battlefield under your control.
> 15+ | Return up to two creature cards put into graveyards this way to the battlefield under your control.

## Observed at v0.131.0

The d20 is typed now (at v0.118.0 it was an `unparsed_verb_arguments` residue and each result line an `unrecognized_clause_head`). Both results are still parked, and the 15+ result's residue carries a `multi_target` although nothing in it targets ("up to two" is a count of cards chosen as the spell resolves):

```json
{"effect": {"type": "RollDie", "count": {"type": "Fixed", "value": 1}, "sides": 20, "results": [{"min": 1, "max": 14, "effect": {"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "Return a creature card put into a graveyard this way to the battlefield under your control"}}}, {"min": 15, "max": 255, "effect": {"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "Return creature cards put into graveyards this way to the battlefield under your control"}, "multi_target": {"min": 0, "max": {"type": "Fixed", "value": 2}}}}], "modifier": {"type": "Add", "value": {"type": "Ref", "qty": {"type": "PropertyAggregate", "function": "Sum", "property": "Toughness", "source": {"type": "TrackedSet", "filter": {"type": "Typed", "type_filters": ["Card"], "controller": "You"}}}}}}}
```

The residue's text has also lost "up to two" (it reads "Return creature cards ..."), so the count survives only as the stray `multi_target`.

## Expected

Each result a `ChangeZone` Graveyard->Battlefield (`enters_under: You`) over creature cards in the tracked set of the sacrifice, choosing one card (1—14) or up to two (15+) as a count on the choice, with no `multi_target`.

## Why it matters

A `multi_target` on a non-targeting clause tells a consumer the spell has up to two targets (our analysis reads it as a variable-target spell), while the actual return is invisible. The "… this way" residue is the shape of issue 35.
