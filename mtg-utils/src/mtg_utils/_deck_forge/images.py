"""Scryfall image-URL extraction for the deck-forge surface.

The UI references Scryfall-hosted art by URL (no local hosting). We expose only the
sizes the SPA actually uses: ``small`` (grid thumbnails), ``normal`` (card preview),
and ``art_crop`` (banner art). Double-faced cards keep their art under ``card_faces``
rather than the top level — we use the front face for those sizes AND, when there are
two or more faces with art, expose every face's ``normal`` image under ``faces`` so
the preview can show both sides.
"""

from __future__ import annotations

_WANTED = ("small", "normal", "art_crop")


def image_urls(card: dict) -> dict | None:
    """Return the ``{size: url}`` subset the UI uses (plus ``faces`` for DFCs), or
    ``None`` if the card lacks art.

    Prefers the card's top-level ``image_uris``; for double-faced layouts (no
    top-level art) it uses the front face's ``image_uris``. When the card has 2+
    faces that carry their own art, a ``faces`` list of ``{name, normal}`` is added
    so the surface can render both sides.
    """
    faces = card.get("card_faces") or []
    uris = card.get("image_uris")
    if not uris and faces:
        uris = faces[0].get("image_uris")
    if not uris:
        return None
    projected: dict = {size: uris[size] for size in _WANTED if uris.get(size)}
    if not projected:
        return None
    face_imgs = [
        {
            "name": face.get("name", ""),
            "normal": (face.get("image_uris") or {})["normal"],
        }
        for face in faces
        if (face.get("image_uris") or {}).get("normal")
    ]
    if len(face_imgs) >= 2:
        projected["faces"] = face_imgs
    return projected
