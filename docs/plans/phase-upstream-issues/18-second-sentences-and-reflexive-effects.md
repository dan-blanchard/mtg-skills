# Geistlight Snare, Blackmail, Mana Clash, Even the Odds, Turtles Forever, Ludevic: second sentences, casting restrictions and reflexive effects parked

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Geistlight Snare** (VOW):
> This spell costs {1} less to cast if you control a Spirit. It also costs {1} less to cast if you control an enchantment.
> Counter target spell unless its controller pays {3}.

**Blackmail** (9ED):
> Target player reveals three cards from their hand and you choose one of them. That player discards that card.

**Mana Clash** (4ED):
> You and target opponent each flip a coin. Mana Clash deals 1 damage to each player whose coin comes up tails. Repeat this process until both players' coins come up heads on the same flip.

**Even the Odds** (FUT):
> Cast this spell only if you control fewer creatures than each opponent.
> Create three 1/1 white Soldier creature tokens.

**Turtles Forever** (TMT):
> Search your library and/or outside the game for exactly four legendary creature cards you own with different names, then reveal those cards. An opponent chooses two of them. Put the chosen cards into your hand and shuffle the rest into your library.

**Ludevic, Necro-Alchemist** (C16):
> At the beginning of each player's end step, that player may draw a card if a player other than you lost life this turn.
> Partner (You can have two commanders if both have partner.)

## Observed at v0.118.0

Geistlight Snare ("This spell costs {1} less ... It also costs {1} less ..."): each sentence is an `unbound_subject` residue ahead of the typed `Counter`:

```json
{"effect": {"type": "Unimplemented", "name": "unbound_subject", "description": "This spell costs {1} less to cast"}, "sub_ability": "…", "condition": {"type": "QuantityCheck", "lhs": {"type": "Ref", "qty": {"type": "ObjectCount", "filter": {"type": "Typed", "type_filters": [{"Subtype": "Spirit"}], "controller": "You", "properties": [{"type": "InZone", "zone": "Battlefield"}]}}}, "comparator": "GE", "rhs": {"type": "Fixed", "value": 1}}}
```

Blackmail ("reveals three cards from their hand and you choose one of them"):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "reveal three cards from their hand and you choose one of them"}, "sub_ability": {"effect": {"type": "DiscardCard", "count": 1, "target": {"type": "ParentTarget"}}}}
```

Mana Clash (per-flip damage and the repeat):

```json
{"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "Repeat this process until both players' coins come up heads on the same flip"}}
```

Even the Odds ("Cast this spell only if you control fewer creatures than each opponent"):

```json
{"effect": {"type": "Unimplemented", "name": "casting_restriction", "description": "Cast this spell only if you control fewer creatures than each opponent."}}
```

Turtles Forever ("Search your library and/or outside the game"):

```json
{"type": "Unimplemented", "name": "search_zone_list", "description": "Search your library and/or outside the game for exactly four legendary creature cards you own with different names"}
```

Ludevic ("may draw a card if a player other than you lost life this turn"):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "draw a card if a player other than you lost life"}, "duration": "UntilEndOfTurn", "optional": true}
```

## Expected

A `ModifyCost` static (mode `Reduce`, as on Sproutback Trudge) for each Snare sentence (the second with its own condition); a typed reveal-and-choose; a per-player coin-flip outcome and loop; a casting-restriction condition typed as a `QuantityCheck`; a search that accepts a list of zones; the Ludevic condition as a typed "a player other than you lost life this turn" condition (the grammar has no field for this today).

## Why it matters

Each is a card whose characteristic effect is a residue.
