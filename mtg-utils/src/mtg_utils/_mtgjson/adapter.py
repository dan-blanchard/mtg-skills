"""Pure per-card MTGJSON → Scryfall-record translation (no I/O).

Every function here is total over a single MTGJSON ``Card (Set)`` (or a small group
of face-entries forming one physical card) and returns the Scryfall-shaped fragment
the downstream code reads. The orchestration that flattens whole files lives in
``load``.

Shapes verified against live MTGJSON v5.3.0 (Arlinn, Sunfall, Human token) — see the
mapping spec. The contract is parity with a Scryfall ``default-cards`` record: a
multi-face card joins every face's type with " // " at the top level and leaves
top-level ``oracle_text`` / ``mana_cost`` / ``image_uris`` empty so ``get_oracle_text``
/ ``get_mana_cost`` fold ``card_faces`` (signals see the whole card).
"""

from __future__ import annotations

# The full legality-format universe. MTGJSON OMITS not-legal formats, so the adapter
# fills every absent key with "not_legal" — matching Scryfall, whose records carry
# every format. These 20 are MTGJSON's emitted set; they cover every format any
# consumer reads via ``format_config`` (Scryfall's extra ``oldschool`` / ``tlr`` are
# read by nothing). Values are lowercased (MTGJSON Capitalizes them).
_LEGALITY_FORMATS: tuple[str, ...] = (
    "alchemy",
    "brawl",
    "commander",
    "duel",
    "future",
    "gladiator",
    "historic",
    "legacy",
    "modern",
    "oathbreaker",
    "pauper",
    "paupercommander",
    "penny",
    "pioneer",
    "predh",
    "premodern",
    "standard",
    "standardbrawl",
    "timeless",
    "vintage",
)

# Scryfall CDN sizes the codebase reads (see ``_deck_forge/images.py``). All are .jpg.
_IMAGE_SIZES: tuple[str, ...] = ("small", "normal", "art_crop")

# MTGJSON ``availability`` → Scryfall ``games``. Drop the dead digital clients
# (dreamcast/shandalar) Scryfall never lists.
_GAMES = {"paper", "arena", "mtgo"}

# Scryfall populates top-level power/toughness/mana_cost/colors for multi-face cards
# that are a SINGLE physical card (flip/adventure creatures, split spells); a true
# two-face card (transform/modal_dfc/meld/reversible) carries them only on card_faces.
# Verified field-by-field against live Scryfall (see the mapping spec).
_TOP_PT_LAYOUTS = frozenset({"flip", "adventure"})  # creature permanent → top P/T
_FRONT_COST_LAYOUTS = frozenset({"flip"})  # one frame, one cost
_JOINED_COST_LAYOUTS = frozenset({"split", "aftermath", "adventure"})  # "A // B"
_TOP_COLORS_LAYOUTS = frozenset({"flip", "adventure", "split", "aftermath"})


def normalize_legalities(leg: dict | None) -> dict:
    """Lowercase MTGJSON legality values and fill omitted formats with ``not_legal``."""
    leg = leg or {}
    return {
        fmt: leg[fmt].lower() if fmt in leg else "not_legal"
        for fmt in _LEGALITY_FORMATS
    }


# Most-permissive wins when aggregating a format's status across printings.
_LEG_RANK = {"legal": 3, "restricted": 2, "banned": 1, "not_legal": 0}


def aggregate_legalities(per_printing: list[dict | None]) -> dict:
    """Collapse per-printing MTGJSON legalities to an oracle-level Scryfall dict.

    MTGJSON legality is per-printing, so an oversized / 30th-Anniversary / gold-border
    printing reads ``not_legal`` for a format the card is otherwise legal in (Karn,
    Silver Golem: 5 Legal printings + 2 oversized). Scryfall reports one oracle-level
    status, so we take the most-permissive value across all of a card's printings
    (legal > restricted > banned > not_legal) and fill omitted formats with not_legal.
    """
    acc: dict[str, str] = {}
    for leg in per_printing:
        for fmt, status in (leg or {}).items():
            s = status.lower()
            if _LEG_RANK.get(s, 0) > _LEG_RANK.get(acc.get(fmt, "not_legal"), 0):
                acc[fmt] = s
    return {fmt: acc.get(fmt, "not_legal") for fmt in _LEGALITY_FORMATS}


# Arena-digital-only formats: a card can't be legal in one without an Arena printing.
# MTGJSON occasionally marks a paper-only card legal here (Lord of Atlantis, pw24);
# Scryfall — which tracks Arena availability precisely — does not. Gate on availability.
_ARENA_ONLY_FORMATS = frozenset(
    {"alchemy", "brawl", "historic", "timeless", "standardbrawl"}
)


def gate_arena_formats(legalities: dict, *, arena_available: bool) -> dict:
    """Force Arena-only formats to ``not_legal`` for a card with no Arena printing."""
    if arena_available:
        return legalities
    return {
        fmt: ("not_legal" if fmt in _ARENA_ONLY_FORMATS else status)
        for fmt, status in legalities.items()
    }


def image_uris(scryfall_id: str | None, *, face: str = "front") -> dict | None:
    """Reconstruct the Scryfall CDN ``{size: url}`` map from a print's ``scryfallId``.

    ``https://cards.scryfall.io/<size>/<front|back>/<id[0]>/<id[1]>/<id>.jpg`` — the
    public, stable scheme (the ``?<timestamp>`` query Scryfall appends is optional).
    """
    if not scryfall_id or len(scryfall_id) < 2:
        return None
    a, b = scryfall_id[0], scryfall_id[1]
    base = "https://cards.scryfall.io"
    return {
        size: f"{base}/{size}/{face}/{a}/{b}/{scryfall_id}.jpg" for size in _IMAGE_SIZES
    }


def _latest(leaf: dict | None) -> str | None:
    """The price for the most recent date in a ``{date: float}`` leaf, as a string
    (Scryfall prices are strings; ``extract_price`` calls ``float()`` either way)."""
    if not leaf:
        return None
    date = max(leaf)
    val = leaf[date]
    return None if val is None else str(val)


def prices(uuid: str | None, price_index: dict) -> dict:
    """Map an MTGJSON AllPrices(Today) entry to Scryfall's flat ``prices`` dict.

    Paths: ``paper.tcgplayer.retail.{normal,foil,etched}`` → usd / usd_foil /
    usd_etched; ``paper.cardmarket.retail.{normal,foil}`` → eur / eur_foil;
    ``mtgo.cardhoarder.retail.normal`` → tix. Absent prices are omitted (Scryfall
    uses ``null``; downstream treats missing the same way).
    """
    entry = price_index.get(uuid or "") or {}
    paper = entry.get("paper") or {}
    mtgo = entry.get("mtgo") or {}
    tcg = (paper.get("tcgplayer") or {}).get("retail") or {}
    cm = (paper.get("cardmarket") or {}).get("retail") or {}
    ch = (mtgo.get("cardhoarder") or {}).get("retail") or {}
    out = {
        "usd": _latest(tcg.get("normal")),
        "usd_foil": _latest(tcg.get("foil")),
        "usd_etched": _latest(tcg.get("etched")),
        "eur": _latest(cm.get("normal")),
        "eur_foil": _latest(cm.get("foil")),
        "tix": _latest(ch.get("normal")),
    }
    return {k: v for k, v in out.items() if v is not None}


def _part(component: str, rec: dict, *, prefer_face: bool = False) -> dict:
    ids = rec.get("identifiers") or {}
    # Tokens use the combined name ("Incubator // Phyrexian" for a DFC token, matching
    # Scryfall); meld components use the singular face name (the piece/result name).
    name = (
        (rec.get("faceName") or rec.get("name", ""))
        if prefer_face
        else rec.get("name", "")
    )
    return {
        "component": component,
        "id": ids.get("scryfallId"),
        "name": name,
        "type_line": rec.get("type", ""),
        "oracle_id": ids.get("scryfallOracleId"),
    }


def token_part(token_rec: dict) -> dict:
    """A Scryfall-style ``token`` all_parts component for a token record."""
    return _part("token", token_rec)


def meld_parts(mj_card: dict, card_by_uuid: dict | None) -> list:
    """``meld_result`` / ``meld_part`` components from a meld card's ``otherFaceIds``.

    A piece (one link) emits a ``meld_result``; the result (2+ links) emits a
    ``meld_part`` per piece. Read by ``production`` (excludes meld results from the
    commander pool) and the meld_pair signal. Resolved via ``card_by_uuid``.
    """
    if mj_card.get("layout") != "meld" or not card_by_uuid:
        return []
    links = mj_card.get("otherFaceIds") or []
    component = "meld_part" if len(links) >= 2 else "meld_result"
    return [
        _part(component, card_by_uuid[u], prefer_face=True)
        for u in links
        if u in card_by_uuid
    ]


def card_face(mj_face: dict) -> dict:
    """One Scryfall ``card_faces[]`` entry from an MTGJSON face record."""
    side = mj_face.get("side") or "a"
    cdn_face = "front" if side == "a" else "back"
    ids = mj_face.get("identifiers") or {}
    face = {
        "name": mj_face.get("faceName") or mj_face.get("name", ""),
        "oracle_text": mj_face.get("text", "") or "",
        "type_line": mj_face.get("type", "") or "",
        "mana_cost": mj_face.get("manaCost", "") or "",
        "colors": mj_face.get("colors") or [],
        "keywords": mj_face.get("keywords") or [],
    }
    for k_out, k_in in (
        ("power", "power"),
        ("toughness", "toughness"),
        ("loyalty", "loyalty"),
        ("defense", "defense"),
    ):
        if mj_face.get(k_in) is not None:
            face[k_out] = mj_face[k_in]
    img = image_uris(ids.get("scryfallId"), face=cdn_face)
    if img:
        face["image_uris"] = img
    return face


def _union(faces: list[dict], key: str) -> list:
    seen: list = []
    for f in faces:
        for v in f.get(key) or []:
            if v not in seen:
                seen.append(v)
    return seen


def translate_card(
    faces: list[dict],
    *,
    price_index: dict | None = None,
    token_parts: list | None = None,
    card_by_uuid: dict | None = None,
    legalities_index: dict | None = None,
    set_meta: dict | None = None,
) -> dict:
    """Translate one physical card (1 entry, or 2+ face-entries) to a Scryfall dict.

    ``token_parts`` is the precomputed oracle-level ``token`` all_parts list for this
    card (built in ``load.flatten`` so a token-less promo printing still carries the
    full token set). ``set_meta`` carries the set-level ``set_type`` / ``set_name`` /
    ``released_at`` the AllPrintings per-card record lacks.
    """
    price_index = price_index or {}
    faces = sorted(faces, key=lambda f: f.get("side") or "a")
    front = faces[0]
    ids = front.get("identifiers") or {}
    oracle_id = ids.get("scryfallOracleId")
    multi = len(faces) > 1
    layout = front.get("layout")
    # Oracle-level legalities (aggregated across printings) when available, else this
    # printing's own — see aggregate_legalities for why per-printing isn't enough.
    legalities = (legalities_index or {}).get(oracle_id)
    if legalities is None:
        legalities = normalize_legalities(front.get("legalities"))

    # A multi-face card's name is the combined "A // B" (matches Scryfall). A single
    # entry that still carries a faceName is a meld piece — Scryfall names it solo.
    name = front.get("name", "")
    if not multi and front.get("faceName"):
        name = front["faceName"]

    rec: dict = {
        "oracle_id": oracle_id,
        "id": ids.get("scryfallId"),
        "name": name,
        "type_line": " // ".join(f.get("type", "") or "" for f in faces),
        # Scryfall cmc is always a float (0.0 for lands/tokens); MTGJSON omits manaValue
        # on tokens/objects → default 0.0 so mana_audit / curve never see None.
        "cmc": front.get("manaValue") or 0.0,
        "color_identity": front.get("colorIdentity") or [],
        "keywords": _union(faces, "keywords"),
        "legalities": legalities,
        "rarity": front.get("rarity"),
        "set": (front.get("setCode") or "").lower(),
        "collector_number": front.get("number"),
        "layout": layout,
        "games": [g for g in (front.get("availability") or []) if g in _GAMES],
        "finishes": front.get("finishes") or [],
        "game_changer": bool(front.get("isGameChanger")),
        # Pre-split arrays — new, used to harden the _subtypes precision gate.
        "types": front.get("types") or [],
        "subtypes": front.get("subtypes") or [],
        "supertypes": front.get("supertypes") or [],
    }
    # colors: a single-face card's own; for multi-face, only the single-permanent /
    # split layouts where Scryfall unions them (transform/modal_dfc omit it).
    if not multi or layout in _TOP_COLORS_LAYOUTS:
        rec["colors"] = _union(faces, "colors")
    # produced_mana: union, omitted when empty (Scryfall omits it on non-producers).
    produced = _union(faces, "producedMana")
    if produced:
        rec["produced_mana"] = produced
    if front.get("colorIndicator"):
        rec["color_indicator"] = front["colorIndicator"]
    if front.get("edhrecRank") is not None:
        rec["edhrec_rank"] = front["edhrecRank"]
    # Arena name aliasing (mark-owned): printed/flavor names when present.
    if front.get("printedName"):
        rec["printed_name"] = front["printedName"]
    if front.get("flavorName"):
        rec["flavor_name"] = front["flavorName"]

    if multi:
        # Faces carry text/cost/art; top-level oracle_text stays empty so get_* fold.
        rec["card_faces"] = [card_face(f) for f in faces]
        # Scryfall keeps top-level P/T for single-permanent multi-face (flip/adventure)
        # and a mana_cost (front for flip, joined "A // B" for adventure/split).
        if layout in _TOP_PT_LAYOUTS:
            for k_out, k_in in (
                ("power", "power"),
                ("toughness", "toughness"),
                ("loyalty", "loyalty"),
            ):
                if front.get(k_in) is not None:
                    rec[k_out] = front[k_in]
        if layout in _FRONT_COST_LAYOUTS:
            rec["mana_cost"] = front.get("manaCost", "") or ""
        elif layout in _JOINED_COST_LAYOUTS:
            rec["mana_cost"] = " // ".join(f.get("manaCost", "") or "" for f in faces)
    else:
        rec["oracle_text"] = front.get("text", "") or ""
        rec["mana_cost"] = front.get("manaCost", "") or ""
        for k_out, k_in in (
            ("power", "power"),
            ("toughness", "toughness"),
            ("loyalty", "loyalty"),
            ("defense", "defense"),
        ):
            if front.get(k_in) is not None:
                rec[k_out] = front[k_in]
        img = image_uris(ids.get("scryfallId"))
        if img:
            rec["image_uris"] = img

    if set_meta:
        rec["set_type"] = set_meta.get("set_type")
        rec["set_name"] = set_meta.get("set_name")
        rec["released_at"] = set_meta.get("released_at")

    parts = list(token_parts or []) + meld_parts(front, card_by_uuid)
    if parts:
        rec["all_parts"] = parts
    prices_dict = prices(front.get("uuid"), price_index)
    if prices_dict:
        rec["prices"] = prices_dict
    return rec
