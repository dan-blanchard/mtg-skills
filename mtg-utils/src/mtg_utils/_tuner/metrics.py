"""The three diagnostic metrics + the Tier-2 flags + the severity-ranked Top issues.

Efficiency (Shape-aware curve/tempo — NOT per-card power, ADR-0009), Template deviation
(over the shared ``slot_budgets`` bands), and Focus (Engine-card concentration over the
deck's signal-derived avenues). Win-cons and protection are Shape-scaled advisory flags
(ADR-0024). Every readout is transparent (matching deck-forge's gate style); none is an
opaque score. ``top_issues`` ranks the findings by severity and is the single
ordering the swap engine acts on (deck-forge CONTEXT.md, "Tune").
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_utils._deck_forge.budgets import protects
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._tuner.classify import CardClass
from mtg_utils.theme_presets import get_preset

# Signal keys that mirror a hard-counted Spine role (ramp / draw / interaction). Not
# themes, so focus excludes their avenues: a "Ramp / big mana" avenue full of mana rocks
# and lands is scaffolding, not a lane the deck is built around.
_SPINE_AVENUE_KEYS = frozenset({"ramp_matters", "card_draw_engine", "removal_matters"})

# Shape → (lo, hi) nonland average-MV band; ~4.0 is the soft ceiling (waived when the
# deck cheats costs). Centred ~3.0 per the verified research.
_AVG_BANDS = {
    "aggro": (1.8, 2.8),
    "midrange": (2.5, 3.5),
    "control": (2.8, 3.8),
    "combo": (2.0, 3.2),
}
_AVG_CEILING = 4.0

# Shape → desired front-load (cmc<=2 nonland) and ramp, per 100 cards.
_FRONT_WANT = {"aggro": 18, "midrange": 14, "control": 10, "combo": 12}

# Shape → (min, max) dedicated closers (ADR-0024; floor ~3, archetype-scaled).
_WINCON_TARGET = {
    "aggro": (4, 6),
    "midrange": (3, 6),
    "control": (2, 4),
    "combo": (2, 3),
}

# Heuristic finisher oracle patterns (labeled heuristic; combos are the precise source).
_WINCON_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"wins? the game",
        r"loses? the game",
        r"an additional combat phase",
        r"extra combat",
        r"infinite",
        r"damage to each opponent equal",
        r"creatures you control get \+\d",
    )
]
_EVASION = ("flying", "menace", "trample", "can't be blocked", "shadow", "fear")


def _matches(card: dict, preset: str) -> bool:
    try:
        return get_preset(preset).matches(card)
    except KeyError:
        return False


def _scaled(value: int, deck_size: int) -> int:
    return round(value * deck_size / 100)


def _is_creature(card: dict) -> bool:
    return "creature" in (card.get("type_line") or "").lower()


def _power(card: dict) -> int:
    try:
        return int(card.get("power", 0))
    except (TypeError, ValueError):
        return 0


# ── Efficiency ────────────────────────────────────────────────────────────────


def efficiency(
    classes: Sequence[CardClass], *, shape: str, avg_cmc: float, deck_size: int
) -> dict:
    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    ramp_cards = [c.name for c in classes if "ramp" in c.roles]
    low_cards = [c.name for c in nonland if c.cmc <= 2.0]
    top_cards = [c.name for c in nonland if c.cmc >= 6.0]
    ramp, low, top = len(ramp_cards), len(low_cards), len(top_cards)
    cheats = sum(1 for c in classes if _matches(c.record, "reanimate")) >= 2

    lo, hi = _AVG_BANDS.get(shape, _AVG_BANDS["midrange"])
    if (avg_cmc > _AVG_CEILING and not cheats) or avg_cmc > hi + 0.3:
        avg_status = "top_heavy"
    else:
        avg_status = "ok"

    ramp_want = 12 if avg_cmc >= 3.3 else (9 if avg_cmc <= 2.6 else 10)
    ramp_want = _scaled(ramp_want, deck_size)
    ramp_status = "low" if ramp < ramp_want - 2 else "ok"

    front_want = _scaled(_FRONT_WANT.get(shape, 14), deck_size)
    front_status = "thin" if low < round(front_want * 0.7) else "ok"

    top_lo, top_hi = _scaled(2, deck_size), _scaled(8, deck_size)
    if top < top_lo:
        top_status = "thin"
    elif top > top_hi:
        top_status = "clogged"
    else:
        top_status = "ok"

    if avg_status == "top_heavy":
        verdict = "top-heavy"
    elif top_status == "clogged":
        verdict = "top-end clogged"
    elif top_status == "thin":
        verdict = "thin top-end"
    elif front_status == "thin":
        verdict = "thin early game"
    else:
        verdict = "ok"

    return {
        "verdict": verdict,
        "avg_mv": {"value": round(avg_cmc, 2), "band": [lo, hi], "status": avg_status},
        "ramp": {
            "have": ramp,
            "want": ramp_want,
            "status": ramp_status,
            "cards": ramp_cards,
        },
        "front_load": {
            "have": low,
            "want": front_want,
            "status": front_status,
            "cards": low_cards,
        },
        "top_end": {
            "have": top,
            "want": [top_lo, top_hi],
            "status": top_status,
            "cards": top_cards,
        },
        "cost_cheat_waiver": cheats,
    }


# ── Focus ─────────────────────────────────────────────────────────────────────


def focus(
    classes: Sequence[CardClass], *, deck_size: int, deck_signals: Sequence = ()
) -> dict:
    # Avenues that are really Spine roles (ramp/draw/removal) are not themes — exclude
    # them so the deck's mana base + scaffolding can't masquerade as its main lane.
    excluded = {
        spec.label
        for sig in deck_signals
        if sig.key in _SPINE_AVENUE_KEYS and (spec := spec_for(sig)) is not None
    }

    def themes(card: CardClass) -> list[str]:
        return [lbl for lbl in card.served if lbl not in excluded]

    nonland = [c for c in classes if c.bucket not in ("land", "commander")]
    engine = [c for c in classes if c.bucket == "engine"]
    engine_pool = len(engine)

    # Depth counts NONLAND supporters only (a land is mana base, never theme support) of
    # genuine theme avenues — engine cards + dual-purpose Spine cards that feed a theme.
    members: dict[str, list[str]] = {}
    for c in classes:
        if c.bucket == "land":
            continue
        for label in themes(c):
            members.setdefault(label, []).append(c.name)
    depth = {lbl: len(names) for lbl, names in members.items()}

    # Two-tier viability (research: 1 main + 1 *sub*-theme; a sub is shallower than the
    # main, so it gets a lower floor — not the same bar as the main).
    main_floor = max(1, _scaled(20, deck_size))
    sub_floor = max(1, _scaled(10, deck_size))
    candidates = sorted(
        (lbl for lbl, d in depth.items() if d >= sub_floor),
        key=lambda lbl: depth[lbl],
        reverse=True,
    )
    # Collapse near-duplicate avenues that are really one theme: drop a shallower avenue
    # ≥80% covered by a deeper one already kept (e.g. Spellslinger / Magecraft).
    viable: list[str] = []
    for lbl in candidates:
        s = set(members[lbl])
        if any(len(s & set(members[k])) / len(s) >= 0.8 for k in viable):
            continue
        viable.append(lbl)
    mains = [lbl for lbl in viable if depth[lbl] >= main_floor]
    subs = [lbl for lbl in viable if depth[lbl] < main_floor]

    # Emerging themes: a real-but-under-supported direction (emerging floor ≤ depth <
    # sub floor) the deck started but didn't commit to — flagged "commit more or cut"
    # rather than dropped as noise. Deduped against the viable themes (a subset of a
    # real theme is not its own emerging theme).
    emerging_floor = max(1, _scaled(5, deck_size))
    emerging: list[str] = []
    for lbl in sorted(depth, key=lambda x: depth[x], reverse=True):
        if not emerging_floor <= depth[lbl] < sub_floor:
            continue
        s = set(members[lbl])
        if any(len(s & set(members[k])) / len(s) >= 0.8 for k in viable + emerging):
            continue
        emerging.append(lbl)

    top2 = viable[:2]
    in_top2 = sum(1 for c in engine if set(top2).intersection(themes(c)))
    top2_share = round(in_top2 / engine_pool, 2) if engine_pool else 0.0

    filler_cards = [c.name for c in nonland if c.bucket == "filler"]
    filler = len(filler_cards)
    filler_rate = round(filler / max(1, len(nonland)), 2)

    engine_labels = {lbl for c in engine for lbl in themes(c)}
    stranded = sorted(lbl for lbl in engine_labels if 1 <= depth.get(lbl, 0) <= 2)

    spine_led_floor = max(1, _scaled(8, deck_size))
    if engine_pool < spine_led_floor:
        verdict = "SPINE-LED"
    elif len(viable) >= 3:
        # More than a main + a sub — too many directions competing for the engine slots.
        verdict = "SPREAD-THIN"
    elif viable:
        verdict = "FOCUSED"  # 1 main, or 1 main + 1 sub — the research ideal
    else:
        # A substantial engine pool that coheres into no theme at all is scattered.
        verdict = "SPREAD-THIN"

    return {
        "verdict": verdict,
        "engine_pool": engine_pool,
        "viable_avenues": [
            {
                "label": lbl,
                "depth": depth[lbl],
                "cards": members[lbl],
                "tier": "main" if depth[lbl] >= main_floor else "sub",
            }
            for lbl in viable
        ],
        "mains": mains,
        "subs": subs,
        "emerging": [
            {"label": lbl, "depth": depth[lbl], "cards": members[lbl]}
            for lbl in emerging
        ],
        "main_floor": main_floor,
        "sub_floor": sub_floor,
        "top2_concentration": top2_share,
        "filler": filler,
        "filler_rate": filler_rate,
        "filler_cards": filler_cards,
        "stranded_avenues": stranded,
        "_depth": depth,
    }


# ── Template deviation (over the shared slot_budgets) ───────────────────────────


def template_deviation(budgets: dict) -> dict:
    short = {r: b for r, b in budgets.items() if b["deviation"] < 0}
    over = {r: b for r, b in budgets.items() if b["deviation"] > 0}
    return {
        "verdict": "on-template" if not short and not over else "off-template",
        "short": short,
        "over": over,
        "budgets": budgets,
    }


# ── Tier-2 advisory flags ──────────────────────────────────────────────────────


def _is_wincon_card(card: dict) -> bool:
    text = card.get("oracle_text") or ""
    if any(p.search(text) for p in _WINCON_PATTERNS):
        return True
    if _is_creature(card) and _power(card) >= 6:
        low = text.lower()
        return any(e in low for e in _EVASION)
    return False


def win_conditions(
    classes: Sequence[CardClass], *, shape: str, combo_count: int
) -> dict:
    cards = sorted({c.name for c in classes if _is_wincon_card(c.record)})
    count = len(cards) + combo_count
    lo, hi = _WINCON_TARGET.get(shape, (3, 6))
    return {
        "count": count,
        "from_combos": combo_count,
        "cards": cards,  # the heuristic finisher cards (combos add to count, not names)
        "target": [lo, hi],
        "status": "low" if count < lo else "ok",
    }


def protection(classes: Sequence[CardClass], *, shape: str, deck_size: int) -> dict:
    cards = [c.name for c in classes if protects(c.record)]
    equip_aura = sum(
        1 for c in classes if _matches(c.record, "equip") or _matches(c.record, "auras")
    )
    voltron = equip_aura >= _scaled(4, deck_size)
    wants = shape in ("combo", "control") or voltron
    target = _scaled(5, deck_size) if wants else 0
    return {
        "count": len(cards),
        "cards": cards,
        "target": target,
        "wants_protection": wants,
        "voltron": voltron,
        "status": "low" if wants and len(cards) < target else "ok",
    }


# ── Commander fit ──────────────────────────────────────────────────────────────


def commander_fit(classes: Sequence[CardClass], focus_result: dict) -> dict:
    commanders = [c for c in classes if c.bucket == "commander"]
    viable = {a["label"] for a in focus_result["viable_avenues"]}
    served = {lbl for c in commanders for lbl in c.served}
    served_viable = sorted(served & viable)
    fit = round(len(served_viable) / len(viable), 2) if viable else 1.0
    # Only meaningful once the deck has ≥2 viable avenues; a single-avenue deck can't be
    # "built for a different commander" on this signal.
    misfit = len(viable) >= 2 and fit < 0.5
    return {
        "fit": fit,
        "serves_viable": served_viable,
        "viable_count": len(viable),
        "misfit": misfit,
    }


# ── Top issues (the severity-ranked ordering the swap engine acts on) ───────────


def top_issues(
    *,
    efficiency_r: dict,
    focus_r: dict,
    template_r: dict,
    wincons_r: dict,
    protection_r: dict,
    commander_r: dict,
) -> list[dict]:
    """Rank findings by severity. Each issue carries a ``kind`` the swap engine maps
    to a cut/add action; ``commander_misfit`` is advisory only (no swap fixes it)."""
    issues: list[dict] = []

    for role, b in template_r["short"].items():
        deficit = -b["deviation"]
        issues.append(
            {
                "kind": "role_short",
                "role": role,
                "severity": deficit,
                "message": f"{role.replace('_', ' ')} short by {deficit} "
                f"({b['current']}/{b['min']}-{b['max']})",
            }
        )
    for role, b in template_r["over"].items():
        issues.append(
            {
                "kind": "role_over",
                "role": role,
                "severity": b["deviation"],
                "message": f"{role.replace('_', ' ')} over by {b['deviation']} "
                f"({b['current']}/{b['min']}-{b['max']})",
            }
        )

    for e in focus_r.get("emerging", []):
        issues.append(
            {
                "kind": "under_supported_theme",
                "label": e["label"],
                "severity": 2,
                "message": f"{e['label']} ({e['depth']}) is an under-supported theme — "
                "commit more or cut it",
            }
        )

    if focus_r["verdict"] == "SPREAD-THIN":
        issues.append(
            {
                "kind": "spread_thin",
                "severity": 4 + len(focus_r["stranded_avenues"]),
                "message": f"spread thin — {len(focus_r['viable_avenues'])} viable "
                f"avenues, {focus_r['filler']} filler",
            }
        )

    if wincons_r["status"] == "low":
        issues.append(
            {
                "kind": "wincon_short",
                "severity": 3 + (wincons_r["target"][0] - wincons_r["count"]),
                "message": f"≈{wincons_r['count']} closers — "
                f"usually wants {wincons_r['target'][0]}-{wincons_r['target'][1]}",
            }
        )

    if protection_r["status"] == "low":
        issues.append(
            {
                "kind": "protection_short",
                "severity": 2 + (protection_r["target"] - protection_r["count"]),
                "message": f"{protection_r['count']} protection — "
                f"this Shape usually wants ~{protection_r['target']}",
            }
        )

    if efficiency_r["verdict"] != "ok":
        issues.append(
            {
                "kind": "efficiency",
                "subkind": efficiency_r["verdict"],
                "severity": 3,
                "message": f"curve: {efficiency_r['verdict']}",
            }
        )

    if commander_r["misfit"]:
        issues.append(
            {
                "kind": "commander_misfit",
                "severity": 5,
                "message": "commander serves "
                f"{len(commander_r['serves_viable'])}/{commander_r['viable_count']} "
                "viable avenues — the deck may be built for a different commander",
            }
        )

    issues.sort(key=lambda i: i["severity"], reverse=True)
    return issues
