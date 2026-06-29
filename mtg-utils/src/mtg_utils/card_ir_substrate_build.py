"""Console-script entry for ``build-card-ir-substrate`` (ADR-0035, Stage 1).

Thin wrapper over the gated phase-mirror substrate builder. NEVER CI.
"""

from __future__ import annotations

from mtg_utils._card_ir.mirror.build import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
