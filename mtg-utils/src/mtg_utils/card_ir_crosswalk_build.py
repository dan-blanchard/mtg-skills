"""Console-script entry for ``build-card-ir-crosswalk`` (ADR-0035, Stage-3a).

Thin wrapper over the crosswalk-backed sidecar builder — the flag-ON backend for
``ir_for``. Gated dev step, never CI.
"""

from __future__ import annotations

from mtg_utils._card_ir.build import main_crosswalk

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_crosswalk())
