"""The card reads a commander need asks of a supplier: whether a card
sacrifices, mills, drains on opponents' turns, places or spends counters,
lets a creature type connect (split out of ``commander_need``)."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import TYPE_CHECKING

from mtg_utils._analysis.signal_base import Ident, ident_key
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._card_ir.creature_types import CREATURE_TYPES
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    counter_kind_any,
    damage_to_player_trigger_kind,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_owners,
    iter_cost_leaves,
    iter_typed_nodes,
    list_field,
    tag_of,
    trigger_def_event,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._analysis.need_model import (
    _card_idents,
    _type_words,
)


def _sacrifices_artifacts(card: dict) -> bool:
    """Whether a cost of the card sacrifices an artifact of yours: a Food
    token is an artifact (CR 111.10b), so Trading Post's "Sacrifice an
    artifact: Draw a card" spends Sam, Loyal Attendant's Foods — it went to
    Village Rites, which spends none (Food and Fellowship, 2026-11-02)."""
    return any(
        tag_of(leaf) == "Sacrifice"
        and "Artifact" in filter_core_types(getattr(leaf, "target", None))
        for tree in trees_for(dict(card))
        for unit in tree.units
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
    )


#: Keys whose emitters make a creature of yours die or leave (fodder and the
#: outlets that spend it) — what a dies / leaves / sacrificed trigger is fed by.
_DEATH_FEED_KEYS: frozenset[str] = frozenset(
    {"sacrifice_outlets", "edict_makers", TOKEN_MAKER, "mass_token_makers"}
)


#: Keys whose emitters let your creatures connect — what a "deals combat damage
#: to a player" trigger is fed by.
_EVASION_KEYS: frozenset[str] = frozenset(
    {"evasion_self", "team_evasion_grant", "keyword_grant_target", "lure_makers"}
)


_EVASION_KEYWORDS: frozenset[str] = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "unblockable",
        "skulk",
        "fear",
        "intimidate",
        "shadow",
    }
)


#: Trigger event → the keys of the cards that make the event happen. An event
#: not listed here opens no need (an "attacks" trigger is fed by every creature;
#: a "phase" trigger carries its condition instead).
_EVENT_MAKER_KEYS: Mapping[str, frozenset[str]] = {
    "surveil": frozenset({"topdeck_selection"}),  # subject-checked below
    "scry": frozenset({"topdeck_selection"}),
    "explored": frozenset({"explore_makers"}),
    "life_gained": frozenset({"lifegain_makers"}),
    "life_lost": frozenset({"lifeloss_makers", "direct_damage"}),
    "discarded": frozenset({"discard_makers", "discard_outlet"}),
    "sacrificed": _DEATH_FEED_KEYS,
    "exploited": _DEATH_FEED_KEYS,
    "dies": _DEATH_FEED_KEYS,
    "leaves": _DEATH_FEED_KEYS | frozenset({"blink_flicker"}),
    "counter_added": frozenset(
        {"plus_one_makers", "any_counter_makers", "proliferate_makers"}
    ),
    "drawn": frozenset(
        {"card_draw_engine", "cantrip", "draw_for_each", "activated_draw"}
    ),
    "deals_damage": _EVASION_KEYS,
    "taps": frozenset({"tapper_engine", "untap_engine"}),
    "rolled_die": frozenset({"dice_makers"}),
    "cast_spell": frozenset(),  # the filter's types decide (below)
    "enters": frozenset(),  # the filter's types decide (below)
    "changes_zone": frozenset(),  # origin / destination decide (below)
    "investigated": frozenset({"clue_makers"}),
    "energy_paid": frozenset({"energy_makers"}),
}


#: The mana value up to which a spell is "cheap" for a commander counting
#: spells per turn (the ``second_spell_matters`` payoff's line).
CHEAP_SPELL_MV = 2


#: The layouts whose halves are cast one at a time: on the stack only the half
#: being cast exists (CR 709.3b), though the card's mana value elsewhere is the
#: two combined (CR 709.4).
_HALF_CAST_LAYOUTS = frozenset({"split", "aftermath"})


def _cost_string_value(cost: str) -> int:
    """The mana value of a printed mana cost string (CR 202.3): a number counts
    its value, {X} counts 0 (CR 202.3e), a monocolored hybrid {2/W} counts 2
    (CR 202.3f), any other symbol 1."""
    total = 0
    for sym in re.findall(r"\{([^}]*)\}", cost or ""):
        if sym.isdigit():
            total += int(sym)
        elif sym == "X":
            continue
        elif sym.split("/", 1)[0].isdigit():
            total += int(sym.split("/", 1)[0])
        else:
            total += 1
    return total


def _mana_value_reaches(card: Mapping, floor: int) -> bool:
    """Whether the card's spell can have mana value ``floor`` or more: its
    printed mana value (CR 202.3), or an {X} in its cost, since X is the number
    chosen while the spell is on the stack (CR 202.3e). A split or aftermath
    card is cast one half at a time (CR 709.3b), so its biggest half counts,
    not the two combined: Commit // Memory casts at 4 or 6, never 10."""
    if card.get("layout") in _HALF_CAST_LAYOUTS and card.get("card_faces"):
        if (
            max(
                _cost_string_value(f.get("mana_cost") or "") for f in card["card_faces"]
            )
            >= floor
        ):
            return True
    elif float(card.get("cmc") or 0) >= floor:
        return True
    return any(
        "X" in (face.get("mana_cost") or "")
        for face in card.get("card_faces") or [card]
    )


def _cheap_spell(card: Mapping) -> bool:
    return float(card.get("cmc") or 0) <= CHEAP_SPELL_MV and bool(
        _type_words(card) & {"instant", "sorcery"}
    )


def _sacrifices_a_creature(unit_node: object) -> bool:
    """Whether the unit's own cost sacrifices a creature ("{2}, {T}, Sacrifice
    another creature:" — Dina, Essence Brewer)."""
    cost = getattr(unit_node, "cost", None)
    return _present(cost) and any(
        tag_of(n) == "Sacrifice"
        and "Creature" in filter_core_types(getattr(n, "target", None))
        for n in iter_typed_nodes(cost)
    )


#: The keywords a permanent enters with counters of a kind under (CR
#: 702.63a: vanishing's "This permanent enters with N time counters on it").
_ENTERS_WITH_COUNTERS: Mapping[str, frozenset[str]] = {
    "TIME": frozenset({"Vanishing"}),
}


def _has_x_cost(card: dict) -> bool:
    """Whether a face of the card has {X} in its mana cost (CR 107.3)."""
    faces = card.get("card_faces") or [card]
    return any("{X}" in (f.get("mana_cost") or "") for f in faces)


def _sacrifices_lands(card: dict) -> bool:
    """Whether the card sacrifices a land of yours, by cost or effect: a
    sacrifice of lands or of any permanent (God-Eternal Bontu's "sacrifice
    any number of other permanents" can pay with lands for Hearthhull, the
    Worldseed's "Whenever you sacrifice a land" — World Shaper, 2026-11-02).
    Not an opponent's (an edict)."""
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            nodes = list(iter_cost_leaves(getattr(unit.node, "cost", None)))
            nodes += [c.node for c in unit.effects]
            for n in nodes:
                if tag_of(n) != "Sacrifice":
                    continue
                target = getattr(n, "target", None)
                if not _present(target) or filter_controller(target) not in (
                    None,
                    "You",
                ):
                    continue
                if {"Land", "Permanent"} & set(
                    filter_core_types(target)
                ) and "Land" not in filter_non_types(target):
                    return True
    return False


def _takes_from_your_graveyard(card: dict) -> bool:
    """Whether an effect of the card moves a card out of a graveyard that may
    be yours: Quintorius, Loremaster's "exile target noncreature, nonland
    card from your graveyard" each end step, Deathrite Shaman's "from a
    graveyard" — what Quintorius, History Chaser's "Whenever one or more
    cards leave your graveyard" is fed by (Lorehold Spirit, 2026-11-02). Not
    one limited to an opponent's graveyard."""
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            for c in unit.effects:
                if c.concept != "change_zone":
                    continue
                if getattr(c.node, "origin", None) != "Graveyard":
                    continue
                target = getattr(c.node, "target", None)
                owners = filter_owners(target) if _present(target) else [None]
                if any(o != "Opponent" for o in owners):
                    return True
    return False


def _holds_counters(kind: str) -> Callable[[dict], bool]:
    """Whether a card puts counters of ``kind`` on a permanent, itself
    included (The Moment's upkeep time counter), or enters with them
    (:data:`_ENTERS_WITH_COUNTERS`)."""

    def holds(card: dict) -> bool:
        if set(card.get("keywords") or ()) & _ENTERS_WITH_COUNTERS.get(
            kind, frozenset()
        ):
            return True
        return any(
            tag_of(n) in ("PutCounter", "PutCounterAll") and counter_kind_any(n) == kind
            for tree in trees_for(dict(card))
            for unit in tree.units
            for n in unit.iter_typed()
        )

    return holds


def _places_counters(kind: str) -> Callable[[dict], bool]:
    """Whether a card puts counters of ``kind`` on a permanent other than
    itself (Coretapper's "Put a charge counter on target artifact"). One that
    charges only itself (Golem Foundry) spends its own."""

    def places(card: dict) -> bool:
        return any(
            tag_of(n) == "PutCounter"
            and counter_kind_any(n) == kind
            and tag_of(getattr(n, "target", None)) != "SelfRef"
            for tree in trees_for(dict(card))
            for unit in tree.units
            for n in unit.iter_typed()
        )

    return places


def _spends_counters(kind: str) -> Callable[[dict], bool]:
    """Whether a card removes counters of ``kind`` from itself to pay a cost
    (Titan Forge's "Remove three charge counters from this artifact"), or
    counters of any kind (Gavel of the Righteous' "Equip—Pay {3} or remove a
    counter from this Equipment": Inspirit's charge counters pay it too)."""

    def spends(card: dict) -> bool:
        return any(
            tag_of(leaf) == "RemoveCounter" and counter_kind_any(leaf) in (kind, "ANY")
            for tree in trees_for(dict(card))
            for unit in tree.units
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
        )

    return spends


#: What a deck whose commander turns its permanents into attackers wants for
#: them: team pumps and anthems, team protection, and the evasion grants a
#: "deals combat damage to a player" trigger already asks for.
_ATTACKER_SUPPORT_KEYS: frozenset[str] = frozenset(
    {"team_buff", "anthem_static", "board_protection", "team_evasion_grant"}
)


def _supports_attackers(card: dict) -> bool:
    """A card with one of :data:`_ATTACKER_SUPPORT_KEYS` that is not an
    Equipment: a piece of gear helps one creature at a time (Hammer of Nazahn
    led Bello's page as "support" for its indestructible), where the deck
    animates a board."""
    if "equipment" in _type_words(card):
        return False
    return any(ident_key(i) in _ATTACKER_SUPPORT_KEYS for i in _card_idents(card))


#: The CR's creature types (CR 205.3m), lower-cased: what a tribal payoff
#: names.
_CREATURE_TYPE_WORDS: frozenset[str] = frozenset(t.lower() for t in CREATURE_TYPES)


#: The keys of a payoff for a creature type: a typed anthem, a choose-a-type
#: card, a multi-type anthem.
_TYPAL_PAYOFF_KEYS: frozenset[str] = frozenset(
    {"anthem_static", "chosen_type_matters", "typed_anthem_multi"}
)


def _typal_payoff(card: dict) -> bool:
    """A card that pays off a creature type: a lord or typed anthem
    (``anthem_static|you|Illusion``), a tribal trigger or reference to a
    creature type of yours (``subtype_ref|you|Sliver``), a choose-a-type card
    (Roaming Throne, Coat of Arms). A reference to a gear or land type is not
    one."""
    for ident in _card_idents(card, membership=False):
        key, _scope, subject = Ident.parse(ident)
        if key in _TYPAL_PAYOFF_KEYS and (key != "anthem_static" or subject):
            return True
        if key == "subtype_ref" and (
            subject == "shared" or subject.lower() in _CREATURE_TYPE_WORDS
        ):
            return True  # a named type, or a shared one (Coat of Arms)
    return False


def typal_payoff_for(card: Mapping, kinds: Collection[str]) -> bool:
    """A card that pays off one of the creature types ``kinds`` (lower-cased):
    a lord or typed anthem of it, a trigger or reference to it among yours, or
    a choose-a-type card (Vanquisher's Banner, Icon of Ancestry, Roaming
    Throne). The tuner's tribe slots keep these beside the tribe's own members
    (``swaps.cut_candidates``' ``tribe_member``): Icon of Ancestry left Sliver
    Swarm for a board wipe, Vanquisher's Banner Cavalry Charge for a Knight
    (2026-11-02)."""
    if not kinds:
        return False
    wanted = {k.lower() for k in kinds}
    idents = _card_idents(card, membership=False)
    keys = {ident_key(i) for i in idents}
    pays_off = bool(keys - _RIDER_KEYS)
    for ident in idents:
        key, _scope, subject = Ident.parse(ident)
        if key == "chosen_type_matters":
            return True
        if key == "anthem_static" and subject.lower() in wanted:
            return True
        if key == "subtype_ref" and (
            subject == "shared" or (subject.lower() in wanted and pays_off)
        ):
            return True
    return False


#: The keys a tribal reference may sit beside and still be a rider on another
#: job rather than a payoff: the card's own body and membership, a mana
#: ability, a graveyard side effect. A reference beside nothing else is a
#: rider — Drover of the Mighty's and Ixalli's Lorekeeper's Dinosaur bonuses
#: on mana dorks held Veloci-Ramp-Tor's ramp to Dinosaur cards and cost it
#: Nature's Lore and Birds of Paradise (2026-11-02); beside anything else it
#: pays the tribe off — a lord's anthem, Galerider Sliver's grant, The First
#: Sliver's cascade, Sliver Overlord's tutor (an allow-list of payoff keys
#: dropped those three, and Sliver Swarm four guide adds).
_RIDER_KEYS: frozenset[str] = frozenset(
    {
        "subtype_ref",
        "type_matters",
        "ramp",
        "permanent_etb",
        "self_etb_payload",
        "self_pump",
        "self_counter_grow",
        "evasion_self",
        "keyword_bodies",
        "graveyard_makers",
        "graveyard_matters",
        "sacrifice_outlets",
        "activated_ability",
    }
)


def _grants_all_creature_types_node(node: object) -> bool:
    """Whether a static's ``modifications`` make the affected permanents every
    creature type (``AddAllCreatureTypes``)."""
    return any(
        tag_of(mod) == "AddAllCreatureTypes"
        for mod in getattr(node, "modifications", None) or ()
    )


def grants_all_creature_types(card: Mapping) -> bool:
    """Whether ``card`` has a static making permanents every creature type
    (Omo, Queen of Vesuva's everything counters; Maskwood Nexus): under such a
    commander every tribe is one the deck fields, so no tribal payoff is dead
    for want of one (``swaps.deck_profile``)."""
    return any(
        unit.origin == "static" and _grants_all_creature_types_node(unit.node)
        for tree in trees_for(dict(card))
        for unit in tree.units
    )


def _animates_attackers(node: object) -> bool:
    """Whether a static's ``modifications`` make the affected permanents
    creatures (``AddType`` Creature) and send them into combat: a granted
    trigger on combat damage (``GrantTrigger`` with ``DamageDone``) or haste
    (``AddKeyword``)."""
    mods = getattr(node, "modifications", None) or ()
    becomes_creature = False
    attacks = False
    for mod in mods:
        tag = tag_of(mod)
        if tag == "AddType" and getattr(mod, "core_type", None) == "Creature":
            becomes_creature = True
        elif (
            tag == "AddKeyword" and str(getattr(mod, "keyword", "")).lower() == "haste"
        ):
            attacks = True
        elif tag == "GrantTrigger":
            trig = getattr(mod, "trigger", None)
            if getattr(trig, "mode", None) == "DamageDone":
                attacks = True
    return becomes_creature and attacks


def _puts_minus_counters(card: dict) -> bool:
    """Whether a card puts -1/-1 counters on creatures: wither or infect (its
    damage to a creature is -1/-1 counters, CR 702.80a / 702.90c), or a
    -1/-1 counter effect of its own."""
    for tree in trees_for(dict(card)):
        if {k.lower() for k in tree.card_keywords} & {"wither", "infect"}:
            return True
        for unit in tree.units:
            for n in unit.iter_typed():
                if (
                    tag_of(n) in ("PutCounter", "PutCounterAll")
                    and counter_kind_any(n) == "M1M1"
                ) or tag_of(n) == "BlightEffect":
                    # To blight N is to put N -1/-1 counters on a creature
                    # you control (CR 701.68a).
                    return True
    return False


def _drains_on_opponents_turns(card: dict) -> bool:
    """A life-loss or damage maker whose trigger watches what other players do:
    an ``opponent_*`` watcher key, a tax, a payoff lane scoped past "you"
    (``*_matters|opponents|`` / ``|each|`` / ``|any|``), a watcher ident scoped
    to opponents or every player (Blood Seeker's ``creature_etb|opponents|``,
    Stormfist Crusader's ``group_hug_draw|each|``), or on the card's own tree a
    trigger on a player action by opponents or every player
    (:data:`_PLAYER_ACTION_EVENTS` at ``crosswalk.trigger_scope`` past "you":
    Harsh Mentor's "whenever an opponent activates an ability", Kaervek's
    "whenever an opponent casts a spell") or on a permanent an opponent
    controls (Blood Seeker's "enters under an opponent's control"). Not the
    card's own attack or cast (Myr Battlesphere, Crypt Ghast's extort), nor a
    removal spell's "any" scope (Toxic Deluge) — the first widening admitted
    them (2026-11-01)."""
    idents = _card_idents(card)
    keys = {ident_key(i) for i in idents}
    if not keys & _EVENT_MAKER_KEYS["life_lost"]:
        return False
    if _drains_only_on_own_combat(card):
        return False
    for ident in idents:
        key, scope, _subject = Ident.parse(ident)
        if key.startswith("opponent_") or key == "stax_taxes":
            return True
        if key in _OWN_COMBAT_KEYS:
            continue  # the card's own attack connecting is your turn's work
        if key.endswith("_matters") and scope in ("opponents", "each", "any"):
            return True
        if key not in _EVENT_MAKER_KEYS["life_lost"] and scope in ("opponents", "each"):
            return True
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            if unit.origin != "trigger" or not isinstance(unit.node, TypedMirrorNode):
                continue
            event = trigger_def_event(unit.node)
            if event in _PLAYER_ACTION_EVENTS and trigger_scope(unit.node) in (
                "opponents",
                "each",
            ):
                return True
            valid = getattr(unit.node, "valid_card", None)
            if _present(valid) and filter_controller(valid) == "Opponent":
                return True
    return False


def _evasion_for(types: frozenset[str], card: dict) -> bool:
    """Whether ``card`` lets a creature of ``types`` connect: an evasion grant
    to your team or a target, a lure, or an evasive body of one of them."""
    idents = _card_idents(card)
    keys = {ident_key(i) for i in idents}
    if keys & {"team_evasion_grant", "lure_makers"}:
        return True
    if any(f"keyword_grant_target|you|{k}" in idents for k in _EVASION_KEYWORDS):
        return True
    evasive = "evasion_self" in keys or any(
        f"keyword_bodies|you|{k}" in idents for k in _EVASION_KEYWORDS
    )
    if not evasive:
        return False
    words = _type_words(card)
    if "creature" not in words:
        # A noncreature card's evasion is a grant: Rogue's Passage,
        # Whispersilk Cloak's equipped creature.
        return True
    # A changeling is every creature type (CR 702.73a).
    keywords = {str(k).lower() for k in card.get("keywords") or ()}
    return "changeling" in keywords or bool({t.lower() for t in types} & words)


def _drains_only_on_own_combat(card: dict) -> bool:
    """Whether every life loss ``card`` makes rides its own combat damage to a
    player: Rankle, Master of Pranks's "each player loses 1 life" on "Whenever
    Rankle deals combat damage to a player". Only an unblocked attacking
    creature assigns combat damage to a player (CR 510.1b), and only the active
    player's creatures attack (CR 506.2), so it is your turn's work — its
    riders' ``opponent_discard|each|`` read it as an opponents'-turn drain, and
    Valgavoth's Spiteful Visions went to it (Endless Punishment, 2026-11-02)."""
    loss_units = [
        unit
        for tree in trees_for(dict(card))
        for unit in tree.units
        if any(c.concept in ("lose_life", "deal_damage") for c in unit.effects)
    ]
    return bool(loss_units) and all(
        unit.origin == "trigger"
        and damage_to_player_trigger_kind(unit.node) == "CombatOnly"
        for unit in loss_units
    )


#: Payoff keys for the card's OWN combat damage to opponents (Sword of Fire and
#: Ice, Rankle): scoped "opponents" by the victim, fired on your turn.
_OWN_COMBAT_KEYS: frozenset[str] = frozenset(
    {"combat_damage_matters", "combat_damage_to_opp", "damage_to_opp_matters"}
)


#: The trigger events that are a player's own action (``trigger_def_event``):
#: one by an opponent happens on their turn, as a rule.
_PLAYER_ACTION_EVENTS: frozenset[str] = frozenset(
    {
        "cast_spell",
        "abilityactivated",
        "drawn",
        "discarded",
        "life_gained",
        "surveil",
        "scry",
        "explored",
        "investigated",
        "sacrificed",
        "taps",
        "tapsformana",
        "phase",
    }
)


#: The keywords a "whenever ~ deals combat damage to a player" commander wants
#: put on itself: evasion to connect, and double strike, with which it deals
#: combat damage in both combat damage steps (CR 702.4b) and so triggers twice.
_OWN_DAMAGE_KEYWORDS: frozenset[str] = _EVASION_KEYWORDS | {"double strike"}


def _grants_the_commander(card: dict) -> bool:
    """Whether the card gives your commander one of :data:`_OWN_DAMAGE_KEYWORDS`
    ("Commander creatures you own have 'Whenever this creature attacks a player,
    … this creature can't be blocked this turn'" — Sword Coast Sailor; "… it
    gains double strike" — Flaming Fist)."""
    idents = _card_idents(card)
    if "commander_matters|you|" not in idents:
        return False
    return any(
        f"{prefix}|you|{kw}" in idents
        for kw in _OWN_DAMAGE_KEYWORDS
        for prefix in ("keyword_bodies", "evasion_self")
    )


def _makes_tokens_of(words: frozenset[str]) -> Callable[[dict], bool]:
    """Whether a card makes a token of one of the card types ``words``: a
    ``Token`` effect whose types name it, or a token copy that adds the type
    (``CopyTokenOf`` with an ``AddType``)."""
    wanted = {w.capitalize() for w in words}

    def makes(card: dict) -> bool:
        for tree in trees_for(dict(card)):
            for unit in tree.units:
                for n in unit.iter_typed():
                    tag = tag_of(n)
                    if tag == "Token" and wanted & set(list_field(n, "types")):
                        return True
                    if tag == "CopyTokenOf" and any(
                        tag_of(m) == "AddType"
                        and getattr(m, "core_type", None) in wanted
                        for m in list_field(n, "additional_modifications")
                    ):
                        return True
        return False

    return makes


def _stat(card: Mapping, name: str) -> int:
    faces = card.get("card_faces") or [card]
    best = 0
    for face in faces:
        raw = face.get(name)
        try:
            best = max(best, int(str(raw).replace("*", "0") or 0))
        except ValueError:
            continue
    return best


def _lifelink_only(trees: Sequence[ConceptTree]) -> bool:
    """Whether a commander's lifegain is only its own lifelink: the keyword,
    and no effect of its that gains life."""
    lifelink = any(
        kw.lower() == "lifelink" for tree in trees for kw in tree.card_keywords
    )
    return lifelink and not any(
        tag_of(n) == "GainLife"
        for tree in trees
        for unit in tree.units
        for n in unit.iter_typed()
    )
