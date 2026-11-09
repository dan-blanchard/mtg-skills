# "Exile it instead of putting it into its owner's graveyard" typed as a second move out of the graveyard

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Dissipate** (DDJ):
> Counter target spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.

**Memory Lapse** (HML):
> Counter target spell. If that spell is countered this way, put it on top of its owner's library instead of into that player's graveyard.

The same shape appears on these cards, not re-quoted here (21 in all, every one with "exile it instead"): Assert Authority, Defabricate, Delay, Deny Existence, Deny the Divine, Devious Cover-Up, Faerie Trickery, Force of Negation, Horribly Awry, Kheru Spellsnatcher, Liquify, No Escape, No More Lies, Reject, Spell Shrivel, Spelljack, Syncopate, Thranduil's Decree, Transcendent Dragon, Void Shatter.

## Observed at v0.118.0

Dissipate counters, then moves the countered spell from the graveyard to exile:

```json
{"effect": {"type": "Counter", "target": {"type": "StackSpell"}}, "sub_ability": {"effect": {"type": "ChangeZone", "origin": "Graveyard", "destination": "Exile", "target": {"type": "ParentTarget"}}, "condition": {"type": "ZoneChangedThisWay", "filter": {"type": "Typed", "type_filters": ["Card"]}}}}
```

For comparison, Memory Lapse's "instead" is typed on the `Counter` itself:

```json
{"effect": {"type": "Counter", "target": {"type": "StackSpell"}, "countered_spell_zone": {"type": "Library", "position": {"type": "Top"}}}}
```

## Expected

"Instead" makes this a replacement effect (CR 614.1a) of the countered spell's move to its owner's graveyard (CR 701.6a): the spell goes from the stack to exile and never enters the graveyard. The natural form is Memory Lapse's: `countered_spell_zone: {"type": "Exile"}` on the `Counter` (today `countered_spell_zone` holds only `Hand` and `Library`), with no second `ChangeZone`. Delay's "with three time counters on it" and the cast-it-later riders (Kheru Spellsnatcher, Spelljack, Thranduil's Decree, Transcendent Dragon) would follow as sub-abilities over the exiled card.

## Why it matters

As typed, the spell visits the graveyard first: an engine would fire "whenever a card is put into a graveyard" triggers and graveyard replacement effects for a card that never gets there, and a deck-analysis consumer reads these counterspells as cards that exile from a graveyard (graveyard hate). MTG Arena's game log shows the move as one `Countered` zone transfer, Stack to Exile.
