"""One consistent Scryfall name-indexing core (candidate 03).

Before this module, the canonical-name → DFC-face → Arena-alias keying mechanic was
hand-copied across ``scryfall_lookup._load_bulk_index``, ``build_rarity_index``,
``card_classify.build_card_lookup``, ``find_commanders``, ``deck.load_bulk_indexes``,
``card_search``, and ``mark_owned`` — each with *subtly inconsistent* rules (front-only
vs every-face DFC handling, ``str.lower`` vs NFKD folding vs none, priced-beats-None vs
not). Dual-faced cards in particular have surfaced repeated silent-lookup bugs. This
module makes the keying ONE implementation:

- **Folding is universal, not a knob.** Keys AND lookups go through
  ``normalize_card_name`` (NFKD + ASCII-fold + lowercase): people rarely type
  diacritics, so an ASCII query matches the real card — while a diacritic query still
  works (both fold to the same key). The stored record keeps its real, diacritic name
  for display, encapsulated in :class:`NameIndex` so call sites never fold by hand.
- **DFC handling is uniform.** Every face is indexed (``card_faces[]`` names, or the
  ``" // "`` split as a fallback), and a real standalone card wins its name over another
  card's face (canonical beats face beats Arena alias).

The genuinely per-caller policy stays as knobs on :func:`build_name_index`: the
acquisition-cost *reducer* (cheapest USD for paper / lowest rarity for Arena wildcards /
prefer-has-oracle for proxies / first-seen), the stored *value* projection, and the
*prefilter*.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from enum import Enum

from mtg_utils.names import normalize_card_name


class _Tier(Enum):
    """Key precedence: a canonical full name beats a face name beats an Arena alias."""

    CANONICAL = 1
    FACE = 2
    ALIAS = 3


def alias_keys(card: dict) -> list[tuple[str, _Tier]]:
    """The folded ``(key, tier)`` pairs a single card claims.

    CANONICAL: the full ``name``. FACE: every face name — from ``card_faces[]`` when
    present (covers MDFC / transform / flip / adventure / meld), else the ``" // "``
    split parts. ALIAS: Arena ``printed_name`` / ``flavor_name`` (English printings
    only, so a Japanese ``printed_name`` can't make a false match). Keys are folded.
    """
    name = card.get("name", "")
    out: list[tuple[str, _Tier]] = []
    if name:
        out.append((normalize_card_name(name), _Tier.CANONICAL))

    faces = card.get("card_faces") or []
    if faces:
        face_names = [f.get("name") or "" for f in faces]
    elif " // " in name:
        face_names = name.split(" // ")
    else:
        face_names = []
    for fname in face_names:
        if fname and fname != name:
            out.append((normalize_card_name(fname), _Tier.FACE))

    if card.get("lang", "en") == "en":
        for field in ("printed_name", "flavor_name"):
            alias = card.get(field) or ""
            if alias and alias != name:
                out.append((normalize_card_name(alias), _Tier.ALIAS))
    return out


class NameIndex(Mapping[str, dict]):
    """A card-name → value map whose keys AND lookups are NFKD-folded.

    ``idx.get("Lim-Dul's Vault")`` matches a ``Lim-Dûl's Vault`` record (and the
    diacritic spelling too) — the lookup folds the same way the keys were, so callers
    never fold by hand. Iteration yields the *folded* keys; read display names off the
    stored values (which keep their real diacritics), not the keys.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, dict] | None = None) -> None:
        self._data: dict[str, dict] = data if data is not None else {}

    def __getitem__(self, key: str) -> dict:
        return self._data[normalize_card_name(key)]

    # ``get`` is inherited from Mapping and folds through ``__getitem__``.

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and normalize_card_name(key) in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def build_name_index(
    cards: Iterable[dict | None],
    *,
    reduce: Callable[[dict, dict], dict] | None = None,
    value: Callable[[dict], dict] | None = None,
    prefilter: Callable[[dict], bool] | None = None,
) -> NameIndex:
    """Build a :class:`NameIndex` over *cards* with one consistent keying pass.

    For each card passing *prefilter*, every key from :func:`alias_keys` competes for
    its slot by tier (canonical beats face beats alias). Among cards claiming the same
    key at the same tier, *reduce(existing, new) -> keeper* picks the survivor — so a
    face key points at the *cheapest* printing of its multi-face card, matching that
    card's canonical key. ``reduce=None`` is first-seen. *value(card)* projects the
    stored payload at the end (default: the card record itself).
    """
    chosen: dict[str, dict] = {}
    tiers: dict[str, int] = {}
    for card in cards:
        if card is None:
            continue
        if prefilter is not None and not prefilter(card):
            continue
        for key, tier in alias_keys(card):
            rank = tier.value
            current = tiers.get(key)
            if current is None or rank < current:
                chosen[key] = card
                tiers[key] = rank
            elif rank == current and reduce is not None:
                chosen[key] = reduce(chosen[key], card)
            # a worse (higher) tier never overwrites a better one
    data = {k: value(c) for k, c in chosen.items()} if value else chosen
    return NameIndex(data)


def keep_cheaper(existing: dict, new: dict) -> dict:
    """Acquisition-cost reducer for paper: keep the cheaper USD printing. A *priced*
    printing always beats a price-less one (paper cards without a price are scarce, not
    free); among priced printings the lower wins; among price-less ones the first stays.
    """
    from mtg_utils.card_classify import extract_price

    new_price = extract_price(new)
    if new_price is None:
        return existing
    existing_price = extract_price(existing)
    if existing_price is None:
        return new
    return new if new_price < existing_price else existing
