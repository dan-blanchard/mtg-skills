# Within Range, Soulblast, Overclocked Electromancer, Tar Fiend, Notorious Throng: damage, life loss and counts "equal to ..." parked as `unparsed_quantity`

Phase tag: v0.118.0 (`card-data-v0.118.0.json`; face record as the card-data holds it, null/false/empty fields and noise keys dropped).

## Cards

**Within Range** (TDC):
> When this enchantment enters, create two 1/1 red Warrior creature tokens.
> Whenever you attack, each opponent loses life equal to the number of creatures attacking them.

**Soulblast** (CHK):
> As an additional cost to cast this spell, sacrifice all creatures you control.
> Soulblast deals damage to any target equal to the total power of the sacrificed creatures.

**Overclocked Electromancer** (M3C):
> At the beginning of combat on your turn, you may pay {E}{E}{E}. If you do, put a +1/+1 counter on this creature.
> Whenever this creature attacks, double its power until end of turn.
> Whenever this creature deals combat damage to a creature, if that creature was dealt excess damage this turn, you get X {E}, where X is that excess damage.

**Tar Fiend** (ALA):
> Devour 2 (As this creature enters, you may sacrifice any number of creatures. It enters with twice that many +1/+1 counters on it.)
> When this creature enters, target player discards a card for each creature it devoured.

**Notorious Throng** (ZNC):
> Prowl {5}{U} (You may cast this for its prowl cost if you dealt combat damage to a player this turn with a Rogue.)
> Create X 1/1 black Faerie Rogue creature tokens with flying, where X is the damage dealt to your opponents this turn. If this spell's prowl cost was paid, take an extra turn after this one.

## Observed at v0.118.0

Within Range:

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_quantity", "description": "lose life equal to the number of creatures attacking them"}, "player_scope": {"type": "Opponent"}}
```

Soulblast:

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_quantity", "description": "deal damage to any target equal to the total power of the sacrificed creatures"}}
```

Overclocked Electromancer (third trigger; the other two are typed):

```json
{"effect": {"type": "Unimplemented", "name": "unparsed_quantity", "description": "get X {E}, where X is that excess damage"}}
```

Tar Fiend (the target player is peeled to `valid_target` on the trigger; Devour 2 itself is typed):

```json
{"mode": "ChangesZone", "execute": {"effect": {"type": "Unimplemented", "name": "unparsed_quantity", "description": "discard a card for each creature it devoured"}}, "valid_card": {"type": "SelfRef"}, "destination": "Battlefield", "valid_target": {"type": "Player"}}
```

Notorious Throng (the flying token is part of the parked text; the `ExtraTurn` rider is typed):

```json
{"type": "Unimplemented", "name": "unparsed_quantity", "description": "Create X 1/1 black Faerie Rogue creature tokens with flying, where X is the damage dealt to your opponents"}
```

## Expected

The verb typed (`LoseLife`, `DealDamage`, `GainEnergy`, `Discard`, `Token`) with an `amount`/`count` of a `QuantityRef` (creatures attacking them; total power of the sacrificed creatures; excess damage; creatures devoured; damage dealt to opponents this turn).

## Why it matters

212 commander-legal cards (279 records in card-data) carry `unparsed_quantity`; each loses its verb as well as its number.
