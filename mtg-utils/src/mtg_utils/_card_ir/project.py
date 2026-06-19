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
    "movecounters": "counter_move",  # Batch 7 — move counters between objects
    "proliferate": "proliferate",
    "mill": "mill",
    "gainlife": "gain_life",
    "loselife": "lose_life",
    "destroy": "destroy",
    "destroyall": "destroy",
    "exiletop": "exile",
    "bounce": "bounce",
    "counter": "counter_spell",
    # A single-target pump is distinct from a mass pump: only the mass form (and
    # static anthems, also category "pump") is the go-wide creatures_matter payoff;
    # a single "pump target creature you control" must not read as go-wide.
    "pump": "pump_target",
    "pumpall": "pump",
    "doublept": "pump_target",
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
    # Batch P — phase-native mechanic effects → their own categories.
    "becomemonarch": "monarch",
    "suspect": "suspect",
    "startyourengines": "speed",
    "increasespeed": "speed",
    "station": "station",
    "ventureinto": "venture",
    "ventureintodungeon": "venture",
    "takesinitiative": "venture",
    "connive": "connive",
    "preventdamage": "damage_prevention",
    "detain": "detain",
    "animate": "animate",
    "seek": "seek",
    "becomecopy": "clone",  # Batch 10 — "becomes a copy of" (clone synergy)
    "copyspell": "spell_copy",  # "copy target spell" (Twincast) — distinct from clone
    # Batch 0 — v0.1.60 structured effect types that previously fell to "other".
    "flipcoin": "coin_flip",
    "flipcoins": "coin_flip",
    "endtheturn": "end_the_turn",
    "extraturn": "extra_turn",
    "setlifetotal": "set_life",
    "exchangelifetotals": "set_life",
    "revealhand": "reveal_hand",
    "regenerate": "regenerate",
    "ringtemptsyou": "ring_tempt",
    "gainenergy": "energy",
    "phaseout": "phasing",
    "phasein": "phasing",
    "rolldie": "roll_die",
    # putontoporbottom / putatlibraryposition → topdeck_stack, but the WHERE
    # (top/bottom/nth) is load-bearing for the lane, so they get a dedicated
    # position-carrying handler in _single_effect (not this flat category map).
    "revealuntil": "dig_until",
    "exilefromtopuntil": "dig_until",
    "setcardtypes": "type_change",  # Batch 14 — sets/changes an object's types
    "goadall": "goad_all",  # Batch 14 — mass goad
}

# Batch 14 — AdditionalPhase.phase → the extra-phase category (distinct lanes).
_EXTRA_PHASE: dict[str, str] = {
    "begincombat": "extra_combat",
    "combat": "extra_combat",
    "upkeep": "extra_upkeep",
    "draw": "extra_draw",
    "drawstep": "extra_draw",
    "end": "extra_end",
    "endstep": "extra_end",
}

# Effect types that defer to recursion / the supplement rather than a category.
_RECURSE = {"genericeffect"}
_OTHER = {"unimplemented", "", "runtimehandled"}

# Pump-shaped static modifications (a +X/+X is one pump, not two).
_PUMP_MODS = {"adddynamicpower", "adddynamictoughness", "addpower", "addtoughness"}

# Card types, to split a made token's bare-string ``types`` list (which mixes the
# card type with subtypes) into card_types vs subtypes.
_CARD_TYPES = frozenset(
    {
        "Creature",
        "Artifact",
        "Enchantment",
        "Land",
        "Planeswalker",
        "Battle",
        "Instant",
        "Sorcery",
        "Tribal",
        "Kindred",
    }
)

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
        many_copies=_allows_many_copies(records[0]),
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
    for rep in record.get("replacements") or []:
        a = _project_replacement(rep)
        if a is not None:
            abilities.append(a)
    return Face(
        name=record.get("name") or "",
        type_line=_type_line(record.get("card_type")),
        keywords=_keywords(record.get("keywords")),
        abilities=tuple(abilities),
    )


# ── ability projection ────────────────────────────────────────────────────────


# Cost-type discriminants we surface on Ability.cost (the activation cost shape:
# a sacrifice outlet, a tap ability, a discard/life/counter cost, ...).
_COST_TYPES = frozenset(
    {
        "sacrifice",
        "tap",
        "untap",
        "discard",
        "paylife",
        "exile",
        "removecounter",
        "mana",
        "return",
        "reveal",
        "mill",
    }
)


def _cost_string(cost: object) -> str | None:
    """Normalized, comma-joined activation cost types (e.g. "sacrifice", "tap")."""
    seen: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            t = _norm(node.get("type"))
            if t == "sacrifice":
                # A sac OUTLET sacrifices fodder; "sacrifice this" (SelfRef) is a
                # self-sac (Fling-style), not a sac-matters outlet.
                tgt = node.get("target")
                self_sac = isinstance(tgt, dict) and _norm(tgt.get("type")) == "selfref"
                seen.add("sacself" if self_sac else "sacrifice")
            elif t == "discard":
                # A discard OUTLET pitches fodder from hand ("Discard a card: ...")
                # — madness/reanimator fuel. "Discard this card" (Cycling, alt-costs)
                # is a SELF-discard (phase's ``self_ref``), not a discard-matters
                # outlet; splitting it out is what unblocks the lane (the +471 flood).
                self_discard = bool(node.get("self_ref"))
                seen.add("discardself" if self_discard else "discard")
            elif t in _COST_TYPES:
                seen.add(t)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(cost)
    return ",".join(sorted(seen)) or None


def _project_spell_or_activated(ab: dict) -> Ability:
    kind = "activated" if _norm(ab.get("kind")) == "activated" else "spell"
    effects = _collect_effects(ab, ab.get("description") or "")
    return Ability(kind=kind, effects=tuple(effects), cost=_cost_string(ab.get("cost")))


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


# Quantity-modification types that INCREASE the amount → the doubler archetype,
# whatever the exact multiplier: Double (2x), Multiply (triple — only Ojer Taq for
# tokens / Nyxbloom for mana exist today), Plus (the "+N"/"that many plus" adders,
# e.g. Hardened Scales, Conclave Mentor). Half / Prevent / Minus are the opposite
# (decreases) and excluded.
_INCREASE_MODS = ("double", "multiply", "plus")


def _project_replacement(rep: dict) -> Ability | None:
    """A replacement effect (v0.1.60's top-level ``replacements``) → a static
    Ability. Doubling is split by the replaced EVENT — a token doubler and a
    counter doubler are different archetypes (one wants token makers, the other
    counter sources), so they are distinct categories, never one "doubling"."""
    event = _norm(rep.get("event"))
    raw = rep.get("description") or ""
    qmod = _norm((rep.get("quantity_modification") or {}).get("type"))
    dmod = _norm((rep.get("damage_modification") or {}).get("type"))
    if event == "createtoken" and qmod in _INCREASE_MODS:
        scope = "you" if _norm(rep.get("token_owner_scope")) == "you" else "any"
        return _static_effect("token_doubling", scope, raw)
    if event == "addcounter" and qmod in _INCREASE_MODS:
        cm = rep.get("counter_match") or {}
        ck = _norm(cm.get("data")) if isinstance(cm.get("data"), str) else ""
        return _static_effect("counter_doubling", "you", raw, counter_kind=ck)
    if event == "damagedone" and dmod in _INCREASE_MODS:
        return _static_effect("damage_doubling", "you", raw)
    return None


def _static_effect(
    category: str, scope: str, raw: str, *, counter_kind: str = ""
) -> Ability:
    return Ability(
        kind="static",
        effects=(
            Effect(category=category, scope=scope, raw=raw, counter_kind=counter_kind),
        ),
    )


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
    if etype in ("changezone", "changezoneall"):
        return [_changezone_effect(eff, raw)]
    if etype == "copytokenof":
        return [_copy_token_effect(eff, raw)]
    if etype == "additionalphase":
        # Batch 14 — an extra phase, split by which phase it grants.
        ph = _norm(eff.get("phase"))
        cat = _EXTRA_PHASE.get(ph, "other")
        return [Effect(category=cat, scope="you", raw=raw)]
    if etype in ("putatlibraryposition", "putontoporbottom"):
        return [_library_position_effect(eff, raw)]
    category = _EFFECT_CATEGORY.get(etype)
    if category is None or etype in _OTHER:
        return [Effect(category="other", scope=_effect_scope(eff), raw=raw)]
    ck = eff.get("counter_type")
    return [
        Effect(
            category=category,
            amount=_amount(eff),
            scope=_effect_scope(eff),
            subject=_effect_subject(eff),
            raw=raw,
            counter_kind=_norm(ck) if isinstance(ck, str) else "",
        )
    ]


# Static restriction modes (stax / taxes) — the mode is the restriction.
_RESTRICTION_MODES = frozenset(
    {
        "cantattack",
        "cantblock",
        "cantattackorblock",
        "cantbecast",
        "cantbeactivated",
        "cantcast",
        "cantuntap",
        "canttap",
        "cantdraw",
        "cantgainlife",
        "cantsearchlibrary",
        "mustattack",
        "mustblock",
        "raisecost",
        "perturncastlimit",
        "perturndrawlimit",
        "addrestriction",
        "blockrestriction",
        "maximumhandsize",
    }
)

# Batch 13 — combat-FORCING modes are pulled OUT of the stax-bound _RESTRICTION_MODES
# into their own categories (a "creatures must attack" is a force-the-table theme, not
# a tax). mustbeblocked* were not captured at all before. cantattack/cantattackorblock
# stay in _RESTRICTION_MODES (pillowfort = stax).
_COMBAT_FORCE_MODES: dict[str, str] = {
    "mustattack": "force_attack",
    "cantblock": "cant_block",
    "mustbeblocked": "lure",
    "mustbeblockedbyall": "lure",
}


def _restriction_scope(st: dict, affected: Filter | None) -> str:
    """Whom a restriction/combat-force static hobbles → the Effect scope (opp / each /
    any). Reads the affected set's controller and the mode's ``who`` qualifier."""
    who = _mode_who(st.get("mode"))
    if (affected is not None and affected.controller == "opp") or "opponent" in who:
        return "opp"
    if "all" in who:
        return "each"
    return "any"


def _mode_token(mode: object) -> str:
    """The restriction-mode discriminant — a bare string or a one-key dict."""
    if isinstance(mode, str):
        return _norm(mode)
    if isinstance(mode, dict) and len(mode) == 1:
        return _norm(next(iter(mode)))
    return ""


def _mode_who(mode: object) -> str:
    if isinstance(mode, dict):
        for v in mode.values():
            if isinstance(v, dict):
                return _norm(v.get("who"))
    return ""


def _modifycost_raise(mode: object) -> bool:
    """True for a v0.1.60 ``ModifyCost{mode: Raise}`` static — a cost TAX. v0.1.60
    merged the old ``raisecost``/``reducecost`` modes into one ``ModifyCost`` whose
    inner ``mode`` is the direction; only a Raise is a stax-style tax (a Reduce, or
    a self-only Strive-style Raise, is not)."""
    if isinstance(mode, dict) and len(mode) == 1:
        inner = next(iter(mode.values()))
        if isinstance(inner, dict):
            return _norm(inner.get("mode")) == "raise"
    return False


def _has_devotion_condition(st: dict) -> bool:
    """A static GATED on your devotion (a ``DevotionGE``, possibly wrapped in ``Not``
    for the 'less than N' form) — the Theros gods' "as long as your devotion to X is
    N or more". batch 8 captured devotion only as a scaling AMOUNT (qty); a devotion
    THRESHOLD lives in the condition subtree, so the lane missed the gods entirely."""

    def walk(n: object) -> bool:
        if isinstance(n, dict):
            if _norm(n.get("type")) == "devotionge":
                return True
            return any(walk(v) for v in n.values())
        if isinstance(n, list):
            return any(walk(x) for x in n)
        return False

    return walk(st.get("condition"))


def _project_static_mods(st: dict, raw: str) -> list[Effect]:
    """A continuous static's modifications + restriction mode → effects."""
    affected = _filter(st.get("affected"))
    desc = st.get("description") or raw
    out: list[Effect] = []
    # A devotion-threshold gate (gods) is a devotion payoff regardless of what the
    # static then does — carry the operand so the existing op="devotion" lane fires.
    if _has_devotion_condition(st):
        out.append(
            Effect(
                category="other",
                scope="you",
                raw=desc,
                amount=Quantity(op="devotion"),
            )
        )
    pump_amount: Quantity | None = None
    is_pump = False
    set_power = set_toughness = False
    for m in st.get("modifications") or []:
        mt = _norm(m.get("type"))
        if mt in _PUMP_MODS:
            is_pump = True
            if pump_amount is None:
                pump_amount = _quantity(m.get("value"))
        elif mt in ("setpower", "setdynamicpower", "setpowerdynamic"):
            set_power = True
        elif mt in ("settoughness", "setdynamictoughness", "settoughnessdynamic"):
            set_toughness = True
        elif mt == "addkeyword":
            # Batch 6 — a static that GRANTS a keyword (Levitation → Flying). The
            # granted keyword rides in counter_kind (a free str field); the lane
            # splits by keyword + whether the affected set is your whole team.
            kw = m.get("keyword")
            if isinstance(kw, str):
                out.append(
                    Effect(
                        category="grant_keyword",
                        scope=_controller_scope(affected),
                        subject=affected,
                        raw=desc,
                        counter_kind=_norm(kw),
                    )
                )
    # A static that SETS base power AND toughness on OTHER permanents (Lignify 0/4,
    # Ovinize 0/1, Kenrith's Transformation, mass-animate like Living Plane) — the
    # base-P/T TOOLBOX. Distinct from a +X/+X pump. Excludes a characteristic-defining
    # */* creature (Tarmogoyf defines its OWN P/T) AND a self-animate (a manland like
    # Treetop Village animates ITSELF — a creature-land, not a toolbox): both set the
    # SOURCE's P/T, not another permanent's.
    _affected_raw = st.get("affected")
    _self_pt = (
        isinstance(_affected_raw, dict)
        and _norm(_affected_raw.get("type")) == "selfref"
    )
    if (
        set_power
        and set_toughness
        and not st.get("characteristic_defining")
        and not _self_pt
    ):
        out.append(
            Effect(
                category="base_pt_set",
                scope=_controller_scope(affected),
                subject=affected,
                raw=desc,
            )
        )
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
    # A cost TAX (v0.1.60 ModifyCost{Raise}): scope = whose spells are taxed,
    # carried on ``affected.controller`` (Opponent → stax on them; unscoped "Card"
    # → symmetric; You → a self-drawback that hobbles no one, so emit nothing).
    if _modifycost_raise(st.get("mode")):
        if affected is not None and affected.controller == "opp":
            out.append(
                Effect(category="restriction", scope="opp", subject=affected, raw=desc)
            )
        elif affected is not None and affected.controller == "any":
            out.append(
                Effect(category="restriction", scope="each", subject=affected, raw=desc)
            )
        return out
    # Batch 13 — a combat-FORCING static (must attack / must be blocked / can't
    # block): its own category, not stax. The scope tracks whom it hobbles so the lane
    # can still feed stax (a "creatures opponents control can't block" is BOTH a
    # path-clearing payoff AND a pillowfort tax). A lure creature lures blockers to
    # ITSELF (SelfRef is the enabler) so lure keeps it; force_attack / cant_block need
    # a themeable affected (a real creature SET or a targeted creature) — a self
    # "this can't block" / "this must attack" is a vanilla drawback, not a theme.
    mode_tok = _mode_token(st.get("mode"))
    # Batch 6 (flash_grant, unblocked) — CastWithKeyword{Flash} is "you may cast
    # [creature] spells as though they had flash" (Teferi, Yeva, Alchemist's Refuge):
    # the flash ENABLER the AddKeyword path couldn't express (flash is a cast-time
    # permission, not a battlefield keyword). The granted keyword rides in
    # counter_kind so other CastWithKeyword grants can extend the lane later.
    if mode_tok == "castwithkeyword":
        mode = st.get("mode")
        inner = mode.get("CastWithKeyword") if isinstance(mode, dict) else None
        kw = inner.get("keyword") if isinstance(inner, dict) else None
        out.append(
            Effect(
                category="cast_with_keyword",
                scope="you",
                raw=desc,
                counter_kind=_norm(kw) if isinstance(kw, str) else "",
            )
        )
        return out
    # Batch 17 — DoubleTriggers static (Yarok / Panharmonicon / Ancient Greenwarden):
    # "a triggered ability triggers an additional time". One lane regardless of the
    # cause (ETB-only vs Any) — the want is the same trigger-doubling engine.
    if mode_tok == "doubletriggers":
        out.append(Effect(category="trigger_doubling", scope="you", raw=desc))
        return out
    # Batch 13 (evasion_denial) — IgnoreLandwalkForBlocking ("creatures can be
    # blocked as though they didn't have <landwalk>", Great Wall / Crevasse): denies
    # an evasion ability so you can block through it. scope "opp" (it strips THEIR
    # evasion); the lane reads it as opponents.
    if mode_tok == "ignorelandwalkforblocking":
        out.append(Effect(category="evasion_denial", scope="opp", raw=desc))
        return out
    combat_cat = _COMBAT_FORCE_MODES.get(mode_tok)
    if combat_cat is not None:
        scope = _restriction_scope(st, affected)
        affected_raw = st.get("affected")
        raw_type = (
            _norm(affected_raw.get("type")) if isinstance(affected_raw, dict) else ""
        )
        themeable = raw_type in ("typed", "parenttarget")
        if combat_cat == "lure" or themeable:
            out.append(
                Effect(category=combat_cat, scope=scope, subject=affected, raw=desc)
            )
        return out
    # A restriction static (stax/tax): scope = whom it hobbles.
    if mode_tok in _RESTRICTION_MODES:
        out.append(
            Effect(
                category="restriction",
                scope=_restriction_scope(st, affected),
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


def _library_position_effect(eff: dict, raw: str) -> Effect:
    """A put-into-library effect → ``topdeck_stack``, tagged with WHERE in
    ``counter_kind``. The top-stacking archetype (Brainstorm; graveyard-/hand-to-top
    recursion) reads top/nth/topbottom; a Bottom put ("rest on the bottom", failed-
    tutor cleanup) is not a top-stack. ``PutOnTopOrBottom`` is a player choice
    (top-eligible) → 'topbottom'. The subject (moved cards) carries the controller so
    the lane can keep self-stacking apart from a bounce-to-top removal (controller
    None)."""
    pos = eff.get("position")
    where = _norm(pos.get("type")) if isinstance(pos, dict) else "topbottom"
    return Effect(
        category="topdeck_stack",
        scope=_effect_scope(eff),
        subject=_effect_subject(eff),
        raw=raw,
        counter_kind=where,
    )


def _changezone_effect(eff: dict, raw: str) -> Effect:
    """A ChangeZone effect → category by its origin/destination zones.

    Graveyard → Battlefield is reanimation; → Exile of your own permanent is a
    blink (ETB-value flicker); → Exile of others' is exile removal; the rest stay
    'other'. The ``target`` (a Typed filter of what's moved) is the subject."""
    origin = _norm(eff.get("origin"))
    dest = _norm(eff.get("destination"))
    target = _filter(eff.get("target"))
    if origin == "graveyard" and dest == "battlefield":
        category = "reanimate"
    elif dest == "battlefield" and origin in ("library", "hand"):
        # Batch 9 — put a permanent into play from library/hand WITHOUT casting it
        # (Sneak Attack / Elvish Piper / Through the Breach). The lane gates on a
        # creature subject in signals (a land into play is ramp, not a cheat).
        category = "cheat_play"
    elif dest == "exile" and target is not None and target.controller == "you":
        # exile-and-return of YOUR own permanent = blink (ETB-value flicker).
        category = "blink"
    elif dest == "exile":
        # exile of others' permanents = exile removal.
        category = "exile"
    else:
        category = "other"
    return Effect(
        category=category,
        amount=_amount(eff),
        scope=_effect_scope(eff),
        subject=target,
        raw=raw,
    )


def _copy_token_effect(eff: dict, raw: str) -> Effect:
    """A CopyTokenOf effect (phase structures "create a token that's a copy of X")
    → a token maker. Scope is the ``owner`` (Controller → you); the made token's
    type is the copied object's filter (``target``) when it's a Typed filter — a
    self/parent/tracked copy leaves the subject unbound (its type is the source's,
    which the effect node doesn't carry)."""
    return Effect(
        category="make_token",
        amount=_amount(eff),
        scope=_effect_scope(eff),
        subject=_filter(eff.get("target")),
        raw=raw,
    )


def _effect_subject(eff: dict) -> Filter | None:
    """What the effect acts ON — the mass/typed filter, the single ``target``, or a
    made token's types. ``target`` is read last and only yields a Filter for a Typed
    object (destroy/bounce/exile target creature); a player target (DefendingPlayer)
    is not Typed, so `_filter` returns None and the effect stays subjectless."""
    for key in ("filter", "affected", "target_filter", "target"):
        f = _filter(eff.get(key))
        if f is not None:
            return f
    # Token effects carry the made token's types as bare strings (mixing the card
    # type "Creature" with subtypes "Goblin"/"Soldier") — split by the card-type set.
    types = eff.get("types")
    if isinstance(types, list):
        strs = [t for t in types if isinstance(t, str)]
        card_types = tuple(t for t in strs if t in _CARD_TYPES)
        subtypes = tuple(t for t in strs if t not in _CARD_TYPES)
        if card_types or subtypes:
            return Filter(card_types=card_types, subtypes=subtypes)
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
        qty = node.get("qty")
        # a Ref over a named scaling operand (devotion/party/domain) — Gray Merchant
        # is Ref→Devotion, so the operand is nested under qty, not a top-level type.
        if isinstance(qty, dict):
            op = _SCALING_OPERANDS.get(_norm(qty.get("type")))
            if op is not None:
                return Quantity(op=op, factor=1)
        return Quantity(op="count", factor=1, subject=_objectcount_filter(qty))
    if t == "objectcount":
        return Quantity(op="count", factor=1, subject=_filter(node.get("filter")))
    if t == "multiply":
        inner = _quantity(node.get("inner"))
        return Quantity(
            op="multiply",
            factor=_int(node.get("factor"), 1),
            subject=inner.subject if inner else None,
        )
    # Batch 8 — named scaling operands (a "for each X" where X is a deck-wide count).
    op = _SCALING_OPERANDS.get(t)
    if op is not None:
        return Quantity(op=op, factor=1)
    return None


# Batch 8 — phase quantity operand type → the Quantity.op the lane reads.
_SCALING_OPERANDS: dict[str, str] = {
    "devotion": "devotion",
    "devotionge": "devotion",
    "partysize": "party",
    "basiclandtypecount": "domain",
}


def _objectcount_filter(qty: object) -> Filter | None:
    if isinstance(qty, dict) and _norm(qty.get("type")) == "objectcount":
        return _filter(qty.get("filter"))
    return None


def _type_and_subtype_filters(node: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a Typed filter's ``type_filters`` into (card_types, subtypes).

    phase encodes card types as bare strings (``"Creature"``) and subtypes as
    one-key dicts (``{"Subtype": "Goblin"}``) within the same ``type_filters``
    list, plus an optional separate ``subtype_filters``. Composite entries —
    ``{"Non": X}`` (negation) and ``{"AnyOf": [...]}`` (disjunction) — are NOT a
    plain type/subtype (a ``{Non: Land}`` must not read as a Land filter); they
    become predicates via ``_composite_predicates`` and are skipped here."""
    card_types: list[str] = []
    subtypes: list[str] = list(_str_tuple(node.get("subtype_filters")))
    for tf in _as_list(node.get("type_filters")):
        if isinstance(tf, str):
            card_types.append(tf)
        elif isinstance(tf, dict):
            for k, v in tf.items():
                if _norm(k) == "subtype" and isinstance(v, str):
                    subtypes.append(v)
    return tuple(card_types), tuple(subtypes)


def _anyof_member(it: object) -> str:
    """The descriptor of one ``AnyOf`` member — a bare card type or a subtype."""
    if isinstance(it, str):
        return it
    if isinstance(it, dict):
        sub = it.get("Subtype")
        if isinstance(sub, str):
            return sub
    return ""


def _composite_predicates(node: dict) -> list[str]:
    """Negation / disjunction type_filter entries → predicate strings (the flat
    Filter has no nested-filter slot). ``{Non: "Land"}`` → ``NotType:Land`` (mirrors
    NotColor), ``{Non: {Subtype: Human}}`` → ``NotSubtype:Human``, ``{AnyOf: [...]}``
    → ``AnyOf:<sorted|members>`` (Instant/Sorcery, basic-land types, an Outlaw
    subtype set, …). Before this, ``{Non: X}`` was silently dropped INTO card_types
    (inverting the meaning) and ``{AnyOf}`` was dropped entirely."""
    out: list[str] = []
    for tf in _as_list(node.get("type_filters")):
        if not isinstance(tf, dict):
            continue
        for k, v in tf.items():
            kn = _norm(k)
            if kn == "non":
                if isinstance(v, str):
                    out.append(f"NotType:{v}")
                elif isinstance(v, dict) and isinstance(v.get("Subtype"), str):
                    out.append(f"NotSubtype:{v['Subtype']}")
            elif kn == "anyof" and isinstance(v, list):
                members = sorted(m for m in (_anyof_member(x) for x in v) if m)
                if members:
                    out.append("AnyOf:" + "|".join(members))
    return out


def _merge_filters(members: list[Filter]) -> Filter:
    """Union member filters into one — for an ``Or`` composite (Spark Double copies a
    Creature OR a Planeswalker; Absorbing Man an Artifact OR an Enchantment). Unions
    card_types/subtypes so a lane that keys on a type sees every type the effect can
    apply to; controller is kept only if all members agree (else "any"); predicates
    are dropped (their union semantics across an Or are ambiguous)."""
    card_types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    for m in members:
        card_types += tuple(t for t in m.card_types if t not in card_types)
        subtypes += tuple(s for s in m.subtypes if s not in subtypes)
    controllers = {m.controller for m in members}
    controller = members[0].controller if len(controllers) == 1 else "any"
    return Filter(card_types=card_types, subtypes=subtypes, controller=controller)


def _filter(node: object) -> Filter | None:
    if not isinstance(node, dict):
        return None
    # An ``Or`` composite target (a copy/effect that can apply to one of several
    # filters) — union the members so the type hierarchy sees every type it reaches.
    if _norm(node.get("type")) == "or":
        members = [f for f in (_filter(x) for x in _as_list(node.get("filters"))) if f]
        return _merge_filters(members) if members else None
    card_types, subtypes = _type_and_subtype_filters(node)
    controller = _controller(node.get("controller"))
    predicates = tuple(
        p for p in (_predicate(x) for x in _as_list(node.get("properties"))) if p
    ) + tuple(_composite_predicates(node))
    if not (card_types or subtypes or controller != "any" or predicates):
        return None
    return Filter(
        card_types=card_types,
        subtypes=subtypes,
        controller=controller,
        predicates=predicates,
    )


def _scalar_value(v: object) -> int | None:
    """An int from a bare int or a ``{type: Fixed, value: N}`` wrapper; None for a
    DYNAMIC value (Ref / Offset / Variable — a relative comparison like "power less
    than this creature's power", not a fixed threshold a theme keys on)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, dict) and _norm(v.get("type")) == "fixed":
        inner = v.get("value")
        return inner if isinstance(inner, int) else None
    return None


def _predicate(p: object) -> str:
    if not isinstance(p, dict):
        return ""
    ptype = p.get("type")
    if not ptype:
        return ""
    # Keep the load-bearing discriminant for the predicates whose meaning is NOT a
    # bare `value` field — color / multicolor-count / power-threshold lanes read it
    # (it was dropped before, collapsing every HasColor to a bare "HasColor"). A
    # dynamic (non-Fixed) comparison value becomes "*" so a relative fight-style
    # "power < source's power" never reads as a fixed power threshold.
    if ptype in ("HasColor", "NotColor"):
        color = p.get("color")
        return f"{ptype}:{color}" if color is not None else str(ptype)
    if ptype == "ColorCount":
        n = _scalar_value(p.get("count"))
        return f"ColorCount:{p.get('comparator')}:{n if n is not None else '*'}"
    if ptype == "PtComparison":
        n = _scalar_value(p.get("value"))
        return (
            f"PtComparison:{p.get('stat')}:{p.get('comparator')}:"
            f"{n if n is not None else '*'}"
        )
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
    # A Token effect's recipient is its ``owner`` (Controller → you; a target's
    # controller → opp, so "destroy target creature, its controller makes a Beast"
    # is removal, not a token engine for you).
    owner = eff.get("owner")
    if isinstance(owner, dict):
        on = _norm(owner.get("type"))
        if on == "controller":
            return "you"
        if "opponent" in on or "target" in on:
            return "opp"
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
    if mode == "damagereceived":
        return "damage_received"
    if mode in ("spellcast", "spellcopy", "spellcastorcopy", "spellabilitycast"):
        return "cast_spell"
    if mode in (
        "attacks",
        "youattack",
        "attackersdeclared",
        "attackersdeclaredonetarget",
        # v0.1.60 split "attacks and isn't blocked" into its own modes; v0.1.19
        # folded them into Attacks, so map them back to keep attack_matters parity.
        "attackerunblocked",
        "youattackunblocked",
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
        if ph in ("begincombat", "combat"):
            return "begin_combat"
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
    if mode == "drawn":
        return "drawn"
    if mode in ("milled", "milledonce", "milledall"):
        return "milled"
    if mode in ("blocks", "blockersdeclared", "becomesblocked", "attackerblocked"):
        return "blocks"
    # Batch 1 — payoff trigger modes previously falling to "other". The Scry/Surveil
    # TRIGGER modes ("whenever you scry/surveil") are distinct from the Scry/Surveil
    # EFFECT types (the doer → topdeck_select in _EFFECT_CATEGORY).
    if mode == "commitcrime":
        return "commit_crime"
    if mode == "cycled":
        return "cycled"
    if mode == "scry":
        return "scried"
    if mode == "surveil":
        return "surveiled"
    if mode in ("excessdamageall", "excessdamage"):
        return "excess_damage"
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
    # Batch 11 — a player-EVENT trigger (whenever an opponent draws/searches) carries
    # the player in valid_target, not valid_card (Nekusar: Drawn + valid_target
    # controller=Opponent). Fall back to it so the scope isn't lost.
    vt = tr.get("valid_target")
    if isinstance(vt, dict):
        c = _controller(vt.get("controller"))
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


def _allows_many_copies(record: dict) -> bool:
    """The CR 100.2a copy-limit exception (a deck may run many copies of this name —
    Relentless Rats, Hare Apparent, Seven Dwarves): phase's ``deck_copy_limit`` is
    ``Unlimited`` or ``UpTo`` with a bound >= 2. UpTo:1 (Vazal's Megalegendary, Once
    More With Feeling) RESTRICTS to one copy — the opposite — so it is excluded."""
    dl = record.get("deck_copy_limit")
    if not isinstance(dl, dict):
        return False
    t = _norm(dl.get("type"))
    if t == "unlimited":
        return True
    return t == "upto" and _int(dl.get("data"), 0) >= 2


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
