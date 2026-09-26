# mtg-utils Context

The bounded context for the shared `mtg_utils` package. Created lazily (per
CONTEXT-MAP.md) when the ADR-0038 architecture conversation surfaced Card IR
terms no prose pinned down; other term clusters join as conversations resolve
them.

## Language

### Card IR

**Concept overlay**:
The crosswalk's decoration layer over the verbatim phase mirror: per preserved
node position, a `ConceptNode` records what the substrate node *means*
(concept, role, scope, subject) without owning or altering the node itself.
The overlay is ours to write; the mirror is phase's verbatim parse.
_Avoid_: "the tree" alone (ambiguous with the mirror), "annotation" (suggests
optional metadata — lanes read nothing else).

**Substrate purity**:
The invariant that every phase mirror node present before an overlay stage is
present after it, same object identity — no mutation, removal, or
impersonation of phase's parse. Decoration is unconstrained; the substrate is
inviolate.
_Avoid_: "immutability" (the overlay layer is also frozen; purity is about the
*phase* nodes specifically).

**Recovery stage**:
The overlay stage that gives Unimplemented clauses a real reading: it parses
the clause text with the clause grammar and re-decorates the node's
`ConceptNode`, recording which rule fired (`recovered_by`). Substrate-wide —
signal lanes and compat consumers both see recovered readings.
_Avoid_: "supplement" (the old-IR path's envelope around the same grammar),
"synthesis" (adds nodes; recovery rewrites decoration in place).

**Re-decoration**:
Rewriting a `ConceptNode`'s decoration in place — new concept/scope/subject,
same underlying mirror node — so a recovered clause keeps its true ability
position and substrate purity holds by construction. The recovery stage's only
write operation.
_Avoid_: "node replacement" (the mirror node is never replaced), "patching"
(vague).

**Clause grammar**:
The shared pure text→structure clause parser (prefix peeling + verb dispatch)
that turns an English clause phase couldn't parse into a structured reading.
One core, one emitter since ADR-0039 step 7: the recovery stage re-decorates
`ConceptNode`s (the old-IR supplement's `Effect.category` re-tag emitter died
with the legacy builder). The substrate's gap-filler; rules retire as phase
learns their clauses.
_Avoid_: "the supplement parser" (names the dead old-IR envelope, not the
shared core), "regex bridge" (the interim per-key marker pattern this
replaces).

**Token allowlist**:
The recovery emitter's set of admitted grammar tokens — the measured rollout
frontier. The grammar may parse more than the allowlist admits; a token enters
only with corpus measurement and pinned tests behind it.
_Avoid_: "feature flag" (it's per-token and permanent-until-superseded, not an
on/off switch).

**Reference arm**:
A tree-synthesis arm for a cares-about *reference* — text that names a
mechanic without performing it (so there is no effect clause to parse). The
irreducible remainder of synthesis after effect clauses moved to the recovery
stage. Its synthesized `synth_<key>` concept is the reference's own vocabulary
(there is no effect concept for it to become), so a lane reading its structural
arm OR that concept is the stable two-arm shape (ADR-0038, 2026-09-13 note).
_Avoid_: "marker arm" (the retired interim pattern where effect clauses also
got synthesized markers), "placeholder" for a reference concept (nothing is
pending behind it).

**Text-only face tree**:
A zero-unit `ConceptTree` for a multi-face card half phase never emits ANY
record for at all (no node to recover — a fourth residue class the recovery
stage can't reach). Built from the bulk (MTGJSON) record's own `card_faces`
text: `units=()`, `oracle` set to the bulk face text verbatim. Carries no
typed substrate, so it feeds only the b12 byte-mirror lanes and
`tree_synthesis`'s bucket-B arms that read `tree.oracle` directly — never a
structural (unit-scoped) lane, which has nothing to read on an empty tree.
_Avoid_: "synthesized tree" (nothing is synthesized — the whole tree is
untyped bulk text, not a decorated phase node), "phase tree" (there is no
phase record behind it at all).

**Dropped clause**:
A clause phase parsed AROUND: the card's tree exists, but this clause left no
node at all — not even an Unimplemented residue — so it survives only in the
oracle text. The third residue class (after Unimplemented residue and the
missing face), and the one bucket-(c) synthesis exists for. A clause phase
built a HOLLOW static def for (`affected: SelfRef`, an empty `modifications`
list, the line kept in the def's `description` — `ConceptTree.hollow_statics`)
is not dropped: phase tried and failed, an upstream parse failure. Neither is a
MISPARSE — a clause phase emitted as a wrong typed node (a mis-scoped grant, a
defaulted destination): phase tried and failed there too.
_Avoid_: "parser failure" (phase didn't fail; it silently omitted),
"parser-blocked" (the text is still reachable — nothing blocks reading it).

**Straggler**:
A clause the shared clause grammar cannot tokenize *yet* — the grammar's
growth frontier, not a permanent gap. A straggler card is served by a
ledgered bridge until its grammar verb lands, at which point the bridge's
gap-gate finds structure and stands down.
_Avoid_: "unparseable" (only unparsed-so-far), "blocked" (nothing waits on
anyone else — the verb is ours to write).

**Ledgered bridge**: A corpus-bounded text read serving an enumerated straggler
set: gap-gated (it runs only where the tree provably lacks the clause), ledgered
(each ties to a named grammar TODO or upstream report), and self-retiring (the
gap-gate stands it down the moment structure arrives; the convergence check
makes any laggard visible). Since ADR-0048 the row also owns its emission (key +
scope): one `bridge_signals` lane fires every row, no lane names a bridge id,
and retiring a bridge is deleting its row. A bridge restores prior serving only
— what the legacy IR served, or what an upstream phase regression took away at a
bump — never beyond-prior breadth. Same matching technology as a regex detector;
opposite scope and lifecycle. A row's KIND names what phase left for its clause
— a missing face (a text-only tree), a dropped clause (no node), an upstream
parse failure (a residue, a hollow static, an `Unrecognized` node's text, or a
misparse) or a straggler (our grammar's frontier) — and `test_bridge_ledger`
checks the kind against every pin's evidence: a dropped clause's pin may carry
no parked text that states the clause, a parse failure's must (unless the row is
a listed misparse). A row whose match reads structure rather than the clause's
words can't be judged by text, so it is listed as structure-matched and judged
structurally instead (a dropped clause's gap keys on no residue text; a parse
failure's does), and a listing goes stale the moment text can locate the clause.
A kind goes stale when a bump changes what phase leaves (Warp's pay-life
keyword: dropped at v0.20.0, a residue by v0.94.0). The ledger is not the only
home for a phase workaround: every workaround for a phase misparse is either a
ledger row or carries a `retirement_canary` test that fails RETIRE-READY when
phase fixes the parse, so none outlives its cause unseen.
_Avoid_: "regex bridge" (the retired per-key marker pattern), "fallback"
(hides that each instance is enumerated, pinned, and scheduled to die).

**Graduation**:
The event where a substrate improvement (recovery row, grammar verb, phase
fix) closes a gap some gap-gated arm existed for: the arm stands down
automatically and its MECHANISM pins must be rewritten to assert the new
structural direction — membership never changes. Suppressing the structural
read to keep an old pin green is never the fix.
_Avoid_: "regression" (the pins fail because the substrate improved).

**Corrected tree**:
The concept tree every structural reader receives — one per phase face record (plus
the predefined-token and text-only face trees), strict-loaded, overlaid (recovery
included) and run through the overlay-correction stage by the one owner,
`_card_ir.trees` (`face_tree` / `build_trees` / `trees_for`, ADR-0047). The compat
`Card`, the tuner's commander-cost and grant reads, the rate metric, the limiter
discounts and the removal-answer walk read it; none re-applies a stage.
_Avoid_: "raw tree" for what a reader gets (no reader sees an uncorrected tree),
"the tree" alone (ambiguous with the signal tree).

**Signal tree**:
A corrected tree with the signals-only tree-synthesis stage applied —
`_analysis.signal_trees.signal_trees_for`, the only shape a lane or a theme-preset
concept predicate reads. Synthesis appends one synthetic unit of reference-arm nodes
and never touches a phase node, so a signal tree is a superset of its corrected tree;
a structural reader never sees one (ADR-0038's signals-only wiring).
_Avoid_: applying `apply_tree_synthesis` at a call site (the owner's second product
does it, once), "synthesized tree" for a text-only face tree.

**Gap predicate**:
The read a gap-gated arm (a recovery row, a synthesis arm, a ledgered bridge, a
membership-floor mirror) makes to decide the substrate lacks the structure it would
otherwise read from text — one of the presence reads `ConceptTree` owns (`has_typed`
/ `has_concept` / `has_static_mode` / `has_trigger` / `has_residue` /
`is_text_only`, over `iter_typed`; ADR-0047), or the residue text they expose
(`residues`; `effect_residues` for a residue in an ability's effect position; and
`hollow_statics` for a static def phase built but left empty). A gate that must
judge a node against its own ability unit (a trigger's mode and condition, a
static's mode fields, an effect's owning wrapper) takes the unit from
`iter_units(*origins)` and reads it through the unit's own `iter_typed` /
`static_defs` / `effects`. A gate composes them; it never re-walks the tree in its
own idiom, so "the tree already carries X" means the same thing in every tier. A
text bridge's gap keys on the residue that carries ITS clause, so a phase fix to
that line reads as RETIRE-READY even when unrelated residue stays behind. Both rules
are checked for every ledger row (`test_bridge_ledger`): a gap's source, followed
through its module-local helpers, may not touch `.units`, `iter_typed_nodes` or
`iter_static_defs`, with no exemptions (a gap needing context the reads don't expose
gets a new presence read); and a gap that reads residue text must go False once the
pin's own clause is fixed while an unrelated line of the same residue class stays
parked.
_Avoid_: a per-arm `for unit in tree.units: for n in iter_typed_nodes(unit.node)` walk
(the retired idiom), "fallback condition" (a gate is a structural fact, not a default).

(The "KEPT twelve" — twelve keys that once lagged on a legacy serving arm —
are ordinary manifest-served lanes since ADR-0039 completed; the surviving
distinction, where one exists, is a per-key ledgered bridge or text mirror
noted in `lanes/` itself. See archived ADR-0039 for the promotion record.)

### Formats

**Format**:
The frozen value that answers every question about one deck format — legality of a
record (with the Competitive Brawl override and the Arena-pool gate folded in),
commander eligibility, the media it is played in and the default, whether a game
in a medium is multiplayer and at what starting life, the deck size and which sizes
a medium may choose, the CR citation for that size, and what a medium implies: the
cost mode (USD or wildcards) and the candidate pool a card search draws on (paper
printings for a paper build, Arena's for a digital one — `paper_only`, which follows
the medium and is separate from the medium-independent Arena-pool gate). Resolved once (`FORMATS[name]`, `get_format`, `Format.for_deck`,
`HydratedDeck.format`) and never re-derived from a table at a call site (ADR-0045).
_Avoid_: "format config" (the retired flag table), "legality key" as a caller-side
concept (the `Format` reads it; callers read a status).

**Family** (`Format.family`):
Which shape rules a format follows — `commander` (a command zone, singleton, an
exact size the CR cites), `constructed` (a copy limit and a sideboard over a size
that is a minimum, CR 100.2a), or `limited` (a build bounded by an opened pool over
a minimum size, with no copy limit and no sideboard cap, CR 100.2b). The switch
every family decision reads in the hub, the tuner and the SPA (served in the format
table with the facts it implies: `has_commander`, `pool_bounded`, `max_copies`,
`sideboard_size`, `size_is_minimum`, `family_label`); a caller that needs one fact
reads that fact, never the format's name.
_Avoid_: "is commander" string compares on a format id; "the Commander family" as an
allowlist (it is `family == "commander"`).

**Pool-bounded format**:
A limited format (`sealed`, `draft`; `Format.pool_bounded`, ADR-0055): the deck is
built from the cards its `pool` zone holds plus basic lands, so its legality is
pool membership (`legality_audit.check_pool_containment`) and every record reads
`legal` — there is no legality key. `max_copies` and `sideboard_size` are `None`
(as many duplicates as the product included; the sideboard is the unused pool).
_Avoid_: borrowing a constructed format at 40 cards; a faked legality key.

**Primary medium**:
For a format played in both media, the one a new build defaults to: paper for a
paper-defined format Arena also hosts (Standard, Pioneer), digital otherwise (the
Brawl queues). A `Format` field, ordered first in `media`; never a UI default.

**Legality status**:
A `Format`'s answer for one record: `legal`, `restricted`, `banned`, `not_legal`, or
`unreleased` — Scryfall's four plus the pre-release case, which the `Format` can only
report when the caller passes the oracle-level unreleased set (a single record cannot
tell a spoiled card from an Un-card). `restricted` is playable; `unreleased` is a
widening callers opt into, never `is_legal`.
_Avoid_: a bare `legalities[...]` read (the raw MTGJSON key, before the override and
the gate).

**Arena-pool format**:
A format whose card pool IS Arena's (brawl / historic_brawl / competitive_brawl /
alchemy / historic / timeless — the Arena-defined MTGJSON legality keys): a card with
no Arena printing is not legal there even when MTGJSON's key says so. Gated on the
record's oracle-level `arena_available`, medium-independent (the paper Brawl queues
use Arena's pool too). Standard and Pioneer are Arena formats whose pool is defined in
paper, so they are not gated.
_Avoid_: "Arena format" for this (that is `is_arena`, the medium fact), "Arena-only"
(that is `is_arena_only`, no paper counterpart at all).

**Game**:
The game a deck built for one medium is played in — its starting life (CR 103.4;
103.4c Commander, 103.4d Brawl), whether it is a multiplayer table or one opponent, and whether 21
commander damage wins (CR 903.10a — Commander's extra loss rule; Brawl games do not use
it, CR 903.12h). Built by `Format.game(medium)`, never assembled at
a call site: the tuner's closer read and bracket gate are relative to it, calibrated at
the 40-life Commander pod and scaled from there.
_Avoid_: "the game the deck plays" as loose prose (that is this term), "format" for
this (a format has several games — paper Historic Brawl at a 30-life table and Arena
Historic Brawl at 25 one-on-one are one format, two games).

**Ownership** (ADR-0058):
How many copies of a card a collection can put in a deck — a medium rule with one
owner, `Format.coverage(medium, name, needed, owned, *, requested_owned)`. Paper: you
have what you own. Arena: owning four copies covers any quantity (the client's
playset rule). In both, the six basic land types are free — except, in paper, a
**special printing request**. Every wildcard cost, shortfall, owned flag and "N of M
owned" readout asks the owner; nothing compares owned to needed (or to four) itself.
_Avoid_: "owned" for "holds at least one copy" (a deck running 17 Hare Apparent with
one owned is not owned); a per-reader basics filter (the owner decides basics).

**Coverage** (`Format.coverage` → `Coverage`):
The owner's answer for one deck entry: `short`, the copies still to acquire
(`Format.copies_short` is this view), and `covered_by` — `"free"` (a basic land),
`"owned"` (the collection's copies cover every one) or null while any copy is short.
Readers sum `short` and branch on `covered_by`; "free" is never "owned".

**Special printing request**:
A paper deck entry asking for a visually special printing of a basic land type:
a foil or etched finish, full-art, borderless, a showcase or other special frame, a
promo, or a visual promo type (`formats.is_special_basic_request`, judged from the
requested printing's own record). Only that exact printing covers it
(`ownership.requested_printing_owned` → `requested_owned`), so a collection that lists
basics by name only, or not at all, holds none of it. A plain set / collector pin is
not special; Snow-Covered basics are different cards, never a basic's printing; on
Arena no basic request is special (styles are cosmetic).
_Avoid_: treating any set pin as a request; distribution promo tags
(`universesbeyond`, `bundle`) as special.

### Deck acquisition

**Card pool**:
The one owner of the card-data bulk and every index over it (`card_pool.CardPool`,
ADR-0046): the name index (one policy — cheapest priced game-layout printing,
text-bearing preferred, tokens never), the id index that still reaches tokens, the
per-format Arena rarity index, the unreleased-oracle set, the Arena alias map, the
printing indexes and the folded-object resolver. Loaded once per process
(`CardPool.load`), indexes built on first use. Every deck-domain bulk reader reads
through it; none walks the bulk itself.
_Avoid_: "bulk index" (there are seven indexes; the pool is the value that owns them),
"the bulk" for this (the bulk is the file; the pool is what the code asks).

**Hydrated sidecar**:
The memoized join `HydratedDeck.acquire` writes beside a deck JSON
(`deck.json` → `deck.hydrated.json`): full adapter records for every distinct name in
all four zones, keyed inside the file by the deck's content hash, the bulk's identity
and the payload version, so a stale one is unreadable by construction (one carve-out: with no bulk on disk, a
names-only CLI reads a same-deck sidecar whatever bulk wrote it). Visible on
purpose — an agent may Grep it — but never passed to a CLI; the deck path is.
_Avoid_: "hydrated cache" / "cache_path" (the retired SHA-named file the agent had to
thread and re-thread), "the hydrated JSON" as a CLI argument (no CLI takes one).

**Deck-acquisition seam**:
The one place a deck on disk becomes a `HydratedDeck`: `HydratedDeck.acquire`, entered
from every deck CLI through `deck_cli.acquire_for_cli` (the shared `--bulk-data` option,
a `NoBulkError` turned into an actionable exit, dropped names warned once). A CLI that
works on names alone (combo-search, export-deck) enters with records optional.
_Avoid_: "the preamble" (what the twelve CLIs used to re-plumb), "from_paths" (retired).
