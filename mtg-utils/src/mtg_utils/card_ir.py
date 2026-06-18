"""The Card IR — a structured, per-face parse of a card's abilities.

deck-forge's detection historically re-grepped raw ``oracle_text`` with a large
bag of regexes across many modules. The structural weakness was that a regex can
see *that* a card scales ("for each", "equal to the number of") but cannot bind
*what it scales with* — the operand ``Y`` in "do A for each Y you control" — nor
reliably resolve *scope* (whose graveyard / whose creatures). The Card IR fixes
that: every card becomes a tuple of :class:`Face` objects, each owning its
:class:`Ability` list (so DFC faces never bleed into each other), and every
ability's effects carry a structured operand (:class:`Quantity` →
:class:`Filter`) and an explicit scope.

This module is **schema only** — pure dataclasses + (de)serialization, stdlib
only. The projection from phase-rs's parse lives in ``_card_ir/project.py``; the
oracle-text gap-filler in ``_card_ir/supplement.py``. The IR deliberately does
*not* re-store fields that are a trivial lookup on the Scryfall record a consumer
already holds (cmc, power/toughness, color identity, legalities): a consumer
joins the IR to its Scryfall card by ``oracle_id`` and reads those there. The IR
carries only the parse.

Altitude is **synergy-sufficient now, rules-accurate later** (the grilled
decision): the closed ``category`` / ``event`` vocabularies cover the dimensions
the tuner / lane detection / sorter consume, and anything unresolved degrades to
``category="other"`` rather than failing — a node that can later be subdivided
toward rules-accuracy without a schema rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── scope / controller vocabularies ───────────────────────────────────────────
# scope: who an effect/trigger concerns. "you" | "opp" | "each" | "any".
# controller (on a Filter): who controls the filtered objects. "you" | "opp" |
# "any". Distinct from scope — a Filter narrows a set of permanents; scope says
# whose resource the surrounding effect touches.


@dataclass(frozen=True)
class Filter:
    """A selector for a set of game objects — the ``Y`` in "for each Y".

    ``predicates`` are normalized strings (e.g. ``"PowerGE:4"``, ``"Tapped"``)
    rather than a nested type, kept flat for a compact sidecar and easy equality;
    they can be promoted to structured predicates later without breaking callers
    that only test membership.
    """

    card_types: tuple[str, ...] = ()  # e.g. ("Creature",) — title-cased
    subtypes: tuple[str, ...] = ()  # e.g. ("Goblin",) — title-cased
    controller: str = "any"  # you | opp | any
    predicates: tuple[str, ...] = ()  # e.g. ("PowerGE:4",)


@dataclass(frozen=True)
class Quantity:
    """A scalar that an effect produces — fixed, a count, or a multiple.

    ``op="fixed"`` → ``factor`` is the literal amount, ``subject`` is None.
    ``op="count"`` → the amount is ``|subject|`` (Craterhoof: count your creatures).
    ``op="multiply"`` → the amount is ``factor * |subject|`` (Shamanic: 4x …).
    """

    op: str = "fixed"  # count | fixed | multiply
    factor: int = 1
    subject: Filter | None = None


@dataclass(frozen=True)
class Effect:
    """One thing an ability does, in the closed synergy ``category`` vocabulary.

    ``amount`` is the scales-with operand (None when the effect has no count).
    ``subject`` is what the effect acts ON (the token kind made, the counter's
    filter, …). ``raw`` is the source oracle/description clause, kept for
    grounding (it is what ``Signal.text`` is sourced from) and debugging.
    """

    category: str  # see CATEGORIES
    amount: Quantity | None = None
    scope: str = "any"  # you | opp | each | any
    subject: Filter | None = None
    raw: str = ""
    counter_kind: str = ""  # for place/remove_counter: p1p1 | m1m1 | charge | oil | …


@dataclass(frozen=True)
class Trigger:
    """The condition a triggered ability waits on.

    ``subject`` narrows *what* triggers it ("another creature you control"),
    ``scope`` says whose event it is.
    """

    event: str  # see EVENTS
    subject: Filter | None = None
    scope: str = "any"  # you | opp | each | any


@dataclass(frozen=True)
class Ability:
    """A single static / triggered / activated / spell ability of one face."""

    kind: str  # static | triggered | activated | spell
    effects: tuple[Effect, ...] = ()
    trigger: Trigger | None = None  # set iff kind == "triggered"
    cost: str | None = None  # raw activation cost text iff kind == "activated"
    zones: tuple[str, ...] = ()  # zones the ability functions in, when not battlefield


@dataclass(frozen=True)
class Face:
    """One face of a card (a single-faced card has exactly one Face)."""

    name: str
    type_line: str = ""
    keywords: tuple[str, ...] = ()
    abilities: tuple[Ability, ...] = ()


@dataclass(frozen=True)
class Card:
    """The parsed IR for one card, keyed by Scryfall ``oracle_id``.

    ``parse_confidence``: ``full`` (everything projected cleanly), ``partial``
    (some clause fell to ``category="other"`` / an unresolved trigger), or
    ``unparsed`` (no abilities recovered at all). ``coverage_gate`` reads this in
    place of the old oracle-text blind-spot heuristics.
    """

    oracle_id: str
    name: str
    faces: tuple[Face, ...] = ()
    castable_zones: tuple[str, ...] = ()  # graveyard | exile | ... (cast-from zones)
    parse_confidence: str = "full"  # full | partial | unparsed

    def all_abilities(self) -> tuple[Ability, ...]:
        """Face-agnostic rollup: every ability across every face, in order."""
        return tuple(a for f in self.faces for a in f.abilities)

    @property
    def keywords(self) -> tuple[str, ...]:
        """Deduped rollup of every face's keywords (order-preserving)."""
        seen: dict[str, None] = {}
        for f in self.faces:
            for kw in f.keywords:
                seen.setdefault(kw, None)
        return tuple(seen)

    # ── serialization (compact: omit empties so the sidecar stays small) ──
    def to_dict(self) -> dict:
        return _card_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Card:
        return _card_from_dict(data)


# Closed vocabularies — the synergy dimensions the consumers read. "other" is the
# escape hatch for the tail (degrade, never fail). Kept here as the single source
# of truth so the projection, supplement, and signal mapping agree.
CATEGORIES: frozenset[str] = frozenset(
    {
        "draw",
        "damage",
        "make_token",
        "place_counter",
        "remove_counter",
        "reanimate",
        "mill",
        "gain_life",
        "lose_life",
        "destroy",
        "exile",
        "bounce",
        "counter_spell",
        "pump",
        "tutor",
        "ramp",
        "sacrifice",
        "discard",
        "gain_control",
        "proliferate",
        "untap",
        "tap",
        "topdeck_select",
        "fight",
        "other",
    }
)

EVENTS: frozenset[str] = frozenset(
    {
        "etb",
        "dies",
        "attacks",
        "blocks",
        "upkeep",
        "end_step",
        "draw_step",
        "cast_spell",
        "combat_damage",
        "deals_damage",
        "counter_added",
        "life_gained",
        "life_lost",
        "taps",
        "sacrificed",
        "discarded",
        "leaves",
        "other",
    }
)


# ── (de)serialization helpers ─────────────────────────────────────────────────
# Compact dicts: a field is omitted when it equals its dataclass default, so an
# empty Filter / a "fixed" Quantity of 1 / an "any" scope costs nothing on disk.


def _filter_to_dict(f: Filter | None) -> dict | None:
    if f is None:
        return None
    out: dict = {}
    if f.card_types:
        out["t"] = list(f.card_types)
    if f.subtypes:
        out["s"] = list(f.subtypes)
    if f.controller != "any":
        out["c"] = f.controller
    if f.predicates:
        out["p"] = list(f.predicates)
    return out


def _filter_from_dict(d: dict | None) -> Filter | None:
    if d is None:
        return None
    return Filter(
        card_types=tuple(d.get("t", ())),
        subtypes=tuple(d.get("s", ())),
        controller=d.get("c", "any"),
        predicates=tuple(d.get("p", ())),
    )


def _quantity_to_dict(q: Quantity | None) -> dict | None:
    if q is None:
        return None
    out: dict = {"op": q.op}
    if q.factor != 1:
        out["f"] = q.factor
    sub = _filter_to_dict(q.subject)
    if sub is not None:
        out["sub"] = sub
    return out


def _quantity_from_dict(d: dict | None) -> Quantity | None:
    if d is None:
        return None
    return Quantity(
        op=d.get("op", "fixed"),
        factor=d.get("f", 1),
        subject=_filter_from_dict(d.get("sub")),
    )


def _effect_to_dict(e: Effect) -> dict:
    out: dict = {"cat": e.category}
    amt = _quantity_to_dict(e.amount)
    if amt is not None:
        out["amt"] = amt
    if e.scope != "any":
        out["sc"] = e.scope
    sub = _filter_to_dict(e.subject)
    if sub is not None:
        out["sub"] = sub
    if e.raw:
        out["raw"] = e.raw
    if e.counter_kind:
        out["ck"] = e.counter_kind
    return out


def _effect_from_dict(d: dict) -> Effect:
    return Effect(
        category=d["cat"],
        amount=_quantity_from_dict(d.get("amt")),
        scope=d.get("sc", "any"),
        subject=_filter_from_dict(d.get("sub")),
        raw=d.get("raw", ""),
        counter_kind=d.get("ck", ""),
    )


def _trigger_to_dict(t: Trigger | None) -> dict | None:
    if t is None:
        return None
    out: dict = {"ev": t.event}
    sub = _filter_to_dict(t.subject)
    if sub is not None:
        out["sub"] = sub
    if t.scope != "any":
        out["sc"] = t.scope
    return out


def _trigger_from_dict(d: dict | None) -> Trigger | None:
    if d is None:
        return None
    return Trigger(
        event=d["ev"],
        subject=_filter_from_dict(d.get("sub")),
        scope=d.get("sc", "any"),
    )


def _ability_to_dict(a: Ability) -> dict:
    out: dict = {"k": a.kind}
    if a.effects:
        out["e"] = [_effect_to_dict(e) for e in a.effects]
    trig = _trigger_to_dict(a.trigger)
    if trig is not None:
        out["tr"] = trig
    if a.cost is not None:
        out["cost"] = a.cost
    if a.zones:
        out["z"] = list(a.zones)
    return out


def _ability_from_dict(d: dict) -> Ability:
    return Ability(
        kind=d["k"],
        effects=tuple(_effect_from_dict(e) for e in d.get("e", ())),
        trigger=_trigger_from_dict(d.get("tr")),
        cost=d.get("cost"),
        zones=tuple(d.get("z", ())),
    )


def _face_to_dict(f: Face) -> dict:
    out: dict = {"n": f.name}
    if f.type_line:
        out["tl"] = f.type_line
    if f.keywords:
        out["kw"] = list(f.keywords)
    if f.abilities:
        out["ab"] = [_ability_to_dict(a) for a in f.abilities]
    return out


def _face_from_dict(d: dict) -> Face:
    return Face(
        name=d["n"],
        type_line=d.get("tl", ""),
        keywords=tuple(d.get("kw", ())),
        abilities=tuple(_ability_from_dict(a) for a in d.get("ab", ())),
    )


def _card_to_dict(c: Card) -> dict:
    out: dict = {"oid": c.oracle_id, "n": c.name}
    if c.faces:
        out["faces"] = [_face_to_dict(f) for f in c.faces]
    if c.castable_zones:
        out["cz"] = list(c.castable_zones)
    if c.parse_confidence != "full":
        out["pc"] = c.parse_confidence
    return out


def _card_from_dict(d: dict) -> Card:
    return Card(
        oracle_id=d["oid"],
        name=d["n"],
        faces=tuple(_face_from_dict(f) for f in d.get("faces", ())),
        castable_zones=tuple(d.get("cz", ())),
        parse_confidence=d.get("pc", "full"),
    )
