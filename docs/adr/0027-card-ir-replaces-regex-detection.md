# deck-forge replaces its regex detection bag with the Card IR

deck-forge's signal detection runs a large bag of oracle-text regexes/substrings
(`_DETECTORS` / `_FLOOR_DETECTORS` / `SWEEP_DETECTORS`, ~260 `re.*` calls in
`signals.py`) that can detect *that* a card does something but bind neither the
operand it scales with (the Y in "for each Y you control") nor the scope (whose
graveyard, whose creatures), and that over- and under-fire in ways invisible
without per-card adjudication. We decided to replace it with a structured **Card
IR** projected from phase-rs's parser (`card_ir.py` + `_card_ir/`) and to
**delete the regex detectors entirely** — not keep them as a fallback or a
permanent second opinion. The migration is an **incremental strangler**: a
`MIGRATED_KEYS` manifest + `extract_signals_hybrid` ship behavior-neutral (empty
manifest → identical to today), then each Signal key is moved to the IR and its
regex detector deleted once it passes a per-key gate. The gate is **adjudicated
correctness, not regex parity** — regex output is a known-flawed oracle, so the
diff harness (`signal_diff.py`) is a *worklist and fixture generator*, never the
bar; each IR-vs-regex disagreement is adjudicated with **rules-lawyer against the
actual Scryfall oracle text + CR** (the Iron Law — never card-name memory, never
the regex's say-so), and the verdicts accrete as fixtures that *are* the
regression-proof ground truth. Scope (Milestone A) is deck-forge's **runtime
closure**: `signals.py` detectors plus the `theme_presets` regex-*patterns* and
`card_classify` oracle-regex deck-forge calls, while keeping the structured
survivors (`theme_presets` keyword-arrays, `card_classify` `type_line` checks);
`theme_presets`' other consumers and repo-wide `card_classify` are Milestone C.
North star: an agent-less deck-forge, **staged** — an intermediary where
detection is fully deterministic (`coverage_gate → ~0`) and the Session-agent is
retained to tune the detectors and collaborate, then complete removal gated on a
*measured creative-novelty delta*, never a date.

## Considered options

- **Keep regex as a permanent fallback / second opinion** (status quo: two
  parallel paths, production on regex) — rejected: it is the trap we are already
  in — double maintenance, neither path fully trusted, and the regex brittleness
  that motivated the IR never actually goes away. The IR is now ~100% parse over
  commander-legal cards, which removes the only honest reason to keep regex.
- **Big-bang cutover** (hold both paths until every key reaches IR parity, then
  flip + delete in one commit) — rejected: it defers all risk to one commit,
  wastes the diff harness as a per-key gate, and — having spent dozens of
  sessions perfecting the parse without ever flipping production — invites "one
  more batch" indefinitely. The strangler forces production onto the IR
  immediately and makes every subsequent step a *deletion*, not an *addition*.
- **Freeze the regex output as the parity gate** (the original A4 instruction) —
  rejected: regex over- and under-fires (`graveyard_matters` fires on any
  "graveyard" substring → ~2.9k regex-only firings; `self_death_payoff` misses
  Festering-Goblin-class cards → ~750 IR-only firings). A regex-parity gate would
  lock in the over-fires and forbid the recall wins — exactly backwards. The gate
  is adjudicated correctness; secondary oracles (Scryfall Tagger, EDHREC
  known-lanes, `phase_crosscheck`) triage the worklist but never render the
  verdict.
- **Remove the agent immediately** (the plan's literal Milestone B) — rejected as
  written: it contradicts the settled interactive-collaborator identity
  (ADR-0009/0010), guts the human-in-the-loop UX, and solves a hallucination risk
  ADR-0009 already neutralized (the agent never names cards). Staged instead, with
  the session used to *perfect the detectors that retire it*.

## Consequences

- **phase-rs becomes a core dependency.** Detection now requires the
  phase-projected Card IR sidecar; `build-card-ir` wires into deck-forge
  first-run alongside `download-bulk`. Previously phase was needed only for the
  optional playtest.
- **`phase_crosscheck`'s "never ground truth" stance is reframed for the
  *projection* layer only.** Phase's parse stays a *second opinion* for the
  crosscheck audit, but its structural IR is now the *substrate* deck-forge's
  detection is projected from — a deliberate, projection-scoped reversal that does
  not touch the crosscheck's adversarial role.
- **The fixture set is the new golden artifact.** It grows from adjudicated
  disagreements and is regression-proof; "how close are we" is measured in
  *deleted detectors*, not slice size.
- **A hybrid production window.** Until the strangler completes, production serves
  some lanes from the IR and some from regex; the empty-manifest start keeps the
  Key-agreement gate (ADR-0014) satisfied throughout, and a validated hybrid is
  never worse than today's all-regex.
- **`ranking.py` / `budgets.py` migrate after** the signal strangler (they consume
  the unchanged `Signal` contract, so they are source-agnostic during it). **A4** —
  deleting the now-empty detector bag, wiring first-run, pointing `coverage_gate`
  at `ir.parse_confidence` — is a falls-out cleanup, not a separate cutover.
- **A small kept-detector tail survives A4**: genuinely-narrow mechanics phase
  does not structure (voting, bending, snow, miracle, …) keep their word-level
  keyword detectors (`_IR_KEPT_DETECTORS`), each rules-lawyer-verified before being
  classified "kept" rather than "migrated" (the "skip" label was repeatedly wrong).
- **A future ADR-0009 amendment** records the agent's retirement from the
  detection-fallback role once the intermediary's `coverage_gate → ~0` lands;
  ADR-0010's interactive-billing decision is untouched. Final agent removal also
  requires closing the *creative-novelty* (Gate 2) delta — promoting any pattern
  the session dreams that `signal_specs` lacks into the deterministic core — which
  is measured during the intermediary, not assumed.

## Status (2026-07-12): strangler completed via ADR-0035/0039

The migration this ADR started finished under a changed substrate: the lossy
projection it named was replaced by the ADR-0035 phase-mirror + concept
overlay, and ADR-0039 then deleted the legacy path entirely (regex serving,
the projected-Card path, `project.py`, `build-card-ir`). The regex byte-mirror
safety-net era is over — the mirrors were the transitional tactic, not the
goal — and the surviving text reads are the enumerated, gap-gated ledgered
bridges of `bridge_ledger.py`. The real-card fixture regime this ADR's
adjudication discipline produced lives on: fixtures now serve through the
crosswalk snapshot (`card_snapshot.json` schema 2, raw phase face records;
`testkit` builds real concept trees in CI). The Iron-Law adjudication rules
and the staged agent-retirement north star still stand.
