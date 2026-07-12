"""ADR-0035 Stage-3b bucket (b)-COMPLETION — reuse-on-compat field corrections.

The (b) FRAMEWORK is :mod:`overlay_corrections` (a TREE-level ``ConceptNode``
overlay that decorates ``scope`` / ``subject`` / ``zones`` / ``returns_to`` and
feeds BOTH the Signal lanes and the compat Card). This module is the (b)-
COMPLETION seam — the exact mirror of bucket (c)'s :mod:`dropped_clauses`: it
REUSES the supplement's ``_recover_*`` FIELD-correction arms DIRECTLY on the
already-built compat :class:`Card`, so the crosswalk compat Card gains the SAME
field corrections the legacy ``project.py`` path carried. Reuse-on-compat is
SIMPLER than a tree reimplementation and is the pattern ADR-0035 Stage-3b (c)
established. ADR-0039 step 7 deleted ``project.py``; the two ability-level arms
it defined (``_recover_clone_subjects`` / ``_recover_cheat_into_play_source``)
moved HERE verbatim (this module is their sole surviving consumer), while
``_recover_tap_down`` stays in ``supplement.py``.

**Where it runs — the compat-Card seam (Seam B), COMPAT-ONLY.** Reached solely
through :func:`compat_card`, strictly DOWNSTREAM of the (c) synthesis stage. It
never receives, reads, or writes a tree / mirror node, so the substrate-purity
invariant holds *a fortiori* (``compat_card`` already snapshots the L1 identity
around the whole build and asserts it unchanged). Because it runs on the compat
Card and NOT on the tree the Signal lanes read (``extract_crosswalk_signals``
does not call this stage), the Signal seam is UNCHANGED by construction — the
``exit_master`` signal diff is byte-identical before/after (the "reuse-on-compat
leaves signals unchanged" property the ADR-0035 Stage-3b (b) gate requires).

**Which (b) arms are ported HERE vs DEFERRED — the lossy-compat boundary.** The
compat Card under-derives fields the OLD per-ability projection carried:
``compat._effect`` sets ``raw=cnode.raw``, which the substrate populates on only
~16% of nodes; ``compat._trigger`` drops a trigger's ``recipient`` / ``source``;
``compat._effect`` derives ``counter_kind`` only as ``"all"`` / ``""`` (never the
``"top"`` / ``"topbottom"`` / ``"p1p1"`` the old projection carried). A (b) arm
whose GUARD reads one of those under-derived fields cannot fire faithfully on
this seam — reusing it would either NO-OP (a false-convergence reading, the
bucket-(c) ``_DEFERRED_RAW_ARMS`` lesson) or misfire. So only the STRUCTURE-
reading (b) arms — whose guards read fields the compat Card DOES derive
(``category`` / ``subject`` / structural siblings), grounding on the whole-card
oracle when a per-node ``raw`` is absent — are reused here:

* ``cheat_into_play_source`` — appends one canonical ``cheat_play`` marker off
  STRUCTURED sibling tutor/reveal/dig/reanimate categories (raw only refines the
  subject). Fires structurally on the seam.
* ``clone_subjects`` — refills a ``clone`` effect's dropped copied-type
  ``subject`` from a sibling effect's / the trigger's structured subject.
* ``tap_down`` — resolves the opponent anaphora on a ``tap`` / ``skip_step``
  effect (a card-level ``(card, oracle)`` arm that falls back to the WHOLE oracle
  when the per-effect ``raw`` is empty — the same whole-oracle grounding the (c)
  card-level arms use, gated on the structural ``category``).

Every ported arm is proven to move 0 cards agree→disagree in ANY of the five
dataclass consumers (ranking / budgets / cut_check / metrics / bracket) at phase
v0.15.0 — a strict per-card SUPERSET (the consumer diff HOLDS: budgets 98.08%,
cut_check 97.43%, ranking 66.35%, metrics 99.95%, bracket 99.99%, all unchanged).
The ported arms are append-only / structurally idempotent, so no convergence gate
is needed (unlike bucket (c)'s two cost/controller-discriminated arms).

The remaining LIVE (b) arms are DEFERRED off this seam (:data:`_DEFERRED_RAW_ARMS`
+ :data:`_DEFERRED_UNDERDERIVED_ARMS`) with their blocker named — dormant (their
legacy ``project.py`` home is deleted, ADR-0039 step 7) until the compat Card
carries the field their guard reads (a post-deletion follow-on: per-node ``raw``
population + richer ``trigger`` / ``counter_kind`` derivation). Their
SIGNAL-facing purpose (scaling_pump, dig_until, play_from_top, recursion, edict,
removal, …) is already reproduced by the crosswalk's STRUCTURAL Signal lanes;
only their compat-Card FIELD awaits the richer compat derivation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from mtg_utils._card_ir.supplement import _recover_tap_down
from mtg_utils._card_ir.text_idioms import _copied_type_from_text
from mtg_utils.card_ir import Effect, Filter

if TYPE_CHECKING:
    from mtg_utils.card_ir import Ability, Card

# An ability-level (b) arm: ``_recover_X(ability) -> ability`` (mapped over every
# face's abilities). A card-level arm: ``_recover_X(card, oracle) -> card``.
_AbilityArm = Callable[["Ability"], "Ability"]
_CardArm = Callable[["Card", str], "Card"]


# ── the absorbed project.py ability-level arms (ADR-0039 step 7) ─────────────
# ``_recover_clone_subjects`` and the ``_recover_cheat_into_play_source``
# cluster below moved here VERBATIM from the deleted ``project.py`` (this
# module was their sole surviving consumer). Comment blocks preserved.


def _recover_clone_subjects(ability: Ability) -> Ability:
    """A BecomeCopy with ``target: ParentTarget`` ("target creature becomes a copy of
    IT") loses its copied type. Recover it from the clone clause's own "copy of <type>"
    text, falling back to a sibling effect's / the trigger's target type (the parent
    the copy refers to). Leaves it None only when neither is present."""
    if not any(e.category == "clone" and e.subject is None for e in ability.effects):
        return ability
    borrowed: Filter | None = next(
        (
            e.subject
            for e in ability.effects
            if e.category != "clone"
            and isinstance(e.subject, Filter)
            and e.subject.card_types
        ),
        None,
    )
    if (
        borrowed is None
        and ability.trigger is not None
        and isinstance(ability.trigger.subject, Filter)
    ):
        borrowed = ability.trigger.subject
    effects = tuple(
        replace(e, subject=_copied_type_from_text(e.raw) or borrowed)
        if e.category == "clone" and e.subject is None
        else e
        for e in ability.effects
    )
    return replace(ability, effects=effects)


# ADR-0027 reveal/dig-v2 (cheat_into_play). phase structures "put a card onto the
# battlefield from library/reveal/hand" INCONSISTENTLY — the put-onto-battlefield
# lands on `reveal`/`exile`/`mill`/`choose`/`blink`/`tutor` effects, with the
# `to:battlefield` destination and the library/hand ORIGIN given on DIFFERENT sibling
# effects (Call of the Wild = two `reveal`s; Lord of the Void = two `exile`s; Mass
# Polymorph = exile + blink + exile) or dropped entirely (Impromptu Raid keeps only
# the non-creature → graveyard branch). So a structural cheat_into_play arm has no
# single consistent effect to read. This recovery APPENDS one canonical `cheat_play`
# Effect per ability that genuinely cheats a non-land card onto the battlefield from a
# NON-graveyard source, carrying a consistent SOURCE-ZONE tag (`from:top` / `from:
# library` / `from:hand`) + `to:battlefield`. Append-only — the scattered originals
# are untouched, so every sibling lane (mill_makers, exile_removal, graveyard_matters,
# blink_flicker, …) is behavior-neutral. The marker carries NO `from:graveyard` (the
# graveyard-ONLY put is reanimation — CR 110.2a shared put-onto-bf, CR 400.7 distinct
# origin — handled by the existing `reanimate` category, routed to the reanimator lane,
# NOT cheat_into_play). A HYBRID "from your hand OR graveyard" (Dakkon) still emits the
# marker off its non-graveyard half (the non-gy origin is sufficient). The control/
# owner of the cheated card is orthogonal to the source (Lord of the Void / Bribery
# cheat from an OPPONENT's library into YOUR control — still cheat_into_play), so scope
# never gates the marker out.
#
# A reveal/look/exile from the TOP of a (your/their/a) library whose card LANDS on the
# battlefield in the same span — the reveal-until-creature / look-at-top / Polymorph
# family (Call of the Wild, Mass Polymorph, Bag of Tricks, Oath of Druids, Lord of the
# Void's opponent-library exile). The "onto the battlefield" landing may be in a later
# sentence ("…until you reveal a creature card. Put that card onto the battlefield"),
# so the scan spans sentences but requires both the top-of-library source and the
# battlefield landing.
_CHEAT_TOP_RAW = re.compile(
    r"(?:reveal|look at|exile)[^.]*?\btop\b[^.]*?\blibrary\b"
    r".*?\bonto the battlefield\b",
    re.IGNORECASE | re.DOTALL,
)
# A put / reveal of a card FROM a hand onto the battlefield (Sneak Attack, Show and
# Tell, Eladamri's "reveal a card from your hand … put it onto the battlefield"). phase
# usually structures these as a clean `cheat_play`+from:hand, but the hybrid hand-or-top
# reveal (Eladamri) and the rarer phrasings land here as the raw fallback.
_CHEAT_HAND_RAW = re.compile(
    r"\b(?:put|reveal)\b[^.]*?\bfrom (?:your|their) hand\b[^.]*?"
    r"\bonto the battlefield\b",
    re.IGNORECASE,
)
# A search of a (your/their/target opponent's) library that puts the found card onto
# the battlefield — a tutor-INTO-PLAY (Birthing Pod, Academy Rector, Bribery, Chord of
# Calling, Pattern of Rebirth). phase structures these as a `tutor` + a subjectless
# `cheat_play`+from:library pair; the marker carries the tutor's subject (a basic-land
# tutor is gated out below). Bounded to one search clause (a "search … put onto the
# battlefield" span) so a "search … into hand. … put a TOKEN onto the battlefield"
# multi-sentence card can't bleed.
_CHEAT_SEARCH_RAW = re.compile(
    r"\bsearch\b[^.]*?\blibrary\b[^.]*?\bonto the battlefield\b",
    re.IGNORECASE,
)
# A creature/permanent type a put-onto-bf cheat names, recovered from the raw when no
# structured sibling subject survives ("put a CREATURE card …", "put all PERMANENT
# cards …"). Only the broad put-into-play type words — a Land-only match is excluded by
# the caller (it is ramp, not a cheat). Ordered most→least specific.
_CHEAT_SUBJECT_WORDS: tuple[tuple[str, str], ...] = (
    ("creature", "Creature"),
    ("artifact", "Artifact"),
    ("enchantment", "Enchantment"),
    ("planeswalker", "Planeswalker"),
    ("permanent", "Permanent"),
)


def _cheat_subject_from_raw(raw: str) -> Filter | None:
    """The put-into-play card type a cheat names in its raw (a Creature / Permanent /…
    Filter), or None when only a land or no type is named. Anchored on a "<type> card"
    so a stray "creature" elsewhere (a fight rider) can't match."""
    low = (raw or "").lower()
    for word, ctype in _CHEAT_SUBJECT_WORDS:
        if re.search(rf"\b{word} cards?\b", low):
            return Filter(card_types=(ctype,))
    return None


# A put-onto-battlefield whose only named card type is LAND ("if it's a LAND card, put
# it onto the battlefield"; "puts all LAND cards … onto the battlefield" — Into the
# Wilds, Skyward Eye Prophets, Clear the Land, Thrasios, Lantern of Revealing, basic-
# land tutors). That is RAMP (extra_land_drop), not a creature/permanent cheat. True
# only when a "land card" put is named AND no non-land put type co-occurs (a card that
# puts a creature OR a land — Kamahl's Druidic Vow — is still a cheat).
def _cheat_is_land_only(raw: str) -> bool:
    """True when a cheat's put-onto-battlefield names only LAND cards (ramp, not a
    card cheat)."""
    low = (raw or "").lower()
    if not re.search(r"\bland cards?\b", low):
        return False
    return not any(
        re.search(rf"\b{word} cards?\b", low) for word, _ in _CHEAT_SUBJECT_WORDS
    )


def _ability_cheat_source(ability: Ability) -> str | None:
    """The non-graveyard SOURCE zone of a put-onto-battlefield cheat this ability does,
    or None when it is not a cheat (no battlefield landing, a graveyard-ONLY source =
    reanimation, or a land-only ramp). Prefers a STRUCTURED source: a sibling effect
    already carrying both `to:battlefield` and a non-gy `from:` tag; falls back to the
    raw idiom. Returns the most specific of from:top / from:library / from:hand."""
    has_to_bf = False
    has_reveal_hand = False
    struct_from: set[str] = set()
    raw_parts: list[str] = []
    for e in ability.effects:
        if not isinstance(e, Effect):
            continue
        raw_parts.append(e.raw or "")
        z = set(e.zones)
        if "to:battlefield" in z:
            has_to_bf = True
        if e.category == "reveal_hand":
            has_reveal_hand = True
        struct_from |= {x for x in z if x in ("from:top", "from:library", "from:hand")}
    raw = max(raw_parts, key=len) if raw_parts else ""
    # A structured non-gy source already co-present with a battlefield landing — the
    # cleanest signal (Bribery, Sneak Attack, the dig-into-play retags).
    if has_to_bf and struct_from:
        for z in ("from:top", "from:library", "from:hand"):
            if z in struct_from:
                return z
    # A reveal-HAND peek + a battlefield landing — a cheat from a (usually opponent's)
    # HAND that phase tags only as `reveal_hand` + a subjectless to:battlefield (Zara
    # Renegade Recruiter "look at defending player's hand … put a creature card from it
    # onto the battlefield"; Treacherous Urge "target opponent reveals their hand … put
    # a creature card from it onto the battlefield"). The cheated card is from a hand =
    # from:hand (the owner is orthogonal — it's still a cheat). CR 110.2a / 400.7.
    if has_to_bf and has_reveal_hand:
        return "from:hand"
    # Raw fallback: the reveal/look/exile-from-top, hand, or search-into-play idiom.
    if _CHEAT_TOP_RAW.search(raw) or _CHEAT_SEARCH_RAW.search(raw):
        return "from:top" if _CHEAT_TOP_RAW.search(raw) else "from:library"
    if _CHEAT_HAND_RAW.search(raw):
        return "from:hand"
    return None


def _recover_cheat_into_play_source(ability: Ability) -> Ability:
    """Append one canonical `cheat_play` marker when this ability cheats a non-land card
    onto the battlefield from a NON-graveyard source (ADR-0027 reveal/dig-v2). The
    marker carries a consistent `from:<top|library|hand>` + `to:battlefield` zone pair
    and the put-into-play subject (from a structured sibling tutor/reveal/cheat, or the
    raw), so the cheat_into_play arm reads ONE shape across phase's scattered
    structures.

    Idempotency / no-double-fire: skip when the ability ALREADY has a clean
    `cheat_play` effect carrying a non-gy `from:` + `to:battlefield` (phase / the
    dig-into-play retag structured it cleanly — Sneak Attack, Show and Tell, Collected
    Company via _recover_dig_into_play), so the arm reads the existing one and this adds
    nothing. The marker is APPENDED (originals untouched), so reanimate / mill / exile /
    blink / graveyard siblings are behavior-neutral. CR 110.2a / 400.7 / 701.23."""
    src = _ability_cheat_source(ability)
    if src is None:
        return ability
    # Already a clean cheat_play with a non-gy origin + battlefield landing — no marker.
    for e in ability.effects:
        if (
            isinstance(e, Effect)
            and e.category == "cheat_play"
            and "to:battlefield" in e.zones
            and any(z in e.zones for z in ("from:top", "from:library", "from:hand"))
        ):
            return ability
    # Subject: a structured non-land put-into-play type from a sibling, else the raw.
    subject: Filter | None = None
    for e in ability.effects:
        if not isinstance(e, Effect) or e.subject is None:
            continue
        if e.category in (
            "tutor",
            "cheat_play",
            "reveal",
            "choose",
            "topdeck_select",
            "dig_until",
            "reanimate",
            "exile",
            "blink",
        ):
            subject = e.subject
            break
    raw = max((e.raw or "" for e in ability.effects), key=len, default="")
    if subject is None:
        subject = _cheat_subject_from_raw(raw)
    # A LAND-only put is ramp (extra_land_drop), not a cheat — drop it. Gate on the
    # structured subject AND the raw ("if it's a LAND card, put it onto the battlefield"
    # — Into the Wilds, Skyward Eye Prophets, Thrasios — where phase leaves no typed
    # subject). The signals arm applies the same gate; skipping here keeps the marker
    # honest (the lane never opens extra_land_drop's territory).
    if isinstance(subject, Filter) and set(subject.card_types) == {"Land"}:
        return ability
    if subject is None and _cheat_is_land_only(raw):
        return ability
    marker = Effect(
        category="cheat_play",
        scope="you",
        subject=subject,
        raw=raw,
        zones=(src, "to:battlefield"),
    )
    return replace(ability, effects=(*ability.effects, marker))


# The ability-level (b) FIELD-correction arms reused on the compat Card, in
# ``project.py``'s projection order (clone during clone-build, then cheat). Each
# fires STRUCTURALLY (reads the built abilities' categories / subjects), so a
# firing on the seam faithfully reproduces the old projection's field correction.
APPLIED_ABILITY_ARMS: tuple[tuple[str, _AbilityArm], ...] = (
    ("clone_subjects", _recover_clone_subjects),
    ("cheat_into_play_source", _recover_cheat_into_play_source),
)

# The card-level (b) FIELD-correction arms reused on the compat Card. ``tap_down``
# reads each effect's own clause ``raw`` but FALLS BACK to the whole-card oracle
# when that raw is empty (which it is on the compat seam), gated on the structural
# ``tap`` / ``skip_step`` category — the same whole-oracle grounding the bucket-(c)
# card-level arms use.
APPLIED_CARD_ARMS: tuple[tuple[str, _CardArm], ...] = (("tap_down", _recover_tap_down),)

ARM_NAMES: tuple[str, ...] = tuple(
    name for name, _ in (*APPLIED_ABILITY_ARMS, *APPLIED_CARD_ARMS)
)


# ── deferred (b) arms (off the compat seam) — blocker named ────────────────────
#
# RAW-READERS: the arm's GUARD keys on a per-effect ``e.raw`` / ``out.raw`` the
# compat Card leaves empty on ~84% of nodes (``compat._effect`` carries only the
# sparse substrate ``description``). Reusing them here would fire unreliably on
# the incidental ~16% and give a FALSE convergence reading (the bucket-(c)
# ``_DEFERRED_RAW_ARMS`` finding). They await per-node ``raw`` population (Stage 4).
_DEFERRED_RAW_ARMS: tuple[str, ...] = (
    "count_operand",  # _FOR_EACH_COUNT over the effect raw (amount->count)
    "top_of_library_owner",  # top:you/top:opp owner tag from the effect raw
    "library_zones",  # from:library from the cast-from-library raw
    "graveyard_origin",  # GY exile-origin / play-from-GY from the effect raw
    "group_hug_draw_scope",  # "each player draws" from the draw effect raw
    "destroy_subject",  # "destroy target creature" from the destroy raw
    "hybrid_exile_zone",  # battlefield-OR-graveyard exile alt from out.raw
    "opponent_exile_subject",  # per-opponent exile clause from out.raw
)

# FIELD-UNDER-DERIVED: the arm's GUARD keys on a discriminator the LOSSY compat
# Card never derives — a trigger's ``recipient`` / ``source`` (``compat._trigger``
# drops both) or an effect's fine ``counter_kind`` (``compat._effect`` derives
# only ``"all"`` / ``""``, never ``"top"`` / ``"topbottom"`` / ``"p1p1"``). The
# arm can never fire on the seam regardless of ``raw``; it awaits richer compat
# derivation (Stage 4).
_DEFERRED_UNDERDERIVED_ARMS: tuple[str, ...] = (
    "tribe_damage_source",  # needs trigger.recipient=='player' (compat drops it)
    "topdeck_stack_self",  # needs counter_kind in {top, topbottom}
    "self_counter_grow",  # needs counter_kind=='p1p1'
)


def _map_abilities(card: Card, arm: _AbilityArm) -> Card:
    """Apply one ability-level (b) arm across every face's abilities."""
    return replace(
        card,
        faces=tuple(
            replace(face, abilities=tuple(arm(ab) for ab in face.abilities))
            for face in card.faces
        ),
    )


def apply_field_corrections(card: Card, oracle: str) -> Card:
    """Reuse the (b) FIELD-correction arms on the compat ``card``.

    Runs the ported ability-level arms (mapped over every face's abilities) then
    the card-level arms, threading the card through so a later arm sees an earlier
    arm's correction — mirroring the deleted ``project.py`` chain. ``oracle`` is
    the card's whole face oracle text (the card-level arms' grounding when a
    per-effect ``raw`` is absent). Each arm is append-only / structurally
    idempotent and pure; a card needing no correction is returned by identity.
    """
    for _name, arm in APPLIED_ABILITY_ARMS:
        card = _map_abilities(card, arm)
    for _name, arm in APPLIED_CARD_ARMS:
        card = arm(card, oracle)
    return card


def correct_with_trace(card: Card, oracle: str) -> tuple[Card, frozenset[str]]:
    """Like :func:`apply_field_corrections`, but also return WHICH arms fired.

    An arm "fired" when it changed the card (a dropped field it refilled) — the
    same dataclass content-inequality firing test the Stage-3b measure phase and
    bucket (c) use. Used by the gated corpus test to assert every ported arm is
    still LIVE at the pin (finds a field gap on >=1 corpus card).
    """
    fired: set[str] = set()
    for name, arm in APPLIED_ABILITY_ARMS:
        nxt = _map_abilities(card, arm)
        if nxt != card:
            fired.add(name)
        card = nxt
    for name, arm in APPLIED_CARD_ARMS:
        nxt = arm(card, oracle)
        if nxt is not card and nxt != card:
            fired.add(name)
        card = nxt
    return card, frozenset(fired)
