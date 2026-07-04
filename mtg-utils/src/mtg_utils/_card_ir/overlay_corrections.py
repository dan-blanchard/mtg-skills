"""ADR-0035 Stage-3b — the named Layer-2 overlay-correction stage (bucket b).

The supplement's ``_recover_*`` arms are three operations (ADR-0035 Decision).
Bucket **(b)** — *overlay corrections that mutate/append phase's correctly-parsed
nodes* — become this stage: it runs AFTER :func:`build_concept_tree`, re-derives a
handful of fields the pure substrate under-reads (a mis-scoped edict, a
put-into-play dig, a dropped removal target), and writes the correction onto the
**Layer-2 concept overlay** (the :class:`ConceptNode` decoration) — NEVER into the
Layer-1 phase mirror node.

**The substrate-purity invariant (the new safety property).** Each arm keeps the
underlying ``ConceptNode.node`` object *by identity* — it only ``dataclasses
.replace``\\s the overlay fields (``scope`` / ``subject`` / ``zones`` /
``returns_to`` / the compat-only ``category`` override).
:func:`apply_overlay_corrections` snapshots a structural fingerprint of every L1
node before the stage and asserts it unchanged
after, so a correction that leaked into the frozen mirror fails loud
(:class:`SubstratePurityError`). The committed ``TypedMirrorNode`` is frozen, so
the invariant is provable, not merely tested.

Gated onto the flag-ON crosswalk path only (called by ``compat_card`` and
``extract_crosswalk_signals``); flag-OFF (the ``project.py`` projection) never
reaches it. ``project.py`` / ``supplement.py`` keep their ``_recover_*`` arms — the
OLD path is untouched; these are the concept-overlay ports.

Each arm records whether the crosswalk substrate ALREADY handles the correction
(``already_handled``) or the overlay genuinely adds it (``newly_ported``) — the
per-arm bucketing ADR-0035 Stage-3b calls for.
"""

from __future__ import annotations

import re
from dataclasses import replace

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    effect_filter,
    filter_controller,
    filter_inzone_zones,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, TypedMirrorNode

# ── substrate-purity invariant ────────────────────────────────────────────────


class SubstratePurityError(AssertionError):
    """Raised when the overlay stage mutated an L1 (phase-mirror) node.

    The overlay may ONLY decorate the Layer-2 :class:`ConceptNode`; the frozen
    :class:`TypedMirrorNode` substrate must round-trip byte-identically and stay
    the same object at every tree position. A violation is a hard bug.
    """


def _l1_nodes(tree: ConceptTree) -> list[TypedMirrorNode]:
    """Every Layer-1 substrate node reachable through the overlay, in tree order.

    Each ability unit's own node plus every decorated concept-node's ``node``
    (effects, costs, statics) — the exact set the overlay is forbidden to write.
    """
    out: list[TypedMirrorNode] = []
    for unit in tree.units:
        out.append(unit.node)
        for c in (*unit.effects, *unit.costs, *unit.statics):
            out.append(c.node)
    return out


def _l1_identity(tree: ConceptTree) -> list[int]:
    """The object-identity fingerprint of every L1 node, in tree order.

    The mirror node is a FROZEN dataclass — it cannot be mutated in place through
    the normal API — so preserving every node's ``id`` is equivalent to never
    writing into L1: an arm that (illegally) rebuilt a mirror node would land a NEW
    object at that position and change its id. Cheap enough for the live guard on
    every card. The committed test additionally byte-checks each node's ``to_dict``
    round-trip (:func:`l1_bytes`) as belt-and-suspenders.
    """
    return [id(n) for n in _l1_nodes(tree)]


def l1_bytes(tree: ConceptTree) -> list[str]:
    """Serialized ``to_dict`` of every L1 node, in tree order (for the test)."""
    return [repr(n.to_dict()) for n in _l1_nodes(tree)]


def _assert_substrate_pure(before: list[int], after: ConceptTree) -> None:
    """Assert the L1 identity fingerprint is unchanged by the stage (dev guard)."""
    now = _l1_identity(after)
    if now != before:
        raise SubstratePurityError(
            "overlay-correction stage wrote into the L1 phase-mirror substrate: "
            f"{len(before)} nodes before, {len(now)} after"
        )


# ── shared reminder-strip + oracle grounding ──────────────────────────────────

_REMINDER = re.compile(r"\([^)]*\)")


def _oracle(tree: ConceptTree) -> str:
    """The card's face oracle text, reminder-parens stripped, lowercased.

    The substrate leaves a structural node's per-node ``raw`` empty (phase carries
    a ``description`` only on a few nodes), so a text-grounded arm reads the
    whole-card oracle — a coarser grounding than the OLD per-effect ``e.raw`` but
    the same evidence for a single-clause card. Each text arm pairs it with a
    STRUCTURAL gate (concept + scope + subject) so the whole-card text only refines
    an already-plausible node.
    """
    return _REMINDER.sub(" ", tree.oracle or "").lower()


# ── (b) arm 1 — dig_into_play (category-flip, STRUCTURAL) ──────────────────────
# _recover_dig_into_play: a reveal/dig-until whose KEPT card lands on the
# battlefield (Jalira, Polymorph, Atla Palani) is a put-into-play cheat, not a
# library dig. Phase carries ``kept_destination == Battlefield`` on the
# RevealUntil / ExileFromTopUntil node — a PURE STRUCTURAL read, no oracle text.
# A LAND subject stays a dig (the extra-land-drop shape, per the OLD arm). Sets
# the compat-only ``category`` override to ``cheat_play``.


def _kept_destination_tag(node: TypedMirrorNode) -> str | None:
    kd = getattr(node, "kept_destination", MISSING)
    if isinstance(kd, str):
        return kd
    if isinstance(kd, TypedMirrorNode):
        return tag_of(kd)
    return None


def _arm_dig_into_play(cnode: ConceptNode) -> ConceptNode | None:
    if cnode.concept not in ("reveal_until", "dig", "exile_top") and tag_of(
        cnode.node
    ) not in ("RevealUntil", "ExileFromTopUntil"):
        return None
    if _kept_destination_tag(cnode.node) != "Battlefield":
        return None
    if "Land" in cnode.subject:  # extra_land_drop shape, left as a dig
        return None
    if cnode.category == "cheat_play":
        return None
    # COMPAT-only category override — see ConceptNode.category. The signal-facing
    # ``concept`` stays ``reveal_until`` so the crosswalk ``dig_until`` signal
    # holds parity with the LIVE path (which keeps emitting it).
    return replace(cnode, category="cheat_play")


# ── (b) arm 2 — exile_removal (category-flip + subject) ────────────────────────
# _recover_exile_removal: a single-target permanent-exile phase swallowed into a
# ``restriction`` / ``gain_life`` rider, or a bare exile left subjectless. The
# structural StP-class exile (ChangeZone→Exile carrying its subject) is ALREADY
# handled; only the swallow / dropped-subject residue needs the overlay, gated on
# the whole-card oracle (the exile verb survives only in text).
_EXILE_REMOVAL_RAW = re.compile(
    r"(exile|~) (?:up to (?:one|two|three|\w+|x) )?(?:other |another )?"
    r"target (?:[a-z]+ )*(creature|permanent|artifact|enchantment|planeswalker)",
    re.IGNORECASE,
)
_EXILE_REMOVAL_RETURN = re.compile(
    r"\breturn (?:it|that card|those cards|them|the exiled|each)", re.IGNORECASE
)
_EXILE_REMOVAL_SUSPEND = re.compile(r"time counter|\bsuspend\b", re.IGNORECASE)
_EXILE_REMOVAL_FROM_ZONE = re.compile(
    r"from (?:a|your|their|its owner's|each|all)?\s*(?:graveyard|hand)",
    re.IGNORECASE,
)
_EXILE_REMOVAL_SELF_TARGET = re.compile(
    r"target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)"
    r" you (?:own|control)",
    re.IGNORECASE,
)
_EXILE_HEAD_TO_TYPE = {
    "creature": "Creature",
    "permanent": "Permanent",
    "artifact": "Artifact",
    "enchantment": "Enchantment",
    "planeswalker": "Planeswalker",
}


def _is_mass(node: TypedMirrorNode) -> bool:
    return (tag_of(node) or "").endswith("All")


def _arm_exile_removal(
    tree: ConceptTree, cnode: ConceptNode, oracle: str
) -> ConceptNode | None:
    concept = cnode.concept
    dest = change_zone_dirs(cnode.node)[1]
    bare_exile = concept == "change_zone" and dest == "Exile" and not cnode.subject
    swallow = concept == "gain_life" or tag_of(cnode.node) == "AddRestriction"
    if not bare_exile and not swallow:
        return None
    if _is_mass(cnode.node):  # the board-wipe sibling — mass_removal's lane
        return None
    # gain_life swallow only when there is NO real exile sibling (StP's lifegain
    # is a genuine rider — its exile is already parsed). The OLD arm gated this on
    # the Unimplemented "~" verb; structurally, an existing exile sibling is the
    # same tell.
    if concept == "gain_life" and _card_has_real_exile(tree):
        return None
    m = _EXILE_REMOVAL_RAW.search(oracle)
    if m is None:
        return None
    if (
        _EXILE_REMOVAL_RETURN.search(oracle)
        or _EXILE_REMOVAL_SUSPEND.search(oracle)
        or _EXILE_REMOVAL_FROM_ZONE.search(oracle)
        or _EXILE_REMOVAL_SELF_TARGET.search(oracle)
    ):
        return None
    head = _EXILE_HEAD_TO_TYPE[m.group(2).lower()]
    if bare_exile:  # already compat-exile via ChangeZone → add subject only
        return replace(cnode, subject=(head,))
    # COMPAT-only ``exile`` category override (the swallowed gain_life / restriction
    # node). ``concept`` stays put so the ``lifegain`` signal the LIVE path still
    # emits (it reads oracle "gain life", not the recovered category) holds parity.
    return replace(cnode, category="exile", subject=(head,))


def _card_has_real_exile(tree: ConceptTree) -> bool:
    return any(change_zone_dirs(c.node)[1] == "Exile" for c in tree.iter_concepts())


# ── (b) arm 3 — edict_scope (field: scope) ────────────────────────────────────
# _recover_edict_scope: a ``sacrifice`` effect whose sacrificer scope phase
# dropped to the ability controller (Plaguecrafter reads scope=you where it should
# be each). "each player sacrifices" → each; "(each|target|an|that) opponent /
# target player sacrifices" → opp. A structural each/opp (Fleshbag already reads
# each) is left untouched.
_EDICT_EACH = re.compile(
    r"\beach player sacrifices?\b|\ball players sacrifice\b", re.IGNORECASE
)
_EDICT_OPP = re.compile(
    r"\b(?:each|target|an|that) opponent(?:'?s)? sacrifices?\b"
    r"|\btarget player sacrifices?\b",
    re.IGNORECASE,
)


def _arm_edict_scope(cnode: ConceptNode, oracle: str) -> ConceptNode | None:
    if cnode.concept != "sacrifice":
        return None
    if cnode.scope in ("opponents", "each"):  # structural scope already set
        return None
    if _EDICT_OPP.search(oracle):
        return replace(cnode, scope="opponents")
    if _EDICT_EACH.search(oracle):
        return replace(cnode, scope="each")
    return None


# ── (b) arm 4 — removal_target_subject (field: subject) ────────────────────────
# _recover_removal_target_subject: a damage / destroy effect whose creature /
# permanent target phase dropped to no subject (Smite, Crush Underfoot). The
# target survives in the whole-card oracle; a player/PW burn, an any-target, a
# land target, and a board wipe are all excluded (they are not single-target
# permanent removal).
_REMOVAL_DAMAGE_TARGET = re.compile(
    r"(?:deals?|dealt|deal) [^.]*?\bto target (?:[a-z]+ )*?"
    r"(?:creature|permanent)\b",
    re.IGNORECASE,
)
_REMOVAL_DESTROY_TARGET = re.compile(
    r"\bdestroy (?:up to (?:one|two|three|x) )?target (?:[a-z]+ )*?"
    r"(?:creature|permanent|artifact|enchantment|planeswalker|wall)\b",
    re.IGNORECASE,
)
_REMOVAL_LAND_TARGET = re.compile(r"\btarget (?:non-?\w+ )?land\b", re.IGNORECASE)
_REMOVAL_MASS = re.compile(r"\bdestroy (?:all|each)\b", re.IGNORECASE)


def _arm_removal_target_subject(cnode: ConceptNode, oracle: str) -> ConceptNode | None:
    if cnode.concept not in ("deal_damage", "destroy"):
        return None
    if cnode.subject:  # structured subject present — never overwrite
        return None
    if _REMOVAL_LAND_TARGET.search(oracle) or _REMOVAL_MASS.search(oracle):
        return None
    dmg = cnode.concept == "deal_damage" and _REMOVAL_DAMAGE_TARGET.search(oracle)
    dstr = cnode.concept == "destroy" and _REMOVAL_DESTROY_TARGET.search(oracle)
    if not (dmg or dstr):
        return None
    head = "Creature" if "creature" in oracle else "Permanent"
    return replace(cnode, subject=(head,))


# ── (b) arm 5 — hand_disruption reveal→reveal_hand + scope ─────────────────────
# _recover_hand_disruption (the (b) half only — the reveal→reveal_hand
# recategorization + the modal scope fix; the bucket-B synth of a whole new
# ability is deferred to (c)). (a) a ``reveal_hand`` whose recipient controller is
# an opponent but whose scope dropped → scope opponents (STRUCTURAL, off the
# recipient filter); (b) a generic ``reveal`` / topdeck peek scoped to an opponent
# whose oracle says "<player> reveals their hand" / "look at ... hand" → concept
# reveal_hand.
_HD_REVEAL_HAND_TEXT = re.compile(
    r"\breveals?\b[^.]*\b(?:their|his or her)\b[^.]*\bhands?\b", re.IGNORECASE
)
_HD_LOOK_HAND_TEXT = re.compile(r"\blook at\b[^.]*\bhands?\b", re.IGNORECASE)


def _recipient_is_opponent(node: TypedMirrorNode) -> bool:
    filt = effect_filter(node)
    return filter_controller(filt) == "Opponent" if filt is not None else False


def _arm_hand_disruption(cnode: ConceptNode, oracle: str) -> ConceptNode | None:
    if cnode.concept == "reveal_hand":
        if cnode.scope != "opponents" and _recipient_is_opponent(cnode.node):
            return replace(cnode, scope="opponents")
        return None
    if cnode.scope == "opponents":
        if cnode.concept == "reveal_top" and _HD_REVEAL_HAND_TEXT.search(oracle):
            return replace(cnode, concept="reveal_hand")
        if cnode.concept in ("scry", "surveil", "dig") and _HD_LOOK_HAND_TEXT.search(
            oracle
        ):
            return replace(cnode, concept="reveal_hand")
    return None


# ── (b) arm 6 — graveyard_zones (field: zones, focused slice) ──────────────────
# _recover_graveyard_zones (the in:graveyard recursion-reference slice only): a
# bounce / recursion whose graveyard-origin InZone phase dropped, surviving in the
# oracle as a "card ... in/from ... graveyard" reference. Ported ONLY for a
# single-effect card (the whole-card oracle == that effect's clause) so the
# SequentialSibling per-sentence bleed the OLD arm guards against cannot occur;
# the multi-sentence per-effect split is deferred to a follow-on (it needs a
# per-node ``raw`` the substrate does not yet populate). Writes the overlay
# ``zones`` field — UNIONed onto the structural zones by the compat reader.
_GY_CARD_REFERENCE = re.compile(
    r"\bcards?\b[^.]*?\b(?:in|from)\b[^.]*?\bgraveyard\b", re.IGNORECASE
)
_GY_FROM_BATTLEFIELD = re.compile(r"\bfrom the battlefield\b", re.IGNORECASE)


def _structural_zones(node: TypedMirrorNode) -> set[str]:
    out: set[str] = set()
    origin, dest = change_zone_dirs(node)
    if isinstance(origin, str):
        out.add(f"from:{origin.lower()}")
    if isinstance(dest, str):
        out.add(f"to:{dest.lower()}")
    filt = effect_filter(node)
    if filt is not None:
        out.update(f"in:{z.lower()}" for z in filter_inzone_zones(filt))
    return out


def _arm_graveyard_zones(
    cnode: ConceptNode, oracle: str, *, single_effect: bool
) -> ConceptNode | None:
    if not single_effect:
        return None
    if cnode.concept not in ("bounce", "make_token"):
        return None
    zones = _structural_zones(cnode.node) | set(cnode.zones)
    if "in:graveyard" in zones or "to:graveyard" in zones:
        return None
    if _GY_FROM_BATTLEFIELD.search(oracle) or not _GY_CARD_REFERENCE.search(oracle):
        return None
    return replace(cnode, zones=tuple(sorted(set(cnode.zones) | {"in:graveyard"})))


# ── (b) unit arm A — discard_unless (category-flip, per-unit) ──────────────────
# _recover_discard_unless: phase's "draw N, then discard a card unless <alt>"
# misparse leaves a real ``draw`` plus a DEGENERATE amount-less duplicate draw
# whose oracle is the "discard ... unless" branch. Convert the degenerate draw to
# a ``discard`` (scope you) so the loot lanes (discard_makers / discard_matters)
# read structure. Per-unit: needs the sibling real draw.
_DISCARD_UNLESS = re.compile(
    r"discard (?:a|an|one|two|three|four|five|x|\d+) cards? unless", re.IGNORECASE
)


def _has_amount(node: TypedMirrorNode) -> bool:
    for f in ("amount", "count", "value"):
        v = getattr(node, f, MISSING)
        if v is not MISSING and v is not None:
            return True
    return False


def _arm_discard_unless_unit(
    unit: AbilityUnit, oracle: str
) -> tuple[ConceptNode, ...] | None:
    draws = [c for c in unit.effects if c.concept == "draw"]
    if len(draws) < 2 or any(c.concept == "discard" for c in unit.effects):
        return None
    if not _DISCARD_UNLESS.search(oracle):
        return None
    has_real = any(_has_amount(c.node) for c in draws)
    degen = next((c for c in draws if not _has_amount(c.node)), None)
    if not has_real or degen is None:
        return None
    return tuple(
        replace(c, concept="discard", scope="you") if c is degen else c
        for c in unit.effects
    )


# ── (b) unit arm B — blink_returns_to (field: returns_to, per-unit) ────────────
# _recover_blink_returns_to: stamp ``returns_to="battlefield"`` on the EXILE half
# of a single-target exile-and-return (a blink/flicker) so a discriminator exists.
# STRUCTURAL: an exile-to-exile sibling paired with a same-ability return-to-
# battlefield. Behavior-neutral (no live consumer reads ``returns_to`` — the blink
# signal lane already reconstructs the flicker from the sibling structurally), so
# this arm is ALREADY_HANDLED at the signal; the overlay field is the faithful
# port of the OLD marker for a future consumer.
_BLINK_EXILE_VETO_ZONES = frozenset(
    {"from:graveyard", "in:graveyard", "from:library", "from:hand", "from:top"}
)


def _is_blink_return(cnode: ConceptNode) -> bool:
    if change_zone_dirs(cnode.node)[1] != "Battlefield":
        return False
    origin = change_zone_dirs(cnode.node)[0]
    return origin not in ("Graveyard", "Library", "Hand")


def _arm_blink_returns_to_unit(
    unit: AbilityUnit,
) -> tuple[ConceptNode, ...] | None:
    if not any(_is_blink_return(c) for c in unit.effects):
        return None
    changed = False
    out: list[ConceptNode] = []
    for c in unit.effects:
        zones = _structural_zones(c.node) | set(c.zones)
        is_exile_half = (
            change_zone_dirs(c.node)[1] == "Exile"
            and not any(z in _BLINK_EXILE_VETO_ZONES for z in zones)
            and not c.returns_to
        )
        if is_exile_half:
            out.append(replace(c, returns_to="battlefield"))
            changed = True
        else:
            out.append(c)
    return tuple(out) if changed else None


# ── the stage ─────────────────────────────────────────────────────────────────


def _correct_unit(
    tree: ConceptTree, unit: AbilityUnit, oracle: str, *, single_effect: bool
) -> tuple[AbilityUnit, bool]:
    """Apply the (b) arms to one ability unit; return (unit, changed)."""
    effects = unit.effects
    changed = False

    # Per-unit arms first (they read sibling co-occurrence). Each reads the
    # unit's effects; the second sees the first's output via the rebound unit.
    du = _arm_discard_unless_unit(unit, oracle)
    if du is not None:
        effects = du
        changed = True
    bl = _arm_blink_returns_to_unit(replace(unit, effects=effects))
    if bl is not None:
        effects = bl
        changed = True

    # Per-effect arms.
    new_effects: list[ConceptNode] = []
    for c in effects:
        cur = c
        for corrected in (
            _arm_dig_into_play(cur),
            _arm_exile_removal(tree, cur, oracle),
            _arm_edict_scope(cur, oracle),
            _arm_removal_target_subject(cur, oracle),
            _arm_hand_disruption(cur, oracle),
            _arm_graveyard_zones(cur, oracle, single_effect=single_effect),
        ):
            if corrected is not None:
                cur = corrected
                changed = True
        new_effects.append(cur)

    if not changed:
        return unit, False
    return replace(unit, effects=tuple(new_effects)), True


def apply_overlay_corrections(tree: ConceptTree) -> ConceptTree:
    """Run the Stage-3b (b) overlay-correction arms over one concept tree.

    Returns the tree with corrected :class:`ConceptNode` overlay fields; the L1
    phase-mirror nodes are preserved by identity (asserted by the substrate-purity
    invariant). A tree needing no correction is returned unchanged (identity).
    """
    fingerprint = _l1_identity(tree)
    oracle = _oracle(tree)
    single_effect = sum(len(u.effects) for u in tree.units) == 1

    new_units: list[AbilityUnit] = []
    changed = False
    for unit in tree.units:
        nu, uch = _correct_unit(tree, unit, oracle, single_effect=single_effect)
        changed = changed or uch
        new_units.append(nu)

    if not changed:
        return tree
    result = replace(tree, units=tuple(new_units))
    _assert_substrate_pure(fingerprint, result)
    return result
