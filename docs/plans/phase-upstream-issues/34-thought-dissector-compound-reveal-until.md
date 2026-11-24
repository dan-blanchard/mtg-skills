# Thought Dissector: "reveals cards until an artifact card or X cards are revealed" parked as `compound_reveal_until`

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Thought Dissector** (DST):
> {X}, {T}: Target opponent reveals cards from the top of their library until an artifact card or X cards are revealed, whichever comes first. If an artifact card is revealed this way, put it onto the battlefield under your control and sacrifice this artifact. Put the rest of the revealed cards into that player's graveyard.

## Observed at v0.131.0

The reveal is the residue; the steps after it are typed and hang off it. The record is marked `confirmed_misparse: "wrong_count"`:

```json
{"effect": {"type": "Unimplemented", "name": "compound_reveal_until", "description": "reveal cards from the top of their library until an artifact card or X cards are revealed, whichever comes first"}, "cost": {"type": "Composite", "costs": [{"type": "Mana", "cost": {"type": "Cost", "shards": ["X"]}}, {"type": "Tap"}]}, "sub_ability": {"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "ParentTarget"}, "enters_under": "You"}, "sub_ability": {"effect": {"type": "Sacrifice", "target": {"type": "SelfRef"}, "count": {"type": "Fixed", "value": 1}}, "sub_ability": {"effect": {"type": "ChangeZoneAll", "origin": "Exile", "destination": "Graveyard", "target": {"type": "TrackedSet"}}}}, "condition": {"type": "TargetMatchesFilter", "filter": {"type": "Typed", "type_filters": ["Artifact"]}, "use_lki": true}}}
```

At v0.118.0 the head was a `RevealTop {count: 1}` by an opponent (one card, not "until"), so this is a move from a wrong count to a residue. `compound_reveal_until` appears on no other record at v0.131.0. Separately, the last step moves "the rest of the revealed cards" from `Exile` to the graveyard, though revealed cards stay in the library.

## Expected

A `RevealUntil` (the effect phase types for Chaos Mutation) by the target opponent with two stop conditions, an artifact card or X cards revealed, whichever comes first; the found artifact put onto the battlefield under your control; the rest moved from the library to that player's graveyard.

## Why it matters

As parsed the ability reveals nothing, so nothing is stolen and the opponent's library is never milled.
