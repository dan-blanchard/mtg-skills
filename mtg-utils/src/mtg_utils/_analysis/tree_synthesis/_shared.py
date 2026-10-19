"""Cross-family helpers shared by every synthesis-arm module.

Part of the :mod:`mtg_utils._analysis.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir._substrate_purity import SynthesizedNode
from mtg_utils._card_ir.crosswalk import ConceptNode

# ── the synthetic concept-node builder ────────────────────────────────────────
# ``SynthesizedNode`` lives in ``_substrate_purity`` (alongside the invariant it is
# exempt from — avoids an import cycle) and is re-exported here as this stage's
# public marker.


def _synthetic_concept(
    *, arm_id: str, concept: str, scope: str, subject: tuple[str, ...], desc: str
) -> ConceptNode:
    """Build a synthetic effect-role :class:`ConceptNode` for one gap."""
    return ConceptNode(
        concept=concept,
        node=SynthesizedNode(arm_id=arm_id, description=desc),
        role="effect",
        scope=scope,
        subject=subject,
        raw="",
    )


# ── shared oracle grounding (reminder-paren strip) ────────────────────────────

_REMINDER = re.compile(r"\([^)]*\)")


# ── the card's own name read as "~" ──────────────────────────────────────────
# A bucket-B keyword-word scan over ``tree.oracle`` also matches the card's OWN
# NAME where the oracle names itself ("Impending Flux deals X damage …", "Exile
# The Book of Exalted Deeds: …", "Whenever Exalted Angel deals damage …") — a
# name is not the keyword. Masks the full name, then the short name before a
# legendary's comma ("Jhoira" for "Jhoira, Weatherlight Captain"), the forms an
# oracle names itself by.


def _unnamed_oracle(oracle: str, name: str) -> str:
    """``oracle`` reminder-stripped, with the card's own name read as "~"."""
    text = _REMINDER.sub(" ", oracle or "")
    for form in (name, name.split(",", maxsplit=1)[0].strip()):
        if form:
            text = text.replace(form, "~")
    return text
