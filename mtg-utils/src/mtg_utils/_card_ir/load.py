"""Runtime loader for the Card IR cache sidecar.

The sidecar is a JSON ``{version, phase_tag, cards: {oracle_id: Card.to_dict()}}``
written by ``_card_ir.build``. Consumers join their Scryfall record to the IR by
``oracle_id`` and read structured abilities instead of re-grepping oracle text.

An in-memory cache (keyed by path + mtime) makes repeated lookups in one process
free — a tune issues many searches, each of which wants the IR, so without this
we'd re-parse the sidecar every call (mirrors ``bulk_loader``'s rationale).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mtg_utils.card_ir import Card

# Bump when the sidecar payload shape OR projection CONTENT changes so old cached
# sidecars are rebuilt (production gates the rebuild on this version — a project.py
# projection change that doesn't bump it would be served stale; ADR-0027 β phase).
# v2: Effect.zones (directional zone refs) + Ability.condition (Condition node).
# v3: Trigger.zones (directional zone refs of a ChangeZone trigger).
# v4: _recover_library_zones — from:library on top-of-library cast_from_zone effects
#     (impulse_top_play / play_from_top).
# v5: _recover_edict_scope — promote scope=='any' sacrifice → each/opp from raw when
#     phase dropped the sacrificer scoping to a null controller (edict_matters).
# v6: _quantity recovers op="power" on a Ref→Power amount (phase folded it to a bare
#     op="count"); read by the damage_equal_power / creature_ping lanes (ADR-0027 β).
# v7: ModifyCost{Reduce} static → a category="cost_reduction" Effect (Goblin
#     Electromancer / Ruby Medallion); the cost_reduction lane reads it (ADR-0027 β).
# v8: exclude affected==SelfRef from the v7 cost_reduction projection (Cavern-Hoard
#     Dragon "this spell costs less" is a self-discount, not a build-around enabler;
#     rules-adjudicated CR 601.2f/118.7).
# v9: GrantAbility/GrantTrigger static over a creature board (controller you) or an
#     all-permanents/all-creatures set (controller any) → a board_grant Effect with
#     counter_kind="grant_ability"; the global_ability_grant lane reads it (the
#     QUOTED-ability discriminator, not a keyword anthem). ADR-0027 β. CR 113.3/604.3.
# v10: a characteristic-defining */* self-CDA static (SetDynamicPower/Toughness over
#     SelfRef, characteristic_defining=true) is re-surfaced as an `other` Effect that
#     supplement._CDA_PT structures into a `characteristic_pt` marker; the variable_pt
#     lane reads it (Nightmare/Pack Rat/Serra Avatar/Cultivator Colossus — phase
#     fully consumed the clause, so base_pt_set dropped it). ADR-0027 β. CR 604.3.
SIDECAR_VERSION = 10


def card_ir_dir() -> Path:
    """The Card IR cache root: ``$MTG_SKILLS_CACHE_DIR/card-ir`` or
    ``$HOME/.cache/mtg-skills/card-ir`` (mirrors ``_phase.cache_dir``)."""
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "card-ir"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "card-ir"


def sidecar_path() -> Path:
    return card_ir_dir() / "card-ir.json"


# oracle_id → Card, keyed by (path, mtime). Shared by reference; treat read-only.
_MEM_CACHE: dict[str, tuple[float, dict[str, Card]]] = {}


def clear_memory_cache() -> None:
    """Drop the in-memory cache (test hygiene)."""
    _MEM_CACHE.clear()


def load_card_ir(path: str | Path | None = None) -> dict[str, Card]:
    """Load the sidecar into an ``oracle_id`` → :class:`Card` map.

    Raises ``FileNotFoundError`` with an actionable message when the sidecar is
    absent (phase not built / ``build-card-ir`` not run), and ``ValueError`` when
    a present sidecar is the wrong on-disk version.
    """
    p = Path(path) if path else sidecar_path()
    if not p.exists():
        raise FileNotFoundError(
            f"Card IR sidecar not found at {p}. Build it with `build-card-ir` "
            "(requires phase's card-data.json — run `playtest-install-phase`)."
        )
    mtime = p.stat().st_mtime
    key = str(p)
    hit = _MEM_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]

    payload = json.loads(p.read_text())
    if payload.get("version") != SIDECAR_VERSION:
        raise ValueError(
            f"Card IR sidecar at {p} is version {payload.get('version')}, "
            f"expected {SIDECAR_VERSION}. Rebuild with `build-card-ir`."
        )
    cards = {oid: Card.from_dict(d) for oid, d in (payload.get("cards") or {}).items()}
    _MEM_CACHE[key] = (mtime, cards)
    return cards


def card_for(oracle_id: str, path: str | Path | None = None) -> Card | None:
    """Look up one card's IR by ``oracle_id`` (``None`` if absent)."""
    if not oracle_id:
        return None
    return load_card_ir(path).get(oracle_id)
