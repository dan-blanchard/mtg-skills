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
2. Tune: `deck-tune <deck.json> --max-swaps 10 --budget 100` (the guides' usual
   budget tier), paper medium, no collection.
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

## What is left

`docs/plans/backlog.md`, "What the 25-precon audit still finds wrong": no
quality read inside a deep lane (the 142), the lane misreads the guides expose
(Gonti, Zurgo, Bello, Yuma, Role tokens, token doublers, pillowfort,
"Opponents' graveyards"), symmetric damage read as interaction, a closer search
with no avenue, template bands against a commander whose lane is the band.

## Rerunning

```
# lists
curl -sL https://mtgjson.com/api/v5/decks/SliverSwarm_CMM.json -o SliverSwarm_CMM.json
python3 -I docs/plans/precon-audit/to_decktxt.py SliverSwarm_CMM.json deck.txt
cd mtg-utils && uv run parse-deck deck.txt --format commander --output deck.json
uv run deck-tune deck.json --max-swaps 10 --budget 100 --output tune.json
# compare: decks/<Name>/tune.json beside precon-audit/<Name>.md
python3 -I docs/plans/precon-audit/compare.py
```
