"""Console-script entry for ``build-card-ir`` (thin wrapper over the builder)."""

from __future__ import annotations

from mtg_utils._card_ir.build import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
