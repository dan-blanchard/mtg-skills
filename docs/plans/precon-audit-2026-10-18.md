# The 25-precon tuner audit (2026-10-18)

The deterministic tuner (`deck-tune`) thrown at 25 Commander precons, one per
archetype family, and compared with what published upgrade guides cut and add.
Guides are the baseline: people upgrade precons constantly and say why, so the
gap between the tuner's swaps and theirs is the tuner's to-do list. A guide
can be dated; where the tuner proposes a stronger, newer card that is fine.

## Method

1. Lists: MTGJSON's deck files (`https://mtgjson.com/api/v5/decks/<Name>_<SET>.json`,
   index at `DeckList.json`, type "Commander Deck"), converted to the
   `Commander` / `Deck` list shape by `precon-audit/to_decktxt.py` and parsed
   with `parse-deck --format commander`. Collector's-edition duplicates skipped.
2. Tune: `deck-tune <deck.json> --max-swaps 10 --budget 100` (passes one to eight;
   from the recall pass on, `--max-swaps 30`, the largest guide's swaps, and from
   2026-10-20 each precon's own budget — the most any of its guides spent,
   `budgets.json` from `precon-audit/guide_sizes.py` — where it was the largest
   guide's $440 for every precon), paper medium, no collection.
3. Guides: 2-3 per precon (EDHREC, Card Kingdom, Draftsim, TCGplayer, Star City
   Games, Hipsters of the Coast, Card Game Base, MTG Rocks), summarized by a
   research agent into `precon-audit/<Name>_<SET>.md`: sources, the plan as the
   guides describe it, weaknesses, cuts, adds, a consensus line. Cards named
   exactly as printed; nothing invented.
4. Compare: `precon-audit/compare.py` — for each precon, the tuner's cuts and
   adds against the guides' tables, the tuner's weak-list (filler, low-value,
   fed-only) against the guides' cuts, and the guides' cuts the tuner
   *protects* (carers of the main theme or doers of the commander's lane).

## Before and after the fixes

| | before | after |
|---|---|---|
| precons read SPREAD-THIN | 9 of 25 | 1 of 25 (Squirreled Away, whose guides also say "pick one lane") |
| tuner cuts | 77 | 79 |
| tuner cuts a guide also cuts | 39 | 40 |
| tuner adds | 77 | 79 |
| tuner adds a guide also adds | 3 | 6 |
| guide consensus cuts (2+ sources, in the list) | 170 | 170 |
| of those, cards the tuner protects as lane or main carers | 141 | 142 |

Exact add matches are a hard metric (a guide names ~25 adds out of thousands of
candidates); the shape of the adds is what changed. Before: Clown Car in five
decks, Genju of the Fields / Falls / Cedars, Bog Rats, Plague Beetle, Fly,
Awesome Presence, the Class enchantments, Jumbo Cactuar beside Swords to
Plowshares in three decks, Tidespout Tyrant beside Sol Ring in seven. After:
Bitterblossom, Sythis, Harvest's Hand, Kappa Cannoneer, Thought Monitor,
Baeloth Barrityl, Kasmina, Heliod, Sun-Crowned, Greater Auramancy, Stoneforge
Mystic, Aether Vial.

The four fixes (commit after this file): the add page is the most-played
matches, not the cheapest by mana value (`card_search` `edhrec` sort,
`swaps._run_search`); a premium card (`classify.PREMIUM_RANK`) is never a
template-band trim (Sol Ring was Veloci-Ramp-Tor's "ramp over by 3" cut); a
one-card-short combo outranks dead weight only when its result ends the game
(`combo_search.ends_the_game`); the focus verdict counts directions (the
commander's own lanes are one), a main needs carers in proportion to its
feeders (`Calibration.focus_main_carer_share`), and the commander's primary lane
is the held lane the most cards care about (Blame Game: Goad, not Combat).

## Per precon

verdict before → after; main theme after; cuts matching a guide / tuner cuts;
the guides' consensus; the notable miss.

| precon | verdict | main | cuts | guides say | notable miss |
|---|---|---|---|---|---|
| Abzan Armor | FOCUSED | Toughness as power | 0/4 | drop the lifegain package and Seedborn Muse for toughness bodies, protection, one-sided sweepers | tuner cuts three fed-only cards the guides keep; adds Overkill off a Jaws of Defeat line |
| Animated Army | FOCUSED | Artifacts | 4/4 | cut the token subtheme; add protection, draw, more MV-4+ animations | Bello's "MV 4+ noncreature" lane does not exist; "ramp over by 14" |
| Blame Game | SPREAD-THIN → FOCUSED | Combat → Goad & politics | 2/5 | more goad payoffs, cheap interaction, a finisher (Aurelia, Agrus Kos) | Feather / Sun Titan / Ransom Note agree; pillowfort read as "Superfriends" |
| Blood Rites | FOCUSED | Vampire tribal | 0/0 | more outlets, reanimation, removal, Vito / Sanguine Bond | **no swaps at all**: 43 of 45 lane cards are carers, so no cut pool |
| Death Toll | FOCUSED | Graveyard engine | 1/2 | swap one-type creatures and one-shot mill for two-type permanents and repeatable mill | 11 guide cuts protected as graveyard carers (Carrion Grub, Mulch, Grisly Salvage) |
| Deep Clue Sea | FOCUSED | Artifacts | 1/4 | cut off-plan creatures; add Clue doublers, mana sinks, counterspells, lands | tuner cuts Adrix and Nev / Esix (token doublers read as fed-only) |
| Desert Bloom | SPREAD-THIN → FOCUSED | Your graveyard | 2/2 | land recursion (Life from the Loam, Crucible), better lands, protection | Yuma's Desert trigger has no lane; "Lands matter" 17 deep with no carer |
| Eldrazi Unbound | FOCUSED | Colorless / Eldrazi | 1/3 | cut X spells and filler; add cheap rocks, utility lands, draw | adds are on-lane but not the guides' (Expedition Map, Eye of Ugin) |
| Endless Punishment | FOCUSED | Drain | 2/3 | efficient life-loss punishers (Roiling Vortex, Zo-Zu), protection, lands | 35 "interaction" trips "over by 20"; the punisher suite reads as removal |
| Enduring Enchantments | FOCUSED | Enchantments | 0/1 | enchantment ramp, protection, Anikthea reanimation targets | one swap only (Binding the Old Gods → Heliod); guides cut Narci, Love Song |
| Fae Dominion | SPREAD-THIN → FOCUSED | Faerie tribal | 2/2 | commit to one direction; Bitterblossom, Spellstutter, Mistbind | Bitterblossom matched; guides also say the deck is pulled two ways |
| Grand Larceny | SPREAD-THIN → FOCUSED | Combat damage | 3/7 | cheap unblockables, cheap ramp, Court of Locthwain, exile effects | Gonti's "spells you don't own" line reads as Cost reduction, not wants_theft; Mimeoplasm / Siphon Insight filler |
| Graveyard Overdrive | SPREAD-THIN → FOCUSED | Your graveyard | 2/3 | more self-mill, recursion, draw (Ripples of Undeath, Buried Alive, Gix) | Garruk / Maelstrom Pulse cuts agree; adds Aggravated Assault off a Selvala line |
| Living Energy | SPREAD-THIN → FOCUSED | Artifacts (+ Energy) | 0/2 | energy generators and doublers, better copy targets; trim Thopter filler | 12 guide cuts protected (the Thopter package is the artifact lane) |
| Mardu Surge | FOCUSED | Combat | 0/1 | cheaper token makers, anthems, protection; cut the clunky top end | Zurgo's token-leaves trigger is not a tokens carer; one swap |
| Multiverse Reforged | FOCUSED | Cheat into play | 4/6 | cut the off-plan bombs (Omnath, Akroma, Dack); cheap token makers, Identity Echo | adds Aether Vial / Stoneforge under a polymorph commander |
| Planeswalker Party | FOCUSED | Superfriends | 4/6 | stronger walkers, proliferate payoffs (Elspeth's Talent, All Will Be One) | Kasmina matched; adds Orzhov Advokist, Roar of Resistance |
| Quick Draw | FOCUSED | Spellslinger | 1/2 | cheaper cantrips and mana, better lands, instant-speed interaction | adds Thor and The Emperor of Palamecia as closers |
| Sliver Swarm | FOCUSED | Sliver tribal | 1/2 | fix the five-color mana base; draw, protection, cheap Slivers | 13 guide cuts are Slivers the tuner protects; closer is Caesar, Legion's Emperor |
| Squirreled Away | SPREAD-THIN | Squirrel tribal | 1/2 | pick one lane (tokens); cut Food filler; Parallel Lives, Craterhoof | the one SPREAD-THIN the guides agree with |
| Sultai Arisen | SPREAD-THIN → FOCUSED | Graveyard engine | 2/3 | utility and dual lands; dedicated recursion engines | Dauthi Voidwalker cut (a guide agrees); Jumbo Cactuar beside Jarad is a real kill |
| Timey-Wimey | SPREAD-THIN → FOCUSED | Suspend / time counters | 2/2 | cut what adds or removes no time counters; Suspend / Vanishing cards | adds Ghost of Ramirez / Sword of Light and Shadow — not time-counter cards |
| Tinker Time | FOCUSED | Artifacts | 2/4 | cheap rocks, draw, distinctly named artifact token makers | Thought Monitor matched; "ramp over by 9" under an artifacts commander |
| Veloci-Ramp-Tor | FOCUSED | Dinosaur tribal | 1/4 | cheap ramp, protection, recursion; Ghalta and Mavren, Gishath | Sol Ring no longer cut; Wayward Swordtooth is |
| Virtue and Valor | FOCUSED | Enchantments | 2/5 | fix mana and ramp; Sythis, protection, on-theme auras | Sythis matched; Gylwain (Role tokens) still filler |

## Second pass (same day)

Three more fixes, re-measured on the eight precons they touch: a template row
whose members are mostly the commander's lane is advisory, never trimmed
(Gimbal's "ramp over by 9", Morska's "card draw over by 7", Bello's "ramp over
by 14", Pantlaza's "ramp over by 3" all read "mostly the commander's own lane,
not a trim"); a closer is sourced on the main lane (Tinker Time's is
Blightsteel Colossus, Deep Clue Sea's Genji Glove — Sliver Swarm's lane holds no
card the wincons read counts, so its closer shortfall is reported unsourced
rather than filled with Bruce Banner); and a deep lane's least-played half is
the last cut tier, open only to a Spine fill, a closer or a game-ending combo
piece. Blood Rites went from no swaps to nine: Sanguine Bond and Vito, Thorn
of the Dusk Rose (the guides' two consensus adds, each one card short of
Exquisite Blood), Malakir Bloodwitch as a closer, and ramp / draw / wipe fills,
each at the expense of a least-played Vampire. Play-rate inside a lane predicts
a guide cut at 0.32-0.40 precision against a 0.21 base rate, which is why the
tier is a slot for a Spine fill and not a dead-weight claim. Four lane misreads
the guides exposed were fixed in the same pass: Gonti, Canny Acquisitor's
"spells you cast but don't own" line is `wants_theft` (Grand Larceny now holds
Wants theft as a commander lane, four carers); a trigger on a token leaving,
dying or being sacrificed is a tokens payoff (Zurgo Stormrender); Role tokens
are on the Enchantments lane (CR 205.3h lists Role among the enchantment
types), so Gylwain is no longer filler under Ellivere; a token replacement
that keeps the count (Esix, Chatterfang) is a tokens payoff. Totals after the
second pass over all 25: 91 adds, 7 matching a guide; 40 of 91 cuts matching;
one SPREAD-THIN.

## Third pass (same day)

Every tuner item in the backlog worked through: Spine fills rank by play-rate
within a mana-value band (an X cost at its cast value); the lane cut tier orders
feeders before carers, then least played (measured: `precon-audit/lane_quality.py`,
906 lane cards vs 222 guide cuts — no function read beats the 0.245 base, this
order puts a guide cut in the top five 48% of the time, costlier-first 30%);
player-only damage is not `interaction` (the `removal` lane fires on burn that can
reach a permanent; `direct_damage` left the preset); Bello's Animation and Yuma's
Deserts have lanes; pillowfort and fogs are not Superfriends; a typed token
replacement carries its kind and an artifact-token maker is a maker; carers
respect scope, one-carer-set avenues fold, emerging needs two carers in
proportion, the primary is a held lane deep enough to show, "Activated-ability
engine" is cared about by its untap engines; three typed-cheat pair rows; CR
2026-09-25 subtypes; Syr Konrad's folded trigger doubles.

| | second pass | third pass |
|---|---|---|
| precons read SPREAD-THIN | 1 of 25 | 1 of 25 (Squirreled Away) |
| tuner cuts / matching a guide | 91 / 40 | 90 / 43 |
| tuner weak-list matching a guide | 20 | 26 |
| tuner adds / matching a guide | 91 / 7 | 90 / 8 |
| guide cuts the tuner protects | 141 | 127 |
| Endless Punishment "interaction" | 35 | 19 |

Mains that moved: Animated Army Artifacts → Animation; Deep Clue Sea Artifacts →
Clues / investigate; Abzan Armor none → Toughness as power. Desert Bloom gained a
commander-held Deserts sub (18 deep). Blame Game lost its phantom Superfriends sub.

## Fourth pass (same day)

The leftovers of the backlog entry: Bello's mana-value floor carried
(`animate_makers|you|Artifact>=4`, `Serve.types_cmc_min`) and the `animate_artifact`
regex lane retired; `clue_matters` and `enchantments_matter` are payoff shapes, never
a maker (`clue_matters` 165 → 31 cards); `artifacts_matter` / `enchantments_matter`
carry subject `cast` on a cast-trigger payoff and the typed-cheat pair rows read
candidates without membership idents (Sol Ring no longer scores as an artifact
payoff under Arcum); an animation static is not an anthem; the +1/+1 keyword
actions and surveil / a mill or discard cost you pay reach their lanes through
shared reads, converting six held serve specs off their regexes; the interaction
role is sourced by its own presets and `roles.is_interaction`; a non-held main
whose builders mostly care about the primary is a sub (Quick Draw's spells in the
graveyard); "Activated-ability engine" is cared about by its untap engines.

| | third pass | fourth pass |
|---|---|---|
| precons read SPREAD-THIN | 1 of 25 | 1 of 25 (Squirreled Away) |
| tuner cuts / matching a guide | 90 / 43 | 86 / 45 |
| tuner weak-list matching a guide | 26 | 25 |
| tuner adds / matching a guide | 90 / 8 | 86 / 10 |
| guide cuts the tuner protects | 127 | 131 |

Mains that moved: Abzan Armor Activated-ability engine → Toughness as power;
Virtue and Valor Enchantments → Voltron / equipment & auras (Ellivere's Roles
are depth, not payoffs); Deep Clue Sea's main is "Clue makers / investigate"
with 12 carers instead of 21. Animated Army's Animation lane is 20 deep (the
mana-value 4+ cards) and no longer proposes an Equipment as an Animation add.

## Fifth pass (2026-10-19): every held serve spec converted

The 41 serve specs the serve-ident pass held, and the six the fourth pass held,
now serve on the lanes' idents (`docs/plans/serve-idents-and-avenue-support.md`
§2 has each census and its classified remainder). The lanes gained one shared
read per gap: keyword actions that make tokens (amass, endure, populate) or
place counters, granted and replacement Treasure / Food / Clue / Blood makers,
discard costs you choose to pay (labelled activation / additional / optional /
tax — a tax to keep a permanent is neither a discard nor a graveyard fill), a
served `connive_matters`, energy / venture / foretell events, library seizes
(Bribery), static damage redirects (Pariah) and a `damage_received_matters` lane,
granted counter triggers, variable and one-sided debuffs with a toughness-0 set
as hard removal (CR 704.5f), granted tap abilities, shield counters, granted
alternative costs, time-counter references, attractions, `modified`, and one
`controller_side` read in place of six opponent-controller sets. Five lane false
positives the census had exposed are fixed, and morbid / graveyard-hate cards
left "Your graveyard" (`graveyard_matters|you|` 3839 → 3686).

| | fourth pass | fifth pass |
|---|---|---|
| precons read SPREAD-THIN | 1 of 25 | 1 of 25 (Squirreled Away) |
| tuner cuts / matching a guide | 86 / 45 | 86 / 44 |
| tuner weak-list matching a guide | 25 | 25 |
| tuner adds / matching a guide | 86 / 10 | 86 / 8 |
| guide cuts the tuner protects | 131 | 124 |

Reads that moved: Living Energy's main Artifacts → Energy (Satya's own lane);
"Go wide" surfaces as a sub in Animated Army, Living Energy, Squirreled Away and
Virtue and Valor now that the token serve reads amass, endure and populate;
Death Toll and Sultai Arisen trade labels between "Your graveyard" and
"Graveyard engine" (one avenue, two spellings) and Sultai regains its Sacrifice
sub.

## Sixth pass (2026-10-19): the phase parse gaps, bridged

Every phase parse gap the serve-spec censuses had logged is worked around in the
supplemental parser, each self-retiring: recovery tokens for the parked residues
(where-X keyword heads read off the residue's own sentence — connive, amass,
investigate, devour, debuff; energy gains and payments; foretell; the "all damage
dealt to X is dealt to Y instead" redirects; a counter bonus; a replacement
idiom is read over its own sentence so a compound residue keeps both readings),
unit-level field corrections for a misstamped field on a node with no concept
decoration (`FieldCorrection`, ADR-0035 amended — untap locks stamped `SelfRef`,
"that player controls" stamped `controller: You`, the self-animation cycle,
Athreos's exile, the graveyard owner, the energy counter kind), concept
re-decoration where the node has one (anaphoric pumps, the suspended-card
target, fresh tap targets), bridge-ledger rows for clauses phase drops whole
(the creature half of a one-sided sweep, a dropped planeswalker target, a dropped
shrink, modified references, shield counters, four Unknown-mode triggers, a
forage cost), and repo-side reads the censuses had blamed on phase (granted
afterlife / mobilize tokens, a replacement-made Map, Dodecapod's counters,
countered-creature cost reductions, Brimaz's Phyrexian death, Tomik's affinity
for planeswalkers, a coin flip's branches minus the ones that are drawbacks).
Still open, nothing to read: Commence the Endgame, the aftermath faces, Pradesh
Gypsies, Desperate Gambit's dropped "you control", Orcish Captain's "it" in an
activated ability.

| | fifth pass | sixth pass |
|---|---|---|
| precons read SPREAD-THIN | 1 of 25 | 1 of 25 (Squirreled Away) |
| tuner cuts / matching a guide | 86 / 44 | 85 / 44 |
| tuner weak-list matching a guide | 25 | 25 |
| tuner adds / matching a guide | 86 / 8 | 85 / 8 |
| guide cuts the tuner protects | 124 | 124 |

The precon reads are unchanged apart from Sultai Arisen regaining its Sacrifice
sub; the pass is about the card pool (about 120 cards gained the ident a guide
would expect, 40 lost a wrong one), not the 25 lists.

## Seventh pass (2026-10-19): the upgrade slots

The six passes before this one fixed what the tuner read; the swaps were still a
third of a guide's list (85 across 25 precons, about three a deck, against a
guide's ten), because every swap answered an issue and most precons have few.
Over half of what the guides cut and add are template-role cards (222 of 424
cuts, 356 of 660 adds): the precon's own removal, draw and ramp traded for the
staples. Two measurements (`precon-audit/upgrade_reads.py`):

- **Cuts.** Off every lane the deck holds (no commander-lane doer, no carer of a
  built theme), a nonland card ranked past 3000 is a guide cut 48% of the time
  (119 of 247, about ten a deck), against 14% for an off-lane role card inside
  rank 1000 and 24% overall; on a lane, ranks 3000-10000 run 17-24% (past
  10000 a lane card is a guide cut 40-75%, but a lane holds few of those —
  the lane tier's least-played half reaches them).
- **Adds.** On the swap engine's candidate pages (187 of them), synergy-first put
  41 guide adds in a page's top ten (median rank 36); a synergy floor of a fifth
  of the page's best, then play-rate, 72 (median 14); play-rate alone 69.

What changed: `focus` names the **upgrade slots** — `upgrade_cards` (off-lane,
past `classify.UPGRADE_RANK`) and `lane_upgrade_cards` (the deep lane's
least-played half, moved here from the cut ranking; never a Granter, which
ADR-0040 §4 judges by its grant) — and a last-ranked `upgrade` issue spends the
rest of the swap budget on them, each for a better-played card at no higher
mana-value band doing the cut's own job (`issues.upgrade_job`: the scarcest
template role, else protection, else the main theme). Every theme add,
upgrades included, is the most-played candidate that fits (`swaps._FIT_FLOOR`).
Two role misreads the upgrade pass surfaced: an Equipment's or Aura's own shrink
("Equipped creature gets +1/-1" — Skullclamp, Dead Weight) and a spell's target
(Nameless Inversion) read as board wipes, and the `board-wipe` view counted
damage to each player (Price of Progress, Descent into Avernus — 27 cards, none a
sweep). And one run-to-run drift: the commander's lanes were sorted by depth
over a set, so two equally deep spellings of one lane (Death Toll's "Your
graveyard" / "Graveyard engine") swapped with the string-hash seed — the label
reads the passes above logged as trading places. The label now breaks the tie;
two full reruns under different hash seeds agree on every swap.

| | sixth pass | seventh pass |
|---|---|---|
| precons read SPREAD-THIN | 1 of 25 | 1 of 25 (Squirreled Away) |
| tuner cuts / matching a guide | 85 / 44 | 223 / 104 |
| tuner weak-list matching a guide | 25 | 25 |
| tuner adds / matching a guide | 85 / 8 | 223 / 29 |
| guide cuts the tuner protects | 124 | 124 |

By issue, the upgrade swaps are 137 of the 223, their cuts matching a guide 43%
of the time (the role trims 75%, dead weight 56%). As shares, cut precision eased
(52% to 47%) while the count more than doubled, and add precision rose (9% to
13%). Adds that match a guide: Delay, Resurgent Belief, Ancestral Vision and
Rousing Refrain (Timey-Wimey); Sanguine Bond, Vito and Marauding Blight-Priest
(Blood Rites); Bitterblossom (Fae Dominion, Grand Larceny) and Faerie
Mastermind; Lae'zel and Teferi, Master of Time (Planeswalker Party); Taunt from
the Rampart and Bothersome Quasit (Blame Game); Skullclamp, Swiftfoot Boots and
Lightning Greaves; Hedge Shredder, Tamiyo's Journal, Buried Alive. Off the
guides' lists but in their spirit: Doubling Season and Hardened Scales (Enduring
Enchantments), Smothering Tithe, Consecrated Sphinx, Sylvan Library. Nine
precons get no guide-matching add: Abzan Armor, Eldrazi Unbound, Enduring
Enchantments, Living Energy, Mardu Surge, Multiverse Reforged, Sultai Arisen,
Tinker Time, Veloci-Ramp-Tor. The most-played card of a job
recurs: Skullclamp is an add in 12 decks (a guide add in 3), Swiftfoot Boots in
9, Frantic Search in 5 — looting counts as card draw (connive is written in as
card advantage).

## Eighth pass (2026-10-19): job reads

Dan's direction after the seventh pass: the tuner should land on the guides' cards
from first principles — what a card does, what it costs, how it fits — with
play-rate as the measuring stick rather than the decision, and no
commander-specific EDHREC lookups. ADR-0060 records the result.

- **A bug first.** The interaction search passed its five presets as
  `preset_names`, which combine with AND, so it found nothing: since the fourth
  pass no removal fill and no removal upgrade was ever proposed. It reads any of
  them now (`any_preset_names`); a test runs the real filter over real cards.
- **Job reads** (`_analysis/job_quality/`): removal, card draw, ramp, board wipe,
  protection, each a handful of features off the concept trees with weights
  fitted on play-rate. Each read's fit, on the cards whose main job it is
  (agents' harness, scratch; `precon-audit/job_reads.py` re-measures the
  production reads over every card they score):

| job | fit on main-job cards: CV Spearman / guide adds (read vs play-rate) | production read, every card it scores: Spearman / guide adds (read vs play-rate) |
|---|---|---|
| protection | 0.56 / 0.94 vs 0.97 | 0.56 / 0.92 vs 0.97 |
| board wipe | 0.50 / 0.94 vs 0.91 | 0.49 / 0.79 vs 0.92 |
| removal | 0.40 / 0.79 vs 0.95 | 0.16 / 0.49 vs 0.94 |
| card draw | 0.33 / 0.75 vs 0.89 | 0.33 / 0.76 vs 0.85 |
| ramp | 0.28 / 0.80 vs 0.90 | 0.27 / 0.69 vs 0.89 |

(Guide adds: the median percentile among the cards of their deck's color identity
the read scores. The production column counts every card with that job's shape —
removal's includes every creature with an incidental fight or enters-the-
battlefield kill, which is why it falls furthest.)

- **How the tuner uses them.** Percentile medians flattered the reads: the tuner
  takes the top card, and there the read alone found guide adds less often than
  play-rate for every job (removal's read made Sheltered by Ghosts the add in
  seven precons). Against the guides' cuts every read found the weaker card less
  often than play-rate too. So every read gates membership — the add must do the
  job by the read — while "better than the cut" stays play-rate's, and wipes, draw
  and protection also order the candidates, by read percentile plus play-rate
  percentile (11 vs 7 guide adds in the top thirty for wipes, 11 vs 6 in the top
  ten for draw; protection's blend trailed play-rate, 24 vs 29 in the top thirty,
  and orders by Dan's call).
- **Overload** spells are sweeps (CR 702.96a): Damn, Mizzium Mortars, Winds of
  Abandon, Electrickery and Vandalblast read `mass_removal`, Cyclonic Rift
  `mass_bounce` — a retirement canary watches for phase typing the mode.

| | seventh pass | eighth pass |
|---|---|---|
| tuner cuts / matching a guide | 223 / 104 | 230 / 109 |
| tuner weak-list matching a guide | 25 | 25 |
| tuner adds / matching a guide | 223 / 29 | 230 / 30 |
| guide cuts the tuner protects | 124 | 124 |

The totals barely move, and the adds stay close to play-rate's — the reads mostly
decide which cards may be an upgrade, not which one wins. Removal upgrades exist at
all (the search found nothing before): Reclamation Sage (six precons), Braids,
Arisen Nightmare (four), Walking Ballista (three), Abrade, Cyclonic Rift, Deadly
Rollick, Lightning Bolt, Boros Charm, Goblin Bombardment, Orcish Bowmasters, Loran
of the Third Path, Aetherflux Reservoir — popular cards that do the job, where play-
rate alone had picked Animate Dead and An Offer You Can't Refuse. Wipes go to Toxic
Deluge and Martial Coup (three each), with Spiteful Banditry and Pyrohemia through
the blend. Protection upgrades go to Flawless Maneuver (two precons), Deflecting
Swat and Lightning Greaves: protection orders by Dan's call, its blend having
trailed play-rate slightly (24 vs 29 guide adds in the top thirty); the
"protection short" fills still rank by mana-value band and play-rate (Swiftfoot
Boots in four). Ramp goes to Smothering Tithe, Farseek, Rampant Growth, Sakura-Tribe Elder
and Talisman, beside Patchwork Banner (three), Ashnod's Altar (two), Fellwar Stone,
Thought Vessel and Cultivate. Card draw drops Faithless Looting and Frantic Search
for Wheel of Misfortune, Distant Melody, Village Rites, Sylvan Library and Deadly
Dispute. A deck fit (ADR-0060's amendment) scores how much of a draw engine's fuel
the deck runs — Skullclamp's X/1 creatures and token makers — and, gating the
upgrades and the "card draw short" fill alike, took Skullclamp from the draw add
in eleven precons to seven with no guide match lost.

## Recall: what the tuner misses, and why (2026-10-19)

Counting matches says how precise the swaps are; Dan asked for the other half — of
what the guides cut and add, how much the tuner finds, and what stops the rest.
`precon-audit/misses.py` reruns the tune with the cut ranking and the candidate
searches recorded and gives every guide card one reason (first that applies).

**The recipe now uses the guides' own size — the largest.** `precon-audit/
guide_sizes.py` counts each guide's list: over 54 guides the median makes 10 cuts
and 13 adds (14 swaps, the larger of the two) and its adds cost $58 at today's
prices; the 90th percentile 22 swaps and $199; the largest 30 swaps and $438. At
the median, 16 of the 25 precons hit the swap cap — the cap, not the tuner, was
stopping recall. At the largest the tuner stops on its own (one deck at the cap,
a median of 20 swaps):

| --max-swaps / --budget | swaps made | decks at the cap | cuts matching a guide | adds matching |
|---|---|---|---|---|
| 10 / $100 (passes one to eight) | 230 | — | 109 (47%) | 30 |
| 14 / $60 (the median guide) | 322 | 16 | 139 (43%) | 30 |
| 22 / $200 (90th percentile) | 454 | 7 | 176 (39%) | 42 |
| 30 / $440 (the largest guide) | 493 | 1 | 185 (38%) | 47 |
| 30 / the precon's own guides' budget ($41–438, median $126; 2026-10-20) | 437 | — | 167 (38%) | 44 |

Past 22 swaps the extra cuts match a guide 27% of the time, about the 24% base
rate. The recipe was **thirty swaps and $440** (since 2026-10-20 the budget is each
precon's own, below), so recall is never capped below
what a guide does; precision is read beside it.

| guide cuts in the decks (424) | n | | guide adds (745) | n |
|---|---|---|---|---|
| cut | 167 | | added | 44 |
| popular: off-lane, inside `UPGRADE_RANK` | 75 | | out of scope (in deck, land, banned, off-identity) | 135 |
| a doer of the commander's lane, outside the deep-lane half | 55 | | a theme card no search looked for | 229 |
| in a cut pool, not reached | 42 | | on a searched page, outranked | 171 |
| a carer of a built theme | 27 | | on a page, gated (play-rate, cost band, job) | 86 |
| other | 25 | | not on any page though its job was searched | 40 |
| land / commander | 20 | | a role card no issue asked for | 40 |
| protected (combo / closer / multiplier) | 13 | | | |

Recall at each precon's own budget (2026-10-20) is 167 of the 404 cuttable guide cuts
(41%) and 44 of the 610 in-scope adds (7%). At $440 for every precon the same tree
matched 186 and 54 (52 before Mystic Remora stopped reading as a lasting engine, 56
before the card-draw page held the repeating draw engines, 52 before an upgrade
stopped being held to a top-heavy deck's four-mana cap, 54 before the lane fixes
below took two adds picked for misread roles, 47 before a job upgrade stopped
requiring theme fit — the floor had kept Swords to Plowshares and Path to Exile
behind Dragon Tempest in a goad deck). The levers, by size: the theme adds no
search reaches (229), the adds outranked on a page (171), the cuts the popularity
threshold still shields (75), the commander-lane cards the guides trim (55), and
the cuts a budget-bound tune never reaches (42).

Of those 238, 115 serve the main theme by the tuner's own read, and 88 of them don't
match the theme's search spec at all: a theme's candidate page is still its
pattern search (Abzan Armor's "assigns combat damage equal to its toughness"), not
its serving predicate (`Serve.matches`, which admits Fecund Greenshell and Perimeter
Captain). Paging the identity's 3,000 most-played cards through the serving
predicate as well, tried 2026-10-19, put the guide adds on the page but dropped the
adds matching a guide from 30 to 26: one pick per swap, and a wider page lets a
popular card that fits loosely win it. Widening the page costs precision without
buying recall until the ranking can tell those apart.

### Where the theme adds go missing (2026-10-19, thirty swaps)

The 238 theme adds no page holds, by why the page missed them
(`precon-audit/misses.py`, then each searched spec re-run without its cap or page
limit):

| reason | n |
|---|---|
| matches no spec the tuner searched | 203 |
| on a searched spec, past the page's depth | 22 |
| cut by the top-heavy deck's four-mana cap | 12 |
| other | 1 |

Of the 203, by the tuner's own serve read: 83 serve the main avenue, 44 another
viable avenue, 72 only lanes the focus read doesn't count as viable (Blood Rites'
sacrifice package: Altar of Dementia, Pyre of Heroes, Victimize), and 4 nothing.
The 12 the cap hides are top-band bodies: Gishath, Ghalta and Etali under
Veloci-Ramp-Tor, The First Sliver and Sliver Legion.

Two retries, both negative — and both, it turned out, measured with a score that
could not see an IR-served theme's payoffs (below, "Theme matching off the cards'
IR"), so neither verdict holds for the IR-served themes:

- **The serving predicate's page, at thirty swaps.** It made 515 swaps, 190 cuts
  and 52 adds matching, against 493 / 185 / 54. The wide page trades a tribe's own
  members for generic tribal support: Cloud Key, Urza's Incubator and Roaming
  Throne over Heart Sliver and Faerie Mastermind.
- **Payoff first.** On the 31 theme pages that hold a guide add (122 of them),
  ordering a candidate with a payoff clause first put 29 guide adds in the top ten,
  against 45 for the current order (fits, then most played). Play-rate alone put
  43, synergy first 26. On an IR-served theme the payoff weight read here was
  always zero, so the test says nothing about those decks.

Three lane misreads turned up on the way, each fixed: Cloud Key, Umori and Shimmer
read as tribal payoffs (`chosen_type_matters`; they choose a card or land type, CR
205.2a, not a creature type); Song of the Dryads, Imprisoned in the Moon and the
other Auras that make a threat a land or a Treasure read as nothing (now
`single_target_neutralize`, which the `pacify-aura` preset reads, so every
neutralize Aura is interaction); and 206 cards read as interaction only because they
return themselves to hand (`bounce_tempo` fired on Rancor, Batterskull, The Scarab
God). After the three: 493 swaps, 185 cuts and 52 adds matching. The two adds lost
were picked for those misreads: Virtue and Valor traded Rancor in as an interaction
fill, and traded Giant Inheritance, read as removal, for Stroke of Midnight.

The cap was the one cause a rule could fix. A top-heavy deck searches every add at
four mana or less, so a fix can't make its curve heavier, but an upgrade already
takes no higher mana-value band than its cut. Lifting the cap for upgrades made 498
swaps, 186 cuts and 56 adds matching: The First Sliver and Sliver Legion for Sliver
Swarm, Ghalta and Etali for Veloci-Ramp-Tor, Conduit of Ruin for Eldrazi Unbound.

The card-draw page never held a repeating trigger's single draw. The card-draw role
counts any draw for you, but the search pages the `card-draw` preset, which reads
`card_draw_engine`, and that lane took only an upkeep draw or a draw of two or more.
Rhystic Study, Esper Sentinel, Kindred Discovery, Bident of Thassa and Sram counted
as card draw and were never offered. The lane now reads a trigger that repeats and
draws for you (718 more commander-legal cards), and 13 guide adds reach a page. The
upgrades then take the most-played engines: Esper Sentinel in 13 decks, Rhystic Study
in 10, Mystic Remora in 9, where Skullclamp was in 15 and Village Rites in 9. The
guides add none of the three, so adds matching fell to 52 (Skullclamp three times,
Deadly Dispute once). Kept: the role and its search now agree, and which engine a
deck takes is the ranking's question (backlog "(e)").

Two corrections followed (2026-10-20). The guides don't add Rhystic Study ($68, a
Game Changer) or Esper Sentinel ($55) because most spend about $50, and the recipe
gave every precon the largest guide's $440, nine times that. Each precon now gets
its own guides' largest spend (`budgets.json`, $41–438). And Mystic Remora's
cumulative upkeep grows every turn until it is sacrificed (CR 702.24a), so the
card-draw read no longer credits it as a lasting engine (Dan's call; the read had
it above Rhystic Study). At per-precon budgets: 437 swaps, 167 cuts and 44 adds
matching (40 before the Remora fix); the card-draw adds are Garruk's Uprising in
12 precons, Esper Sentinel in 8, Skullclamp in 6, Rhystic Study in 4.

### Theme matching off the cards' IR (2026-10-20)

Of the 376 theme specs, 343 searched their candidate page by an oracle pattern, and
the synergy score found a hit's clause by the serve's pattern. 193 serves read the
cards' IR idents instead, and a hit with no pattern scored as a bare type-line match
(0.5, against 3.0 for a payoff), so on the ten precon main themes served by IR —
"Your graveyard", "Toughness as power", "Energy", "Cheat into play" — the score
could not tell a payoff from filler. Two changes:

1. **The score reads an IR hit's role.** The idents the serve matched are traced to
   the ability that emits them (`ident_provenance`), whose text lines up with an
   oracle clause, and that clause takes the same payoff test as a pattern hit: Syr
   Konrad is a payoff of "Your graveyard", Hedge Shredder an enabler. Alone: 436
   swaps, 166 cuts and 41 adds matching (437 / 167 / 44 before) — a payoff now
   scores 3.0, which lifts the fit floor past the type-line-only cards.
2. **A pattern-searched theme pages by its serve.** The page is the identity's cards
   the serve admits, most played first (`card_search`'s `serve` filter). A card-type
   or preset search stays: a tribe's serve also admits the generic tribal support
   (Roaming Throne, Urza's Incubator, Changeling Outcast), played more than any
   tribe's own cards, which took every Sliver Swarm upgrade when tribes paged by
   serve too. The toughness-as-power serve lost its toughness ≥ 4 arm: a creature
   assigns damage equal to its power (CR 510.1a), Doran swaps in toughness, so a
   6/6 gains nothing, and $48 Roaming Throne spent Abzan Armor's whole budget.

Two limits remain. Of the 343 pattern-searched themes, 184 now page off the cards'
idents; the other 150 (creature recursion, landfall, sacrifice outlets, attack
triggers) have a serve that is itself an oracle pattern, so their page is still a
pattern, now the serve's. And an IR hit whose ident no single ability emits — a
keyword's (lifelink), a whole card's (Crucible of Worlds), a modal spell's text-less
mode — still scores structural; a sampled 8-25 of every 60 served cards per theme.

Both, at each precon's own budget: **411 swaps, 165 cuts and 47 adds matching**.
The graveyard themes reach their guide adds (Syr Konrad twice, Ripples of Undeath,
Crucible of Worlds, Life from the Loam, Exquisite Blood); four decks make fewer
swaps, the wider page's picks costing more.

| guide cuts in the decks (424) | n | | guide adds (745) | n |
|---|---|---|---|---|
| cut | 165 | | added | 47 |
| popular: off-lane, inside `UPGRADE_RANK` | 75 | | out of scope | 135 |
| a doer of the commander's lane, outside the deep-lane half | 55 | | a theme card no search looked for | 215 |
| in a cut pool, not reached | 44 | | on a searched page, outranked | 167 |
| a carer of a built theme | 27 | | on a page, gated (play-rate, cost band, job) | 101 |
| other | 25 | | not on any page though its job was searched | 42 |
| land / commander | 20 | | a role card no issue asked for | 38 |
| protected (combo / closer / multiplier) | 13 | | | |

### The serves read the cards' IR (2026-10-22)

The theme serves that still matched on an oracle regex moved to the cards' idents
in two passes (`docs/plans/serve-idents-and-avenue-support.md`, "Pass C"): 78
where the lanes already read the theme, then 40 more after seven lane fixes. 312
of 376 serves read idents; 50 are left. At each precon's own budget the tune made
**401 swaps, 157 cuts and 41 adds matching** (417 / 166 / 47 before), about the
same share of matches per swap. Most of the drop is Virtue and Valor: its
enchantment payoffs (Ajani's Chosen, Archon of Sun's Grace, Ethereal Armor) now
read as Enchantments carers, Enchantments became its deepest theme, and Voltron
and Combat, whose Auras are mostly enchantments, fold into it — the read the
guides themselves give the deck; the cuts it lost are weak carers the tuner now
protects (backlog "(g)").

### The last pattern serves (2026-10-23)

The lane pass behind the 50 regex holds converted all but four; 362 of 379
serves now read idents (`docs/plans/serve-idents-and-avenue-support.md`, "Pass
D"). Over the 25 precons at their own budgets: **410 swaps, 158 cuts and 40 adds
matching** (401 / 157 / 41 before) — flat, as a change to how themes are read
rather than which themes win should be. Abzan Armor now cuts Protector of the
Wastes, a guide cut; Animated Army trades Swiftfoot Boots, a guide add, for Sword
of Feast and Famine.

### The job reads on signal trees, over the whole match set (2026-10-23)

The job reads walk the signal trees the lanes read, and an upgrade with a read
searches the job's whole match set rather than its 600 most-played matches
(ADR-0060's 2026-10-23 amendment). Over the 25 precons at their own budgets:
**417 swaps, 159 cuts and 39 adds matching** (420 / 161 / 40 before). The signal
trees alone move no swap (three fights become removal reads). The whole match set
and the tie-sharing blend change swaps in nine precons; the guide-matched changes
are Fae Dominion's (Kindred Discovery in, Skullclamp and Spellstutter Sprite out:
the dearer draw add leaves Spellstutter over budget) and Sultai Arisen's (its draw
add becomes Vanquisher's Banner at $2.94, and the four upgrades after it, two of
them guide cuts, no longer fit $132). Twenty guide adds the 600-card page never
held now sit on a page, outranked or gated.

### Where a job read leads (2026-10-24)

Dan's calls after the job reads moved to the signal trees: try each read as the order
of its upgrades and as "better than the cut", a job upgrade one mana-value band
higher, and theme fit as the tie-break between a staple and an on-theme card that do
a job about equally well; ship each only where the guide-matching adds rise and the
guide-matching cuts fall by two at most. One `misses.py` run per change, each alone
against the baseline, then the kept ones together (ADR-0060's 2026-10-24 amendment).
Columns: swaps / guide cuts / guide adds, then the guide adds matched per job (wipes,
removal, protection, draw, ramp, theme).

| change | swaps / cuts / adds | wipe / int / prot / draw / ramp / theme | |
|---|---|---|---|
| HEAD (64327f31) | 417 / 162 / 39 | 1 / 7 / 0 / 5 / 3 / 23 | |
| read fixes (below) | 407 / 158 / 39 | 1 / 7 / 0 / 5 / 3 / 23 | shipped; the baseline below |
| the read orders wipe upgrades | 412 / 159 / 40 | 1 / 7 / 0 / 5 / 3 / 24 | passed alone; 47 vs 50 with the rest |
| … card draw | 422 / 164 / 43 | 1 / 8 / 0 / 4 / 4 / 26 | draw matches fall; 39 with theme ties |
| … removal (on HEAD) | 413 / 163 / 35 | 1 / 2 / 0 / 4 / 3 / 25 | rejected |
| … ramp (on HEAD) | 397 / 161 / 35 | 1 / 7 / 0 / 3 / 4 / 20 | rejected |
| … protection | 407 / 158 / 39 | unchanged | rejected |
| better than the cut by the read: removal | 407 / 159 / 38 | 1 / 6 / 0 / 5 / 3 / 23 | rejected |
| … ramp | 406 / 158 / 38 | 1 / 7 / 0 / 5 / 3 / 22 | rejected |
| … card draw | 407 / 157 / 39 | 1 / 7 / 0 / 5 / 3 / 23 | rejected |
| … wipes | 404 / 158 / 39 | 1 / 7 / 0 / 5 / 3 / 23 | rejected |
| … protection | 408 / 158 / 39 | 1 / 7 / 0 / 5 / 3 / 23 | rejected |
| a job upgrade one band higher | 417 / 161 / 43 | 2 / 7 / 0 / 5 / 3 / 26 | kept |
| every upgrade one band higher | 414 / 161 / 41 | 2 / 7 / 0 / 4 / 3 / 25 | theme part rejected |
| theme fit breaks a near tie: card draw | 435 / 167 / 42 | 1 / 8 / 0 / 5 / 4 / 24 | kept |
| … ramp | 409 / 159 / 41 | 1 / 7 / 0 / 5 / 5 / 23 | kept |
| … removal | 405 / 157 / 38 | 1 / 5 / 0 / 5 / 3 / 24 | rejected |
| … wipes | 412 / 159 / 39 | 0 / 7 / 0 / 5 / 3 / 24 | rejected |
| … protection | 407 / 158 / 39 | unchanged | rejected |
| the read leads card draw, with theme ties | 430 / 167 / 39 | 1 / 8 / 0 / 3 / 4 / 23 | rejected |
| the wipe read orders the wipe fill | 413 / 160 / 40 | 1 / 7 / 0 / 5 / 3 / 24 | kept |
| protection fills skip the avenue guard | 407 / 158 / 40 | 1 / 7 / 1 / 5 / 3 / 23 | kept |
| the protection read orders its fill (and no guard) | 401 / 158 / 38 | 1 / 7 / 0 / 4 / 3 / 23 | rejected |
| every shape wants protection, target 5 / 3 | 412 / 159 / 38 · 415 / 160 / 39 | | rejected |
| kept, with the wipe read leading its upgrades | 423 / 166 / 47 | 1 / 7 / 1 / 5 / 7 / 26 | |
| **kept** | **434 / 168 / 50** | **2 / 8 / 1 / 5 / 7 / 27** | shipped |

Against HEAD the tune makes 17 more swaps, 6 more guide-matching cuts and 11 more
guide-matching adds. The guide adds it gains: Swiftfoot Boots (Animated Army, the
protection fill without the avenue guard), Blasphemous Act (Blame Game, one band
above its cut), Kindred Discovery (Sliver Swarm) and Spellstutter Sprite (Fae
Dominion, which gives up Kindred Discovery), Fertile Ground (Enduring Enchantments),
Liquimetal Torque (Tinker Time), All That Glitters (Virtue and Valor), Insidious
Roots (Death Toll), Animate Dead (Graveyard Overdrive: no longer interaction, it is
a reanimation add), Professional Face-Breaker (Mardu Surge), Bothersome Quasit,
Inevitable Betrayal and Jhoira of the Ghitu; Endless Punishment loses Razorkin
Needlehead. Garruk's Uprising is the draw add in 7 precons (10).
Death Toll's wipe fill is Find // Finality, not Wail of War.

The read fixes: removal weighs an exile that lasts until the card leaves when the card
leaves by itself — an Aura goes when its host does (CR 704.5m: Sheltered by Ghosts,
0.86 to 0.56), Static Prison sacrifices itself (0.36) — hand-set weights; a free
alternative cost costs nothing (Deadly Rollick 0.37 to 0.64, Snuff Out 0.15 to 0.35:
phase parses both into `casting_options`, which only the protection read had read);
and the `removal` preset takes the debuffs that lower toughness, not all of
`debuff_makers`, so Animate Dead and Jace, Architect of Thought (a −1/−0) are no
interaction. That cost Planeswalker Party four guide cuts: with Jace out of the
interaction row its dead-weight fills could take Elspeth, Storm Slayer, which spent
the budget its later upgrades had used.

The 18 protection guide adds "no search" reached are not a preset gap — the
`protects-board` preset reads all 18. Their decks are aggro or midrange without a
voltron plan, which ADR-0024 asks for no protection, and none of their upgrade cuts
reads as protection.

Measured with Commander Spellbook's answers cached per request: a run on 2026-10-24
met the API's rate limit and tuned without combos, which moved every deck's swaps.

### Theme reach (2026-10-24)

At a913f172, 203 in-scope guide adds were theme cards no search reached. A
fact-finding pass sorted them. 94 serve the deck's main avenue: 71 sit below the
theme page's 150-card play-rate cutoff, and 22 because the main avenue searches by
card type and the card isn't that type (Urza's Incubator under Dinosaurs, Gruul War
Chant under Animation's artifacts). 35 serve only another viable avenue, which no
remedy pages. 73 serve only a lane that isn't viable. And Virtue and Valor's
Voltron, 27 of whose 31 members are Auras, folded into Enchantments, so no theme
page held its guides' Equipment.

Dan's calls: four policies, each measured alone against HEAD, the kept ones
measured together, and each shipped only if guide-matching adds rise while
guide-matching cuts fall by two at most. The four:

1. Theme adds ordered payoffs-first (an IR hit's payoff role for the page's
   avenue, then play-rate) over the serve's whole match set.
2. A type-searched theme (a tribe, Artifacts, Goad's preset) keeps its type search
   for its members, plus a capped share of support from its serve's broader page.
3. Each viable avenue gets its own add search, the theme's slots shared by depth.
4. The suit-up avenue survives the fold under a creature commander.

One `misses.py` run per row, Spellbook cached (`ROOT/spellbook-cache`, now in
`misses.py`). The columns are swaps / guide cuts / guide adds, then the swaps
whose add is a theme add, then the guide adds matched per job (wipe / removal /
protection / draw / ramp / theme). Tune time is each deck's median under six
workers, and memory is the largest worker's peak RSS.

| change | swaps / cuts / adds | theme swaps | wipe / int / prot / draw / ramp / theme | tune s · GB | |
|---|---|---|---|---|---|
| HEAD (a913f172) | 434 / 168 / 50 | 212 | 2 / 8 / 1 / 5 / 7 / 27 | 7.0 · 1.67 | |
| the serve's whole match set as the theme page | 433 / 168 / 50 | 212 | unchanged | 13.7 · 1.63 | rejected: no gain, twice the time |
| payoffs first, over the whole match set | 414 / 162 / 47 | 205 | 2 / 8 / 1 / 5 / 4 / 27 | 13.3 · 1.63 | rejected |
| payoffs first, over the 150-card page | 426 / 164 / 44 | 203 | 2 / 7 / 1 / 6 / 5 / 23 | 6.6 · 1.68 | rejected |
| type search + support, one in three | 437 / 170 / 48 | 215 | 2 / 7 / 1 / 4 / 7 / 27 | 7.5 · 1.62 | rejected |
| … one in five | 435 / 170 / 48 | 213 | 2 / 7 / 1 / 4 / 7 / 27 | 7.6 · 1.62 | rejected |
| … one in two | 441 / 171 / 47 | 219 | 2 / 7 / 1 / 5 / 7 / 25 | 7.1 · 1.62 | rejected |
| … the fit floor read off the members only, one in five | 436 / 170 / 51 | 215 | 2 / 8 / 1 / 6 / 7 / 27 | 7.5 · 1.62 | kept |
| … members' floor, one in three | 442 / 171 / 49 | 220 | 2 / 7 / 1 / 5 / 7 / 27 | 7.6 · 1.62 | rejected |
| every viable avenue, slots shared by depth | 420 / 159 / 35 | 209 | 2 / 5 / 1 / 3 / 4 / 20 | 7.0 · 1.63 | rejected |
| … shared by carers | 445 / 169 / 45 | 221 | 2 / 6 / 1 / 4 / 7 / 25 | 7.3 · 1.60 | rejected |
| … the main avenues only, by depth | 440 / 169 / 51 | 218 | 2 / 8 / 1 / 5 / 7 / 28 | 6.8 · 1.68 | kept |
| the suit-up avenue survives the fold | 431 / 167 / 51 | 209 | 2 / 8 / 1 / 6 / 7 / 27 | 7.1 · 1.67 | kept |
| … with every viable avenue shared by depth | 424 / 160 / 38 | 210 | 2 / 5 / 3 / 4 / 4 / 20 | 7.0 · 1.66 | |
| … with the mains shared by depth | 443 / 170 / 53 | 218 | 2 / 8 / 3 / 6 / 7 / 27 | 6.9 · 1.63 | |
| **kept** | **447 / 171 / 56** | **221** | **2 / 8 / 4 / 8 / 7 / 27** | **7.3 · 1.63** | shipped |

Against HEAD the tune makes 13 more swaps, with 3 more guide-matching cuts and 6
more guide-matching adds. The adds: Swiftfoot Boots, Lightning Greaves, Skullclamp,
Sram, Senior Edificer and Clever Concealment (Virtue and Valor, which loses All
That Glitters), Scute Swarm (Squirreled Away) and Aurelia, the Law Above (Blame Game).
The cuts: Paradise Druid, Nested Shambler and Vedalken Humiliator. Theme guide adds
no search reaches fell from 203 to 169; those 34 now sit on a page and are
outranked (242, from 204).

What each policy does:

- **Payoffs first lost again**, now that IR hits carry roles. It won guide adds
  where the payoff is the guide's pick (Enduring Enchantments' Calix and Weaver of
  Harmony, Planeswalker Party's Oath of Chandra, Graveyard Overdrive's Ripples of
  Undeath). But the payoffs cost more, so Timey Wimey's budget ran out after 12
  swaps where it made 22. The deeper page on its own moved one swap and doubled
  the tune time.
- **Type search plus support.** A type-searched theme pages its own members, and
  its serve's broader page adds the support that isn't of the type
  (`signal_specs.serve_page_search`). At most one add in five is support, never the
  first (`swaps._SUPPORT_SHARE`). The fit floor is read off the members only: with
  support in the floor, Herald's Horn scored high enough to push Fae Dominion's own
  Faeries below it, and that cost Likeness Looter and Spellstutter Sprite. At one
  in three or one in two, Herald's Horn and Roaming Throne take Fae Dominion's and
  Sliver Swarm's budget from their members.
- **Second themes.** Shared over every viable avenue by depth, the theme's adds
  went to generic subs whose pages hold staples. Fae Dominion's Spellslinger page
  gave Murder. Timey Wimey's Combat and Doctor pages gave Sol Talisman and Idol of
  Oblivion and spent its budget. Shared by carers it lost too. Shared over the
  main avenues only, by depth (`Sourcing.theme_avenues`), it reaches Squirreled
  Away's Sacrifice and Virtue and Valor's Voltron and passes. Every other precon
  reads one main, so its swaps don't change.
- **The suit-up fold.** Under a creature commander the voltron avenue doesn't fold
  into another theme. Equipment attaches only to a creature (CR 301.5), and its
  page holds Equipment, an artifact type (CR 205.3g) an Enchantments page never
  reaches. Alone it adds Skullclamp: an Equipment serves the now-viable avenue,
  so the card-draw fill's avenue guard (ADR-0040) prefers it. With the mains
  shared, Voltron's page adds Swiftfoot Boots and Lightning Greaves as theme
  upgrades. Virtue and Valor's upgrade drain also runs further (19 swaps, from
  13), trading four of its own Auras that were upgrade slots before: Daybreak
  Coronet, Angelic Destiny, Ancestral Mask and Snake Umbra, none a guide cut.

### The remaining tuner levers (2026-10-24)

The backlog's last tuner items: the wipe read's calibration ((j)), the guide cuts the
tuner protects ((g)), the adds a page held but outranked ((m)) and the subs no search
reaches ((r)). The bar: a change ships if guide-matching adds rise and guide-matching
cuts fall by two at most, or for a cut-side change if cuts rise and adds fall by two
at most; a read-correctness fix ships on correctness with its delta recorded. One
`misses.py` run per row, Spellbook cached. The wipe rows and the two popular-cut rows
are each measured alone against the wipe fixes; M1, M2 and R1 on top of the kept
popular tier (474 / 180 / 57). Columns as in "Theme reach".

| change | swaps / cuts / adds | theme swaps | wipe / int / prot / draw / ramp / theme | tune s · GB | |
|---|---|---|---|---|---|
| HEAD (9e0026ed) | 444 / 169 / 56 | 220 | 2 / 8 / 4 / 8 / 7 / 27 | 7.2 · 1.62 | |
| wipe read: spree and enters-X costs, the reference wipe at four | 436 / 169 / 55 | 215 | 2 / 8 / 4 / 8 / 7 / 26 | 6.4 · 1.71 | exposed three misreads |
| … and no flicker, transform back or event-fired clean sweep | 439 / 170 / 56 | 217 | 2 / 8 / 4 / 8 / 7 / 27 | 7.6 · 1.63 | shipped (read fixes + recalibration) |
| the wipe read leads its upgrades | 438 / 170 / 55 | 216 | 1 / 8 / 4 / 8 / 7 / 27 | 7.5 · 1.63 | rejected |
| popular off-avenue cards as upgrade slots, beside the fringe ones | 478 / 177 / 51 | 204 | 3 / 7 / 4 / 8 / 6 / 23 | 7.8 · 1.63 | rejected |
| … as the last upgrade tier | 474 / 180 / 57 | 217 | 2 / 8 / 4 / 9 / 7 / 27 | 8.3 · 1.70 | kept |
| theme adds: a card on two viable avenues first | 455 / 169 / 46 | 207 | 2 / 6 / 4 / 7 / 5 / 22 | 8.2 · 1.63 | rejected |
| theme adds: synergy and play-rate percentiles blended | 498 / 182 / 53 | 229 | 3 / 5 / 3 / 11 / 4 / 27 | 7.6 · 1.69 | rejected |
| a sub with a main's carers (6) takes one add that also serves a main | 470 / 178 / 57 | 214 | 2 / 8 / 4 / 9 / 6 / 28 | 8.7 · 1.71 | rejected |
| **shipped** | **474 / 180 / 57** | **217** | **2 / 8 / 4 / 9 / 7 / 27** | **8.1 · 1.63** | |

Against HEAD: 30 more swaps, 11 more guide-matching cuts, one more guide-matching add.

- **The wipe read** (ADR-0060's second 2026-10-24 amendment). Wrath of God and
  Damnation read 0.32 because the cheap-clean line sat at three mana, not because of
  "can't be regenerated"; Final Showdown, Spiteful Banditry and Meathook read high
  because their spree mode and their X went uncounted (two cost misreads). Moving the
  line to four mana is a recalibration, not a misread fix: from first principles Wrath
  of God at four is the reference board wipe. The four-mana line let three misreads
  into the wipe fills (Golden Argosy's crew flicker, Jin-Gitaxias's transformed Great
  Synthesis, Sarkhan's Unsealing's cast trigger), which the second row fixes. The
  recalibration was only ever measured together with the misread fixes: 439 / 170 / 56
  against HEAD's 444 / 169 / 56, adds flat and one guide cut more. Now Blasphemous Act
  and Toxic Deluge 0.78, Wrath of God and Damnation 0.76, Final Showdown, Banditry and
  Meathook 0.48; the open leftover is Vanquish the Horde at 0.80, above them all (its
  per-creature discount taken at a full board). The wipe upgrades become Toxic Deluge,
  Wrath of God and Damn. Leading the upgrades, the read still loses Blame Game's
  Blasphemous Act to Vanquish the Horde. In review the flicker veto moved onto the
  shared tree's blink return (`ConceptNode.returns_to`), which also drops Planar Guide,
  Sudden Disappearance and Thieves' Auction from the read; the precon totals stayed
  474 / 180 / 57.
- **Popular cards on no viable avenue** (`focus.popular_upgrade_cards`): off every
  lane, ranked inside `UPGRADE_RANK` but not premium, serving none of the deck's
  viable avenues. Of those cards the precon guides cut 0.28 (27 of 96,
  `precon-audit/cut_splits.py`), against 0.24
  for the decks overall and 0.48 for the fringe upgrade tier. Taken beside the fringe
  ones they spent the budget the deep lane's theme upgrades had (Sliver Swarm lost
  Kindred Discovery, Muscle Sliver and Sliver Legion); as the last tier, after the
  lane's half, every earlier swap stands and the tail adds Decimate, Harmonize,
  Bedevil, Decree of Pain, Burnished Hart, Whirlwind of Thought, Tear Asunder,
  Chandra's Ignition and Lifecrafter's Bestiary as guide cuts, and Guardian Project
  as a guide add. Feed the Swarm stays: it is premium (rank 93).
- **Lane doers the guides trim** (55): 54 are carers, and outside the deep lane's half
  their guide-cut rate is 0.08 to 0.20 in every carer split by role and play-rate
  holding more than four cards (`cut_splits.py`), below the decks' 0.24 — no read
  to try ((a) holds). Sliver Swarm's 11 are Granters,
  judged by their grant (ADR-0040 §4).
- **Outranked adds** (229 at the shipped tune, split against the swaps each tune
  made): theme 76, ramp 45, removal 40, draw 29, protection 27, wipes 12. Against the
  picks of their kind: every pick was more played for 28 theme, 27 ramp, 31 removal,
  18 draw, 13 protection and 9 wipe adds; over what was left of the budget for 22
  theme, 8 ramp and 6 removal; a less-played pick won (band, budget order) for 21
  theme and 7 ramp and 7 draw; 5 theme adds sat below the fit floor. 21 of the 76
  theme adds serve two viable avenues, but ranking those first took the adds to 46,
  and a blend of synergy and play-rate to 53.
- **A sub's one add.** Only Living Energy's Arcum Dagsson, Clever Impersonator and
  Scrap Welder and Deep Clue Sea's Displaced Dinosaurs still serve only a sub; the
  sub's picks there never served a main, so neither deck moved, and elsewhere the
  sub's add reordered upgrades (Squirreled Away's Bitterblossom for Thornvault
  Forager) and cost two guide cuts.

### The last tuner levers (2026-10-24, later)

The backlog's last four tuner items: the board a wipe's discount is read at ((j)),
the replacement doublers' role ((o)), the budget ((m)) and Virtue and Valor's Aura
drain ((r)). The bar as in "The remaining tuner levers". One `misses.py` run per
row, Spellbook cached; each row on top of the row it names (the wipe and Winnow
fixes move no guide card, so every later row is in effect measured alone against
HEAD's guide matches). Columns as in "Theme reach".

| change | swaps / cuts / adds | theme swaps | wipe / int / prot / draw / ramp / theme | tune s · GB | |
|---|---|---|---|---|---|
| HEAD (f601a983) | 474 / 180 / 57 | 217 | 2 / 8 / 4 / 9 / 7 / 27 | 8.4 · 1.54 | |
| J1 wipe discount at a board of eight, generic mana only (on HEAD) | 482 / 180 / 57 | 223 | 2 / 8 / 4 / 9 / 7 / 27 | 8.1 · 1.60 | shipped (read fix) |
| J2 the wipe read leads its upgrades (on J1) | 486 / 179 / 58 | 226 | 2 / 8 / 4 / 9 / 7 / 28 | 7.9 · 1.71 | cleared alone; nothing in the combination, not kept |
| O1 an IR hit's role read off its emitting unit (on J1 + Winnow) | 481 / 180 / 56 | 222 | 2 / 8 / 4 / 9 / 7 / 26 | 7.7 · 1.63 | shipped (read fix, one add fewer) |
| R1 pump gear is a voltron commander's lane doer (on O1) | 479 / 179 / 56 | 221 | 2 / 8 / 3 / 10 / 7 / 26 | 7.9 · 1.49 | shipped (read fix, one cut fewer) |
| M near tie to the cheaper, 0.1 log10 rank (on R1) | 512 / 186 / 56 | 235 | 2 / 6 / 3 / 8 / 7 / 30 | 7.6 · 1.63 | clears (cuts up, adds flat) |
| … 0.2 | 538 / 192 / 59 | 243 | 3 / 6 / 3 / 11 / 6 / 30 | 6.5 · 1.63 | clears |
| … 0.3 (a factor of two in rank) | 546 / 195 / 60 | 248 | 3 / 6 / 3 / 11 / 5 / 32 | 7.6 · 1.57 | kept |
| … 0.5 | 569 / 199 / 61 | 256 | 3 / 5 / 4 / 11 / 6 / 32 | 6.6 · 1.65 | clears; a threefold rank gap is no tie |
| kept combination + J2 | 547 / 195 / 60 | 248 | 3 / 6 / 3 / 11 / 6 / 31 | 6.9 · 1.63 | J2 adds nothing |
| **shipped** | **546 / 195 / 60** | **248** | **3 / 6 / 3 / 11 / 5 / 32** | **7.7 · 1.65** | |

Against HEAD: 72 more swaps, 15 more guide-matching cuts, 3 more guide-matching adds.

- **The wipe discount** (ADR-0060's last 2026-10-24 amendment). A "{1} less for each
  creature on the battlefield" discount counts every creature, yours and the
  opponents'; it was read at six and could eat the colored mana. A generic reduction
  never touches the colored part (CR 118.7a; Blasphemous Act's ruling: never below
  {R}), and the board is now eight, two a seat at the four-seat table Undaunted is
  read at. Blasphemous Act 0.82 ({R}), Vanquish the Horde 0.80 ({W}{W}), Toxic Deluge
  0.78, Wrath of God and Damnation 0.76. Only Quick Draw moved: Blasphemous Act over
  Cyclonic Rift, and eight more swaps on the mana saved. Leading the wipe upgrades
  with the read then cleared the bar alone (Jhoira of the Ghitu in Timey Wimey, on the
  budget it moved — no wipe add) and added nothing beside M; one of its picks is a
  wipe phase misreads (Harsh Mercy, whose chosen-type spare phase drops), so it is
  not kept. Winnow's dropped same-name condition is read (`removal._CONDITION_DROPPED`,
  a retirement canary); removal only gates, so it can move no swap.
- **The doublers' role.** A theme hit read off a card's idents takes its role from the
  unit that emits the ident (`ranking._unit_role`): a replacement that emits the
  lane's ident modifies the event the lane is built on (CR 614.1a), so Parallel Lives,
  Anointed Procession, Doubling Season and Hardened Scales are payoffs (Parallel Lives
  scores 3.35 under Squirreled Away's tokens, where it scored 1.35); an ident the
  lanes mark as a doer subject (`signal_keys.DOER_SUBJECTS`) is an enabler; anything
  else keeps the clause test. The doublers already passed the fit floor, and
  play-rate orders the fitting cards, so no doubler guide add was gained; Virtue and
  Valor took Hardened Scales and lost Sram, Senior Edificer (one guide add fewer).
  Shipped as a read fix.
- **Virtue and Valor's Aura drain.** Ellivere holds `voltron_makers|you|` (she attaches
  Roles); the Auras that pump their creature emit `voltron_makers|you|pump`, a subject
  of its own, so no lane counted them and they sat in the off-lane upgrade slots. As
  the commander's lane doers (`metrics._LANE_DOER_IDENTS`) they leave the off-lane
  tier, but the deep lane's least-played half still holds them: the tune trades
  Daybreak Coronet, Angelic Destiny, Ancestral Mask and Snake Umbra as lane slots (for
  Whispersilk Cloak, Hardened Scales, Sram and Heroic Intervention at the shipped
  tune; 20 swaps). Shipped as a read fix (adds flat, one guide cut fewer).
- **The budget.** Where play-rate orders a page, the first eligible add is weighed
  against the next ten, and a near tie that costs less is the add: play-rates within
  0.3 log10 rank (a factor of two) and, for a job whose read orders, read scores within
  0.1 (`swaps._near_tie`). Every width cleared the bar and wider kept gaining, which
  says the budget binds; 0.3 is the widest that is still a tie. Timey Wimey ran 21 to
  27 swaps (Jhoira of the Ghitu, The Millennium Calendar and Wheel of Fate added);
  Blame Game traded Aurelia, the Law Above and Bothersome Quasit for Firemane
  Commando.

## What is left

`docs/plans/backlog.md`, "What the polymorph tune and the 25-precon audit still
get wrong" and "Every held serve spec is converted": the phase gaps behind the
interaction role, the superfriends veto, animation and the converted serves; the
text-mirror leftovers; the phase gaps nothing can read; the lane gaps the censuses left (a destination subject on
`creature_recursion`, a spell-type subject on `cost_reduction`, the edict lane,
keyword token-copy makers, `FlipCoin.win_effect`).

## Rerunning

```
# lists
curl -sL https://mtgjson.com/api/v5/decks/SliverSwarm_CMM.json -o SliverSwarm_CMM.json
python3 -I docs/plans/precon-audit/to_decktxt.py SliverSwarm_CMM.json deck.txt
cd mtg-utils && uv run parse-deck deck.txt --format commander --output deck.json
uv run python ../docs/plans/precon-audit/guide_sizes.py ROOT  # writes ROOT/budgets.json
uv run deck-tune deck.json --max-swaps 30 --budget <budgets.json[Name]> --output tune.json
# compare: decks/<Name>/tune.json beside precon-audit/<Name>.md
python3 -I docs/plans/precon-audit/compare.py
```

The tunes (and `misses.py`'s six workers) can start in parallel with no warm-up
step. An edit to a lane or a preset stales the signals index beside the bulk; the
first tune rebuilds it (about 2 min) under a lock, and the tunes started
meanwhile wait for that build and then read it, so the rebuild happens once rather
than once per worker (backlog (l), 2026-10-23). To take the wait before the
workers start instead, run `uv run build-signals-index` first. With a warm index a
precon tune takes 11–17 s (20–60 s before): its ramp, card-draw and board-wipe
pages no longer build trees for every card in the pool.
