"""Where a perpetual power/toughness change lands: the rules both readers share.

"Perpetually" is an Arena-only (Alchemy) mechanic outside the Comprehensive
Rules (the repo's digital supplement, DD1.1: "A perpetual effect modifies a
specific card permanently for the rest of the game, regardless of zone
changes"); counting such a change as a pump only on a creature on the battlefield is
the lane's own decision (2026-11-25). Two readers ask where a change lands:
``crosswalk.perpetual`` over the typed tree (which ``ApplyPerpetual`` is a pump)
and ``misparsed_shapes`` over the raw face records (which parked change to
write as one). Each pulls the tags and zones out of its own representation and
asks the same questions here, so the two cannot drift. Where a change lands
off the battlefield (:func:`earlier_zone`, :func:`trigger_zone`) is the
``card_boost`` read's (``crosswalk.perpetual.card_boost_zones``). Plain values only:
nothing here reads the mirror, a tree or a record.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

#: Where a perpetual change lands: the card itself on the battlefield, the card
#: itself an earlier effect of the chain put onto the battlefield ("Return ~
#: from your graveyard to the battlefield tapped. It perpetually gets +1/+1" —
#: Vladimir and Godfrey), another creature (or a population of them) on the
#: battlefield, a card that is not on the battlefield, or a recipient the
#: structure doesn't tell.
Recipient = Literal["self", "returned", "battlefield", "off", "unknown"]

#: Trigger modes whose watched object is a permanent on the battlefield (an
#: attacker, a blocker, a crewing creature, the crewed Vehicle).
BATTLEFIELD_EVENT_MODES = frozenset(
    {"Attacks", "Blocks", "BecomesBlocked", "Crews", "EntersOrAttacks"}
)
#: Effects that leave their target where it is: a creature they act on is still
#: on the battlefield for the next effect of the chain (Freyalise, Skyshroud
#: Partisan's untap).
LEAVES_IT_TAGS = frozenset(
    {"TargetOnly", "SetTapState", "Pump", "PutCounter", "GainControl"}
)
#: Mass effects over a population of permanents that stays on the battlefield
#: (Chaos Balor's "deals 2 damage to each creature target player controls").
MASS_IN_PLACE_TAGS = frozenset(
    {"DamageAll", "PumpAll", "TapAll", "UntapAll", "PutCounterAll"}
)
#: Effects whose object is a card outside the battlefield, or one they take off
#: it.
OFF_BATTLEFIELD_TAGS = frozenset(
    {
        "Seek",
        "Conjure",
        "DraftFromSpellbook",
        "Draw",
        "Bounce",
        "Destroy",
        "Sacrifice",
        "Discard",
        "Mill",
    }
)
_ZONE_MOVES = frozenset({"ChangeZone", "ChangeZoneAll"})


def names_another_zone(zones: Iterable[str]) -> bool:
    """A filter's ``InZone`` zones name somewhere other than the battlefield."""
    found = set(zones)
    return bool(found) and "Battlefield" not in found


def card_by_zones(zones: Iterable[str]) -> Recipient:
    """Where the card itself is when its ability, working from ``zones``
    (``reads.ability_zones``: a trigger's zones, an activation's), resolves: on
    the battlefield when none is named or the battlefield is among them."""
    found = set(zones)
    return "self" if not found or "Battlefield" in found else "off"


def trigger_object(
    mode: str | None, destination: str | None, *, watches_self: bool
) -> Recipient:
    """Where a trigger's object is (``ParentTarget`` with no earlier effect, or
    ``TriggeringSource``): a creature entering the battlefield (the card itself
    when the trigger watches only it), an attacker, a blocker, a crewing
    creature; not a spell cast (Rothga, Bonded Engulfer) or a card that died
    (Tomakul Phoenix)."""
    if mode in ("ChangesZone", "ChangesZoneAll"):
        if destination != "Battlefield":
            return "off"
        return "self" if watches_self else "battlefield"
    if mode == "SpellCast":
        return "off"
    if mode in BATTLEFIELD_EVENT_MODES:
        return "battlefield"
    return "unknown"


def earlier_object(
    tag: str | None,
    *,
    destination: str | None,
    choice_zone: str | None,
    target_typed: bool,
    target_zones: Iterable[str],
) -> Recipient:
    """Where the object the earlier effect of the chain acted on is
    (``ParentTarget``'s antecedent): a card put onto the battlefield, a target
    an effect left there; not a card chosen from a hand (Veteran Charger),
    sought (Hardened Bonds) or returned to a hand (Candela, Aegis of Adagia).
    The card itself put back onto the battlefield is the caller's to tell."""
    if tag in _ZONE_MOVES:
        return "battlefield" if destination == "Battlefield" else "off"
    if tag == "ChooseFromZone":
        return "battlefield" if choice_zone == "Battlefield" else "off"
    if tag in OFF_BATTLEFIELD_TAGS:
        return "off"
    if tag in LEAVES_IT_TAGS and target_typed:
        return "off" if names_another_zone(target_zones) else "battlefield"
    return "unknown"


def tracked_population(
    tag: str | None, *, target_typed: bool, target_zones: Iterable[str]
) -> Recipient:
    """Where the population the earlier mass effect acted on is (``TrackedSet``,
    "those creatures")."""
    if tag in MASS_IN_PLACE_TAGS and target_typed:
        return "off" if names_another_zone(target_zones) else "battlefield"
    if tag in OFF_BATTLEFIELD_TAGS:
        return "off"
    return "unknown"


#: The zone a card is put into by an effect that takes it off the battlefield
#: or acts on it outside it, where the effect itself doesn't name one: a card
#: sought, drawn or returned to a hand is in a hand; one destroyed, sacrificed,
#: discarded or milled is in a graveyard.
_TAG_ZONES = {
    "Seek": "Hand",
    "Draw": "Hand",
    "DraftFromSpellbook": "Hand",
    "Bounce": "Hand",
    "Destroy": "Graveyard",
    "Sacrifice": "Graveyard",
    "Discard": "Graveyard",
    "Mill": "Graveyard",
}


#: What a parked perpetual raise on cards outside the battlefield lands on,
#: beside a zone (``ConceptNode.perpetual_cards``): every card you own, in any
#: zone, and a card an earlier instruction named ("it", "that card", "the
#: duplicate"), which the ``card_boost`` read locates by the chain's structure.
EVERYWHERE = "Everywhere"
EARLIER = "Earlier"
#: The residues a perpetual change is parked as: the clause, and the "it" whose
#: subject phase couldn't bind.
PERPETUAL_RESIDUES = frozenset({"perpetual_modify_pt", "unbound_subject"})


def one_other_zone(zones: Iterable[str]) -> str | None:
    """The one zone ``zones`` names, when it is not the battlefield."""
    found = set(zones)
    return next(iter(found)) if len(found) == 1 and "Battlefield" not in found else None


def earlier_zone(
    tag: str | None,
    *,
    destination: str | None,
    choice_zone: str | None,
    target_zones: Iterable[str],
) -> str | None:
    """The zone outside the battlefield the object the earlier effect of the
    chain acted on is in (``ParentTarget``'s antecedent, :func:`earlier_object`
    "off"): a card chosen from a hand (Veteran Charger), put into one
    (Giant Regrowth), sought (Hardened Bonds), returned to one (Candela, Aegis
    of Adagia), conjured into a library (Goblin Morale Sergeant), or a target
    its filter places in a graveyard (Richlau, Headmaster). ``None`` on the
    battlefield, or where the structure doesn't tell."""
    if destination and destination != "Battlefield":
        return destination
    if tag == "ChooseFromZone":
        return choice_zone if choice_zone and choice_zone != "Battlefield" else None
    if tag in _TAG_ZONES:
        return _TAG_ZONES[tag]
    return one_other_zone(target_zones)


def trigger_zone(mode: str | None, destination: str | None) -> str | None:
    """The zone a trigger's object is in outside the battlefield
    (:func:`trigger_object` "off"): the zone a card was put into (Volatile
    Rift's "a creature card is put into your hand"), the stack for a spell cast
    (Rothga, Bonded Engulfer's "When you cast a creature spell, it perpetually
    gets …")."""
    if mode in ("ChangesZone", "ChangesZoneAll"):
        return destination if destination and destination != "Battlefield" else None
    return "Stack" if mode == "SpellCast" else None


#: Effects that put a card into a library without naming a destination.
_TO_LIBRARY_TAGS = frozenset({"PutAtLibraryPosition", "PutOnTopOrBottom"})


def later_zone(tag: str | None, destination: str | None) -> str | None:
    """The zone a later effect of the chain moves the object it names into
    (``ParentTarget``), outside the battlefield: Richlau, Headmaster's "Put it
    into your library second from the top" after the change. ``None`` for an
    effect that moves nothing."""
    if tag in ("ChangeZone", "ChangeZoneAll"):
        return destination if destination and destination != "Battlefield" else None
    return "Library" if tag in _TO_LIBRARY_TAGS else None


def population_pump_is_yours(controller: str | None, *, raises: bool) -> bool:
    """Whether a change that raises a population's power or toughness can be a
    pump of yours: not when only your opponents control the population ("each
    creature your opponents control"). A chosen player's ("each creature target
    player controls" — Chaos Balor, whose player can be you) or anyone's can."""
    return not (raises and controller == "Opponent")
