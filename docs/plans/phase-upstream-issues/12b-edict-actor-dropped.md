# Undercity Plague, Priest of Forgotten Gods, Variable Solutions: the player who sacrifices is dropped from a chained edict

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Undercity Plague** (GTC):
> Target player loses 1 life, discards a card, then sacrifices a permanent of their choice.
> Cipher (Then you may exile this spell card encoded on a creature you control. Whenever that creature deals combat damage to a player, its controller may cast a copy of the encoded card without paying its mana cost.)

**Priest of Forgotten Gods** (SOC):
> {T}, Sacrifice two other creatures: Any number of target players each lose 2 life and sacrifice a creature of their choice. You add {B}{B} and draw a card. (Activate only as an instant.)

**Variable Solutions** (YSOS):
> If X is 1, seek a basic land card and put it onto the battlefield tapped.
> If X is 2, each opponent sacrifices an artifact of their choice.
> If X is 3, conjure a random creature card with mana value X onto the battlefield.
> If X is 4 or more, you gain 2 life. Then do all of the above.

## Observed at v0.118.0

Undercity Plague: `LoseLife` declares a chosen group and `Discard` targets `DeclaredPlayer`, but the final `Sacrifice` has no player:

```json
{"effect": {"type": "LoseLife", "amount": {"type": "Fixed", "value": 1}, "target": {"type": "Player"}}, "declares_chosen_group": 2147483648, "sub_ability": {"effect": {"type": "Discard", "count": {"type": "Fixed", "value": 1}, "target": {"type": "DeclaredPlayer", "group": 2147483648}}, "sub_ability": {"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Permanent"]}, "count": {"type": "Fixed", "value": 1}}}}}
```

Priest of Forgotten Gods: the `Sacrifice` after `LoseLife` carries no player (trimmed to the first two links):

```json
{"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Creature"]}, "count": {"type": "Fixed", "value": 1}}, "sub_ability": "…"}
```

Variable Solutions, "each opponent sacrifices an artifact of their choice": no `player_scope`:

```json
{"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Artifact"]}, "count": {"type": "Fixed", "value": 1}}
```

## Expected

The sacrifice's actor is the declared player (`DeclaredPlayer`) or `player_scope: Opponent`, as the leading `Discard` in the same chain already is.

## Why it matters

An edict with no actor reads as the controller sacrificing, i.e. as a cost to the caster rather than removal.
