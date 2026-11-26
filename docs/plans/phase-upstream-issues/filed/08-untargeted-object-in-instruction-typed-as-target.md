<!-- Status: FILED 2026-11-26 as https://github.com/phase-rs/phase/issues/11384 (against phase v0.134.0, commit 5d226a5; measured in phase's engine and independently verified). Everything below this line is the text as posted: the TITLE line, then the body. -->

TITLE: [Card Bug] Sunder the Gateway / Calix, Guided by Fate: "transform an Incubator token you control" and "a copy of a nonlegendary enchantment you control" are announced as targets, so Sunder's second mode can't transform the token it just made

:robot: _AI text below_ :robot:

### Card(s)

Sunder the Gateway, Calix, Guided by Fate (both reported supported by the coverage export)

### Build/version

v0.134.0 5d226a5 (release card-data `card-data-0fd43dd7cf32923f.json`; the same parses are in v0.133.0)

### Game mode

Unknown (found by reading the release card-data; outcome measured with a throwaway integration test at the v0.134.0 tag, see Logs)

### Actual behavior

Both cards name an object with "a/an … you control" and no "target", inside an instruction that isn't a "Choose …" sentence. The parse gives that object a plain `Typed` filter at the default `Stack` choice timing, so the engine announces it as a target: Sunder's when the spell is cast, Calix's when the trigger is put on the stack.

> Sunder the Gateway (sorcery): Choose one — • Destroy target nontoken artifact or enchantment an opponent controls. Incubate 2. • Incubate 2, then transform an Incubator token you control.

Second mode:

```json
{"effect": {"type": "Incubate", "count": {"type": "Fixed", "value": 2}}, "sub_ability": {"effect": {"type": "Transform", "target": {"type": "Typed", "type_filters": [{"Subtype": "Incubator"}], "controller": "You", "properties": [{"type": "Token"}]}, "scope": {"type": "Single"}}}}
```

> Calix, Guided by Fate: Whenever Calix or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you control. Do this only once each turn.

```json
{"mode": "DamageDone", "execute": {"effect": {"type": "CopyTokenOf", "target": {"type": "Typed", "type_filters": ["Enchantment"], "controller": "You", "properties": [{"type": "NotSupertype", "value": "Legendary"}]}, "owner": {"type": "Controller"}, "count": {"type": "Fixed", "value": 1}}, "optional": true}, "optional": true, "constraint": {"type": "OncePerTurn", "spent_by": "IndicatedAction"}}
```

`Effect::target_filter` returns the `Transform { scope: Single }` target and, with no `source_filter`, the `CopyTokenOf` source. Neither is a context ref, so `collect_target_slots_inner` (`crates/engine/src/game/ability_utils.rs`) pushes a required slot for each.

The bare form is already handled. Since #10176 (PR #10555), "Choose a creature you control." gets `target_choice_timing: "Resolution"`, as in Final Showdown's second mode:

```json
{"effect": {"type": "TargetOnly", "target": {"type": "Typed", "type_filters": ["Creature"], "controller": "You"}}, "sub_ability": {"…": "…"}, "target_choice_timing": "Resolution"}
```

The same untargeted object written inside a transform or token-copy instruction gets no such mark. PR #10427 already notes the Calix half ("currently modelled as a stack-time target … That misparse is a separate follow-up") and added the guard test `calix_with_no_nonlegendary_enchantment_offers_nothing_and_spends_nothing`, which should keep passing after the fix.

Controls from the same card data:

- Seedpod Caretaker's targeted "Transform target Incubator token you control." parses to the identical node: `{"effect": {"type": "Transform", "target": {"type": "Typed", "type_filters": [{"Subtype": "Incubator"}], "controller": "You", "properties": [{"type": "Token"}]}, "scope": {"type": "Single"}}}`.
- City of Death's targeted "Create a token that's a copy of target non-Saga token you control." is the same `CopyTokenOf` shape as Calix's, with no timing mark.
- Followed Footsteps' untargeted "create a token that's a copy of enchanted creature" already carries `CopyTokenOf` with `"target_choice_timing": "Resolution"`.

Measured at v0.134.0 (oracle text parsed by `parse_oracle_text`):

- Sunder the Gateway, second mode, with no Incubator token: the cast is refused with `ActionNotAllowed("No legal mode selection for modal spell")`. The slot builder alone reports "No legal targets available" for that mode. With one Incubator token already in play, the mode builds one slot whose only legal target is that token. The target is fixed at cast, before this mode's own token exists, so the new token can never be the one transformed.
- Calix, Guided by Fate's second trigger, with two enchantments: one slot with two legal targets.

### Expected behavior

> CR 115.10: Spells and abilities can affect objects and players they don’t target. In general, those objects and players aren’t chosen until the spell or ability resolves. See rule 608, “Resolving Spells and Abilities.”

> CR 115.10a: Just because an object or player is being affected by a spell or ability doesn’t make that object or player a target of that spell or ability. Unless that object or player is identified by the word “target” in the text of that spell or ability, or the rule for that keyword ability, it’s not a target.

> CR 700.2a: The controller of a modal spell or activated ability chooses the mode(s) as part of casting that spell or activating that ability. If one of the modes would be illegal (due to an inability to choose legal targets, for example), that mode can’t be chosen. (See rule 601.2b.)

Rulings:

> Sunder the Gateway (2023-04-14): For the second mode, the Incubator token is chosen as Sunder the Gateway resolves. You can transform the Incubator token you just created or one you already controlled.

> Calix, Guided by Fate (2023-05-12): Calix's last ability doesn't target any permanent. You choose which nonlegendary enchantment you control you're creating a token copy of, if any, as the ability resolves. No player may take any actions between your choice and the creation of the token.

Sunder the Gateway's second mode needs no target, so it can always be chosen. On resolution it makes an Incubator token and then transforms one Incubator token you control, which can be the new one. Calix's ability doesn't target: the enchantment is chosen as it resolves, from the enchantments you control then.

By the parse, the enchantment is a target picked when the trigger goes on the stack. That has two effects:

- An enchantment that enters in response can't be chosen.
- If the chosen enchantment leaves before resolution, the only target is illegal and the ability doesn't resolve. By the rules you would choose another enchantment.

> CR 608.2b (excerpt): If all its targets, for every instance of the word “target,” are now illegal, the spell or ability doesn’t resolve.

Expected parse: the same `Resolution` timing PR #10555 gives the bare choice (and Followed Footsteps already has), for a "transform a/an …" or "a copy of a/an … you control" object with no printed "target".

### Steps to reproduce

1. Control no Incubator token. Cast Sunder the Gateway and choose the second mode. The engine refuses the mode. By the rules, you create an Incubator token and transform it into a 0/0 Phyrexian artifact creature with two +1/+1 counters.
2. Control Calix, Guided by Fate and two nonlegendary enchantments. Deal combat damage to a player with Calix. The trigger asks for a target among the two enchantments now. By the rules, nothing is chosen until it resolves.

### Logs/screenshots/game-state

Parses taken from the v0.134.0 release card-data (identical in v0.133.0). Outcome measured at the v0.134.0 tag with a throwaway test in `crates/engine/tests/`. It used `GameScenario::add_spell_to_hand_from_oracle` plus `runner.cast(id).modes(&[1]).try_resolve()` for Sunder, and `build_target_slots` on the parsed trigger's `execute` for Calix:

```
PROBE sunder mode 2, no Incubator: ok=false err=Some(ActionNotAllowed("No legal mode selection for modal spell")) zone=Hand
PROBE Sunder the Gateway [1] mine=0 theirs=0: slot build error: ActionNotAllowed("No legal targets available")
PROBE sunder mode 2 with one Incubator token in play: 1 slot(s): [[Object(ObjectId(1))]]
PROBE Calix trigger: 1 slot(s): [2] timing=Stack
```

The two Calix consequences listed under Expected behavior follow from the slot and CR 608.2b. They were not played.
