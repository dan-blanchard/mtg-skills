"""The curve cap (ADR-0066): no add far past the deck's own top end, and the
cards a cheat plan reaches that it never holds back (split out of ``swaps``)."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from mtg_utils._analysis.costs import CastCosts, cast_costs
from mtg_utils._card_ir.crosswalk.core import TypedMirrorNode
from mtg_utils._card_ir.crosswalk.reads import (
    change_zone_dirs,
    filter_admits,
    filter_controller,
    mill_reaches_you,
    replacement_event_tag,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.card_classify import is_land
from mtg_utils.deck import split_type_line

#: The deck cards a cheat must have (two) before the cap lifts for what it
#: reaches: the floor ``metrics.efficiency``'s ``cost_cheat_waiver`` holds its
#: reanimation slots to.
CHEAT_FLOOR = 2

#: The card types that can be put onto the battlefield: an untyped cheat reaches
#: these only, an instant or a sorcery never (CR 304.4, 307.4).
PERMANENT_TYPES = frozenset(
    {"artifact", "battle", "creature", "enchantment", "land", "planeswalker"}
)

#: The moves a "from anywhere" replacement of a card's own graveyard move takes
#: over beside a death: a discard and a mill (its active zones).
_OFF_BATTLEFIELD = frozenset({"Hand", "Library"})


def _zones(value: object) -> set[str]:
    return set(value) if isinstance(value, (list, tuple)) else set()


def cant_be_reanimated(card: Mapping) -> bool:
    """Whether no reanimation can return the card from a graveyard, read off its
    front face: a mandatory replacement of its own move to a graveyard from
    anywhere — its hand and library too, not only a death (CR 614.1a, "instead":
    Blightsteel Colossus, Darksteel Colossus and Progenitus shuffle themselves
    into the library) — or a trigger on its own move to a graveyard from
    anywhere that shuffles the graveyard away (Kozilek, Butcher of Truth; Ulamog,
    the Infinite Gyre; Emrakul, the Aeons Torn) or the card itself (Worldspine
    Wurm; Dread and the other Lorwyn Incarnations), the conservative line for a
    card a reanimation could answer in response. A "would die … instead"
    (Possessed Skaab, Gravebane Zombie) is not one: a discard or a mill still
    puts the card in the graveyard. The builder's addition to Dan's R2."""
    trees = trees_for(dict(card))
    if not trees:
        return False
    for unit in trees[0].units:
        node = unit.node
        if (
            unit.origin == "replacement"
            and replacement_event_tag(node) == "Moved"
            and getattr(node, "destination_zone", None) == "Graveyard"
            and tag_of(getattr(node, "valid_card", None)) == "SelfRef"
            and getattr(node, "condition", None) is None
            and tag_of(getattr(node, "mode", None)) == "Mandatory"
            and _zones(getattr(node, "active_zones", None)) >= _OFF_BATTLEFIELD
        ):
            return True
        if (
            unit.origin == "trigger"
            and unit.trigger_event == "changes_zone"
            and getattr(node, "destination", None) == "Graveyard"
            and getattr(node, "origin", None) is None
            and tag_of(getattr(node, "valid_card", None)) == "SelfRef"
            and any(_moves_out_of_graveyard(c.node) for c in unit.effects)
        ):
            return True
    return False


def _moves_out_of_graveyard(effect: TypedMirrorNode) -> bool:
    """A graveyard trigger's effect taking the card away: the graveyard shuffled
    into the library (Kozilek's ``ChangeZoneAll`` from it) or the card itself
    (Worldspine Wurm, the Lorwyn Incarnations: a ``ChangeZone`` of ``SelfRef``
    to the library)."""
    origin, destination = change_zone_dirs(effect)
    if destination != "Library":
        return False
    return origin == "Graveyard" or (
        tag_of(effect) == "ChangeZone"
        and tag_of(getattr(effect, "target", None)) == "SelfRef"
    )


#: The filter properties a reanimator's target is read through
#: (:func:`_reanimator_admits`): a zone, an owner, a fixed mana-value bound and the
#: ones ``reads.filter_admits`` reads. Any other (a power bound, a mana value the
#: game decides) is a bound the read can't hold the candidate to, and the
#: reanimator does not count.
_READ_PROPERTIES = frozenset(
    {"InZone", "Owned", "Cmc", "HasSupertype", "NotSupertype", "ColorCount"}
)


def _reanimator_filters(record: Mapping) -> list[tuple[object, bool]]:
    """The target filters of a reanimator's typed moves from a graveyard onto
    the battlefield, an Aura's at its ``Enchant`` filter (``AttachedTo``:
    Animate Dead), each with whether its ability runs for every player (a
    ``player_scope`` of ``All``: Exhume's "each player", whose ``ScopedPlayer``
    owner includes you). A move of the card itself (``SelfRef``), one bound to
    another reference or a tracked set (Victimize, Living Death), and one whose
    origin phase leaves unset (Puppeteer Clique's) return no add read here."""
    out: list[tuple[object, bool]] = []
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            every_player = "All" in _player_scopes(unit.node)
            for node in unit.iter_typed():
                if change_zone_dirs(node) != ("Graveyard", "Battlefield"):
                    continue
                target = getattr(node, "target", None)
                if tag_of(target) == "AttachedTo":
                    target = tree.card_enchant_filter
                if tag_of(target) in ("Typed", "Or", "And"):
                    out.append((target, every_player))
    return out


def _player_scopes(node: object) -> set[str]:
    """The ``player_scope`` tags down an ability's chain (its ``execute`` and
    ``sub_ability`` links)."""
    out: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        scope = tag_of(getattr(current, "player_scope", None))
        if scope:
            out.add(scope)
        for link in ("execute", "sub_ability"):
            child = getattr(current, link, None)
            if hasattr(child, "sub_ability"):
                stack.append(child)
    return out


def _reanimator_admits(
    filt: object, card: Mapping, *, every_player: bool = False
) -> bool:
    """Whether a reanimator's target filter takes in ``card`` from your own
    graveyard: ``reads.filter_admits`` on its types, subtypes and fixed mana value,
    an owner and a controller that include you (you, or each player under an
    ``every_player`` scope; a defending player's graveyard returns no add of
    yours: Rakshasa Debaser), and no bound the read can't hold it to."""
    from mtg_utils._card_ir.trees import object_facts

    for sub in _filter_parts(filt):
        if filter_controller(sub) not in (None, "You"):
            return False
        for prop in getattr(sub, "properties", ()) or ():
            ptag = tag_of(prop)
            if ptag not in _READ_PROPERTIES:
                return False
            owner = getattr(prop, "controller", None)
            if ptag == "Owned" and not (
                owner in (None, "You") or (owner == "ScopedPlayer" and every_player)
            ):
                return False
            if ptag == "Cmc" and tag_of(getattr(prop, "value", None)) != "Fixed":
                return False
    return filter_admits(filt, object_facts(dict(card), zone="elsewhere")) is True


def _filter_parts(filt: object) -> list[object]:
    if tag_of(filt) in ("Or", "And"):
        return [p for f in getattr(filt, "filters", ()) or () for p in _filter_parts(f)]
    return [filt]


#: A discard outlet or a loot (``discard_outlet|you``: fuel for your own
#: graveyard), one of the deck reads of a card filling its own graveyard for
#: delve (``costs.GRAVEYARD_FILL_FLOOR``).
_DISCARD_OUTLET = ("discard_outlet", "you", "")


def _mills_you(record: Mapping) -> bool:
    """Whether a card has a mill that can put your own cards into your
    graveyard (``reads.mill_reaches_you``): a self-mill, each player's, or a
    target player's, which can be you. The ``mill_makers`` signals can't say
    so: ``any`` is every mill and ``opponents`` every mill that can reach an
    opponent (Millstone reaches both)."""
    for tree in trees_for(dict(record)):
        for unit in tree.units:
            for node in unit.iter_typed():
                if tag_of(node) == "Mill" and mill_reaches_you(unit, node):
                    return True
    return False


def _graveyard_fillers(
    deck: Sequence[tuple[Mapping, int, bool]],
    emitters: Mapping[tuple[str, str, str], Collection[str]],
    commander_idents: Collection[tuple[str, str, str]],
) -> int:
    """The deck cards that fill its own graveyard: a mill that can hit you or a
    discard outlet (a loot included). A commander doing so counts as the whole
    floor at once, as R2's cheat floor counts it."""
    from mtg_utils._analysis.costs import GRAVEYARD_FILL_FLOOR

    names = set(emitters.get(_DISCARD_OUTLET, ()))
    commander = _DISCARD_OUTLET in set(commander_idents)
    for rec, _q, is_commander in deck:
        if rec.get("name", "") in names and not is_commander:
            continue
        if _mills_you(rec) or (is_commander and rec.get("name", "") in names):
            names.add(rec.get("name", ""))
            commander |= is_commander
    if commander:
        return max(len(names), GRAVEYARD_FILL_FLOOR)
    return len(names)


@dataclass
class CurveCap:
    """One deck's curve cap: ``cap`` (None: no ceiling), the card types a cheat
    puts onto the battlefield (``cheat_types``; ``"*"`` for an untyped one), and
    the target filters of each card returning creature cards to it from a
    graveyard (``reanimators``)."""

    cap: float | None
    top: float
    cheat_types: frozenset[str] = frozenset()
    reanimators: list[list[tuple[object, bool]]] = field(default_factory=list)
    memo: dict[str, CastCosts] = field(default_factory=dict)
    entries: Sequence[tuple[Mapping, int]] = ()
    library: int = 99
    graveyard_fillers: int = 0

    @classmethod
    def build(
        cls,
        deck: Sequence[tuple[Mapping, int, bool]],
        *,
        room: float | None,
        emitters: Mapping[tuple[str, str, str], Collection[str]] | None,
        commander_idents: Collection[tuple[str, str, str]] = (),
    ) -> CurveCap:
        """``deck`` is ``(record, copies, is_commander)`` per card."""
        entries = [(rec, max(1, q)) for rec, q, _cmd in deck]
        library = max(1, sum(max(1, q) for _r, q, cmd in deck if not cmd))
        out = cls(
            cap=None,
            top=0.0,
            entries=entries,
            library=library,
            graveyard_fillers=_graveyard_fillers(
                deck, emitters or {}, commander_idents
            ),
        )
        if room is None:
            return out
        tops = [
            cost
            for rec, _q, _cmd in deck
            if not is_land(dict(rec)) and (cost := out.costs(rec).top) is not None
        ]
        if not tops:
            return out  # nothing the deck casts sets a top: no ceiling
        out.top = max(tops)
        out.cap = out.top + room
        emitters = emitters or {}
        cheat = {
            subject.lower() or "*"
            for (key, scope, subject), names in emitters.items()
            if key == "cheat_into_play" and scope == "you" and len(names) >= CHEAT_FLOOR
        } | {
            subject.lower() or "*"
            for key, scope, subject in commander_idents
            if key == "cheat_into_play" and scope == "you"
        }
        out.cheat_types = frozenset(cheat)
        by_name = {rec.get("name", ""): rec for rec, _q, _cmd in deck}
        names = set(emitters.get(("creature_recursion", "you", "battlefield"), ()))
        if ("creature_recursion", "you", "battlefield") in commander_idents:
            names |= {rec.get("name", "") for rec, _q, cmd in deck if cmd}
        out.reanimators = [
            filters
            for name in sorted(names)
            if (rec := by_name.get(name)) is not None
            and (filters := _reanimator_filters(rec))
        ]
        return out

    def costs(self, card: Mapping) -> CastCosts:
        key = card.get("oracle_id") or card.get("name", "")
        if key not in self.memo:
            self.memo[key] = cast_costs(
                card,
                self.entries,
                library_size=self.library,
                graveyard_fillers=self.graveyard_fillers,
            )
        return self.memo[key]

    def returners(self, card: Mapping) -> int:
        """How many of the deck's reanimators can return ``card`` from your
        graveyard (:func:`_reanimator_admits`)."""
        return sum(
            1
            for filters in self.reanimators
            if any(_reanimator_admits(f, card, every_player=e) for f, e in filters)
        )

    def reached(self, card: Mapping) -> bool:
        """Whether the deck's cheat plan reaches ``card`` (Dan's R2, the
        coordinator's scope of 2026-11-26): a typed cheat its type, an untyped
        one any permanent card, a reanimation onto the battlefield a creature
        card it can return (any, or its own tribe's) that can be reanimated."""
        types = {t.lower() for t in split_type_line(card.get("type_line", ""))[0]}
        if types & self.cheat_types or (
            "*" in self.cheat_types and types & PERMANENT_TYPES
        ):
            return True
        if "creature" not in types or not self.reanimators:
            return False
        return self.returners(card) >= CHEAT_FLOOR and not cant_be_reanimated(card)

    def over(self, card: Mapping, spec: Mapping) -> bool:
        """Whether ``card`` costs past the cap for ``spec``'s search: never for a
        search asking for the top end itself (``cmc_min``), a card with no
        cheapest cost, or a card the cheat plan reaches."""
        if self.cap is None or "cmc_min" in spec:
            return False
        cheapest = self.costs(card).cheapest
        if cheapest is None or cheapest <= self.cap:
            return False
        return not self.reached(card)
