---
name: twohg-guide
description: Build a Two-Headed Giant (2HG) sealed prerelease cheat sheet for a new MTG set — what's winning (Arena Early Access stats + paper prerelease reports), team pairings, every card that doubles against two opponents, partner-hitting gotchas, rules that change in 2HG, bombs, removal, and a build-hour checklist — published as a private artifact page with card-image hovers.
compatibility: Requires Python 3.12+ and uv. Shares mtg_utils package via symlink. Uses Claude in Chrome for Untapped Premium data and the Artifact tool to publish.
license: 0BSD
---

# 2HG Guide

Dan and his partner play Two-Headed Giant sealed prereleases. Before each one this skill
produces a **2HG Cheat Sheet**: a short, two-column page they read on the way to the store
and at the build table. The Hobbit (Aug 2026) and Reality Fracture (Sept 2026) sheets are
the style model: `Artifact action=list` shows them; read one before drafting.

Vocabulary (head, ×2 card, partner hit, step trigger, bomb, pile) is in `CONTEXT.md`.

## Iron Rules

1. **No card text from memory.** Every card name, cost, and ability on the sheet comes from
   `twohg-scan` / `scryfall-lookup` / the local MTGJSON data. Check each claim you write
   about a card against its text.
2. **No CR number from memory.** Run `download-rules --output-dir <scratch>` fresh every
   time and pass that file to every lookup: `rules-lookup --rule <n> --rules-file
   <scratch>/comprehensive-rules-<date>.txt`. Without `--rules-file` it reads the newest copy
   in the current directory, which can be an old one checked into the repo. Cite only what it
   returns, and check your description against the rule text: CR 810.9 covers damage and life
   only, while "each opponent means both heads" is CR 102.3. For card-specific questions use
   `/rules-lawyer`.
3. **Every recommendation must agree with every other one.** The team pairings, the build
   checklist, the bombs list, and the "what's winning" section are checked against each
   other in Phase 3. If the checklist says "blue in one deck, black in the other", every
   pairing follows it.
4. **Two-sided sections.** Bombs and Removal are the pile you pull *and* the threats and
   answers the other team has. Never frame them as only one side.
5. **Say "bomb" only if the Bombs section names it.**
6. **Quote evidence exactly.** One player's deck is not a team's; "3-0 (6-0)" means three
   matches and six games without a loss, not a 6-0 match record; a comment about one store
   is one store. Label small samples.

## Workflow

```
Phase 0 intake ─► Phase 1 gather (parallel) ─► Phase 2 draft on the spine ─► Phase 3 audits ─► Phase 4 publish
```

### Phase 0 — Intake (ask once, early)

Settle these with the user in one AskUserQuestion round (skip anything already known):

- **Set code** and name, **event date and start time** (drives how much paper data exists).
- **Store product**: WPN's 2HG product from Reality Fracture on is **1 Prerelease Pack + 2 Play
  Boosters** (8 boosters, one kit) per team; some stores still run two kits (12 boosters).
  Ask which the store uses; it changes deck-building advice.
- **Match structure** (usually best-of-one).

Then, **immediately** (Reddit is blocked for every tool: WebFetch, WebSearch, and the Chrome
extension all refuse it):

> Ask the user to open r/magicTCG's "Prerelease Megathread" and the r/lrcast / r/mtglimited
> result posts from the prerelease weekend, and save each with **Cmd+S** into
> `~/Downloads`. The `_files/` folder each save creates holds the deck photos.

### Phase 1 — Gather (run in parallel)

Work in the session scratchpad. Launch these together:

1. **Card scan**:
   ```bash
   twohg-scan --set <CODE> --json > scan.json
   twohg-scan --set <CODE>             # readable version
   ```
   - The scan sorts cards into five buckets:
     - `doubles`: the ×2 cards.
     - `hits_partner`: symmetric effects and wipes that also land on your teammate.
     - `target_player`: effects you can aim at your partner.
     - `step_triggers`: CR 805.4d, `per_head` vs `once`.
     - `removal_reach`: whether each removal spell can hit a planeswalker, and its `mv_floor`. MV-gated removal can't hit Jace or other mana-value-0 tokens.
   - Each card is tagged `[ir]` (phase's parse) or `[text]` (an oracle-text fallback, used for sets phase hasn't parsed yet). Read `[text]` rows more skeptically, and check them against the card text.
2. **Fresh rules**: `download-rules --output-dir <scratch>`; every later `rules-lookup` passes
   `--rules-file` pointing at it (Iron Rule 2).
3. **Arena stats**:
   - Free tier: `limited-stats --set <CODE> --json > stats.json`. This works over plain HTTP but omits the diamond and mythic ranks.
   - **Premium**, via Chrome, when the user has Untapped Premium:
     1. Load the Chrome tools in one ToolSearch.
     2. Open `https://mtga.untapped.gg/limited/draft/<set-slug>/set-guide` in a new tab. It can take ~30 s to load, and reads `chrome://newtab` until it does, so don't retry-loop.
     3. `get_page_text` for the page summary: match count, the "Early Access" note, color tiers with 6+ win rates, top commons, signpost uncommons.
     4. In the tab, run:
        ```js
        const r = await fetch('https://api.mtga.untapped.gg/api/v1/analytics/query/card_stats_limited_by_set/premium?CardSetFilter=<CODE>&LimitedEventTypeFilter=PREMIER_DRAFT', {credentials: 'include'});
        const t = await r.text();
        document.getElementById('__out')?.remove();
        const pre = Object.assign(document.createElement('pre'), {id: '__out', textContent: t});
        document.querySelector('main').prepend(pre);
        t.length
        ```
     5. `get_page_text` hands back the JSON. Anything over about 50K characters is saved to a tool-results file; join the pieces into `premium.json`.
     6. Run `limited-stats --set <CODE> --premium-json premium.json --json`.
   - **Payload shape** (the same for free and Premium, so `limited-stats` reads either):
     - `data` is keyed by Arena **titleId**, not grpid. Names come from mtgajson `loc_en.json`, and rarity and colors from `cards.json`.
     - Inside each card, the keys are archetypes, then rank buckets (`b`/`s`/`g`/`p`/`d`/`m`). An archetype key is a color bitmask (W1 U2 B4 R8 G16, so `3` = WU and `24` = RG), or `ALL`.
     - Each rank holds three arrays: games/wins in deck, drawn-or-in-hand ("GIH"), and opening hand.
     - The free tier truncates these arrays and omits diamond/mythic. `metadata.fields` names the positions.
   - The page's `?eventType=SEALED` view is usually empty before release; say so rather than guessing.
4. **Web research subagent** (general-purpose, background). It gathers:
   - the WPN prerelease page (the 2HG product);
   - the official release notes and mechanics article;
   - Early Access write-ups (Substack, MTG Rocks);
   - set reviews: Draftsim sealed, best commons and archetypes; chunk.science's grade aggregate; Card Game Base; MTGAZone.

   Tell it that Reddit is unreachable, and to mark each claim *reported* (played events) or *predicted* (reviews).
5. **Paper reports**:
   - When the saved threads land, run `thread-extract ~/Downloads/<thread>.html`. It prints the post, the top-level comments, and the saved image paths, largest first.
   - Read the deck photos: decklists are usually images, not text.
   - Collapsed replies aren't in a saved page. If a key reply is missing, ask the user to expand it and save again.

### Phase 2 — Draft on the spine

- Start from the template: `twohg-template <scratch>/<code>-2hg.html`.
- Fill every section, keeping the Hobbit/FRA length: a cheat sheet, not an essay. Write in plain English (the reader is a player, not the repo).
- Use `.card` for card names, `.cost` for `{1}{B}` costs, `.x2` for doubled numbers, `.cr` for rule numbers and `.pip` for color pips.

| Section | What goes in it | Source |
|---|---|---|
| **What's winning** | One merged section, never separate Arena and paper blocks. Open with the lessons (e.g. bombs + removal beat pair choice; splash). Then give one line per color pair joining its Arena win rate with its paper records, and say so wherever the two disagree. Put decklists under their pair. Add the only 2HG-specific reports, quoted exactly, plus format speed and overperforming commons. Close with a footnote saying which numbers come from where. | stats, paper reports, research |
| **Team pairing** | Store product and pool size first. Then a **default split** derived from the data: which colors hold the deepest commons, and which hold the most ×2 cards and removal (in FRA: blue in one deck, black in the other). Ranked shapes must all follow the default; a fallback may break it, but must say what it gives up. Cover "both decks must work alone" and the fixing available. | scan, stats |
| **The ×2 cards** | A table (rarity · card · cost · the 2HG math) built from `doubles`. Add a "bigger here" line for triggers that fire off opponents, and a **not doubled** line from `step_triggers` rows where `fires: once` (CR 805.4d). | scan |
| **Downgrades & gotchas** | From `hits_partner` and `target_player`: wipes that hit your partner (still good, just time them together); "each player" effects; "target opponent" doesn't double; "target player" can be your partner; set-specific traps. | scan |
| **Rules that win games** | 102.3 + 810.9, 805.4d, 805.10d (a combined block; menace needs 2 blockers from your team), 805.10b, 810.8a (one decked head loses for both), 810.6 (whoever plays first skips *both* first draws, so usually draw first), 810.5, 805.8. Cite from `rules-lookup` output only. | rules-lookup |
| **Bombs** | Your pile and their threats, by color and gold pair. Each entry: the win rate when drawn (bracketed if the sample is small), paper evidence, or reviewer consensus, plus a play-around note for the big ones. Mark ones that are also ×2. End with a "not bombs despite the hype" line from `underperformers`. | stats `bomb_candidates` + paper + research |
| **Removal** | Your pile and their answers, by color, with costs and speed. Say which spells can and can't hit a planeswalker (`removal_reach`) and the MV-floor note, plus which toughness dodges what. | scan + card text |
| **Build hour checklist** | Confirm the product, pull piles (removal → bombs → ×2 → fixing; colors follow the piles), the default split, splashes and ~17 lands, 2HG grade adjustments, draw first, play fast if rounds go to time, and in-game coordination. | everything above |
| **Sources** (footer) | Every source used, with links, dates and sample sizes. Credit card images to Scryfall and © Wizards. | — |

### Phase 3 — Audits (both required)

1. **Rules audit.** Invoke `/rules-lawyer` over the whole sheet.
   - Every CR number must come from `rules-lookup` against the fresh CR.
   - Check every card claim against its text: conditional abilities ("whenever you don't cast…"), one-shot vs repeatable loyalty abilities, "nonland", "creature *or legendary* spell".
   - A tempting inference with no official ruling yet (the set's rulings usually aren't published until release) is labeled as a reading of the rules, citing the rule it rests on.
2. **Consistency audit.** Re-read the sheet top to bottom and check:
   - every "bomb" is in Bombs;
   - the pairings follow the default split, and the checklist says the same;
   - no section frames removal or bombs as one-sided;
   - single reports aren't generalized, and records are exact;
   - the ×2 table, gotchas and step-trigger lines agree with `scan.json`;
   - nothing claims the CR is silent on something it covers.

   Fix everything before publishing.

### Phase 4 — Publish

```bash
guide-card-hovers <scratch>/<code>-2hg.html --set <CODE> --out <scratch>/publish \
    [--alias "Prepare Spell=Card Name" ...]
```

- The command:
  - finds every card name in the page, including prepare-spell and face names;
  - downloads each card's Scryfall image (cached), fills the page's hover map;
  - writes `<scratch>/publish/files.json`.
- Publish with the Artifact tool:
  - `file_path`: `<scratch>/publish/<code>-2hg.html`
  - `root`: `<scratch>/publish`
  - `files`: the contents of `files.json`
  - `icon: "cards"`
  - a one-sentence `description`
- Republish revisions to the same path so the URL stays put. A revision from a **later
  session** (the store, the next day) must pass the artifact's `url`: find it with
  `Artifact action=list`, read it first, then publish with `url`. Publishing without `url`
  from a new session creates a second page.
- Tell the user the page is private until they share it from its Share menu, and give them the link.
- A face name shared by several cards (e.g. a prepare spell on three cards) is skipped with a warning. Pass `--alias` for the one the sheet means.

## Revisions

Dan usually iterates while he's at the store:
- He adds threads: run `thread-extract` again and fold the results into *What's winning*.
- He corrects the product: update Team pairing and the checklist.
- He spots inconsistencies: fix them, then re-run the Phase 3 consistency audit, since a fix in one section often contradicts another.

Republish after each round and summarize what changed in plain English.
