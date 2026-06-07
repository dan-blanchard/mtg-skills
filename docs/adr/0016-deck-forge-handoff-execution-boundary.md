# deck-forge handoff buttons split by a run-here / session execution boundary

The Export tab's "Hand off to other tools" section listed four downstream tools as
copy-paste command strings (`proxy-print … deck.json`, `lgs-search deck.json`,
`deck-strat deck.json`, `playtest-goldfish deck.json`). The ask: make them **buttons
that perform the action**. But the four are not the same kind of work, and the backend
hub had — by design — never executed anything (it is analysis + canonical state + the
message bus to the Session-agent, ADR-0013), and it must never run an LLM itself
(interactive-skill-only, ADR-0010 / the zero-cost rule).

**Decision.** Handoffs split into two tiers by a single boundary — *does this need
reasoning or a headed browser?*

- **Run-here handoffs — `playtest-goldfish`, `proxy-print`.** These are thin CLIs over
  functions in `mtg_utils`, the shared package the hub already imports. The hub runs
  them **in-process**: goldfish returns a report rendered inline; proxies render a PDF
  served as a download (`reportlab` is added to deck-forge's deps for this). No
  subprocess, no API key, no billing — pure local compute, the same class as
  `mana_audit`. They work with **no session attached**.
- **Session handoffs — `deck-strat`, `lgs-search`.** `deck-strat` needs a Claude session
  to author the guide; `lgs-search` drives interactive headed Playwright browsers.
  Neither can run in the hub without an API key. Their buttons enqueue an agent-bridge
  request (a new handoff `kind`) that the **attached Session-agent** fulfils by invoking
  the skill; the buttons grey out with a hint when no session is attached.

**Why not uniform (route all four through the session).** Purer — the hub would stay
execute-nothing — but it forces a session for goldfish/proxies (which need no
reasoning), breaks the documented agent-less mode for non-Claude-Code users, and lands
those results in the terminal/filesystem instead of in the browser. The whole value of
a one-click button is the instant in-page result; tier 1 delivers that, and tier 1 is
provably billing-safe because no LLM is involved.

**Why not let the hub shell out to all four.** The reverse temptation — have the hub run
`deck-strat`/`lgs-search` headlessly too — would require an API key in the backend,
violating ADR-0010 and the zero-cost subscription rule, and would duplicate the
reasoning the live session already provides for free.

**What this stops re-suggesting.** Don't route goldfish/proxies through the session "for
consistency" (it breaks agent-less use). Don't make the hub execute `deck-strat` or
`lgs-search` (it breaks billing safety). The dividing line is *pure compute vs.
reasoning/browser*, not *first-party vs. third-party* — new downstream tools get sorted
into a tier by that test.
