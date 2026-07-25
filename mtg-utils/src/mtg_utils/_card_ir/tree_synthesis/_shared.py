"""Cross-family helpers shared by every synthesis-arm module.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
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
