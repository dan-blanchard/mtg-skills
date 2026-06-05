# deck-forge is an interactive skill, not an Agent-SDK / ACP app

deck-forge needs LLM reasoning, but the user has a Claude Code Max 20x subscription
and requires zero extra spend. The obvious "web app calls an LLM" designs all bill
on top of the subscription: a BYO `ANTHROPIC_API_KEY` web app is metered per token,
and — verified 2026-06-05 — as of **2026-06-15** the headless paths (`claude -p`,
the **Agent SDK**, **ACP** third-party agents, GitHub Actions) draw from a separate
metered credit pool (~$200/mo on Max 20x, then API rates). Only **interactive**
Claude Code (terminal TUI + official IDE integrations) stays on the subscription.

**Decision.** deck-forge is a Claude Code **skill** run in a normal **interactive**
session. The session is the reasoning brain; it spawns a local Backend hub that
serves the browser surface. We deliberately do NOT build on the Agent SDK, ACP, or
`claude -p` — those are the metered paths. The Deterministic core still runs with no
agent attached (deterministic-only mode for non-Claude-Code users). BYO-key remains
a hypothetical future "use without a subscription" fallback, explicitly not v1.

**Why this is the right call.** It is the only architecture that keeps reasoning at
zero marginal cost on a Max subscription. And it composes for free with the product
goal: the user wanted to make every decision (creative agency), so the loop is
genuinely human-in-the-loop — which is exactly what keeps it classified as
interactive ("a human drives each step → interactive; a robot runs unattended →
metered"). The property that satisfies the creative-agency requirement is the same
one that satisfies the billing requirement.

**Known caveat.** That a skill's reasoning *inside* an interactive session is
classified as interactive is strongly indicated (interactive TUI is, and skills run
in it) but not explicitly documented. Confirm with Anthropic support before relying
on it heavily. Interactive-billed reference implementations to study if we ever want
a single-window UI: "Code Quest" (web UI over the interactive `claude` NDJSON
protocol) and the JetBrains "Claude Code with GUI" plugin.

**What this stops re-suggesting.** Don't "make deck-forge embeddable / headless /
hostable as a service via the Agent SDK or ACP" — that silently moves the user onto
metered billing and breaks the core constraint. Any move toward unattended/automated
operation must surface the metered-pool cost first.
