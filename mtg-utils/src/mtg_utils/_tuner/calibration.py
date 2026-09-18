"""Per-family calibration of the tuner's floors.

The metrics' floors — front-load, top-end, focus tiers, closers, protection, the
voltron read — are Shape-scaled tuner knobs stated at one deck size; a
:class:`Calibration` carries them for a format family (``Format.family``) and scales
them to the deck's size from the family's own base, so a 60-card deck is measured
against 60-card norms rather than 0.6 of a Commander deck's. The Commander numbers
are the ones every readout was tuned on; the constructed and limited rows are the
honest minimum a 60- or 40-card deck is held to. The Commander-only axes —
commander fit, grant coverage, the bracket gate, the partner / commander
suggestion, edhrec play-rate as a quality read (a paper-EDH population) — are
switched off by ``commander_axes`` / ``playrate_meaningful`` rather than left to
no-op silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mtg_utils._analysis.budgets import Template, template_for


@dataclass(frozen=True)
class Calibration:
    family: str
    #: Shape → desired front-load (cmc<=2 nonland) at ``base_size``.
    front_want: Mapping[str, int]
    #: The (low, mid, high) ramp wants by avg-MV band at ``base_size``, or None when
    #: ramp is not an axis for the family (a Burn deck at zero ramp is fine).
    ramp_want: tuple[int, int, int] | None
    #: (min, max) six-plus drops at ``base_size``.
    top_end: tuple[int, int]
    focus_main: int
    focus_sub: int
    focus_emerging: int
    spine_led: int
    #: Shape → (min, max) dedicated closers at ``base_size`` (life-scaled downstream).
    wincon_target: Mapping[str, tuple[int, int]]
    protection_target: int
    #: Equip/aura density that reads as a voltron plan, or None: no voltron read.
    voltron_pieces: int | None
    #: The Commander-only axes: commander fit, grant coverage, bracket, suggestions.
    commander_axes: bool
    #: Whether edhrec play-rate is a meaningful quality / fringe read here.
    playrate_meaningful: bool
    default_shape: str = field(default="midrange")

    @property
    def template(self) -> Template:
        """The family's budgets template — the one place its base size lives."""
        return template_for(self.family)

    @property
    def base_size(self) -> int:
        """The deck size every floor here is stated at: the family template's, so
        the two can never disagree about what "per deck" means."""
        return self.template.base_size

    def scaled(self, value: int, deck_size: int) -> int:
        """``value`` (stated at ``base_size``) at ``deck_size``, Python-rounded."""
        return round(value * deck_size / self.base_size)


COMMANDER = Calibration(
    family="commander",
    front_want={"aggro": 18, "midrange": 14, "control": 10, "combo": 12},
    ramp_want=(9, 10, 12),
    top_end=(2, 8),
    focus_main=20,
    focus_sub=10,
    focus_emerging=5,
    spine_led=8,
    wincon_target={
        "aggro": (4, 6),
        "midrange": (3, 6),
        "control": (2, 4),
        "combo": (2, 3),
    },
    protection_target=5,
    voltron_pieces=4,
    commander_axes=True,
    playrate_meaningful=True,
)

CONSTRUCTED = Calibration(
    family="constructed",
    front_want={"aggro": 16, "midrange": 12, "control": 8, "combo": 10},
    ramp_want=None,
    top_end=(0, 4),
    focus_main=12,
    focus_sub=6,
    focus_emerging=3,
    spine_led=6,
    wincon_target={
        "aggro": (4, 8),
        "midrange": (3, 6),
        "control": (2, 4),
        "combo": (2, 3),
    },
    protection_target=3,
    voltron_pieces=None,
    commander_axes=False,
    playrate_meaningful=False,
)

LIMITED = Calibration(
    family="limited",
    front_want={"aggro": 8, "midrange": 8, "control": 8, "combo": 8},
    ramp_want=None,
    top_end=(0, 2),
    focus_main=8,
    focus_sub=4,
    focus_emerging=2,
    spine_led=4,
    wincon_target={
        "aggro": (2, 4),
        "midrange": (2, 4),
        "control": (2, 4),
        "combo": (2, 4),
    },
    protection_target=0,
    voltron_pieces=None,
    commander_axes=False,
    playrate_meaningful=False,
)

CALIBRATIONS: dict[str, Calibration] = {
    c.family: c for c in (COMMANDER, CONSTRUCTED, LIMITED)
}


def calibration_for(family: str) -> Calibration:
    """The calibration for a format family (``Format.family``)."""
    try:
        return CALIBRATIONS[family]
    except KeyError:
        msg = f"no calibration for family {family!r}"
        raise ValueError(msg) from None
