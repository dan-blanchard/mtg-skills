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
:func:`apply_overlay_corrections` snapshots the object-**identity** fingerprint of
every L1 node before the stage and asserts it unchanged after, so a correction
that swapped a mirror node for a rebuilt one — the realistic leak mode, since an
arm would ``dataclasses.replace`` the node to write it — fails loud
(:class:`SubstratePurityError`). The live guard is that id-check; the committed
test pairs it with a byte-level ``to_dict`` round-trip (:func:`l1_bytes`) so
content drift is caught too, and a dedicated negative test proves the id-check is
not vacuous — it catches even a *byte-identical* rebuild, which the byte-check
alone would miss. The frozen ``TypedMirrorNode`` rules out in-place mutation, so
those checks together enforce the invariant (it is guarded + tested, not provable
by construction alone).

Called by ``compat_card`` and ``extract_crosswalk_signals`` — since the ADR-0039
cutover, the only build paths there are. These arms are the concept-overlay
ports of the supplement's ``_recover_*`` originals (their legacy ``project.py``
orchestrator died in step 7; ``supplement.py`` keeps the arms the compat stages
still reuse).

Six live arms run at the current phase pin (v0.9.0): ``dig_into_play``,
``exile_removal``, ``edict_scope``, ``removal_target_subject``, ``graveyard_zones``
(per-effect) and ``blink_returns_to`` (per-unit). Two v0.8.0-era arms —
``discard_unless`` (a phase draw-then-discard misparse) and ``hand_disruption``'s
reveal→reveal_hand recategorization — were RETIRED here: both fired on zero corpus
cards at v0.9.0 (phase fixed the draw misparse; the crosswalk ``hand_disruption``
signal lane already reads the reveal STRUCTURALLY), and both were concept-rewrites,
the one shape this stage deliberately avoids (a ``concept`` flip moves the Signal
seam — see ``ConceptNode.category``).

Each arm records whether the crosswalk substrate ALREADY handles the correction
(``already_handled``) or the overlay genuinely adds it (``newly_ported``) — the
per-arm bucketing ADR-0035 Stage-3b calls for.

**Field arms.** A wrong field on an effect is that effect's ``ConceptNode``
decoration — a ``scope`` or a ``subject`` mark. A wrong field on a node that has
no ``ConceptNode`` — a static def's ``affected``, a target filter's
``controller``, a trigger's dropped counter kind — is a
:class:`~mtg_utils._card_ir.crosswalk.FieldCorrection` on the unit
(``AbilityUnit.corrections``), read through the shared reads that take the unit
(``filter_controller(filt, unit)``, ``static_affected(sdef, unit)``); the
trigger-event arm rewrites the unit's derived ``trigger_event``. All keep every
mirror node by identity, so the same purity guard covers them. Each carries a
``retirement_canary`` (tests/mtg-utils/test_phase_gaps_fields.py).
"""

from __future__ import annotations

import re
from dataclasses import replace

# ── substrate-purity invariant (shared with dropped_clauses, ADR-0035 3b) ──────
# Factored into ``_substrate_purity`` so bucket (b) here and bucket (c)
# (``dropped_clauses``) enforce the SAME property from one home. Re-exported under
# the historic private names (``__all__`` below) so the committed tests keep
# importing them here.
from mtg_utils._card_ir._substrate_purity import (
    SubstratePurityError,
    l1_bytes,
)
from mtg_utils._card_ir._substrate_purity import (
    assert_substrate_pure as _assert_substrate_pure,
)
from mtg_utils._card_ir._substrate_purity import (
    l1_identity as _l1_identity,
)
from mtg_utils._card_ir._substrate_purity import (
    l1_nodes as _l1_nodes,
)
from mtg_utils._card_ir.crosswalk import (
    ANAPHORIC,
    SUSPENDED_CARD,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    FieldCorrection,
    adds_creature_type,
    answers_its_target,
    change_zone_dirs,
    effect_filter,
    effect_owner_raw,
    filter_controller,
    filter_inzone_zones,
    filter_owners,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    static_mode_tag,
    tag_of,
)
from mtg_utils._card_ir.crosswalk.reads import ends_target_thread
from mtg_utils._card_ir.mirror.runtime import MISSING, TypedMirrorNode
from mtg_utils._card_ir.recovery import TARGET_OBJECT

# The substrate-purity names re-exported here for the committed tests (and the
# historic private aliases callers import from this module).
__all__ = [
    "SubstratePurityError",
    "_assert_substrate_pure",
    "_l1_identity",
    "_l1_nodes",
    "apply_overlay_corrections",
    "l1_bytes",
]

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
# the whole-card oracle (the exile verb survives only in text). 9 cards fire
# corpus-wide at the v0.9.0 pin: 8 take the bare-exile subject-add; exactly ONE
# (the card *Exile*) takes the gain_life→exile category-flip, pinned by
# test_overlay_exile_removal_lands_category_and_subject.
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


# ── (b) arm 5 — graveyard_zones (field: zones, focused slice) ──────────────────
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


# ── (b) unit arm — blink_returns_to (field: returns_to, per-unit) ──────────────
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


# ── (b) field and decoration arms over one unit ───────────────────────────────
# A wrong field on an effect is that effect's ConceptNode decoration: a ``scope``
# or a ``subject`` mark (``anaphoric_pump``, ``graveyard_owner``,
# ``suspended_card_target``). A wrong field on a node with no ConceptNode of its
# own — a static def, a trigger def, a target filter — is a
# :class:`FieldCorrection` on the unit (``AbilityUnit.corrections``), read through
# the shared reads that take the unit (``filter_controller(filt, unit)``,
# ``static_affected(sdef, unit)``). Each arm names the one shape it re-reads and
# carries a ``retirement_canary`` in tests/mtg-utils/test_phase_gaps_fields.py
# that fails RETIRE-READY once phase stamps the field right. A text read is the
# node's own clause (:func:`_clause_text`).


def _clause_text(tree: ConceptTree, unit: AbilityUnit, node: object) -> str:
    """The clause ``node`` sits in, reminder-stripped and lowercased: a def's own
    ``description``, else its owning wrapper's, else the unit's; the card's
    oracle only for a one-ability card whose unit carries no description at all
    (Delirium's spell ability) — a multi-ability card never reads another
    ability's sentence."""
    raw = getattr(node, "description", None)
    if not isinstance(raw, str) or not raw:
        raw = effect_owner_raw(unit.node, node) or getattr(
            unit.node, "description", None
        )
    if raw is None and len(tree.units) == 1:
        raw = tree.oracle
    return _REMINDER.sub(" ", raw or "").lower()


# "X doesn't untap during …" (CR 502.3: effects can keep a permanent from
# untapping). Phase stamps ``affected: SelfRef`` on every such static; the
# subject before "doesn't untap" says whose it is. "~" (or "~ enters tapped and")
# is the card; any other subject — "that creature" (Mesmerizing Benthid's token),
# "each land with an activated ability" (Tsabo's Web), "enchanted creature … it"
# (Stunning Strike) — is another object. A def with no subject ("doesn't untap
# during its controller's next untap step") is the object an earlier clause of
# its unit chose (Wall of Stolen Identity, Telekinesis, Triton Tactics) unless
# the unit names no object but the card (Apes of Rath's "whenever ~ attacks, it
# doesn't untap"); "your untap step" is always the card's own drawback (the
# depletion lands).
_UNTAP_SUBJECT = re.compile(r"^(.*?)\s*\bdoesn't untap\b")
_SELF_SUBJECT = re.compile(r"(?:^|,\s*)~(?: enters tapped and)?$")
_OBJECT_TARGET_TAGS = frozenset({"Typed", "Or", "And", "Any", "ParentTarget"})


def _names_an_object(unit: AbilityUnit) -> bool:
    """Whether some effect of the unit picks an object other than the card."""
    return any(
        tag_of(getattr(n, "target", None)) in _OBJECT_TARGET_TAGS
        for n in unit.iter_typed()
    )


def _arm_cant_untap_object(
    tree: ConceptTree, unit: AbilityUnit
) -> list[FieldCorrection]:
    out: list[FieldCorrection] = []
    for sdef in iter_static_defs(unit.node):
        if static_mode_tag(sdef) != "CantUntap":
            continue
        if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
            continue
        desc = _clause_text(tree, unit, sdef).strip()
        m = _UNTAP_SUBJECT.search(desc)
        if m is None:
            continue
        subject = m.group(1).strip()
        if subject:
            other = _SELF_SUBJECT.search(subject) is None
        else:
            other = "its controller's" in desc and _names_an_object(unit)
        if other:
            out.append(
                FieldCorrection(sdef, "affected", ANAPHORIC, "cant_untap_object")
            )
    return out


# "Tap target creature that player controls" (Delirium), "tap all lands that
# player controls" (Mana Web, Nature's Will): phase stamps the tapped filter
# ``controller: You``, the same stamp as "tap any number of untapped creatures you
# control" (Jaddi Lifestrider). "That player" is the player an earlier clause
# named. Arena's "tap … target creature of an opponent's choice they control"
# carries the same stamp; its own wrapper's ``target_chooser: Opponent`` names
# "they" (Arena, Magus of the Arena).
_TAP_THAT_PLAYER = re.compile(r"\btap\b([^.]*?)\bthat player controls\b")


def _opponent_chooses(unit: AbilityUnit, node: object) -> bool:
    """Whether the wrapper holding ``node`` hands its target choice to an
    opponent."""
    return any(
        getattr(w, "effect", None) is node
        and tag_of(getattr(w, "target_chooser", None)) == "Opponent"
        for w in unit.iter_typed()
    )


def _arm_tap_other_player(
    tree: ConceptTree, unit: AbilityUnit
) -> list[FieldCorrection]:
    out: list[FieldCorrection] = []
    for c in unit.effects:
        node = c.node
        if tag_of(node) != "SetTapState":
            continue
        target = getattr(node, "target", None)
        if (
            not isinstance(target, TypedMirrorNode)
            or filter_controller(target) != "You"
        ):
            continue
        m = _TAP_THAT_PLAYER.search(_clause_text(tree, unit, node))
        if (m is not None and "you control" not in m.group(1)) or _opponent_chooses(
            unit, node
        ):
            out.append(
                FieldCorrection(target, "controller", ANAPHORIC, "tap_other_player")
            )
    return out


# "When an opponent casts an artifact spell, if ~ is an enchantment, it becomes
# a 5/3 Soldier creature" (Hidden Guerrillas and the Hidden / Opal / Veiled
# cycles): "it" is the card (its ruling: "When it turns into a creature, it is
# no longer an enchantment"), but phase stamps the animation ``affected:
# TriggeringSource`` — the cast spell. The trigger's own "if ~ is …" condition
# (``SourceMatchesFilter``) is the tell that "it" is the source.
def _arm_self_animation(_tree: ConceptTree, unit: AbilityUnit) -> list[FieldCorrection]:
    if unit.origin != "trigger":
        return []
    cond = getattr(unit.node, "condition", None)
    if not any(tag_of(n) == "SourceMatchesFilter" for n in iter_typed_nodes(cond)):
        return []
    return [
        FieldCorrection(sdef, "affected", "SelfRef", "self_animation")
        for sdef in iter_static_defs(unit.node)
        if tag_of(getattr(sdef, "affected", None)) == "TriggeringSource"
        and adds_creature_type(sdef)
    ]


def _ends_thread(eff: TypedMirrorNode) -> bool:
    """A mass effect ends the chosen-target thread: Chimeric Idol's "tap all lands
    you control. ~ becomes a 3/3" animates the card, not the lands."""
    return ends_target_thread(eff) or tag_of(getattr(eff, "scope", None)) == "All"


def _enchanted_filter(cond: object) -> object | None:
    """The ``EnchantedBy`` filter an Aura's static condition names ("as long as
    enchanted artifact isn't a creature") — never one under a ``Not``."""
    tag = tag_of(cond)
    if tag == "And":
        for sub in getattr(cond, "conditions", None) or ():
            found = _enchanted_filter(sub)
            if found is not None:
                return found
    if tag == "IsPresent":
        filt = getattr(cond, "filter", None)
        if any(tag_of(p) == "EnchantedBy" for p in iter_typed_nodes(filt)):
            return filt
    return None


# The animated object phase stamps ``SelfRef``: "choose up to one target Mount or
# Vehicle you control. … that permanent … becomes an artifact creature" (Alacrian
# Armory — the chain's chosen target), and an Aura's "enchanted artifact … is an
# artifact creature" (Animate Artifact; Aerial and Siege Modification's
# "enchanted permanent … is a creature" — CR 303.4b: the enchanted object). The
# correction is the filter phase did parse: the threaded target, or the
# condition's ``EnchantedBy`` filter.
def _arm_animated_object(tree: ConceptTree, unit: AbilityUnit) -> list[FieldCorrection]:
    out = [
        FieldCorrection(sdef, "affected", target, "animated_object")
        for target, sdef in iter_threaded_target_statics(
            unit.node, affected_tag="SelfRef", resets_thread=_ends_thread
        )
        if adds_creature_type(sdef)
    ]
    if "Aura" in tree.card_subtypes:
        for sdef in iter_static_defs(unit.node):
            if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
                continue
            if not adds_creature_type(sdef):
                continue
            filt = _enchanted_filter(getattr(sdef, "condition", None))
            if filt is not None:
                out.append(FieldCorrection(sdef, "affected", filt, "animated_object"))
    return out


# "Whenever you get one or more {E}" (Territorial Gorger): phase types the
# trigger ``CounterPlayerAddedAll`` and drops the counter kind (CR 107.14: {E} is
# one energy counter). Every such trigger of the corpus is an energy one; the
# kind is in the trigger's own clause.
_GETS_ENERGY = re.compile(r"\bone or more \{e\}")


def _arm_player_counter_kind(
    tree: ConceptTree, unit: AbilityUnit
) -> list[FieldCorrection]:
    return [
        FieldCorrection(n, "counter_kind", "energy", "player_counter_kind")
        for n in unit.iter_typed()
        if getattr(n, "mode", None) == "CounterPlayerAddedAll"
        and _GETS_ENERGY.search(_clause_text(tree, unit, n))
    ]


# ── fresh_tap_target ──────────────────────────────────────────────────────────
# "Tap up to one target creature an opponent controls and put a stun counter on
# it" (Stunning Shot), "When you do, tap target creature an opponent controls"
# (Snaremaster Sprite), "If the gift was promised, tap target creature …" (Mind
# Spiral): the clause picks its own target (CR 115.1), but phase stamps the
# ``SetTapState`` ``target: ParentTarget`` — the bare back-reference a "tap it"
# carries, with the filter lost. The clause read is the tap's own wrapper
# description only, never the unit's or the card's, so a later "tap it" never
# borrows an earlier sentence's target. The decoration is the seam's
# ``TARGET_OBJECT`` subject mark — the mark a recovered "tap target creature"
# carries — which the tapper lane reads.
_FRESH_TAP_TARGET = re.compile(
    r"(?:^|, )tap (?:up to (?:\w+|that many) )?(?:other )?target\b"
)


def _arm_fresh_tap_target(unit: AbilityUnit, cnode: ConceptNode) -> ConceptNode | None:
    if TARGET_OBJECT in cnode.subject or tag_of(cnode.node) != "SetTapState":
        return None
    if tag_of(getattr(cnode.node, "target", None)) != "ParentTarget":
        return None
    own = effect_owner_raw(unit.node, cnode.node) or ""
    if not _FRESH_TAP_TARGET.search(_REMINDER.sub(" ", own).lower()):
        return None
    return replace(cnode, subject=(*cnode.subject, TARGET_OBJECT))


# The def / filter arms (FieldCorrection).
_FIELD_ARMS = (
    _arm_cant_untap_object,
    _arm_tap_other_player,
    _arm_self_animation,
    _arm_animated_object,
    _arm_player_counter_kind,
)


# ── effect decorations: a wrong field on an effect's own ConceptNode ──────────


# "it gets -N/-0" in a delayed trigger or a spell's own chain (Blood Lust,
# Six-Sided Die): phase stamps the delayed trigger's
# pump ``target: SelfRef``; the arm reads "it" as the creature the delayed
# trigger watched (a ``Typed`` watched object, never the card). An instant's or
# sorcery's ``SelfRef`` pump is an object an earlier clause chose (Blood Lust's
# "if target creature has toughness 5 or greater, it gets +4/-4"; Six-Sided
# Die's "It gets -4/-4"): the spell is never on the battlefield to pump itself.
# The decoration is the :data:`ANAPHORIC` subject mark
# (``reads.targets_the_card``).
def _anaphoric_pumps(tree: ConceptTree, unit: AbilityUnit) -> set[int]:
    def self_pump(n: object) -> bool:
        return tag_of(n) == "Pump" and tag_of(getattr(n, "target", None)) == "SelfRef"

    out: set[int] = set()
    for n in unit.iter_typed():
        if tag_of(n) != "CreateDelayedTrigger":
            continue
        trigger = getattr(getattr(n, "condition", None), "trigger", None)
        if tag_of(getattr(trigger, "valid_card", None)) in ("Typed", "Or", "And"):
            out.update(
                id(p)
                for p in iter_typed_nodes(getattr(n, "effect", None))
                if self_pump(p)
            )
    if {"Instant", "Sorcery"} & set(tree.card_types):
        # The spell's own chain only: a token it makes or an ability it grants
        # pumps itself ("'{R}: This creature gets +1/+0'" — Dragonrage).
        out.update(id(c.node) for c in unit.effects if self_pump(c.node))
    return out


def _arm_anaphoric_pump(cnode: ConceptNode, pumps: set[int]) -> ConceptNode | None:
    if id(cnode.node) not in pumps or ANAPHORIC in cnode.subject:
        return None
    return replace(cnode, subject=(*cnode.subject, ANAPHORIC))


# An exile out of a graveyard whose filter names no owner: phase drops "your" off
# "exile target card … from your graveyard" (Rooting Moloch), "defending
# player's" / "that player's" off an opponent's (Grime Gorger, Skullsnatcher,
# Zombie Cannibal) and leaves "a graveyard" (Savior of Ollenbock) without the
# ``InZone`` its siblings carry. The owner is in the exile's own clause; every
# graveyard sentence of it must agree, or the arm stands down (Waste
# Management's "a single graveyard" beside its kicked "target player's
# graveyard"). The decoration is the exile's ``scope``: you / opponents / any.
_GY_OWNER_PHRASES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("you", re.compile(r"\byour graveyard\b")),
    (
        "opponents",
        re.compile(
            r"\b(?:(?:that|target|defending) player|(?:an|target|that|each) "
            r"opponent)'s graveyard\b"
        ),
    ),
    ("any", re.compile(r"\b(?:from|in) a (?:single )?graveyard\b")),
)


def _arm_graveyard_owner(
    tree: ConceptTree, unit: AbilityUnit, cnode: ConceptNode
) -> ConceptNode | None:
    node = cnode.node
    # A targeted exile; a mass one ("then exile all graveyards" — Abstergo
    # Entertainment) shares its sentence with another clause's owner.
    if not answers_its_target(node) or (tag_of(node) or "").endswith("All"):
        return None
    filt = effect_filter(node)
    if tag_of(filt) not in ("Typed", "Or") or any(filter_owners(filt)):
        return None
    in_zone = "Graveyard" in filter_inzone_zones(filt)
    if change_zone_dirs(node)[0] != "Graveyard" and not in_zone:
        return None
    owners = {
        owner
        for sentence in _clause_text(tree, unit, node).split(".")
        if "graveyard" in sentence
        for owner, rx in _GY_OWNER_PHRASES
        if rx.search(sentence)
    }
    # An ownerless ``InZone(Graveyard)`` filter already reads "a graveyard";
    # only an owner it dropped is a correction there.
    if len(owners) != 1 or (in_zone and owners == {"any"}):
        return None
    (owner,) = owners
    return None if cnode.scope == owner else replace(cnode, scope=owner)


# "Return target nonland permanent or suspended card to its owner's hand"
# (Venser's Diffusion): phase keeps the permanent and drops the "or suspended
# card" alternative (CR 702.62b: a card in exile with suspend and a time
# counter). Clockspinning's same alternative carries its time-counter predicate.
# The decoration is the :data:`SUSPENDED_CARD` subject mark.
def _arm_suspended_card_target(
    tree: ConceptTree, unit: AbilityUnit, cnode: ConceptNode
) -> ConceptNode | None:
    if tag_of(cnode.node) != "Bounce" or SUSPENDED_CARD in cnode.subject:
        return None
    if "or suspended card" not in _clause_text(tree, unit, cnode.node):
        return None
    return replace(cnode, subject=(*cnode.subject, SUSPENDED_CARD))


def _decorate_effects(tree: ConceptTree, unit: AbilityUnit) -> AbilityUnit:
    """The effect decoration arms over one unit (identity when none fires)."""
    pumps = _anaphoric_pumps(tree, unit)
    changed = False
    effects: list[ConceptNode] = []
    for c in unit.effects:
        cur = c
        for corrected in (
            _arm_anaphoric_pump(cur, pumps),
            _arm_graveyard_owner(tree, unit, cur),
            _arm_suspended_card_target(tree, unit, cur),
            _arm_fresh_tap_target(unit, cur),
        ):
            if corrected is not None:
                cur = corrected
                changed = True
        effects.append(cur)
    return replace(unit, effects=tuple(effects)) if changed else unit


# "Whenever a creature with a coin counter on it is put into exile" (Athreos,
# Shroud-Veiled): phase types the exile half as a ``CounterAdded`` trigger
# watching ``Any`` — the only ``CounterAdded`` trigger of the corpus whose
# watched object is ``Any``. Its event is the zone change, not a placement.
_PUT_INTO_EXILE = re.compile(r"\bis put into exile\b")


def _arm_counter_added_zone_change(
    tree: ConceptTree, unit: AbilityUnit
) -> AbilityUnit | None:
    if unit.origin != "trigger" or unit.trigger_event != "counter_added":
        return None
    if tag_of(getattr(unit.node, "valid_card", None)) != "Any":
        return None
    if not _PUT_INTO_EXILE.search(_clause_text(tree, unit, unit.node)):
        return None
    return replace(unit, trigger_event="changes_zone")


def _correct_fields(tree: ConceptTree, unit: AbilityUnit) -> AbilityUnit:
    """The field, effect-decoration and trigger-event arms over one unit
    (identity when none fires)."""
    found = [fc for arm in _FIELD_ARMS for fc in arm(tree, unit)]
    if found:
        unit = replace(unit, corrections=(*unit.corrections, *found))
    unit = _decorate_effects(tree, unit)
    return _arm_counter_added_zone_change(tree, unit) or unit


# ── the stage ─────────────────────────────────────────────────────────────────


def _correct_unit(
    tree: ConceptTree, unit: AbilityUnit, oracle: str, *, single_effect: bool
) -> tuple[AbilityUnit, bool]:
    """Apply the (b) arms to one ability unit; return (unit, changed)."""
    effects = unit.effects
    changed = False

    # Per-unit arm (reads sibling co-occurrence): stamp the blink returns_to
    # marker off an exile/return pair within the unit.
    bl = _arm_blink_returns_to_unit(unit)
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
        fixed = _correct_fields(tree, nu)
        changed = changed or uch or fixed is not nu
        new_units.append(fixed)

    if not changed:
        return tree
    result = replace(tree, units=tuple(new_units))
    _assert_substrate_pure(fingerprint, result)
    return result
