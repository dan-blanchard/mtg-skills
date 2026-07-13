"""Console-script entry for ``build-signals-index`` (task #90).

A tiny prebuild hook over ``_deck_forge.signals_index.load_signals_index`` —
every real production call site already builds the sidecar lazily on first
whole-pool touch (``card_search --preset``, deck-forge's commander-discovery
novelty sweep), so this CLI exists purely to pay that one-time ~2-4 min cost
up front (e.g. right after ``download-mtgjson``) instead of during a user's
first request. Gated dev/ops step, never CI (mirrors ``build-card-snapshot`` /
``build-card-ir-crosswalk``: needs the local bulk on disk).
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """CLI: ``build-signals-index`` — build/refresh the oracle_id -> signal
    idents sidecar for the default bulk file (``bulk_loader.default_bulk_path``)."""
    import argparse

    from mtg_utils._deck_forge.signals_index import load_signals_index
    from mtg_utils.bulk_loader import default_bulk_path

    parser = argparse.ArgumentParser(
        description="Build/refresh the oracle_id -> signal-idents sidecar "
        "(task #90) so the first whole-pool preset scan or commander-"
        "discovery sweep doesn't pay the one-time cost mid-request."
    )
    parser.parse_args(argv)

    bulk_path = default_bulk_path()
    if bulk_path is None:
        print(
            "No card-data bulk found. Run `download-mtgjson` first.",
            file=sys.stderr,
        )
        return 1

    index = load_signals_index(bulk_path)
    if index is None:
        print(f"Could not build a signals index for {bulk_path}.", file=sys.stderr)
        return 1

    print(f"Signals index ready: {len(index)} oracle_ids indexed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
