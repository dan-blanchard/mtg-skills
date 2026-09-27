# twohg-guide Context

The bounded context for producing **2HG Cheat Sheets**: short, printable pages that prepare
a two-player team for a Two-Headed Giant sealed prerelease of one specific set. Read-only on
cards and data; the skill builds no decks (for a real pool, run `/deck-wizard` or
`/deck-forge` on it afterwards).

## Language

### Output artifact

**2HG Cheat Sheet**:
One HTML page per set, published as a private claude.ai artifact and republished in place
when revised. A fixed spine of sections (see *Spine*), two columns on desktop, one on a
phone, card names hover to show the card.
_Avoid_: "guide" alone (ambiguous with deck-strat's Strategy Guide), "report".

**Spine**:
The always-present sections, in order: What's winning · Team pairing · The ×2 cards ·
Downgrades & gotchas · Rules that win games · Bombs · Removal · Build hour checklist ·
Sources. The template (`twohg-template`) ships it empty.

### 2HG terms

**Head**:
One of the two players on a team. "Each opponent" means both enemy heads (CR 102.3).
_Avoid_: "player" when the team/individual distinction matters.

**Team**:
The two heads sharing one 30-life total (CR 810.4) and one turn (CR 805.4).

**×2 card**:
A card whose effect applies once per opponent, so in 2HG it moves the discards, the
sacrifices or the targets twice (both enemy heads are opponents, CR 102.3), and the shared
life total twice (damage and life loss happen per player, CR 810.9): "each opponent", "for each
opponent", "creatures your opponents control", "whenever an opponent…". `twohg-scan`'s
`doubles` bucket.
_Avoid_: "doubler" (collides with token/counter doublers).

**Partner hit**:
A symmetric effect that also lands on your teammate: "each player", a sweeper that isn't
limited to opponents' permanents, "each other player". `twohg-scan`'s `hits_partner`.

**Step trigger**:
"At the beginning of each player's / each opponent's [step]". Fires once per head only if
the ability refers to "that player" or "that opponent"; otherwise once per step
(CR 805.4d). `twohg-scan`'s `step_triggers`, `fires: per_head | once`.

### Evidence

**Paper report**:
A result posted by someone who played the paper prerelease (Reddit threads Dan saves with
Cmd+S, read with `thread-extract`). The primary evidence for Sealed.

**Arena stats**:
Untapped.gg's MTGA limited card stats (`limited-stats`). Usually Premier Draft from the
Early Access event before release, so it's draft data, not Sealed.

**Win rate when drawn**:
Untapped's games-in-hand win rate: games the card was drawn or in the opening hand. Shown
as a percentage; bracketed (`[71%]`) when the sample is under the floor.

### Guide sections

**Bomb**:
A card that wins the game if it isn't answered. Every use of the word on a sheet is backed
by the Bombs section, which lists them by color with evidence.

**Pile**:
The build-hour sort of the shared pool: removal → bombs → ×2 cards → fixing. Bombs and
Removal are two-sided sections: your pile, and the other team's threats and answers.
