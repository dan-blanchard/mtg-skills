# Fully-parsed Card IR is a pull-based, measured direction — not a push-to-completion

We want the Card IR (ADR-0027) to trend toward *fully parsed* — every clause structured,
not just the synergy-relevant ones — because it will be useful later even though nothing
consumes the full depth today. But "useful later, unused now" is the shape of speculative
over-investment, so we **do not push to completion**. Instead:

**The consumers we are building for** (these define "done"): (1) **new synergy lanes as
cheap derived queries** over the IR — adding a lane is "filter the IR," not "write a regex
+ adjudicate"; (2) **validation / drift detection** — a measurable completeness surface
that trips when a projection change regresses parse coverage. A **card-behavior substrate**
(a "what does this card do" explainer / rules-lawyer ground truth) is a welcome by-product,
not a target. Feeding **phase's own engine** stays open as a future possibility, but only
via **Reading 1** — contributing our parse-gap fills *upstream into phase-rs's grammar*
(ADR-0028), where phase's engine executes them — **never** by making our IR itself
engine-consumable (Reading 2: an execution-faithful, losslessly round-trippable IR is a
non-goal nice-to-have, because it re-imports most of the cost of a rules engine through
the back door). **We are not building our own rules engine.**

**Pacing is pull, not push.** Three standing commitments, no completion sprint: (a)
IR-read is the default for all new work — a new lane reads the node, never a fresh regex
(the ADR-0027 posture), so each lane *pulls* exactly the fields it needs into "fully
parsed" and gates them against real lane membership as they land (the regime that is
reliable; structural-only adjudication with no membership signal is the regime that is
not); (b) a **measured completeness surface** makes the future value concrete and
self-defending today; (c) the **parser-substrate** (recoveries rewritten as `_combinators`
that mirror phase's nom grammar) advances opportunistically as the feed-phase enabler, not
in a dedicated sprint.

**Two metrics, committed, because the two consumers want different cuts of the fidelity
ladder** (native node read > combinator recovery > regex recovery for a genuine gap >
regex recovery that *masks* a node phase actually has):

- **Synergy-completeness (primary, regression-tripping).** `parse_confidence` full-% plus
  field-coverage (count of triggers at `event="other"`, `Unimplemented` nodes,
  `category="other"` clauses). **Any** structure counts — a regex-recovered card *is*
  parsed for synergy. This is the drift detector that would have caught this work's −9
  `parse_confidence` flip.
- **Feed-phase-readiness (secondary, direction-tracking).** The mirror/recovery inventory
  promoted to a committed count of raw-regex recoveries remaining, split **bucket-A
  (masking a node phase has → is DEBT, must become a native read)** vs **bucket-B (a
  genuine phase gap → combinator-ize later)**. Bucket-A masking is debt *even though it
  produces valid structure* — it hides a node we should be reading.

**The metric trips two ways (option C), because CI can't see the full corpus** (it is
network-free off the committed ~717-card snapshot, not the 34k-card `card-data.json`): a
committed full-corpus `parse_metrics.json` — regenerated in the same gated step that builds
the IR sidecar / `card_snapshot.json`, holding *both* metrics' numbers — is the
authoritative surface and the review-time drift-watch (a regression shows as a diff in a
committed file); and a CI assertion computes the field-coverage numbers over the committed
717-card snapshot as the cheap automated guard. The committed file is the truth + the
human watch; the snapshot test is the auto-tripwire. Neither alone suffices (A relies on
someone noticing the diff; B is blind to anything off the biased, usage-derived 717).

## Considered options

- **Push to completion now** — proactively structure the whole tail (map every trigger
  mode, every modal/granted/Saga clause, drive `parse_confidence` → 100%). Rejected: pays
  full price up front for a payoff that arrives only when a consumer does, and forces
  fidelity to be adjudicated structurally with no membership signal — the least reliable
  regime.
- **Do nothing / leave it implicit** — keep improving the IR ad hoc with no committed
  metric. Rejected: "useful in the future" stays an unfalsifiable intention, and silent
  regressions (the −9) keep hiding.
- **One blended metric** — fold feed-phase-readiness into parse_confidence. Rejected:
  either understates synergy-completeness (penalizing working regex recoveries) or lets
  bucket-A masking hide as "done."
- **Make the IR engine-consumable (Reading 2)** — design for round-trip into phase's
  engine. Rejected as a *goal* (kept as a non-goal nice-to-have): it forecloses the lossy,
  synergy-shaped normalization the actual consumers want and re-imports rules-engine cost.

## Consequences

- The near-term deliverable is the **`parse_metrics.json` metric + snapshot assertion**,
  not a parse-completeness sprint. Building the metric *is* the investment that makes the
  direction real and cheap.
- Closing the trigger-mode-to-`event="other"` tail and the 1.6% partial tail becomes
  *pull-driven*: worth doing when a lane (or the feed-phase track) needs the field, tracked
  as a number meanwhile — not a standalone push.
- Bucket-A regex masking is now first-class debt with a committed count, so the kind of
  drift this work fixed (doublers/votes/clone re-derived from text while phase had the
  node) can't silently re-accumulate.
- The upstream-to-phase contribution path (ADR-0028, the 6 documented gap classes) is the
  *only* sanctioned "feed phase" mechanism; any future engine-consumability is explicitly
  out of the committed scope.

## Status (2026-07-12): parse metrics retired with the legacy builder

`parse_metrics.json` and `compute_parse_metrics` measured the *legacy
projection's* own bookkeeping (`parse_confidence`, the recovery footprint, the
bucket-A/B masking split) and died with that builder in ADR-0039 step 7
(commit 779a64ff) — there is no truthful crosswalk-level equivalent, because
the lossless substrate retains every phase field by construction (ADR-0035),
which discharges the bucket-A debt this ADR named. The substrate-level
drift-watch survives as the committed `phase_variant_population.json`
(per-variant node counts over phase's raw discriminator tags — catches a node
relocating between two both-valid variants that strict-load can't see). The
pull-based posture itself stands: a new lane reads the node, never a fresh
regex.
