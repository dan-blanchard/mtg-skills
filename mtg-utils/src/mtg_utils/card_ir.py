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
    # Directional non-battlefield zone references this effect structurally touches,
    # e.g. ("from:graveyard", "to:exile") for "exile target card from a graveyard",
    # ("in:graveyard",) for a target/count filtered to the graveyard. Lane-agnostic
    # IR; signals derives zone-matters lanes (graveyard_matters, …) and applies its
    # own policy (e.g. battlefield→graveyard is death, not graveyard synergy).
    zones: tuple[str, ...] = ()


@dataclass(frozen=True)
class Trigger:
    """The condition a triggered ability waits on.

    ``subject`` narrows *what* triggers it ("another creature you control"),
    ``scope`` says whose event it is.
    """

    event: str  # see EVENTS
    subject: Filter | None = None
    scope: str = "any"  # you | opp | each | any
    # Directional zone refs of a ChangeZone trigger ("whenever a card is put into
    # your graveyard" → ("to:graveyard",)), same shape as Effect.zones. The `event`
    # collapses the zone movement to etb/dies/leaves; zones keeps it for the
    # zone-matters lanes (a dies trigger is from:battlefield+to:graveyard, so signals
    # can tell graveyard-FILL from death).
    zones: tuple[str, ...] = ()


@dataclass(frozen=True)
class Condition:
    """A gate on an ability — phase's ``condition`` field projected structurally.

    ``kind`` is the normalized phase condition type (``source_in_zone``,
    ``quantity_comparison``, ``controls_type``, ``has_counters``, …). ``zones`` is
    every non-stack zone referenced anywhere in the condition tree (recursive —
    "if a creature card is in your graveyard", a graveyard count, cast-from-zone),
    the field zone-matters lanes read. ``subject`` is the type/object filter the
    condition checks (ControlsType → metalcraft, ZoneChangedThisWay), ``nested``
    holds And/Or/Not children.
    """

    kind: str
    zones: tuple[str, ...] = ()
    subject: Filter | None = None
    counter_kind: str = ""  # for has_counters
    comparator: str = ""  # GE | LE | EQ | … for quantity_comparison
    nested: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class Ability:
    """A single static / triggered / activated / spell ability of one face."""

    kind: str  # static | triggered | activated | spell
    effects: tuple[Effect, ...] = ()
    trigger: Trigger | None = None  # set iff kind == "triggered"
    cost: str | None = None  # raw activation cost text iff kind == "activated"
    zones: tuple[str, ...] = ()  # zones the ability functions in, when not battlefield
    condition: Condition | None = None  # the ability's gate, when present


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

    ``parse_confidence``: ``full`` (everything projected cleanly — including a
    vanilla/textless card, which has nothing to parse) or ``partial`` (some clause
    fell to ``category="other"`` / an unresolved trigger). The legacy ``unparsed``
    level is no longer produced: a card with no abilities AND no keywords is vanilla
    (its full mechanics are its types + P/T), so it is ``full``; any text-bearing
    card phase whiffs on is synthesized into clauses first, so it is never abilityless.
    """

    oracle_id: str
    name: str
    faces: tuple[Face, ...] = ()
    castable_zones: tuple[str, ...] = ()  # graveyard | exile | ... (cast-from zones)
    parse_confidence: str = "full"  # full | partial  (legacy: unparsed, now folded)
    # CR 100.2a exception: a deck may run many copies of this name (Relentless Rats,
    # Hare Apparent, Seven Dwarves) — phase's deck_copy_limit Unlimited or UpTo>=2.
    # The authoritative named-deck signal (a structured field, not an oracle regex).
    many_copies: bool = False

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
        "blink",
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
        # cast-from-a-zone (impulse / flashback-grant / graveyard-cast permission) —
        # phase's CastFromZone / GrantCastingPermission map (project._EFFECT_CATEGORY)
        # and the ADR-0027 graveyard-cast emblem marker
        # (project._graveyard_cast_grant_markers).
        "cast_from_zone",
        # Batch P — phase-native mechanic effects.
        "monarch",
        "suspect",
        "speed",
        "station",
        "venture",
        "connive",
        "damage_prevention",
        "animate",
        "detain",
        "restriction",
        "seek",
        # ADR-0027 restriction-narrow markers — precise categories appended when a
        # generic carrier's raw encodes the mechanic (project._narrow_mechanic_refs).
        "cant_block",
        "saddle",
        "soulbond",
        "phasing",
        # ADR-0027 trigger-other raw-markers — precise categories appended when an
        # event='other' triggered ability's effect raw encodes the trigger clause
        # (project._narrow_trigger_other_refs). coin_flip/explore/discover are also
        # produced by phase's typed-effect map (_EFFECT_CATEGORY); these are the
        # keyword-less payoff anchors phase flattened the trigger of.
        "boast",
        "exhaust",
        "ninjutsu",
        "scry_surveil",
        # ADR-0027 conferred-keyword re-parse markers — precise categories appended
        # when a grant carrier's raw encodes a keyword/ability GRANTED to a class of
        # objects (project._narrow_conferred_keyword_refs). affinity/madness/foretell/
        # devour are the conferred KEYWORDS; evasion_denial/damage_reflect are the
        # generic-landwalk umbrella + quoted reflection ability (evasion_denial is
        # also phase's own named-walk category; connive/counter_spell already exist
        # above as phase's own effect categories).
        "affinity",
        "madness",
        "foretell",
        "devour",
        "evasion_denial",
        "damage_reflect",
        # ADR-0027 keyword-conditioned payoff + dropped-static face markers — precise
        # categories appended for a payoff/grant phase left only in a non-grant
        # carrier raw (project._narrow_payoff_condition_refs: "if it has mutate") or
        # dropped from the parse entirely, surviving only on the face oracle text
        # (project._dropped_static_markers: a "has scavenge" graveyard-wide grant).
        # boast/scry_surveil/madness/foretell already exist above; trigger_doubling /
        # extra_end are phase's own effect categories the dropped-static pass also
        # produces for the granted/replacement residual.
        "mutate",
        "scavenge",
        # ADR-0027 sweep dropped-static / trigger-other markers — precise categories
        # appended for a payoff/reference phase left only on the face oracle text or
        # in an event='other' carrier raw (project._dropped_static_markers /
        # _narrow_trigger_other_refs). starting_life ← "starting life total" compare;
        # mass_death ← "creatures that died this turn" count operand; cycling_payoff
        # ← a "cycle or discard" payoff trigger (DISTINCT from phase's native `cycling`
        # doer effect for landcycling, so the payoff lane stays payoff-only); roll_die
        # is also phase's own effect category (the keyword-less dice payoff/spell).
        # CR 103.4 / 700.4 / 702.29.
        "starting_life",
        "mass_death",
        "cycling_payoff",
        # ADR-0027 sweep batch 2 conferred/dropped-static markers — the keyword-less
        # GRANTERS / anthems / references phase folds into a carrier raw or drops onto
        # the face oracle. cascade ← "(have|has|gain) cascade" conferral (Maelstrom
        # Nexus, Yidris); undying_persist ← "(gains|have|has) undying/persist" grant
        # (Mikaeus, the persist-granters); changeling ← "changeling" / "is every
        # creature type" all-tribes maker/anthem (Maskwood Nexus, Mistform Ultimus).
        # CR 702.85 / 702.92 / 702.78 / 702.73.
        "cascade",
        "undying_persist",
        "changeling",
        # creature_cast ← a "casts a creature spell" reference phase dropped onto the
        # face oracle (a quoted token ability — Blink — or a spell's delayed trigger —
        # Glimpse of Nature). CR 601 (a creatures-being-cast payoff, scope "any").
        "creature_cast",
        # token_subtype_ref ← a cares-about reference to a named token subtype
        # (Food/Treasure/Clue/Blood) WITHOUT making/sacrificing it ("Foods you control",
        # "was a Treasure", "is a Food") phase has no structure for; the subtype rides
        # counter_kind. Read in extract_signals_ir → food/treasure/clue/blood_matters.
        "token_subtype_ref",
        # saga ← a lore-counter MANIPULATION / PAYOFF ("lore counter", "Saga you
        # control") phase keeps only on the face oracle (the lore placement it does emit
        # is the subjectless intrinsic advancement). CR 714 → saga_matters.
        "saga",
        # ADR-0027 go-wide marker — a count-over-your-own-board operand (creatures /
        # artifacts / enchantments you control) the structured projection dropped to a
        # subjectless characteristic_pt / ModifyCost / damage / gate condition;
        # project._board_count_markers recovers it. Its amount.subject is the generic
        # own-board Filter the count lane reads (CR 604.3).
        "board_count",
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
    if e.zones:
        out["z"] = list(e.zones)
    return out


def _effect_from_dict(d: dict) -> Effect:
    return Effect(
        category=d["cat"],
        amount=_quantity_from_dict(d.get("amt")),
        scope=d.get("sc", "any"),
        subject=_filter_from_dict(d.get("sub")),
        raw=d.get("raw", ""),
        counter_kind=d.get("ck", ""),
        zones=tuple(d.get("z", ())),
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
    if t.zones:
        out["z"] = list(t.zones)
    return out


def _trigger_from_dict(d: dict | None) -> Trigger | None:
    if d is None:
        return None
    return Trigger(
        event=d["ev"],
        subject=_filter_from_dict(d.get("sub")),
        scope=d.get("sc", "any"),
        zones=tuple(d.get("z", ())),
    )


def _condition_to_dict(c: Condition | None) -> dict | None:
    if c is None:
        return None
    out: dict = {"kind": c.kind}
    if c.zones:
        out["zn"] = list(c.zones)
    sub = _filter_to_dict(c.subject)
    if sub is not None:
        out["sub"] = sub
    if c.counter_kind:
        out["ck"] = c.counter_kind
    if c.comparator:
        out["cmp"] = c.comparator
    if c.nested:
        out["nest"] = [_condition_to_dict(n) for n in c.nested]
    return out


def _condition_from_dict(d: dict | None) -> Condition | None:
    if d is None:
        return None
    return Condition(
        kind=d["kind"],
        zones=tuple(d.get("zn", ())),
        subject=_filter_from_dict(d.get("sub")),
        counter_kind=d.get("ck", ""),
        comparator=d.get("cmp", ""),
        nested=tuple(
            c
            for c in (_condition_from_dict(n) for n in d.get("nest", ()))
            if c is not None
        ),
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
    cond = _condition_to_dict(a.condition)
    if cond is not None:
        out["cond"] = cond
    return out


def _ability_from_dict(d: dict) -> Ability:
    return Ability(
        kind=d["k"],
        effects=tuple(_effect_from_dict(e) for e in d.get("e", ())),
        trigger=_trigger_from_dict(d.get("tr")),
        cost=d.get("cost"),
        zones=tuple(d.get("z", ())),
        condition=_condition_from_dict(d.get("cond")),
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
    if c.many_copies:
        out["mc"] = True
    return out


def _card_from_dict(d: dict) -> Card:
    return Card(
        oracle_id=d["oid"],
        name=d["n"],
        faces=tuple(_face_from_dict(f) for f in d.get("faces", ())),
        castable_zones=tuple(d.get("cz", ())),
        parse_confidence=d.get("pc", "full"),
        many_copies=d.get("mc", False),
    )
