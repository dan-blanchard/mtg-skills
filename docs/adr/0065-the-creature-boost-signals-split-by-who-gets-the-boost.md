# The creature-boost signals split by who gets the boost

The boost signals had grown one at a time, each beside the last, and their lines no
longer matched what a deck wants. `effect_boost` (once `pump_makers`) held every timed
pump, including 277 legal creatures whose pump only ever lands on themselves ("Whenever
another artifact you control enters, this creature gets +2/+2" — Glaze Fiend), and its
`target` subject flagged a pump of one chosen creature, the heroic enabler. `self_pump`
held firebreathing alone. Phase's keyword-built exalted, battle cry and bushido pumps
carried no duration, so 35 exalted and 14 battle cry cards were no pump at all. The
combat buff read missed phase's `BlocksOrBecomesBlocked` trigger and took any counter
but -1/-1 as a buff. A survey of every boost signal (2026-11-25) put the cases in front
of Dan, who ruled where the lines sit. The lines come from three places, and each
item says which: **Dan's rulings** (2026-11-25); **the coordinator's decisions**
(2026-11-25, made from Dan's confirmed summary of the rulings, after review of the
first build); and **the builder's choices** where both were silent.

**Decision.** Six signals, each one question about a boost: who gets it, and how.

*Dan's rulings (2026-11-25):*

- **`effect_boost`: an effect boosts ANOTHER creature or a group.** A spell, an
  activated or a triggered ability raises a creature's power or toughness, until end of
  turn or perpetually. A card whose pump only ever lands on itself is never one. Exalted
  ("that creature gets +1/+1 until end of turn", CR 702.83a) and battle cry ("each other
  attacking creature gets +1/+0 until end of turn", 702.91a) are; bushido ("it gets
  +N/+N until end of turn", 702.45a) is a self-boost. The subject `target` is gone.
- **`self_boost` (new, "Grows itself"): a creature raises its OWN power or toughness.**
  Subject `""` for a triggered or perpetual effect on itself (the self-only pumps,
  bushido, prowess — the keyword and the printed form alike, 702.108a — the perpetual
  self-growers, and Vladimir and Godfrey, whose graveyard activation returns the card
  and grows it); `activated` for an activated ability (firebreathing: it replaced
  `self_pump`, page and all); `counters` for +1/+1 counters it puts on itself.
  `self_counter_grow` keeps its own key for the counters cluster, and its
  population is not this one: of the legal cards (`signals-8-final2.pkl`), 1,602
  hold `self_boost|counters` and 1,668 `self_counter_grow`. 93 hold
  `self_counter_grow` alone: 20 noncreatures (Afiya Grove, Agent's Toolkit), which
  have no body of their own to grow, and 73 creatures the counters cluster's wider
  read admits: a power reference (Brambleguard Captain's "where X is this
  creature's power"), ravenous's "enters with X +1/+1 counters", which no typed
  placement carries (Termagant Swarm), and another creature's counters (Master
  Biomancer). 27 hold `self_boost|counters` alone, among them devour and a
  would-die replacement that puts counters on the card (Mycoloth, Ravenous Slime,
  Me, the Immortal).
- **`boosts_others` (new, "Boosts your other creatures"): anything that makes your
  OTHER creatures bigger**, the delivery as subject: `effect` (every `effect_boost`
  card), `counters` (+1/+1 counters put on another creature or a group), `anthem` (a
  static boost of a group that reaches your creatures; Bad Moon's symmetric one counts,
  one only opponents' creatures get does not), `attached` (an Aura or Equipment that
  boosts the creature it is attached to). `target_spell` when the boost targets one
  creature that isn't an opponent's as a spell (an instant or sorcery pump or
  +1/+1-counter spell, CR 115.1a; an Aura spell, 303.4a) and `target_ability` when it
  does so as an activated or triggered ability (equip, 702.6a). A heroic payoff ("a
  spell that targets this") is offered only `target_spell`; a "becomes the target of a
  spell or ability" payoff both. The existing keys (`plus_one_makers`,
  `counter_distribute`, `anthem_static`, `team_boost_or_grant`, `voltron_makers`) stay as
  they are for their own partners.
- **`combat_trigger_boost`** keeps a creature that boosts itself in combat (it carries
  `self_boost` beside), reads phase's `BlocksOrBecomesBlocked` (Chub Toad, Brushwagg),
  and its typed counter arm counts only a counter that raises power or toughness
  (122.1a). **Dan's later ruling (2026-11-25):** a combat trigger that places a
  counter which the same card's static turns into power or toughness is a combat
  boost too (`crosswalk.feeds_own_static` over `crosswalk.counter_fed_statics`: a
  P/T-raising static whose quantity counts that kind of counter on the card, or
  among your permanents for a token's static, or whose condition needs it). Rose
  Tyler's time counters ("+1/+1 for each time counter on it"), Gavel of the
  Righteous's charge counter ("+1/+1 for each counter on this Equipment"),
  Beastmaster Ascension's quest counters (its seven-counter anthem) and Moira Brown's
  quest counter (her Book's "+1/+1 for each quest counter among permanents you
  control") count. Beorn the Fierce's trample counter (its +2/+2 is the Bear lord's,
  reached by the type change) and Sephiroth, Fallen Hero's cell counter (a one-shot
  base-P/T setting, 613.4b, not a raise) don't.
- **A raise of one number is a boost**, whatever the other does: "+2/-2" is a pump and a
  shrink (Lash of Malice). **A boost that can only land on an opponent's creature is
  never yours.** Chaos Balor keeps its combat boost. Veteran Motorist and Flailing Drake
  boost a different creature, not themselves.
- **A granted boost keyword boosts your other creatures (Dan's rulings,
  2026-11-25, after the first build).** Every keyword whose whole effect is a
  power/toughness boost counts when granted to your other creatures: prowess (CR
  702.108a), exalted (702.83a), bushido (702.45a), rampage (702.23a), melee
  (702.121a) and battle cry (702.91a: "each other attacking creature gets +1/+0",
  a boost of the team). Flanking does not: it shrinks the blocker (702.25a). It
  is `boosts_others`, filed by how it is granted: `anthem` for a standing grant
  to a group of yours ("Other creatures you control have prowess" — Bria,
  Riptide Rogue; Syr Joshua and Syr Saxon's battle cry), `attached` with its
  delivery for an Aura's or Equipment's ("Equipped
  creature has prowess" — Wizard's Staff, `target_ability`; Taught by Narset's
  Aura, `target_spell`). Prowess, bushido, rampage, melee and battle cry
  trigger on the creature that has them, so only a grant to creatures counts;
  exalted's boost lands on the creature attacking alone, so a grant to any
  permanents of yours counts ("Clues you control have exalted" — Merchant of
  Truth; Rashel, Fist of Torm's Auras). A battle cry the card gives itself
  boosts the others too, `effect` as a printed battle cry is (Reckless
  Pyrosurfer; Marshland Hordemaster's parked "perpetually gains battle cry");
  any other grant to the card itself grows itself (Fumiko the Lowblood's
  bushido). *The coordinator's decision, consistent with the target-flag
  ruling:* a boost keyword granted to ONE target creature that is not an
  opponent's carries the target flag as any targeted boost does, `effect` plus
  `target_spell` or `target_ability` by delivery (Fang of the Pack's "another
  target creature you control gains melee", Rapid Fire's rampage, Sensei
  Golden-Tail's bushido). *The coordinator's choice, consistent with how team
  pumps read:* a group grant that lasts a turn is `effect`, as a one-shot team
  pump is, not `anthem` — decided by structure, a static ability against an
  effect with a duration (Vivien's Stampede's "Each creature you control gains …
  melee until end of turn"; Rammas Echor, Ancient Shield's "creatures you
  control with defender gain exalted until end of turn").
- **The counter keywords count, under `counters` (Dan's ruling, 2026-11-27).**
  Training (CR 702.149a), dethrone (702.105a) and mentor (702.134a) put +1/+1
  counters and do nothing else. Granted to your other creatures, however the
  grant lands (a group, gear's creature, one target), the card is
  `boosts_others|you|counters` ("Other creatures you control have dethrone" —
  Marchesa, the Black Rose); a grant to one target creature adds its target flag
  as the boost keywords do. A creature that has mentor reads through the trigger
  phase builds for it (a +1/+1 counter on another attacking creature), as a
  printed exalted or battle cry does; a printed training or dethrone grows the
  creature itself. The other counter-placing keywords are not part of this
  ruling (evolve, outlast, adapt, riot and the rest; bolster, amass, support and
  explore already read as counters on another creature, by their own actions).
- **Earthbend is its own thing (Dan's ruling, 2026-11-27).** Earthbend N animates
  a land you control and puts N +1/+1 counters on it (CR 701.66a): no boost of
  another creature (`boosts_others` `counters` / `target_spell` /
  `target_ability`), and no target of yours for `own_target_spell` or the
  targeting payoffs' offers. Keyed on phase's keyword action
  (`crosswalk.earthbend_effects`: the `Animate` of a land through phase's
  `RegisterBending{kind: Earth}` marker); a clause of the same card outside the
  earthbend keeps its reading.
  (`lanes.boosts._granted_boost_keywords`,
  `_targeted_boost_keyword_deliveries`, `_own_battle_cry`.)

- **`card_boost` (new; built on the sibling branch `card-boost` and merged here): a
  perpetual power/toughness raise on cards of yours NOT on the battlefield** — "creature
  cards in your graveyard perpetually get +1/+1" (Feed the Bog), "choose a creature card
  in your hand. It perpetually gets +2/+2" (Veteran Charger). Its subject is the zone the
  card ends up in within the ability (`crosswalk.perpetual.card_boost_zones`): `hand`,
  `graveyard`, `library`, `stack` (a creature spell you cast — Rothga, Bonded Engulfer)
  or `everywhere` (every card you own — Unbreakable Remnant); a change naming several
  zones emits one signal per zone. It is its own key: a boost only to cards off the
  battlefield is no `boosts_others` and no `self_boost`, and a card that perpetually
  boosts ITSELF off the battlefield (Tomakul Phoenix, in the graveyard) is neither
  `card_boost` nor a battlefield `self_boost`. Its pairings: `graveyard` both ways
  with reanimation and creature recursion; `hand` and `stack` both ways with
  creature-dense decks; `library` and `everywhere` page-only
  (`signal_keys.SubjectRole.PAGE_ONLY`). The same branch writes a perpetual boost to a
  group of your creatures on the battlefield (Legion of Clay, Arming Gala, Coalition
  Construct, Stalwart Speartail, Lae'zel, Primal Warrior) and the battlefield half of
  one to every card you own (Naktamun Shines Again, Network Marauder, Unbreakable
  Remnant) as a team pump with no end date, so they read here as boosts to others:
  `effect_boost` and `boosts_others|you|effect` (the team signal, `team_boost_or_grant`,
  where its own rule — a generic team, no tribe — holds), never `self_boost` from that
  clause; and Defiling Tears' "+1/-1" as a targeted `Pump`, read as Lash of Malice is:
  `effect_boost`, `boosts_others|you|effect` + `target_spell`, and the shrink.

*The coordinator's decisions (2026-11-25, from Dan's confirmed summary):*

- **A static self-boost counts**: `self_boost|you|static`, from Dan's "a creature grows
  itself by any means".
- **Counter movers are `boosts_others|counters`** (moving a +1/+1 counter onto another
  creature puts it there, CR 122.5; graft, 702.58a); bolster, amass and "each creature
  you control explores" stay `counters`.
- **The heroic page offers only spells for every key**: its keyword grants too —
  a targeted grant an instant's or sorcery's own spell makes (Gods Willing; not Dirge
  of Dread's cycling trigger, whose target is the ability's, 115.1a's example), and an
  Aura whose grant is all it gives (Flight): an Aura spell targets as it is cast
  (303.4a). Equipment is not offered (equip is an ability, 702.6a).
- **The ability-only page serves only abilities' keyword grants**
  (`card_reads.grants_keyword_by_ability`): an instant's or sorcery's own grant is a
  spell's, its cycling trigger's an ability's (`crosswalk.keyword_grant_deliveries`).
- **Gear that attaches only to an opponent's creature is no boost of yours**
  (Bloodthirsty Blade's "{1}: Attach this Equipment to target creature an opponent
  controls", with no equip): no `boosts_others|attached`, no target subject, and
  no `voltron_makers` either (`counters_voltron.gear_pump_subjects`, the read both
  share, skips it; Dan's ruling, 2026-11-25: a boost that can only land on
  opponents' creatures is never yours).
- **Tribal and "cards you own" team pumps stay off `team_boost_or_grant|you|pump`**,
  as their typed peers are: Coalition Construct's chosen type and Stalwart Speartail's
  Dinosaurs read as History of Benalia's Knights and Goblin General's Goblins do, and
  Network Marauder's and Unbreakable Remnant's "cards you own" likewise;
  `effect_boost` and `boosts_others|you|effect` carry them.
- **Kept**: `boosts_others` page-only, with no avenue of its own; the one "Cash in its
  size" sub-avenue; the `targeting_matters|any|ability` subject; `power_tap_engine` as a
  power-as-damage page; the 400 `self_boost|you|static` cards (Dan confirmed).

*The builder's choices where both were silent:*

- **The static line**: a static whose `affected` is the card (alone, or beside a group:
  "~ and land creatures you control get +2/+2" — Sylvan Advocate) and whose modification
  ADDS to power or toughness (`AddPower` / `AddToughness` or their counted forms,
  "gets +1/+1 for each …"); a characteristic-defining ability that SETS them (CR 604.3,
  layer 7a — Tarmogoyf's "*/1+*") is the card's size, not a boost.
- **Only a creature body grows itself** (CR 208.3: a noncreature permanent has no power
  or toughness): a creature card, a Vehicle (301.7) or Spacecraft, or a permanent that
  makes itself a creature (a manland). A noncreature that grants growth to a creature
  is `boosts_others`: `attached` (and its delivery) for an Aura's or Equipment's grant
  to the creature it is on (Sunbond), `counters` for a grant to a group (Clan Crafter).
- A payoff that only an ability fires ("of an activated ability" — Professor Hojo) is
  `targeting_matters|any|ability`, offered only `target_ability`; a card's payoffs
  combine into one subject (spells and abilities both make `""`).
- A crew trigger isn't combat; exert, "enters or attacks" and "attacks and isn't
  blocked" are (`combat_trigger_boost`; exert is an optional cost to attack, 701.43d).
  Bolster (701.39a), amass (701.47a) and "each creature you control explores" are
  `counters`.
- A bestow creature's "this creature and enchanted creature each get +X/+X"
  (Nighthowler) is `attached` + `target_spell` (its bestowed spell targets, 702.103b),
  not an anthem.
- `team_boost_or_grant|you|trample` is offered the self-growers under its trample
  subject only (`SubAvenue.deck_subjects`).

**Who is offered what** (`signal_specs`):

| Page | Offered |
|------|---------|
| Grows itself (`self_boost`) | one "Cash in its size" sub-avenue: fights / bites, power-as-damage and power-tap (`_POWER_FLING_EXTRA`'s idents), power doublers, power-matters payoffs, trample and evasion grants; under `activated` only, big mana and untap effects |
| fight, power-as-damage (`damage_equal_power`, `power_tap_engine`), power doubling, power matters, trample / evasion granters (`team_evasion_grant`, `keyword_grant_target`, `aura_equip_kw_grant`) | creatures that grow themselves |
| power matters, the combat-damage payoffs (the old "Combat tricks / pump" extra), fight, power-as-damage, power doubling | boosts your other creatures |
| big mana, untap engine | firebreathers (`self_boost|you|activated`) |
| targeting payoffs (`targeting_matters`) | by the payoff's trigger: "Whenever you cast a spell that targets ~" (heroic; subject `spell`) the spells (`target_spell`, an instant's or sorcery's own keyword grant, a keyword-only Aura); "becomes the target of an activated ability" (subject `ability`) the abilities (`target_ability`, an ability's keyword grant); "of a spell or ability" (`""`) both |
| team boost and keyword grants, under `trample` | creatures that grow themselves |
| a graveyard `card_boost` | reanimation, creature recursion (and those pages offer it back) |
| a hand or stack `card_boost` | creature cards (and creature-dense pages offer it back) |

A sub-avenue offered under one subject only carries `SubAvenue.deck_subjects`; the hub
opens it for a later signal of that subject even when an earlier subject opened the
theme (`engine._subject_extras`).

**How it is read.** One shared walk answers who a boost lands on and how
(`_card_ir/crosswalk/boosts.py`). `boost_recipient`: `SelfRef` is the card; a
`TriggeringSource` is the trigger's own object — the card when the trigger watches only
the card, except an event with a second object (the creature in combat with it, which
another player controls, CR 509.1a; the Vehicle it crews); an "it" (`ParentTarget`)
resolves through the chain's own target thread (`reads.iter_threaded_target_statics`),
a `TargetOnly` slot, a token the chain made, the last object an earlier effect named,
a delayed trigger's watched object, a "for each" repeat, else the trigger's own object;
what the structure doesn't name is `unknown`, never guessed. `chosen_target` says
whether a boost targets one creature (never an attached object, nor one chosen on
resolution — `reads.effect_chosen_on_resolution`, CR 115.10a); `boost_delivery` how
(a delayed triggered ability a spell creates is an ability, CR 603.7, 115.1d). Where
phase binds the "it" to the wrong object, the correction layer rewrites it first:
`misparsed_shapes`' paid-then-it, heroic-it, Aura-self-pump and moved-away-it rows,
each with a canary, beside the keyword-pump duration row and the flattened-boon row
(Flaming Fist Duskguard and Valiant Farewell's next-creature-spell boon, which phase
writes as a plain `Pump`, rewritten to its own `CreateBoon`). A replacement's
`SelfRef` is the object an enters-with replacement watches (Metallic Mimic's
entering creature), and the card in any other (Ravenous Slime); a damage
replacement's `PostReplacementDamageTarget` the damaged creature (Vigor);
an untargeted pending enters-with counter another creature's (Yuna). A target in a
graveyard, hand or library, and a delayed trigger's "it", is no chosen target (Defy
Death, Valiant Farewell). `crosswalk.targeting_trigger_source` reads what a typed
targeting payoff watches, a granted one included (Livewire Lash, Kira); a payoff
phase parks (an `Unknown` trigger mode, a whole-ability residue, the dropped half of a
typed trigger) is read by the shared clause grammar
(`crosswalk.parked_targeting_payoffs` over `clause_grammar.targeting_payoffs`, phase
v0.133.0's block): Agrus Kos, Eternal Soldier and Skophos Maze-Warden `ability`,
Dormant Gomazoa, Iron Fist, Living Weapon and Ms. Marvel, Kamala Khan `spell` (the last
two also `you`), Bill Potts `""` (spells and abilities both). Only a parked payoff the
grammar can't read is left to the residue arm, which names no source (`""`). The lanes are `_analysis/lanes/boosts.py` (`self_boost`;
`boosts_others`, read after every lane and bridge row from the tree and the lanes'
own signals; its `attached` is `counters_voltron.gear_pump_subjects`, the read behind
`voltron_makers|you|pump`) and `tree_synthesis.combat.effect_boost_units`. Sickle
Dancer's parked self-pump is its own ledger row (`self_pump_condition_parked` →
`self_boost`).

**Measured** on the whole index (`signals-8b2.pkl` against `signals-8a.pkl`, 2026-11-25,
legal cards; the summary is `8b2-summary.md` beside them, with what moved since the
first build, `signals-8b.pkl`): `effect_boost` lost 282 (the self-only pumps, the
paid-for and heroic "it"s, Sickle Dancer's ledger row, Flailing Drake, and the "it"s the
structure leaves unread) and gained 49 (exalted and battle cry), 1,698 in all.
`self_boost` 3,130 cards (`""` 608, `activated` 755 — `self_pump` held 714, the rest
phase's "+N/+N and gains …" self-pumps it never read — `counters` 1,616, `static` 400).
`boosts_others` 4,572 (`effect` 1,698, `counters` 1,471, `anthem` 545, `attached` 987,
`target_spell` 1,251, `target_ability` 1,602). `combat_trigger_boost` +45 / -34 (811).
`targeting_matters|any|spell` 122, `|ability` 5. No card that lost `effect_boost` to the
self-only rule is left with no boost signal; two cards hold none (Flailing Drake, whose
pump lands on an opponent's creature, and Garruk, Apex Predator, whose emblem the read
doesn't follow).

The five cash-ins began as one sub-avenue each; under the hub's 12-label avenue cap
they pushed Ishai, Ojutai Dragonspeaker's Partner avenue off the list (a self-counter
grower now opens "Grows itself" too), so they are one.

**Measured again** after the second review (`signals-8-final2.pkl`, with the
`card-boost` merge; `8-final2-summary.md`): 54 cards moved against
`signals-8-final.pkl`, each by one of the fixes above. `self_boost` 3,116 (`""` 608,
`activated` 755, `counters` 1,602, `static` 400); `boosts_others` 4,585 (`effect`
1,706, `counters` 1,477, `anthem` 545, `attached` 986, `target_spell` 1,246,
`target_ability` 1,593); `effect_boost` 1,706; `combat_trigger_boost` 815;
`card_boost` hand 29, graveyard 7, library 9, stack 5, everywhere 3;
`targeting_matters|any|spell` 120, `|ability` 3.

**Consequences.**

- `boosts_others` opens no avenue (`signal_keys.PAGE_ONLY_KEYS`): it is the umbrella the
  size pages offer, so a deck's pumps, anthems and gear still open their own themes.
- `self_boost`'s `activated`, `counters` and `static` are riders in the commander-need
  read, as `self_pump` and `self_counter_grow` were; a triggered self-pump on a tribe
  entering still pays the tribe off.
- The heroic page's and the ability-only page's keyword grants are matched per
  ability (`crosswalk.keyword_grant_deliveries`, read through two `card_reads`); the
  "spell or ability" page serves every `keyword_grant_target` card.
- The correction rows change what other lanes see too: the Thriving cycle and the four
  heroic counter cards are now `self_counter_grow`, and Paroxysm `voltron_makers|you|pump`.
