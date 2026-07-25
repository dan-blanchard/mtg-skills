"""Value-engine (cloning, recursion, theft, kill, big-hand, power-tap) synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    effect_owner_player_scope,
    effect_reaches_player,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    hand_size_scopes,
    has_nested_connive,
    has_nested_extra_turn,
    has_nested_fight,
    has_nested_flip_coin,
    has_nested_roll_die,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_typed_nodes,
    recipient_tag,
    static_mode_tag,
    tag_of,
    trigger_constraint_tag,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _CASCADE_GRANT,
    _CHANGELING_REF,
    _KEYWORD_COST_SAC,
    _PITCH_SAC,
    _SOULBOND_REF,
    _UNDYING_PERSIST_GRANT,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._card_ir.tree_synthesis.death_life import (
    _is_death_payoff_effect,
    _is_self_return_effect,
    _is_shuffle_back_effect,
)
from mtg_utils._deck_forge.text_reads import (
    _FIGHT_RAW,
    _MELD_FULLTEXT_RE,
    _POWER_SCALING_RAW,
    _self_dies_value,
    _self_etb_value,
    _self_name_alts,
)

# ── wants_cloning structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_wants_cloning`` lane (a LOW clone-TARGET membership heuristic — CR
# 707.1 copy / 704.5j legend rule) reads these typed predicates; this stage's
# bucket-B gap gate (:func:`_arm_wants_cloning`) reads the SAME
# :func:`has_self_etb_value` / :func:`has_self_dies_value` so the lane and the synth
# never disagree on which self-ETB/dies value phase structuralizes (the
# gap-gate-alignment invariant — one source, no drift). The card-level gates
# (Legendary+Creature, ``cmc >= 5``) stay in the lane, already structural
# (``card_supertypes`` / ``is_type`` / ``cmc``).

# Compound self-ETB trigger events phase derives ("~ enters", "~ enters or attacks"
# — All-Seeing Arbiter, Aragorn and Arwen; the Haunt "enters or the haunted
# creature dies" front) — read off ``trigger_event`` exactly like
# ``CAST_TRIGGER_EVENTS`` / ``ATTACK_TRIGGER_EVENTS``.
ETB_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {"enters", "entersorattacks", "entersorhauntedcreaturedies"}
)
# Per-turn-cadence trigger CONSTRAINTS phase types on a recurring value engine
# (CR 603.2): "the first time each turn" / "once each turn" (``OncePerTurn``),
# "your second spell each turn" (``NthSpellThisTurn`` — Alphinaud, Sevinne),
# "your second card each turn" (``NthDrawThisTurn`` — Alandra, Blue Marvel). A
# clone forks the per-turn value, so these mark a genuine engine.
PER_TURN_CONSTRAINT_TAGS: frozenset[str] = frozenset(
    {"OncePerTurn", "NthSpellThisTurn", "NthDrawThisTurn"}
)
# ETB card-advantage / board-impact VALUE verbs beyond the death payoff set — a
# clone/token-copy re-fires the self-ETB, so these are the value forms a
# high-value ETB creature wants (Solemn's tutor, Man-o'-War's bounce, Duplicant's
# exile, Sakashima-adjacent copy). Unioned with :data:`_DEATH_PAYOFF_EFFECTS`.
_CLONE_ETB_VALUE: frozenset[str] = frozenset(
    {
        "tutor",
        "bounce",
        "change_zone",
        "gain_control",
        "scry",
        "reveal_top",
        "reveal_hand",
        "investigate",
        "copy_spell",
        "copy_token",
        "conjure",
        "amass",
    }
)


def is_clone_value_effect(e: ConceptNode) -> bool:
    """The shared "non-vanilla VALUE effect" predicate for the ETB and dies arms.

    Reuses the death fold's :func:`_is_death_payoff_effect` (card advantage / drain
    / tokens / counters / reanimation-deploy) unioned with the ETB-specific
    card-advantage verbs (:data:`_CLONE_ETB_VALUE`), MINUS the two self-preservation
    forms (:func:`_is_self_return_effect` — undying/persist return; and
    :func:`_is_shuffle_back_effect` — shuffle-into-library protection), which are
    resilience, not a fork-worthy clone-want (CR 700.4). One source for both arms so
    they never drift.
    """
    if _is_self_return_effect(e) or _is_shuffle_back_effect(e):
        return False
    return _is_death_payoff_effect(e) or e.concept in _CLONE_ETB_VALUE


# Per-turn CAST/PLAY-permission frequencies phase types on a recurring
# card-advantage engine (CR 601.3e / 118.5 permission): a "once each turn, you may
# play/cast a card from <non-hand zone>" grant. ``OncePerTurn`` is the recurring
# cadence a clone forks; the ``Unlimited`` permissions (Bolas's Citadel, Future
# Sight) carry no per-turn cadence and stay out of this read (they were never a
# PER_TURN mirror hit either).
PER_TURN_CAST_FREQS: frozenset[str] = frozenset({"OncePerTurn"})
# Cast/play-permission static MODES phase emits for "you may play/cast a card from
# <exile|top-of-library>" (CR 601.3e) — the ``frequency``-carrying shapes.
_CAST_PERMISSION_MODES: frozenset[str] = frozenset(
    {"TopOfLibraryCastPermission", "ExileCastPermission"}
)


def _once_per_turn_restricted(node: object) -> bool:
    """Whether an activated-ability node carries an ``OnlyOnceEachTurn`` activation
    restriction (CR 602.5f) — the "Activate only once each turn" cap phase types as
    an ``activation_restrictions`` entry."""
    ars = getattr(node, "activation_restrictions", None)
    if not isinstance(ars, (list, tuple)):
        return False
    return any(tag_of(a) == "OnlyOnceEachTurn" for a in ars)


def _has_once_per_turn_cast_engine(tree: ConceptTree) -> bool:
    """A once-each-turn permission to CAST/PLAY a card from a zone other than hand —
    a recurring card-ADVANTAGE engine a clone forks (Evelyn, Johann, The Fourth
    Doctor, Maralen Fae Ascendant, Chainer, Mavinda). CR 601.3e / 707.

    Three typed surfaces, all gated to the ``OncePerTurn`` cadence
    (:data:`PER_TURN_CAST_FREQS`) so the ``Unlimited`` continuous permissions and
    the plain per-turn RESTRICTIONS on non-advantage abilities (self-pump, tap,
    mana, attach — CR 602.5f caps that a clone gains nothing from) stay out:

    * a ``grant_cast_permission`` EFFECT whose ``permission`` sub-node has a
      per-turn ``frequency`` (Evelyn's "once each turn, you may play a card from
      exile" — a ``PlayFromExile`` permission);
    * a static ability whose MODE is a cast-from-exile / cast-from-top permission
      (:data:`_CAST_PERMISSION_MODES` via :func:`static_mode_tag`) whose inner spec
      has a per-turn ``frequency`` (Johann / The Fourth Doctor / Maralen Fae);
    * an own activated ability with an ``OnlyOnceEachTurn`` restriction whose effect
      CASTS a card from a zone (``cast_from_zone`` — Chainer's graveyard recast,
      Mavinda). A once-each-turn cap on a self-pump / mana / attach ability is NOT a
      card-advantage engine and is deliberately not read here.
    """
    for unit in tree.units:
        if unit.origin == "static" and (
            static_mode_tag(unit.node) in _CAST_PERMISSION_MODES
        ):
            inner = getattr(getattr(unit.node, "mode", None), "inner", None)
            if getattr(inner, "frequency", None) in PER_TURN_CAST_FREQS:
                return True
        if (
            unit.origin == "ability"
            and _once_per_turn_restricted(unit.node)
            and any(c.concept == "cast_from_zone" for c in unit.effects)
        ):
            return True
        for c in unit.effects:
            if c.concept == "grant_cast_permission":
                perm = getattr(c.node, "permission", None)
                if getattr(perm, "frequency", None) in PER_TURN_CAST_FREQS:
                    return True
    return False


def has_repeatable_engine(tree: ConceptTree) -> bool:
    """A repeatable per-turn VALUE engine a clone would fork each turn (CR 707).

    Typed tells: a beginning-of-phase trigger (``trigger_event == "phase"`` — the
    upkeep/end-step/combat engines phase derives, including the "at the beginning of
    combat on your turn" form the regex mirror's ``of your combat`` literal missed),
    a trigger with a per-turn-cadence CONSTRAINT (:data:`PER_TURN_CONSTRAINT_TAGS` —
    the "Nth thing each turn" recurring engines), an extra-turn / extra-phase
    generator (``extra_turn`` / ``extra_phase`` — Koma, Aurelia), or a
    once-each-turn CAST/PLAY-permission card-advantage engine
    (:func:`_has_once_per_turn_cast_engine` — Evelyn, Johann, Maralen Fae). A "once
    each turn" RESTRICTION on a non-advantage ability (self-pump, mana dork, A-Nadu's
    twice-a-turn TRIGGER cap) carries no such typed shape, so it is correctly shed.
    """
    for unit in tree.units:
        if unit.trigger_event == "phase":
            return True
        if unit.origin == "trigger" and (
            trigger_constraint_tag(unit.node) in PER_TURN_CONSTRAINT_TAGS
        ):
            return True
    if _has_once_per_turn_cast_engine(tree):
        return True
    return tree.has_effect("extra_turn") or tree.has_effect("extra_phase")


def has_value_tap_ability(tree: ConceptTree) -> bool:
    """An activated ability with a Tap cost whose value is MORE than mana (CR 602).

    An own activated ability (``origin == "ability"``) whose cost leaves include a
    ``Tap`` and whose effects are not solely ``ramp`` — the repeatable tap engine a
    clone forks, minus the vanilla mana dork (a bare ``{T}: Add`` whose only effect
    is ``ramp`` — the structural ``_MANA_TAP_RE`` carve-out). Reads the card's OWN
    activated abilities only, so a ``{T}:`` GRANTED to other creatures
    ("creatures you control have '{T}: …'" — Ghired, Sliv-Mizzet) is not the card's
    engine and is correctly shed.
    """
    for unit in tree.units:
        if unit.origin != "ability":
            continue
        cost = getattr(unit.node, "cost", None)
        leaves = {tag_of(leaf) for leaf in iter_cost_leaves(cost)}
        if "Tap" in leaves and any(c.concept != "ramp" for c in unit.effects):
            return True
    return False


def has_self_etb_value(tree: ConceptTree) -> bool:
    """A self-ETB VALUE trigger — a clone/token-copy re-fires it (CR 603.6).

    A trigger unit whose event is a self-enters form (:data:`ETB_TRIGGER_EVENTS`)
    watching the source itself (``valid_card`` = ``SelfRef``) with a
    :func:`is_clone_value_effect` effect. Shared by the lane's arm 2 and this
    stage's gap gate — one source, no drift.
    """
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event in ETB_TRIGGER_EVENTS
            and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
            and any(is_clone_value_effect(c) for c in unit.effects)
        ):
            return True
    return False


# The iteration-3 lane's WIDER value set: has_self_etb_value gates on
# is_clone_value_effect (clone-worthy payloads for wants_cloning) and misses
# the removal half of the recast-loop class — Shriekmaw ['destroy'],
# Fleshbag Marauder ['sacrifice'] (probed 2026-07-18). This set names the
# effect CONCEPTS a self-ETB trigger converts into value on every re-entry.
_SELF_ETB_PAYLOAD_CONCEPTS = frozenset(
    {"destroy", "draw", "sacrifice", "damage", "discard", "mill", "tutor", "exile"}
)


def has_self_etb_payload(tree: ConceptTree) -> bool:
    """A self-ETB trigger with a VALUE payload — the recast-loop candidate
    class (iteration-3 pair row): each re-entry re-fires it (CR 603.6a),
    so under a commander that repeatably recasts/reanimates/bounces the
    permanent, the one-shot clause is a per-turn engine. Wider than
    :func:`has_self_etb_value` (which keeps its is_clone_value_effect gate
    for wants_cloning): any :data:`_SELF_ETB_PAYLOAD_CONCEPTS` effect
    qualifies — Shriekmaw's destroy, Mulldrifter's draw, Fleshbag
    Marauder's edict sacrifice."""
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event in ETB_TRIGGER_EVENTS
            and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
            and any(c.concept in _SELF_ETB_PAYLOAD_CONCEPTS for c in unit.effects)
        ):
            return True
    return False


def _subtree_has_graveyard_zone(root: object) -> bool:
    """Whether any filter node in the unit subtree is ``InZone(Graveyard)``
    — reanimation targets carry their source zone on the TARGET filter, not
    the ChangeZone effect (Meren's ``origin`` is absent; the "creature card
    in your graveyard" scoping is the filter's InZone property)."""
    seen: set[int] = set()
    queue = [root]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        if tag_of(node) == "InZone" and getattr(node, "zone", None) == "Graveyard":
            return True
        for v in vars(node).values():
            if isinstance(v, TypedMirrorNode):
                queue.append(v)
            elif isinstance(v, list):
                queue.extend(x for x in v if isinstance(x, TypedMirrorNode))
    return False


def has_own_target_spell(tree: ConceptTree) -> bool:
    """An instant/sorcery that TARGETS your own permanent by its printed
    filter (``Typed`` target with ``controller == You`` — Ephemerate, Feat
    of Resistance, Fall of the Hammer's first target) — the own-target
    pair row's candidate class (iteration-4): a spell-recursion commander
    (Feather) rebates exactly these every turn. Two arms (4b widening,
    measured: the strict arm alone halved Feather's median target rank —
    4340 to 2611 — but left top-250 recall flat, so the beneficial-pump
    class was admitted):

    * a ``Typed`` target with ``controller == You`` (the printed
      own-target class — Ephemerate); or
    * a NON-NEGATIVE targeted ``pump`` on a creature (Infuriate, Defiant
      Strike — a beneficial pump is own-directed in practice; a "-X/-X"
      debuff-removal spell fails the sign gate, the anthem lane's rule).
    """
    if not (tree.is_type("Instant") or tree.is_type("Sorcery")):
        return False
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "pump":
                continue
            tgt = getattr(c.node, "target", None)
            if not (
                isinstance(tgt, TypedMirrorNode)
                and tag_of(tgt) == "Typed"
                and "Creature" in filter_core_types(tgt)
            ):
                continue
            if not any(v < 0 for v in _pump_mod_ints(c.node)):
                return True
    seen: set[int] = set()
    queue: list[object] = [u.node for u in tree.units]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        tgt = getattr(node, "target", None)
        if (
            isinstance(tgt, TypedMirrorNode)
            and tag_of(tgt) == "Typed"
            and filter_controller(tgt) == "You"
        ):
            return True
        for v in vars(node).values():
            if isinstance(v, TypedMirrorNode):
                queue.append(v)
            elif isinstance(v, list):
                queue.extend(x for x in v if isinstance(x, TypedMirrorNode))
    return False


def _pump_mod_ints(node: object) -> list[int]:
    """Every literal int reachable through a pump node's power/toughness
    fields (Fixed(value=N) wrappers peel; Variable/Ref scale nodes yield
    nothing — a +X/+X pump is beneficial, only literal negatives gate)."""
    out: list[int] = []
    for fname in ("power", "toughness"):
        v = getattr(node, fname, None)
        if isinstance(v, int):
            out.append(v)
        elif isinstance(v, TypedMirrorNode):
            inner = getattr(v, "value", None)
            if isinstance(inner, int):
                out.append(inner)
    return out


def _parenttarget_return_refers_to_source(unit: AbilityUnit, c: ConceptNode) -> bool:
    """Whether a ``ChangeZone{Battlefield, target: ParentTarget}`` inside this
    SelfRef-watching trigger unit back-references the trigger's OWN SOURCE —
    i.e. the unit targets nothing else for ``ParentTarget`` to denote.

    phase v0.35.2 emits Ivory Gargoyle's "when this creature dies, return it
    to the battlefield ... at the beginning of the next end step" as a
    ``CreateDelayedTrigger`` whose inner return targets ``ParentTarget`` (the
    delayed-trigger back-reference); with no other target on the unit that IS
    the dying source — a resilience return (shed, CR 700.4), not clone value.
    A unit that DOES target something (Restoration Angel's "exile target
    creature, then return it" flicker — corpus census 2026-07-24: 57
    commander-legal SelfRef-trigger ParentTarget battlefield-returns, the
    majority this flicker-value shape) keeps the back-reference pointed at
    that target, so the shed never touches it."""
    if not (
        tag_of(c.node) == "ChangeZone"
        and getattr(c.node, "destination", None) == "Battlefield"
        and tag_of(getattr(c.node, "target", None)) == "ParentTarget"
    ):
        return False
    if getattr(unit.node, "valid_target", None) is not None:
        return False
    for n in iter_typed_nodes(unit.node):
        if n is c.node:
            continue
        tgt = getattr(n, "target", None)
        if (
            tgt is not None
            and tgt is not MISSING
            and (tag_of(tgt) in ("Typed", "Or", "And", "Any", "Player"))
        ):
            return False
    return True


def has_self_dies_value(tree: ConceptTree) -> bool:
    """A self-DIES VALUE trigger — a clone/token-copy re-fires it when it dies
    (Kokusho, Protean Hulk — CR 700.4).

    Mirrors the death fold's ``_self_death_payoff`` shape: a ``dies`` trigger
    watching the source itself (``valid_card`` = ``SelfRef``) with a
    :func:`is_clone_value_effect` effect (the self-return / shuffle-back resilience
    forms are shed inside the shared predicate; the v0.35.2 delayed
    ``ParentTarget`` self-return form needs the unit and is shed here via
    :func:`_parenttarget_return_refers_to_source`). Shared by the lane's arm 2
    and this stage's gap gate — one source, no drift.
    """
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event == "dies"
            and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
            and any(
                is_clone_value_effect(c)
                and not _parenttarget_return_refers_to_source(unit, c)
                for c in unit.effects
            )
        ):
            return True
    return False


# ── bucket-B idiom mirrors: self-recursion exclusion + folded engine grant ────
# The idiom-form mirror of the structural self-return / shuffle-back exclusion
# (:func:`_is_self_return_effect` / :func:`_is_shuffle_back_effect`), for the synth's
# raw-text value gate. The synth reads reminder-stripped oracle because phase folded
# the VALUE to ``other`` (no typed node to read) — but the bare ``_self_dies_value``
# regex's payoff alternation includes ``returns?``, so without this it re-admits the
# self-return dies-recursion cards (Ojer Taq's "return it to the battlefield", the
# God-Eternals' "put it into its owner's library", Kaya's granted "return it to its
# owner's hand") the structural predicate correctly sheds. Gap-gate-alignment: the
# synth's value gate must AGREE with the structural predicate, not paraphrase it
# (CR 700.4 — a token-copy gets no benefit from its own resilience return).


def _is_self_recursion_return(clause: str, name: str) -> bool:
    """Whether a matched self-ETB/dies clause's payoff is a SELF-recursion — the
    source returns / reshuffles ITSELF (resilience, SHED), not a fork-worthy clone
    VALUE (CR 700.4). Idiom mirror of :func:`_is_self_return_effect` /
    :func:`_is_shuffle_back_effect`: "return / put IT | this card | this creature |
    <own name> to the battlefield | to its owner's hand | into its owner's
    library/graveyard", or "shuffle IT into …". Name-aware for symmetry with the
    positive helpers. A return-OTHER payoff ("return a creature you control" —
    Chivalrous Chevalier) and destroy / draw / modal value keep firing.
    """
    alts = "|".join(
        [
            "it",
            "this card",
            "this creature",
            "this permanent",
            "~",
            *_self_name_alts(name),
        ]
    )
    pat = re.compile(
        rf"\b(?:return|put) (?:{alts})\b[^.]*?"
        r"(?:to the battlefield|to its owner's hand|to your hand"
        r"|into (?:its owner's|your) (?:library|graveyard))"
        rf"|\bshuffle (?:{alts})\b[^.]*?\binto\b",
        re.IGNORECASE,
    )
    return pat.search(clause) is not None


# A LEGENDARY creature that GRANTS ITSELF the activated abilities of exiled/owned
# cards, usable once each turn (Mairsil the Pretender — the canonical clone-combo
# target; a clone forks the whole once-each-turn ability suite). Phase folds this
# static grant to ``Unimplemented`` (a genuine parse gap), so the structural
# repeatable-engine read cannot see it — this bucket-B idiom bridges it until phase
# parses the grant (gap-gated to ``not has_repeatable_engine`` below).
_GRANT_ABILITIES_ONCE_RE = re.compile(
    r"\bactivate (?:each of )?(?:those|these|the exiled|all|its) "
    r"(?:activated )?abilit(?:y|ies)\b[^.]*?\bonce each turn\b",
    re.IGNORECASE,
)


# ── arm: wants_cloning bucket-B (ADR-0036 fold) ───────────────────────────────
# Two bucket-B tails phase emits no typed value node for. (A) A LEGENDARY creature
# whose once-each-turn activated-ability GRANT phase folds to ``Unimplemented``
# (Mairsil) — the legendary-engine arm's bucket-B tail. (B) The ``cmc >= 5``
# self-ETB / self-dies clone-want whose body phase folds to ``other``: a MODAL
# ("choose one —") or CONDITIONAL-COUNT ("for each {U}{U} spent, draw") or
# return-your-own ETB (Baleful Beholder, Bladecoil Serpent, Chivalrous Chevalier),
# and the analogous dies form. The self-ETB / self-dies VALUE idiom is read ONCE
# (the ``text_reads.py`` mirror helpers, the SHARED defs — never
# re-implemented), gap-gated to :func:`has_self_etb_value` / :func:`has_self_dies_value`
# (the SAME predicates the lane fires on) so it never double-counts a card phase
# already structuralizes, and the self-recursion payoff is shed via
# :func:`_is_self_recursion_return` (the structural exclusion's idiom mirror).


def _arm_wants_cloning(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``wants_cloning`` node for a description-only engine / ETB / dies
    value phase leaves value-less (CR 707 / 603.6).

    Tail A — a LEGENDARY creature whose once-each-turn activated-ability grant phase
    folds to ``Unimplemented`` (Mairsil), gap-gated to ``not has_repeatable_engine``.
    Tail B — a ``cmc >= 5`` card with :func:`has_self_etb_value` /
    :func:`has_self_dies_value` both False whose oracle carries a genuine self-ETB or
    self-dies VALUE idiom (``_self_etb_value`` / ``_self_dies_value`` over the
    reminder-stripped text), MINUS the self-recursion payoff
    (:func:`_is_self_recursion_return`). Scope "you", the lane's forced scope.
    """
    if (
        "Legendary" in tree.card_supertypes
        and tree.is_type("Creature")
        and not has_repeatable_engine(tree)
        and _GRANT_ABILITIES_ONCE_RE.search(tree.oracle or "")
    ):
        return _synthetic_concept(
            arm_id="wants_cloning",
            concept="synth_wants_cloning",
            scope="you",
            subject=(),
            desc="bucket-B clone-want (folded once-each-turn ability grant)",
        )
    if tree.cmc < 5:
        return None
    if has_self_etb_value(tree) or has_self_dies_value(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    etb = _self_etb_value(kept, tree.name)
    dies = _self_dies_value(kept, tree.name)
    if etb is not None and _is_self_recursion_return(etb, tree.name):
        etb = None
    if dies is not None and _is_self_recursion_return(dies, tree.name):
        dies = None
    if etb is None and dies is None:
        return None
    return _synthetic_concept(
        arm_id="wants_cloning",
        concept="synth_wants_cloning",
        scope="you",
        subject=(),
        desc="bucket-B clone-want (phase emits no typed self-ETB/dies value node)",
    )


# discover ACTION idiom (CR 701.57): "discover N" / "discover again". The
# re-trigger case ("whenever you discover, discover again for the same value"
# — Curator of Sun's Creation) leaves the inner discover ACTION as an
# ``Unimplemented`` EFFECT-role node, which ADR-0038 clause-grammar recovery
# (mtg_utils._card_ir.recovery.ALLOWLIST) now re-decorates in place — no synth
# needed there. This arm is the irreducible remainder (ADR-0037/0038): a
# "Discover N" granted via a static ability's ``GrantAbility`` text (Swash-
# buckler's Whip's equip-granted "{8}, {T}: Discover 10.") is NEVER its own
# concept node at all — phase folds the whole granted-ability clause into the
# ``GrantAbility`` static's raw grounding text, so there is no Unimplemented
# node for recovery to re-decorate. Gap-gated on NO typed ``discover`` effect
# (which now also excludes the recovery-promoted Curator case, so the two
# mechanisms never double-fire the same card).
_DISCOVER_ACTION_RE = re.compile(r"\bdiscover (?:again|\d+|x)\b", re.IGNORECASE)


def _arm_discover_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``discover`` maker node for the no-node discover grant
    (Swashbuckler's Whip: "Discover N" embedded in a granted-ability's raw
    text). Gap-gated on NO typed ``discover`` effect (a keyword bearer —
    Geological Appraiser — is already Tier-1; Curator of Sun's Creation is
    now recovery-promoted), so this only fills the genuine no-node gap."""
    if any(True for _ in tree.effect_concepts("discover")):
        return None
    if not _DISCOVER_ACTION_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="discover_makers",
        concept="discover",
        scope="you",
        subject=(),
        desc="bucket-B discover (no-node grant, e.g. Swashbuckler's Whip)",
    )


# Draw recipients naming EVERY player (CR 121.1) — the group_hug_draw
# direction. ``ScopedPlayer`` is deliberately ABSENT: an each-player Phase
# trigger's "that player draws" (Howling Mine) is the card_draw_engine
# each-arm, not the group-hug gift. Lives here (not in crosswalk_signals.py)
# so :func:`has_structural_group_hug_draw` and the ``_group_hug_draw`` lane
# share ONE source — imported back by crosswalk_signals.py.
_EACH_DRAW_RECIPIENTS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})


def has_structural_group_hug_draw(tree: ConceptTree) -> bool:
    """The group_hug_draw TYPED gate (CR 121.1): a ``Draw`` whose recipient is
    every player — an explicit ``_EACH_DRAW_RECIPIENTS`` tag (Temple Bell), or
    a ``player_scope: All`` wrapper on the ability that owns the Draw. Shared
    verbatim with the ``_group_hug_draw`` lane (the gap-gate ALIGNMENT the
    death_matters lesson demands) so the synthesis arm below never fires on a
    card the typed read already covers, and never drifts from what the lane
    itself considers structural."""
    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS or (
                effect_owner_player_scope(unit.node, c.node) == "All"
            ):
                return True
    return False


# each-player draw idiom (CR 121.1 "each player"; CR 102.1 — "each player"
# includes you). Grothama, All-Devouring's leaves-the-battlefield trigger
# ("each player draws cards equal to the damage dealt to ~ this turn by
# sources they control") lands in phase as an Unimplemented effect whose OWN
# raw text is just the damage-count clause — phase's own prefix parse
# consumes the "each player" SUBJECT before handing the remainder to the
# Unimplemented tag, so the subject survives ONLY in the whole-card oracle.
# ADR-0038 re-decoration reads the clause's own raw text, so it has no scope
# datum here to honestly write — this is the PARTIAL-residue class, and it
# stays a synthesis arm (ADR-0037) reading ``tree.oracle`` instead. The
# "who does" branch covers the symmetric-wheel idiom (Step Between Worlds /
# Turtles in Time — "Each player who does draws seven cards").
_GROUP_HUG_DRAW_RE = re.compile(
    r"\beach player (?:who does |may )?draws?\b", re.IGNORECASE
)


def _arm_group_hug_draw(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an each-player ``draw`` node for the group-hug gift phase
    leaves unstructured (Grothama's dropped each-player subject). Gap-gated
    on :func:`has_structural_group_hug_draw` — the SAME typed read the
    ``_group_hug_draw`` lane runs — so a card the typed gate already covers
    never doubles, and ``ScopedPlayer`` ("that player draws" — Howling Mine)
    stays routed to card_draw_engine, never widening into group-hug
    territory. Emits the REAL "draw" concept with ``scope="each"`` (ADR-0038
    retired the ``synth_*`` marker namespace), so the lane reads it via its
    own typed ``effect_concepts("draw")`` walk, keyed off the synthesized
    node identity — no lane special-case beyond that one extra branch."""
    if has_structural_group_hug_draw(tree):
        return None
    if not _GROUP_HUG_DRAW_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="group_hug_draw",
        concept="draw",
        scope="each",
        subject=(),
        desc="each-player draw phase left unstructured (dropped subject — Grothama)",
    )


# dice_makers TYPED gate (CR 706): a first-class ``roll_die`` concept-node
# (RollDie / RollToVisitAttractions, flat) OR a ``RollDie`` tag nested inside
# a unit's cost/granted-ability substructure the flat per-unit concept walk
# never surfaces as its own node (Clay Golem's Monstrosity cost roll, Captain
# Rex Nebula's Crash Land grant). Lives here (not in crosswalk_signals.py) so
# :func:`has_structural_dice_makers` and the ``_dice_makers`` lane share ONE
# source — imported back by crosswalk_signals.py.
def has_structural_dice_makers(tree: ConceptTree) -> bool:
    """Whether the card has a structural (typed, flat OR nested) die-roll
    node anywhere — the dice_makers TYPED gate. Shared verbatim with the
    ``_dice_makers`` lane and the reroll-only synthesis arm's gap gate below."""
    if tree.effect_concepts("roll_die"):
        return True
    return any(has_nested_roll_die(u.node) for u in tree.units)


# reroll-only die ACTION idiom (CR 706.8b: "To reroll one or more stored
# results … roll one of the kind of die noted for each of them" — rerolling
# IS rolling that die again). Monitor Monitor's "Once each turn, you may pay
# {1} to reroll one or more dice you rolled." lands in phase as an
# Unimplemented effect with NO RollDie node anywhere (nested OR flat) — a
# genuine no-residue gap (ADR-0038 amendment class 2), unlike Clay Golem /
# Captain Rex Nebula above (which DO carry a nested RollDie the structural
# gate already reaches). Mirrors the old-IR ``_DICE_REF`` reroll branch.
_DICE_REROLL_RE = re.compile(
    r"\breroll (?:any|a|that|one or more) (?:die|dice)\b", re.IGNORECASE
)


def _arm_dice_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``roll_die`` node for the reroll-only doer phase leaves
    wholly unstructured (Monitor Monitor, CR 706.8b). Gap-gated on
    :func:`has_structural_dice_makers` so a card the typed/nested read
    already covers never doubles. Emits the REAL "roll_die" concept, so the
    ``_dice_makers`` lane reads it via its ordinary typed
    ``effect_concepts("roll_die")`` walk — no lane special-case."""
    if has_structural_dice_makers(tree):
        return None
    if not _DICE_REROLL_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="dice_makers",
        concept="roll_die",
        scope="you",
        subject=(),
        desc="reroll-only die action phase leaves unstructured (Monitor Monitor)",
    )


# coin-flip WIN/LOSE payoff trigger idiom (CR 705.2): "Whenever you win/lose
# a coin flip, ..." (Chance Encounter, Karplusan Minotaur). phase flattens
# this trigger CONDITION to event='other', keeping only the consequence
# effect (place_counter / deal_damage) — the coin-flip reference survives
# ONLY in the whole-card oracle, never as a FlipCoin node (no player
# instructs a flip; the card just cares when ONE happens). NO-residue class
# (ADR-0038 amendment class 2). Mirrors the OLD-IR ``_COIN_FLIP_TRIG``
# marker regex byte-for-byte (verbatim extraction discipline) — both the
# doer AND this payoff feed the SAME legacy "coin_flip" category
# (``_sweep_detectors`` labels the key "coin-flip payoffs plus
# flip-fixing"), so this arm closes the gap the crosswalk's narrower
# doer-only read left.
_COIN_FLIP_PAYOFF_RE = re.compile(
    r"\b(?:win|lose)s? (?:a|the) (?:coin )?flip\b", re.IGNORECASE
)


def has_structural_coin_flip(tree: ConceptTree) -> bool:
    """The coin_flip TYPED gate: a native ``flip_coin`` concept-node
    (flat OR ADR-0038-recovered) anywhere, OR a ``FlipCoin`` tag nested
    inside a unit's granted-ability substructure the flat per-unit
    concept walk never surfaces (Frenetic Sliver). Shared verbatim with
    the ``_coin_flip`` lane and this arm's gap gate below."""
    if tree.effect_concepts("flip_coin"):
        return True
    return any(has_nested_flip_coin(u.node) for u in tree.units)


def _arm_coin_flip_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``flip_coin`` node for the "win/lose a coin flip"
    PAYOFF trigger phase flattens to ``event='other'`` (Chance Encounter's
    win/lose damage triggers), leaving the condition wholly unstructured.
    Gap-gated on :func:`has_structural_coin_flip` so a card the
    typed/nested/recovered read already covers never doubles — the gate
    is whole-tree, not per-trigger, so a card served ELSEWHERE (Karplusan
    Minotaur: its OWN "Flip a coin" DOER now structures off the
    ``crosswalk._keyword_effect_units`` keyword origin, task #87 — its
    win/lose damage triggers are STILL just as unstructured as Chance
    Encounter's, but the card no longer needs this arm at all) correctly
    stands this arm down without needing the payoff trigger itself to gain
    structure. Emits the REAL "flip_coin" concept, so the ``_coin_flip``
    lane reads it via its ordinary typed ``effect_concepts("flip_coin")``
    walk — no lane special-case. CR 705.2."""
    if has_structural_coin_flip(tree):
        return None
    if not _COIN_FLIP_PAYOFF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="coin_flip_payoff",
        concept="flip_coin",
        scope="you",
        subject=(),
        desc="win/lose-a-coin-flip trigger phase leaves unstructured",
    )


# Direct connive-DOER idiom requiring the word "target" ahead of "connives"
# in the same clause (Unstable Experiment: "up to one target creature you
# control connives") — the doer/payoff discriminator. A pure connive-STATE
# payoff clause ("Whenever a creature you control connives, ...") never
# contains "target" ahead of "connives" (CR 701.50a — connive is an
# instruction TO a permanent; a payoff merely watches for it elsewhere),
# so Glorious Purpose / Iron Monger, Sadistic Tycoon never match.
_CONNIVE_DOER_RE = re.compile(r"\btarget\b[^.]*\bconnives\b", re.IGNORECASE)


def has_structural_connive_makers(tree: ConceptTree) -> bool:
    """The connive_makers TYPED gate: a native ``connive`` concept-node
    (flat OR ADR-0038-recovered) anywhere, OR a ``Connive`` tag nested
    inside a unit's granted-trigger substructure the flat per-unit concept
    walk never surfaces (Security Bypass, Copycrook). Shared verbatim with
    the ``_connive_makers`` lane and this arm's gap gate below."""
    if tree.effect_concepts("connive"):
        return True
    return any(has_nested_connive(u.node) for u in tree.units)


def _arm_connive_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``connive`` node for Unstable Experiment's "Target
    player draws a card, then up to one target creature you control
    connives" — phase parses only the ``Draw`` half; the "then ... target
    creature ... connives" clause survives as no node at all (``sub_ability
    = None``), a no-residue class 2 gap (ADR-0038 amendment). Gap-gated on
    :func:`has_structural_connive_makers` so a typed/nested card never
    doubles. Emits the REAL "connive" concept, so the ``_connive_makers``
    lane reads it via its ordinary typed ``effect_concepts("connive")``
    walk — no lane special-case. CR 701.50a."""
    if has_structural_connive_makers(tree):
        return None
    if not _CONNIVE_DOER_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="connive_makers",
        concept="connive",
        scope="you",
        subject=(),
        desc="target-creature-connives clause phase drops entirely",
    )


def has_structural_fight_makers(tree: ConceptTree) -> bool:
    """The fight_makers TYPED gate (CR 701.12): a flat top-level ``Fight``
    effect OR a ``Fight`` tag :func:`has_nested_fight` reaches inside a
    GRANTED-ability construct (a trigger grant, an activated-ability
    grant, a ``CreateEmblem``, a token-copy exception clause). Shared
    verbatim with the ``_fight_makers`` lane and this arm's gap gate
    below."""
    for unit in tree.units:
        if unit.has_effect("fight") or has_nested_fight(unit.node):
            return True
    return False


def _arm_fight_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``fight`` node for a fight clause phase drops WHOLLY,
    no node of any kind (Tolsimir, Friend to Wolves's "that creature
    fights up to one target creature you don't control" -- the trigger's
    ``execute`` is a bare ``GainLife``, no ``sub_ability`` chain at all)
    -- a no-residue class 2 gap (ADR-0038 amendment; Tunnel of Love's
    "Otherwise, the chosen creatures fight each other" LOOKED like the
    same shape but turned out to carry a real, buried ``Fight`` node --
    :func:`has_structural_fight_makers`'s nested fallback already covers
    it). Relocates the legacy ``_FIGHT_RAW`` face-level fallback
    (originally written for the Aftermath-DFC single-face drop, Prepare
    // Fight) to gap-gated projection time, emitting the REAL "fight"
    concept (ADR-0038 retires the synth_* marker namespace) so the
    lane's ordinary ``effect_concepts("fight")`` read covers it with no
    special-case. Gap-gated on :func:`has_structural_fight_makers` so a
    typed/nested card never doubles. A genuine SPLIT-card second half
    (the "Fight" face itself) still needs task #74's face union --
    ``tree.oracle`` is single-face, so it never reaches this card at
    all. CR 701.12."""
    if has_structural_fight_makers(tree):
        return None
    if not _FIGHT_RAW.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="fight_makers",
        concept="fight",
        scope="you",
        subject=(),
        desc="fight clause phase drops wholly (no node of any kind)",
    )


# "take an extra/additional turn" idiom (CR 500.7) — the no-residue-or-
# Unimplemented-only tail :func:`has_structural_extra_turns`'s typed reach
# (a flat ``ExtraTurn`` OR a nested one reachable via ``has_nested_
# extra_turn``) never finds because phase leaves no real ``ExtraTurn`` node
# anywhere for these three shapes. Deliberately NOT reminder-stripped —
# Perch Protection's whole grant lives inside the Gift keyword's
# parenthetical, which is functionally operative text for that keyword,
# not flavor reminder.
_EXTRA_TURN_GRANT_RX = re.compile(r"take an (?:extra|additional) turn", re.IGNORECASE)


def has_structural_extra_turns(tree: ConceptTree) -> bool:
    """The extra_turns TYPED gate: a flat top-level ``ExtraTurn`` effect OR
    :func:`has_nested_extra_turn` reaching one buried inside a GRANTED
    construct (a ``Vote`` branch, a ``FlipCoin``/``FlipCoins`` win_effect,
    a static ability's ``GrantAbility.definition``). Shared verbatim with
    the ``_extra_turns`` lane and this arm's gap gate below."""
    if tree.has_effect("extra_turn"):
        return True
    return any(has_nested_extra_turn(u.node) for u in tree.units)


def _arm_extra_turns(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``extra_turn`` node for an extra-turn grant phase
    drops WHOLLY or parks as an untyped ``Unimplemented`` residue — a
    no-residue-or-Unimplemented-only class 2 gap (ADR-0038 amendment).
    Three distinct phase-v0.23.0 shapes, all covered by ONE oracle-text
    idiom scan since none leaves a real ``ExtraTurn`` node anywhere:

    * Chance for Glory's whole 3-sentence body ("Creatures you control
      gain indestructible. Take an extra turn after this one. At the
      beginning of that turn's end step, you lose the game.") collapses
      into ONE ``S_static_abilities`` def whose ONLY modification is the
      indestructible ``AddKeyword`` — the extra-turn + lose-the-game
      sentences survive only in the def's own ``description``, no node
      of any kind (a static-collapse silent drop).
    * Perch Protection's Gift keyword ("Gift an extra turn (You may
      promise an opponent a gift as you cast this spell. If you do,
      they take an extra turn after this one.)") parks the whole gift
      body as ``Unimplemented(name="gift", ...)`` — the grant goes to
      the OPPONENT ("they"), still a build-around per this lane's
      "regardless of who takes it" contract (see ``_extra_turns``'s
      docstring in ``crosswalk_signals.py``).
    * Ugin's Nexus's self-sacrifice replacement ("If ~ would be put
      into a graveyard from the battlefield, instead exile it and take
      an extra turn after this one.") parks as ``Unimplemented(name=
      "replacement_structure", ...)``. The SAME card also carries a
      real, correctly-typed ANTI-extra-turn ``Replacement`` (a separate
      "if a player would begin an extra turn, skip it" static, condition
      ``OnlyExtraTurn``) that must never be mistaken for a grant — its
      wording is "begin an extra turn" / "skip that turn", which this
      idiom never matches, so the scan can't double-fire on it.
    * Piece It Together's intensity payoff ("If ~'s intensity is 4,
      instead take an extra turn after this one.") parks as
      ``Unimplemented(name="instead", ...)`` inside the Draw ability's
      sub_ability chain (not commander-legal — an Un-set/Arena-only
      printing — but the same gap shape, so this arm covers it too).

    Full commander-legal corpus census (31,622 cards, phase v0.23.0,
    2026-07-12) found exactly these 3 commander-legal hits (Chance for
    Glory, Perch Protection, Ugin's Nexus) — a narrow, corpus-bound
    idiom scan, not a third detector. Gap-gated on
    :func:`has_structural_extra_turns` so a typed/nested card never
    doubles. Scope "you" (the live doer). CR 500.7."""
    if has_structural_extra_turns(tree):
        return None
    if not _EXTRA_TURN_GRANT_RX.search(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="extra_turns",
        concept="extra_turn",
        scope="you",
        subject=(),
        desc="extra-turn grant phase drops wholly or parks unreadably",
    )


# ── theft_makers structural read (ADR-0036/0037 Stage 5 fold) ──────────────────
# CR DD9 heist / 613.1b: the steal-and-cast/mill/play DOER. The [P5] direction
# trap (the lane's own reason for staying mirror-only): phase parses the SAME
# steal family (``Heist`` / ``ExileFromTopUntil`` / a directed ``SearchLibrary``
# / a Hand-zone ``CastFromZone`` / a triple-zone ``ChangeZoneAll``) whether the
# card steals from an OPPONENT or digs its OWN library (impulse draw — Light Up
# the Stage). Each read below is gated to an explicit non-controller player
# reference, never a bare/ambiguous tag a self-effect could also carry.

# Typed-filter ``controller`` STRING values meaning "not the ability's
# controller" (an explicit opponent/targeted-player direction — CR 613.1b).
# Shared by every theft sub-read below (one source, per GAP-GATE-ALIGNMENT).
_THEFT_OPP_CONTROLLERS = frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TargetPlayer",
        "DefendingPlayer",
        "SourceChosenPlayer",
    }
)


def _theft_typed_opponent(node: object) -> bool:
    """Whether a ``Typed`` player/zone-owner filter names an opponent (a
    ``controller`` string in :data:`_THEFT_OPP_CONTROLLERS`) — never a bare
    ``You``/``None`` (the self-effect default)."""
    return tag_of(node) == "Typed" and filter_controller(node) in _THEFT_OPP_CONTROLLERS


# ExileFromTopUntil.player discriminator TAGS meaning "not the controller"
# WITHOUT going through a Typed filter (combat-damage-to-a-player —
# TriggeringPlayer; a villainous-choice per-opponent branch — ScopedPlayer;
# ...). Deliberately EXCLUDES ParentTarget/ParentTargetController/Player/
# Target/Any/AllPlayers — those resolve through an arbitrary chosen OBJECT or
# a bare unscoped player and have zero genuine theft_makers member needing
# them (the ``_directed_search_sibling`` precedent: ParentTargetController
# routinely resolves to YOU, the ability's controller).
_THEFT_DIG_OPP_TAGS = frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
        "DefendingPlayer",
        "SourceChosenPlayer",
    }
)


def _theft_heist_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``Heist`` effect (CR DD9 digital supplement) targeting an opponent's
    library — Grenzo, Crooked Jailer; Polterheist; Thieving Aven."""
    for c in unit.effects:
        if tag_of(c.node) == "Heist" and _theft_typed_opponent(
            getattr(c.node, "target", None)
        ):
            return c
    return None


def _theft_dig_effect(unit: AbilityUnit) -> ConceptNode | None:
    """An ``ExileFromTopUntil`` (CR 701.20a-adjacent dig) whose DIGGER is an
    opponent — direct (:data:`_THEFT_DIG_OPP_TAGS` / a ``Typed`` opponent
    filter — Chaos Wand, Nicol Bolas, Umbris) or via the wrapper's
    ``player_scope`` (:func:`effect_owner_player_scope`) broadening a
    per-card ``Controller`` digger to "each opponent" / "each player"
    (Dream Harvest, Tasha's Hideous Laughter, Krang & Shredder, Etali). A
    bare ``Controller`` digger with NO opponent wrapper is the [P5] trap —
    impulse draw (Light Up the Stage) — and never fires here.
    """
    for c in unit.effects:
        if tag_of(c.node) != "ExileFromTopUntil":
            continue
        player = getattr(c.node, "player", None)
        if tag_of(player) in _THEFT_DIG_OPP_TAGS or _theft_typed_opponent(player):
            return c
        if effect_owner_player_scope(unit.node, c.node) in ("Opponent", "All"):
            return c
    return None


def _theft_tutor_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``SearchLibrary`` (``tutor`` concept) directed at an opponent's
    library (Bribery, Ancient Vendetta, Dichotomancy) — a ``Typed``
    ``target_player`` naming an opponent. A bare ``Player`` tag is
    deliberately excluded (the Partner-with reminder text — "target player
    may put X into their hand from their library" — names the CONTROLLER,
    not an opponent; a card-specific-name search has no genuine theft_makers
    member needing the bare tag).
    """
    for c in unit.effects:
        if c.concept == "tutor" and _theft_typed_opponent(
            getattr(c.node, "target_player", None)
        ):
            return c
    return None


def _theft_inanyzone_zones(filt: object) -> tuple[str, ...]:
    """The zones named by a filter's ``InAnyZone`` property (a triple-zone
    "graveyard, hand, and library" hate-piece search) — the ``InZone``
    single-zone sibling of :func:`filter_inzone_zones`, which has no
    ``InAnyZone`` case."""
    out: list[str] = []
    if tag_of(filt) == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "InAnyZone":
                out.extend(getattr(prop, "zones", ()) or ())
    return tuple(out)


def _theft_mass_zone_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``ChangeZoneAll`` exiling an opponent's graveyard+hand+library
    (Shimian Specter, Cranial Extraction, Stain the Mind) — the "same name"
    hate-piece family the mirror's triple-zone branch covered by text.
    """
    for c in unit.effects:
        if c.concept != "change_zone" or tag_of(c.node) != "ChangeZoneAll":
            continue
        if getattr(c.node, "destination", None) != "Exile":
            continue
        target = getattr(c.node, "target", None)
        zones = set(_theft_inanyzone_zones(target))
        if {"Graveyard", "Hand", "Library"} <= zones and _theft_typed_opponent(target):
            return c
    return None


def _theft_hand_effect(unit: AbilityUnit) -> ConceptNode | None:
    """A ``CastFromZone`` naming the HAND zone, in a unit that separately
    targets an opponent (Sen Triplets: "you may play lands and cast spells
    from that player's hand this turn" — CR 613.1b, a per-turn hand steal).
    A same-zone SELF grant (the Expertise cycle's "cast an additional spell
    from your hand", ``controller: You``) is the direction trap and is
    excluded on the ``CastFromZone`` node itself, not by the sibling check.
    """
    hand_cz: ConceptNode | None = None
    for c in unit.effects:
        if c.concept != "cast_from_zone":
            continue
        target = getattr(c.node, "target", None)
        if "Hand" not in filter_inzone_zones(target):
            continue
        if filter_controller(target) == "You":
            continue
        hand_cz = c
        break
    if hand_cz is None:
        return None
    opp_targeted = any(
        tag_of(c.node) == "TargetOnly"
        and _theft_typed_opponent(getattr(c.node, "target", None))
        for c in unit.effects
    )
    return hand_cz if opp_targeted else None


def has_structural_theft_makers(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the theft_makers Tier-1
    read sees — the synth gap-gate (GAP-GATE-ALIGNMENT: the SAME five
    sub-reads the lane fires on, so the lane and the gate never disagree).
    """
    for unit in tree.units:
        if (
            _theft_heist_effect(unit) is not None
            or _theft_dig_effect(unit) is not None
            or _theft_tutor_effect(unit) is not None
            or _theft_mass_zone_effect(unit) is not None
            or _theft_hand_effect(unit) is not None
        ):
            return True
    return False


# Genuine bucket-B residue (SYNTH-EXCLUSION-PARITY-checked on the corpus): a
# compound sentence phase drops entirely ("discard a card, then heist target
# opponent's library" — Axavar, Impetuous Lootmonger; a "Heist!"-flavored
# fixed-count exile — Mr. Monopoly), a "conjure" with no zone/player field at
# all (Lae'zel, Illithid Thrall), a triple-zone search phase leaves
# ``Unimplemented`` (Kotose, Lobotomy, Pick the Brain, Reap Intellect), and a
# per-branch/modal "for each opponent, exile ... you may cast" whose
# player_scope phase doesn't propagate into the branch (Seek Bolas's Counsel,
# Ensnared by the Mara's ``ChooseOneOf`` branch). The exile-actor alternation
# is deliberately "each/target/an OPPONENT" only — NOT "each player"/"a
# player" — so a symmetric self-cast rider (Guff Rewrites History's "each
# player may cast the card THEY exiled"; Possibility Storm's "that player may
# cast" replacement, whoever cast the ORIGINAL spell) stays correctly shed:
# both are corpus-verified NOT to match.
_THEFT_SYNTH_RX = re.compile(
    r"conjure a duplicate of[^.]*from an opponent's library"
    r"|\bheist\b"
    r"|search (?:that player|target opponent|an opponent|each opponent"
    r"|target player)'?s? graveyard, hand,? and library"
    r"|(?:each opponent|target opponent|an opponent)[^.]*exiles? cards from"
    r" the top of (?:their|its) library",
    re.IGNORECASE,
)


def _matches_theft_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B theft idiom."""
    return bool(_THEFT_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_theft_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``theft_makers`` node for the bucket-B steal/heist tail
    (ADR-0036/0037 Stage 5) — see :data:`_THEFT_SYNTH_RX`."""
    if has_structural_theft_makers(tree):
        return None
    if not _matches_theft_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="theft_makers",
        concept="synth_theft_makers",
        scope="opponents",
        subject=(),
        desc="bucket-B theft (phase drops the steal/heist clause)",
    )


# ── arm: b13_raw_anchor, subject-carrying (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# The batch-13 keyword-LESS conferred/quoted grant residue
# (:data:`_B13_RAW_ANCHOR_LANES` relocated verbatim): soulbond / undying-
# persist / changeling / cascade references phase folds into a carrier, so
# no retained-node text survives — a WHOLE-ORACLE scan is the deliberate,
# already-adjudicated choice (a node-scoped read drops soulbond -12/
# changeling -12/cascade -1 over the corpus, per the live comment this
# relocates verbatim). One subject-carrying node per card (the type_matters
# precedent) — the lane emits one Signal per matched key.
_B13_RAW_ANCHOR_SYNTH_LANES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_SOULBOND_REF, "has_soulbond"),
    (_UNDYING_PERSIST_GRANT, "has_undying_persist"),
    (_CHANGELING_REF, "has_changeling"),
    (_CASCADE_GRANT, "cascade_matters"),
)


def _arm_b13_raw_anchor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a subject-carrying node for the b13 conferred/quoted
    residue (:data:`_B13_RAW_ANCHOR_SYNTH_LANES`, the deleted
    ``_B13_RAW_ANCHOR_LANES`` whole-oracle scan relocated verbatim)."""
    kept = _REMINDER.sub(" ", tree.oracle or "")
    keys = tuple(key for pat, key in _B13_RAW_ANCHOR_SYNTH_LANES if pat.search(kept))
    if not keys:
        return None
    return _synthetic_concept(
        arm_id="b13_raw_anchor",
        concept="synth_b13_raw_anchor",
        scope="you",
        subject=keys,
        desc="bucket-B conferred/quoted grant residue (soulbond/undying/"
        "changeling/cascade)",
    )


# ── arm: b13_node_anchor, subject-carrying (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# ADR-0035 Stage 3b (a) re-categorizers: madness / affinity / mutate
# references phase RETAINS on a node it preserves losslessly — an
# Unimplemented effect's own description (Falkenrath Gorger's "… has
# madness"), a typed trigger's own description (Anje's "if it has
# madness", Pollywog's "if it has mutate"), or a typed grant static's own
# description (the affinity conferrals). Scanned over the RETAINED node
# texts (:data:`_B13_NODE_ANCHOR_SYNTH_LANES`, the deleted
# ``_B13_NODE_ANCHOR_LANES`` / ``_retained_node_texts`` pair relocated
# verbatim), NOT the reconstructed whole oracle — proven byte-identical to
# the whole-oracle grep over the commander corpus (madness 2, affinity 8,
# mutate 1 — 0 lost / 0 gained).
_MADNESS_GRANT_SYNTH_RE = re.compile(r"\bhas madness\b", re.IGNORECASE)
_AFFINITY_GRANT_SYNTH_RE = re.compile(
    r"\bhave affinity for|\bhas affinity for", re.IGNORECASE
)
_MUTATE_COND_SYNTH_RE = re.compile(r"\bif it has mutate\b", re.IGNORECASE)
_B13_NODE_ANCHOR_SYNTH_LANES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_MADNESS_GRANT_SYNTH_RE, "madness_matters"),
    (_AFFINITY_GRANT_SYNTH_RE, "affinity_type"),
    (_MUTATE_COND_SYNTH_RE, "has_mutate"),
)


def _retained_node_texts_synth(tree: ConceptTree) -> list[str]:
    """The reminder-stripped verbatim clauses phase RETAINS on each node —
    per-ability ``description`` plus each concept-node's grounding ``raw``
    (the deleted crosswalk ``_retained_node_texts`` helper relocated
    verbatim; reimplemented here rather than imported to avoid a
    crosswalk_signals↔tree_synthesis cycle)."""
    out: list[str] = []
    for unit in tree.units:
        d = getattr(unit.node, "description", None)
        if isinstance(d, str) and d:
            out.append(_REMINDER.sub(" ", d))
        for c in unit.iter_concepts():
            if c.raw:
                out.append(_REMINDER.sub(" ", c.raw))
    return out


def _arm_b13_node_anchor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a subject-carrying node for the three Stage-3b (a)
    re-categorizers (:data:`_B13_NODE_ANCHOR_SYNTH_LANES`, scanned over
    :func:`_retained_node_texts_synth`)."""
    texts = _retained_node_texts_synth(tree)
    keys = tuple(
        key
        for pat, key in _B13_NODE_ANCHOR_SYNTH_LANES
        if any(pat.search(t) for t in texts)
    )
    if not keys:
        return None
    return _synthetic_concept(
        arm_id="b13_node_anchor",
        concept="synth_b13_node_anchor",
        scope="you",
        subject=keys,
        desc="bucket-B Stage-3b madness/affinity/mutate re-categorizer",
    )


# ── ADR-0039 task #82 grammar sprint — sacrifice_outlets dropped-cost /
# grammar-straggler bridges (bridge_ledger.py's ``sac_alt_cost_pitch`` /
# ``sac_keyword_cost`` / ``sac_etb_self_sac_unimplemented`` rows). Three
# genuinely-dropped Sacrifice-COST idioms — a CR 118.9 alternative-cost
# pitch ("you may sacrifice ... rather than pay this spell's mana cost"),
# a CR 702.34/702.37 keyword's OWN alternative cost ("Flashback—Sacrifice
# three creatures"), and Devour's un-keyworded written-out sibling (CR
# 614.12/701.21a — "As this creature enters, sacrifice any number of
# creatures ...") — where phase's typed tree carries NO Sacrifice node
# anywhere for the clause. Gated on the SAME "no typed Sacrifice node
# reachable anywhere on this tree" absence proof the ledgered bridges
# shared (:func:`_tree_has_sacrifice_node`) — a card that already carries a
# REAL Sacrifice node elsewhere (an edict, a different cost) is already
# served structurally, and these arms correctly decline (Flare of Malice's
# edict Sacrifice node; Worthy Cause's existing ``_CAST_ADD_SAC_RX`` fire
# stays a harmless redundant re-fire, signal dedupe absorbs it). One shared
# marker concept (``synth_sac_outlet_dropped_cost``) — the lane
# (``crosswalk_signals._sacrifice_outlets``) reads it structurally with no
# per-idiom special-casing, all three idioms resolving to the SAME "you"
# sac-cost outlet (CR 602.1a — a cost is always paid by the activator).
def _tree_has_sacrifice_node(tree: ConceptTree) -> bool:
    """Whether TREE carries a typed ``Sacrifice`` node anywhere — the shared
    gap for the three arms below (mirrors
    ``bridge_ledger._no_typed_sacrifice_node`` exactly)."""
    return any(
        tag_of(n) == "Sacrifice"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _arm_sac_alt_cost_pitch(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_sac_outlet_dropped_cost`` node for a CR 118.9
    alternative-cost pitch ("You may sacrifice three artifacts rather than
    pay this spell's mana cost." — Salvage Titan; CR 118.9). Reuses
    legacy's OWN ``_PITCH_SAC`` regex verbatim (relocated to
    ``text_idioms``, not re-derived) — its own ``_SAC_COUNT`` / ``_SAC_TYPE``
    vocabulary already excludes a land-only pitch ("sacrifice two
    Mountains" — Fireblast, ``land_sacrifice_makers`` territory) and a
    count word it doesn't carry (Hand of Emrakul's "sacrifice four Eldrazi
    Spawn")."""
    if _tree_has_sacrifice_node(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    if not _PITCH_SAC.search(kept):
        return None
    return _synthetic_concept(
        arm_id="sac_alt_cost_pitch",
        concept="synth_sac_outlet_dropped_cost",
        scope="you",
        subject=(),
        desc="bucket-B CR 118.9 alternative-cost sacrifice pitch (spell cost dropped)",
    )


def _arm_sac_keyword_cost(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_sac_outlet_dropped_cost`` node for a keyworded
    alternative-cost sacrifice ("Flashback—Sacrifice three creatures." —
    Dread Return; "Morph—Sacrifice another creature." — Gift of Doom; CR
    702.34a / 702.37a). Reuses legacy's ``_KEYWORD_COST_SAC`` verbatim
    (relocated to ``text_idioms``) — the same land-type exclusion applies
    (Walk the Aeons' "Buyback—Sacrifice three Islands" stays unmatched)."""
    if _tree_has_sacrifice_node(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    if not _KEYWORD_COST_SAC.search(kept):
        return None
    return _synthetic_concept(
        arm_id="sac_keyword_cost",
        concept="synth_sac_outlet_dropped_cost",
        scope="you",
        subject=(),
        desc="bucket-B CR 702.34/702.37 keyword alternative-cost sacrifice (dropped)",
    )


# Devour's un-keyworded sibling: a written-out (non-keyword) self-sac ETB
# parked as a bare ``Unimplemented`` residue ("As this creature enters,
# sacrifice any number of creatures. This creature's power becomes the
# total power of those creatures..." — Dracoplasm; CR 614.12 — a
# replacement effect that modifies how the permanent enters the
# battlefield, the same rule Devour itself is templated under; CR 701.21a
# for the sacrifice action). Anchored on the residue NODE (not raw whole-
# card oracle) so the read stays precise the same way the ledgered bridge
# did.
_SAC_ETB_UNIMPL_RX = re.compile(
    r"as [^.]*enters[^.]*,\s*sacrifice any number of creatures", re.IGNORECASE
)


def _arm_sac_etb_self_sac(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_sac_outlet_dropped_cost`` node for the written-
    out (un-keyworded) Devour-sibling ETB self-sac idiom (Dracoplasm)."""
    if _tree_has_sacrifice_node(tree):
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and _SAC_ETB_UNIMPL_RX.search(
                getattr(n, "description", "") or ""
            ):
                return _synthetic_concept(
                    arm_id="sac_etb_self_sac_unimplemented",
                    concept="synth_sac_outlet_dropped_cost",
                    scope="you",
                    subject=(),
                    desc=(
                        "bucket-B written-out ETB self-sac Devour sibling "
                        "(CR 614.12/701.21a)"
                    ),
                )
    return None


# ── ADR-0039 task #82 grammar sprint — direct_damage dropped-grant /
# upstream-parse-failure bridges (bridge_ledger.py's ``devil_token_quoted_
# grant_dominant_verb_create`` / ``keranos_effect_structure_parse_failure``
# rows). Two genuinely-buried DealDamage idioms — a quoted granted-ability
# death trigger nested INSIDE a single token-creation ``Unimplemented``
# residue (Maestros Diabolist / Pugnacious Pugilist) and a compound reveal-
# and-punish ability that fails phase's OWN effect-sentence parser wholesale
# (Keranos, God of Storms) — where phase's typed tree carries NO DealDamage
# node reaching a player anywhere for the clause. Gated on the SAME "no
# player-reaching damage node anywhere on this tree" absence proof the
# ledgered bridges shared (:func:`_tree_has_reaching_damage_node`, the
# ``_tree_has_sacrifice_node`` precedent) — a card that already carries a
# REAL reaching DealDamage node elsewhere is already served structurally.
# One shared marker concept (``synth_direct_damage_dropped_grant``) — the
# lane (``crosswalk_signals._direct_damage``) reads it structurally with no
# per-idiom special-casing, both idioms resolving to the SAME "you" burn
# read (CR 120.1).
def _tree_has_reaching_damage_node(tree: ConceptTree) -> bool:
    """Whether TREE carries a ``DealDamage``/``DamageAll``/``DamageEach
    Player`` node that structurally reaches a PLAYER anywhere — the shared
    gap for the two arms below (mirrors ``bridge_ledger._no_player_
    reaching_damage_node`` exactly, CR 120.1)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in (
                "DealDamage",
                "DamageAll",
                "DamageEachPlayer",
            ) and effect_reaches_player(n, unit.node):
                return True
    return False


# Maestros Diabolist / Pugnacious Pugilist's "create a tapped and attacking
# 1/1 red Devil creature token with 'When this token dies, it deals 1
# damage to any target.'" — the WHOLE clause is one
# ``Unimplemented(name='create', ...)`` residue whose dominant verb token is
# "create," so the recovery stage's ``make_token`` ALLOWLIST entry
# re-decorates the node's CONCEPT but never descends into the quoted
# granted-ability text for the nested damage clause. Reuses the ledgered
# bridge's own verbatim idiom regex, anchored on the residue NODE (not raw
# whole-card oracle) so the read stays precise the same way the bridge did.
_DEVIL_TOKEN_QUOTED_GRANT_SYNTH_RX = re.compile(
    r"create a tapped and attacking 1/1 red devil creature token with "
    r'"when [^"]*dies, it deals \d+ damage to any target',
    re.IGNORECASE,
)


def _arm_devil_token_quoted_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_direct_damage_dropped_grant`` node for the
    Devil-token quoted death-trigger damage clause nested inside a single
    ``create`` ``Unimplemented`` residue (Maestros Diabolist, Pugnacious
    Pugilist; CR 701.7/120.1). Dance with Devils's simpler, un-triggered
    "Create two ... tokens. They have '...'" phrasing decomposes into a REAL
    typed ``GrantTrigger`` -> ``DealDamage(target=Any())`` chain phase
    structures fine — this arm mirrors that same shape for the quoted-
    inside-a-single-create-clause idiom phase's token grammar can't yet
    split."""
    if _tree_has_reaching_damage_node(tree):
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Unimplemented" or getattr(n, "name", None) != "create":
                continue
            desc = getattr(n, "description", "") or ""
            if _DEVIL_TOKEN_QUOTED_GRANT_SYNTH_RX.search(desc):
                return _synthetic_concept(
                    arm_id="devil_token_quoted_grant_dominant_verb_create",
                    concept="synth_direct_damage_dropped_grant",
                    scope="you",
                    subject=(),
                    desc=(
                        "bucket-B Devil-token quoted death-trigger damage "
                        "clause nested inside a create residue (CR "
                        "701.7/120.1)"
                    ),
                )
    return None


# Keranos, God of Storms's three-sentence reveal-and-punish ability
# ("Reveal the first card you draw on each of your turns. Whenever you
# reveal a land card this way, draw a card. Whenever you reveal a nonland
# card this way, Keranos deals 3 damage to any target.") fails phase's OWN
# effect-sentence parser wholesale — a genuine upstream parse failure (CR
# 120.1): an ``Unimplemented(name='effect_structure', description=
# "Effect sentence candidate but line failed effect parser: ...")``
# diagnostic residue. Grolnok / Mairsil share the SAME diagnostic name for
# their OWN unrelated multi-clause idioms and stay open bridge_ledger rows
# (``bridge_ledger._grolnok_gap`` / ``_mairsil_rex_gap``) — this arm reads
# ONLY the bounded damage-clause tail of Keranos's own idiom (the SAME
# scalpel the ledgered bridge used), not the whole compound trigger; a
# general multi-trigger-sentence parser for ``effect_structure`` residues
# stays the named upstream retirement path for the Grolnok/Mairsil siblings.
_KERANOS_EFFECT_STRUCTURE_SYNTH_RX = re.compile(
    r"whenever you reveal a nonland card this way, [^.]*deals \d+ "
    r"damage to any target",
    re.IGNORECASE,
)


def _arm_keranos_effect_structure(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``synth_direct_damage_dropped_grant`` node for Keranos,
    God of Storms's bounded damage-clause tail inside its whole-ability
    ``effect_structure`` parse-failure residue (CR 120.1)."""
    if _tree_has_reaching_damage_node(tree):
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) != "Unimplemented"
                or getattr(n, "name", None) != "effect_structure"
            ):
                continue
            desc = getattr(n, "description", "") or ""
            if _KERANOS_EFFECT_STRUCTURE_SYNTH_RX.search(desc):
                return _synthetic_concept(
                    arm_id="keranos_effect_structure_parse_failure",
                    concept="synth_direct_damage_dropped_grant",
                    scope="you",
                    subject=(),
                    desc=(
                        "bucket-B bounded damage-clause tail inside an "
                        "effect_structure parse-failure residue (CR 120.1)"
                    ),
                )
    return None


# ── batch T6-niche-b: kill_engine bucket-B tail (Evil Twin) ─────────────────
# CR 305.6/701.8 (destroy) + 707.2 (a granted quoted ability): a REPEATABLE
# creature ``Destroy`` engine — the live structural walk (an Activated unit,
# or a recurring trigger outside the one-shot event set, with a Creature-
# targeted ``Destroy``) already binds 84 commander-legal cards. The sole
# residual: Evil Twin, whose destroy ability lives inside a QUOTED granted
# ability folded into a ``clone`` Effect (no destroy ability of its own to
# walk) — the ONE card phase can't structure at v0.9.0. Relocates the
# deleted ``_REPEATABLE_KILL_RE`` mirror verbatim, gap-gated against the
# structural census (and the same whole-card ``is_type("Creature")`` gate
# the live lane applies to BOTH arms). Measured byte-identical (84
# structural + 1 bucket-B, 0 drops, 0 adds).
#
# Trigger events that fire AT MOST ONCE per object — NOT a repeatable kill
# frame. ONE pinned source the live lane (crosswalk_signals) imports back —
# see ``_KILL_ONESHOT_EVENTS`` there (the PAY_LIFE_REF/MASS_DEATH_REF
# single-source precedent, just inverted direction since this module sits
# below crosswalk_signals in the import graph).
_KILL_ONESHOT_EVENTS: frozenset[str] = frozenset(
    {
        "enters",
        "dies",
        "leaves",
        "changes_zone",
        "transformed",
        "transforms",
        "turnedfaceup",
        "turnfaceup",
        "becomemonstrous",
        "becomesmonstrous",
    }
)


def _has_repeatable_kill_unit(tree: ConceptTree) -> bool:
    """The repeatable-Destroy-creature unit scan, WITHOUT the whole-card
    ``is_type("Creature")`` gate :func:`has_structural_kill_engine` applies.

    ADR-0039 task #80 step 6: the deck-forge membership floor now unions this
    predicate across EVERY face of a DFC/split card and applies the
    creature-type gate separately at the whole-card level (the floor's own
    ``"creature" in type_line`` check over the bulk record's WHOLE-CARD type
    line) — closing the per-face isolation gap on Sheoldred // The True
    Scriptures, whose repeatable destroy lives on the Enchantment — Saga
    face (a Saga chapter trigger, ``trigger_event="counter_added"`` — not in
    ``_KILL_ONESHOT_EVENTS``) while the Creature face (Sheoldred) carries no
    destroy ability of its own. See
    ``crosswalk_signals.apply_membership_floor``."""
    for unit in tree.units:
        repeatable = (unit.origin == "ability" and unit.kind == "Activated") or (
            unit.origin == "trigger"
            and (unit.trigger_event or "") not in _KILL_ONESHOT_EVENTS
        )
        if not repeatable:
            continue
        for c in unit.effect_concepts("destroy"):
            if tag_of(c.node) != "Destroy":
                continue
            if "Creature" in filter_core_types(getattr(c.node, "target", None)):
                return True
    return False


def has_structural_kill_engine(tree: ConceptTree) -> bool:
    """Whether a REPEATABLE unit (an Activated ability, or a recurring
    trigger outside the one-shot event set) carries a Creature-targeted
    ``Destroy`` effect."""
    if not tree.is_type("Creature"):
        return False
    return _has_repeatable_kill_unit(tree)


_KILL_ENGINE_SYNTH_RX = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*destroy target creature"
    r"|(?:whenever|at the beginning of)[^.]*destroy target creature",
    re.IGNORECASE,
)


def _matches_kill_engine_idiom(oracle: str) -> bool:
    return bool(_KILL_ENGINE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_kill_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``kill_engine`` node for the Evil Twin quoted-granted-
    ability tail (the deleted ``_REPEATABLE_KILL_RE`` mirror relocated,
    gap-gated against :func:`has_structural_kill_engine`)."""
    if not tree.is_type("Creature"):
        return None
    if has_structural_kill_engine(tree):
        return None
    if not _matches_kill_engine_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="kill_engine",
        concept="synth_kill_engine",
        scope="you",
        subject=(),
        desc="bucket-B quoted-granted repeatable-destroy residue (CR 707.2)",
    )


# ── batch T6-niche-b: big_hand_makers / big_hand_matters bucket-B tail ──────
# CR 402.2: the live structural walk already binds the ``NoMaximumHandSize``/
# ``MaximumHandSize`` static mode + the ``no_max_handsize`` effect concept
# (makers half), and the hand-size ``QuantityComparison`` condition (GE/GT,
# threshold >= 4) + the dynamic-P/T hand-size mod (matters half). The
# residual on EACH half rides the byte-identical live mirror (no competing
# Tier-1 predicate for either): makers' "maximum hand size" REDUCER phrasing
# the structural static-mode walk doesn't independently reach on every face,
# and matters' "N or more cards in hand" / "equal to … cards in your hand"
# phrasing outside a QuantityComparison/dynamic-P/T node shape (Body of
# Knowledge fires BOTH halves — the live pair's parity). Relocates the two
# deleted mirrors verbatim, gap-gated against each half's own structural
# predicate. Measured byte-identical over the commander-legal corpus
# (makers 57/57, matters 90/90, 0 drops, 0 adds each — the matters recall
# includes 18 Maro-shaped ``SetDynamicPower``/``SetDynamicToughness`` CDA
# cards NOW read structurally: the lane-local ``_DYNAMIC_PT_MODS`` name in
# crosswalk_signals was shadowed by a LATER batch-14 redefinition — see
# ``_WB_PT_SET_MODS``'s identical shadowing note — so these cards rode the
# mirror exclusively pre-fold; this fold's ``_BIG_HAND_DYNAMIC_PT_MODS``
# pins the correct Set* spellings, recovering the structural read).
def has_structural_big_hand_makers(tree: ConceptTree) -> bool:
    """Whether a static's mode is ``NoMaximumHandSize``/``MaximumHandSize``,
    or a ``no_max_handsize`` effect concept exists."""
    for unit in tree.units:
        if unit.origin == "static":
            mt = static_mode_tag(unit.node)
            if mt in ("NoMaximumHandSize", "MaximumHandSize"):
                return True
        if unit.effect_concepts("no_max_handsize"):
            return True
    return False


# Dynamic P/T modification tags (both phase spellings — Maro's
# ``SetDynamicPower`` pair and Titania's Song's ``SetPowerDynamic`` pair):
# the big_hand_matters CDA site. ONE pinned source the live lane
# (crosswalk_signals) reuses byte-identically for its own inline walk.
_BIG_HAND_DYNAMIC_PT_MODS: frozenset[str] = frozenset(
    {
        "SetDynamicPower",
        "SetDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
    }
)


def has_structural_big_hand_matters(tree: ConceptTree) -> bool:
    """Whether a YOUR-hand-size ``QuantityComparison`` condition (GE/GT,
    threshold >= 4) or a hand-size-scoped dynamic-P/T modification exists."""
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(site):
                if tag_of(q) != "QuantityComparison":
                    continue
                lhs = getattr(q, "lhs", None)
                if "you" not in hand_size_scopes(lhs):
                    continue
                if getattr(q, "comparator", None) not in ("GE", "GT"):
                    continue
                rhs = getattr(q, "rhs", None)
                val = getattr(rhs, "value", None) if tag_of(rhs) == "Fixed" else None
                if isinstance(val, int) and val >= 4:
                    return True
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) in _BIG_HAND_DYNAMIC_PT_MODS and "you" in hand_size_scopes(
                mod
            ):
                return True
    return False


_BIG_HAND_MAKERS_SYNTH_RX = re.compile(
    r"no maximum hand size|maximum hand size", re.IGNORECASE
)
_BIG_HAND_MATTERS_SYNTH_RX = re.compile(
    r"(?:five|six|seven|eight) or more cards in (?:your )?hand"
    r"|(?:equal to|number of) [^.]*cards in your hand",
    re.IGNORECASE,
)


def _matches_big_hand_makers_idiom(oracle: str) -> bool:
    return bool(_BIG_HAND_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _matches_big_hand_matters_idiom(oracle: str) -> bool:
    return bool(_BIG_HAND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_big_hand_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``big_hand_makers`` node for the "maximum hand size"
    residual (the deleted ``_BIG_HAND_MAKERS_MIRROR`` relocated, gap-gated
    against :func:`has_structural_big_hand_makers`)."""
    if has_structural_big_hand_makers(tree):
        return None
    if not _matches_big_hand_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="big_hand_makers",
        concept="synth_big_hand_makers",
        scope="you",
        subject=(),
        desc="bucket-B no-max/maximum-hand-size residue (CR 402.2)",
    )


def _arm_big_hand_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``big_hand_matters`` node for the full-grip-reference
    residual (the deleted ``_BIG_HAND_MATTERS_MIRROR`` relocated, gap-gated
    against :func:`has_structural_big_hand_matters`)."""
    if has_structural_big_hand_matters(tree):
        return None
    if not _matches_big_hand_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="big_hand_matters",
        concept="synth_big_hand_matters",
        scope="you",
        subject=(),
        desc="bucket-B full-grip-reference residue (CR 402.2)",
    )


# ── batch T7-niche-c: power_tap_engine (structural + bucket-B tail) ────────
# CR 602.1 (activated abilities): the repeatable {T} power-scaling engine
# (Karametra's Acolyte-style). STRUCTURAL — an Activated unit whose cost
# carries a Tap/Untap leaf and whose effect's ``amount``/``count`` operand is
# a self ``Ref(qty=Power)`` (or an ``Aggregate``-of-``Power``); OR the SAME
# shape nested inside a ``GrantAbility.definition`` (the conferred/DFC-back
# form — Predatory Urge, Dragon Throne of Tarkir). The residual: phase
# captures "equal to the SACRIFICED/TAPPED/EXILED creature's power" (an
# OTHER creature, not self) as an opaque ``Variable(name=...)`` with no typed
# Power ref at all (Kalitas, Eye of Yawgmoth, Unerring Sling, Sword of the
# Ages, Stitcher Geralf, Soul Separator), and the "gets +X/+X where X is
# [that/this] creature's power" pump form (Rabble-Rouser, Nantuko Mentor,
# Auriok Bladewarden, Dragon Throne) rides a modification's ``value`` field
# the structural amount/count walk doesn't reach — genuine gaps. Relocates
# the deleted ``_POWER_SCALING_RAW`` / ``_POWER_TAP_CONFERRED_RX`` mirrors
# verbatim, gap-gated. Measured over the commander-legal corpus: 57
# structural + 16 bucket-B, 1 genuine ADD over the old mirror (Surestrike
# Trident: "{T}, Unattach ~: ... deals damage equal to its power" — the old
# ``_POWER_TAP_CONFERRED_RX``'s ``\{t\}:`` anchor required the colon
# immediately after "{T}", missing the "{T}, Unattach ...:" cost-chain
# phrasing the structural ``GrantAbility.definition`` walk isn't anchored
# on), 0 drops.
_POWER_TAP_TAP_COST_TAGS: frozenset[str] = frozenset({"Tap", "Untap"})


def _power_tap_has_tap_cost(cost: object) -> bool:
    return any(
        tag_of(leaf) in _POWER_TAP_TAP_COST_TAGS for leaf in iter_cost_leaves(cost)
    )


def _power_tap_has_power_amount(node: object) -> bool:
    for n in iter_typed_nodes(node):
        for fname in ("amount", "count"):
            q = getattr(n, fname, None)
            if tag_of(q) != "Ref":
                continue
            qty = getattr(q, "qty", None)
            qt = tag_of(qty)
            if qt == "Power" or (
                qt == "Aggregate" and getattr(qty, "property", None) == "Power"
            ):
                return True
    return False


def has_structural_power_tap_engine(tree: ConceptTree) -> bool:
    """Whether an Activated tap-cost unit's own effect (or a granted
    ability's ``GrantAbility.definition``) scales an ``amount``/``count``
    operand off a self ``Power`` (or ``Aggregate``-of-``Power``) ref."""
    for unit in tree.units:
        if (
            unit.kind == "Activated"
            and _power_tap_has_tap_cost(getattr(unit.node, "cost", None))
            and _power_tap_has_power_amount(unit.node)
        ):
            return True
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            if d is None:
                continue
            if _power_tap_has_tap_cost(
                getattr(d, "cost", None)
            ) and _power_tap_has_power_amount(getattr(d, "effect", None)):
                return True
    return False


_POWER_TAP_CONFERRED_RX = re.compile(
    r"\{t\}:[^.]*(?:equal to|where x is|x is)[^.]*\bpower\b", re.IGNORECASE
)


def _arm_power_tap_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``power_tap_engine`` node for the other-creature-power /
    modification-``value`` residual (the deleted ``_POWER_SCALING_RAW`` /
    ``_POWER_TAP_CONFERRED_RX`` mirrors relocated, gap-gated against
    :func:`has_structural_power_tap_engine`)."""
    if has_structural_power_tap_engine(tree):
        return None
    for unit in tree.units:
        if unit.kind != "Activated":
            continue
        if not _power_tap_has_tap_cost(getattr(unit.node, "cost", None)):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        if any(_POWER_SCALING_RAW.search(r) for r in raws if r):
            return _synthetic_concept(
                arm_id="power_tap_engine",
                concept="synth_power_tap_engine",
                scope="you",
                subject=(),
                desc="bucket-B other-power/value-field scaling residue (CR 602.1)",
            )
    if _POWER_TAP_CONFERRED_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return _synthetic_concept(
            arm_id="power_tap_engine",
            concept="synth_power_tap_engine",
            scope="you",
            subject=(),
            desc="bucket-B conferred power-tap residue (CR 602.1)",
        )
    return None


# ── batch T7-niche-c: meld_pair (structural + bucket-B tail) ───────────────
# CR 701.42a/701.42b (meld pairs) + 712.1: STRUCTURAL — a ``Meld`` effect
# node anywhere in the tree (phase structures the trigger-front's own Meld
# node — Gisela, Graf Rat — 2/14 commander-legal partners). The residual:
# the partner-side info that lives ONLY in reminder text ("(Melds with
# X.)"), which reminder-STRIPPING would lose — phase never structures the
# back piece's own Meld node (Brisela names no partner) — a long-logged
# genuine gap. Relocates the deleted ``_MELD_FULLTEXT_RE`` mirror verbatim
# over the UN-stripped oracle, gap-gated. Measured over the commander-legal
# corpus: 2 structural + 12 bucket-B, 0 drops, 0 adds (byte-identical
# union).
def has_structural_meld_pair(tree: ConceptTree) -> bool:
    """Whether a ``Meld`` effect node exists anywhere in the tree (the
    trigger-front's own meld — Gisela, Graf Rat)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Meld":
                return True
    return False


def _arm_meld_pair(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``meld_pair`` node for the reminder-text-only partner
    residual (the deleted ``_MELD_FULLTEXT_RE`` mirror relocated over the
    UN-stripped oracle, gap-gated against :func:`has_structural_meld_pair`)."""
    if not tree.name:
        return None
    if has_structural_meld_pair(tree):
        return None
    if _MELD_FULLTEXT_RE.search(tree.oracle or "") is None:
        return None
    return _synthetic_concept(
        arm_id="meld_pair",
        concept="synth_meld_pair",
        scope="you",
        subject=(),
        desc="bucket-B meld reminder-text partner residue (CR 701.42a)",
    )
