# Defer single-caller helper extractions until a second caller appears

Per LANGUAGE.md (`improve-codebase-architecture` skill): "Two adapters =
real seam. One adapter = hypothetical." We apply the same rule to
extracted helpers: a function with one production caller is a
hypothetical seam, not a real one. Extracting it doesn't unlock leverage,
it just adds an indirection layer.

This came up concretely with the proposed `resolve_gauntlet_archetypes`
helper (would have pulled the 23-line if/elif/else block out of
`gauntlet_main` into its own function). Originally surfaced as a
deepening candidate ("three documented input paths in cube-wizard
SKILL.md") but the prose paths converged to ONE Python caller. The user
correctly pushed back; we superseded it with a deeper unification of
gauntlet archetypes with `stated_archetypes` (see ADR-0002).

**The rule going forward:** when a deepening candidate's only argument
is testability or "documented as a feature," apply the deletion test
honestly. If the function has one caller and inlining costs less than
30 LOC, leave it inline. Re-evaluate when a second caller appears.
This avoids churn for hypothetical leverage and keeps the call-graph
shallow where the actual code is shallow.

**Exceptions worth keeping:** a pure function whose body is a multi-tier
spec a reader needs to understand independently (e.g., `pick_best_listing`
with its 6-tier precedence) earns extraction even with one caller —
*readability* of the named spec is the leverage, not call-site reuse.
That distinction is the one to apply, not "is it pure".
