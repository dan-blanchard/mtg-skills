# Mask of the Schemer, Officious Interrogation, Thromok the Insatiable: `where X is ...` binding residue swallows the whole effect

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Mask of the Schemer** (NCC):
> Whenever equipped creature deals combat damage to a player, it connives X, where X is the amount of damage it dealt to that player. (Draw X cards, then discard X cards. Put a +1/+1 counter on that creature for each nonland card discarded this way.)
> Equip {2}

**Officious Interrogation** (MKM):
> This spell costs {W}{U} more to cast for each target beyond the first.
> Choose any number of target players. Investigate X times, where X is the total number of creatures those players control.

**Thromok the Insatiable** (PCA):
> Devour X, where X is the number of creatures devoured this way (As this creature enters, you may sacrifice any number of creatures. It enters with X +1/+1 counters on it for each of those creatures.)

## Observed at v0.118.0

Mask of the Schemer ("it connives X, where X is the amount of damage it dealt to that player"): the trigger body is only the residue, no `Connive`:

```json
{"effect": {"type": "Unimplemented", "name": "where_x_binding", "description": "where X is the amount of damage it dealt to that player"}}
```

Officious Interrogation: `TargetOnly Player`, then the residue; no `Investigate`:

```json
{"effect": {"type": "TargetOnly", "target": {"type": "Player"}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "where_x_binding", "description": "where X is the total number of creatures those players control"}}, "multi_target": {}}
```

Thromok ("Devour X, where X is the number of creatures devoured this way"): an `unknown` residue and no `Devour` keyword (Tar Fiend's `Devour 2` keyword is typed):

```json
{"effect": {"type": "Unimplemented", "name": "unknown", "description": "Devour X, where X is the number of creatures devoured this way"}}
```

## Expected

The verb typed (`Connive`, `Investigate`) with its count as a `QuantityRef` (damage dealt by the triggering source to that player; count of the targeted players' creatures); a `Devour` keyword accepting X.

## Why it matters

A parked `where X` clause removes the verb and its object, not just the number. 41 commander-legal cards (57 records in card-data) carry `where_x_binding`.
