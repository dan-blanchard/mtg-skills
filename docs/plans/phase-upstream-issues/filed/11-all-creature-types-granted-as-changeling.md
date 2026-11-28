<!-- Status: FILED 2026-11-27 as https://github.com/phase-rs/phase/issues/11414 (against phase v0.135.0, commit 3d5ecbf; measured in phase's engine at the v0.134.0 tag and independently verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] "with/gain all creature types" is parsed as AddKeyword Changeling (layer 6) instead of a layer-4 type change (Mutavault, Volatile Claws, …)

:robot: _AI text below_ :robot:

### Card(s)

Mutavault, Faceless Haven, Soulstone Sanctuary, Glamer Gifter, Oko, Lorwyn Liege, Amoeboid Changeling, Blades of Velis Vel, Mirror Entity, Volatile Claws (all reported supported by the coverage export); Shields of Velis Vel (already in `confirmed-misparses.toml` as `extra_effect` on this clause)

### Build/version

v0.135.0 3d5ecbf (release card-data `card-data-f1733bdf9bd2e771.json`; Mutavault's parse is the same in every release card-data checked, v0.66.0 to v0.135.0)

### Game mode

Unknown (found by reading the release card-data; outcome measured with a throwaway integration test at the v0.134.0 tag, whose `crates/engine/src/game/layers.rs` and Mutavault record are identical to v0.135.0's, see Logs)

### Actual behavior

Oracle text:

> Mutavault: {T}: Add {C}.
> {1}: This land becomes a 2/2 creature with all creature types until end of turn. It's still a land.

The animation gives the land the Changeling keyword instead of the creature types (record abridged: null fields omitted):

```json
{"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "SelfRef"}, "modifications": [{"type": "SetPower", "value": 2}, {"type": "SetToughness", "value": 2}, {"type": "AddKeyword", "keyword": "Changeling"}, {"type": "AddType", "core_type": "Creature"}], "description": "become a 2/2 creature with all creature types"}], "duration": "UntilEndOfTurn"}
```

This is deliberate in the parser. `map_keyword` (`crates/phase-parser/src/parser/oracle_static/grammar.rs`) maps "all creature types" to `Keyword::Changeling` ("Granting Changeling keyword triggers layer system post-fixup to add all types"). `map_token_keyword` (`oracle_effect/token.rs`) does the same, and `map_keyword_all_creature_types_returns_changeling` / `gain_all_creature_types_produces_add_keyword_changeling` assert it. The keyword is a layer-6 ability, though, and `derive_layer_characteristics` (`crates/engine/src/game/layers.rs`) turns a granted Changeling into subtypes only after the whole layer loop ("Step 3b: Changeling post-fixup"). The rules make these types a layer-4 type change. Two things go wrong:

1. **A lord already on the battlefield skips it.** Lord of Atlantis ("Other Merfolk get +1/+1 and have islandwalk") first applies in layer 6. Its affected set is fixed there and kept for layer 7c (`started_effect_sets`, CR 613.6). Its timestamp is earlier than the animation's, so the set is fixed before Mutavault has Changeling. The animated Mutavault is every creature type, but it stays 2/2 with no islandwalk. If the lord enters after the animation, Mutavault is 3/3 with islandwalk. Goblin King behaves the same way. Merfolk Sovereign, whose +1/+1 has no layer-6 part, does reach it. So does Lord of Atlantis for a printed changeling (Changeling Outcast), whose types come from the layer-4 `AddAllCreatureTypes` CDA.
2. **"Loses all abilities" after the animation removes every creature type.** Dress Down ("Creatures lose all abilities") or a single-target "loses all abilities until end of turn" strips the Changeling keyword. The post-fixup then adds nothing, and the animated Mutavault has no creature types at all.

The "gains all creature types" cards carry the same grant. Volatile Claws: `{"type": "AddPower", "value": 2}, {"type": "AddToughness", "value": 0}, {"type": "AddKeyword", "keyword": "Changeling"}` on your creatures. Cast with Goblin King in play, it leaves a Merfolk of the Pearl Trident a 3/1 with no mountainwalk. Faceless Haven and Soulstone Sanctuary have Mutavault's node with `AddKeyword Vigilance` beside it. Glamer Gifter, Oko, Lorwyn Liege's +2, Amoeboid Changeling's first ability, Blades of Velis Vel, Mirror Entity and Shields of Velis Vel each have `AddKeyword Changeling` for "gain(s) all creature types".

Phase already has a layer-4 primitive for this, `ContinuousModification::AddAllCreatureTypes`. It is used for "is every creature type" (Maskwood Nexus, Amorphous Axe, Mistform Ultimus) and for printed changeling's CDA (`database/synthesis.rs`).

### Expected behavior

> CR 702.73a: Changeling is a characteristic-defining ability. "Changeling" means "This object is every creature type." This ability works everywhere, even outside the game. See rule 604.3.

> CR 613.1d: Layer 4: Type-changing effects are applied. These include effects that change an object's card type, subtype, and/or supertype.

> CR 613.1f: Layer 6: Ability-adding effects, keyword counters, ability-removing effects, and effects that say an object can't have an ability are applied.

> CR 613.6: … If an effect starts to apply in one layer and/or sublayer, it will continue to be applied to the same set of objects in each other applicable layer and/or sublayer, even if the ability generating the effect is removed during this process.

Rulings:

> Mutavault (2008-04-01): "Although Mutavault has all creature types while it's animated, it does not have the changeling keyword ability."

> Faceless Haven (2021-02-05): "Although Faceless Haven will have all creature types after its last activated ability resolves, it will not have the changeling keyword ability."

"With all creature types" and "gain all creature types" are type-changing effects (layer 4), not an ability. So:

- With Lord of Atlantis in play, the animated Mutavault is a Merfolk before layer 6. It is in the lord's set, so it is 3/3 with islandwalk, whichever entered first.
- After it is animated, losing all abilities leaves its creature types alone. It has no changeling ability to lose.

Expected parse: `AddAllCreatureTypes` for "with all creature types" / "gain(s) all creature types", not `AddKeyword Changeling`. The Changeling keyword grant should stay for text that says "has changeling" (Moritte of the Frost, Omni-Changeling).

### Steps to reproduce

1. Control Lord of Atlantis and Mutavault (Mutavault under your control since your turn began). Activate Mutavault's {1} ability.
2. By the rules, Mutavault is a 3/3 with islandwalk. In phase it is a 2/2 without islandwalk, though it has every creature type.
3. Separately: control Mutavault, Coat of Arms and Goblin Piker. Activate Mutavault, then cast Dress Down.
4. By the rules, Mutavault is still every creature type: Mutavault 3/3, Goblin Piker 3/2. In phase, Mutavault has no creature types left: Mutavault 2/2, Goblin Piker 2/1. If Dress Down is cast before the activation, phase gives 3/3 and 3/2, which is correct.

### Logs/screenshots/game-state

Parse taken from the v0.135.0 release card-data. Outcome measured at the v0.134.0 tag with a throwaway test in `crates/engine/tests/`. It loaded the v0.134.0 release export with `CardDatabase::from_export`, added the real cards with `GameScenarioDbExt::add_real_card`, set `all_creature_types` to `creature_type_vocabulary()` as game setup does, activated with `runner.activate(mutavault, 1)`, and cast the real Dress Down and Volatile Claws. "loses-all-abilities" is a zero-cost "Target creature loses all abilities until end of turn." on Mutavault. The lines below are condensed from the test's output: labels shortened, and fields that don't bear on the result left out.

```
PROBE lord=Lord of Atlantis lord_enters_after_animation=false: Mutavault (islandwalk=false): core=[Land, Creature] pt=Some(2)/Some(2) changeling_kw=true n_subtypes=408 merfolk=true
PROBE lord=Lord of Atlantis lord_enters_after_animation=false: Merfolk of the Pearl Trident (islandwalk=true): pt=Some(2)/Some(2)
PROBE lord=Lord of Atlantis lord_enters_after_animation=true: Mutavault (islandwalk=true): core=[Land, Creature] pt=Some(3)/Some(3) changeling_kw=true n_subtypes=408 merfolk=true
PROBE lord=Lord of Atlantis lord_enters_after_animation=false: Changeling Outcast (islandwalk=true): pt=Some(2)/Some(2) changeling_kw=true n_subtypes=408
PROBE lord=Merfolk Sovereign lord_enters_after_animation=false: Mutavault: pt=Some(3)/Some(3)
PROBE lord=Goblin King lord_enters_after_animation=false: Mutavault: pt=Some(2)/Some(2) goblin=true
PROBE lord=Goblin King lord_enters_after_animation=false: Goblin Piker: pt=Some(3)/Some(2)
PROBE Dress Down after animation: Mutavault before Dress Down: pt=Some(3)/Some(3) changeling_kw=true n_subtypes=408
PROBE Dress Down after animation: Mutavault: core=[Land, Creature] pt=Some(2)/Some(2) changeling_kw=false n_subtypes=0 merfolk=false goblin=false
PROBE Dress Down after animation: Goblin Piker: pt=Some(2)/Some(1)
PROBE Dress Down first: Mutavault: pt=Some(3)/Some(3) changeling_kw=true n_subtypes=408
PROBE Dress Down first: Goblin Piker: pt=Some(3)/Some(2)
PROBE after loses-all-abilities: Mutavault: core=[Land, Creature] pt=Some(2)/Some(2) changeling_kw=false n_subtypes=0
PROBE after Volatile Claws (Goblin King in play): Merfolk of the Pearl Trident (mountainwalk=false): pt=Some(3)/Some(1) changeling_kw=true goblin=true
```
