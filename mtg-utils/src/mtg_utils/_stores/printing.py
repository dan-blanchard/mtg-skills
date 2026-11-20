"""Pinned printings: which store listings are the printing a want-list asked for.

A want-list line can pin a printing — "Daxos, Blessed by the Sun (plst) THB-9",
"Citizen (tfrc) 11 *F*". ``PrintingSpec`` answers, for one such line, whether a
store listing is that printing, by what the store says about it:

* **exact** — the listing names the set and collector number (TGP does).
* **equivalent** — the listing is another printing of the same card (oracle id:
  the same rules text, power/toughness, colors) with the same art and style: the
  same illustration, frame version, border, full-art flag, frame effects and
  visual promo treatment (a stamp, a foil treatment). The List's THB-9 Daxos and
  Theros Beyond Death's 9 are one card to look at.
* **set+style** — the store gives no collector number (Atomic Empire), so the
  listing is matched by its set and its variant labels ("Showcase", "Extended
  Art"); accepted only when every printing of the card in that set wearing those
  labels is an acceptable one.

The finish always has to agree: a foil request takes only foil listings.

Token records sit under their parent set in the card pool (TNCC's Elemental is
``ncc 18``) while want-lists and stores write the token set (``tncc``), so a
token printing answers to both codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._stores._common import Listing, PrintingRequest
from mtg_utils.names import normalize_card_name

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Promo types that change what a printing looks like: stamps, and the foil and
#: ink treatments. Distribution and marketing tags (``boosterfun``,
#: ``universesbeyond``, ``setpromo``, ``bundle``) don't.
_STAMPS = frozenset(
    {"stamped", "planeswalkerstamped", "datestamped", "promopack", "prerelease"}
)
_VISUAL_TREATMENTS = frozenset(
    {
        "serialized",
        "oilslick",
        "textured",
        "embossed",
        "gilded",
        "doublerainbow",
        "japanshowcase",
        "headliner",
        "poster",
        "scroll",
        "silverscroll",
        "portrait",
        "dossier",
        "magnified",
        "invisibleink",
        "concept",
        "sourcematerial",
        "schinesealtart",
        "thick",
    }
)

#: Atomic Empire's variant labels, as the printing traits they name.
_LABEL_TRAITS = {
    "showcase": "showcase",
    "extended art": "extendedart",
    "borderless": "borderless",
    "full art": "fullart",
    "retro frame": "retro",
    "retro": "retro",
    "promo pack": "promopack",
    "prerelease": "prerelease",
}
_SET_CODE_LABEL = re.compile(r"^[A-Z0-9]{2,5}$")
_NUMBER_LABEL = re.compile(r"^\d+$")
_TOKEN_LAYOUTS = frozenset({"token", "double_faced_token"})
_FINISH_PRICE_KEY = {"nonfoil": "usd", "foil": "usd_foil", "etched": "usd_etched"}


def _visual_promos(record: dict) -> frozenset[str]:
    return frozenset(
        t
        for t in record.get("promo_types") or ()
        if t in _STAMPS
        or t in _VISUAL_TREATMENTS
        or t.endswith("foil")
        or t.startswith("neonink")
    )


def style(record: dict) -> tuple:
    """What a printing looks like, beyond its art: frame version, border,
    full-art, frame effects (less ``etched``, a finish) and visual promos."""
    return (
        record.get("frame"),
        record.get("border_color"),
        bool(record.get("full_art")),
        frozenset(record.get("frame_effects") or ()) - {"etched"},
        _visual_promos(record),
    )


def traits(record: dict) -> frozenset[str]:
    """The printing traits a store's variant label can name (``_LABEL_TRAITS``),
    plus its foil treatments ("Halo Foil" names ``halofoil``)."""
    out: set[str] = set()
    effects = set(record.get("frame_effects") or ())
    promos = set(record.get("promo_types") or ())
    if "showcase" in effects:
        out.add("showcase")
    if "extendedart" in effects:
        out.add("extendedart")
    if record.get("border_color") == "borderless":
        out.add("borderless")
    if record.get("full_art"):
        out.add("fullart")
    if record.get("frame") in {"1993", "1997"} and "boosterfun" in promos:
        out.add("retro")
    out.update(promos & {"promopack", "prerelease"})
    out.update(t for t in promos if t.endswith("foil"))
    return frozenset(out)


def label_traits(labels: Iterable[str]) -> frozenset[str] | None:
    """A store's variant labels as printing traits, or None when a label names
    something this module can't read (the listing then matches nothing). A
    token's "created by ..." note, The List's origin set code ("THB") and a
    collector number are not traits."""
    out: set[str] = set()
    for raw in labels:
        label = raw.strip()
        low = label.lower()
        if (
            not label
            or low.startswith("created by")
            or _SET_CODE_LABEL.match(label)
            or _NUMBER_LABEL.match(label)
        ):
            continue
        if low in _LABEL_TRAITS:
            out.add(_LABEL_TRAITS[low])
        elif low.endswith(" foil"):
            out.add(low.replace(" ", ""))
        else:
            return None
    return frozenset(out)


def set_keys(record: dict) -> frozenset[str]:
    """The set codes a printing answers to: its own, and for a token stored
    under its parent set (``ncc``) the token set too (``tncc``)."""
    code = (record.get("set") or "").lower()
    if record.get("layout") in _TOKEN_LAYOUTS and code != "plst":
        return frozenset({code, f"t{code}"})
    return frozenset({code})


def _number(value: object) -> str:
    return str(value or "").strip().lower()


def _record_finishes(record: dict) -> frozenset[str]:
    return frozenset(record.get("finishes") or ("nonfoil",))


def listing_finish(listing: Listing) -> str:
    return listing.get("finish") or ("foil" if listing["foil"] else "nonfoil")


@dataclass(frozen=True)
class PrintingSpec:
    """One pinned printing and the printings that count as it.

    ``records`` is every printing of the card in the pool (tokens included);
    with none (a set newer than the card data) only the exact set and number
    match.
    """

    name: str
    request: PrintingRequest
    records: tuple[dict, ...] = ()
    exact_keys: frozenset[tuple[str, str]] = field(init=False)
    equivalent_keys: frozenset[tuple[str, str]] = field(init=False)
    acceptable: tuple[dict, ...] = field(init=False)

    def __post_init__(self) -> None:
        req_set = self.request["set"].lower()
        req_number = _number(self.request["collector_number"])
        finish = self.request["finish"]
        exact = next(
            (
                r
                for r in self.records
                if req_set in set_keys(r)
                and _number(r.get("collector_number")) == req_number
            ),
            None,
        )
        # The List's "THB-9" is a reprint of THB 9: when the pool lacks the
        # List printing itself, the original stands in for its art and style.
        reference = exact or self._list_origin(req_set, req_number)
        acceptable = [exact] if exact else []
        if reference is not None and reference.get("illustration_id"):
            acceptable += [
                r
                for r in self.records
                if r is not exact
                and r.get("illustration_id") == reference["illustration_id"]
                # The same game object too: one name and one art can be two
                # tokens (Bloomburrow Commander's Wolf has a dies trigger,
                # Double Masters' is vanilla; 19 such pairs, 2026-11).
                and r.get("oracle_id") == reference.get("oracle_id")
                and style(r) == style(reference)
                and finish in _record_finishes(r)
            ]
        object.__setattr__(self, "acceptable", tuple(acceptable))
        object.__setattr__(self, "exact_keys", frozenset({(req_set, req_number)}))
        object.__setattr__(
            self,
            "equivalent_keys",
            frozenset(
                (code, _number(r.get("collector_number")))
                for r in acceptable
                if r is not exact
                for code in set_keys(r)
            ),
        )

    def _list_origin(self, req_set: str, req_number: str) -> dict | None:
        if req_set != "plst" or "-" not in req_number:
            return None
        origin_set, _, origin_number = req_number.partition("-")
        return next(
            (
                r
                for r in self.records
                if origin_set in set_keys(r)
                and _number(r.get("collector_number")) == origin_number
            ),
            None,
        )

    @property
    def label(self) -> str:
        """The line as a want-list writes it: "Citizen (TFRC) 11 *F*"."""
        marker = {"foil": " *F*", "etched": " *E*"}.get(self.request["finish"], "")
        return (
            f"{self.name} ({self.request['set'].upper()}) "
            f"{self.request['collector_number']}{marker}"
        )

    def usd(self) -> float:
        """The cheapest price of an acceptable printing in the requested
        finish (the spill check's online proxy), 0.0 when none is priced."""
        key = _FINISH_PRICE_KEY[self.request["finish"]]
        prices = []
        for record in self.acceptable:
            raw = (record.get("prices") or {}).get(key)
            try:
                price = float(raw) if raw else 0.0
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                prices.append(price)
        return min(prices, default=0.0)

    def match(self, listing: Listing) -> str | None:
        """How *listing* is this printing — "exact", "equivalent",
        "set+style" — or None when it isn't."""
        if listing_finish(listing) != self.request["finish"]:
            return None
        listing_set = (listing.get("set_code") or "").lower()
        number = _number(listing.get("collector_number"))
        if number:
            if (listing_set, number) in self.exact_keys:
                return "exact"
            if (listing_set, number) in self.equivalent_keys:
                return "equivalent"
            return None
        return self._match_by_style(listing_set, listing.get("variant_labels") or [])

    def _match_by_style(self, listing_set: str, labels: list[str]) -> str | None:
        wanted = label_traits(labels)
        if wanted is None:
            return None
        numbers = {_number(x) for x in labels if _NUMBER_LABEL.match(x.strip())}
        finish = self.request["finish"]
        candidates = [
            r
            for r in self.records
            if listing_set in set_keys(r)
            and finish in _record_finishes(r)
            and traits(r) == wanted
            and (
                not numbers
                or _number(r.get("collector_number")).lstrip("0")
                in {n.lstrip("0") for n in numbers}
            )
        ]
        if not candidates and not self.records:
            # No card data for this card: the set alone, unlabelled, is the
            # best the store tells us — and the request's own set must match.
            return (
                "set+style"
                if (listing_set == self.request["set"] and not wanted)
                else None
            )
        accepted = {id(r) for r in self.acceptable}
        if not candidates or not all(id(r) in accepted for r in candidates):
            return None
        (exact_key,) = self.exact_keys
        pinned = all(
            exact_key[0] in set_keys(r)
            and _number(r.get("collector_number")) == exact_key[1]
            for r in candidates
        )
        return "set+style" if pinned else "equivalent"


def records_by_name(
    cards: Iterable[dict], names: Iterable[str]
) -> dict[str, list[dict]]:
    """Every printing (tokens included) of each name in *names*, keyed by the
    name as given; a two-faced card also answers to its front face."""
    wanted = {normalize_card_name(n): n for n in names}
    wanted.update(
        {normalize_card_name(n.split(" // ")[0]): n for n in names if " // " in n}
    )
    out: dict[str, list[dict]] = {n: [] for n in wanted.values()}
    for card in cards:
        name = card.get("name") or ""
        for key in {
            normalize_card_name(name),
            normalize_card_name(name.split(" // ")[0]),
        }:
            if key in wanted:
                out[wanted[key]].append(card)
                break
    return out
