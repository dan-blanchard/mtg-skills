"""Scryfall image-URL extraction for the deck-forge surface.

The UI references Scryfall-hosted art by URL (no local hosting). We expose only the
sizes the SPA actually uses: ``small`` (grid thumbnails), ``normal`` (card preview),
and ``art_crop`` (banner art). Double-faced cards keep their art under
``card_faces`` rather than the top level, so we fall back to the front face.
"""

from __future__ import annotations

_WANTED = ("small", "normal", "art_crop")


def image_urls(card: dict) -> dict[str, str] | None:
    """Return the ``{size: url}`` subset the UI uses, or ``None`` if the card lacks art.

    Prefers the card's top-level ``image_uris``; for double-faced layouts (no
    top-level art) it uses the front face's ``image_uris``.
    """
    uris = card.get("image_uris")
    if not uris:
        faces = card.get("card_faces") or []
        if faces:
            uris = faces[0].get("image_uris")
    if not uris:
        return None
    projected = {size: uris[size] for size in _WANTED if uris.get(size)}
    return projected or None
