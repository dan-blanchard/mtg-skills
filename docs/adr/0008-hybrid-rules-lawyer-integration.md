# Hybrid rules-lawyer integration: CLI for routine, Skill tool for nuance

deck-strat needs to verify every rules-adjacent claim that lands in a
Strategy Guide (stack timing, replacement effects, commander-zone
behavior, keyword interactions, intervening-if clauses). Three plausible
integration models existed:

1. **CLI-only.** Re-declare `rules-lookup` / `rulings-lookup` /
   `download-rules` in deck-strat's `pyproject.toml`; shell out for
   every claim. Matches cube-wizard's pyproject re-declaration pattern
   verbatim. Loses access to rules-lawyer's skill-level discipline
   (Phase 1 classification → Phase 2 lookup → Phase 3 escalation;
   subagent spawning for section-slice reads on multi-rule reasoning).
2. **Skill-only.** Every rules question routes through
   `Skill(rules-lawyer, ...)`. Maximum discipline; ~5× the latency of
   a CLI call and noisy in the conversation log. Wrong fit for
   routine keyword lookups (`rules-lookup --term trample` is a single
   round trip).
3. **Hybrid.** CLI for routine (term / rule-number / narrow grep
   lookups during the rules verification pass and the Rules Audit
   subagent). Skill tool for nuanced multi-rule questions surfaced
   during drafting (e.g., "does this trigger's intervening-if check
   on resolution interact with the replacement effect on Helm of the
   Host?"). Mirrors how deck-wizard already integrates rules-lawyer
   (`cut-check --cite-rules` for routine keyword citations; Skill-tool
   invocation reserved for nuance) and matches cube-wizard's
   documented pattern in `CONTEXT-MAP.md`.

We chose hybrid (option 3). The trade-off is real: hybrid means two
callers must know when to escalate. We accept that cost because:

- **Routine claim verification dominates.** A Strategy Guide cites
  ~20-40 rules-adjacent claims; the vast majority resolve with a
  single `rules-lookup --term <keyword>` or `--rule <n>` call. Routing
  every one through `Skill(rules-lawyer)` would noise up the
  conversation log and cost ~5× the latency.
- **Nuance failures are catastrophic.** A wrong layer / replacement /
  stack-ordering claim makes the entire guide untrustworthy (see the
  session that motivated this skill: a "High Market saves your
  commander from exile" line that was structurally wrong about CR
  903.9). Multi-rule reasoning needs rules-lawyer's escalation
  discipline, including its option to slice the CR by section and
  spawn a specialist subagent.
- **Symmetry with cube-wizard.** cube-wizard's tuning pipeline
  already invokes rules-lawyer via the Skill tool for trigger-
  interaction / timing / replacement-effect questions during
  archetype review. The hybrid pattern is the established norm,
  not a new convention.

The mechanical escalation rule is in deck-strat's SKILL.md:

> Default to `rules-lookup` (CLI) for any claim that can be verified
> from one rule number, one glossary term, or one narrow regex. Escalate
> to `Skill(rules-lawyer, ...)` when (a) the claim spans two or more
> rules and their interaction is the load-bearing part, (b) the relevant
> rule's prose is thin and a section slice is needed, or (c) the
> verification depends on reasoning about layers, replacement-effect
> ordering, or stack timing across triggered + activated abilities.

Both the Phase 3 rules verification pass and the Rules Audit subagent
follow the same rule. The subagent has explicit access to both the CLI
(via `Bash`) and the Skill tool, with the same escalation directive.

**Why this is hard to reverse:** every "verify a claim" path in
deck-strat depends on this choice. Switching to CLI-only or Skill-only
later would mean rewriting both the verification pass and the audit
subagent charter — not a one-line change.

See `deck-strat/CONTEXT.md` for the Rules verification pass / Rules
Audit vocabulary. See `CONTEXT-MAP.md` for the cross-skill relationship
listing.
