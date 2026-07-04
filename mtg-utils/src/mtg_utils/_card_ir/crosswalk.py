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
lives at Layer 3 in ``_deck_forge.crosswalk_signals``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, fields

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
# card_types (Emissary Green, Giant Opportunity). Mirrors ``_signals_ir``
# ``_ARTIFACT_TOKEN_SUBTYPES``.
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


@dataclass(frozen=True)
class AbilityUnit:
    """One ability of the card — the per-ability join scope (granularities a/b).

    A unit is one entry of phase's ``abilities`` (activated/spell/static-on-an-
    ability), ``triggers`` (a triggered ability — ``trigger_event`` derived from
    its ``mode`` + zone/recipient), ``static_abilities`` (a continuous ability —
    its ``modifications`` become ``static``-role concepts), or ``replacements``.
    ``node`` is the verbatim typed ability node (the preserved tree position).
    """

    origin: str  # "ability" | "trigger" | "static" | "replacement"
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


# ── scalar/typed-node helpers ─────────────────────────────────────────────────


def _present(v: object) -> bool:
    """A built optional field that is neither absent (MISSING) nor JSON-null."""
    return v is not MISSING and v is not None


def tag_of(node: object) -> str | None:
    """The discriminator tag of a typed tagged node (``None`` for struct/scalar)."""
    if isinstance(node, TypedMirrorNode):
        # ``_tag`` is the generated node's documented discriminator ClassVar (the
        # same field ``to_dict`` re-emits as ``"type"``) — the intended read.
        return type(node)._tag  # noqa: SLF001
    return None


# Recipient-bearing sub-fields an effect/trigger uses to name a player. Read in
# order; the first present one decides scope.
_SCOPE_FIELDS = ("target", "player", "owner", "recipient", "valid_target")


def _scope_from_player_node(node: object) -> str | None:
    """Map a player-reference typed node to a Signal scope, or None if unknown.

    Reads the node's discriminator tag (``Controller`` / ``Opponent`` / …) and,
    for a ``Typed`` filter, its ``controller`` — never oracle text.
    """
    t = tag_of(node)
    if t in ("Controller", "SelfRef", "You"):
        return "you"
    if t in ("Opponent", "Opponents", "EachOpponent"):
        return "opponents"
    if t in ("Each", "AllPlayers", "EachPlayer"):
        return "each"
    # A chosen/targeted player (``ParentTarget`` / ``Player`` / ``Any``) is NOT a
    # self resource — "target player draws, then discards" is a targeted effect,
    # not a self-loot outlet; the live self-loot lane scopes it out. Map to "any"
    # so a maker lane gated to you/each does not over-fire on it.
    if t in ("ParentTarget", "Player", "Any", "Target"):
        return "any"
    if t == "Typed":
        ctrl = getattr(node, "controller", None)
        if ctrl == "You":
            return "you"
        if ctrl == "Opponent":
            return "opponents"
        return "each"
    return None


def _effect_scope(node: TypedMirrorNode) -> str:
    """Derive a concept-node scope from an effect's recipient sub-fields."""
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            sc = _scope_from_player_node(sub)
            if sc is not None:
                return sc
    return "you"


def explicit_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The scope of an effect's EXPLICIT recipient field, or ``None`` if none present.

    Distinct from :func:`_effect_scope` (which defaults to "you" when phase carries
    no recipient): the self-loss-sustain lane must NOT read a default-"you" as a
    genuine self target (Gray Merchant's ``LoseLife`` has no ``target`` — the "each
    opponent loses" recipient lives on the trigger, not the node — so its scope is
    *unknown*, not self). ``None`` here means "no recipient on the node".
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            return _scope_from_player_node(sub)
    return None


# Recipient tags naming a player OTHER than the ability's controller: the
# triggering object's controller (``ParentTargetController``), the triggering
# player (``TriggeringPlayer``), or a chosen/targeted player (``ParentTarget`` /
# ``Player`` / ``Target`` / ``Any``). A loss aimed at one of these is a DIRECTED
# loss at another player (CR 119.3), never a self-loss.
_DIRECTED_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "ParentTargetController",
        "TriggeringPlayer",
        "ParentTarget",
        "Player",
        "Target",
        "Any",
    }
)


def lifeloss_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The DIRECTION of a life-loss effect (who loses) from its recipient node.

    Reads a ``LoseLife`` node's recipient/target player STRUCTURALLY (CR 119.3), so
    direction never rides phase's ``trigger_scope`` — which it MIS-scopes to ``you``
    for an ability triggered off an OPPONENT's object (Archfiend of the Dross
    "whenever a creature an opponent controls dies, its controller loses 2 life" —
    recipient ``ParentTargetController``; Ashenmoor Liege "that player loses 4 life"
    — recipient ``TriggeringPlayer``; phase bug [P5]). A controller/self recipient →
    ``you``; an each/all-player recipient → ``each``; an opponent recipient, or a
    RELATIVE/targeted one (the triggering object's controller / the triggering
    player / a targeted player) → ``opponents`` (a directed loss). ``None`` when the
    node carries NO recipient field — a bare self-loss (Agent Venom "you draw a card
    and lose 1 life", Dark Confidant's upkeep self-loss), so the caller falls back to
    the wrapper ``player_scope`` (Gray Merchant's "each opponent loses").
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        if tag_of(sub) in _DIRECTED_PLAYER_TAGS:
            return "opponents"
        sc = _scope_from_player_node(sub)
        if sc == "you":
            return "you"
        if sc == "each":
            return "each"
        return "opponents"
    return None


def trigger_constraint_tag(trig: TypedMirrorNode) -> str | None:
    """The discriminator tag of a trigger's ``constraint`` node, or ``None``.

    phase gates a trigger with a typed ``constraint``: the per-turn restrictions
    (``OnlyDuringYourTurn`` / ``OnlyDuringOpponentsTurn``) and the spell-velocity
    ``NthSpellThisTurn`` ("whenever you cast your second spell each turn" —
    Cori-Steel Cutter; the qualifier the OLD lossy projection dropped, forcing
    the live path onto a byte word-mirror). The batch-10 second-spell lane reads
    this tag + :func:`trigger_constraint_n` — a pure typed read (CR 603.2).
    """
    return tag_of(getattr(trig, "constraint", None))


def trigger_constraint_n(trig: TypedMirrorNode) -> int | None:
    """The ``n`` of a trigger's constraint (``NthSpellThisTurn`` → 2 for the
    second-spell form, 1 for "your first spell during each opponent's turn" —
    Alela, Cunning Conqueror, which the second-spell lane must NOT read as a
    velocity payoff). ``None`` when the constraint carries no ``n``.
    """
    n = getattr(getattr(trig, "constraint", None), "n", None)
    return n if isinstance(n, int) else None


def trigger_turn_constraint(trig: TypedMirrorNode) -> str | None:
    """The turn-restriction tag of a trigger's ``constraint`` (``OnlyDuringYourTurn``
    / ``OnlyDuringOpponentsTurn`` / ``None``).

    phase gates a per-turn trigger with a ``constraint`` node: an "each opponent's
    upkeep" trigger carries ``OnlyDuringOpponentsTurn`` (Sheoldred, Whispering One),
    a "your upkeep" trigger ``OnlyDuringYourTurn`` (Archfiend of the Dross), and an
    "each player's upkeep" trigger no constraint (Braids, Cabal Minion; Smokestack).
    The edict scope of a ``ScopedPlayer`` ("that player sacrifices") reads it to tell
    a symmetric each-player wrath from an opponent-only edict (CR 701.21a).
    """
    return trigger_constraint_tag(trig)


def trigger_damage_kind(trig: TypedMirrorNode) -> str:
    """The ``damage_kind`` of a damage trigger (``"CombatOnly"`` / ``"Any"``),
    ``""`` when absent.

    phase stamps every trigger with a ``damage_kind`` (default ``"Any"``); it is
    meaningful only on a ``DamageDone``-mode trigger, where it discriminates the
    combat-connect payoff ("deals combat damage to an opponent" — Coastal Piracy,
    CR 510.1b) from the any-damage connect ("deals damage to an opponent" —
    Hypnotic Specter, CR 120.3). The caller gates on the mode first.
    """
    dk = getattr(trig, "damage_kind", MISSING)
    return dk if isinstance(dk, str) else ""


def mana_restrictions(node: TypedMirrorNode) -> tuple[str, ...]:
    """The spend-restriction strings of a ``Mana`` effect (CR 106.4 / 106.6).

    phase carries "Spend this mana only …" as ``Mana.restrictions`` —
    ``"XCostOnly"`` (Rosheen Meanderer's "only on costs that contain {X}", the
    xspell-enabler arm), ``"ActivateOnly"``, ``"ChosenCreatureType"``,
    ``"SpellOnly"``. Empty when unrestricted.
    """
    rs = getattr(node, "restrictions", MISSING)
    if _present(rs) and isinstance(rs, (list, tuple)):
        return tuple(r for r in rs if isinstance(r, str))
    return ()


def effect_reaches_player(node: TypedMirrorNode) -> bool:
    """Whether a damage EFFECT reaches a PLAYER (CR 120.1), read structurally.

    The direct-damage / burn gate: a creature-only bite ("4 damage to target
    creature" — Flame Slash; "2 to each creature" — Pyroclasm) is removal, not burn.

    * ``DamageEachPlayer`` always hits players.
    * ``DamageAll`` hits players iff it carries a ``player_filter`` (Pestilence pings
      creatures AND each player; Pyroclasm-as-``DamageAll`` has none).
    * ``DealDamage`` hits a player iff its target is "any target"/a player node, or a
      ``Player``-typed filter — NOT a creature/permanent-typed filter, and NOT a
      bare self target ("deals 1 damage to you" painland).
    """
    t = tag_of(node)
    if t == "DamageEachPlayer":
        return True
    if t == "DamageAll":
        return _present(getattr(node, "player_filter", MISSING))
    if t == "DealDamage":
        tgt = getattr(node, "target", MISSING)
        if not _present(tgt):
            return False
        tt = tag_of(tgt)
        if tt == "Typed":
            words = _filter_type_words(tgt)
            return "Player" in words  # creature/permanent typed → removal
        if tt in ("Any", "Target", "ParentTarget"):
            return True
        # A CHOSEN / TRIGGERING player node reaches a player too — "deals X to
        # that player" where the player was chosen (Black Vise's
        # ``SourceChosenPlayer``) or triggered the effect (Booby Trap's
        # ``TriggeringPlayer``). ``_scope_from_player_node`` maps neither (they
        # are not a fixed you/opp/each scope), but both are burn recipients.
        if tt in _CHOSEN_PLAYER_TARGETS:
            return True
        sc = _scope_from_player_node(tgt)  # a direct player node
        return sc in ("opponents", "each", "any")
    return False


# Player-reference target tags that name a specific chosen / triggering player —
# a valid direct-damage recipient (CR 120.1) though not a fixed-scope node.
_CHOSEN_PLAYER_TARGETS: frozenset[str] = frozenset(
    {"SourceChosenPlayer", "TriggeringPlayer"}
)


def _type_filter_words(entries: object) -> list[str]:
    """Flatten one ``type_filters`` list to plain positive type words.

    Handles each entry kind: a bare ``str`` (``"Creature"``); a ``{Subtype: X}``
    wrapper (surfaced as ``X``); a ``{AnyOf: [...]}`` disjunction (recursed, so an
    "Assassin, Mercenary, … you control dies" — Rakish Crew — surfaces its inner
    creature subtypes, parallel to the ``Or`` recursion below); and a ``{Non: X}``
    NEGATION (CR 207.2c type words / 400.7), whose inner word is DROPPED — never
    flattened to the positive it negates (the reanimator-on-Astelli-Reclaimer,
    landfall-on-Brainstealer-Dragon / Builder's-Talent over-fires all stemmed from
    flattening ``{Non: Land}`` / ``{Non: Creature}`` to the positive type word).
    """
    out: list[str] = []
    if not isinstance(entries, (list, tuple)):
        return out
    for tf in entries:
        if isinstance(tf, str):
            out.append(tf)
        elif isinstance(tf, MirrorVariant):
            if tf.key == "Non":
                continue  # negation — drop the inner word
            if tf.key == "AnyOf" and isinstance(tf.inner, list):
                out.extend(_type_filter_words(tf.inner))  # disjunction — recurse
                continue
            inner = tf.inner
            out.append(inner if isinstance(inner, str) else tf.key)
    return out


def _filter_type_words(filt: object) -> tuple[str, ...]:
    """Flatten a typed filter's ``type_filters`` (str / ``{Subtype: X}`` / ``{AnyOf:
    [...]}`` / ``{Non: X}``) words.

    Recurses through ``Or`` / ``And`` filter nodes so a dual ``Creature``+``Land``
    or a ``{Subtype: Goblin}`` is surfaced as plain strings — the type-membership
    granularity reads these, not oracle text. Per-entry handling (Subtype / AnyOf /
    Non) lives in :func:`_type_filter_words`.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        out.extend(_type_filter_words(getattr(filt, "type_filters", ())))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(_filter_type_words(sub))
    return tuple(out)


def _effect_subject(node: TypedMirrorNode) -> tuple[str, ...]:
    """The type/subtype words an effect names (its filter or token types).

    A ``Token`` effect carries the token's ``types`` directly; other effects carry
    a ``subject`` / ``filter`` / ``target`` typed filter. Empty when none.
    """
    types = getattr(node, "types", MISSING)
    if _present(types) and isinstance(types, list):
        return tuple(t for t in types if isinstance(t, str))
    for fname in ("subject", "filter", "target", "affected"):
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            words = _filter_type_words(sub)
            if words:
                return words
    return ()


def _node_raw(node: TypedMirrorNode) -> str:
    """A grounding clause for a node — its ``description`` if present, else ``""``.

    Not identity-bearing (the diff keys on key/scope/subject); kept so a lane can
    surface a human-readable quote.
    """
    desc = getattr(node, "description", MISSING)
    return desc if isinstance(desc, str) else ""


# ── trigger-event derivation (provenance: phase ``mode`` + zone/recipient) ─────


def _trigger_event(trig: TypedMirrorNode) -> str:
    """Derive a normalized trigger event from a phase trigger's typed shape.

    Reads ``mode`` (a string discriminator) plus ``destination`` / ``origin`` for
    the overloaded ``ChangesZone`` mode — never oracle text.
    """
    mode = getattr(trig, "mode", None)
    mode = mode if isinstance(mode, str) else tag_of(mode) or "other"
    # ``ChangesZoneAll`` is the mass form of the same watcher ("whenever one
    # or more … are put into …" — The Gitrog Monster's land-dies trigger);
    # the zone derivation is identical (CR 603.6c).
    if mode in ("ChangesZone", "ChangesZoneAll"):
        dest = getattr(trig, "destination", None)
        origin = getattr(trig, "origin", None)
        if dest == "Battlefield":
            return "enters"
        if dest == "Graveyard" and origin in ("Battlefield", None):
            return "dies"
        return "changes_zone"
    return {
        "Drawn": "drawn",
        "Discarded": "discarded",
        # CR 702.29a: cycling IS "[Cost], Discard this card: Draw a card" —
        # a cycle is a discard, so the combined mode joins the discard event
        # (Archfiend of Ifnir); ``DiscardedAll`` is the mass watcher.
        "CycledOrDiscarded": "discarded",
        "DiscardedAll": "discarded",
        "LeavesBattlefield": "leaves",  # CR 603.6c — broader than dies
        "Explored": "explored",  # CR 701.44 — the explore PAYOFF watcher
        "RolledDie": "rolled_die",  # CR 706 — the roll PAYOFF watcher
        "RolledDieOnce": "rolled_die",
        "Attacks": "attacks",
        "YouAttack": "attacks",
        "SpellCast": "cast_spell",
        "DamageDone": "deals_damage",
        # CR 510.1b batched form — "whenever one or more [creatures you
        # control] deal (combat) damage to …" (Anowon, the Ruin Thief). Same
        # valid_target / valid_source / damage_kind shape as ``DamageDone``;
        # the live path fires the same combat-connect lanes on it (b10
        # follow-up d).
        "DamageDoneOnceByController": "deals_damage",
        "DamageReceived": "damage_received",  # the "is dealt damage" reflector
        "CounterAdded": "counter_added",
        "LifeGained": "life_gained",
        "LifeLost": "life_lost",  # lifeloss_matters (CR 119.3)
        "Taps": "taps",
        "Sacrificed": "sacrificed",
        "Exploited": "exploited",  # CR 702.110 — exploit IS a sacrifice payoff
        "BecomesTarget": "becomes_target",
        "BecomesBlocked": "becomes_blocked",
        "Blocks": "blocks",
    }.get(mode, mode.lower())


def trigger_scope(trig: TypedMirrorNode) -> str:
    """The scope a trigger watches (you/opponents/each) from its recipient field.

    For a player-event trigger (Drawn / Discarded / …) phase carries the watched
    player on ``valid_target``; ``you`` is the default when unmarked.
    """
    vt = getattr(trig, "valid_target", MISSING)
    if _present(vt):
        sc = _scope_from_player_node(vt)
        if sc is not None:
            return sc
    return "you"


def trigger_subject(trig: TypedMirrorNode) -> tuple[str, ...]:
    """Type-words of the OBJECT a trigger watches (its ``valid_card`` filter).

    Parallel to :func:`trigger_scope` (which reads the watched *player*): the
    death/landfall/token-ETB lanes need the watched OBJECT's types — "a creature
    dies", "a land you control enters", "a token you control enters". A bare
    ``SelfRef`` (When THIS dies) yields ``()`` so the self-death payoff stays out of
    the aristocrats lane. Recurses ``Or`` / ``And`` (Blood Artist's "this or another
    creature") so the real creature filter surfaces past the SelfRef arm.
    """
    vc = getattr(trig, "valid_card", MISSING)
    return _filter_type_words(vc) if _present(vc) else ()


def trigger_subject_scope(trig: TypedMirrorNode) -> str:
    """The watched OBJECT's controller scope (you/opponents/any) for a trigger.

    Reads ``valid_card``'s ``controller`` (a creature-you-control death vs an
    opponent's creature vs the symmetric any). An ``Or``/``And`` (Blood Artist —
    SelfRef OR another creature) or an unscoped filter is "any". Mirrors the old
    projection's ``trig.scope`` for the death lane (You→you, Opponent→opponents,
    null/mixed→any).
    """
    vc = getattr(trig, "valid_card", MISSING)
    if _present(vc):
        t = tag_of(vc)
        if t == "Typed":
            ctrl = getattr(vc, "controller", None)
            if ctrl == "You":
                return "you"
            if ctrl == "Opponent":
                return "opponents"
    return "any"


def filter_predicates(filt: object) -> tuple[str, ...]:
    """The PREDICATE tags of a typed filter (``Token`` / ``Counters`` / ``Tapped`` /
    ``Attacking`` / ``Another`` / ``NonToken`` …), read off its ``properties`` list.

    Distinct from :func:`_filter_type_words` (which flattens ``type_filters`` —
    Creature / Land): the token / go-wide lanes gate on the *property* a filter
    carries, not its card type ("Creature tokens you control", "creatures with a
    +1/+1 counter"). Recurses ``Or`` / ``And`` like the type-word read. Generic and
    reusable (the Tapped / Attacking / Counters predicates land here for later
    batches).
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            pt = tag_of(prop)
            if pt is not None:
                out.append(pt)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_predicates(sub))
    return tuple(out)


def filter_without_keywords(filt: object) -> tuple[str, ...]:
    """The keyword names a typed filter EXCLUDES via ``WithoutKeyword``
    properties ("creature without flanking" — the flanking template's blocker
    filter, CR 702.25a). The value-level companion to
    :func:`filter_predicates`, which returns only the property TAGS. Recurses
    ``Or`` / ``And`` like the other filter reads.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "WithoutKeyword":
                v = getattr(prop, "value", None)
                if isinstance(v, str):
                    out.append(v)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_without_keywords(sub))
    return tuple(out)


def effect_filter(node: TypedMirrorNode) -> object | None:
    """The typed FILTER node an effect names (``subject`` / ``filter`` / ``target`` /
    ``affected``), or ``None``.

    Distinct from :func:`_effect_subject` (which flattens a filter to plain type
    words and special-cases a token's ``types`` list): the type-payoff / predicate
    lanes need the filter NODE itself to read its controller, core-vs-subtype split,
    and predicates (:func:`filter_controller` / :func:`filter_core_types` /
    :func:`filter_subtypes` / :func:`filter_predicates`).
    """
    for fname in ("subject", "filter", "target", "affected"):
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            return sub
    return None


def count_operand_filter(node: TypedMirrorNode) -> object | None:
    """The FILTER of an effect's dynamic count operand (``Ref`` → ``ObjectCount``).

    A scaling value ("draw a card for each artifact you control" — Inspiring Call;
    "+X/+X where X is the number of creatures you control" — Craterhoof) carries the
    counted population on ``amount`` / ``count`` / ``value`` as a ``Ref`` whose
    ``qty`` is an ``ObjectCount`` with a ``filter``. The type/counter-matters lanes
    read that counted set's filter — the operand the old projection dropped.
    """
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if not _present(q) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                return filt
    return None


def count_distinct_operand_filter(node: TypedMirrorNode) -> object | None:
    """The FILTER of a DISTINCT-count operand (``Ref`` → ``ObjectCountDistinct``).

    The sibling of :func:`count_operand_filter` for the "for each **differently
    named** ~ you control" scaler (Audience with Trostani — draw = the number of
    differently-named creature tokens you control). phase carries the counted
    population on the same ``amount`` / ``count`` / ``value`` ``Ref`` but under an
    ``ObjectCountDistinct`` qty (a distinct ``qualities`` dimension). Kept a SEPARATE
    helper so widening it never moves the lanes that read the plain ObjectCount form.
    """
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if not _present(q) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCountDistinct":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                return filt
    return None


def filter_controller(filt: object) -> str | None:
    """The phase ``controller`` of a typed filter (``"You"`` / ``"Opponent"`` /
    ``None``), recursing ``Or`` / ``And`` to the first that names one.
    """
    t = tag_of(filt)
    if t == "Typed":
        c = getattr(filt, "controller", None)
        return c if isinstance(c, str) else None
    if t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            c = filter_controller(sub)
            if c is not None:
                return c
    return None


def filter_core_types(filt: object) -> tuple[str, ...]:
    """The CORE card-type words of a typed filter (bare strings — ``Creature`` /
    ``Artifact`` / ``Permanent``), EXCLUDING subtype / ``Non`` / ``AnyOf`` wrappers.

    The complement of :func:`filter_subtypes`. The generic-board / type-matters gates
    read core types (no subtype) — a ``{Subtype: Equipment}`` entry is NOT a core
    type. Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, str):
                out.append(tf)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_core_types(sub))
    return tuple(out)


def filter_subtypes(filt: object) -> tuple[str, ...]:
    """The SUBTYPE words of a typed filter (``{Subtype: Equipment}`` → ``Equipment``;
    ``{AnyOf: [...]}`` recursed), EXCLUDING bare core types and ``Non`` negations.

    The voltron / tribal gates read subtypes; the generic-board gate requires the
    subtype set EMPTY. Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, MirrorVariant):
                if tf.key == "Subtype":
                    inner = tf.inner
                    out.append(inner if isinstance(inner, str) else tf.key)
                elif tf.key == "AnyOf" and isinstance(tf.inner, list):
                    for e in tf.inner:
                        if isinstance(e, MirrorVariant) and e.key == "Subtype":
                            out.append(e.inner if isinstance(e.inner, str) else e.key)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_subtypes(sub))
    return tuple(out)


def counter_pred_kinds(filt: object) -> tuple[str, ...]:
    """The counter KINDS a filter's ``Counters`` predicates reference (``"P1P1"`` /
    ``"M1M1"`` / ``"Any"`` …), EXCLUDING the ``EQ 0`` "with NO counter" inverse.

    Mirrors ``_signals_ir._counter_pred_kinds`` over the typed predicate: a
    ``Counters`` property carries ``comparator`` + ``count`` + ``counters``
    (``{OfType: <kind>}`` for a named kind, else the kind-agnostic "any counter"
    form → ``"Any"``). The +1/+1 / -1/-1 / any-counter payoff lanes route by kind.
    Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "Counters":
                continue
            cmp_ = getattr(prop, "comparator", None)
            cnt = getattr(prop, "count", None)
            val = getattr(cnt, "value", None) if cnt is not None else None
            if cmp_ == "EQ" and val == 0:
                continue  # "with NO counter" — the inverse, not a payoff
            counters = getattr(prop, "counters", None)
            if tag_of(counters) == "OfType":
                data = getattr(counters, "data", None)
                out.append(data if isinstance(data, str) else "Any")
            else:
                out.append("Any")
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(counter_pred_kinds(sub))
    return tuple(out)


def color_count_preds(filt: object) -> tuple[tuple[str, int], ...]:
    """The ``(comparator, count)`` pairs of a filter's ``ColorCount`` predicates.

    Mirrors the OLD-IR ``ColorCount:<CMP>:<N>`` predicate string (CR 105.2): a
    ``ColorCount`` property carries ``comparator`` (``GE`` / ``EQ`` / …) + ``count``
    (an int). The multicolor (``GE``≥2 / ``EQ``≥2) and colorless (``EQ`` 0)
    build-around lanes route by it. Recurses ``Or`` / ``And``.
    """
    out: list[tuple[str, int]] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "ColorCount":
                continue
            cmp_ = getattr(prop, "comparator", None)
            cnt = getattr(prop, "count", None)
            if isinstance(cmp_, str) and isinstance(cnt, int):
                out.append((cmp_, cnt))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(color_count_preds(sub))
    return tuple(out)


def power_threshold_preds(filt: object) -> tuple[tuple[str, str, int], ...]:
    """The ``(stat, comparator, value)`` triples of a filter's FIXED ``PtComparison``
    predicates (CR 208.1).

    Mirrors the OLD-IR ``PtComparison:Power:GE:4`` predicate string but EXCLUDES the
    dynamic form (the old ``:*`` tail — a relative "power less than this creature's"
    fight-style check, whose ``value`` is a ``Ref``/``Difference``, not a ``Fixed``).
    Only a ``Fixed`` value yields a triple; the high-power (GE/GT) and low-power
    (LE/LT) lanes split on the comparator direction. Recurses ``Or`` / ``And``.
    """
    out: list[tuple[str, str, int]] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "PtComparison":
                continue
            val = getattr(prop, "value", None)
            if tag_of(val) != "Fixed":
                continue  # dynamic / relative comparison — not a fixed theme floor
            stat = getattr(prop, "stat", None)
            cmp_ = getattr(prop, "comparator", None)
            v = getattr(val, "value", None)
            if isinstance(stat, str) and isinstance(cmp_, str) and isinstance(v, int):
                out.append((stat, cmp_, v))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(power_threshold_preds(sub))
    return tuple(out)


def player_counter_kind(node: TypedMirrorNode) -> str:
    """The ``counter_kind`` of a ``GivePlayerCounter`` effect (``"Rad"`` /
    ``"Experience"`` / ``"Poison"`` …), normalized to a string (``""`` when absent).

    A player-resource counter (CR 122.1 / 728) is given to a PLAYER, not placed on a
    permanent — phase carries the kind directly on ``GivePlayerCounter.counter_kind``.
    The rad / experience maker lanes route by it (the OLD lossy IR split the giver
    into per-kind effect categories; this reads the kind off the typed node).
    """
    ck = getattr(node, "counter_kind", MISSING)
    return ck if isinstance(ck, str) else ""


def count_operand_qty(node: TypedMirrorNode) -> object | None:
    """The QTY node of an effect's dynamic count operand, or ``None``.

    Two shapes carry a named scaler (CR 700.5 devotion / 700.6 domain / 700.8 party,
    or a player-counter count): a ``Ref``-wrapped operand on ``amount`` / ``count`` /
    ``value`` (``Ref.qty`` — the same path :func:`count_operand_filter` reads, but
    returning the qty itself rather than its ``ObjectCount`` filter), and a direct
    ``dynamic_count`` on a static P/T modification (``AddDynamicPower`` — "+X/+X where
    X is your devotion"). Returns the qty node so a lane can read its discriminator
    tag (:func:`tag_of`) plus its ``controller`` / ``player`` / ``kind`` fields.
    """
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if _present(q) and tag_of(q) == "Ref":
            qty = getattr(q, "qty", None)
            if isinstance(qty, TypedMirrorNode):
                return qty
    dc = getattr(node, "dynamic_count", MISSING)
    if isinstance(dc, TypedMirrorNode):
        return dc
    return None


# Recipient tags marking a discard DIRECTED at another player (CR 701.9): a targeted
# player ("target player / opponent discards" — Mind Rot, Stupor), or an explicit
# opponent. A you/controller recipient is a self-loot (the ported ``discard_makers``
# lane), not this hand-attack.
_DISCARD_OPP_TAGS: frozenset[str] = frozenset(
    {
        "Player",
        "Target",
        "ParentTarget",
        "Any",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TargetPlayer",
        "TriggeringPlayer",
        "ParentTargetController",
    }
)
_DISCARD_EACH_TAGS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})


def recipient_tag(node: TypedMirrorNode) -> str | None:
    """The discriminator tag of an effect's FIRST present recipient sub-field, or
    ``None``.

    The raw tag (``ParentTarget`` / ``Player`` / ``Controller`` / ``Opponent`` …)
    behind :func:`_effect_scope` — exposed so a lane can tell a directed-player loot
    (a "target player draws, then discards" whose draw + discard share the SAME
    targeted player — Cephalid Looter) from a one-sided hand attack.
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if _present(sub) and tag_of(sub) is not None:
            return tag_of(sub)
    return None


def discard_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The DIRECTION of a ``Discard`` effect (who discards) from its recipient node.

    The ``opponent_discard`` gate (CR 701.9). Mirrors the OLD-IR ``_discard_player_
    scope`` promotion: a targeted "target player discards" (recipient ``Player``) is a
    forced opponent-hand attack → ``opponents``; an explicit opponent recipient →
    ``opponents``; a symmetric "each player discards" wheel → ``each`` (it hits
    opponents too); a you/controller recipient (a self-loot — Faithless Looting) →
    ``you`` (NOT this lane); ``None`` when the node carries no recipient field. Reads
    the discard's OWN recipient STRUCTURALLY, never phase's mis-scoped trigger scope.
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        t = tag_of(sub)
        if t in _DISCARD_EACH_TAGS:
            return "each"
        if t in _DISCARD_OPP_TAGS:
            return "opponents"
        if t == "Typed":
            ctrl = getattr(sub, "controller", None)
            if ctrl == "Opponent":
                return "opponents"
            if ctrl == "You":
                return "you"
            return "each"
        sc = _scope_from_player_node(sub)
        if sc == "you":
            return "you"
        if sc == "each":
            return "each"
        return "opponents"
    return None


def change_zone_dirs(node: TypedMirrorNode) -> tuple[str | None, str | None]:
    """``(origin, destination)`` of a ``ChangeZone`` EFFECT, the same fields
    :func:`_trigger_event` reads on the trigger side.

    Reanimation is ``(Graveyard, Battlefield)``; a blink exile is
    ``(_, Exile)`` and its return ``(_, Battlefield)``. Exposing them on the effect
    side lets the GY-engine / flicker lanes read the zone change STRUCTURALLY rather
    than from a post-hoc recovered field.
    """
    return (
        getattr(node, "origin", None),
        getattr(node, "destination", None),
    )


def additional_phase_kind(node: TypedMirrorNode) -> str:
    """The lowercased ``phase`` of an ``AdditionalPhase`` effect (CR 505 / 506), or
    ``""`` when absent.

    Phase carries the granted extra phase on ``AdditionalPhase.phase``
    (``"BeginCombat"`` — Aurelia, Moraug, Combat Celebrant). The ``extra_combats``
    lane gates on it being a combat phase, mirroring ``project._EXTRA_PHASE``: phase
    v0.9.0 only structurally emits a combat phase here (it mis-routes
    extra-upkeep/draw/end to combat, recovered by a separate ``project`` marker), so
    the combat read mirrors the live ``extra_combats`` exactly.
    """
    p = getattr(node, "phase", MISSING)
    return p.lower() if isinstance(p, str) else ""


def modify_cost_mode(static_node: TypedMirrorNode) -> str | None:
    """The ``mode`` of a static ability's ``ModifyCost`` (``"Reduce"`` / ``"Raise"`` /
    ``"Minimum"``), or ``None`` when the static is not a cost modifier.

    Phase models a cost modifier (CR 601.2f / 118.7) as a ``static_ability`` whose
    ``mode`` field is a ``{ModifyCost: S_ModifyCost}`` variant (the ``modifications``
    list is empty — the cost change rides ``mode``, not a P/T modification). The
    ``cost_reduction`` lane reads the inner ``S_ModifyCost.mode`` STRUCTURALLY to
    gate direction — a ``Raise`` tax (Thalia) is excluded without the live path's raw
    ``_COST_INCREASE`` screen. ``None`` for any non-``ModifyCost`` static.
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "ModifyCost":
        inner_mode = getattr(mode.inner, "mode", None)
        return inner_mode if isinstance(inner_mode, str) else None
    return None


def control_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The scope of a control-change effect's ``recipient`` (who GAINS control), or
    ``None`` when the node carries no recipient.

    A ``GiveControl`` (CR 110.2) hands a permanent YOU control to ``recipient`` — a
    targeted player (``Player`` → ``"any"`` — Donate, Bazaar Trader) or an explicit
    opponent (``Typed controller=Opponent`` → ``"opponents"`` — Harmless Offering).
    The ``donate_makers`` give-away gate (checklist #2) reads the ``recipient`` node
    directly — NOT :func:`explicit_recipient_scope`, which reads the donated
    permanent's own ``target`` filter first and mis-returns ``"you"``. Reading the
    recipient SPECIFICALLY isolates the beneficiary the OLD lossy IR dropped.
    """
    rcp = getattr(node, "recipient", MISSING)
    if not _present(rcp):
        return None
    return _scope_from_player_node(rcp)


def counter_kind(node: TypedMirrorNode) -> str:
    """The ``counter_type`` of a counter-placing effect (``"P1P1"`` / ``"Loyalty"`` /
    ``"Oil"`` …), normalized to a string (``""`` when absent).

    The discriminator that keeps a +1/+1 placement (``plus_one_makers``) apart from
    loyalty / oil / shield / charge placements (their own lanes). CR 122.1.
    """
    ck = getattr(node, "counter_type", MISSING)
    return ck if isinstance(ck, str) else ""


def amount_is_scaling(node: TypedMirrorNode, field: str = "amount") -> bool:
    """Whether an effect's ``field`` (``amount`` / ``count``) is a DYNAMIC quantity.

    A ``Fixed`` value is a constant magnitude; anything else (``Ref`` over a
    devotion / power / object-count / multiply) scales with the board — the
    "significant engine" signal a one-shot fixed rider lacks (Dark Confidant's
    lose-life-equal-to-mana-value vs Infernal Grasp's fixed "lose 2 life").
    """
    q = getattr(node, field, MISSING)
    if not _present(q):
        return False
    return tag_of(q) not in ("Fixed", None)


def amount_factor(node: TypedMirrorNode, field: str = "amount") -> int:
    """The fixed magnitude of an effect's ``field`` (``1`` when dynamic/absent).

    The acceleration / upkeep-bleed gates read it (Sol Ring's ``{C}{C}`` count 2,
    a recurring upkeep loss ≥ 2). A dynamic quantity returns ``1`` (its magnitude
    is read via :func:`amount_is_scaling` instead).
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Fixed":
        v = getattr(q, "value", None)
        if isinstance(v, int):
            return v
    return 1


def pump_is_negative(node: TypedMirrorNode) -> bool:
    """Whether a ``Pump`` / ``PumpAll`` effect is a SHRINK (CR 613.4c) — a negative
    fixed ``power`` or ``toughness`` (Bile Blight's -3/-3, a -X/-X mass shrink).

    The ``Pump`` effect carries ``power`` / ``toughness`` as ``Fixed`` sub-nodes
    (distinct from the static ``AddPower`` mod's plain-int ``value``); a negative
    value is a debuff (CR 613.4c), a positive one a buff (an anthem). A dynamic /
    variable amount is NOT read here (it has no fixed sign to gate on).
    """
    for fname in ("power", "toughness"):
        sub = getattr(node, fname, MISSING)
        if _present(sub) and tag_of(sub) == "Fixed":
            v = getattr(sub, "value", None)
            if isinstance(v, int) and v < 0:
                return True
    return False


def mod_value(node: TypedMirrorNode) -> int | None:
    """The plain-int ``value`` of a static P/T modification (``AddPower`` /
    ``SetToughness`` …), or ``None`` when absent/dynamic.

    The static mods carry a bare-int ``value`` (Glorious Anthem's +1, Humility's
    set-to-1), unlike the ``Pump`` effect's ``Fixed``-wrapped ``power``/``toughness``.
    The base-P/T-shrink debuff gate (a SET ≤ 2 on opponents/symmetric) reads it.
    """
    v = getattr(node, "value", MISSING)
    return v if isinstance(v, int) else None


# Cost component tags that constitute a self life-payment (CR 118.8) — "Pay N life".
_PAYLIFE_COST_TAGS: frozenset[str] = frozenset({"PayLife"})


def cost_has_paylife(node: object, *, depth: int = 0) -> bool:
    """Whether an activation-cost node pays life (CR 118.8), recursing ``Composite``.

    Phase nests a ``Pay N life`` cost as a ``PayLife`` node, often inside a
    ``Composite`` cost (mana + life — Erebos's ``{1}{B}, Pay 2 life``). The
    lifeloss-maker cost arm reads it through the composite the single top-level
    cost-concept decoration does not flatten.
    """
    if depth > 8 or not isinstance(node, TypedMirrorNode):
        return False
    if tag_of(node) in _PAYLIFE_COST_TAGS:
        return True
    costs = getattr(node, "costs", MISSING)
    if _present(costs) and isinstance(costs, list):
        return any(cost_has_paylife(c, depth=depth + 1) for c in costs)
    return False


def damage_recipient_is_player(vt: object) -> bool:
    """Whether a combat-damage TRIGGER's recipient (``valid_target``) is a PLAYER an
    aggressor reaches — an OPPONENT / generic / targeted player (CR 510.1c).

    The ``combat_damage_to_opp`` gate. A ``Player`` / planeswalker / opponent / generic
    targeted player IS a reachable player; a ``Typed`` filter naming ``Creature`` (or
    any core type that is not Player/Planeswalker) is a CREATURE recipient (Ohran
    Viper's first trigger → the to-creature lane). A ``Controller`` / ``You`` /
    ``SelfRef`` recipient is "deals combat damage to YOU" — a DEFENSIVE trigger
    (Contested War Zone, Norn's Decree; phase also MISLABELS some "to a player"
    triggers as ``Controller``, a phase-parse bug the live path excludes too), NOT this
    aggressive lane. A bare ``Typed`` filter with no core type words (a controller-only
    reference — Coastal Piracy's "an opponent") IS a reachable player.
    """
    t = tag_of(vt)
    if t in (
        "Player",
        "Any",
        "Target",
        "ParentTarget",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "Each",
        "AllPlayers",
        "EachPlayer",
    ):
        return True
    if t == "Typed":
        ctrl = getattr(vt, "controller", None)
        if ctrl == "You":
            return False
        cores = filter_core_types(vt)
        if not cores:
            return True
        return "Player" in cores or "Planeswalker" in cores
    return False


# Static-restriction modes that force a creature to be blocked (CR 509.1c lure).
_LURE_MODES: frozenset[str] = frozenset({"MustBeBlocked", "MustBeBlockedByAll"})


def permission_tag(node: TypedMirrorNode) -> str | None:
    """The tag of a ``GrantCastingPermission`` effect's ``permission`` sub-node.

    Phase models "you may play those cards" / plot as a ``GrantCastingPermission``
    effect carrying a ``permission`` node — ``PlayFromExile`` (impulse exile-and-
    play — Act on Impulse, Abbot of Keral Keep) or ``Plotted`` (CR 702.170 plot —
    Aloe Alchemist). The cast-from-exile lane reads that tag STRUCTURALLY (the live
    path kept a byte-identical word-mirror; this is the fidelity gain of batch 5).
    """
    return tag_of(getattr(node, "permission", None))


# Condition-wrapper fields that nest an inner condition (CR boolean glue):
# ``Not`` carries ``condition``; ``ConditionInstead`` carries ``inner``; an
# ``And`` / ``Or`` of conditions carries ``conditions``. Walked so a leaf
# condition tag (``IsMonarch`` …) buried under a wrapper still surfaces.
_CONDITION_INNER_FIELDS = ("inner", "condition", "conditions")
# Ability-wrapper fields a ``condition`` can hang off, recursively: a trigger's
# ``execute`` Spell, a sequential ``sub_ability``, a nested ``effect``, modal
# ``mode_abilities`` arms, a ``GenericEffect``'s ``static_abilities``.
_CONDITION_CARRIER_FIELDS = ("effect", "sub_ability", "execute")


def _walk_condition_subtree(cond: object, depth: int, seen: set[int]) -> Iterator[str]:
    """Yield every condition-node tag reachable from one ``condition`` value."""
    if depth > 20 or not isinstance(cond, TypedMirrorNode) or id(cond) in seen:
        return
    seen.add(id(cond))
    t = tag_of(cond)
    if t is not None:
        yield t
    for fname in _CONDITION_INNER_FIELDS:
        child = getattr(cond, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_condition_subtree(child, depth + 1, seen)
        elif _present(child) and isinstance(child, list):
            for c in child:
                yield from _walk_condition_subtree(c, depth + 1, seen)


def _walk_unit_conditions(node: object, depth: int, seen: set[int]) -> Iterator[str]:
    """Yield condition-node tags from every ``condition`` field under one unit node.

    Descends the ability-wrapper chain (``effect`` / ``sub_ability`` / ``execute``
    / ``mode_abilities`` / nested ``static_abilities``) so a condition on a
    trigger's ``execute`` Spell (Court of Ambition, Sauron) or a continuous
    ability (Gloom Stalker, Nadaar) surfaces alongside one on the wrapper itself
    (Brimstone Vandal, Imoen). Cycle-safe (id-set + depth cap).
    """
    if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
        return
    seen.add(id(node))
    cond = getattr(node, "condition", MISSING)
    if isinstance(cond, TypedMirrorNode):
        yield from _walk_condition_subtree(cond, 0, set())
    for fname in (*_CONDITION_CARRIER_FIELDS, "mode_abilities", "static_abilities"):
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_unit_conditions(child, depth + 1, seen)
        elif _present(child) and isinstance(child, list):
            for m in child:
                yield from _walk_unit_conditions(m, depth + 1, seen)


def condition_tags(tree: ConceptTree) -> frozenset[str]:
    """Every condition-node tag present anywhere on the card (whole-card scan).

    The additive primitive the batch-5 ``*_matters`` lanes read: a payoff GATED on
    a designation/state (``IsMonarch`` / ``CompletedADungeon`` / ``IsInitiative`` /
    ``IsRingBearer`` …) carries a typed ``condition`` node the crosswalk's
    effect/cost/static decoration does not surface. These leaf tags are unique to
    conditions (no effect shares the name), so a tag-membership scan is precise.
    """
    out: set[str] = set()
    for unit in tree.units:
        out.update(_walk_unit_conditions(unit.node, 0, set()))
    return frozenset(out)


def node_lure_mode(node: object) -> bool:
    """Whether a typed node carries a "must be blocked" lure mode (CR 509.1c).

    Phase encodes Lure as a static ability whose ``mode`` is ``MustBeBlockedByAll``,
    conferred via an ``AddStaticMode`` modification carrying the same ``mode``. Either
    surface marks the all-creatures-must-block requirement the lure lane reads (a
    single-creature ``ForceBlock`` — Academic Dispute — is a narrower provoke-style
    effect, NOT this lane).
    """
    if not isinstance(node, TypedMirrorNode):
        return False
    mode = getattr(node, "mode", None)
    return isinstance(mode, str) and mode in _LURE_MODES


# ── Batch-8 typed accessors (removal / card-flow / library-top cluster) ──────


def static_mode_tag(node: object) -> str | None:
    """The MODE discriminator of a static ability (CR 604.3), across shapes.

    Phase's static ``mode`` is a plain string for the common forms
    (``"Continuous"`` / ``"MayLookAtTopOfLibrary"``) and a variant wrapper for
    the parameterized ones (``{TopOfLibraryCastPermission: …}`` — Bolas's
    Citadel, Future Sight; ``{ModifyCost: …}`` — the cost_reduction seam). The
    play_from_top lane reads the variant KEY so the ongoing top-play permission
    is a pure typed read (the live path needed a recovered ``from:library``
    zone marker).
    """
    mode = getattr(node, "mode", MISSING)
    if isinstance(mode, str):
        return mode
    if isinstance(mode, MirrorVariant):
        return mode.key
    if isinstance(mode, TypedMirrorNode):
        return tag_of(mode)
    return None


def mana_replacement_multiplier(node: TypedMirrorNode) -> int:
    """The ``Multiply`` factor of a ``ProduceMana`` replacement's
    ``mana_modification`` (CR 106.4 / 614.1) — Mana Reflection x2, Virtue of
    Strength x3. ``0`` when the node is not a mana-multiplier replacement, so
    the mana_amplifier lane can gate on ``>= 2``.
    """
    mm = getattr(node, "mana_modification", MISSING)
    if _present(mm) and tag_of(mm) == "Multiply":
        f = getattr(mm, "factor", None)
        return f if isinstance(f, int) else 2
    return 0


def produced_contribution(node: TypedMirrorNode) -> str:
    """The ``contribution`` of a ``Mana`` effect's ``produced`` spec (CR 106.4).

    Phase marks the triggered "whenever you tap a <land> for mana, add an
    additional {B}" doublers (Crypt Ghast, Nirkana Revenant) with
    ``produced.contribution == "Additional"`` — the extra mana rides ON TOP of
    the tap's own production. ``""`` when absent (a plain producer).
    """
    p = getattr(node, "produced", MISSING)
    if not _present(p):
        return ""
    c = getattr(p, "contribution", MISSING)
    return c if isinstance(c, str) else ""


def counter_kind_any(node: TypedMirrorNode) -> str:
    """``counter_type`` normalized UPPER across BOTH phase shapes (CR 122.1).

    An EFFECT-side counter node carries a plain string kind (``"M1M1"`` /
    ``"fade"``); a COST-side ``RemoveCounter`` carries a tagged node —
    ``{OfType: "P1P1"}`` (Walking Ballista's remove-as-cost) or the kindless
    ``{Any}`` (Power Conduit) → ``"ANY"``. ``""`` when absent. The
    counter_manipulation lane routes by the normalized kind.
    """
    ck = getattr(node, "counter_type", MISSING)
    if isinstance(ck, str):
        return ck.upper()
    if isinstance(ck, TypedMirrorNode):
        t = tag_of(ck)
        if t == "OfType":
            data = getattr(ck, "data", None)
            return data.upper() if isinstance(data, str) else ""
        return (t or "").upper()
    return ""


def iter_cost_leaves(node: object, *, depth: int = 0) -> Iterator[TypedMirrorNode]:
    """Leaf cost nodes of an activation cost, recursing ``Composite`` /
    ``OneOf`` ``costs`` lists (the same nesting :func:`cost_has_paylife`
    walks). A ``{B}, Remove a -1/-1 counter from ~:`` composite (Carnifex
    Demon) yields its ``Mana`` AND ``RemoveCounter`` leaves; a bare cost
    yields itself.
    """
    if depth > 8 or not isinstance(node, TypedMirrorNode):
        return
    costs = getattr(node, "costs", MISSING)
    if _present(costs) and isinstance(costs, list):
        for c in costs:
            yield from iter_cost_leaves(c, depth=depth + 1)
        return
    yield node


def ref_qty_tag(node: TypedMirrorNode, field: str) -> str | None:
    """The qty-node discriminator tag of a ``Ref``-wrapped ``field``, or
    ``None`` when the field is absent / not a ``Ref``.

    The scaling-count lanes (draw_for_each / scaling_pump / count_anthem) read
    the tag to tell a board-count scaler (``ObjectCount`` — Shamanic
    Revelation, Craterhoof) from a bare X-spell (``Variable`` — Braingeyser,
    CR 107.3).
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Ref":
        qty = getattr(q, "qty", None)
        return tag_of(qty)
    return None


def ref_count_qty(node: TypedMirrorNode, field: str) -> str | None:
    """The board-count qty tag of a ``Ref`` value, unwrapping a ``Multiply``.

    A dynamic P/T modification can hide its counted-object ``Ref`` under a
    ``Multiply`` scalar: "gets +2/+2 for each Aura attached to it" projects
    ``Multiply(factor=2, inner=Ref(ObjectCount(...)))`` (Champion of the Flame,
    Auramancer's Guise). :func:`ref_qty_tag` reads only a bare ``Ref``; this
    variant unwraps the scalar first so the scaling-pump read reaches the count.
    ``None`` when ``field`` is not a (possibly scaled) ``Ref``.
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Multiply":
        q = getattr(q, "inner", None)
    if _present(q) and tag_of(q) == "Ref":
        return tag_of(getattr(q, "qty", None))
    return None


def ref_count_filter(node: TypedMirrorNode, field: str) -> object | None:
    """The counted-object filter inside a (``Multiply``-wrapped) ``Ref`` →
    ``ObjectCount`` value at ``node.field``, or ``None``.

    The voltron read of a dynamic self-pump ("+X/+X for each Aura/Equipment
    attached to it" — Champion of the Flame) needs the ``AttachedToRecipient``
    ``ObjectCount`` filter, which the value's ``Multiply`` scalar hides from
    :func:`effect_filter` / :func:`count_operand_filter`. Returns ``None``
    unless the value resolves to a ``Ref`` over an ``ObjectCount``.
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Multiply":
        q = getattr(q, "inner", None)
    if _present(q) and tag_of(q) == "Ref":
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            return getattr(qty, "filter", None)
    return None


def iter_mod_sites(
    root: object,
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    """``(static_def, modification)`` pairs reachable from one unit node.

    Covers BOTH continuous-ability shapes: a top-level static (the unit node
    itself carries ``modifications`` — Glorious Anthem, Commander's Insignia)
    and the one-shot ``GenericEffect``-nested static defs a spell/trigger
    confers (Craterhoof's "gain trample and get +X/+X" — nested
    ``static_abilities`` whose defs carry their OWN ``affected``). The
    anthem / scaling-pump / team-buff lanes read the def's ``affected`` filter
    together with each modification (granularity b). Cycle-safe, depth-capped.
    """
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        mods = getattr(node, "modifications", MISSING)
        if _present(mods) and isinstance(mods, list):
            for mod in mods:
                if isinstance(mod, TypedMirrorNode):
                    yield node, mod
        for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities", "static_abilities"):
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif _present(child) and isinstance(child, list):
                stack.extend(child)


def filter_inzone_zones(filt: object) -> tuple[str, ...]:
    """The zones named by a filter's ``InZone`` properties (CR 400.7),
    recursing ``Or`` / ``And``. The exile_removal zone gate reads them: an
    "exile … from a graveyard" subject carries ``InZone: Graveyard`` — GY-hate,
    not battlefield removal.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "InZone":
                z = getattr(prop, "zone", None)
                if isinstance(z, str):
                    out.append(z)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_inzone_zones(sub))
    return tuple(out)


def filter_owned_controller(filt: object) -> str | None:
    """The ``controller`` of a filter's ``Owned`` property (CR 108.3), or
    ``None``. ``Owned: You`` marks an exile of YOUR OWN object — the
    blink-your-own tell the exile_removal lane must exclude (the object comes
    back, CR 603.6e). Recurses ``Or`` / ``And``.
    """
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "Owned":
                c = getattr(prop, "controller", None)
                return c if isinstance(c, str) else ""
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            c = filter_owned_controller(sub)
            if c is not None:
                return c
    return None


# ── Batch-9 typed accessors (death / library-top / grant cluster) ────────────

# Effect targets that name the granted-trigger's OWN source object: the bare
# ``SelfRef`` (an undying/persist expansion — Young Wolf) and the granted-quote
# ``TriggeringSource`` (Feign Death's "return IT to the battlefield").
_SELF_RETURN_TARGETS: frozenset[str] = frozenset({"SelfRef", "TriggeringSource"})


def is_dies_return_trigger(trig: object) -> bool:
    """Whether a trigger node is the dies-self-return shape (CR 702.93a undying
    / 702.79a persist): "When this permanent dies, … return it to the
    battlefield".

    Reads the trigger's OWN typed shape — a dies event (``ChangesZone``
    Battlefield→Graveyard) watching ``SelfRef``, whose ``execute`` chain
    carries a ``ChangeZone`` back to the Battlefield targeting the same object
    (``SelfRef`` / ``TriggeringSource``). Works on a card's own trigger unit
    (Young Wolf — undying parses to exactly this) AND on the granted trigger
    inside a ``GrantTrigger`` modification (Feign Death), so the
    dies_recursion lane walks both tree positions with one predicate. A
    dies→HAND return is NOT this shape (the destination gate).
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if _trigger_event(trig) != "dies":
        return False
    if tag_of(getattr(trig, "valid_card", None)) != "SelfRef":
        return False
    execute = getattr(trig, "execute", MISSING)
    if not isinstance(execute, TypedMirrorNode):
        return False
    for cn in _walk_effect_chain(execute):
        if tag_of(cn.node) != "ChangeZone":
            continue
        if getattr(cn.node, "destination", None) == "Battlefield" and (
            tag_of(getattr(cn.node, "target", None)) in _SELF_RETURN_TARGETS
        ):
            return True
    return False


def mod_keyword_name(mod: TypedMirrorNode) -> str | None:
    """The keyword NAME of an ``AddKeyword`` modification, across both shapes.

    A plain evergreen grant carries a bare string (``"Trample"`` — the
    team_buff read); a PARAMETERIZED grant carries a variant wrapper whose key
    is the keyword name (``{Flashback: <cost>}`` — Snapcaster Mage's targeted
    flashback grant, CR 702.34). ``None`` when absent / not a keyword node.
    """
    kw = getattr(mod, "keyword", MISSING)
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def token_profile_keywords(node: object) -> tuple[str, ...]:
    """The keyword NAMES a ``Token`` effect's profile carries (CR 111.4).

    A token profile's ``keywords`` list mixes bare strings (``"Flying"``)
    with parameterized variants whose KEY is the keyword name (Dragon
    Broodmother's ``{Devour: 2}``, Chromanticore's bestow token) — the same
    two shapes :func:`mod_keyword_name` normalizes. ``()`` for a non-Token
    node. The has_devour / has_changeling token-profile tails read this
    (grow-on-demand: only the batch-13 lanes consume it today).
    """
    if not isinstance(node, TypedMirrorNode) or tag_of(node) != "Token":
        return ()
    kws = getattr(node, "keywords", MISSING)
    if not _present(kws) or not isinstance(kws, list):
        return ()
    out: list[str] = []
    for kw in kws:
        if isinstance(kw, str):
            out.append(kw)
        elif isinstance(kw, MirrorVariant):
            out.append(kw.key)
        elif isinstance(kw, TypedMirrorNode):
            t = tag_of(kw)
            if t is not None:
                out.append(t)
    return tuple(out)


def cast_with_keyword_name(static_node: TypedMirrorNode) -> str | None:
    """The keyword a ``CastWithKeyword`` static confers on casts, or ``None``.

    Phase models "you may cast spells as though they had flash" / "<class>
    spells you cast have <keyword>" as a static whose ``mode`` is a
    ``{CastWithKeyword: {keyword: …}}`` variant (Leyline of Anticipation —
    ``Flash``; Chief Engineer — ``Convoke``). The keyword itself is a plain
    string or a parameterized variant (``{Affinity: …}``) — the KEY is the
    name. ``None`` for any other static mode (CR 601.3e).
    """
    mode = getattr(static_node, "mode", MISSING)
    if not (isinstance(mode, MirrorVariant) and mode.key == "CastWithKeyword"):
        return None
    kw = _variant_field(mode.inner, "keyword")
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def _variant_field(inner: object, field: str) -> object:
    """One named field of a variant's INNER payload, across both loads.

    A single-field payload loads as a nested ``MirrorVariant`` whose key IS
    the field name (``{RevealHand: {who: "Opponents"}}`` →
    ``MirrorVariant(key="who", inner="Opponents")``); a multi-field payload
    loads as a typed struct read by attribute. ``None`` when absent.
    """
    if isinstance(inner, MirrorVariant):
        return inner.inner if inner.key == field else None
    v = getattr(inner, field, MISSING)
    return v if _present(v) else None


def static_reveal_who(static_node: TypedMirrorNode) -> str | None:
    """The revealed PLAYER of a ``RevealHand`` static mode, or ``None``.

    Phase models "players play with their hands revealed" as a static whose
    ``mode`` is ``{RevealHand: {who: …}}`` — ``who`` ∈ ``Controller`` (Enduring
    Renewal's self-reveal) / ``Opponents`` (Telepathy) / ``AllPlayers`` (Zur's
    Weirding). The hand_disruption lane gates on the reveal reaching an
    opponent's hand (CR 402.3).
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "RevealHand":
        who = _variant_field(mode.inner, "who")
        return who if isinstance(who, str) else None
    return None


# ── Batch-10 typed accessors (trigger-event / grant / static-mode cluster) ───


def double_triggers_cause_core_types(
    static_node: TypedMirrorNode,
) -> tuple[str, ...] | None:
    """The ``core_types`` of a ``DoubleTriggers`` static's ``EntersBattlefield``
    cause, or ``None`` when the static is not an ETB-cause trigger doubler.

    phase models "an [artifact or creature / permanent] entering … causes a
    triggered ability … to trigger an additional time" as a static whose ``mode``
    is ``{DoubleTriggers: {cause: {EntersBattlefield: {core_types: […]}}}}``
    (Panharmonicon — ``["Artifact", "Creature"]``; Yarok / Elesh Norn — ``[]``,
    the any-PERMANENT form, which subsumes creatures). A non-ETB cause (``Any`` —
    Strionic Resonator; ``CreatureDying`` — Teysa Karlov) and any other static
    return ``None`` — those still open ``trigger_doubling`` via
    :func:`static_mode_tag`, but carry no creature-ETB evidence. CR 603.2 +
    Panharmonicon's 2021-03-19 ruling.
    """
    mode = getattr(static_node, "mode", MISSING)
    if not (isinstance(mode, MirrorVariant) and mode.key == "DoubleTriggers"):
        return None
    cause = _variant_field(mode.inner, "cause")
    if not (isinstance(cause, MirrorVariant) and cause.key == "EntersBattlefield"):
        return None
    cores = _variant_field(cause.inner, "core_types")
    if isinstance(cores, (list, tuple)):
        return tuple(c for c in cores if isinstance(c, str))
    return ()


def _is_static_def(node: object) -> bool:
    """Whether a typed node is a static-ability DEF (carries the ``affected`` +
    ``modifications`` field pair — a trigger/ability wrapper carries neither)."""
    return (
        isinstance(node, TypedMirrorNode)
        and getattr(node, "affected", MISSING) is not MISSING
        and getattr(node, "modifications", MISSING) is not MISSING
    )


def iter_static_defs(root: object) -> Iterator[TypedMirrorNode]:
    """Every static-ability DEF node reachable from one unit node.

    Yields the unit node itself when it IS a def (a top-level continuous
    ability — Warmonger Hellkite's "All creatures attack each combat if able")
    plus every def inside a nested ``GenericEffect.static_abilities`` list (the
    one-shot conferred form). The modification-less MODE statics
    (``MustAttack`` / ``DoubleTriggers`` / ``CantBeCountered``) never surface
    through :func:`iter_mod_sites` (no modifications to pair with), so the
    mode-read lanes walk defs directly via :func:`static_mode_tag`.
    Cycle-safe, same traversal as :func:`iter_mod_sites`.
    """
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        if _is_static_def(node):
            yield node
        for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities", "static_abilities"):
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif _present(child) and isinstance(child, list):
                stack.extend(child)


def _iter_typed_nodes(root: object) -> Iterator[TypedMirrorNode]:
    """Every typed node reachable from ``root`` via dataclass fields /
    variant payloads / lists — the generic deep walk behind the narrow
    unique-tag scans (cycle-safe, field-order agnostic)."""
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, TypedMirrorNode):
            yield node
            for f in fields(node):
                stack.append(getattr(node, f.name))
        elif isinstance(node, MirrorVariant):
            stack.append(node.inner)
        elif isinstance(node, list):
            stack.extend(node)


def iter_threaded_target_statics(
    ability_like: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, static_def)`` pairs for every
    ``ParentTarget``-affected nested static in one ability/trigger chain, the
    target THREADED through the chain.

    Mirrors the live v14 tracked-target walk over the typed substrate: phase
    parses "target creature gains <kw> / becomes a 1/1" as a ``GenericEffect``
    whose nested static's ``affected`` is ``ParentTarget``, with the real
    target riding the ``GenericEffect``'s own ``target`` (Jump, Gods Willing)
    or an EARLIER effect's target the static re-references — the "It gains X"
    / "It becomes a 0/0" idiom ("Untap target creature. It gains reach" — Aim
    High; Cyclone Sire's land animate), resolved by threading the most recent
    non-ParentTarget filter through the ``effect`` / ``sub_ability`` /
    ``execute`` chain. Callers apply their own gates on the resolved filter.
    """
    tracked: object | None = None
    seen: set[int] = set()
    queue: list[object] = [ability_like]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        execute = getattr(node, "execute", MISSING)
        if isinstance(execute, TypedMirrorNode):
            queue.append(execute)
        eff = getattr(node, "effect", MISSING)
        if isinstance(eff, TypedMirrorNode) and id(eff) not in seen:
            seen.add(id(eff))
            tgt = getattr(eff, "target", MISSING)
            if _present(tgt) and tag_of(tgt) in ("Typed", "Or", "And"):
                tracked = tgt
            if tag_of(eff) == "GenericEffect" and tracked is not None:
                nested = getattr(eff, "static_abilities", MISSING)
                sts = nested if _present(nested) and isinstance(nested, list) else []
                for st in sts:
                    if tag_of(getattr(st, "affected", None)) == "ParentTarget":
                        yield tracked, st
            sub2 = getattr(eff, "sub_ability", MISSING)
            if isinstance(sub2, TypedMirrorNode):
                queue.append(sub2)
        sub = getattr(node, "sub_ability", MISSING)
        if isinstance(sub, TypedMirrorNode):
            queue.append(sub)


def iter_single_target_grants(
    ability_like: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, AddKeyword_mod)`` pairs for the SINGLE-TARGET
    keyword grants of one SPELL/ability node (CR 700.2) — the AddKeyword
    projection of :func:`iter_threaded_target_statics`, mirroring the live v14
    ``_single_target_keyword_grant_markers`` emit. The caller applies the live
    gates (Creature core on the resolved filter; abilities only — the
    trigger-conferred grants ride the DEEP local-target arm).
    """
    for tracked, st in iter_threaded_target_statics(ability_like):
        mods = getattr(st, "modifications", MISSING)
        for mod in mods if _present(mods) and isinstance(mods, list) else []:
            if tag_of(mod) == "AddKeyword":
                yield tracked, mod


def iter_deep_target_grants(
    root: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(local_target_filter, AddKeyword_mod)`` pairs for every
    ``GenericEffect`` leaf under ``root`` with a LOCAL Typed target and a
    ``ParentTarget``-affected AddKeyword static.

    Mirrors the live DEEP marker (``project._deep_single_target_grant``
    shapes): the same leaf phase structures for a trigger-conferred grant
    ("target artifact creature you control … gains indestructible" —
    Aethershield Artificer), a modal arm, a Saga chapter, or a quoted
    GrantAbility definition — the flat threaded walk
    (:func:`iter_single_target_grants`) never descends there. LOCAL target
    only (the "It gains X" tracked idiom stays with the flat walk, exactly
    the live split). CR 700.2.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "GenericEffect":
            continue
        tgt = getattr(n, "target", MISSING)
        if not _present(tgt) or tag_of(tgt) not in ("Typed", "Or", "And"):
            continue
        nested = getattr(n, "static_abilities", MISSING)
        for st in nested if _present(nested) and isinstance(nested, list) else []:
            if tag_of(getattr(st, "affected", None)) != "ParentTarget":
                continue
            mods = getattr(st, "modifications", MISSING)
            for mod in mods if _present(mods) and isinstance(mods, list) else []:
                if tag_of(mod) == "AddKeyword":
                    yield tgt, mod


def spell_count_at_least(root: object) -> int:
    """The largest ``count`` of any ``YouCastSpellCountAtLeast`` condition on
    the card (``0`` when none).

    phase gates "Activate only if you've cast two or more spells this turn"
    (Xerex Strobe-Knight) as an activation-restriction condition ``{type:
    YouCastSpellCountAtLeast, count: 2}`` — the CONDITION form of the
    second-spell velocity payoff (the trigger form rides the
    ``NthSpellThisTurn`` constraint, :func:`trigger_constraint_tag`). The tag
    is unique to conditions, so the deep typed scan is precise. CR 601.
    """
    best = 0
    for n in _iter_typed_nodes(root):
        if tag_of(n) == "YouCastSpellCountAtLeast":
            c = getattr(n, "count", None)
            if isinstance(c, int) and c > best:
                best = c
    return best


def spell_velocity_static_two(root: object) -> bool:
    """True when a ``QuantityComparison`` gates a payoff on "you've cast two or
    more spells this turn" — ``lhs`` a ``Ref`` over ``SpellsCastThisTurn``
    (``scope: Controller``), comparator ``GE`` with ``rhs == 2`` (or the
    equivalent ``GT`` / ``rhs == 1``).

    The STATIC-CONDITION form of second_spell_matters (b3 recall): Brightspear
    Zealot's "gets +2/+0 as long as you've cast two or more spells this turn"
    hangs the count on a continuous-ability ``condition`` — a
    ``QuantityComparison`` — distinct from the ``YouCastSpellCountAtLeast``
    activation restriction (:func:`spell_count_at_least`, the Xerex Strobe-Knight
    "activate only if" form) and the ``NthSpellThisTurn`` trigger constraint
    (:func:`trigger_constraint_tag`, the Cori-Steel Cutter "your second spell"
    form). The threshold is pinned to exactly two-or-more so a "three or more
    spells" velocity payoff (Arclight Phoenix — a broader lane, not the
    second-spell counter) never fires, and the ``Controller`` scope excludes an
    opponent-cast watcher (Captain Mar-Vell). CR 603.2.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "QuantityComparison":
            continue
        lhs = getattr(n, "lhs", None)
        qty = getattr(lhs, "qty", None) if lhs is not None else None
        if qty is None or tag_of(qty) != "SpellsCastThisTurn":
            continue
        if getattr(qty, "scope", None) != "Controller":
            continue
        comp = getattr(n, "comparator", None)
        rhs = getattr(n, "rhs", None)
        rv = getattr(rhs, "value", None) if rhs is not None else None
        if (comp == "GE" and rv == 2) or (comp == "GT" and rv == 1):
            return True
    return False


# ── Batch-11 typed accessors (replacement / damage-trigger / tap / library) ──


def replacement_event_tag(node: TypedMirrorNode) -> str:
    """The ``event`` of a replacement node (``"CreateToken"`` / ``"AddCounter"``
    / ``"DamageDone"`` / ``"Moved"`` …), ``""`` when absent. CR 614.1a — the
    event discriminator splits the token / counter / damage doubler lanes.
    """
    ev = getattr(node, "event", MISSING)
    return ev if isinstance(ev, str) else ""


def replacement_qty_mod(node: TypedMirrorNode) -> tuple[str, int] | None:
    """``(kind, n)`` of a replacement's ``quantity_modification``, or ``None``.

    phase types the CR 614 quantity rewrites as a tagged node — ``Times``
    (factor: Doubling Season x2), ``Plus`` (value: Hardened Scales +1),
    ``Minus`` (Vizier of Remedies), ``Prevent``, ``Half``. The doubler lanes
    gate on the INCREASE kinds; a reducer/denial never fires.
    """
    qm = getattr(node, "quantity_modification", MISSING)
    if not _present(qm):
        return None
    t = tag_of(qm)
    if t is None:
        return None
    f = getattr(qm, "factor", None)
    v = getattr(qm, "value", None)
    n = f if isinstance(f, int) else (v if isinstance(v, int) else 0)
    return (t, n)


def replacement_damage_mod(node: TypedMirrorNode) -> str | None:
    """The tag of a replacement's ``damage_modification`` (``Double`` /
    ``Triple`` / ``Plus`` / ``Minus`` / ``LifeFloor`` …), or ``None`` when the
    node carries none (a pure prevention/redirect shield — Palisade Giant).
    CR 614.1a + 120.3.
    """
    return tag_of(getattr(node, "damage_modification", None))


def replacement_counter_match(node: TypedMirrorNode) -> str:
    """The counter KIND a replacement's ``counter_match`` names (``"P1P1"`` /
    ``"M1M1"``), ``""`` when kindless/absent. CR 122.1.
    """
    cm = getattr(node, "counter_match", MISSING)
    if _present(cm) and tag_of(cm) == "OfType":
        d = getattr(cm, "data", None)
        return d if isinstance(d, str) else ""
    return ""


def replacement_shield_kind(node: TypedMirrorNode) -> str | None:
    """The tag of a replacement's ``shield_kind`` (``Prevention`` — the CR 615
    prevention-shield membership on a DamageDone replacement, Palisade Giant
    family), or ``None``. Deliberately does NOT read ``redirect_target`` —
    the redirect lane is a settled KEPT (phase drops the redirect side on all
    but 8 corpus replacements).
    """
    sk = getattr(node, "shield_kind", MISSING)
    if isinstance(sk, MirrorVariant):
        return sk.key
    if isinstance(sk, TypedMirrorNode):
        return tag_of(sk)
    return None


def replacement_token_owner_scope(node: TypedMirrorNode) -> str:
    """The ``token_owner_scope`` of a ``CreateToken`` replacement (``"You"``
    — Doubling Season / Parallel Lives; ``""`` for the symmetric Primal
    Vigor form). The give-away gate (checklist #2) reads it.
    """
    s = getattr(node, "token_owner_scope", MISSING)
    return s if isinstance(s, str) else ""


def damage_filter_scope(node: TypedMirrorNode, field: str) -> str | None:
    """The player scope of a DamageDone replacement's ``damage_target_filter``
    / ``damage_source_filter``, or ``None`` when absent.

    Three phase shapes: a bare string (``"CreatureOnly"`` — Blind Fury) →
    ``"objects"`` (no player reach); a variant ``{Player: {player}}`` /
    ``{PlayerOrPermanentsControlledBy: {player}}`` → the named player's scope
    (Gisela: Opponent → ``"opponents"``; Ali from Cairo: Controller →
    ``"you"``); a ``Typed`` object filter (Gratuitous Violence's creature
    source) → ``"objects"``. Checklist #5: direction reads the filter's OWN
    player node, never a summary scope.
    """
    f = getattr(node, field, MISSING)
    if not _present(f):
        return None
    if isinstance(f, str):
        return "objects"
    if isinstance(f, MirrorVariant):
        if f.key in ("Player", "PlayerOrPermanentsControlledBy"):
            ply = _variant_field(f.inner, "player")
            return _scope_from_player_node(ply) or "any"
        return "objects"
    if isinstance(f, TypedMirrorNode):
        if tag_of(f) in ("Typed", "Or", "And"):
            return "objects"
        return _scope_from_player_node(f) or "objects"
    return None


def trigger_counter_filter(trig: TypedMirrorNode) -> tuple[str, int]:
    """``(counter_type, threshold)`` of a ``CounterAdded`` trigger's
    ``counter_filter`` (``("lore", 3)`` — a Saga chapter, CR 714.2b;
    ``("P1P1", 0)`` — Scurry Oak; ``("", 0)`` when kindless/absent).

    The typed Saga gate: 723 of the 798 CounterAdded triggers are Saga
    chapters, and the ``lore`` counter_type is a CLEANER discriminator than
    live's type_line sniff.
    """
    cf = getattr(trig, "counter_filter", MISSING)
    if not _present(cf):
        return ("", 0)
    ct = getattr(cf, "counter_type", None)
    th = getattr(cf, "threshold", None)
    return (
        ct if isinstance(ct, str) else "",
        th if isinstance(th, int) else 0,
    )


def trigger_caster_scope(trig: TypedMirrorNode) -> str | None:
    """The cast-PLAYER scope of a ``SpellCast`` trigger's ``valid_target`` —
    ``"you"`` for the "whenever YOU cast" form (Lys Alana — ``Controller``),
    ``"opponents"`` for the opponent punisher, ``None`` for the symmetric
    "a player casts" hoser (Elvish Handservant — no valid_target). The typed
    you-cast discriminator that replaces live's ``_self_cast_oracle`` regex
    gate. CR 603.2 + 102.2.
    """
    vt = getattr(trig, "valid_target", MISSING)
    if not _present(vt):
        return None
    return _scope_from_player_node(vt)


def settap_state(node: TypedMirrorNode) -> str | None:
    """The ``state`` tag of a ``SetTapState`` effect (``Tap`` / ``Untap``),
    or ``None``. CR 701.26a.
    """
    return tag_of(getattr(node, "state", None))


def player_filter_tag(node: TypedMirrorNode) -> str | None:
    """The ``player_filter`` tag of a ``DamageAll`` / ``DamageEachPlayer``
    effect (``All`` — the symmetric Pestilence form; ``Opponent`` — the
    one-sided Witty Roastmaster form), or ``None`` when the sweep never
    reaches players (Pyroclasm). CR 102.2/102.3 — the each-PLAYER vs
    each-OPPONENT split is the whole gate.
    """
    return tag_of(getattr(node, "player_filter", None))


def double_target_kind(node: TypedMirrorNode) -> str | None:
    """The ``target_kind`` tag of a one-shot ``Double`` effect (``Counters``
    — Vorel; ``LifeTotal``; ``ManaPool``; ``None`` for the power doublers).
    The counter_doubling arm gates on ``Counters`` exactly. CR 122.1.
    """
    return tag_of(getattr(node, "target_kind", None))


def node_duration(node: object) -> str | None:
    """The ``duration`` of an ability/effect wrapper, normalized to its tag
    string (``"UntilHostLeavesPlay"`` — the O-Ring exile duration, CR 611.2b;
    ``"UntilEndOfTurn"``; the parameterized ``{UntilNextStepOf: …}`` → its
    KEY). ``None`` when absent.
    """
    d = getattr(node, "duration", MISSING)
    if isinstance(d, str):
        return d
    if isinstance(d, MirrorVariant):
        return d.key
    if isinstance(d, TypedMirrorNode):
        return tag_of(d)
    return None


def _find_owner_wrapper(
    node: object, target: object, depth: int, seen: set[int]
) -> TypedMirrorNode | None:
    """The ability wrapper whose ``.effect`` IS ``target`` (same walk as
    :func:`effect_owner_player_scope`'s), or ``None``."""
    if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
        return None
    seen.add(id(node))
    if getattr(node, "effect", MISSING) is target:
        return node
    for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities"):
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            r = _find_owner_wrapper(child, target, depth + 1, seen)
            if r is not None:
                return r
        elif _present(child) and isinstance(child, list):
            for m in child:
                r = _find_owner_wrapper(m, target, depth + 1, seen)
                if r is not None:
                    return r
    return None


def effect_owner_duration(root: object, effect_node: object) -> str | None:
    """The ``duration`` tag on the wrapper that DIRECTLY owns ``effect_node``
    (Banisher Priest's exile execute carries ``UntilHostLeavesPlay`` on the
    Spell wrapper, not on the ``ChangeZone`` node itself), or ``None``.
    CR 611.2b.
    """
    owner = _find_owner_wrapper(root, effect_node, 0, set())
    return node_duration(owner) if owner is not None else None


def reveal_until_player(node: TypedMirrorNode) -> str | None:
    """The DIGGER of a ``RevealUntil`` effect from its ``player`` node —
    ``"you"`` for an own-library dig (Hermit Druid — ``Controller``); the
    opponent-library digs carry ``ParentTargetController`` /
    ``TriggeringPlayer`` / ``Typed`` → not-you ([P16]-adjacent direction
    gate). ``None`` when unresolvable. CR 701.20a.
    """
    return _scope_from_player_node(getattr(node, "player", None))


def filter_non_types(filt: object) -> tuple[str, ...]:
    """The words a typed filter NEGATES via ``{Non: X}`` entries ("noncreature
    spell" — Ruric Thar → ``("Creature",)``; "non-Zombie" → ``("Zombie",)``).

    The complement of :func:`_type_filter_words` (which DROPS the negation):
    the noncreature-cast punisher gates on the ``Non`` entry itself being
    present. Recurses ``Or`` / ``And``. CR 207.2c / 400.7.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, MirrorVariant) and tf.key == "Non":
                inner = tf.inner
                if isinstance(inner, str):
                    out.append(inner)
                elif isinstance(inner, MirrorVariant):
                    out.append(
                        inner.inner if isinstance(inner.inner, str) else inner.key
                    )
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_non_types(sub))
    return tuple(out)


def has_filter_property(root: object, tag: str, value: str | None = None) -> bool:
    """Whether ANY typed node under ``root`` carries the property ``tag``
    (optionally with ``value``) — the whole-card predicate scan behind the
    legends_matter / historic_matters build-arounds (``HasSupertype:
    Legendary`` — Reki; ``Historic`` — Jhoira). The property tags are unique
    to filter ``properties`` entries, so the deep scan is precise. CR 205.4d
    / 700.6.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != tag:
            continue
        if value is None or getattr(n, "value", None) == value:
            return True
    return False


def zone_change_count_reads(
    root: object,
) -> Iterator[tuple[str | None, str | None, object]]:
    """``(from, to, filter)`` for every ``ZoneChangeCountThisTurn`` qty node
    under ``root`` — the "a permanent left the battlefield this turn"
    condition family (CR 603.10-adjacent state checks). Revolt carries
    ``from: Battlefield`` with NO ``to`` (Airdrop Aeronauts); Morbid carries
    ``to: Graveyard`` (Tragic Slip) — zone-precise, the two must not blur.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "ZoneChangeCountThisTurn":
            continue
        frm = getattr(n, "from_", MISSING)
        to = getattr(n, "to", MISSING)
        yield (
            frm if isinstance(frm, str) else None,
            to if isinstance(to, str) else None,
            getattr(n, "filter", None),
        )


def entered_this_turn_filters(root: object) -> Iterator[object]:
    """The ``filter`` of every ``EnteredThisTurn`` QTY node under ``root`` —
    the "if a creature entered the battlefield under your control this turn"
    condition family (Bellowing Elk; CR 603.6a-adjacent state check). A
    filterless ``EnteredThisTurn`` (Cactuar's self-check) yields nothing.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) == "EnteredThisTurn":
            f = getattr(n, "filter", MISSING)
            if _present(f):
                yield f


# ── Batch-12 typed accessors (life / stax / protection / condition cluster) ──


def protection_cardtype(mod: TypedMirrorNode) -> str | None:
    """The CardType ARGUMENT of an ``AddKeyword {Protection: {CardType: X}}``
    modification (Gor Muldrak — ``"salamanders"``), or ``None`` for any other
    keyword / a protection-from-COLOR payload (White Knight). CR 702.16: the
    type_change lane vocab-validates the argument upstream.
    """
    kw = getattr(mod, "keyword", MISSING)
    if not (isinstance(kw, MirrorVariant) and kw.key == "Protection"):
        return None
    arg = _variant_field(kw.inner, "CardType")
    return arg if isinstance(arg, str) else None


def modify_cost_spell_filter(static_node: TypedMirrorNode) -> object | None:
    """The ``spell_filter`` of a ``{ModifyCost: …}`` static mode, or ``None``.

    The typed_spellcast static arm (b11 follow-up a) reads its subtypes: a
    "<Subtype> spells you cast cost {N} less" static (Goblin Warchief) carries
    the tribe on ``spell_filter`` — CR 601.2f couples the discount to the cast
    event, so the tribal reducer is a cast payoff, subject-bearing.
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "ModifyCost":
        return _variant_field(mode.inner, "spell_filter")
    return None


def static_mode_field(node: object, field: str) -> object:
    """One named field of a parameterized static MODE's payload, or ``None``.

    The stax census reads discriminating sub-fields off the variant modes the
    b12 port added — ``who`` (``CantBeActivated`` / ``CantBeCast`` /
    ``PerTurnCastLimit`` …), ``source_filter`` (the Arrest pacify veto),
    ``defender`` (``MaxAttackersEachCombat``). ``None`` for a plain-string
    mode or an absent field.
    """
    mode = getattr(node, "mode", MISSING)
    if isinstance(mode, MirrorVariant):
        return _variant_field(mode.inner, field)
    return None


def distribute_counter_kind(node: TypedMirrorNode) -> str:
    """The counter kind of a ``PutCounter`` effect's ``distribute`` marker
    (Verdurous Gearhulk — ``{Counters: "P1P1"}`` → ``"P1P1"``), ``""`` when the
    placement is not a distribute-among (CR 601.2d). v0.9.0 DOES carry the
    marker — the earlier "[P-fold]" note was stale.
    """
    d = getattr(node, "distribute", MISSING)
    if _present(d) and tag_of(d) == "Counters":
        data = getattr(d, "data", None)
        return data if isinstance(data, str) else ""
    return ""


def iter_typed_nodes(root: object) -> Iterator[TypedMirrorNode]:
    """Public deep walk over every typed node reachable from ``root`` (the
    generic scan behind narrow unique-tag reads — the b12 saga CountersOn
    and big-hand HandSize operand arms). Cycle-safe, field-order agnostic.
    """
    yield from _iter_typed_nodes(root)


def iter_condition_sites(root: object) -> Iterator[TypedMirrorNode]:
    """Every CONDITION-site subtree root under one unit node: each ``condition``
    field plus each ``activation_restrictions`` entry (Companion of the Trials'
    ``RequiresCondition``). The superfriends lane scans ONLY these sites — an
    effect TARGET filter naming a Planeswalker is removal, not synergy
    (checklist gate; CR 306.5).
    """
    for n in _iter_typed_nodes(root):
        cond = getattr(n, "condition", MISSING)
        if isinstance(cond, TypedMirrorNode):
            yield cond
        ars = getattr(n, "activation_restrictions", MISSING)
        if _present(ars) and isinstance(ars, list):
            for ar in ars:
                if isinstance(ar, TypedMirrorNode):
                    yield ar


def hand_size_scopes(root: object) -> tuple[str, ...]:
    """The player scope of every ``HandSize`` / ``HandSizeExact`` /
    ``HandSizeOneOf`` QTY operand under one unit node (Maro's dynamic-P/T
    pair, Akki Underling's threshold condition). The big_hand_matters lane
    fires only on a ``"you"`` scope ([P5] — an opponent-hand count is not
    your grip payoff). A player-less operand reports ``"you"`` (phase's
    implicit controller). CR 402.2.
    """
    out: list[str] = []
    for n in _iter_typed_nodes(root):
        if tag_of(n) in ("HandSize", "HandSizeExact", "HandSizeOneOf"):
            player = getattr(n, "player", MISSING)
            if not _present(player):
                out.append("you")
                continue
            out.append(_scope_from_player_node(player) or "any")
    return tuple(out)


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


# Effect-bearing child fields a node nests further effects through. Phase chains
# sequential siblings ("draw two cards, then discard two") via ``sub_ability``,
# wraps a delayed/granted effect in ``effect`` / ``execute`` (a replacement's
# ``execute``, Final Fortune's nested end-step loss), and branches modes through
# ``mode_abilities`` (Demonic Pact). A faithful unit aggregates them all — the same
# flattening the old projection's ``ab.effects`` did.
_EFFECT_CHILD_FIELDS = ("effect", "sub_ability", "execute")


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
    units: list[AbilityUnit] = []

    abilities = getattr(root, "abilities", ()) or ()
    for i, ab in enumerate(abilities):
        if not isinstance(ab, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="ability",
                index=i,
                node=ab,
                kind=getattr(ab, "kind", None),
                trigger_event=None,
                effects=tuple(_walk_effect_chain(ab)),
                costs=_cost_concepts(ab),
                statics=_nested_static_concepts(ab),
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

    oracle = getattr(root, "oracle_text", None)
    return ConceptTree(
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
    )
