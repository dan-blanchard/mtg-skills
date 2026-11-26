<!-- Status: NOT FILED. Dropped 2026-11-25 after verification; the reason is the first line below. -->

NOT FILED (2026-11-25, verifier): the demotion is deliberate and tested (crates/engine/tests/integration/granted_ability_self_binding.rs, self_grant_refused_name_demotes_its_grant asserts this line becomes granter_reference_unreached), and open #7619 reports the typed version misbehaving; a tested fail-closed choice is not a regression.

TITLE: [Card Bug] Necromancy: the reanimation trigger regressed to Unimplemented granter_reference_unreached at v0.104.0 (typed through v0.94.0)

:robot: _AI text below_ :robot:

### Card(s)

Necromancy

### Build/version

v0.133.0 890e1ee (release card-data `card-data-c747aa7d71f80ab3.json`). Last typed in v0.94.0 bd1e795. Parked since v0.104.0 4227122.

### Game mode

Unknown (found by comparing release card-data)

### Actual behavior

Oracle text:

> You may cast this spell as though it had flash. If you cast it any time a sorcery couldn't have been cast, the controller of the permanent it becomes sacrifices it at the beginning of the next cleanup step.
> When this enchantment enters, if it's on the battlefield, it becomes an Aura with "enchant creature put onto the battlefield with Necromancy." Put target creature card from a graveyard onto the battlefield under your control and attach this enchantment to it. When this enchantment leaves the battlefield, that creature's controller sacrifices it.

At v0.133.0 the second paragraph is one residue, and the card has no enters trigger. The flash permission and the cleanup-step sacrifice are still typed.

```json
{"abilities": [{"effect": {"type": "Unimplemented", "name": "granter_reference_unreached", "description": "When ~ enters, if it's on the battlefield, it becomes an Aura with \"enchant creature put onto the battlefield with ~.\" Put target creature card from a graveyard onto the battlefield under your control and attach ~ to it. When ~ leaves the battlefield, that creature's controller sacrifices it."}}]}
```

The release card-data for v0.66.0, v0.86.0 and v0.94.0 typed it as a second enters trigger, with no gap anywhere on the card (v0.94.0, `triggers[1]`):

```json
{"mode": "ChangesZone", "execute": {"effect": {"type": "ChangeZone", "origin": "Graveyard", "destination": "Battlefield", "target": {"type": "Typed", "type_filters": ["Creature"], "properties": [{"type": "InZone", "zone": "Graveyard"}]}, "enters_under": "You"}, "sub_ability": {"effect": {"type": "GenericEffect", "static_abilities": [{"mode": "Continuous", "affected": {"type": "OriginalSource"}, "modifications": [{"type": "AddSubtype", "subtype": "Aura"}, {"type": "AddKeyword", "keyword": {"Enchant": {"type": "ParentTarget"}}}]}], "duration": "Permanent"}, "sub_ability": {"effect": {"type": "Attach", "target": {"type": "ParentTarget"}, "selection": {}}, "sub_ability": {"effect": {"type": "CreateDelayedTrigger", "condition": {"type": "WhenLeavesPlayFiltered", "filter": {"type": "SelfRef"}}, "effect": {"effect": {"type": "Sacrifice", "target": {"type": "ParentTarget"}, "count": {"type": "Fixed", "value": 1}}}}}}}, "forward_result": true}, "valid_card": {"type": "SelfRef"}, "destination": "Battlefield", "condition": {"type": "SourceInZone", "zone": "Battlefield"}}
```

The v0.104.0 to v0.133.0 card-data all hold the residue above.

### Expected behavior

The card's ruling (2005-08-01): "Necromancy enters as an enchantment and then becomes an Enchant Creature Aura as a triggered ability upon entering. It follows all the rules for Auras from then on." CR 303.4b: "The object or player an Aura is attached to is called enchanted. The Aura is attached to, or "enchants," that object or player."

As parsed since v0.104.0, Necromancy enters and does nothing: no creature comes back. Phase reports the card unsupported. Through v0.94.0 it reanimated.

Expected parse: the v0.94.0 trigger above. It is the same chain phase types today for Animate Dead, which the v0.133.0 coverage export reports as supported: `ChangeZone` Graveyard→Battlefield `enters_under: You`, a `GenericEffect` on `OriginalSource` setting `Enchant ParentTarget`, `Attach` to `ParentTarget`, and a `WhenLeavesPlayFiltered` delayed `Sacrifice` of `ParentTarget`. For Necromancy the effect also adds the Aura subtype, and the `ChangeZone` target is a creature card in any graveyard.

### Steps to reproduce

1. Have a creature card in any graveyard. Cast Necromancy at sorcery speed.
2. The enters trigger should put that creature onto the battlefield under your control, with Necromancy attached to it. As parsed, nothing happens.

### Logs/screenshots/game-state

Release card-data compared: v0.66.0, v0.86.0, v0.94.0 (typed) against v0.104.0, v0.118.0, v0.131.0, v0.133.0 (residue).
