"""Production wiring: build a ``ForgeState`` backed by real Scryfall bulk data.

If no bulk data is on disk, the state degrades to an agent-less, search-disabled
mode (``bulk_available=False``) so the hub still starts and the search endpoint can
fail loudly with a "run download-bulk" message rather than silently returning empty.
"""

from __future__ import annotations

import functools
import os
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from mtg_utils import card_search, combo_search, mark_owned
from mtg_utils._deck_forge import collection
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils._name_index import NameIndex, build_name_index, keep_cheaper
from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards
from mtg_utils.card_search import SKIP_LAYOUTS
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.names import build_name_alias_map


def _combos(deck: dict, by_name: Mapping[str, dict]) -> dict:
    # Build a HydratedDeck so combo_search can validate template requirements
    # (e.g. "a Persist Creature") against the deck — without records, near-miss
    # detection falls back to counting named cards only and over-reports near-misses.
    return combo_search.combo_search(HydratedDeck.from_parsed(deck, by_name))


def build_object_resolver(cards: list[dict]) -> Callable[[str], dict | None]:
    """A name → card lookup for *folded objects* (ADR-0025): the Dungeon cards a
    commander ventures into and the Emblem-typed objects it brings in (the Ring,
    "The Ring // The Ring Tempts You"). These are deliberately excluded from
    `build_by_name` (you can't add one to a deck), so signal-extraction folding needs
    this separate raw-bulk lookup. Keyed by full name AND DFC front-face name, so a
    rules-fixed fold can resolve "The Ring" / "Undercity". Tiny (~dozen objects)."""
    # Meld results are addable legendary creatures (also in `by_name`), but the folder
    # only gets THIS resolver, so index them here too — identified by appearing as a
    # `meld_result` component in some card's all_parts (Bruna → Brisela).
    meld_results = {
        p.get("name")
        for c in cards
        if isinstance(c, dict)
        for p in (c.get("all_parts") or [])
        if p.get("component") == "meld_result" and p.get("name")
    }
    objects: dict[str, dict] = {}
    for c in cards:
        if not isinstance(c, dict):
            continue
        tl = (c.get("type_line") or "").lower()
        name = c.get("name") or ""
        if not name or (
            "dungeon" not in tl and "emblem" not in tl and name not in meld_results
        ):
            continue
        objects.setdefault(name, c)
        objects.setdefault(name.split(" // ")[0], c)  # front-face: The Ring, Undercity
    return objects.get


def build_printings_index(
    cards: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Index EVERY legal printing for the printing picker: ``oracle_id → [records]``
    (newest set first) plus ``printing id → record``. Unlike ``build_by_name`` (which
    folds to the cheapest printing), this keeps them all so a card's alternate sets/arts
    are enumerable. Same prefilter as ``build_by_name`` (drop token/memorabilia/skip
    layouts) so the picker only ever offers addable printings."""
    by_oracle: dict[str, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        if card.get("layout") in SKIP_LAYOUTS or card.get("set_type") in (
            "token",
            "memorabilia",
        ):
            continue
        oracle_id, printing_id = card.get("oracle_id"), card.get("id")
        if not oracle_id or not printing_id:
            continue
        by_oracle.setdefault(oracle_id, []).append(card)
        by_id[printing_id] = card
    for prints in by_oracle.values():
        prints.sort(key=lambda r: r.get("released_at") or "", reverse=True)
    return by_oracle, by_id


def build_by_name(cards: list[dict]) -> NameIndex:
    """Index real cards by name (NFKD-folded, every DFC face + Arena alias, via the
    shared name-index core), deduped to the cheapest printing — so a searchable card is
    always addable and hydrates with matching art/price. Folding makes lookups
    case- and diacritic-robust, so this no longer needs proper-case keys to match
    search output (which an earlier hand-rolled version did)."""
    return build_name_index(
        cards,
        reduce=keep_cheaper,
        prefilter=lambda card: (
            card.get("layout") not in SKIP_LAYOUTS
            and card.get("set_type") not in ("token", "memorabilia")
        ),
    )


def _deck_forge_dir() -> Path:
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "mtg-skills"
    return root / "deck-forge"


def _builds_dir() -> Path:
    return _deck_forge_dir() / "builds"


def resume_or_new(store: BuildStore, fmt: str) -> tuple[DeckSession, str, str]:
    """Resume the most recent saved build, or start a fresh one. Returns
    (session, build_id, build_name). Auto-resume means relaunching continues your
    deck instead of minting a new 'Untitled' every time."""
    builds = store.list()  # newest first
    if builds:
        record = store.load(builds[0]["id"])
        if record is not None:
            return (
                DeckSession.from_deck_dict(record.get("deck") or {}),
                record.get("id", builds[0]["id"]),
                record.get("name", "Untitled"),
            )
    return DeckSession(fmt), uuid.uuid4().hex[:8], "Untitled"


def _no_search(**_: object) -> list[dict]:
    return []


def _load_collections(
    store: CollectionStore,
    name_aliases: dict[str, str] | None = None,
) -> tuple[dict[str, dict], dict[str, tuple]]:
    """Load both Collection slots and precompute each slot's ownership lookup once, so a
    per-snapshot ownership check stays O(deck size) (ADR-0018). ``name_aliases`` (built
    from bulk) threads Arena printed_name / flavor_name matching into the lookup."""
    # Drop quantity-0 (un-owned / wishlist) rows up front so size, ownership, and
    # discovery all see owned-only — even for collections saved before this rule.
    collections = {
        slot: collection.owned_only(pile) for slot, pile in store.load().items()
    }
    index = {
        slot: mark_owned.owned_lookup(pile, name_aliases=name_aliases or None)
        for slot, pile in collections.items()
    }
    return collections, index


def _ensure_sidecar(
    *,
    loader: Callable[[], object],
    builder: Callable[[], tuple[Path, dict]],
    label: str,
    build_cmd: str,
) -> bool:
    """Shared ensure-idempotent-or-build machinery for both sidecar flavors
    (ADR-0027 legacy / ADR-0035 crosswalk). ``loader`` raises ``FileNotFoundError``
    (absent) / ``ValueError`` (stale on-disk version) exactly like the sidecar
    loaders it wraps; a clean load means nothing to do. A build failure (no
    phase card-data reachable) warns loudly and returns ``False`` — NON-BLOCKING,
    never a hard crash."""
    from mtg_utils._deck_forge.signals import MIGRATED_KEYS

    try:
        loader()  # present + current version → nothing to do (idempotent)
    except FileNotFoundError:
        reason = "missing"  # absent sidecar — first run / never built
    except ValueError:
        reason = "stale"  # present but wrong on-disk version — phase/schema bump
    else:
        return True

    try:
        _out, stats = builder()
    except (FileNotFoundError, RuntimeError):
        # card-data couldn't be obtained (download failed / unreachable) → the
        # sidecar can't be built. Do NOT silently degrade: name the cost (N
        # migrated lanes) and the fix.
        print(
            f"deck-forge: WARNING — {label}Card IR sidecar unavailable "
            f"({len(MIGRATED_KEYS)} migrated signal lanes degraded). "
            f"card-data download failed; re-run `{build_cmd}` with network "
            "access. Building continues; those lanes stay dark until then.",
            file=sys.stderr,
        )
        return False
    else:
        print(
            f"deck-forge: built {label}Card IR sidecar ({reason}) — "
            f"{stats['cards']} cards, phase {stats['phase_tag']}.",
            file=sys.stderr,
        )
        return True


def ensure_crosswalk_card_ir() -> bool:
    """Ensure the ADR-0035 crosswalk-backed Card IR sidecar exists at launch,
    building it if absent/stale — the Stage-4 default production build
    (ADR-0039 task #80 step 4).

    ``_ir_lookup.ir_for`` (Seam B — ``cut_check`` / ``ranking`` / ``budgets`` /
    the engine / ``_tuner`` bracket-metrics-tune, plus the deck-signals /
    deck-rank / deck-tune CLIs) reads THIS sidecar whenever the crosswalk flag
    is ON (the default): with no sidecar it returns ``None`` per card rather
    than silently cross-wiring to the legacy sidecar's differently-built Cards.
    This ensure pays the build cost once at launch (mirrors the
    ``download-bulk`` ensure) so the common case never leaves Seam B dark.

    IDEMPOTENT + fast: a right-on-disk-version sidecar is a single
    ``load_crosswalk_card_ir`` (memoized) and returns ``True`` without
    rebuilding. A missing/stale sidecar is rebuilt from phase's
    ``card-data.json`` via ``build-card-ir-crosswalk``. When phase isn't
    installed, it CANNOT be built — so we surface a loud, actionable warning
    naming the degraded lanes and proceed NON-BLOCKING (returns ``False``).
    Returns whether the sidecar is present after the call."""
    from mtg_utils._card_ir.build import build_crosswalk_sidecar
    from mtg_utils._card_ir.load import load_crosswalk_card_ir

    return _ensure_sidecar(
        loader=load_crosswalk_card_ir,
        builder=build_crosswalk_sidecar,
        label="crosswalk ",
        build_cmd="build-card-ir-crosswalk",
    )


def ensure_legacy_card_ir() -> bool:
    """Ensure the LEGACY (project.py) Card IR sidecar exists — the dependency
    of the ``MTG_SKILLS_CROSSWALK_SIGNALS=0`` revert path (ADR-0027, pre-dates
    ADR-0035). Kept alongside :func:`ensure_crosswalk_card_ir` so the revert
    path stays byte-identical to before the Stage-4 flip; steps 5-7 of the
    ADR-0039 deletion retire this once the legacy sidecar itself goes."""
    from mtg_utils._card_ir.build import build_sidecar
    from mtg_utils._card_ir.load import load_card_ir

    return _ensure_sidecar(
        loader=load_card_ir,
        builder=build_sidecar,
        label="",
        build_cmd="build-card-ir",
    )


def ensure_card_ir() -> bool:
    """Ensure the Card IR sidecar the crosswalk flag currently selects exists
    at launch (ADR-0027; ADR-0039 task #80 step 4).

    Every existing call site (``default_state``, and the ``deck-signals`` /
    ``deck-rank`` / ``deck-tune`` CLIs) calls this ONE function; which sidecar
    it builds is decided by
    :func:`~mtg_utils._deck_forge._ir_lookup.crosswalk_enabled` — the
    crosswalk-backed sidecar by default (Stage-4), the legacy sidecar only
    under the explicit ``MTG_SKILLS_CROSSWALK_SIGNALS=0`` revert. Returns
    whether the selected sidecar is present after the call."""
    from mtg_utils._deck_forge._ir_lookup import crosswalk_enabled

    if crosswalk_enabled():
        return ensure_crosswalk_card_ir()
    return ensure_legacy_card_ir()


def default_state(fmt: str = "commander") -> ForgeState:
    """Build the live backend state, loading bulk data when available."""
    ensure_card_ir()  # build/refresh the Card IR sidecar (ADR-0027); never blocks
    store = BuildStore(_builds_dir())
    session, build_id, build_name = resume_or_new(store, fmt)
    collection_store = CollectionStore(_deck_forge_dir() / "collection.json")
    bulk_path = default_bulk_path()
    by_name: Mapping[str, dict] = {}
    search = _no_search
    available = False
    object_resolver: Callable[[str], dict | None] | None = None
    printings_by_oracle: dict[str, list[dict]] = {}
    printing_by_id: dict[str, dict] = {}
    # Built from bulk so the Collection's ownership matching honors Arena printed_name /
    # flavor_name aliases (ADR-0018). Empty without bulk → DFC-only matching (fine).
    name_aliases: dict[str, str] = {}
    if bulk_path is not None and bulk_path.exists():
        cards = load_bulk_cards(bulk_path)
        by_name = build_by_name(cards)
        object_resolver = build_object_resolver(cards)
        printings_by_oracle, printing_by_id = build_printings_index(cards)

        # partial keeps search_cards's typed keyword signature (a `**kwargs:
        # object` wrapper would widen every arg to `object` and fail the checker).
        search = functools.partial(card_search.search_cards, bulk_path)

        name_aliases = build_name_alias_map(bulk_path)
        available = True

    collections, collection_index = _load_collections(collection_store, name_aliases)

    return ForgeState(
        by_name=by_name,
        search_fn=search,
        session=session,
        bulk_available=available,
        combos_fn=lambda deck: _combos(deck, by_name),
        store=store,
        build_id=build_id,
        build_name=build_name,
        collection_store=collection_store,
        collections=collections,
        collection_index=collection_index,
        name_aliases=name_aliases,
        bulk_path=bulk_path if available else None,
        object_resolver=object_resolver,
        printings_by_oracle=printings_by_oracle,
        printing_by_id=printing_by_id,
    )
