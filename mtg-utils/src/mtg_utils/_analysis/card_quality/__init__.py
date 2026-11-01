"""Theme-card quality reads (ADR-0063): how strong a card is on its own text.

One read per card type, each fitted on the guide pairs of
``docs/plans/precon-audit/theme_pairs.py`` (a guide add against each on-plan card
the reads-first theme order put above it): :mod:`creature`,
:mod:`noncreature_permanent` (artifacts, enchantments, planeswalkers, battles)
and :mod:`spell` (instants and sorceries). :func:`quality` picks the read by the
card's front face and scores it; a land, or a card no read sees, is ``None`` —
never a low number. The reads are pure: no play-rate, no price, no deck.

:func:`theme_strength` is a second read per type, for ordering a theme page:
each type module's ``THEME_READ`` (its ``THEME_WEIGHTS``), fitted on pairs no
tuner order chose (a guide's adds against its cuts, and against the more-played
on-plan cards the live play-rate order ranked above them). A module without a
``THEME_READ`` scores ``None``. :func:`quality` is unchanged.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

from mtg_utils._analysis.card_quality import creature, noncreature_permanent, spell
from mtg_utils._analysis.job_quality._common import faces

#: One type's read: each module has its own dataclass with ``type_name`` and
#: ``score(record) -> float | None``.
QualityRead = creature.QualityRead | noncreature_permanent.QualityRead

#: The reads by type name.
READS: Mapping[str, QualityRead] = {
    creature.READ.type_name: creature.READ,
    noncreature_permanent.READ.type_name: noncreature_permanent.READ,
    spell.READ.type_name: spell.READ,
}

_PERMANENT_TYPES = ("Artifact", "Enchantment", "Planeswalker", "Battle")


def type_name(record: Mapping) -> str | None:
    """Which read a card's front face takes: a creature (an artifact creature is
    a creature) first, then an instant or sorcery, then a noncreature permanent;
    a land or anything else ``None``."""
    front = faces(dict(record))[0]
    if "Land" in front:
        return None
    if "Creature" in front:
        return creature.READ.type_name
    if "Instant" in front or "Sorcery" in front:
        return spell.READ.type_name
    if any(t in front for t in _PERMANENT_TYPES):
        return noncreature_permanent.READ.type_name
    return None


def quality(record: dict) -> float | None:
    """The card's quality score under its type's read (log-odds of being the
    guide's pick among on-plan cards; higher is stronger), or ``None``."""
    name = type_name(record)
    if name is None:
        return None
    return READS[name].score(record)


#: The type modules by type name: where :func:`theme_strength` finds each one's
#: ``THEME_READ``.
_MODULES = {
    creature.READ.type_name: creature,
    noncreature_permanent.READ.type_name: noncreature_permanent,
    spell.READ.type_name: spell,
}


def theme_strength(record: dict) -> float | None:
    """The card's theme-strength score under its type's ``THEME_READ`` (log-odds
    of being the guide's pick over another on-plan card of its type on a theme
    page; fitted on the guides' add-vs-cut pairs and the live play-rate order's
    misses, not on an order's own picks; higher is stronger), or ``None`` for a
    card no theme read sees — a land, a type whose module has no ``THEME_READ``,
    or a card that module's read can't see. The job-page blend's
    :func:`quality` is a separate read."""
    name = type_name(record)
    read = None if name is None else getattr(_MODULES[name], "THEME_READ", None)
    return None if read is None else read.score(record)


def quality_factor(record: dict) -> float:
    """``quality`` as a factor in (0, 1) a synergy score is multiplied by: the
    logistic of the score; a card no read sees is neutral (0.5)."""
    score = quality(record)
    if score is None:
        return 0.5
    return 1.0 / (1.0 + math.exp(-score))


def attach_sidecars(bulk_path: Path | None) -> None:
    """Persist every read's scores beside the bulk (see each module's
    ``attach_sidecar``)."""
    creature.attach_sidecar(bulk_path)
    noncreature_permanent.attach_sidecar(bulk_path)
    spell.attach_sidecar(bulk_path)
