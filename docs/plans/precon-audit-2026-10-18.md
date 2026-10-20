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
   from the recall pass on, `--max-swaps 30 --budget 440`, the largest guide's size —
   `precon-audit/guide_sizes.py`), paper medium, no collection.
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

Past 22 swaps the extra cuts match a guide 27% of the time, about the 24% base
rate. The recipe is now **thirty swaps and $440**, so recall is never capped below
what a guide does; precision is read beside it.

| guide cuts in the decks (424) | n | | guide adds (745) | n |
|---|---|---|---|---|
| cut | 185 | | added | 47 |
| popular: off-lane, inside `UPGRADE_RANK` | 75 | | out of scope (in deck, land, banned, off-identity) | 135 |
| a doer of the commander's lane, outside the deep-lane half | 55 | | a theme card no search looked for | 238 |
| a carer of a built theme | 27 | | on a searched page, outranked | 175 |
| other | 25 | | not on any page though its job was searched | 67 |
| in a cut pool, not reached | 24 | | on a page, gated (play-rate, cost band, job) | 40 |
| land / commander | 20 | | a role card no issue asked for | 43 |
| protected (combo / closer / multiplier) | 13 | | | |

Recall is 185 of the 404 cuttable guide cuts (46%) and 47 of the 610 in-scope adds
(8%). The levers, by size: the theme adds no search reaches (238), the adds
outranked on a page (175), the cuts the popularity threshold still shields (75),
and the commander-lane cards the guides trim (55).

Of those 238, 115 serve the main theme by the tuner's own read, and 88 of them don't
match the theme's search spec at all: a theme's candidate page is still its
pattern search (Abzan Armor's "assigns combat damage equal to its toughness"), not
its serving predicate (`Serve.matches`, which admits Fecund Greenshell and Perimeter
Captain). Paging the identity's 3,000 most-played cards through the serving
predicate as well, tried 2026-10-19, put the guide adds on the page but dropped the
adds matching a guide from 30 to 26: one pick per swap, and a wider page lets a
popular card that fits loosely win it. Widening the page costs precision without
buying recall until the ranking can tell those apart.

## What is left

`docs/plans/backlog.md`, "What the polymorph tune and the 25-precon audit still
get wrong" and "Every held serve spec is converted": the phase gaps behind the
interaction role, the superfriends veto, animation and the converted serves; the
text-mirror leftovers; the phase gaps nothing can read; the lane gaps the censuses left (a destination subject on
`creature_recursion`, a spell-type subject on `cost_reduction`, the edict lane,
keyword token-copy makers, `FlipCoin.win_effect`); the ranking module's
clause-cluster attribution for ident-served hits.

## Rerunning

```
# lists
curl -sL https://mtgjson.com/api/v5/decks/SliverSwarm_CMM.json -o SliverSwarm_CMM.json
python3 -I docs/plans/precon-audit/to_decktxt.py SliverSwarm_CMM.json deck.txt
cd mtg-utils && uv run parse-deck deck.txt --format commander --output deck.json
uv run deck-tune deck.json --max-swaps 30 --budget 440 --output tune.json  # the largest guide (guide_sizes.py)
# compare: decks/<Name>/tune.json beside precon-audit/<Name>.md
python3 -I docs/plans/precon-audit/compare.py
```
