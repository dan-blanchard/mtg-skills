"""Project phase-rs's parsed ``card-data.json`` records into the Card IR.

phase already binds the hard part — the "for each Y" operand — as
``Ref → ObjectCount{filter}`` / ``Multiply{factor, inner}`` nodes, even when the
surrounding effect is wrapped in a ``GenericEffect``. This module walks those
trees into the synergy-shaped :mod:`mtg_utils.card_ir`, then hands off to
:func:`mtg_utils._card_ir.supplement.supplement_card` for the payoff/scope holes
phase leaves in description strings.

``project_card`` takes the list of phase face-records that share one
``scryfall_oracle_id`` (one element for a single-faced card; the front/back faces
for a DFC) so DFC faces become distinct :class:`~mtg_utils.card_ir.Face` objects
with no cross-face bleed.
"""

from __future__ import annotations

import re
from dataclasses import replace

from mtg_utils._card_ir.supplement import supplement_card
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger


def _norm(token: object) -> str:
    """Lowercase + strip non-alphanumerics, so ``DealDamage``/``deal_damage`` match."""
    return re.sub(r"[^a-z0-9]", "", str(token).lower())


def _str_tuple(value: object) -> tuple[str, ...]:
    """A JSON list field → tuple of its string items (() if absent/not a list)."""
    if not isinstance(value, list):
        return ()
    return tuple(x for x in value if isinstance(x, str))


def _as_list(value: object) -> list:
    """A JSON list field → the list (or [] if absent/not a list)."""
    return value if isinstance(value, list) else []


# ── effect.type discriminant → synergy category ───────────────────────────────
_EFFECT_CATEGORY: dict[str, str] = {
    "draw": "draw",
    "dealdamage": "damage",
    "damageall": "damage",
    "damageeachplayer": "damage",
    "token": "make_token",
    "populate": "make_token",
    "investigate": "make_token",
    "incubate": "make_token",
    "amass": "make_token",
    "conjure": "make_token",
    "manifest": "make_token",
    "manifestdread": "make_token",
    "fabricate": "make_token",
    "addcounter": "place_counter",
    "putcounter": "place_counter",
    "putcounterall": "place_counter",
    "multiplycounter": "place_counter",
    "addpendingetbcounters": "place_counter",
    "removecounter": "remove_counter",
    "movecounters": "place_counter",
    "proliferate": "proliferate",
    "mill": "mill",
    "gainlife": "gain_life",
    "loselife": "lose_life",
    "destroy": "destroy",
    "destroyall": "destroy",
    "exiletop": "exile",
    "bounce": "bounce",
    "counter": "counter_spell",
    "pump": "pump",
    "pumpall": "pump",
    "doublept": "pump",
    "doubleptall": "pump",
    "searchlibrary": "tutor",
    "mana": "ramp",
    "sacrifice": "sacrifice",
    "discard": "discard",
    "discardcard": "discard",
    "gaincontrol": "gain_control",
    "controlnextturn": "gain_control",
    "exchangecontrol": "gain_control",
    "givecontrol": "gain_control",
    "untap": "untap",
    "untapall": "untap",
    "tap": "tap",
    "tapall": "tap",
    "scry": "topdeck_select",
    "surveil": "topdeck_select",
    "dig": "topdeck_select",
    "explore": "topdeck_select",
    "fight": "fight",
}

# Effect types that defer to recursion / the supplement rather than a category.
_RECURSE = {"genericeffect"}
_OTHER = {"unimplemented", "", "runtimehandled"}

# Pump-shaped static modifications (a +X/+X is one pump, not two).
_PUMP_MODS = {"adddynamicpower", "adddynamictoughness", "addpower", "addtoughness"}

# Keyword → cast-from zone, for Card.castable_zones.
_CASTABLE_ZONE_KEYWORDS: dict[str, str] = {
    "flashback": "graveyard",
    "escape": "graveyard",
    "disturb": "graveyard",
    "jumpstart": "graveyard",
    "aftermath": "graveyard",
    "embalm": "graveyard",
    "eternalize": "graveyard",
    "encore": "graveyard",
    "retrace": "graveyard",
    "foretell": "exile",
    "forecast": "hand",
}


def project_card(records: list[dict]) -> Card:
    """Project the phase face-records sharing one oracle_id into a Card."""
    faces = tuple(_project_face(rec) for rec in records)
    oracle_id = records[0].get("scryfall_oracle_id") or ""
    name = records[0].get("name") or ""
    card = Card(
        oracle_id=oracle_id,
        name=name,
        faces=faces,
        castable_zones=_castable_zones(records),
        parse_confidence="full",  # recomputed after the supplement
    )
    card = supplement_card(card)
    return replace(card, parse_confidence=_confidence(card))


def _confidence(card: Card) -> str:
    abilities = card.all_abilities()
    has_keywords = any(f.keywords for f in card.faces)
    if not abilities and not has_keywords:
        return "unparsed"
    effects = [e for a in abilities for e in a.effects]
    # An ability with no recovered effects, or any effect still 'other', is a gap.
    if any(e.category == "other" for e in effects):
        return "partial"
    if any(not a.effects for a in abilities if a.kind != "static"):
        return "partial"
    return "full"


def _project_face(record: dict) -> Face:
    abilities: list[Ability] = []
    for ab in record.get("abilities") or []:
        abilities.append(_project_spell_or_activated(ab))
    for tr in record.get("triggers") or []:
        abilities.append(_project_trigger(tr))
    for st in record.get("static_abilities") or []:
        a = _project_top_static(st)
        if a is not None:
            abilities.append(a)
    return Face(
        name=record.get("name") or "",
        type_line=_type_line(record.get("card_type")),
        keywords=_keywords(record.get("keywords")),
        abilities=tuple(abilities),
    )


# ── ability projection ────────────────────────────────────────────────────────


def _project_spell_or_activated(ab: dict) -> Ability:
    kind = "activated" if _norm(ab.get("kind")) == "activated" else "spell"
    effects = _collect_effects(ab, ab.get("description") or "")
    return Ability(kind=kind, effects=tuple(effects))


def _project_trigger(tr: dict) -> Ability:
    trigger = Trigger(
        event=_trigger_event(tr),
        subject=_filter(tr.get("valid_card")),
        scope=_trigger_scope(tr),
    )
    effects = _collect_effects(tr.get("execute"), tr.get("description") or "")
    return Ability(kind="triggered", trigger=trigger, effects=tuple(effects))


def _project_top_static(st: dict) -> Ability | None:
    effects = _project_static_mods(st, st.get("description") or "")
    if not effects:
        return None
    return Ability(kind="static", effects=tuple(effects))


def _collect_effects(node: dict | None, default_raw: str) -> list[Effect]:
    """Walk an ability node's effect + sub_ability chain into a flat effect list."""
    if not isinstance(node, dict):
        return []
    raw = node.get("description") or default_raw
    out: list[Effect] = []
    eff = node.get("effect")
    if isinstance(eff, dict):
        out.extend(_project_effect(eff, raw))
    sub = node.get("sub_ability")
    if isinstance(sub, dict):
        out.extend(_collect_effects(sub, default_raw))
    return out


def _project_effect(eff: dict, raw: str) -> list[Effect]:
    etype = _norm(eff.get("type"))
    if etype in _RECURSE:
        out: list[Effect] = []
        for st in eff.get("static_abilities") or []:
            out.extend(_project_static_mods(st, raw))
        sub = eff.get("sub_ability")
        if isinstance(sub, dict):
            out.extend(_collect_effects(sub, raw))
        if not out:
            out.append(Effect(category="other", scope=_effect_scope(eff), raw=raw))
        return out
    category = _EFFECT_CATEGORY.get(etype)
    if category is None or etype in _OTHER:
        return [Effect(category="other", scope=_effect_scope(eff), raw=raw)]
    return [
        Effect(
            category=category,
            amount=_amount(eff),
            scope=_effect_scope(eff),
            subject=_effect_subject(eff),
            raw=raw,
        )
    ]


def _project_static_mods(st: dict, raw: str) -> list[Effect]:
    """A continuous static's modifications → effects (pump today; more in A2)."""
    affected = _filter(st.get("affected"))
    desc = st.get("description") or raw
    pump_amount: Quantity | None = None
    is_pump = False
    for m in st.get("modifications") or []:
        mt = _norm(m.get("type"))
        if mt in _PUMP_MODS:
            is_pump = True
            if pump_amount is None:
                pump_amount = _quantity(m.get("value"))
    out: list[Effect] = []
    if is_pump:
        out.append(
            Effect(
                category="pump",
                amount=pump_amount,
                scope=_controller_scope(affected),
                subject=affected,
                raw=desc,
            )
        )
    return out


# ── operand / filter projection (the load-bearing part) ───────────────────────


def _amount(eff: dict) -> Quantity | None:
    for key in ("count", "amount", "value", "number"):
        if key in eff:
            q = _quantity(eff[key])
            if q is not None:
                return q
    return None


def _effect_subject(eff: dict) -> Filter | None:
    """What the effect acts ON — the filter on a mass/typed effect (DestroyAll …)."""
    for key in ("filter", "affected", "target_filter"):
        f = _filter(eff.get(key))
        if f is not None:
            return f
    return None


def _quantity(node: object) -> Quantity | None:
    if isinstance(node, bool):  # guard: bool is an int subclass
        return None
    if isinstance(node, int):
        return Quantity(op="fixed", factor=node)
    if not isinstance(node, dict):
        return None
    t = _norm(node.get("type"))
    if t == "fixed":
        return Quantity(op="fixed", factor=_int(node.get("value"), 1))
    if t == "ref":
        return Quantity(
            op="count", factor=1, subject=_objectcount_filter(node.get("qty"))
        )
    if t == "objectcount":
        return Quantity(op="count", factor=1, subject=_filter(node.get("filter")))
    if t == "multiply":
        inner = _quantity(node.get("inner"))
        return Quantity(
            op="multiply",
            factor=_int(node.get("factor"), 1),
            subject=inner.subject if inner else None,
        )
    return None


def _objectcount_filter(qty: object) -> Filter | None:
    if isinstance(qty, dict) and _norm(qty.get("type")) == "objectcount":
        return _filter(qty.get("filter"))
    return None


def _filter(node: object) -> Filter | None:
    if not isinstance(node, dict):
        return None
    card_types = _str_tuple(node.get("type_filters"))
    subtypes = _str_tuple(node.get("subtype_filters"))
    controller = _controller(node.get("controller"))
    predicates = tuple(
        p for p in (_predicate(x) for x in _as_list(node.get("properties"))) if p
    )
    if not (card_types or subtypes or controller != "any" or predicates):
        return None
    return Filter(
        card_types=card_types,
        subtypes=subtypes,
        controller=controller,
        predicates=predicates,
    )


def _predicate(p: object) -> str:
    if not isinstance(p, dict):
        return ""
    ptype = p.get("type")
    if not ptype:
        return ""
    val = p.get("value")
    if isinstance(val, dict):
        val = val.get("value")
    return f"{ptype}:{val}" if val is not None else str(ptype)


# ── scope / controller / type helpers ─────────────────────────────────────────


def _controller(c: object) -> str:
    n = _norm(c)
    if n == "you":
        return "you"
    if "opponent" in n:
        return "opp"
    return "any"


def _controller_scope(f: Filter | None) -> str:
    return f.controller if f is not None else "any"


def _effect_scope(eff: dict) -> str:
    tgt = eff.get("target")
    if isinstance(tgt, dict):
        tt = _norm(tgt.get("type"))
        if tt == "controller":
            return "you"
        if "opponent" in tt:
            return "opp"
        if tt in ("eachplayer", "allplayers"):
            return "each"
    player = eff.get("player")
    if isinstance(player, str):
        pl = player.lower()
        if pl == "controller":
            return "you"
        if "opponent" in pl:
            return "opp"
        if pl in ("each", "all", "allplayers"):
            return "each"
    ps = eff.get("player_scope")
    if isinstance(ps, dict):
        pst = _norm(ps.get("type"))
        if "opponent" in pst:
            return "opp"
        if pst == "all":
            return "each"
    return "any"


def _trigger_event(tr: dict) -> str:
    mode = _norm(tr.get("mode"))
    if mode in ("changeszone", "changeszoneall"):
        dest = _norm(tr.get("destination"))
        origin = _norm(tr.get("origin"))
        if dest == "battlefield":
            return "etb"
        if origin == "battlefield" and dest == "graveyard":
            return "dies"
        return "leaves"
    if mode in ("damagedone", "damagedoneonce", "damagedealtonce"):
        return (
            "combat_damage"
            if _norm(tr.get("damage_kind")) == "combatonly"
            else "deals_damage"
        )
    if mode in ("spellcast", "spellcopy", "spellcastorcopy", "spellabilitycast"):
        return "cast_spell"
    if mode in (
        "attacks",
        "youattack",
        "attackersdeclared",
        "attackersdeclaredonetarget",
    ):
        return "attacks"
    if mode in ("blocks", "blockersdeclared", "becomesblocked"):
        return "blocks"
    if mode == "phase":
        ph = _norm(tr.get("phase"))
        if ph == "upkeep":
            return "upkeep"
        if ph == "end":
            return "end_step"
        if ph == "draw":
            return "draw_step"
        return "other"
    if mode in ("counteradded", "counteraddedonce", "counteraddedall"):
        return "counter_added"
    if mode == "lifegained":
        return "life_gained"
    if mode in ("lifelost", "lifelostall", "paylife"):
        return "life_lost"
    if mode in ("destroyed", "leavesbattlefield"):
        return "dies"
    if mode in ("sacrificed", "sacrificedonce"):
        return "sacrificed"
    if mode in ("taps", "tapsformana"):
        return "taps"
    if mode in ("discarded", "discardedall"):
        return "discarded"
    return "other"


def _trigger_scope(tr: dict) -> str:
    vc = tr.get("valid_card")
    if isinstance(vc, dict):
        n = _norm(vc.get("type"))
        if n == "selfref":
            return "you"
        c = _controller(vc.get("controller"))
        if c != "any":
            return c
    return "any"


def _type_line(card_type: object) -> str:
    if not isinstance(card_type, dict):
        return ""
    left = _str_tuple(card_type.get("supertypes")) + _str_tuple(
        card_type.get("core_types")
    )
    subs = _str_tuple(card_type.get("subtypes"))
    line = " ".join(left)
    if subs:
        line = f"{line} — {' '.join(subs)}".strip()
    return line.strip()


def _keywords(kws: object) -> tuple[str, ...]:
    if not isinstance(kws, list):
        return ()
    out: list[str] = []
    for kw in kws:
        if isinstance(kw, str):
            out.append(kw)
        elif isinstance(kw, dict) and kw:
            k = next(iter(kw))
            if isinstance(k, str):
                out.append(k)
    return tuple(out)


def _castable_zones(records: list[dict]) -> tuple[str, ...]:
    zones: dict[str, None] = {}
    for rec in records:
        for kw in _keywords(rec.get("keywords")):
            zone = _CASTABLE_ZONE_KEYWORDS.get(_norm(kw))
            if zone:
                zones.setdefault(zone, None)
    return tuple(zones)


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
