# deck-forge imports external lists as in-process hub compute — the inbound mirror of run-here handoffs

deck-forge had no way to bring an existing list INTO the hub. The only ways to populate a
session were one-card `/api/deck/add`, an empty `/api/builds/new`, or reopening an
already-saved build (`/api/builds/load`); SKILL.md Phase 1 said "`parse-deck` the user's
list, then load it," but no endpoint ingested a parsed deck. The user asked to import
existing decks and collections. ADR-0016 had just established that the hub may run
pure-compute `mtg_utils` functions in-process (goldfish, proxies) but must never run a
reasoning/browser skill itself (ADR-0010, the zero-cost subscription rule).

**Decision.** Import is **browser-native pure compute on the hub**.

- A new endpoint accepts raw text — pasted, or read client-side from an uploaded file
  (collections are usually Untapped/Moxfield **CSV files**, so upload matters) — plus a
  format, and runs `parse_deck` (and, for collections, `mark_owned` / `find_commanders`)
  **in-process**. No subprocess, no LLM, no API key — the same class of work as
  `mana_audit` or the run-here handoffs.
- It is the **inbound mirror** of ADR-0016's outbound handoffs: 0016 routes a *finished
  deck out*; import brings *external data in*. The same boundary test — *pure compute vs.
  reasoning/browser* — sorts both.
- A **deck** import always mints a NEW build (never overwrites the live session) and never
  guesses a commander; an unmarked list lands as a pile the user promotes from.

**Why not session-agent-mediated.** Routing the paste through the agent bridge (user
pastes in chat → agent runs `parse-deck` → adds cards) would burn session turns on
mechanical parsing, fail when no session is attached, and deliver the result indirectly.
Parsing a list the *user supplied* is not the agent naming a card from memory, so the
Iron Rule (ADR-0009) does not require — or benefit from — agent involvement.

**What this stops re-suggesting.** Don't add an "agent imports the deck" path because
parsing "feels like reasoning" — it isn't; it's `parse_deck`. The hub running
`parse_deck` / `mark_owned` / `find_commanders` is squarely inside the ADR-0016 boundary,
not a violation of it. See the **Import** glossary term in `deck-forge/CONTEXT.md`.
