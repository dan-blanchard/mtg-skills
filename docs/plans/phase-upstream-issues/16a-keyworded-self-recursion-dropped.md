# Garza's Assassin, Salvation Colossus, Oscorp Industries, Dusk // Dawn: recover, unearth, mayhem and aftermath not typed

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Garza's Assassin** (CSP):
> Sacrifice this creature: Destroy target nonblack creature.
> Recover—Pay half your life, rounded up. (When another creature is put into your graveyard from the battlefield, you may pay half your life, rounded up. If you do, return this card from your graveyard to your hand. Otherwise, exile this card.)

**Salvation Colossus** (M3C):
> Flying, vigilance, trample
> Whenever you attack, other creatures you control get +2/+2 and gain indestructible until end of turn.
> Unearth—Pay eight {E}. (Pay eight energy counters: Return this card from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step or if it would leave the battlefield. Unearth only as a sorcery.)

**Oscorp Industries** (SPM):
> This land enters tapped.
> When this land enters from a graveyard, you lose 2 life.
> {T}: Add {U}, {B}, or {R}.
> Mayhem (You may play this card from your graveyard if you discarded it this turn. Timing rules still apply.)

**Dusk // Dawn** (AKH):
*Dusk*
> Destroy all creatures with power 3 or greater.
*Dawn*
> Aftermath (Cast this spell only from your graveyard. Then exile it.)
> Return all creature cards with power 2 or less from your graveyard to your hand.

## Observed at v0.118.0

Garza's Assassin ("Recover--Pay half your life, rounded up.") is an `unknown` residue and the record has no `Recover` keyword:

```json
{"effect": {"type": "Unimplemented", "name": "unknown", "description": "Recover—Pay half your life, rounded up."}}
```

Salvation Colossus ("Unearth--Pay eight {E}."):

```json
{"effect": {"type": "Unimplemented", "name": "unknown", "description": "Unearth—Pay eight {E}."}}
```

Oscorp Industries: the "Mayhem (You may play this card from your graveyard if you discarded it this turn ...)" line leaves no node; the record holds only the mana ability, the enters-from-graveyard trigger and the enters-tapped replacement.

Dusk // Dawn: phase has exactly one face record, `Dusk`, holding the `DestroyAll`; there is no record for `Dawn` and no `Aftermath` keyword:

```json
[{"effect": {"type": "DestroyAll", "target": {"type": "Typed", "type_filters": ["Creature"], "properties": [{"type": "PtComparison", "stat": "Power", "scope": "Current", "comparator": "GE", "value": {"type": "Fixed", "value": 3}}]}}}]
```

## Expected

The keyword typed on each: `Recover`, `Unearth` and `Mayhem` already exist as keywords in the card-data (6, 57 and 15 cards) but not on these cards. `Aftermath` has no keyword in the card-data today, and Dawn has no face record.

## Why it matters

These cards' only recursion is the missing keyword, so they look like they cannot return from the graveyard.
