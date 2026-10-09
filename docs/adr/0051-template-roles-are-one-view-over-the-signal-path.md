# Template roles are one view over the signal path

"Is this card ramp?" had four answers. `card_classify.is_ramp` (an oracle-text regex)
fed the ramp budget row, `deck-stats`, `mana-audit`, the ranking floor and the tuner's
cut side. The structural `ramp` lane fed Find and the presets. The tuner's candidate
search hand-copied `is_ramp`'s regex (its comment: "mirroring is_ramp's own patterns"),
because no `ramp` preset existed. A tree-synthesis arm carried a fourth, sentence-level
copy of the fetch branch. "Mirrors `card_classify.is_ramp`" appeared in five comments,
and every convention change (lf_ramp, 2026-07-13) was a three-site edit.

They disagreed. Over the 33,993 commander-legal nonland cards (2026-09-17): 1,628 agree;
142 are regex-only; 448 are structural-only. The regex could not read a number word
after "add", so *Gilded Lotus*, *Black Lotus* and *Zaxara* were not ramp to the budgets
row and the tuner could never suggest them; its fetch pattern missed "up to two Forest
cards" (*Skyshroud Claim*, *Hunting Wilds*); it counted a Treasure maker only when the
printing happened to carry reminder text. Archived ADR-0027 had already rejected regex
as a permanent second path and left `card_classify` as its unfinished Milestone C.

**Decision.** `mtg_utils/_analysis/roles.py` owns the template-role facts: `role_of`
(`lands` / `ramp` / `card_draw` / `interaction` / `board_wipe`), `is_ramp`, and the
advisory `protects`, moved out of `budgets.py`, which keeps the bands. Every role is a
view over the signal path. Ramp gains the `ramp` preset the other three roles already
had. It is concept-only, because the role is "NONLAND and …" and a preset's arms only
OR: a nonland card carrying

- a ramp signal key — `ramp`, `mana_amplifier`, `extra_land_drop`, `firebending_makers`;
- a **Treasure maker whose token you keep** (`lanes.treasure_maker_you_keep`). The
  `treasure_makers` key is scoped "you" for a giveaway too, but the `Token` node's own
  `owner` says who creates it: `ParentTargetController` for *An Offer You Can't Refuse*
  ("Its controller creates two Treasure tokens"), `Controller` for *Smothering Tithe*;
- an **extra land play** (*Exploration*, *Azusa*; CR 305.2). The lanes route it to
  `landfall`, a key that also covers pure payoffs, so the arm reads the same static mode
  through `lanes.additional_land_play`, now the landfall lane's own read too.

A land is never ramp — it is the mana base (CR 305), and the `ramp` key fires for every
fixing land, which would fill the tuner's small cmc-ascending search page with lands.
`roles.is_ramp` is that preset. The tuner sources ramp by the same preset, so "counts as
ramp" and "suggested as ramp" cannot drift; a test asserts the two sets are equal over
the whole snapshot. The tree-synthesis fetch sentence read stays: it is an arm of the
signal path (it feeds the `ramp` lane a concept for text-only trees), not a second
definition of the role.

The regex survives once, renamed `card_classify.ramp_by_text`, as the **no-coverage
degrade**: a card the signal path cannot see (`theme_presets.has_signal_coverage` — no
`oracle_id`, no phase parse, no card-data) still counts its rocks, so a no-sidecar
`deck-stats` or a cube goldfish keeps working. A covered card never falls back to text.

**Consequences.** Measured over the 30,598 distinct commander-legal nonland cards
(2026-09-17): 1,540 keep the role, 278 gain it, 51 lose it. The gains are the number-word
producers, the multi-land fetches, granted mana abilities, and every Treasure maker you
keep (not only the printings with reminder text). The losses are mostly DFCs whose back
face is a land (*Search for Azcanta* — the text read only said ramp because the faces'
oracle text is joined), token makers whose tokens carry firebending or a Vibranium-style
mana ability, and a handful of genuine lane recall gaps a lane fix now repairs for every
consumer at once: *Tireless Provisioner* ("a Food token or a Treasure token" fires
`food_makers` only) and *Surveyor's Scope* (its X-basics fetch reads as `tutor`).

`deck-stats`, `mana-audit` and the cube category classifier (its colorless-fixing slot)
now join the surfaces that read the signal path, so like `slot-budgets` they fetch
phase's card-data on first use and degrade to text offline. The degrade itself learned
number words ("Add three mana"), so an uncovered Gilded Lotus still counts.

**Considered and rejected.** Widening the `extra_land_drop` lane to cover extra land
plays (the lane's own docstring excludes that mechanic, and it would change a served
key's population for Find). Fixing the number-word regex and leaving two paths (it is
the drift, not the one bug, that ADR-0027 rejected). Deleting the text read outright
(cube pools and synthetic fixtures have no coverage).

**Amendment (2026-10-04): ramp is judged under the deck's commander.** The role was the
card's alone, so a rock that makes no usable mana for *this* deck still filled a ramp
slot. Arcane Signet under a colorless commander "produces no mana. It doesn't produce
{C}" (its ruling). Mox Amber and Chrome Mox take their colors from your legends and your
exiled card, all colorless in such a deck. The Mightstone and Weakstone's mana "can't be
spent to cast nonartifact spells", so it can't cast a creature commander. An Omnath,
Locus of the Void deck counted all of them, and the tuner could have suggested Arcane
Signet as ramp.

`roles.DeckMana` is the deck context: the commanders' combined color identity and
facts, plus the deck's nonland cards and their copies, from `HydratedDeck.deck_mana`.
`is_ramp` and `role_of` take it as an optional `deck_mana`. With it, a source is not
ramp when every `Mana` effect it has is dead for the deck: a deck-colored `produced`
kind (`AnyInCommandersColorIdentity`, `AnyOneColorAmongPermanents`,
`ChoiceAmongExiledColors`) under an empty identity, or a spell-type restriction the
deck can't use. A restriction is usable when it admits a commander or at least a third
of the deck's nonland cards by copies, so artifact-only mana is ramp in an artifact deck
under a creature commander. The restriction is phase's string ("Instant, Sorcery,
Demon, and Spirit"), split on its list words and read word by word against each card's
types, subtypes, supertypes and colors (outlaw per CR 700.12); a word it doesn't know
admits, so a card is never condemned on vocabulary alone. One usable ability keeps a source live
(Eldrazi Temple's plain {C}), and a card phase hasn't parsed is never condemned. The
reads are two new crosswalk helpers, `produced_kind` and `mana_spell_type_restriction`.
Every surface that counts a deck's ramp passes the context: `deck-stats`, `deck-diff`,
`mana-audit` (so a dead rock no longer lowers the land band), `slot-budgets`, the hub's
budgets, candidate ranking (`deck-rank`, the hub's Find, the tuner's adds), and the tuner's
classes, band and ramp sourcing. Without a commander the deck-colored rule doesn't
apply; for a card on its own the answer is unchanged.

**Amendment (2026-10-08): protection is a view too.** `protects` was the last role on
oracle text: four regexes (grant, save, deter, redirect) beside the `counterspell`
preset and the compat IR's `redirect` category. Its docstring said protection is
"another permanent", but the grant regex fired on any "has hexproof", so some 200
cards that protect only themselves (Dragonlord Ojutai, Yahenni, Fleecemane Lion,
Paradise Druid) bucketed as protection — Spine, never cut. The `redirect` category
also tagged every "exile it instead" replacement (Lava Coil, Anger of the Gods), and
Temporal Isolation's "prevent all damage that would be dealt by enchanted creature"
counted as a save. The tuner sourced protection from a fifth definition: the
self-keyword presets (`hexproof`, `indestructible`, `protection`, `ward`).

`protects` is now the `protects-board` preset, and the tuner's protection search reads
the same preset. The reads live in `crosswalk/protection.py`. Its keys:

- `board_protection` (new, served; its own preset is `board-protection`): a
  protective keyword (hexproof, shroud, indestructible, ward, protection — CR 702.11,
  702.18, 702.12, 702.21, 702.16) given to something other than the card itself,
  permanent or player (`protective_grant_recipients`: Avacyn's "Another" filter,
  Darksteel Forge, Sterling Grove, Apostle's Blessing's `ChooseOneOf` branch, Leyline
  of Sanctity's `Hexproof` player mode, Giant's Amulet's granted static); a save for
  something other than itself (`protective_saves`: regeneration, CR 701.19a; phasing
  out, 702.26b; a prevention shield, 615.1; Angel's Grace's life floor and Cosmic
  Intervention's exile-and-return, both replacements, 614.1a); umbra armor on an Aura,
  from the keyword array or a grant (Dog Umbra, Estrid's Mask; 702.89a). A keyword
  that comes with animating a permanent (Avalanche Caller's "becomes a 4/4 Elemental
  creature with hexproof and haste") is part of the creature it makes, not a shield.
  A spell's `SelfRef` grant is phase binding "it" to the spell; the read takes it as
  the chosen object (its own decision), guarded by
  `test_spell_selfref_misbinding_canary`.
- `pillowfort` (new, served): `attack_deterrent` — attack taxes (Ghostly Prison),
  attack bans on you (Blazing Archon, the Vow cycle) and attack limits (Crawlspace,
  Silent Arbiter, Tomik's granted limit), and a player's creatures barred from
  attacking you for a turn (The Second Doctor, Orzhov Advokist), CR 508.1c / 508.1h.
- `counter_control` (CR 701.6a), and `spell_redirect` (CR 115.7), which now also
  takes Reroute's redirect of an activated ability (`reads.redirects_stack_object`)
  and the spell thieves (`reads.steals_stack_spell` — Commandeer, Aethersnatch,
  Perplexing Chimera, Invert Polarity): taking a removal spell answers it like a
  counterspell (Dan, 2026-10-08).

Dan's rulings on the boundary (2026-10-08): defensive neutralisers count, removal
doesn't. Damage prevention scoped to the damage an opponent's object would deal
shields you and your board like a fog or a pillowfort (CR 615.1 — Dovin, Hand of
Control; Kiora, the Crashing Wave; Resistance Fighter; Sokrates, Athenian Teacher's
granted shield). Phasing out or exiling an opponent's object is removal: a phase-out
aimed only at an opponent's object, or one held by "can't phase in" until the source
leaves (Oubliette, whose creature skips the CR 702.26a untap-step phase-in), is not a
save. And protection is protecting YOUR board: a permanent's shield over every
player's objects alike (Crumbling Sanctuary, Plated Pegasus) isn't, while a fog you
cast and an optional shield you aim (Battletide Alchemist) are.

Ten ledger rows (ADR-0048) restore cards whose protective clause phase parks, drops or
misparses: `protective_grant_parse_failure`, `prevention_shield_parse_failure` (with
Ajani Steadfast's emblem, read through the new `hollow_emblem_statics` accessor for
phase's `EmblemStatic` placeholders, CR 114.4), `attack_you_parse_failure`,
`granted_unattach_prevention_parse_failure` (Blinding Powder),
`spell_or_ability_redirect_parse_failure` (Emissary of Grudges),
`equipped_cant_attack_you_dropped` (Assault Suit),
`enters_and_gains_protection_dropped` (Nick Fury, Spymaster),
`sokrates_granted_prevention_misparse`, `akiri_unattach_selfref_grant` and
`dauntless_bodyguard_chosen_creature`. Maze's Mantle's "that creature" (the enchanted
creature, CR 303.4b) is phase-bound to the triggering Aura and read past with
`test_aura_etb_triggering_source_canary`. Unlike `is_ramp`, `protects` has no text
degrade: a card the signal path can't see is not protection.

**Consequences.** Over the 32,758 cards legal in at least one format (MTGJSON
2026-09-22, phase v0.94.0): 1,650 keep the role, 85 gain it, 435 lose it. The gains
are protection the regex couldn't phrase: Regeneration and Trollhide's granted
regeneration, the Sphere cycle's "prevent 2 of that damage", Pariah and Palisade
Giant's damage shields, Urza's Armor, Worship's life floor, Zombie Master, Clot Sliver,
Vines of Vastwood. The losses are mostly self-only grants and saves (Dragonlord
Ojutai, the Gideons, Phantom creatures, Fog Bank), cards only the `redirect` category
caught ("exile it instead" replacements), pacifying, symmetric or removal effects
(Temporal Isolation, Hostility, Crumbling Sanctuary, Oubliette), land and planeswalker
animators, and The Eternal Wanderer's limit on attacking itself. The tuner's
protection bucket loses self-protecting creatures, which become cut-eligible like any
other card that serves no avenue.

The candidate ranking lost its text fallback in the same change: a card with no IR
(newer than the phase pin, or synthetic) scores every clause as an enabler with no
tribal gate, the same "never guess from text" rule `extract_signals` follows.
