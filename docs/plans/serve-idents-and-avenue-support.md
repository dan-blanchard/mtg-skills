# Plan: retire the serve regexes; make an avenue need cards that care

Two passes, found tuning the Multiverse Reforged precon (Jace, Multiverse Architect,
a polymorph deck) on 2026-10-17. Commit 247db14b fixed the narrow symptom (the
commander's own avenue collapsing into a generic one); this plan is the two broad
follow-ups Dan asked for. Pass B shipped 2026-10-18 (§3, "Measured"); Pass A is in progress.

## 1. What the census measured

`signal_specs` holds 357 static serve specs with an oracle-regex arm (355 whose
key a lane produces, 3 that already carry an ident arm beside the regex). A serve
answers "which cards feed this avenue", so it is *meant* to be broader than "which
cards emit this key": a `_matters` lane is fed by its `_makers`. The question is
whether the lanes already have a structural read that reproduces each regex.

Over the commander-legal pool (one gameplay printing per name), for each regex
spec: the regex-served set, versus the best union of up to four existing idents
at ≥50 % precision (scratchpad `serve_census2.json`):

| greedy-union recall of the regex set | specs |
|---|---|
| ≥ 0.9 (an ident set reproduces the regex) | 184 |
| 0.7 – 0.9 | 38 |
| 0.4 – 0.7 | 38 |
| < 0.4 (no structural replacement today) | 95 |

For 232 specs the best ident is the spec's own key; for 37 it is the makers /
matters sibling; for 86 it is another lane. The 95 with no replacement split into
three kinds, each a different job:

- **Lane under-detects what the regex names.** `protection_grant` (regex 281
  cards, the lane's ident ~0), `extra_end_step` (563 vs 1), `bounce_tempo` (245),
  `pump_makers` (862 vs a 47 % Jaccard), `creature_recursion` (404), `activated_draw`
  (117), `topdeck_stack` (88), `cant_block_grant` (70). These are phase-gap or
  lane-gap findings: the structural read exists but misses most of the idiom.
  Each one is an ADR-0039-style promotion (measure live-only vs crosswalk-only,
  adjudicate the sheds, canary the bridges), reported upstream where phase is the
  gap.
- **The regex is archetype adjacency, not the key.** `cost_reduction`'s serve is
  `\bstorm\b`; `has_dash`'s is `equip {`; `nonhuman_attackers`' is "gains flying".
  These are SubAvenues in a main spec's clothing. They move to `extras` (a
  `SubAvenue` is the sanctioned home for prose adjacency, CONTEXT.md) or get a
  real lane; a regex serve on the main spec is the wrong shape either way.
- **The lane is right and the regex was the noise.** `cheat_into_play` (done:
  credited reanimation, missed "creature or planeswalker card"), `graveyard_matters`
  (regex 3375 vs ident 3839, 2703 shared), `removal`, `direct_damage`, `ramp`.
  Switch to the ident arm, keep the structured dims (`serve_power_min`, types,
  keywords), delete the regex, pin a real-card test on each side of the boundary.

The 59 `SubAvenue` extras in `_shared.py` carry their own regexes and are out of
scope for the first pass: adjacency in prose is their documented purpose.

## 2. Pass A: serve idents

Policy, per spec, in census order (worst divergence first):

1. **≥ 0.9 recall, best ident is the own key or its sibling (≈200 specs):**
   replace the regex with `serve_idents` of those idents; keep every structured
   dim. One real-card test per spec on the ident arm (a card the regex missed, or
   one it wrongly served), snapshot regen with `--names`. Mechanical; batches of
   ~25 per agent, each agent reports regex-only / ident-only names it dropped or
   gained with the card text, and the parent spot-checks.
2. **0.4 – 0.9 (76 specs):** the union of idents reproduces part of the regex.
   Convert, and log every regex-only remainder as either a lane gap (backlog +
   upstream) or deliberate adjacency (→ `extras`). Needs a human read per spec.
3. **< 0.4 (95 specs):** no conversion until the lane is promoted or the serve
   is re-shaped as adjacency. Each gets a backlog row with its numbers; the lane
   gaps go upstream in one batch (Dan posts).

Invariants the pass keeps: `search` fragments (what card-search runs) are
untouched; `Serve.as_dict` already round-trips `signal_idents`; the ident arm is
the costliest dimension and is checked last, so a card the structured dims admit
never pays for it. CI has no bulk: every new test name is a `test_card` literal
the snapshot builder scans.

Done when: zero `_spec(... <regex>)` calls remain in `data_*.py` for a producible
key, or each remaining one is a backlog row naming the lane gap.

## 3. Pass B: an avenue needs cards that care

`_tuner.metrics.focus` measures an avenue's depth as the number of nonland cards
whose serve matches it. On the stock Jace precon that gives:

| avenue | depth (serve) | cards that emit the key | opened by |
|---|---|---|---|
| Historic | 32 (main) | 1 | Jhoira's reveal-a-historic trigger |
| Cantrips | 27 (main) | 1 | Fatehold Charm |
| Combat | 22 (main) | 9 | — |
| Big creatures / power matters | 19 (sub) | 1 | Dreadhorde Invasion |
| Cheat into play | 18 (sub) | 7 incl. the commander | Jace's −3 |
| Cost reduction | 17 (sub) | 1 | The Ur-Sphinx's eminence |
| Top-deck selection | 6 (emerging) | 8 | — |
| Dig-until | 5 (emerging) | 5 | — |

Every "main" theme is one card's lane that the rest of the deck feeds by
accident (every legendary creature and every rock is Historic); the deck's
engine is a sub-theme. Every downstream read inherits it: `SPREAD-THIN`, the
"barely played for this theme" cut, the candidate adds (Kari Zev for Combat,
Hidden Strings for Cantrips), and `commander_fit` (Jace "serves 1 of 6 avenues").

The emerging-tribal gate already solves this for tribes: an emerging tribal
avenue needs a HIGH non-commander payoff emitter or it is a changeling phantom
(`tribal_payoff_subjects`). Generalise it:

- `read_deck_signals` already computes `support` (cards emitting each ident). Add
  it to `DeckSignals` as `emitters` (ident → the names of the cards emitting it) plus the commander's idents
  (done).
- An avenue is **viable** only if its key has emitter support ≥ a scaled floor
  (proposal: `focus_emitters`, 3 at 100 cards — Combat's 9 passes, Historic's 1
  fails) **or** the commander holds it (Jace's Cheat into play). Below the floor
  the avenue is *fed*, not *built*: report it under a new `fed` list (so the
  reader still sees "32 cards are historic") and keep it out of mains / subs /
  the collapse / `commander_fit` / the spread-thin cut.
- Rank viable avenues by emitter support first, serve depth second, so the
  commander's lane with 7 emitters outranks a 1-emitter lane with 19 feeders.
- Candidate adds for a viable avenue stay serve-based (the avenue wants feeders),
  but a cut for "barely played for this theme" must name a theme that is viable
  under the new rule.

Expected effect on the Jace precon (to measure, not assume): mains = Cheat into
play (commander-held, 7), Combat (9); subs = Lifegain makers (9), Activated-ability
engine (9); fed = Historic, Cantrips, Big creatures, Cost reduction. Verdict
FOCUSED or a two-main SPREAD-THIN, and the adds come from the cheat serve
(polymorph effects, power-5+ bodies) and token makers once Pass A's
`token_maker` ident credits them.

Commanders this touches beyond Jace: any commander whose plan is a lane the 99
feeds broadly (cheat, reanimator, blink, spellslinger with many rocks) — exactly
the "misguided on commanders like this one" case.

Done when: the eight-row table above is re-measured through `deck-tune` and the
tuner's swaps for the stock precon are polymorph effects / token makers / bombs,
not Kari Zev; the `test_tuner_focus` suite pins a one-emitter avenue as `fed`;
every deck in `tests/` that asserts a focus verdict still passes or has its
assertion re-adjudicated in the same commit.

**Measured 2026-10-18 (shipped).** `read_deck_signals` carries `emitters`
(ident → the cards emitting it); `focus` takes it, reads a `_makers` avenue's
carers off its `_matters` sibling, demotes a deep avenue below `focus_emitters`
(3 at 100 cards, waived for a commander-held lane) to a new `fed` list, ranks
viable avenues commander-held first then by carers, makes the commander's lane
a main theme whatever its depth, and exposes `commander_avenues`; the
`role_over` remedy deepens that lane before any emerging direction. On the
stock precon:

| avenue | before | after |
|---|---|---|
| Cheat into play | sub, 4th | main, 1st (7 carers) |
| Combat | main | main (9 carers) |
| Artifacts, Spellslinger | collapsed under Historic / Cantrips | main (5, 4 carers) |
| Historic, Cantrips, Big creatures, Cost reduction, Lifegain | main / sub | fed |
| swaps | Kari Zev, Patchwork Crawler, Hidden Strings, … (6) | Inevitable Betrayal, Glimpse of Tomorrow, Unstoppable Slasher (3) |

The verdict is still SPREAD-THIN (four viable avenues) and the remaining gaps
are the backlog's "What the polymorph tune still gets wrong" entry: flip
quality, token makers as fodder, and sibling-lane co-emission (Artifacts and
Top-deck selection are inflated by artifact-token makers and reveal-until
effects emitting those keys).

## 4. Order

B first (one function, one data plumb, measurable on the Jace deck in an
afternoon), then A in census order. B does not depend on A; A's token-maker
conversion is what makes B's adds right for polymorph.

## Appendix: the serve specs Pass A did not convert (census 2026-10-17)

Measured over the commander-legal pool, one gameplay printing per name: the
regex-served count, the best existing ident (Jaccard with the regex set), and
the recall a greedy union of up to four idents at ≥50 % precision reaches. A
row moves out of here when its lane is promoted to cover the regex-only
remainder (upstream phase gap or lane gap) or its regex is re-shaped as a
`SubAvenue`.

### Partial (0.4 ≤ recall < 0.9): convert, log the remainder — 76 specs

| key \| scope | regex | best ident (Jaccard) | union recall | pattern |
|---|---:|---|---:|---|
| `permanent_etb\|you` | 8329 | `type_matters\|you\|*` (0.3) | 0.6 | `create [^.]*token\|put [^.]*onto the battlefield\|wh` |
| `attack_matters\|you` | 6597 | `token_maker\|you\|*` (0.36) | 0.75 | `(?:gains?\|gain\|have\|has) haste\|create [^.]*creatur` |
| `permanent_recast\|you` | 5307 | `blink_flicker\|you\|` (0.32) | 0.55 | `when(?:ever)? [^.]*enters(?: the battlefield)?, ` |
| `activated_ability\|you` | 4514 | `activated_ability\|you\|` (0.43) | 0.65 | `activated abilities[^.]*\bcost\b\|untap (?:target\|a` |
| `sacrifice_outlets\|you` | 4414 | `token_maker\|you\|*` (0.54) | 0.83 | `create [^.]*creature token\|sacrifices? (?:a\|an\|ano` |
| `death_matters\|any` | 4247 | `token_maker\|you\|*` (0.56) | 0.86 | `create [^.]*creature token\|sacrifices? (?:a\|an\|ano` |
| `proliferate_makers\|you` | 3720 | `plus_one_makers\|you\|` (0.75) | 0.85 | `\bproliferate\b\|(?:poison\|loyalty\|charge\|oil\|\+1/\` |
| `proliferate_matters\|you` | 3720 | `plus_one_makers\|you\|` (0.75) | 0.85 | `\bproliferate\b\|(?:poison\|loyalty\|charge\|oil\|\+1/\` |
| `ramp\|you` | 2744 | `ramp\|you\|` (0.56) | 0.63 | `\{t\}[^.]*:\s*add\|add .* mana\|search your library ` |
| `removal\|you` | 1972 | `removal\|you\|` (0.44) | 0.66 | `destroy target (?:creature\|permanent\|artifact\|ench` |
| `direct_damage\|you` | 1791 | `direct_damage\|you\|` (0.53) | 0.69 | `deals \d+ damage to any target\|\{t\}[^.]*deals .*d` |
| `combat_damage_matters\|opponents` | 1429 | `combat_damage_matters\|opponents\|` (0.5) | 0.56 | `deals combat damage to (?:a player\|an opponent\|one` |
| `self_counter_grow\|you` | 1420 | `self_counter_grow\|you\|` (0.61) | 0.86 | `enters with (?:x\|\d+\|a\|an\|one\|two\|three) \+1/\+1 c` |
| `lifeloss_makers\|opponents` | 1078 | `lifeloss_makers\|opponents\|` (0.45) | 0.61 | `opponent[^.]*loses [^.]*life\|whenever an opponent ` |
| `lifeloss_matters\|opponents` | 1078 | `lifeloss_makers\|opponents\|` (0.45) | 0.61 | `opponent[^.]*loses [^.]*life\|whenever an opponent ` |
| `card_draw_engine\|you` | 1000 | `card_draw_engine\|you\|` (0.67) | 0.88 | `at the beginning of [^.]*\bdraws? (?:a\|an\|two\|thre` |
| `team_buff\|you` | 987 | `creatures_matter\|you\|` (0.39) | 0.49 | `creatures? you control (?:gain\|gains\|have\|has) (?:` |
| `tutor\|you` | 932 | `tutor\|you\|` (0.62) | 0.66 | `search your library for` |
| `reanimator\|you` | 836 | `creature_recursion\|you\|` (0.28) | 0.43 | `(?:return\|put)[^.]*creature card[^.]*from (?:a\|you` |
| `lands_matter\|you` | 805 | `landfall\|you\|` (0.28) | 0.44 | `the number of lands you control\|for each land you ` |
| `landfall\|you` | 731 | `landfall\|you\|` (0.3) | 0.42 | `\blandfall\b\|search your library for [^.]*\bland\b` |
| `untap_engine\|you` | 708 | `untap_engine\|you\|` (0.41) | 0.48 | `untap (?:target\|all\|another\|each\|enchanted\|this\|th` |
| `lifeloss_makers\|you` | 617 | `lifeloss_makers\|you\|` (0.58) | 0.84 | `whenever you (?:gain or )?lose life\|you lose (?:\d` |
| `lifeloss_matters\|you` | 617 | `lifeloss_makers\|you\|` (0.58) | 0.84 | `whenever you (?:gain or )?lose life\|you lose (?:\d` |
| `self_pump\|you` | 601 | `self_pump\|you\|` (0.41) | 0.66 | `\{[^}]*\}(?:, \{t\})?: [^.]* gets \+[0-9x]/\+[0-9x` |
| `free_cast\|you` | 566 | `free_cast\|you\|` (0.59) | 0.79 | `rather than pay (?:its\|their\|the) mana cost\|withou` |
| `exile_removal\|you` | 386 | `exile_removal\|you\|` (0.54) | 0.74 | `exile target (?:creature\|permanent\|artifact\|enchan` |
| `blocked_matters\|you` | 378 | `blocked_matters\|you\|` (0.52) | 0.63 | `whenever [^.]*becomes blocked\|\bwhenever \w[^.]*\b` |
| `impulse_top_play\|you` | 374 | `impulse_top_play\|you\|` (0.57) | 0.78 | `exile the top [^.]*card[^.]*(?:you may play\|may pl` |
| `ltb_matters\|you` | 367 | `ltb_matters\|you\|` (0.58) | 0.88 | `a permanent (?:you controlled )?left the battlefie` |
| `clone_makers\|you` | 354 | `token_copy_makers\|you\|` (0.4) | 0.83 | `becomes a copy\|copy of (?:target\|another\|any\|a\|tha` |
| `copy_permanent\|you` | 354 | `token_copy_makers\|you\|` (0.4) | 0.83 | `becomes a copy\|copy of (?:target\|another\|any\|a\|tha` |
| `wants_cloning\|you` | 354 | `token_copy_makers\|you\|` (0.4) | 0.83 | `becomes a copy\|copy of (?:target\|another\|any\|a\|tha` |
| `token_copy_makers\|you` | 349 | `token_copy_makers\|you\|` (0.63) | 0.64 | `tokens? that(?:'s\| are) (?:a )?cop(?:y\|ies) of\|\bp` |
| `minus_counters_matter\|you` | 294 | `minus_counters_matter\|you\|` (0.61) | 0.64 | `-1/-1 counter` |
| `targeting_matters\|any` | 283 | `targeting_matters\|any\|` (0.69) | 0.7 | `becomes the target of a spell or ability\|whenever ` |
| `power_tap_engine\|you` | 275 | `untap_engine\|you\|` (0.4) | 0.61 | `untap (?:another )?target (?:creature\|permanent)\|\` |
| `variable_pt\|you` | 251 | `variable_pt\|any\|` (0.78) | 0.85 | `power and toughness are each equal to(?: the (?:to` |
| `tokens_matter\|you` | 242 | `amass_makers\|you\|` (0.29) | 0.5 | `\btokens? you control\b\|whenever (?:a\|one or more\|` |
| `opponent_cast_matters\|opponents` | 237 | `opponent_cast_matters\|opponents\|` (0.36) | 0.42 | `whenever an opponent casts\|whenever a player casts` |
| `opponent_draw_matters\|opponents` | 235 | `target_player_draws\|any\|` (0.4) | 0.89 | `whenever an opponent draws\|whenever each opponent ` |
| `any_counter_makers\|you` | 196 | `proliferate_makers\|you\|` (0.46) | 0.84 | `proliferate\|for each counter on\|twice that many [^` |
| `any_counter_matters\|you` | 196 | `proliferate_makers\|you\|` (0.46) | 0.84 | `proliferate\|for each counter on\|twice that many [^` |
| `superfriends_matters\|you` | 191 | `superfriends_matters\|you\|` (0.61) | 0.81 | `planeswalkers? you control\|loyalty counters?` |
| `animate_artifact\|you` | 168 | `animate_artifact\|you\|` (0.41) | 0.42 | `(?:target \|each )?(?:noncreature )?artifact(?:s)? ` |
| `forced_attack\|you` | 163 | `forced_attack\|any\|` (0.5) | 0.66 | `may attack only the nearest opponent\|attacks? that` |
| `card_draw_engine\|each` | 142 | `group_hug_draw\|each\|` (0.58) | 0.71 | `each player[^.]*draws?\|that player draws\|whenever ` |
| `big_hand_makers\|you` | 132 | `big_hand_makers\|you\|` (0.45) | 0.52 | `maximum hand size\|(?:\d+\|five\|six\|seven\|eight) or ` |
| `big_hand_matters\|you` | 132 | `big_hand_makers\|you\|` (0.45) | 0.52 | `maximum hand size\|(?:\d+\|five\|six\|seven\|eight) or ` |
| `draw_matters\|you` | 126 | `draw_matters\|you\|` (0.73) | 0.79 | `whenever you draw\|draws? (?:your )?(?:second\|an ad` |
| `snow_matters\|you` | 114 | `snow_matters\|you\|` (0.72) | 0.73 | `\bsnow\b` |
| `play_from_top\|you` | 102 | `play_from_top\|you\|` (0.45) | 0.89 | `(?:play\|cast)\b[^.]*?\bfrom the top of your librar` |
| `island_makers\|you` | 78 | `island_makers\|you\|` (0.62) | 0.62 | `(?:nonbasic \|all )?lands?[^.]*are islands\|becomes?` |
| `secret_writedown\|you` | 76 | `secret_writedown\|you\|` (0.39) | 0.53 | `secretly (?:write\|choose\|name)\|before the game beg` |
| `pacify_makers\|you` | 73 | `pacify_makers\|you\|` (0.73) | 0.81 | `enchanted (?:creature\|permanent\|artifact\|land\|plan` |
| `damage_doubling\|you` | 68 | `damage_doubling\|you\|` (0.75) | 0.75 | `deals? (?:double\|triple) that damage\|deals? twice ` |
| `ability_copy\|you` | 66 | `ability_copy\|you\|` (0.88) | 0.88 | `copy (?:that\|this\|the\|target) (?:activated \|trigge` |
| `outlaw_matters\|you` | 66 | `token_maker\|you\|Rogue` (0.33) | 0.82 | `\boutlaws? you control\b\|another outlaw\|create[s]?` |
| `domain_matters\|you` | 65 | `domain_matters\|you\|` (0.89) | 0.89 | `\bdomain\b\|number of basic land types?\|basic land ` |
| `multicolor_matters\|you` | 59 | `multicolor_matters\|you\|` (0.46) | 0.53 | `whenever you cast a multicolored\|multicolored (?:c` |
| `win_lose_game\|any` | 52 | `win_lose_game\|any\|` (0.58) | 0.87 | `you win the game\|(?:that player\|each opponent\|targ` |
| `mass_bounce\|any` | 50 | `mass_bounce\|any\|` (0.68) | 0.88 | `return each (?:other )?(?:nonland )?permanent[^.]*` |
| `lessons_matter\|you` | 49 | `lessons_matter\|you\|` (0.55) | 0.57 | `lesson spells?\|cast (?:an? )?(?:artifact or )?less` |
| `has_banding\|you` | 47 | `has_banding\|you\|` (0.51) | 0.53 | `\bbands? with other\|\bbanding\b` |
| `flash_makers\|you` | 42 | `flash_makers\|you\|` (0.74) | 0.76 | `cast[^.]{0,60}spells?[^.]{0,30}as though they had ` |
| `life_total_set\|any` | 40 | `life_total_set\|any\|` (0.7) | 0.8 | `life total (?:becomes\|equal to)\|equal to half (?:t` |
| `opponent_exile_makers\|opponents` | 37 | `opponent_exile_makers\|opponents\|` (0.63) | 0.78 | `exile (?:target player's\|target opponent's\|each op` |
| `voting_makers\|each` | 34 | `voting_makers\|each\|` (0.56) | 0.65 | `\bvote\b\|will of the council` |
| `voting_matters\|each` | 34 | `voting_makers\|each\|` (0.56) | 0.65 | `\bvote\b\|will of the council` |
| `noncreature_cast_punish\|any` | 31 | `noncreature_cast_punish\|any\|` (0.44) | 0.52 | `whenever a player casts a noncreature spell\|whenev` |
| `spell_redirect\|you` | 26 | `spell_redirect\|you\|` (0.66) | 0.88 | `change (?:a\|the) target of target spell or ability` |
| `target_redirect\|you` | 26 | `spell_redirect\|you\|` (0.66) | 0.88 | `change (?:a\|the) target of target spell or ability` |
| `xspell_matters\|you` | 19 | `xspell_matters\|you\|` (0.45) | 0.47 | `\{x\} in (?:its\|their) (?:mana )?cost\|cost (?:that` |
| `tapped_matters\|you` | 18 | `tapped_matters\|you\|` (0.38) | 0.56 | `number of tapped creatures you control\|\btapped cr` |
| `creature_etb\|opponents` | 15 | `creature_etb\|opponents\|` (0.56) | 0.6 | `creature an opponent controls enters\|creatures? yo` |
| `type_change\|you` | 11 | `type_changers\|you\|` (0.42) | 0.55 | `(?:target\|each\|all\|that) creatures?[^.]{0,25}becom` |

### Blocked (recall < 0.4): lane gap or adjacency first — 95 specs

| key \| scope | regex | best ident (Jaccard) | union recall | pattern |
|---|---:|---|---:|---|
| `cantrip\|you` | 3194 | `cantrip\|you\|` (0.14) | 0.35 | `draws? (?:a\|an additional) card` |
| `stax_taxes\|opponents` | 1844 | `stax_taxes\|opponents\|` (0.12) | 0.22 | `opponents? can't\|(?:players?\|that player\|each play` |
| `symmetric_stax\|each` | 1844 | `stax_taxes\|opponents\|` (0.12) | 0.22 | `opponents? can't\|(?:players?\|that player\|each play` |
| `artifacts_matter\|you` | 1717 | `artifacts_matter\|you\|` (0.3) | 0.39 | `artifacts? you control\|for each artifact\|\bmetalcr` |
| `voltron_makers\|you` | 1325 | `enchantments_matter\|you\|` (0.12) | 0.11 | `equipped creature\|enchanted creature gets\|equip \{` |
| `voltron_matters\|you` | 1325 | `enchantments_matter\|you\|` (0.12) | 0.11 | `equipped creature\|enchanted creature gets\|equip \{` |
| `extra_upkeep\|you` | 1127 | `enchantments_matter\|you\|` (0.08) | 0.08 | `at the beginning of (?:your\|each) upkeep` |
| `pump_makers\|you` | 862 | `pump_makers\|you\|` (0.47) | 0.02 | `target (?:[a-z]+ )*creature(?: you control)? gets ` |
| `damage_to_opp_matters\|opponents` | 824 | `evasion_self\|you\|` (0.42) | 0.15 | `deals (?:noncombat )?damage to (?:a player\|an oppo` |
| `evasion_self\|you` | 743 | `evasion_self\|you\|` (0.44) | 0.08 | `can't be blocked(?! except)\|\bunblockable\b\|\b(?:f` |
| `has_ninjutsu\|you` | 743 | `evasion_self\|you\|` (0.44) | 0.08 | `can't be blocked(?! except)\|\bunblockable\b\|\b(?:f` |
| `topdeck_selection\|you` | 720 | `topdeck_selection\|you\|` (0.39) | 0.11 | `look at the top (?:two\|three\|four\|five\|six\|seven\|e` |
| `scry_surveil_matters\|you` | 697 | `topdeck_selection\|you\|` (0.36) | 0.04 | `\b(?:scry\|surveil)\b` |
| `self_etb_payload\|you` | 689 | `creature_recursion\|you\|` (0.28) | 0.34 | `exile [^.]*return[^.]*battlefield\|return [^.]*from` |
| `has_dash\|you` | 655 | `artifacts_matter\|you\|` (0.12) | 0.08 | `equip \{\|attach [^.]*equipment` |
| `nonhuman_attackers\|you` | 627 | `keyword_grant_target\|you\|` (0.11) | 0.07 | `(?:gains?\|have\|has) flying\|creatures you control[^` |
| `anthem_static\|you` | 596 | `creatures_matter\|you\|` (0.26) | 0.3 | `(?:other [a-z]+ creatures\|creatures you control\|[a` |
| `extra_end_step\|you` | 563 | `wants_cloning\|you\|` (0.07) | 0.0 | `at the beginning of (?:your\|each) end step` |
| `power_matters\|you` | 557 | `power_matters\|you\|` (0.19) | 0.31 | `power \d+ or (?:greater\|more)\|with power \d+ or\|\b` |
| `magecraft_matters\|you` | 511 | `spellcast_matters\|you\|` (0.41) | 0.19 | `\bmagecraft\b\|whenever you cast (?:an instant\|a so` |
| `spellcast_matters\|you` | 511 | `spellcast_matters\|you\|` (0.41) | 0.19 | `\bmagecraft\b\|whenever you cast (?:an instant\|a so` |
| `counter_doubling\|you` | 481 | `self_counter_grow\|you\|` (0.2) | 0.16 | `(?:twice that many\|double the number of) [^.]*coun` |
| `creature_recursion\|you` | 404 | `removal\|you\|` (0.04) | 0.01 | `sacrifice (?:this creature\|~\|this permanent)\b[^:.` |
| `mass_death_payoff\|you` | 401 | `mass_removal\|you\|` (0.4) | 0.14 | `destroy all creatures\|exile all creatures\|deals \d` |
| `graveyard_makers\|opponents` | 367 | `mill_makers\|any\|` (0.34) | 0.07 | `(?:each opponent\|target opponent\|an opponent\|that ` |
| `graveyard_matters\|opponents` | 367 | `mill_makers\|any\|` (0.34) | 0.07 | `(?:each opponent\|target opponent\|an opponent\|that ` |
| `combat_buff_engine\|you` | 362 | `combat_buff_engine\|you\|` (0.36) | 0.15 | `at the beginning of combat on your turn[^.]*creatu` |
| `mana_amplifier\|you` | 355 | `mana_amplifier\|you\|` (0.04) | 0.07 | `you tap [^.]*for mana[^.]*(?:add\|produces?)\|produc` |
| `per_target_payoff\|you` | 328 | `counter_distribute\|you\|` (0.03) | 0.01 | `any number of targets?\|divided[^.]*among[^.]*(?:an` |
| `enchantments_matter\|you` | 299 | `type_matters\|you\|Shrine` (0.08) | 0.19 | `enchantments? you control\|for each enchantment\|\bc` |
| `protection_grant\|you` | 281 | `protection_grant\|you\|` (0.24) | 0.0 | `gains? protection from\|gains? (?:hexproof\|shroud)\` |
| `big_mana\|you` | 274 | `direct_damage\|you\|` (0.08) | 0.01 | `deals x damage\|x damage to\|deals [^.]*times x dama` |
| `symmetric_damage_each\|each` | 267 | `symmetric_damage_each\|each\|` (0.24) | 0.33 | `deals \d+ damage to each (?:player\|opponent and\|cr` |
| `vehicles_matter\|you` | 255 | `vehicles_matter\|you\|` (0.16) | 0.17 | `\bvehicles? you control\b\|\bcrew\b\|create [^.]*veh` |
| `bounce_tempo\|you` | 245 | `bounce_tempo\|you\|` (0.32) | 0.0 | `return (?:up to \w+ )?target (?:creature\|permanent` |
| `color_hoser\|you` | 237 | `color_change\|you\|` (0.05) | 0.06 | `becomes the color of your choice\|(?:spell or perma` |
| `saga_matters\|you` | 237 | `saga_matters\|you\|` (0.06) | 0.08 | `lore counter\|sagas? you control\|chapter abilit\|rea` |
| `blink_flicker\|you` | 236 | `self_blink\|you\|` (0.16) | 0.32 | `exile[^.]*?return[^.]*?battlefield\|exile[^.]{0,90}` |
| `scaling_pump\|you` | 235 | `scaling_pump\|you\|` (0.48) | 0.01 | `gets [+\-][0-9x]/[+\-][0-9x] for (?:each\|every)` |
| `spell_copy_makers\|you` | 171 | `spell_copy_makers\|you\|` (0.3) | 0.02 | `copy target (?:instant\|sorcery\|spell)\|\bcopy that ` |
| `land_destruction\|you` | 132 | `land_destruction\|you\|` (0.17) | 0.2 | `destroy (?:up to (?:one\|two\|three) )?target lands?` |
| `theft_protection\|you` | 126 | `wants_theft\|opponents\|` (0.38) | 0.01 | `gain control of (?:up to one )?target (?:creature\|` |
| `cast_from_exile\|you` | 122 | `void_warp_makers\|you\|` (0.25) | 0.27 | `spells? you cast from exile\|whenever you cast a sp` |
| `activated_draw\|you` | 117 | `activated_draw\|you\|` (0.28) | 0.0 | `\{t\}: draw a card` |
| `entered_attacker\|you` | 114 | `team_buff\|you\|` (0.17) | 0.0 | `(?:another \|a )?creature you control enters[^.]*(?` |
| `cheat_from_top\|you` | 111 | `topdeck_stack\|you\|` (0.2) | 0.0 | `(?:put\|return) (?:target \|a )?(?:\w+ )?cards? from` |
| `theft_makers\|opponents` | 110 | `theft_makers\|opponents\|` (0.27) | 0.31 | `conjure a duplicate of[^.]*from an opponent's libr` |
| `wants_theft\|opponents` | 110 | `theft_makers\|opponents\|` (0.27) | 0.31 | `conjure a duplicate of[^.]*from an opponent's libr` |
| `one_punch\|you` | 99 | `keyword_grant_target\|you\|` (0.03) | 0.0 | `(?:target creature\|target attacking creature\|equip` |
| `flash_grant\|you` | 89 | `flash_makers\|you\|` (0.37) | 0.37 | `as though (?:it\|they) (?:had\|have) flash\|have flas` |
| `topdeck_stack\|you` | 88 | `topdeck_stack\|you\|` (0.1) | 0.0 | `put (?:two\|three\|\w+) cards? from your hand on top` |
| `base_power_matters\|you` | 85 | `base_pt_set\|any\|` (0.28) | 0.08 | `with base (?:power\|toughness)` |
| `kill_engine\|you` | 83 | `death_matters\|any\|` (0.11) | 0.02 | `whenever [^.]*\bcreatures?\b[^.]*dies[^.]*(?:each ` |
| `legends_matter\|you` | 82 | `legends_matter\|you\|` (0.35) | 0.01 | `legendary creatures? you control\|another legendary` |
| `color_change\|you` | 77 | `color_change\|you\|` (0.31) | 0.31 | `becomes the color of your choice\|becomes? (?:the c` |
| `cant_block_grant\|you` | 70 | `cant_block_grant\|you\|` (0.38) | 0.0 | `target creature can't block` |
| `exile_matters\|you` | 68 | `exile_matters\|you\|` (0.44) | 0.07 | `cards? (?:you own )?in exile\|for each card[^.]*exi` |
| `self_blink\|you` | 67 | `control_exchange\|you\|` (0.09) | 0.1 | `exile (?:up to one \|another \|a \|target )?(?:other ` |
| `land_sacrifice_makers\|you` | 62 | `land_sacrifice_makers\|you\|` (0.38) | 0.11 | `sacrifice a land(?: card)?:\|each player sacrifices` |
| `land_sacrifice_matters\|you` | 61 | `land_sacrifice_makers\|you\|` (0.29) | 0.2 | `sacrifice a land(?: card)?:\|whenever (?:a\|one or m` |
| `cost_reduction\|you` | 59 | `token_maker\|you\|Bird` (0.02) | 0.02 | `\bstorm\b` |
| `control_exchange\|you` | 33 | `wants_theft\|opponents\|` (0.1) | 0.0 | `exchange control of\|exchange (?:control of )?(?:th` |
| `target_player_draws\|any` | 33 | `target_player_draws\|any\|` (0.16) | 0.0 | `target player draws a card\|target opponent draws` |
| `island_matters\|you` | 28 | `island_matters\|you\|` (0.1) | 0.0 | `(?:nonbasic \|all )?lands?[^.]*are islands\|becomes?` |
| `arcane_matters\|you` | 27 | `arcane_matters\|you\|` (0.29) | 0.0 | `splice onto arcane` |
| `named_synergy\|you` | 27 | `named_synergy\|you\|` (0.4) | 0.15 | `(?:permanent\|creature\|another permanent) named [A-` |
| `own_target_spell\|you` | 27 | `targeting_matters\|any\|` (0.09) | 0.0 | `instant or sorcery spell that targets` |
| `aoe_ping\|you` | 25 | `aura_equip_kw_grant\|you\|` (0.04) | 0.0 | `(?:equipped\|enchanted) creature[^.]*\bdeathtouch\b` |
| `exert_matters\|you` | 25 | `type_matters\|you\|Warrior` (0.03) | 0.0 | `you may exert this creature` |
| `conditional_self_protection\|you` | 24 | `conditional_self_protection\|you\|` (0.28) | 0.08 | `has hexproof (?:if\|while\|as long as\|during)\|during` |
| `opp_top_exile\|you` | 24 | `opp_top_exile\|you\|` (0.05) | 0.0 | `plays? with the top card of their (?:libraries\|lib` |
| `life_payment_insurance\|you` | 22 | `lifeloss_matters\|you\|` (0.14) | 0.0 | `don'?t lose the game for having\|can'?t lose the ga` |
| `lose_unless_hand\|you` | 21 | `commander_matters\|you\|` (0.04) | 0.0 | `can'?t lose the game\|into your hand from the comma` |
| `spell_keyword_grant\|you` | 21 | `spell_keyword_grant\|you\|` (0.16) | 0.05 | `spells you cast have (?:convoke\|affinity\|cascade\|f` |
| `land_creatures_matter\|you` | 19 | `token_maker\|you\|Dryad` (0.16) | 0.26 | `\bland creatures?\b` |
| `land_protection\|you` | 19 | `land_creatures_matter\|you\|` (0.06) | 0.0 | `lands?[^.]*(?:have\|gain\|with)[^.]*indestructible\|a` |
| `counter_grants_kw\|you` | 18 | `counter_grants_kw\|you\|` (0.39) | 0.0 | `creature you control with a \+1/\+1 counter on it ` |
| `tap_down_blockers\|you` | 17 | `untap_engine\|each\|` (0.05) | 0.0 | `tap all creatures (?:target\|that\|defending) player` |
| `count_anthem\|you` | 16 | `count_anthem\|you\|` (0.33) | 0.0 | `(?:creatures you control get\|each creature you con` |
| `extra_draw_step\|you` | 16 | `big_hand_makers\|you\|` (0.01) | 0.0 | `at the beginning of (?:your\|each) draw step` |
| `target_own_payoff\|you` | 13 | `damage_redirect\|you\|` (0.08) | 0.0 | `\{0\}:[^.]*target (?:a \|another )?(?:creature\|perm` |
| `typed_anthem_multi\|you` | 13 | `typed_anthem_multi\|you\|` (0.39) | 0.0 | `each (?:other )?creature (?:you control )?that's (` |
| `opponent_search_matters\|opponents` | 12 | `opponent_search_matters\|opponents\|` (0.29) | 0.33 | `(?:opponent\|each player\|a player)[^.]*(?:scries\|su` |
| `land_denial\|you` | 9 | `edict_makers\|each\|` (0.06) | 0.0 | `whenever a player[^.]*(?:returns? a land\|sacrifice` |
| `typed_enters_punish\|you` | 9 | `typed_enters_punish\|you\|` (0.32) | 0.0 | `whenever another (?:outlaw\|ally\|\w+) you control e` |
| `group_mana\|each` | 8 | `group_mana\|each\|` (0.26) | 0.0 | `each player adds \{\|that player adds \{\|the active` |
| `flip_self\|you` | 7 | `flip_self\|you\|` (0.33) | 0.0 | `\bflip this creature\b` |
| `all_creatures_kw_grant\|any` | 6 | `all_creatures_kw_grant\|any\|` (0.24) | 0.0 | `all creatures have (?:haste\|flying\|trample\|vigilan` |
| `tribal_etb_multi\|you` | 5 | `has_undying_persist\|you\|` (0.03) | 0.0 | `whenever [^.]*or another [A-Z][a-z]+(?:, [A-Z][a-z` |
| `land_exchange\|you` | 3 | `land_exchange\|you\|` (0.18) | 0.0 | `exchange control of[^.]*\bland\b` |
| `opponent_counter_grant\|opponents` | 2 | `opponent_counter_grant\|opponents\|` (0.05) | 0.0 | `put a (?:bounty\|stun) counter on target (?:creatur` |
| `aura_equip_kw_grant\|you` | 1 | `aura_equip_kw_grant\|you\|` (0.33) | 0.0 | `(?:auras?\|equipment) you control have (?:exalted\|f` |
| `conjure_makers\|you` | 1 | `land_creatures_matter\|you\|` (0.01) | 0.0 | `\bconjure\b` |
| `has_enlist\|you` | 1 | `has_enlist\|you\|` (0.08) | 0.0 | `\benlisted? (?:a\|another) creature` |
| `vanilla_matters\|you` | 1 | `vanilla_matters\|you\|` (0.2) | 0.0 | `creatures? with no abilities` |

