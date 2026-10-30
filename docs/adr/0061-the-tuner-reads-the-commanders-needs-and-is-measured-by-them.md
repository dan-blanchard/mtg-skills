# The tuner reads the commander's needs, and is measured by them

The 2026-10-30 review of the tuner against the precon upgrade guides
(`docs/plans/tuner-holistic-review-2026-10-30.md`) found the add side failing for
one reason above the others: the guides' adds satisfy the commander's own
conditions 44-83% of the time, the tuner's 0-10%. Winter, Cynical Opportunist
asks for four card types among the cards in your graveyard; Mirko, Obsessive
Theorist for surveil; Killian, Decisive Mentor for Auras on creatures that
attack. The tuner read a commander only through its lane idents, which project
all three onto an umbrella lane ("Your graveyard", 10% of the pool; "Combat",
6%) whose most-played cards became the adds. The conditions were already in the
Card IR (Winter's delirium is a `QuantityComparison` over
`DistinctCardTypes(Zone(Controller, Graveyard))`); nothing read them. The same
review found the 25-precon evaluation over-fitted: 210 measured variants gated on
±1-2 add deltas took the 25 from 8 to 121 guide adds while the held-out ten went
from 24 to 37.

**Decision.** `_analysis/commander_need.py` reads a commander's needs off its
concept trees and says whether a card supplies one; the scoreboard measures a
tune by it before any policy change does, and the tune's reach pages are built on
the same read (the plan: `docs/plans/tuner-plan-2026-10-30.md`).

- **Four kinds of need, one predicate.** *Events* the commander's triggers fire
  on (`trigger_def_event`, the trigger's typed filters: surveil → surveil
  outlets, a creature token leaving → token makers, an enchantment entering →
  enchantments, creatures enchanted by an Aura attacking → Auras); *conditions*
  its ability conditions compare (`DistinctCardTypes` of the graveyard → a
  two-type card or a self-mill; a zone or object count → what raises it);
  *resources* its doer idents produce (tokens of a kind, energy, +1/+1 counters →
  the payoffs that consume them, `metrics._cares_keys`); *redundancy*, the cards
  that do what the commander does (its doer idents: more goad under Nelly Borca,
  more mill under Winter); and the *payoff* idents with no trigger of their own
  (a tribe its filters name, Felothar's toughness over power). A `Need` is a set
  of ident / key / type-line tests and an optional record predicate;
  `satisfies(card, need)` is the one test. A commander's own creature types and
  card types are what it is, not what it asks for (the membership floor is left
  out; a tribe counts only when the commander's filters name it).
- **Specificity decides what counts.** A need more than `BROAD_SHARE` (10%) of
  the commander-legal nonland pool supplies is broad ("instants and sorceries"
  under a spellslinger, 24%; "enchantments" under an enchantress, 12%) and is
  reported, not scored. The 2026-10-30 run over the 35 audited precons: specific
  needs are supplied by 43% of the guides' adds and 38% of the tune's; needs at
  most 2% of the pool supplies by 19% and 16%; per deck the gap is where the
  review found it (Silverquill 54% / 17%, Revenant Recon 53% / 40% and on the
  2% needs 38% / 0%, Grand Larceny 15% / 0%).
- **Measurement before policy.** The scoreboard (`precon-audit/scoreboard.py`)
  gains a PLAN line — plan-consistent adds, the tune's and the guides' — a
  page-level recall (`misses.py` records each guide add's best position on the
  search pages of its kind: a template job's row search, else the theme pages;
  recall@10 / @30 is ranking and reach apart from the swap cascade and the
  budget), a job-equivalent line (the near-miss job half, the generic guide
  rows' job-level score) and a mana-base line (the guides' land rows, exact or
  the same colour pair untapped). The recipe tunes with `target_bracket=3`:
  every tune aims at bracket 3 or higher, so the gate's Game Changer ceiling
  applies and the guides' Game Changer adds count. The held-out set is twenty
  precons, never used to design a rule. A policy change ships when page
  recall@30 rises on the 25 and does not fall held-out, plan-consistency does
  not fall on either, the held-out tune adds do not fall, cuts fall ≤2 / ≤1 and
  consensus adds do not fall — in place of the ±1-2 add gates.
- **The read is pure.** The commander's records and trees in, needs out; no
  play-rate, no deck context. The tune's need pages (the plan's Phase B) rank
  inside a page by play-rate as every theme page does; the predicate is the fit.

**Consequences.** A commander's distinctive mechanic has a read of its own, so a
surveil outlet can be asked for under Mirko without the "surveil matters" lane
reaching the viable floor, and a guide's Invasion of Ixalan under Winter is
scored as on-plan where no lane names it. Needs the IR can express but this read
doesn't yet (a reanimation target's power under Mirko; a cost reduction's
subject) score nothing rather than something wrong. The baselines before and
after the read were measured on both sets (`~/mtg/tuner-work/w41/`), and the
audit report records them.

**Amendment (2026-10-30, Phase B shipped).** How a need page is reached decided
everything. Sharing the theme adds with the need pages by depth cost the mains'
guide hits for cards the guides never named (three shared adds per page: the 25
121 → 109 guide adds, the held-out 20 80 → 76; one: 114 and 78). What ships is
**routing**: a theme cut that itself supplies a commander need is upgraded off
that need's page (`Sourcing.upgrade_spec`; `swaps._NEED_CAP = 0`), so a weak
Aura's slot goes to a better Aura and a cut surveil card's to a better surveil
outlet, and no main loses a slot — 123 and 86 guide adds, consensus +2 and +6,
page recall@30 +20 and +29. Two guards on the read: a tribe the commander pays
off opens no need page (the tribal avenue is that page), and a self-growing
commander (Mirko's counter on himself) makes no counters for counter payoffs.
The pages are built once in `tune` (`swaps.need_pages`) because the upgrade
remedy's `Sourcing` lives there. The **specificity-first primary** shipped on top
(`metrics.focus`, `base_rates` from `signals_index.ident_base_rates`): among the
held lanes at least emerging-deep with the carer floor of builders, the rarest
ident per card the deck holds leads; it is viable whatever its depth; a held lane
five times as specific as a kept one does not fold into it. Held-out 86 → 97
guide adds, the 25 123 → 122 with cuts +2. Rejected: a commander-held lane at
main depth as a main whatever share of its feeders care (Living Energy's
Artifacts umbrella took the Energy adds); the fold guard without the builders
floor (Saheeli's Artificers became protected lane doers). The audit report's
"Phase B" section holds every run.
