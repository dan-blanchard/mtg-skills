# Delirium, Mana Web, Devastating Mastery: "that player controls" / "they control" stamped `controller: You` (Teferi, Temporal Pilgrim's -12 now parked instead)

Phase tag: v0.131.0 (`card-data-v0.131.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Delirium** (MIR):
> Cast this spell only during an opponent's turn.
> Tap target creature that player controls. That creature deals damage equal to its power to the player. Prevent all combat damage that would be dealt to and dealt by the creature this turn.

**Mana Web** (WTH):
> Whenever a land an opponent controls is tapped for mana, tap all lands that player controls that could produce any type of mana that land could produce.

**Devastating Mastery** (STX):
> You may pay {2}{W}{W} rather than pay this spell's mana cost.
> If the {2}{W}{W} cost was paid, an opponent chooses up to two nonland permanents they control and returns them to their owner's hand.
> Destroy all nonland permanents.

**Teferi, Temporal Pilgrim** (BRO):
> Whenever you draw a card, put a loyalty counter on Teferi.
> [0]: Draw a card.
> [−2]: Create a 2/2 blue Spirit creature token with vigilance and "Whenever you draw a card, put a +1/+1 counter on this token."
> [−12]: Target opponent chooses a permanent they control and returns it to its owner's hand. Then they shuffle each nonland permanent they control into its owner's library.

## Observed at v0.131.0

Delirium ("Tap target creature that player controls"):

```json
{"type": "SetTapState", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}, "scope": {"type": "Single"}, "state": {"type": "Tap"}}
```

Mana Web ("tap all lands that player controls ..."; the trigger's `valid_card` correctly says `controller: Opponent`):

```json
{"type": "SetTapState", "target": {"type": "Typed", "type_filters": ["Land"], "controller": "You"}, "scope": {"type": "All"}, "state": {"type": "Tap"}}
```

Devastating Mastery ("an opponent chooses up to two nonland permanents they control and returns them"):

```json
{"type": "TargetOnly", "target": {"type": "Typed", "type_filters": ["Permanent", {"Non": "Land"}], "controller": "You"}}
```

Teferi -12 changed shape at v0.131.0: the `controller: You` stamp is gone because both sentences are now parked (at v0.118.0 the opening `TargetOnly` carried `controller: TargetOpponent` and the final `ChangeZone` to `Library` carried `controller: You`). The record is marked `confirmed_misparse: "wrong_player"`:

```json
{"effect": {"type": "Unimplemented", "name": "target-opponent permanent choice", "description": "Target opponent chooses a permanent they control and returns it to its owner's hand."}, "declares_chosen_group": 0, "cost": {"type": "Loyalty", "amount": -12}, "sub_ability": {"effect": {"type": "Unimplemented", "name": "shuffle", "description": "shuffle each nonland permanent they control into its owner's library"}}, "activation_restrictions": [{"type": "AsSorcery"}]}
```

## Expected

The filter's controller is the anaphoric player the earlier clause or trigger named (`TriggeringPlayer` / `ScopedPlayer` / `TargetOpponent`; `DeclaredPlayer` is already used this way for The Fall of Kroog). For Teferi, the two sentences typed again (a chosen-permanent bounce by the target opponent, then a `ChangeZone` to its owner's library over that opponent's nonland permanents).

## Why it matters

Stamped `You`, the clause targets the caster's own permanents: Delirium taps your creature, Devastating Mastery bounces your permanents. Teferi's ultimate now does nothing at all.
