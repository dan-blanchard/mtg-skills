"""Mana, ramp, tutor, and land-fetch bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    effect_filter,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    has_filter_property,
    iter_cost_leaves,
    iter_nested_trigger_defs,
    iter_typed_nodes,
    reveal_until_player,
    settap_state,
    static_mode_tag,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    TypedMirrorNode,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge.signal_base import clauses

# ── untap_engine structural reads + bucket-B synth (ADR-0036/0037 fold) ───────
# CR 701.26/701.26b: a DELIBERATE untap engine (Seedborn Muse, Candelabra,
# Turnabout). The Tier-1 ``_untap_engine`` lane reads a SetTapState{Untap}
# effect wherever phase routes it — a direct effect (Arbor Elf, Nature's
# Chosen), the "you may tap or untap target X" Twiddle carrier (a sibling
# ``TargetOnly`` declaring the target, threaded via ``ParentTarget`` into a
# ``ChooseOneOf``/``mode_abilities`` branch — Twiddle, Turnabout, Elder Druid,
# Captain of the Mists, Component Collector, Dee Kay), a GRANTED trigger (a
# static's ``GrantTrigger`` wrapping the identical TargetOnly/ChooseOneOf
# shape — Bear Umbra, Ghostly Touch), an activation-cost carrier (Halo
# Fountain, Crackleburr — ``EffectCost``), or the untap-during-each-other-
# player's-untap-step static mode (Seedborn Muse, Drumbellower, Unwinding
# Clock, Ohabi Caleria, and the SELF-scoped form — Bender's Waterskin,
# Endbringer). Vetoed (CR 701.26b): an OPPONENT-directed target (Provoke /
# Spinal Embrace / Soldevi Golem / Ray of Command — anti-synergy, not an
# engine), a ``gain_control`` sibling in the same unit (Threaten / Goatnapper
# / Insurrection / Reins of Power — a control-steal combat trick, not a
# deliberate untap engine), a provoke force-block sibling (untaps the
# BLOCKER, not your board), and the single-permanent ATTACH rider (Crab Umbra
# "untap enchanted creature" — read structurally via the target filter's
# ``EnchantedBy``/``EquippedBy`` property, not text).

# Sibling force-block tags (the provoke veto — an "untap … and block" combat
# trick untaps the BLOCKER, not your board).
_FORCE_BLOCK_TAGS: frozenset[str] = frozenset(
    {"MustBlock", "ForceBlock", "MustBeBlocked", "Provoke"}
)


def _iter_untap_targets(
    root: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target, SetTapState_node)`` for every Untap ``SetTapState``
    reachable from one ability/trigger/static unit's raw node, the target
    THREADED through the effect/sub_ability/execute/branches/mode_abilities/
    GrantTrigger chain (mirrors :func:`~mtg_utils._card_ir.crosswalk.
    iter_threaded_target_statics`): a ``ParentTarget``-tagged branch target
    resolves to the nearest preceding ``TargetOnly`` node's own target (the
    dedicated target declaration for a "tap or untap" choice — NOT any other
    effect's target, which would wrongly thread an unrelated pump spell's
    "target creature" into an incidental "Untap it" rider — Bull's Strength,
    Acrobatic Leap — CR 701.26b excludes those as incidental, not engines).
    """
    tracked: object | None = None
    seen: set[int] = set()
    queue: list[object] = [root]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        tgt = getattr(node, "target", None)
        if (
            tag_of(node) == "TargetOnly"
            and isinstance(tgt, TypedMirrorNode)
            and tag_of(tgt) in ("Typed", "Or", "And")
        ):
            tracked = tgt
        if tag_of(node) == "SetTapState" and settap_state(node) == "Untap":
            resolved = tracked if tag_of(tgt) == "ParentTarget" else tgt
            yield resolved, node
        for fname in ("execute", "effect", "sub_ability"):
            child = getattr(node, fname, None)
            if isinstance(child, TypedMirrorNode):
                queue.append(child)
        branches = getattr(node, "branches", None)
        if isinstance(branches, list):
            queue.extend(branches)
        modes = getattr(node, "mode_abilities", None)
        if isinstance(modes, list):
            queue.extend(modes)
        mods = getattr(node, "modifications", None)
        for mod in mods if isinstance(mods, list) else ():
            if isinstance(mod, TypedMirrorNode) and tag_of(mod) == "GrantTrigger":
                trig = getattr(mod, "trigger", None)
                if isinstance(trig, TypedMirrorNode):
                    queue.append(trig)


def _untap_target_ok(target: object) -> bool:
    """Whether a resolved untap TARGET is a genuine engine subject (CR 701.26b):
    not opponent-controlled, and either a real card core-type/subtype filter
    (Candelabra "lands", Arbor Elf "Forest", Snap "up to two lands") or the
    Crab Umbra attach rider is absent (``EnchantedBy``/``EquippedBy``)."""
    if target is None or filter_controller(target) == "Opponent":
        return False
    if tag_of(target) not in ("Typed", "Or", "And"):
        return False
    if has_filter_property(target, "EnchantedBy") or has_filter_property(
        target, "EquippedBy"
    ):
        return False
    return bool(filter_core_types(target) or filter_subtypes(target))


def _engine_untap_surfaces(
    tree: ConceptTree,
) -> Iterator[tuple[AbilityUnit, object | None, bool]]:
    """``(unit, scope_filter, mass)`` per qualifying untap-engine surface —
    the ONE walk :func:`has_structural_untap_engine` (bool),
    :func:`structural_untap_subject` (subject fold), and
    :func:`structural_untap_scope` (symmetry fold) all consume, so the
    vetoes can't drift. ``scope_filter`` is the node whose type filter scopes
    WHAT gets untapped: the resolved target for a direct/cost Untap (mass
    ``All`` scopes still carry their group filter there — Myr Galvanizer),
    the static ``affected`` for the untap-during-each-step mode. ``mass`` is
    True for board-wide surfaces (``scope == 'All'`` / the static mode) —
    the only surfaces that can be SYMMETRIC.
    """
    for unit in tree.units:
        if any(tag_of(c.node) in _FORCE_BLOCK_TAGS for c in unit.effects):
            continue
        if any(c.concept == "gain_control" for c in unit.effects):
            continue
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "UntapsDuringEachOtherPlayersUntapStep"
            and filter_controller(getattr(unit.node, "affected", None)) != "Opponent"
        ):
            yield unit, getattr(unit.node, "affected", None), True
        for target, node in _iter_untap_targets(unit.node):
            mass = tag_of(getattr(node, "scope", None)) == "All"
            if mass or _untap_target_ok(target):
                yield unit, target, mass
        for cc in unit.costs:
            for leaf in iter_cost_leaves(cc.node):
                if tag_of(leaf) != "EffectCost":
                    continue
                eff = getattr(leaf, "effect", None)
                if not isinstance(eff, TypedMirrorNode):
                    continue
                if tag_of(eff) != "SetTapState" or settap_state(eff) != "Untap":
                    continue
                mass = tag_of(getattr(eff, "scope", None)) == "All"
                tgt = getattr(eff, "target", None)
                if mass or _untap_target_ok(tgt):
                    yield unit, tgt, mass


def has_structural_untap_engine(tree: ConceptTree) -> bool:
    """A DELIBERATE untap engine phase structures (CR 701.26/701.26b).

    Shared by the ``_untap_engine`` lane (its entire Tier-1 structural read)
    AND this stage's synth gap gate — one source, no drift. Per unit: skip a
    provoke sibling (:data:`_FORCE_BLOCK_TAGS`) or a ``gain_control`` sibling
    (a Threaten-variant steal, not an engine — CR 701.26b), then check the
    untap-during-each-step static mode (self or board-wide), every Untap
    ``SetTapState`` reachable via :func:`_iter_untap_targets` (mass ``scope
    == 'All'`` OR a real-type/subtype single target), and every activation-
    cost ``EffectCost`` wrapping an Untap ``SetTapState`` (Halo Fountain,
    Crackleburr). Surface enumeration lives in
    :func:`_engine_untap_surfaces`; :func:`structural_untap_subject` and
    :func:`structural_untap_scope` fold the same surfaces into the ident
    subject / scope.
    """
    return next(_engine_untap_surfaces(tree), None) is not None


def structural_untap_scope(tree: ConceptTree) -> str:
    """ "you" for a your-side engine, "each" when EVERY surface is a
    symmetric board-wide untap (a mass Untap over a TYPED GROUP with no
    controller filter — Intruder Alarm's "Whenever a creature enters, untap
    all creatures" untaps every player's board; the iteration-1b panel
    killed it unanimously as a your-side engine credit under Urza). A
    TARGETED untap stays "you" even without a controller filter — the
    controller chooses the target (CR 601.2c); a You-filtered mass/static
    surface (Seedborn Muse) anchors "you"; and a SELF-scoped untap-during
    static (Endbringer's ``SelfRef`` affected) is your own permanent, not
    symmetry — only a real group filter without You reads "each"."""
    saw = False
    for _unit, scope_filter, mass in _engine_untap_surfaces(tree):
        saw = True
        group = tag_of(scope_filter) in ("Typed", "Or", "And")
        if not mass or not group or filter_controller(scope_filter) == "You":
            return "you"
    return "each" if saw else "you"


def _surface_untap_subject(unit: AbilityUnit, scope_filter: object | None) -> str:
    """One surface's subtype scope: the scope filter's single subtype (Myr
    Galvanizer's "each other Myr", Arbor Elf's Forest), else — for a
    trigger-origin surface whose untap target is unscoped — the single
    subtype of the trigger's ``valid_card`` event filter (Merrow Reejerey:
    the untap fires once per Merfolk CAST, so Merfolk is the engine's rate
    scope, CR 603.2c). Unscoped or multi-subtype → "" (universal)."""
    subs = set(filter_subtypes(scope_filter)) if scope_filter is not None else set()
    if len(subs) == 1:
        return next(iter(subs))
    if not subs and unit.origin == "trigger":
        vc = getattr(unit.node, "valid_card", None)
        tsubs = set(filter_subtypes(vc)) if vc is not None else set()
        if len(tsubs) == 1:
            return next(iter(tsubs))
    return ""


def structural_untap_subject(tree: ConceptTree) -> str:
    """The card-level untap-engine subject: every qualifying surface must
    agree on ONE subtype scope, else "" (any universal surface makes the
    ENGINE universal — the gate must never hide a card that can untap the
    commander). Feeds the ``untap_engine|you|<Subject>`` ident the pair
    ledger's scoped_subject_gate compares against commander subtypes."""
    subject = None
    for unit, scope_filter, _mass in _engine_untap_surfaces(tree):
        s = _surface_untap_subject(unit, scope_filter)
        if not s:
            return ""
        if subject is None:
            subject = s
        elif s != subject:
            return ""
    return subject or ""


# ── arm: untap_engine bucket-B (ADR-0036/0037 fold) ───────────────────────────
# The genuine phase-parse gap tail: a "tap or untap" choice phase folds to a
# BARE ``Tap`` (Curse of Inertia drops the "or untap" alternative entirely), a
# "simultaneously untap X and tap Y" swap phase folds half to
# ``Unimplemented`` (Breaking Wave), a granted EMBLEM ability phase leaves
# unstructured (Zariel's "untap target creature you control" emblem text), a
# conditional "if you pay, untap all creatures" branch phase drops (Lightning
# Runner), and a counter-gated conditional static phase leaves as a bare
# ``Continuous`` mode with no typed payload (Quest for Renewal). Read PER-
# CLAUSE (reminder-stripped) so a match is confined to ONE clause. The
# engine-words idiom is the exact deleted mirror
# (``_UNTAP_ENGINE_MIRROR_RAW`` — "untap target/another target/all/each/two/
# up to"); the "creatures you control are lands" Ashaya idiom is NOT ported
# (ADR-0036 adjudication: Ashaya's ability is a pure CR 205.1a type-change —
# it untaps nothing itself; the ONE corpus carrier is lands_matter synergy,
# not a genuine untap_engine member — shed, not recovered).
#
# SYNTH-EXCLUSION-PARITY: mirrors the SAME three vetoes
# :func:`has_structural_untap_engine` applies — opponent-directed (Soldevi
# Golem "an opponent controls", Provoke's spelled-out "target creature an
# opponent controls"), a `gain_control` companion clause (Threaten variants),
# and the attach rider (Crab Umbra) — so the synth never re-admits a card the
# structural read correctly shed.
_UNTAP_ENGINE_IDIOM_RE = re.compile(
    r"\buntap (?:target|another target|all|each|two|up to)\b", re.IGNORECASE
)
_UNTAP_ENGINE_OPP_TEXT_VETO = re.compile(
    r"you don't control|opponent controls", re.IGNORECASE
)
_UNTAP_ENGINE_STEAL_TEXT_VETO = re.compile(r"gain control of", re.IGNORECASE)
_UNTAP_ENGINE_ATTACH_TEXT_VETO = re.compile(
    r"untap (?:enchanted|equipped)\b", re.IGNORECASE
)


def _matches_untap_engine_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B untap-engine
    idiom, per-clause, minus the opponent/steal/attach over-fire vetoes."""
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _UNTAP_ENGINE_OPP_TEXT_VETO.search(cl)
            or _UNTAP_ENGINE_STEAL_TEXT_VETO.search(cl)
            or _UNTAP_ENGINE_ATTACH_TEXT_VETO.search(cl)
        ):
            continue
        if _UNTAP_ENGINE_IDIOM_RE.search(cl):
            return True
    return False


def _arm_untap_engine(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``untap_engine`` node for a description-only deliberate
    untap engine (CR 701.26/701.26b) phase leaves untap-less."""
    if has_structural_untap_engine(tree):
        return None
    if not _matches_untap_engine_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="untap_engine",
        concept="synth_untap_engine",
        scope="you",
        subject=(),
        desc="bucket-B untap engine (phase emits no typed Untap node)",
    )


# ── arm: tutor bucket-B (ADR-0036/0037 fold) ──────────────────────────────────
# tutor (CR 701.23/701.23a): a deliberate YOUR-library search (Demonic Tutor,
# Vampiric Tutor). phase keeps a ``SearchLibrary`` node for EVERY search --
# opponent (Bribery's ``target_player``), a compensation search resolving
# through a removed permanent's controller (Path to Exile, Assassin's Trophy --
# ``ParentTargetController`` / ``ParentObjectTargetController``), symmetric
# ("each player searches" -- an ability-level ``player_scope`` of All/Opponent),
# and a Cycling/Landcycling/Typecycling reminder-granted search (the keyword's
# reminder text expands to its own ``Activated`` unit tagged
# ``ability_tag=Cycling`` -- a keyword reminder is not a deliberate tutor).
# :func:`has_structural_tutor` reads all four exclusions off typed fields --
# the entire Tier-1 structural read, shared verbatim by the ``tutor`` lane and
# this stage's two gap gates (no drift).
_TUTOR_DIRECTED_PLAYER_TAGS = frozenset(
    {
        "ParentTarget",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
_TUTOR_NON_SELF_ABILITY_SCOPE = frozenset(
    {
        "All",
        "AllExcept",
        "EachPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
_TUTOR_SIBLING_RECIPIENT_CONCEPTS = frozenset(
    {"gain_life", "lose_life", "draw", "discard"}
)
# A bespoke non-SearchLibrary effect tag phase uses for a still-genuine own-
# library search (Teacher's Pet's Augment-combine); mapped to concept "tutor"
# in the crosswalk (crosswalk.EFFECT_CONCEPTS) alongside SearchLibrary.
_TUTOR_EFFECT_TAGS = frozenset({"SearchLibrary", "ChooseAugmentAndCombineWithHost"})


def _tutor_ability_body(unit: AbilityUnit) -> TypedMirrorNode | None:
    """The execute-shaped ability body carrying ``ability_tag`` /
    ``player_scope`` -- a trigger/replacement unit wraps its real ability body
    one level down in ``.execute`` (``AbilityUnit.node`` is the OUTER trigger/
    replacement wrapper for those origins); an ``ability``-origin unit's own
    node already IS that body."""
    if unit.origin in ("trigger", "replacement"):
        ex = getattr(unit.node, "execute", MISSING)
        return ex if isinstance(ex, TypedMirrorNode) else None
    return unit.node


def _unit_is_self_tutor(unit: AbilityUnit) -> bool | None:
    """Whether THIS unit's tutor concept(s) search YOUR OWN library (CR
    701.23a), or ``None`` if the unit carries no tutor concept at all.

    Four vetoes, all typed: (1) a Cycling/Landcycling/Typecycling reminder-
    granted search (``ability_tag``); (2) a symmetric/opponent-scoped ability
    (``player_scope`` on the execute body -- Old-Growth Dryads' ``Opponent``,
    Weird Harvest's ``All``); (3) a sibling gain_life/lose_life/draw/discard
    effect in the SAME unit naming another player (Restorative Technique's
    "target player gains 2 life, then searches their library" -- the search
    itself carries no recipient, inheriting the preceding effect's); (4) the
    search's own ``target_player`` (absent/You/Controller = self; Player/
    Target/Opponent(s)/TriggeringPlayer/ScopedPlayer/ParentTarget(Controller)
    = directed). A unit MAY carry more than one SearchLibrary (Sadistic
    Sacrament's directed find-and-exile chains a second, recipient-less
    SearchLibrary for "the rest") -- if ANY search in the unit is directed,
    the WHOLE unit is (they share one targeted-player action chain)."""
    tutors = [
        c
        for c in unit.effects
        if c.concept == "tutor" and tag_of(c.node) in _TUTOR_EFFECT_TAGS
    ]
    if not tutors:
        return None
    body = _tutor_ability_body(unit)
    if tag_of(getattr(body, "ability_tag", None)) == "Cycling":
        return False
    ps_tag = tag_of(getattr(body, "player_scope", None)) if body else None
    if ps_tag in _TUTOR_NON_SELF_ABILITY_SCOPE:
        return False
    for c in unit.effects:
        if c.concept in _TUTOR_SIBLING_RECIPIENT_CONCEPTS and (
            explicit_recipient_scope(c.node) in ("opponents", "each", "any")
        ):
            return False
    saw_self = False
    for c in tutors:
        tp = getattr(c.node, "target_player", MISSING)
        if tp is MISSING or tp is None:
            saw_self = True
            continue
        t = tag_of(tp)
        if t in _TUTOR_DIRECTED_PLAYER_TAGS:
            return False
        if t == "Typed":
            if getattr(tp, "controller", None) in ("You", "Controller"):
                saw_self = True
            else:
                return False
            continue
        # unknown target_player shape -- never guess either way for THIS node
    return saw_self or None


def has_structural_tutor(tree: ConceptTree) -> bool:
    """A deliberate self search-your-library tutor (CR 701.23/701.23a) --
    shared by the ``tutor`` lane (its entire Tier-1 structural read) AND this
    stage's two gap gates. See :func:`_unit_is_self_tutor`."""
    return any(_unit_is_self_tutor(unit) for unit in tree.units)


# ── lf_ramp (2026-07-13 signal-key convention change): a NONLAND card whose
# clause searches for a LAND and puts it ONTO THE BATTLEFIELD is RAMP, never
# tutor (mirrors card_classify.is_ramp's fetch branch; CR 701.23/701.23a for
# the search action itself). A land fetch TO HAND (Sylvan Scrying) or an
# arbitrary/nonland search stays tutor; a clause that can do both (Archdruid's
# Charm's "creature or land ... onto the battlefield ... if it's a land card,
# otherwise ... your hand") fires BOTH keys. LAND cards (Evolving Wilds,
# Krosan Verge) are untouched -- the ramp lane's mana-base carve-out stands,
# and the callers gate on ``tree.is_type("Land")`` before consulting this
# split. :func:`structural_land_fetch_split` is the shared classifier both
# the ``tutor`` and ``ramp`` lanes read, so a clause can never lose tutor
# without the ramp side firing from the SAME facts.

# CR 205.3i's full land-type list (June 2026 CR). Deliberately NOT the
# ``_LAND_SUBTYPE_WORDS_SYNTH`` manland set below (which predates Town and
# Planet): widening THAT set would move the manland/land-animate arms'
# population; this one is fetch-classification-only.
_SEARCH_LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(
    {
        "cave",
        "desert",
        "forest",
        "gate",
        "island",
        "lair",
        "locus",
        "mine",
        "mountain",
        "plains",
        "planet",
        "power-plant",
        "sphere",
        "swamp",
        "tower",
        "town",
        "urza's",
    }
)


def _search_filter_land_facts(f: object) -> tuple[bool, bool] | None:
    """``(can_fetch_land, fetches_only_lands)`` for a ``SearchLibrary``
    filter, or ``None`` when phase left the filter unresolved (a bare ``Any``
    -- Planar Engineering's "four basic land cards"; an empty ``Typed`` --
    Wild Endeavor's dice-scaled count). Landish = a ``Land`` core type, a CR
    205.3i land-subtype word, or a ``HasSupertype Basic`` property (CR
    305.6); land-ONLY additionally requires no nonland core type / nonland
    subtype disjunct (Archdruid's Charm's Or(Creature, Land) can fetch a
    creature, so it is landish but never land-only)."""
    t = tag_of(f)
    if t in ("Or", "And"):
        subs = [
            _search_filter_land_facts(x) for x in (getattr(f, "filters", None) or ())
        ]
        subs = [s for s in subs if s is not None]
        if not subs:
            return None
        can = any(c for c, _ in subs)
        only = all(o for _, o in subs) if t == "Or" else any(o for _, o in subs)
        return can, only
    if t != "Typed":
        return None
    cores = set(filter_core_types(f))
    subtys = {s.lower() for s in filter_subtypes(f)}
    basic = any(
        tag_of(p) == "HasSupertype" and getattr(p, "value", None) == "Basic"
        for p in (getattr(f, "properties", None) or ())
    )
    if not cores and not subtys and not basic:
        return None
    landish = bool("Land" in cores or (subtys & _SEARCH_LAND_SUBTYPE_WORDS) or basic)
    only = (
        landish
        and not (cores - {"Land", "Card"})
        and not (subtys - _SEARCH_LAND_SUBTYPE_WORDS)
    )
    return landish, only


def _unit_search_destinations(unit: AbilityUnit) -> set[str]:
    """Every zone the UNIT's searched card(s) can reach: the search node's
    own ``split`` destinations (Cultivate's one-to-battlefield/rest-to-hand)
    plus every ``ChangeZone`` in the unit whose origin is ``Library`` (the
    plain "put that card into X" continuation) or absent with an ``Any`` /
    ``ParentTarget`` target (the conditional-continuation shape phase emits
    for "put it onto the battlefield tapped if it's a land card" -- an
    origin-less ChangeZone chained onto the search's own result)."""
    dests: set[str] = set()
    for n in iter_typed_nodes(unit.node):
        t = tag_of(n)
        if t == "SearchLibrary":
            split = getattr(n, "split", MISSING)
            if split is not MISSING and split is not None:
                for fname in ("primary_destination", "rest_destination"):
                    v = getattr(split, fname, None)
                    if isinstance(v, str):
                        dests.add(v)
        elif t == "ChangeZone":
            origin = getattr(n, "origin", MISSING)
            if origin is not MISSING and origin is not None:
                if origin != "Library":
                    continue
            elif tag_of(getattr(n, "target", None)) not in (
                "Any",
                "ParentTarget",
            ):
                continue
            d = getattr(n, "destination", None)
            if isinstance(d, str):
                dests.add(d)
    return dests


def _tree_search_continuations(tree: ConceptTree) -> set[str]:
    """Cross-unit battlefield continuations of a search clause. ``cont_bf``:
    a sibling ability unit whose PRIMARY effect is an origin-less
    ``ChangeZone(ParentTarget -> Battlefield)`` -- phase's split of Caravan
    Vigil's "Morbid -- You may put that card onto the battlefield instead"
    rider into its own condition-gated unit. ``exile_bf``: an exile-staging
    re-delivery unit (``ChooseFromZone(zone=Exile, filter=ExiledBySource)``
    chaining to a Battlefield ``ChangeZone`` -- Omenpath Journey's end-step
    "put a card at random exiled with ~ onto the battlefield")."""
    out: set[str] = set()
    for unit in tree.units:
        body = _tutor_ability_body(unit)
        if body is None:
            continue
        eff = getattr(body, "effect", MISSING)
        if eff is MISSING or eff is None:
            continue
        t = tag_of(eff)
        if (
            t == "ChangeZone"
            and (
                getattr(eff, "origin", MISSING) is MISSING
                or getattr(eff, "origin", None) is None
            )
            and tag_of(getattr(eff, "target", None)) == "ParentTarget"
            and getattr(eff, "destination", None) == "Battlefield"
        ):
            out.add("cont_bf")
        elif (
            t == "ChooseFromZone"
            and getattr(eff, "zone", None) == "Exile"
            and tag_of(getattr(eff, "filter", None)) == "ExiledBySource"
        ):
            for n in iter_typed_nodes(body):
                if (
                    tag_of(n) == "ChangeZone"
                    and getattr(n, "destination", None) == "Battlefield"
                ):
                    out.add("exile_bf")
                    break
    return out


def structural_land_fetch_split(tree: ConceptTree) -> tuple[bool, bool]:
    """``(land_fetch, other_search)`` over every CONFIRMED self search
    (:func:`_unit_is_self_tutor` ``True`` units only -- directed/symmetric
    searches never enter). ``land_fetch``: some clause fetches a land to the
    battlefield (the ramp side); ``other_search``: some clause remains a
    genuine tutor (to-hand / nonland-fetchable / unresolvable destination).
    The two flags are per CLAUSE, so Archdruid's Charm raises both while
    Rampant Growth raises only ``land_fetch`` and Demonic Tutor only
    ``other_search``.

    Per-unit mechanics: filter facts from :func:`_search_filter_land_facts`
    (an unresolved filter inherits a resolved sibling search's facts -- the
    "instead search for up to three" count-upgrade idiom -- else falls back
    to the unit-less sentence read :func:`_text_search_facts`); destinations
    from :func:`_unit_search_destinations` plus the cross-unit continuations
    (:func:`_tree_search_continuations`). A condition-gated land-only unit
    with NO battlefield destination of its own is skipped as a
    count-upgrade continuation when a land-only battlefield clause exists
    (Nissa's Pilgrimage's spell-mastery unit, which phase parses with its
    own Hand-dest chain)."""
    conts = _tree_search_continuations(tree)
    rows: list[tuple[bool, bool, bool, bool]] = []
    other = False
    for unit in tree.units:
        if _unit_is_self_tutor(unit) is not True:
            continue
        tutors = [
            c
            for c in unit.effects
            if c.concept == "tutor" and tag_of(c.node) in _TUTOR_EFFECT_TAGS
        ]
        if not tutors:
            continue
        if any(tag_of(c.node) != "SearchLibrary" for c in tutors):
            other = True  # Augment-combine: a creature search, never lands
        facts = [
            _search_filter_land_facts(getattr(c.node, "filter", None))
            for c in tutors
            if tag_of(c.node) == "SearchLibrary"
        ]
        if not facts:
            continue
        resolved = [f for f in facts if f is not None]
        if len(resolved) < len(facts):
            if resolved:
                inherit = (
                    any(c for c, _ in resolved),
                    all(o for _, o in resolved),
                )
            else:
                kept = _REMINDER.sub(" ", tree.oracle or "")
                t_landish, t_only, _t_other = _text_search_facts(kept)
                inherit = (t_landish, t_only)
            resolved = [f if f is not None else inherit for f in facts]
        landish = any(c for c, _ in resolved)
        land_only = all(o for _, o in resolved)
        dests = _unit_search_destinations(unit)
        bf = "Battlefield" in dests
        if not bf and "cont_bf" in conts:
            bf = True
        if not bf and dests and dests <= {"Exile"} and "exile_bf" in conts:
            bf = True
        body = _tutor_ability_body(unit)
        cond = getattr(body, "condition", MISSING) if body is not None else MISSING
        cond_gated = cond is not MISSING and cond is not None
        rows.append((landish, land_only, bf, cond_gated))
    land_fetch = False
    bf_land_only = any(lo and bf for _l, lo, bf, _c in rows)
    for landish, land_only, bf, cond_gated in rows:
        if cond_gated and land_only and not bf and bf_land_only:
            continue  # count-upgrade continuation of the battlefield clause
        if landish and bf:
            land_fetch = True
        if not (land_only and bf):
            other = True
    return land_fetch, other


# The sentence-level text mirror of ``card_classify.is_ramp``'s fetch branch
# (lf_ramp): a search sentence naming a land ("land card(s)" / "basic land" /
# a CR 205.3i land-type word) AND "onto the battlefield" is the ramp side; a
# search sentence that can also fetch a nonland type keeps the tutor side
# too. Only consulted where the tree is text-only or a filter is unresolved
# (the substrate-first doctrine's sanctioned text-gate territory).
_LF_SEARCH_SENTENCE_RE = re.compile(r"search your librar(?:y|ies) for", re.IGNORECASE)
_LF_TEXT_LAND_RE = re.compile(
    r"\bland cards?\b|\bbasic land\b|\b(?:cave|desert|forest|gate|island|lair"
    r"|locus|mine|mountain|plains|planet|power-plant|sphere|swamp|tower|town"
    r"|urza's)\b",
    re.IGNORECASE,
)
_LF_TEXT_NONLAND_RE = re.compile(
    r"search your librar(?:y|ies) for [^.]*?\b(?:creature|artifact"
    r"|enchantment|instant|sorcery|planeswalker|battle|aura|equipment"
    r"|permanent|card named)\b[^.]*?cards?",
    re.IGNORECASE,
)
_LF_ONTO_BATTLEFIELD_RE = re.compile(r"onto the battlefield", re.IGNORECASE)


def _text_search_facts(kept: str) -> tuple[bool, bool, bool]:
    """``(landish_bf, land_only_bf, other)`` over KEPT's search sentences:
    ``landish_bf`` -- some sentence fetches a land to the battlefield;
    ``land_only_bf`` -- some sentence does so and can ONLY fetch lands;
    ``other`` -- some search sentence stays a genuine tutor (no land word,
    no battlefield, or a nonland type alongside the land word)."""
    landish = land_only = other = False
    for s in re.split(r"(?<=[.!])\s+|\n", kept):
        if not _LF_SEARCH_SENTENCE_RE.search(s):
            continue
        land = bool(_LF_TEXT_LAND_RE.search(s))
        bf = bool(_LF_ONTO_BATTLEFIELD_RE.search(s))
        nonland = bool(_LF_TEXT_NONLAND_RE.search(s))
        if land and bf and not nonland:
            landish = True
            land_only = True
        elif land and bf:
            landish = True
            other = True
        else:
            other = True
    return landish, land_only, other


# The directed/symmetric text idiom phase's structure sometimes omits
# entirely (Head Games, Rootwater Thief, Oath of Lieges, Scheming Symmetry,
# Deceptive Divination, Sphinx Ambassador, Thada Adel, Sadistic Sacrament's
# second search -- no target_player, no player_scope, no sibling recipient:
# NOTHING typed marks the direction). A genuine self-tutor always says
# "search YOUR library" (CR 701.23a); a directed/symmetric one says "search
# THAT/TARGET player's/opponent's library" or "search THEIR/HIS OR HER
# library" -- the veto idiom below. Read whole-card (the historical mirror's
# own grain) WITH an escape hatch: a card that ALSO says "your library"
# ANYWHERE is never vetoed -- Demolition Field ("that land's controller may
# search their library... You may search YOUR library..."), Tempt with
# Discovery, and I Call on the Ancient Magics all pair a genuine self clause
# with an unrelated opponent/symmetric compensation clause on the SAME card;
# the confirmed self clause must stand regardless. Applies as a VETO to BOTH
# the structural read above and the rescue arm below, so it is its own synth
# node the lane checks, not folded into ``has_structural_tutor`` (which stays
# 100%-typed, no oracle text, so the gap-gate-sharing rule holds clean).
_TUTOR_DIRECTED_TEXT_RE = re.compile(
    r"search(?:es)?\s+(?:that|target)\s+(?:player|opponent)(?:'s|s')?\s+library"
    r"|search(?:es)?\s+(?:their|his or her)\s+library",
    re.IGNORECASE,
)
_TUTOR_OWN_LIBRARY_CONFIRM_RE = re.compile(r"your library", re.IGNORECASE)


def _matches_tutor_directed_idiom(oracle: str) -> bool:
    kept = _REMINDER.sub(" ", oracle or "")
    if _TUTOR_OWN_LIBRARY_CONFIRM_RE.search(kept):
        return False
    return bool(_TUTOR_DIRECTED_TEXT_RE.search(kept))


def _arm_tutor_directed(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a veto marker when the reminder-stripped oracle reveals a
    SearchLibrary directed at ANOTHER player or symmetric across players --
    the residual phase leaves with no typed direction marker at all."""
    if not any(
        c.concept == "tutor" and tag_of(c.node) in _TUTOR_EFFECT_TAGS
        for c in tree.iter_concepts()
    ):
        return None
    if not _matches_tutor_directed_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="tutor_directed",
        concept="synth_tutor_directed",
        scope="opponents",
        subject=(),
        desc="bucket-B tutor directed/symmetric veto (no typed direction marker)",
    )


# The own-library idiom -- byte-identical to the deleted TUTOR_MATTERS_REGEX
# (over the reminder-stripped whole-card oracle): a description-only self-
# tutor phase's SearchLibrary can't structurally reach at all -- an emblem-
# granted future search whose granted-ability text phase leaves an
# unstructured string (Kaito Shizuki, Nissa Who Shakes the World, Garruk
# Unleashed, Tezzeret Artifice Master, Garruk Caller of Beasts); a vote/dice-
# table/repeat-for per-outcome body phase parses only as ``Unimplemented``
# (Travel Through Caradhras, Clarion Ultimatum, Treasure Chest's d20 table);
# or a bare top-level ``Unimplemented`` effect (Rampant Growth, Mr. Wiggles,
# "Ach! Hans, Run!", Archmage Ascension's replacement).
_TUTOR_OWN_LIBRARY_RE = re.compile(
    r"search your library for (?:a|an|up to|one|two|three|x|that)",
    re.IGNORECASE,
)


def _arm_tutor(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``tutor`` node for the description-only bucket-B tail
    phase's SearchLibrary structure doesn't reach at all -- gap-gated by
    ``has_structural_tutor`` (never double-counts a card Tier-1 already
    reads) and the directed-idiom veto (SYNTH-EXCLUSION-PARITY).

    lf_ramp (2026-07-13): a NONLAND tree whose search text is PURE
    land-fetch-to-battlefield (Pir's Whim, the Lander known-token tree) is
    the ramp side of the convention -- :func:`_arm_land_fetch_ramp` emits a
    real ``ramp`` node for it instead, so this arm stays silent. A text
    that ALSO carries a genuine tutor sentence (Verdant Crescendo's Nissa
    fetch) keeps its ``synth_tutor`` alongside the ramp node."""
    if has_structural_tutor(tree):
        return None
    if _matches_tutor_directed_idiom(tree.oracle or ""):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    if not _TUTOR_OWN_LIBRARY_RE.search(kept):
        return None
    if not tree.is_type("Land"):
        _landish, land_only, other = _text_search_facts(kept)
        if land_only and not other:
            return None  # pure land fetch: ramp, never tutor (lf_ramp)
    return _synthetic_concept(
        arm_id="tutor",
        concept="synth_tutor",
        scope="you",
        subject=(),
        desc="bucket-B tutor (phase emits no reachable SearchLibrary node)",
    )


def _arm_land_fetch_ramp(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a real ``ramp`` node for the description-only land-fetch
    tail (lf_ramp, 2026-07-13): a NONLAND tree phase's SearchLibrary never
    structurally reaches whose search sentence fetches a LAND to the
    BATTLEFIELD -- the Lander known-token zero-unit tree ("Sacrifice this
    token: Search your library for a basic land card, put it onto the
    battlefield tapped"), a vote/repeat-for body (Travel Through
    Caradhras's Redhorn Pass branch), an emblem-granted future fetch.
    Shares :func:`_arm_tutor`'s exact gap gates (structural / directed-veto
    / own-library idiom), so its population is a strict subset of the cards
    the old ``synth_tutor`` rescue used to fire on -- a reroute, never a
    reach widening. Emits the REAL ``ramp`` concept, read by ``_ramp``'s
    first branch unconditionally for a nonland tree (the
    ``_arm_known_token_ramp`` precedent). LAND trees are excluded outright
    (the mana-base carve-out -- CR 305.6)."""
    if tree.is_type("Land"):
        return None
    if has_structural_tutor(tree):
        return None
    if _matches_tutor_directed_idiom(tree.oracle or ""):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    if not _TUTOR_OWN_LIBRARY_RE.search(kept):
        return None
    landish, _land_only, _other = _text_search_facts(kept)
    if not landish:
        return None
    return _synthetic_concept(
        arm_id="land_fetch_ramp",
        concept="ramp",
        scope="you",
        subject=(),
        desc="bucket-B land-fetch-to-battlefield ramp (lf_ramp reroute)",
    )


def _land_only_filter(filt: object) -> bool:
    """A filter whose CORE types are Land and nothing else (the ramp-vs-
    cheat carve-out, CR 305). Shared verbatim with the ``_extra_land_drop``
    lane (moved here alongside its structural gate)."""
    cores = set(filter_core_types(filt))
    return bool(cores) and cores <= {"Land"}


def has_structural_extra_land_drop(tree: ConceptTree) -> bool:
    """The extra_land_drop TYPED gate (CR 305.2/116.2a/305.4): a land PUT
    onto the battlefield bypassing the land-per-turn limit. Two structural
    shapes, shared verbatim with the ``_extra_land_drop`` lane (gap-gate-
    alignment) so the idiom-bridge synthesis arm below never fires on a
    card the typed read already covers:

    * a ``ChangeZone`` Hand->Battlefield whose moved subject is Land-only,
      controller you (Burgeoning's "put a land card from your hand onto
      the battlefield");
    * a ``Dig`` whose destination is Battlefield with a Land filter
      (Elvish Rejuvenator's look-at-top-five put).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("change_zone"):
            origin, dest = change_zone_dirs(c.node)
            sub = effect_filter(c.node)
            if (
                tag_of(c.node) == "ChangeZone"
                and origin == "Hand"
                and dest == "Battlefield"
                and _land_only_filter(sub)
                and filter_controller(sub) == "You"
            ):
                return True
        for c in unit.effect_concepts("dig"):
            if getattr(c.node, "destination", None) == "Battlefield" and (
                "Land" in filter_core_types(getattr(c.node, "filter", None))
            ):
                return True
    return False


# YOUR land-into-play PUT idiom (CR 305.4/720): "you may put a/up to N land
# card(s) from your hand|among them|among those cards|among the exiled
# cards ... onto the battlefield". phase folds this off a typed ChangeZone/
# Dig read a variety of ways: a cascade-from-exile reanimate (Averna) or a
# dig-into-play buried inside an exile/topdeck_select raw (Aminatou's
# Augury, Planar Genesis) leave it as a role=effect Unimplemented node with
# NO Land filter data (the ADR-0038 clause-grammar recovery would mis-tag
# these "reanimate"/"cast_from_zone" — concepts this lane doesn't read, so
# re-decoration alone can't close them), a dropped d20-branch put (Journey
# to the Lost City), or a "from hand OR graveyard" disjunction that defeats
# phase's controller pin on an otherwise-typed ChangeZone (Bonny Pall,
# Dread Tiller, Riveteers Confluence — controller=None, no InZone
# property). NO structured controller='You'+Land carrier survives any of
# these; the datum lives only in the whole-card oracle. Mirrors the
# OLD-IR ``_EXTRA_LAND_DROP_PUT_P``/``_recover_extra_land_drop`` idiom-scan
# byte-for-byte (verbatim extraction discipline).
_EXTRA_LAND_DROP_PUT_RE = re.compile(
    r"\byou may put (?:a |up to \w+ )?lands?\s+cards?\s+from\s+"
    r"(?:your hand|among them|among those cards|among the exiled cards)"
    r"\b.*\bonto the battlefield\b",
    re.IGNORECASE,
)


def _arm_extra_land_drop(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an "extra_land_drop" node for the YOUR land-into-play PUT
    idiom phase leaves wholly or partially unstructured. Gap-gated on
    :func:`has_structural_extra_land_drop` so a card the typed read already
    covers never doubles. Matched PER LINE (a modal/table card's bullets
    are '\\n'-delimited in the oracle; scanning the whole joined string
    risks a non-greedy match bridging into an unrelated later ability's
    own "onto the battlefield"). Emits its own concept
    ("extra_land_drop" — the mechanic name itself; no native effect/static
    tag is generic enough to reuse, since the lost datum is the
    Land+you-controller PAIRING, not a dispatchable verb), so the lane
    reads it via one added branch. CR 305.4/720."""
    if has_structural_extra_land_drop(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for line in kept.splitlines():
        if _EXTRA_LAND_DROP_PUT_RE.search(line):
            return _synthetic_concept(
                arm_id="extra_land_drop",
                concept="extra_land_drop",
                scope="you",
                subject=(),
                desc="land-into-play put phase leaves unstructured",
            )
    return None


# historic bare-word reference (CR 700.10: "an object is historic if it's
# an artifact, a legendary [permanent], and/or a Saga"). Multiple residue
# shapes lose the Historic qualifier entirely: a cast-restriction/cost-
# reduction filter phase collapses to an untyped Card filter (Jhoira's
# Familiar's ModifyCost "affected"), a LeavesBattlefield trigger's own "if
# it was historic" condition left unstructured (Curator's Ward), an
# activation cost "Discard a historic card" collapsed to a bare Discard
# cost with no filter (Sanctum Spirit), an Affinity-for-historic cost
# reduction with no cost-reduction node at all (Banish to Another
# Universe), a multi-clause Unimplemented "play a historic land or cast a
# historic permanent spell" (The Eighth Doctor — parseable as
# ``cast_from_zone`` via the shared verb grammar, but that concept isn't
# what THIS lane reads, so the ALLOWLIST recovery wouldn't close the gap
# either way), or an ``Unrecognized`` static CONDITION carrying the raw
# clause text (Havi's "four or more historic cards in your graveyard").
# NO structured Historic/NotHistoric carrier survives any of these; the
# reference lives only in the whole-card oracle. NO-residue class (ADR-
# 0038 amendment class 2). Mirrors the OLD-IR ``_HISTORIC_REF``/
# ``_recover_historic_subject`` bare-word fallback byte-for-byte
# (verbatim extraction discipline).
_HISTORIC_REF_RE = re.compile(r"\bhistoric\b", re.IGNORECASE)


def _arm_historic_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a bare "historic" REFERENCE for a card whose Historic
    predicate phase drops entirely (no typed Historic filter property
    anywhere). Gap-gated on the SAME ``has_filter_property(..., "Historic")``
    scan the ``_legends_historic_matters`` lane runs, so a card the typed
    read already covers never doubles. A cares-about REFERENCE, not an
    effect clause (ADR-0037's irreducible tree_synthesis remainder) — the
    concept name IS the mechanic ("historic_ref"), no native Historic
    effect/static tag exists to reuse (the property is a filter QUALIFIER,
    never its own node). CR 700.6/700.10."""
    if any(has_filter_property(u.node, "Historic") for u in tree.units):
        return None
    if not _HISTORIC_REF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="historic_matters",
        concept="historic_ref",
        scope="you",
        subject=(),
        desc="historic reference phase drops entirely (bare-word bridge)",
    )


# ── batch T6-niche-b: unspent_mana bucket-B tail ────────────────────────────
# CR 106.4/500.5 (case law Kruphix: unspent mana becomes colorless as steps
# end): the live structural ``StepEndUnspentMana`` static mode (Upwelling,
# Kruphix, Horizon Stone) already binds the 10 mode-carriers. The residual:
# the mana-BURST riders ("Until end of turn, you don't lose this mana as
# steps and phases end" — Savage Ventmaw, Brazen Collector, Birgi) and the
# "loses all unspent mana" tax forms (Mana Short, Power Sink, Worldpurge) —
# phase buries the retention/loss clause in an Unimplemented sub-ability of
# an unrelated trigger, no typed node exists. Relocates the deleted
# ``UNSPENT_MANA_REGEX`` mirror verbatim, gap-gated against the structural
# mode census. Measured byte-identical over the commander-legal corpus
# (10 structural + 32 bucket-B, 0 drops, 0 adds).
def has_structural_unspent_mana(tree: ConceptTree) -> bool:
    """Whether ANY static unit carries the ``StepEndUnspentMana`` mode
    (Upwelling/Kruphix/Horizon Stone's "unspent mana becomes colorless
    instead" replacement)."""
    return any(
        unit.origin == "static" and static_mode_tag(unit.node) == "StepEndUnspentMana"
        for unit in tree.units
    )


_UNSPENT_MANA_SYNTH_RX = re.compile(
    r"\bunspent mana\b|don't lose unspent|lose unspent mana|\bmana burn\b"
    r"|loses? (?:one or more )?unspent mana|don't lose (?:this |unspent )?"
    r"(?:\w+ )?mana as (?:steps|phases|those steps)",
    re.IGNORECASE,
)


def _matches_unspent_mana_idiom(oracle: str) -> bool:
    return bool(_UNSPENT_MANA_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_unspent_mana(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``unspent_mana`` node for the mana-burst-rider / mana-
    loss-tax bucket-B tail (the deleted ``UNSPENT_MANA_REGEX`` mirror
    relocated, gap-gated against :func:`has_structural_unspent_mana`)."""
    if has_structural_unspent_mana(tree):
        return None
    if not _matches_unspent_mana_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="unspent_mana",
        concept="synth_unspent_mana",
        scope="you",
        subject=(),
        desc="bucket-B unspent-mana burst-rider/tax residue (CR 106.4)",
    )


# ── dig_until bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ────────
# The reveal-until-a-condition deep dig (CR 701.20a): a ``RevealUntil`` effect
# whose ``player`` is Controller (Hermit Druid, 90/115 corpus). [P28]: phase
# mis-stamps ``player=Controller`` on "each opponent reveals cards from the
# top of THEIR library" (Mind Grind family), so the digger-field gate alone
# passes on opponent mills; the "their library" tell lives only in the
# unit's own description ([P8]/[P21]-precedent screen — the fix).
_DIG_UNTIL_NO_RESIDUE_RE = re.compile(
    r"\b(?:exile|reveal)s? cards? from the top of your library until you "
    r"(?:exile|reveal)s?\b",
    re.IGNORECASE,
)


def _arm_dig_until(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``dig_until`` node, vetoing the [P28] opponent-mill
    mis-stamp ("their library" in the unit's own description) via the
    node's own text — the deleted lane-time screen relocated verbatim.
    CR 701.20a.

    ADR-0037/0038 W3: a GRANTED trigger (Shifting Shadow's upkeep-destroy
    grant, Time Lord Regeneration's dies-grant) carries its own
    ``RevealUntil`` execute effect that is never surfaced as its own
    top-level concept node — the connive_makers / opponent_cast_matters
    shared descent (:func:`iter_nested_trigger_defs`) reaches it; the SAME
    :func:`reveal_until_player` digger read applies to the nested def's
    execute effect unchanged."""
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        if "their library" in desc:
            continue
        for c in unit.iter_concepts():
            if c.role != "effect" or c.concept != "reveal_until":
                continue
            # ADR-0038 recovery.py's "dig_until" grammar token already
            # requires "your library" ... "until" in the clause text (the
            # same digger-is-you fact a typed node's own ``player`` field
            # carries) — trust it unconditionally rather than reading
            # ``.player`` off the recovered node's ``.node``, which is
            # still the phase Unimplemented wrapper (no ``player`` field
            # of its own).
            if c.recovered_by or reveal_until_player(c.node) == "you":
                return _synthetic_concept(
                    arm_id="dig_until",
                    concept="synth_dig_until",
                    scope="you",
                    subject=(),
                    desc="bucket-B reveal-until-a-condition dig (CR 701.20a)",
                )
        for trig in iter_nested_trigger_defs(unit.node):
            # Deep-walk (not just ``trig.execute.effect``) — the RevealUntil
            # effect may sit a few ``sub_ability`` links deep in the
            # trigger's own SequentialSibling chain (Shifting Shadow: the
            # granted trigger's FIRST effect is "destroy this creature",
            # the RevealUntil is its ``sub_ability``).
            for effect in iter_typed_nodes(trig):
                if tag_of(effect) not in ("RevealUntil", "ExileFromTopUntil"):
                    continue
                if reveal_until_player(effect) == "you":
                    return _synthetic_concept(
                        arm_id="dig_until",
                        concept="synth_dig_until",
                        scope="you",
                        subject=(),
                        desc="bucket-B GRANTED reveal-until dig (CR 701.20a)",
                    )
    # ADR-0037/0038 W3 no-residue class (ADR-0038 amendment class 2): a
    # multi-card threshold ("until you exile TWO nonland cards", "until you
    # exile X permanent cards") defeats phase's own ExileFromTopUntil
    # DynamicQty parser — it degrades the whole trigger to a bare
    # single-card ChangeZone(Library->Exile) with a SwallowedClause parse
    # warning, dropping the until-loop ENTIRELY (Invasion of Alara's ETB,
    # Auspicious Starrix's mutate trigger). No Unimplemented node survives
    # to re-decorate, so this is a whole-card oracle-text fallback, gated
    # to run only after every structural arm above has already missed.
    if _DIG_UNTIL_NO_RESIDUE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return _synthetic_concept(
            arm_id="dig_until",
            concept="synth_dig_until",
            scope="you",
            subject=(),
            desc="bucket-B no-residue multi-card dig (phase DynamicQty gap)",
        )
    return None


# ── bounce_tempo bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ─────
# battlefield→hand bounce as tempo (CR 402.1: Boomerang, Unsummon) vs a
# graveyard-recall/self-return (CR 404.1). Phase emits a ZONE-LESS ``Bounce``
# for graveyard-to-hand returns ([P21] — the InZone marker is dropped), so
# the [P8]-precedent node-local description screen restores the boundary,
# scoped two ways: a SelfRef subject with a "from ... graveyard" description
# is a self-return (Abzan Devotee); a targeted bounce with that description
# is vetoed only when it's the unit's ONLY bounce (Aphetto Dredging,
# Greasefang's reanimate-loop return) — a unit that also carries a genuine
# tempo bounce (Aether Helix's two-sentence pair) still fires. A nested
# delayed-trigger unit carries no description of its own (the oracle text
# stayed on the parent), so the screen falls back to the whole-card
# description — the genuine gap needing text, both branches read ONLY
# description fields, never a cross-node typed lookup.
_BOUNCE_GY_PHRASES: tuple[str, ...] = (
    "from your graveyard",
    "from a graveyard",
    "from their graveyard",
    "from graveyards",
    "from target player's graveyard",
)


def _bounce_gy_phrase(text: str) -> bool:
    return any(phrase in text for phrase in _BOUNCE_GY_PHRASES)


def _arm_bounce_tempo(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``bounce_tempo`` node — the deleted lane-time GY-return
    veto (node-own description, whole-card fallback for a description-less
    nested delayed-trigger unit) relocated verbatim. CR 402.1 vs 404.1.

    v0.23.0 port (task #84): phase migrated the GY→hand recall family from
    the zone-less ``Bounce`` the [P21] description screen was built for to
    a full ``ChangeZone`` carrying ``origin: Graveyard`` directly (698
    carriers at the bump census). When a unit's own typed nodes carry the
    recall structurally, the unit's "from … graveyard" description is
    ACCOUNTED FOR by that node — any ``Bounce`` node still present in the
    same unit is the genuine tempo half (Aether Helix's two-sentence pair),
    so the description screen stands down for that unit rather than
    vetoing the survivor."""
    card_desc = " ".join(
        (getattr(u.node, "description", None) or "") for u in tree.units
    ).lower()
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        gy_return = _bounce_gy_phrase(desc) if desc else _bounce_gy_phrase(card_desc)
        gy_typed = any(
            tag_of(n) in ("ChangeZone", "ChangeZoneAll")
            and getattr(n, "origin", None) == "Graveyard"
            for n in iter_typed_nodes(unit.node)
        )
        if gy_return and gy_typed:
            gy_return = False  # the recall is typed; the screen stands down
        bounces = [
            c
            for c in unit.iter_concepts()
            if c.role == "effect" and c.concept == "bounce"
        ]
        for c in bounces:
            sub = effect_filter(c.node)
            # Typed-recall rider gates (task #84), BOTH scoped to a unit
            # whose own typed nodes carry a Graveyard-origin ChangeZone —
            # i.e. the unit IS a recall/reanimation chain, so a bounce
            # back-referencing that chain is the recalled object's rider,
            # never an opponent-facing tempo bounce (CR 402.1 vs 404.1):
            # * a ``ParentTarget``/``TrackedSet`` bounce is the delayed
            #   self-return rider on the reanimated object ("return it to
            #   its owner's hand at the beginning of the next end step" —
            #   Cauldron Dance, Greasefang) or the recall pair's second
            #   half (Once and Future). OUTSIDE a recall unit the same tags
            #   are phase's generic back-reference plumbing (Rancor's own
            #   return trigger, Run Away Together's two-target set — both
            #   genuine members, untouched);
            # * a ``SelfRef`` bounce on an INSTANT/SORCERY tree is the
            #   spell returning ITSELF from the graveyard (Revive the
            #   Fallen's clash rider) — spell recursion, not the Blinking
            #   Spirit battlefield self-bounce family. A PERMANENT's
            #   SelfRef bounce in the same shape (Mtenda Griffin's
            #   return-this-to-hand cost rider) keeps firing.
            if gy_typed and tag_of(getattr(c.node, "target", None)) in (
                "ParentTarget",
                "TrackedSet",
            ):
                continue
            if tag_of(sub) == "SelfRef":
                if gy_typed and (tree.is_type("Instant") or tree.is_type("Sorcery")):
                    continue
                if gy_return:
                    continue  # self GY-return — recursion, not tempo
            elif gy_return and len(bounces) == 1 and desc:
                continue  # the unit IS the graveyard recall
            if "Graveyard" in filter_inzone_zones(sub):
                continue
            if filter_controller(sub) == "You":
                continue
            return _synthetic_concept(
                arm_id="bounce_tempo",
                concept="synth_bounce_tempo",
                scope="you",
                subject=(),
                desc="bucket-B battlefield->hand tempo bounce (CR 402.1)",
            )
    return None


# ── ramp: the "Add {mana-expression}" clause-grammar tail (ADR-0039 W7 →
# task #82 grammar sprint) ───────────────────────────────────────────────────
# CR 106.1 / 605.1a: any ability that literally adds mana is acceleration.
# phase's clause grammar drops two DISTINCT idiom families as an
# ``Unimplemented`` node whose OWN ``description`` still names the add-mana
# clause verbatim — the read below is a per-NODE regex (never the whole-card
# oracle), so it structurally cannot hit a created TOKEN's own reminder-text
# ability (a ``Token`` effect node carries no oracle-echoing ``description``
# field at all — Deadly Derision / T'Challa's Treasure/Vibranium tokens
# corpus-verified this session to never produce a matching node).
#
# Two full-corpus-scan-verified false-positive shapes (ADR-0039 task #82,
# adjudicated genuine EXCLUSIONS, not census members): a replacement/
# redirect rider on ANOTHER ability's mana ("spells and abilities you
# control that WOULD add colored mana instead add that much white mana" —
# False Dawn) never itself produces mana (CR 614 — it just recolors what
# some OTHER ability adds), and a bare "mana value" (CMC) reference inside
# an unrelated arithmetic clause ("Roll a d20 and add the total mana value
# of those cards" — Song of Inspiration) is ADDING A NUMBER to a die roll,
# not mana.
_ADD_MANA_CLAUSE_RX = re.compile(
    r"\badds?\b[^.]*(\{[A-Za-z0-9]{1,3}\}|\bmana\b(?!\s+value))", re.IGNORECASE
)
_MANA_REDIRECT_RX = re.compile(r"\bwould\s+adds?\b", re.IGNORECASE)


def _matches_add_mana_clause(desc: str) -> bool:
    """A genuine "add mana" production clause (CR 106.1), excluding the
    two corpus-verified false-positive shapes above."""
    if _MANA_REDIRECT_RX.search(desc):
        return False
    return bool(_ADD_MANA_CLAUSE_RX.search(desc))


def has_structural_ramp_grant_mana(tree: ConceptTree) -> bool:
    """Whether a ``GrantAbility``'s OWN ``definition.effect`` already
    structures as a typed ``Mana`` node anywhere in the tree — the
    ``ramp_grant_unimplemented_body`` TYPED gate (former ledgered bridge,
    ADR-0039 task #82), so a card phase later parses the grant natively
    never doubles."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            if d is not None and tag_of(getattr(d, "effect", None)) == "Mana":
                return True
    return False


def _arm_ramp_grant_unimplemented_body(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``ramp`` node for a ``GrantAbility`` whose OWN granted-
    ability body parks as ``Unimplemented`` but names an "add ... mana"
    clause — Katilda, Dawnhart Prime / Tazri, Stalwart Survivor's self-
    referential "add one mana of any of ~'s colors" dynamic-color
    derivation (a clause phase's grammar has no verb for), and Old-Growth
    Troll's compound TWO-quoted granted-ability body joined by "and"
    ("Enchanted Forest has '{T}: Add {G}{G}' and '{1}, {T}, Sacrifice ~:
    Create...'" — phase's quote-splitter garbles BOTH the cost and effect
    halves of the FIRST quoted ability into one Unimplemented mess).
    ADR-0039 task #82 — graduates the former ``ramp_grant_unimplemented_
    body`` ledgered bridge (retired: deleted from ``bridge_ledger.BRIDGES``,
    its ``bridge_fires`` call site dropped from ``crosswalk_signals._ramp``).

    Gap-gated on :func:`has_structural_ramp_grant_mana`. Emits the REAL
    "ramp" concept (ADR-0038 retired the ``synth_*`` marker namespace), so
    the ``_ramp`` lane reads it through its OWN typed
    ``effect_concepts("ramp")`` walk — the very first branch, which fires
    unconditionally for a nonland card — no lane special-case at all (every
    pin here is a creature, never a land)."""
    if has_structural_ramp_grant_mana(tree):
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            if d is None:
                continue
            if tag_of(getattr(d, "effect", None)) != "Unimplemented":
                continue
            desc = getattr(d, "description", "") or ""
            if _matches_add_mana_clause(desc):
                return _synthetic_concept(
                    arm_id="ramp_grant_unimplemented_body",
                    concept="ramp",
                    scope="you",
                    subject=(),
                    desc=(
                        "granted mana-ability body parks as Unimplemented "
                        "(self-referential dynamic color / compound "
                        "two-quoted grant)"
                    ),
                )
    return None


def _ramp_unimplemented_add_mana_node(tree: ConceptTree) -> object | None:
    """The first ``Unimplemented`` node anywhere in the tree whose OWN
    ``description`` names an add-mana clause (CR 106.1), or ``None``."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Unimplemented":
                continue
            desc = getattr(n, "description", "") or ""
            if _matches_add_mana_clause(desc):
                return n
    return None


def _arm_ramp_dropped_add_mana_clause(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``ramp`` node for a nonland card whose own "Add
    {mana-expression}" clause parks as an ``Unimplemented`` node — a
    dynamic/scaling count (Neheb's "for each 1 life...", Fangorn's "twice
    that much", Plasm Capture's "X mana ... where X is that spell's mana
    value"), a restricted-spend or note-type rider (Adarkar Unicorn, Ice
    Cauldron, Jeweled Amulet, Kyren Toy, Charmed Pendant, Unglued Pea-
    Brained Dinosaur), a die-roll/sticker value table ("Name Sticker"
    Goblin, ________ Goblin), or a player-choice recipient (Victory
    Chimes) — the "add ... mana" clause always survives verbatim in the
    dropped node's OWN ``description``, never elsewhere. ADR-0039 task #82
    — graduates 22 of the former ``ramp_dropped_add_mana_clause`` ledgered
    bridge's 24-name enumeration into this typed read; the row NARROWED
    (task #82) to the 2 names this per-node scan structurally cannot
    reach, then NARROWED AGAIN (task #87): Braid of Fire graduated a
    SECOND time when ``build_concept_tree`` grew a dedicated
    ``"keyword"`` ``AbilityUnit`` origin for a keyword's own effect
    payload (Cumulative Upkeep's "Add {R}", ``root.keywords``) — it now
    carries a REAL ``effect_concepts("ramp")`` hit, so this arm's own gap
    check (below) stands it down through the FIRST branch (already
    served), never reaching the per-node scan at all. Raggadragga,
    Goreguts Boss (a mana-ability-HAVER support card with no add-mana
    clause of its own at all — its ``keywords`` list is empty, so the new
    origin doesn't touch it either) is the ONLY name left un-synthesizable
    by any current arm.

    Gap-gated on the SAME "not a land, no existing structural ramp"
    condition the bridge's own ``_ramp_dropped_clause_gap`` used, so a card
    already served through ANY other ramp path (its own top-level Mana
    effect) never doubles. Emits the REAL "ramp" concept — the ``_ramp``
    lane's first branch fires unconditionally for a nonland card, no lane
    special-case (every corpus hit here is a nonland permanent or a
    sorcery/instant, never itself a Land).

    BLAST RADIUS (ADR-0039 task #82, full commander-legal corpus re-scan,
    32,521 cards): beyond the graduated 22, 7 genuine BEYOND-LEGACY
    structural gains, each corpus-verified as a real CR 106.1 mana-
    producing ability the naive whole-card-regex over-fire concern never
    applied to (Drain Power — "you add the mana lost this way" off an
    opponent's forced mana-ability activation; Jetfire, Ingenious
    Scientist — "Target player adds that much {C}"; Mana Seism —
    "Sacrifice any number of lands, then add that much {C}"; Pygmy Hippo
    — "you add an amount of {C} equal to the amount of mana that player
    lost"; Runaway Growth — an Aura granting its enchanted land "add an
    additional amount of {G}"; Summitfest Closing Ceremony — "Add X {U}
    and X {R}"; Vigorous Farming — perpetually grants a library's topmost
    land "add an additional {G}"). Two additional raw regex hits were
    ADJUDICATED NOT RAMP and excluded by :func:`_matches_add_mana_clause`
    (see its docstring): False Dawn's "spells... that WOULD add colored
    mana instead add..." is a CR 614 mana-color REPLACEMENT rider that
    never itself produces mana; Song of Inspiration's "add the total mana
    value of those cards" is arithmetic addition to a die roll (CMC, not
    mana)."""
    if tree.is_type("Land") or tree.effect_concepts("ramp"):
        return None
    if _ramp_unimplemented_add_mana_node(tree) is None:
        return None
    return _synthetic_concept(
        arm_id="ramp_dropped_add_mana_clause",
        concept="ramp",
        scope="you",
        subject=(),
        desc=(
            "add-mana clause parks as Unimplemented (scaling/restricted/"
            "die-roll/choice residue, CR 106.1)"
        ),
    )


# ── task #95 — known-tokens text-only-tree bucket-B arms ───────────────────
# The ``_ir_lookup`` KNOWN-TOKENS SUBSTRATE (task #92) appends one zero-unit
# TEXT-ONLY ``ConceptTree`` per matched predefined token whose OWN Token
# effect node phase parsed no ability body for — carrying the token's
# verbatim ``rules_text`` on ``tree.oracle``, ``units=()``. The task #95
# adjudication sweep widened the wired allowlist beyond Mutagen/Young Hero
# to five more identities whose FIXED, KNOWN wording names a CR-grounded
# ramp / explore / impulse-draw / life-loss ability: Powerstone, Gold
# (ramp), Map (explore), Junk (impulse-draw), Wicked (opponent life loss).
# Lander ("Search your library for a basic land card, put it onto the
# battlefield tapped") is DELIBERATELY absent from the ramp idiom below —
# corpus-verified (Rampant Growth, Nature's Lore, Wayfarer's Bauble, Solemn
# Simulacrum, Migration Path all probed) this system's OWN ``_ramp`` lane
# never tags a search-basic-land-to-battlefield effect ``ramp`` at all
# (``_ramp`` requires a literal Mana-producing effect; a land fetch is
# ``tutor``'s territory instead, CR 701.23/701.23a) — Lander already gets
# ``tutor`` for FREE via ``_tutor_lane``'s existing ``synth_tutor``
# bucket-B oracle-text rescue arm (:func:`_arm_tutor` below), with zero
# code needed here; tagging it ``ramp`` too would be a genuine
# inconsistency against every real land-tutor card's own treatment. Each
# arm below matches its fixed wording directly off ``tree.oracle`` — no
# unit walk needed (there are none to walk) — gated on ``not tree.units``
# so it scopes STRICTLY to a zero-unit text-only tree (a normal phase-
# parsed card's ``units`` is never empty, so this gate never touches a
# real ability's own text), plus the target lane's own "not already
# served" check where the lane exposes one, so a future card whose OWN
# typed effect happens to ALSO carry this wording never double-fires.
_RAMP_KNOWN_TOKEN_IDIOMS: tuple[str, ...] = (
    "can't be spent to cast a nonartifact spell",  # Powerstone (CR 605.1a)
    "add one mana of any color",  # Gold (CR 106.1/605.1a)
    # task #np_roles adjudicated AGAINST adding the bare land-tap idiom
    # ("{T}: Add {G}." — Forest Dryad; "{T}: Add {C}." — the Mutavault
    # token): both identities are LAND tokens, and the ``_ramp`` lane's own
    # land split (CR 305 vs 106.1) reads a basic-equivalent single-color/
    # single-{C} tap as MANA BASE, never ramp — a real Forest / Mutavault
    # card doesn't fire ``ramp``, so its token twin must not either (the
    # token twin mirrors its real-card twin; the lf_ramp convention change
    # doesn't touch these LAND tokens — the mana-base carve-out stands).
)


def _arm_known_token_ramp(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``ramp`` node for a Powerstone / Gold known-token
    zero-unit text-only tree (task #95) — see the block comment above.
    Gated on ``not tree.units`` (the text-only-tree shape) and ``not
    tree.effect_concepts("ramp")`` (never doubles a card that already
    structures its own ramp). Emits the REAL ``ramp`` concept — the
    ``_ramp`` lane's first branch (``effect_concepts("ramp")``) reads it
    unconditionally for a nonland tree (both identities are Artifacts,
    never Lands), the SAME real-concept precedent
    ``_arm_ramp_grant_unimplemented_body`` above already established."""
    if tree.units or tree.effect_concepts("ramp"):
        return None
    oracle = (tree.oracle or "").lower()
    if not any(idiom in oracle for idiom in _RAMP_KNOWN_TOKEN_IDIOMS):
        return None
    return _synthetic_concept(
        arm_id="known_token_ramp",
        concept="ramp",
        scope="you",
        subject=(),
        desc="predefined known-token mana ability (Powerstone/Gold)",
    )


def _arm_known_token_explore(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``explore`` node for a Map known-token zero-unit
    text-only tree (task #95) — "Target creature you control explores"
    (CR 701.44a). Gated on ``not tree.units`` and
    ``not tree.effect_concepts("explore")``. Emits the REAL ``explore``
    concept — ``_explore_makers``'s only branch reads it unconditionally."""
    if tree.units or tree.effect_concepts("explore"):
        return None
    if "target creature you control explores" not in (tree.oracle or "").lower():
        return None
    return _synthetic_concept(
        arm_id="known_token_explore",
        concept="explore",
        scope="you",
        subject=(),
        desc="predefined known-token explore ability (Map, CR 701.44a)",
    )
