<!-- Status: FILED 2026-11-26 as https://github.com/phase-rs/phase/issues/11383 (against phase v0.134.0, commit 5d226a5; measured in phase's engine and independently verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] "Regenerate each creature you control" and "all lands you control phase out" parse exactly like "target …", so they ask for one target and affect only it (Wrap in Vigor, Loxodon Hierarch, Taniwha, …)

:robot: _AI text below_ :robot:

### Card(s)

Wrap in Vigor, Golgari Charm, Wail of the Nim, Loxodon Hierarch, Full Moon's Rise, Taniwha (all reported supported by the coverage export); The City on the Edge of Forever (unsupported, but only for its chapter III)

### Build/version

v0.134.0 5d226a5 (release card-data `card-data-0fd43dd7cf32923f.json`; the same parses are in v0.133.0)

### Game mode

Unknown (found by reading the release card-data; outcome measured with a throwaway integration test at the v0.134.0 tag, see Logs)

### Actual behavior

`Regenerate` and `PhaseOut` have only a `target` field, and "each X" / "all X" is written into it as the same `Typed` filter that "target X" produces. Nothing in the node tells the population form from the targeted one, so the engine builds a cast-time target slot for it, the player picks one object, and only that object is affected.

Oracle text:

> Wrap in Vigor: Regenerate each creature you control.

```json
{"effect": {"type": "Regenerate", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}}
```

The same node, field for field, is what `parse_oracle_text` gives "Regenerate target creature you control." (see Logs), and Death Ward's "Regenerate target creature." is that node without the controller (`{"type": "Regenerate", "target": {"type": "Typed", "type_filters": ["Creature"]}}`). The other regenerate cards carry it too:

- Golgari Charm, third mode: "Regenerate each creature you control." Same node.
- Wail of the Nim, first mode: "Regenerate each creature you control." Same node.
- Loxodon Hierarch: "{G}{W}, Sacrifice this creature: Regenerate each creature you control." Same node.
- Full Moon's Rise: "Sacrifice this enchantment: Regenerate all Werewolf creatures you control." `{"type": "Regenerate", "target": {"type": "Typed", "type_filters": ["Creature", {"Subtype": "Werewolf"}], "controller": "You"}}`

This is a follow-up to #2907. For phasing, #2907 (Teferi's Protection) was fixed with `phase_out_or_in_filter_is_mass` (`crates/phase-ast/src/types/ability.rs`), which treats an object `PhaseOut` as a population only when its filter is exactly `Typed[Permanent]` with a controller and no properties (or is anchored on a target player). Other "all … phase out" populations still get a target slot:

> Taniwha: At the beginning of your upkeep, all lands you control phase out.

```json
{"mode": "Phase", "phase": "Upkeep", "execute": {"effect": {"type": "PhaseOut", "target": {"type": "Typed", "type_filters": ["Land"], "controller": "You"}}}}
```

That is the node of Haystack's "Target creature you control phases out" with `Land` for `Creature`. The City on the Edge of Forever's chapter I, "All artifacts and creatures phase out", is `{"type": "PhaseOut", "target": {"type": "Or", "filters": [{"type": "Typed", "type_filters": ["Artifact"]}, {"type": "Typed", "type_filters": ["Creature"]}]}}`, which also gets a slot.

Where it goes wrong in the engine:

- `extract_target_filter_from_effect` returns the `Typed` filter (it is not a context ref, and `Regenerate` has no population carve-out), so `collect_target_slots_inner` (`crates/engine/src/game/ability_utils.rs`) pushes one required slot over the matching objects.
- `regenerate::resolve` installs a shield only on `ability.targets` when targets exist.
- `phase_out::collect_object_targets` returns the declared object targets before its mass fallback.

Measured at v0.134.0 (each card's oracle text parsed by `parse_oracle_text`):

- Wrap in Vigor with two creatures: one slot, two legal targets. With no creatures: `ActionNotAllowed("No legal targets available")`, so the spell can't be cast.
- Wrap in Vigor targeting creature A, then "Destroy all creatures": A is on the battlefield, B is in the graveyard.
- Golgari Charm's third mode, Wail of the Nim's first mode, Loxodon Hierarch: one slot each. Full Moon's Rise with no Werewolves: "No legal targets available".
- Taniwha's trigger with three lands: `TriggerTargetSelection` with one slot over the three lands. After it resolves, one land is phased out and two are not.
- The City on the Edge of Forever, chapter I: one slot over the artifacts and creatures.
- Controls: "All permanents you control phase out" (Teferi's Protection) builds no slot.

### Expected behavior

> CR 115.10: Spells and abilities can affect objects and players they don’t target. In general, those objects and players aren’t chosen until the spell or ability resolves. See rule 608, “Resolving Spells and Abilities.”

> CR 115.10a: Just because an object or player is being affected by a spell or ability doesn’t make that object or player a target of that spell or ability. Unless that object or player is identified by the word “target” in the text of that spell or ability, or the rule for that keyword ability, it’s not a target.

> CR 701.19a: If the effect of a resolving spell or ability regenerates a permanent, it creates a replacement effect that protects the permanent the next time it would be destroyed this turn. In this case, “Regenerate [permanent]” means “The next time [permanent] would be destroyed this turn, instead remove all damage marked on it and its controller taps it. If it’s an attacking or blocking creature, remove it from combat.”

Rulings:

> Wrap in Vigor (2007-05-01): Wrap in Vigor sets up a separate regeneration shield on each creature you control at the time it resolves.

> Loxodon Hierarch (2005-10-01): The second ability sets up individual regeneration shields for each creature you control. They are each used up as necessary during the turn and wear off when the turn ends.

None of these cards targets. Wrap in Vigor, Golgari Charm, Wail of the Nim, Loxodon Hierarch and Full Moon's Rise should put a shield on every matching creature as they resolve, and can be cast or activated with none. Taniwha should phase out every land you control, and the Saga every artifact and creature.

Expected parse: a population form that the slot builder skips, like `DestroyAll`, `PumpAll` and `Transform { scope: All }` already have. PR #10814 did this for "remove all … counters from all …" (#9899) with a `scope: EffectScope` on `RemoveCounter`; the same shape fits here. A mass scope on `Regenerate` and `PhaseOut`, or an `All` variant, set from the "each" / "all" wording instead of inferred from the filter's shape. The narrow `phase_out_or_in_filter_is_mass` check could then go.

### Steps to reproduce

1. Control two 2/2 creatures. Cast Wrap in Vigor. The engine asks for a target. Choose one.
2. Cast a "Destroy all creatures" spell. By the rules both creatures regenerate. By the parse, only the chosen one survives.
3. Control Taniwha and three lands. At your upkeep the trigger asks you to choose one land, and only that land phases out. By the rules all three phase out.
4. Control no creatures and try to cast Wrap in Vigor. It is refused ("No legal targets available"). By the rules it can be cast.

### Logs/screenshots/game-state

Parses taken from the v0.134.0 release card-data (identical in v0.133.0). Outcome measured at the v0.134.0 tag with a throwaway test in `crates/engine/tests/`. Its core:

```rust
let parsed = parse_oracle_text("Regenerate each creature you control.", "Wrap in Vigor", &[], &["Instant".into()], &[]);
let resolved = build_resolved_from_def(&parsed.abilities[0], source, PlayerId(0));
build_target_slots(&state, &resolved) // two creatures: 1 slot, 2 legal targets; none: Err("No legal targets available")
```

Output ("Control Regen" is "Regenerate target creature you control."; "Loxodon Hierarch Probe" is Loxodon Hierarch's activated line alone):

```
PROBE Wrap in Vigor: 1 slot(s): [2]
PROBE Wrap in Vigor: slot build error: ActionNotAllowed("No legal targets available")
PROBE Control Regen [ability 0] creatures=2: effect={"type":"Regenerate","target":{"type":"Typed","type_filters":["Creature"],"controller":"You","properties":[]}}
PROBE Control Regen: 1 slot(s): [2]
PROBE zones after wrath: A=Battlefield B=Graveyard
PROBE Golgari Charm: 1 slot(s): [3]
PROBE Wail of the Nim: 1 slot(s): [3]
PROBE Loxodon Hierarch Probe: 1 slot(s): [2]
PROBE Full Moon's Rise: slot build error: ActionNotAllowed("No legal targets available")
PROBE taniwha after advance: TriggerTargetSelection { … target_slots: [TargetSelectionSlot { legal_targets: [Object(ObjectId(1)), Object(ObjectId(2)), Object(ObjectId(3))], optional: false, … effect_kind: PhaseOut, … }], … }
PROBE taniwha phased out: true false false
PROBE The City on the Edge of Forever trigger 0: 1 slot(s): [3]
PROBE Mass Phase Control: 0 slot(s): []
```
