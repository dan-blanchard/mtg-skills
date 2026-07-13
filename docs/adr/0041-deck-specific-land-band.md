# A deck-specific land band replaces the static lands row and the raw-Burgess gate

One tune result on the Sliver Weftwinder benchmark (2026-07-13) emitted three
contradictory land verdicts at once: the static template row said lands **over** (40 vs
36-38), the mana gate said **FAIL** (40 below the raw Burgess floor, 31 + 5 colors +
CMC-5 commander = 41), and the swaps note said "~5 lands short" (a separate `_fill_gap`
bug: it re-joins class records to deck entries by exact name, dropping DFC lands whose
deck entries carry front-face names — 4 lands lost here). The first two are
*structurally* irreconcilable for high-color / high-CMC commanders: the raw Burgess
floor (41) exceeds the static band's max (38), so no land count can satisfy both. The
mana section already computed the Karsten ramp adjustment (38 with 12 ramp) and then
ignored it for the verdict.

**Decision.** Derive ONE deck-specific land band — **[Karsten-adjusted floor, raw
Burgess]** ([38, 41] for the benchmark deck) — and point every surface at it: the
scorecard's template lands row (replacing the static 36-38), the mana section's
verdict, and the swaps note. The **hard gate FAILs only below the Karsten-adjusted
floor**; raw Burgess becomes the band's top, a comfortable-maximum reference rather
than a failure line. Ramp count and commander cost are exactly the deck-specific facts
the static band ignored.

**Consequences.** `mana-audit`'s FAIL softens (a 40-land / 12-ramp / 5-color deck goes
FAIL → PASS), and deck-wizard's "FAIL means you must add lands" hard gate inherits the
Karsten floor — accepted deliberately: every layer of the benchmark (deterministic
scorecard's own Karsten number, agent review, user judgment) agreed 40 was right and
the old gate would have forced a 41st land. Tests pinning the raw-Burgess FAIL re-pin.
The `_fill_gap` DFC name-join fix rides along as a plain bug fix (join on the same
front-face aliasing `hydrate`/`mark-owned` already use, or sum land quantities from
the classified records directly).
