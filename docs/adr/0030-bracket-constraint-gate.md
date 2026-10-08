# A target-bracket constraint gate in the shared tuner (orthogonal to the role template)

deck-wizard tunes by power bracket; ADR-0024 deliberately rejected bracket-scaled *role
bands* (interaction floors that rise with bracket) as contested false precision, keeping
role density **Shape**-scaled. But WotC's official Commander Bracket system gates
specific deck-construction *elements* by bracket — a **permission** axis orthogonal to
role density. We want the tuner bracket-aware along *that* axis.

**Decision.** Add a **bracket-constraint gate** to the shared `tune()`, parameterized by
a *target* bracket (1-5), separate from and additive to the Shape-scaled role bands
(`Template deviation`). Input: `target_bracket`. Output: `{target_bracket, pass,
ceilings, violations: [{axis, severity: FAIL|WARN, cards, detail}]}`. The brackets are
WotC's system for multiplayer Commander, so for a one-on-one **Game** (`Format.game`
under the build's medium: every Arena game, Competitive Brawl) the gate passes with a
`not_applicable` reason instead of measuring pod permissions against a duel. Four axes, verified
against the WotC "Commander Brackets Beta Update" (most recent official version
2026-02-09):

| Axis | B1 Exhibition | B2 Core | B3 Upgraded | B4 Optimized / B5 cEDH |
|---|---|---|---|---|
| Game Changers (count) | 0 | 0 | ≤ 3 | unlimited |
| Mass land denial | none | none | none | allowed |
| Extra-turn cards | none | low qty, no chain/loop | low qty, no chain/loop | allowed |
| Two-card infinite combo | none | none | only if not cheap-&-early (~turn 6) | allowed |

- **Game Changers** and **mass land denial** are crisp/deterministic — reuse
  `deck_stats.detect_bracket`'s existing detection (the `game_changer` Scryfall flag;
  the mass-land-denial read). The Game-Changers list is **pulled from Scryfall's
  `game_changer` bulk field, never hardcoded** — it is a moving target (40 cards at
  launch → 53 as of 2026-02-09) that auto-updates with each bulk refresh.
- **Mass land denial** follows Wizards' definition (Introducing Commander Brackets,
  <https://magic.wizards.com/en/news/announcements/introducing-commander-brackets-beta>,
  re-checked 2026-10-07): *"cards that regularly destroy, exile, and bounce other
  lands, keep lands tapped, or change what mana is produced by four or more lands per
  player without replacing them"* (examples: Armageddon, Ruination, Sunder, Winter
  Orb, Blood Moon). The `mass_land_denial` signal key (`crosswalk.reads.mass_land_denial`,
  the `mass-land-denial` preset) reads it off phase's trees in
  four shapes (the subject, `crosswalk.LAND_DENIAL_KINDS`): a destroy / exile /
  bounce over lands as a class, not only your own (Armageddon, Ruination, Sunder,
  Boil, Ajani Vengeant's −7, Apocalypse's and Upheaval's every permanent); a
  sacrifice of four or more lands each, or of a growing number (Wildfire, Death
  Cloud, Cataclysm, Restore Balance); an untap lock (Winter Orb, Static Orb, Back to
  Basics, Choke, Stasis); a mana change (Blood Moon, Contamination). Project calls
  inside that definition: a one-land edict is out (Yawning Fissure, Tremble), as are
  three lands each (Ember Swallower) and Pox's third (four only at ten lands); a
  sweep its own ability gives back is "replacing them" (From the Ashes, Wave of
  Vitriol), but Fall of the Thran's two-per-chapter return on later turns is not;
  "regularly" means lasting, so one untap step (Exhaustion, Mana Vapors) or one
  turn (Nightcreep) is out; four lands of one target opponent counts (Burning of
  Xinye, Ajani Vengeant); a basic-land-type hoser counts (Boil, Choke). Phase
  misparses are bridged or vetoed with a canary (Burning of Xinye, Global Ruin; End
  Hostilities, Eye of Singularity, Herald of Vengeance).
- **Extra-turn cards** read the `extra_turns` signal key (any extra turn, whoever
  takes it — CR 500.7: Time Stretch, Expropriate's vote, Emrakul, the Promised End's
  controlled player). Extra turns and the **B3 "cheap-&-early" combo** test are
  *qualitative in the official text* — encoded as project-chosen heuristics flagged
  **WARN, not FAIL** (e.g. extra-turn count over a low cap or an extra-turn + recursion
  loop; combined-mana-value / earliest-assembly-turn vs the ~turn-6 anchor), and labeled
  as heuristic, never asserted as an official number.
- **Brackets 4 and 5 short-circuit to PASS** (banned-list only; nothing to enforce).
- **No tutor axis** — WotC removed tutor restrictions on 2025-10-21; the most efficient
  tutors are now caught only via their Game-Changers membership.
- The swap proposer **respects the ceiling** (won't propose a Game-Changer add that
  breaches the target). The gate reports `counts` beside `ceilings`; the proposer's
  headroom is their difference, unclamped — a deck two over the ceiling cannot cut one
  Game Changer and add another.
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
