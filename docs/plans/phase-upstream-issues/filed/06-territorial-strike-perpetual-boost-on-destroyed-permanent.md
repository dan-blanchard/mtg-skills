<!-- Status: FILED 2026-11-25 as https://github.com/phase-rs/phase/issues/11364 (against phase v0.133.0, commit 890e1ee; verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Territorial Strike: "it perpetually gets +2/+2" is aimed at the destroyed permanent, not the beheld Dragon

:robot: _AI text below_ :robot:

### Card(s)

Territorial Strike (Alchemy: Tarkir)

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`, and the coverage export of the same build)

### Game mode

Unknown (found by reading the release card-data and engine source)

### Actual behavior

Oracle text ({1}{B}{G} sorcery):

> As an additional cost to cast this spell, you may behold a Dragon creature.
> Destroy target nonland permanent. If a Dragon creature was beheld, it perpetually gets +2/+2.

The additional cost is typed as an optional `Behold` of a Dragon creature:

```json
{"type": "Optional", "data": {"cost": {"type": "Behold", "count": 1, "filter": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Dragon"}]}, "action": "ChooseOrReveal"}}}
```

The perpetual +2/+2 that follows the destroy is typed on `ParentTarget`, which is the permanent the spell destroys:

```json
{"effect": {"type": "Destroy", "target": {"type": "Typed", "type_filters": ["Permanent", {"Non": "Land"}]}}, "sub_ability": {"effect": {"type": "ApplyPerpetual", "target": {"type": "ParentTarget"}, "modification": {"kind": "ModifyPowerToughness", "power": {"type": "Fixed", "value": 2}, "toughness": {"type": "Fixed", "value": 2}}}, "condition": {"type": "AdditionalCostPaid"}, "sub_link": "SequentialSibling"}}
```

The rider inherits the Destroy's target, which the engine still finds after the move, so the destroyed card, now in its owner's graveyard, perpetually gets +2/+2.

The coverage export reports the card as supported, and the card is not in `confirmed-misparses.toml`.

### Expected behavior

> CR 701.4a: “Behold a [quality]” means “Reveal a [quality] card from your hand or choose a [quality] permanent you control on the battlefield.”

> CR 701.4b: The phrase “if a [quality] was beheld” refers to whether or not the object had that quality at the time the player took that action, regardless of whether or not the revealed card or chosen permanent still has that quality as the spell or ability including that phrase resolves.

"It" is the beheld Dragon: the Dragon creature you control that you chose, or the Dragon card you revealed from your hand. By the parse, the beheld Dragon never gets +2/+2, and the perpetual change is aimed at the permanent the spell just destroyed.

Expected parse: the same `ApplyPerpetual` and `AdditionalCostPaid` condition, with the target being the object beheld for the additional cost instead of `ParentTarget`. `CostPaidObject` ("the object paid as a cost for the resolving spell or ability") looks like the matching referent, if the behold cost records its object there.

Monstrous Emergence (supported) types its choose-or-reveal additional cost as the same `Behold` cost and reads the chosen object with `Power` of `CostPaidObject`. Prophet of the Planeswalker has the same "If you do, it perpetually gains …" after a behold, and the coverage export reports it unsupported, with the gap `Effect:unbound_subject` on that clause.

### Steps to reproduce

1. Control a Dragon creature, and let your opponent control a nonland permanent.
2. Cast Territorial Strike, beholding your Dragon as the additional cost and targeting the opponent's permanent.
3. The permanent is destroyed, and your Dragon should perpetually get +2/+2. By the engine, the destroyed card perpetually gets +2/+2 in its owner's graveyard, and your Dragon is unchanged.

### Logs/screenshots/game-state

Parse taken from the v0.133.0 release card-data. `supported: true` comes from the v0.133.0 coverage export (`coverage-data.json`, commit 890e1ee).

Outcome read from the v0.133.0 engine source, not played.
