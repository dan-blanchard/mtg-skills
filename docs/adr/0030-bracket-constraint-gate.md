# A target-bracket constraint gate in the shared tuner (orthogonal to the role template)

deck-wizard tunes by power bracket; ADR-0024 deliberately rejected bracket-scaled *role
bands* (interaction floors that rise with bracket) as contested false precision, keeping
role density **Shape**-scaled. But WotC's official Commander Bracket system gates
specific deck-construction *elements* by bracket — a **permission** axis orthogonal to
role density. We want the tuner bracket-aware along *that* axis.

**Decision.** Add a **bracket-constraint gate** to the shared `tune()`, parameterized by
a *target* bracket (1-5), separate from and additive to the Shape-scaled role bands
(`Template deviation`). Input: `target_bracket`. Output: `{target_bracket, pass,
ceilings, violations: [{axis, severity: FAIL|WARN, cards, detail}]}`. Four axes, verified
against the WotC "Commander Brackets Beta Update" (most recent official version
2026-02-09):

| Axis | B1 Exhibition | B2 Core | B3 Upgraded | B4 Optimized / B5 cEDH |
|---|---|---|---|---|
| Game Changers (count) | 0 | 0 | ≤ 3 | unlimited |
| Mass land denial | none | none | none | allowed |
| Extra-turn cards | none | low qty, no chain/loop | low qty, no chain/loop | allowed |
| Two-card infinite combo | none | none | only if not cheap-&-early (~turn 6) | allowed |

- **Game Changers** and **mass land denial** are crisp/deterministic — reuse
  `deck_stats.detect_bracket`'s existing detection (the `game_changer` Scryfall flag; the
  mass-land-denial regex). The Game-Changers list is **pulled from Scryfall's
  `game_changer` bulk field, never hardcoded** — it is a moving target (40 cards at
  launch → 53 as of 2026-02-09) that auto-updates with each bulk refresh.
- **Extra-turn cards** (new detector) and the **B3 "cheap-&-early" combo** test are
  *qualitative in the official text* — encoded as project-chosen heuristics flagged
  **WARN, not FAIL** (e.g. extra-turn count over a low cap or an extra-turn + recursion
  loop; combined-mana-value / earliest-assembly-turn vs the ~turn-6 anchor), and labeled
  as heuristic, never asserted as an official number.
- **Brackets 4 and 5 short-circuit to PASS** (banned-list only; nothing to enforce).
- **No tutor axis** — WotC removed tutor restrictions on 2025-10-21; the most efficient
  tutors are now caught only via their Game-Changers membership.
- The swap proposer **respects the ceiling** (won't propose a Game-Changer add that
  breaches the target).
- deck-wizard's bracket interaction-*target* table (Command Zone Ep. 658: 5-7 / 8-10 /
  10-12) stays an **agent-layer overlay**, never tuner role floors — that boundary is
  the ADR-0024 line.

**Why this is the right call.** This is an *official published ruleset*, not a contested
community fork, so encoding it is legitimate where bracket-scaled role bands were not.
It is orthogonal to role density, so ADR-0024 stands unchanged. deck-forge already
detects the raw signals (`detect_bracket` surfaces `game_changers` / `mass_land_denial`
/ `fast_curve`), so the gate is mostly a comparison-against-a-chosen-target layer — cheap
to add, and both consumers benefit. The crisp/soft split keeps it honest: the two
deterministic axes are exact; the two qualitative ones warn rather than inventing
precision the source does not give.

**Known caveats.** The system is officially **beta** — the next update is expected
~May/June 2026 (unpublished as of 2026-06-27). Keep the Game-Changers list re-fetchable
(Scryfall flag via bulk) and the bracket rules in one editable table stamped "verified
2026-02-09," not frozen. Brackets 1 and 2 are nearly indistinguishable mechanically
(both cap Game Changers at 0, both ban mass land denial and two-card combos) — only the
extra-turn rule and non-mechanical intent separate them; the gate enforces the former and
cannot see the latter.

**What this stops re-suggesting.** Don't fold bracket into the role-density bands — that
is ADR-0024's deliberately-rejected path; bracket is a *permission* gate, not a *density*
scale. Don't hardcode the Game-Changers list (it is a moving, Scryfall-tagged target).
Don't promote the soft WARN axes (extra-turn "low quantity," B3 "cheap-&-early") to hard
FAIL with invented numeric thresholds — the official text is qualitative there. Don't
re-add a tutor axis (WotC removed it 2025-10-21).
