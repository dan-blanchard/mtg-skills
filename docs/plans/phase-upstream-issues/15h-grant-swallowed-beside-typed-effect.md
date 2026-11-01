# Woolly Razorback, Wakanda Forever!, Hide in Plain Sight: a clause is swallowed beside an effect phase types

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Woolly Razorback** (CSP):
> This creature enters with three ice counters on it.
> As long as this creature has an ice counter on it, prevent all combat damage it would deal and it has defender.
> Whenever this creature blocks, remove an ice counter from it.

**Wakanda Forever!** (MSC):
> Reveal the top six cards of your library. You may put a permanent card from among them onto the battlefield with an indestructible counter on it. You may put a permanent card from among them into your hand. Put the rest into your graveyard.

**Hide in Plain Sight** (MKM):
> Look at the top five cards of your library, cloak two of them, and put the rest on the bottom of your library in a random order. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)

## Observed at v0.118.0

Woolly Razorback ("prevent all combat damage it would deal and it has defender"): the whole static is `prevention_conjunct`:

```json
{"effect": {"type": "Unimplemented", "name": "prevention_conjunct", "description": "As long as ~ has an ice counter on it, prevent all combat damage it would deal and it has defender."}}
```

Wakanda Forever! ("put a permanent card ... onto the battlefield with an indestructible counter on it" and "a permanent card ... into your hand" become one `Dig` to Hand):

```json
{"type": "Dig", "player": {"type": "Controller"}, "count": {"type": "Fixed", "value": 6}, "destination": "Hand", "keep_count": 1, "up_to": true, "filter": {"type": "Typed", "type_filters": ["Permanent"]}, "rest_destination": "Graveyard", "reveal": true}
```

Hide in Plain Sight ("cloak two of them"): no destination or cloak for the kept cards:

```json
{"type": "Dig", "player": {"type": "Controller"}, "count": {"type": "Fixed", "value": 5}, "filter": {"type": "Any"}, "rest_destination": "Library", "rest_order": "random"}
```

## Expected

Razorback: A combat-damage prevention for the creature plus `AddKeyword Defender`, both conditioned on the creature having an ice counter (the grammar has no field for the first today). Wakanda: two keep steps (one to the battlefield with an `indestructible` counter, one to hand). Hide: a `Dig` whose kept cards are cloaked.

## Why it matters

The typed `Dig` reads as a plain dig-to-hand / dig-and-bottom.
