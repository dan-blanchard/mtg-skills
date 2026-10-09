"""Report-facing text: a card's ability as words, for a tool's readout (cut-check's
trigger and ability lists, the commander-multiplier clauses). Display only — no read
decides anything from this text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_utils._card_ir.crosswalk.cost_text import cost_text
from mtg_utils._card_ir.crosswalk.reads import tag_of
from mtg_utils._card_ir.mirror.runtime import MISSING

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk.core import AbilityUnit


def unit_text(unit: AbilityUnit, name: str) -> str:
    """One ability of a card in words, for a report: phase's own description with
    the card's name for ``~``. Phase leaves a few without one — a basic land's
    intrinsic mana ability, a modal activated ability (Umezawa's Jitte), some
    keyword abilities (outlast) — and those read as their cost and modes, keyword
    or effect ("Remove counter 1: Equipped creature gets +2/+2 … • You gain 2
    life")."""
    desc = getattr(unit.node, "description", None)
    if isinstance(desc, str) and desc.strip():
        return desc.replace("~", name).strip()
    modal = getattr(unit.node, "modal", None)
    modes = getattr(modal, "mode_descriptions", None)
    if isinstance(modes, list) and modes:
        body = " • ".join(str(m).replace("~", name) for m in modes)
    else:
        body = tag_of(getattr(unit.node, "ability_tag", None)) or tag_of(
            getattr(unit.node, "effect", None)
        )
        body = "Add mana" if body == "Mana" else (body or "")
    cost = cost_text(getattr(unit.node, "cost", MISSING))
    return f"{cost}: {body}" if cost else body
