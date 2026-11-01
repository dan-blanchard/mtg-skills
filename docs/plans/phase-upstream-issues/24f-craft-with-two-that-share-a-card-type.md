# Eye of Ojer Taq: "Craft with two that share a card type {6}" parked as `unknown`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Eye of Ojer Taq // Apex Observatory** (LCC):
*Eye of Ojer Taq*
> {T}: Add one mana of any color.
> Craft with two that share a card type {6} ({6}, Exile this artifact, Exile the two from among other permanents you control and/or cards from your graveyard: Return this card transformed under its owner's control. Craft only as a sorcery.)
*Apex Observatory*
> This artifact enters tapped. As it enters, choose a card type shared among two exiled cards used to craft it.
> {T}: The next spell you cast this turn of the chosen type can be cast without paying its mana cost.

## Observed at v0.118.0

Back face (`Eye of Ojer Taq`) second ability:

```json
{"effect": {"type": "Unimplemented", "name": "unknown", "description": "Craft with two that share a card type {6}"}}
```

## Expected

The `Craft` keyword (present on 21 cards) with this material requirement; the grammar has no field for "share a card type" today.

## Why it matters

The transform path of the card is absent.
