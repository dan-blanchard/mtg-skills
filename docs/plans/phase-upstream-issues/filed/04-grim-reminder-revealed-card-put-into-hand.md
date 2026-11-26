<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11362 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Grim Reminder: the card it only reveals is put into your hand (CR 701.23a)

:robot: _AI text below_ :robot:

### Card(s)

Grim Reminder

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`)

### Game mode

Unknown (found by reading the release card-data)

### Actual behavior

Oracle text:

> Search your library for a nonland card and reveal it. Each opponent who cast a spell this turn with the same name as that card loses 6 life. Then shuffle.
> {B}{B}: Return this card from your graveyard to your hand. Activate only during your upkeep.

The search is typed with `reveal: true`. It is then followed by a `ChangeZone` from Library to Hand, which the card does not print. The life-loss sentence is a separate residue (`unbound_subject`), and that residue is the only coverage gap on the card:

```json
{"effect": {"type": "SearchLibrary", "filter": {"type": "Typed", "type_filters": ["Card", {"Non": "Land"}]}, "count": {"type": "Fixed", "value": 1}, "reveal": true}, "sub_ability": {"effect": {"type": "ChangeZone", "origin": "Library", "destination": "Hand", "target": {"type": "Any"}}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "unbound_subject", "description": "who cast a spell this turn with the same name as that card loses 6 life"}, "sub_ability": {"effect": {"type": "Shuffle", "target": {"type": "Controller"}}}, "player_scope": {"type": "Opponent"}}}}
```

The life-loss residue is tracked in #9752 (open); this issue is only the move to hand.

The same `ChangeZone` to Hand is in every release card-data checked, from v0.66.0 to v0.133.0. At v0.104.0 and earlier, the life loss was a plain `LoseLife 6` for each opponent with no same-name qualifier, and the card carried only a `Duration_ThisTurn` parse warning.

### Expected behavior

> CR 701.23a: To search for a card in a zone, look at all cards in that zone (even if it’s a hidden zone) and find a card that matches the given description.

> CR 701.20a: To reveal a card, show that card to all players for a brief time. If an effect causes a card to be revealed, it remains revealed for as long as necessary to complete the parts of the effect that card is relevant to. …

Grim Reminder never moves the card: it is found, revealed, and shuffled back with the rest of the library. By the parse, Grim Reminder is a one-mana-more Demonic Tutor that puts any nonland card into your hand.

Expected parse: the `SearchLibrary {reveal: true}`, then the per-opponent life loss over "the same name as that card", then the `Shuffle`, with no `ChangeZone`.

### Steps to reproduce

1. Cast Grim Reminder and find any nonland card.
2. The card should be revealed and shuffled back into your library. By the parse, the `ChangeZone` puts it into your hand.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data.

Outcome read from the v0.133.0 engine source, not played.
