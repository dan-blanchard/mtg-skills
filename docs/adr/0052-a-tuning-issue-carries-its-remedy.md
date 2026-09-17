# A tuning issue carries its remedy; the tuner asks the Format what the medium means

The tuner's diagnosis (`metrics.top_issues`) emitted untyped dicts with nine `kind`
strings, and the swap engine re-decided what each kind meant in four separate places:
which search it gets (`_spec_for_issue`), which cut pool pays (`take_cut`), whether it
ranks efficiency-first (`_SPINE_KINDS`), whether one issue makes many swaps (a
`dead_weight` branch). "Is this issue actionable, and how?" had no owner. The swap engine
has three sourcing paths — the issue loop, the dead-weight drain, the under-sized-deck
fill — and a rule added on one was forgotten on another: `grant_covered` (ADR-0040 §1)
was written once and gated in five places, one of them commented "a THIRD sourcing path
the #98 advisory downgrade missed"; five consecutive review-round commits (1d05e83e →
2d5a791a) each closed a decision re-derived or forgotten on one path, the last solely to
correct comments claiming the `advisory` flag was a switch when nothing read it.

**Decision.** `_tuner/issues.py` owns the issue. An `Issue` is a typed value that
carries a `Remedy` — the add's search spec, the cut pool that pays for it, whether it is
a Spine fill (efficiency-first under the ADR-0040 role-fix guard), whether it drains —
or `None`: nothing to source, the issue is the builder's to read. `Sourcing`, built
from the focus result, the deck's signals and the slot budgets, is the one place that
decision is made: `remedy_for(kind, …)` for an issue, `role_spec(role)` for the fill
pass. `role_spec` is the single Grant-covered gate — the issue loop, the dead-weight
redeploy and the fill pass all read it. `propose_swaps` reads `issue.remedy` and has no
kind switch. `advisory` stays what it always was, a label on the wire for readers; the
engine reads `remedy`. The scorecard's JSON is unchanged (`Issue.to_json`).

The low-value read (a weak Granter, else a fringe play-rate) was copied into the Focus
metric and the cut ranking; it is `CardClass.low_value` now.

**The medium.** `TuneParams` asked each caller to pre-derive three facts from the format
and medium — `paper_only`, and which of `budget` / `wildcard_budget` applies — and the two
adapters disagreed: `deck-tune` derived `paper_only` from the medium, the hub from
`is_arena`, so the same paper Historic Brawl deck searched different card pools. Now a
caller passes the medium and both purses; `tune` asks the Format (ADR-0045):
`Format.paper_only(medium)` and `Format.cost_mode`. The rule follows the **medium** — a
paper Historic Brawl table buys paper printings in USD; the Arena-pool gate is separate,
medium-independent, and applied by `Format.legality` either way. The hub's Find reads
the same method, for the build's own format and medium (a Find format filter narrows
legality, not the pool). `TuneParams.medium` defaults to `None` — the Format's default
medium — where it used to default to `"paper"`, and `paper_only` survives only as an
explicit override (`--paper-only`); `deck-tune` still resolves the medium, but only to
tell the user which one it inferred. `deck-tune` gains `--wildcards` (a digital build never spent USD
coherently; `--budget` is now ignored there, with a note).

**Considered and rejected.** Deriving `advisory` from `remedy is None` (a short `lands`
row sources nothing here — it is Balance Lands' job — but is anything but advisory).
Resolving remedies inside the swap engine from a typed kind enum (keeps the decision on
the action side, where the three paths already diverged). Storing `low_value` on
`CardClass` at classification time (it is medium-dependent, and `classify_deck` is
medium-free).
