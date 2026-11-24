# Battlefield Thaumaturge, Thrasta and others: a cost change "for each [count]" parked as `static_structure`

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Battlefield Thaumaturge** (JOU):
> Each instant and sorcery spell you cast costs {1} less to cast for each creature it targets.
> Heroic — Whenever you cast a spell that targets this creature, this creature gains hexproof until end of turn.

**Thrasta, Tempest's Roar** (MH2):
> This spell costs {3} less to cast for each other spell cast this turn.
> Trample, haste
> Trample over planeswalkers (This creature can deal excess combat damage to the controller of the planeswalker it's attacking.)
> Thrasta has hexproof as long as it entered this turn.

## Observed at v0.131.0

The whole cost line is a residue in `abilities`; the record has no `ModifyCost` static. Both records are marked `confirmed_misparse: "wrong_count"`.

Battlefield Thaumaturge:

```json
{"effect": {"type": "Unimplemented", "name": "static_structure", "description": "Static pattern matched but line failed static parser: Each instant and sorcery spell you cast costs {1} less to cast for each creature it targets."}}
```

Thrasta:

```json
{"effect": {"type": "Unimplemented", "name": "static_structure", "description": "Static pattern matched but line failed static parser: This spell costs {3} less to cast for each other spell cast this turn."}}
```

At v0.118.0 both were a `ModifyCost {mode: Reduce}` static whose `dynamic_count` counted the wrong thing (Thaumaturge: every creature, `ObjectCount` of `Typed[Creature]`; Thrasta: `ObjectCount` of `Typed[Card] + Another`):

```json
{"ModifyCost": {"mode": "Reduce", "amount": {"type": "Cost", "generic": 1}, "spell_filter": {"type": "Or", "filters": [{"type": "Typed", "type_filters": ["Instant"]}, {"type": "Typed", "type_filters": ["Sorcery"]}]}, "dynamic_count": {"type": "ObjectCount", "filter": {"type": "Typed", "type_filters": ["Creature"]}}}}
```

The same residue, new at v0.131.0 (each was a `ModifyCost` with a loose `dynamic_count` at v0.118.0), on these cards, not re-quoted here:

- **Hinata, Dawn-Crowned**: "Spells you cast cost {1} less to cast for each target." and "Spells your opponents cast cost {1} more to cast for each target."
- **Korvold, Gleeful Glutton**: "for each card type among permanents you've sacrificed this turn"
- **Lumbering Megasloth**: "for each counter among players and permanents"
- **Obsidian Charmaw**: "for each land your opponents control that could produce {C}"
- **Seal of the Guildpact**: "Each spell you cast costs {1} less to cast for each of the chosen colors it is."
- **The Balrog, Durin's Bane**: "for each permanent sacrificed this turn"
- **Valiant Changeling**: "for each creature type among creatures you control. This effect can't reduce the amount of mana this spell costs by more than {5}."
- **Etali, Primal Garden** (Alchemy): "Actualize — This spell costs {1} less to cast for each spell you've cast this game that wasn't from your starting deck."

## Expected

The v0.118.0 `ModifyCost` static, with a `dynamic_count` that says what is counted: targets of the spell being cast that are creatures (Thaumaturge) or any targets (Hinata); spells cast this turn other than this one (Thrasta); and so on for the list. Valiant Changeling's cap needs a maximum on the reduction.

## Why it matters

These cards' cost change is a large part of what they do. Parked, each costs its full printed cost; at v0.118.0 each had a cost change, but the wrong one.
