# Reaper of Night, Inventive Wingsmith, Genku Future Shaper: a keyword grant, keyword counter or token is parked as `Unimplemented`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Reaper of Night // Harvest Fear** (ELD):
*Reaper of Night*
> Whenever this creature attacks, if defending player has two or fewer cards in hand, it gains flying until end of turn.
*Harvest Fear*
> Target opponent discards two cards. (Then exile this card. You may cast the creature later from exile.)

**Inventive Wingsmith** (OTJ):
> At the beginning of your end step, if you haven't cast a spell from your hand this turn and this creature doesn't have a flying counter on it, put a flying counter on it.

**Genku, Future Shaper** (MH3):
> Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. Create a creature token with those characteristics.
> • 2/2 white Fox with vigilance.
> • 1/2 blue Moonfolk with flying.
> • 1/1 black Rat with lifelink.
> {3}{W}{U}: Put a +1/+1 counter on each creature you control.

## Observed at v0.118.0

Reaper of Night (Harvest Fear half is typed as discard; the attack trigger is one residue):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "if defending player has two or fewer cards in hand, it gains flying until end of turn"}}
```

Inventive Wingsmith ("put a flying counter on it" inside an intervening-if):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_condition", "description": "if you haven't cast a spell from your hand this turn and ~ doesn't have a flying counter on it, put a flying counter on it"}}
```

Genku, Future Shaper, mode 2 (every mode is an `unrecognized_clause_head`; "Create a creature token with those characteristics" is the selection):

```json
{"effect": {"type": "Unimplemented", "name": "unrecognized_clause_head", "description": "1/2 blue Moonfolk with flying"}}
```

## Expected

Reaper of Night: a conditional (`defending player has two or fewer cards in hand`) `GenericEffect` granting flying. Wingsmith: the condition typed, `PutCounter` with a keyword-counter type `flying`. Genku: a `Token` of the stated characteristics per mode.

## Why it matters

Notorious Throng ("X 1/1 ... tokens with flying") is the same kind of loss; see the `unparsed_quantity` issue (09).
