# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

The phase-rs parse reports below are packaged as ready-to-post issue files in
`docs/plans/phase-upstream-issues/` (45, re-verified against v0.118.0; 2026-11-01).
Posting them is Dan's.

**From the Jace, Multiverse Architect precon tune (2026-10-17)**

- **Phase parse gap, worked around locally (2026-10-31): Disa the Restless.** Her
  "Whenever a Lhurgoyf permanent card is put into your graveyard from anywhere
  other than the battlefield" is a trigger with mode `Unknown` and no zone
  fields (its effect is a `ChangeZone` to the battlefield of the
  `ParentTarget`); `misparsed_shapes`' graveyard-arrival row rewrites it to the
  `ChangesZone` → Graveyard form (`test_graveyard_arrival_unknown_mode_canary`
  retires it). Upstream report, ready to file against phase-rs/phase: *"Disa the
  Restless (DSK): the first triggered ability parses with `mode: {Unknown: "Whenever
  a Lhurgoyf permanent card is put into your graveyard from anywhere other than
  the battlefield"}`, `origin`/`destination`/`valid_card` null, while the body is
  typed (`ChangeZone` of `ParentTarget` to `Battlefield`). Expected: `mode:
  ChangesZone`, `destination: Graveyard`, `valid_card: Typed[Permanent,
  {Subtype: Lhurgoyf}] + Owned You`. Note the grammar has no origin for 'from
  anywhere other than the battlefield' (origin null today means 'from anywhere',
  as on Countryside Crusher); an `origin: NotBattlefield` or an excluded-origin
  field would let the clause be typed exactly."* (drafted: `docs/plans/phase-upstream-reports.md` §1) Beside it, the crosswalk's
  `trigger_def_event` no longer reads every null-origin graveyard arrival as a
  death: 49 of the 61 null-origin `ChangesZone` → Graveyard triggers are "from
  anywhere" watchers (Gitrog, Titania, Sefris, Yuma), told from the 12 permanent
  watchers by their filter (an owner, no controller — CR 108.4; a controller or
  an attached object is a permanent — CR 110.1). The one filter the shape cannot
  split: Patron of the Nezumi's "a permanent is put into an opponent's
  graveyard" (owner-scoped like Moonshadow's "permanent cards"), read as a card.
- **Pass D: the serves still on a regex** (2026-10-23;
  `docs/plans/serve-idents-and-avenue-support.md` "Pass D"; each spec's comment
  names its remainder). Regex-only, measured over the legal corpus:
  `ability_strip_payoff` (the
  crippling-drawback text beside a power floor; no lane reads a drawback a strip
  turns off). Every lane follow-up the pass found shipped or was settled by
  2026-11-01 (the lane passes of that day, the audit's "The fourth lane pass");
  what remains here is phase's. Phase gaps
  to report upstream (Dan posts): Mask of the Schemer's connive X (phase parks
  "where X is the amount of damage it dealt" as `where_x_binding`, so
  `card_draw_engine` can't read it); (drafted: `docs/plans/phase-upstream-reports.md` §6, §12–§15, §19, §20, §23; "Already fixed"; "Not drafted") — from Pass D: Frodo, Sauron's Bane's granted
  trigger;
  Teferi, Temporal Pilgrim and Devastating Mastery's chooser stamped You; The
  Canopy Cover's opponent-only hexproof as SelfRef; Phyrexian Unlife and the
  zero-life cards as unconditional CantLoseTheGame; seek has no player and nine
  seeks drop; printed firebending has no trigger; double team as CopyTokenOf;
  conjure-of-choice as DraftFromSpellbook; Ojutai Exemplars' "Return it" as
  TriggeringSource (a canary); Fatespinner's skip (a canary); Leonin Arbiter,
  Shadow of Doubt, Pale Moon, Cephalid Shrine, Hallowed Moonlight, Mistcaller,
  Juxtapose, Cultural Exchange, Legerdemain, Desolation,
  Cleanse, Crusade, Artificial Evolution, Tomik; Champion of Stray Souls'
  graveyard zone; Sinister Gnarlbark's blight; Become Brutes' Role; Gemcutter
  Buccaneer's Equipment subtype; Krydle's mill; One Ring to Rule Them All's mill
  reach; where-X scry / surveil (Desmond Miles); Platinum Angel Avatar's "If you
  control an artifact, a creature, an enchantment, and a land" condition (a
  Vanguard card, so no bridge). Earlier: council's dilemma /
  secret council votes parked as residues (a canary), Brago's Representative, Overlord of the Hauntwoods'
  token, Narset Transcendent's rebound, Ral Izzet Viceroy's emblem, a block
  trigger's "it" as ParentTarget, Go Blank's graveyard owner, Estrid's
  Invocation's copy, Mortarion, fourteen damage clauses left Unimplemented
  (Power Surge, Urborg Stalker …), Curse of the Pierced Heart's controller,
  Masako, Lander / Map token abilities, Collision Course's AnyOf, the optional
  wheel's draw scope (Snort — a canary), Can't Stay Away, Custodi
  Soulcaller, Lich-Knights' Conquest, Balthor, Omen Machine, Blightwing Bandit,
  Abduction's ChangeController, "as though it had flash" dropped (Rootwater
  Shaman, Arlinn), Radagast, Aluren, Jin Sakai, Nether Void's unless-pay, Mana
  Breach's controller, Dimir Keyrune, Hive of the Eye Tyrant, Corpse Cobble,
  snow landwalk, Vectis Gloves, Quicksilver Fountain, Sideswipe.
- **Every held serve spec is converted (2026-10-19); the phase gaps behind
  the lanes** (every lane gap and false positive this entry listed shipped or
  was settled in the lane passes of 2026-11-01; the per-spec censuses are in `docs/plans/serve-idents-and-avenue-support.md`
  §2; the 41 holds of the serve-ident pass and the six of the fourth pass are
  all `serve_idents` now, each with its remainder classified). Phase gaps,
  each bridged 2026-10-19 by the supplemental parser with a `retirement_canary`
  or a self-retiring ledger row (tests/mtg-utils/test_phase_gaps_*.py; report
  upstream all the same, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §7, §8, §9, §15, §19, §22, App. A): where-X keyword heads (Mask of the
  Schemer's connive X, Thromok's devour X, Fall of Cair Andros's amass X,
  Officious Interrogation's investigate X — the `_where_x_head` recovery,
  scoped to connive / amass / investigate; opening it to every allowlisted verb
  would recover ~40 more where-X clauses across many lanes, a separate
  measured promotion); energy residues (`gain_energy` / `energy_payment`
  tokens: Overclocked Electromancer, Robobrain War Mind, The Motherlode,
  Reiterating Bolt, Salvation Colossus, Izzet Generatorium's condition);
  foretell residues (Ethereal Valkyrie, Karfell Harbinger, Ranar); Osteomancer
  Adept's forage cost (a ledger row); Jetmir's Fixer (a lane arm over the
  recovered counter); the nine "all damage dealt to X is dealt to Y instead"
  replacements (`damage_redirect` token, Treacherous Link and Megatron kept
  out as opponent-side); Prairie Dog and Zabaz (`counter_bonus` token);
  Death's Approach and kin (`debuff` static token — the Sewer Plague ledger row
  retired by it); Attempted Murder; Ian the Reckless and Volcano Hellion ("to
  you and …" burn); Stunning Shot and three more fresh tap targets; ledger rows
  for Cragganwick Cremator / Flames of the Blood Hand / Kaboom! / Unstable
  Footing (a dropped planeswalker target), Insult // Injury, Tetsuo, Mob
  Verdict / Chandra's Flame Wave / Path of Mettle (the creature half), Decimator
  Beetle / Zealous Persecution / Foul Renewal (a dropped shrink), Heir of the
  Ancient Fang / Lethal Exploit / Lethal Throwdown / Lion Umbra (modified),
  Elspeth Resplendent / Undercover Operative (shield counters), Nicanzil,
  Dream Devourer, The Fourth Doctor, You Find a Cursed Idol (Unknown or
  dropped trigger modes); field corrections for the `SelfRef` untap locks
  (Mesmerizing Benthid, Wall of Stolen Identity, Tsabo's Web; Scion of Stygia and
  Code of Constraint fixed at v0.118.0), the anaphoric "it gets -N/-0" pumps
  (the other Jace, Tamiyo, Blood Lust, Six-Sided Die; Jace, Architect of
  Thought fixed at v0.118.0), "that player controls" taps (Delirium, Mana Web;
  Yosei fixed at v0.118.0 — and 22 self-tap cards such as Jaddi Lifestrider left
  `tapper_engine`), the Hidden / Opal / Veiled / Lurking self-animation cycle,
  Alacrian Armory and Animate Artifact, Athreos's exile, the graveyard owner
  (Skullsnatcher, Zombie Cannibal, Grime Gorger — opponents; Savior of
  Ollenbock — any), `CounterPlayerAddedAll`'s energy kind, Venser's Diffusion;
  the eight protective superfriends cards (a parked-recipient check); and the
  repo-side reads: granted afterlife / mobilize token makers, Worldwalker
  Helm's replacement Map, Dodecapod's enters-with counters, Hamza / Starport
  Security's countered-creature cost reductions, Brimaz's Phyrexian death,
  `walk_effect_chain` descending a coin flip's WIN branch only (+23 idents;
  the lose branch — Volatile Rig's sweep — is deliberately not walked, since
  both branches would serve drawbacks: Scoria Wurm's self-bounce). Phase gaps
  with nothing on our side to read (report upstream, Dan posts): Commence the Endgame (the amass is folded into the Draw
  node's description with no residue; the keyword-array fallback serves it),
  Izzet Generatorium's energy replacement (a payoff on makers, left), Aether
  Refinery's doubler typed as a CreateToken replacement (no consumer reads it
  wrong), Rain of Riches (already served), the aftermath faces Rags // Riches,
  Reduce // Rubble, Indulge // Excess (phase emits no record for the second
  face — a canary waits on it), Pradesh Gypsies (no record at all), Tomik's
  "affinity for planeswalkers" (the keyword's parameter is not exposed), the
  Attraction Unknown modes (already served by the sweep row). Report upstream
  (worked around, each with a `retirement_canary`): Orcish Captain's losing
  flip "it gets -0/-2" stamps its "it" `SelfRef` (it is the Orc the winning
  outcome targets); Desperate Gambit's one coin flip is typed as two (a
  win-only `FlipCoins` whose `sub_ability` is a lose-only one —
  `misparsed_shapes` merges them; Goblin Kites' and Fickle Efreet's delayed
  flip is the same split with an outcome-less first flip) and its "choose a source you control" loses
  "you control" (`TargetOnly{target: Any}`; no read needs it once the losing
  prevention reads as the gamble's drawback).
  Tragic Arrogance stays keep_n_wrath's (adjudicated disjoint from edicts).
  Phase parks, report upstream (Dan posts): Dark Sphere's "prevent half that
  damage" (`prevent` residue) and Forcefield's "prevent all but 1"
  (`unrecognized_clause_head`); Blinding Powder's and Torrent of Lava's granted
  prevention (`granter_reference_unreached`); Eye of Ojer Taq's "Craft with two
  that share a card type" (`unknown`); Guardian of the Ages' "it loses defender
  and gains trample" parks as `unparsed_condition` (ledger row
  `loses_defender_trigger_parked` keeps it a voltron carrier).
  A phase gap behind one false positive (report upstream, Dan posts; drafted in
  `docs/plans/phase-upstream-reports.md` §24): Skyclave Apparition's "the exiled
  card's owner creates" token reads as yours — phase stamps the Token's `owner`
  `Controller` and the exiled card `Owned{You}`, so no structure tells it from
  your own token; nothing on our side can read it. Not a false positive (2026-10-31, don't
  re-suggest): Investigator's Journal's LOW `proliferate_matters` — its suspect
  counters are counters (CR 122.1, not the suspected designation of CR
  701.60a), proliferate adds one of each kind already there (CR 701.34a), and
  removing one is its draw cost, the remove-counter-cost read's own case.

**From the Fynn, the Fangbearer real-deck validation (2026-10-29; `real-deck-validation.md`)**

- **Phase drops a bite's own target** (report upstream, Dan posts): Spirit
  Flare's "it deals damage equal to its power to target attacking or blocking
  creature an opponent controls", Crush Underfoot's "to target creature" and
  Thorin, Mountain-king's "to up to one target creature" parse as a
  `DealDamage` to `ParentTarget`, the dealer itself, so none reads as a bite
  (`crosswalk.is_bite`) or as power damage of yours.

**From the Omnath Competitive Brawl build (2026-10-04)**

- **Phase gaps behind the closer, alternative-cost and mass-land-denial reads**
  (found moving `_tuner/` and `deck_stats` onto the trees, phase v0.94.0; report
  upstream, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §6, §9, §19, §22, App. A). Each is a card the old regexes read and the trees don't:
  - Reach: `unparsed_quantity` residues park "loses life / deals damage equal to …"
    (Within Range, Soulblast, Final Punishment, Mjölnir; ~28 such residues name
    damage or life loss). (Underbridge Warlock's boon, once a self loss, is a
    typed ``CreateBoon`` since v0.118.0.) (The
    `where_x_binding` X effects — Insatiable Hemophage, Zenith Flare — are read by
    `reads.unbound_x_reach`, canary `test_unbound_x_reach_canary`.)
  - Game wins: Frodo, Sauron's Bane's Rogue clause is dropped (its second ability
    parses as the Ring tempting you); Celestial Convergence's win is an
    `unbound_subject` residue.
  - Alternative costs, each corrected where the tree is built with a canary: keyword
    lines with a non-mana cost parked as residues (morph "Reveal a blue card", warp
    / madness with life, Escape Velocity's escape; blitz parses since v0.104.0 —
    `core._dropped_keyword_costs`, `test_dropped_keyword_costs_canary`); suspend X
    read as count 0 and Warbringer's / Catalyst Stone's cost changers read as empty
    keywords (`core._misread_keyword`, `test_misread_keyword_canary`).
  - Mass land denial, each with a canary or a ledger row: Eye of Singularity and
    Herald of Vengeance lose their narrowing clause and read as "all permanents"
    (vetoed by `reads.NARROWED_PERMANENT_SWEEPS`; End Hostilities is an
    `attached_to_qualifier` residue since v0.104.0); Burning of Xinye's "destroys
    four lands" is a residue
    and Global Ruin's sacrifice a tracked set (both ledger bridges).
- **Phase gap behind the tuner's ramp sourcing** (found 2026-10-08, phase v0.94.0;
  report upstream, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §10). Boxing Ring's "Activate only if you control a
  creature that fought this turn" is an `unparsed_condition` residue, not an
  activation restriction — the only legal card whose mana or Treasure ability is
  gated that way (`reads.UNPARSED_ACTIVATION_GATE`,
  `test_boxing_ring_gate_is_still_a_residue_canary`).
- **Phase misparses behind cut-check reads** (found 2026-10-08; report upstream,
  Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §14, §16, §17). Each has a canary: Glorfindel, Dauntless Rescuer's "can't be blocked
  by more than one creature each combat" parses as `CantBeBlockedBy` a typeless
  filter (`test_glorfindel_blocking_limit_misparse_canary`); Wyll's Reversal loses
  "with one or more targets", so it reads as a commander-spell copy
  (`test_wylls_reversal_target_constraint_canary`); aftermath halves (Dusk // Dawn),
  Garza's Assassin's recover, Salvation Colossus's unearth and Oscorp Industries'
  mayhem are dropped, so the `self-recurring` preset and the "Self-recurring
  fodder" serve read them by keyword (`theme_presets.SELF_RECURRING_KEYWORD_GAPS`,
  `test_self_recurring_keyword_gap_canary`); Nether Shadow's graveyard return is an
  `unparsed_condition` residue since v0.104.0 (ledger row
  `nether_shadow_graveyard_return_parked`); Bumi's Feast
  Lecture's earthbend return binds to the Food token (`LastCreated`) instead of the
  land (`test_earthbend_last_created_binding_canary`).
- **Phase misparses behind the "Self-recurring fodder" serve** (found 2026-10-09,
  phase v0.104.0; report upstream, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §3, §6, §16). The serve reads the card's graveyard
  return routes (`card_advantage.comes_back_from_graveyard`); three legal creatures
  the old regex served stay out because
  phase loses "this card": Sproutback Trudge's and Syrix, Carrier of the Flame's "you
  may cast this card from your graveyard" is a `CastFromZone` with target `Any` in a
  battlefield-zone trigger; Worldheart Phoenix's (and Raffine's Guidance's)
  graveyard alternative cost is a `CastWithAlternativeCost` static whose `affected`
  is your typed permanents, active on the battlefield. Read with a canary: "you may
  cast it from your graveyard" (Skyclave Shade, Hildibrand Manderville, Mosswood
  Dreadknight, Ichor Aberration) is a `PlayFromExile` permission on an empty
  `TrackedSet` (`test_unbound_graveyard_cast_misparse_canary`); Forgeborn Phoenix's
  granted "return this card from your graveyard to battlefield" parses as a
  `Bounce` to hand (`test_perpetual_bounce_misparse_canary`).

**From the twohg-guide skill (2026-09-27)**

- **Phase drops the player behind edicts** (found 2026-10-09, phase v0.104.0;
  report upstream, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §12b). Each is read with a workaround that retires itself:
  a chained "…, then sacrifices" loses its subject (Undercity Plague, Priest of
  Forgotten Gods, Din of the Fireherd's land half, Nicol Bolas, Planeswalker's −9 —
  `test_chained_sacrifice_actor_dropped_canary`); "each opponent [who …]
  sacrifices" parses with no player at all (Variable Solutions — ledger row
  `opponent_sacrifice_actor_dropped`). Fixed at v0.118.0: Davriel, Soul Broker's
  sacrifice now sits in its delayed trigger; Papalymo Totolymo's clause is parked
  whole as an `unbound_subject` residue instead.
- **phase tags "each other player" as `Opponent`.** Grave Pact and Syphon Mind carry
  `player_scope: Opponent`, which only differs from "each opponent" in team formats
  (it includes your teammate). phase doesn't support team formats yet, so this isn't
  reported upstream for now. `twohg_scan` vetoes it with an oracle-text check guarded by
  a `retirement_canary` test; delete the veto when the canary fails.
- **`twohg-scan --shadow`.** Listing IR-vs-text disagreements (information only, never
  merged) would calibrate the text fallback and surface phase misparses. Deferred until
  a set arrives that phase hasn't parsed. Baseline from FRA with the IR stripped: the
  text path misses Tomik, Izzet Sparkmage (a damage *replacement*, not an "each
  opponent" clause), reads Cruel Calculations as target-player (phase drops its player
  target), and differs on removal reach for about 18 cards.

**From walking phase's branch shapes (2026-10-09)**

- **Phase misparses behind the branch-misread registry** (`_card_ir.branches.
  BRANCH_MISREADS`, each row with its `retirement_canary`; report upstream, Dan
  posts) (drafted: `docs/plans/phase-upstream-reports.md` §12c). Fraying Line's "that player may pay {2}" is a `PayCost` with `payer:
  Controller`, so its "Otherwise" branch reads as yours (pruned from the certain
  records: LOW). (Osseous Sticktwister's phantom discard choice and Spitting Slug's
  dropped blocking-or-blocked narrowing are fixed at v0.118.0; their rows retired.)
  Also unreported, no workaround: Worms of the
  Earth's "any player may" choice is `chooser: Controller` (read off the wrapper's
  `optional_for`), and Ensnared by the Mara's villainous branch carries
  `player_scope: All`, so its (LOW) impulse_top_play scopes "each".

**From the phase v0.104.0 bump (2026-10-09)**

- **Phase now fails closed on what it can't represent** (#9392 and kin), parking the
  whole effect as a residue named for its shape (`unparsed_condition` 63 → 216 at
  v0.104.0, `put_counter_tail`, `attached_to_qualifier`, `static_structure`,
  `unparsed_verb_arguments`, `perpetual_modify_pt`, `granter_reference_unreached`).
  Recovery reads the parked verbs (`recovery.ALLOWLIST`), each instruction of a
  compound clause and a granted body's residue (nine rows retired that way,
  2026-10-09); the remaining v0.104.0 ledger rows are parked conditions and verbs the
  grammar doesn't tag. Report upstream by residue class, not per card. (drafted: `docs/plans/phase-upstream-reports.md` §21, App. A1)

**From the phase v0.118.0 bump (2026-10-30)**

- **Phase misparses new at v0.118.0** (report upstream by shape, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §9, §14, §18, App. A):
  - *Subject peeled from a parked clause.* "Target player discards a card for each
    creature it devoured" (Tar Fiend) parks as `unparsed_quantity` "discard a card
    for each …"; likewise Whispering Specter, Doom Foretold, Brain Pry, Cabal
    Shrine, Thoughtcutter Agent ("lose 1 life and reveals their hand"). Read back
    by `recovery._peeled_subject`; Thoughtcutter's second verb is ledger row
    `second_verb_reveal_hand_parked`.
  - Geistlight Snare's "It also costs {1} less to cast" parks as its own
    `unbound_subject` residue in the spell's chain (canary
    `test_self_discount_continuation_parked_canary`).
  - "Reveal N cards from their hand and you choose one" (Blackmail, Hollow
    Specter, Cabal Interrogator, Pulse of the Dross) and "pay one or more {E}"
    (Pia Nalaar, Chief Mechanic; Rampaging Aetherhood) park as
    `unparsed_verb_arguments`; recovered by new grammar rows.
  - Mana Clash's and Rakdos, the Showstopper's per-flip outcome park as
    `per_object_coin_flip_outcome` (direct_damage / mass_removal lost).
  - Bestial Fury's "it gets +4/+0 and gains trample" binds `ParentTarget`, not
    the enchanted creature (aura_equip_kw_grant lost).
  - Seasoned Cryomancer's reflexive tap and Summon: Kujata's, Vivien's
    Invocation's and Adaptive Armorer's reflexive effects park as
    `zone_change_reflexive_*`.
  - Parked whole, each an accepted loss with no workaround (one line each to
    report): Legion's Chant (`unenforced_aggregate_resolution_selection`), Rune
    Snag (`unless_payment`), Lich Lord of Unx's loss per Zombie, Helm of
    Obedience's repeat mill, Turtles Forever (`search_zone_list`), Nazahn's
    search (`search_result_condition`), Even the Odds (`casting_restriction`),
    Smogbelcher Chariot (`perpetual_gain_choice`), Divine Purge's perpetual
    grant, Ursine Monstrosity's mill, Soulgorger Orgg's and Glimmer Hoarder's
    life loss, Absolving Lammasu's and Marrow Chomper's life gain, Tar Fiend's
    enters payload, Hateful Eidolon and Stone Haven Outfitter
    (`departure_attachment_relation`), Ludevic (`unparsed_condition`), Consuming
    Tide, Sudden Salvation and Biomantic Mastery (`unparsed_quantity` draws),
    Wheel of Potential's draw count, Pharika's Spawn's escape counters, Dark
    Intimations' +1/+1-counter tail, Brokers' Safeguard's perpetual shield
    counter, Rakdos Augermage's and Impetuous Lootmonger's own discard, Indominus
    Rex's keyword counters, Invasion of Arcavios's search.

**From the keyword tribe's dropped keywords (2026-10-26, phase v0.104.0)**

- **Phase drops a keyword from a body it otherwise types** (report upstream by
  shape, Dan posts) (drafted: `docs/plans/phase-upstream-reports.md` §15). Each is read in our correction layer
  (``_card_ir.dropped_keywords`` before strict load, the recovery stage's
  ``ConceptNode.body_keywords``), with a ``retirement_canary`` in
  ``test_phase_gaps_keywords.py``, or by a ``keyword_bodies`` ledger row:
  - *A static def's grant left out of its modifications.* Chariot of the Sun:
    "{2}, {T}: Until end of turn, target creature you control gains flying and
    has base toughness 1" types a ``Continuous`` def with ``SetToughness`` alone.
    It should add ``AddKeyword(Flying)``. Likewise Valkyrie's Call's "It has
    flying and is an Angel" (``AddSubtype`` alone), the Zendikons' "is a 4/4
    Elemental creature with reach and haste" (the animation's mods have no
    keyword), and Argivian Avenger's "your choice of flying, vigilance,
    deathtouch, or haste" (``AddKeyword`` for vigilance and deathtouch only); 32
    defs on the legal corpus. Also Guardian Zendikon's "is a 2/6 white Wall
    creature with defender", Jodah's Avenger's "your choice of double strike,
    protection from red, vigilance, or shadow" (the list past "protection from
    red" dropped) and Urza's Avenger's banding.
  - *A grant parked in an ``Unrecognized`` condition.* Tek: "~ gets +0/+2 as long
    as you control a Plains, has flying as long as you control an Island, …"
    types ``AddPower 0 / AddToughness 2`` with the rest of the line as the
    condition's ``text``. It should be one def per clause, each with its own
    condition and ``AddKeyword``. Tribal Golem, Altar of the
    Wretched's "The same is true for first strike, …", and Evolved Spinoderm's
    "Otherwise, it has hexproof" are the same.
  - *A copy's keyword dropped from its exceptions.* Irenicus's Vile
    Duplication: "Create a token that's a copy of target creature you control,
    except the token has flying and it isn't legendary" types ``CopyTokenOf``
    whose ``additional_modifications`` hold only ``RemoveSupertype(Legendary)``.
    It should also hold ``AddKeyword(Flying)``. March from Velis Vel's
    "becomes a copy … and gains haste" is the same.
  - *A keyword misread as a subtype.* Will of the Temur: "except it's a 4/4
    Dragon creature with flying" types ``AddSubtype("With")`` and
    ``AddSubtype("Flying")``. It should type ``AddKeyword(Flying)``. Leonardo da
    Vinci, Sauron, the Necromancer, Kaya, Intangible Slayer and Dino DNA are the
    same.
  - *A pump's grant dropped.* Tromp the Domains: "creatures you control gain
    trample and get +1/+1 for each basic land type" types a bare ``PumpAll``. It
    should add a ``GenericEffect`` with ``AddKeyword(Trample)`` (Haldir, Lórien
    Lieutenant likewise; the team-grant lanes read the decoration as the pump's
    own grant, ``crosswalk.pump_keyword_grants``). Stolen Vitality's
    "Otherwise, it gains first strike" drops the else branch. Indominus Rex,
    Alpha's and Priest of Possibility's "The same is true for …" lists keep only
    their first keyword.
  - *A grant, token or keyword counter parked as an ``Unimplemented`` residue.*
    Notorious Throng: "Create X 1/1 black Faerie Rogue creature tokens with
    flying" should be a ``Token`` with ``keywords: [Flying]``. Reaper of Night's
    "it gains flying until end of turn", Inventive Wingsmith's "put a flying
    counter on it" and Genku, Future Shaper's mode "1/2 blue Moonfolk with
    flying" are the same.
  - *Counter kinds swallowing a clause* (Dralnu's Pet, Printlifter Ooze, March
    Toward Perfection's boon): fixed at v0.118.0; the recovery read and the
    ledger row retired.
  - *A Role token's own ability.* Monstrous Rage: "Create a Monster Role token
    attached to it" types the ``Token`` with no static. It should carry the
    Role's "Enchanted creature gets +1/+1 and has trample" (CR 111.10k; Royal's
    "has ward {1}", 111.10m), which known-tokens has: restored before load, 11
    cards. Become Brutes parks the creation itself (a ledger row).
  - *A spell's conditional flash dropped.* Crashing Tide: "This spell has flash
    as long as you control a Merfolk" leaves no node; phase types the same line
    on Supernatural Rescue. Graveyard Shift, Mutual Destruction (whose
    condition is also a flash payoff) and Take for a Ride likewise (one ledger
    row).
  - *A grant swallowed beside the effect phase types.* Woolly Razorback's "it
    has defender" (the prevention kept), Nick Fury, Spymaster's "and gains
    indestructible until end of turn" (a ``SwallowedClause``), Guardian Beast's
    "they have indestructible" (folded into a ``CantBeEnchanted`` static on
    itself), Wakanda Forever!'s "put a permanent card … onto the battlefield
    with an indestructible counter" (a ``Dig`` to the hand alone) — ledger rows.
  - *A cloak dropped or parked* (CR 701.58a: a 2/2 with ward {2}). Hide in Plain
    Sight's "cloak two of them" is a ``Dig`` with no destination; Become
    Anonymous parks "then cloak those cards" as a residue (ledger rows).
  - *A static bound to the Equipment.* Warmonger's Chariot's "As long as
    equipped creature has defender, it can attack as though it didn't have
    defender" types ``CanAttackWithDefender`` with ``affected: SelfRef`` and the
    equipped creature only in its condition; it should affect the equipped
    creature (a ledger row).
  - *A zone's owner dropped.* Soovril, Patient Antiquarian's "nonland card in
    exile that was put there from your graveyard" types
    ``ZoneChangedThisTurn{from: Graveyard}`` with no owner, so its "gains
    suspend" can't be told yours (a ledger row; the typed grants are
    ``crosswalk.suspends_own_card``'s). The Eleventh Doctor's "If it doesn't
    have suspend, it gains suspend" is a ``keyword_anaphor_resolution_time_pick``
    residue (a ledger row).
  - Single cards, as ledger rows (card: phase emits → should emit):
    Furygale Flocking: "create two 3/3 … Elemental creature tokens with flying"
    → a ``SwallowedClause`` warning, no ``Token`` → a ``Token`` with
    ``keywords: [Flying]``; Welcome the Darkness: "Create an X/X black Demon
    creature token with flying" → only a ``CantGainLife`` static carrying the
    whole text → a ``Token``; (Doom Foretold's Knight token and Spry and
    Mighty's trample are fixed at v0.118.0, their rows retired); Case
    of the Stashed Skeleton: "create a 2/1 black Skeleton … and suspect it" →
    ``Token`` alone → plus ``Suspect``; Burn Down the House: "They gain haste
    until end of turn" → ``Token`` alone → plus a haste grant; Yasova
    Dragonclaw: "untap that creature, and it gains haste" → ``GainControl``
    alone → plus untap and haste; Thundermane Dragon: "If you cast a creature
    spell this way, it gains haste" → swallowed → a haste grant on the cast;
    Alaundo the Seer: the same clause in its granted trigger → an
    ``Unimplemented`` residue; Araumi of the Dead Tide: "gains encore" → a
    residue → ``AddKeyword(Encore)``; Salvation Colossus: "Unearth—Pay eight
    {E}" → a residue → the ``Unearth`` keyword with an energy cost; Ginger,
    Queen of Sweets: "create a Gingerbrute token" → a residue → a ``Token``;
    Phyrexian Splicer: "Choose flying, first strike, trample, or shadow: …
    another target creature gains it" → the choice parked as a cost residue → a
    ``Choose`` of a keyword and its grant; Solid Footing: "As long as enchanted
    creature has vigilance" and Ram Through: "If the creature you control has
    trample" → no ``WithKeyword`` condition → one.

**From the 2026-09-17 architecture review (worth exploring, not started)**

- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Discovery ranking:** see ADR-0043's terminal-state amendment for the unclaimed
headroom and parked items.

**From the 25-precon deckbuilder pass (2026-11-01; Dan's call: read each
proposal as a deckbuilder, fix the structure, the guide score is a yardstick)**

- **Bello's and Anikthea's pages: popular cards of the type whose text does
  nothing here.** Bello's artifacts at 4+ mana by play-rate are Banner of
  Kinship, Door of Destinies, Coat of Arms; Anikthea's enchantments Hardened
  Scales and Branching Evolution. Every candidate supplies the same need; the
  difference is whether the card's own payoff is fed in THIS deck. **Measured
  and held back (2026-11-01):** a theme-page candidate that also fills a role
  the deck is short of leading the rest (meant for Asceticism over
  Panharmonicon with no protection in the deck) put cycling Dinosaurs over
  Etali and Gishath on Pantlaza's page and protection Equipment on Bello's:
  the 25 121 → 109 guide adds. A "dead payoff" veto (a `*_matters` /
  `wants_*` card whose doer the deck lacks) has no clean key: the junk adds
  carry `chosen_type_matters`, `subtype_ref|you|shared`, `counter_doubling`,
  `any_counter_matters` — no one inverse of `metrics._cares_keys`. The
  ranker's `_gate_penalty` (a tribal gate the deck lacks) is the shape of the
  right read, widened to a payoff's doer. Idents alone cannot tell it: Etali,
  Primal Conqueror carries five payoff idents that are its own effects, and
  Hardened Scales is tagged a counter *maker* (2026-11-01).

## Settled: don't re-suggest

**From the 25-precon deckbuilder pass (2026-11-01)**

- **Shipped, keyed on commander structure, measured on the 25 (734 / 339 / 120
  → 733 / 341 / 121 swaps / guide cuts / guide adds) and the held-out 20 (579
  / 253 / 83 → 578 / 252 / 101).** (1) *The commander's needs outrank
  play-rate on its theme pages* (`swaps._ranked_pool`'s need lead,
  `_upgrades`' need gate; the needs the deck builds toward —
  `_NEED_BUILT_FLOOR` — that are a role in the plan, not more of what the
  commander already does (`kind == "redundancy"`: Ms. Bumbleflower's page
  filled with wheels) nor a property of the card (`Need.leads`: "cheap
  spells", "instants and sorceries")): Felothar's walls (Abzan Armor 2 → 6
  guide adds), Morska's Clue makers (Deep Clue Sea 5 → 8), Ellivere's Auras.
  Need reads fixed on the way: a keyword lord's bodies read off the card's
  keywords (`defender bodies` matched nothing); an artifact-TOKEN payoff asks
  for the token makers, not every artifact (Gimbal); a toughness-reading
  commander wants HIGH toughness (`commander_need.HIGH_TOUGHNESS`), not a butt
  — "toughness over power" put Snubhorn Sentry over Ghalta on Pantlaza's page;
  a voltron commander whose own suit is Auras asks for Auras, never Equipment
  (Ellivere; `Sourcing.aura_commander` filters her voltron pages the same
  way). (2) *Near-miss combos*: at
  most two adds completing a line on one deck card (`swaps._COMBO_PIECE_ADDS`;
  Blood Rites took five Exquisite Blood partners), and never a named add
  costing more than anything the deck runs (Mardu Surge's Blightsteel
  Colossus). (3) *A trim takes the card serving the fewest of the deck's
  themes first*, then the least played (`cut_candidates`). (4) *A tribe
  member's slot stays the tribe's*, members and changelings only, unless the
  commander makes that tribe's tokens itself (`Sourcing.tribe_spec`; Disa's
  Lhurgoyfs went to the graveyard page, Herald's Horn took a Dinosaur's slot,
  Quintorius's weak Spirits became other Spirits). (5) *Under a commander
  whose plan is its top end* (a need with `Need.mana_floor` ≥
  `tune.TOP_END_FLOOR`) the ramp and card-draw rows are the plan's fuel, never
  a trim (`plan_fuel`; Eldrazi Unbound trimmed four rocks and three draw
  engines). Guide-score losses taken knowingly: Tinker Time 3 → 2, Graveyard
  Overdrive 6 → 4 (its Lhurgoyfs are no longer cut at all), Eldrazi Unbound 1
  → 0 (its one hit was a draw trim's add).
- **Batch 2 (same day; the 25 733 / 341 / 121 → 729 / 340 / 121, held-out 578
  / 252 / 101 → 578 / 252 / 99).** (7) *A life-loss trigger gated to
  opponents' turns* (Valgavoth's `OncePerOpponentPerTurn`) asks for makers
  that fire on their turns — a trigger watching what opponents do
  (`opponent_*` watcher keys, a tax, a payoff lane scoped past "you":
  `commander_need._drains_on_opponents_turns`), never your own spells'
  riders; the payoff read's generic "lifeloss makers" stands down beside it.
  Endless Punishment's page is Painful Quandary, Underworld Dreams, Razorkin
  Needlehead, Sheoldred where it was Guttersnipe and Reckless Fireweaver. A
  need read off the commander's own trigger or condition leads its page
  whatever the deck holds yet (the `_NEED_BUILT_FLOOR` is for resource and
  payoff needs). (8) *Izzet Generatorium is an energy maker* through the
  ledger row `energy_gain_replacement_parked` (ADR-0048: its "you get that
  many plus one {E} instead" is a phase `replacement_structure` residue);
  Living Energy takes it and Aether Refinery again.
- **Batch 3 (same day; the 25 729 / 340 / 121 → 723 / 339 / 118, held-out 578
  / 252 / 99 → 573 / 256 / 100 — the held-out gate's floors cleared, the 25's
  three adds taken knowingly).** (9) *A graveyard-to-battlefield effect wants
  its payload*: a permanent card of the filter's types at
  `commander_need.REANIMATION_MV` (7) or more — the top end a deck cheats in,
  where Death Toll's guides' adds sit (Overlord of the Balemurk, Hoarding
  Broodlord); not a land (Teval), not a tribe's card (Sidar Jabari's Knights,
  Admiral Brass's Pirates, which come back as 4/4s), not a unit that sizes
  the card itself (Meren's experience, Alesha's power). Hornet Queen goes to
  Myr Battlesphere and Vile Mutilator to Meteor Golem where they went to
  Buried Alive and Beast Within. (10) *A commander that takes a typed card
  from its graveyard wants that type put there* (Anikthea's enchantments: the
  self-mill and discard outlets its guides add; the one graveyard-fill need
  the "put into your graveyard" trigger read and this share,
  `_graveyard_fill_need`). (11) *A token effect that favours one kind of
  token asks for makers of that kind* (Hazel's "if that token is a Squirrel,
  instead create two": `token_maker|you|Squirrel`). (12) *A land-sacrificing
  commander's consumers include the repeatable extra land drops*
  (`card_reads.plays_extra_lands` — Exploration, Azusa, Oracle of Mul Daya,
  not Explore's one turn; the landfall lane folds the read into its umbrella
  key, so the need reads it as a predicate). (13) *An ident-derived
  mana-value need stands down for the tree-read one* (Bello's
  `animate_makers|you|Artifact>=4` dropped his "non-Equipment": Hammer of
  Nazahn and Leyline Axe led his page), and *a mana-value-floor need is never
  broad* (`is_broad`; his need is 10.5% of a Gruul pool and had no page at
  all). (14) *An upgrade keeps what the cut gives the commander, whatever the
  job* (`_upgrades`: Living Death stays under Teval, Squirrel Nest and Deep
  Forest Hermit under Hazel — Assassin's Trophy and Fanatic of Rhonas supply
  none of their needs); and (15) *a trim takes a card supplying a built need
  last, ahead even of the fixing shield* (Oracle of Mul Daya over Harrow under
  Yuma). Swap counts fell where a gated upgrade found no replacement
  (Veloci-Ramp-Tor 30 → 27, Sultai Arisen 30 → 28): a card the commander
  asks for and nothing better for it is no swap.
- **Batch 4 (same day, the recursive pass over batch 3's own proposals; the
  25 723 / 339 / 118 → 719 / 338 / 117, held-out 573 / 256 / 100 → 574 / 256
  / 101).** (16) *A led page's deep suppliers join its play-rate head*
  (`swaps._ranked_pool`): a card the lead ranks ahead of every addable card
  in the head (Hazel's Squirrel makers, two needs to the head's one) is on
  the page though play-rate never reached it — Squirreled Away takes Drey
  Keeper, Scurry Oak, Camellia, Cloakwood Hermit, Squirrel Sanctuary where
  Fanatic of Rhonas and Oketra's Monument took Squirrel Nest's and Deep
  Forest Hermit's slots. Measured and held back on the way: the whole page
  sorted and cut to the lead's top — a thousand obscure one-need cards, and
  the tune spent its budget on them before its job upgrades (held-out
  Counter Intelligence 30 → 21 swaps; Enduring Enchantments took eight
  self-mill enchantments). (17) *A need-count admission never trades down a
  card that already served the commander* (`_upgrades`, the card-quality
  read as the guard): Zetalpa, Primal Dawn went to Shield-Wall Sentinel for
  ticking two of Felothar's boxes to its one. (18) *Valgavoth's
  opponents'-turn read covers the watchers no lane key names*
  (`_drains_on_opponents_turns`: a trigger on a player action by opponents
  or every player — Harsh Mentor's "an opponent activates", Kaervek's "an
  opponent casts" — or on a permanent an opponent controls, Blood Seeker;
  not the card's own attack or cast, nor a sweeper's "any": Myr
  Battlesphere, Crypt Ghast and Toxic Deluge, which the first widening
  admitted). Blood Seeker, Harsh Mentor and Stormfist Crusader are kept
  where they went to Guttersnipe and Reckless Fireweaver; Endless
  Punishment proposes 20 swaps on its $126 (30 on an unlimited budget): the
  right replacements are the pricier drainers. (19) *A `graveyard_leave_matters`
  lane* ("Cards leaving your graveyard": Teval, Desecrated Tomb, Chalk
  Outline, Tormod, Syr Konrad's second trigger — read off the trigger's
  graveyard origin through the shared `trigger_zone_changes`), and *a payoff
  with no maker lane behind it is its own redundancy*
  (`commander_need._PAYOFF_REDUNDANCY_KEYS`: "graveyard leave payoffs like
  the commander" under Teval). (20) *Mirko's dropped "power less than"
  clause* is read off the ability's description behind a `retirement_canary`
  (`_desc_sizes_the_card`; phase v0.118.0 keeps no residue), so his return
  states its own line and opens no payload page.

**From the Jace, Multiverse Architect precon tune and the 25-precon audit (2026-10-17 to 2026-11-01)**

- **The polymorph tune and the 25-precon audit: every lever measured, the
  verdicts** (third pass, 2026-10-18, closed 2026-11-01 at baseline N8 —
  `docs/plans/precon-audit-2026-10-18.md` has the method, the before / after
  tables and the per-precon reads; the first two passes' fixes are listed
  there; `docs/plans/tuner-plan-2026-10-30.md` "Progress" is the ledger of
  every run since. Each lettered sub-entry below is a verdict: a shipped read,
  or a policy measured against the held-out gate and held back as a patch under
  `~/mtg/tuner-work/w41/`. Nothing in it is open; a new tuner lever needs a new
  card read first). Fixed in the third pass: a quality read
  inside a lane is "a feeder nobody plays" (measured, below); Spine fills
  rank by play-rate within a mana-value band; player-only damage is not
  `interaction`; Bello's Animation and Yuma's Deserts have lanes
  (`animate_makers|you|<Type>`, `land_type_matters|you|<Type>`); pillowfort
  and fogs are not `superfriends_matters`; a typed token replacement or
  sacrifice trigger carries its token kind (Xorn is `treasure_matters`,
  Academy Manufactor three kinds, Fisher's Talent `tokens_matter|you|Fish`);
  an artifact-TOKEN maker is a maker, never `artifacts_matter`; carers respect
  scope where the specs split it ("Opponents' graveyards" 43 → 4 under
  Teval); two avenues with one carer set are one theme (Polymorph fodder
  absorbs Token generators); an emerging theme needs two carers in
  proportion; the primary lane is a held lane deep enough to show; three pair
  rows for the Enchantment / Artifact / Planeswalker cheat subjects; the CR
  2026-09-25 subtype lists (Heartwood); Syr Konrad's folded zone-change
  trigger reads as `dies` for a dies doubler; a card that merely has an
  activated ability is a payoff target of "Activated-ability engine", not a
  builder (its untap engines are — Abzan Armor read that lane as its main
  over a 42-deep toughness lane; the Jace phantom of the polymorph entry's
  (d) is gone with it). Fixed in the seventh pass (2026-10-19): the upgrade
  slots — an off-lane card past rank 3000 and the deep lane's least-played
  half (never a Granter), traded by a last-ranked `upgrade` issue for a
  better-played card at no higher mana-value band doing the same job (223
  swaps, 104 cuts and 29 adds matching a guide, from 85 / 44 / 8); every theme
  add is the most-played candidate that fits; an Equipment's, Aura's or
  target's shrink and damage to each player are not board wipes; the main
  theme no longer changes with the string-hash seed. Fixed in the eighth pass
  (2026-10-19): the interaction search combined its five presets with AND and
  sourced nothing (no removal fill or upgrade since the fourth pass) — it reads
  any of them now; job reads (`_analysis/job_quality/`, ADR-0060) gate which
  cards may be an upgrade and, for wipes / draw, order them blended with
  play-rate, so a looter is no draw upgrade and Animate Dead no removal; overload spells are
  sweeps (`crosswalk.overload_sweep`, a retirement canary). Left:
  (a) **Inside a lane, the cut read is "a feeder nobody plays" — don't
  re-suggest a function read.** Measured 2026-10-18 on the 25 precons' main
  lanes (906 lane cards, 222 guide cuts, base rate 0.245): no function
  feature moved the rate — one-shot vs repeatable 0.19, body for its cost
  0.27-0.32, in-deck synergy depth (`rank_candidates` over the deck's own
  cards) flat 0.22-0.25 across quartiles, lanes touched 0.14-0.28. Play-rate
  does (least-played quarter 0.35), and "a member that does not itself care
  about the lane" more so (0.32 vs carers 0.20; rank-bottom-quarter feeders
  0.46; a feeder with no template role past rank 8000: 0.67, n=24). The
  `lane_upgrade` tier now orders feeders before carers, then least played
  (top-five precision 0.48; costlier-first within the half was 0.30). The
  guides' stated reasons (one-shot, delirium type, curve) are not what their
  cuts share, and the same holds for the flip-quality read the polymorph tune
  wanted. Script: `docs/plans/precon-audit/lane_quality.py` (rerun recipe in
  `docs/plans/precon-audit-2026-10-18.md`).
  (b) **Lane verdicts — don't re-suggest** (the leftovers closed 2026-10-23).
  The `animate_artifact` regex lane retired for `animate_makers` drops 24
  cards with no replacement by design: 19 Vehicles, 2 artifacts that animate
  only themselves, 2 copy effects (Saheeli, Sublime Artificer; True
  Polymorph). A token maker is a doer — `artifacts_matter|you|token` /
  `enchantments_matter|you|token` (Roles, Glimmers), never the bare payoff;
  an artifact or enchantment card keeps the LOW membership-floor key. In Too
  Deep is no `clue_makers`: the Clue it makes is the enchanted permanent's
  controller's. The superfriends synth arm stands down on a card naming
  planeswalkers only as half of a bare "creature or planeswalker" and never
  their loyalty (`crosswalk.planeswalkers_only_beside_creatures` — Angelic
  Intervention, Kaya's Ghostform, Fey Steed and six more), so Spark Double
  (an extra loyalty counter) and Lae'zel (no typed planeswalker filter) keep
  it.
  (d) **Type payoffs — don't re-suggest** (2026-10-25). A choice of types
  ("creature or artifact you control" — Abuelo, Heliod, Zimone), stax or edicts
  over other players' artifacts (Null Rod, Harsh Mentor, Pick Your Poison), a
  count another player wins (Ward of Bones' lock on each opponent with more
  artifacts than you, `crosswalk.counts_behind_another_player`) and a retype
  that also strips abilities (Sugar Coat, Kitesail Larcenist, Vraska,
  Betrayal's Sting, Soul Sculptor: removal) are no payoff. The type-grant read
  (`crosswalk.granted_card_types`) has no node for Xathrid Gorgon's dropped
  "becomes a colorless artifact" or the Alchemy perpetual grants (Hinterland
  Chef, Resourceful Collector, Woodland Investigation, Glimmer Hoarder,
  Housemeld); none is an artifacts or enchantments payoff a guide plays.
  (g) **The guide cuts the tuner protects** (2026-10-24, the experiment table in
  `docs/plans/precon-audit-2026-10-18.md`, "The remaining tuner levers"). Shipped:
  popular cards (inside `UPGRADE_RANK`, not premium) off every lane and on none of
  the deck's main avenues are the last upgrade tier (`focus.popular_upgrade_cards`,
  after the deep lane's half; the guides cut 0.28 of them, 27 of 96, when any viable
  avenue spared a card; beside the fringe tier they spent the lane's theme budget,
  51 adds). Since 2026-10-25 only a main shields an off-lane card from the upgrade
  tiers (a sub's or an emerging or folded theme's carer is a slot, and a popular
  card on a sub alone; the audit's "The cut pool"); keeping a folded theme's
  carers shielded lost five guide cuts. Since 2026-10-26 (the audit's "The open
  levers, closed") a main shields only its carers (a popular main feeder is the
  last slot), a solid Granter is a slot and may go to a better grant (ADR-0040's
  amendment). Left: 23 popular cuts, all premium (the guides cut 0.10 of premium
  cards, 22 of 210 — premium stays), and 45 commander-lane doers, whose guide-cut
  rate outside the lane's half is 0.08-0.20 in every carer split by role and
  play-rate holding more than four cards, below the decks' 0.24 — (a) holds,
  don't re-suggest a split of them without a new read; most sit in tunes that
  reach the thirty swaps. Combo protection stays whole: only a game-ending combo
  protecting its pieces lost an add, and `proposal-check` gates every infinite.
  Script: `docs/plans/precon-audit/cut_splits.py` (both splits; same ROOT as
  `misses.py`).
  (j) **Job-read verdicts — don't re-suggest without a new read** (ADR-0060 and
  its amendments; the experiment tables are the audit's "The tuner-policy
  leftovers" and "The deck-fit wipe read"). The order is the blend (wipes, draw,
  protection) or play-rate (removal, ramp), theme fit breaking a near tie for draw
  and ramp. The wipe read leading its upgrades was flat twice (547 / 195 / 60): it
  moves picks only in precons whose guides add no wipe. The deck-fit wipe read was
  built and measured 2026-10-25 (the share of the deck's own permanents a sweep
  leaves, off its filter: a chosen type, a power or mana-value bound, one each,
  one-sidedness, damage against toughness): the deck-free read already prices a
  spare and one-sidedness at the average deck's board, so on its own it moves no
  non-tribal deck, and leading the wipe order and fill with it in a tribal deck
  (most creatures share a type: Fae Dominion, Blood Rites, Sliver Swarm,
  VelociRampTor) took Raise the Palisade in Fae Dominion but cost three guide adds
  there on the budget (guide adds 18 → 16 over those four, cuts flat): rejected.
  Expel the Interlopers and Tragic Arrogance under Ellivere, and Chain Reaction
  and Winds of Abandon in Blame Game, need a slot the tune doesn't open (one wipe
  upgrade each, already Vanquish the Horde / Blasphemous Act, both guide adds);
  a lead for every deck trades those away. Rejected for removal: the deck's count
  of instant any-permanent answers deciding flexible vs targeted (59 and 56 adds;
  Beast Within's recurrence moved to Abrade). Rejected for ramp: the read blended
  into the order (56; Mana Vault took Fellwar Stone's 10). The removal read's weak
  agreement with play-rate over every card with a removal effect stands (it was
  fitted on main-job removal and only gates). Theme fit as a tie lost for removal,
  wipes and protection. Protection goes unsearched in 18 guide adds' decks because
  ADR-0024 asks for it only from a combo or control deck or a voltron plan; a
  target of 5 or 3 for every shape matched fewer adds. Left narrow, none a guide
  card: a size off a card the caster takes from a graveyard (Volcanic Vision, Too
  Greedily, Too Deep) or off a random discard (Kindle the Carnage). An on-theme
  draw or ramp card reading within a tie of its cut passing the play-rate gate
  gained none of its targets (Insidious Roots, Faerie Mastermind; 2026-10-26).
  Where the deck holds the most of a job it wants (a row at its max, protection
  at the Shape's target) the job's upgrade moves onto the theme (2026-10-26); a
  looser row read or cost bar spent the budget-bound decks' cuts.
  (k) **Age-adjusted play-rate — don't re-suggest** (2026-10-30; patch and runs in
  `~/mtg/tuner-work/w29/`). A card's rank as a percentile among cards first printed
  within ±6/12/24 months, the better of that and the raw rank, and a recent-only lag
  boost, each through the add order, fills, near-tie, play-rate gate, page sort or
  cut side: no variant raised guide adds on the 25 (best 108 against 109; the
  ordering variants lost 13-19, mostly old staples: Swiftfoot Boots, Counterspell,
  Nature's Lore). The "newer and less played" misses were mostly a dating error
  (MTGO's promo set dates every card 2002-06-24; The List and Secret Lair likewise);
  with reprint-aware dates a ±6-month cohort puts the guide card first in 5 of 151.
  Real rank lag is limited to 2025-26 cards, which mostly postdate the guides. A
  card's first printing is its earliest printing not flagged `reprint`
  (`precon-audit/scoreboard.py`).
  A recent-only boost also failed, scored fairly (2026-10-30; patch and runs in
  `~/mtg/tuner-work/w39/`, the audit's "A play-rate boost for recently printed
  cards"), against 732 / 335 / 121 (held-out 297 / 139 / 37, Jace 30 / 15 / 4). Cards
  first printed in the last 24 months, sized by how far their cohort's top 5% trails
  mature years: gate only 737 / 338 / 118, order only 734 / 335 / 112, both 738 / 338 /
  110, held-out adds 36 each. The fair line (cards a guide could name; `scoreboard.py`'s
  `FAIR`) falls too, 119 to 116 / 112 / 110, so the scoring wasn't hiding a win. On the
  19 decks with a guide dated since 2024-11, the boost matches at most 5 of the 55
  recent guide adds against the baseline's 4, while those decks' guide adds fall from 69
  to 65-67. Near tie only scored 122 and passes every gate, but through one reshuffle
  in one deck (Supreme Verdict, a 2012 card, for Flawless Maneuver) and no recent card;
  not shipped.
  (s) **Deck fit for job upgrades — don't re-suggest** (2026-10-30; patch and runs
  in `~/mtg/tuner-work/w31/`, the audit's "Deck fit for the job upgrades"). Two
  levers, each measured alone, then together; none raised guide adds on the 25.
  (3a) a job upgrade never cuts a card serving the main theme or the commander (a
  main's member or carer, a commander-lane doer, or a card sharing a non-generic
  ident with the commander): 611 / 281 / 97, every split of the set lost (shared
  ident only 672 / 314 / 103, carers and lane doers 684 / 317 / 101, main members
  634 / 292 / 98), because the guides cut those cards at 0.39 (57 of the 146
  protected job-upgrade cuts), above the decks' 0.24. Only two of the five
  motivating trades are theme cards by focus's sets (Vona, Chittering Witch);
  Stalking Leonin, Siege-Gang Lieutenant and Will of the Abzan share no
  non-generic ident with their commander and serve no main. (3b) a job's
  candidates (upgrade, Spine fill) that share a non-generic ident with the
  commander or a main's serve rank first, play-rate or the blend within each
  group: 710 / 324 / 91; per job removal 104, wipes 108, draw 107, ramp 104,
  protection 107 adds (109 base). Unlike (j)'s theme tie (fit breaks a 0.1
  job-read tie over the viable avenues) it reorders the whole match set, and the
  fit read is too loose: `attack_matters`, `combat_damage_to_opp` and
  `target_player_draws` tie Myr Battlesphere, Sword of Fire and Ice and
  Kozilek's Command to Nelly Borca, and the guides add the staples it pushes out
  (Swords and Path in Blame Game, Counterspell, Swiftfoot Boots, Heroic
  Intervention). A 5% pool-share cap on the shared idents (102) or fit only
  within tenfold of the top card's play-rate (102) lost too. The guides' deck-fit
  removal (Wall of Souls, Soul Shatter, Grasp of Fate) is played less than its
  cuts, so no order reaches it. The two misreads found on the way (Noxious
  Gearhulk's `toughness_combat`, Myr Battlesphere as removal) were fixed
  2026-10-30. A strong fit skipping the play-rate gate, with the order kept, also
  failed (2026-10-30; patch and runs in `~/mtg/tuner-work/w38/`, the audit's "A
  strong fit skipping the play-rate gate"): the gate isn't what holds these adds
  out. Under a play-rate order a less-played candidate is reached only when nothing
  more played passes the other gates. With the gate off for every job candidate:
  727 / 333 / 117, no guide add gained. With it off for the deck's guide cards
  alone, the ceiling for any fit read: 119 adds on the 25 (Elemental Bond,
  Overgrowth), 38 held-out (Brass's Bounty), and none of the three shares a
  non-generic ident with its commander beyond `permanent_etb`. Every fit read
  scored 117 adds and 37 held-out. Wall of Souls, Soul Shatter, Grasp of Fate, Rip
  Apart and Blazing Sunsteel share none either, so no commander-fit read names
  them. Don't re-suggest a gate change for job adds without a new order, which (s)
  and (t) already lost on.
  (t) **Card reads leading the theme adds — don't re-suggest** (2026-10-30;
  patch and runs in `~/mtg/tuner-work/w33/`, the audit's "Card reads leading the
  theme adds"). Measured against 715 / 329 / 114 (held-out 297 / 139 / 35, Jace
  29 / 14 / 3). Order A (fit to the commander, a non-generic ident shared with
  it; then `rank_candidates`' synergy; then play-rate) over the whole match set:
  723 / 331 / 82, held-out 30 adds, 2.3× the tune time. Order B (commander fit,
  then how many deck cards emit one of the candidate's non-generic idents, then
  play-rate) over the whole match set: 740 / 335 / 80, held-out 30. Each reaches
  about 22 unpopular guide adds (Gix, Krydle, Djeru, Teferi, Temporal Pilgrim,
  Conduit of Ruin) and loses about 55 popular ones. The 150-card page, the
  synergy rounded to whole points, a log-depth, a 5% pool-share cap and tiered
  forms (fit, then the 0.2 fit floor; fit, then 15+ deck sharers) scored 87-111.
  Blends in log10 play-rate (fit worth 0.1-0.5 decades, a depth doubling up to
  0.2, synergy share 0.47, weights from a logistic fit) scored 109-116 adds. The
  best, fit worth 0.25 decades, scored 725 / 332 / 116 with held-out 38, but Jace
  fell to 1 add (it lost Archfiend of Depravity and Nezahal). No variant passed
  all three bars. Inside a play-rate band, fit (2-3×) and 31+ deck sharers (2-5×)
  do raise the guide-add rate on the whole match sets, but play-rate separates
  more: rank ≤ 1000 runs 5.4% against 0.07% past 15,000. Found on the way:
  dropping the theme page's 0.2 synergy fit floor, with play-rate alone and no
  read, scored 720 / 331 / 118, held-out 290 / 139 / 36, Jace 29 / 14 / 3. By
  the user's decision it was tested again after the phase v0.118.0 bump, on top
  of the token doublers ((u)), and shipped (the audit's "Dropping the theme
  page's fit floor"): 718 / 333 / 118 against 722 / 332 / 115, held-out 290 /
  139 / 37 against 36, Jace unchanged. A Commander-family theme page is now
  play-rate, then price; don't re-suggest a synergy floor on it.
  (u) **The other side of a maker lane, the commander's own mechanics — don't
  re-suggest the rejected forms** (2026-10-30; patches and runs in
  `~/mtg/tuner-work/w34/`, the audit's "The other side of a maker lane, and the
  commander's own mechanics"). Shipped: the token doublers page, one theme add,
  under a commander that makes tokens or Clues, Treasures, Food or Blood
  (`Sourcing.multiplier_avenue`; on the phase v0.118.0 pin 722 / 332 / 115,
  held-out 297 / 139 / 36, Jace unchanged; 720 / 329 / 116 on v0.104.0).
  Rejected: opening it by deck density (5+ makers: 109 adds, Jace 1;
  the commander's or 12+: 114, Jace 1); two adds off it (115); the other
  multiplier sub-avenues (counter and ETB-trigger doublers, trigger copiers,
  damage and mana amplifiers) on the same terms (116-117 on the 25, held-out 31);
  every sub-avenue made only of a held doer's payoff keys (114, held-out 33). 4c,
  the commander's own non-viable lanes sharing the theme adds off its exact-ident
  page, differs from (r)'s rule in page and purse and still fails: 112 adds, or
  116 held to one lane per deck but held-out 34. (A note here once said phase
  misreads Parallel Lives as doubling every token; it does — "If an effect would
  create one or more tokens under your control, it creates twice that many",
  checked 2026-10-31 — so `crosswalk.token_doubler_kinds` is right to keep it
  under a Clue commander.)
  (v) **A polymorph's flip targets skip the mana-value band — don't
  re-suggest without a new order** (2026-10-30; patch
  `~/mtg/tuner-work/w26/flip-band.patch`, runs in `~/mtg/tuner-work/w36/`).
  Under a commander that `wants_fodder`, a creature or planeswalker card its
  `cheat_into_play` reveals for (Jace, Multiverse Architect's -3) skipped
  `over_band`: the commander puts it onto the battlefield, so its mana cost is
  never paid (CR 601.2f-h pay a spell's cost as it is cast). Jace is the only
  polymorph deck, so the 25 move only through Jace. Before the phase v0.118.0
  bump it lost Nezahal, Primal Tide (Jace adds 3 → 2). Re-tested on top of the
  token doublers and the dropped fit floor, it lost Nezahal again: Jace 30 / 14
  / 2 against 29 / 14 / 3, the 25 719 / 333 / 117 against 718 / 333 / 118.
  Play-rate fills the opened slots with the big creatures the band held back
  (Grave Titan, Artisan of Kozilek, Scourge of the Throne, Gisela, Blade of
  Goldnight, Combustible Gearhulk), and Nezahal is outranked on its page.
  (w) **Polymorph fodder — don't re-suggest the rejected forms** (2026-10-30;
  runs and `experiment.patch` in `~/mtg/tuner-work/w37/`, the audit's "Polymorph
  fodder and the purse cap"). Shipped then: a polymorph commander's trim adds
  fodder (`Sourcing.fodder_trim_spec`); its fodder maker's job upgrade must
  make fodder too; past the even share, no upgrade's add takes more than 0.6 of
  what is left (`swaps._PURSE_CAP`, every deck). Jace 30 / 15 / 4. Rejected: the
  lane sharing the theme adds as a sub (Loyal Apprentice or Raise the Alarm, but
  Archfiend of Depravity lost every time); the lane's whole page for the trims in
  play-rate order (30 / 15 / 3).
  **Rewritten 2026-11-01 on Dan's Jace tune, by his call, not the guide score**
  (the tune he saw: ten two- and three-mana creature cards added as "Polymorph
  fodder" beside eleven bombs cut, and the trims one-shot token spells — Dragon
  Fodder, Krenko's Command, Raise the Alarm, Frontline Rush). Jace's -3 reveals
  until a creature or planeswalker card, so every creature card in the library
  is a flip. Shipped: (1) the fodder serve (`signal_specs` `wants_fodder`) admits
  a creature card only when its token comes every turn
  (`card_reads.makes_tokens_repeatedly` over `crosswalk.unit_repeats`); (2) the
  fodder page orders repeatable makers first, noncreature before creature, the
  one-shots last (`issues._fodder_lead`, the spec's `_lead` in
  `swaps._ranked_pool`), and the trim page IS the fodder page (the two-mana
  instants-and-sorceries page is gone); (3) under a polymorph commander a
  creature or planeswalker add below the deck's flip floor (one band under its
  median flip, `swaps.flip_floor_band`) is a whiff unless it is fodder, and a
  fodder flip only while the flips under the floor stay one in four
  (`swaps._WHIFF_SHARE`); (4) a flip with no job that is no fodder is upgraded
  on the flips' page, the commander's typed cheat avenue held to flips
  (`Sourcing.flip_spec`: every typed cheat avenue as one serve, a five-power
  body or a planeswalker; "upgrade a flip: …"), and so is a flip WITH a job
  while its row is in band or over (Niv-Mizzet's draw, Ob Nixilis's wipe); a
  short row keeps the job page — the guides swap the Jace precon's bombs for
  better bombs and call its creature count thin. Multiverse Reforged's guide
  score before: 30 / 16 / 4 (Swiftfoot Boots, Loyal Apprentice, Raise the Alarm,
  Tempt with Bunnies); after: 30 / 16 / 1 (the one-shots and Loyal Apprentice
  now sort behind the repeatable non-flip makers). Left: Currency Converter
  still goes as a ramp trim, since the rest of that row is fixing.
  (m) **Recall** (`precon-audit/misses.py`, at the largest guide's thirty
  swaps and each precon's own guides' budget, `budgets.json`, Spellbook cached):
  335 of 505 cuttable guide cuts, 121 of 793 in-scope guide adds, 732 swaps;
  held-out 139 of 216 / 37 of 407, 297 swaps (2026-10-30, polymorph fodder and the
  purse cap, (w): near-misses 63 / 30, consensus adds 38 / 6, Jace 30 / 15 / 4.
  Before it 332 / 117, 720 swaps; held-out 139 / 37, 290 swaps, Fynn's fixes,
  `real-deck-validation.md`: poison closers, the fed-only lane exemption,
  front-face keywords, the attacked defender as no removal, the trim's band;
  Mardu Surge lost Professional Face-Breaker, Virtue and Valor a guide cut;
  Jace 29 / 14 / 3. Before it 333 / 118, 718 swaps; held-out 139 / 37, 290
  swaps, the theme page's fit floor dropped, (t): Animated Army's Chimil, Death Toll's and Graveyard
  Overdrive's Buried Alive, Living Energy's Conversion Apparatus, Virtue and
  Valor's Sram; Lorehold Spirit's Crucible of Worlds and Underworld Breach;
  near-misses 61 / 30, consensus adds 39 / 6, Jace 29 / 14 / 3. Before it 332 /
  115, 722 swaps; held-out 139 / 36, 297 swaps, the token doublers
  under a token-making commander, (u): Deep Clue Sea's and Squirreled Away's
  Primal Vigor, Lorehold Spirit's Anointed Procession, Tinker Time's Liquimetal
  Torque becomes Big Score, Planeswalker Party's Supreme Verdict lost to Bard,
  King of Dale; near-misses 71 / 29, consensus adds 40 / 6, Jace 29 / 14 / 3.
  Before it 332 / 114, 717 swaps; held-out 139 / 35, 297 swaps, the phase
  v0.118.0 pin bump, same day: Planeswalker Party one guide cut more, Sliver Swarm two more swaps and
  two guide cuts more; near-misses 70 / 29, consensus 39 / 121 and 6 / 37, Jace
  29 / 14 / 3, all as before. Before it 329 / 114, 715 swaps; held-out 139 /
  35, 297 swaps (2026-10-30, the signal-gap pass:
  Sundial of the Infinite in all four guide decks, Graveyard Overdrive's Six,
  Tarmogoyf and Terravore; Mardu Surge's Sundial spends the budget its last five
  upgrades had, one guide cut fewer; Jace unchanged. Before it 330 / 109, 721
  swaps; held-out 139 / 34). The scoreboard
  (`precon-audit/scoreboard.py`, the audit's "The scoreboard", 2026-10-30) adds
  two reported numbers, not gates: near-misses (a tuner add standing in for a
  missed guide add by job subtype or shared deck signal; 13 of 20 sampled pairs
  held up by the rules) 61 on the 25 (71 before the fit floor was dropped), 30
  held-out, 2 on Jace; consensus guide cards (named by 2+ guides) matched, adds
  39 of 137 / cuts 121 of 169 on the 25 (40 adds before the fit floor was
  dropped), 6 of 52 / 37 of 53 held-out, Jace 0 of 2 / 7 of 10. (The baseline is
  from 2026-10-29, after the guide-row fix: 108 rows that joined cards with commas or misspelled them now name real
  cards, and the audit scripts no longer split "Dusk // Dawn" at its second
  slash; the larger add counts raise 14 precons' budgets. Before it, on the old
  rows: 271 of 408 cuttable guide cuts, 88 of 610 in-scope guide adds,
  713 swaps (2026-10-26, the audit's "The open levers, closed": solid
  Granters and a main's popular feeders are upgrade slots, a Spine fill takes a
  jobless slot before a lane slot, a full job's upgrade moves onto the theme;
  271 / 88, 713 swaps again, every swap of the 25 precons the same, once a
  lifelink body kept the voltron carrier, 2026-10-29: 66 cards gained it, none
  legendary — the held-out ten likewise, 139 / 34, 297 swaps, every swap the
  same; 256 / 76, 680 swaps before the open levers, unchanged by the
  fourth and fifth (o) passes; 252 / 75, 669 swaps before the third (o) pass;
  199 / 67, 562 swaps before the cut pool; 197 / 66, 560 swaps at the even share;
  195 / 59, 543 swaps before it; 180 / 57 before the near-tie budget rule, 169 / 56
  at 9e0026ed.) The levers by size now: adds a page held but outranked
  (235, from 251 by the full-job move; no read separates the rest), theme adds no search reaches (164, (r)), guide cuts in a cut pool
  the tune never reaches (50: seventeen tunes reach thirty swaps, six
  end on their budget, two on their cut pool — Blood Rites, its lane all Vampires,
  and Sliver Swarm), commander-lane cards the guides trim (45, (g)), premium cuts
  (23, (g)) and protected ones (13). 49 guide adds are gated as fewer
  played than their cut and 31 as a band higher: a theme upgrade of a
  main card letting a near tie in play-rate through when it fits better lost two
  adds, and a band more where the curve has room was flat (2026-10-26). Taking
  the popular tier before the lane's carers cut four more guide cards but lost two
  adds: the carers' slots bring the lane's theme adds. The outranked adds, by what beat
  them (`find_add` traced, 2026-10-25, before the even share): theme pages 122 (91
  behind a more-played pick, 17 ahead of it but passed over for a cheaper near
  tie, 8 on a page that picked nothing), removal 37, ramp 26, draw 21, protection
  16, wipes 6. No card read separates them from the picks: a commander pair read
  (ADR-0042's rows) fires on 8.0% of the theme pages' guide adds and 7.3% of the
  rest, a template role on 31% of the outranked guide adds and 28% of the theme
  picks; the top fifth of a page's synergy holds guide adds at twice the rate,
  which the synergy orderings below already lost on. Measured negative, so don't
  re-suggest without a new read: theme adds serving two viable avenues first (46
  adds), theme adds by a synergy / play-rate blend (53), and, against the even
  share's experiments (the audit's "The budget's even share"): a theme page's near
  tie to the better fit where the budget doesn't bind (58), the even share on the
  guarded Spine fills (one add fewer), and the cheapest card in the window, near
  tie or not, past the share (adds flat, one cut more); and, against the cut
  pool's: a lane feeder's theme upgrade to a less-played payoff of the main lane
  (one add fewer), an over-band trim's add shared over the mains (flat).
  Six guide summaries don't tag sources per row (`guide_sizes.py` skips them).
  (r) **Theme reach, what's left** (2026-10-25; the experiment table is in
  `docs/plans/precon-audit-2026-10-18.md`, "Theme reach"; unchanged by the
  2026-10-26 pass, which found no new read for it). 164 theme guide adds
  still have no search. Both levers measured and closed (2026-11-01):
  - the 150-card play-rate page (`swaps._PAGE`), which hid 71 main-avenue guide
    adds at a913f172 (Blood Rites' Lich-Knights' Conquest carries
    `sacrifice_outlets|you|`, which the Aristocrats serve counts, but the page
    doesn't hold it). The whole match set as the page gained nothing at twice
    the tune time (below); reordering the page by the card reads (V1, 2026-10-30;
    V3 reads-first and V3b blended with the theme-strength reads, 2026-10-31)
    failed the gate every time — held-out plan +69 / adds −12 for V3, plan +5 /
    the 25 adds −8 for V3b; retested 2026-11-01 under the lowered bar (0.65 on
    the adds-vs-cuts pairs alone) and failed again — V3 held-out adds −12, V3b
    plan +9 with the 25 adds −8. Don't re-suggest a page depth or order change
    (the audit's "The theme-strength reads and the V3 order");
  - four guide adds serve only a sub (Living Energy's Arcum Dagsson, Clever
    Impersonator, Scrap Welder; Deep Clue Sea's Displaced Dinosaurs). Sharing the
    theme adds over the commander's held subs as well as the mains took Roaming
    Throne and Praetor's Grasp but lost eight guide adds elsewhere (2026-10-25,
    the audit's "The cut pool"), as every sub sharing did; sub and emerging
    lanes paged after the mains (S-A, 2026-10-31) lost 24 adds on the 25 and 14
    held-out (the audit's "Sub-theme pages"). Don't re-suggest a sub share.
  The guide adds that serve only a lane that isn't viable — don't re-suggest
  without a new read (2026-10-25): of those no search reaches, 54 serve only a
  fed lane (Spellslinger, Artifacts, Cost reduction: incidental keys, mostly
  staples and protection) and 4 an emerging one; 14 more on an emerging lane are
  outranked. The guides cut the carers of an emerging or folded theme (22 of 52
  past `UPGRADE_RANK`) more than they commit to one, so "commit more" is no
  lever; the tune now trades those carers as upgrade slots.
  An Aura deck's gear apart from Equipment (Ellivere counts enchanted creatures;
  an Aura makes one, CR 303.4b; Equipment an "equipped" one, 301.5a) was
  simulated before building the read: Auras only on Virtue and Valor's suit-up
  page took Sram and lost Swiftfoot Boots and Lightning Greaves, the guide adds
  that page makes (one add fewer) — don't build it without a new read.
  Measured deltas: a granted "When this creature dies, <payoff>" read as
  `death_matters|you` alone moved no swap (543 / 195 / 60); a held lane as deep
  as a main never folding into a held tribe added Blood Rites' Skullclamp (544 /
  196 / 62; 542 / 195 / 61 after the near-miss piece fix); Ancestral Mask's count
  of every player's enchantments read as an enchantments carer keeps it in Virtue
  and Valor, and its slot moves Sram and All That Glitters off the adds (543 /
  196 / 59). Measured negative, so don't re-suggest without a new read: payoffs
  first (47 guide adds over the serve's whole match set, 44 over the 150-card
  page, against 50: the payoffs cost more and spend small budgets); the whole
  match set as the theme page (no gain, twice the tune time); support at one in
  three or more (generic tribal support takes the members' budget); slots shared
  over every viable avenue (35) or by carers (45), because the generic subs'
  pages hold staples (Murder for Fae Dominion's Spellslinger); one swap off the
  serve page for each lane below the viable floor that the commander holds and
  cares about (58 adds; 60 held to the emerging floor, flat); a sub with a
  main's carers taking one add that also serves a main (57 adds, 2 guide cuts
  fewer).
  (n) **Lane follow-up verdicts — don't re-suggest without a card** (2026-10-24:
  a targeted Treasure conversion is no `ramp` — Vraska, Betrayal's Sting's −2,
  Kitesail Larcenist answer the target, whose controller keeps it, CR 110.2 /
  602.2). Checked and empty on the 2026-10-23 corpus: a card with both a creature-type and a card-type Choose firing
  `chosen_type_matters` (none), and a discard or leaves-the-battlefield
  trigger's self-return firing `bounce_tempo` (none; the other trigger
  back-references on cards that fire return an event object — a blocked
  creature, a damage source, a land tapped for mana).
  (o) **Theme matching off the IR, what's left** (2026-10-25, after the third
  pass: the tribe spec and its payoff sub-avenue page off the IR too; the
  fourth and fifth (2026-10-26) took the pattern off every keyword tribe —
  ``text_reads._ABILITY_KEYWORDS``, first and double strike now among them; the
  class of every card the tribe pages lost is in
  ``~/mtg/tuner-work/w16/classification-tribes.tsv``, the keyword pages' in
  ``~/mtg/tuner-work/w18/classification-keywords.tsv`` (flying … hexproof, 445
  cards) and ``~/mtg/tuner-work/w19/classification-keywords2.tsv`` (the rest,
  281 cards), the second pass's in ``~/mtg/tuner-work/w13/classification-final.tsv``).
  A theme pages by its serve (``signal_specs.theme_page``); no search carries an
  oracle pattern (``test_a_theme_pages_by_its_serve_not_a_pattern``). The tribe
  pages were checked on every tribe (2026-10-31, the audit's "The tribe pages,
  every tribe"; `~/mtg/tuner-work/w41/tribe-pages-sweep.tsv`): 151 tribes, no
  member lost to a phase drop; 57 memberships are back-face-only and stay off by
  the front-face rule; the one false admission (Urza's Power Plant on the Plant
  page, a hyphenated subtype split in two) and Vecna's related token on the
  Zombie and God pages were fixed in the two lane passes (f150c80b, e375dd46).
  The page-only keys (``signal_keys.PAGE_ONLY_KEYS``: ``subtype_ref``,
  ``keyword_bodies`` and ``land_return_untap``, the Forest-bounce untap engines
  split off ``permanent_etb``) feed a theme's page and open no avenue or plan
  (``signal_keys.is_page_only``).
  A card phase has no record for carries no ident at all, so it drops off a
  pattern-free page: of the permanents-entering makers, Oko, Lord of the Fae;
  Flourishing Forces; Enter the Eternities; Quintorius, Fate Splitter; Potential
  Horizon; Searing Soloist; Plunderer's Prize; of the token makers and counter
  placers, the same Oko, Flourishing Forces and Quintorius; Rootha, Ardent
  Artisan (sacrifice outlets); Change the Narrative (cost reducers); Nylea's
  Oracle (go-wide anthems); Avoided Stairwurm (Enlist fodder, Ability-strip
  targets). The ledger rows that gate on a node's absence (Estrid's
  Invocation, both rows; Venture Forth; Hide in Plain Sight; the
  typeless reanimations; the dropped return costs; Catastrophe's creature
  branch; the where-X player burns; Commence the Endgame's amass; Widespread
  Brutality's Army bite; Jin Sakai's modes) retire only through
  ``test_bridge_ledger``'s "already served" guard, not their own gap.
  Rules that stand: serves were written to credit a deck's own cards, so each
  OR arm admits a card on its own; ``tests/deck-forge/test_serve_arm_guards.py``
  pins each structured arm on a page serve to a real card and a near miss, and a
  new arm needs a row. An IR hit whose emitting unit decides no role
  (``ranking._unit_role``) is read by lining the unit's text up with an oracle
  clause, then that clause with a compat ability (``ranking._hit_clauses``):
  reading the payoff test off the unit itself would drop both text alignments,
  and would give a role to the hits no single ability emits (a keyword's
  lifelink, Crucible of Worlds' whole-card ident, a modal spell's text-less
  mode), which still score structural.
  What the keyword pages dropped (2026-10-26, each class rules-checked): a card
  naming the keyword to fight it (a removal or block rider, "without", "loses",
  flying's reminder "except by creatures with flying or reach" on the reach page,
  CR 702.9b); "as though it had flash" or "… didn't have defender" adds no
  ability (CR 113.10: an added ability "gains" or "has" it — 74 flash enablers),
  though a static letting other creatures attack as though they didn't have
  defender is a defender payoff (``crosswalk.lets_defenders_attack``, CR
  702.3b — High Alert; a creature letting only itself attack, Backstreet
  Bruiser, is not); shroud or hexproof on a player (CR 702.18a / 702.11c); a
  grant of defender onto another creature, yours or not (Guard Duty, Stasis
  Field; Peregrine Mask, Dormant Sliver) is the drawback ``_DRAWBACK_GRANT_KW``
  names, where a body with defender the card is or makes counts
  (``crosswalk.made_keyword_bodies``: a Wall token, Primal Clay, Guardian
  Zendikon's land); a Vibranium token is a noncreature artifact (no body); a
  keyword-variety payoff (Akroma, Vision of Ixidor; Odric, Blood-Cursed) or a
  keyword-sorting dig (Selective Adaptation) is no one keyword's; a card or
  ability name (Fear Ray, Shadow the Hedgehog, Undying Flames). A keyword tutor
  of your own library pages its keyword (Mystical Teachings, Isperia,
  Mwonvuli Beast Tracker). A token any player may create is no body the card
  makes for you (Basalt Golem's Wall is the blocker's controller's, CR 111.2).
  Don't re-suggest: an enters drawback (Phage, the sacrifice-unless lands), an
  Equipment's auto-attach, a token or search another player gets (the Hunted
  cycle, gift, Path to Exile) and a card putting only itself are no
  permanents-entering member; the Emergence Auras' "that land gains
  indestructible" replacement (CR 614.1a) guards only the land they animate,
  the animator's own payoff like Kamahl's Will, not land protection; an
  untargeted edict ("each opponent sacrifices" — Liliana's Triumph, Grave Pact)
  commits no crime (CR 700.13: a crime targets); a land-creature anthem or
  token maker (Sylvan Advocate, Jyoti) and a land already a creature (Dryad
  Arbor) animate no land, so the land-animation preset leaves them out (13
  cards); a coin-flip-gated self-exile-and-return (Frenetic Sliver) is a blink
  though the effect walk drops it as the card's own drawback, but one returning
  the card transformed (Ral, Monsoon Mage) is the transform vehicle. What the
  second pass dropped from the pages, each class adjudicated: an upkeep "sacrifice
  it unless you pay" is the card's restriction (``self_drawback|you|restriction``),
  not harm a donate deck hands over (76 cards), and a pact, an extra-turn spell
  or another instant or sorcery is no permanent to donate; a self-mill on a card
  that reads its graveyard is fuel (Splinterfright, Sidisi), not harm; a payoff
  for damage dealt to you, a Phyrexian Arena's paid draw and a curse on another
  permanent are no drawback; a creature that untaps only itself, a
  {Q} cost, a threaten's untap and a "doesn't untap" static are no untap effect
  (294 cards); a debuff Aura ("enchanted creature gets -N/-N") is removal, and
  an Equipment payoff or equip-cost reducer is ``voltron_matters``' page, not
  gear; a creature giving itself double strike, and "that much damage" counting
  something other than damage dealt, amplify nothing; a symmetric draw, token,
  tutor or Food is no symmetric mana; a sacrifice-cost drain (Anje, Glass-Cast
  Heart) is the aristocrats outlet, not a token-leaves drain, and a drain on the
  token a card makes is that token's; a curse watching its enchanted player's
  creatures enter punishes them, not a creature-ETB payoff of yours. What the
  third pass dropped from the tribe pages (``/rules-lawyer``, 2026-10-25): a
  protection from the tribe guards its holder (CR 702.16b/e); a targeted
  removal (CR 115.1) that can't hit the tribe spares no board (Victim of
  Night), while an untargeted mass effect (CR 115.10) or an every-player edict
  that leaves the tribe out rewards a board of it — the lane's call (Eyeblight
  Massacre, Kindred Dominance, Call to the Grave) — and pages on both the
  tribe and its payoffs; a Siege's
  "Dragons" is an anchor word with no tie to the type (its ruling, CR 607.2m);
  a party counts one Wizard (CR 700.8); a four-material craft (Throne of the
  Grim Captain, CR 702.167a), a named card (conjured, tutored) and an
  opponent's tokens of the tribe are no tribe's; a token maker of the tribe
  is its main page's, not a payoff. Merging ``creature_etb|you|punish`` into
  ``typed_enters_punish`` doesn't hold: 17 cards carry both, but each keeps
  cards the other rightly lacks (a landfall or artifact-entering burn there; a
  drain or a creature-entering burn here), and the ETB-payoff page reads both.
  (l) **Tune speed, what's left** (2026-10-26, after the third speed pass: a
  warm Blood Rites / Eldrazi Unbound / Sliver Swarm `deck-tune` 2.3-2.6 /
  2.5-2.9 / 3.1-3.5 → 1.7-2.0 / 2.0 / 2.1 s; the 25 precons' warm tunes, each a
  fresh process, 2.04 / 2.49 → 1.66 / 2.02 s median / max; the precon audit 23 s
  warm, 1.25 GB peak, its output identical). Settled 2026-10-31 late night: a
  warm thirty-swap tune reads 2.8 / 2.8 / 3.0 s on those three decks after the
  need pages, the quality and strength reads and the multiplier need (which cost
  1.5-3 s until its signal-key gate and per-commander memo); the swap phase's
  page scans remain the cost, and no further speed pass is planned — re-open on
  a warm tune past 5 s. Before that: the CLI is now Spellbook's:
  it asks at 0.4 s (after the deck's names: `acquire_for_cli` loads the pool
  index, 0.3 s) and the answer lands at 1.1-1.7 s, while the deck reads are done
  by 1.0 s — what's left behind the answer is the swap phase (0.5 s), whose page
  scans read every card of the gated slice once a page (~32k cards x 16 pages
  for a five-colour deck: 0.5 s; Blood Rites 0.2 s), each through one shared
  `CardView`; the per-card cost left is Python's (`_matches_card`, then
  `Serve.matches`' arms). Measured verdicts, don't re-suggest: **a Spellbook
  cache** — a cached answer can't equal a live one: 25 of 25 precon answers
  changed `popularity` / `prices` within 40 h (popularity orders the near-misses
  and is in the output), `find-my-combos` sends no ETag or version, and the bulk
  export's ETag dates the export, not the live database; so the CLI asks before
  it loads anything else (`deck_tune`), which took the wait off the warm CLI.
  **`is_wincon_card`'s trees** — 2-16 ms a warm tune, no builds (the trees store
  serves them). **The mirror classes** (0.28 s) — `mirror/__init__` no longer
  re-exports the loader, so nothing imports them before the first tree is built
  or unpickled: a CLI pays them inside Spellbook's wait, a tune still pays them;
  only a codegen emitting plain classes would cut them, and `dataclasses.fields`
  / `replace` read the nodes. **The crosswalk JSON** — read through a span index
  (`<sidecar>.spans.pkl`), 0.12 → 0.02 s. **The import-closure walks** used
  `find_spec`, which imported every parent (0.45 s, the mirror among them); they
  resolve names off `sys.modules` and the path finder now, once a process. **The
  two-face trees memo** — bulk-face reads have their own memo
  (`trees._BULK_TREES_MEMO`), so neither read depends on the order and
  `card_reads` / the store need no special case; the 25 precon tunes and the
  audit were unchanged by it. Earlier verdicts: the per-card reads in
  `_analysis/card_reads` stay beside the trees store — reading the four light
  ones (mana, gate, has-trees, self-return) live off stored trees cost a warm
  tune 0.1 / 0.5 / 0.4 s (Blood Rites / Eldrazi Unbound / Sliver Swarm); the
  trees store moves a warm tune by nothing measurable but a cold one, with no
  sidecars attached, by ~0.5 s of its ~1 s of builds; a stored tree carries none
  of the memos reads leave on its nodes (`crosswalk.reads.MEMO_ATTR_PREFIX`;
  `_owner_index` is keyed by node ids); a per-serve slice memo (no gain, two
  serve pages a tune); the collector off for the whole tune (a tune may start
  the signals index's whole-pool build, which makes ~50 cyclic objects a card —
  the tune collects at a 100,000 young threshold instead, measured as fast).

- **The tuner plan of 2026-10-30 and every lever measured after it — settled**
  (2026-10-30 to 31; `docs/plans/tuner-plan-2026-10-30.md` "Progress" and
  `docs/plans/precon-audit-2026-10-18.md` hold each run's numbers). Shipped: the
  commander-need read and its metrics, need pages by cut routing, the
  specificity-first primary, the wide need near tie, the deck-aware
  incidental-job read, the recursion / tutor / quality / theme-strength reads,
  the one instant-speed read, the `copy_ability` concept, the "multipliers of
  the commander" and "counters on the commander" needs, X costs, a Pact's
  payment, a tribal tutor's deck fit; land swaps opt-in. The gate is
  plan-primary (held-out plan-consistent adds ≥ +10; guide adds + job-equivalents
  ≥ −5; cuts ≥ −1; the 25 reported). Measured and held back, don't re-suggest
  without a NEW read: the incidental-job read as first specified, the marquee
  purse, removal-MV slots (C10 / D1 / D2); generic recursion and tutor rows (T1,
  plan −31) and the same rows gated on the plan (PR1, plan −30; patches
  `w41/rows-T1.patch`, `rows-PR1.patch`) — the guides' tutors and recursion are
  plan cards found on the plan's pages; reads-first theme orders S1 / S2 / V1 /
  V2 / V3 (plan +43 to +70, guide adds −12 to −22) and the play-rate + strength
  blend V3b (plan +5; patches `w41/theme-order-*.patch`) — the bar for a retest
  was 0.70 leave-one-deck-out on both pair sources (`w41/pairs-cuts.json`,
  `pairs-live.json`), lowered by Dan 2026-11-01 to 0.65 on adds-vs-cuts alone
  for ONE retest of each against N12: V3 held-out plan +71 but adds −12 and
  job-equivalents −4 (the 25 adds −4); V3b held-out plan +9, adds +1,
  job-equivalents −2, the 25 adds −8 (`w41/sb-*-V3r.json`, `sb-*-V3br.json`).
  **The reorder thread is closed:** no theme reorder by the card reads at any
  strength bar — the reads lift plan cards the guides don't play and the
  play-rate order keeps the guides' adds. Don't re-suggest; the job pages by read score (J1);
  per-source guide down-weighting (the 2026-10-30 plan's deferred item) is
  settled as "consensus reported, not weighted" (Dan, 2026-11-01): the scoreboard's
  consensus and near-miss columns are the view, and weighting the gate's adds
  mid-block would make every prior baseline incomparable;
  P1 / P2 / P3 and sub-theme pages (below). What the tutor and recursion reads
  still can't see is phase's, drafted in `docs/plans/phase-upstream-reports.md`
  (Rhystic Tutor, Grim Reminder, Cleansing Meditation, five unparsed returns,
  Necromancy's flash); by design they leave an ultimate's emblem search (Kaito,
  Garruk) and a self-return riding a made token's ability (Everquill Phoenix).
  The tutor read's six hand-set weights are set (Dan, 2026-10-31).
- **The no-search guide adds' four gaps — closed** (2026-10-30 to 31). Shipped:
  `end_step_sacrifice` and `end_the_turn|you|instant`, the `commander_keeps`
  issue (Sundial in all four guide decks), tutor subjects (`tutor|you|<card
  type>`), ability copiers no longer read as spell copiers (now the
  `copy_ability` concept), multipliers seeing a granted cascade, a paid tribe the
  commander isn't in kept apart from its lane. What stayed unpaged was measured
  and lost: Fabricate and Expedition Map sit on sub pages (sub-theme pages,
  S-A, above); Enlightened Tutor and Moonsilver Key are tutor-row fills (T1 and
  PR1, above); Call the Gatewatch and Firemind's Foresight sit past the 150-card
  page (P2, above). Don't re-suggest a page for them without a new read.
- **A fresh validation set exists and the block's gains hold on it (2026-11-01).**
  Ten never-used precon families with two or more guides each (Necron Dynasties,
  Explorers of the Deep, Tricky Terrain, Tyranid Swarm, Eldrazi Incursion, Family
  Matters, Food and Fellowship, Party Time, Call for Backup, Riders of Rohan;
  `~/mtg/tuner-work/fresh/root`, README there), built by the held-out method and
  never used to design a rule. Scored at N11 and at the block's end (N16): 295 swaps
  / 130 of 193 guide cuts / 38 of 386 guide adds both times, plan 119 → 120
  (`w41/sb-fresh-N11.json`, `sb-fresh-N16.json`): 67% of cuts and 9.8% of adds, the
  held-out 20's 63% and 9.9% at its first score. Use it as the generalization check
  at a block's end, never as a gate; a third set is not worth building until a
  policy passes the gate.
- **The never-admitted adds are triaged; what is left is the guides' own choices
  (2026-11-01).** `docs/plans/precon-audit/triage-2026-11-01.md`: 61 cards (the 84 less
  Ahoy Mateys' 13 and the 10 other tutors), one verdict each, every rules claim through
  the CLIs. 21 recall gaps fixed as reads in three passes (ending at c6552a3f, 8f7e7a1f,
  ec181037, f291a8c4): a token's `player_scope` and an effect for an answered
  target's controller or owner are the opponents' (`crosswalk.effect_actor_scope`,
  `acts_for_answered_target`, `effects_by_actor` — Skyclave Apparition, Spell
  Queller, Darkstar Banisher, Reality Shift, Unidentified Hovership); phase's
  record-level `casting_options` flash (`casts_as_though_flash`, 33 cards; the ledger
  row retired); an opponents'-draw count; the resource needs' missing consumers; a
  planeswalker commander's loyalty need; a commander's own `<type>_matter` trigger
  as a redundancy page; a cast trigger reading the spell's power; the counter-added
  need by counter kind; a commander's own combat-damage trigger asking for grants
  that reach it; a nontoken sacrifice trigger fed by no token maker; Dina's
  "sacrifice fodder with power 5+ at mana value 4 or less" (Kalakscion is a vanilla
  7/2); Mirrormind Crown's parked replacement as a ledger row. Re-based N13 → N15:
  held-out plan +28, guide adds −1 (Witherbloom's add to a near-miss under Dina's
  page), cuts −1; the 25 adds +3. 39 guide-specific: the first-principles ceiling
  (Panharmonicon and Elesh Norn multiply the copied creatures' ETBs, not Satya's
  trigger; Saradoc and Serra Redeemer trigger on face-down 2/2s, a pair read;
  Ephemerate, Approach of the Second Sun, Insurrection, Lurrus and the rest are the
  guides' picks). One settled as ceiling: Secret Arcade // Dusty Parlor under Killian
  makes your permanents enchantments (a static ability's continuous effect, CR
  611.3), and an enters trigger checks the newcomer as it sits on the battlefield
  (CR 603.6a), so each of your permanents enters as an enchantment for Killian; a
  "makes your permanents the commander's watched type" read would admit it, for one
  card in one deck — not built. Don't re-triage this bucket without a new reach profile.
- **Ramp need not land two turns before the commander — settled 2026-11-01 (R1).**
  The 2026-10-30 plan's "ramp MV ≤ commander MV − 2": nonland ramp that lands later
  (`ramp_in_time`, `RAMP_LEAD` 2; never fixing, premium or the commander's lane) read
  as a low-value upgrade target, and the ramp row sourcing only ramp that lands in
  time (branch `block2-value-rules` 5f8a3b9a, `w41/ramp-lead-R1.patch`). Against
  N12: held-out plan −13, adds +1, job-equivalents −4, swaps −9; the 25 plan −12,
  cuts −7, adds −4, swaps −22 (`sb-*-R1`). The guides keep three-mana rocks and
  ramp creatures under four- and five-mana commanders (the body or the fixing is the
  point), and the sourcing filter starves the ramp row on a cheap commander. With
  R2 and the scaling feature, all three value rules are settled: don't re-suggest a
  mana-value rule for ramp, cuts or one-shots.
- **The alternate-commander compare shipped as an advisory (2026-11-01).**
  `deck-tune --compare-commanders`, deck-forge's `compare_commanders` tune flag and
  the Tune panel's table (`_tuner/compare_commanders.py`): every single the format's
  `commander_eligibility` accepts and every legal partner pair (`can_partner`, CR
  702.124f) tuned in the command zone, ranked by post-tune commander fit then issue
  load — the scorecard has no single total, so that is the rank's definition.
  Evaluated against the nine guides that switch commanders
  (`w41/alt-commander-guides.md`, `compare_commanders_eval.py`): the guide's
  alternate ranks first in 1 of 9, above the face commander in 5 of 9, and the top
  pick disagrees with the guide in 8 of 9 (the fit saturates at 1.0 for every legend
  serving a tribal deck's lane). The guides switch for a build's flavor as much as
  for fit; the table says which legends the deck as built supports. Don't turn it
  into a proposal.
- **The off-plan MV ≥ 6 cut changes nothing — settled 2026-11-01 (R2).** An Engine
  card at mana value 6+ serving no viable avenue (not the commander's lane, not
  premium) read as a low-value upgrade target, least played first (branch
  `block2-value-rules` cbae6d1d). Against N12: held-out adds +1, cuts 0, plan −2;
  the 25 adds +1, cuts −1, plan +2 (`sb-*-R2`). The filler and low-value tiers
  already hold nearly every such card; what the rule adds is a handful of swaps the
  guides don't make. Don't re-suggest a mana-value cut rule.
- **Multiplayer scaling is no quality feature — settled 2026-11-01 (SC).** An
  "each opponent" one-shot does its work three times at a Commander table, so the
  spell quality and strength reads got an ``opponents`` feature (any effect whose
  `effect_player_reach` is each opponent, a per-opponent loop or every player;
  `w41/scaling-feature-SC.diff`). Refit on the same pairs: quality leave-one-deck-out
  0.712 → 0.710 (weight −0.06; the feature splits 18% of pairs and the guide add has
  it 40% of the time), strength on the adds-vs-cuts pairs 0.677 → 0.666 (weight
  −0.36). The guides prefer the cheaper, narrower card over the symmetric one at
  the same slot; the fit says so on both pair sources. No gate run (the design was
  refit, then gate). Don't re-suggest an opponent-count feature.
- **No graveyard-hate template row — settled 2026-11-01 (HR1).** A floor-only row
  (one piece, open ceiling) counted by `roles.is_graveyard_hate` (a nonland card
  carrying `graveyard_matters|opponents|` or `|any|`: Tormod's Crypt, Soul-Guide
  Lantern, Rest in Peace; Bojuka Bog is the mana base's) and sourced by the same
  idents' serve, on the T1 floor-only machinery (branch `block2-hate-row`,
  `w41/hate-row-HR1.patch`). Against N12: held-out adds −5, plan −9, cuts +1,
  job-equivalents +2, page recall @30 −30; the 25 adds −1, plan +2, cuts +2
  (`sb-*-HR1`). The row's fill takes a slot from the plan on every deck short of
  it, and the guides add graveyard hate rarely and by name. With T1 / PR1 that is
  every generic template row beyond the Command Zone five measured and lost:
  don't re-suggest a template row of any kind.
- **A tribe's signal profile opens no page — settled 2026-11-01 (TPa / TPb).** Under a
  commander whose plan lane is a tribe, the lanes the identity pool's tribe members
  over-index on (share ≥ RATIO × the pool's and ≥ MIN_SHARE of the members; a Spine
  role, the tribe's own key, a page-only doer and a lane whose subject is the tribe
  excluded) opened as theme pages after the mains and need pages
  (`_tuner/tribe_profile.py`, branch `block2-tribe-profile`, patches
  `w41/tribe-profile-TPa.patch` + `-TPb-main.diff`). The census first: the pool's
  Pirates over-index on Treasure makers (10.5×), Combat (3.8×), combat damage, blink
  and evasion — not on theft, so Ahoy Mateys' 13 theft adds were out of reach of any
  bar. Fitted on the design 25: 2.0× / 10% adds −5, plan −4; 3.0× / 15% adds −2, plan
  −5 (`sb-25-TPa`, `sb-25-TPb`); the better bar on the held-out 20: adds −2, plan 0,
  cuts 0 (`sb-ho-TPb`). A tribe's pool profile is the tribe's generic cards (Treasure
  under Pirates), which the mains already page; the guides' theme adds are the
  deck's, not the tribe's. Don't re-suggest a tribe → lane read; Ahoy Mateys' theft
  and Silverquill's Spirit rebuild are the first-principles ceiling.
- **A tutor is no need-satisfier — settled 2026-11-01 (TU1).** The third try at the
  guides' tutors (after the generic and plan-conditional rows T1 / PR1): a need
  carries the type-line words a quarter of its pool satisfiers share, and a tutor
  whose own-library search names one of them supplies it (Idyllic Tutor the Auras,
  Worldly Tutor the creatures), an unrestricted tutor only the commander's most
  specific need. Measured against N12 (`w41/sb-*-TU1.json`, `tutor-need-TU1.patch`;
  branch `block2-tutor-need`): held-out plan +3 with the tutor arm alone crediting
  48 adds, guide adds −5, cuts −1; the 25 plan +5 (arm 54), adds −12, cuts −2. The
  tutors take the need pages' slots from the cards the guides add, and the gate's
  plan line would have read the swap as plan-consistent by definition
  (`plan_tune_tutor`, the scoreboard's new column, says how much). The guides' tutors
  stay play-rate adds no page prefers. Don't re-suggest a tutor page, row or arm.
  **Stacked with V3b (VT1, 2026-11-01, Dan's ask after the block):** the one pair
  whose single-run sums cleared the plan bar (+9 and +3). Measured together against
  N16 (`w41/sb-*-VT1.json`): held-out plan +13 of which the tutor arm alone 77,
  guide adds −16, job-equivalents −1, cuts 0; the 25 adds −20, plan +24 (arm 69).
  The two losses compound — the reorder lifts the tutors the need page admits over
  the guides' adds — so the combination loses more adds than either alone. No
  other pair sums past the plan bar. Don't re-suggest stacking the block's losers.
- **The commander's multipliers are a need, not a page** (2026-10-31). The
  ability-multiplier PAGE was measured negative 2026-10-30 (its one swap took the
  first upgrade cut: held-out adds 35 → 31). The read that replaced it: a
  "multipliers of the commander" need (`commander_need._multiplier_need`, a
  predicate over `multipliers.multiplier_reasons`' `copy` and `ability` families),
  shipped in N5. The need routes a cut to its own page and gives the E1 near tie
  its reason, so Strionic Resonator, Lithoform Engine and Illusionist's Bracers
  are paged now (Ahoy Mateys' need page holds 141 cards; they sit outranked, as
  the guides' theft adds do there). Ceiling 27 of 807 held-out guide adds. Don't
  re-suggest the page.
- **Sub-theme pages — don't re-suggest without a new read** (2026-10-31, S-A,
  the audit's "Sub-theme pages"). Every built sub and emerging lane sharing the
  theme adds by depth lost the 25 24 adds / plan −45 and the held-out 20 14 adds /
  plan −12: the generic subs' pages take the adds. Ahoy Mateys' theft (the
  motivating case: fifteen guide adds, eight precon cards across `gain_control` /
  `theft_makers` / `cast_from_exile`) is not built even at the emerging tier, so
  no sub-theme rule reaches it; its theft adds sit on the "multipliers of the
  commander" need page now, outranked.
- **The held-back policy patches P1 and P3 stay held** (Dan, 2026-10-31
  grilling: the gate stays plan-primary). `w41/job-blend-P1.patch` (play-rate
  counted twice in the ordering jobs' blend: held-out adds +2, plan −2) and
  `w41/theme-band-P3.patch` (theme upgrades may cost one band more: held-out adds
  +2, plan 0, job-equivalents −5) each gain two guide adds inside the ±3 noise a
  hash-seed rescore shows. A 300-card theme page (P2) converted nothing. Don't
  re-suggest any of the three without a rebalanced gate.

- **A folded held lane keeps its doers — don't re-suggest** (2026-10-30;
  `real-deck-validation.md`, Fynn). When Fynn v4's poison lane folds into
  Deathtouch matters (`metrics.focus`, `same_members`), Infectious Bite stops
  counting as a commander-lane doer. Unioning the doers over every held ident
  cost 4 guide cuts on the 25 precons (712 / 325 / 114); keeping only those
  inside the kept lane's members cost 6 (711 / 323 / 114). The guides cut a
  folded lane's doers: Quick Draw's spell copies and top-deck selection,
  Sultai Arisen's self-mill. No Fynn run cuts Infectious Bite.
- **The "Power-as-damage payoffs" page doesn't read `bite` alone — don't
  re-suggest** (2026-11-01, Fynn validation follow-up). The page turns your big
  creature's power into damage, and the spell is often the dealer: Tiger-Tribe
  Hunter's sacrificed creature, Monstrous Emergence's chosen or revealed one,
  Bloodfire Infusion, Bouncer's Beatdown's greatest power, Foray of Orcs' Army.
  Read through `bite` the page lost 43 cards, about fifteen of them those. The
  lane's `creature` subject now carries only power a creature of yours sizes
  (`crosswalk.power_is_yours`: 183 → 160 cards; Repentance, Solar Blaze, Mutiny,
  Alpha Brawl, Dead Reckoning, Lie in Wait and the self-damage spells leave), and
  the page keeps `damage_equal_power|you|*`. Corpse Explosion stays: a creature
  card of yours, exiled as its cost, sizes it. Left out by the read's own call:
  Too Greedily, Too Deep's creature returned "under your control". (An attached
  dealer was left out too, superseded 2026-11-01: an Equipment's equipped
  creature is yours — equip attaches it to "target creature you control", CR
  702.6a, 301.5a — so Lothlórien Blade bites; an Aura's enchanted creature stays
  out.) `is_bite` reads a triggering dealer off the trigger's watched
  creature (Halana, Kessig Ranger) and a batch's off its sources (Moonlight
  Hunt, Kamahl's Will, Bartz and Boko, Nissa's Judgment, Signature Slam, The
  Bears of Littjara, Judgment of Alexander): `bite` 128 → 136.
- **Smothering Tithe and Pyxis of Pandemonium sit in no stax or graveyard-hate
  lane — don't re-suggest** (2026-11-01, Pass D follow-up). `stax_taxes` /
  `symmetric_stax` read static restrictions and taxes (CR 604.1: casting,
  attacking, untapping, hand size); Smothering Tithe is a triggered punisher on
  an opponent's draw, already `opponent_draw_matters|opponents|` and
  `treasure_makers|you|`. `opponent_exile_makers` is graveyard hate (a
  graveyard exiled); Pyxis exiles the top card of each player's library face
  down and later puts the permanents among them onto the battlefield, already
  `cheat_into_play|you|`. Auton Soldier (`clone_makers|you|`) and Mouth //
  Feed's aftermath draw (`draw_for_each|you|`, `card_draw_engine|you|`) were
  served by the second lane pass.
- **`etb_value_x_recast_commander` keeps one weight for every ETB payload —
  don't re-suggest without a per-payload read** (2026-11-01, Pass D follow-up;
  `self_etb_payload` now reads 4,768 cards). The pair rows reach `deck-rank`
  only (`build_pair_context` has no other caller: deck-tune and deck-forge's
  Find never price them). Inside a deck whose commander anchors the row, it adds
  the same 3.0 to every ETB-payload card, so it never reorders them among
  themselves: Shriekmaw still outranks a scry-1 ETB on its synergy. What the
  flat weight does is lift a weak ETB over a non-ETB card of equal synergy. A
  payload weight needs a job read of the enters trigger itself, which the
  lane's ident doesn't carry (no subject), and of the 25 precons only Death
  Toll (Winter, Cynical Opportunist) and Sultai Arisen (Teval) anchor the row,
  neither through a ranking the gate scores.
- **The voltron floor's `has_other_plan` asks `avenue_spec_for`; the serve specs
  key the signals index** (shipped 2026-11-01, Dan's call: correctness over the
  rebuild a spec edit costs). A signal that opens no avenue — a page-only doer,
  a step-trigger payoff, a subject its theme's serve doesn't count — is no other
  plan, so twelve cards whose only plan opens none keep the commander-damage
  carrier tell (`voltron_matters|you|carrier`, 2405 → 2417: Brass Secretary,
  Parcel Myr, the Hunted cycle, Avatar of Will). `signal_specs/` is in
  `signals_index.signal_source_files` now (`test_includes_signal_specs_which_the_membership_floor_asks`),
  so every spec edit rebuilds the persisted index once. No tune moved.
- **A spell's casting-cost discard is a discard outlet** (Dan, 2026-10-10). The
  optional keyword costs count: escalate (Collective Brutality, CR 702.120a),
  buyback (Forbid, Demonic Collusion, CR 702.27a), flashback (Conflagrate, Twinned
  Vision, CR 702.34a), as Sabin's blitz does (CR 702.152a). Jump-start (CR
  702.133a) and retrace (CR 702.81a) count too; phase leaves their discard
  untyped, so `discard_outlet` reads them by keyword name behind a
  `retirement_canary`. A mandatory additional-cost discard counts as well
  (Tormenting Voice, Thrill of Possibility, CR 601.2f): you choose the card and
  when to cast. So does a discard that is one choice of an either/or cost (Bitter
  Triumph, Bone Shards, Lightning Axe: "discard a card or pay …"), since you may
  always choose it. `discard_outlet` reads each off the spell's merged `unit.costs`.
- **A random discard isn't a discard outlet, but it still makes discards** (Dan,
  2026-10-10). It can't be aimed (CR 701.9b; Flowstone Flood's buyback, Goblin
  Lore, Amok), so `discard_outlet` skips it in every arm, the kept text mirror
  included (`crosswalk.discard_is_random`). `discard_makers` (loot and rummage)
  keeps it, because a "whenever you discard" payoff (Drake Haven) fires whichever
  card goes (Burning Inquiry). A chosen opponent's discard is not yours either
  (Fervent Mastery, `lanes._shared._choose_opponent_bound_discard`).
- **Swarmyard Massacre's `scaling_pump` stays** (2026-11-01): the lane asks
  whether a P/T change scales with a board count (CR 107.3, 613.4c), and its own
  corpus adjudication admits a scaling shrink (Dark Salvation's "-1/-1 for each
  Zombie"); Swarmyard's -1/-1 grows with your Insects, Rats, Spiders and
  Squirrels, the board the deck builds. (The bump's other policy questions were
  fixed the same day: an opponent's lifegain, the attack-less voltron carriers,
  Aura enchant, one creature's Auras, a parked loot, a self-exiling trigger.)
- **Empower Jace is no graveyard maker** (2026-11-01): the Jace token it makes
  (only when you control none) surveils through a "[−1]: Surveil 1" loyalty
  ability beside "[−3]: Draw a card"; the 28 empower cards (Protege's Awakening,
  the Way of the … cycle) build a Jace's loyalty, and a graveyard page that
  served them would serve a planeswalker plan. `graveyard_makers` reads a fill
  the card itself makes (surveil, a mill, a discard cost).
- **Upkeep-payment discards aren't discard outlets** (Dan, 2026-10-09): echo's and
  cumulative upkeep's discard (Deepcavern Imp, Rakdos Headliner, Vexing Sphinx) is
  a forced payment to keep the permanent, not a discard you make on demand (CR
  702.30a, 702.24a); `core._UPKEEP_PAYMENT_KEYWORDS` reads only their life costs.

- **Two-arm lanes** (a structural arm OR a `synth_<key>` reference-arm concept, 91 of
  279 lanes): stable by design, not debt (ADR-0038 amendment). Don't tabulate or
  rename them.
- **Judged in good shape by the 2026-09-17 review:** `theme_presets` (a registry over
  signals; removal isn't duplicated), `cut_check`, proxy-printer's layout and Fetcher
  seam, `phase_bump`, `testkit`, `agent_bridge` / `events`, and the tuner's classify,
  shape and bracket modules.
- **Firebending isn't ramp** (Dan, 2026-10-09): not a creature with firebending
  (Uncle Iroh; `firebending_makers` is out of the ramp preset's keys), a maker of
  firebending tokens (Fire Nation Attacks, Firebender Ascension, Cruel
  Administrator, Fire Nation Occupation) nor a grant (Sozin's Comet, Fire Nation
  Turret, Fire Nation Cadets). The mana comes only as the creature attacks and lasts
  until end of combat (CR 702.189a), so it doesn't speed up the curve.
- **Symmetric shields aren't protection** (Dan, 2026-10-08): `roles.protects` is
  protecting YOUR board, so a permanent's shield over every player's objects alike
  (Crumbling Sanctuary, Plated Pegasus, Well-Laid Plans' residue) stays out; a fog
  you cast and an optional shield you aim stay in.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
