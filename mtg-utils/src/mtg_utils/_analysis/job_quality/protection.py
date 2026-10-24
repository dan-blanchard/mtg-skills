"""Protection — how well a card protects your board or you (``roles.protects``,
the ``protects-board`` preset's protective half; a counterspell is the counter
job and scores ``None`` here).

Read off the shared protection walks (``crosswalk.protection``:
:func:`protective_grant_recipients`, :func:`protective_saves`,
:func:`attack_deterrent`, and ``reads.redirects_stack_object``), run on a
one-unit view of each tree so each protective ability's own scope, speed, cost
and duration come off its own node.

Fitted on the 798 commander-legal cards whose main job is protection (a
protective ability usable at instant speed, always on or lasting; not riding a
+2-or-more pump; a creature's only when it is a hard grant it activates, holds
statically, or gives the whole board on entering): cross-validated Spearman 0.555
against play-rate; the precon guides' protection adds sit at the 94th percentile
of their color identity's protection by this read (97th by play-rate). Strong
enough to ORDER candidates.

A protective keyword granted only while a condition holds (Eater of Virtue's "as
long as a card exiled with ~ has hexproof", Bedrock Tortoise's "during your
turn", a kicker's or spell mastery's "if ...") reads as soft: it shields nothing
the turn the condition fails. That read cost the fit 0.03 of CV (0.586 before) —
those cards' play-rate rewarded the keyword — and moved 45 cards.

Swiftfoot Boots and Lightning Greaves: the haste beside their hexproof / shroud
is a second job, not protection, so it is not scored. As a feature it fit only
those two cards' play-rate and put them above every board-wide one-shot; without
it Heroic Intervention, Teferi's Protection and Flawless Maneuver (which shield
the whole board from targeted removal AND a destroy-wipe) rank above them, as the
upgrade guides do, and both stay in the top 7%.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    activation_mana,
    cast_cost,
    faces,
    land_back,
    mana_in,
    one_unit,
    unit_kind,
)
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    attack_deterrent,
    filter_controller,
    filter_predicates,
    filter_subtypes,
    iter_cost_leaves,
    iter_mod_sites,
    iter_typed_nodes,
    node_duration,
    protective_grant_recipients,
    protective_keyword,
    protective_saves,
    redirects_stack_object,
    static_mode_tag,
    tag_of,
    unit_keyword_grants,
)
from mtg_utils._card_ir.trees import phase_records_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree

#: What survives a destroy-wipe: indestructible ("can't be destroyed", CR
#: 702.12b), phasing out ("treated as though it does not exist", 702.26b — its
#: example: not destroyed by "Destroy all creatures"), a return-to-battlefield
#: replacement. Protection from everything (702.16j) stops targeting, Auras,
#: Equipment, blocking and damage — the rule names no destruction, so it is
#: target-proof, not wipe-proof.
_WIPE_PROOF = frozenset({"indestructible", "phase_out", "return"})
#: Regeneration replaces the next destruction this turn (701.19a), so a WHOLE
#: board's regeneration also saves it from a destroy-wipe (one that doesn't say
#: "can't be regenerated"); one creature's regeneration stays a soft save.
_WIPE_PROOF_TEAM = _WIPE_PROOF | {"regenerate"}
#: Shields against targeted removal. Ward is not one: it is a tax — "counter
#: that spell or ability unless that player pays [cost]" (702.21a).
_TARGET_PROOF = frozenset({"hexproof", "shroud", "protection", "phase_out"})
#: Everything short of soft (prevention, regeneration, ward, a life floor).
_HARD = _WIPE_PROOF | _TARGET_PROOF | {"pillowfort", "redirect"}
#: Filter properties naming the attached permanent (an Equipment's, an Aura's).
_ATTACH_PROPS = frozenset({"EquippedBy", "EnchantedBy", "AttachedTo"})
#: Back-references and object tags that name one chosen object.
_ONE_OBJECT_TAGS = frozenset(
    {
        "ParentTarget",
        "TrackedSet",
        "SelfRef",
        "Any",
        "SourceOrPaired",
        "TriggeringSource",
        "EventTarget",
    }
)
#: Durations that outlast the turn: the one-shot is still up on their turn.
_LONG = frozenset(
    {"UntilNextTurnOf", "UntilYourNextTurn", "Permanent", "UntilHostLeavesPlay"}
)
#: Layouts whose back face is not cast on its own: only the front protects.
_BACK_HIDDEN = frozenset({"transform", "flip", "meld"})
#: Layouts whose halves are cast separately, each at its own cost.
_HALF_COST = frozenset({"split", "adventure", "modal_dfc"})
#: Keywords that charge rent for keeping the permanent.
_UPKEEP_KEYWORDS = frozenset({"cumulative upkeep", "echo", "fading", "vanishing"})


@dataclass(frozen=True)
class _Unit:
    """One protective ability: what it gives, to whom, when and at what cost."""

    kind: str  # spell | activated | etb | trigger | static | <origin>
    kws: frozenset[str]  # protective keywords and save kinds, pillowfort, redirect
    scopes: frozenset[str]  # team | team_narrow | one | attached | player
    pump: int  # the most power the same grant adds (a voltron Sword's +2)
    narrow_prot: bool  # every protection grant is from a fixed quality
    act_mana: int | None  # an activated ability's mana cost
    sac_self: bool  # the card pays itself away (one use)
    sorcery: bool  # an activation held to sorcery speed (equip)
    equip: bool  # the Equip ability itself
    duration: str | None
    fog: bool  # prevents a whole attack's damage
    deter: str | None  # attack_deterrent's kind
    deter_one: bool  # the deterrent binds only the enchanted creature (the Vows)
    redirect_wide: bool  # redirects every target, or spells and abilities alike
    upkeep_sac: bool  # an upkeep trigger that sacrifices
    face_cmc: int | None  # the face's own printed mana value
    equip_cost: int | None  # the card's cheapest equip


def _list(x: object) -> list:
    return x if isinstance(x, list) else []


def _broad(filt: object) -> bool:
    """A team filter covering your creatures or permanents with no tribe, type
    subset (lands only) or further predicate (creatures with a counter)."""
    parts = [filt] if tag_of(filt) == "Typed" else _list(getattr(filt, "filters", None))
    for f in parts:
        types = [
            t for t in _list(getattr(f, "type_filters", None)) if isinstance(t, str)
        ]
        if (
            (not types or {"Creature", "Permanent"} & set(types))
            and not filter_subtypes(f)
            and not [p for p in filter_predicates(f) if p != "Another"]
        ):
            return True
    return False


def _filter_scope(filt: object, *, targeted: bool, multi: bool) -> str:
    """Who one protective recipient filter covers: ``team`` (every matching
    permanent of yours), ``one`` (a chosen object), ``attached``, or ``player``."""
    tag = tag_of(filt)
    if tag in ("Controller", "Player"):
        return "player"
    if tag == "ControllerAndControlledPermanents":
        return "team"
    if tag == "AttachedTo":
        return "attached"
    if targeted or tag in _ONE_OBJECT_TAGS:
        return "team" if multi else "one"
    if tag not in ("Typed", "Or", "And"):
        return "one"
    props = {
        tag_of(p)
        for n in iter_typed_nodes(filt)
        for p in _list(getattr(n, "properties", None))
    }
    if props & _ATTACH_PROPS:
        return "attached"
    parts = [filt] if tag == "Typed" else _list(getattr(filt, "filters", None))
    if "You" not in {filter_controller(f) for f in parts}:
        # Any player's object is a chosen one (Vodalian Illusionist's phase-out):
        # phase types "target creature phases out" and "all permanents you control
        # phase out" alike, so the controller is the tell.
        return "team" if multi else "one"
    if (
        tag == "Typed"
        and not _list(getattr(filt, "type_filters", None))
        and filter_controller(filt) == "You"
    ):
        return "player"
    return "team"


def _any_number(unit_node: object) -> bool:
    """ "Any number of target ..." — a ``multi_target`` with no upper bound."""
    for n in iter_typed_nodes(unit_node):
        mt = getattr(n, "multi_target", None)
        if hasattr(mt, "max") and getattr(mt, "max", None) is None:
            return True
    return False


#: A player's own protective static modes (Leyline of Sanctity's "You have
#: hexproof"), by the keyword ``protective_grant_recipients`` reports for them.
_PLAYER_MODES = {
    "Hexproof": "hexproof",
    "Shroud": "shroud",
    "PlayerProtection": "protection",
}


def _conditional_defs(unit_node: object) -> set[int]:
    """The ids of the static defs under ``unit_node`` that hold only while a
    condition does: a def with its own ``condition`` (Eater of Virtue's "as long
    as a card exiled with ~ has hexproof"; a static unit's condition is its def's;
    Giant's Amulet's granted "as long as it's untapped"), and every def inside
    the ``effect`` of an ability or sub-ability that carries a condition ("If ~ is
    a Detective, ... it gains 'Other creatures you control have indestructible'").
    A condition gating only a sibling effect (Veil of Summer's draw) leaves the
    grant in the sub-ability unconditional."""
    out: set[int] = set()
    for n in iter_typed_nodes(unit_node):
        if tag_of(getattr(n, "condition", None)) is None:
            continue
        if (
            isinstance(getattr(n, "modifications", None), list)
            or static_mode_tag(n) in _PLAYER_MODES
        ):
            out.add(id(n))
        effect = getattr(n, "effect", None)
        if tag_of(effect) is not None:
            out.update(id(m) for m in iter_typed_nodes(effect))
    return out


def _is_fog(n: object) -> bool:
    """A prevention of a whole attack: all combat damage (Fog), all damage to you
    (Riot Control), all damage your opponents' creatures deal (Obscuring Haze)."""
    if tag_of(n) != "PreventDamage" or getattr(n, "amount", None) != "All":
        return False
    recipient = tag_of(getattr(n, "target", None))
    if recipient in ("Controller", "ControllerAndControlledPermanents"):
        return True
    return recipient == "Any" and (
        getattr(n, "scope", None) == "CombatDamage"
        or tag_of(getattr(n, "damage_source_filter", None)) is not None
    )


def _read_unit(tree: ConceptTree, u: AbilityUnit) -> _Unit | None:
    """The protective ability ``u`` is, or ``None``: the shared walks run on a
    one-unit view of ``tree``, then scope, speed and cost read off ``u``'s node."""
    sub = one_unit(tree, u)
    grants = list(protective_grant_recipients(sub))
    saves = list(protective_saves(sub))
    deter = attack_deterrent(sub)
    redirects = [
        n
        for n in iter_typed_nodes(u.node)
        if tag_of(n) == "ChangeTargets" and redirects_stack_object(n)
    ]
    if not (grants or saves or deter or redirects):
        return None
    multi = _any_number(u.node)
    targeted = {id(mod) for _t, mod in unit_keyword_grants(u)}
    kws: set[str] = set()
    scopes: set[str] = set()
    pump, narrow = 0, []
    conditional = _conditional_defs(u.node)
    held, cond_held = set(), set()
    # The scope of each grant the walk found: the same mod sites, read for their
    # recipient filter (the walk yields only "player" / "permanent"). A grant
    # that holds only under a condition reads as soft: no keyword, no scope.
    for sdef, mod in iter_mod_sites(u.node, deep=True):
        kw = protective_keyword(mod)
        if kw is None:
            continue
        if id(sdef) in conditional:
            cond_held.add(kw)
            continue
        held.add(kw)
        kws.add(kw)
        if kw == "protection":
            inner = getattr(getattr(mod, "keyword", None), "inner", None)
            # A quality chosen on resolution (Mother of Runes' color, Serra's
            # Emissary's card type) answers whatever is coming.
            narrow.append(
                not (
                    inner == "Everything"
                    or (isinstance(inner, str) and inner.startswith("Chosen"))
                )
            )
        affected = getattr(sdef, "affected", None)
        scope = _filter_scope(affected, targeted=id(mod) in targeted, multi=multi)
        if scope == "team" and not _broad(affected):
            scope = "team_narrow"  # a tribe, lands only, a strive pick
        scopes.add(scope)
        for m2 in _list(getattr(sdef, "modifications", None)):
            if tag_of(m2) == "AddPower":
                v = getattr(m2, "value", 0)
                pump = max(pump, v if isinstance(v, int) else 2)
    player_modes = [
        n for n in iter_typed_nodes(u.node) if static_mode_tag(n) in _PLAYER_MODES
    ]
    player_cond = bool(player_modes) and all(id(n) in conditional for n in player_modes)
    for kw, who in grants:
        only_conditional = kw in cond_held - held and (
            who == "permanent" or not player_modes
        )
        if only_conditional or (who == "player" and player_cond):
            continue  # granted only under a condition
        kws.add(kw)
        if who == "player":
            scopes.add("player")
    fog = False
    for n in iter_typed_nodes(u.node):
        fog = fog or _is_fog(n)
        if tag_of(n) in ("PhaseOut", "Regenerate", "PreventDamage"):
            target = getattr(n, "target", None)
            if tag_of(target):
                scopes.add(
                    _filter_scope(
                        target, targeted=tag_of(target) == "ParentTarget", multi=multi
                    )
                )
    for kind, who in saves:
        kws.add(kind)
        valid = getattr(u.node, "valid_card", None)
        if who == "player":
            scopes.add("player")
        elif u.origin == "replacement" and tag_of(valid):
            # A standing shield names what it covers (General's Kabuto: the
            # equipped creature; Vigor: creatures you control).
            scopes.add(_filter_scope(valid, targeted=False, multi=False))
        elif kind in ("prevent_damage", "return", "life_floor") and not scopes - {
            "player"
        }:
            scopes.add("team")
    deter_one = False
    if deter:
        kws.add("pillowfort")
        scopes.add("player")
        for n in iter_typed_nodes(u.node):
            if getattr(n, "mode", None) in ("CantAttack", "CantAttackOrBlock"):
                aff = getattr(n, "affected", None)
                props = {tag_of(p) for p in _list(getattr(aff, "properties", None))}
                deter_one = deter_one or bool(props & _ATTACH_PROPS)
    if redirects:
        kws.add("redirect")
        scopes.add("one")

    def _stack_kinds(n: object) -> set[str | None]:
        return {tag_of(x) for x in iter_typed_nodes(getattr(n, "target", None))} & {
            "StackSpell",
            "StackAbility",
        }

    cost = getattr(u.node, "cost", None)
    kind = unit_kind(u)
    duration = node_duration(u.node)
    for n in iter_typed_nodes(u.node):
        duration = duration or node_duration(n)
    restrictions = {
        tag_of(r) for r in _list(getattr(u.node, "activation_restrictions", None))
    }
    return _Unit(
        kind=kind,
        kws=frozenset(kws),
        scopes=frozenset(scopes),
        pump=pump,
        narrow_prot=bool(narrow) and all(narrow),
        act_mana=activation_mana(u),
        # The card pays itself away (Selfless Spirit's sacrifice, Selfless
        # Glyphweaver's exile): one use, not a repeatable shield.
        sac_self=any(
            (
                tag_of(n) == "Sacrifice"
                and tag_of(getattr(n, "target", None)) == "SelfRef"
            )
            or (
                tag_of(n) == "Exile" and tag_of(getattr(n, "filter", None)) == "SelfRef"
            )
            for n in iter_cost_leaves(cost)
        ),
        sorcery="AsSorcery" in restrictions,
        equip=tag_of(getattr(u.node, "ability_tag", None)) == "Equip",
        duration=duration,
        fog=fog,
        deter=deter,
        deter_one=deter_one,
        redirect_wide=any(
            tag_of(getattr(n, "scope", None)) == "All" or len(_stack_kinds(n)) == 2
            for n in redirects
        ),
        upkeep_sac=u.origin == "trigger"
        and (u.trigger_event or "").lower() in ("upkeep", "phase")
        and u.has_effect("sacrifice"),
        face_cmc=tree.cmc if tree.has_printed_cost else None,
        equip_cost=None,
    )


def _units(card: dict) -> list[_Unit]:
    """Every protective ability of ``card`` (front face only for a transforming
    card), each carrying the card's cheapest equip cost."""
    trees = list(signal_trees_for(card, bulk=card))
    if card.get("layout") in _BACK_HIDDEN and len(trees) > 1:
        front = (card.get("name") or "").split(" // ")[0]
        trees = [t for t in trees if t.name == front] or trees[:1]
    out: list[_Unit] = []
    for tree in trees:
        read = [r for u in tree.units if (r := _read_unit(tree, u)) is not None]
        equips = [
            mana_in(getattr(u.node, "cost", None))
            for u in tree.units
            if u.kind == "Activated"
            and tag_of(getattr(u.node, "ability_tag", None)) == "Equip"
        ]
        if equips:
            read = [dataclasses.replace(r, equip_cost=min(equips)) for r in read]
        out.extend(read)
    return out


def _free_cast(card: dict) -> bool:
    """Whether phase's ``casting_options`` let the card be cast for no mana:
    ``CastWithoutManaCost`` (Deflecting Swat, Flawless Maneuver — "If you control
    a commander, you may cast this spell without paying its mana cost") or a pitch
    ``AlternativeCost`` with no mana in it (Misdirection). ``casting_options`` is
    a phase record field the concept tree does not carry, so this reads the raw
    phase face records (structured data, not oracle text)."""
    for face in phase_records_for(card.get("oracle_id") or ""):
        for opt in face.get("casting_options") or ():
            if opt.get("kind") == "CastWithoutManaCost":
                return True
            if opt.get("kind") == "AlternativeCost" and "Mana" not in json.dumps(
                opt.get("cost")
            ):
                return True
    return False


#: Protection's weights, log10 play-rate per unit (ridge fit, 2026-10-19,
#: standardised weight / feature sd, rounded).
WEIGHTS: dict[str, float] = {
    "team": 0.12,  # covers every creature / permanent you control
    "team_narrow": 0.30,  # covers a tribe, a type subset or a conditioned set
    "wipe_proof": 0.49,  # whole board, up in time, survives a destroy-wipe
    "player_only": 0.04,  # protects only you (Leyline of Sanctity)
    "target_proof": 0.22,  # hexproof, shroud, protection or phasing out
    "indestructible": 0.22,  # indestructible or phasing out
    "soft_only": -0.15,  # only prevention, regeneration, ward or a life floor
    "fog": 0.13,  # prevents a whole attack's damage
    "equipment": 0.67,  # an Equipment's grant: moves on when its creature dies
    "repeat_cheap": 0.34,  # a repeatable hard grant at one mana or less a use
    "upkeep_cost": -0.22,  # cumulative upkeep, echo, an upkeep sacrifice
    "free_cast": 0.40,  # castable for no mana (a commander, a pitch cost)
    "cheap": 0.06,  # cast plus equip costs 2 or less
    "body": -0.08,  # a creature
    "pillow_tax": 0.87,  # every attacker on you pays (Ghostly Prison)
    "pillow_other": 0.32,  # another attack ban or limit on you
    "redirect_wide": 0.93,  # redirects every target, or spells and abilities
    "narrow_prot": -0.29,  # protection only from a fixed color or type
    "land_back": 0.60,  # a modal double-faced card whose back is a land
}


def _timely(u: _Unit, *, instant: bool) -> bool:
    """Up when removal resolves: an instant / flash spell, an activation not held
    to sorcery speed, an always-on static, or a one-shot outlasting the turn."""
    return (
        (u.kind == "spell" and instant)
        or (u.kind == "activated" and not u.sorcery)
        or u.kind == "static"
        or u.duration in _LONG
    )


def features(card: dict) -> dict[str, float] | None:
    """The protection read's features for ``card``, or ``None`` when it has no
    protective ability of its own (a counterspell only is the counter job)."""
    units = _units(card)
    if not units:
        return None
    front = faces(card)[0]
    subtypes = (front.split("—")[1] if "—" in front else "").split()
    instant = "Instant" in front or "Flash" in (card.get("keywords") or ())
    kws = frozenset().union(*(u.kws for u in units))
    live = [u for u in units if _timely(u, instant=instant)]
    scopes = frozenset().union(*(u.scopes for u in live)) if live else frozenset()
    all_scopes = frozenset().union(*(u.scopes for u in units))
    attach = "attached" in all_scopes
    team = "team" in scopes
    cost = cast_cost(card)
    if card.get("layout") in _HALF_COST:
        # Each half is cast on its own: the protecting half's cost (No More's 3,
        # not Gallifrey Falls // No More's combined 9).
        halves = [u.face_cmc for u in units if u.face_cmc is not None]
        cost = float(min(halves)) if halves else cost
    free = _free_cast(card)
    if free:
        cost = 0.0
    equips = [u.equip_cost for u in units if u.equip_cost is not None]
    deploy = cost + (min(equips) if equips and attach else 0)
    pillow = [u for u in units if "pillowfort" in u.kws]
    tax = any(u.deter == "attack_tax" and not u.deter_one for u in pillow)
    keywords = {k.lower() for k in card.get("keywords") or ()}
    return {
        "team": float(team),
        "team_narrow": float("team_narrow" in scopes and not team),
        "wipe_proof": float(
            any("team" in u.scopes and u.kws & _WIPE_PROOF_TEAM for u in live)
        ),
        "player_only": float(
            bool(all_scopes) and all_scopes <= {"player"} and not pillow
        ),
        "target_proof": float(bool(kws & _TARGET_PROOF)),
        "indestructible": float(bool(kws & {"indestructible", "phase_out"})),
        "soft_only": float(not kws & _HARD),
        "fog": float(any(u.fog for u in units)),
        "equipment": float(attach and "Equipment" in subtypes),
        "repeat_cheap": float(
            any(
                u.kind == "activated"
                and not u.sac_self
                and not u.equip
                and (u.act_mana or 0) <= 1
                and u.kws & (_WIPE_PROOF | _TARGET_PROOF)
                for u in units
            )
        ),
        "upkeep_cost": float(
            bool(keywords & _UPKEEP_KEYWORDS) or any(u.upkeep_sac for u in units)
        ),
        "free_cast": float(free),
        "cheap": float(deploy <= 2),
        "body": float("Creature" in front),
        "pillow_tax": float(tax),
        "pillow_other": float(
            not tax and any(u.deter != "attack_tax" and not u.deter_one for u in pillow)
        ),
        "redirect_wide": float(any(u.redirect_wide for u in units)),
        "narrow_prot": float(
            any(u.narrow_prot for u in units) and not kws - {"protection"}
        ),
        "land_back": float(land_back(card)),
    }
