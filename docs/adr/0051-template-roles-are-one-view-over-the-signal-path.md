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
