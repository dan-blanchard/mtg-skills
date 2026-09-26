# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

**From the phase v0.94.0 bump (2026-09-26)**

- **d20 roll tables.** Phase now parses them into `results[]` rows, which the shared
  effect walker never reads. Farideh's Fireball (`symmetric_damage_each`),
  Overwhelming Encounter (`pump_makers`) and Druid of the Emerald Grove (`tutor`) lost
  their old flattened fires. Walking `results[]` adds about 50 fires across 117 cards,
  so those need a review first.
- **Walking `else_ability` everywhere.** "Otherwise" branches are opt-in per read
  (`walk_effects_with_else`). Walking them globally would change 176 cards: mostly
  plausible gains, but the Champion cards' `self_etb_payload` looks doubtful and 3
  fires are lost (`suspect_matters` ×2, `exile_removal`).
- **`named_synergy_overloaded_named_node`'s gap is the constant `True`**, so that
  bridge row can never retire itself.
- **Raw walks left in bridge-ledger matches.** The purity rule covers gaps only; the
  Ceremonial Knife `GrantTrigger` walk and `_blood_sacrificed_trigger_match` still
  walk nodes directly.

**From the 2026-09-17 architecture review (worth exploring, not started)**

- **lgs-search and mtga-import read the bulk around `CardPool`.** The legacy
  `default-cards*.json` locator is still alive in `lgs_search._locate_bulk_data`, and
  an exact-name price lookup may price an MDFC front face at 0.0 (unverified).
- **One Storefront browser session.** `open_handoff` / `open_login` are repeated
  across eight adapters.
- **The snapshot should serve the cost readout.** The SPA re-derives wildcard totals.
- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Known lane recall gaps (surfaced by ADR-0051; a lane fix repairs every consumer)**

- Tireless Provisioner ("Food or Treasure") fires only `food_makers`.
- Surveyor's Scope (fetch X basics) reads as `tutor`.
- Token makers whose tokens carry firebending or Vibranium mana.

**Limited support:** P0, P1 and P3 in `docs/plans/limited-sealed-support.md` are
untouched.

**Discovery ranking:** see ADR-0043's terminal-state amendment for the unclaimed
headroom and parked items.

## Settled: don't re-suggest

- **Two-arm lanes** (a structural arm OR a `synth_<key>` reference-arm concept, 91 of
  279 lanes): stable by design, not debt (ADR-0038 amendment). Don't tabulate or
  rename them.
- **Judged in good shape by the 2026-09-17 review:** `theme_presets` (a registry over
  signals; removal isn't duplicated), `cut_check`, proxy-printer's layout and Fetcher
  seam, `phase_bump`, `testkit`, `agent_bridge` / `events`, and the tuner's classify,
  shape and bracket modules.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
