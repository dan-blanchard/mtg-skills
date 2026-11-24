# "[Player] reveals their hand and discards all … cards": the discard parked, its player cut

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face records as the card-data holds them, null/false/empty fields and noise keys dropped).

## Cards

**Amnesia** (DRK):
> Target player reveals their hand and discards all nonland cards.

**Persecute** (7ED):
> Choose a color. Target player reveals their hand and discards all cards of that color.

**Shatter Assumptions** (MH1):
> Choose one —
> • Target opponent reveals their hand and discards all colorless nonland cards.
> • Target opponent reveals their hand and discards all multicolored cards.

Also, the same shape (a typed `RevealHand` followed by a parked discard): Cabal Therapy, Cabal Therapist, Crosis, the Purger, Fall, Hint of Insanity, Infernal Kirin, Minamo's Meddling, Mind Extraction, Nebuchadnezzar, Trapfinder's Trick, Tsabo's Decree, Void (Void's is an `unparsed_quantity`).

## Observed at v0.131.0

The reveal is typed and names its player; the discard after it is an `Unimplemented` residue whose description starts at the verb, so nothing says who discards or which cards:

```json
{"kind": "Spell", "effect": {"type": "RevealHand", "target": {"type": "Player"}, "card_filter": {"type": "None"}, "reveal": true}, "declares_chosen_group": 2147483648, "sub_ability": {"kind": "Spell", "effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "discard all nonland cards"}}, "description": "Target player reveals their hand and discards all nonland cards."}
{"kind": "Spell", "effect": {"type": "RevealHand", "target": {"type": "Typed", "controller": "Opponent"}, "card_filter": {"type": "None"}, "reveal": true}, "declares_chosen_group": 2147483648, "sub_ability": {"kind": "Spell", "effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "discard all colorless nonland cards"}}}
```

Shatter Assumptions is modal: each mode is its own ability with this pair, and neither carries the mode's text.

## Expected

A `Discard` by the player who revealed (the `RevealHand`'s own target), over the cards the clause names: every nonland card (Amnesia), every card of the chosen colour (Persecute), every colorless nonland or every multicolored card (Shatter Assumptions' modes). The filter is the part phase can't type today; the player is known from the reveal either way.

## Why it matters

As parsed the opponent reveals a hand and nothing is discarded. A reader recovering the clause from its text sees a bare "discard all … cards", which reads as the spell's controller discarding.
