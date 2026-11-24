# Variable Solutions: "each opponent sacrifices an artifact of their choice" has no player

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Variable Solutions** (YSOS):
> If X is 1, seek a basic land card and put it onto the battlefield tapped.
> If X is 2, each opponent sacrifices an artifact of their choice.
> If X is 3, conjure a random creature card with mana value X onto the battlefield.
> If X is 4 or more, you gain 2 life. Then do all of the above.

## Observed at v0.131.0

"each opponent sacrifices an artifact of their choice": no `player_scope`, and the sacrificed filter has no `controller`:

```json
{"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Artifact"]}, "count": {"type": "Fixed", "value": 1}}
```

Undercity Plague and Priest of Forgotten Gods, drafted here at v0.118.0, are fixed at v0.131.0: the sacrificed filter's `controller` is `TargetPlayer` (Undercity Plague) and `ScopedPlayer` (Priest's "any number of target players each ... sacrifice a creature", the binding phase also uses for Tinybones Joins Up's per-target `LoseLife`).

## Expected

The sacrifice's actor is the opponent: `player_scope: Opponent` on the effect, or `controller: ScopedPlayer` on the filter, as the fixed cards above now carry.

## Why it matters

An edict with no actor reads as the controller sacrificing, i.e. as a cost to the caster rather than removal.
