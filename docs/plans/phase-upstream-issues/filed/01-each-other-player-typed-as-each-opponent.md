<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11359 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] "Each other player" is typed as each opponent, so a teammate is skipped (CR 102.3): Syphon Mind, Savra, Shattergang Brothers and 9 more

:robot: _AI text below_ :robot:

### Card(s)

Syphon Mind, Savra, Queen of the Golgari, Shattergang Brothers, Syphon Flesh, Bond of Agony, Urborg Syphon-Mage, Rampage of the Valkyries, Hunted Wumpus, Charmed Griffin, Enslaved Horror, Hired Giant, Indentured Djinn

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`, and the coverage export of the same build)

### Game mode

Unknown (found by reading the release card-data and engine source; the wrong outcome needs a team game such as Two-Headed Giant or Two-Headed Giant Commander)

### Actual behavior

Every "each other player …" instruction on these cards is lowered to `player_scope: {"type": "Opponent"}`, the same scope as "each opponent". The coverage export reports all 12 cards as supported.

Syphon Mind ("Each other player discards a card. You draw a card for each card discarded this way."):

```json
{"effect": {"type": "Discard", "count": {"type": "Fixed", "value": 1}, "target": {"type": "Controller"}}, "sub_ability": {"effect": {"type": "Draw", "count": {"type": "Ref", "qty": {"type": "FilteredTrackedSetSize", "filter": {"type": "Typed", "type_filters": ["Card"]}, "caused_by": "Discarded"}}, "target": {"type": "Controller"}}}, "player_scope": {"type": "Opponent"}}
```

Savra, Queen of the Golgari ("… you may pay 2 life. If you do, each other player sacrifices a creature of their choice."), the sacrifice after the life payment:

```json
{"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}, "count": {"type": "Fixed", "value": 1}}, "condition": {"type": "EffectOutcome", "signal": "OptionalEffectPerformed"}, "player_scope": {"type": "Opponent"}}
```

Shattergang Brothers ("{2}{B}, Sacrifice a creature: Each other player sacrifices a creature."; its artifact and enchantment abilities have the same scope):

```json
{"effect": {"type": "Sacrifice", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}, "count": {"type": "Fixed", "value": 1}}, "player_scope": {"type": "Opponent"}}
```

Bond of Agony ("Each other player loses X life."):

```json
{"effect": {"type": "LoseLife", "amount": {"type": "Ref", "qty": {"type": "Variable", "name": "X"}}}, "player_scope": {"type": "Opponent"}}
```

The other cards listed carry the same `player_scope: {"type": "Opponent"}` on their "each other player" instruction.

### Expected behavior

> CR 102.3: In a multiplayer game between teams, a player’s teammates are the other players on their team, and the player’s opponents are all players not on their team.

"Each other player" is every player except you, so in a team game it includes your teammate; "each opponent" does not. The `player_scope` driver resolves `Opponent` through the team-aware `players::is_opponent` (`matches_player_scope`). In Two-Headed Giant, then, the parse would skip your teammate: they would not discard to Syphon Mind (and you would draw one card fewer), would not sacrifice to Savra or Shattergang Brothers, and would not lose life to Bond of Agony.

The expected scope is every player but the controller. Phase already writes such a scope in two places:

- Reverent Silence types "you may have each other player gain 6 life" as `{"type": "PlayerMatching", "player": {"type": "AllExcept", "exclude": {"type": "Controller"}}}`. That scope sits in its alternative cost (the `GainLife` of an `EffectCost` in `casting_options`). Reverent Silence itself is unsupported, for another clause (`Swallow:Optional_MayHave`).
- Zenith Chronicler is the clean supported example of the per-player form: its "each other player draws a card" is `player_scope: {"type": "AllExcept", "exclude": {"type": "TriggeringPlayer"}}`.

Grave Pact has the same clause and is already in `confirmed-misparses.toml` (`wrong_player`, "each other player sacrifices a creature of their choice"). None of the 12 cards above are listed there.

Related: #9858 (open), the converse case, where some `Opponent` arms test `!= controller` and so include teammates.

### Steps to reproduce

1. Start a Two-Headed Giant game. P0 and P1 are teammates, and P2 and P3 are the opposing team. Each player has cards in hand.
2. P0 casts Syphon Mind.
3. P2 and P3 should each discard a card, and so should P1, P0's teammate; P0 should then draw three cards. By the parse and the scope driver above, P1 keeps their hand and P0 draws two.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data. Each card's `supported: true` comes from the v0.133.0 coverage export (`coverage-data.json`, commit 890e1ee).

Outcome read from the v0.133.0 engine source, not played.
