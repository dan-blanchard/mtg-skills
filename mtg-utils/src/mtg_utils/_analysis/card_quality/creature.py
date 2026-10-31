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
    if "Creature" not in faces(card)[0]:
        return None
    trees = signal_trees_for(card, bulk=card)
    if not trees:
        return None
    front = trees[0]
    if front.is_text_only and front.oracle and not front.card_keywords:
        return None  # text phase parsed none of: its abilities would count 0
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
    evasion = any(evasion_keyword_kind(k) for k in kws) or is_evasive_body(front)
    return {
        "share": min(cast_cost(card) / max(len(abilities), 1), _SHARE_CAP),
        "engines": float(min(len(engines), 4)),
        "dies": float(dies),
        "evasion": float(evasion),
        "defender": float("defender" in kws),
        "ramp": float(_JOB_READS["ramp"].score(card) is not None),
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
        it. Memoized per oracle_id for the module's own read (another
        ``QualityRead`` with its own features or weights is scored live)."""
        oid = record.get("oracle_id")
        memoized = bool(oid) and self is READ
        if memoized and (hit := _SCORES.get(oid)) is not MISSING:
            return cast("float | None", hit)
        feats = self.features(record)
        score = (
            None
            if feats is None
            else round(sum(self.weights[k] * v for k, v in feats.items()), 3)
        )
        if memoized and (feats is not None or signal_trees_for(record, bulk=record)):
            _SCORES.put(oid, score)  # never a None read before phase data is there
        return score


READ = QualityRead("creature", features, WEIGHTS)
