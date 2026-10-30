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

### The tuner-policy leftovers (2026-10-24, last)

Backlog (j)'s wipe and job leftovers and (r)'s non-viable lanes. The bar as in "The
remaining tuner levers": a policy change, measured alone against the baseline, ships
only if guide-matching adds rise and guide-matching cuts fall by two at most (or cuts
rise with adds flat); a read fix ships on its correctness, with its delta recorded.
One `misses.py` run per row, Spellbook cached; every experiment row on W2 (whose
guide matches equal HEAD's). Tune seconds are the median per precon.

| change | swaps / cuts / adds | theme swaps | tune s | |
|---|---|---|---|---|
| HEAD (e3d1c6d5) | 546 / 195 / 60 | 248 | 6.1 | |
| W1 the wipe read's listed misreads (on HEAD) | 546 / 195 / 60 | 248 | 6.1 | no swap moved |
| J2 the wipe read leads its upgrades (on W1) | 547 / 195 / 60 | 248 | 5.7 | flat, rejected |
| W2 W1 + a draw "each player who controls" gets is no rider | 546 / 195 / 60 | 248 | 5.8 | **shipped** (read fixes) |
| J2 again (on W2) | 547 / 195 / 60 | 248 | 5.8 | flat, rejected |
| removal deck fit A: a deck with two or more instant any-permanent answers takes a targeted one first | 546 / 196 / 59 | 249 | 6.5 | rejected |
| removal deck fit B: A, and a deck with fewer takes a flexible one first | 544 / 196 / 56 | 249 | 6.5 | rejected |
| the ramp read orders its upgrades, blended with play-rate | 532 / 195 / 56 | 243 | 6.6 | rejected |
| a commander-paid lane below the viable floor gets one swap off its serve page, cut from the upgrade pool | 550 / 196 / 58 | 243 | 6.0 | rejected |
| … only a lane at least the emerging floor deep | 548 / 195 / 60 | 244 | 5.9 | flat, rejected |
| HEAD (04925758) | 542 / 195 / 61 | | | |
| W3 the last five wipe misreads (on 04925758) | 543 / 196 / 61 | 249 | 5.1 | **shipped** (read fixes) |

- **The wipe read's misreads (W1, W2).** An X paid in cards is an X (Sickening and
  Devastating Dreams, CR 107.3a: 0.80 to 0.48); a pitch cost is the cards it pitches,
  each a mana (Force of Despair, CR 118.9); "lands you control don't untap during your
  next untap step" costs the sweep again (Bontu's Last Reckoning, CR 502.3: 0.78 to
  0.28); Massacre Girl's delayed "whenever a creature dies this turn" shrink chains
  (CR 603.7a, its ruling: 0.15 to 0.39); a `Choose` the sweep's filter never reads
  limits it, a spare when each player chooses (Harsh Mercy 0.78 to 0.34), else a
  narrow slice (Sudden Demise, Void); and the clauses phase drops whole are read by
  name with canaries (Extinction narrow, Swarmyard Massacre a spare, Do or Die a
  one-sided pile, CR 700.3). W2 adds the rider fix the J2 picks exposed: Shatter the
  Sky's and Depopulate's draw goes to each player who controls a big or multicolored
  creature, not to the caster (0.82 to 0.76, Wrath of God's). ADR-0060's board-wipe
  row: Spearman 0.501 to 0.510, guide adds still at the 84th percentile, 9 of 19 in
  the top decile (8), the cut side unchanged (9 of the bottom two). On the tunes only
  VelociRampTor (Wrath of God over Shatter the Sky) and Multiverse Reforged (two wipe
  adds swap cuts) move.
- **The wipe read leading (J2), a measured verdict.** Flat twice. Its picks change in
  six precons (Blood Rites, Enduring Enchantments, Grand Larceny, Living Energy, Timey
  Wimey, VelociRampTor), and no guide for those six adds a wipe, so no wipe order can
  gain there; Timey Wimey's one add moved (Lotus Bloom for Jhoira's Timebug) on the
  budget. Of the 19 guide wipe adds, the tuner makes 3 (Blasphemous Act, Cyclonic
  Rift, Vanquish the Horde); the reachable rest are deck-fit picks: Raise the Palisade
  and Faerie Slumber Party in Fae Dominion (a sweep that spares the deck's tribe),
  Expel the Interlopers and Tragic Arrogance in Virtue and Valor (sweeps that leave
  one big creature), Chain Reaction and Winds of Abandon in Blame Game. What would
  change it is a deck-fit wipe read (the share of the deck's own board a sweep
  leaves), not a better card read. The misreads left then were no guide add, and
  two were shipped picks in decks with no in-scope guide wipe add to displace
  (Deluge of Doom in Sultai Arisen, Boompile in Tinker Time); W3 reads them.
- **The last wipe misreads (W3).** An X the card defines (CR 107.3) reads by what
  it counts, off the quantity's typed shape (`crosswalk.count_operand_qty`,
  `quantity_scope`), wrapped in phase's `Multiply(-1, …)` or bare: a bounded count is
  narrow (distinct card types, Deluge of Doom 0.78 to -0.13; basic land types, five
  by CR 305.6, Planar Despair 0.30 to -0.08; life gained this turn, Essence Pulse
  0.82 to 0.00; cards in hand, cut to seven at cleanup by CR 402.2, Kagemaro 0.30 to
  -0.10); an object count of yours the deck fills scales (Mutilate's Swamps 0.76,
  Terror Tide's permanent cards in your graveyard 0.76, Terisiare's Devastation's
  artifacts 0.50, Immolating Gyre 0.13 to 0.51, Themberchaud -0.06 to 0.18), unless
  it names a type only a deck built on it holds (Gates Ablaze's Gates, Olivia's
  Wrath's Vampires 0.39 to 0.15, Thundercloud Shaman's Giants: narrow). A sweep under
  a coin flip is gated (Boompile, CR 705.1-705.2: 0.58 to 0.00). A creature's
  activation costs its mana as any permanent's does (CR 602.2: Jaya Ballard, Task
  Mage 0.66 to 0.10, Infected Vermin 0.86 to 0.36). A discount behind a board-count
  condition is taken on the board the read assumes (Hour of Revelation, unchanged at
  0.72); one behind any other condition at half, as the ramp read halves gated mana
  (CR 601.2f; Avenge 0.82 to 0.36). And a token another player creates in the
  sweep's unit is theirs (CR 111.2): no rider and no clean sweep (March of Souls 0.36
  to 0.16, The Phasing of Zhalfir 0.82 to 0.18, Mogg Infestation 0.61 to 0.41).
  ADR-0060's board-wipe row: Spearman 0.510 to 0.526, guide adds at the 86th
  percentile (84th), 9 of 19 in the top decile, the cut side unchanged. On the tunes:
  Sultai Arisen takes Terror Tide for Deluge of Doom, Tinker Time Ashling's Command
  for Boompile (the mana saved buys a guide cut, Vedalken Humiliator), and Eldrazi
  Unbound Blasphemous Act over Damn. Reading Gates as filled made Gates Ablaze
  VelociRampTor's wipe over Wrath of God, which the build-around rule undoes.
- **Removal's deck fit.** Beast Within, Chaos Warp and Generous Gift read alike (0.61)
  and Beast Within is the most played, so play-rate's pick recurs (14 upgrades, many of
  them for an any-permanent answer the deck already ran: Casualties of War, Cast Out,
  Putrefy, Terminate). A deck already holding two instant any-permanent answers taking
  a targeted one moved the recurrence to Abrade (12) and lost Blood Rites' Generous
  Gift; also taking a flexible one first where the deck has fewer lost Blame Game's
  and VelociRampTor's Swords to Plowshares and Path to Exile. The guides add both kinds
  whatever the deck's flexible count.
- **Ramp.** Fellwar Stone is the ramp add in 10 upgrades: the most played two-mana rock
  not already in the deck, reading as Arcane Signet does (0.70). It reads as fixing
  though its colours are an opponent's lands' (phase's `OpponentLandColors`), but the
  fixing weight is 0.03, so the correction moves nothing (not made). The ramp read
  blended into the order took Fellwar Stone to none and gained Desert Bloom's
  Exploration, but Mana Vault took 9 upgrades, Enduring Enchantments lost Fertile
  Ground, and Virtue and Valor (two), Sliver Swarm and Deep Clue Sea lost adds
  elsewhere in their tunes.
- **Lanes below the floor ((r)).** Blood Rites' sacrifice package is not the
  commander's lane by the signal read: Clavileño holds Vampire, Demon and Combat only,
  so no commander-paid rule reaches it. Ten precons hold a lane below the viable floor
  whose carers include the commander; an emerging lane already raises an issue, but its
  remedy cuts only from the generic pool, which the dead-weight drain empties first
  (one such swap in 25 precons). Paying one swap per such lane from the upgrade pool
  gained Squirreled Away's Doubling Season, but the shallow lanes' pages are noise
  (Platinum Angel for "Life-loss insurance", Coveted Jewel for "Targeted draw") and
  cost Virtue and Valor two adds; held to the emerging floor it was flat (Timey
  Wimey's Herald's Horn took Jhoira's Timebug's budget).

### The commander's lane read (2026-10-25)

Backlog (r)'s new read: Clavileño grants "When this creature dies, draw a card and
create a … Vampire Demon" to the attacking Vampire it targets, so it is a death payoff
for every Vampire it hits (CR 113.1a, 113.7, 603.3a, 700.4). The bar as in "The
tuner-policy leftovers". One `misses.py` run per row, Spellbook cached; tune seconds
are the median per precon.

| change | swaps / cuts / adds | theme swaps | tune s | |
|---|---|---|---|---|
| HEAD (c3210f12) | 543 / 195 / 60 | 248 | 5.3 | |
| a granted dies payoff reads as `death_matters\|you` | 543 / 195 / 60 | 248 | 6.1 | **shipped** (read fix) |
| … and a held lane as deep as a main never folds into a held tribe | 544 / 196 / 62 | 249 | 6.0 | **shipped** |
| … and no cut goes to a piece a near-miss add completes | 542 / 195 / 61 | 248 | 5.9 | **shipped** (correctness) |

- **The read.** `crosswalk.iter_granted_triggers` pairs each granted trigger with
  its grantee, threading "It gains" / "those creatures gain" to the chosen target.
  Over the legal pool eight cards gain `death_matters|you` and none lose an ident:
  Clavileño, Showstopper, Rabid Attack, Galuf's Final Act, Fall of Gil-galad and Time
  Lord Regeneration (granted to a target or your team), Infernal Scarring (the
  enchanted creature) and Doom Weaver (a soulbond pair). Left out: a grant to an
  opponent's creature (Mathas, Putrid Hexhag: the trigger's controller is the
  creature's, CR 603.3a), to every creature (Endless Whispers), to the card itself
  or a token's own ability (the Pest makers), and a grant that returns the dying
  creature (Feign Death, Kaya the Inexorable). Alone it moved no swap: Aristocrats
  is now held, 28 deep, but 26 of its members are Vampires, so it folded into
  Vampire tribal.
- **The tribe fold.** A tribe's page is a type search, so a lane folded into it
  loses the page that holds its cards beyond the tribe. Of the 25 precons only Blood
  Rites holds a lane as deep as a main (20) that folded into a held tribe; Blood
  Rites' Combat (19) and VelociRampTor's Toughness as power (17) are shallower and
  still fold. Aristocrats is Blood Rites' second main, and its tune adds Skullclamp
  (the card-draw fill) and Victimize, both guide adds, and cuts Exquisite Blood,
  one guide's cut. That cut was a bug the deeper drain exposed: the tune's
  near-miss swaps add five cards that complete Exquisite Blood. Pyre of Heroes
  and Lich-Knights' Conquest still have no search; Altar of Dementia, Diabolic
  Intent, Razaketh and Dictate of Erebos are on the Aristocrats page, outranked.
  Theme guide adds no search reaches: 164, from 169.
- **The near-miss pieces.** Combo protection covered only the combos a deck holds
  before the tune. A near-miss issue now names the deck cards its add completes
  (`Issue.relies_on`), and once the swap is taken no later cut takes one of them
  (`swaps.propose_swaps`); a near-miss whose piece is already cut takes no add. Three
  precons cut a piece their own near-miss add needed: Blood Rites (Exquisite Blood,
  beside Sanguine Bond and four more), Abzan Armor (Jaws of Defeat, beside Overkill)
  and Multiverse Reforged (Archfiend of Despair, beside Unstoppable Slasher). Blood
  Rites loses Victimize, whose upgrade slot was Exquisite Blood and which no other
  upgrade cut replaces, and the guide-matched Exquisite Blood cut; Abzan Armor and
  Multiverse Reforged take other cuts and match no guide card differently.

### The deck-fit wipe read and the tune's speed (2026-10-25)

Backlog (j)'s lever and its small item, and (l). The bar as in "The tuner-policy
leftovers". Three `misses.py` runs, Spellbook cached, each tune's whole result
dumped and compared byte for byte; the speed and final runs seed the signals index
and attach the provenance and job-read sidecars first, as `deck-tune` does. Tune
seconds are the median per precon. The lead was measured on the four precons it can
move (a deck most of whose creatures share a type), one process, the same cache,
the lead off and on.

| change | swaps / cuts / adds | tune s · GB | |
|---|---|---|---|
| HEAD (a825a59c) | 543 / 196 / 61 | 6.1 · 1.58 | |
| S the speed levers (on HEAD) | 543 / 196 / 61 | 4.7 · 1.25 | **shipped**: all 25 results byte-identical |
| W S + the wipe read's amounts | 543 / 196 / 61 | 4.4 · 1.23 | read fixes: all 25 byte-identical |
| W2 W with the deck's count in proportion (review fixes) | 543 / 196 / 61 | 4.9 · 2.03 | **shipped** (read fixes): all 25 byte-identical; the run rebuilt the signals index and the phase-records sidecar |
| L W + the deck-fit lead, four tribal precons (off → on) | 77 / 23 / 18 → 73 / 23 / 16 | | rejected |

- **The deck-fit read (L).** What a sweep leaves of the deck's own permanents, read off
  its filter against the deck's records: a chosen creature type is the deck's most
  common, a bound the caster sets sits at the kill size (Expel the Interlopers names
  four), one each is one of the two creatures a seat, a one-sided sweep leaves all,
  damage or a shrink spares a toughness above it. Raise the Palisade leaves 28 of Fae
  Dominion's 29 creatures, Toxic Deluge none. The deck-free read already prices a
  spare and one-sidedness at the average deck's board, so the read moves nothing
  where the deck is average; it leads only in a deck most of whose creatures share a
  type. There Raise the Palisade became Fae Dominion's wipe upgrade (a guide add), but
  it costs $0.29 less than Toxic Deluge, which made Nezahal affordable as the first
  card-draw upgrade, so the near tie took Talion, the Kindly Lord ($7.92) and the
  budget ran out five swaps earlier: Deadly Dispute, Likeness Looter and Spellstutter
  Sprite, all guide adds, lost. Blood Rites (Winds of Abandon for Olivia's Wrath, and
  Damn upgraded to Toxic Deluge), Sliver Swarm (Cyclonic Rift, Raise the Palisade) and
  VelociRampTor (Storm's Wrath, Austere Command, Mizzium Mortars, Winds of Abandon)
  moved no guide card. Ellivere's Expel the Interlopers and Tragic Arrogance and Blame
  Game's Chain Reaction and Winds of Abandon need a second wipe slot: each deck's one
  wipe upgrade is already a guide add (Vanquish the Horde, Blasphemous Act). Rejected,
  and the read with it.
- **The wipe read's amounts (W).** No wrapper decides an amount that counts nothing.
  The size of an object of the caster's own reads at the kill size: one paid as a
  cost (Ichor Explosion's sacrificed creature, its ruling; Corpse Explosion's exiled
  card, now a lethal sweep) or the greatest mana value of a commander you own
  (Cloudkill). A "this way" set of the caster's own cards scales (Specter of
  Mortality's creature cards exiled from your graveyard); any other stays narrow
  (Volcanic Eruption's "Destroy X target Mountains" may take anyone's, yours too,
  but nothing makes them yours and X caps them). In a deck (`JobRead.in_deck`), a
  count of a type only a deck built on it holds is what the deck has out: its share
  of the deck's cards over a board of eight of its own permanents, the sweep killing
  in proportion to the kill size, so the read rises smoothly with the count. Olivia's
  Wrath in Blood Rites (36 Vampires of 100: 2.88 out) reads 0.32, from 0.15; Gates
  Ablaze -0.13 with no Gates, -0.08 with 3, 0.02 with 8, 0.14 with 15. A sacrificed
  creature's size is the deck's biggest, a negative power kept (Loot, the Anomaly's
  -2). The first cut (a count of eight or more read as a full sweep) jumped from
  -0.13 to 0.78 between seven Gates and eight. An amount drawn from a negative power
  is 0 (CR 107.1b). No tune changed.
- **Speed (S).** A Blood Rites tune profiled at 7.9 s, now 5.6. Each candidate's ranking
  readout is computed once per tune (`rank_candidates`' `scores`: 1,591 readouts for
  1,027 cards before), `deck-tune` seeds the signals index before the deck is read (the
  deck's cards paid 153 live extractions for their keys and their idents; 253 in
  all, 81 now), and the phase card-data is read per oracle_id from a sidecar beside it
  (`trees.PhaseRecordIndex`: 1.2 s and every record decoded before, 0.02 s and only
  the ones a tune reads now; the peak RSS fell by a third of a gigabyte).

### The budget's even share (2026-10-25)

Backlog (m)'s largest lever, the adds a page held but outranked, and (j)'s small
read. The bar as in "The tuner-policy leftovers". Two `misses.py` runs, Spellbook
cached (rows marked *run*). The other rows were screened first: one process, the 25
tunes in sequence (`find_add` traced), scored against HEAD's guide lists, which
read HEAD as 543 / 189 / 58 (the run's name matching differs by a few cards); the
screen reproduces a run's swaps exactly.

| change | swaps / cuts / adds | |
|---|---|---|
| HEAD (f9e25ec9), *run* | 543 / 195 / 59 | |
| E1 the near tie only where the budget binds (screen) | 543 / 188 / 59 | +1 add, -1 cut |
| E2 E1, and an unbound theme page's near tie to the better fit (screen) | 541 / 187 / 58 | rejected |
| Auras only on Virtue and Valor's suit-up page (screen, that deck) | 20 → 20 swaps, adds -1 | rejected |
| E3 E1, and past the share the window's first card within it: job adds only (screen) | 565 / 192 / 63 | |
| … every add (screen) | 560 / 191 / 63 | |
| … without E1 (screen, job adds) | 566 / 192 / 60 | |
| the even share (E3, every add, one rule; screen) | 560 / 191 / 64 | |
| **the even share**, *run* | **560 / 197 / 66** | **shipped** |
| … and the guarded Spine fills too (screen, against 560 / 191 / 64) | 557 / 191 / 63 | rejected |
| … and the cheapest card in the window, near tie or not, past the share (screen, same) | 563 / 192 / 64 | adds flat, rejected |
| the wipe read's caster-picked power, *run* | 560 / 197 / 66 | **shipped** (read fix, no swap moved) |

Against HEAD: 17 more swaps, 2 more guide-matching cuts (Staff of Compleation in
Abzan Armor, Siege-Gang Commander in Mardu Surge), 7 more guide-matching adds:
Ohran Frostfang, Aurelia, the Law Above, Victimize, Insidious Roots, Ripples of
Undeath, Kellan, Inquisitive Prodigy, Crucible of Worlds, Faerie Mastermind, Muscle
Sliver, Lotus Bloom, Liquimetal Torque, Boros Charm and Clever Concealment, for
Firemane Commando, Cyclonic Rift, Likeness Looter, Spellstutter Sprite, Homing
Sliver and Elemental Bond. Per job: wipe 3 → 2, removal 6 → 7, protection 3 → 4,
draw 11, ramp 5 → 8, theme 31 → 34.

- **What outranks the guide adds.** Every `find_add` traced at HEAD: of the
  outranked guide adds, 122 sat on theme pages (91 behind a more-played pick; 17
  ahead of it but passed over for a cheaper near tie; the rest unaffordable,
  overshooting a full role, or on a page that picked nothing), 37 on removal
  pages, 26 ramp, 21 draw, 16 protection, 6 wipes, 24 on a support or filtered
  page. No card read separates them from the picks. On the theme pages the tune
  read, a commander pair read (ADR-0042's rows) fires on 8.0% of the guide adds and
  7.3% of the rest; 31% of the outranked guide adds carry a template role, against
  28% of the theme picks. The top fifth of a page's synergy holds guide adds at
  twice the page's rate (0.093 against 0.04), but every synergy-led order has lost
  in the tune (payoffs first, the blend, E2). What the trace did show is the
  budget: in the tunes that spent their budget, card-draw upgrades took $436 for two
  guide adds and protection upgrades $201 for none, against $569 for 24 on theme
  upgrades (Esper Sentinel, $55, was an add in five precons, Rhystic Study, $68, in
  three, Deflecting Swat, $71, in two).
- **The even share** (`swaps.find_add`, `_Purse.share`). What is left over the
  swaps still open is the share an add may cost without leaving any later add
  less. The first eligible card within it is the add; past it the budget binds,
  and the next ten are weighed: the first that fits the share is the add (most
  played first, and still an upgrade of the cut), else the cheapest near tie, as
  before. Two effects: an unbound tune no longer trades its most-played pick for
  a cheaper near tie it never needed (Victimize over Deadly Dispute in Blood Rites,
  Aurelia over Geode Rager in Blame Game, Muscle Sliver, Boros Charm), and a bound
  one stops spending half its budget on one staple (Blame Game spends $44 of $169,
  from $162). Abzan Armor and Tinker Time reach thirty swaps on the money saved,
  Mardu Surge twenty from sixteen. Fae Dominion loses two guide adds: past the share, Glen Elendra
  Guardian ($0.37) takes Spellstutter Sprite's ($3.67) slot. Most tunes now end
  on their cut pool, not their budget.
- **Variants.** Job adds only (E3, a theme card has no substitute in its window)
  matched the same adds with five swaps more; one rule for every add is the simpler
  statement. The guarded Spine fills (ADR-0040's avenue guard) keep their first
  on-avenue pick: the share there cost Quick Draw's Jeska's Will and Virtue and
  Valor's Clever Concealment for Fae Dominion's Likeness Looter (one add fewer).
  Past the share, the cheapest card in the window whether or not it is a near
  tie matched the same adds with one guide cut more; this task's bar asks adds
  to rise, so the near tie stays. The share never overrides the on-theme rule:
  on a theme page every card in the window fits the theme, and card draw's and
  ramp's order already puts an on-theme near tie first (`JobRead.theme_ties`;
  the other jobs measured negative on it, backlog (j)), so the share picks
  among an order the rule has already set.
  Screened rows differ from a run by a guide add or two (the screen read HEAD as
  58 adds, the run 59); the shipped rule's gain is the run's.
- **The wipe read's caster-picked power** (backlog (j)). A size read off a target
  among the creatures you control (Chandra's Ignition, Waltz of Rage; Nibelheim
  Aflame, Showstopping Surprise and Nova Flame's "it") or off the creature the
  sweep has you sacrifice (Rupture: the instruction names no player, so the caster
  follows it, CR 608.2c, and sacrifices one they control, CR 701.21a) is the
  caster's pick, read at the kill size (the deck's biggest in a deck), as a
  cost's object is; the source's own power is its printed power (Jack of Hearts,
  Volatile Hero), never below 0 (CR 107.1b). Chandra's Ignition reads lethal (it
  read 2); no tune moved.

### The cut pool (2026-10-25, later)

Backlog (m)'s cut-side levers: the guide cuts the tune never reaches and the ones the
popularity threshold and the lanes shield. The bar as in "The tuner-policy leftovers",
and for a cut-side change: guide-matching cuts rise and guide-matching adds hold. Every
missed guide cut was traced first (one process, the 25 tunes in sequence, the cut
ranking and every cut the swap loop took or passed over recorded): 17 of the 26 "never
reached" sat in an over-band trim's pool, which made one trim per issue whatever the
excess (Animated Army's ramp, 26 against a band of 10-12, trimmed one); and the cards
the upgrade tiers spared for caring about a built theme split by which theme. Past
`UPGRADE_RANK`, off the commander's lanes, the guides cut 13 of the 24 cards caring
only about a sub, 22 of the 52 caring only about an emerging or folded theme, and 5 of
the 17 caring about a main, against 0.24 of the decks' cards. Rows marked *run* are
`misses.py` runs (Spellbook cached); the rest are screens, which reproduce a run's swaps
exactly but match guide names a little differently (HEAD screens as 562 / 196 / 67).
Each row is on the row above unless it says otherwise.

| change | swaps / cuts / adds | |
|---|---|---|
| HEAD (b91ab000), *run* | 562 / 199 / 67 | |
| E1 an over-band trim drains its excess | 593 / 209 / 67 | cuts +13, adds flat: **shipped** |
| E2 only a main theme's carers are spared the upgrade tiers | 645 / 236 / 67 | cuts +27, adds flat: **shipped** |
| E1 + E2, *run* | 645 / 240 / 67 | |
| E3 an off-theme card's theme upgrade need not be more played | 654 / 242 / 71 | cuts +6, adds +4: **shipped** |
| E4 … and may cost one band more | 658 / 243 / 74 | cuts +1, adds +3: **shipped** |
| E5 the commander's held subs share the theme adds (on E4) | 663 / 243 / 66 | adds -8: rejected |
| E6 an over-band trim's add shares the theme over the mains (on E4) | 658 / 243 / 74 | flat: not kept |
| E7 a sub shields no popular card either (on E4) | 669 / 248 / 75 | cuts +5, adds +1: **shipped** |
| E1-E4 + E7, *run* | **669 / 252 / 75** | **shipped** |
| E8 a lane feeder may become a less-played payoff of the main (on E7) | 669 / 248 / 74 | adds -1: rejected |
| E2b a theme folded into a main shields its carers (on E7) | 661 / 243 / 76 | cuts -5, adds +1: rejected |

Against HEAD: 107 more swaps, 53 more guide-matching cuts (precision 0.38, from 0.35),
8 more guide-matching adds. Gained adds: Bothersome Quasit, Teferi's Protection,
Cyclonic Rift, Conduit of Ruin, Emrakul, the Promised End, Thought-Knot Seer, Razorkin
Needlehead, Aether Refinery, Aether Revolt, Gonti's Aether Heart, Ugin, the Spirit
Dragon; lost Ohran Frostfang, Insidious Roots and Ulamog, the Ceaseless Hunger (the
budget the new swaps spend). Lost cuts, to the swap cap or the budget the new cuts
spend first: Dragonlord Dromoka, Rhox Faithmender, Staff of Compleation, Decimate,
Harmonize, Burnished Hart, Bedevil, Faerie Formation, Sage of the Beyond, Brainsurge,
Shark Typhoon, Vedalken Humiliator. Eleven tunes now reach the thirty swaps, four end
on their budget, and ten on their cut pool.

- **The over-band trim (E1).** `cut_candidates` lists exactly a row's excess, the least
  played first; the trim now drains it (`Remedy.drain`) as dead weight does. Animated
  Army trims thirteen more ramp cards (Alchemist's Talent, Burnished Hart, Llanowar
  Loamspeaker, Prosperous Bandit, Rain of Riches and Domri are guide cuts), Eldrazi
  Unbound its interaction, ramp and draw (Duplicant, Bane of Bala Ged, Unstable
  Obelisk, Endless Atlas), Squirreled Away and Fae Dominion theirs. Of the 75 cards
  the trims cut, 33 are guide cuts.
- **A sub is no shield (E2, E7).** A carer of a built theme was spared every upgrade
  tier, and a popular card serving any viable avenue the popular tier; now only a
  main does either. The newly cut guide cuts include Blame Game's emerging themes'
  carers (Otherworldly Escort, Prisoner's Dilemma, Selfless Squire), Enduring
  Enchantments' folded themes' (Cunning Rhetoric, The Binding of the Titans, The
  Mending of Dominaria, Nyx Weaver), Endless Punishment's sub carers (Mask of
  Griselbrand, Séance Board, Star Athlete, Enchanter's Bane), Living Energy's
  Artifacts sub (Saheeli, Sublime Artificer, Whirler Rogue, Adaptive Omnitool),
  Sultai Arisen's Harrow, Springbloom Druid and Noxious Gearhulk. A popular card on a
  sub alone is a guide cut at the decks' rate (0.24), so E7 rides on E2's statement
  rather than a read of its own; keeping the carers of a theme folded into a main
  shielded (E2b) lost five guide cuts, Enduring Enchantments' four among them, for
  one add.
- **Off the main theme onto it (E3, E4).** A card with no job is upgraded on the main
  theme, and had to be out-played by its add at no higher band. For a card serving
  none of the mains (`swaps._upgrades`' `off_theme`) the swap's point is moving the
  slot onto the main theme, so the add need not be more played, and it may cost one
  band more, as a job upgrade may. Living Energy's Energy page held no fitting card
  played more than its Artifacts sub's Whirler Rogue (rank 2245), so the slots were
  passed over; now the tune cuts Whirler Rogue, Adaptive Omnitool, Bootleggers' Stash
  and Triplicate Titan and adds Gonti's Aether Heart, Aether Refinery and Aether
  Revolt, and Eldrazi Unbound reaches Conduit of Ruin and Emrakul, the Promised End.
  On a card already on a main (most lane feeders) both gates stand; E8 let a feeder
  become a less-played payoff of the main lane and lost an add. The rule reads the
  card, not its tier: 23 deep-lane slots serve only a held sub or a folded lane,
  and leaving them their gates moved no swap.
- **What the trace left.** Of the guide cuts still missed: 57 lane doers outside the
  half and 44 popular cards (premium, or on a main) as before, (a) and (g); 23 in
  the popular tier past the swap cap or the budget; 13 protected; 8 main carers (5
  of 17 past `UPGRADE_RANK`). The held subs as theme avenues (E5) took Living
  Energy's Roaming Throne and Grand Larceny's Praetor's Grasp but spent the adds of
  six decks on the subs' staples, as every sub sharing did before.

### The open levers, closed (2026-10-26)

Backlog (m)'s levers and the open items of (g), (j) and (r). The bar as in "The
tuner-policy leftovers": a policy change ships if guide-matching adds rise and
guide-matching cuts fall by two at most, or cuts rise with adds flat; a read fix ships
on its correctness, with its delta recorded. Rows marked *run* are `misses.py` runs
(Spellbook cached); the rest are screens (one process, the 25 tunes in sequence),
which read HEAD as 680 / 252 / 76. Each row is on the row above unless it says
otherwise.

| change | swaps / cuts / adds | |
|---|---|---|
| HEAD (5fd0a053), *run* | 680 / 256 / 76 | |
| G1 a solid Granter is an upgrade slot, a premium one never | 699 / 258 / 80 | **shipped** |
| G2 a main shields its carers, not its feeders: a popular main feeder is the last slot | 711 / 264 / 80 | cuts +6, adds flat: **shipped** |
| A1 a theme upgrade of a main card may be a near tie in play-rate that fits better (on G2) | 721 / 268 / 78 | adds -2: rejected |
| S1 a Spine fill or closer takes a jobless upgrade slot before a lane slot (on G2) | 711 / 264 / 81 | **shipped** |
| B1 a theme upgrade may cost a band more where the curve has room | 713 / 264 / 81 | flat: rejected |
| P1 only a combo that ends the game protects its pieces | 706 / 264 / 80 | adds -1: rejected |
| U1 a role card's upgrade moves onto the theme while its row stays above its floor | 667 / 251 / 86 | cuts -13: rejected |
| U2 … only from a row at its max | 672 / 254 / 84 | cuts -10: rejected |
| U3 U2, the theme's add held to the even share | 703 / 263 / 85 | clears |
| U4 U1, the theme's add held to the even share | 698 / 260 / 90 | cuts -4: rejected |
| U5 U4, a cut on no main only | 704 / 262 / 86 | clears at the edge |
| U6 U3, a cut on no main only | 712 / 264 / 81 | flat |
| U7 U3 or U5 | 700 / 261 / 90 | cuts -3: rejected |
| U8 U1, the theme's add no dearer than the job's | 708 / 263 / 86 | clears |
| U9 U2, the theme's add no dearer than the job's | 710 / 265 / 86 | **shipped** |
| J1 an on-theme card reading within a tie of the cut passes the play-rate gate (draw, ramp) | 710 / 264 / 87 | noise, none of its targets: rejected |
| G3 the lane's feeders, then the popular tier, then the lane's carers | 715 / 269 / 84 | adds -2: rejected |
| F1 a full role read off the running counts, not the deck's | 694 / 258 / 82 | rejected |
| G1 + G2 + S1 + U9, *run* | 710 / 269 / 86 | |
| R the size referent (`crosswalk.quantity_referent`) | 710 / 265 / 86 | **shipped** (read fix, no swap moved) |
| U10 U9 for protection at the Shape's target | 710 / 265 / 88 | **shipped** |
| G1-U10, *run* | 710 / 269 / 88 | |
| G4 a Granter's slot may go to a better grant | 713 / 267 / 88 | cuts +2, adds flat: **shipped** |
| **shipped**, *run* | **713 / 271 / 88** | |

Against HEAD: 33 more swaps, 15 more guide-matching cuts, 12 more guide-matching adds.
Gained adds: Baeloth Barrityl, Firemane Commando, Life of the Party, Anguished
Unmaking, Utopia Sprawl, Wild Growth, Blaster Hulk, Izzet Generatorium, Roil
Cartographer, The Motherlode, Swiftfoot Boots (Multiverse Reforged), Homing Sliver,
Boros Charm, Palani's Hatcher; lost Teferi's Protection (Blame Game) and Sram, Senior
Edificer (Virtue and Valor). Gained cuts: Dragonlord Dromoka, Fact or Fiction (Fae
Dominion), Stridehangar Automaton, Kaya, Geist Hunter, Curse of the Swine, Deep
Analysis, Finale of Revelation, Tezzeret's Gambit, Blade, Bonesplitter, Cleaving and
Megantic Sliver, Icon of Ancestry, Squirrel Sovereign, Skull Prophet, Donna Noble,
The Girl in the Fireplace, Rhythm of the Wild, Fertile Ground, Syr Armont, Utopia
Sprawl (Virtue and Valor); lost Wakestone Gargoyle, Viscera Seer, Fact or Fiction
and Shark Typhoon (Multiverse Reforged), Constricting Sliver and Grasp of Fate.

- **Granters (G1, G4).** ADR-0040 §4's "play-rate never condemns a Granter" had grown
  into "a Granter is never an upgrade slot", which left Sliver Swarm's lane, every
  member a Granter, with no cut pool (fifteen swaps). By grade the guides do read
  them: of the solid Granters past `UPGRADE_RANK` they cut 0.30 (14 of 47 in a lane,
  6 of 17 off it), of the premium ones 0.12, of the decks' cards 0.24. A premium
  grant stays shielded; a solid one is a slot, play-rate ordering it as a tie in
  grade (`metrics._grant_leaves_slot`; ADR-0040's 2026-10-26 amendment). Its slot may go to
  a Granter whose grant grades higher however few decks play it
  (`swaps._grants_better`: Megantic Sliver for Pulmonic Sliver). Sliver Swarm cuts
  Blade, Bonesplitter, Cleaving and Megantic Sliver and Icon of Ancestry and adds
  Homing Sliver; Timey Wimey's Donna Noble and The Girl in the Fireplace, Squirreled
  Away's Squirrel Sovereign and Virtue and Valor's Syr Armont are guide cuts too.
- **A main's feeders (G2).** The popular tier spared every card a main serves; only
  a main's carers have a read that shields them (the guides cut 5 of 17 past
  `UPGRADE_RANK`). A popular feeder of a main is now the last slot of all: Quick
  Draw's Deep Analysis, Finale of Revelation and Tezzeret's Gambit, Virtue and
  Valor's Fertile Ground and Utopia Sprawl. The 23 popular guide cuts left are all
  premium (rank 200 or better), where the guides cut 0.10 (22 of 210): premium stays.
- **A jobless slot for a Spine fill (S1).** A Spine fill, closer or game-ending piece
  with its own pool dry took a lane slot, never an off-lane upgrade slot. One doing
  no job is a theme upgrade's slot anyway and a guide cut more often (0.39 against
  the lane's 0.28): Multiverse Reforged's protection fill now cuts one and adds
  Swiftfoot Boots. One doing a job stays the upgrade issue's.
- **A full job moves onto the theme (U9, U10).** An upgrade keeps its cut's job, and
  the job adds matched badly (interaction 5 of 84, card draw 3 of 80, ramp 2 of 57,
  wipes 3 of 49 at G2) beside the theme upgrades (47 of 271). Where the deck already
  holds the most of the job it wants — a template row at its max, protection at the
  Shape's target — the template says another such card adds nothing, so the slot
  takes the theme's add, if it costs no more than the job's (`propose_swaps`).
  Living Energy's off-theme draw becomes Izzet Generatorium, Roil Cartographer,
  Blaster Hulk and The Motherlode; Enduring Enchantments' ramp Wild Growth and
  Utopia Sprawl; Blame Game's protection Baeloth Barrityl, Firemane Commando and
  Life of the Party. Every looser row read (above the floor) or cost bar (the even
  share, none) spent budget-bound decks' cuts (Graveyard Overdrive, Planeswalker
  Party); a cut on no main only moved nothing at the max.
- **The size referent (R, backlog (j)).** `crosswalk.quantity_referent` names the
  object a size quantity reads off from phase's scope (the card, a target of an
  earlier effect, the creature an earlier effect sacrificed, a cost's, the
  triggering object, each source of a batch), resolving the earlier effect.
  `board_wipe._picked_by_caster` reads it in place of "does any effect target your
  creature", and `crosswalk.deals_its_own_power` replaces `creature_ping`'s "deals
  damage equal to its power" text confirm on a typed node (the recovered text-only
  clauses keep it: no node to read). Over the 3,598 legal cards naming power,
  toughness or mana value: no wipe read moved; `creature_ping` gains Batroc the
  Leaper and Spider-Man 2099 ("his power"), Eshki, Meglonoth, River Song, Ukkima and
  Pandemonium, and loses Form of the Dinosaur — its fought creature's power dealt
  to you is a drawback, as Bind the Monster's is (neither is a ping). No swap moved.
- **Rejected.** A1, J1: letting a less-played card past the play-rate gate, by fit
  or by the job read, gained none of the guide adds it aimed at (Insidious Roots,
  Faerie Mastermind, the Faerie and Energy pages). B1: the curve's room flat. P1:
  combo protection is what `proposal-check` gates (`is_game_winning`), and the
  guide cuts it shields (Kodama of the East Tree, Rampaging Baloths, Peema
  Aether-Seer) sit in tunes that hit the cap anyway. G3: the lane's carers bring the
  lane slots' theme adds (26 of 29), so the popular tier ahead of them costs adds.
  F1: refilled trimmed rows and spent the budget.
- **What the run leaves.** Seventeen tunes reach thirty swaps, six end on their
  budget, two on their cut pool (Blood Rites, Sliver Swarm), so "cut pool, not
  reached" rose to 50 (from 28) and the lane doers (45) and the popular tier wait on the cap.
  The theme adds no search reaches (164) are unchanged: neither the 150-card page
  nor the four sub-only adds (backlog (r)) had a new read to try, so their measured
  verdicts stand. The outranked adds fell from 251 to 235 only through the full-job
  move, which hands a slot to the theme page rather than reordering any page: no
  read this pass separated the outranked guide adds from the picks either, and the
  two that let less-played cards through (A1, J1) lost or gained nothing.

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
# recall: the misses run, then its scoreboard ("The scoreboard" below)
uv run python ../docs/plans/precon-audit/misses.py ROOT              # writes ROOT/misses.json
uv run python ../docs/plans/precon-audit/scoreboard.py ROOT/misses.json ROOT --json board.json
uv run python ../docs/plans/precon-audit/scoreboard.py ROOT/misses.json ROOT --diff OLD-board.json --pairs
```

The scoreboard is post-processing: it reads the run's JSON and the card data
(run it under the cache the run used) and never tunes, so it takes seconds.

The tunes (and `misses.py`'s six workers) can start in parallel with no warm-up
step. An edit to a lane or a preset stales the signals index beside the bulk; the
first tune rebuilds it (about 2 min) under a lock, and the tunes started
meanwhile wait for that build and then read it, so the rebuild happens once rather
than once per worker (backlog (l), 2026-10-23). To take the wait before the
workers start instead, run `uv run build-signals-index` first. With a warm index a
precon tune takes 11–17 s (20–60 s before): its ramp, card-draw and board-wipe
pages no longer build trees for every card in the pool.

## The held-out set (2026-10-29)

Ten more Commander precons, never used to design a rule, only to check one:
Avengers Assemble (MSC), Cavalry Charge (MOC), Creative Energy (M3C), Lorehold
Spirit, Prismari Artistry, Silverquill Influence and Witherbloom Pestilence (SOC),
Peace Offering (BLC), Revenant Recon (MKC) and World Shaper (EOC). Guides were
collected and summarized the same way (2–3 per precon); they live outside the
repo, with the audit ROOT, in `~/mtg/tuner-work/heldout/` (`INDEX.md`, `guides/`,
`root/`). Budgets from `guide_sizes.py` as for the 25 (median $221).

Scored once at the code from before the 2026-10-25 work (33ca5243, 546 / 195 / 60
on the 25) and once at main (d14aea55, 713 / 271 / 88 on the 25):

| held-out, 10 precons | swaps | guide cuts matching (of 216 cuttable) | guide adds matching (of 406 in scope) |
|---|---|---|---|
| before (33ca5243) | 234 | 111 | 24 |
| main (d14aea55) | 297 | 139 (+25%) | 34 (+42%) |

The gains mostly carry over: on the 25 the same code went +39% cuts and +47%
adds. Cut precision held (matching cuts per swap 0.47 both times). The held-out
adds' biggest miss is the same as the 25's: a page held the guide card but
ranked another first (186), then theme cards no search reaches (127).

From now on a policy change ships only if, on the 25, guide-matching adds rise
and cuts fall by at most 2, and, on the held-out set, adds don't fall and cuts
fall by at most 1. Read fixes ship on correctness with both deltas recorded.

## The guide-row fix (2026-10-29)

108 guide-table rows named their cards in a form the audit couldn't read: several
cards joined by commas ("Austere Command, Agent of Treachery, Rune-Scarred Demon,
Nezahal" read as one name), or a misspelling ("Niv-Mizzet, Ghost Council"). Each
row now lists real card names separated by semicolons, every name checked against
the card pool (a name that itself holds a comma stays whole). The audit scripts
also split "Dusk // Dawn" at its second slash; the split no longer breaks a `//`.
About 25 entries stay unmatched on purpose: generic text ("fetch lands", "basic
lands") and three ambiguous names (Sting, Lonis, Kykar). More guide adds are now
priced, so 14 precons' budgets rose (Eldrazi Unbound $168 → $641, Sliver Swarm
$221 → $587). New baseline, same code (main 9e049c66 + the fix):

| set | swaps | guide cuts matching | guide adds matching |
|---|---|---|---|
| the 25 (before the fix) | 713 | 271 of 408 | 88 of 610 |
| the 25 | 721 | 330 of 505 | 109 of 793 |
| held-out 10 | 297 | 139 of 216 | 34 of 407 |

## The scoreboard (2026-10-30)

`precon-audit/scoreboard.py MISSES ROOT` reads a `misses.py` run and prints the
whole scoreboard: swaps, guide cuts and adds matched (as before), and two numbers
that are reported, not gated.

**Near-misses** are tuner adds no guide names that stand in for a guide add the
tuner missed in the same deck. Each missed guide add pairs with at most one tuner
add (a maximum matching), and a tuner add first printed after the precon's
newest guide date (its Sources section, updates included) is left out, since no
guide could name it (37 such adds on the 25, 12 on the held-out ten). A pair
holds when:

- **Job:** both cards do the same template job by the tuner's own read
  (`upgrade_job(role_of(card, deck_mana=...))`), the same subtype of it, and,
  when both carry non-generic signal idents, they share one. The subtype is the
  kind of card (instant or sorcery, creature, planeswalker, other permanent)
  plus what the job reads report: a removal answer's mode and reach (exile,
  destroy, edict, damage, bounce; creatures, noncreatures, both), a wipe's
  shape (creatures, bounce, too small to kill all, one-sided, sparing a class,
  repeating), ramp's kind (lands put onto the battlefield, extra land drops, a
  mana creature, a rock, another permanent's mana, one-shot), a draw card's
  kind (wheel, engine by what fires it, one-shot), protection's cover and
  grant.
- **Theme:** neither does a job, and the two share a strongest deck signal and
  one more non-generic ident. A card's strongest deck signals are those of its
  non-generic idents (w27's generic list, plus any ident more than 5% of the
  pool carries, like `graveyard_matters|you|`) that at least three of the
  deck's nonland cards carry, ranked by how far the deck carries them above
  their base rate in the pool.

The definition was checked by the rules. In each round, 20 pairs (10 job, 10
theme) were drawn at random and each was judged with `rulings-lookup --card`
and `rules-lookup --rule` (CR 2026-09-25): does the add do what the guide card
does in that deck?

| definition | near-misses, the 25 | pairs that hold |
|---|---|---|
| as first specified: job alone; theme = the guide card's ident the most deck cards carry (`--loose`) | 329 | 5 of 20 (job 2, theme 3) |
| plus the job subtype, card kind included; theme signals by lift, on both cards, no ident on 5%+ of the pool | 104 | 10 of 20 (job 4, theme 6) |
| final: plus a shared ident for job pairs, two for theme pairs; land fetch vs extra land drop | 71 | 13 of 20 (job 7, theme 6) |

The loose rule paired 54% of the unmatched adds, in line with w27's finding.
Its failures were mostly different effects under one job: Fellwar Stone for
Birgi (Birgi's mana comes from a cast trigger, not a mana ability, CR 605.1b,
so it pays only for spells cast), Whispersilk Cloak for Alseid of Life's Bounty
in an Aura deck (shroud, CR 702.18a, also stops the deck's own Aura spells,
which target, CR 303.4a), Swords to Plowshares for Portal to Phyrexia (exile
one, CR 406.1, against an edict of three, CR 701.21a). The seven final-rule
failures: Cultivate for Scapeshift (Scapeshift sacrifices the lands it
replaces, CR 701.21a, so it adds none), Wave Goodbye for Raise the Palisade
(the Faerie deck carries no +1/+1 counters, so Wave Goodbye returns its own
creatures; Palisade spares the chosen type), Flusterstorm for Fierce
Guardianship (a soft counter of instants and sorceries against a hard counter
of any noncreature spell, CR 701.6a), Reality Acid for Chronozoa (both vanishing,
CR 702.63a; one removal, one a body), Virulent Sliver for Dormant Sliver
(poisonous, CR 702.70a, needs combat damage, which Dormant's defender, CR
702.3b, stops), Gray Merchant for MacCready and Eldrazi Mimic for Conduit of
Ruin (a shared trigger or condition, different effects). The theme half is
the weaker one: its pairs share a deck signal, which can be a condition rather
than an effect. Read near-misses as a trend between runs, not a count of right
cards. The judged pairs are in `~/mtg/tuner-work/w28/judgments.md`.

**Consensus** is the guide cards two or more of a precon's guides name (the
rows' "Source #"): how many of the in-scope ones the tuner added and of the
cuttable ones it cut.

Baseline, same runs as the guide-row fix (`misses-r-guidefix.json`):

| set | swaps | guide cuts | guide adds | near-misses (job / theme) | consensus adds | consensus cuts |
|---|---|---|---|---|---|---|
| the 25 | 721 | 330 of 505 | 109 of 793 | 71 (34 / 37) | 39 of 137 | 122 of 169 |
| held-out 10 | 297 | 139 of 216 | 34 of 407 | 29 (13 / 16) | 6 of 52 | 37 of 53 |
| Multiverse Reforged (Jace, a gate deck) | 29 | 14 of 22 | 3 of 30 | 2 (1 / 1) | 0 of 2 | 7 of 10 |

`--loose` gives 329 (208 / 121) near-misses on the 25, 162 (101 / 61) on the
held-out ten and 18 (10 / 8) on Jace. The tuner matches consensus adds at 28%
on the 25 against 14% for all in-scope adds, and consensus cuts at 72% against
65%; on the held-out ten consensus adds are 12%, against 8%.

## Deck fit for the job upgrades (2026-10-30, measured and rejected)

On the 25 the tuner adds Path to Exile, Feed the Swarm, Beast Within or Chaos Warp
to 8-13 decks each, where the guides add each to 0-2, and the w27 read found that
the outranked guide job adds share a non-generic signal with the commander far
more often than the tuner's picks. Two levers, each alone against the baseline,
then together. The bar was guide adds up and cuts down by two at most on the 25,
held-out adds flat and cuts down by one at most, and Jace with at least 3 adds.

- **3a, the cut side.** A job upgrade never cuts a card serving the main theme or
  the commander: a main's member or carer, a doer of the commander's lanes, or a
  card sharing a signal with the commander that isn't generic
  (`metrics.generic_ident`: the Spine keys, `creatures_matter`, the page-only
  idents, own ETB, own activated ability, board protection, bare artifact or
  enchantment). Of the five trades that prompted it, focus's sets make only Vona,
  Butcher of Magan (a Vampire under Clavileño, `type_matters|you|Vampire`) and
  Chittering Witch (a member of Mardu Surge's Combat main) theme cards. Stalking
  Leonin, Siege-Gang Lieutenant and Will of the Abzan share only generic idents
  with their commanders.
- **3b, the add side.** Among a job's candidates (the upgrade's match set, a Spine
  fill's page), a card sharing a non-generic ident with the commander or counted
  by a main avenue's serve ranks first, with play-rate or the job's blend
  ordering each group. Path still comes in when nothing fits. This differs from
  backlog (j)'s rejected theme tie, which let fit decide only between cards
  within 0.1 on the job read and read fit as serving a viable avenue. Here fit
  goes first over the whole match set.

| variant | the 25: swaps / cuts / adds | near-misses | consensus adds | held-out: swaps / cuts / adds | Jace |
|---|---|---|---|---|---|
| baseline | 721 / 330 / 109 | 71 | 39 | 297 / 139 / 34 | 29 / 14 / 3 |
| 3a | 611 / 281 / 97 | 61 | 35 | 239 / 112 / 25 | 16 / 10 / 1 |
| 3a, commander-shared ident only | 672 / 314 / 103 | | | | |
| 3a, main carers and lane doers only | 684 / 317 / 101 | | | | |
| 3a, main members only | 634 / 292 / 98 | | | | |
| 3b, every job | 710 / 324 / 91 | 72 | 32 | 297 / 140 / 34 | 19 / 11 / 0 |
| 3b, removal only | 717 / 326 / 104 | 73 | 40 | | 29 / 14 / 3 |
| 3b, wipes only | 727 / 330 / 108 | 66 | 39 | | 30 / 14 / 3 |
| 3b, card draw only | 711 / 327 / 107 | 71 | 38 | | 17 / 11 / 1 |
| 3b, ramp only | 722 / 330 / 104 | 75 | 38 | | 29 / 14 / 3 |
| 3b, protection only | 722 / 330 / 107 | 69 | 38 | | 30 / 14 / 2 |
| 3b, commander ident only, no ident on 5%+ of the pool | 696 / 320 / 102 | | | | |
| 3b, fit first only within tenfold of the top card's play-rate | 714 / 327 / 102 | | | | |
| 3a + 3b | 625 / 282 / 93 | 65 | 34 | 243 / 114 / 29 | 20 / 10 / 0 |

Nothing shipped, for these reasons:

- **The guides cut theme cards that do a job.** Of the 146 job-upgrade cuts that 3a
  protects, 57 are guide cuts (0.39, against 0.24 across the decks' cards), and 12
  of their adds are guide adds: Sorin, Lord of Innistrad for Anguished Unmaking,
  Confirm Suspicions for Counterspell, Whirlwind of Thought for Nezahal. With
  those slots closed, the tune runs out of cuts: 110 fewer swaps, 49 fewer guide
  cuts.
- **The fit read is too loose, and the guides add the staples.** By job, 3b loses
  every one: removal by 5, ramp by 5, card draw and protection by 2 each, wipes
  by 1. The adds it loses are the staples the guides do add: Swords to Plowshares
  and Path to Exile in Blame Game, Counterspell in two decks, Swiftfoot Boots in
  two, Heroic Intervention, Cyclonic Rift, Supreme Verdict, Fellwar Stone, Nature's
  Lore. Few of its gains are guide adds: Living Death, Crop Rotation, Faerie
  Mastermind, Sram. The guides' deck-fit removal (Abzan Armor's Wall of Souls,
  rank 16278, against cuts near 2500; Soul Shatter; Grasp of Fate) is less played
  than the cuts it would replace, so the upgrade gate holds it out under any
  order.

The /rules-lawyer spot-check covered ten cases: eight of 3b's new picks
(`rulings-lookup --card`, `rules-lookup --rule`, CR 2026-09-25) and the two
motivating cuts 3a protects.

- **One add held up.** Accursed Marauder in Blood Rites is an edict (CR 701.21a)
  in an Aristocrats deck.
- **Two did the job only partly.** Sword of Fire and Ice in Blame Game deals 2
  damage on a combat hit. Braids, Arisen Nightmare in Blood Rites lets each
  opponent choose to sacrifice or take 2 and give you a card, so it removes
  nothing reliably.
- **Five failed.** Myr Battlesphere deals its damage only to the player or
  planeswalker it attacks (its own text), so it is no removal. Alibou's X counts
  tapped artifacts, which Blame Game hardly has. Kozilek's Command needs {C}{C}
  (CR 107.4c) in a Boros deck, and its fit is Nelly Borca's symmetric draw. Bow
  of Nylea hits only a flyer. Noxious Gearhulk's fit to Felothar is its
  `toughness_combat` ident, but its life gain uses the destroyed creature's
  toughness (its 2016-09-20 ruling), so it is no toughness payoff.
- **Both protected cuts serve the deck.** Vona is a Vampire that Clavileño's
  attack trigger can target, and her vigilance (CR 702.20b) keeps her {T}
  activation open. Chittering Witch's Rats, and Zurgo's mobilized Warriors when
  she sacrifices them, are creature tokens leaving the battlefield (CR
  701.21a), which is what Zurgo Stormrender draws or drains on.

## Card reads leading the theme adds (2026-10-30, measured and rejected)

Theme adds are ordered by play-rate today: of the candidates whose synergy reaches a
fifth of the page's best (`_FIT_FLOOR`), the most played comes first, over a
150-card page (`swaps._PAGE`). The guides' theme adds include many cards that few
decks play. The plan was to let card reads lead, with play-rate breaking ties, and
to search past the page. Two orders were built:

- **Order A** puts fit to the commander first (the card shares a non-generic
  signal ident with it; `metrics.generic_ident` is the scoreboard's `GENERIC` in
  the tuner's terms). Then `rank_candidates`' synergy score, then play-rate.
- **Order B** also puts commander fit first. Then depth (how many of the deck's
  cards emit one of the candidate's non-generic idents, `DeckSignals.emitters`),
  then play-rate.

Both were run over the 150-card page and over the serve's whole match set. Then
came tiered and blended forms. The bar was guide adds up with cuts down by two at
most on the 25, held-out adds flat with cuts down by one at most, and Jace
(Multiverse Reforged) at 3 adds or more with cuts down by one at most from 14.
The phase-rs v0.118.0 bump had not landed, so these runs are against the v0.104.0
baselines. Wall time is for a whole run, six tunes at a time.

| variant | the 25: swaps / cuts / adds | near-misses | consensus adds | held-out: swaps / cuts / adds | Jace | time (25) |
|---|---|---|---|---|---|---|
| baseline | 715 / 329 / 114 | 70 | 39 | 297 / 139 / 35 | 29 / 14 / 3 | 22 s |
| A, whole match set | 723 / 331 / 82 | 94 | 29 | 297 / 140 / 30 | 30 / 14 / 3 | 50 s |
| A, 150-card page | 724 / 333 / 81 | | | | | 22 s |
| A, synergy rounded to whole points | 729 / 335 / 87 | | | | | 49 s |
| A tiered: fit, then the fit floor, then play-rate | 725 / 329 / 109 | 87 | 38 | 297 / 140 / 38 | 30 / 14 / 2 | 22 s |
| B, whole match set | 740 / 335 / 80 | 97 | 26 | 297 / 139 / 30 | 30 / 14 / 2 | 17 s |
| B, 150-card page | 739 / 335 / 82 | | | | | 17 s |
| B, log2 depth | 732 / 334 / 103 | | | | | 17 s |
| B tiered: fit, then 15+ deck sharers, then play-rate | 735 / 335 / 110 | 85 | 40 | 295 / 139 / 38 | 30 / 14 / 2 | 18 s |
| blend: log10 rank − 0.25·fit | 725 / 332 / 116 | 66 | 38 | 295 / 139 / 38 | 30 / 14 / 1 | 19 s |
| blend: log10 rank − 0.5·fit − 0.2·log2(depth+1) | 714 / 329 / 109 | | | | | 19 s |
| blend, logistic weights (fit 0.45, depth 0.12, synergy share 0.47) | 723 / 334 / 114 | 84 | 37 | 297 / 139 / 37 | 30 / 14 / 2 | 47 s |
| control: play-rate alone, no fit floor | 720 / 331 / 118 | 61 | 40 | 290 / 139 / 36 | 29 / 14 / 3 | 21 s |

Other blends scored between these: fit 0.1-0.5 with depth 0-0.2 gave 111-116
adds, and a 1000-card page gave the same as the whole set. Nothing shipped, for
these reasons:

- **The strict orders reach unpopular guide adds but lose more popular ones.**
  Order A gained 22 guide adds on the 25, including Gix, Krydle, Djeru, Teferi,
  Temporal Pilgrim, Kasmina, Bitterblossom and Chronozoa. Order B gained 23,
  including Conduit of Ruin, Senator Peacock, Delay and Hunting Velociraptor.
  Each lost about 55 guide adds. Their near-miss counts rise to 94-97 only
  because the theme near-miss rule reads the same shared idents these orders
  sort by.
- **Play-rate separates the guide adds better than any read here.** Each deck's
  theme match sets were dumped with every read (`w33/probe/`). Across them the
  guide-add rate is 5.4% at rank 1000 or better and 0.07% past 15,000. Within a
  rank band, commander fit doubles or triples the rate, and 31+ deck cards
  sharing an ident multiplies it by 2-5. A logistic fit prices fit at 0.45
  decades of play-rate, a depth doubling at 0.12 and the page's best synergy at
  0.47. Ordered by fit at 0.5 and depth at 0.15, close to those weights, the
  whole match sets hold 82 guide adds in their top ten, against 71 today. The tune doesn't keep that gain, because the
  upgrade gate, the even share and the full-job move change what each pick
  costs, and Jace loses Archfiend of Depravity and Nezahal under every read.
- **The fit floor costs four adds.** With no fit floor and play-rate alone, the
  tune scored 118 / 331 on the 25, 36 adds on the held-out ten and 3 on Jace.
  That passes the bar, but it reads less of the card than today, which runs
  against this plan. It is left for a separate decision. (Re-tested on the
  phase v0.118.0 pin and shipped: "Dropping the theme page's fit floor".)

The /rules-lawyer spot-check took ten new theme adds that match no guide card:
five from Order B and five from Order A (`rulings-lookup --card`, `rules-lookup
--rule`, CR 2026-09-25). Seven held up, one only partly, two failed.

- **Seven held up.**
  - Zopandrel under Felothar doubles toughness (CR 701.10b), and Felothar's
    creatures assign combat damage equal to toughness.
  - Taunting Kobold's goad (CR 701.15b) sends a creature at another opponent,
    which feeds Nelly Borca's draw.
  - Hotshot Investigators returning your own creature investigates (CR
    701.16a), feeding Morska's second draw.
  - Sleep-Cursed Faerie is a Faerie for Tegwyll's anthem and death draw, though
    it enters with stun counters (CR 122.1d).
  - Wharf Infiltrator's skulk (CR 702.118b) helps it deal combat damage, which
    is Gonti's trigger.
  - Longshot's cost reduction (CR 601.2f) and its 2 damage per noncreature
    spell help Stella Lee reach her second spell.
  - Gleaming Geardrake's Clue is another differently named artifact token for
    Gimbal and grows the Geardrake when sacrificed.
- **One held up only partly.** Giggling Skitterspike's damage is life loss (CR
  120.3a), but Valgavoth only counts an opponent's first loss on that opponent's
  own turn. On that turn the Skitterspike deals damage only when it blocks or is
  targeted.
- **Two failed.**
  - Cauldron Familiar can't return in Death Toll, which makes no Food (a
    sacrifice needs a permanent you control, CR 701.21a).
  - Alibou in Mardu Surge counts tapped artifacts and triggers off artifact
    creatures. Zurgo's Warriors are neither (by its ruling, X can be 0).

## The phase v0.118.0 pin bump (2026-10-30)

A read change: it ships on correctness, the deltas recorded. The bump learns the
renamed shapes (the triage guide's v0.118.0 entry) and retires 18 ledger rows and
the canaries phase's parse made unnecessary. Measured against the signal-gap
baseline (`misses-r-gaps.json`):

| | swaps / cuts / adds | near-misses | consensus adds / cuts |
|---|---|---|---|
| the 25, before | 715 / 329 / 114 | 70 | 39 / 121 |
| the 25, v0.118.0 | 717 / 332 / 114 | 70 | 39 / 121 |
| held-out, before | 297 / 139 / 35 | 29 | 6 / 37 |
| held-out, v0.118.0 | 297 / 139 / 35 | 29 | 6 / 37 |
| Jace (Multiverse Reforged) | 29 / 14 / 3, unchanged | 2 | 0 / 7 |

Planeswalker Party cuts one more guide card; Sliver Swarm makes two more swaps,
both guide cuts, and its near-miss for Chromatic Lantern is Patchwork Banner
where it was Thought Vessel. No other deck moved, and the held-out ten are swap
for swap the same. The new baseline is `w32/misses-25.json` /
`w32/misses-ho.json` (`~/mtg/tuner-work/w32/`).

## The other side of a maker lane, and the commander's own mechanics (2026-10-30)

Backlog (r) and (t) closed the levers that reorder a theme page. These two add
reach instead: a page no search held. The w27 analysis
(`~/mtg/tuner-work/w27/nosearch_buckets.tsv`) found guide adds that tie to the
deck only through a maker / payoff pair (Doubling Season and Parallel Lives
beside Tinker Time's token makers, Panharmonicon beside ETB makers, The Ozolith
beside +1/+1 counter makers), and others that fit a mechanic only the commander
has (Impact Tremors in Mardu Surge, Entomb and Buried Alive in Sliver Swarm). The
repo already pairs the two sides twice: a spec's sub-avenues (`SubAvenue`, such
as "Token doublers" on every token lane) and focus's carers (`metrics._cares_keys`:
a `<x>_makers` lane is cared about by `<x>_matters`, and every token doer by
`tokens_matter` and `token_doubling`). Each lever adds a theme avenue beside the
mains (`Sourcing.theme_avenues`) that takes one add (`_cap`), asked by its depth
as the mains are. The bar is the one in "Card reads leading the theme adds". The
phase-rs v0.118.0 bump had not landed, so the table's runs are against the
v0.104.0 baselines; the shipped lever was measured again on top of the bump
(below the table). Patches and runs are in `~/mtg/tuner-work/w34/`.

| variant | the 25: swaps / cuts / adds | near-misses | consensus adds | held-out | Jace | |
|---|---|---|---|---|---|---|
| baseline | 715 / 329 / 114 | 70 | 39 | 297 / 139 / 35 (29, 6) | 29 / 14 / 3 | |
| **4b** every multiplier sub-avenue (token, counter, ETB-trigger doublers, trigger copiers, damage and mana amplifiers), 5+ deck makers | 715 / 327 / 105 | 71 | 32 | | 21 / 11 / 1 | rejected |
| token doublers, 5+ deck makers | 710 / 327 / 109 | 72 | 37 | | 21 / 11 / 1 | rejected |
| token doublers, the commander's or 12+ deck makers | 712 / 326 / 114 | 73 | 40 | | 21 / 11 / 1 | rejected |
| token doublers, a maker lane the commander holds | 720 / 329 / 115 | 71 | 40 | | 29 / 14 / 3 | |
| every multiplier, a lane the commander holds | 720 / 329 / 115 | 71 | 39 | | 29 / 14 / 3 | |
| **token doublers, the commander's maker lane or its Clue / Treasure / Food / Blood maker** | **720 / 329 / 116** | **71** | **40** | **297 / 139 / 36 (29, 6)** | **29 / 14 / 3** | **shipped** |
| … and counter doublers | 720 / 329 / 117 | 71 | 40 | 296 / 140 / 31 (29, 6) | 29 / 14 / 3 | rejected |
| … and every multiplier | 720 / 329 / 116 | 71 | 39 | 296 / 140 / 31 (29, 6) | 29 / 14 / 3 | rejected |
| … two adds off the page | 720 / 329 / 115 | 71 | 38 | | 29 / 14 / 3 | rejected |
| every sub-avenue all of whose idents are a held doer's payoff keys | 715 / 329 / 114 | 71 | 39 | 297 / 139 / 33 (26, 6) | 29 / 14 / 3 | rejected |
| **4c** the commander's every non-generic ident whose lane isn't viable, its exact-ident page | 723 / 328 / 112 | 69 | 38 | | 22 / 11 / 1 | rejected |
| … only an ident 3 or fewer deck cards emit | 727 / 331 / 112 | 70 | 37 | | 29 / 14 / 3 | rejected |
| … and no emerging lane | 727 / 331 / 111 | 70 | 37 | | 29 / 14 / 3 | rejected |
| … one per deck, the deepest | 722 / 330 / 116 | 70 | 39 | 297 / 139 / 34 (29, 6) | 29 / 14 / 3 | rejected |

Held-out near-misses and consensus adds are in brackets.

**Measured again on the phase v0.118.0 pin** (`~/mtg/tuner-work/w36/`), against
its baseline (717 / 332 / 114, near-misses 70, consensus adds 39; held-out 297 /
139 / 35 (29, 6); Jace 29 / 14 / 3), the shipped lever scores **722 / 332 /
115**, near-misses 71, consensus adds 40; held-out **297 / 139 / 36 (29, 6)**;
Jace **29 / 14 / 3**, unchanged. It clears the bar. Deep Clue Sea and Squirreled
Away take Primal Vigor, Lorehold Spirit (held-out) Anointed Procession, and
Tinker Time's Liquimetal Torque becomes Big Score, as before the bump. One add
less than before the bump: in Planeswalker Party, Bard, King of Dale takes the
swap Supreme Verdict had. Squirreled Away makes five more swaps, none of them a
guide card; Desert Bloom takes Primal Vigor, and
Sultai Arisen Doubling Season, neither a guide add.

- **4b shipped: the token doublers, once, under a token-making commander.**
  `Sourcing.multiplier_avenue` opens the "Token doublers" sub-avenue
  (`signal_specs._TOKEN_DOUBLER_EXTRA`, CR 614.1a) when the commander itself
  holds a lane whose spec carries it (a token maker's, a token copier's, a
  tokens payoff's) or a Clue, Treasure, Food or Blood maker, whose payoff keys
  name `token_doubling`. Its depth is the deck's makers of that kind. A doubler
  limited to a kind the commander doesn't make is filtered out
  (`crosswalk.token_doubler_kinds`): Ojer Taq triples creature tokens only, and
  a Clue is an artifact token (CR 111.10f). It reached Primal Vigor in Deep Clue
  Sea and Squirreled Away and Anointed Procession in Lorehold Spirit (held-out).
  Tinker Time's tune took Primal Vigor, not the guides' Doubling Season or
  Parallel Lives: on its $100 budget both ($28-30) are past the even share, so
  the cheaper Primal Vigor ($6) is the add. Its Liquimetal Torque became Big Score, both guide adds.
- **Density alone pairs the wrong decks.** Five or more deck makers opened the
  page in Jace's polymorph deck (its Spirit fodder), which took Kaya, Geist
  Hunter and lost Archfiend of Depravity and Nezahal, and in Death Toll, which
  lost Ripples of Undeath and Six. Under the commander, the guides add a token
  doubler in 8 of the 12 decks whose page fires, and in 4 of 16 by density alone.
- **The other multipliers cost held-out adds.** Counter doublers reached Deep
  Clue Sea's Hardened Scales on the 25, but in World Shaper (held-out) Hardened
  Scales displaced three guide adds through the budget. The ETB-trigger page
  served Traveling Chocobo, which doubles only the triggers a land or a Bird
  entering causes, to three decks holding one Bird between them (Gilded Goose).
- **4c differs from (r)'s rejected rule in page and purse, and still fails.**
  (r) gave each commander-paid lane below the viable floor one swap of its own,
  off the lane's serve page and cut from the upgrade pool. Here the lane shares
  the theme adds and its page is the cards emitting the commander's exact ident.
  The pages reach the targets: Faithless Looting and Frantic Search in Sliver
  Swarm, Professional Face-Breaker, Sylvan Safekeeper, Gix, Brudiclad, Hardened
  Scales and Stalwart Shield-Bearers. But a commander holds five to eight such
  lanes (Partner, Top-deck selection, Dig-until), and each takes an add the mains
  would have made. Held to one per deck, it passed on the 25 (116 / 330) but lost
  Cavalry Charge's Black Market Connections to a Discard outlets page's Frantic
  Search on the held-out ten.

The /rules-lawyer spot-check took the ten new adds of the shipped lever that
match no guide card (all on the 25; the held-out ten gained only a guide card),
using `rulings-lookup --card` and `rules-lookup --rule` (CR 2026-09-25). Nine
held up and one only partly.

- **The six token doublers all double what their commander makes** (CR
  614.1a; each doubler's ruling: the extra tokens copy what the effect
  specifies).
  - Primal Vigor doubles Yuma's Plant Warriors (Desert Bloom) and Gimbal's
    Gremlins, with their +1/+1 counters (Tinker Time). By its ruling it doubles
    every player's tokens too.
  - Kaya, Geist Hunter's -2 doubles Anikthea's token copy (Enduring
    Enchantments) the turn it is used.
  - Exalted Sunborn doubles Zurgo's mobilize Warriors (CR 702.181a), which
    enter tapped and attacking (Mardu Surge).
  - Bard, King of Dale doubles Commodore Guff's +1 Wizard (Planeswalker Party).
  - Doubling Season doubles Teval's Zombie Druids (Sultai Arisen).
- **Three of the four cascade adds held up.** Bastion Protector makes Zurgo
  indestructible (its ruling: a commander creature you control). Osteomancer
  Adept forages Squirreled Away's Food (Food is an artifact type, its ruling).
  Rise of the Dark Realms is a mass reanimation that also fires Teval's
  leave-the-graveyard trigger.
- **One held up only partly.** Shiny Impetus makes its controller a Treasure
  (its ruling), but its goad is for an opponent's creature, which Mardu Surge
  doesn't build toward.

Found on the way, not fixed: phase reads Parallel Lives' doubling as every
token, but it doubles creature tokens only ("one or more creature tokens"), so
`token_doubler_kinds` can't keep it from a Clue commander. Xorn's extra Treasure
carries no count change, so it is no doubler to the read.

## Dropping the theme page's fit floor (2026-10-30, shipped)

"Card reads leading the theme adds" found that the theme page's 0.2 synergy fit
floor, with play-rate picking among the cards above it, cost adds against
play-rate alone, and left the call for a separate decision. The decision was
to test it again after the phase v0.118.0 bump and ship it only if it still
clears all three bars. A theme page where play-rate means something (the
Commander family) is now ordered by play-rate, then price
(`_tuner/swaps.py`, `_ranked_pool`); the page's search already holds only the
theme's cards. Without play-rate, synergy still orders the page. Measured on
top of the token doublers (`~/mtg/tuner-work/w36/`):

| | swaps / cuts / adds | near-misses | consensus adds / cuts |
|---|---|---|---|
| the 25, the floor | 722 / 332 / 115 | 71 | 40 / 121 |
| the 25, play-rate alone | 718 / 333 / 118 | 61 | 39 / 121 |
| held-out, the floor | 297 / 139 / 36 | 29 | 6 / 37 |
| held-out, play-rate alone | 290 / 139 / 37 | 30 | 6 / 37 |
| Jace (Multiverse Reforged) | 29 / 14 / 3, unchanged | 2 | 0 / 7 |

It clears the bar: adds rise by three on the 25 and one on the held-out ten,
cuts rise by one on the 25, and Jace is unchanged.

- **The 25.** Animated Army takes Chimil, the Inner Sun; Death Toll Buried
  Alive and cuts Burnished Hart; Living Energy Conversion Apparatus, cutting
  Reckless Fireweaver; Virtue and Valor Sram, Senior Edificer; Graveyard
  Overdrive Buried Alive for Six; Timey-Wimey Delay for Jhoira's Timebug; Tinker
  Time Liquimetal Torque for Big Score. Desert Bloom loses Life from the Loam,
  and Abzan Armor makes two fewer swaps and loses the Rhox Faithmender cut.
- **The held-out ten.** Lorehold Spirit takes Crucible of Worlds and Underworld
  Breach, Avengers Assemble SP//dr, Piloted by Peni, and it cuts Tome of Legends
  where it cut Captain America, Living Legend. Witherbloom Pestilence loses Sanguine
  Bond and Vito, Thorn of the Dusk Rose. Prismari Artistry and Revenant Recon
  make seven fewer swaps between them.
- **Near-misses fall by ten on the 25.** Some were stand-ins for a guide card
  the order now takes (Virtue and Valor's Puresteel Paladin for Sram, Living
  Energy's Fellwar Stone for Conversion Apparatus). Near-misses are reported,
  not a gate.

## A polymorph's flip targets and the mana-value band (2026-10-30, rejected)

Under a commander that `wants_fodder`, a creature or planeswalker card its
`cheat_into_play` reveals for skipped the upgrade's mana-value band
(`over_band`): Jace, Multiverse Architect's -3 reveals "until you reveal a
creature or planeswalker card" and puts it onto the battlefield, so the card's
mana cost is never paid (CR 601.2f-h: a spell's total cost is determined and
paid as it is cast). The patch is `~/mtg/tuner-work/w26/flip-band.patch`.
Jace's deck is the only polymorph deck in either set, so only it moves. The
bar needs Jace at 4 adds or more for the 25's adds to rise.

Measured on top of the token doublers and the dropped fit floor
(`~/mtg/tuner-work/w36/`): Jace 30 / 14 / 2 against 29 / 14 / 3, the 25 719 /
333 / 117 against 718 / 333 / 118. It fails, as it did before the bump. The
band's room went to the big creatures play-rate ranks first (Grave Titan,
Artisan of Kozilek, Scourge of the Throne, Gisela, Blade of Goldnight,
Combustible Gearhulk), and Nezahal, Primal Tide, a guide add, was outranked
on its page. Archfiend of Depravity and Swiftfoot Boots stayed.

