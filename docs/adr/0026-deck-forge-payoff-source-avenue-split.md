# deck-forge splits fused payoff/source specs into separate avenues

A `<mechanic>_matters` avenue should surface the deck's **payoffs/enablers** ("this
deck wants to suit up") separately from its **sources** ("the auras & equipment to
suit up with"), because fusing both into one avenue hides the balance a builder needs
to read — "6 pieces, 1 payoff" is invisible in a single ✦-list. We decided the engine
**systematically** derives two avenues from any spec whose `serve` carries a type or
keyword dimension: a **payoff/enabler avenue** from `serve.oracle`, and a **Source
avenue** from `serve.types`/`serve.keywords` (plus the `serve_not` veto). This is the
static-membership analogue of what `_subject_spec` already does for tribes (a
`type_matters:Goblin` signal already fans into "Goblin tribal" bodies / "Goblin
payoffs" / "Goblin enablers"); ~46 fused non-subject specs (voltron, artifacts_matter,
spellcast_matters, …) are brought into line with that established split. See the
**Payoff avenue / Source avenue** entry in `deck-forge/CONTEXT.md`.

## Considered options

- **Hand-authored `SubAvenue` per spec** — rejected: the split is the same mechanical
  operation every time (oracle→payoff, types/keywords→source) over ~46 specs; 46
  bespoke definitions would be pure duplication that drifts.
- **Additive (keep pieces in the payoff avenue too, add a Source avenue alongside)** —
  rejected: the payoff avenue's count would still mix pieces + payoffs, so the
  imbalance stays unreadable — defeating the only reason for the split.
- **A new `signals.py` detector for membership sources** (e.g. firing on
  `EnchantedBy`/`EquippedBy`) — rejected: an aura/equipment is identified by *type
  membership*, not a signal it emits; routing it through a detector floods the payoff
  lane (≈3.5k of 3.6k such cards are the serve pool, not build-arounds). Sources are
  served by type, never detected.

## Consequences

- A small **denylist of modifier keywords** (haste, indestructible, trample, the
  evasion set) keeps a property keyword from spawning a junk "pool" lane — that
  denylist is where the judgment lives.
- **Two source flavors stay distinct**: a *membership* source (you ARE the thing →
  type/keyword serve, auto-derived here) vs an *effect* source (you MAKE the thing → a
  detector signal such as `token_maker`, which is subject-keyed and correctly remains
  its own lane). They are not unified.
- `focus-all` still OR-combines both lanes, reproducing the pre-split fused list, so
  ADR-0015's serendipity is preserved.
- Reshapes the avenue surface for ~46 specs at once, so the rollout is validated on
  voltron + a few clean pools before flipping on globally.
