"""Creature quality: which of two on-plan creatures is the stronger card, read
off its own trees, cost and keywords (never play-rate, price or the deck).

Fitted on the 5,102 creature guide pairs of ``theme_pairs.py`` (126 guide adds,
24 precons; 2026-10-31): each pair is a guide add and an on-plan creature the
reads-first theme order put above it, weighted so every guide add counts once
per guide naming it. A pairwise logistic regression (L2) on the feature
differences, hand-rounded. ``docs/plans/precon-audit/quality_fit_creature.py``
re-runs the fit and the measurement.

Leave-one-deck-out pair accuracy (the fit before rounding): this read 0.66,
play-rate 0.58, mana value 0.50. The hand-rounded weights score 0.67 in sample.

The features, each in units of log-odds that the card is the guide's pick:

- ``share`` (+0.08 per mana): the mana the card costs per distinct ability it
  has, capped at 8. A card's cost pays for its whole text, so the same mana
  spread over several abilities buys less of each. Identical abilities count
  once: Goldspan Dragon's two "create a Treasure" triggers are one ability. The
  cost is the curve cost (``_common.cast_cost``: evoke and the other curve
  costs, Phyrexian mana paid with life).
- ``engines`` (-0.55 each, at most 4): the distinct engines, the abilities
  that work again and again. These are a trigger other than the card's own
  entering, dying or leaving, and an activation that works on the battlefield
  and doesn't sacrifice the card. Each needs its event to happen or mana paid
  every time, so two small engines are worth less than one. These pairs also
  hold a measurement bias: the theme order's synergy score counts each ability
  a card has, so a wordy card sits above the guide's pick. Part of this weight
  corrects that count, not card strength.
- ``dies`` (-1.0): a dies or leaves-the-battlefield trigger of its own (CR
  603.6c). It pays off only once the creature is gone.
- ``evasion`` (+0.55): an evasion ability on itself, a static ability that
  restricts what can block it (CR 509.1b). This means menace, shadow, fear,
  intimidate, skulk, horsemanship or landwalk (``evasion_keyword_kind``), or
  "can't be blocked" (``is_evasive_body``). Its combat triggers connect. Flying
  is left out as soft evasion, as the crosswalk does; the fit gave it nothing.
- ``defender`` (-2.4): a creature with defender can't attack (CR 702.3b). Rare
  (1% of the pairs' weight), hence the size.
- ``ramp`` (+0.40): the ramp job read scores it (``job_quality.ramp``). It
  makes mana, a Treasure or a land. Kept though it moves the cross-validated
  accuracy by less than its noise (0.66 without it): it is what makes
  Goldspan Dragon the stronger card than Firespitter Whelp.

Rejected by the fit, each scoring no better than chance alone or lowering the
cross-validated accuracy when added:

- power plus toughness, and per mana;
- flying, trample, deathtouch, lifelink, first strike, vigilance;
- haste;
- self-protection (hexproof, ward, indestructible, protection, "can't be
  countered");
- flash;
- draw, tokens and impulse draw;
- an enters trigger;
- a static effect on other permanents;
- replacement effects;
- legendary;
- the other job reads.

A creature the read can't see scores ``None``: a card phase has no trees for,
one whose front face has text but no ability or keyword phase parsed (its
abilities would count none), or one whose front face is no creature. ``None``
is never a low number.

**The theme-strength read** (:data:`THEME_READ`, :func:`theme_features`,
:data:`THEME_WEIGHTS`) is a second read beside :data:`READ`, which stays the job
pages' (ADR-0063's J2). It says which of two on-plan creatures a theme page
should rank first, and is fitted on two pair sets the reads-first order didn't
choose (2026-10-31, design 25 only): source A, a guide's add against the same
guide's cut of a creature (3,565 pairs, 310 deck-adds, 24 decks), and source B,
a guide add against each on-plan creature the live play-rate order put above it
on the same theme page (6,627 pairs, 160 deck-adds, 24 decks). Each source's
weights sum to one, every add counting once per guide naming it.
``docs/plans/precon-audit/strength_fit_creature.py`` re-runs the fit; its
docstring holds the table. Leave-one-deck-out pair accuracy, fitted on both
sources: A 0.668 (play-rate 0.574), B 0.616 (play-rate 0.000 by construction,
so chance, 0.5, is B's real bar). Fitted on one source and scored on the other:
A to B 0.606, B to A 0.664. The six features were chosen by forward selection
over 56 candidates, which saw every deck; with the selection itself inside the
leave-one-deck-out loop (at most six, ``strength_select_creature.py nested``)
it is A 0.616 and B 0.537: still above both bars, B's by little. 19 of the 25
folds chose the same first five (all but ``evasion``).

The features, in log-odds per unit that the card is the guide's pick:

- ``cost`` (-0.10 a mana, capped at 9): the curve cost (``_common.cast_cost``).
  A cheaper creature is out sooner and leaves mana for the rest of the plan.
- ``legendary`` (+0.60): the legendary supertype. The supertype
  itself only puts the permanent under the legend rule (CR 205.4d, 704.5j),
  so this is no strength the rules give: it is
  the pairs' verdict on both sources, most likely because a recent legendary
  creature carries more text for its cost than a common body. A proxy, kept
  because it holds on both sources.
- ``tutor`` (+2.4): the tutor job read scores it (``job_quality.tutor``: it
  finds a nonland card in your library, CR 701.23a). Rare (2% of the pairs'
  cards; Faerie Harbinger, Fauna Shaman, Ranger-Captain of Eos), hence the size.
- ``board_static`` (+0.60): a static ability of its own (CR 604.1) that affects
  something other than the card itself: a lord, a cost reduction, a rule for
  the opponents' creatures. It works on every card it reaches.
- ``attack_trigger`` (+0.70): a trigger on attacking (CR 508.3a), phase's
  "attacks" or "enters or attacks": value again each combat.
- ``evasion`` (+0.55): the same evasion as :func:`features`' (CR 509.1b).

The ADR-0063 features refitted on these sources take opposite signs on A and B
(``share``: cheaper per ability on A, dearer on B) and score A 0.618 but B 0.505
alone, 0.453 fitted on both: they read the old order's bias, not strength.
Body, power per mana, flying and the other combat keywords also split by
source; card-advantage effects, trigger counts and job reads agree in sign but
add nothing past these six.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtg_utils._analysis.job_quality import READS as _JOB_READS
from mtg_utils._analysis.job_quality._common import cast_cost, faces
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.write_back import MISSING, WriteBackSidecar, content_key
from mtg_utils._card_ir.crosswalk import (
    activated_ability_units,
    affected_tag,
    evasion_keyword_kind,
    is_evasive_body,
    normalised_keyword_name,
    static_mode_tag,
    targets_the_card,
    watches_itself,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree

#: Trigger events that fire once for the card itself when they watch it: its
#: own entering, dying, leaving, being sacrificed. The same events watching
#: other objects (Blood Artist's "another creature dies") repeat.
_ONCE_EVENTS = frozenset({"enters", "dies", "leaves", "sacrificed", "changes_zone"})
#: A dies or leaves-the-battlefield trigger (CR 603.6c).
_LEAVES_EVENTS = frozenset({"dies", "leaves"})
#: ``share``'s cap, in mana per ability.
_SHARE_CAP = 8.0


def _is_ability(u: AbilityUnit) -> bool:
    """A phase-parsed ability of the card's: anything with an effect or a
    static modification, or a static or replacement whose mode alone is its
    meaning ("can't be blocked", "can't block"). Synthesized units are the
    signal stage's, not the card's."""
    if u.origin == "synth":
        return False
    return bool(u.effects or u.statics) or u.origin in ("static", "replacement")


def _ability_key(u: AbilityUnit) -> tuple[str, frozenset[str]]:
    """What an ability does, so identical ones count once: its origin and its
    effect concepts, or its static modes."""
    did = frozenset(c.concept for c in u.effects)
    if not did:
        did = frozenset(str(static_mode_tag(sd)) for sd in u.static_defs())
    return u.origin, did


def _engines(tree: ConceptTree) -> Iterator[AbilityUnit]:
    """The abilities that work again and again: a trigger with an effect that
    doesn't watch the card's own entering, dying or leaving, and an activated
    ability with an effect that works on the battlefield
    (``activated_ability_units``, so encore, unearth and cycling are left out)
    whose cost doesn't sacrifice the card (Sakura-Tribe Elder)."""
    for u in tree.iter_units("trigger"):
        if u.effects and not (
            u.trigger_event in _ONCE_EVENTS and watches_itself(u.node)
        ):
            yield u
    for u in activated_ability_units(tree):
        if u.effects and not any(
            c.concept == "sacrifice" and targets_the_card(c) for c in u.costs
        ):
            yield u


def features(card: dict) -> dict[str, float] | None:
    """The creature read's features for ``card``, or ``None`` when its front
    face is no creature or phase has no trees for it."""
    trees = _readable_trees(card)
    if trees is None:
        return None  # (text phase parsed none of: its abilities would count 0)
    front = trees[0]
    units = [u for tree in trees for u in tree.units]
    abilities = {_ability_key(u) for u in units if _is_ability(u)}
    engines = {_ability_key(u) for tree in trees for u in _engines(tree)}
    dies = any(
        u.origin == "trigger"
        and u.effects
        and u.trigger_event in _LEAVES_EVENTS
        and watches_itself(u.node)
        for u in units
    )
    kws = [normalised_keyword_name(k) for k in front.card_keywords]
    return {
        "share": min(cast_cost(card) / max(len(abilities), 1), _SHARE_CAP),
        "engines": float(min(len(engines), 4)),
        "dies": float(dies),
        "evasion": float(_is_evasive(front)),
        "defender": float("defender" in kws),
        "ramp": float(_JOB_READS["ramp"].score(card) is not None),
    }


def _is_evasive(front: ConceptTree) -> bool:
    """An evasion ability on the card itself (``features``' ``evasion``)."""
    return any(
        evasion_keyword_kind(normalised_keyword_name(k)) for k in front.card_keywords
    ) or is_evasive_body(front)


def _readable_trees(card: dict) -> list[ConceptTree] | None:
    """The card's signal trees when its front face is a creature the reads can
    see: phase has trees for it, and its front face's text parsed to at least
    one ability or keyword."""
    if "Creature" not in faces(card)[0]:
        return None
    trees = signal_trees_for(card, bulk=card)
    if not trees:
        return None
    front = trees[0]
    if front.is_text_only and front.oracle and not front.card_keywords:
        return None
    return list(trees)


#: Trigger events of an attack trigger (CR 508.3a): "whenever [a creature]
#: attacks", and phase's combined "enters or attacks".
_ATTACK_EVENTS = frozenset({"attacks", "entersorattacks"})
#: ``cost``'s cap, in mana.
_COST_CAP = 9.0


def theme_features(card: dict) -> dict[str, float] | None:
    """The theme-strength read's features for ``card`` (see :data:`THEME_WEIGHTS`),
    or ``None`` when the reads can't see it (as for :func:`features`)."""
    trees = _readable_trees(card)
    if trees is None:
        return None
    front = trees[0]
    units = [u for tree in trees for u in tree.units if u.origin != "synth"]
    board_static = any(
        affected_tag(sd, u) != "SelfRef"
        for u in units
        if u.origin == "static"
        for sd in u.static_defs()
    )
    attack_trigger = any(
        u.origin == "trigger" and u.effects and u.trigger_event in _ATTACK_EVENTS
        for u in units
    )
    return {
        "cost": min(cast_cost(card), _COST_CAP),
        "legendary": float("Legendary" in front.card_supertypes),
        "tutor": float(_JOB_READS["tutor"].score(card) is not None),
        "board_static": float(board_static),
        "attack_trigger": float(attack_trigger),
        "evasion": float(_is_evasive(front)),
    }


#: Log-odds per feature unit that the card is the guide's pick (pairwise
#: logistic fit, 2026-10-31, rounded). The module docstring gives each one's
#: reasoning.
WEIGHTS: dict[str, float] = {
    "share": 0.08,
    "engines": -0.55,
    "dies": -1.0,
    "evasion": 0.55,
    "defender": -2.4,
    "ramp": 0.40,
}

#: The theme-strength read's log-odds per feature unit (pairwise logistic fit
#: on both pair sources, 2026-10-31, rounded). The theme-strength section of
#: the module docstring gives each one's reasoning.
THEME_WEIGHTS: dict[str, float] = {
    "cost": -0.10,
    "legendary": 0.60,
    "tutor": 2.4,
    "board_static": 0.60,
    "attack_trigger": 0.70,
    "evasion": 0.55,
}


#: Bumped for a change in what a persisted score means that the module's code
#: hash doesn't cover.
SIDECAR_VERSION = 1


def _content_key() -> str:
    """The code a score is computed by: the signal path and this module's
    import closure (``write_back.content_key``), so an edit to either makes old
    entries unreadable."""
    return content_key(
        f"creature_quality_version:{SIDECAR_VERSION}",
        "mtg_utils._analysis.card_quality.creature",
    )


#: ``<bulk>.creature-quality.pkl``: the per-card scores, persisted across
#: processes (a theme page scores every creature on it).
SIDECAR = WriteBackSidecar(".creature-quality.pkl", _content_key)
_SCORES = SIDECAR.memo("score")
_THEME_SCORES = SIDECAR.memo("theme_score")


def attach_sidecar(bulk_path: Path | None) -> bool:
    """Serve the scores from ``<bulk_path>.creature-quality.pkl`` and write
    back what this process computes at exit. ``False`` (no bulk) leaves them
    in-process only."""
    return SIDECAR.attach(bulk_path)


@dataclass(frozen=True)
class QualityRead:
    """One card type's quality read: its ``features`` and ``weights``."""

    type_name: str
    features: Callable[[dict], dict[str, float] | None]
    weights: Mapping[str, float]

    def score(self, record: dict) -> float | None:
        """How strong ``record`` is as a card of this type (higher is better):
        the weighted sum of its features, or ``None`` when the read can't see
        it. Memoized per oracle_id for the module's own reads, :data:`READ`
        and :data:`THEME_READ` (another ``QualityRead`` with its own features or
        weights is scored live)."""
        oid = record.get("oracle_id")
        memo = (
            _SCORES if self is READ else _THEME_SCORES if self is THEME_READ else None
        )
        memoized = bool(oid) and memo is not None
        if memoized and (hit := memo.get(oid)) is not MISSING:
            return cast("float | None", hit)
        feats = self.features(record)
        score = (
            None
            if feats is None
            else round(sum(self.weights[k] * v for k, v in feats.items()), 3)
        )
        if memoized and (feats is not None or signal_trees_for(record, bulk=record)):
            memo.put(oid, score)  # never a None read before phase data is there
        return score


READ = QualityRead("creature", features, WEIGHTS)
#: The theme-strength read: which of two on-plan creatures a theme page should
#: rank first (:data:`THEME_WEIGHTS`). Not the job pages' :data:`READ`.
THEME_READ = QualityRead("creature", theme_features, THEME_WEIGHTS)
