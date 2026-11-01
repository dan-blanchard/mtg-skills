# Custodi Soulcaller, Venerable Warsinger, All Hallow's Eve, Necromancy, Can't Stay Away: returns from the graveyard parked or lost

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Custodi Soulcaller** (CN2):
> Melee (Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)
> Whenever this creature attacks, return target creature card with mana value X or less from your graveyard to the battlefield, where X is the number of players you attacked this combat.

**Venerable Warsinger** (SOC):
> Vigilance, trample
> Whenever this creature deals combat damage to a player, you may return target creature card with mana value X or less from your graveyard to the battlefield, where X is the amount of damage this creature dealt to that player.

**All Hallow's Eve** (LEG):
> Exile All Hallow's Eve with two scream counters on it.
> At the beginning of your upkeep, if this card is exiled with a scream counter on it, remove a scream counter from it. If there are no more scream counters on it, put it into your graveyard and each player returns all creature cards from their graveyard to the battlefield.

**Necromancy** (MKC):
> You may cast this spell as though it had flash. If you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step.
> When this enchantment enters, if it's on the battlefield, it becomes an Aura with "enchant creature put onto the battlefield with Necromancy." Put target creature card from a graveyard onto the battlefield under your control and attach this enchantment to it. When this enchantment leaves the battlefield, that creature's controller sacrifices it.

**Can't Stay Away** (PMID):
> Return target creature card with mana value 3 or less from your graveyard to the battlefield. It gains "If this creature would die, exile it instead."
> Flashback {3}{W}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)

## Observed at v0.118.0

Custodi Soulcaller: the whole attack-trigger body is a `where_x_binding` residue (the reanimation itself has no node). Melee on the same card types `OpponentAttacked` fine:

```json
{"mode": "Attacks", "execute": {"effect": {"type": "Unimplemented", "name": "where_x_binding", "description": "where X is the number of players you attacked this combat"}, "duration": "UntilEndOfCombat"}, "valid_card": {"type": "SelfRef"}}
```

Venerable Warsinger: same residue, description "where X is the amount of damage ~ dealt to that player":

```json
{"effect": {"type": "Unimplemented", "name": "where_x_binding", "description": "where X is the amount of damage ~ dealt to that player"}, "optional": true}
```

All Hallow's Eve: the upkeep trigger body, including "each player returns all creature cards from their graveyard to the battlefield", is one `unparsed_condition`:

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "if this card is exiled with a scream counter on it, remove a scream counter from it. If there are no more scream counters on it, put it into your graveyard and each player returns all creature cards from their graveyard to the battlefield"}}
```

Necromancy: the main ability is `granter_reference_unreached`:

```json
{"effect": {"type": "Unimplemented", "name": "granter_reference_unreached", "description": "When ~ enters, if it's on the battlefield, it becomes an Aura with \"enchant creature put onto the battlefield with ~.\" Put target creature card from a graveyard onto the battlefield under your control and attach ~ to it. When ~ leaves the battlefield, that creature's controller sacrifices it."}}
```

Can't Stay Away: the spell's `ChangeZone` return has no node at all; the only record is a replacement whose tail is a stray `"` residue:

```json
{"event": "Moved", "execute": {"effect": {"type": "ChangeZone", "destination": "Exile", "target": {"type": "SelfRef"}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "\""}}}, "mode": {"type": "Mandatory"}, "valid_card": {"type": "SelfRef"}, "destination_zone": "Graveyard"}
```

## Expected

`ChangeZone` / `ChangeZoneAll` Graveyard->Battlefield with the X count as a quantity (`ObjectCount`/`PlayerCount`, as `OpponentAttacked` already gives Melee); for Necromancy a `ChangeZone` plus an `Attach`; for Can't Stay Away the return plus a duration-limited "if it would die, exile it instead" replacement on the returned creature.

## Why it matters

These are reanimation spells and triggers whose only typed parts are incidental, so analysis sees no recursion at all.
