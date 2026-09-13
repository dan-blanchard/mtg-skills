# The bridge ledger owns bridge emission: a bridge is one row

ADR-0039 made every text bridge a ledger row (gap, match, census, retirement path,
pins) but left its *emission* in the lanes: 28 sites across ten lane modules named a
bridge id as a literal and restated the key and scope the row already carried
(`if bridge_fires("zuko_modal_unconditional_paylife", tree): fire("you", "")`). So
"which bridges serve key K" had no answer short of grepping, retiring a bridge was a
two-file edit whose lane half could be forgotten, and two lanes existed only to host a
bridge call. The 2026-09-12 architecture review listed this as a Strong candidate.

**Decision.** The row owns its emission. `Bridge` gains `scope` (default `"you"`) and
`quote_oracle` (carry the card's oracle text as `Signal.text`, for the two rows that
did); `Bridge.signal(tree)` builds `Signal(key, scope, "", text, card, "high")`. One
generic lane, `bridge_ledger.bridge_signals`, registered last in `lanes._LANES`, fires
every row and emits its signal; the crosswalk's per-lane dedupe by (key, scope, subject)
folds a bridge signal into a structural read of the same ident, which is what the two
`if key not in seen` guards did by hand. The 28 call sites are deleted, along with the
two lanes (`_combat_choice_makers`, `_named_synergy`) that were only a bridge call.
`bridges_for(key)` answers the review's question. The convergence test gains two
hygiene checks: every row's key is a served key with a valid scope, and no file under
`lanes/` contains a bridge id literal, so retirement stays a one-file edit. The
full-snapshot corpus dump is byte-identical before and after.

**Considered and rejected.** A by-key index alone (answers the question, leaves the
two-file retirement); a per-row `only_if` hook to preserve the two dedupe guards
exactly (a second gate concept beside `gap`, doing what the dedupe already does).
