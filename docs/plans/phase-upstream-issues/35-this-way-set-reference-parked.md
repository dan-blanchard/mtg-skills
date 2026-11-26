# Revivify, Raiding Party and others: a clause over the cards an earlier clause chose or moved ("… this way", "those cards") parked

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

**Fixed in v0.133.0 for Starfall Invocation** (phase #11332: its gift-gated "return a creature card put into your graveyard this way" is typed, the `confirmed_misparse` flag gone); it is removed from the list below. The rest of this draft is unchanged.

## Cards

**Revivify** (AFC):
> Roll a d20 and add the number of creature cards in your graveyard that were put there from the battlefield this turn.
> 1—14 | Return all creature cards in your graveyard that were put there from the battlefield this turn to your hand.
> 15+ | Return those cards from your graveyard to the battlefield.

**Raiding Party** (FEM):
> This enchantment can't be the target of white spells or abilities from white sources.
> Sacrifice an Orc: Each player may tap any number of untapped white creatures they control. For each creature tapped this way, that player chooses up to two Plains. Then destroy all Plains that weren't chosen this way by any player.

## Observed at v0.131.0

Revivify: all three lines are residues, the d20 included:

```json
[{"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "Roll a d20 and add the number of creature cards in your graveyard that were put there from the battlefield this turn"}}, {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "1—14 | Return all creature cards in your graveyard that were put there from the battlefield this turn to your hand"}}, {"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "15+ | Return those cards from your graveyard to the battlefield"}}]
```

At v0.118.0 Revivify was one typed `RollDie` (with a `SwallowedClause` warning for the uncounted modifier): 1—14 a `BounceAll` of creature cards in your graveyard with `ZoneChangedThisTurn {from: Battlefield, to: Graveyard}`, 15+ a `ChangeZone` Graveyard->Battlefield of `And[TrackedSet, Owned{You} in graveyard]`.

Raiding Party: the final destroy is parked after the typed tap and choice (the record is marked `confirmed_misparse: "dropped_qualifier"`; at v0.118.0 this was a `DestroyAll` of every Plains):

```json
{"effect": {"type": "TargetOnly", "target": {"type": "Typed", "type_filters": [{"Subtype": "Plains"}]}}, "declares_chosen_group": 1, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "destroy all Plains that weren't chosen this way by any player"}}, "repeat_for": {"type": "Ref", "qty": {"type": "FilteredTrackedSetSize", "filter": {"type": "Typed", "type_filters": ["Creature"]}}}, "repeat_timing": "SimultaneousInstances"}
```

The same residue, new at v0.131.0, on these cards (each named with its residue text; not re-quoted). Most were typed at v0.118.0 with the "this way" qualifier dropped, so a sweep that spares the chosen permanents hit everything, and a return of the cards moved this way returned every matching card:

- A sweep that spares what was chosen: **Harsh Mercy** ("Destroy all creatures that aren't of a type chosen this way"; at v0.118.0 a `DestroyAll` of every creature), **Celestial Judgment** ("Destroy each creature not chosen this way"), **Consuming Tide** ("Return all nonland permanents not chosen this way to their owners' hands"), **Sculpted Sunburst** ("exile each creature not chosen by any player this way"), **Unstable Glyphbridge** ("destroy all creatures except creatures chosen this way").
- A move of the cards an earlier clause moved or chose: **Patriarch's Bidding** ("return all creature cards of a type chosen this way from their graveyard to the battlefield"; at v0.118.0 every creature card in the graveyard), **Sorin, Lord of Innistrad** ("Return each card put into a graveyard this way to the battlefield under your control"), **Necromantic Selection**, **Zero Point Ballad** ("return a creature card put into a graveyard this way …"), **Stitcher Geralf** ("Exile creature cards put into graveyards this way"), **Avatar Destiny** ("… up to one creature card milled this way …"), **Shadow Kin** ("exile a creature card from among the cards milled this way"), **Struggle for Sanity** ("return the cards they exiled this way to their hand"), **Covenant of Minds** ("choose to put those cards into your hand").

Cleansing Meditation (issue 03) and Danse Macabre's two results (issue 27) carry the same residue.

## Expected

The tracked set phase already builds for "this way" (`TrackedSet`, with a `caused_by` or a chosen group, as Raiding Party's own `FilteredTrackedSetSize` and `declares_chosen_group` show) used as the clause's object: `ChangeZone` / `ChangeZoneAll` over the set's cards for the returns, and `DestroyAll` / `ChangeZoneAll` / `BounceAll` over the population minus the chosen set for the sweeps.

## Why it matters

These are sweepers and mass reanimation spells whose effect is the parked clause, so they do nothing as parsed. v0.118.0's typed forms were wrong (a one-sided sweep read as a full wipe), but a consumer could see what the card was for; parked, the card has no effect a consumer can read.
