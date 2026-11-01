# Kaust, Eyes of the Glade: "a creature you control that was turned face up this turn deals combat damage to a player" is an `Unknown` trigger mode

Phase tag: v0.118.0 (`card-data-v0.118.0.json`).

## Card

**Kaust, Eyes of the Glade** (MKC), Legendary Creature — Dryad Detective, {R/W}{G}, 2/2:
> Whenever a creature you control that was turned face up this turn deals combat damage to a player, draw a card.
> {T}: Turn target face-down attacking creature you control face up.

## Observed at v0.118.0

The first ability's trigger keeps the whole trigger line as `mode.Unknown`; `valid_source` and `valid_target` are absent, while the body (draw a card) is typed:

```json
{"mode": {"Unknown": "Whenever a creature you control that was turned face up this turn deals combat damage to a player"}, "execute": {"effect": {"type": "Draw", "count": {"type": "Fixed", "value": 1}, "target": {"type": "Controller"}}}, "trigger_zones": ["Battlefield"], "damage_kind": "Any", "valid_source": null, "valid_target": null}
```

The activated ability (turn a face-down attacking creature face up) is typed.

## Expected

`mode: DamageDone` (combat damage, to a player) with a `valid_source` of a creature you control that was turned face up this turn. The grammar already has a `DamageDone` mode with a player recipient and a controlled-creature source filter; what is missing is the "turned face up this turn" qualifier on the source, which may need a field of its own (today nothing expresses it).

## Why it matters

With an `Unknown` mode the card's first ability has no event any consumer can read: deck analysis sees a two-mana 2/2 with an untap-style activation and nothing that rewards face-down creatures turning face up, so the deck built around it (Deadly Disguise) reads as having no plan on its commander.
