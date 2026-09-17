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
had: signal keys `ramp`, `mana_amplifier`, `extra_land_drop`, `firebending_makers`, plus
a concept arm for the two facts no key carries alone —

- an **extra land play** (*Exploration*, *Azusa*; CR 305.2). The lanes route it to
  `landfall`, a key that also covers pure payoffs, so the arm reads the same static mode
  through `lanes.additional_land_play`, now the landfall lane's own read too;
- a **Treasure maker you keep**: `treasure_makers|you` minus a giveaway veto (every
  Treasure-creating clause has a third-party subject — *An Offer You Can't Refuse*).
  The `make_token` concept carries no recipient, so the veto reads the clause subject.

`roles.is_ramp` is that preset, never for a land (the mana base, CR 305). The tuner
sources ramp by the same preset, so "counts as ramp" and "suggested as ramp" cannot
drift; a test asserts the subset relation over the whole snapshot.

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

`deck-stats` and `mana-audit` now join the surfaces that read the signal path, so like
`slot-budgets` they fetch phase's card-data on first use and degrade to text offline.

**Considered and rejected.** Widening the `extra_land_drop` lane to cover extra land
plays (the lane's own docstring excludes that mechanic, and it would change a served
key's population for Find). Fixing the number-word regex and leaving two paths (it is
the drift, not the one bug, that ADR-0027 rejected). Deleting the text read outright
(cube pools and synthetic fixtures have no coverage).
