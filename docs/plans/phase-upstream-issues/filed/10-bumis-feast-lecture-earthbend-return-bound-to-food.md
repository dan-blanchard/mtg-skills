<!-- Status: FILED 2026-11-27 as https://github.com/phase-rs/phase/issues/11406 (against phase v0.134.0, commit 5d226a5; measured in phase's engine and independently verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Bumi's Feast Lecture: the earthbend return is bound to `LastCreated` (the Food token), so the land never returns when it dies

:robot: _AI text below_ :robot:

### Card(s)

Bumi's Feast Lecture (reported supported by the coverage export)

### Build/version

v0.134.0 5d226a5 (release card-data `card-data-0fd43dd7cf32923f.json`; the same parse is in every release card-data checked, v0.66.0 to v0.134.0; #313 fixed the general earthbend return before v0.66.0, and this card's parse was not changed by it)

### Game mode

Unknown (found by reading the release card-data; outcome measured with a throwaway integration test at the v0.134.0 tag, see Logs)

### Actual behavior

Oracle text:

> Create a Food token. Then earthbend X, where X is twice the number of Foods you control. (A Food token is an artifact with "{2}, {T}, Sacrifice this token: You gain 3 life." To earthbend X, target land you control becomes a 0/0 creature with haste that's still a land. Put X +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)

The earthbend's delayed trigger returns `LastCreated`, and the last object this spell created is the Food token:

```json
{"type": "CreateDelayedTrigger", "condition": {"type": "WhenDiesOrExiled", "filter": {"type": "ParentTarget"}}, "effect": {"effect": {"type": "ChangeZone", "origin": "Battlefield", "destination": "Battlefield", "target": {"type": "LastCreated"}, "enters_under": "You", "enter_tapped": true}}}
```

Across the card data, 36 of the 38 earthbend delayed returns write it on the land that died (`TriggeringSource`), Earthbending Lesson's among them:

```json
{"type": "CreateDelayedTrigger", "condition": {"type": "WhenDiesOrExiled", "filter": {"type": "ParentTarget"}}, "effect": {"effect": {"type": "ChangeZone", "destination": "Battlefield", "target": {"type": "TriggeringSource"}, "enters_under": "You", "enter_tapped": true}}}
```

Bumi's Feast Lecture's is the only one on `LastCreated`. It is also the only one with `origin: "Battlefield"`. When the trigger resolves, the land is in the graveyard or exile, and `ChangeZone` skips a move whose origin no longer matches (`crates/engine/src/game/effects/change_zone.rs`, the CR 400.7 guard), so both fields need fixing. The other exception, Fatal Fissure's `ParentTarget`, is in the delayed trigger already reported in #9394.

Measured at v0.134.0, with the release card data loaded by `CardDatabase::from_export` and the real card cast through `GameScenario`. P0 controls a Forest, casts Bumi's Feast Lecture targeting it, then destroys the animated Forest:

- The Food token is created, and the Forest becomes a creature with two +1/+1 counters.
- After the Forest is destroyed, it stays in the graveyard. It is not returned.
- Control: Earthbending Lesson on the same board returns the destroyed Forest to the battlefield tapped.

### Expected behavior

> CR 701.66a: “Earthbend N” means “Target land you control becomes a 0/0 land creature with haste in addition to its other types. Put N +1/+1 counters on it. When that land dies or is put into exile, return it to the battlefield tapped under your control.”

Ruling (Bumi's Feast Lecture, 2025-10-02):

> "Earthbend N" means "Target land you control becomes a 0/0 land creature with haste in addition to its other types. Put N +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped under your control."

When the earthbent land dies or is exiled, the land itself returns to the battlefield tapped. The Food token has nothing to do with the return.

Expected parse: the same return the other earthbend cards carry (`target: TriggeringSource`, no `origin: Battlefield`), not `LastCreated`.

### Steps to reproduce

1. Control a land. Cast Bumi's Feast Lecture targeting it. You create a Food token, and the land becomes a 2/2 land creature (X = 2 with one Food).
2. Destroy the land creature, for example with "Destroy target creature."
3. By the rules, the land returns to the battlefield tapped. By the parse, it stays in your graveyard.

### Logs/screenshots/game-state

Parse taken from the v0.134.0 release card-data. Outcome measured at the v0.134.0 tag with a throwaway test in `crates/engine/tests/`. It used `GameScenarioDbExt::add_real_card` with the release export, `runner.cast(bumi).target_object(forest)`, then a zero-cost "Destroy target creature." on the Forest:

```
PROBE bumi land zone=Battlefield counters=2 battlefield P0=["Food", "Forest"]
PROBE bumi after the land dies: battlefield P0=["Food"] graveyard P0=["Bumi's Feast Lecture", "Forest", "Murder"]
PROBE bumi Forest objects (zone, tapped): [(Graveyard, false)]
PROBE lesson land zone=Battlefield counters=4 battlefield P0=["Forest"]
PROBE lesson after the land dies: battlefield P0=["Forest"] graveyard P0=["Earthbending Lesson", "Murder"]
PROBE lesson Forest objects (zone, tapped): [(Battlefield, true)]
```

("lesson" is Earthbending Lesson, the control.)
