# Architecture Decision Records

Active ADRs. Each states its current decision directly — no amendment/addendum
trail to read for current state. Completed migrations and reversed decisions
live in [`archive/`](archive/).

| # | Title | Current state |
|---|---|---|
| 0001 | Split StoreAdapter into StoreSession + LGSAdapter + MarketplaceAdapter | lgs-search per-storefront protocol split over a shared session base |
| 0002 | stated_archetypes is the source of truth for the gauntlet | gauntlet/draft deckbuilding reads the cube's stated archetypes |
| 0003 | lgs-search has no resume path; the sidecar is write-only audit | no session resume; sidecar JSON is audit-only |
| 0005 | Card-data lookups go through bulk_loader; HTTP is fallback only | bulk-primary, Scryfall HTTP per-card fallback |
| 0007 | Attributed art is mined from multiple sources with per-source license stance | two ASCII-art sources, per-source license header; folds in ADR-0006's ships-empty/per-slug-interleave rationale |
| 0008 | Hybrid rules-lawyer integration: CLI for routine, Skill tool for nuance | CLI for routine checks, Skill-tool invocation for multi-rule reasoning |
| 0009 | deck-forge's reasoning layer never names cards from memory | agent proposes patterns; deterministic core names real cards |
| 0010 | deck-forge is an interactive skill, not an Agent-SDK / ACP app | billing-safe interactive-only posture |
| 0011 | deck-forge autosaves and resumes, departing from ADR-0003 | autosave + resume for deck-forge builds |
| 0012 | Deck analysis takes a HydratedDeck, not a (deck, hydrated) pair | one value type, from_session/from_parsed/from_paths constructors |
| 0013 | deck-forge splits into engine / views / transport, not one app module | engine / views / app module split |
| 0014 | deck-forge guards signal keys with an import-time gate, not a registry | gate stands; fed by a hand-maintained manifest, rename+dedup fix in progress |
| 0015 | deck-forge merges Search and Synergies into one Avenue-driven Find surface | one Find surface; guardrail against restoring deleted routes |
| 0016 | deck-forge handoff buttons split by a run-here / session execution boundary | run-here vs session-side handoff execution split |
| 0017 | deck-forge imports external lists as in-process hub compute | import runs in-process, not via a handoff round-trip |
| 0018 | deck-forge collections are global, two medium-keyed slots, derived ownership | slot keyed by medium (paper/arena), not format |
| 0019 | deck-forge partner ranking is widening-primary and strict-tiered | color-identity widening before synergy |
| 0022 | One Scryfall name-index core: NFKD-folded lookups, consistent DFC handling | one keying core (`alias_keys`/`NameIndex`); mark_owned and deck-forge's build_by_name both consolidated onto it |
| 0023 | A shared, deterministic tuning core (HydratedDeck → scorecard + swaps) | the engine `/api/tune` and deck-wizard both call |
| 0024 | Win-conditions and protection are Shape-scaled advisory flags | not hard-counted roles; ADR-0030's bracket gate is a separate permission question |
| 0025 | A commander's signal extraction folds in the referenced objects its plan brings into play | |
| 0026 | deck-forge splits fused payoff/source specs into separate avenues | |
| 0028 | Consume phase-rs (bump the tag); structure the tail in Python — do not fork | |
| 0029 | deck-wizard adopts the shared deterministic tuner | enriched for both consumers |
| 0030 | A target-bracket constraint gate in the shared tuner | orthogonal to the Shape-scaled role template (ADR-0024) |
| 0031 | Signal membership is strict; archetype adjacency lives in SubAvenues | |
| 0033 | MTGJSON AllPrintings is the card-data source | adapter preserves the Scryfall record shape |
| 0034 | The `_matters` sweep: lane names encode role (doer / payoff / wants) | |
| 0035 | Lossless phase-mirror Card IR with a derived concept overlay | anchor ADR for the structural substrate; strangler complete, only serving path |
| 0038 | Unimplemented recovery re-decorates the concept overlay via a shared clause grammar | handles four residue classes (full / none / partial / text-only face trees) |
| 0040 | Granter-aware value in the shared tuner | quality table over playrate |
| 0041 | A deck-specific land band replaces the static lands row and the raw-Burgess gate | |
| 0043 | Adjudicated precision replaces crowd recall as the discovery yardstick | paired-delta acceptance + verdict ledger is the current acceptance rule |
