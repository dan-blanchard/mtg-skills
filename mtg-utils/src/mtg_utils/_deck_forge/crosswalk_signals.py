"""Layer-3 ``Signal`` lanes derived from the Layer-2 concept overlay (ADR-0035).

The first ported concept batch. Each lane reads the tree-preserving concept
overlay (``_card_ir.crosswalk.ConceptTree``) — typed reads only, no oracle re-grep
— and emits the frozen ``Signal(key, scope, subject)`` contract, mirroring the live
``_deck_forge._signals_ir`` arm closely enough that the shadow diff reproduces it
(or improves on a known lossy case). **Shadow-only / additive**: production
detection (``signals.py`` / ``_signals_ir.py``) is untouched; this runs alongside
for the diff.

The batch spans every concept kind the framework must prove:

* ``win_lose_game`` — a terminal **effect category** (whole-card scan, scope "any").
* ``discard_makers`` — a **join-dependent** maker: a ``draw`` + ``discard`` effect
  in the SAME ability unit (granularity *a*; never across abilities, never a cost).
* ``spell_copy_makers`` — a structural **effect**, plus the whole-card
  ``spellcast_matters`` reconciliation (granularity *c*).
* ``token_maker`` — a structural effect that is **subject-bearing** (the token's
  creature subtype, vocab-validated).
* ``draw_matters`` — a **trigger event** (Drawn), scope-discriminated.
* ``land_creatures_matter`` — a **per-ability aggregation** of a Land(+Creature)
  subject with a pump/animate modification (granularity *b*; the animate-land
  split-subject).

``PORTED_KEYS`` is the batch's Signal-key set — the shadow diff slices both paths
to it.
"""

from __future__ import annotations

from mtg_utils._card_ir.crosswalk import (
    ConceptTree,
    trigger_scope,
)
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._signals_regex import Signal, _resolve_subject
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

# The Signal keys this batch derives from the typed substrate. The shadow harness
# slices BOTH the crosswalk and the live hybrid path to exactly this set.
PORTED_KEYS: frozenset[str] = frozenset(
    {
        "win_lose_game",
        "discard_makers",
        "spell_copy_makers",
        "spellcast_matters",
        signal_keys.TOKEN_MAKER,
        "draw_matters",
        "land_creatures_matter",
    }
)

# Effect/owner scopes that count as "your" resource for a maker lane.
_YOU_EACH = ("you", "each")


def _win_lose_game(tree: ConceptTree) -> list[Signal]:
    """Terminal alt-win / alt-loss (CR 104.2). Whole-card; scope "any" (HIGH).

    Mirrors ``_signals_ir`` line ~7330: any ``win_game`` / ``lose_game`` effect →
    one ``win_lose_game`` firing scoped "any" (the behavior-neutral merge of
    self-wins and opponent-losses the deleted SWEEP row used).
    """
    for concept in ("win_game", "lose_game"):
        hits = tree.effect_concepts(concept)
        if hits:
            return [Signal("win_lose_game", "any", "", hits[0].raw, tree.name, "high")]
    return []


def _discard_makers(tree: ConceptTree) -> list[Signal]:
    """Loot / rummage / connive OUTLET — a draw + discard in the SAME ability unit.

    Granularity (a), per-ability sibling co-occurrence. Mirrors ``_signals_ir``
    line ~7535: an ability carrying BOTH a ``draw`` effect AND a ``discard`` effect
    scoped you/each is a self-loot outlet. The per-unit gate (``effect_concepts``
    reads role=effect only, scoped to one unit) is load-bearing: Psychic Frog and
    Nezahal carry a combat-damage draw *trigger* and a separate ``Discard a card:``
    *cost* in DIFFERENT units, so they must NOT fire here.
    """
    for unit in tree.units:
        if not unit.has_effect("draw"):
            continue
        disc = next(
            (c for c in unit.effect_concepts("discard") if c.scope in _YOU_EACH),
            None,
        )
        if disc is not None:
            return [Signal("discard_makers", "you", "", disc.raw, tree.name, "high")]
    return []


def _spell_copy_makers(tree: ConceptTree) -> list[Signal]:
    """A spell-copier (Twincast / Fork — "copy target spell"). Whole-card (HIGH).

    Mirrors ``_signals_ir`` line ~8684: a ``copy_spell`` effect → spell_copy_makers
    you. Distinct from clone (creatures-on-battlefield) and token-copy.
    """
    hits = tree.effect_concepts("copy_spell")
    if hits:
        return [Signal("spell_copy_makers", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _token_maker(tree: ConceptTree) -> list[Signal]:
    """A creature-token MAKER — subject-bearing (the token's kindred subtype).

    Mirrors ``_signals_ir`` line ~8072: a ``make_token`` effect scoped you/each
    whose token is a creature → ``token_maker`` with the vocab-resolved subtype
    subject ("" when none resolves). The owner-scope gate drops opponent-gift
    tokens (Hunted Dragon). Reads the token's ``types`` from the typed node, never
    oracle text.
    """
    seen: set[str] = set()
    out: list[Signal] = []
    for concept in tree.effect_concepts("make_token"):
        if concept.scope not in _YOU_EACH:
            continue
        types = concept.subject
        if "Creature" not in types:
            continue
        subject = ""
        for word in reversed(types):
            resolved = _resolve_subject(word, CREATURE_SUBTYPES)
            if resolved:
                subject = resolved
                break
        if subject in seen:
            continue
        seen.add(subject)
        out.append(
            Signal(
                signal_keys.TOKEN_MAKER, "you", subject, concept.raw, tree.name, "high"
            )
        )
    return out


def _draw_matters(tree: ConceptTree) -> list[Signal]:
    """ "Whenever you draw a card" payoff (The Locust God, Chasm Skulker).

    A trigger-event lane. Mirrors ``_signals_ir`` line ~10653: a ``Drawn`` trigger
    whose watched scope is not the opponent → ``draw_matters`` you (HIGH). The
    opponent-draw punisher (Bowmasters, Nekusar) is a SEPARATE lane and does not
    fire here.
    """
    for unit in tree.units:
        if unit.trigger_event != "drawn":
            continue
        if trigger_scope(unit.node) != "opponents":
            return [Signal("draw_matters", "you", "", "", tree.name, "high")]
    return []


def _is_creature_animator(unit: object) -> bool:
    """A static ability that turns its Land subject into a creature (animate-land).

    Granularity (b) per-ability aggregation: the unit's ``affected`` Land subject
    and an ``AddType Creature`` (or a base-P/T set that makes it a creature) modi-
    fication are read TOGETHER off one continuous ability — the split-subject the
    old projection drops to ``None`` and spreads across effects (Natural
    Emergence). Scope-gated to YOUR lands (``_signals_ir`` passes ``("you",)``), so
    a symmetric all-lands animate (Living Plane) does not open a your-lands build.
    """
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    if statics[0].scope != "you":  # the affected-filter controller (you-gate)
        return False
    subject = statics[0].subject  # all mods share the ability's affected subject
    if "Land" not in subject or "Creature" in subject:
        return False
    for concept in statics:
        if (
            concept.concept == "add_type"
            and getattr(concept.node, "core_type", None) == "Creature"
        ):
            return True
        # A Land made into a 1/1 via base-P/T set + AddType handled above; a bare
        # set_pt with no AddType is not an animator (it stays a land).
    return False


def _has_land_and_creature(subject: tuple[str, ...]) -> bool:
    """A dual Land+Creature subject (the anthem/maker shape — Sylvan Advocate)."""
    return "Land" in subject and "Creature" in subject


def _land_creatures_matter(tree: ConceptTree) -> list[Signal]:
    """A land-creatures build — anthem over Land+Creature, or a land-animator.

    Mirrors ``_signals_ir`` line ~7720. Two arms read off the typed substrate:

    * **anthem** — a pump / grant-keyword / set-P/T modification (static) OR a
      ``make_token`` effect whose subject is a dual Land+Creature (Sylvan Advocate,
      Jyoti).
    * **animator** — a static ability turning a Land subject into a creature
      (Living Plane), via :func:`_is_creature_animator` (granularity b).
    """
    for unit in tree.units:
        for concept in unit.statics:
            if concept.concept in (
                "pump",
                "grant_keyword",
                "set_pt",
            ) and _has_land_and_creature(concept.subject):
                return [
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                ]
        for concept in unit.effect_concepts("make_token"):
            if _has_land_and_creature(concept.subject):
                return [
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                ]
        if _is_creature_animator(unit):
            return [Signal("land_creatures_matter", "you", "", "", tree.name, "high")]
    return []


_LANES = (
    _win_lose_game,
    _discard_makers,
    _spell_copy_makers,
    _token_maker,
    _draw_matters,
    _land_creatures_matter,
)


def extract_crosswalk_signals(
    tree: ConceptTree, *, keys: frozenset[str] = PORTED_KEYS
) -> list[Signal]:
    """Run the ported crosswalk lanes over one concept tree; dedupe by ident.

    Returns the ``Signal`` list for the ported batch, sliced to ``keys``, with the
    whole-card ``spell_copy_makers`` → ``spellcast_matters`` reconciliation applied
    (granularity c — mirrors ``signals.py`` lines 185-188: a spell-copier wants a
    dense instant/sorcery base, so a ``spellcast_matters`` LOW is cross-opened when
    absent).
    """
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(sig: Signal) -> None:
        if sig.key not in keys:
            return
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(sig)

    for lane in _LANES:
        for sig in lane(tree):
            add(sig)

    # Whole-card reconciliation (granularity c): cross-open spellcast_matters LOW
    # from a spell-copier that has no native spellcast signal in this batch.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        add(Signal("spellcast_matters", "you", "", "", tree.name, "low"))

    return out
