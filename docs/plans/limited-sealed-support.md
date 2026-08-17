# Limited / Sealed support — defects found and proposed fixes

Derived from a live session tuning a 40-card Sealed pool (The Hobbit, Arena). Every
item below was reproduced against the current code; line references are to
`mtg-utils/src/mtg_utils/`. Ordered by severity.

The through-line: **the toolchain assumes Commander-family or 60-card constructed.**
A 40-card limited deck silently falls through to the constructed branch of every
gate, and three separate mana/stat models return values that are not merely
imprecise but *inverted* — they rank a better manabase lower.

---

## P0 — `scryfall-lookup` strips power/toughness from every hydrated card

**Where:** `scryfall_lookup.py:26` — the `CARD_FIELDS` whitelist.

`_mtgjson/adapter.py:233-235` correctly maps `power` / `toughness` / `loyalty`.
The hydration step then drops them, because they are not in `CARD_FIELDS`. Every
consumer of the hydrated cache is therefore blind to creature size.

For Commander this is survivable. For Limited it is disqualifying — P/T is the
single most important stat in the format. In this session it forced a manual
`ijson` stream over the 657 MB `AllPrintings.json` to recover P/T for 67 cards.

That same list already carries a comment documenting an identical past incident
(`edhrec_rank` dropped → every card looked unranked → the tuner cut staples). The
whitelist is a recurring footgun.

**Fix.** Add `power`, `toughness`, `loyalty`, `defense`, `card_faces` to
`CARD_FIELDS`. Consider inverting the pattern to a denylist, or asserting at test
time that every field the adapter emits is either whitelisted or explicitly
excluded with a reason.

---

## P1 — The goldfish mana model mis-ranks decks that fix their mana

**Where:** `playtest.py:130` (`_land_produces`), `playtest.py:302`
(`_sources_available`), `playtest.py:234` (`_is_color_screwed`).

`_land_produces` derives a land's colors solely from `produced_mana`. Fetch-style
lands (Elven Passage, Hobbit Hole — *"{T}, Sacrifice: search your library for a
basic land"*) have `produced_mana = None`, so they enter the sources list as an
**empty set**. In `_is_color_screwed`:

```python
if len(sources) < cmc:
    return False          # empty sets DO count toward total mana
return not _pips_coverable(_card_pips(card), sources)   # but cover no colored pip
```

Both halves push the same way: the land inflates apparent mana (so the screw check
fires more often) while covering no pip (so it cannot satisfy one). A land whose
entire purpose is *guaranteeing the color you need* is modeled as a colorless
liability.

Compounding it, nonland land-fetchers (Wood Elves — *"search your library for a
Forest, put it onto the battlefield"*; Troop of Ponies) also have
`produced_mana = None` and are invisible to `_mana_ability_profile`, so their
guaranteed land drop is never modeled.

**Observed effect.** Three B/G builds of the same pool, measured color-screw:

| build | fixing the model cannot see | reported screw |
|---|---|---|
| 2 Wood Elves + Elven Passage + Hobbit Hole | 4 cards | 52.0% |
| 2 Wood Elves + Elven Passage | 3 cards | 48.7% |
| 2 Wood Elves | 2 cards | **42.6%** |

The ranking is a **perfect inverse of how much color fixing each deck runs.** The
metric actively rewards *not* fixing your mana. This produced a wrong
recommendation in-session that survived several rounds of argument because the
number looked authoritative.

**Fix.**
1. In `_land_produces`, detect a land-fetch clause in oracle text
   (`search your library for a .* land`) and return the union of basic-land colors
   actually present in the decklist, rather than `[]`.
2. Model the tapped/untapped distinction: most fetch a basic **tapped** (treat as a
   source from the following turn); conditional untappers (Elven Passage's *behold
   an Elf*) can be treated as tapped for a conservative floor.
3. Extend `_mana_ability_profile` (or add a sibling) to recognise nonland
   permanents that put a land onto the battlefield, and credit an extra land drop.
4. Until fixed, have `playtest-goldfish` emit an explicit warning when the deck
   contains land-fetch effects the model cannot see, the way the docstring already
   warns about token-mana approximation.

---

## P2 — No limited format exists, so every gate uses the wrong rules

**Where:** `format_config.py` — `FORMAT_CONFIGS` has 12 entries, none for limited.

Consequences observed:

- `parse-deck` has no `--format sealed`; the workaround is
  `--format standard --deck-size 40`, which then tells every downstream tool the
  deck is 60-card constructed.
- `legality-audit` applies the 4-copy limit. Limited has **no copy limit** — you
  play what you opened. A pool with 4 of a common is legal and the audit would
  flag a 5th that physically cannot exist anyway.
- `legality-audit` enforces a 15-card sideboard maximum. In Sealed the sideboard is
  **the entire remaining pool** (43 cards here), which the audit would reject.
- No pool-containment check exists: nothing verifies the built deck is a subset of
  the opened pool. This had to be hand-written three times this session.

**Fix.** Add `sealed` and `draft` entries: `deck_size: 40`, `max_copies: None`
(unbounded), `sideboard_size: None` (unbounded), `is_singleton: false`,
`legality_key`: the set's own legality is irrelevant — validate **pool membership**
instead. Add a `--pool <pool.json>` flag to `legality-audit` that asserts every
maindeck card is available in the pool at the required quantity.

---

## P2 — `mana-audit` returns FAIL for a correct limited manabase

**Where:** `mana_audit.py:72` — `constructed_land_target`.

Baseline 24 lands, scaled `round(base * deck_size / 60)`. For a 40-card deck with
2 ramp pieces this yields **target 15**, and 17 lands — the universal limited
default — is reported **FAIL**.

The linear scale is wrong at 40 cards. Limited runs 17/40 (42.5%) against
constructed's 24/60 (40%), and the band is tighter (16–18), not proportional.

**Fix.** Add a `limited_land_target()` branch for `deck_size <= 45`: base 17,
−1 for a low curve (avg MV < 2.5) or 3+ land-fetch effects, +1 for a high curve
(avg MV > 3.5), clamped to 16–18. Route it from the same dispatcher that chooses
Burgess vs constructed.

---

## P3 — `deck-stats` reports no-mana lands as `any`-color sources

**Where:** `deck_stats.py` colour-source counting.

Reported `Color sources: B=8, G=10, any=2` for a deck whose two "any" lands
(Elven Passage, Hobbit Hole) tap for **nothing**. Same root cause as P1, different
surface. Either resolve fetchers to the basics they can find, or report them in a
distinct `fetch=N` bucket so the number is not silently wrong.

---

## P3 — `card-summary` has no power/toughness column

**Where:** `card_summary.py:36` — `headers = ["Name", "Cost", "CMC", "Type", "Oracle Text"]`.

Blocked on P0. Once P/T survives hydration, add a `P/T` column (and prefer it over
truncating oracle text further). For limited work this is the column that matters
most.

---

## P3 — `playtest-match` discards all completed games on timeout

**Where:** `playtest.py`, phase batch runner; `--timeout-s` default 600.

At ~5 s/game, a 200-game batch needs ~17 minutes. The run hit the 600 s default and
returned **`Results (0 games)`** — every completed game discarded. The report does
warn that 0-0 is "did not finish" rather than a tie, which is good, but the work is
gone.

**Fix.** Stream results per game and return partial output with
`games_completed` / `games_requested`, plus a `timed_out: true` flag. A 118-game
sample is far more useful than nothing. Also consider defaulting `--timeout-s`
proportional to `--games`.

---

## P4 — `deck-wizard` SKILL.md has no limited path

Phase 1 offers "tune an existing deck" or "build from scratch." Sealed is neither:
the deck is **built from a fixed pool**, and the whole Commander-family spine
(`deck-tune`, `cut-check`, commander-interaction audit) is inapplicable, as is the
60-card metagame-archetype research path.

**Fix.** Add a Sealed/Draft path to Phase 1:

1. Parse the pool; hydrate (needs P0 for P/T).
2. **Enumerate all ten colour pairs mechanically** — playables, creatures, removal,
   evasion, bodies at power 4+, rares — before forming any opinion. A one-shot
   script; it took ~20 lines this session and immediately contradicted the
   hypothesis being defended.
3. Build the best 40 for the top 2–3 pairs and compare on equal footing.
4. Scan the **full set**, not the pool, for the threats the deck must answer.
5. Verify pool containment, then 17 lands via the new limited branch.

---

## P4 — Add a `set-scan` capability

Every threat assessment this session was initially made against the *player's
67-card pool* rather than the *193-card set opponents draw from*. That produced two
wrong claims that survived into a published deliverable ("nothing in this format
answers My Precious"; "Stone by Sunlight is narrow filler" — it hits 29% of the
set's creatures and is one of only two answers to its seven toughness-6+ bodies).

A ~40-line script over the set would have prevented both: removal density by
rarity, evasion density, sweepers, and the largest creatures. Worth shipping as
`set-scan --set HOB --bulk-data <path>` and making it a required step of the
limited path.

---

## P4 — Process: the self-grill cannot arbitrate archetype choice

Step 8 dispatches a Proposer and a Challenger **around an existing proposal**.
That is right for tuning a deck and wrong for choosing one: in this session both
agents were handed the same predetermined colour pair, so the Challenger optimised
against a single build instead of evaluating the pool. It cost-ed out rivals only
because the prompt happened to ask.

**Fix.** For the limited path, the Step 8 prompt should be *"rank every viable
colour pair from this pool and justify the ordering,"* with no candidate named —
and the enumeration from the limited path (step 2 above) supplied as input rather
than a finished decklist.

---

## Not a repo defect

For the record: the blank oracle text on Adventure cards mid-session was a bug in a
throwaway join script, not in the tools. `scryfall_lookup.py:71` already indexes
"every DFC face" plus Arena `printed_name` / `flavor_name`, and `--batch` resolved
all 67 cards with zero misses. The ad-hoc join keyed on front-face names against
records stored under the combined `A // B` name.

A small ergonomic improvement would still help: have the hydrated cache carry a
face-name index, so downstream joins by decklist name cannot hit this.
