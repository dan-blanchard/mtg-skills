---
name: proxy-printer
description: Render printable PDF proxies for an MTG deck — one PDF for the deck's cards, one for every token kind those cards produce. Cards and tokens both use a layout that mirrors a real MTG card frame (name banner / ASCII art / type banner / oracle text / P/T) with all data pulled live from Scryfall.
compatibility: Requires Python 3.12+, uv, and reportlab. Shares mtg_utils package via symlink.
license: 0BSD
---

# Proxy Printer

Turn a parsed MTG deck list into printable proxy PDFs. The skill emits two
artifacts: `cards.pdf` (one proxy per copy of every card in the deck) and
`tokens.pdf` (one proxy per distinct token kind produced by any card in the
deck, deduped by Scryfall `oracle_id`). Both use the same render template:
name banner, ASCII art keyed by card subtype, type banner, oracle text, P/T.

The skill is callable standalone (the user gives a list, the agent prints
PDFs) or by another wizard — deck-wizard and cube-wizard both produce the
parsed-deck JSON schema this skill consumes.

## The Iron Rule

**NEVER render a proxy from training-data oracle text.** Every name, mana
cost, type line, oracle text, P/T, and token-side stat on a generated PDF
MUST come from a Scryfall lookup performed by `proxy-print`. The CLI is
the authoritative renderer; the agent is not allowed to "fix up" any
printed content.

## When to use this skill

- The user gives a deck list and asks for printable proxies.
- The user gives a TCGPlayer order CSV / Moxfield txt / plain card list
  and wants to physically print the cards.
- A higher-level skill (deck-wizard, cube-wizard) wants to ship a
  printable artifact at the end of a build session.

## Workflow

```
[raw deck list]  →  parse-deck  →  deck.json  →  proxy-print --kind cards   →  cards.pdf
                                              \→ proxy-print --kind tokens  →  tokens.pdf
```

### Step 1 — Parse the input

If the user supplies anything other than a parsed deck JSON, run
`parse-deck` first to produce the canonical schema. `parse-deck` already
handles Moxfield, MTGO, plain text, and CSV (including the
TCGPlayer-order-CSV shape).

```bash
parse-deck input.txt > /tmp/deck.json
```

### Step 2 — Refresh bulk data if needed

`proxy-print` reads from the Scryfall bulk JSON. If the cached file is
older than 7 days the CLI exits with code 1 and a message pointing here.
Run:

```bash
download-bulk --output-dir /tmp/scryfall-bulk
```

> One-time-ish: if you want artist-credited art on the proxies, populate
> the attributed catalog first. See [ASCII art catalog](#ascii-art-catalog)
> below.

### Step 3 — Render cards

```bash
proxy-print --kind cards \
    --deck /tmp/deck.json \
    --bulk-data /tmp/scryfall-bulk/default-cards.json \
    --out /tmp/cards.pdf
```

### Step 4 — Render tokens

```bash
proxy-print --kind tokens \
    --deck /tmp/deck.json \
    --bulk-data /tmp/scryfall-bulk/default-cards.json \
    --out /tmp/tokens.pdf
```

The two render passes are intentionally separate so the user can re-print
just one half if a deck change only affects cards (or only the token list).

## CLI reference

```
proxy-print --kind {cards,tokens} --deck DECK.json --out OUT.pdf [options]
```

| Flag | Required | Default | Notes |
|------|----------|---------|-------|
| `--kind`                       | yes | —      | `cards` or `tokens` |
| `--deck PATH`                  | yes | —      | parsed deck JSON |
| `--out PATH`                   | yes | —      | output PDF path |
| `--bulk-data PATH`             | no  | auto   | Scryfall bulk JSON; auto-resolves the cached default |
| `--page-size letter\|a4`       | no  | letter | page size |
| `--copies N`                   | no  | 1      | extra copies of every card / token |
| `--include-sideboard`          | no  | on     | cards mode; flip with `--no-sideboard` |
| `--no-sideboard`               | no  | off    | cards mode |
| `--report-art-coverage`        | no  | off    | tokens mode; emits per-token JSON to stderr |

Exit codes: `0` ok, `1` bulk missing/stale, `2` deck JSON invalid, `3` output
unwritable, `4` rendering error.

## Layout

Cards and tokens share one render template; the proportions adapt based on
how much oracle text the card has.

```
┌───────────────────────────────┐
│ ╔══════════════════════════╗  │  name banner
│ ║ NAME              {COST} ║  │  (cost omitted for tokens)
├─╚══════════════════════════╝──┤
│         (ASCII art)           │  art region (proportional)
├───────────────────────────────┤
│ ╔══════════════════════════╗  │  type banner
│ ║ Type — Subtype       {C} ║  │
├─╚══════════════════════════╝──┤
│ oracle text                   │  oracle region (proportional)
│                       ┌─────┐ │
│                       │ P/T │ │
└───────────────────────┴─────┴─┘
```

Card geometry: 2.5″ × 3.5″. Grid: 3 × 3 = 9 per page on Letter or A4.

## ASCII art catalog

Art comes from two tiers, with the **attributed catalog** layered on top
of a hand-curated **local catalog**:

- **Local catalog** — ships in the repo at
  `mtg-utils/src/mtg_utils/data/card_art/`. One `.txt` per card subtype
  (creature / artifact / enchantment / land subtypes) plus card-type
  fallbacks (`creature.txt`, `artifact.txt`, `enchantment.txt`,
  `land.txt`, `sorcery.txt`, `instant.txt`, `planeswalker.txt`) and an
  ultimate `_generic.txt`. Hand-curated ASCII, no attribution carried.
- **Attributed catalog** — user-populated cache at
  `$MTG_SKILLS_CACHE_DIR/attributed-art/` (default
  `~/.cache/mtg-skills/attributed-art/`). Files carry a 3-line header
  noting title, source, and license. When art comes from here the
  proxy renders `art by <Name>` in the lower-left footer, on the same
  row as P/T (where real MTG cards put the artist credit).

### Lookup chain

For each card, lookup walks slugs in order — subtypes first, then
card-types, then `_generic`. For each slug it tries the attributed
catalog first, then the local catalog. First hit wins:

1. Parse `type_line`. For each subtype after `—`, in order
   (`Vampire Knight` → `vampire`, then `knight`):
   - try `attributed/<sub>.txt`
   - try `local/<sub>.txt`
2. If no subtype matched, walk card-type words (skipping meta words
   like Token / Legendary / Snow / Tribal / Basic). For each card-type:
   - try `attributed/<card-type>.txt`
   - try `local/<card-type>.txt`
3. Final fallback: `local/_generic.txt`.

This per-slug interleaving (instead of attributed-tier-then-local-tier)
means a hand-curated local Vampire beats a generic attributed Creature,
which is usually what you want. See
[`docs/adr/0006-attributed-art-catalog.md`](../docs/adr/0006-attributed-art-catalog.md).

Art is **P/T-independent** by design — every Soldier token shares
`soldier.txt`; the P/T appears as text in the proxy.

### Populating the attributed catalog (one-time-ish)

The attributed catalog ships **empty**. Populate it with `fetch-art`,
which pulls every MTG subtype from Scryfall's catalog endpoints, mines
asciiart.eu category pages for candidates, scores by target 20×10 (hard
cap 30×13), and writes attributed `.txt` files with the 3-line license
header that `proxy-print` knows how to read:

```bash
fetch-art
```

HTTP responses are cached on disk for 7 days under
`$MTG_SKILLS_CACHE_DIR/ascii-art-fetcher/`, so re-running is cheap. Add
`--report-missing` to see every subtype that had no fitting candidate —
those fall through to the local catalog at render time.

Subtypes that are MTG-only mechanics or set / plane names (Treasure,
Saga, Innistrad, etc.) are deliberately skipped; the local catalog
handles them.

### Token source vs artist credit

Both render in the same lower-left footer slot. If a token has both a
"from: X" source and an artist credit, the token source wins — the
in-art **signature** (the artist's initials embedded inside the ASCII
itself) is preserved verbatim during fetch and already satisfies
asciiart.eu's FAQ attribution requirement. The explicit "art by X"
footer is courtesy on top of that.

## Interpreting `WARN:` output

`proxy-print` writes warnings to stderr but exits 0. Two patterns to
recognize:

- `WARN: missing from bulk: <name>` — Scryfall's cached bulk doesn't
  know this card. Most common cause: a flavor name like
  "Paradise Chocobo" (which is the FIC printing of "Birds of Paradise").
  The user should check the source list and fix the name, or refresh
  bulk data if it's a brand-new set.
- `WARN: token id <id> from <source>` — a card's `all_parts` references
  a token id not in the local bulk. Should be rare; safe to ignore.

Don't escalate either case automatically. Tell the user which cards
were skipped and continue.

## Common pitfalls

- **Don't paraphrase oracle text.** If the rendered PDF has truncated
  oracle text, fix the layout (the renderer auto-shrinks font from
  9.5pt down to 6.5pt) — don't edit the text content.
- **Don't add tokens manually.** If a card "should" make a token but
  doesn't show up in the rendered tokens.pdf, that's because Scryfall's
  `all_parts` doesn't link it. Custom / homebrew tokens are out of scope.
- **Don't run `download-bulk` reflexively.** It downloads ~500MB. Only
  refresh when `proxy-print` exits with code 1 telling you to.
- **Don't merge the two PDFs.** They're separate by design — tokens stay
  off to the side during play, cards go in the deck. The user almost
  always wants to print or replace them independently.

## Limitations

- Custom / homebrew tokens not in Scryfall are skipped silently.
- Image-based proxies (Scryfall art) are not supported in v1.
- Cut guides / crop marks are not drawn.
- Double-faced card backs are not rendered (only the front face appears
  on the proxy; both faces' oracle text is concatenated).
- Symbol-font mana cost rendering is out of scope; mana costs use the
  Scryfall-brace form (e.g. `{2}{B}{R}`).

## Cross-skill use

- **deck-wizard** can shell out to `proxy-print` after a tuning session
  to ship a printable artifact alongside the deck JSON.
- **cube-wizard** consumes parsed cube JSON, which is shape-compatible
  with parsed deck JSON for `proxy-print`'s purposes (commanders +
  cards lists, no sideboard).
- **lgs-search** is independent — proxies are for print-at-home, not
  sourcing.
