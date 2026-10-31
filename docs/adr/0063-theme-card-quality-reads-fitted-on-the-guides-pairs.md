# Theme-card quality reads, fitted on the guides' pairs

The tuner orders a theme page by EDHREC play-rate because it has had no way to
tell a strong theme card from a weak one. Dan's stance (2026-10-31 grilling,
ADR-0061's third amendment's measurements): reads order the pages, play-rate is
at most a floor and a tiebreak — "less played doesn't necessarily mean worse;
cards are expensive, people haven't realized what the best cards are, people
build different brackets with the same commander". A reads-first theme order
without a quality read (S1: need fit, main lanes served, synergy, then
play-rate) raised the held-out 20's plan-consistent adds by 70 and lost 17 guide
adds to on-plan but weak picks: Fathom Fleet Swordjack over Breeches, five Hydras
over Green Sun's Zenith, Firespitter Whelp over Goldspan Dragon, Banner of
Kinship over Roaming Throne. The missing read says which of two on-plan cards is
the stronger card, from the card's own text, cost and body.

**Decision** (grilled with Dan, 2026-10-31). `_analysis/card_quality/` holds one
read per card type — `creature`, `noncreature_permanent` (artifacts,
enchantments, planeswalkers, battles), `spell` (instants and sorceries) — each a
few features read off phase's concept trees through the shared crosswalk walks
(no new walks were needed), a `QualityRead` with `score(record) -> float | None`
(`None` for a card the read can't see, never a low number), its scores persisted
in a write-back sidecar keyed on the module's content. `card_quality.quality`
picks the read by the front face; `quality_factor` is its logistic, neutral (0.5)
for a card no read sees. Pure: no play-rate, no price, no deck context.

**What the reads are fitted against.** Not play-rate — a read meant to replace
play-rate can't be fitted to it. The guides: `docs/plans/precon-audit/theme_pairs.py`
builds, from a dump of every theme page the design 25's tunes ranked under the S1
order (the `pairs-dump` worktree, `~/mtg/tuner-work/w41/pages-S1/`), one pair per
guide add and each on-plan non-guide card the order placed above it, within the
same page and the same card type, repeated once per guide naming the add
(`w41/pairs.json`). An add that sat deep on a page carries hundreds of pairs, so
each pair is weighted by one over its add's pair count times the guides naming
it: every guide add counts once per guide. A pairwise L2 logistic regression on
feature differences, hand-rounded, measured by **leave-one-deck-out
cross-validated pair accuracy** (pairs of one deck share a preferred card)
against play-rate and mana value on the same pairs. A read ships when it beats
play-rate's accuracy (a type under 40 pairs would have taken hand-set weights;
none did). The held-out 20 is never read.

| type | pairs (guide adds, decks) | read, LODO CV | play-rate | mana value | features kept (log-odds) |
|---|---|---|---|---|---|
| creature | 5,102 (126, 24) | **0.657** | 0.578 | 0.505 | mana per distinct ability +0.08, engines −0.55 each (cap 4), own dies/leaves trigger −1.0, evasion +0.55, defender −2.4, does ramp +0.40 |
| noncreature permanent | 7,973 (115, 23) | **0.717** | 0.650 | 0.501 | cheap (≤ 2, free alt cost = 0) +0.45, doubler (quantity-increasing replacement) +0.55, best job-read score +0.2, abilities beyond the first −0.6 (cap 4), makes tokens −0.9, scaling amount −0.7 |
| spell | 965 (37, 16) | **0.734** | 0.723 | 0.553 | cost −0.2 a mana, tutor +0.6, answer (counter / removal / wipe) +0.35, distinct effects per cast +0.6 each (cap 4), stack abilities beyond the first −0.35 |

Rejected by every fit: body (power + toughness, and per mana), flying and the
other combat keywords, haste, self-protection, flash, cards drawn, an enters
trigger, statics on other permanents, replacement effects in general, legendary,
mana value as a cost on permanents (it fitted with the wrong sign). Both agents'
fit scripts (`docs/plans/precon-audit/quality_fit_creature.py`,
`quality_fit_noncreature.py`) re-run the baselines, the cross-validation, the fit
and the pairs each read still gets wrong. Rules citations in the modules came
from `rules-lookup` (CR 118.9, 509.1b, 603.6c, 614.1, 700.2, 701.23a, 702.3b,
702.62a).

**What the fits found, honestly.** The pair set is cards the S1 order put above a
guide add, so a read that undoes S1's own features wins pairs without measuring
strength. The creature agent measured it: 69% of the creature pairs' weight is
pairs where need and lanes tied and synergy — which counts every ability a card
has — put the wordier card first; the single strongest predictor is having fewer
abilities (0.66 alone). On the 31% of weight where need or lanes decided the
order the read scores 0.57 against play-rate's 0.61, and on pairs with equal
ability counts 0.58 against 0.61. Its scores say the same: Craterhoof Behemoth
tops the list only because one ability on eight mana hits the per-ability cap;
Solemn Simulacrum is last for its dies trigger; Scute Swarm ties Firespitter
Whelp. The noncreature read's `tokens` −0.9 and `scaling` −0.7 are the same
kind of weight (a token deck's page is all token makers; the guide adds the
multiplier), and `abilities` −0.6 partly so; with only the defensible features
(cheap, doubler, job, abilities, cost) it still scores about 0.70. The spell read
is level with play-rate within the noise of 16 decks. **So: the creature read is
a correction for synergy counting text, not a card-strength read, and ships as
that** — it is exactly what the S1 order lacked, and the plan-primary gate on the
held-out 20 (ADR-0061's second amendment) is what decides whether the order it
enables is better, which no pair set can game. Whether the two bias-shaped
noncreature weights stay is Dan's call, recorded here when made.

**Where the reads act.** V1 (the first of the two pre-declared theme-page orders):
need fit, main lanes served, then synergy × `quality_factor`, play-rate a
rank-10,000 floor (`swaps._POPULARITY_FLOOR`; an unranked card passes) and the
last tiebreak, then price. V2, only if V1 fails the gate: need fit, lanes,
quality, then synergy. Then quality as a third term in the job pages' blend
beside the job read and play-rate. Each measured alone against the C12 baseline
(`w41/sb-*-C12b.json`); the results are this ADR's amendments.

**Consequences.** Three more reads to keep correct as phase's grammar moves
(their sidecars invalidate on a module edit). The pair-set method is reusable for
any read meant to replace play-rate, with the caveat above: pairs built from an
order measure what that order gets wrong, not strength in general; a future
strength read wants pairs from a source the tuner's order didn't choose (the
guides' adds against the guides' cuts of the same type, say). The method
(`theme_pairs.py` + the fit scripts) is the deliverable as much as the weights.

**Amendment (2026-10-31, the orders measured).** Each alone against C12
(`w41/sb-*-C12b.json`), the plan-primary gate (held-out plan ≥ +10; guide adds +
job-equivalents ≥ −5; cuts ≥ −1):

| run | where quality acts | held-out plan | adds | job-equiv | cuts | verdict |
|---|---|---|---|---|---|---|
| V1 (`w41/theme-order-V1.patch`) | theme pages: need, lanes, synergy × quality factor, play-rate floor 10,000 and tiebreak | +63 | −22 | +1 | −2 | held back |
| V2 (`w41/theme-order-V2.patch`) | theme pages: need, lanes, quality factor, synergy | +66 | −20 | +4 | −2 | held back |
| J2 (shipped) | job pages: quality percentile as a third term in `swaps._blended_percentiles`, beside the job read's and play-rate's, for the ordering jobs (board wipe, card draw, protection) | +19 | −2 | 0 | −1 | **ships** |

The theme orders fail the floor by more than S1 did without the reads (−17):
the reads correct synergy's text count but do not carry the strength play-rate
carries on a theme page (Quandrix Unlimited's nine theme slots went to Hydras,
an X creature with one ability reading as cheap per ability). **The theme order
stays play-rate first, then price.** On the job pages the reads do their work:
the third term moved held-out plan-consistency +19 with the floor held (the 25:
plan +14, adds −6, job-equivalents −3, reported). A card no read sees sits at
the middle of the quality percentile. Dan's stance on theme pages is still
unmet; what it needs is a strength read whose pairs are not chosen by the order
it would replace (the consequences above).
