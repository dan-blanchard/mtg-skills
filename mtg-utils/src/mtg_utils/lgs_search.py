"""lgs-search orchestrator CLI.

Workflow: input → LGS sweep → allocate → online optimize → confirm →
build carts → handoff. See specs/2026-05-04-lgs-search-design.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from mtg_utils._sidecar import atomic_write_json
from mtg_utils._stores._common import Listing
from mtg_utils.names import normalize_card_name

BASIC_LAND_NAMES = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"},
)


class NeededCard(TypedDict):
    card_name: str
    qty: int


def _parse_text_line(line: str) -> NeededCard | None:
    from mtg_utils.parse_deck import _strip_set_code

    line = line.strip()
    if not line or line.startswith(("#", "//")):
        return None
    parts = line.split(maxsplit=1)
    if len(parts) == 1:
        return NeededCard(card_name=_strip_set_code(parts[0]), qty=1)
    head, rest = parts
    if head.rstrip("xX").isdigit():
        qty = int(head.rstrip("xX"))
        return NeededCard(card_name=_strip_set_code(rest.strip()), qty=qty)
    return NeededCard(card_name=_strip_set_code(line), qty=1)


def _read_text_list(path: Path) -> list[NeededCard]:
    cards: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_text_line(line)
        if parsed is None:
            continue
        cards[parsed["card_name"]] = cards.get(parsed["card_name"], 0) + parsed["qty"]
    return [NeededCard(card_name=n, qty=q) for n, q in cards.items()]


def _read_deck_json(path: Path) -> list[NeededCard]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cards: dict[str, int] = {}
    for entry in data.get("commanders") or []:
        # parse-deck emits [{"name", "quantity"}]; tolerate bare strings too.
        if isinstance(entry, str):
            cards[entry] = cards.get(entry, 0) + 1
        else:
            name = entry["name"]
            qty = int(entry.get("quantity", entry.get("qty", 1)))
            cards[name] = cards.get(name, 0) + qty
    for entry in (data.get("cards") or []) + (data.get("sideboard") or []):
        name = entry["name"]
        qty = int(entry.get("quantity", entry.get("qty", 1)))
        cards[name] = cards.get(name, 0) + qty
    return [NeededCard(card_name=n, qty=q) for n, q in cards.items()]


def _looks_like_json(path: Path) -> bool:
    if path.suffix.lower() == ".json":
        return True
    head = path.read_text(encoding="utf-8", errors="ignore")[:64].lstrip()
    return head.startswith(("{", "["))


def _subtract_collection(
    cards: list[NeededCard],
    collection_path: Path,
) -> list[NeededCard]:
    coll = json.loads(collection_path.read_text(encoding="utf-8"))
    if isinstance(coll, dict):
        owned: dict[str, int] = {k: int(v) for k, v in coll.items()}
    else:
        owned = {}
        for row in coll:
            name = row.get("name")
            if not name:
                continue
            owned[name] = owned.get(name, 0) + int(row.get("qty", 1))
    result: list[NeededCard] = []
    for c in cards:
        remaining = c["qty"] - owned.get(c["card_name"], 0)
        if remaining > 0:
            result.append(NeededCard(card_name=c["card_name"], qty=remaining))
    return result


def resolve_input(
    input_path: Path,
    *,
    collection_path: Path | None,
    include_basics: bool,
) -> tuple[list[NeededCard], dict[str, int]]:
    """Resolve input → (cards-to-buy, basic-lands-needed-summary).

    Accepts either a parsed-deck JSON (`{"commanders": [...], "cards": [...],
    "sideboard": [...]}`) or a plain text list (one entry per line, optional
    `Nx ` or `N ` quantity prefix). Mainboard + sideboard are summed. If
    `collection_path` points at a JSON file mapping card name → owned qty
    (or a list of `{"name": ..., "qty": ...}` rows), owned copies are
    subtracted before returning. Basic lands are filtered out and surfaced
    in the second return value unless `include_basics` is True. Snow basics
    are not filtered.
    """
    if _looks_like_json(input_path):
        raw = _read_deck_json(input_path)
    else:
        raw = _read_text_list(input_path)
    if collection_path:
        raw = _subtract_collection(raw, collection_path)
    if include_basics:
        return raw, {}
    basics: dict[str, int] = {}
    cards: list[NeededCard] = []
    for c in raw:
        if c["card_name"] in BASIC_LAND_NAMES:
            basics[c["card_name"]] = basics.get(c["card_name"], 0) + c["qty"]
        else:
            cards.append(c)
    return cards, basics


def summarize_basics(basics: dict[str, int]) -> str:
    if not basics:
        return ""
    lines = [f"  - {qty}x {name}" for name, qty in sorted(basics.items())]
    return "Basic lands needed (not searched):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: per-card allocation
# ---------------------------------------------------------------------------


class SearchResultRow(TypedDict):
    card_name: str
    qty: int
    tgp: Listing | None
    atomic_empire: Listing | None
    scryfall_usd: float


class AllocatedCard(TypedDict):
    card_name: str
    qty: int
    store: str  # "tgp" | "atomic_empire" | "online"
    listing: Listing | None  # None for online (resolved in Step 4)


@dataclass(frozen=True)
class AllocationConfig:
    lgs_online_threshold_pct: float
    lgs_online_threshold_usd: float
    consolidate_threshold_pct: float
    consolidate_threshold_usd: float


# TODO: replace with `_stores.LGS_STORES` once Task 12 wires the registry.
_LGS_KEYS = ("tgp", "atomic_empire")


def _spill_triggered(
    cheapest_lgs: float,
    online_proxy: float,
    cfg: AllocationConfig,
) -> bool:
    # OR semantics intentional; see specs/2026-05-04-lgs-search-design.md
    # "Default thresholds". Trivially-cheap cards may spill on the pct branch
    # alone — accepted as noise.
    if cheapest_lgs <= 0:
        return False
    if online_proxy <= 0:
        # Unknown online price (lookup miss / no Scryfall data). We have no
        # signal to spill on; keep the card at the LGS.
        return False
    pct_save = (cheapest_lgs - online_proxy) / cheapest_lgs * 100
    usd_save = cheapest_lgs - online_proxy
    return (
        pct_save >= cfg.lgs_online_threshold_pct
        or usd_save >= cfg.lgs_online_threshold_usd
    )


def _close_enough(price_a: float, price_b: float, cfg: AllocationConfig) -> bool:
    # OR semantics intentional; "close" means within EITHER threshold so the
    # consolidation tie-break fires on small differences regardless of scale.
    diff = abs(price_a - price_b)
    cheaper = min(price_a, price_b)
    pct = (diff / cheaper * 100) if cheaper > 0 else 0
    return diff <= cfg.consolidate_threshold_usd or pct <= cfg.consolidate_threshold_pct


def allocate(
    rows: list[SearchResultRow],
    cfg: AllocationConfig,
) -> list[AllocatedCard]:
    """Step 3 of the workflow. Assign each (card, qty) to a store or split.

    Per-card decision tree:
      1. Compute the cheapest in-stock LGS candidate.
      2. If online (Scryfall USD proxy) is much cheaper than the cheapest LGS
         (per cfg's pct/usd thresholds), spill the whole card line to "online".
      3. Otherwise pick cheapest LGS. If both LGS are "close" by cfg's
         consolidate thresholds, prefer the LGS with the higher running cart
         total to minimize trips.
      4. If chosen store can't fill the requested qty, fall through to the
         next-cheapest store; residual that no store can fill goes online.
    """
    running_totals: dict[str, float] = dict.fromkeys(_LGS_KEYS, 0.0)
    out: list[AllocatedCard] = []

    for row in rows:
        candidates = {k: row[k] for k in _LGS_KEYS if row[k] is not None}
        sorted_keys = sorted(candidates, key=lambda k: candidates[k]["price"])

        cheapest_lgs = (
            candidates[sorted_keys[0]]["price"] if sorted_keys else float("inf")
        )

        if _spill_triggered(cheapest_lgs, row["scryfall_usd"], cfg):
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="online",
                    listing=None,
                )
            )
            continue

        if not sorted_keys:
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=row["qty"],
                    store="online",
                    listing=None,
                )
            )
            continue

        # Trip-consolidation tie-break: among LGS prices that are "close",
        # prefer the store with the higher running total so far.
        if len(sorted_keys) > 1:
            a, b = sorted_keys[0], sorted_keys[1]
            if (
                _close_enough(candidates[a]["price"], candidates[b]["price"], cfg)
                and running_totals[b] > running_totals[a]
            ):
                sorted_keys = [b, a]

        # Quantity-aware fill across stores
        remaining = row["qty"]
        for key in sorted_keys:
            if remaining <= 0:
                break
            avail = candidates[key]["qty_available"]
            take = min(avail, remaining)
            if take <= 0:
                continue
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=take,
                    store=key,
                    listing=candidates[key],
                )
            )
            running_totals[key] += take * candidates[key]["price"]
            remaining -= take

        if remaining > 0:
            out.append(
                AllocatedCard(
                    card_name=row["card_name"],
                    qty=remaining,
                    store="online",
                    listing=None,
                )
            )

    return out


def assert_no_duplicates_invariant(
    needed: list[NeededCard],
    allocated: list[AllocatedCard],
) -> None:
    """Each (card, copy) is assigned to exactly one store. Sum-of-qtys per
    card name must equal the requested qty.
    """
    needed_qty = {c["card_name"]: c["qty"] for c in needed}
    actual: dict[str, int] = {}
    for a in allocated:
        actual[a["card_name"]] = actual.get(a["card_name"], 0) + a["qty"]
    if needed_qty != actual:
        diff = {
            k: (needed_qty.get(k, 0), actual.get(k, 0))
            for k in set(needed_qty) | set(actual)
            if needed_qty.get(k, 0) != actual.get(k, 0)
        }
        msg = f"allocation invariant violated: needed_vs_actual={diff!r}"
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Sidecar I/O and resume rules
# ---------------------------------------------------------------------------

SIDECAR_VERSION = 1


class PhaseProgress(TypedDict, total=False):
    status: Literal["pending", "partial", "complete"]
    items_added: int
    remaining: list


class Sidecar(TypedDict, total=False):
    version: int
    generated_at: str
    input_hash: str
    phase: Literal[
        "search_complete",
        "allocation_complete",
        "cart_build_in_progress",
        "done",
    ]
    phase_progress: dict[str, PhaseProgress]
    allocation: list[dict]
    online_optimizer_results: dict | None
    unfindable: list[str]
    basic_lands_needed: dict[str, int]


def compute_input_hash(cards: list[dict]) -> str:
    """SHA-256 over the canonicalized card list. Order- and case-independent.

    Card names are normalized via `mtg_utils.names.normalize_card_name`
    (NFKD ASCII-fold + lowercase) before hashing so cosmetic edits to the
    deck input (re-casing, whitespace) don't trip the --resume hash gate.
    """
    canon = sorted((normalize_card_name(c["card_name"]), int(c["qty"])) for c in cards)
    payload = json.dumps(canon, ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_sidecar(path: Path, sc: Sidecar) -> None:
    """Atomic-rename write so concurrent readers can't see a partial file.

    Delegates to the shared `atomic_write_json` helper, which uses a
    per-call NamedTemporaryFile so concurrent writers don't collide on
    the same `.tmp` name.
    """
    atomic_write_json(path, sc)


def load_sidecar(path: Path) -> Sidecar:
    sc = json.loads(path.read_text(encoding="utf-8"))
    if sc.get("version") != SIDECAR_VERSION:
        msg = (
            f"unsupported sidecar version {sc.get('version')};"
            f" expected {SIDECAR_VERSION}"
        )
        raise ValueError(msg)
    return sc


def assert_hash_matches(*, sidecar: Sidecar, cards: list[dict]) -> None:
    """Reject ``--resume`` if the input deck has changed since sidecar was written."""
    expected = compute_input_hash(cards)
    if sidecar.get("input_hash") != expected:
        msg = (
            f"input hash mismatch: sidecar={sidecar.get('input_hash')} "
            f"current={expected}"
        )
        raise ValueError(msg)


def next_phase_actions(sc: Sidecar) -> list[str]:
    """Given a sidecar's phase, return the list of remaining workflow steps."""
    phase = sc["phase"]
    if phase == "search_complete":
        return ["allocate", "confirm", "build_carts", "handoff"]
    if phase == "allocation_complete":
        return ["confirm", "build_carts", "handoff"]
    if phase == "cart_build_in_progress":
        return ["resume_carts", "handoff"]
    if phase == "done":
        return []
    msg = f"unknown sidecar phase {phase!r}"
    raise ValueError(msg)
