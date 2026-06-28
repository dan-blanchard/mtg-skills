# Signal membership is strict; archetype adjacency lives in SubAvenues

A card emits a [[Signal]] **only when it literally performs that exact mechanic** —
never because a deck built on that Signal would also want the card. A "create a token
that's a copy of X" card (`CopyTokenOf`) emits `token_copy_matters`, **not**
`clone_matters` ("a permanent *becomes* a copy", `BecomeCopy`), even though a clone deck
genuinely wants it. The two axes are kept separate: **emission = membership** (a clean
truth about *this card*, derived strictly from what it does) and **serve =
`SignalSpec` + `SubAvenue`** (a separate question about what a *deck* on a Signal wants).
Every "and a deck might also reach for…" is expressed as a SubAvenue on the relevant
Signal's serve spec — never as an extra emission. So a clone deck still surfaces
token-copy gear (Helm of the Host, populate) through `clone_matters`'s existing
`_COPY_EXTRA` SubAvenue, while those cards themselves stay out of `clone_matters`
membership.

The trigger was the ADR-0027 #24 cutover's `_recover_clone_creature`, whose `"copy"`
substring regex stamped a `clone` category onto ~125 `CopyTokenOf` cards, putting 31 of
them into both `clone_matters` and `token_copy_matters` membership. Under this decision
that is a false positive on `clone_matters`: those cards do not *become* copies, they
*make* copy tokens. The fix drops the spurious `clone` emission (keeping
`token_copy_matters`); a clone *deck-builder* is unaffected because the want is served by
the SubAvenue layer, not by the cards' membership.

## Considered options

1. **Strict membership, adjacency in SubAvenues (chosen).** Emission means "does exactly
   this mechanic." Cross-archetype wants are serve concerns, modeled once, in the place
   already built for them (`SignalSpec.extras`). Membership stays a reliable, auditable
   statement about a card — which is exactly what archetype detection, the agreement gate
   (ADR-0014), and any future IR consumer need.
2. **Archetype-loose membership** — let a Signal claim cards that are "close enough" that
   its deck wants them. Rejected: it conflates two genuinely different questions, makes
   membership unauditable (every "should X also fire Y?" becomes a judgment call with no
   rule to appeal to), double-counts cards across overlapping archetypes, and duplicates
   the serve fan-out the SubAvenue already provides.

## Consequences

- A clean decision rule for every future "should X also emit Y?" call: if X doesn't
  literally do Y's mechanic, no — put the want in a SubAvenue on Y's (or X's) serve spec.
- Membership becomes audit-able against the actual mechanic (rules-lawyer + real oracle,
  per ADR-0027's Iron Law), independent of any deck-archetype intuition.
- A one-time cleanup: audit existing emissions for the same adjacency-not-mechanic
  violation the CopyTokenOf case exposed (a recovery/detector firing a Signal on a
  related-but-distinct mechanic), move each want into a SubAvenue, and gate the drop
  set-equal-minus-the-false-positives.
- Cross-archetype reach that *was* implicit in a loose emission must be made explicit as a
  SubAvenue if it's actually wanted (e.g. if a token-copy deck should reach for clones,
  that's a clone SubAvenue on `token_copy_matters` — a deliberate serve addition, not a
  free side effect of membership).
