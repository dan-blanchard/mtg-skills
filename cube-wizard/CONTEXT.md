# cube-wizard Context

The bounded context for designing, balancing, and stress-testing MTG
cubes — curated card pools of 360–720 cards designed for drafting.

## Language

### Cube concepts

**Cube**:
A curated card pool sized 360–720 cards designed for drafting. The
cube is the unit of design; archetypes, themes, and gauntlet decks
are all framed relative to *this* cube's pool, not a generic
metagame.
_Avoid_: "deck pool", "card list" (too generic), "set" (means
something specific in MTG).

**Cube format**:
One of nine flavors that determine card-pool eligibility, rarity
filters, and whether commander pools are tracked: vintage, unpowered,
legacy, modern, pauper, peasant, set, commander, pdh. See the
"Supported Cube Formats" table in the repo-root CLAUDE.md.
_Avoid_: "format" alone (ambiguous with constructed deck formats —
say "cube format" when referring to the cube ones).

**Designer intent**:
The cube author's declared shape for the cube — what archetypes it
should support, what themes it should reward, what curve it should
have. Lives at `cube.designer_intent` in the cube JSON. Tools
(archetype-audit, gauntlet, custom-format simulator) read this
field to verify the cube actually delivers what the author intended.
_Avoid_: "design goals" (too generic), "metadata" (sounds passive;
designer_intent is consumed by tools).

### The three "archetype" concepts (do not conflate)

These three concepts share the word "archetype" but model genuinely
different things. Always say which one you mean.

**Theme preset**:
A named, testable matcher for one MTG mechanic — flying, sacrifice,
counter-target, +1/+1-counters, etc. Defined in
`mtg_utils.theme_presets.PRESETS` (~80 entries), each a `Preset`
dataclass with keyword-list and/or oracle-text regex matchers. Use
`PRESETS[name].matches(card) -> bool` to test one card. The smallest
unit; consumed by stated archetypes and by gauntlet auto-inference.
_Avoid_: "theme" alone (ambiguous), "tag" (presets are matchers, not
labels).

**Stated archetype**:
A cube-level declaration of an archetype the designer intends the
cube to support. Lives at `cube.designer_intent.stated_archetypes`
as a list with three shapes:
- `{"name": "flying"}` — preset reference
- `{"name": "Aristocrats", "members": ["sacrifice", "death-trigger"]}` — group of presets
- `{"name": "Tokens", "regex": "create.*token"}` — custom regex
Resolved by `_archetype_resolver.resolve_stated_archetypes(cube)` into
a `ResolvedArchetypes` triple of `(preset_names, groups, custom)`.
The source of truth for what archetypes the gauntlet tests.
_Avoid_: "archetype" alone (ambiguous), "theme" (theme presets are
the matchers; stated archetypes USE theme presets).

**Gauntlet archetype**:
A concrete deck-build specification used by `playtest-gauntlet` to
construct a round-robin test deck. Shape:
`{name, colors, matchers, shape, curve_target}` where `matchers` is
a list of card-predicates (typically derived from a stated
archetype's theme matchers) and `shape` is an optional canonical
deck-shape prior. Auto-inferred from stated_archetypes by default;
the cube author can override per-archetype via an optional
`gauntlet:` block on the stated_archetype entry, or replace the
whole manifest via `--gauntlet path/to/manifest.json`.
_Avoid_: "archetype deck" (the spec, not the resulting deck), the
old `cube.gauntlet_archetypes` field name (hard-deleted).

### Scoring concepts

**Shape**:
A canonical deck-shape prior — one of `aggro | midrange | control |
combo`. Adds the historical hardcoded `score_card` priors
(2-power-2-CMC creatures rewarded for aggro, counter-target rewarded
for control, etc.) on top of any theme-match scoring. Optional;
omit for pure theme-driven scoring.
_Avoid_: "preset" (the field was named that originally; it's now
`shape` to disambiguate from theme presets), "strategy" (close, but
"shape" is the term in the code).

**Score**:
A fitness score for a card given an archetype's matchers and shape.
Each matching theme adds `+3.0`; the shape prior adds canonical
hardcoded weights. Off-color cards return -1.0 (deprioritized but
not eliminated, since the deck builder needs backfill). Lands return
0.0. Only the relative ordering matters — magnitudes are internal.
_Avoid_: "fit", "rating".

### Workflow concepts

**Tuning pipeline**:
The 10-step cube tuning workflow defined in cube-wizard SKILL.md:
baseline metrics → designer intent → balance dashboard → archetype
audit → power-level review → self-grill → propose changes → pack
simulation → export → optional empirical playtest.
_Avoid_: "process" (too vague).

**Hydrated cube**:
The cube JSON joined with full Scryfall card data (oracle text,
type lines, color identity, prices, etc.) — produced by
`download-bulk` + the cube-wizard's hydration step. Required input
for any tool that needs to inspect card text, like archetype-audit
or playtest-gauntlet.
_Avoid_: "expanded", "enriched".

## Relationships

- A **Cube** has zero or more **Stated archetypes**, declared by the
  designer.
- A **Stated archetype** is composed of one or more **Theme presets**
  (or a custom regex matcher).
- A **Gauntlet archetype** is auto-derived from a **Stated archetype**
  (its name + matchers) and optionally augmented with explicit
  `colors`, `curve_target`, and `shape` from a `gauntlet:` override
  block.
- A **Theme preset** is a single-purpose matcher; multiple stated
  archetypes can reference the same preset.
- The **Hydrated cube** is what every tool except parsing consumes;
  it's the join of the cube JSON with Scryfall card data.

## Example dialogue

> **Dev:** "I want the gauntlet to test my Aristocrats archetype. Where do I declare it?"
> **Domain expert:** "Add a **Stated archetype** to `cube.designer_intent.stated_archetypes`. For Aristocrats you'd write a group: `{name: 'Aristocrats', members: ['sacrifice', 'death-trigger']}` — those are **Theme preset** names. The gauntlet will auto-infer the **Colors** (probably BW from your cube's actual sacrifice/death-trigger card density) and the **Curve target** (from those cards' CMC distribution). If the inference picks weird colors, override with a `gauntlet:` block on the stated_archetype entry."

> **Dev:** "Why is there both a 'theme preset' and a 'stated archetype' — aren't they the same thing?"
> **Domain expert:** "**Theme presets** are atoms — one name, one matcher. **Stated archetypes** compose them. 'flying' is a preset; 'Skies tribal' might be a stated archetype with members `['flying', 'spirit']`. You can also have a stated archetype that's just one preset (`{name: 'flying'}`) — that's fine, it's a 1-element composition."

## Flagged ambiguities

- **"archetype"** alone is ambiguous between **Stated archetype** and
  **Gauntlet archetype**. They're related (gauntlet is derived from
  stated) but distinct. Use the precise term. The third meaning —
  the drafter's per-pile choice — is also called "archetype" in
  prose; pin it as "drafter archetype choice" if that distinction
  matters.
- **"preset"** used to mean two things: (1) a **Theme preset** in
  `theme_presets.PRESETS`, and (2) the canonical scoring strategy
  (`aggro|midrange|control|combo`). The second is now called
  **Shape**. The `preset` field on gauntlet archetype manifests was
  renamed to `shape` in 2026-05; do not reintroduce that overload.
- **"format"** in this context is a **Cube format**
  (vintage/modern/pauper/etc.), not a constructed deck format
  (standard/modern/legacy). When both are in scope (e.g., a cube
  tuned for a constructed format), say "cube format" and "deck
  format" explicitly.
