# The goldfish model is its own module, and the hub calls the command's result-builder

`playtest.py` held six Click commands and the goldfish simulator in 1,486 lines. The
2026-09-17 architecture review flagged its mode functions as worth exploring. A
survey found two problems. The commands repeated the same blocks: the output tail
five times, the cube loading and the stated-archetype read twice each, the phase
error handling and coverage refusal in both match and gauntlet, and the same click
options on several commands. And deck-forge's goldfish handoff
(`_deck_forge/engine.py`, ADR-0016) carried its own copy of `goldfish_main`'s
result-building code. That copy had drifted: it dropped the unresolved-fetch warning
and computed the missing cards with a different expression.

**Decision** (Dan, 2026-11-27):

1. **Extract the simulator and remove the duplication.** The goldfish model moves,
   verbatim, to `mtg_utils/_goldfish.py`: the mana model, the mulligan, the game
   loop, the aggregate, `GOLDFISH_VERSION`, and `goldfish_envelope`, the one
   function that builds the envelope's results, coverage and warnings. The six
   commands **stay in `playtest.py`**, shorter, over small shared helpers: the click
   option factories, `_load_cube`, `_stated_archetypes`, and the phase-run path that
   match and gauntlet share (`_run_duel` reports an engine failure as a
   `ClickException`, `_refuse_if_blocked` exits 2 on a blocked coverage gate,
   `_phase_envelope`, `_first_five`). `_playtest_common.emit` is the one output tail,
   and `_phase.is_phase_native` replaces match's inline copy of the phase-shape
   check.
   **Not** one module per mode.
2. **The hub calls the command's function.** `engine.goldfish_report` calls
   `goldfish_envelope`, so the goldfish panel reports what `playtest-goldfish`
   reports. This is the one intended behaviour change. A deck whose generic land
   fetches the model cannot resolve (no coloured basics) now carries the command's
   warning in the panel. Dan asked to see the difference on real decks before it
   landed (`~/mtg/playtest-refactor/hub-diff.md`, four decks). The colourless
   Omnath list and the Eldrazi Unbound precon gain the warning. Fynn, and a 60-card
   list with a misspelt card, are unchanged. The missing-card list is the same on
   every deck, and has to be: both expressions take the main-deck names that
   `hd.by_name` cannot join.

**What stays the same.** The command side changes no behaviour, and this was checked
by a re-runnable capture (`~/mtg/playtest-refactor/capture.py`, 69 cases, before
and after byte-identical; the base run was a scratch copy of the tree at b56f0295). It covers goldfish on six real decks (two seeds each, a
long run, a mulligan-heavy short run), draft and custom-format on a real cube, every
command's `--help`, two error cases per command, a real phase match and gauntlet,
and match / gauntlet through recording stubs of `_phase.run_duel` /
`_phase.coverage_report` on every branch. The stubs record the arguments, the deck
files written, the results, warnings, exit codes and stderr. Kept on purpose:

- The RNG call order. The model moved verbatim. The mulligan shuffle now calls
  `_build_indexed_deck`, which returns the same `list(range(n))`, so the RNG sees
  the same list.
- Every seed formula (gauntlet's `seed + i * 100 + j`, draft's `seed + pod * 1000`
  and `pod_seed + player`), custom-format's dict insertion order, every message and
  every output key order.
- The gauntlet has no `--force`: a blocked gate always refuses there.
- The coverage and timeout warnings keep their own wording per command. They share
  `_first_five`, not one message.
- `_phase` is read at call time (`from mtg_utils import _phase`, then
  `_phase.run_duel(...)`), so a test's patch of `mtg_utils._phase.run_duel` applies.
- The gauntlet's phase decks stay the inline `{name, format, main}` dict, the format
  written as the manifest gives it, less `_cube`. `_phase.to_phase_deck` would turn
  an empty format (`""`, or `"_cube"`) into `"modern"`. Phase plays a deck with
  `"format": ""` normally, so that would have been a change. Two capture cases
  cover it: a stated-archetype cube with `"format": ""` and a manifest with
  `"_cube"`.

**Pinned by tests.** Seeded golden runs guard the model and the custom-format path:
`test_playtest_goldfish.py::TestGoldfishGolden` (a 60-card real-card deck through
`--bulk-data`, two seeds, the full `results`) and
`test_playtest_custom_format.py::test_seeded_run_is_pinned`. Unit tests cover the
helpers (`test_playtest_helpers.py`), and a hub-parity test checks that the panel's
report equals `goldfish_envelope`'s.

**A bug fix beside it.** `playtest-draft` was not reproducible across processes for
a fixed `--seed`. A pile's colour counts were keyed off a set, so a tie broke by set
order, and `PYTHONHASHSEED` changes that per process. Ties now break in WUBRG order,
a separate commit from the refactor. A seed with no tie gives the same results as
before; the real cube's two captured seeds are unchanged. A subprocess test runs
the same draft under two hash seeds, and a golden test pins it.

**What this stops re-suggesting.** Splitting `playtest.py` into one module per
mode. A second goldfish result-builder: a new caller calls `goldfish_envelope`.
