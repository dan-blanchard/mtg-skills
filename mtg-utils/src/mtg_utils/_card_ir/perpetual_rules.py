"""Where a perpetual power/toughness change lands: the rules both readers share.

"Perpetually" is an Arena-only (Alchemy) mechanic with no Comprehensive Rules
entry; counting such a change as a pump only on a creature on the battlefield is
the lane's own decision (2026-11-25). Two readers ask where a change lands:
``crosswalk.perpetual`` over the typed tree (which ``ApplyPerpetual`` is a pump)
and ``misparsed_shapes`` over the raw face records (which parked change to
write as one). Each pulls the tags and zones out of its own representation and
asks the same questions here, so the two cannot drift. Plain values only:
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


def population_pump_is_yours(controller: str | None, *, raises: bool) -> bool:
    """Whether a change that raises a population's power or toughness can be a
    pump of yours: not when only your opponents control the population ("each
    creature your opponents control"). A chosen player's ("each creature target
    player controls" — Chaos Balor, whose player can be you) or anyone's can."""
    return not (raises and controller == "Opponent")
