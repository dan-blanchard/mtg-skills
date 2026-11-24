# Veiling Oddity: "creatures can't be blocked this turn" parked as `broadcast_static_mode_live_set`

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Veiling Oddity** (PLC):
> Suspend 4—{1}{U} (Rather than cast this card from your hand, you may pay {1}{U} and exile it with four time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost. It has haste.)
> When the last time counter is removed from this card while it's exiled, creatures can't be blocked this turn.

## Observed at v0.131.0

The trigger event is typed now (`CounterRemoved`, time counters, threshold 0), but the whole line, effect included, is the residue:

```json
{"mode": "CounterRemoved", "execute": {"effect": {"type": "Unimplemented", "name": "broadcast_static_mode_live_set", "description": "When the last time counter is removed from this card while it's exiled, creatures can't be blocked this turn."}}, "valid_card": {"type": "SelfRef"}, "counter_filter": {"counter_type": "time", "threshold": 0}}
```

At v0.118.0 it was the reverse: the mode was `Unknown`, and the body a `GenericEffect` with a `CantBeBlocked` static on `Typed[Creature]` until end of turn:

```json
{"mode": {"Unknown": "When the last time counter is removed from this card while it's exiled"}, "execute": {"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "CantBeBlocked", "affected": {"type": "Typed", "type_filters": ["Creature"]}, "modifications": [{"type": "AddStaticMode", "mode": "CantBeBlocked"}]}], "duration": "UntilEndOfTurn"}, "duration": "UntilEndOfTurn"}}
```

`broadcast_static_mode_live_set` appears on no other record at v0.131.0.

## Expected

The v0.131.0 trigger with the v0.118.0 body: a `CantBeBlocked` grant to creatures until end of turn. Question: the residue name suggests phase wants to know whether "creatures" means the creatures on the battlefield as the trigger resolves or every creature during the turn; either reading is better than no effect.

## Why it matters

The card's only payoff is an unblockable turn for every creature; as parsed it has none, and a deck-analysis read sees a suspend creature with no team evasion.
