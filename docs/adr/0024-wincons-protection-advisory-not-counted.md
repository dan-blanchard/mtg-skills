# Win-conditions and protection are Shape-scaled advisory flags, not hard-counted template roles

The deterministic tuner's **template-deviation** metric counts Spine roles against the
Command Zone template. The obvious move is to add **win conditions** and **protection** as
counted roles alongside ramp / draw / removal — the user assumed they were simply missing,
and a future reader looking at the role set will assume the same.

**Decision.** Keep the **hard-counted** template to the roles the community literature
actually agrees on — lands, ramp, card draw, interaction (targeted removal **and
counterspells**, folded together), board wipes — and treat **win conditions** and
**protection** as **Tier-2 advisory flags**, scaled by the inferred **Shape** (and, for
protection, a voltron / single-big-threat signal), not as fixed counts that drive swaps.
Win-conditions are detected heuristically (Commander Spellbook combos ∪ a small labeled
oracle-pattern set) and surfaced as "≈N closers detected," never as a precise count.

**Why this is the right call.** Verified multi-source research (Command Zone Ep. 658,
EDHREC, Cardsphere, Manacove, Draftsim, et al., each claim cross-checked against a second
source) found a genuine **fork**: the dominant template *deliberately* does not budget
win-cons or protection (they emerge from the flexible "Plan Cards" remainder), while a
reputable minority budgets win-cons (~3) and protection (~5–7) for every deck. The numbers
that do exist scale by **archetype, not by power bracket**, and counterspells are classed
as *interaction*, not a separate protection bucket, in the dominant template. Hard-coding
one contested number as a counted role would be **false precision** the sources don't
support. Advisory flags (e.g. "≈2 closers detected; control decks usually want 2–4") stay
honest about the disagreement while still catching the real failure modes: "explosive but
can't close" (the win-con floor + the Efficiency curve/closing check) and an
under-protected combo / voltron deck.

**What this stops re-suggesting.** Don't "finish" the template by promoting win-cons or
protection to hard-counted roles — their absence from the counted set is deliberate,
grounded in a real literature fork, not an oversight. Don't split counterspells out of
interaction into a separate protection role for template counting. If a new consensus
emerges that settles the fork, revisit it *here* — don't silently encode a number.

**Amended by ADR-0030.** A *bracket-constraint* gate (Game Changers / mass land denial /
extra turns / two-card combos, gated by a chosen target bracket) was later added to the
tuner. It does **not** reintroduce bracket-scaled role bands — role density stays
Shape-scaled per this ADR. The two are different questions: *permission* (what a bracket
forbids) vs *density* (how much scaffolding a Shape wants). See ADR-0030.
