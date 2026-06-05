# deck-forge's reasoning layer never names cards from memory

deck-forge's whole value over deck-wizard is trustworthy suggestions. deck-wizard
lets the agent reason about cards from training-data memory, which produces two
failure modes the user explicitly called out: oracle-text overgeneralization
(*Tinybones, the Pickpocket* steals only from **opponents'** graveyards, but the
agent "remembered" generic graveyard-matters and added wasted self-mill), and
novelty bounded by what the model half-recalls.

**Decision.** The Session-agent may never name, recall, or assert the existence of
a card. It produces only **patterns, searches, and judgments**; the Deterministic
core (`card_search` + `theme_presets` + Commander Spellbook) names the actual cards.
Concretely:
- Novelty: the agent dreams a Synergy *pattern* ("this commander rewards creatures
  entering — look for cheap mass-token-makers and 'put creatures from library onto
  the battlefield' effects in these colors"); code runs the search; every surfaced
  Candidate is a real Scryfall hit.
- Rules accuracy: code hands the agent the full oracle text + Scryfall rulings + CR
  citations; the agent must quote the exact clause before asserting a Signal or
  synergy. A Signal is stored with its scope (Tinybones → "opponents' graveyards
  only"), so downstream search never recommends self-mill.

**Why this is the right call.** It is the anti-hallucination contract the entire UX
trusts — a user picking cards must believe every Candidate is real and every
"why it fits" reflects the actual card. It also turns the assistant's only creative
job into *pattern-dreaming*, where imprecision is harmless (a bad pattern just
returns no good cards), while delegating ground truth to deterministic search. This
is simultaneously the fix for the EDHREC-over-reliance complaint: novelty comes from
patterns, not popularity, without inventing cards.

**What this stops re-suggesting.** Don't add "let the model suggest a few cards
directly to save a search round-trip," and don't let the agent answer "is there a
card that does X?" from memory — always route through `card_search`. If a pattern
can't be expressed as a search, that's a signal to extend the Deterministic core,
not to bypass it.
