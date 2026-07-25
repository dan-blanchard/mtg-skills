"""Layer-2 concept overlay over the lossless typed substrate (ADR-0035, Stage 2).

The crosswalk is a **tree-preserving** decoration over the codegen'd typed mirror
(``_card_ir/mirror``): it reads the typed substrate by ``isinstance`` / typed
attribute access — never re-greps oracle text, never bypasses to a stringly-keyed
dict — and hangs a :class:`ConceptNode` off every effect's preserved tree
position. Each concept-node is either a **recognized concept** (``draw`` /
``discard`` / ``make_token`` / ``win_game`` / …) or an ``other`` concept **carrying
the verbatim typed node** (the lossless hatch — categorically different from a
verbatim-*text* ``raw`` that forces re-regex; the structured node is preserved).

It is **additive / shadow-only** (ADR-0035 Stage 2): nothing in production reads
this. The live regex+IR detection path (``_deck_forge.signals``) is untouched; the
crosswalk runs alongside it for the shadow ``Signal``-diff.

The overlay preserves the **three join granularities** the lanes depend on, so a
flat-overlay regression fails loud:

* **(a) per-ability sibling co-occurrence** — :meth:`AbilityUnit.effect_concepts`
  scopes effects to ONE ability unit. ``discard_makers`` fires only when a ``draw``
  *and* a ``discard`` effect coexist in the SAME unit (Faithless Looting), never
  across two abilities (Psychic Frog / Nezahal — a combat-damage draw *trigger* and
  a separate ``Discard a card:`` *cost* live in different units, and a cost is not
  an effect).
* **(b) per-ability effect/raw aggregation** — :meth:`AbilityUnit.iter_concepts`
  exposes a unit's effects *and* static modifications together, so the animate-land
  split-subject (a Land subject + a becomes-creature modification spread across one
  static ability) reconstructs as one decision.
* **(c) whole-card / cross-face merged-key joins** — :meth:`ConceptTree.has_effect`
  / :meth:`ConceptTree.iter_concepts` scan every unit, the surface the four
  ``signals.py`` reconciliations read.

Stays self-contained within ``_card_ir`` (Layer-2 framework only — no
``_deck_forge`` import); the ``Signal``-lane derivation that *uses* this overlay
lives at Layer 3 in ``_deck_forge.lanes``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from mtg_utils._card_ir.crosswalk.reads import (
    _EFFECT_CHILD_FIELDS,
    _PAYLIFE_COST_TAGS,
    _effect_scope,
    _effect_subject,
    _filter_type_words,
    _iter_typed_nodes,
    _node_raw,
    _present,
    _scope_from_player_node,
    _trigger_event,
    filter_core_types,
    iter_nested_granted_bodies,
    iter_typed_nodes,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

# ── Effect tag → concept map (the stable Layer-2 vocabulary) ──────────────────
# Phase ``Effect`` discriminator tag (the node's ``_tag``) → recognized concept
# name. An effect whose tag is absent here decorates as ``other`` CARRYING the
# verbatim typed node — the lossless tail. Grown per ported batch; everything
# else stays ``other`` (never silently dropped).
EFFECT_CONCEPTS: dict[str, str] = {
    "Draw": "draw",
    "Discard": "discard",
    # ADR-0038 W4 giants (opponent_discard) — "discard THAT card" after a
    # reveal-and-choose (Thoughtseize, Duress, Inquisition of Kozilek): phase
    # tags the FOLLOW-UP discard of an already-identified card ``DiscardCard``
    # (count=1, target=ParentTarget) distinctly from a self-count ``Discard``
    # ("discards N cards"). Corpus-verified 92/92 commander-legal instances
    # carry ``target=ParentTarget`` — never Controller/self — so folding it
    # into the SAME "discard" concept is safe for every sibling lane that
    # reads ``effect_concepts("discard")``: ``discard_makers``/
    # ``discard_outlet`` both gate on scope you/each (ParentTarget resolves
    # "any"/"opponents", never you/each — CR 701.9), so neither over-fires.
    "DiscardCard": "discard",
    "Token": "make_token",
    "CopySpell": "copy_spell",
    "WinTheGame": "win_game",
    "LoseTheGame": "lose_game",
    "Pump": "pump",
    "PumpAll": "pump",
    # Batch 2 (ADR-0035 Stage 2):
    "GainLife": "gain_life",  # lifegain_makers / matters
    "LoseLife": "lose_life",  # lifegain_matters self-loss sustain
    "DealDamage": "deal_damage",  # direct_damage (single-target / "any target")
    "DamageEachPlayer": "deal_damage",  # direct_damage (each/opp player)
    "DamageAll": "deal_damage",  # direct_damage (mass; players when player_filter)
    "Sacrifice": "sacrifice",  # sacrifice_outlets (effect + cost) / edict
    "PutCounter": "place_counter",  # plus_one_makers (counter_type discriminates)
    "PutCounterAll": "place_counter",
    "AddPendingETBCounters": "place_counter",
    "ExtraTurn": "extra_turn",  # extra_turns (CR 500.7)
    "ChangeZone": "change_zone",  # reanimator (GY→bf) / blink (exile+return)
    "ChangeZoneAll": "change_zone",
    "Mana": "ramp",  # mana production (lane splits land base vs accel/fixing)
    # Batch 3 (ADR-0035 Stage 2):
    "Mill": "mill",  # mill_makers / graveyard self-fill (CR 701.17a)
    "Proliferate": "proliferate",  # proliferate_makers / any_counter_makers
    "MoveCounters": "move_counters",  # any_counter_makers / plus_one_matters (p1p1)
    "RemoveCounter": "remove_counter",  # any_counter_makers (kindless)
    "GainControl": "gain_control",  # theft (CR 720) — donate/reset excluded
    "GainControlAll": "gain_control",
    "GiveControl": "give_control",  # donate (the exclusion direction)
    "Attach": "attach",  # voltron_makers (attach-other gear)
    "SearchLibrary": "tutor",  # type/subtype tutor (artifacts/voltron)
    # ADR-0036 tutor Tier-1 fold: Teacher's Pet's bespoke Augment-combine
    # search is phase's own library search, just under a card-specific tag
    # rather than the generic SearchLibrary (no target_player variant exists
    # for it — always a self search, CR 701.23).
    "ChooseAugmentAndCombineWithHost": "tutor",
    "Investigate": "investigate",  # clue_makers (CR 701.16a) → also artifacts
    "GainEnergy": "gain_energy",  # energy_makers (CR 107.14)
    # Batch 4 (ADR-0035 Stage 2):
    "Fight": "fight",  # fight_makers (CR 701.14a)
    "Goad": "goad",  # goad_makers (CR 701.15a)
    "GoadAll": "goad",
    "Regenerate": "regenerate",  # regenerate_makers (CR 701.19a)
    "Connive": "connive",  # connive_makers (CR 701.50a)
    "Explore": "explore",  # explore_makers (CR 701.44a)
    "ExploreAll": "explore",
    "Suspect": "suspect",  # suspect_makers (CR 701.60a)
    "BecomeCopy": "become_copy",  # clone_makers / copy_permanent (CR 707)
    "CopyTokenOf": "copy_token",  # token_copy_makers (CR 707 / 701.36)
    "CopyTokenBlockingAttacker": "copy_token",  # Mirror Match
    "Populate": "populate",  # token_copy_makers (CR 701.36a)
    "NoMaximumHandSize": "no_max_handsize",  # big_hand_makers (CR 402.2)
    # NB: phase's ``Mill`` effect is NOT mapped — mill_makers reverted to the
    # Scryfall ``Mill`` keyword field-lookup (ADR-0027), because phase mislabels
    # three non-mill effects (Bone Dancer / Scroll Rack / Soldevi Digger) as Mill.
    # Batch 5 (ADR-0035 Stage 2) — the named-mechanic long tail. Each is a
    # first-class phase effect node the OLD lossy IR dropped (the live path
    # reached most via a Scryfall-keyword survivor or a kept-word-mirror); the
    # crosswalk reads them STRUCTURALLY off the typed substrate.
    "BecomeMonarch": "become_monarch",  # monarch_makers (CR 725)
    "Discover": "discover",  # discover_makers (CR 701.57)
    "VentureIntoDungeon": "venture",  # venture_makers (CR 701.49 / 309)
    "TakeTheInitiative": "venture",  # venture_makers (the Initiative designation)
    "SetDayNight": "set_daynight",  # daynight_makers (CR 731)
    "PhaseOut": "phasing",  # phasing_makers (CR 702.26)
    "PhaseIn": "phasing",
    "Vote": "vote",  # voting_makers (CR 701.38; raw-guarded vs friend-or-foe)
    "RingTemptsYou": "ring_tempt",  # ring_tempters (CR 701.54)
    "Amass": "amass",  # amass_makers (CR 701.47)
    "Incubate": "incubate",  # incubate_makers (CR 701.53)
    "Manifest": "facedown",  # facedown_makers (CR 701.40 / 708)
    "Cloak": "facedown",  # facedown_makers (CR 701.58 / 708)
    "TurnFaceUp": "turn_face_up",  # facedown_matters payoff (out of this batch)
    "RollDie": "roll_die",  # dice_makers (CR 706)
    # Attractions "roll to visit" (CR 701.52a: "roll a six-sided die …") is a
    # DISTINCT phase tag from RollDie (no shared die-count/sides fields) but
    # the SAME CR 706 die-roll action — Command Performance.
    "RollToVisitAttractions": "roll_die",  # dice_makers (CR 701.52a / 706)
    # ``GrantCastingPermission`` carries a ``permission`` sub-node (PlayFromExile /
    # Plotted) — the cast_from_exile build-around the live path kept as a
    # byte-identical word-mirror. Read structurally via :func:`permission_tag`.
    "GrantCastingPermission": "grant_cast_permission",  # cast_from_exile
    # Batch 6 (ADR-0035 Stage 2) — the counter-KIND / count-operand / property
    # cluster. A player-counter giver (rad / experience) and a coin flip the OLD
    # lossy IR reached via a kind-split effect category; the crosswalk reads them
    # off the first-class typed node.
    "GivePlayerCounter": "give_player_counter",  # rad / experience makers (CR 122.1)
    "FlipCoin": "flip_coin",  # coin_flip (CR 705.1)
    "FlipCoins": "flip_coin",
    "FlipCoinUntilLose": "flip_coin",
    # Batch 7 (ADR-0035 Stage 2) — the phase / control / terminal-effect cluster.
    # An additional combat phase, a card conjure (Alchemy), and an end-the-turn
    # the OLD lossy IR reached via a kind-split effect category / word-mirror; the
    # crosswalk reads them off the first-class typed node.
    "AdditionalPhase": "extra_phase",  # extra_combats (phase gates begin/combat)
    "Conjure": "conjure",  # conjure_makers (DD2/DD5 — a real card, not a token)
    "EndTheTurn": "end_the_turn",  # end_the_turn (CR 724 — Time Stop, Sundial)
    # NB: ``TakeTheInitiative`` stays mapped to ``venture`` (above) so
    # ``venture_makers`` keeps co-firing; ``initiative_makers`` reads the
    # ``TakeTheInitiative`` _tag distinctly off the same effect node.
    # Batch 8 (ADR-0035 Stage 2) — the removal / card-flow / library-top
    # cluster. ``Destroy``/``Bounce`` and their ``*All`` mass forms are
    # first-class phase tags (the ``*All`` tag IS the CR 115.10 mass
    # discriminator — the lanes read it via :func:`tag_of`); ``Dig`` is the
    # look-at-top-N selector (destination-gated: to:battlefield = a put-into-
    # play, to:hand = card selection); ``ExileTop`` + ``CastFromZone`` are the
    # impulse-draw pair (exile the top, then cast from exile).
    "Destroy": "destroy",  # single-target destroy (CR 701.8)
    "DestroyAll": "destroy",  # board wipe (mass_removal, CR 115.10)
    "Bounce": "bounce",  # return-to-hand (single target)
    "BounceAll": "bounce",  # mass_bounce (CR 115.10)
    "Dig": "dig",  # look at top N (extra_land_drop's dig-into-play arm)
    "ExileTop": "exile_top",  # impulse_top_play's exile-the-top half
    "CastFromZone": "cast_from_zone",  # the play-it half (Etali)
    # Batch 9 (ADR-0035 Stage 2) — the library-top / hand-reveal cluster.
    # ``Scry`` / ``Surveil`` are first-class doer nodes (CR 701.22 / 701.25 —
    # the library owner is always the implicit controller); the two library
    # PUT forms carry a ``position`` sub-node (``Top`` / ``Bottom`` /
    # ``NthFromTop``) the topdeck_stack lane discriminates on; the hand /
    # top-of-library reveals carry the revealed PLAYER (CR 402.3 / 401.1).
    "Scry": "scry",  # topdeck_selection (CR 701.22)
    "Surveil": "surveil",  # topdeck_selection (CR 701.25)
    "PutAtLibraryPosition": "put_library_position",  # topdeck_stack (CR 401.4)
    "PutOnTopOrBottom": "put_library_position",  # the top-or-bottom choice form
    "RevealHand": "reveal_hand",  # hand_disruption (CR 402.3)
    "RevealTop": "reveal_top",  # topdeck_selection's reveal arm (CR 401.1)
    # Batch 10 (ADR-0035 Stage 2) — the trigger-event / effect-tag / P/T /
    # static-mode cluster. ``Counter`` is the stack counterspell (CR 701.6a —
    # structurally DISJOINT from ``PutCounter``/``RemoveCounter``, the other
    # meaning of "counter"); ``PreventDamage`` the CR 615 prevention shield;
    # ``DoublePT``/``SwitchPT`` the P/T arithmetic forms (CR 613.4c/613.4d);
    # ``ManifestDread`` the batch-9-adjudicated first-class manifest-dread doer
    # (CR 701.55 — joins Manifest/Cloak under the facedown concept).
    "Counter": "counter_spell",  # counter_control (CR 701.6a)
    "CounterAll": "counter_spell",  # the mass form ("counter all …")
    "PreventDamage": "prevent_damage",  # damage_prevention (CR 615.1)
    "DoublePT": "double_pt",  # power_double (CR 613.4c)
    "DoublePTAll": "double_pt",
    "SwitchPT": "switch_pt",  # base_pt_set's switch arm (CR 613.4d)
    "ManifestDread": "facedown",  # facedown_makers + _matters (CR 701.55)
    # Batch 11 (ADR-0035 Stage 2) — the tap / detain / library-dig / one-shot
    # doubler cluster. ``SetTapState`` carries a ``state`` sub-node (Tap /
    # Untap — CR 701.26a) the tap lanes discriminate on via
    # :func:`settap_state`; ``Detain`` is the CR 701.35 tempo-denial (all
    # opponent-targeted corpus-wide); ``RevealUntil`` the reveal-until-a-
    # condition dig (CR 701.20a) whose digger rides ``player``;
    # ``Double`` the one-shot quantity doubler whose ``target_kind``
    # (Counters / LifeTotal / ManaPool) routes the lane (Vorel — the live
    # byte-mirror's "phase mangles Vorel" complaint was STALE);
    # ``MultiplyCounter`` the triggered counter-multiplier (Kalonian Hydra).
    # NB: ``DamageAll`` / ``DamageEachPlayer`` stay mapped to ``deal_damage``
    # (batch 2) — the spec's ``mass_damage`` remap would break the ported
    # ``direct_damage`` parity; the mass lanes read the TAG via ``tag_of``.
    "SetTapState": "tap_untap",  # tap_down / tapper_engine (CR 701.26a)
    "Detain": "detain",  # tap_down's detain arm (CR 701.35)
    "RevealUntil": "reveal_until",  # dig_until (CR 701.20a)
    # ``ExileFromTopUntil`` is phase's EXILE-side sibling of ``RevealUntil`` —
    # the SAME dig-until-a-condition shape (CR 701.13 + 701.20a idiom), just
    # to Exile instead of staying revealed-in-place (Demonlord Belzenlok:
    # "exile cards from the top of your library until you exile a nonland
    # card"). The OLD-IR ``project.py`` category map already folds both tags
    # to one ``dig_until`` category (``"revealuntil"``/``"exilefromtopuntil"``
    # -> ``dig_until``); this mirrors that verbatim so the crosswalk's
    # digger-field read (:func:`reveal_until_player`, generic on ``.player``)
    # and the dig_until lane's structural arm cover BOTH tags with no lane
    # change (~25-card corpus recovery, ADR-0037/0038 W3).
    "ExileFromTopUntil": "reveal_until",
    # ``SkipNextStep`` (a phase v0.20 addition — ADR-0037/0038 W3; the tap_down
    # docstring's "no SkipStep node in v0.9.0" note is now STALE) is the
    # "skips their next untap step" tempo-skip (Brine Elemental, Shisato) —
    # a DISTINCT effect from ``SetTapState``, read via its own ``step``/
    # ``target`` fields by the tap_down lane's dedicated arm below.
    "SkipNextStep": "skip_next_step",
    "Double": "double_quantity",  # counter_doubling arm b (CR 122.1)
    "MultiplyCounter": "multiply_counter",  # counter_doubling arm c
    # Batch 12 (ADR-0035 Stage 2) — the life-total / control-exchange
    # cluster. ``SetLifeTotal`` / ``ExchangeLifeTotals`` /
    # ``ExchangeLifeWithStat`` are the CR 119.5 + 701.12c set-life family
    # (case law Magister Sphinx: becoming 10 IS gaining/losing the
    # difference); ``Double{LifeTotal}`` reuses :func:`double_target_kind`.
    # ``ExchangeControl`` is the CR 701.12b two-sided control swap (Gilded
    # Drake, Political Trickery) — the land_exchange lane reads its two
    # target filters; the creature swaps stay in gain_control's country
    # (live-extractor-verified, the b12 mandatory parity check).
    "SetLifeTotal": "set_life",  # life_total_set (CR 119.5)
    "ExchangeLifeTotals": "set_life",  # Axis of Mortality
    "ExchangeLifeWithStat": "set_life",  # Serra Avatar-family stat swap
    "ExchangeControl": "exchange_control",  # land_exchange (CR 701.12b)
    # Stage-2 closeout sweep (ADR-0035) — ``Seek`` is the DD3 Alchemy doer
    # ("the game randomly chooses a matching card from your library"); the
    # live path reads it via project.py's ``"seek"`` category row, and the
    # sweep's seek_matters lane reads the same node here. Arena-only is a
    # LEGALITY property, not a skip (deck-forge serves historic_brawl).
    "Seek": "seek",  # seek_matters (DD3)
}

# Predefined ARTIFACT token subtypes (CR 111.10 / 205.3g): a maker / sac-payoff over
# one feeds artifacts_matter even when phase carries only the subtype with an empty
# card_types (Emissary Green, Giant Opportunity). Consumed by
# ``crosswalk_signals.py`` and ``dropped_clauses.py``.
ARTIFACT_TOKEN_SUBTYPES: frozenset[str] = frozenset(
    {
        "treasure",
        "clue",
        "food",
        "powerstone",
        "gold",
        "map",
        "junk",
        "incubator",
        "blood",
        "lander",
        "mutagen",
    }
)

OTHER = "other"


@dataclass(frozen=True)
class ConceptNode:
    """A per-node decoration hanging off a preserved typed-tree position.

    ``node`` is the **verbatim** typed substrate instance (an ``other`` concept
    carries it losslessly — its ``to_dict`` still round-trips). ``role`` records
    the structural slot the node occupies within its ability unit (``effect`` for
    a resolved effect / sub-effect, ``cost`` for an activation cost, ``static``
    for a continuous-ability modification) — the per-ability granularity gate that
    keeps a *discard cost* from reading as a *discard effect*.
    """

    concept: str  # recognized concept name, or ``OTHER``
    node: TypedMirrorNode  # the verbatim typed node (lossless)
    role: str  # "effect" | "cost" | "static"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: tuple[str, ...]  # type/subtype strings the node names ("" → empty)
    raw: str  # a grounding clause (node description / "") — not identity-bearing
    # ── ADR-0035 Stage-3b (b) overlay-correction fields ───────────────────────
    # Additive overlay decorations written ONLY by the named
    # ``overlay_corrections`` stage (never by ``build_concept_tree``), so a
    # default-constructed node carries none. They correct a field the pure
    # substrate under-derives — a graveyard zone phase dropped, a blink
    # return marker — WITHOUT touching the L1 mirror ``node`` (the
    # substrate-purity invariant). ``zones`` is UNIONed onto the structurally
    # derived zones by the compat reader; ``returns_to`` names the blink
    # return destination ("battlefield"), read by no live consumer yet
    # (behavior-neutral, mirroring the OLD ``_recover_blink_returns_to``).
    #
    # ``category`` is a COMPAT-ONLY old-IR category override (a dig re-read as
    # ``cheat_play``, a swallowed exile as ``exile``). It is DELIBERATELY separate
    # from ``concept``: the signal lanes read ``concept`` (a category-flip that
    # rewrote it would silence the ``dig_until`` / ``lifegain`` signal the LIVE
    # path — which reads oracle text, not the recovered category — still emits, a
    # measured shadow-diff regression), while ``compat`` reads ``category``. So the
    # flip corrects the compat consumer WITHOUT moving the Signal seam.
    zones: tuple[str, ...] = ()
    returns_to: str = ""
    category: str = ""
    # ADR-0038 recovery provenance — the clause-grammar token that recovered
    # this node's decoration (written ONLY by the recovery stage; "" means
    # decorated straight from the typed substrate). Per-rule corpus fire
    # counts over this field are the bridge-remaining metric.
    recovered_by: str = ""


@dataclass(frozen=True)
class AbilityUnit:
    """One ability of the card — the per-ability join scope (granularities a/b).

    A unit is one entry of phase's ``abilities`` (activated/spell/static-on-an-
    ability), ``triggers`` (a triggered ability — ``trigger_event`` derived from
    its ``mode`` + zone/recipient), ``static_abilities`` (a continuous ability —
    its ``modifications`` become ``static``-role concepts), ``replacements``, or
    a KEYWORD's own effect payload (``root.keywords`` — CR 702's own-effect
    idiom, e.g. Cumulative Upkeep's "Add {R}"; see
    :func:`_keyword_effect_units`, distinct from a keyword's alternative-cost
    PayLife leaf which merges onto an ``"ability"``-origin unit instead).
    ``node`` is the verbatim typed ability node (the preserved tree position).
    """

    origin: str  # "ability" | "trigger" | "static" | "replacement" | "keyword"
    index: int
    node: TypedMirrorNode
    kind: str | None  # phase ability ``kind`` (Activated/Spell/Static/…) or None
    trigger_event: str | None  # derived event for a trigger unit, else None
    effects: tuple[ConceptNode, ...]  # role=effect (the effect+sub_ability chain)
    costs: tuple[ConceptNode, ...]  # role=cost (activation costs)
    statics: tuple[ConceptNode, ...]  # role=static (continuous modifications)

    def iter_concepts(self) -> Iterator[ConceptNode]:
        """Every concept-node in this unit (effects, costs, statics)."""
        yield from self.effects
        yield from self.costs
        yield from self.statics

    def effect_concepts(self, concept: str) -> tuple[ConceptNode, ...]:
        """The role=effect concept-nodes in THIS unit matching ``concept``.

        The per-ability sibling-co-occurrence gate (granularity a): reads only
        resolved effects, so an activation *cost* of the same kind never counts.
        """
        return tuple(c for c in self.effects if c.concept == concept)

    def has_effect(self, concept: str) -> bool:
        """Whether THIS unit has a role=effect concept-node named ``concept``."""
        return any(c.concept == concept for c in self.effects)


@dataclass(frozen=True)
class ConceptTree:
    """The whole-card overlay: the card's ability units, tree position preserved.

    ``units`` is the per-ability join surface (granularities a/b). The whole-card
    joins (granularity c) read across all units via :meth:`iter_concepts` /
    :meth:`has_effect`.
    """

    name: str
    oracle_id: str
    units: tuple[AbilityUnit, ...] = field(default_factory=tuple)
    card_types: tuple[str, ...] = ()  # the card's own core types (Creature / Land …)
    card_subtypes: tuple[str, ...] = ()  # the card's own subtypes (Saga / Elf …)
    # b14 (§0 deepening-start-minimal): the card's own supertypes (Legendary /
    # Snow — CR 205.4) and its phase-derived mana value (``mana_cost.generic +
    # len(shards)``, 0 when the cost is null — CR 202.3). Added ONLY for the
    # wants_cloning membership gates; phase cmc can differ from bulk cmc on odd
    # frames (logged shadow-diff data, not chased).
    card_supertypes: tuple[str, ...] = ()
    cmc: int = 0
    # b16 (§16 one_punch, deepening-start-minimal): the card's own FIXED printed
    # power (None for CDA/dynamic ``*`` powers) and whether the face carries a
    # REAL printed mana cost (phase tags transform backs / meld results
    # ``NoCost`` — their mana value lives on the FRONT face, so a NoCost face
    # must never enter a power-for-cost numeric gate; CR 202.3b treats the back
    # face's mana value as the front's).
    power: int | None = None
    has_printed_cost: bool = False
    # The phase record's face oracle text (``S_Root.oracle_text``), verbatim.
    # Carried for the b12 SANCTIONED byte-identical mirror ports (the live
    # kept-regex lanes: entered_attacker, animate_artifact, color_change, the
    # stax residues, …) — those lanes strip reminder parens and re-run the
    # EXACT live constants; every structural lane stays a typed read.
    oracle: str = ""
    # ADR-0039 W8 (deepening-start-minimal, the b16 precedent): the CR 100.2a
    # deck copy-limit relaxation ("A deck can have any number of cards named
    # X" / "up to N cards named X" — Relentless Rats, Hare Apparent, Seven
    # Dwarves). Read off ``root.deck_copy_limit`` (``Unlimited`` or ``UpTo``
    # with a bound >= 2 — ``UpTo:1``, Vazal's Megalegendary, RESTRICTS to one
    # copy and is excluded), the SAME phase field the old-IR
    # ``card_ir._allows_many_copies`` reads off the raw record. copy_limit is
    # the only consumer today; a card-level bool (not a per-unit concept) since
    # the field is a whole-card deck-construction property, not tied to any
    # one ability.
    many_copies: bool = False
    # ADR-0039 grammar sprint (task #82, deepening-start-minimal): a modal
    # SPELL's card-root ``modal.mode_descriptions`` (CR 700.2 "choose one"),
    # positionally paired with ``root.abilities`` — the REAL per-mode English
    # phase carries at the ROOT, never on the mode ability's own (frozen,
    # unwritable) ``description`` field (Fatal Lore, Season of the Burrow).
    # A TRIGGER's modal branches carry the same pairing one level down
    # (``execute.modal``/``execute.mode_abilities``, reachable directly off
    # the owning unit's own node — see :func:`modal_mode_description`), so
    # only the card-root shape needs a ``ConceptTree`` field. Empty for every
    # non-modal card (the overwhelming majority) — cheap, additive, mirrors
    # the b16 field-addition precedent (``power``/``has_printed_cost``).
    card_modal_mode_descriptions: tuple[str, ...] = ()
    # task #87 (deepening-start-minimal, the b16 precedent): the core TYPE
    # words of the card's OWN printed ``Enchant`` keyword filter (CR 303.4a
    # — "Enchant creature", "Enchant creature card in a graveyard") — Animate
    # Dead / Dance of the Dead's "enchant creature card in a graveyard".
    # Read off ``root.keywords``'s ``Enchant`` variant (a root-level array,
    # never surfaced on any :class:`AbilityUnit`), so a reanimation trigger's
    # ``ChangeZone(target=AttachedTo())`` — CR 303.4f: the Aura carries no
    # target filter of its own once attached, the type constraint lives
    # SOLELY on this printed keyword — can cross-reference the type this
    # ``AttachedTo`` binder implicitly restricts to (:func:`_creature_
    # recursion`'s own cross-ref). Empty for every non-Aura card and for an
    # Aura with a non-Enchant-typed keyword predicate this narrow read
    # doesn't resolve.
    card_enchant_core_types: tuple[str, ...] = ()

    def is_type(self, core: str) -> bool:
        """Whether the card itself has core type ``core`` (Creature / Land / …).

        The whole-card type gate the reanimator (is-creature) and ramp (is-land)
        lanes read off the typed ``card_type`` — never a re-grepped type line.
        """
        return core in self.card_types

    def iter_concepts(self) -> Iterator[ConceptNode]:
        """Every concept-node across every unit (the whole-card scan)."""
        for unit in self.units:
            yield from unit.iter_concepts()

    def effect_concepts(self, concept: str) -> tuple[ConceptNode, ...]:
        """Every role=effect concept-node named ``concept``, whole-card."""
        out: list[ConceptNode] = []
        for unit in self.units:
            out.extend(unit.effect_concepts(concept))
        return tuple(out)

    def has_effect(self, concept: str) -> bool:
        """Whether ANY unit has a role=effect concept named ``concept``."""
        return any(u.has_effect(concept) for u in self.units)


def iter_nested_token_effects(node: object) -> Iterator[ConceptNode]:
    """Every ``Token`` effect (CR 701.7 Create) reachable ANYWHERE under
    ``node`` — a token-maker buried inside a granted static/triggered
    ability (Presence of Gond's Aura grant, Squirrel Nest / Spawning
    Grounds / Leafdrake Roost's land-animator grants, "Commander creatures
    you own have '...'" — Veteran Soldier / Feywild Visitor), a
    ``CreateEmblem`` (Kiora, the Crashing Wave's -5 Kraken emblem), a Saga
    chapter (Urza's Saga's chapter II), or a dice-roll/coin-flip modal
    branch (Swarming Goblins, Bottle of Suleiman) — none of which the flat
    per-unit ``AbilityUnit`` walk ever surfaces as its own unit-level
    effect. Decorated the same way a top-level effect is
    (:func:`_decorate_effect`), so ``token_maker``'s existing scope/subject
    reads apply unchanged (CR 111.2: no explicit recipient field on the
    granted definition defaults to the activator, "you"). The
    :func:`has_nested_fight` / :func:`iter_nested_trigger_defs` sibling —
    corpus-verified no false hit off a token-COPY clause (``CopyTokenOf`` /
    ``Populate`` / ``BecomeCopy`` never nest a ``Token`` tag of their own,
    so the ``token_copy_makers`` boundary holds, CR 707).
    """
    for n in _iter_typed_nodes(node):
        if tag_of(n) != "Token":
            continue
        decorated = _decorate_effect(n, role="effect")
        if decorated is not None:
            yield decorated


def iter_nested_granted_effect_concepts(node: object) -> Iterator[ConceptNode]:
    """Every role=effect :class:`ConceptNode` reachable inside ANY granted-
    ability/trigger body under ``node`` (see :func:`iter_nested_granted_bodies`)
    — walks each yielded body through the SAME effect/sub_ability/execute/
    mode_abilities chain a top-level unit's own effects walk uses
    (:func:`_walk_effect_chain`), so a granted ABILITY's
    ``definition.effect`` (Arc Spitter's Equip-granted damage ability,
    Lavamancer's Skill / Pathway Arrows / Shuriken's Aura/Equipment-granted
    damage abilities) and a granted TRIGGER's ``execute.effect`` (Tyrant's
    Familiar's Lieutenant-granted attack trigger, Showstopper's until-end-
    of-turn dies-trigger grant) both decorate identically — a multi-step
    granted ability's ``sub_ability`` chain (Deadeye Navigator's soulbond
    exile-then-return: ``definition.effect`` is the Exile leg,
    ``definition.sub_ability.effect`` is the Battlefield-return leg)
    decorates too. task #86's ``direct_damage``/``removal``/
    ``blink_flicker`` structural fallback — the flat per-unit
    ``effect_concepts`` walk never surfaces any of these as a top-level
    concept of their own (CR 113.3 / 605 / 611).
    """
    for _kind, body in iter_nested_granted_bodies(node):
        yield from _walk_effect_chain(body)


# ── Batch-9 typed accessors (death / library-top / grant cluster) ────────────

# Effect targets that name the granted-trigger's OWN source object: the bare
# ``SelfRef`` (an undying/persist expansion — Young Wolf) and the granted-quote
# ``TriggeringSource`` (Feign Death's "return IT to the battlefield").
# ``ParentTarget`` is deliberately NOT here: it binds to the nearest ancestor
# that produced an object, which is the dying self only when no card-producer
# effect precedes it (Accursed Witch, Loyal Cathar) — after a producer it
# names the produced card (Matter Reshaper's revealed top card).
# :func:`is_dies_return_trigger` handles it explicitly with producer tracking.
_SELF_RETURN_TARGETS: frozenset[str] = frozenset({"SelfRef", "TriggeringSource"})

# Effects that introduce a NEW card object into a dies trigger's chain — a
# back-reference after one of these names the produced card, not the dying
# self (CR 702.93a/702.79a's "return it" is the dying object itself).
_CARD_PRODUCER_TAGS: frozenset[str] = frozenset(
    {"RevealTop", "Dig", "TurnFaceUp", "Search"}
)

# ADR-0038 W3 batch 2: the dies-return trigger's OWN watcher — a bare
# ``SelfRef`` (Young Wolf) or an Aura's ``AttachedTo`` ("enchanted creature
# dies" — Changing Loyalty, Fungal Fortitude, Journey to Eternity: the Aura
# grants the ENCHANTED creature dies-recursion, so the Aura itself is the
# dies_recursion card).
_DIES_RETURN_WATCHER_TAGS: frozenset[str] = frozenset({"SelfRef", "AttachedTo"})


def is_dies_return_trigger(trig: object) -> bool:
    """Whether a trigger node is the dies-self-return shape (CR 702.93a undying
    / 702.79a persist): "When this permanent dies, … return it to the
    battlefield".

    Reads the trigger's OWN typed shape — a dies event (``ChangesZone``
    Battlefield→Graveyard) watching ``SelfRef`` or an Aura's ``AttachedTo``
    (:data:`_DIES_RETURN_WATCHER_TAGS`), whose ``execute`` chain carries a
    ``ChangeZone`` back to the Battlefield targeting the same object
    (:data:`_SELF_RETURN_TARGETS` — directly, or one level down inside a
    ``CreateDelayedTrigger`` wrapper, which :func:`_walk_effect_chain`
    already descends into). Works on a card's own trigger unit (Young Wolf
    — undying parses to exactly this) AND on the granted trigger inside a
    ``GrantTrigger`` modification (Feign Death), so the dies_recursion lane
    walks both tree positions with one predicate. A dies→HAND return is NOT
    this shape (the destination gate).

    A ``valid_target`` naming a ``Player`` on the dies trigger ITSELF marks
    a player CHOICE somewhere in the ability (Accursed Witch's "return it
    … attached to TARGET OPPONENT" still returns it under YOUR control —
    only the attach point is chosen; Endless Whispers's "choose target
    opponent. That player puts this card … onto the battlefield UNDER
    THEIR CONTROL" hands the returned object itself to that opponent). The
    discriminator is the matched ChangeZone's own ``enters_under``: when a
    player was chosen, the return is only accepted if it explicitly says
    ``"You"`` — an ambiguous/opponent-owned return (Endless Whispers'
    ``enters_under`` is unset; legacy never fires dies_recursion there
    either) is excluded. Cards with NO player choice keep the plain
    self-return match (``enters_under`` unset defaults to CR 401.3's owner,
    always safe there since no OTHER player was ever named).
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if _trigger_event(trig) != "dies":
        return False
    if tag_of(getattr(trig, "valid_card", None)) not in _DIES_RETURN_WATCHER_TAGS:
        return False
    player_chosen = tag_of(getattr(trig, "valid_target", None)) == "Player"
    execute = getattr(trig, "execute", MISSING)
    if not isinstance(execute, TypedMirrorNode):
        return False
    # Phase's back-reference tags are POSITION-relative, so two shapes name a
    # NON-self object with a tag that elsewhere means the dying self
    # (verification catch on the W3-batch-2 unit-3 widening, corpus-diagnosed;
    # the lane's contract is CR 702.93a/702.79a's "return IT to the
    # battlefield" — the SAME object that died, per 603.6c's
    # leaves-the-battlefield reference — never a DIFFERENT card):
    #   * ``ParentTarget`` binds to the nearest ancestor that produced an
    #     object. With NO card-producer effect earlier in the chain, that
    #     ancestor is the trigger itself → the dying self (Accursed Witch's
    #     "return it … attached to target opponent"; Loyal Cathar's
    #     delayed-trigger "return it at the beginning of the next end
    #     step"). AFTER a producer (``RevealTop`` — Matter Reshaper's "put
    #     THAT CARD onto the battlefield"), it names the produced card —
    #     dies-VALUE, cheat_into_play's business, not recursion.
    #   * ``TriggeringSource`` next to a ``TurnFaceUp`` sibling is phase's
    #     loose back-ref to the face-down IMPRINTED card being turned up
    #     (Clone Shell, Summoner's Egg — the returned object never died).
    #     A ``Dig``/exile producer marks the same imprint indirection.
    delayed_ids: set[int] = set()
    for cn in _walk_effect_chain(execute):
        if tag_of(cn.node) == "CreateDelayedTrigger":
            delayed_ids.update(id(x.node) for x in _walk_effect_chain(cn.node))
    producer_seen = False
    for cn in _walk_effect_chain(execute):
        node = cn.node
        tag = tag_of(node)
        if tag in _CARD_PRODUCER_TAGS:
            producer_seen = True
            continue
        if tag != "ChangeZone":
            continue
        if getattr(node, "destination", None) != "Battlefield":
            # a dies→exile leg is NOT a producer: the phoenix class exiles
            # the dying SELF before returning it (Lamplight Phoenix) — the
            # later self-return must keep matching.
            continue
        target = tag_of(getattr(node, "target", None))
        in_delayed = id(node) in delayed_ids
        if target == "ParentTarget":
            if producer_seen and not in_delayed:
                continue  # binds to the produced card — not the dying self
        elif target not in _SELF_RETURN_TARGETS:
            continue
        if producer_seen and target == "TriggeringSource" and not in_delayed:
            continue  # imprint return — the face-down card, not the self
        if player_chosen and getattr(node, "enters_under", None) != "You":
            continue  # hot-potato — the return goes to the CHOSEN player
        return True
    return False


# ── overlay construction ──────────────────────────────────────────────────────


def _decorate_effect(node: object, role: str) -> ConceptNode | None:
    """Decorate one effect/cost typed node as a :class:`ConceptNode`.

    Returns ``None`` for an absent/scalar slot. An unrecognized tag decorates as
    ``OTHER`` carrying the verbatim node.
    """
    if not isinstance(node, TypedMirrorNode):
        return None
    t = tag_of(node)
    concept = EFFECT_CONCEPTS.get(t or "", OTHER)
    return ConceptNode(
        concept=concept,
        node=node,
        role=role,
        scope=_effect_scope(node),
        subject=_effect_subject(node),
        raw=_node_raw(node),
    )


def _walk_effect_chain(ability_like: TypedMirrorNode) -> Iterator[ConceptNode]:
    """Yield role=effect concepts reachable from one ability unit, depth-first.

    Decorates every tagged effect node reached through an effect-bearing field
    (``effect`` / ``sub_ability`` / ``execute`` / ``mode_abilities``) so a deeply
    nested terminal effect (a replacement's ``execute.effect`` win, a modal arm's
    loss) is still one of the unit's effects — the whole-unit aggregation the
    co-occurrence and whole-card lanes read. Cycle-safe (id-set + depth cap).
    """
    yield from _walk_effects(ability_like, 0, set())


def _walk_effects(node: object, depth: int, seen: set[int]) -> Iterator[ConceptNode]:
    if depth > 40 or not isinstance(node, TypedMirrorNode):
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    # A tagged node reached via an effect position IS an effect — decorate it.
    if tag_of(node) is not None:
        cn = _decorate_effect(node, "effect")
        if cn is not None:
            yield cn
    for fname in _EFFECT_CHILD_FIELDS:
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_effects(child, depth + 1, seen)
    modes = getattr(node, "mode_abilities", MISSING)
    if _present(modes) and isinstance(modes, list):
        for m in modes:
            if isinstance(m, TypedMirrorNode):
                yield from _walk_effects(m, depth + 1, seen)


def _player_scope_tag(ps: object) -> str | None:
    """The actor tag of a ``player_scope`` value (tagged node / variant / string)."""
    if isinstance(ps, TypedMirrorNode):
        return tag_of(ps)
    if isinstance(ps, MirrorVariant):
        return ps.key
    return ps if isinstance(ps, str) else None


def _find_owner_scope(
    node: object, target: object, depth: int, seen: set[int]
) -> str | None:
    if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
        return None
    seen.add(id(node))
    if getattr(node, "effect", MISSING) is target:
        return _player_scope_tag(getattr(node, "player_scope", MISSING))
    for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities"):
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            r = _find_owner_scope(child, target, depth + 1, seen)
            if r is not None:
                return r
        elif _present(child) and isinstance(child, list):
            for m in child:
                r = _find_owner_scope(m, target, depth + 1, seen)
                if r is not None:
                    return r
    return None


def effect_owner_player_scope(root: object, effect_node: object) -> str | None:
    """The ``player_scope`` actor tag on the ability wrapper that DIRECTLY owns
    ``effect_node`` (the wrapper whose ``.effect`` IS it), or ``None`` when that
    wrapper carries none.

    phase hangs ``player_scope`` ("each player / an opponent <does X>") on the
    wrapper whose ``effect`` is the resolving action — a trigger ``execute``, a
    sequential ``sub_ability``, a modal ``mode_abilities`` arm — NOT on the inner
    effect node the overlay decorates. Reading the scope of the wrapper that owns
    THIS effect (not a sibling's) tells a give-away / edict ("each player gains
    control", "each opponent sacrifices an enchantment") from a you-effect that
    merely shares a unit with an unrelated each-player action — Nihiloor's
    per-opponent tap loop (a ``repeat_for`` on the OUTER trigger, not the
    gain-control's wrapper), Garland's monarch vote. Typed-attr reads only;
    depth-capped, cycle-safe. ``None`` == owned by the ability's controller.
    """
    return _find_owner_scope(root, effect_node, 0, set())


def _cost_concepts(ability: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=cost concepts for an ability's activation cost (a single typed node)."""
    cost = getattr(ability, "cost", MISSING)
    cn = _decorate_effect(cost, "cost")
    return (cn,) if cn is not None else ()


def _spell_additional_cost_concepts(root: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=cost concepts from the card's ``additional_cost`` (CR 601.2b) — a
    spell-level "as an additional cost to cast this spell, sacrifice/discard/pay
    ..." clause the ability-unit walk never reaches (it lives on the root, not
    inside any ``S_abilities.cost``). ``additional_cost`` wraps its payload as
    Required/Optional/Choice/Kicker; :func:`iter_typed_nodes` deep-walks past
    that wrapper (and a Choice's alternative-cost list) to decorate every
    concrete cost leaf reached (Sacrifice — Costly Plunder, Trash for Treasure,
    Kuldotha Rebirth; a Choice arm — Bone Shards' "sacrifice a creature or
    discard a card").

    A ``PayLife`` leaf (Toxic Deluge's "pay X life", Bitter Triumph's
    "discard a card or pay 3 life" ``Choice`` arm) has no ``EFFECT_CONCEPTS``
    entry — it is a cost primitive, not a named effect — so it decorates
    ``concept=OTHER`` like any unrecognized tag; the ordinary OTHER filter
    below would silently drop it, and unlike Sacrifice/Discard it has NO
    other structural path back into ``unit.costs`` (:func:`cost_has_paylife`'s
    own ``.costs``-list recursion is built for a Composite cost's nested
    fields, not this wrapper's ``data``/``options`` shape), so a dropped
    PayLife leaf is invisible to every cost-reading lane, not just
    under-decorated. Kept explicitly (CR 119.4: paying life IS a cost) —
    every OTHER consumer of ``unit.costs`` filters by an explicit
    ``concept ==`` name (sacrifice / grant-cast-exile-evidence scans), so an
    admitted OTHER-concept PayLife node is inert everywhere except a raw
    node walk like :func:`cost_has_paylife`, exactly what
    ``lifeloss_makers``'s cost arm needs.
    """
    ac = getattr(root, "additional_cost", MISSING)
    if not isinstance(ac, TypedMirrorNode):
        return ()
    out: list[ConceptNode] = []
    for n in iter_typed_nodes(ac):
        if n is ac:
            continue
        cn = _decorate_effect(n, "cost")
        if cn is None:
            continue
        if cn.concept != OTHER or tag_of(n) in _PAYLIFE_COST_TAGS:
            out.append(cn)
    return tuple(out)


def _spell_alt_cost_paylife_concepts(root: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=cost ``PayLife`` concepts from the card's ALTERNATIVE casting
    cost(s) (CR 118.9) — Force of Will's "You may pay 1 life and exile a
    blue card from your hand rather than pay this spell's mana cost.",
    Snuff Out's "you may pay 4 life rather than pay this spell's mana
    cost." phase models an alternative cost as a root-level
    ``casting_options`` entry (``kind='AlternativeCost'``) — a DISTINCT
    field from ``additional_cost`` (CR 601.2b is paid ON TOP of the mana
    cost; an alternative cost REPLACES it) that NO existing crosswalk
    reader touches at all, so a PayLife leaf inside it has zero path back
    into ``unit.costs``. Narrow by construction: only a ``PayLife`` leaf is
    read (the one primitive ``lifeloss_makers``'s CR 119.4 cost arm needs);
    a general alt-cost concept surface (Composite's OTHER siblings —
    Force of Will's Exile leaf) is left for a future consumer to widen,
    same discipline as :func:`_spell_additional_cost_concepts`'s own
    PayLife carve-out.
    """
    opts = getattr(root, "casting_options", MISSING)
    if not _present(opts) or not isinstance(opts, list):
        return ()
    out: list[ConceptNode] = []
    for opt in opts:
        if not isinstance(opt, TypedMirrorNode):
            continue
        if getattr(opt, "kind", None) != "AlternativeCost":
            continue
        cost = getattr(opt, "cost", MISSING)
        if not isinstance(cost, TypedMirrorNode):
            continue
        for n in iter_typed_nodes(cost):
            if tag_of(n) in _PAYLIFE_COST_TAGS:
                cn = _decorate_effect(n, "cost")
                if cn is not None:
                    out.append(cn)
    return tuple(out)


def _keyword_cost_paylife_concepts(root: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=cost ``PayLife`` concepts inside a KEYWORD's own alternative-cost
    payload (CR 702 — Flashback/Warp/Blitz/Morph "Pay N life" variants) —
    Deep Analysis's "Flashback—{1}{U}, Pay 3 life.", Timeline Culler's
    "Warp—{B}, Pay 2 life.", Tenacious Underdog's "Blitz—{2}{B}{B}, Pay 2
    life.", Zombie Cutthroat's "Morph—Pay 5 life." Each keyword rides
    ``root.keywords`` as a ``MirrorVariant`` whose payload nests the cost
    (often a ``Composite`` mixing mana + PayLife, mirroring Flashback's own
    shape) — a THIRD root-level cost surface, distinct from both
    ``additional_cost`` and ``casting_options``, that no per-ability walk
    reaches (a keyword grants an alternative way to CAST the card, CR
    702.1, never an ability of its own). ``iter_typed_nodes`` accepts a
    ``MirrorVariant`` directly (it already unwraps ``.inner``), so a plain
    string keyword entry (Flying, Trample) simply yields nothing.

    Excludes the ``Ward`` keyword outright (CR 702.21a: "Whenever this
    permanent becomes the target of a spell or ability an OPPONENT
    controls, counter it unless THAT PLAYER pays [cost]") even though
    phase tags its own life-cost payload ``T_Ward__PayLife`` with the
    SAME "PayLife" discriminator string as every controller-paid variant:
    a Ward tax is paid by whoever TARGETS the permanent, never by this
    card's own controller, so admitting it here would misattribute an
    opponent's tax as this card's own life loss (Nine-Fingers Keene's
    "Ward-Pay 9 life").
    """
    kws = getattr(root, "keywords", MISSING)
    if not _present(kws) or not isinstance(kws, list):
        return ()
    out: list[ConceptNode] = []
    for kw in kws:
        if isinstance(kw, MirrorVariant) and kw.key == "Ward":
            continue
        for n in iter_typed_nodes(kw):
            if tag_of(n) in _PAYLIFE_COST_TAGS:
                cn = _decorate_effect(n, "cost")
                if cn is not None:
                    out.append(cn)
    return tuple(out)


def _keyword_effect_units(root: TypedMirrorNode) -> list[AbilityUnit]:
    """``AbilityUnit``\\s for a keyword's own EFFECT payload (CR 702).

    Cumulative Upkeep's "Add {R}" (Braid of Fire) rides ``root.keywords`` as
    an ``EffectCost``-tagged variant whose ``effect`` field is the payoff
    body — a tree position ``build_concept_tree``'s ``abilities`` /
    ``triggers`` / ``static_abilities`` / ``replacements`` walks never reach,
    so a card whose ONLY structured content lives here previously carried
    ZERO ability units (no arm could ever fire on it). Distinct from
    :func:`_keyword_cost_paylife_concepts` (role=cost, merges onto an
    ``"ability"``-origin Spell unit): this is the keyword's own role=effect
    body, decorated the same way any other origin's effect chain is
    (:func:`_walk_effect_chain`), so e.g. a ``Mana`` effect tag reads as the
    ordinary ``ramp`` concept.

    v0.23.0 corpus census: 9 commander-legal cards carry an ``EffectCost``
    keyword variant, all under ``CumulativeUpkeep`` — Aboroth (PutCounter),
    Braid of Fire (Mana), Herald of Leshrac (GainControl), Infernal
    Darkness (PayCost), Jötun Grunt (PutAtLibraryPosition), Karplusan
    Minotaur (FlipCoin), Psychic Vortex (Draw), Sheltering Ancient
    (PutCounter), Varchild's War-Riders (Token) — this origin decorates all
    9 the same structural way; only Braid of Fire's ``Mana`` tag maps to a
    ported concept (``ramp``) today, the rest surface as ``other`` until a
    future batch ports their own effect tags.
    """
    kws = getattr(root, "keywords", MISSING)
    if not _present(kws) or not isinstance(kws, list):
        return []
    out: list[AbilityUnit] = []
    i = 0
    for kw in kws:
        if not isinstance(kw, MirrorVariant):
            continue
        inner = kw.inner
        if not isinstance(inner, TypedMirrorNode) or tag_of(inner) != "EffectCost":
            continue
        effect = getattr(inner, "effect", MISSING)
        if not isinstance(effect, TypedMirrorNode):
            continue
        out.append(
            AbilityUnit(
                origin="keyword",
                index=i,
                node=inner,
                kind=tag_of(effect),
                trigger_event=None,
                effects=tuple(_walk_effect_chain(effect)),
                costs=(),
                statics=(),
            )
        )
        i += 1
    return out


# Modification tag → a coarse static-concept the land/anthem lanes read.
_MOD_CONCEPTS: dict[str, str] = {
    "AddPower": "pump",
    "AddToughness": "pump",
    "SetPower": "set_pt",
    "SetToughness": "set_pt",
    "AddType": "add_type",
    "AddKeyword": "grant_keyword",
}


def _static_concepts(static_ab: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=static concepts for a continuous ability's ``modifications``.

    Each modification carries the ability's ``affected`` filter as its subject so a
    per-ability aggregation (granularity b) can read the subject + the
    modification kind together (animate-land: a Land subject + an ``AddType
    Creature``).
    """
    affected = getattr(static_ab, "affected", MISSING)
    subject = _filter_type_words(affected) if _present(affected) else ()
    scope = "any"
    if _present(affected):
        sc = _scope_from_player_node(affected)
        if sc is not None:
            scope = sc
    out: list[ConceptNode] = []
    mods = getattr(static_ab, "modifications", MISSING)
    if _present(mods) and isinstance(mods, list):
        for mod in mods:
            if not isinstance(mod, TypedMirrorNode):
                continue
            concept = _MOD_CONCEPTS.get(tag_of(mod) or "", OTHER)
            out.append(
                ConceptNode(
                    concept=concept,
                    node=mod,
                    role="static",
                    scope=scope,
                    subject=subject,
                    raw=_node_raw(static_ab),
                )
            )
    return tuple(out)


def _nested_static_concepts(
    ability_like: TypedMirrorNode,
) -> tuple[ConceptNode, ...]:
    """Static-role concepts from a ``GenericEffect`` nested inside an ability.

    Phase wraps a one-shot / activated animate ("target land you control becomes a
    4/4 creature") as a ``GenericEffect`` effect carrying its ``target`` (the
    animated permanent's filter) plus nested ``static_abilities`` whose
    modifications confer the creature-ness. Harvesting them as ``static`` concepts
    — subject + scope taken from the ``GenericEffect``'s ``target`` — lets the
    per-ability aggregation (granularity b) reconstruct the animate-land split
    through a nested effect, the dominant animator shape.
    """
    out: list[ConceptNode] = []
    seen: set[int] = set()
    stack: list[object] = [ability_like]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities"):
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif _present(child) and isinstance(child, list):
                stack.extend(child)
        if tag_of(node) != "GenericEffect":
            continue
        target = getattr(node, "target", MISSING)
        subject = _filter_type_words(target) if _present(target) else ()
        scope = "any"
        if _present(target):
            sc = _scope_from_player_node(target)
            if sc is not None:
                scope = sc
        nested = getattr(node, "static_abilities", MISSING)
        if not (_present(nested) and isinstance(nested, list)):
            continue
        for st in nested:
            mods = getattr(st, "modifications", MISSING)
            if not (_present(mods) and isinstance(mods, list)):
                continue
            for mod in mods:
                if not isinstance(mod, TypedMirrorNode):
                    continue
                out.append(
                    ConceptNode(
                        concept=_MOD_CONCEPTS.get(tag_of(mod) or "", OTHER),
                        node=mod,
                        role="static",
                        scope=scope,
                        subject=subject,
                        raw=_node_raw(node),
                    )
                )
    return tuple(out)


def build_concept_tree(
    root: TypedMirrorNode, *, name: str = "", oracle_id: str = ""
) -> ConceptTree:
    """Build the tree-preserving concept overlay for one typed card root.

    ``root`` is an ``S_Root`` from ``strict_load_card(record, schema)``. Every
    ability of the card becomes an :class:`AbilityUnit` whose effects/costs/statics
    are decorated concept-nodes; unrecognized effects carry their verbatim node as
    ``other``.
    """
    oid = oracle_id or getattr(root, "scryfall_oracle_id", "") or ""
    nm = name or getattr(root, "name", "") or ""
    ct = getattr(root, "card_type", None)
    cores = getattr(ct, "core_types", None) if ct is not None else None
    card_types = tuple(c for c in cores if isinstance(c, str)) if cores else ()
    subs = getattr(ct, "subtypes", None) if ct is not None else None
    card_subtypes = tuple(s for s in subs if isinstance(s, str)) if subs else ()
    supers = getattr(ct, "supertypes", None) if ct is not None else None
    card_supertypes = tuple(s for s in supers if isinstance(s, str)) if supers else ()
    # Phase mana value (CR 202.3): generic + one per shard ("X" counts 1 in the
    # shard list — an accepted phase-vs-bulk cmc divergence, logged not chased).
    mc = getattr(root, "mana_cost", None)
    if isinstance(mc, TypedMirrorNode):
        generic = getattr(mc, "generic", 0)
        shards = getattr(mc, "shards", None) or []
        cmc = (generic if isinstance(generic, int) else 0) + len(shards)
    else:
        cmc = 0
    # b16: a REAL printed cost is phase's ``Cost`` node; transform backs / meld
    # results carry ``NoCost`` (mana value belongs to the front, CR 202.3b).
    has_printed_cost = isinstance(mc, TypedMirrorNode) and tag_of(mc) == "Cost"
    pw = getattr(root, "power", None)
    power: int | None = None
    if isinstance(pw, TypedMirrorNode) and tag_of(pw) == "Fixed":
        v = getattr(pw, "value", None)
        power = v if isinstance(v, int) else None
    # ADR-0039 W8: CR 100.2a copy-limit relaxation, read off the typed
    # ``deck_copy_limit`` union (mirrors old-IR ``card_ir._allows_many_copies``).
    dcl = getattr(root, "deck_copy_limit", None)
    many_copies = False
    if isinstance(dcl, TypedMirrorNode):
        dcl_tag = tag_of(dcl)
        if dcl_tag == "Unlimited":
            many_copies = True
        elif dcl_tag == "UpTo":
            dcl_data = getattr(dcl, "data", None)
            many_copies = isinstance(dcl_data, int) and dcl_data >= 2
    # task #87: the card's own printed ``Enchant`` keyword filter's core
    # type words (see ``ConceptTree.card_enchant_core_types``'s own
    # docstring) — a root-level array, never surfaced by any per-ability
    # unit walk.
    card_enchant_core_types: tuple[str, ...] = ()
    kws_root = getattr(root, "keywords", None)
    if isinstance(kws_root, list):
        for kw in kws_root:
            if isinstance(kw, MirrorVariant) and kw.key == "Enchant":
                card_enchant_core_types = filter_core_types(kw.inner)
                break
    # ADR-0039 grammar sprint (task #82): a modal SPELL's card-root
    # ``modal.mode_descriptions`` (CR 700.2), positionally paired with
    # ``root.abilities`` (Fatal Lore, Season of the Burrow) — see the
    # ``ConceptTree.card_modal_mode_descriptions`` field docstring.
    card_modal = getattr(root, "modal", None)
    card_modal_mode_descriptions: tuple[str, ...] = ()
    if isinstance(card_modal, TypedMirrorNode):
        cm_descs = getattr(card_modal, "mode_descriptions", None)
        if isinstance(cm_descs, list):
            card_modal_mode_descriptions = tuple(
                d for d in cm_descs if isinstance(d, str)
            )
    units: list[AbilityUnit] = []

    # A spell-level ``additional_cost`` (CR 601.2b) rides the ROOT, not any
    # ability's own ``cost`` — merge its cost concepts onto every Spell-kind
    # ability unit so the existing per-unit ``costs`` walk sees it (Costly
    # Plunder, Trash for Treasure, Kuldotha Rebirth).
    spell_ac_costs = _spell_additional_cost_concepts(root)
    spell_ac_attached = False
    # An alternative casting cost's PayLife leaf (CR 118.9 — see
    # :func:`_spell_alt_cost_paylife_concepts`) merges onto every Spell-kind
    # unit the SAME way, alongside (never instead of) the additional-cost
    # merge — a card can carry both (none in the corpus today, but nothing
    # about the two idioms is mutually exclusive: CR 601.2b/118.9 are
    # independent cost layers).
    alt_costs = _spell_alt_cost_paylife_concepts(root)
    alt_attached = False
    # A keyword's own alternative-cost PayLife leaf (CR 702 — Flashback's
    # "Pay N life" variant, see :func:`_keyword_cost_paylife_concepts`)
    # merges the SAME way — a FOURTH independent root-level cost surface
    # (``keywords``, distinct from ``additional_cost``/``casting_options``).
    kw_costs = _keyword_cost_paylife_concepts(root)
    kw_attached = False
    abilities = getattr(root, "abilities", ()) or ()
    for i, ab in enumerate(abilities):
        if not isinstance(ab, TypedMirrorNode):
            continue
        kind = getattr(ab, "kind", None)
        costs = _cost_concepts(ab)
        if kind == "Spell" and spell_ac_costs:
            costs = costs + spell_ac_costs
            spell_ac_attached = True
        if kind == "Spell" and alt_costs:
            costs = costs + alt_costs
            alt_attached = True
        if kind == "Spell" and kw_costs:
            costs = costs + kw_costs
            kw_attached = True
        units.append(
            AbilityUnit(
                origin="ability",
                index=i,
                node=ab,
                kind=kind,
                trigger_event=None,
                effects=tuple(_walk_effect_chain(ab)),
                costs=costs,
                statics=_nested_static_concepts(ab),
            )
        )
    if spell_ac_costs and not spell_ac_attached:
        # Dargo class: the root ``additional_cost`` exists but NO Spell-kind
        # ability entry does (a permanent whose only parsed ability is a
        # static/triggered rider — Dargo, the Shipwrecker's cost-reduction
        # static). Without a carrier the computed cost concepts were silently
        # dropped. Synthesize the Spell-kind carrier unit the merge above
        # needs; ``node`` is the verbatim ``additional_cost`` wrapper (the
        # preserved tree position), so the unit carries the SAME visibility
        # the merge path gives an existing Spell unit: the concepts ride
        # ``costs``, and ``node.cost`` stays absent on both paths (CR 601.2b —
        # an additional cost is part of casting the spell, not an activation
        # cost).
        ac_node = getattr(root, "additional_cost", MISSING)
        if isinstance(ac_node, TypedMirrorNode):
            units.append(
                AbilityUnit(
                    origin="ability",
                    index=len(abilities),
                    node=ac_node,
                    kind="Spell",
                    trigger_event=None,
                    effects=(),
                    costs=spell_ac_costs,
                    statics=(),
                )
            )
    if alt_costs and not alt_attached:
        # Same carrier shape for an alternative-cost-only card with no
        # Spell-kind ability entry (none in the corpus today — every current
        # alt-cost PayLife card also carries an ordinary Spell ability the
        # merge above already reaches — but the fallback keeps this reader
        # symmetric with the additional-cost carrier rather than silently
        # dropping a future such card).
        opts = getattr(root, "casting_options", MISSING)
        alt_node = None
        if _present(opts) and isinstance(opts, list):
            alt_node = next(
                (
                    o
                    for o in opts
                    if isinstance(o, TypedMirrorNode)
                    and getattr(o, "kind", None) == "AlternativeCost"
                ),
                None,
            )
        if alt_node is not None:
            units.append(
                AbilityUnit(
                    origin="ability",
                    index=len(abilities),
                    node=alt_node,
                    kind="Spell",
                    trigger_event=None,
                    effects=(),
                    costs=alt_costs,
                    statics=(),
                )
            )
    if kw_costs and not kw_attached:
        # Same carrier shape for a keyword-cost-only card with no Spell-kind
        # ability entry (Deep Analysis's own "draw two cards" ability
        # already absorbs its Flashback cost via the merge above — the
        # fallback exists for a hypothetical vanilla-permanent Flashback
        # card, keeping this reader symmetric with the other two carriers).
        # ``node`` is the PayLife leaf itself (``kw_costs[0].node`` — a real
        # ``TypedMirrorNode``, unlike the ``MirrorVariant`` keyword wrapper
        # the other carriers' ``additional_cost``/``casting_options`` roots
        # never need to unwrap).
        units.append(
            AbilityUnit(
                origin="ability",
                index=len(abilities),
                node=kw_costs[0].node,
                kind="Spell",
                trigger_event=None,
                effects=(),
                costs=kw_costs,
                statics=(),
            )
        )

    triggers = getattr(root, "triggers", ()) or ()
    for i, trig in enumerate(triggers):
        if not isinstance(trig, TypedMirrorNode):
            continue
        execute = getattr(trig, "execute", MISSING)
        effects = (
            tuple(_walk_effect_chain(execute))
            if isinstance(execute, TypedMirrorNode)
            else ()
        )
        units.append(
            AbilityUnit(
                origin="trigger",
                index=i,
                node=trig,
                kind=getattr(execute, "kind", None)
                if isinstance(execute, TypedMirrorNode)
                else None,
                trigger_event=_trigger_event(trig),
                effects=effects,
                costs=(),
                statics=_nested_static_concepts(execute)
                if isinstance(execute, TypedMirrorNode)
                else (),
            )
        )

    statics = getattr(root, "static_abilities", ()) or ()
    for i, st in enumerate(statics):
        if not isinstance(st, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="static",
                index=i,
                node=st,
                kind="static",
                trigger_event=None,
                effects=(),
                costs=(),
                statics=_static_concepts(st),
            )
        )

    replacements = getattr(root, "replacements", ()) or ()
    for i, rp in enumerate(replacements):
        if not isinstance(rp, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="replacement",
                index=i,
                node=rp,
                kind="replacement",
                trigger_event=None,
                effects=tuple(_walk_effect_chain(rp)),
                costs=(),
                statics=_nested_static_concepts(rp),
            )
        )

    units.extend(_keyword_effect_units(root))

    oracle = getattr(root, "oracle_text", None)
    tree = ConceptTree(
        name=nm,
        oracle_id=oid,
        units=tuple(units),
        card_types=card_types,
        card_subtypes=card_subtypes,
        card_supertypes=card_supertypes,
        cmc=cmc,
        power=power,
        has_printed_cost=has_printed_cost,
        oracle=oracle if isinstance(oracle, str) else "",
        many_copies=many_copies,
        card_modal_mode_descriptions=card_modal_mode_descriptions,
        card_enchant_core_types=card_enchant_core_types,
    )
    # ADR-0038 — substrate-wide Unimplemented recovery runs INSIDE the tree
    # build so every consumer (signal lanes, compat projection, convergence +
    # diff harnesses) sees recovered decorations; downstream
    # ``apply_overlay_corrections`` stays curated-wins (it runs later and
    # overwrites on conflict). No-op while the allowlist is empty.
    from mtg_utils._card_ir.recovery import apply_unimplemented_recovery

    return apply_unimplemented_recovery(tree)
