# Eye of Singularity, Ranar the Ever-Watchful, Nicanzil and others: trigger events phase can't type are parked as `mode.Unknown`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Eye of Singularity** (VIS):
> When this enchantment enters, destroy each permanent with the same name as another permanent, except for basic lands. They can't be regenerated.
> Whenever a permanent other than a basic land enters, destroy all other permanents with that name. They can't be regenerated.

**Ranar the Ever-Watchful** (KHC):
> Flying, vigilance
> The first card you foretell each turn costs {0} to foretell.
> Whenever one or more cards are put into exile from your hand or a spell or ability you control exiles one or more permanents from the battlefield, create a 1/1 white Spirit creature token with flying.

## Observed at v0.118.0

Eye of Singularity, second trigger ("a permanent other than a basic land enters"):

```json
{"mode": {"Unknown": "Whenever a permanent other than a basic land enters"}, "execute": {"effect": {"type": "DestroyAll", "target": {"type": "Typed", "type_filters": ["Permanent"], "properties": [{"type": "Another"}]}, "cant_regenerate": true}}}
```

Ranar (compound event: cards exiled from hand, or a spell/ability you control exiles permanents):

```json
{"Unknown": "Whenever one or more cards are put into exile from your hand or a spell or ability you control exiles one or more permanents from the battlefield"}
```

Other cards with the same `mode.Unknown` shape (each record's `mode` is `{"Unknown": "<trigger text>"}`):

- **Nicanzil, Current Conductor** (LCI): `Whenever a creature you control explores a land card (and the nonland twin)`
- **Dream Devourer** (KHM): `Whenever you foretell a card`
- **Sacred Ground** (8ED): `Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield`
- **Thrasher Brute** (BBD): `Whenever ~ or another Warrior your team controls enters`
- **The Fourth Doctor** (WHO): `when you do (no `execute` at all; the Food token is not in the record)`
- **Hero of Bretagard** (KHC): `same compound exile event as Ranar`

## Expected

A typed event for each: an enters watcher with an excluded-basic-land filter (Eye); `ChangesZone` Hand->Exile for Ranar's first half (the grammar has no way to join two events on one trigger today); an `Explored` watcher with a land/nonland filter (Nicanzil; `Explore` already exists as a keyword); a foretell player-action watcher (Dream Devourer; the `PlayerPerformedAction` mode already exists for proliferate); a reflexive-trigger link (Fourth Doctor).

## Why it matters

172 commander-legal cards (298 records in card-data) carry an `Unknown` trigger mode. The effect is typed, so the card looks implemented while never firing.
