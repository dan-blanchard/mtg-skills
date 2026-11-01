# Frodo, Sauron's Bane; Nicol Bolas, Dragon-God; Forgeborn Phoenix: quoted or granted abilities dropped, parked, or typed as the wrong effect

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Frodo, Sauron's Bane** (LTR):
> {W/B}{W/B}: If Frodo is a Citizen, it becomes a Halfling Scout with base power and toughness 2/3 and lifelink.
> {B}{B}{B}: If Frodo is a Scout, it becomes a Halfling Rogue with "Whenever this creature deals combat damage to a player, that player loses the game if the Ring has tempted you four or more times this game. Otherwise, the Ring tempts you."

**Nicol Bolas, Dragon-God** (PWAR):
> Nicol Bolas has all loyalty abilities of all other planeswalkers on the battlefield.
> [+1]: You draw a card. Each opponent exiles a card from their hand or a permanent they control.
> [−3]: Destroy target creature or planeswalker.
> [−8]: Each opponent who doesn't control a legendary creature or planeswalker loses the game.

**Forgeborn Phoenix** (YNEO):
> Flying
> Equipped creature has flying.
> Whenever Forgeborn Phoenix or equipped creature dies, it perpetually gains "Whenever an equipped creature you control deals combat damage to a player or planeswalker, return this card from your graveyard to battlefield tapped."
> Reconfigure {R} ({R}: Attach to target creature you control; or unattach from a creature. Reconfigure only as a sorcery. While attached, this isn't a creature.)

## Observed at v0.118.0

Frodo's second ability keeps `RingTemptsYou` (condition: is a Scout) but the "becomes a Halfling Rogue with '<quoted trigger>'" part is gone: no type change, no granted trigger (the first ability, Citizen->Scout, is typed fully):

```json
{"effect": {"type": "RingTemptsYou"}, "cost": {"type": "Mana", "cost": {"type": "Cost", "shards": ["Black", "Black", "Black"]}}, "condition": {"type": "SourceMatchesFilter", "filter": {"type": "Typed", "type_filters": [{"Subtype": "Scout"}]}}}
```

Nicol Bolas: "has all loyalty abilities of all other planeswalkers on the battlefield" is a static-structure residue:

```json
{"effect": {"type": "Unimplemented", "name": "static_structure", "description": "Static pattern matched but line failed static parser: ~ has all loyalty abilities of all other planeswalkers on the battlefield."}}
```

Forgeborn Phoenix: the perpetual grant "return this card from your graveyard to the battlefield tapped" is a `Bounce` of `SelfRef` (to hand) -- see `execute.effect` below (fragment trimmed):

```json
{"effect": {"type": "ApplyPerpetual", "target": {"type": "TriggeringSource"}, "modification": {"modifications": [{"type": "GrantTrigger", "trigger": {"mode": "DamageDone", "execute": {"effect": {"type": "Bounce", "target": {"type": "SelfRef"}}}, "valid_target": {"type": "Or", "filters": [{"type": "Player"}, {"type": "Typed", "type_filters": ["Planeswalker"]}]}, "valid_source": {"type": "Typed", "type_filters": ["Creature"], "controller": "You", "properties": [{"type": "EquippedBy"}]}}}]}}}
```

## Expected

Frodo: an effect that gives itself the Rogue subtype and a `GrantTrigger` carrying the quoted combat-damage trigger. Bolas: a static granting activated loyalty abilities of other planeswalkers (the `GrantAllActivatedAbilitiesOf` shape phase already emits for Thranduil, the Elvenking could be parameterised by a loyalty-ability filter). Forgeborn Phoenix: `ChangeZone` Graveyard->Battlefield `enter_tapped: true` on `SelfRef`.

## Why it matters

Whatever a card grants is invisible to analysis and to the engine: Frodo never becomes a Rogue, Bolas has no extra abilities, and the Phoenix's recursion reads as a bounce.
