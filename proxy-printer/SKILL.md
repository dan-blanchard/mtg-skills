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

Art lives at `mtg-utils/src/mtg_utils/data/card_art/`, one `.txt` per
card subtype (creature subtypes plus artifact / enchantment / land
subtypes). Plus card-type fallbacks (`creature.txt`, `artifact.txt`,
`enchantment.txt`, `land.txt`, `sorcery.txt`, `instant.txt`,
`planeswalker.txt`) and an ultimate `_generic.txt`.

Lookup is the same for cards and tokens:

1. Parse `type_line`. Subtypes after `—` are tried in order
   (`Vampire Knight` → tries `vampire.txt` first, then `knight.txt`).
2. If no subtype matched, iterate card-type words (skipping non-art
   words like Token / Legendary / Snow / Tribal / Basic) and try
   `<card-type-slug>.txt`.
3. Final fallback: `_generic.txt`.

Art is **P/T-independent** by design — every Soldier token shares
`soldier.txt`; the P/T appears as text in the proxy.

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
