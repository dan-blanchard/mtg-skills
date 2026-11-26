# "[Player] reveals their hand and discards all … cards": the discard parked, its player cut

Phase tag: v0.133.0 (`card-data-v0.133.0.json`; face records as the card-data holds them, null/false/empty fields and noise keys dropped). Drafted against v0.131.0.

**Fixed in v0.133.0 for four of its cards:** Amnesia and Shatter Assumptions (this draft's first fragments at v0.131.0), Trapfinder's Trick and Tsabo's Decree are typed now, a `Discard` by the revealing player (`DeclaredPlayer` of the reveal's group) over the named cards, and their `confirmed_misparse` flag is gone. They are removed from the lists below. The shape stays on the cards that follow.

## Cards

**Persecute** (7ED):
> Choose a color. Target player reveals their hand and discards all cards of that color.

**Mind Extraction** (APC):
> As an additional cost to cast this spell, sacrifice a creature.
> Target player reveals their hand and discards all cards of each of the sacrificed creature's colors.

Also, the same shape (a typed `RevealHand` followed by a parked discard): Cabal Therapy, Cabal Therapist, Crosis, the Purger, Fall, Hint of Insanity, Infernal Kirin, Minamo's Meddling, Nebuchadnezzar, Void (Void's is an `unparsed_quantity`).

## Observed at v0.133.0

The reveal is typed and names its player; the discard after it is an `Unimplemented` residue whose description starts at the verb, so nothing says who discards or which cards:

```json
{"kind": "Spell", "effect": {"type": "Choose", "choice_type": "Color"}, "sub_ability": {"kind": "Spell", "effect": {"type": "RevealHand", "target": {"type": "Player"}, "card_filter": {"type": "None"}, "reveal": true}, "declares_chosen_group": 2147483648, "sub_ability": {"kind": "Spell", "effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "discard all cards of that color"}}}, "description": "Choose a color. Target player reveals their hand and discards all cards of that color."}
{"kind": "Spell", "effect": {"type": "RevealHand", "target": {"type": "Player"}, "card_filter": {"type": "None"}, "reveal": true}, "declares_chosen_group": 2147483648, "sub_ability": {"kind": "Spell", "effect": {"type": "Unimplemented", "name": "unparsed_verb_arguments", "description": "discard all cards of each of the sacrificed creature's colors"}}, "description": "Target player reveals their hand and discards all cards of each of the sacrificed creature's colors."}
```

The fixed cards show the shape phase now gives this clause elsewhere (Amnesia: `Discard{target: DeclaredPlayer, filter: Typed[Card, Non-Land]}`), so it is the filter these two name — a chosen colour, the sacrificed creature's colours — that still parks.

## Expected

A `Discard` by the player who revealed (the `RevealHand`'s own target), over the cards the clause names: every card of the chosen colour (Persecute), every card of each of the sacrificed creature's colours (Mind Extraction). The filter is the part phase can't type today; the player is known from the reveal either way.

## Why it matters

As parsed the opponent reveals a hand and nothing is discarded. A reader recovering the clause from its text sees a bare "discard all … cards", which reads as the spell's controller discarding.
