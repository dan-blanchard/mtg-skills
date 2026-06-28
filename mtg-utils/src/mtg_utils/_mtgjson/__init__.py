"""MTGJSON → Scryfall-record adapter.

The card-data source is MTGJSON ``AllPrintings`` (the per-printing file). This
package translates each MTGJSON ``Card (Set)`` into the same Scryfall-shaped dict
the rest of the codebase already reads, so the ~30 downstream call sites stay
unchanged. Scryfall's HTTP API is retained only as a thin per-card fallback for
the rare card MTGJSON does not carry.

``adapter`` holds the pure per-card translation (legalities normalize, image-URL
reconstruction, price join, DFC face collapse, token graph). ``load`` flattens an
``AllPrintings`` document + an ``AllPricesToday`` document into the Scryfall-shaped
list ``bulk_loader`` caches.
"""

from __future__ import annotations
